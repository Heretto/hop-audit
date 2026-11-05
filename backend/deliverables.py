"""Prospect deliverables (milestone 8): the lead one-sheet and the executive
brief, rendered from the skill's templates, plus the internal note.

What a one-sheet says comes from two places:

- the triage as it stands (confirmed or not; the hand-off checklist says
  which), read every time a sheet is rendered: the stats, categories,
  severity split, issue mix, the three examples (the triage's one-sheet
  picks), the eyebrow, the review sentences and the footnote. These can't
  drift from the confirmed totals.
- the copy, written once by the Collateral Writer and then edited by people:
  headlines, the subhead's opening, the executive lead sentence, three "why
  it matters" lines and three impact cards (``Copy``). The counts it was
  written against are kept, so a later change to the triage shows as a
  mismatch on the hand-off checklist.

Rules and length budgets are the skill's (`onesheet-data.md`,
`business-imperatives.md`); the writer gets them as its context files.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import rendering
import report
import review
import runner
from models import AuditRun, Deliverables, IntegrityFinding, Page
from readability import MIN_WORDS

PAGE_H = 1056  # Letter at 96 dpi; a sheet taller than this overflows
KINDS = ("lead", "exec")
TEMPLATES = {"lead": "onesheet_lead.html", "exec": "onesheet_exec.html"}
IMPERATIVES = ("Risk", "Customer Acquisition", "Customer Retention", "Cost")
MIX_COLORS = ["#79ecdd", "#2bb1a9", "#4f8fa0", "#3c5a70"]  # the skill's build_onesheet.py
# Length budgets from onesheet-data.md, for the editor and the writer.
BUDGETS = {
    "headline_line1": 26, "headline_line2": 26, "subhead": 260, "exec_headline": 45, "lead_sentence": 160,
    "why": 95, "impact_title": 45, "impact_body": 190, "impact_evidence": 150,
}  # fmt: skip
# Category labels as the one-sheets word them (the skill's approved examples).
SHEET_LABELS = {
    "C": "Contradictions between articles",
    "U": "Instructions don't match the app",
    "N": "Broken or misdirected links",
    "L": "Retired products still shown",
    "O": "Outdated content",
    "TM": "Inconsistent terminology",
    "X": "Structure and publishing errors",
    "S": "Product rules stated as general",
    "D": "Disclosure text that conflicts",
}
MIX_LABELS = {
    "C": "Contradictions between articles",
    "U": "Mismatched instructions",
    "N": "Links and duplicates",
    "L": "Retired products",
    "O": "Outdated content",
    "TM": "Terminology",
    "X": "Structure errors",
    "S": "Scope errors",
    "D": "Disclosure text",
}
DEFAULT_CTA = {
    "lead": ("The full findings are ready to walk through",
             "Every issue with exact quoted text, URLs, and severity. 30 minutes."),
    "exec": ("Worth 20 minutes to walk through what we found?",
             "The full findings, with every quote and where it appears, are ready."),
}  # fmt: skip


# ── The copy ─────────────────────────────────────────────────────────────────


class WhyLine(BaseModel):
    imperative: Literal["Risk", "Customer Acquisition", "Customer Retention", "Cost"] = "Risk"
    ai: bool = False  # an AI point, filed under Risk or Cost
    lead: str = ""
    text: str = ""
    codes: list[str] = []  # the findings it traces to


class Impact(BaseModel):
    tone: Literal["risk", "cost"] = "risk"
    label: str = ""
    title: str = ""
    body: str = ""
    evidence: str = ""
    codes: list[str] = []


class Copy(BaseModel):
    """What the Collateral Writer writes, and people edit."""

    industry: str = ""
    headline_line1: str = ""
    headline_line2: str = ""
    subhead_lead: str = ""  # what structured content makes possible; the review sentence follows
    exec_headline: str = ""
    lead_sentence: str = ""
    why: list[WhyLine] = Field(default_factory=list, max_length=3)
    impacts: list[Impact] = Field(default_factory=list, max_length=3)


# ── Facts from the triage ────────────────────────────────────────────────────


@dataclass
class Facts:
    prospect: str
    as_of: datetime | None
    firm: list[IntegrityFinding]
    review: list[IntegrityFinding]
    articles: int
    centers: list
    languages: list[str]  # language names, primary first
    hosts: list[str]
    blocked: list[str] = field(default_factory=list)  # help centers the crawler couldn't read
    labels: dict[str, str] = field(default_factory=dict)  # sheet category labels, with T named
    mix_labels: dict[str, str] = field(default_factory=dict)

    @property
    def severity(self) -> Counter:
        return Counter(f.severity for f in self.firm)

    @property
    def counts(self) -> dict[str, int]:
        return {"firm": len(self.firm), "high": self.severity["High"], "review": len(self.review),
                "articles": self.articles, "help_centers": len(self.centers)}  # fmt: skip

    @property
    def examples(self) -> list[IntegrityFinding]:
        """The triage's one-sheet picks, in their order: three, then a backup."""
        return sorted((f for f in self.firm if f.example_rank), key=lambda f: f.example_rank)

    @property
    def date(self) -> str:
        return f"{self.as_of:%B} {self.as_of.day}, {self.as_of:%Y}" if self.as_of else ""


