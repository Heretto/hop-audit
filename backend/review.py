"""Agent review: the Readability Reviewer and SEO Analyst read each page on
its own and report findings. HOP Audit's own checks (``analysis.py``) give
them the numbers; the agents explain them, propose fixes and apply the
site's focus. Links need no agent: ``links.py`` checks them and proposes the
fix. Content integrity (``integrity.py``) uses the same call machinery with
batches, since it compares articles with each other.

Each agent is a hop-core agent: its context files, references and feedback
memory form the system prompt, its AI configuration (a credential) the model.
Every request carries the site's standing focus and the run's focus. Agents
answer in JSON; findings are validated, and a quote that isn't on the page is
removed rather than shown, because a wrong quote costs more than none.
"""

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import httpx
from hop_core.agents import AgentDefinition, AgentRequest, AgentRunner, AiProviderError, CredentialAiService, providers
from hop_core.core.security import decrypt_credentials
from hop_core.models.agent import Agent
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from models import AgentFinding, AuditRun, Page

AGENT_CONCURRENCY = 4  # pages under review at once, per agent
TEXT_LIMIT = 12000  # characters of page text sent for readability review
SEO_TEXT_LIMIT = 1200  # enough to draft a description from
# Reply budgets (max_tokens). Reasoning models think inside this budget, so it
# must cover thinking as well as the JSON. A reply that runs out of room is
# asked again with double the budget, up to the ceiling; the agent keeps the
# budget that worked for the rest of the run. max_tokens is a cap, not a charge.
REPLY_BUDGET = {"readability": 8192, "seo": 8192, "content_integrity": 16384}
MAX_REPLY_BUDGET = 65536
CUT_OFF = {"max_tokens", "length", "MAX_TOKENS"}  # what providers report when the budget ran out
RETRYABLE = {429, 500, 502, 503, 504, 529}
RETRIES = 2
RETRY_DELAY = 12.0  # seconds, times the attempt; tests shorten it
# hop-core waits 120 s for a model's reply. Replies aren't streamed, so a page
# review with a large reply budget can take longer than that; wait as long as
# the vendors' own SDKs do. hop-core reads this when it opens each request.
GENERATION_TIMEOUT = 600.0
providers.GENERATION_TIMEOUT_SECONDS = max(providers.GENERATION_TIMEOUT_SECONDS, GENERATION_TIMEOUT)
MAX_FAILED = 3  # failed requests in a row before an agent stops
LABELS = {"readability": "readability", "seo": "SEO and metadata", "content_integrity": "content integrity"}


class AgentUnavailable(Exception):
    """The analysis has no usable agent; the run keeps HOP Audit's own metrics."""


class FindingIn(BaseModel):
    """One finding as an agent returns it."""

    page: str | None = None  # "P1"
    severity: Literal["High", "Medium", "Low"]
    title: str = Field(min_length=1, max_length=300)
    body: str = ""
    quote: str = ""
    suggestion: str = ""
    on_focus: bool = False


@dataclass
class ReviewAgent:
    id: UUID
    name: str
    model: str
    provider: str
    definition: AgentDefinition
    service: CredentialAiService


@dataclass
class Tally:
    tokens: int = 0
    findings: int = 0
    on_focus: int = 0
    errors: int = 0
    retries: int = 0
    quotes_removed: int = 0
    reused: int = 0
    status: str = "done"
    note: str = ""
    failing: int = 0  # failed requests in a row
    answered: int = 0  # requests the agent answered

    @property
    def failed(self) -> bool:
        """The review can't stand: the agent stopped, or answered nothing."""
        return self.status == "stopped" or (self.errors > 0 and self.answered == 0)


# ── The agent ─────────────────────────────────────────────────────────────────


