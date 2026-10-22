"""Agent review: the analysis agents read the pages in batches and report
findings. HOP Audit's own checks (``analysis.py``) give them the numbers; the
agents explain them and propose fixes, and apply the site's focus.

Each agent is a hop-core agent: its context files, references and feedback
memory form the system prompt, its AI configuration (a credential) the model.
Every batch carries the site's standing focus and the run's focus. Agents
answer in JSON; findings are validated, and a quote that isn't on the page is
removed rather than shown, because a wrong quote costs more than none.
"""

import asyncio
import difflib
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from hop_core.agents import AgentDefinition, AgentRequest, AgentRunner, AiProviderError, CredentialAiService
from hop_core.core.security import decrypt_credentials
from hop_core.models.agent import Agent
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from models import AgentFinding, AuditRun, LinkResult, Page

BATCH_SIZE = {"readability": 12, "seo": 20, "links": 25}
TEXT_LIMIT = 6000  # characters of page text per page in a readability batch
SEO_TEXT_LIMIT = 1200  # enough to draft a description from
MAX_OUTPUT_TOKENS = 4096
RETRYABLE = {429, 500, 502, 503, 504, 529}
RETRIES = 2
RETRY_DELAY = 12.0  # seconds, times the attempt; tests shorten it
MAX_FAILED_BATCHES = 3
LABELS = {
    "readability": "readability",
    "seo": "SEO and metadata",
    "links": "links",
    "content_integrity": "content integrity",
}


class AgentUnavailable(Exception):
    """The analysis has no usable agent; the run keeps HOP Audit's own metrics."""


class FindingIn(BaseModel):
    """One finding as an agent returns it."""

    page: str | None = None  # "P3" for page findings
    target: str | None = None  # the link target, for link findings
    severity: Literal["High", "Medium", "Low"]
    title: str = Field(min_length=1, max_length=300)
    body: str = ""
    quote: str = ""
    suggestion: str = ""
    fix: str = ""  # links: relink | redirect | restore | remove
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
    failing: int = 0  # failed batches in a row
    answered: int = 0  # batches the agent answered

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
    "links": (
        '{"target": "the target URL exactly as given", "severity": "High|Medium|Low", '
        '"title": "under 90 characters", "body": "what happened and what to do", '
        '"fix": "relink|redirect|restore|remove", "suggestion": "the URL to link to instead, or empty", '
        '"on_focus": true|false}'
    ),
}

TASK = {
    "readability": (
        "Review these pages for readability, following your context files. HOP Audit measured each page; "
        "don't recompute the numbers, explain them and propose concrete rewrites. Flag what the focus asks for "
        "on any page."
    ),
    "seo": (
        "Review these pages' SEO and metadata, following your context files. HOP Audit's checks found the "
        "problems listed with each page; explain what matters and draft replacements that fit the limits."
    ),
    "links": (
        "Classify these problem links and propose the fix for each target, following your context files. "
        "Each target lists the pages that link to it and, for broken internal links, pages on the site with "
        "similar paths that may be where the content moved."
    ),
}


def instructions(
    analysis: str, site_focus: str, run_focus: str, task: str | None = None, fmt: str | None = None
) -> str:
    parts = [task or TASK[analysis]]
    if site_focus.strip():
        parts.append(f"Focus for this site (applies to every page):\n{site_focus.strip()}")
    if run_focus.strip():
        parts.append(f"Focus for this run only:\n{run_focus.strip()}")
    parts.append(
        "Mark a finding on_focus when it is something the focus asked for. Quote exactly; never invent or "
        "paraphrase text inside a quote. Report only real problems: return [] when nothing needs fixing."
    )
    parts.append(f"Answer with a JSON array and nothing else, one object per finding:\n[{fmt or FORMAT[analysis]}]")
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


