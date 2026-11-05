"""The full findings report (milestone 7), in the skill's structure
(`report-structure.md`): summary, findings by category, contradictions,
translation mismatches, instructions, the remaining categories, items for
review, then a site-health appendix.

Built from the tiers as they stand, confirmed or not: firm findings are
counted, review items are listed and excluded from the totals, and only
dropped ones are left out. ``confirmed`` says whether a person has confirmed
that triage yet; the page shows it, the exported document doesn't. Every table is the same
small model (columns, rows of cells, each cell a list of runs) so the page,
the Letter PDF and the Word file render from one structure. Leads are written
here from the counts: plain and factual, no adjectives, no product mention.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import runner
from models import AuditRun, IntegrityFinding, LinkResult, Page
from readability import MIN_WORDS

SEVERITIES = ("High", "Medium", "Low")
SEVERITY_ORDER = {s: i for i, s in enumerate(SEVERITIES)}
SEVERITY_LINE = (
    "High: a customer could act on wrong information, or the content is compliance-sensitive. "
    "Medium: confusing, conflicting, or outdated, with lower stakes. Low: cosmetic or structural."
)
CATEGORY_LABELS = {
    "C": "Contradictions between articles",
    "T": "Translations that don't match",  # named by language in the report
    "U": "Instructions that don't match each other or the app",
    "N": "Links and duplicates",
    "L": "Retired products",
    "O": "Outdated content",
    "TM": "Terminology",
    "X": "Structure and publishing errors",
    "S": "Scope errors",
    "D": "Disclosure text",
}
REMAINING = ("N", "L", "O", "TM", "X", "S", "D")  # the skill's order for section 6
LANGUAGES = {
    "en": "English", "fr": "French", "de": "German", "es": "Spanish", "it": "Italian", "pt": "Portuguese",
    "nl": "Dutch", "sv": "Swedish", "da": "Danish", "nb": "Norwegian", "no": "Norwegian", "fi": "Finnish",
    "pl": "Polish", "cs": "Czech", "tr": "Turkish", "ru": "Russian", "ja": "Japanese", "ko": "Korean",
    "zh": "Chinese", "ar": "Arabic", "he": "Hebrew", "hi": "Hindi",
}  # fmt: skip
WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


# ── The table model ──────────────────────────────────────────────────────────


@dataclass
class Run:
    """A piece of a cell: text, quote (exact, in quotation marks), slug, note
    (a translation or aside), sev (a severity pill), code (an ID), br (new line)."""

    kind: str
    text: str = ""


Cell = list[Run]


@dataclass
class Column:
    label: str
    num: bool = False


@dataclass
class Table:
    columns: list[Column]
    rows: list[list[Cell]]
    heading: str = ""  # a ### subsection above the table
    total: list[Cell] | None = None  # a bold total row
    more: str = ""  # a line under the table


@dataclass
class Section:
    id: str
    title: str
    lead: str
    tables: list[Table] = field(default_factory=list)
    after: str = ""  # a closing line (e.g. the severity definitions)


@dataclass
class Metric:
    label: str
    value: str
    detail: str


@dataclass
class Report:
    ready: bool
    confirmed: bool = False
    reason: str = ""
    title: str = ""
    subject: str = ""
    as_of: datetime | None = None
    author: str = ""
    sections: list[Section] = field(default_factory=list)
    appendix: list[Metric] = field(default_factory=list)
    counts: dict = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────────────


def text(value: str) -> Cell:
    return [Run("text", value)]


def columns(*labels: str) -> list[Column]:
    return [Column(label) for label in labels]


def num(value: int | str) -> Cell:
    return [Run("text", f"{value:,}" if isinstance(value, int) else value)]


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def spelled(n: int) -> str:
    """Small counts in words, as the report's prose reads ("three help centers")."""
    return WORDS[n] if 0 <= n < len(WORDS) else f"{n:,}"


def language(tag: str, fallback: str) -> str:
    return LANGUAGES.get(tag.split("-")[0].lower(), fallback)


