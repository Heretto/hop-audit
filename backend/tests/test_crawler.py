"""The planner and crawler against the fake help center."""

import asyncio
import uuid
from datetime import UTC, datetime

import httpx
import pytest
import respx

import discovery
from crawler import Cancelled, Control, Crawler, Previous, plan
from schemas.site import CrawlRules
from scope import Root
from tests.fake_site import BASE, SITEMAP, serve

EN = Root(uuid.uuid4(), "US English", BASE, "en", True)
DE = Root(uuid.uuid4(), "Deutsch", f"{BASE}de/", "de", False)
ROOTS = [EN, DE]


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        yield m


class Log(list):
    def __call__(self, stage, level, message):
        self.append((stage, level, message))

    def text(self, level=None):
        return " | ".join(m for _, lv, m in self if level in (None, lv))


async def make_plan(rules=None, scope=None, previous=None, roots=ROOTS):
    log = Log()
    async with discovery.client() as http:
        p = await plan(
            http, roots, rules or CrawlRules(follow_links=False), scope or {"mode": "site"}, previous or {}, log
        )
    return p, log


async def crawl(rules=None, scope=None, previous=None, reuse=False, control=None, **kwargs):
    rules = rules or CrawlRules(follow_links=False, delay_ms=0)
    scope = scope or {"mode": "site"}
    log, results, totals = Log(), [], []

    async def on_page(result):
        results.append(result)

    async with discovery.client() as http:
        p = await plan(http, ROOTS, rules, scope, previous or {}, log)
        crawler = Crawler(
            http,
            rules,
            scope,
            previous or {},
            reuse,
            log,
            control or Control(),
            on_page,
            totals.append,
            retry_delay=0,
            **kwargs,
        )
        stats = await crawler.run(p)
    return {r.target.url: r for r in results}, stats, log, totals


def urls(*paths):
    return {f"{BASE}{p}" for p in paths}


# ── Planning ──────────────────────────────────────────────────────────────────


async def test_plan_assigns_help_centers_and_sections(mock):
    serve(mock)
    p, _ = await make_plan()
    by_url = {t.url: t for t in p.targets}
    assert set(by_url) == urls("", "authoring/a", "authoring/b", "api/c", "de/", "de/authoring/a", "archive/old")
    assert by_url[f"{BASE}de/authoring/a"].root == DE
    assert by_url[f"{BASE}de/authoring/a"].section == "/authoring"  # relative to the help center
    assert by_url[f"{BASE}authoring/a"].lastmod == datetime(2026, 10, 1, tzinfo=UTC)
    assert p.per_root[DE.id] == 2 and p.listed == 7
    assert p.sections["/authoring"] == 3
    assert p.sitemaps == {"help.x.com": f"{BASE}sitemap.xml"}


async def test_plan_reads_sections_below_a_language_segment(mock):
    entries = [(p, None) for p in ("", "en/", "en/ccms/a", "en/ccms/b", "en/portal/c", "fr/ccms/a")]
    serve(mock, entries=entries)
    p, log = await make_plan(roots=[EN])
    assert p.sections == {"/ccms": 3, "/portal": 1, "/": 2}
    assert {t.section for t in p.targets if t.url == f"{BASE}fr/ccms/a"} == {"/ccms"}
    assert "US English: paths start with a language (en, fr)" in log.text("info")
    sectioned, _ = await make_plan(scope={"mode": "sections", "sections": ["/portal"]}, roots=[EN])
    assert {t.url for t in sectioned.targets} == urls("en/portal/c")


async def test_plan_applies_include_exclude_and_max_pages(mock):
    serve(mock)
    p, _ = await make_plan(CrawlRules(include=["/authoring/**", "/api/**"], exclude=["/authoring/b"]))
    assert {t.url for t in p.targets} == urls("authoring/a", "api/c", "de/authoring/a")
    p, log = await make_plan(CrawlRules(max_pages=2))
    assert len(p.targets) == 2 and "5 pages left out" in log.text("warn")


async def test_plan_respects_robots(mock):
    serve(mock, robots="User-agent: *\nDisallow: /archive/\n")
    p, _ = await make_plan()
    assert f"{BASE}archive/old" not in {t.url for t in p.targets}
    p, _ = await make_plan(CrawlRules(respect_robots=False))
    assert f"{BASE}archive/old" in {t.url for t in p.targets}


