"""What a run found: dashboard, pages, page detail, comparison."""

import csv
import io
from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from hop_core.api.dependencies import CurrentUserContext, get_current_active_user_with_org
from hop_core.db import get_db
from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis import comparable_run
from models import AuditRun, HelpCenter, LinkResult, Page
from routes.runs import detail, get_run
from schemas.results import (
    ChangedPage,
    CompareRow,
    Comparison,
    Dashboard,
    PageDetail,
    PageRow,
    SectionRow,
)
from schemas.run import RunSummary
from scoring import mean_of

router = APIRouter(tags=["results"])
Ctx = Depends(get_current_active_user_with_org)

# (metric key, label, the direction that's good)
COMPARED = (
    ("score", "Site score", "up"),
    ("pages", "Pages analyzed", "flat"),
    ("flesch", "Avg Flesch Reading Ease", "up"),
    ("under_50", "Pages under Flesch 50", "down"),
    ("broken", "Broken links", "down"),
    ("redirects", "Redirected links", "down"),
    ("anchors", "Anchors not found", "down"),
    ("seo_issues", "SEO issues", "down"),
)
CSV_COLUMNS = ("url", "title", "section", "http_status", "score", "flesch", "broken_links", "redirects",
               "anchor_issues", "seo_issues", "word_count", "error")  # fmt: skip


def _pages(db: Session, run_id: UUID) -> list[Page]:
    return db.scalars(select(Page).where(Page.run_id == run_id).order_by(Page.path)).all()


@router.get("/runs/{run_id}/dashboard", response_model=Dashboard)
def dashboard(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)
    by_section: dict[str, list[Page]] = defaultdict(list)
    for page in _pages(db, run.id):
        by_section[page.section].append(page)
    sections = []
    for path, pages in sorted(by_section.items()):
        read = [p for p in pages if p.http_status == 200]
        score = mean_of(p.score for p in read)
        sections.append(
            SectionRow(
                path=path,
                pages=len(pages),
                flesch=mean_of(p.flesch for p in read),
                broken=sum(p.broken_links or 0 for p in read),
                seo_issues=sum(p.seo_issues or 0 for p in read),
                score=round(score) if score is not None else None,
            )
        )
    compared_number = run.metrics.get("compared_with")
    compared = (
        db.scalar(select(AuditRun).where(AuditRun.site_id == run.site_id, AuditRun.number == compared_number))
        if compared_number
        else None
    )
    return Dashboard(
        run=detail(run),
        compared=RunSummary.model_validate(compared) if compared else None,
        sections=sections,
        analyzed=bool(run.metrics),
    )


@router.get("/runs/{run_id}/pages", response_model=list[PageRow])
def pages(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    return _pages(db, get_run(db, ctx, run_id).id)


@router.get("/runs/{run_id}/pages.csv")
def pages_csv(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for page in _pages(db, run.id):
        writer.writerow(["" if getattr(page, c) is None else getattr(page, c) for c in CSV_COLUMNS])
    name = f"{run.site.name}-audit-{run.number}-pages.csv".replace(" ", "-").lower()
    return Response(
        out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'}
    )


@router.get("/pages/{page_id}", response_model=PageDetail)
def page_detail(page_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    page = db.get(Page, page_id)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Page not found")
    run = get_run(db, ctx, page.run_id)  # 404 for other organizations
    center = db.get(HelpCenter, page.help_center_id)
    section = db.scalars(
        select(Page.flesch).where(Page.run_id == run.id, Page.section == page.section, Page.http_status == 200)
    )
    previous = comparable_run(db, run)
    before = db.scalar(select(Page).where(Page.run_id == previous.id, Page.url == page.url)) if previous else None
    links = db.scalars(select(LinkResult).where(LinkResult.page_id == page.id).order_by(LinkResult.id)).all()
    return PageDetail.model_validate(
        {
            **{k: getattr(page, k) for k in PageDetail.model_fields if hasattr(page, k)},
            "run_number": run.number,
            "site_id": run.site_id,
            "site_name": run.site.name,
            "help_center_name": center.name,
            "language": center.language,
            "links": links,
            "section_flesch": mean_of(section),
            "previous_score": before.score if before else None,
            "previous_run_number": previous.number if before else None,
        }
    )


@router.get("/runs/compare", response_model=Comparison)
def compare(a: UUID, b: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    """Run ``a`` (earlier) against run ``b``, metric by metric and page by page."""
    run_a, run_b = get_run(db, ctx, a), get_run(db, ctx, b)
    if run_a.site_id != run_b.site_id:
        raise HTTPException(422, "Compare two audits of the same site")
    rows = []
    for key, label, better in COMPARED:
        va, vb = run_a.metrics.get(key), run_b.metrics.get(key)
        delta = round(vb - va, 1) if va is not None and vb is not None else None
        rows.append(CompareRow(key=key, label=label, a=va, b=vb, delta=delta, better=better))
    scores_a = {p.url: p.score for p in _pages(db, run_a.id) if p.score is not None}
    changed = [
        ChangedPage(url=p.url, path=p.path, page_id=p.id, a=scores_a[p.url], b=p.score, delta=p.score - scores_a[p.url])
        for p in _pages(db, run_b.id)
        if p.score is not None and p.url in scores_a and p.score != scores_a[p.url]
    ]
    changed.sort(key=lambda c: (-abs(c.delta), c.path))
    return Comparison(
        a=RunSummary.model_validate(run_a), b=RunSummary.model_validate(run_b), rows=rows, changed_pages=changed[:10]
    )