def joined(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def ordered(findings: list[IntegrityFinding]) -> list[IntegrityFinding]:
    return sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 3), f.code))


def quotes(f: IntegrityFinding, keep=lambda q: True) -> Cell:
    """The finding's quotes, each exact, with its slug and any note, one per line.
    Quote labels (A, B, EN…) are left out: the slug and the column say where."""
    cell: Cell = []
    for q in f.quotes:
        if not keep(q):
            continue
        if cell:
            cell.append(Run("br"))
        cell.append(Run("quote", q["text"]))
        if q.get("note"):
            cell.append(Run("note", q["note"]))
        if q.get("slug"):
            cell.append(Run("slug", q["slug"]))
    return cell


def severity(f: IntegrityFinding) -> Cell:
    return [Run("sev", f.severity)]


# ── Building ─────────────────────────────────────────────────────────────────


def build(db: Session, run: AuditRun) -> Report:
    findings = db.scalars(select(IntegrityFinding).where(IntegrityFinding.run_id == run.id)).all()
    if not findings and not (run.metrics or {}).get("integrity"):
        return Report(False, reason="Content integrity hasn't run for this audit, so there is nothing to report.")
    site = run.site
    prospect = site.prospect or {}
    subject = (prospect.get("company") or "").strip() or site.name
    firm = [f for f in findings if f.tier == "firm"]
    review = [f for f in findings if f.tier == "review"]
    centers = [r for r in runner.roots_of(db, site.id) if not run.help_center_ids or str(r.id) in run.help_center_ids]
    primary = next((c for c in centers if c.is_primary), centers[0] if centers else None)
    page_center = dict(db.execute(select(Page.id, Page.help_center_id).where(Page.run_id == run.id)).all())
    names = {c.id: language(c.language, c.name) for c in centers}
    by_cat: dict[str, list[IntegrityFinding]] = defaultdict(list)
    for f in firm:
        by_cat[f.category].append(f)

    articles = dict(
        db.execute(
            select(Page.help_center_id, func.count())
            .where(Page.run_id == run.id, Page.http_status == 200, Page.word_count >= MIN_WORDS)
            .group_by(Page.help_center_id)
        ).all()
    )
    pages = dict(
        db.execute(
            select(Page.help_center_id, func.count()).where(Page.run_id == run.id).group_by(Page.help_center_id)
        ).all()
    )
    total_articles = sum(articles.get(c.id, 0) for c in centers)
    high = sum(1 for f in firm if f.severity == "High")
    others = [c for c in centers if c is not primary]
    other_names = list(dict.fromkeys(names[c.id] for c in others))
    t_label = (
        f"{joined(other_names)} and {names[primary.id]} versions don't match"
        if primary and other_names and set(other_names) != {names[primary.id]}
        else "Language versions don't match"
    )
    labels = {**CATEGORY_LABELS, "T": t_label}

    sections = [
        _summary(subject, centers, articles, pages, total_articles, len(firm), high, len(review)),
        _by_category(by_cat, labels, len(firm)),
    ]
    if by_cat.get("C"):
        what = "two articles give a customer different answers"
        sections.append(_conflicts("contradictions", labels["C"], by_cat["C"], what, "Conflicting text (article)"))
    if by_cat.get("T") and primary:
        sections.append(_translation(t_label, by_cat["T"], primary, names, page_center))
    if by_cat.get("U"):
        what = "articles name different menus, numbers, or steps for the same task"
        sections.append(_conflicts("instructions", labels["U"], by_cat["U"], what, "Text (article)"))
    remaining = [c for c in REMAINING if by_cat.get(c)]
    if remaining:
        sections.append(_remaining(remaining, by_cat, labels))
    if review:
        sections.append(_review(review))

    author = (prospect.get("sender_name") or "").strip() or (run.triage or {}).get("confirmed_by", "")
    confirmed = (run.triage or {}).get("status") == "confirmed"
    return Report(
        True,
        confirmed=confirmed,
        title=f"{subject} — Content Integrity Review",
        subject=subject,
        as_of=run.started_at or run.created_at,
        author=author,
        sections=sections,
        appendix=_appendix(db, run, centers),
        counts={
            "firm": len(firm),
            "high": high,
            "review": len(review),
            "articles": total_articles,
            "help_centers": len(centers),
        },  # fmt: skip
    )


