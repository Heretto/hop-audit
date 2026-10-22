"""Audit runs: preview, start, follow, pause, resume, cancel."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from hop_core.api.dependencies import CurrentUserContext, get_current_active_user_with_org
from hop_core.db import get_db
from sqlalchemy import func
from sqlalchemy.orm import Session

import crawler
import discovery
import runner
from models import ACTIVE_STATUSES, AuditRun, RunLogEntry, Site
from routes.sites import get_site
from schemas.run import AnalyzeIn, LogEntry, Preview, PreviewHelpCenter, PreviewSection, RunDetail, RunIn, RunListItem
from schemas.site import CrawlRules

router = APIRouter(tags=["runs"])
Ctx = Depends(get_current_active_user_with_org)
TOKENS_PER_PAGE = 1400  # all five analyses together; refined once agents report usage
FETCH_SECONDS = 0.5  # a page fetch, before the crawl delay


def get_run(db: Session, ctx: CurrentUserContext, run_id: UUID) -> AuditRun:
    run = db.get(AuditRun, run_id)
    if run is None or run.organization_id != ctx.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audit not found")
    return run


def _with_site(model, run: AuditRun):
    return model(**{k: getattr(run, k) for k in model.model_fields if k != "site_name"}, site_name=run.site.name)


def detail(run: AuditRun) -> RunDetail:
    return _with_site(RunDetail, run)


def list_item(run: AuditRun) -> RunListItem:
    return _with_site(RunListItem, run)


def log(db: Session, run: AuditRun, message: str, level="info") -> None:
    db.add(RunLogEntry(run_id=run.id, at=datetime.now(UTC), stage="run", level=level, message=message))


# ── Preview and start ─────────────────────────────────────────────────────────


@router.get("/sites/{site_id}/runs/preview", response_model=Preview)
async def preview(site_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    """What a run would cover, from a fresh read of the sitemaps (no pages are
    fetched): pages by section and help center, pages changed since the last
    run, and per-page rates the Run audit screen multiplies out as you choose."""
    site = get_site(db, ctx, site_id)
    rules = CrawlRules(**site.crawl)
    roots = runner.roots_of(db, site.id)
    last = runner.last_completed(db, site.id)
    previous = runner.previous_pages(db, last)
    notes: list[str] = []

    def note(_stage: str, level: str, message: str) -> None:
        if level != "info":  # blocked help centers, pages left out
            notes.append(message)

    async with discovery.client() as http:
        plan = await crawler.plan(http, roots, rules, {"mode": "site"}, previous, note)
    sitemap_pages = [t for t in plan.targets if t.depth > 0]
    if last and last.page_count and last.started_at and last.finished_at:
        per_page = (last.finished_at - last.started_at).total_seconds() / last.page_count
    else:
        per_page = (FETCH_SECONDS + rules.delay_ms / 1000) / rules.concurrency
    return Preview(
        site_pages=len(plan.targets),
        changed=sum(crawler.changed(t, previous) for t in sitemap_pages),
        sections=[PreviewSection(path=p, count=n) for p, n in sorted(plan.sections.items())],
        help_centers=[
            PreviewHelpCenter(
                id=r.id,
                name=r.name,
                language=r.language,
                is_primary=r.is_primary,
                pages=plan.per_root[r.id],
                blocked=plan.blocked.get(r.id),
            )
            for r in roots
        ],
        last_run_number=last.number if last else None,
        last_run_at=last.finished_at if last else None,
        seconds_per_page=per_page,
        tokens_per_page=TOKENS_PER_PAGE,
        notes=notes,
    )


@router.post("/sites/{site_id}/runs", response_model=RunDetail, status_code=status.HTTP_201_CREATED)
async def start_run(site_id: UUID, body: RunIn, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    site = get_site(db, ctx, site_id)
    active = db.query(AuditRun).filter(AuditRun.site_id == site.id, AuditRun.status.in_(ACTIVE_STATUSES)).first()
    if active:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Audit #{active.number} of this site is still running")
    centers = {hc.id for hc in site.help_centers}
    if unknown := set(body.help_center_ids) - centers:
        raise HTTPException(422, f"Unknown help center: {', '.join(map(str, unknown))}")
    number = (db.query(func.max(AuditRun.number)).filter(AuditRun.site_id == site.id).scalar() or 0) + 1
    run = AuditRun(
        organization_id=ctx.organization_id,
        site_id=site.id,
        number=number,
        scope=body.scope.model_dump(),
        analyses=body.analyses,
        help_center_ids=[str(i) for i in (body.help_center_ids or [hc.id for hc in site.help_centers])],
        trigger="manual",
        created_by=ctx.user.email,
        reuse_crawl=body.reuse_crawl,
        recheck_external=body.recheck_external,
        force_reevaluate=body.force_reevaluate,
        focus=body.focus.strip(),
        stages=runner.initial_stages(body.analyses),
    )
    db.add(run)
    db.commit()
    runner.start(run.id)
    return detail(run)


# ── Reading ───────────────────────────────────────────────────────────────────


@router.get("/sites/{site_id}/runs", response_model=list[RunListItem])
def site_runs(site_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    site = get_site(db, ctx, site_id)
    runs = db.query(AuditRun).filter(AuditRun.site_id == site.id).order_by(AuditRun.number.desc()).all()
    return [list_item(r) for r in runs]


@router.get("/runs", response_model=list[RunListItem])
def all_runs(ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    runs = (
        db.query(AuditRun)
        .join(Site)
        .filter(AuditRun.organization_id == ctx.organization_id)
        .order_by(AuditRun.created_at.desc(), AuditRun.number.desc())
        .limit(500)
        .all()
    )
    return [list_item(r) for r in runs]


@router.get("/runs/{run_id}", response_model=RunDetail)
def read_run(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    return detail(get_run(db, ctx, run_id))


@router.get("/runs/{run_id}/log", response_model=list[LogEntry])
def run_log(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    return get_run(db, ctx, run_id).log


# ── Controls ──────────────────────────────────────────────────────────────────


@router.post("/runs/{run_id}/pause", response_model=RunDetail)
def pause(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)
    control = runner.control_for(run.id)
    if run.status != "running" or control is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a running audit can be paused")
    control.pause()
    run.status = "paused"
    log(db, run, f"Paused by {ctx.user.email}.")
    db.commit()
    return detail(run)


@router.post("/runs/{run_id}/resume", response_model=RunDetail)
def resume(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)
    control = runner.control_for(run.id)
    if run.status != "paused" or control is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a paused audit can be resumed")
    control.resume()
    run.status = "running"
    log(db, run, f"Resumed by {ctx.user.email}.")
    db.commit()
    return detail(run)


@router.post("/runs/{run_id}/analyze", response_model=RunDetail)
async def analyze(
    run_id: UUID, body: AnalyzeIn | None = None, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)
):
    """Analyze a finished run's stored pages again. Pages whose checksum is
    unchanged since the last audit keep its readability and SEO results
    unless ``force`` is set."""
    run = get_run(db, ctx, run_id)
    if run.status != "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a completed audit can be analyzed again")
    if not set(run.analyses) & {*runner.MECHANICAL, "content_integrity"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "This audit didn't include an analysis to repeat")
    run.status = "running"
    run.force_reevaluate = bool(body and body.force)
    forced = ", re-evaluating every page" if run.force_reevaluate else ""
    log(db, run, f"Analysis requested by {ctx.user.email}{forced}.")
    db.commit()
    runner.start(run.id, runner.reanalyze)
    return detail(run)


@router.post("/runs/{run_id}/cancel", response_model=RunDetail)
def cancel(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)
    if run.status not in ACTIVE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "This audit has already finished")
    log(db, run, f"Cancel requested by {ctx.user.email}.")
    control = runner.control_for(run.id)
    if control:
        control.cancel()  # the runner records the cancellation when it stops
    else:  # no task behind it: nothing to wait for
        run.status, run.finished_at = "cancelled", datetime.now(UTC)
    db.commit()
    return detail(run)
