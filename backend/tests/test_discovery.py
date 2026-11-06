"""Sitemap and hreflang discovery, against mocked HTTP."""

import gzip
import xml.etree.ElementTree as ET

import httpx
import pytest
import respx

import discovery
from discovery import group_sections, parse_hreflang, parse_lastmod, parse_sitemap

URLSET = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://help.example.com/authoring/a</loc><lastmod>2026-10-20</lastmod></url>
  <url><loc>https://help.example.com/authoring/b</loc></url>
  <url><loc>https://help.example.com/api/c</loc><lastmod>2026-10-18T09:00:00Z</lastmod></url>
  <url><loc>https://help.example.com/</loc></url>
  <url><loc>https://elsewhere.example.org/x</loc></url>
</urlset>"""

INDEX = b"""<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://help.example.com/sitemap-1.xml</loc></sitemap>
  <sitemap><loc>https://help.example.com/sitemap-2.xml.gz</loc></sitemap>
</sitemapindex>"""

HOME = """<html><head>
<link rel="alternate" hreflang="en" href="https://help.example.com/">
<link rel="alternate" hreflang="de" href="/de/">
<link rel="alternate" hreflang="fr_CA" href="https://help.example.ca/fr/">
<link rel="alternate" hreflang="x-default" href="https://help.example.com/">
<link rel="alternate" hreflang="DE" href="/de-again/">
<link rel="stylesheet" href="/a.css">
</head><body></body></html>"""

START = "https://help.example.com/"


def test_parse_urlset():
    pages, children = parse_sitemap(URLSET)
    assert len(pages) == 5 and children == []
    assert pages[0] == ("https://help.example.com/authoring/a", parse_lastmod("2026-10-20"))
    assert pages[1][1] is None
    assert pages[2][1].isoformat() == "2026-10-18T09:00:00+00:00"


def test_parse_index_and_gzip():
    pages, children = parse_sitemap(gzip.compress(INDEX))
    assert pages == [] and len(children) == 2


def test_parse_invalid_xml():
    with pytest.raises(ET.ParseError):
        parse_sitemap(b"<urlset><url>")


def test_sections():
    groups = group_sections(["https://a.com/b/1", "https://a.com/a/1", "https://a.com/b/2", "https://a.com/"])
    assert [(s.path, s.count) for s in groups] == [("/b", 2), ("/", 1), ("/a", 1)]
    # A Heretto portal: the first segment is the language, the second the section.
    heretto = group_sections(
        ["https://d.com/en/", "https://d.com/en/ccms/x", "https://d.com/en/ccms/y", "https://d.com/de/portal/z"]
    )
    assert [(s.path, s.count) for s in heretto] == [("/ccms", 2), ("/", 1), ("/portal", 1)]


def test_parse_hreflang():
    alts = parse_hreflang(HOME, START)
    assert [(a.language, a.url) for a in alts] == [
        ("en", "https://help.example.com/"),
        ("de", "https://help.example.com/de/"),
        ("fr-CA", "https://help.example.ca/fr/"),
    ]


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        yield m


async def run(**kwargs):
    async with discovery.client() as http:
        return await discovery.detect(START, http=http, **kwargs)


async def test_detect_sitemap_from_robots(mock):
    mock.get(f"{START}robots.txt").respond(
        text="User-agent: *\nAllow: /\nSitemap: https://help.example.com/index.xml\n"
    )
    mock.get(START).respond(html=HOME)
    mock.get(f"{START}index.xml").respond(content=INDEX)
    mock.get(f"{START}sitemap-1.xml").respond(content=URLSET)
    mock.get(f"{START}sitemap-2.xml.gz").respond(
        content=gzip.compress(b"<urlset><url><loc>https://help.example.com/api/d</loc></url></urlset>")
    )
    result = await run()
    assert result.status == "ok"
    assert result.sitemap_url == f"{START}index.xml" and result.sitemap_count == 3
    assert result.url_count == 5  # other hosts dropped
    assert [(s.path, s.count) for s in result.sections] == [("/api", 2), ("/authoring", 2), ("/", 1)]
    assert result.last_modified.date().isoformat() == "2026-10-20"
    assert [a.language for a in result.alternates] == ["en", "de", "fr-CA"]


async def test_detect_falls_back_to_sitemap_xml(mock):
    mock.get(f"{START}robots.txt").respond(404)
    mock.get(START).respond(html="<html></html>")
    mock.get(f"{START}sitemap.xml").respond(content=URLSET)
    result = await run()
    assert result.status == "ok" and result.sitemap_url == f"{START}sitemap.xml"


async def test_detect_given_sitemap(mock):
    mock.get(f"{START}robots.txt").respond(404)
    mock.get(START).respond(html="<html></html>")
    mock.get(f"{START}custom.xml").respond(content=URLSET)
    assert (await run(sitemap_url=f"{START}custom.xml")).status == "ok"
    mock.get(f"{START}missing.xml").respond(404)
    result = await run(sitemap_url=f"{START}missing.xml")
    assert result.status == "no_sitemap" and "missing.xml" in result.message


async def test_detect_no_sitemap(mock):
    mock.get(f"{START}robots.txt").respond(404)
    mock.get(START).respond(html=HOME)
    mock.get(f"{START}sitemap.xml").respond(404)
    result = await run()
    assert result.status == "no_sitemap" and len(result.alternates) == 3


@pytest.mark.parametrize("code", [401, 403, 429])
async def test_detect_reports_blocked_site(mock, code):
    mock.get(f"{START}robots.txt").respond(404)
    route = mock.get(START).respond(code)
    result = await run()
    assert result.status == "blocked" and f"HTTP {code}" in result.message
    assert route.call_count == 1  # no retry, no other user agent
    assert route.calls[0].request.headers["user-agent"] == discovery.USER_AGENT


async def test_detect_respects_robots(mock):
    mock.get(f"{START}robots.txt").respond(text="User-agent: *\nDisallow: /\n")
    page = mock.get(START).respond(html=HOME)
    result = await run()
    assert result.status == "blocked" and "robots.txt" in result.message
    assert not page.called
    mock.get(f"{START}sitemap.xml").respond(404)
    assert (await run(respect_robots=False)).status == "no_sitemap"


async def test_detect_unreachable(mock):
    mock.get(f"{START}robots.txt").mock(side_effect=httpx.ConnectError("refused"))
    result = await run()
    assert result.status == "unreachable" and "ConnectError" in result.message


async def test_detect_invalid_sitemap(mock):
    mock.get(f"{START}robots.txt").respond(404)
    mock.get(START).respond(html="<html></html>")
    mock.get(f"{START}sitemap.xml").respond(content=b"<urlset><url>")
    assert (await run()).status == "unreachable"


def test_detect_route(client, user, monkeypatch):
    async def fake(start_url, sitemap_url, respect_robots):
        return discovery.Discovery("ok", "found", url_count=3, sections=[discovery.Section("/a", 3)])

    monkeypatch.setattr(discovery, "detect", fake)
    r = client.post("/api/v1/sites/detect", json={"start_url": START}, headers=user["headers"])
    assert r.status_code == 200
    assert r.json()["sections"] == [{"path": "/a", "count": 3}]
    assert client.post("/api/v1/sites/detect", json={"start_url": "nope"}, headers=user["headers"]).status_code == 422
    assert client.post("/api/v1/sites/detect", json={"start_url": START}).status_code == 401


def test_lastmod_is_always_aware():
    assert parse_lastmod("2026-10-20").tzinfo is not None
    assert parse_lastmod("2026-10-20T10:00:00+02:00").utcoffset().total_seconds() == 7200
    assert parse_lastmod("last tuesday") is None