def facts(db: Session, run: AuditRun) -> Facts:
    site = run.site
    findings = db.scalars(select(IntegrityFinding).where(IntegrityFinding.run_id == run.id)).all()
    centers = [r for r in runner.roots_of(db, site.id) if not run.help_center_ids or str(r.id) in run.help_center_ids]
    primary = next((c for c in centers if c.is_primary), centers[0] if centers else None)
    languages = list(dict.fromkeys(report.language(c.language, c.name) for c in [primary, *centers] if c))
    articles = db.scalar(
        select(func.count()).where(
            Page.run_id == run.id, Page.http_status == 200, Page.word_count >= MIN_WORDS,
            Page.help_center_id.in_([c.id for c in centers]),
        )
    )  # fmt: skip
    others = languages[1:]
    t_label = f"{report.joined(others)} and {languages[0]} don't match" if others else "Language versions don't match"
    t_mix = f"{report.joined(others)} vs. {languages[0]}" if others else "Translations"
    read = {c for (c,) in db.execute(select(Page.help_center_id).where(Page.run_id == run.id, Page.http_status == 200))}
    return Facts(
        prospect=((site.prospect or {}).get("company") or "").strip() or site.name,
        as_of=run.started_at or run.created_at,
        firm=[f for f in findings if f.tier == "firm"],
        review=[f for f in findings if f.tier == "review"],
        articles=articles or 0,
        centers=centers,
        languages=languages,
        hosts=list(dict.fromkeys(urlsplit(c.url).netloc for c in centers)),
        blocked=[c.name for c in centers if c.id not in read],
        labels={**SHEET_LABELS, "T": t_label},
        mix_labels={**MIX_LABELS, "T": t_mix},
    )


def by_category(f: Facts) -> list[tuple[str, int]]:
    order = list(f.labels)
    return sorted(Counter(x.category for x in f.firm).items(), key=lambda kv: (-kv[1], order.index(kv[0])))


def stats(f: Facts) -> list[dict]:
    s = f.counts
    return [
        {"value": f"{s['firm']:,}", "label": "confirmed issues"},
        {"value": f"{s['high']:,}", "label": "high severity"},
        {"value": f"{s['articles']:,}", "label": "articles reviewed"},
        {"value": f"{s['help_centers']:,}", "label": "help centers" if s["help_centers"] != 1 else "help center"},
    ]


def lead_review_sentence(f: Facts) -> str:
    languages = f" in {report.joined(f.languages)}" if len(f.languages) > 1 else ""
    return (
        f"A review of {f.prospect}'s public help {'centers' if len(f.centers) != 1 else 'center'} on {f.date} "
        f"found {len(f.firm):,} issues across {f.articles:,} articles{languages}."
    )


def exec_review_sentence(f: Facts) -> str:
    return (
        f"A review of {f.articles:,} of {f.prospect}'s public help articles on {f.date} "
        f"found {len(f.firm):,} confirmed issues."
    )


def footnote(f: Facts) -> str:
    excluded = (
        f"; {report.spelled(len(f.review))} {'item that depends' if len(f.review) == 1 else 'items that depend'} "
        "on internal policy {} excluded".format("is" if len(f.review) == 1 else "are")
        if f.review
        else ""
    )
    return (
        f"Review of public pages at {report.joined(f.hosts)} as of {f.date}{excluded}. "
        f"{f.prospect} is a trademark of its owner; Heretto is not affiliated with {f.prospect}."
    )


