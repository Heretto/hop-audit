"""Content integrity: the Content Integrity Reviewer reads every article in
every reviewed help center and logs what is wrong, conflicting, outdated,
missing or unscoped (the skill's assessment, in its context files).

Three passes, so no request has to hold the whole site and unchanged
articles cost nothing:

1. Per article (one request each): issues inside the article, and the
   checkable statements it makes (claims). Kept for unchanged pages.
2. Per translation pair: the translation against the article it translates
   (and two versions of one language against each other). Kept when neither
   side changed.
3. Across articles: claims about the same subject, within a help center,
   grouped by embeddings (an OpenAI or Gemini key) or by keywords (no extra
   service, and the fallback); each group whose statements differ goes to
   the reviewer once. A group seen before with the same statements keeps
   its verdict.

Some findings need no model at all: duplicate titles, links into another
language's help center, broken links, and articles missing a translation.

Candidates are verified (every quote must be on its page, or the finding
goes to review), merged, and given stable codes: a candidate matching an
earlier run's finding keeps its code, and its tier when that run's triage
was confirmed. Nothing is counted until a person confirms.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urldefrag
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

import claims as claim_groups
import embeddings
import review
from catalog import CATEGORY_CODES, INTEGRITY_CATEGORIES
from models import AuditRun, ClaimGroupReview, HelpCenter, IntegrityFinding, LinkResult, Page
from scope import Root, help_center_for, relative_path

ARTICLE_TEXT_LIMIT = 20_000  # characters of an article sent in one request
MAX_CLAIMS = 30  # per article
BROKEN_LINK = "Broken link: "  # title prefix of code-found broken links
MISSING_LISTED = 8  # pages quoted on a code-made finding
SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
CATEGORY_LABELS = {c.code: c.label for c in INTEGRITY_CATEGORIES}
CROSS_ARTICLE = ("C", "U", "TM", "D", "S")  # what comparing statements can find

TASK_ARTICLE = (
    "Assess this article (P1) for content-integrity issues inside it, following your assessment, counting "
    "rule and triage files: contradictions within it, instructions that can't match the app, outdated "
    "content, retired products, scope errors, inconsistent terms or disclosure text, and structure or "
    "publishing errors. Articles are compared with each other separately, so don't guess about others.\n\n"
    "Then list the article's checkable claims: statements a customer could act on or check (numbers, prices, "
    "rates, fees, timelines, eligibility, limits, steps, contact details, product names). Give each a short "
    "subject (2 to 6 words, the same subject wording another article would use) and the exact sentence."
)
TASK_PAIR = (
    "Compare the translation (P2) with the article it translates (P1), following your assessment, counting "
    "rule and triage files: changed meaning, missing or added sentences, untranslated strings, one version "
    "visibly older. Never log wording differences where both say the same thing."
)
TASK_GROUP = (
    "These statements come from different articles in one help center and are about the same subject. Log a "
    "finding only where they can't all be true for the same customer, product and locale, or would give a "
    "customer two different answers. Never log statements that are both accurate (different situations, or "
    "the same fact worded differently). Refer to statements by their S number."
)
ISSUE = (
    '{"category": "C|U|T|TM|D|L|S|O|N|X", "severity": "High|Medium|Low", "title": "under 100 characters", '
    '"quotes": [{"label": "A|B|EN|FR…", "page": "P1", "text": "exact text, trimmed to the clause that matters", '
    '"note": "a translation of a non-English quote, or empty"}], "why": "one sentence on why it is a problem", '
    '"tier": "firm|review|drop", "tier_reason": "why, for review or drop"}'
)
ANSWER_ARTICLE = (
    "Answer with one JSON object and nothing else:\n"
    '{"issues": [' + ISSUE + '], "claims": [{"subject": "late payment fee", "statement": "exact sentence"}]}'
)
GROUP_FINDING = (
    '{"category": "C|U|TM|D|S", "severity": "High|Medium|Low", "title": "under 100 characters", '
    '"statements": ["S1", "S3"], "why": "one sentence on why it is a problem", '
    '"tier": "firm|review|drop", "tier_reason": "why, for review or drop"}'
)


class QuoteIn(BaseModel):
    label: str = ""
    page: str
    text: str = Field(min_length=1)
    note: str = ""


class CandidateIn(BaseModel):
    category: str
    severity: Literal["High", "Medium", "Low"]
    title: str = Field(min_length=1, max_length=300)
    quotes: list[QuoteIn] = Field(min_length=1)
    why: str = ""
    tier: Literal["firm", "review", "drop"] = "review"
    tier_reason: str = ""

    @field_validator("category")
    @classmethod
    def _category(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in CATEGORY_CODES:
            raise ValueError("unknown category")
        return v


@dataclass
class Candidate:
    """A verified candidate, before it gets its code."""

    category: str
    severity: str
    title: str
    quotes: list[dict]
    why: str
    tier: str
    reason: str
    center_ids: list[UUID] = field(default_factory=list)

    def keys(self) -> set[tuple[str, str]]:
        return {(q["slug"], review._normalize(q["text"])[:80]) for q in self.quotes}


# ── Articles and pairs ──────────────────────────────────────────────────────


def slug(page: Page, root: Root) -> str:
    rel = relative_path(page.url, root).strip("/")
    prefix = root.url.split("://", 1)[-1].split("/", 1)[-1].strip("/")
    return f"{prefix}/{rel}".strip("/") if prefix else (rel or "(home)")


def base_language(tag: str) -> str:
    return tag.split("-")[0].lower()


def pairings(roots: list[Root]) -> list[tuple[Root, Root]]:
    """(other, original) help centers to compare: each non-primary with the
    primary, and two versions of one language with each other."""
    primary = next((r for r in roots if r.is_primary), roots[0])
    pairs = [(r, primary) for r in roots if r.id != primary.id]
    for i, a in enumerate(roots):
        for b in roots[i + 1 :]:
            same = base_language(a.language) == base_language(b.language)
            if same and primary.id not in (a.id, b.id):
                pairs.append((b, a))
    return pairs


def counterparts(
    originals: list[Page], original: Root, translations: list[Page], other: Root
) -> list[tuple[Page, Page]]:
    """(original, translation) pairs: by hreflang alternate when the
    translation declares one, else by the same path relative to its root."""
    by_url = {p.url: p for p in originals}
    by_rel = {relative_path(p.url, original): p for p in originals}
    pairs = []
    for page in translations:
        alternates = [alt["url"] for alt in page.content.get("alternates", [])]
        source = next((by_url[u] for u in alternates if u in by_url), None)
        source = source or by_rel.get(relative_path(page.url, other))
        if source is not None:
            pairs.append((source, page))
    return pairs


def article(ref: str, page: Page, root: Root) -> str:
    text = page.content.get("text", "")
    cut = text[:ARTICLE_TEXT_LIMIT] + ("\n[… text cut]" if len(text) > ARTICLE_TEXT_LIMIT else "")
    return f'### {ref} · {root.name} ({root.language}) · {slug(page, root)} · "{page.title}"\n{cut}'


# ── Candidates ────────────────────────────────────────────────────────────────


def verify(raw: list[dict], refs: dict[str, tuple[Page, Root]], enabled: set[str]) -> tuple[list[Candidate], int]:
    """Valid candidates in enabled categories, quotes checked against their
    pages; also how many replies were malformed."""
    out, malformed = [], 0
    for item in raw:
        try:
            c = CandidateIn.model_validate(item)
        except ValidationError:
            malformed += 1
            continue
        if c.category not in enabled or any(q.page not in refs for q in c.quotes):
            malformed += 1
            continue
        quotes, centers, unverified = [], [], 0
        for q in c.quotes:
            page, root = refs[q.page]
            found = review.quote_found(q.text, page.content.get("text", ""), page.title)
            unverified += not found
            quotes.append(
                {
                    "label": q.label,
                    "text": q.text.strip().strip('"“”'),
                    "slug": slug(page, root),
                    "note": q.note,
                    "page_id": str(page.id),
                    "verified": found,
                }
            )
            if root.id not in centers:
                centers.append(root.id)
        tier, reason = c.tier, c.tier_reason
        if unverified and tier == "firm":
            tier, reason = "review", "A quote couldn't be found on its page; check it in a browser before counting."
        out.append(Candidate(c.category, c.severity, c.title.strip(), quotes, c.why.strip(), tier, reason, centers))
    return out, malformed


def merge(candidates: list[Candidate]) -> list[Candidate]:
    """One candidate per issue: same category and a shared quote means the same finding."""
    kept: list[Candidate] = []
    for c in sorted(candidates, key=lambda c: SEVERITY_ORDER[c.severity]):
        if not any(k.category == c.category and k.keys() & c.keys() for k in kept):
            kept.append(c)
    return kept


def missing_translations(
    pairs_by_center: dict, roots: dict[UUID, Root], pages: dict[UUID, list[Page]]
) -> list[Candidate]:
    """Articles that exist only in the original language, per translated help center (for review)."""
    out = []
    for (other_id, original_id), matched in pairs_by_center.items():
        original, other = roots[original_id], roots[other_id]
        if base_language(other.language) == base_language(original.language):
            continue
        have = {source.id for source, _ in matched}  # matched: (original, translation) pairs
        missing = [p for p in pages[original_id] if p.id not in have]
        if not missing:
            continue
        quotes = [
            {"label": "", "text": p.title or slug(p, original), "slug": slug(p, original),
             "note": f"no {other.name} version", "page_id": str(p.id), "verified": True}
            for p in missing[:MISSING_LISTED]
        ]  # fmt: skip
        more = f" (first {MISSING_LISTED} listed)" if len(missing) > MISSING_LISTED else ""
        out.append(
            Candidate(
                "T",
                "Medium",
                f"{len(missing)} {original.name} articles have no {other.name} version",
                quotes,
                f"Readers of {other.name} can't find these articles in their language{more}.",
                "review",
                "Found by matching paths and hreflang, not judged by the reviewer: some articles may be meant "
                "for one market only.",
                [original.id, other.id],
            )
        )
    return out


def verify_group(
    raw: list[dict], refs: dict[str, claim_groups.Claim], enabled: set[str]
) -> tuple[list[Candidate], int]:
    """Pass 3 verdicts: each names the statements (S1…) it concerns; their
    exact text and pages come from the claims, already verified on their pages."""
    out, malformed = [], 0
    for item in raw:
        if not isinstance(item, dict):
            malformed += 1
            continue
        named = [refs[r] for r in item.get("statements", []) if isinstance(r, str) and r in refs]
        category = str(item.get("category", "")).strip().upper()
        if len(named) < 2 or category not in enabled or category not in CROSS_ARTICLE:
            malformed += 1
            continue
        try:
            c = CandidateIn.model_validate(
                {**item, "category": category, "quotes": [{"page": "S", "text": n.statement} for n in named]}
            )
        except ValidationError:
            malformed += 1
            continue
        labels = "ABCDEFGHIJKL"
        quotes = [
            {"label": labels[i], "text": n.statement, "slug": n.slug, "note": "", "page_id": str(n.page_id),
             "verified": True}
            for i, n in enumerate(named)
        ]  # fmt: skip
        centers = list(dict.fromkeys(n.center_id for n in named))
        out.append(Candidate(c.category, c.severity, c.title.strip(), quotes, c.why.strip(), c.tier, c.tier_reason,
                             centers))  # fmt: skip
    return out, malformed


def code_findings(
    db: Session, run: AuditRun, roots: list[Root], every_root: list[Root], pages: dict[UUID, list[Page]]
) -> list[Candidate]:
    """Findings that need no model: duplicate titles, links into another
    language's help center, and broken links (from this run's link check, or
    the latest earlier one when this run didn't check links)."""
    out: list[Candidate] = []
    by_id = {r.id: r for r in every_root}

    def quote(page: Page, root: Root, text: str, note: str) -> dict:
        return {"label": "", "text": text, "slug": slug(page, root), "note": note, "page_id": str(page.id),
                "verified": True}  # fmt: skip

    for root in roots:
        titles: dict[str, list[Page]] = defaultdict(list)
        for p in pages[root.id]:
            if p.title.strip():
                titles[claim_groups.normalize(p.title)].append(p)
        for same in titles.values():
            if len(same) > 1:
                out.append(Candidate(
                    "N", "Low", f'{len(same)} articles share the title "{same[0].title}"',
                    [quote(p, root, p.title, "") for p in same[:MISSING_LISTED]],
                    "Readers, search and AI answers can't tell these articles apart.", "firm", "", [root.id],
                ))  # fmt: skip

        wrong: dict[UUID, list[tuple[Page, str, str]]] = defaultdict(list)
        for p in pages[root.id]:
            for link in p.content.get("links", []):
                target = help_center_for(urldefrag(link["url"])[0], every_root)
                if target and base_language(target.language) != base_language(root.language) and link.get("text"):
                    wrong[target.id].append((p, link["text"], link["url"]))
        for target_id, found in wrong.items():
            target = by_id[target_id]
            links = f"{len(found)} link" + ("s" if len(found) != 1 else "")
            out.append(Candidate(
                "N", "Medium", f"{root.name} links into the {target.name} help center ({links})",
                [quote(p, root, text, f"→ {url}") for p, text, url in found[:MISSING_LISTED]],
                f"A {root.name} reader following these links lands in another language.", "firm", "",
                [root.id, target.id],
            ))  # fmt: skip

    reviewed = {p.url: (p, by_id[p.help_center_id]) for ps in pages.values() for p in ps}
    broken: dict[str, list[tuple[LinkResult, Page, Root]]] = defaultdict(list)
    checked_in = run.id if "links" in (run.analyses or []) else _last_link_check(db, run)
    rows = db.execute(
        select(LinkResult, Page.url)
        .join(Page, Page.id == LinkResult.page_id)
        .where(LinkResult.run_id == checked_in, LinkResult.outcome == "broken")
    ) if checked_in else []  # fmt: skip
    for r, page_url in rows:
        if page_url in reviewed and r.text:
            broken[urldefrag(r.url)[0]].append((r, *reviewed[page_url]))
    for target, found in broken.items():
        first = found[0][0]
        out.append(Candidate(
            "N", "Medium" if first.internal else "Low",
            f"{BROKEN_LINK}{target.split('://', 1)[-1][:80]} ({first.note or first.status})",
            [quote(p, root, r.text, f"→ {first.note or 'broken'}") for r, p, root in found[:MISSING_LISTED]],
            "The link goes nowhere; readers who need what it points to are stuck.", "firm", "",
            list(dict.fromkeys(root.id for _, _, root in found)),
        ))  # fmt: skip
    return out


