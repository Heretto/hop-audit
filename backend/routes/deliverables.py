"""Prospect deliverables: the Deliverables screen, the Collateral Writer's
copy, the prospect's details and logo, and the one-sheets as HTML and PDF."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from hop_core.api.dependencies import CurrentUserContext, get_current_active_user_with_org
from hop_core.db import get_db
from sqlalchemy.orm import Session

import deliverables as d
import pdf
from models import AuditRun, Deliverables
from routes.report import download
from routes.runs import detail, get_run
from schemas.deliverables import CheckItem, DeliverablesUpdate, DeliverablesView, LogoIn, ProspectOut, Step

router = APIRouter(tags=["deliverables"])
Ctx = Depends(get_current_active_user_with_org)
NAMES = {"lead": "lead one-sheet", "exec": "executive brief"}
COUNTS_MATCH = "Counts on the one-sheets match the triaged totals ({firm} · {high} · {articles} · {help_centers})."


def unavailable(run: AuditRun) -> str:
    """Why deliverables can't be built for this run, or ""."""
    if run.site.purpose != "prospect":
        return "Deliverables are for prospect reviews; this site is set up as your own documentation."
    if (run.triage or {}).get("status") != "confirmed":
        return "Confirm the triage first: the one-sheets use triaged numbers only."
    return ""


def short(when) -> str:
    return f"{when:%b} {when.day}" if when else ""


def overflow(heights: dict) -> str:
    over = [f"{NAMES[k]} by {heights[k] - d.PAGE_H:,} px" for k in d.KINDS if heights.get(k, 0) > d.PAGE_H]
    if over:
        return "overflow: " + ", ".join(over)
    return "no overflow" if all(k in heights for k in d.KINDS) else "not measured yet"


def view(db: Session, run: AuditRun) -> DeliverablesView:
    site, saved = run.site, d.row(db, run)
    reason = unavailable(run)
    f = d.facts(db, run)
    copy = d.copy_of(saved)
    heights = (saved.heights if saved else None) or {}
    triage = run.triage or {}
    integrity = (run.metrics or {}).get("integrity") or {}
    missing = d.placeholders(site)
    quotes = d.spot_checks(f)
    confirmed = triage.get("status") == "confirmed"

    checklist = [
        CheckItem(
            key="examples",
            ok=len(f.examples) >= 3,
            text="Three one-sheet examples are picked in triage."
            if len(f.examples) >= 3
            else f"Pick three one-sheet examples on Findings ({len(f.examples)} picked).",
        ),
        CheckItem(
            key="placeholders",
            ok=not missing,
            text="Prospect logo and sender details are filled in."
            if not missing
            else f"Still placeholders: {', '.join(missing)}.",
        ),
        CheckItem(
            key="spot_checked",
            ok=bool(saved and saved.spot_checked),
            toggle=True,
            quotes=quotes,
            text="Spot-check every one-sheet quote in a live browser"
            + (f"; {', '.join(f.blocked)} blocked the crawler" if f.blocked else "")
            + (
                f"; {sum(not q['verified'] for q in quotes)} weren't found on the crawled page"
                if any(not q["verified"] for q in quotes)
                else ""
            )
            + ".",
        ),
        CheckItem(
            key="marketing_ok",
            ok=bool(saved and saved.marketing_ok),
            toggle=True,
            text="Check with Heretto marketing before putting the prospect's logo on unsolicited collateral.",
        ),
        CheckItem(
            key="fits",
            ok=all(0 < heights.get(k, 0) <= d.PAGE_H for k in d.KINDS),
            text=(
                "Both one-sheets fit on one page (lead {:,} px, exec {:,} px of {:,}).".format(
                    heights["lead"], heights["exec"], d.PAGE_H
                )
                if all(0 < heights.get(k, 0) <= d.PAGE_H for k in d.KINDS)
                else "The one-sheets are measured when their previews load on this page."
                if not all(k in heights for k in d.KINDS)
                else f"One-sheet length: {overflow(heights)}. Shorten the copy until both fit."
            ),
        ),
        CheckItem(
            key="counts",
            ok=bool(saved) and saved.counts == f.counts,
            text=(
                COUNTS_MATCH.format(**f.counts)
                if saved and saved.counts == f.counts
                else "The triage changed after the copy was written; check the copy or rebuild."
                if saved
                else "Counts are checked once the one-sheets are built."
            ),
        ),
    ]
    built = bool(copy)
    handoff_left = sum(not c.ok for c in checklist)
    steps = [
        Step(
            key="assess",
            label="Assess",
            status="done" if integrity else "now",
            detail=f"{integrity.get('candidates', 0):,} candidates · {short(f.as_of)}" if integrity else "Not run yet",
        ),
        Step(
            key="triage",
            label="Triage",
            status="done" if confirmed else ("now" if integrity else "todo"),
            detail=(
                f"{integrity.get('firm', 0):,} firm · {integrity.get('review', 0):,} review · "
                f"{integrity.get('drop', 0):,} dropped"
                + (
                    f" · confirmed {short(datetime.fromisoformat(triage['confirmed_at']))}"
                    if triage.get("confirmed_at")
                    else ""
                )
                + (f" by {triage['confirmed_by'].split('@')[0]}" if triage.get("confirmed_by") else "")
                if confirmed
                else "Confirm on Findings"
            ),
        ),
        Step(
            key="build",
            label="Build",
            status="done" if built else ("now" if not reason else "todo"),
            detail=f"4 deliverables · {overflow(heights)}" if built else "Not built yet",
        ),
        Step(
            key="handoff",
            label="Hand off",
            status=("done" if not handoff_left else "now") if built else "todo",
            detail=(
                f"{len(missing)} placeholder{'s' if len(missing) != 1 else ''} · "
                f"{len(quotes)} quote{'s' if len(quotes) != 1 else ''} to spot-check"
            ),
        ),
    ]
    p = site.prospect or {}
    return DeliverablesView(
        run=detail(run),
        purpose=site.purpose,
        available=not reason,
        reason=reason,
        steps=steps,
        built_at=saved.built_at if saved else None,
        built_by=saved.built_by if saved else None,
        agent_name=saved.agent_name if saved else "",
        copy=copy,
        budgets=d.BUDGETS,
        problems=d.budget_problems(copy) if copy else [],
        prospect=ProspectOut(
            company=p.get("company", ""),
            sender_name=p.get("sender_name", ""),
            sender_title=p.get("sender_title", ""),
            sender_email=p.get("sender_email", ""),
            logo=site.prospect_logo,
        ),
        checklist=checklist,
        heights=heights,
        counts=f.counts,
        examples=[x.code for x in f.examples[:3]],
        internal_note=d.internal_note(f) if confirmed else "",
        report_ready=bool(integrity),
    )