def example(f: IntegrityFinding, facts_: Facts) -> dict:
    """One "What we found" item: severity, where, title and its quotes as lines."""
    kind = {"T": "Translation", "C": "Contradiction", "U": "Instructions"}.get(f.category, facts_.labels[f.category])
    lines = []
    for q in f.quotes[:2]:
        line = {"text": f"“{q['text']}”"}
        if f.category == "T" and q.get("label"):
            line["label"] = q["label"]
        if q.get("note"):
            line["note"] = f"({q['note']})"
        lines.append(line)
    return {"severity": f.severity, "where": f"{f.locale} · {kind}", "title": f.title, "lines": lines}


# ── Rendering ────────────────────────────────────────────────────────────────


def sheet_context(kind: str, f: Facts, copy: Copy, site) -> dict:
    """The template's data, shaped as the skill's example JSON files and
    prepared as its build_onesheet.py prepares them."""
    prospect = site.prospect or {}
    contact = ", ".join(
        p for p in (prospect.get("sender_name", "").strip(), prospect.get("sender_title", "").strip()) if p
    )
    cta_title, cta_text = DEFAULT_CTA[kind]
    ctx = {
        "prospect": f.prospect,
        "prospect_logo": site.prospect_logo,
        "heretto_logo": rendering.asset("heretto-wordmark-white.png"),
        "stats": stats(f),
        "contact_name": contact or "[Name, Title]",
        "contact_email": (prospect.get("sender_email") or "").strip() or "[email]",
        "footnote": footnote(f),
        "cta_title": cta_title,
        "cta_text": cta_text,
        "cta_button": "heretto.com",
    }
    if kind == "lead":
        cats = [{"label": f.labels[c], "count": n} for c, n in by_category(f)][:9]
        top = max((c["count"] for c in cats), default=1) or 1
        for c in cats:
            c["pct"] = max(4, round(100 * c["count"] / top))
        sev = f.severity
        total = sum(sev.values()) or 1
        high, medium = round(100 * sev["High"] / total, 1), round(100 * sev["Medium"] / total, 1)
        subhead = " ".join(p for p in (copy.subhead_lead.strip(), lead_review_sentence(f)) if p)
        return (
            ctx
            | {
                "eyebrow": f"Content Integrity Snapshot · {f.prospect} Help Center",
                "headline_line1": copy.headline_line1,
                "headline_line2": copy.headline_line2,
                "subhead": subhead,
                "categories": cats,
                "sev": {
                    "high": sev["High"],
                    "medium": sev["Medium"],
                    "low": sev["Low"],
                    "high_pct": high,
                    "medium_pct": medium,
                    "low_pct": round(100 - high - medium, 1),
                },  # fmt: skip
                "examples": [example(x, f) for x in f.examples[:3]],
                "examples_heading": "What we found: selected issues",
                "why": [{"lead": w.lead, "text": w.text} for w in copy.why],
            }
        )
    counts = by_category(f)
    mix = [{"label": f.mix_labels[c], "count": n} for c, n in counts[:3]]
    if rest := sum(n for _, n in counts[3:]):
        mix.append({"label": "Other", "count": rest})
    total = sum(m["count"] for m in mix) or 1
    for i, m in enumerate(mix):
        m["pct"], m["color"] = round(100 * m["count"] / total, 1), MIX_COLORS[i]
    return ctx | {
        "eyebrow": f"Executive Brief · {f.prospect} Help Center Content",
        "headline": copy.exec_headline,
        "lead_sentence": copy.lead_sentence,
        "review_sentence": exec_review_sentence(f),
        "mix": mix,
        "impacts": [i.model_dump() for i in copy.impacts],
    }


def html(kind: str, f: Facts, copy: Copy, site) -> str:
    return rendering.render(TEMPLATES[kind], **sheet_context(kind, f, copy, site))


# ── The Collateral Writer ────────────────────────────────────────────────────