def _last_link_check(db: Session, run: AuditRun) -> UUID | None:
    """The latest earlier completed run of the site that checked links."""
    for earlier in db.scalars(
        select(AuditRun)
        .where(AuditRun.site_id == run.site_id, AuditRun.number < run.number, AuditRun.status == "completed")
        .order_by(AuditRun.number.desc())
    ):
        if "links" in (earlier.analyses or []):
            return earlier.id
    return None


# ── Codes across runs ─────────────────────────────────────────────────────────


def previous_findings(db: Session, run: AuditRun) -> tuple[AuditRun | None, list[IntegrityFinding]]:
    """The latest earlier run of the site with integrity findings."""
    prev = db.scalar(
        select(AuditRun)
        .join(IntegrityFinding, IntegrityFinding.run_id == AuditRun.id)
        .where(AuditRun.site_id == run.site_id, AuditRun.number < run.number)
        .order_by(AuditRun.number.desc())
        .limit(1)
    )
    if prev is None:
        return None, []
    return prev, db.scalars(select(IntegrityFinding).where(IntegrityFinding.run_id == prev.id)).all()


def _keys(f: IntegrityFinding) -> set[tuple[str, str]]:
    return {(q["slug"], review._normalize(q["text"])[:80]) for q in f.quotes}


def assign(
    db: Session, run: AuditRun, candidates: list[Candidate], reviewed_urls: set[str]
) -> tuple[list[IntegrityFinding], list[str]]:
    """Findings with stable codes, and the codes resolved since the previous run."""
    prev_run, previous = previous_findings(db, run)
    confirmed = bool(prev_run and (prev_run.triage or {}).get("status") == "confirmed")
    used: Counter = Counter()
    for code in db.scalars(select(IntegrityFinding.code).where(IntegrityFinding.site_id == run.site_id)):
        cat, _, n = code.rpartition("-")
        used[cat] = max(used[cat], int(n) if n.isdigit() else 0)

    matched: set[UUID] = set()
    findings = []
    for c in candidates:
        earlier = next(
            (f for f in previous if f.id not in matched and f.category == c.category and _keys(f) & c.keys()), None
        )
        if earlier:
            matched.add(earlier.id)
            code, first_seen = earlier.code, earlier.first_seen
        else:
            used[c.category] += 1
            code, first_seen = f"{c.category}-{used[c.category]:02d}", run.number
        carry = earlier is not None and confirmed
        findings.append(
            IntegrityFinding(
                run_id=run.id,
                site_id=run.site_id,
                code=code,
                category=c.category,
                severity=c.severity,
                help_center_ids=[str(i) for i in c.center_ids],
                title=c.title,
                quotes=c.quotes,
                why=c.why,
                proposed_tier=c.tier,
                proposed_reason=c.reason,
                tier=earlier.tier if carry else c.tier,
                triage_note=earlier.triage_note if carry else c.reason,
                first_seen=first_seen,
                carried_from=prev_run.number if carry else None,
            )
        )

    # Earlier findings not seen again on pages this run reviewed are resolved.
    page_urls = {
        str(p.id): p.url
        for p in db.scalars(select(Page).where(Page.run_id == prev_run.id))
    } if prev_run else {}  # fmt: skip
    resolved = sorted(
        f.code
        for f in previous
        if f.id not in matched
        and f.tier != "drop"
        and all(page_urls.get(q.get("page_id", "")) in reviewed_urls for q in f.quotes)
    )
    return findings, resolved