@dataclass
class LinkGroup:
    target: str
    outcome: str
    status: int | None
    note: str
    internal: bool
    page_ids: list[UUID]
    pages: list[str]  # paths, for the prompt
    texts: list[str]  # anchor texts
    candidates: list[str] = field(default_factory=list)


def relink_candidates(missing: str, paths: list[str], limit: int = 5) -> list[str]:
    """Pages on the site whose path looks like where a missing page went: the
    last segment matters most (keys -> keys-and-keydefs), then the folder."""
    leaf = missing.rstrip("/").rsplit("/", 1)[-1].lower()

    def score(path: str) -> float:
        other = path.rstrip("/").rsplit("/", 1)[-1].lower()
        leaf_score = 1.0 if leaf and leaf in other else difflib.SequenceMatcher(None, leaf, other).ratio()
        return 0.7 * leaf_score + 0.3 * difflib.SequenceMatcher(None, missing, path).ratio()

    ranked = sorted(((score(p), p) for p in paths if p != missing), reverse=True)
    return [p for s, p in ranked if s >= 0.6][:limit]


def link_groups(rows: list[LinkResult], pages: dict[UUID, Page]) -> list[LinkGroup]:
    """Problem links grouped by target, worst first, with relink candidates."""
    groups: dict[str, LinkGroup] = {}
    for r in rows:
        if r.outcome not in ("broken", "anchor", "redirect"):
            continue
        g = groups.get(r.url)
        if g is None:
            g = groups[r.url] = LinkGroup(r.url, r.outcome, r.status, r.note, r.internal, [], [], [])
        if r.page_id not in g.page_ids:
            g.page_ids.append(r.page_id)
            g.pages.append(pages[r.page_id].path)
        if r.text and r.text not in g.texts:
            g.texts.append(r.text)
    paths = sorted({p.path for p in pages.values() if p.http_status == 200})
    for g in groups.values():
        if g.outcome == "broken" and g.internal:
            g.candidates = relink_candidates(urlsplit(g.target).path, paths)
    order = {"broken": 0, "anchor": 1, "redirect": 2}
    return sorted(groups.values(), key=lambda g: (order[g.outcome], -len(g.page_ids), g.target))


def link_input(group: LinkGroup) -> str:
    lines = [
        f"### {group.target}",
        f"{group.outcome} · {group.note or group.status} · {'internal' if group.internal else 'external'}",
        f"Linked from {len(group.pages)} page(s): {', '.join(group.pages[:5])}"
        + (" …" if len(group.pages) > 5 else ""),
    ]
    if group.texts:
        lines.append("Anchor text: " + "; ".join(f'"{t}"' for t in group.texts[:5]))
    if group.candidates:
        lines.append("Similar pages on the site: " + ", ".join(group.candidates))
    return "\n".join(lines)


