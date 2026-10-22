"""Audit runs: the runner end to end, and the run routes."""

import time
import uuid

import httpx
import pytest
import respx

import crawler
import discovery
import runner
from models import AuditRun, Page, RunLogEntry
from tests.conftest import make_user
from tests.fake_site import BASE, serve


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    monkeypatch.setattr(runner, "RETRY_DELAY", 0)


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        yield m


def make_site(client, user, **crawl) -> dict:
    body = {
        "name": "X Help",
        "start_url": BASE,
        "help_centers": [
            {"name": "US English", "url": BASE, "language": "en", "is_primary": True},
            {"name": "Deutsch", "url": f"{BASE}de/", "language": "de"},
        ],
        "crawl": {"delay_ms": 0, "follow_links": False, **crawl},
    }
    r = client.post("/api/v1/sites", json=body, headers=user["headers"])
    assert r.status_code == 201, r.text
    return r.json()


def add_run(db, site: dict, user, number=1, **fields) -> AuditRun:
    from sqlalchemy import select

    from models import Site

    org = db.scalar(select(Site.organization_id).where(Site.id == uuid.UUID(site["id"])))
    analyses = fields.pop("analyses", ["readability", "links"])
    run = AuditRun(
        organization_id=org,
        site_id=uuid.UUID(site["id"]),
        number=number,
        scope=fields.pop("scope", {"mode": "site", "sections": [], "pages": []}),
        analyses=analyses,
        stages=runner.initial_stages(analyses),
        created_by=user["email"],
        **fields,
    )
    db.add(run)
    db.commit()
    return run


async def execute(db, run: AuditRun) -> AuditRun:
    async with discovery.client() as http:
        await runner.execute(run.id, crawler.Control(), http=http)
    db.expire_all()
    return db.get(AuditRun, run.id)


# ── Runner ────────────────────────────────────────────────────────────────────


async def test_run_crawls_and_records_stages_log_and_pages(client, user, db, mock):
    serve(mock)
    site = make_site(client, user)
    run = await execute(db, add_run(db, site, user))

    assert run.status == "completed", run.error
    assert run.started_at and run.finished_at and run.page_count == 7
    stages = {s["key"]: s for s in run.stages}
    assert list(stages) == ["discover", "crawl", "readability", "links"]
    assert stages["discover"] == {**stages["discover"], "status": "done", "done": 7, "detail": "sitemap.xml read"}
    assert stages["crawl"]["status"] == "done" and stages["crawl"]["done"] == 7
    assert stages["crawl"]["detail"] == "7 fetched"
    assert stages["readability"]["status"] == "done" and stages["readability"]["detail"].startswith("Mean Flesch")
    assert stages["links"]["status"] == "done" and "links to" in stages["links"]["detail"]
    assert run.metrics["pages"] == 7 and run.metrics["score"] is not None and run.metrics["compared_with"] is None

    pages = db.query(Page).filter(Page.run_id == run.id).all()
    de = next(p for p in pages if p.url == f"{BASE}de/authoring/a")
    assert de.section == "/authoring" and de.path == "/de/authoring/a" and de.title == "Thema A"
    assert de.help_center_id == uuid.UUID(site["help_centers"][1]["id"])
    assert de.content["text"].startswith("Thema A") and de.fetched_at

    assert de.flesch is not None and de.score is not None and de.links_internal is not None
    assert de.seo is None  # SEO wasn't asked for

    log = [e.message for e in db.query(RunLogEntry).filter(RunLogEntry.run_id == run.id).order_by(RunLogEntry.id)]
    assert log[0].startswith("Read https://help.x.com/sitemap.xml: 7 URLs")
    assert any("Crawl complete: 7 pages" in m for m in log)
    assert any(m.startswith("Link check complete") for m in log)
    assert log[-1].startswith("Link check complete")  # links need no agent
    assert "No agent review of readability: no agent is assigned in site settings." in log
    assert "metrics only: no agent is assigned" in stages["readability"]["detail"]


async def test_second_run_reuses_and_reports_new_pages(client, user, db, mock):
    serve(mock)
    site = make_site(client, user)
    await execute(db, add_run(db, site, user))
    mock.reset()
    routes = serve(mock, entries=[("", "2026-10-01"), ("authoring/a", "2026-10-01"), ("api/new", None)])
    mock.get(f"{BASE}api/new").respond(html="<main><h1>New</h1></main>")
    run = await execute(db, add_run(db, site, user, number=2))
    assert run.status == "completed", run.error

    stages = {s["key"]: s for s in run.stages}
    assert "1 new pages" in stages["discover"]["detail"]
    assert "2 unchanged pages reused from #1" in stages["crawl"]["detail"]
    assert not routes["authoring/a"].called
    reused = db.query(Page).filter(Page.run_id == run.id, Page.url == f"{BASE}authoring/a").one()
    assert reused.reused_from_id and reused.fetched_at is None and reused.title == "Topic A"