def locale_label(center_ids: list[str], names: dict[str, str], category: str) -> str:
    """ "US English"; for translations, the translation first: "Deutsch vs. US English"."""
    labels = [names[i] for i in center_ids if i in names]
    if category == "T" and len(labels) == 2:
        return " vs. ".join(reversed(labels))
    return ", ".join(labels)


def metrics(findings: list[IntegrityFinding], resolved: list[str], confirmed: bool) -> dict:
    """The run's integrity numbers. Counts use the tiers as they stand; they
    are shown only once triage is confirmed."""
    firm = [f for f in findings if f.tier == "firm"]
    severity = Counter(f.severity for f in firm)
    return {
        "candidates": len(findings),
        "firm": len(firm),
        "review": sum(1 for f in findings if f.tier == "review"),
        "drop": sum(1 for f in findings if f.tier == "drop"),
        "high": severity["High"],
        "medium": severity["Medium"],
        "low": severity["Low"],
        "by_category": dict(Counter(f.category for f in firm)),
        # Each category's firm findings by severity: the dashboard's bars.
        "severity_by_category": {
            category: dict(Counter(f.severity for f in firm if f.category == category))
            for category in sorted({f.category for f in firm})
        },
        "top": _top(firm),
        "resolved": resolved,
        "confirmed": confirmed,
    }


