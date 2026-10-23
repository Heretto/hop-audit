"""Content-integrity findings and their triage."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from hop_core.api.dependencies import CurrentUserContext, get_current_active_user_with_org
from hop_core.db import get_db
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import integrity
import runner
from models import AuditRun, HelpCenter, IntegrityFinding, Page
from routes.results import csv_response
from routes.runs import detail, get_run
from schemas.integrity import (
    CenterCount,
    ClaimCenter,
    ClaimGroup,
    ClaimRow,
    ClaimsView,
    IntegrityRow,
    IntegrityUpdate,
    IntegrityView,
)

router = APIRouter(tags=["integrity"])
Ctx = Depends(get_current_active_user_with_org)
CSV_COLUMNS = ("code", "severity", "category", "locale", "tier", "title", "quotes", "why", "triage_note", "example")


def _findings(db: Session, run_id: UUID) -> list[IntegrityFinding]:
    findings = db.scalars(select(IntegrityFinding).where(IntegrityFinding.run_id == run_id)).all()
    order = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(findings, key=lambda f: (order[f.severity], f.category, f.code))


@router.get("/runs/{run_id}/integrity", response_model=IntegrityView)
def view(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)
    centers = db.scalars(select(HelpCenter).where(HelpCenter.site_id == run.site_id).order_by(HelpCenter.position))
    counts = dict(
        db.execute(
            select(Page.help_center_id, func.count())
            .where(Page.run_id == run.id, Page.http_status == 200, Page.word_count >= 30)
            .group_by(Page.help_center_id)
        ).all()
    )
    pages = dict(
        db.execute(
            select(Page.help_center_id, func.count()).where(Page.run_id == run.id).group_by(Page.help_center_id)
        ).all()
    )
    reviewed = {str(i) for i in run.help_center_ids or []}
    return IntegrityView(
        run=detail(run),
        purpose=run.site.purpose,
        triage=run.triage or {"status": "pending"},
        findings=_findings(db, run.id),
        help_centers=[
            CenterCount(
                id=c.id,
                name=c.name,
                language=c.language,
                is_primary=c.is_primary,
                articles=counts.get(c.id, 0),
                pages=pages.get(c.id, 0),
            )
            for c in centers
            if not reviewed or str(c.id) in reviewed
        ],
        resolved=(run.metrics or {}).get("integrity", {}).get("resolved", []),
    )


@router.patch("/integrity-findings/{finding_id}", response_model=IntegrityRow)
def update(finding_id: UUID, body: IntegrityUpdate, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    """Set a finding's tier, triage note or one-sheet example. Any change to a
    confirmed triage reopens it; examples come from the firm tier only."""
    finding = db.get(IntegrityFinding, finding_id)
    if finding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finding not found")
    run = get_run(db, ctx, finding.run_id)
    if body.tier is not None:
        finding.tier = body.tier
        if body.tier != "firm":
            finding.example_rank = None
    if body.triage_note is not None:
        finding.triage_note = body.triage_note.strip()
    if body.example is not None:
        if body.example and finding.tier != "firm":
            raise HTTPException(422, "Only confirmed (firm) findings can be one-sheet examples")
        if body.example and finding.example_rank is None:
            ranks = db.scalars(select(IntegrityFinding.example_rank).where(IntegrityFinding.run_id == run.id))
            finding.example_rank = max((r for r in ranks if r is not None), default=0) + 1
        elif not body.example:
            finding.example_rank = None
    if (run.triage or {}).get("status") != "in_progress":
        run.triage = {"status": "in_progress"}
    integrity.refresh_metrics(db, run)
    db.commit()
    return finding


@router.post("/runs/{run_id}/triage/confirm", response_model=IntegrityView)
def confirm(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    """Confirm what counts. The counts appear everywhere from now on, and the
    reviewer's memory gets every tier the user changed."""
    run = get_run(db, ctx, run_id)
    if not integrity.candidates_total(db, run.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "This audit has no content-integrity findings to triage")
    integrity.confirm(db, run, ctx.user.email)
    db.commit()
    return view(run_id, ctx, db)


@router.get("/runs/{run_id}/integrity.csv")
def export(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)

    def quotes(f: IntegrityFinding) -> str:
        return " | ".join(f'{q["label"] + ": " if q["label"] else ""}"{q["text"]}" ({q["slug"]})' for q in f.quotes)

    rows = (
        [f.code, f.severity, f.category, f.locale, f.tier, f.title, quotes(f), f.why, f.triage_note,
         f.example_rank or ""]
        for f in _findings(db, run.id)
    )  # fmt: skip
    return csv_response(run, "integrity", CSV_COLUMNS, rows)


def claims_view(db: Session, run: AuditRun) -> ClaimsView:
    """Every claim pass 1 kept, page by page, with the group pass 3 matched it into."""
    centers = runner.roots_of(db, run.site_id)
    roots = {c.id: c for c in centers}
    position = {c.id: i for i, c in enumerate(centers)}
    pages = sorted(
        (p for p in db.scalars(select(Page).where(Page.run_id == run.id)) if p.integrity and p.integrity.get("claims")),
        key=lambda p: (position.get(p.help_center_id, len(centers)), p.url),
    )
    stored = run.claim_groups or {}
    member_of: dict[tuple[str, str], int] = {}
    groups = []
    for n, g in enumerate(stored.get("groups", []), 1):
        for m in g["members"]:
            member_of[(m["page_id"], m["statement"])] = n
        groups.append(
            ClaimGroup(
                number=n,
                subject=g["subject"],
                status=g["status"],
                issues=g["issues"],
                claims=len(g["members"]),
                articles=len({m["page_id"] for m in g["members"]}),
            )
        )
    rows = [
        ClaimRow(
            page_id=p.id,
            url=p.url,
            slug=integrity.slug(p, roots[p.help_center_id]),
            title=p.title,
            help_center_id=p.help_center_id,
            subject=c["subject"],
            statement=c["statement"],
            group=member_of.get((str(p.id), c["statement"])),
        )
        for p in pages
        if p.help_center_id in roots
        for c in p.integrity["claims"]
    ]
    used = {r.help_center_id for r in rows}
    return ClaimsView(
        run=detail(run),
        method=stored.get("method"),
        help_centers=[ClaimCenter(id=c.id, name=c.name) for c in centers if c.id in used],
        claims=rows,
        groups=groups,
    )


@router.get("/runs/{run_id}/claims", response_model=ClaimsView)
def claims(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    return claims_view(db, get_run(db, ctx, run_id))


@router.get("/runs/{run_id}/claims.csv")
def claims_csv(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)
    view = claims_view(db, run)
    centers = {c.id: c.name for c in view.help_centers}
    status = {g.number: g.status for g in view.groups}
    rows = [
        (c.subject, c.statement, c.title, c.url, centers[c.help_center_id], c.group or "", status.get(c.group, ""))
        for c in view.claims
    ]
    header = ("subject", "statement", "page_title", "url", "help_center", "group", "group_status")
    return csv_response(run, "claims", header, rows)