async def test_plan_reports_blocked_help_center(mock):
    serve(mock, **{"de/": httpx.Response(403)})
    p, log = await make_plan()
    assert p.blocked == {DE.id: "help.x.com refused the request (HTTP 403)"}
    assert all(t.root == EN for t in p.targets)
    assert "Deutsch: help.x.com refused the request (HTTP 403). Reported, not worked around" in log.text("error")


async def test_plan_scopes(mock):
    serve(mock)
    p, _ = await make_plan(scope={"mode": "sections", "sections": ["/api"]})
    assert {t.url for t in p.targets} == urls("api/c")

    p, _ = await make_plan(scope={"mode": "pages", "pages": ["/authoring/a", f"{BASE}de/", "https://nope.org/x"]})
    assert {t.url for t in p.targets} == urls("authoring/a", "de/")
    assert not p.follow

    old = datetime(2026, 9, 1, tzinfo=UTC)
    previous = {
        f"{BASE}authoring/a": Previous(uuid.uuid4(), datetime(2026, 10, 1, tzinfo=UTC), "h", 200, "", 0, {}),
        f"{BASE}authoring/b": Previous(uuid.uuid4(), old, "h", 200, "", 0, {}),
    }
    p, _ = await make_plan(scope={"mode": "changed"}, previous=previous)
    changed = {t.url for t in p.targets}
    assert f"{BASE}authoring/a" not in changed  # same lastmod
    assert f"{BASE}authoring/b" in changed and f"{BASE}api/c" in changed  # newer, and new


async def test_plan_without_sitemap_starts_from_roots(mock):
    serve(mock, **{"sitemap.xml": httpx.Response(404)})
    p, log = await make_plan()
    assert {(t.url, t.depth) for t in p.targets} == {(BASE, 0), (f"{BASE}de/", 0)}
    assert p.follow
    assert "No sitemap on help.x.com" in log.text("warn")


# ── Crawling ──────────────────────────────────────────────────────────────────


async def test_crawl_reads_every_planned_page(mock):
    routes = serve(mock)
    pages, stats, log, _ = await crawl()
    assert set(pages) == urls("", "authoring/a", "authoring/b", "api/c", "de/", "de/authoring/a", "archive/old")
    a = pages[f"{BASE}authoring/a"]
    assert a.http_status == 200 and a.title == "Topic A" and a.word_count > 30 and a.content_hash
    assert a.content["links"][0]["url"] == f"{BASE}authoring/b#step-2"
    assert stats.fetched == 7 and stats.links > 0
    assert routes["robots.txt"].calls[0].request.headers["user-agent"] == discovery.USER_AGENT
    assert not routes["hidden/extra"].called  # follow_links off


async def test_crawl_follows_links_within_help_centers_and_depth(mock):
    routes = serve(mock)
    pages, stats, _, totals = await crawl(CrawlRules(follow_links=True, delay_ms=0, max_depth=2))
    assert f"{BASE}hidden/extra" in pages  # linked from the home page (depth 1 -> 2)
    assert f"{BASE}hidden/deeper" not in pages  # would be depth 3
    assert f"{BASE}nav-only" not in pages  # navigation isn't main content
    assert not any("elsewhere.org" in u for u in pages)
    assert stats.found == 1 and totals[-1] == 8
    assert routes["authoring/b"].call_count == 1  # #fragment links aren't new pages


async def test_crawl_retries_server_errors(mock):
    serve(
        mock,
        **{"api/c": [httpx.Response(503), httpx.Response(503), httpx.Response(200, html="<main><h1>C</h1></main>")]},
    )
    pages, _, log, _ = await crawl()
    assert pages[f"{BASE}api/c"].http_status == 200
    assert "/api/c returned 503 twice; retried after 0 s and succeeded." in log.text("warn")


async def test_crawl_gives_up_after_retries(mock):
    serve(mock, **{"api/c": httpx.Response(500)})
    pages, stats, log, _ = await crawl()
    assert pages[f"{BASE}api/c"].error == "Failed after 3 attempts (returned 500)"
    assert stats.failed == 1 and "gave up" in log.text("error")


