"""Content integrity: the Content Integrity Reviewer reads every article in
every reviewed help center and logs what is wrong, conflicting, outdated,
missing or unscoped (the skill's assessment, in its context files).

Articles go in batches per help center, a section at a time so related
articles are read together; translated articles go as pairs with their
primary-language version (and two versions of one language with each other).
A site too large for one prompt is therefore read in parts: contradictions
between distant sections can be missed.

Candidates are verified (every quote must be on its page, or the finding
goes to review), merged across batches, and given stable codes: a candidate
matching an earlier run's finding keeps its code, and its tier when that
run's triage was confirmed. Nothing is counted until a person confirms.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

import review
from catalog import CATEGORY_CODES, INTEGRITY_CATEGORIES
from models import AuditRun, HelpCenter, IntegrityFinding, Page
from scope import Root, relative_path

ARTICLE_TEXT_LIMIT = 8000  # characters per article in a batch
BATCH_CHARS = 60_000  # characters of article text per batch
MISSING_LISTED = 8  # untranslated articles quoted on the mechanical finding
SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
CATEGORY_LABELS = {c.code: c.label for c in INTEGRITY_CATEGORIES}

TASK_ARTICLES = (
    "Assess these articles for content-integrity issues, following your assessment, counting rule and triage "
    "files. They are from one help center, a section at a time. Log only content that is wrong, conflicting, "
    "outdated, missing or unscoped; never differences where both versions are accurate."
)
TASK_PAIRS = (
    "Compare each translated article with the version it translates, following your assessment, counting rule "
    "and triage files: changed meaning, missing or added sentences, untranslated strings, one version visibly "
    "older. Also log anything else wrong inside either article. Never log wording differences where both say "
    "the same thing."
)
FORMAT = (
    '{"category": "C|U|T|TM|D|L|S|O|N|X", "severity": "High|Medium|Low", "title": "under 100 characters", '
    '"quotes": [{"label": "A|B|EN|FR…", "page": "P1", "text": "exact text, trimmed to the clause that matters", '
    '"note": "a translation of a non-English quote, or empty"}], "why": "one sentence on why it is a problem", '
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


# ── Articles and batches ──────────────────────────────────────────────────────


def slug(page: Page, root: Root) -> str:
    rel = relative_path(page.url, root).strip("/")
    prefix = root.url.split("://", 1)[-1].split("/", 1)[-1].strip("/")
    return f"{prefix}/{rel}".strip("/") if prefix else (rel or "(home)")


def article_batches(pages: list[Page], budget: int = BATCH_CHARS) -> list[list[Page]]:
    """One help center's articles packed by section, a section kept whole where it fits."""
    by_section: dict[str, list[Page]] = defaultdict(list)
    for p in sorted(pages, key=lambda p: (p.section, p.path)):
        by_section[p.section].append(p)
    batches, current, size = [], [], 0
    for section_pages in by_section.values():
        for page in section_pages:
            n = min(len(page.content.get("text", "")), ARTICLE_TEXT_LIMIT)
            if current and size + n > budget:
                batches.append(current)
                current, size = [], 0
            current.append(page)
            size += n
    if current:
        batches.append(current)
    return batches


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


def pack_pairs(pairs: list[tuple[Page, Page]], budget: int = BATCH_CHARS) -> list[list[tuple[Page, Page]]]:
    batches, current, size = [], [], 0
    for a, b in pairs:
        n = sum(min(len(p.content.get("text", "")), ARTICLE_TEXT_LIMIT) for p in (a, b))
        if current and size + n > budget:
            batches.append(current)
            current, size = [], 0
        current.append((a, b))
        size += n
    if current:
        batches.append(current)
    return batches


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
        "resolved": resolved,
        "confirmed": confirmed,
    }


def refresh_metrics(db: Session, run: AuditRun) -> None:
    findings = db.scalars(select(IntegrityFinding).where(IntegrityFinding.run_id == run.id)).all()
    resolved = (run.metrics or {}).get("integrity", {}).get("resolved", [])
    confirmed = (run.triage or {}).get("status") == "confirmed"
    run.metrics = {**(run.metrics or {}), "integrity": metrics(findings, resolved, confirmed)}


# ── The stage ─────────────────────────────────────────────────────────────────