def built_row(db: Session, run: AuditRun) -> Deliverables:
    if reason := unavailable(run):
        raise HTTPException(status.HTTP_409_CONFLICT, reason)
    saved = d.row(db, run)
    if saved is None or not saved.copy:
        raise HTTPException(status.HTTP_409_CONFLICT, "Build the deliverables first.")
    return saved


@router.get("/runs/{run_id}/deliverables", response_model=DeliverablesView, response_model_by_alias=True)
def get_view(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    return view(db, get_run(db, ctx, run_id))


@router.post("/runs/{run_id}/deliverables/build", response_model=DeliverablesView, response_model_by_alias=True)
async def build(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    """Ask the Collateral Writer for fresh copy; replaces any edits."""
    run = get_run(db, ctx, run_id)
    if reason := unavailable(run):
        raise HTTPException(status.HTTP_409_CONFLICT, reason)
    f = d.facts(db, run)
    try:
        copy, agent_name = await d.write(db, run, f)
    except d.WriterFailed as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"The Collateral Writer couldn't write the copy: {exc}"
        ) from exc
    saved = d.row(db, run) or Deliverables(run_id=run.id)
    saved.copy, saved.counts, saved.heights = d.dumps(copy), f.counts, {}
    saved.spot_checked = False  # the copy and its evidence are new
    saved.agent_name, saved.built_by, saved.built_at = agent_name, ctx.user.email, datetime.now(UTC)
    db.add(saved)
    db.commit()
    return view(db, run)


@router.patch("/runs/{run_id}/deliverables", response_model=DeliverablesView, response_model_by_alias=True)
def update(run_id: UUID, body: DeliverablesUpdate, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)
    if body.prospect is not None:
        if run.site.purpose != "prospect":
            raise HTTPException(status.HTTP_409_CONFLICT, unavailable(run))
        changes = {k: v.strip() for k, v in body.prospect.model_dump(exclude_none=True).items()}
        run.site.prospect = {**(run.site.prospect or {}), **changes}
    if any(v is not None for v in (body.copy_, body.spot_checked, body.marketing_ok, body.heights)):
        saved = built_row(db, run)
        if body.copy_ is not None:
            saved.copy = d.dumps(body.copy_)
            saved.heights = {}  # the sheets change; they're measured again
        if body.spot_checked is not None:
            saved.spot_checked = body.spot_checked
        if body.marketing_ok is not None:
            saved.marketing_ok = body.marketing_ok
        if body.heights is not None:
            saved.heights = {**(saved.heights or {}), **body.heights}
    db.commit()
    return view(db, run)


@router.put("/runs/{run_id}/deliverables/logo", response_model=DeliverablesView, response_model_by_alias=True)
def put_logo(run_id: UUID, body: LogoIn, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)
    if run.site.purpose != "prospect":
        raise HTTPException(status.HTTP_409_CONFLICT, unavailable(run))
    run.site.prospect_logo = body.data_uri
    db.commit()
    return view(db, run)


@router.delete("/runs/{run_id}/deliverables/logo", response_model=DeliverablesView, response_model_by_alias=True)
def delete_logo(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)
    run.site.prospect_logo = None
    db.commit()
    return view(db, run)


def _kind(kind: str) -> str:
    if kind not in d.KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such deliverable")
    return kind


@router.get("/runs/{run_id}/deliverables/{kind}.html")
def sheet_html(run_id: UUID, kind: str, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    """The one-sheet as one Letter-sized HTML page, for the preview."""
    run = get_run(db, ctx, run_id)
    saved = built_row(db, run)
    html = d.html(_kind(kind), d.facts(db, run), d.Copy.model_validate(saved.copy), run.site)
    return Response(html, media_type="text/html")


@router.get("/runs/{run_id}/deliverables/{kind}.pdf")
async def sheet_pdf(run_id: UUID, kind: str, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    """The one-sheet as a one-page Letter PDF; refused when it overflows the page."""
    run = get_run(db, ctx, run_id)
    saved = built_row(db, run)
    kind = _kind(kind)
    html = d.html(kind, d.facts(db, run), d.Copy.model_validate(saved.copy), run.site)
    try:
        rendered = await pdf.sheet(html)
    except pdf.PdfUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    saved.heights = {**(saved.heights or {}), kind: rendered.height}
    db.commit()
    if rendered.height and rendered.height > d.PAGE_H:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"The {NAMES[kind]} overflows the page by {rendered.height - d.PAGE_H:,} px: "
            "shorten the copy and try again.",
        )
    what = "content-integrity-snapshot" if kind == "lead" else "executive-brief"
    return download(run, rendered.pdf, "application/pdf", what, "pdf")
