"""The full findings report and its exports (milestone 7)."""

import json
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from hop_core.api.dependencies import CurrentUserContext, get_current_active_user_with_org
from hop_core.db import get_db
from sqlalchemy import select
from sqlalchemy.orm import Session

import pdf
import report
import report_export
import runner
from models import AgentFinding, AuditRun, IntegrityFinding, Page
from routes.runs import detail, get_run
from schemas.report import ReportView

router = APIRouter(tags=["report"])
Ctx = Depends(get_current_active_user_with_org)


def filename(run: AuditRun, what: str, ext: str) -> str:
    """<site>-audit-<n>-<what>.<ext>, as the CSV exports are named."""
    return f"{run.site.name}-audit-{run.number}-{what}.{ext}".replace(" ", "-").lower()


def download(run: AuditRun, body: bytes | str, media_type: str, what: str, ext: str) -> Response:
    disposition = f'attachment; filename="{filename(run, what, ext)}"'
    return Response(body, media_type=media_type, headers={"Content-Disposition": disposition})


def ready_report(db: Session, run: AuditRun) -> report.Report:
    built = report.build(db, run)
    if not built.ready:
        raise HTTPException(status.HTTP_409_CONFLICT, built.reason)
    return built


@router.get("/runs/{run_id}/report", response_model=ReportView)
def view(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)
    return {"run": detail(run), "purpose": run.site.purpose, **asdict(report.build(db, run))}


@router.get("/runs/{run_id}/report.pdf")
async def report_pdf(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)
    html = report_export.html(ready_report(db, run))
    try:
        rendered = await pdf.document(html)
    except pdf.PdfUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return download(run, rendered.pdf, "application/pdf", "report", "pdf")


@router.get("/runs/{run_id}/report.docx")
def report_docx(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    run = get_run(db, ctx, run_id)
    body = report_export.docx(ready_report(db, run))
    media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return download(run, body, media, "report", "docx")


@router.get("/runs/{run_id}/audit.json")
def audit_json(run_id: UUID, ctx: CurrentUserContext = Ctx, db: Session = Depends(get_db)):
    """Everything the audit holds, for other tools: the run, its help centers,
    every page's metrics, the agents' findings and the integrity findings with
    their triage."""
    run = get_run(db, ctx, run_id)
    centers = {r.id: r for r in runner.roots_of(db, run.site_id)}
    pages = db.scalars(select(Page).where(Page.run_id == run.id).order_by(Page.url)).all()
    urls = {p.id: p.url for p in pages}
    data = {
        "exported_at": datetime.now(UTC).isoformat(),
        "site": {"name": run.site.name, "start_url": run.site.start_url, "purpose": run.site.purpose},
        "help_centers": [
            {"name": c.name, "url": c.url, "language": c.language, "primary": c.is_primary} for c in centers.values()
        ],
        "run": json.loads(detail(run).model_dump_json(exclude={"stages"})),
        "pages": [
            {
                "url": p.url, "title": p.title, "help_center": centers[p.help_center_id].name
                if p.help_center_id in centers else None, "section": p.section, "http_status": p.http_status,
                "words": p.word_count, "flesch": p.flesch, "grade": p.grade, "broken_links": p.broken_links,
                "seo_issues": p.seo_issues, "score": p.score,
            }
            for p in pages
        ],
        "agent_findings": [
            {"analysis": f.analysis, "agent": f.agent_name, "severity": f.severity, "title": f.title,
             "body": f.body, "quote": f.quote, "suggestion": f.suggestion, "on_focus": f.on_focus,
             "page": urls.get(f.page_id)}
            for f in db.scalars(select(AgentFinding).where(AgentFinding.run_id == run.id))
        ],
        "integrity_findings": [
            {"code": f.code, "category": f.category, "severity": f.severity, "locale": f.locale, "title": f.title,
             "quotes": f.quotes, "why": f.why, "tier": f.tier, "triage_note": f.triage_note,
             "example_rank": f.example_rank, "first_seen": f.first_seen}
            for f in db.scalars(select(IntegrityFinding).where(IntegrityFinding.run_id == run.id))
        ],
    }  # fmt: skip
    return download(run, json.dumps(data, indent=2, default=str), "application/json", "audit", "json")