def _summary(subject, centers, articles, pages, total, firm, high, review) -> Section:
    lead = (
        f"A review of {plural(total, 'article')} across {subject}'s {spelled(len(centers))} public help "
        f"{'center' if len(centers) == 1 else 'centers'} found {plural(firm, 'confirmed issue')}, "
        f"{high:,} of them High, meaning a customer could act on wrong information or the content is "
        "compliance-sensitive. We counted content that is wrong, conflicting, outdated, or missing its scope; "
        "differences where both versions are accurate were not counted."
    )
    if review:
        lead += (
            f" A further {plural(review, 'item')} whose correctness depends on internal policy "
            f"{'is' if review == 1 else 'are'} listed for review and excluded from every total."
        )
    rows = []
    for c in centers:
        n = articles.get(c.id, 0)
        reviewed = num(n)
        if pages.get(c.id, 0) != n:
            reviewed.append(Run("note", f"{pages.get(c.id, 0):,} pages"))
        site = urlsplit(c.url)
        rows.append([text(c.name), [Run("code", (site.netloc + site.path).rstrip("/"))], reviewed])
    table = Table(
        [Column("Help center"), Column("Site"), Column("Articles reviewed", num=True)],
        rows,
        total=[text("Total"), text(""), num(total)] if len(centers) > 1 else None,
    )
    return Section(
        "summary", "Summary", lead, [table],
        after="Quotes are exact, trimmed to the clause that matters; articles are identified by URL slug.",
    )  # fmt: skip


def _by_category(by_cat, labels, firm) -> Section:
    counts = sorted(by_cat.items(), key=lambda kv: (-len(kv[1]), list(labels).index(kv[0])))
    rows = []
    for code, found in counts:
        sev = Counter(f.severity for f in found)
        rows.append([text(labels[code]), num(len(found)), *(num(sev[s]) for s in SEVERITIES)])
    totals = Counter(f.severity for fs in by_cat.values() for f in fs)
    if len(counts) >= 2:
        (first, a), (second, b) = counts[0], counts[1]
        lead = (
            f"{labels[first]} ({len(a):,}) and {labels[second]} ({len(b):,}) "
            f"account for {len(a) + len(b):,} of the {plural(firm, 'issue')}."
        )
    elif counts:
        lead = f"All {plural(firm, 'issue')} are in one category: {labels[counts[0][0]].lower()}."
    else:
        lead = "No issues were confirmed."
    table = Table(
        [Column("Category"), Column("Total", True), Column("High", True), Column("Medium", True), Column("Low", True)],
        rows,
        total=[text("Total"), num(firm), *(num(totals[s]) for s in SEVERITIES)],
    )
    return Section("categories", "Findings by category", lead, [table], after=SEVERITY_LINE)


def _high_part(found) -> str:
    high = sum(1 for f in found if f.severity == "High")
    if not high:
        return ""
    if len(found) == 1:
        return ", rated High"
    return ", all of them High" if high == len(found) else f", {high:,} of them High"


def _conflicts(id_, label, found, what, text_column) -> Section:
    rows = [[[Run("code", f.code)], severity(f), text(f.locale), text(f.title), quotes(f)] for f in ordered(found)]
    lead = f"{plural(len(found), 'finding')} where {what}{_high_part(found)}."
    table = Table(columns("ID", "Severity", "Help center", "Issue", text_column), rows)
    return Section(id_, f"{label} ({len(found)})", lead, [table])


