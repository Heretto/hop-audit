"""The analyses of a run's pages: HOP Audit's own readability, SEO and link
checks, each followed by its agent's review (``review.py``), then the scores
and metrics built from them.

``analyze`` works on the pages already stored, so it serves both a run
straight after its crawl and a finished run analyzed again.
"""

from collections import Counter
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import links as link_checks
import readability
import review
import seo
from models import AgentFinding, AuditRun, HelpCenter, LinkCache, LinkResult, Page
from scoring import page_score, run_metrics

PROGRESS_EVERY = 25  # pages between stage progress writes


def comparable_run(db: Session, run: AuditRun) -> AuditRun | None:
    """The run to compare with: the last completed one before it with metrics,
    a whole-site run when this is one."""
    query = select(AuditRun).where(
        AuditRun.site_id == run.site_id, AuditRun.status == "completed", AuditRun.number < run.number
    )
    for candidate in db.scalars(query.order_by(AuditRun.number.desc())):
        if not candidate.metrics:
            continue
        if run.scope.get("mode") != "site" or candidate.scope.get("mode") == "site":
            return candidate
    return None


async def analyze(db: Session, run: AuditRun, rec, http: httpx.AsyncClient, checkpoint) -> None:
    """``rec`` is the runner's Recorder (stages and log); ``checkpoint`` honors pause and cancel."""
    pages = db.scalars(select(Page).where(Page.run_id == run.id)).all()
    readable = [p for p in pages if p.http_status == 200 and p.content]
    centers = select(HelpCenter.id, HelpCenter.language).where(HelpCenter.site_id == run.site_id)
    languages = {hc_id: language for hc_id, language in db.execute(centers)}
    keys = {s["key"] for s in run.stages}

    if "readability" in keys:
        rec.stage("readability", status="running", done=0, total=len(readable), detail="")
        for i, page in enumerate(readable, 1):
            r = readability.measure(page.content.get("text", ""), languages.get(page.help_center_id, "en"))
            page.flesch, page.grade, page.words_per_sentence = r.flesch, r.grade, r.words_per_sentence
            page.passive_pct, page.sentences = r.passive_pct, r.sentences
            if i % PROGRESS_EVERY == 0:
                await checkpoint()
                rec.stage("readability", done=i)
        scored = [p.flesch for p in readable if p.flesch is not None]
        detail = (
            f"Mean Flesch {sum(scored) / len(scored):.1f} · {sum(1 for f in scored if f < 50):,} pages under 50"
            if scored
            else "No page had enough text in a measurable language"
        )
        rec.log("readability", "info", f"{len(scored):,} of {len(readable):,} pages scored. {detail}.")
        reviewable = [p for p in readable if p.word_count >= readability.MIN_WORDS]
        await _review(db, run, rec, "readability", reviewable, detail, checkpoint, languages)

    if "seo" in keys:
        rec.stage("seo", status="running", done=0, total=len(readable), detail="")
        titles = Counter(p.content.get("title") for p in readable if p.content.get("title"))
        descriptions = Counter(p.content.get("description") for p in readable if p.content.get("description"))
        for page in readable:
            checks = seo.check(page.content, page.url, titles, descriptions)
            page.seo, page.seo_issues = seo.as_json(checks), seo.issues(checks)
        issues = sum(p.seo_issues for p in readable)
        affected = sum(1 for p in readable if p.seo_issues)
        detail = f"{issues:,} issues on {affected:,} pages"
        rec.log("seo", "info", f"SEO checks complete: {detail}.")
        await _review(db, run, rec, "seo", [p for p in readable if p.seo_issues], detail, checkpoint, languages)
    await checkpoint()

    link_counts: Counter = Counter()
    if "links" in keys:
        link_counts, detail = await _links(db, run, rec, http, pages, readable, checkpoint)
        rows = db.scalars(select(LinkResult).where(LinkResult.run_id == run.id)).all()
        groups = review.link_groups(rows, {p.id: p for p in pages})
        await _review(db, run, rec, "links", groups, detail, checkpoint)

    for page in pages:
        page.score = page_score(
            page.http_status,
            page.flesch,
            page.broken_links or 0,
            page.redirects or 0,
            page.anchor_issues or 0,
            page.seo,
        )
    previous = comparable_run(db, run)
    new = None
    if previous:
        before = set(db.scalars(select(Page.url).where(Page.run_id == previous.id)))
        new = sum(1 for p in pages if p.url not in before)
    findings = db.scalars(
        select(AgentFinding).where(AgentFinding.run_id == run.id, AgentFinding.dismissed.is_(False))
    ).all()
    run.metrics = {
        **run_metrics(pages, new, link_counts),
        "agent_findings": len(findings),
        "focus_findings": sum(1 for f in findings if f.on_focus),
        "tokens": sum((run.tokens or {}).values()),
        "compared_with": previous.number if previous else None,
        "analyzed_at": datetime.now(UTC).isoformat(),
    }
    db.commit()