def _top(firm: list[IntegrityFinding]) -> dict | None:
    """The finding to name first on the dashboard: the most severe firm one, lowest code."""
    order = {"High": 0, "Medium": 1, "Low": 2}
    best = min(firm, key=lambda f: (order.get(f.severity, 3), f.code), default=None)
    return {"code": best.code, "title": best.title, "severity": best.severity} if best else None


def refresh_metrics(db: Session, run: AuditRun) -> None:
    findings = db.scalars(select(IntegrityFinding).where(IntegrityFinding.run_id == run.id)).all()
    resolved = (run.metrics or {}).get("integrity", {}).get("resolved", [])
    confirmed = (run.triage or {}).get("status") == "confirmed"
    run.metrics = {**(run.metrics or {}), "integrity": metrics(findings, resolved, confirmed)}


# ── The stage ─────────────────────────────────────────────────────────────────


async def run_review(db: Session, run: AuditRun, rec, checkpoint, record_stats, unchanged: dict) -> None:
    """The content_integrity stage. ``record_stats(agent, tally)`` adds the
    agent's tokens and counts to the run; ``unchanged`` maps a page id to the
    last audit's page with the same checksum (empty when forcing)."""
    key = "content_integrity"
    db.execute(delete(IntegrityFinding).where(IntegrityFinding.run_id == run.id))
    run.claim_groups = None
    site = run.site
    centers = db.scalars(select(HelpCenter).where(HelpCenter.site_id == site.id).order_by(HelpCenter.position)).all()
    every_root = [Root(c.id, c.name, c.url, c.language, c.is_primary) for c in centers]
    wanted = {str(i) for i in (run.help_center_ids or [])} or {str(c.id) for c in centers}
    roots = [r for r in every_root if str(r.id) in wanted]
    if not roots:
        rec.stage(key, status="skipped", detail="No help center chosen for review")
        return
    by_id = {r.id: r for r in roots}
    pages_by_center: dict[UUID, list[Page]] = defaultdict(list)
    for p in db.scalars(
        select(Page).where(Page.run_id == run.id, Page.http_status == 200, Page.help_center_id.in_(list(by_id)))
    ):
        if p.word_count >= 30:
            pages_by_center[p.help_center_id].append(p)
    articles = [p for r in roots for p in sorted(pages_by_center[r.id], key=lambda p: p.path)]

    try:
        agent = review.load_agent(db, run.organization_id, (site.agent_assignments or {}).get(key))
    except review.AgentUnavailable as exc:
        rec.stage(key, status="skipped", detail=f"Not reviewed: {exc}")
        rec.log(key, "warn", f"No content-integrity review: {exc}.")
        return

    site_categories = set(site.integrity_categories or CATEGORY_CODES)
    enabled = site_categories if run.integrity_categories is None else set(run.integrity_categories)
    categories = sorted(enabled)

    def covers(asked: list[str] | None, needed: set[str] = enabled) -> bool:
        """Was an earlier answer asked for every category this run needs? Answers
        stored before categories were recorded were asked for the site's."""
        return needed <= (site_categories if asked is None else set(asked))

    focus = dict(site_focus=site.focus or "", run_focus=run.focus or "")
    names = ", ".join(r.name for r in roots)
    pairs = [
        (orig, trans, original, other)
        for other, original in (pairings(roots) if "T" in enabled else [])
        for orig, trans in counterparts(pages_by_center[original.id], original, pages_by_center[other.id], other)
    ]
    total = len(articles) + len(pairs)
    done = 0
    rec.stage(key, status="running", done=0, total=total, detail=f"{agent.name} · {agent.model} · {names}")
    rec.log(key, "info", f"{agent.name} started on {len(articles):,} articles and {len(pairs):,} translation pairs "
                         f"in {names}, one per request, focus attached.")  # fmt: skip

    def progress(n: int = 1) -> None:
        nonlocal done
        done += n
        rec.stage(key, done=done, total=total)

    reviewer = review.Review(db, run, key, agent, rec.log, lambda d, t: None, checkpoint)
    kept = Counter()

    # Pass 1: each article on its own.
    task = review.instructions(key, task=_with_categories(TASK_ARTICLE, enabled), answer=ANSWER_ARTICLE, **focus)

    async def one_article(page: Page) -> None:
        prev = unchanged.get(page.id)
        if prev is not None and prev.integrity is not None and covers(prev.integrity.get("categories")):
            page.integrity = prev.integrity
            kept["articles"] += 1
        else:
            raw = await reviewer.ask(page.path, article("P1", page, by_id[page.help_center_id]), task,
                                     parse=review.parse_object)  # fmt: skip
            if raw is None:
                reviewer.failed()
                progress()
                return
            reviewer.tally.failing = 0
            page.integrity = {"issues": _dicts(raw.get("issues")), "claims": _claims(raw.get("claims"), page),
                              "categories": categories}  # fmt: skip
        progress()

    await reviewer.each(articles, one_article)
    if reviewer.tally.failed:
        return _failed(db, rec, key, agent, reviewer.tally, record_stats)

    # Pass 2: each translation against its original.
    task = review.instructions(key, task=_with_categories(TASK_PAIR, enabled), fmt=ISSUE, **focus)

    async def one_pair(pair) -> None:
        orig, trans, original, other = pair
        prev = unchanged.get(trans.id)
        saved = prev.integrity_pair if prev is not None else None
        if (
            saved
            and saved.get("original_url") == orig.url
            and saved.get("original_checksum") == orig.content_hash
            and covers(saved.get("categories"))
        ):
            trans.integrity_pair = saved
            kept["pairs"] += 1
        else:
            material = f"{article('P1', orig, original)}\n\n{article('P2', trans, other)}"
            raw = await reviewer.ask(f"{trans.path} vs {orig.path}", material, task)
            if raw is None:
                reviewer.failed()
                progress()
                return
            reviewer.tally.failing = 0
            trans.integrity_pair = {"original_url": orig.url, "original_checksum": orig.content_hash,
                                    "issues": _dicts(raw), "categories": categories}  # fmt: skip
        progress()

    await reviewer.each(pairs, one_pair)

    candidates: list[Candidate] = []
    malformed = 0
    reviewed: set[str] = set()
    for page in articles:
        if page.integrity is None:
            continue
        reviewed.add(page.url)
        found, bad = verify(page.integrity["issues"], {"P1": (page, by_id[page.help_center_id])}, enabled)
        candidates += found
        malformed += bad
    for orig, trans, original, other in pairs:
        if trans.integrity_pair and trans.integrity_pair.get("original_url") == orig.url:
            refs = {"P1": (orig, original), "P2": (trans, other)}
            found, bad = verify(trans.integrity_pair["issues"], refs, enabled)
            candidates += found
            malformed += bad

    # Pass 3: statements about the same subject, compared across articles.
    matched, method = await _claim_groups(db, run, rec, roots, pages_by_center)
    groups = [i for i, g in enumerate(matched) if claim_groups.worth_asking(g)]
    status = {i: "compared" if i in groups else "agree" for i in range(len(matched))}
    verdicts: Counter = Counter()
    total += len(groups)
    rec.stage(key, total=total, detail=f"{agent.name} · comparing {len(groups):,} statement groups ({method})")
    previous = {} if run.force_reevaluate else {
        r.key: r for r in db.scalars(
            select(ClaimGroupReview).where(ClaimGroupReview.site_id == site.id)
            .order_by(ClaimGroupReview.run_number)
        )
    }  # fmt: skip
    allowed = [c for c in CROSS_ARTICLE if c in enabled]
    task = review.instructions(
        key, task=f"{TASK_GROUP}\n\nLog these categories only: {', '.join(allowed)}.", fmt=GROUP_FINDING, **focus
    )

    async def one_group(index: int) -> None:
        nonlocal malformed
        group = claim_groups.trim(matched[index])
        group_key = claim_groups.group_key(group)
        refs = {f"S{i}": c for i, c in enumerate(group, 1)}
        if group_key in previous and covers(previous[group_key].categories, set(allowed)):
            issues = previous[group_key].issues
            kept["groups"] += 1
            status[index] = "kept"
        else:
            lines = [f"Subject: {group[0].subject}"]
            lines += [f'{ref} · {by_id[c.center_id].name} · {c.slug}: "{c.statement}"' for ref, c in refs.items()]
            raw = await reviewer.ask(f"statements about {group[0].subject!r}", "\n".join(lines), task)
            if raw is None:
                reviewer.failed()
                progress()
                return
            reviewer.tally.failing = 0
            issues = _dicts(raw)
            db.add(ClaimGroupReview(site_id=site.id, key=group_key, run_number=run.number, issues=issues,
                                    categories=allowed))  # fmt: skip
        found, bad = verify_group(issues, refs, enabled)
        verdicts[index] = len(found)
        candidates.extend(found)
        malformed += bad
        progress()

    await reviewer.each(groups, one_group)
    status.update({i: "failed" for i in groups if i not in verdicts})  # failed, or skipped once stopped
    run.claim_groups = {
        "method": method,
        "groups": [
            {"subject": g[0].subject, "status": status[i], "issues": verdicts[i],
             "members": [{"page_id": str(c.page_id), "statement": c.statement} for c in g]}
            for i, g in enumerate(matched)
        ],
    }  # fmt: skip
    if malformed:
        rec.log(key, "warn", f"{agent.name}: {malformed} malformed or out-of-scope candidate(s) dropped.")

    # Findings that need no model.
    if "N" in enabled:
        candidates += code_findings(db, run, roots, every_root, pages_by_center)
    if "T" in enabled:
        pairs_by_center: dict = defaultdict(list)
        for orig, trans, original, other in pairs:
            pairs_by_center[(other.id, original.id)].append((orig, trans))
        for other, original in pairings(roots):
            pairs_by_center.setdefault((other.id, original.id), [])
        candidates += missing_translations(pairs_by_center, by_id, pages_by_center)

    tally = reviewer.tally
    findings, resolved = assign(db, run, merge(candidates), reviewed)
    center_names = {str(c.id): c.name for c in centers}
    for f in findings:
        f.locale = locale_label(f.help_center_ids, center_names, f.category)
        f.agent_id, f.agent_name = agent.id, agent.name
        db.add(f)
    # Only a complete review with nothing to triage confirms itself.
    clean = not findings and not tally.errors
    run.triage = {"status": "confirmed", "confirmed_at": None} if clean else {"status": "pending"}
    run.metrics = {**(run.metrics or {}), "integrity": metrics(findings, resolved, confirmed=clean)}
    tally.findings = len(findings)
    record_stats(agent, tally)

    unverified = sum(1 for f in findings for q in f.quotes if not q["verified"])
    high = sum(1 for f in findings if f.severity == "High")
    parts = [f"{agent.name}: {len(findings):,} candidates ({high:,} High) in {names}"]
    parts.append(
        f"{len(articles):,} articles ({kept['articles']:,} unchanged kept), {len(pairs):,} translation pairs "
        f"({kept['pairs']:,} kept), {len(groups):,} statement groups by {method} ({kept['groups']:,} kept)"
    )
    if unverified:
        parts.append(f"{unverified:,} quotes not found on their page (sent to review)")
    if resolved:
        parts.append(f"{len(resolved):,} earlier findings resolved")
    if tally.errors:
        parts.append(f"{tally.errors:,} failed requests")
    if tally.note:
        parts.append(tally.note)
    rec.stage(key, status="done", done=total, total=total, detail=", ".join(parts))
    rec.log(key, "info", f"{', '.join(parts)}; {tally.tokens:,} tokens. Triage before anything is counted.")
    db.commit()