def load_agent(db: Session, organization_id: UUID, agent_id: str | UUID | None) -> ReviewAgent:
    """The agent and a model service for it, or why there isn't one."""
    if not agent_id:
        raise AgentUnavailable("no agent is assigned in site settings")
    agent = db.scalar(
        select(Agent)
        .options(selectinload(Agent.context_files), selectinload(Agent.references), joinedload(Agent.ai_configuration))
        .where(Agent.id == UUID(str(agent_id)), Agent.organization_id == organization_id)
    )
    if agent is None:
        raise AgentUnavailable("the assigned agent was deleted")
    if not agent.is_active:
        raise AgentUnavailable(f"{agent.name} is deactivated")
    credential = agent.ai_configuration
    if credential is None:
        raise AgentUnavailable(f"{agent.name} has no AI configuration; choose one on the Agents page")
    try:
        payload = decrypt_credentials(credential.encrypted_data)
    except Exception as exc:
        raise AgentUnavailable(f"{credential.name} can't be decrypted; re-enter its API key") from exc
    model = str(payload.get("model") or "").strip()
    if not payload.get("api_key") or not model:
        raise AgentUnavailable(f"{credential.name} needs an API key and a model")
    return ReviewAgent(
        id=agent.id,
        name=agent.name,
        model=model,
        provider=credential.type,
        definition=AgentDefinition.from_model(agent),
        service=CredentialAiService(provider=credential.type, model=model, api_key=payload["api_key"]),
    )


def review_key(agent: ReviewAgent, site_focus: str, run_focus: str) -> str:
    """Same agent, model, instructions and focus: an unchanged page's findings still hold."""
    material = "\n".join([str(agent.id), agent.model, agent.definition.build_system_prompt(), site_focus, run_focus])
    return hashlib.sha256(material.encode()).hexdigest()


# ── Prompts ───────────────────────────────────────────────────────────────────

FORMAT = {
    "readability": (
        '{"page": "P1", "severity": "High|Medium|Low", "title": "under 90 characters", '
        '"body": "what is wrong and the concrete fix", "quote": "exact text from the page, or empty", '
        '"suggestion": "a rewrite of the quoted text, or empty", "on_focus": true|false}'
    ),
    "seo": (
        '{"page": "P1", "severity": "High|Medium|Low", "title": "under 90 characters", '
        '"body": "what is wrong and why it matters", "quote": "the current title, description or heading, '
        'or empty", "suggestion": "a replacement within the limits, or empty", "on_focus": true|false}'
    ),
}

TASK = {
    "readability": (
        "Review this page (P1) for readability, following your context files. HOP Audit measured it; don't "
        "recompute the numbers, explain them and propose concrete rewrites. Flag anything the focus asks for."
    ),
    "seo": (
        "Review this page's (P1) SEO and metadata, following your context files. HOP Audit's checks found the "
        "problems listed; explain what matters and draft replacements that fit the limits."
    ),
}


def instructions(
    analysis: str,
    site_focus: str,
    run_focus: str,
    task: str | None = None,
    fmt: str | None = None,
    answer: str | None = None,
) -> str:
    """The request's instructions: the task, both focuses, the rules, and the
    answer's shape (``answer`` replaces the default JSON-array sentence)."""
    parts = [task or TASK[analysis]]
    if site_focus.strip():
        parts.append(f"Focus for this site (applies to every page):\n{site_focus.strip()}")
    if run_focus.strip():
        parts.append(f"Focus for this run only:\n{run_focus.strip()}")
    parts.append(
        "Mark a finding on_focus when it is something the focus asked for. Quote exactly; never invent or "
        "paraphrase text inside a quote. Report only real problems: return [] when nothing needs fixing."
    )
    parts.append(
        answer or f"Answer with a JSON array and nothing else, one object per finding:\n[{fmt or FORMAT[analysis]}]"
    )
    return "\n\n".join(parts)