TASK = """Write the copy for two one-sheets about this prospect's public help center: the lead one-sheet \
for their documentation lead and the executive brief for a CIO. Follow your context files: the headline \
rules and length budgets in the one-sheet data file, and the business-imperatives file for the "why it \
matters" lines and the impact cards. The counts, categories and examples on the sheets are filled in from \
the triage; write only the fields below, fresh for this prospect.

- headline_line1 / headline_line2: the lead headline over two lines, each at most 26 characters. It may \
address the reader. Not critical of the prospect; never implies Heretto audits or scans content.
- subhead_lead: one sentence on what structured content makes possible for the team (the review sentence \
is added after it).
- exec_headline: about 45 characters, no "you" or "your".
- lead_sentence: "Structured content is critical to [imperative]; without it, [consequence]." At most 160 \
characters, with a semicolon.
- why: three lines, Risk first when it applies: imperative (Risk, Customer Acquisition, Customer \
Retention or Cost), ai (true for an AI point), lead (two to four words), text (one sentence of \
consequence; lead and text together about 95 characters), codes (the finding IDs it traces to).
- impacts: three cards: tone ("risk" for Risk and AI risk, otherwise "cost"), label (e.g. "Regulatory \
risk", "AI risk", "Cost to serve", "Customer retention"), title (at most 45 characters), body (at most \
190), evidence (one or two exact quotes from the findings, at most 150, no commentary), codes.
- industry: the prospect's industry in a word or two, as you judged it.

Every line must trace to the findings listed. Don't mention Heretto or CCMS in the why lines; don't name \
the imperatives on the page."""

ANSWER = (
    'Answer with one JSON object and nothing else: {"industry": "", "headline_line1": "", "headline_line2": "", '
    '"subhead_lead": "", "exec_headline": "", "lead_sentence": "", "why": [{"imperative": "Risk", "ai": false, '
    '"lead": "", "text": "", "codes": ["C-01"]}], "impacts": [{"tone": "risk", "label": "", "title": "", '
    '"body": "", "evidence": "", "codes": ["C-01"]}]}'
)
MAX_LISTED = 80  # findings sent to the writer, most severe first


class WriterFailed(Exception):
    """The Collateral Writer gave no usable copy; the message says why."""


def material(f: Facts, site) -> str:
    lines = [
        f"Prospect: {f.prospect}",
        f"About the site: {site.description.strip()}" if site.description.strip() else "",
        f"Help centers: {', '.join(f'{c.name} ({c.url})' for c in f.centers)}",
        f"Reviewed on {f.date}: {f.articles:,} articles; {len(f.firm):,} confirmed issues "
        f"({f.severity['High']} High, {f.severity['Medium']} Medium, {f.severity['Low']} Low); "
        f"{len(f.review):,} items for review, not counted.",
        "By category: " + "; ".join(f"{f.labels[c]} {n}" for c, n in by_category(f)),
        "One-sheet examples picked in triage: " + (", ".join(x.code for x in f.examples[:3]) or "none yet"),
        "",
        "Confirmed findings:",
    ]
    for x in report.ordered(f.firm)[:MAX_LISTED]:
        quotes = " / ".join(f"“{q['text']}” ({q.get('slug', '')})" for q in x.quotes[:2])
        lines.append(f"- {x.code} · {x.severity} · {x.locale} · {x.title}: {quotes}. {x.why}".rstrip())
    if site.focus and site.focus.strip():
        lines += ["", f"Standing focus for this site: {site.focus.strip()}"]
    return "\n".join(line for line in lines if line is not None)


def parse_copy(raw: dict, codes: set[str]) -> Copy:
    try:
        copy = Copy.model_validate(raw)
    except ValidationError as exc:
        raise WriterFailed(f"the copy didn't have the expected fields ({exc.error_count()} problems)") from exc
    for item in [*copy.why, *copy.impacts]:
        item.codes = [c for c in item.codes if c in codes]
    return copy


async def write(db: Session, run: AuditRun, f: Facts) -> tuple[Copy, str]:
    """Ask the site's Collateral Writer for the copy; returns it and the agent's name."""
    site = run.site
    try:
        agent = review.load_agent(db, run.organization_id, (site.agent_assignments or {}).get("deliverables"))
    except review.AgentUnavailable as exc:
        raise WriterFailed(str(exc)) from exc
    errors: list[str] = []

    async def ready() -> None:
        return None

    asking = review.Review(db, run, "deliverables", agent, lambda _a, level, m: errors.append(m),
                           lambda _d, _t: None, ready)  # fmt: skip
    raw = await asking.ask("the one-sheet copy", material(f, site), TASK + "\n\n" + ANSWER, parse=review.parse_object)
    if raw is None:
        raise WriterFailed(errors[-1] if errors else f"{agent.name} didn't answer")
    return parse_copy(raw, {x.code for x in f.firm}), agent.name


# ── Hand-off ─────────────────────────────────────────────────────────────────