def _failed(db: Session, rec, key: str, agent, tally, record_stats) -> None:
    """Nothing to triage and nothing resolved: no answer isn't a clean bill."""
    record_stats(agent, tally)
    detail = (
        f"{agent.name} didn't review this audit: {tally.errors:,} failed request(s)"
        + (f", {tally.note}" if tally.note else "")
        + ". See the run log, then analyze again."
    )
    rec.stage(key, status="failed", detail=detail)
    rec.log(key, "error", detail)
    db.commit()


def _dicts(value) -> list[dict]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _claims(value, page: Page) -> list[dict]:
    """Claims with a subject and a statement that is really on the page."""
    out = []
    for item in _dicts(value):
        subject, statement = str(item.get("subject", "")).strip(), str(item.get("statement", "")).strip()
        if subject and statement and review.quote_found(statement, page.content.get("text", ""), page.title):
            out.append({"subject": subject[:120], "statement": statement[:600]})
    return out[:MAX_CLAIMS]


async def _claim_groups(db: Session, run: AuditRun, rec, roots: list[Root], pages: dict) -> tuple[list, str]:
    """Pass 3's groups of two or more statements, per help center, and how
    they were matched. Embeddings when the site's setting finds a key; keywords
    otherwise, or when embedding fails."""
    per_center = {
        r.id: [
            claim_groups.Claim(p.id, p.url, slug(p, r), r.id, c["subject"], c["statement"])
            for p in pages[r.id]
            if p.integrity
            for c in p.integrity.get("claims", [])
        ]
        for r in roots
    }
    embedder = embeddings.choose(db, run.organization_id, run.site.claim_matching or "auto")
    method = "keywords"
    grouped: list[list[claim_groups.Claim]] = []
    if embedder is not None:
        try:
            for found in per_center.values():
                vectors = await embedder.embed([c.text for c in found]) if found else []
                grouped += claim_groups.embedding_groups(found, vectors)
            method = f"embeddings ({embedder.label})"
        except embeddings.EmbeddingError as exc:
            rec.log("content_integrity", "warn", f"Embedding failed ({exc}); matching statements by keywords instead.")
            grouped = []
    if method == "keywords":
        for found in per_center.values():
            grouped += claim_groups.keyword_groups(found)
    return [g for g in grouped if len(g) > 1], method