def _metrics_line(page: Page) -> str:
    bits = []
    if page.flesch is not None:
        bits.append(f"Flesch {page.flesch}")
    if page.grade is not None:
        bits.append(f"grade {page.grade}")
    if page.words_per_sentence is not None:
        bits.append(f"{page.words_per_sentence} words/sentence")
    if page.passive_pct is not None:
        bits.append(f"{page.passive_pct}% passive")
    return " · ".join(bits) or "not measurable in this language"


def page_input(ref: str, page: Page, language: str, analysis: str) -> str:
    content = page.content or {}
    head = f'### {ref} · {page.path} · "{page.title}" · {language}'
    if analysis == "readability":
        text = content.get("text", "")
        cut = text[:TEXT_LIMIT] + ("\n[… text cut]" if len(text) > TEXT_LIMIT else "")
        return f"{head}\nMetrics: {_metrics_line(page)}\n\n{cut}"
    problems = "\n".join(f"- {c['label']}: {c['detail']}" for c in (page.seo or []) if c["status"] != "ok")
    headings = "\n".join(f"{'  ' * (level - 1)}H{level} {text}" for level, text in content.get("headings", [])[:25])
    return (
        f"{head}\nTitle: {content.get('title') or '(none)'}\n"
        f"Description: {content.get('description') or '(none)'}\n"
        f"Problems:\n{problems}\nHeadings:\n{headings or '(none)'}\n"
        f"Opening text:\n{content.get('text', '')[:SEO_TEXT_LIMIT]}"
    )


# ── Answers ───────────────────────────────────────────────────────────────────


def transport_problem(exc: httpx.TransportError) -> str:
    """ "timed out after 600 s" or "connection failed (ConnectError)", for the run log."""
    if isinstance(exc, httpx.TimeoutException):
        return f"timed out after {providers.GENERATION_TIMEOUT_SECONDS:g} s"
    return f"connection failed ({type(exc).__name__})"


def out_of_room(exc: AiProviderError) -> bool:
    """hop-core's error for a reply with no text because max_tokens ran out
    (typically all spent thinking)."""
    return exc.status_code is None and "max_tokens budget was used up" in exc.message


def parse_findings(output: str) -> list[dict] | None:
    """The JSON array in an agent's reply, tolerating code fences and prose."""
    text = re.sub(r"```(?:json)?", "", output).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end < start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return value if isinstance(value, list) else None


