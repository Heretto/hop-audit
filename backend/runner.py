"""Run audits in the background, in this process.

Each run is an asyncio task with a ``Control`` for pause, resume and cancel.
The app runs as a single replica (AGENTS.md), so an in-memory registry is
enough; a run that was active when the process stopped is marked failed at
the next startup.

Stages: discover and crawl, then the mechanical analyses (``analysis.py``).
Agent analyses join in later milestones; until one exists, its stage is
marked skipped with the reason.
"""

import asyncio
import logging
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from hop_core.db import get_session_factory
from sqlalchemy import select
from sqlalchemy.orm import Session

import analysis
import crawler
import discovery
import render
from models import ACTIVE_STATUSES, AuditRun, HelpCenter, IntegrityFinding, Page, RunLogEntry
from schemas.site import CrawlRules
from scope import Root

logger = logging.getLogger(__name__)


def failure(exc: Exception) -> str:
    """What a failed run says: its message, or the error's name; for a request
    that went wrong, also which host it was for ("ReadTimeout from api.anthropic.com")."""
    if not isinstance(exc, httpx.RequestError):
        return str(exc) or type(exc).__name__
    name = type(exc).__name__
    try:
        name += f" from {exc.request.url.host}"
    except RuntimeError:  # no request attached
        pass
    if isinstance(exc, httpx.TimeoutException):
        name += " (the request timed out)"
    return f"{name}: {exc}" if str(exc) else name


STAGE_LABELS = {
    "discover": "Discover",
    "crawl": "Crawl",
    "readability": "Readability",
    "links": "Links",
    "seo": "SEO and metadata",
    "content_integrity": "Content integrity",
    "summary": "Summary report",
}
NOT_AVAILABLE = "Not run: this analysis isn't available yet"
RETRY_DELAY = 30.0  # seconds; tests shorten it

_controls: dict[UUID, crawler.Control] = {}
_tasks: set[asyncio.Task] = set()


def initial_stages(analyses: list[str]) -> list[dict]:
    keys = ["discover", "crawl", *[k for k in STAGE_LABELS if k in analyses]]
    return [
        {"key": k, "label": STAGE_LABELS[k], "status": "pending", "done": 0, "total": 0, "detail": ""} for k in keys
    ]


def control_for(run_id: UUID) -> crawler.Control | None:
    return _controls.get(run_id)


async def stopped(run_id: UUID, timeout: float) -> None:
    """Wait up to ``timeout`` seconds for a run's job to finish (after a cancel)."""
    control = _controls.get(run_id)
    if control and control.task:
        await asyncio.wait({control.task}, timeout=timeout)


def _user_cancelled(exc: BaseException, control: crawler.Control) -> bool:
    """A cancel from the API, as opposed to the server shutting down (which re-raises)."""
    if isinstance(exc, crawler.Cancelled):
        return True
    if not control.cancelled:
        return False
    asyncio.current_task().uncancel()  # handled here; the job's own clean-up can still await
    return True


def start(run_id: UUID, job=None) -> None:
    """Schedule a run (or another job on it, such as ``reanalyze``) on the running event loop."""
    control = _controls[run_id] = crawler.Control()
    task = control.task = asyncio.get_running_loop().create_task((job or execute)(run_id, control))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


MECHANICAL = ("readability", "seo", "links")


async def reanalyze(run_id: UUID, control: crawler.Control, http=None) -> None:
    """Analyze a finished run's stored pages again, without crawling. Runs
    crawled before the analyses existed get their results this way."""
    db = get_session_factory()()
    run = db.get(AuditRun, run_id)
    rec = Recorder(db, run)
    own_client = http is None
    http = http or discovery.client()
    try:
        run.status = "running"
        # An integrity review would replace findings someone may have triaged:
        # redo it only when there are none, or it failed and triage hasn't started.
        has_findings = db.scalar(select(IntegrityFinding.id).where(IntegrityFinding.run_id == run.id).limit(1))
        stage = next((s for s in run.stages if s["key"] == "content_integrity"), {})
        untouched = (run.triage or {}).get("status", "pending") == "pending"
        integrity_review = not has_findings or (stage.get("status") == "failed" and untouched)
        redo = set(MECHANICAL) | ({"content_integrity"} if integrity_review else set())
        for stage in run.stages:
            if stage["key"] in redo:
                rec.stage(stage["key"], status="pending", done=0, total=0, detail="")
        rec.log("run", "info", "Analyzing the stored pages again; nothing is re-crawled.")
        await analysis.analyze(db, run, rec, http, control.checkpoint, integrity_review)
        rec.log("run", "info", "Analysis complete.")
    except (crawler.Cancelled, asyncio.CancelledError) as exc:
        if not _user_cancelled(exc, control):
            raise
        db.rollback()
        rec.log("run", "warn", "Analysis cancelled; the earlier results are kept.")
        _settle(rec, "skipped")
    except Exception as exc:
        db.rollback()
        logger.exception("Analysis of run %s failed", run_id)
        rec.log("run", "error", f"Analysis failed: {failure(exc)}")
        _settle(rec, "failed")
    finally:
        run.status = "completed"  # the crawl itself still stands
        db.commit()
        db.close()
        _controls.pop(run_id, None)
        if own_client:
            await http.aclose()