async def test_reanalyze_a_finished_run(client, user, db, mock):
    """Runs crawled before the analyses existed get their results without a new crawl."""
    serve(mock)
    site = make_site(client, user)
    run = await execute(db, add_run(db, site, user, analyses=["readability", "seo", "links", "summary"]))
    db.query(Page).filter(Page.run_id == run.id).update({"flesch": None, "score": None, "seo": None})
    run.metrics = {}
    db.commit()
    crawled = mock.calls.call_count

    async with discovery.client() as http:
        await runner.reanalyze(run.id, crawler.Control(), http=http)
    db.expire_all()
    run = db.get(AuditRun, run.id)
    assert run.status == "completed" and run.metrics["pages"] == 7
    assert {s["key"]: s["status"] for s in run.stages}["summary"] == "skipped"
    page = db.query(Page).filter(Page.run_id == run.id, Page.url == f"{BASE}authoring/a").one()
    assert page.flesch is not None and page.score is not None and page.seo
    page_fetches = [c for c in mock.calls[crawled:] if c.request.method == "GET"]
    assert page_fetches == []  # nothing re-crawled


async def test_run_fails_when_every_help_center_refuses(client, user, db, mock):
    serve(mock, **{"": httpx.Response(403), "de/": httpx.Response(403)})
    site = make_site(client, user)
    run = await execute(db, add_run(db, site, user))
    assert run.status == "failed"
    assert run.error == "Every help center refused the crawler; see the run log."
    assert {s["key"]: s["status"] for s in run.stages} == {
        "discover": "done",
        "crawl": "skipped",
        "readability": "skipped",
        "links": "skipped",
    }


async def test_blocked_help_center_is_reported_and_the_rest_crawled(client, user, db, mock):
    serve(mock, **{"de/": httpx.Response(403)})
    site = make_site(client, user)
    run = await execute(db, add_run(db, site, user))
    assert run.status == "completed" and run.page_count == 5
    assert "1 help center(s) blocked" in run.stages[0]["detail"]


async def test_cancelled_run_keeps_pages(client, user, db, mock, monkeypatch):
    serve(mock)
    site = make_site(client, user, concurrency=1)
    run = add_run(db, site, user)
    control = crawler.Control()
    original = runner.Recorder.page

    async def page_then_cancel(self, result):
        await original(self, result)
        control.cancel()

    monkeypatch.setattr(runner.Recorder, "page", page_then_cancel)
    async with discovery.client() as http:
        await runner.execute(run.id, control, http=http)
    db.expire_all()
    run = db.get(AuditRun, run.id)
    assert run.status == "cancelled" and run.page_count == 1
    assert run.stages[1]["status"] == "skipped"


def test_recover_interrupted(client, user, db):
    site = make_site(client, user)
    run = add_run(db, site, user, status="running")
    assert runner.recover_interrupted(db) >= 1
    db.refresh(run)
    assert run.status == "failed" and "server restarted" in run.error


# ── Routes ────────────────────────────────────────────────────────────────────


@pytest.fixture
def started(monkeypatch):
    ids = []
    monkeypatch.setattr(runner, "start", ids.append)
    return ids


def test_start_run_creates_queued_run(client, user, started):
    site = make_site(client, user)
    body = {
        "scope": {"mode": "sections", "sections": ["/api"]},
        "analyses": ["links"],
        "focus": " Check X ",
        "force_reevaluate": True,
    }
    r = client.post(f"/api/v1/sites/{site['id']}/runs", json=body, headers=user["headers"])
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["number"] == 1 and run["status"] == "queued" and run["site_name"] == "X Help"
    assert run["focus"] == "Check X" and run["created_by"] == user["email"] and run["force_reevaluate"]
    assert [s["key"] for s in run["stages"]] == ["discover", "crawl", "links"]
    assert len(run["help_center_ids"]) == 2  # all help centers by default
    assert started == [uuid.UUID(run["id"])]

    again = client.post(f"/api/v1/sites/{site['id']}/runs", json=body, headers=user["headers"])
    assert again.status_code == 409 and "#1" in again.text


@pytest.mark.parametrize(
    "body, message",
    [
        ({"scope": {"mode": "sections"}}, "at least one section"),
        ({"scope": {"mode": "pages", "pages": [" "]}}, "at least one page"),
        ({"analyses": ["spelling"]}, "analyses"),
        ({"help_center_ids": [str(uuid.uuid4())]}, "Unknown help center"),
    ],
)
def test_start_run_validation(client, user, started, body, message):
    site = make_site(client, user)
    r = client.post(f"/api/v1/sites/{site['id']}/runs", json=body, headers=user["headers"])
    assert r.status_code == 422 and message in r.text