def _with_categories(task: str, enabled: set[str]) -> str:
    listed = "; ".join(f"{c} {CATEGORY_LABELS[c]}" for c in CATEGORY_CODES if c in enabled)
    return f"{task}\n\nLog these categories only: {listed}. Refer to articles by their P number."


# ── Triage ───────────────────────────────────────────────────────────────────


def triage_feedback(findings: list[IntegrityFinding], site_name: str, number: int) -> str:
    """What the person changed from the reviewer's proposals, for its memory."""
    lines = []
    for f in sorted(findings, key=lambda f: f.code):
        if f.tier != f.proposed_tier:
            note = f" Note: {f.triage_note}" if f.triage_note and f.triage_note != f.proposed_reason else ""
            lines.append(f'- {f.code} "{f.title}" ({f.severity}): proposed {f.proposed_tier}, judged {f.tier}.{note}')
    if not lines:
        return ""
    return f"Triage of {site_name} audit #{number}: the user's calls where they differed from yours.\n" + "\n".join(
        lines
    )


def confirm(db: Session, run: AuditRun, email: str) -> str:
    """Confirm the run's triage; returns the feedback added to the reviewer's memory, if any."""
    from hop_core.models.agent import Agent

    findings = db.scalars(select(IntegrityFinding).where(IntegrityFinding.run_id == run.id)).all()
    run.triage = {"status": "confirmed", "confirmed_at": datetime.now(UTC).isoformat(), "confirmed_by": email}
    refresh_metrics(db, run)
    feedback = triage_feedback(findings, run.site.name, run.number)
    agent_id = next((f.agent_id for f in findings if f.agent_id), None)
    agent = db.get(Agent, agent_id) if agent_id else None
    if feedback and agent is not None and agent.organization_id == run.organization_id:
        entry = f"### Triage {datetime.now(UTC):%Y-%m-%d} by {email}\n\n{feedback}"
        existing = (agent.feedback_memory or "").rstrip()
        agent.feedback_memory = f"{existing}\n\n{entry}" if existing else entry
    return feedback


def candidates_total(db: Session, run_id: UUID) -> int:
    return db.scalar(select(func.count()).select_from(IntegrityFinding).where(IntegrityFinding.run_id == run_id))