async def run_review(db: Session, run: AuditRun, rec, checkpoint, record_stats) -> None:
    """The content_integrity stage. ``record_stats(agent, tally)`` adds the
    agent's tokens and counts to the run (shared with the other analyses)."""
    key = "content_integrity"
    db.execute(delete(IntegrityFinding).where(IntegrityFinding.run_id == run.id))
    site = run.site
    centers = db.scalars(select(HelpCenter).where(HelpCenter.site_id == site.id).order_by(HelpCenter.position)).all()
    wanted = {str(i) for i in (run.help_center_ids or [])} or {str(c.id) for c in centers}
    roots = [Root(c.id, c.name, c.url, c.language, c.is_primary) for c in centers if str(c.id) in wanted]
    if not roots:
        rec.stage(key, status="skipped", detail="No help center chosen for review")
        return
    by_id = {r.id: r for r in roots}
    pages = db.scalars(
        select(Page).where(Page.run_id == run.id, Page.http_status == 200, Page.help_center_id.in_(list(by_id)))
    ).all()
    pages_by_center: dict[UUID, list[Page]] = defaultdict(list)
    for p in pages:
        if p.word_count >= 30:
            pages_by_center[p.help_center_id].append(p)

    try:
        agent = review.load_agent(db, run.organization_id, (site.agent_assignments or {}).get(key))
    except review.AgentUnavailable as exc:
        rec.stage(key, status="skipped", detail=f"Not reviewed: {exc}")
        rec.log(key, "warn", f"No content-integrity review: {exc}.")
        return

    enabled = set(site.integrity_categories or CATEGORY_CODES)
    shared = dict(site_focus=site.focus or "", run_focus=run.focus or "")
    task_articles = review.instructions(key, task=_with_categories(TASK_ARTICLES, enabled), fmt=FORMAT, **shared)
    task_pairs = review.instructions(key, task=_with_categories(TASK_PAIRS, enabled), fmt=FORMAT, **shared)

    jobs: list[tuple[str, str, dict]] = []  # (task, material, refs)
    for root in roots:
        for batch in article_batches(pages_by_center[root.id]):
            refs = {f"P{i}": (p, root) for i, p in enumerate(batch, 1)}
            head = f"Help center: {root.name} ({root.language}{', primary' if root.is_primary else ''})\n\n"
            jobs.append((task_articles, head + "\n\n".join(article(r, p, rt) for r, (p, rt) in refs.items()), refs))
    pairs_by_center = {}
    if "T" in enabled:
        for other, original in pairings(roots):
            matched = counterparts(pages_by_center[original.id], original, pages_by_center[other.id], other)
            pairs_by_center[(other.id, original.id)] = matched
            for batch in pack_pairs(matched):
                refs, blocks = {}, []
                for n, (orig, trans) in enumerate(batch, 1):
                    a, b = f"P{2 * n - 1}", f"P{2 * n}"
                    refs[a], refs[b] = (orig, original), (trans, other)
                    blocks.append(f"## Pair {n}\n{article(a, orig, original)}\n\n{article(b, trans, other)}")
                jobs.append((task_pairs, "\n\n".join(blocks), refs))

    names = ", ".join(r.name for r in roots)
    rec.stage(key, status="running", done=0, total=len(jobs), detail=f"{agent.name} · {agent.model} · {names}")
    rec.log(
        key,
        "info",
        f"{agent.name} started on {sum(len(v) for v in pages_by_center.values()):,} articles in {len(roots)} help "
        f"center(s): {len(jobs)} batches, {len(enabled)} categories, focus attached.",
    )
    reviewer = review.Review(db, run, key, agent, rec.log, lambda d, t: rec.stage(key, done=d, total=t), checkpoint)
    candidates: list[Candidate] = []
    malformed = 0
    for n, (task, material, refs) in enumerate(jobs, 1):
        raw = await reviewer.ask(n, material, task)
        if raw is None:
            if reviewer.failed():
                break
        else:
            reviewer.tally.failing = 0
            found, bad = verify(raw, refs, enabled)
            candidates += found
            malformed += bad
        rec.stage(key, done=n, detail=f"{agent.name} · {len(merge(candidates)):,} candidates so far")
    if malformed:
        rec.log(key, "warn", f"{agent.name}: {malformed} malformed or out-of-scope candidate(s) dropped.")

    if "T" in enabled:
        candidates += missing_translations(pairs_by_center, by_id, pages_by_center)
    reviewed = {p.url for v in pages_by_center.values() for p in v}
    findings, resolved = assign(db, run, merge(candidates), reviewed)
    center_names = {str(c.id): c.name for c in centers}
    for f in findings:
        f.locale = locale_label(f.help_center_ids, center_names, f.category)
        f.agent_id, f.agent_name = agent.id, agent.name
        db.add(f)
    run.triage = {"status": "pending"} if findings else {"status": "confirmed", "confirmed_at": None}
    run.metrics = {**(run.metrics or {}), "integrity": metrics(findings, resolved, confirmed=not findings)}
    reviewer.tally.findings = len(findings)
    record_stats(agent, reviewer.tally)

    unverified = sum(1 for f in findings for q in f.quotes if not q["verified"])
    high = sum(1 for f in findings if f.severity == "High")
    parts = [f"{agent.name}: {len(findings):,} candidates ({high:,} High) in {names}"]
    if unverified:
        parts.append(f"{unverified:,} quotes not found on their page (sent to review)")
    if resolved:
        parts.append(f"{len(resolved):,} earlier findings resolved")
    if reviewer.tally.errors:
        parts.append(f"{reviewer.tally.errors:,} failed batches")
    if reviewer.tally.note:
        parts.append(reviewer.tally.note)
    rec.stage(key, status="done", detail=", ".join(parts))
    rec.log(key, "info", f"{', '.join(parts)}; {reviewer.tally.tokens:,} tokens. Triage before anything is counted.")
    db.commit()


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