async def _links(db, run, rec, http, pages, readable, checkpoint) -> Counter:
    db.execute(delete(LinkResult).where(LinkResult.run_id == run.id))
    hosts = {(urlsplit(hc.url).hostname or "").lower() for hc in run.site.help_centers}
    known = {
        p.url: link_checks.Known(p.http_status, p.content.get("final_url"), p.content.get("anchors"))
        for p in pages
        if p.http_status is not None
    }
    cache = {
        c.url: (link_checks.Outcome(c.outcome, c.status, c.final_url, c.note), c.checked_at)
        for c in db.scalars(select(LinkCache).where(LinkCache.organization_id == run.organization_id))
    }
    rec.stage("links", status="running", done=0, total=0, detail="")
    last = [0]

    def progress(done: int, total: int):
        if done - last[0] >= PROGRESS_EVERY or done == total:
            last[0] = done
            rec.stage("links", done=done, total=total)

    rows, probed = await link_checks.check(
        http,
        [(p.id, p.content.get("links", [])) for p in readable],
        hosts,
        known,
        cache,
        run.recheck_external,
        progress,
        checkpoint,
    )
    now = datetime.now(UTC)
    for url, o in probed.items():
        db.merge(
            LinkCache(
                organization_id=run.organization_id,
                url=url,
                outcome=o.outcome,
                status=o.status,
                final_url=o.final_url,
                note=o.note,
                checked_at=now,
            )
        )
    by_page: dict = {}
    for row in rows:
        db.add(
            LinkResult(
                run_id=run.id,
                page_id=row.page_id,
                url=row.url,
                text=row.text,
                internal=row.internal,
                outcome=row.outcome,
                status=row.status,
                final_url=row.final_url,
                note=row.note,
            )
        )
        by_page.setdefault(row.page_id, []).append(row)
    for page in readable:
        mine = by_page.get(page.id, [])
        page.links_internal = sum(1 for r in mine if r.internal)
        page.links_external = len(mine) - page.links_internal
        page.broken_links = sum(1 for r in mine if r.outcome == "broken")
        page.redirects = sum(1 for r in mine if r.outcome == "redirect")
        page.anchor_issues = sum(1 for r in mine if r.outcome == "anchor")
    counts = Counter(r.outcome for r in rows)
    targets = len({r.url.split("#")[0] for r in rows})
    detail = (
        f"{len(rows):,} links to {targets:,} targets checked, {counts['broken']:,} broken, "
        f"{counts['redirect']:,} redirects, {counts['anchor']:,} anchors not found"
    )
    if counts["blocked"]:
        detail += f", {counts['blocked']:,} couldn't be checked"
    rec.log("links", "info", f"Link check complete: {detail}.")
    db.commit()
    return counts, detail


async def _review(db: Session, run: AuditRun, rec, analysis: str, items: list, mechanical: str, checkpoint,
                  languages: dict | None = None) -> None:  # fmt: skip
    """The analysis's agent reviews ``items`` (pages, or link groups); the stage ends here."""
    db.execute(delete(AgentFinding).where(AgentFinding.run_id == run.id, AgentFinding.analysis == analysis))
    try:
        agent = review.load_agent(db, run.organization_id, (run.site.agent_assignments or {}).get(analysis))
    except review.AgentUnavailable as exc:
        rec.stage(analysis, status="done", detail=f"{mechanical} · metrics only: {exc}")
        rec.log(analysis, "warn", f"No agent review of {review.LABELS[analysis]}: {exc}.")
        return
    if not items:
        rec.stage(analysis, status="done", detail=f"{mechanical} · nothing for {agent.name} to review")
        return
    size = review.BATCH_SIZE[analysis]
    rec.stage(analysis, status="running", done=0, total=len(items), detail=f"{agent.name} · {agent.model}")
    rec.log(analysis, "info", f"{agent.name} started on {len(items):,} items, batches of {size}, focus attached.")

    def progress(done: int, total: int) -> None:
        rec.stage(analysis, done=done, total=total)

    reviewer = review.Review(db, run, analysis, agent, rec.log, progress, checkpoint)
    tally = await (reviewer.links(items) if analysis == "links" else reviewer.pages(items, languages or {}))

    key = str(agent.id)
    before = (run.agent_stats or {}).get(key, {})
    run.agent_stats = {
        **(run.agent_stats or {}),
        key: {
            "name": agent.name,
            "model": agent.model,
            "provider": agent.provider,
            "tokens": before.get("tokens", 0) + tally.tokens,
            "findings": before.get("findings", 0) + tally.findings,
            "errors": before.get("errors", 0) + tally.errors,
            "retries": before.get("retries", 0) + tally.retries,
            "status": "stopped" if "stopped" in (tally.status, before.get("status")) else "done",
        },
    }
    run.tokens = {**(run.tokens or {}), key: run.agent_stats[key]["tokens"]}
    plural = "" if tally.findings == 1 else "s"
    parts = [f"{agent.name}: {tally.findings:,} finding{plural} ({tally.on_focus:,} on focus)"]
    if tally.reused:
        parts.append(f"{tally.reused:,} unchanged pages' findings reused")
    if tally.quotes_removed:
        parts.append(f"{tally.quotes_removed:,} quotes not on the page removed")
    if tally.errors:
        parts.append(f"{tally.errors:,} failed batches")
    if tally.note:
        parts.append(tally.note)
    rec.stage(analysis, status="done", detail=f"{mechanical} · " + ", ".join(parts))
    rec.log(analysis, "info", f"{', '.join(parts)}; {tally.tokens:,} tokens.")
    db.commit()