def recover_interrupted(db: Session) -> int:
    """Runs left active by a stopped process can't resume; say so."""
    runs = db.query(AuditRun).filter(AuditRun.status.in_(ACTIVE_STATUSES)).all()
    now = datetime.now(UTC)
    for run in runs:
        run.status, run.finished_at = "failed", now
        run.error = "Interrupted when the server restarted. Start the audit again."
        db.add(RunLogEntry(run_id=run.id, at=now, stage="run", level="error", message=run.error))
    db.commit()
    return len(runs)


class Recorder:
    """Writes stage progress, log entries and pages for one run."""

    def __init__(self, db: Session, run: AuditRun):
        self.db, self.run = db, run

    def log(self, stage: str, level: str, message: str) -> None:
        self.db.add(RunLogEntry(run_id=self.run.id, at=datetime.now(UTC), stage=stage, level=level, message=message))
        self.db.commit()

    def stage(self, key: str, **changes) -> None:
        # A new list, so SQLAlchemy sees the JSON change.
        self.run.stages = [{**s, **changes} if s["key"] == key else s for s in self.run.stages]
        self.db.commit()

    def get_stage(self, key: str) -> dict:
        return next(s for s in self.run.stages if s["key"] == key)

    async def page(self, result: crawler.Result) -> None:
        t = result.target
        self.db.add(
            Page(
                run_id=self.run.id,
                help_center_id=t.root.id,
                url=t.url,
                path=urlsplit(t.url).path or "/",
                section=result.section,
                title=result.title,
                http_status=result.http_status,
                content_hash=result.content_hash,
                lastmod=t.lastmod,
                word_count=result.word_count,
                content=result.content,
                error=result.error,
                reused_from_id=result.reused_from,
                fetched_at=datetime.now(UTC) if result.fetched else None,
            )
        )
        self.run.page_count += 1
        crawl = self.get_stage("crawl")
        self.stage("crawl", done=crawl["done"] + 1)

    def total(self, n: int) -> None:
        self.stage("crawl", total=n)


def last_completed(db: Session, site_id: UUID, before: int | None = None) -> AuditRun | None:
    query = db.query(AuditRun).filter(AuditRun.site_id == site_id, AuditRun.status == "completed")
    if before is not None:
        query = query.filter(AuditRun.number < before)
    return query.order_by(AuditRun.number.desc()).first()


def previous_pages(db: Session, run: AuditRun | None) -> dict[str, crawler.Previous]:
    """A run's pages by URL, for reuse and change detection."""
    if run is None:
        return {}
    return {
        p.url: crawler.Previous(p.id, p.lastmod, p.content_hash, p.http_status, p.title, p.word_count, p.content)
        for p in db.query(Page).filter(Page.run_id == run.id)
    }


def roots_of(db: Session, site_id: UUID) -> list[Root]:
    centers = db.query(HelpCenter).filter(HelpCenter.site_id == site_id).order_by(HelpCenter.position).all()
    return [Root(hc.id, hc.name, hc.url, hc.language, hc.is_primary) for hc in centers]