def test_run_listing_detail_log_and_isolation(client, user, db, started):
    site = make_site(client, user)
    run = client.post(f"/api/v1/sites/{site['id']}/runs", json={}, headers=user["headers"]).json()
    db.add(
        RunLogEntry(run_id=uuid.UUID(run["id"]), at=__import__("datetime").datetime.now(), stage="crawl", message="hi")
    )
    db.commit()
    h = user["headers"]
    assert [r["number"] for r in client.get(f"/api/v1/sites/{site['id']}/runs", headers=h).json()] == [1]
    assert run["id"] in [r["id"] for r in client.get("/api/v1/runs", headers=h).json()]
    assert client.get(f"/api/v1/runs/{run['id']}", headers=h).json()["progress"] == 0
    assert client.get(f"/api/v1/runs/{run['id']}/log", headers=h).json()[0]["message"] == "hi"

    other = make_user(client)
    assert client.get(f"/api/v1/runs/{run['id']}", headers=other["headers"]).status_code == 404
    assert client.get("/api/v1/runs", headers=other["headers"]).json() == []
    assert client.post(f"/api/v1/runs/{run['id']}/cancel", headers=other["headers"]).status_code == 404


def test_controls(client, user, db, started):
    site = make_site(client, user)
    run = client.post(f"/api/v1/sites/{site['id']}/runs", json={}, headers=user["headers"]).json()
    url, h = f"/api/v1/runs/{run['id']}", user["headers"]
    control = runner._controls[uuid.UUID(run["id"])] = crawler.Control()
    assert client.post(f"{url}/pause", headers=h).status_code == 409  # queued, not running

    db.get(AuditRun, uuid.UUID(run["id"])).status = "running"
    db.commit()
    assert client.post(f"{url}/pause", headers=h).json()["status"] == "paused" and control.paused
    assert client.post(f"{url}/resume", headers=h).json()["status"] == "running" and not control.paused
    assert client.post(f"{url}/cancel", headers=h).status_code == 200 and control.cancelled
    runner._controls.clear()

    # No task behind it (e.g. after a restart): cancelling settles it at once.
    assert client.post(f"{url}/cancel", headers=h).json()["status"] == "cancelled"
    assert client.post(f"{url}/cancel", headers=h).status_code == 409
    messages = [e["message"] for e in client.get(f"{url}/log", headers=h).json()]
    assert messages[:2] == [f"Paused by {user['email']}.", f"Resumed by {user['email']}."]


def test_analyze_route(client, user, db, started, monkeypatch):
    site = make_site(client, user)
    run = add_run(db, site, user, status="running")
    url, h = f"/api/v1/runs/{run.id}/analyze", user["headers"]
    assert client.post(url, headers=h).status_code == 409  # still running
    run.status = "completed"
    db.commit()
    jobs = []
    monkeypatch.setattr(runner, "start", lambda run_id, job=None: jobs.append((run_id, job)))
    r = client.post(url, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "running" and r.json()["force_reevaluate"] is False
    assert jobs == [(run.id, runner.reanalyze)]
    db.refresh(run)
    run.status = "completed"
    db.commit()
    forced = client.post(url, json={"force": True}, headers=h).json()
    assert forced["force_reevaluate"] is True
    other = add_run(db, site, user, number=2, status="completed", analyses=["summary"])
    assert client.post(f"/api/v1/runs/{other.id}/analyze", headers=h).status_code == 409


def test_preview(client, user, db, mock):
    serve(mock, **{"de/": httpx.Response(403)})
    site = make_site(client, user, delay_ms=500, concurrency=2)
    r = client.get(f"/api/v1/sites/{site['id']}/runs/preview", headers=user["headers"])
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["site_pages"] == 5 and p["changed"] == 5 and p["last_run_number"] is None
    assert p["sections"] == [
        {"path": "/", "count": 1},
        {"path": "/api", "count": 1},
        {"path": "/archive", "count": 1},
        {"path": "/authoring", "count": 2},
    ]
    de = p["help_centers"][1]
    assert de["name"] == "Deutsch" and de["pages"] == 0 and "HTTP 403" in de["blocked"]
    assert p["seconds_per_page"] == 0.5 and p["tokens_per_page"] == 1400
    assert any("Deutsch" in n for n in p["notes"])


def test_run_end_to_end_through_the_api(client, user, mock):
    serve(mock)
    site = make_site(client, user)
    run = client.post(f"/api/v1/sites/{site['id']}/runs", json={}, headers=user["headers"]).json()
    for _ in range(100):
        detail = client.get(f"/api/v1/runs/{run['id']}", headers=user["headers"]).json()
        if detail["status"] not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert detail["status"] == "completed", detail
    assert detail["page_count"] == 7 and detail["progress"] == 100
    listed = client.get("/api/v1/sites", headers=user["headers"]).json()
    assert listed[0]["last_run"]["number"] == 1 and listed[0]["last_run"]["status"] == "completed"
    assert listed[0]["last_run"]["page_count"] == 7