def placeholders(site) -> list[str]:
    p = site.prospect or {}
    missing = []
    if not site.prospect_logo:
        missing.append("prospect logo")
    if not (p.get("sender_name") or "").strip():
        missing.append("sender name")
    if not (p.get("sender_email") or "").strip():
        missing.append("sender email")
    return missing


def spot_checks(f: Facts) -> list[dict]:
    """The one-sheet quotes to check in a live browser before sending."""
    out = []
    for x in f.examples[:3]:
        for q in x.quotes[:2]:
            out.append({"code": x.code, "slug": q.get("slug", ""), "page_id": q.get("page_id"),
                        "verified": bool(q.get("verified", True))})  # fmt: skip
    return out


def internal_note(f: Facts) -> str:
    """The skill's internal explainer (`internal-summary.md`), filled in."""
    present = {x.category for x in f.firm}
    types = {
        "C": "Contradictions between articles: two statements that can't both be true for the same customer, "
        "product, and country.",
        "T": f"{f.labels['T']}: versions that change the meaning, leave out content, contain untranslated text, "
        "or exist in only one language.",
        "U": "Instructions that don't match the app: different menu names, button labels, or steps for the same task.",
        "TM": "Inconsistent terminology: different terms for the same thing within one site.",
        "D": "Disclosure and legal text: rates, examples, and partner disclosures that differ across pages.",
        "L": "Retired products: content for discontinued products shown without saying who it applies to.",
        "S": "Product rules stated as general policy, and general statements that ignore a product exception.",
        "O": 'Outdated content: past dates written as future, "new" features that aren\'t new, articles that '
        "predate a policy change.",
        "N": "Links and duplicates: broken links, links to the wrong country or language, articles with the "
        "same title.",
        "X": "Structure and publishing errors: inconsistent layouts, swapped headings, template leftovers, "
        "internal notes published to customers.",
    }
    per_center = report.joined([c.name for c in f.centers])
    not_reviewed = f" Not reviewed: {', '.join(f.blocked)} (the site blocked the crawler)." if f.blocked else ""
    lines = [
        f"{f.prospect} Help Center Content Integrity Review: what it assessed",
        "",
        f"We reviewed {f.prospect}'s public help centers as of {f.date}: {f.articles:,} articles across "
        f"{per_center}." + not_reviewed
        + " We looked for content that is wrong, conflicting, outdated, or missing its scope. Differences where "
        "both versions are accurate weren't counted.",
        "",
        "Issue types we looked for:",
        *(f"- {types[c]}" for c in types if c in present),
        "",
        "Each issue is rated High (a customer could act on wrong information, or compliance-sensitive), Medium "
        "(confusing or outdated), or Low (cosmetic). Items that depend on internal policy are listed separately "
        "and excluded from the counts.",
        "",
        f"Result: {len(f.firm):,} confirmed issues, {f.severity['High']:,} High, plus {len(f.review):,} items "
        "for review.",
        "",
        "Together these point to content copied and maintained by hand rather than managed from a single source, "
        "the problem a CCMS like Heretto addresses through reuse, governed translation, and controlled publishing.",
    ]  # fmt: skip
    return "\n".join(lines)


def budget_problems(copy: Copy) -> list[str]:
    """Copy over its length budget, and an executive headline that says "you"."""
    out = []
    checks = [
        ("Lead headline, line 1", copy.headline_line1, BUDGETS["headline_line1"]),
        ("Lead headline, line 2", copy.headline_line2, BUDGETS["headline_line2"]),
        ("Executive headline", copy.exec_headline, BUDGETS["exec_headline"]),
        ("Executive lead sentence", copy.lead_sentence, BUDGETS["lead_sentence"]),
        *((f"Why it matters {i}", f"{w.lead} {w.text}".strip(), BUDGETS["why"]) for i, w in enumerate(copy.why, 1)),
    ]
    for name, value, limit in checks:
        if len(value) > limit:
            out.append(f"{name} is {len(value)} characters (budget {limit})")
    if re.search(r"\byour?\b", copy.exec_headline, re.IGNORECASE):
        out.append('The executive headline says "you" or "your"')
    return out


def row(db: Session, run: AuditRun) -> Deliverables | None:
    return db.scalar(select(Deliverables).where(Deliverables.run_id == run.id))


def copy_of(saved: Deliverables | None) -> Copy | None:
    return Copy.model_validate(saved.copy) if saved and saved.copy else None


def dumps(copy: Copy) -> dict:
    return json.loads(copy.model_dump_json())