# ── Answers ───────────────────────────────────────────────────────────────────


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

    async def ask(self, batch_no: int, material: str, task: str | None = None) -> list[dict] | None:
        """One batch: the parsed findings, or None when the batch failed.

        ``task`` replaces the analysis's usual instructions for this batch.
        Rate limits and server errors are retried with backoff; a reply that
        isn't JSON is asked for again once. The two don't share a budget.
        """
        base = task or self.instructions
        instructions, retries, reasked = base, 0, False
        while True:
            await self.checkpoint()
            # No temperature: newer models reject it (Anthropic answers 400
            # "temperature is deprecated"), and hop-core omits it when unset.
            request = AgentRequest(instructions=instructions, input=material, max_tokens=MAX_OUTPUT_TOKENS)
            try:
                result = await self.runner.run(self.agent.definition, request)
            except AiProviderError as exc:
                if exc.status_code in RETRYABLE and retries < RETRIES:
                    retries += 1
                    wait = RETRY_DELAY * retries
                    self.tally.retries += 1
                    message = f"returned {exc.status_code} on batch {batch_no}; retried after {wait:g} s."
                    self.log(self.analysis, "warn", f"{self.agent.provider} {message}")
                    await asyncio.sleep(wait)
                    continue
                self.log(self.analysis, "error", f"{self.agent.name}, batch {batch_no}: {exc.message}")
                return None
            self.tally.tokens += (result.input_tokens or 0) + (result.output_tokens or 0)
            found = parse_findings(result.output)
            if found is not None:
                self.tally.answered += 1
                return found
            if reasked:
                self.log(
                    self.analysis, "error", f"{self.agent.name}, batch {batch_no}: reply wasn't JSON twice; skipped."
                )
                return None
            reasked = True
            self.log(self.analysis, "warn", f"{self.agent.name}, batch {batch_no}: reply wasn't JSON; asked again.")
            instructions = base + "\n\nYour last reply wasn't a JSON array. Reply with the array only."

    def failed(self) -> bool:
        """Record a failed batch; True when the agent should stop."""
        self.tally.errors += 1
        self.tally.failing += 1
        if self.tally.failing >= MAX_FAILED_BATCHES:
            self.tally.status = "stopped"
            self.tally.note = f"stopped after {MAX_FAILED_BATCHES} failed batches in a row"
            self.log(self.analysis, "error", f"{self.agent.name} {self.tally.note}; the rest keep HOP Audit's metrics.")
            return True
        return False

    def add(self, finding: FindingIn, page_id: UUID | None, page_ids: list, target: str | None) -> None:
        self.db.add(
            AgentFinding(
                run_id=self.run.id,
                page_id=page_id,
                page_ids=[str(i) for i in page_ids],
                target=target,
                analysis=self.analysis,
                agent_id=self.agent.id,
                agent_name=self.agent.name,
                model=self.agent.model,
                severity=finding.severity,
                title=finding.title.strip(),
                body=finding.body.strip(),
                quote=finding.quote.strip(),
                suggestion=(f"{finding.fix}: " if finding.fix and finding.suggestion else finding.fix)
                + finding.suggestion.strip(),
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
        todo = self.reuse(pages, unchanged or {})
        size = BATCH_SIZE[self.analysis]
        done = len(pages) - len(todo)
        self.progress(done, len(pages))
        for batch_no, start in enumerate(range(0, len(todo), size), 1):
            batch = todo[start : start + size]
            refs = {f"P{i}": p for i, p in enumerate(batch, 1)}
            material = "\n\n".join(page_input(ref, p, languages.get(p.help_center_id, "en"), self.analysis)
                                   for ref, p in refs.items())  # fmt: skip
            raw = await self.ask(batch_no, material)
            if raw is None:
                if self.failed():
                    break
            else:
                self.tally.failing = 0
                for finding in self.valid(raw):
                    page = refs.get(finding.page or "")
                    if page is None:
                        continue
                    content = page.content or {}
                    if not quote_found(finding.quote, content.get("text", ""), content.get("title", ""),
                                       content.get("description") or ""):  # fmt: skip
                        finding.quote = ""
                        self.tally.quotes_removed += 1
                    self.add(finding, page.id, [], None)
                self.mark_reviewed(batch)
            done += len(batch)
            self.progress(done, len(pages))
            self.db.commit()
        return self.tally

    # ── Link targets ──

    async def links(self, groups: list[LinkGroup]) -> Tally:
        size = BATCH_SIZE["links"]
        done = 0
        self.progress(0, len(groups))
        for batch_no, start in enumerate(range(0, len(groups), size), 1):
            batch = groups[start : start + size]
            by_target = {g.target: g for g in batch}
            raw = await self.ask(batch_no, "\n\n".join(link_input(g) for g in batch))
            if raw is None:
                if self.failed():
                    break
            else:
                self.tally.failing = 0
                for finding in self.valid(raw):
                    group = by_target.get(finding.target or "")
                    if group is None:
                        continue
                    finding.quote = ""
                    self.add(finding, None, group.page_ids, group.target)
            done += len(batch)
            self.progress(done, len(groups))
            self.db.commit()
        return self.tally