async def test_crawl_records_missing_pages_and_skips_non_html(mock):
    serve(
        mock,
        **{
            "authoring/b": httpx.Response(404),
            "api/c": httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"}),
        },
    )
    pages, stats, _, _ = await crawl()
    assert pages[f"{BASE}authoring/b"].http_status == 404 and pages[f"{BASE}authoring/b"].error == "HTTP 404"
    assert f"{BASE}api/c" not in pages and stats.skipped == 1


async def test_crawl_blocks_help_center_that_refuses_every_page(mock):
    entries = SITEMAP + [(f"de/p{i}", None) for i in range(8)]
    serve(
        mock,
        entries=entries,
        **{"de/authoring/a": httpx.Response(403), **{f"de/p{i}": httpx.Response(403) for i in range(8)}},
    )
    rules = CrawlRules(follow_links=False, delay_ms=0, concurrency=1)
    pages, _, log, _ = await crawl(rules)
    refused = [u for u, r in pages.items() if r.error and r.error.startswith("Refused")]
    # The German root page itself was read, so the help center isn't blocked outright.
    assert len(refused) == 9
    assert "Deutsch" not in log.text("error")


async def test_crawl_stops_on_help_center_with_only_refusals(mock):
    entries = [("", None), *[(f"de/p{i}", None) for i in range(8)]]
    serve(mock, entries=entries, **{f"de/p{i}": httpx.Response(403) for i in range(8)})
    rules = CrawlRules(follow_links=False, delay_ms=0, concurrency=1)
    log, results = Log(), []

    async def on_page(r):
        results.append(r)

    async with discovery.client() as http:
        p = await plan(http, ROOTS, rules, {"mode": "site"}, {}, log)
        p.targets = [t for t in p.targets if t.root == DE and t.depth > 0]  # the root check passed; pages refuse
        await Crawler(http, rules, {"mode": "site"}, {}, False, log, Control(), on_page, retry_delay=0).run(p)
    assert len(results) == 5  # stops asking after five refusals
    assert "Deutsch: refused 5 requests in a row. Reported, not worked around; skipped." in log.text("error")


async def test_crawl_reuses_unchanged_pages(mock):
    routes = serve(mock)
    first, _, _, _ = await crawl()
    a = first[f"{BASE}authoring/a"]
    previous = {
        url: Previous(uuid.uuid4(), r.target.lastmod, r.content_hash, r.http_status, r.title, r.word_count, r.content)
        for url, r in first.items()
    }
    # authoring/b changed lastmod but not content; api/c changed both.
    entries = [(p, "2026-10-05" if p in ("authoring/b", "api/c") else lm) for p, lm in SITEMAP]
    mock.reset()
    routes = serve(mock, entries=entries, **{"api/c": httpx.Response(200, html="<main><h1>New C</h1></main>")})
    second, stats, _, _ = await crawl(previous=previous, reuse=True)

    reused = second[f"{BASE}authoring/a"]
    assert not reused.fetched and reused.reused_from == previous[f"{BASE}authoring/a"].id
    assert reused.content == a.content and not routes["authoring/a"].called
    assert second[f"{BASE}authoring/b"].fetched and second[f"{BASE}authoring/b"].reused_from  # same hash
    assert second[f"{BASE}api/c"].reused_from is None and second[f"{BASE}api/c"].content["headings"] == [[1, "New C"]]
    assert stats.reused == 5 and stats.fetched == 2

    changed_only, stats, _, _ = await crawl(scope={"mode": "changed"}, previous=previous)
    assert set(changed_only) == urls("api/c")
    assert stats.unchanged == 1  # authoring/b: newer lastmod, same text


async def test_cancel_stops_the_crawl(mock):
    serve(mock)
    control = Control()
    seen = []

    async def on_page(result):
        seen.append(result)
        control.cancel()

    rules = CrawlRules(follow_links=False, delay_ms=0, concurrency=1)
    async with discovery.client() as http:
        p = await plan(http, ROOTS, rules, {"mode": "site"}, {}, Log())
        with pytest.raises(Cancelled):
            await Crawler(http, rules, {"mode": "site"}, {}, False, Log(), control, on_page, retry_delay=0).run(p)
    assert len(seen) == 1


async def test_pause_holds_the_crawl_until_resumed(mock):
    serve(mock)
    control = Control()
    control.pause()
    task = asyncio.create_task(crawl(control=control))
    await asyncio.sleep(0.2)
    assert not task.done()
    control.resume()
    pages, _, _, _ = await asyncio.wait_for(task, 5)
    assert len(pages) == 7