async def execute(run_id: UUID, control: crawler.Control, http=None) -> None:
    db = get_session_factory()()
    run = db.get(AuditRun, run_id)
    rec = Recorder(db, run)
    own_client = http is None
    renderer: render.Renderer | None = None
    http = http or discovery.client()
    try:
        site = run.site
        rules = CrawlRules(**site.crawl)
        roots = roots_of(db, site.id)
        prev = last_completed(db, site.id, before=run.number)
        previous = previous_pages(db, prev)
        run.status, run.started_at = "running", datetime.now(UTC)
        rec.stage("discover", status="running")
        if rules.render_js:
            try:
                renderer = await render.start(rules.concurrency)
                rec.log("discover", "info", "JavaScript is rendered in Chromium for every page fetched.")
            except render.RenderUnavailable as exc:
                rec.log("discover", "warn", f"{exc} Pages are read as served.")

        plan = await crawler.plan(http, roots, rules, run.scope, previous, rec.log)
        new = sum(1 for t in plan.targets if t.url not in previous) if prev else 0
        rec.log(
            "discover",
            "info",
            f"{plan.listed:,} sitemap URLs on the help centers; scope and rules kept {len(plan.targets):,}"
            + (f" ({new:,} new since #{prev.number})." if prev else "."),
        )
        rec.stage(
            "discover",
            status="done",
            done=len(plan.targets),
            total=len(plan.targets),
            detail=_discover_detail(plan, new if prev else None),
        )
        if not plan.targets:
            reason = (
                "Every help center refused the crawler; see the run log."
                if plan.blocked and len(plan.blocked) == len(roots)
                else "No pages matched the scope and the site's rules."
            )
            raise RuntimeError(reason)

        reuse = run.reuse_crawl and bool(previous)
        if reuse:
            rec.log("crawl", "info", f"Reusing pages from #{prev.number} whose sitemap lastmod hasn't changed.")
        rec.log(
            "crawl",
            "info",
            f"Fetching up to {len(plan.targets):,} pages, {rules.concurrency} at a time, {rules.delay_ms} ms delay.",
        )
        rec.stage("crawl", status="running", total=len(plan.targets))
        stats = await crawler.Crawler(
            http,
            rules,
            run.scope,
            previous,
            reuse,
            rec.log,
            control,
            rec.page,
            rec.total,
            retry_delay=RETRY_DELAY,
            render=renderer.html if renderer else None,
        ).run(plan)
        if renderer:  # Chromium's memory back before the analyses
            await renderer.close()
            renderer = None
        crawl = rec.get_stage("crawl")
        rec.stage("crawl", status="done", total=crawl["done"], detail=_crawl_detail(stats, prev))
        rec.log("crawl", "info", f"Crawl complete: {run.page_count:,} pages, {stats.links:,} links extracted.")

        await analysis.analyze(db, run, rec, http, control.checkpoint)
        for stage in run.stages:
            if stage["status"] == "pending":
                rec.stage(stage["key"], status="skipped", detail=NOT_AVAILABLE)
        run.status = "completed"
    except (crawler.Cancelled, asyncio.CancelledError) as exc:
        if not _user_cancelled(exc, control):
            raise  # the server is stopping; startup marks the run interrupted
        db.rollback()
        run.status = "cancelled"
        rec.log("run", "warn", "Cancelled. Pages read so far are kept.")
        _settle(rec, "skipped")
    except Exception as exc:  # recorded on the run, never re-raised into the loop
        db.rollback()
        logger.exception("Run %s failed", run_id)
        run.status, run.error = "failed", failure(exc)
        rec.log("run", "error", run.error)
        _settle(rec, "failed")
    finally:
        run.finished_at = datetime.now(UTC)
        db.commit()
        db.close()
        _controls.pop(run_id, None)
        if own_client:
            await http.aclose()
        if renderer:
            await renderer.close()


def _settle(rec: Recorder, status: str) -> None:
    """The stage that was running gets ``status``; stages not reached are skipped."""
    for stage in rec.run.stages:
        if stage["status"] == "running":
            rec.stage(stage["key"], status=status)
        elif stage["status"] == "pending":
            rec.stage(stage["key"], status="skipped")


def _discover_detail(plan: crawler.Plan, new: int | None) -> str:
    found = [s.rsplit("/", 1)[-1] for s in plan.sitemaps.values() if s]
    parts = [f"{', '.join(found)} read" if found else "no sitemap; following links"]
    if new is not None:
        parts.append(f"{new:,} new pages")
    if plan.blocked:
        parts.append(f"{len(plan.blocked)} help center(s) blocked")
    return ", ".join(parts)


def _crawl_detail(stats: crawler.Stats, prev: AuditRun | None) -> str:
    parts = [f"{stats.fetched:,} fetched"]
    if stats.reused:
        parts.append(f"{stats.reused:,} unchanged pages reused from #{prev.number}")
    if stats.unchanged:
        parts.append(f"{stats.unchanged:,} unchanged left out")
    if stats.failed:
        parts.append(f"{stats.failed:,} failed")
    if stats.skipped:
        parts.append(f"{stats.skipped:,} not HTML")
    return ", ".join(parts)
