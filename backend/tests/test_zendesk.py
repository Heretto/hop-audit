"""Zendesk help centers read through the Help Center API."""

import uuid

import httpx
import pytest
import respx

import discovery
import zendesk
from crawler import Control, Crawler, Previous, plan
from schemas.site import CrawlRules
from scope import Root
from tests.fake_zendesk import API, ZD, article, serve

EN = Root(uuid.uuid4(), "English", f"{ZD}/", "en", True)
DE = Root(uuid.uuid4(), "Deutsch", f"{ZD}/hc/de", "de", False)
RULES = CrawlRules(source="zendesk", delay_ms=0)


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        yield m


class Log(list):
    def __call__(self, stage, level, message):
        self.append((stage, level, message))

    def text(self, level=None):
        return " | ".join(m for _, lv, m in self if level in (None, lv))


async def crawl(roots=(EN,), rules=RULES, scope=None, previous=None, reuse=False):
    log, results = Log(), []

    async def on_page(result):
        results.append(result)

    scope = scope or {"mode": "site"}
    async with discovery.client() as http:
        p = await plan(http, list(roots), rules, scope, previous or {}, log)
        stats = await Crawler(http, rules, scope, previous or {}, reuse, log, Control(), on_page, retry_delay=0).run(p)
    return {r.target.url: r for r in results}, stats, log, p


@pytest.mark.parametrize(
    "url, language, expected",
    [
        (f"{ZD}/hc/de", "en", "de"),  # the URL's locale wins
        (f"{ZD}/hc/en-us/", "en", "en-us"),
        (f"{ZD}/", "en", "en-us"),  # en for en-us
        (f"{ZD}/", "fr", "fr"),
        (f"{ZD}/", "ja", None),
        (f"{ZD}/", "", "en-us"),
    ],
)
def test_locale_for(url, language, expected):
    assert zendesk.locale_for(url, language, ["en-us", "de", "fr"], "en-us") == expected


async def test_probe_finds_locales_and_counts_articles(mock):
    serve(mock)
    async with discovery.client() as http:
        info = await zendesk.probe(http, f"{ZD}/hc/en-us")
    assert info == zendesk.Info(locales=["en-us", "de"], default_locale="en-us", articles=3)


async def test_probe_is_none_for_a_site_that_isnt_zendesk(mock):
    mock.get(f"{API}/locales.json").respond(404)
    async with discovery.client() as http:
        assert await zendesk.probe(http, ZD) is None


async def test_detect_reports_zendesk_even_when_the_pages_are_refused(mock):
    """As on help.chromeriver.com: pages behind a bot challenge, the API open."""
    serve(mock)
    mock.get(f"{ZD}/").respond(403, headers={"server": "cloudflare", "cf-mitigated": "challenge"})
    d = await discovery.detect(f"{ZD}/")
    assert d.status == "blocked" and "Cloudflare's bot challenge" in d.message
    assert d.zendesk == zendesk.Info(["en-us", "de"], "en-us", 3)


async def test_articles_become_pages_without_fetching_them(mock):
    serve(mock)
    pages, stats, log, p = await crawl()
    assert set(pages) == {f"{ZD}/hc/en-us/articles/1-article-1", f"{ZD}/hc/en-us/articles/2-article-2"}  # no draft
    one = pages[f"{ZD}/hc/en-us/articles/1-article-1"]
    assert one.http_status == 200 and one.title == "Article 1" and one.word_count > 40
    assert one.section == "Basics" and one.content["breadcrumb"] == ["Basics", "Getting started"]
    assert one.content["source"] == "zendesk" and one.content["headings"][0] == [1, "Article 1"]
    assert one.content["links"] == [{"url": f"{ZD}/hc/en-us/articles/2", "text": "Next"}]
    assert one.target.lastmod.isoformat() == "2026-10-01T10:00:00+00:00"
    assert pages[f"{ZD}/hc/en-us/articles/2-article-2"].section == "Accounts"
    assert not p.follow and stats.fetched == 2 and stats.found == 0
    assert "English: Zendesk's Help Center API lists 2 published articles in en-us (4 requests)." in log.text("info")
    assert "/hc/en-us/articles/1-article-1: from Zendesk's API, " in log.text("detail")
    html_pages = [c.request.url for c in mock.calls if "/hc/" in c.request.url.path]
    assert html_pages == []  # the article pages themselves are never requested


async def test_each_help_center_reads_its_own_locale(mock):
    serve(mock, articles=[article(1), article(5, locale="de")])
    pages, _, _, _ = await crawl(roots=(EN, DE))
    assert pages[f"{ZD}/hc/de/articles/5-article-5"].target.root == DE
    assert pages[f"{ZD}/hc/en-us/articles/1-article-1"].target.root == EN