def parse_object(output: str) -> dict | None:
    """The JSON object in an agent's reply, tolerating code fences and prose."""
    text = re.sub(r"```(?:json)?", "", output).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _normalize(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_found(quote: str, *sources: str) -> bool:
    q = _normalize(quote.strip().strip('"').rstrip("…").strip())
    return not q or any(q in _normalize(s) for s in sources if s)


# ── Running a review ─────────────────────────────────────────────────────────


class Review:
    """Reviews one analysis of one run with its agent."""

    def __init__(
        self,
        db: Session,
        run: AuditRun,
        analysis: str,
        agent: ReviewAgent,
        log: Callable[[str, str, str], None],
        progress: Callable[[int, int], None],
        checkpoint: Callable[[], Awaitable[None]],
    ):
        self.db, self.run, self.analysis, self.agent = db, run, analysis, agent
        self.log, self.progress, self.checkpoint = log, progress, checkpoint
        self.key = review_key(agent, run.site.focus or "", run.focus or "")
        self.instructions = instructions(analysis, run.site.focus or "", run.focus or "") if analysis in TASK else ""
        self.tally = Tally()
        self.runner = AgentRunner(agent.service)
        self.budget = REPLY_BUDGET.get(analysis, 8192)

    async def ask(self, where: str, material: str, task: str | None = None, parse=None) -> list | dict | None:
        """One request: the parsed findings, or None when it failed. ``where``
        names it in the log (a page path, or "batch 3").

        ``task`` replaces the analysis's usual instructions for this request;
        ``parse`` replaces the JSON-array parser (pass 1 of integrity answers an object).
        Rate limits and server errors are retried with backoff; a reply that
        ran out of room is asked again with a bigger budget; a reply that
        isn't JSON is asked for again once. None of these share a count.
        """
        base = task or self.instructions
        instructions, retries, reasked = base, 0, False
        while True:
            await self.checkpoint()
            # No temperature: newer models reject it (Anthropic answers 400
            # "temperature is deprecated"), and hop-core omits it when unset.
            request = AgentRequest(instructions=instructions, input=material, max_tokens=self.budget)
            try:
                result = await self.runner.run(self.agent.definition, request)
            except AiProviderError as exc:
                if out_of_room(exc):
                    if self.grow(where):
                        continue
                    self.log(self.analysis, "error", f"{self.agent.name}, {where}: {self.too_long()}")
                    return None
                if exc.status_code in RETRYABLE and retries < RETRIES:
                    retries += 1
                    wait = RETRY_DELAY * retries
                    self.tally.retries += 1
                    message = f"returned {exc.status_code} on {where}; retried after {wait:g} s."
                    self.log(self.analysis, "warn", f"{self.agent.provider} {message}")
                    await asyncio.sleep(wait)
                    continue
                self.log(self.analysis, "error", f"{self.agent.name}, {where}: {exc.message}")
                return None
            except httpx.TransportError as exc:  # timed out, or the connection dropped
                problem = transport_problem(exc)
                if retries < RETRIES:
                    retries += 1
                    wait = RETRY_DELAY * retries
                    self.tally.retries += 1
                    self.log(
                        self.analysis, "warn", f"{self.agent.provider} {problem} on {where}; retried after {wait:g} s."
                    )
                    await asyncio.sleep(wait)
                    continue
                self.log(self.analysis, "error", f"{self.agent.name}, {where}: {problem} {RETRIES + 1} times; skipped.")
                return None
            self.tally.tokens += (result.input_tokens or 0) + (result.output_tokens or 0)
            if result.stop_reason in CUT_OFF:  # the JSON was cut off mid-reply
                if self.grow(where):
                    continue
                self.log(self.analysis, "error", f"{self.agent.name}, {where}: {self.too_long()}")
                return None
            found = (parse or parse_findings)(result.output)
            if found is not None:
                self.tally.answered += 1
                return found
            if reasked:
                self.log(self.analysis, "error", f"{self.agent.name}, {where}: reply wasn't JSON twice; skipped.")
                return None
            reasked = True
            self.log(self.analysis, "warn", f"{self.agent.name}, {where}: reply wasn't JSON; asked again.")
            instructions = base + "\n\nYour last reply wasn't the JSON asked for. Reply with the JSON only."

    def grow(self, where: str) -> bool:
        """Double the reply budget after a reply ran out of room; False at the ceiling."""
        if self.budget >= MAX_REPLY_BUDGET:
            return False
        before, self.budget = self.budget, min(self.budget * 2, MAX_REPLY_BUDGET)
        self.log(
            self.analysis,
            "warn",
            f"{self.agent.name}, {where}: the reply didn't fit in {before:,} tokens (thinking included); "
            f"asked again with {self.budget:,}.",
        )
        return True

    def too_long(self) -> str:
        return f"the reply didn't fit even in {MAX_REPLY_BUDGET:,} tokens; skipped."

    def failed(self) -> bool:
        """Record a failed request; True when the agent should stop."""
        self.tally.errors += 1
        self.tally.failing += 1
        if self.tally.failing >= MAX_FAILED and self.tally.status != "stopped":
            self.tally.status = "stopped"
            self.tally.note = f"stopped after {MAX_FAILED} failed requests in a row"
            self.log(self.analysis, "error", f"{self.agent.name} {self.tally.note}; the rest keep HOP Audit's metrics.")
            return True
        return False

    def add(self, finding: FindingIn, page_id: UUID) -> None:
        self.db.add(
            AgentFinding(
                run_id=self.run.id,
                page_id=page_id,
                analysis=self.analysis,
                agent_id=self.agent.id,
                agent_name=self.agent.name,
                model=self.agent.model,
                severity=finding.severity,
                title=finding.title.strip(),
                body=finding.body.strip(),
                quote=finding.quote.strip(),
                suggestion=finding.suggestion.strip(),
                on_focus=finding.on_focus,
                review_key=self.key,
            )
        )
        self.tally.findings += 1
        self.tally.on_focus += finding.on_focus

    def valid(self, raw: list[dict]) -> list[FindingIn]:
        out = []
        for item in raw:
            try:
                out.append(FindingIn.model_validate(item))
            except ValidationError:
                continue
        if len(out) < len(raw):
            self.log(self.analysis, "warn", f"{self.agent.name}: {len(raw) - len(out)} malformed finding(s) dropped.")
        return out

    # ── Pages (readability, SEO) ──

    def reuse(self, pages: list[Page], unchanged: dict) -> list[Page]:
        """Keep the findings of pages whose checksum hasn't changed since the
        last audit reviewed them (``unchanged``: page id -> that audit's page;
        empty when the run forces re-evaluation). Returns the pages still to review."""
        sources = {
            prev.id: page
            for page in pages
            if (prev := unchanged.get(page.id)) is not None and self.analysis in (prev.reviews or {})
        }
        if not sources:
            return pages
        previous = self.db.scalars(
            select(AgentFinding).where(AgentFinding.page_id.in_(list(sources)), AgentFinding.analysis == self.analysis)
        ).all()
        for f in previous:
            copy = {c.name: getattr(f, c.name) for c in AgentFinding.__table__.columns if c.name != "id"}
            self.db.add(AgentFinding(**{**copy, "run_id": self.run.id, "page_id": sources[f.page_id].id}))
            self.tally.findings += 1
            self.tally.on_focus += f.on_focus
        for page in sources.values():
            page.reviews = {**(page.reviews or {}), self.analysis: unchanged[page.id].reviews[self.analysis]}
        self.tally.reused = len(sources)
        return [p for p in pages if p not in sources.values()]

    def mark_reviewed(self, pages: list[Page]) -> None:
        for page in pages:
            page.reviews = {**(page.reviews or {}), self.analysis: self.key}

    async def pages(self, pages: list[Page], languages: dict[UUID, str], unchanged: dict | None = None) -> Tally:
        """Each page on its own request, a few at a time. Unchanged pages keep
        their findings (``reuse``); the rest are reviewed until the agent stops."""
        todo = self.reuse(pages, unchanged or {})
        done = len(pages) - len(todo)
        self.progress(done, len(pages))

        async def one(page: Page) -> None:
            nonlocal done
            language = languages.get(page.help_center_id, "en")
            raw = await self.ask(page.path, page_input("P1", page, language, self.analysis))
            if raw is None:
                self.failed()
            else:
                self.tally.failing = 0
                self.record(page, raw)
            done += 1
            self.progress(done, len(pages))

        await self.each(todo, one)
        return self.tally

    async def each(self, items: list, fn) -> None:
        """``fn(item)`` for every item, AGENT_CONCURRENCY at a time, until the
        agent stops; cancelling the run cancels what's in flight."""
        limit = asyncio.Semaphore(AGENT_CONCURRENCY)

        async def one(item) -> None:
            async with limit:
                if self.tally.status == "stopped":
                    return
                await fn(item)
                self.db.commit()

        tasks = [asyncio.create_task(one(i)) for i in items]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            raise

    def record(self, page: Page, raw: list[dict]) -> None:
        """Keep a page's valid findings; drop quotes that aren't on the page."""
        content = page.content or {}
        sources = (content.get("text", ""), content.get("title", ""), content.get("description") or "")
        for finding in self.valid(raw):
            if finding.page not in (None, "P1"):
                continue
            if not quote_found(finding.quote, *sources):
                finding.quote = ""
                self.tally.quotes_removed += 1
            self.add(finding, page.id)
        self.mark_reviewed([page])
