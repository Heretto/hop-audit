"""Dashboard, pages, page detail and comparison, from two real runs of the fake site."""

import httpx
import pytest
import respx

from tests.conftest import make_user
from tests.fake_site import BASE, page, serve
from tests.test_runs import add_run, execute, fast_retries, make_site  # noqa: F401

ANALYSES = ["readability", "links", "seo"]


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        yield m


@pytest.fixture
async def two_runs(client, user, db, mock):
    serve(mock)
    site = make_site(client, user)
    first = await execute(db, add_run(db, site, user, analyses=ANALYSES))
    mock.routes.clear()
    # Topic B gains a broken link and loses its description in the second run.
    worse = page("Topic B", links=["/nowhere"]).replace('<meta name="description" content="About Topic B">', "")
    serve(mock, **{"authoring/b": httpx.Response(200, html=worse), "nowhere": httpx.Response(404)})
    second = await execute(db, add_run(db, site, user, number=2, analyses=ANALYSES, reuse_crawl=False))
    return site, first, second


async def test_dashboard(client, user, two_runs):
    _, first, second = two_runs
    d = client.get(f"/api/v1/runs/{second.id}/dashboard", headers=user["headers"]).json()
    assert d["analyzed"] and d["compared"]["number"] == 1
    assert d["run"]["metrics"]["compared_with"] == 1 and d["run"]["metrics"]["broken"] == 1
    assert d["run"]["metrics"]["new_pages"] == 0
    sections = {s["path"]: s for s in d["sections"]}
    assert set(sections) == {"/", "/api", "/archive", "/authoring"}
    assert sections["/authoring"]["pages"] == 3 and sections["/authoring"]["broken"] == 1
    assert sections["/authoring"]["score"] < 100

    d1 = client.get(f"/api/v1/runs/{first.id}/dashboard", headers=user["headers"]).json()
    assert d1["compared"] is None and d1["run"]["metrics"]["broken"] == 0


async def test_pages_and_csv(client, user, two_runs):
    _, _, second = two_runs
    rows = client.get(f"/api/v1/runs/{second.id}/pages", headers=user["headers"]).json()
    assert len(rows) == 7 and [r["path"] for r in rows] == sorted(r["path"] for r in rows)
    b = next(r for r in rows if r["path"] == "/authoring/b")
    assert b["broken_links"] == 1 and b["seo_issues"] >= 2 and b["score"] < 90
    assert "content" not in b  # the list stays light

    r = client.get(f"/api/v1/runs/{second.id}/pages.csv", headers=user["headers"])
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="x-help-audit-2-pages.csv"' in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("url,title,section,http_status,score") and len(lines) == 8


async def test_page_detail(client, user, two_runs):
    _, _, second = two_runs
    rows = client.get(f"/api/v1/runs/{second.id}/pages", headers=user["headers"]).json()
    b = next(r for r in rows if r["path"] == "/authoring/b")
    p = client.get(f"/api/v1/pages/{b['id']}", headers=user["headers"]).json()
    assert p["site_name"] == "X Help" and p["run_number"] == 2 and p["help_center_name"] == "US English"
    assert p["language"] == "en" and p["content"]["headings"] == [[1, "Topic B"]]
    assert {c["key"]: c["status"] for c in p["seo"]}["description"] == "error"
    assert p["links"] == [
        {
            "url": f"{BASE}nowhere",
            "text": "/nowhere",
            "internal": True,
            "outcome": "broken",
            "status": 404,
            "final_url": None,
            "note": "HTTP 404",
        }
    ]
    assert p["previous_run_number"] == 1 and p["previous_score"] > p["score"]
    assert p["section_flesch"] is not None or p["flesch"] is None

    other = make_user(client)
    assert client.get(f"/api/v1/pages/{b['id']}", headers=other["headers"]).status_code == 404
    assert client.get(f"/api/v1/runs/{second.id}/dashboard", headers=other["headers"]).status_code == 404


async def test_compare(client, user, two_runs):
    _, first, second = two_runs
    c = client.get(f"/api/v1/runs/compare?a={first.id}&b={second.id}", headers=user["headers"]).json()
    rows = {r["key"]: r for r in c["rows"]}
    assert rows["broken"] == {**rows["broken"], "a": 0, "b": 1, "delta": 1, "better": "down"}
    assert rows["pages"]["delta"] == 0
    assert c["changed_pages"][0]["path"] == "/authoring/b" and c["changed_pages"][0]["delta"] < 0


async def test_compare_needs_one_site(client, user, db, two_runs):
    site, first, _ = two_runs
    other_site = make_site(client, user)
    other = add_run(db, other_site, user, status="completed")
    r = client.get(f"/api/v1/runs/compare?a={first.id}&b={other.id}", headers=user["headers"])
    assert r.status_code == 422


async def test_sites_list_carries_last_completed(client, user, db, two_runs):
    site, _, second = two_runs
    add_run(db, site, user, number=3, status="running")
    listed = {s["id"]: s for s in client.get("/api/v1/sites", headers=user["headers"]).json()}[site["id"]]
    assert listed["last_run"]["number"] == 3
    assert listed["last_completed"]["number"] == 2 and listed["last_completed"]["metrics"]["broken"] == 1