async def test_a_help_center_without_its_locale_or_without_zendesk_is_reported(mock):
    serve(mock, locales=("en-us",))
    ja = Root(uuid.uuid4(), "日本語", f"{ZD}/hc/ja", "ja", False)
    pages, _, log, p = await crawl(roots=(EN, ja))
    assert p.blocked == {ja.id: "Zendesk on support.z.com has no ja locale (it has en-us)"}
    assert len(pages) == 2


async def test_a_refused_api_is_reported_not_worked_around(mock):
    serve(mock)
    mock.get(f"{API}/en-us/sections.json", params={"per_page": "100"}).respond(
        403, headers={"server": "cloudflare", "cf-mitigated": "challenge"}
    )
    pages, _, log, p = await crawl()
    assert pages == {}
    assert "refused the request with Cloudflare's bot challenge" in p.blocked[EN.id]
    assert "Reported, not worked around; skipped." in log.text("error")


async def test_robots_txt_can_rule_out_the_api(mock):
    serve(mock, robots="User-agent: *\nDisallow: /api/\n")
    pages, _, _, p = await crawl()
    assert pages == {} and "isn't there" in p.blocked[EN.id]  # the probe itself is disallowed


async def test_rate_limits_wait_for_retry_after(mock):
    waits = []

    async def wait(seconds):
        waits.append(seconds)

    route = mock.get(f"{API}/locales.json").mock(
        side_effect=[httpx.Response(429, headers={"retry-after": "3"}), httpx.Response(200, json={"ok": 1})]
    )
    async with discovery.client() as http:
        response = await zendesk._get(http, f"{API}/locales.json", wait=wait)
    assert response.json() == {"ok": 1} and waits == [3.0] and route.call_count == 2


async def test_scope_include_and_reuse_work_on_articles(mock):
    serve(mock)
    rules = CrawlRules(source="zendesk", delay_ms=0, exclude=["/hc/en-us/articles/2-*"])
    pages, _, _, _ = await crawl(rules=rules)
    assert list(pages) == [f"{ZD}/hc/en-us/articles/1-article-1"]

    sections, _, _, _ = await crawl(scope={"mode": "sections", "sections": ["Accounts"]})
    assert list(sections) == [f"{ZD}/hc/en-us/articles/2-article-2"]

    first = pages[f"{ZD}/hc/en-us/articles/1-article-1"]
    previous = {first.target.url: Previous(uuid.uuid4(), first.target.lastmod, first.content_hash, 200,
                                           first.title, first.word_count, first.content)}  # fmt: skip
    again, stats, _, _ = await crawl(previous=previous, reuse=True)
    assert not again[first.target.url].fetched and stats.reused == 1  # same edit date: reused


async def test_a_listing_whose_next_page_points_back_stops(mock):
    looping = {"articles": [article(1)], "next_page": f"{API}/en-us/articles.json?per_page=100"}
    route = mock.get(f"{API}/en-us/articles.json").respond(json=looping)
    async with discovery.client() as http:
        items = await zendesk._all(http, f"{API}/en-us/articles.json?per_page=100", "articles", None, 0,
                                   zendesk.Listing("en-us"))  # fmt: skip
    assert len(items) == 1 and route.call_count == 1


async def test_an_audit_reads_zendesk_and_skips_seo_for_its_pages(client, user, db, mock):
    from models import Page
    from tests.test_runs import add_run, execute

    serve(mock)
    body = {
        "name": "Z Help",
        "start_url": f"{ZD}/",
        "help_centers": [{"name": "English", "url": f"{ZD}/", "language": "en", "is_primary": True}],
        "crawl": {"source": "zendesk", "delay_ms": 0, "render_js": True},
    }
    r = client.post("/api/v1/sites", json=body, headers=user["headers"])
    assert r.status_code == 201 and r.json()["crawl"]["source"] == "zendesk"
    run = await execute(db, add_run(db, r.json(), user, analyses=["readability", "seo"]))
    assert run.status == "completed", run.error
    stages = {s["key"]: s for s in run.stages}
    assert stages["seo"]["detail"].startswith(
        "Not checked: all 2 pages were read through Zendesk's API, without page metadata"
    )
    assert stages["readability"]["status"] == "done"
    pages = db.query(Page).filter(Page.run_id == run.id).all()
    assert {p.content["source"] for p in pages} == {"zendesk"} and all(p.seo is None for p in pages)
    log = [e.message for e in run.log]
    assert "Render JavaScript is off for this run: Zendesk's API sends the articles' text." in log
    assert stages["discover"]["detail"].startswith("articles.json read")
