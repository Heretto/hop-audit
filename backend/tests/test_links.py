from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

import discovery
from links import Known, Outcome, check, classify, fragment_outcome

BASE = "https://help.x.com"


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        yield m


def test_classify():
    assert classify(200, None, "https://a.com/x").outcome == "ok"
    assert classify(200, "https://a.com/x/", "https://a.com/x").outcome == "ok"  # trailing slash only
    r = classify(200, "https://a.com/y", "https://a.com/x")
    assert (r.outcome, r.note) == ("redirect", "Redirects to https://a.com/y")
    assert classify(404, None, "u").outcome == "broken"
    assert classify(403, None, "u").outcome == "blocked"
    assert classify(None, None, "u", "Timed out").note == "Timed out"


def test_fragments():
    known = Known(200, None, ["limits"])
    ok = Outcome("ok", 200)
    assert fragment_outcome(ok, "limits", known) == ("ok", "")
    assert fragment_outcome(ok, "filters", known)[0] == "anchor"
    assert fragment_outcome(ok, "top", known)[0] == "ok"
    assert fragment_outcome(ok, "filters", Known(200, None, None))[0] == "ok"  # no anchors recorded
    assert fragment_outcome(ok, "x", None)[0] == "ok"  # external: not checked


async def test_check_run(mock):
    mock.head("https://ext.org/ok").respond(200)
    mock.head("https://ext.org/gone").respond(410)
    mock.head("https://ext.org/moved").mock(
        return_value=httpx.Response(301, headers={"location": "https://ext.org/new"})
    )
    mock.head("https://ext.org/new").respond(200)
    mock.head("https://ext.org/no-head").respond(405)
    mock.get("https://ext.org/no-head").respond(200)
    mock.head("https://ext.org/wall").respond(403)
    mock.get("https://ext.org/wall").respond(403)
    flaky = mock.head("https://ext.org/flaky").mock(
        side_effect=[httpx.Response(503), httpx.Response(200), httpx.Response(200)]
    )
    mock.head(f"{BASE}/not-crawled").respond(404)
    cached = mock.head("https://ext.org/cached").respond(500)

    pages = [
        (
            "p1",
            [
                {"url": f"{BASE}/b#limits", "text": "B"},
                {"url": f"{BASE}/b#nope", "text": "B nope"},
                {"url": f"{BASE}/missing", "text": "Missing"},
                {"url": f"{BASE}/old", "text": "Old"},
                {"url": f"{BASE}/not-crawled", "text": "Elsewhere"},
                {"url": "https://ext.org/ok", "text": "ok"},
                {"url": "https://ext.org/gone", "text": "gone"},
                {"url": "https://ext.org/moved", "text": "moved"},
                {"url": "https://ext.org/no-head", "text": "no head"},
                {"url": "https://ext.org/wall", "text": "wall"},
                {"url": "https://ext.org/flaky", "text": "flaky"},
                {"url": "https://ext.org/cached", "text": "cached"},
                {"url": "ftp://ext.org/file", "text": "ftp"},
            ],
        ),
        ("p2", [{"url": "https://ext.org/ok", "text": "again"}]),
    ]
    known = {
        f"{BASE}/b": Known(200, None, ["limits"]),
        f"{BASE}/missing": Known(404, None, None),
        f"{BASE}/old": Known(200, f"{BASE}/new", []),
    }
    cache = {"https://ext.org/cached": (Outcome("ok", 200), datetime.now(UTC) - timedelta(days=2))}
    progress = []
    async with discovery.client() as http:
        rows, probed = await check(
            http, pages, {"help.x.com"}, known, cache, False, lambda d, t: progress.append((d, t))
        )

    by_url = {(r.page_id, r.url): r for r in rows}
    out = {u: r.outcome for (p, u), r in by_url.items() if p == "p1"}
    assert out == {
        f"{BASE}/b#limits": "ok",
        f"{BASE}/b#nope": "anchor",
        f"{BASE}/missing": "broken",
        f"{BASE}/old": "redirect",
        f"{BASE}/not-crawled": "broken",
        "https://ext.org/ok": "ok",
        "https://ext.org/gone": "broken",
        "https://ext.org/moved": "redirect",
        "https://ext.org/no-head": "ok",
        "https://ext.org/wall": "blocked",
        "https://ext.org/flaky": "ok",
        "https://ext.org/cached": "ok",
    }
    assert by_url[("p1", f"{BASE}/b#limits")].internal and not by_url[("p1", "https://ext.org/ok")].internal
    assert by_url[("p1", "https://ext.org/moved")].final_url == "https://ext.org/new"
    assert ("p2", "https://ext.org/ok") in by_url
    assert flaky.call_count == 2 and not cached.called  # one retry after the 503
    assert f"{BASE}/not-crawled" not in probed and "https://ext.org/gone" in probed  # only external is cached
    assert progress[-1] == (11, 11)  # distinct http(s) targets; ftp: is skipped

    async with discovery.client() as http:
        rows, _ = await check(http, pages[:1], {"help.x.com"}, known, cache, True)
    assert cached.called  # re-check asked for