def _translation(label, found, primary, names, page_center) -> Section:
    def is_primary(q) -> bool:
        return page_center.get(_uuid(q.get("page_id"))) == primary.id

    other_names = list(dict.fromkeys(n for cid, n in names.items() if cid != primary.id))
    other_label = other_names[0] if len(other_names) == 1 else "Translation"

    def translated(q) -> bool:
        return not is_primary(q)

    rows = [
        [[Run("code", f.code)], severity(f), text(f.title), quotes(f, is_primary), quotes(f, translated)]
        for f in ordered(found)
    ]
    lead = (
        f"{plural(len(found), 'translated article')} change the meaning, leave out content, or don't match "
        f"the {names[primary.id]}{_high_part(found)}."
    )
    table = Table(columns("ID", "Severity", "Issue", names[primary.id], f"{other_label} (article)"), rows)
    return Section("translation", f"{label} ({len(found)})", lead, [table])


def _remaining(codes, by_cat, labels) -> Section:
    tables = []
    for code in codes:
        rows = []
        for f in ordered(by_cat[code]):
            detail = quotes(f)
            if f.why:
                detail += [Run("br"), Run("text", f.why)] if detail else [Run("text", f.why)]
            rows.append([[Run("code", f.code)], severity(f), text(f.locale), text(f.title), detail])
        tables.append(
            Table(
                columns("ID", "Severity", "Help center", "Issue", "Detail"),
                rows,
                heading=f"{labels[code]} ({len(by_cat[code])})",
            )
        )
    found = [f for c in codes for f in by_cat[c]]
    high = [f.code for f in ordered(found) if f.severity == "High"]
    lead = f"{plural(len(found), 'more issue')} in {plural(len(codes), 'category', 'categories')}"
    lead += f"; High: {', '.join(high)}." if high else ", none of them High."
    return Section("remaining", "Remaining categories", lead, tables)


def _review(found) -> Section:
    rows = [
        [[Run("code", f.code)], text(f.locale), text(f.title), quotes(f), text(f.triage_note or f.proposed_reason)]
        for f in sorted(found, key=lambda f: f.code)
    ]
    table = Table(columns("ID", "Help center", "Issue", "Text (article)", "Why it may be accurate"), rows)
    return Section(
        "review", f"Items for review ({len(found)})",
        "These may be accurate depending on internal policy, so they are not counted.", [table],
    )  # fmt: skip


def _appendix(db: Session, run: AuditRun, centers) -> list[Metric]:
    """Mechanical checks from the same crawl, kept apart from the integrity findings."""
    m = run.metrics or {}
    read = db.scalars(select(Page).where(Page.run_id == run.id, Page.http_status == 200)).all()
    out = []
    if m.get("flesch") is not None:
        per = defaultdict(list)
        lang = {c.id: c.language.split("-")[0] for c in centers}
        for p in read:
            if p.flesch is not None and p.help_center_id in lang:
                per[lang[p.help_center_id]].append(p.flesch)
        detail = " · ".join(f"{k} {sum(v) / len(v):.1f}" for k, v in per.items()) if len(per) > 1 else ""
        out.append(Metric("Avg Flesch Reading Ease", f"{m['flesch']:.1f}", detail))
        out.append(Metric("Pages under Flesch 50", f"{m.get('under_50', 0):,}", f"of {m.get('pages', len(read)):,}"))
    if "broken" in m:
        internal = dict(
            db.execute(
                select(LinkResult.internal, func.count())
                .where(LinkResult.run_id == run.id, LinkResult.outcome == "broken")
                .group_by(LinkResult.internal)
            ).all()
        )
        out.append(
            Metric(
                "Broken links",
                f"{m['broken']:,}",
                f"{internal.get(True, 0):,} internal · {internal.get(False, 0):,} external",
            )
        )
    if "seo_issues" in m:
        missing = sum(
            1 for p in read for c in (p.seo or []) if c.get("key") == "description" and c.get("status") == "error"
        )
        out.append(Metric("SEO issues", f"{m['seo_issues']:,}", plural(missing, "missing description")))
    return out


def _uuid(value):
    try:
        return UUID(str(value))
    except ValueError:
        return None
