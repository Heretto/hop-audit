"""Find a site's pages and language versions before crawling.

Sitemaps come first: the one given, else those robots.txt names, else
``/sitemap.xml``. A site that refuses us (401/403/429, robots.txt) is
reported as blocked, never worked around: HOP Audit identifies itself
honestly and does not retry with another user agent.
"""

import gzip
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from scope import detect_prefix, path_section

USER_AGENT = "HOP-Audit/0.1 (+https://heretto.com)"
BLOCKED_STATUSES = {401, 403, 407, 429, 451}
MAX_BYTES = 20 * 1024 * 1024  # per sitemap or page
MAX_SITEMAPS = 50  # children followed from sitemap indexes

Status = Literal["ok", "no_sitemap", "blocked", "unreachable"]


class Blocked(Exception):
    """The site refused the request; report it, don't work around it."""


# Bot protection names itself in its response headers. Its challenges are meant
# to let browsers through and stop crawlers, so they're reported, never solved
# or dodged (no browser user agent, no headless browser to pass them).
PROTECTIONS = (
    ("Cloudflare's bot challenge", lambda h: h.get("cf-mitigated", "").lower() == "challenge"),
    ("DataDome's bot protection", lambda h: "x-datadome" in h or "datadome" in h.get("server", "").lower()),
    ("Akamai's bot protection", lambda h: "akamai" in h.get("server", "").lower()),
    ("Imperva's bot protection", lambda h: "x-iinfo" in h or "imperva" in h.get("x-cdn", "").lower()),
    ("AWS WAF", lambda h: "x-amzn-waf-action" in h),
    ("Cloudflare's firewall", lambda h: h.get("server", "").lower() == "cloudflare"),
)


def protection(response: httpx.Response) -> str | None:
    """The bot protection that refused a request, from its headers, or None."""
    return next((name for name, matches in PROTECTIONS if matches(response.headers)), None)


def refusal(response: httpx.Response) -> str:
    """Why the site refused us, for the run log and the site's detection."""
    status, host = response.status_code, response.url.host
    by = protection(response)
    if by:
        return (
            f"{host} refused the request with {by} (HTTP {status}), which lets browsers through and stops "
            f"crawlers. The site's owner can allow HOP Audit's user agent ({USER_AGENT})"
        )
    if status == 401:
        return f"{host} asks for a login (HTTP 401)"
    return f"{host} refused the request (HTTP {status})"


@dataclass
class Section:
    path: str
    count: int


@dataclass
class Alternate:
    language: str
    url: str


@dataclass
class Discovery:
    status: Status
    message: str
    sitemap_url: str | None = None
    sitemap_count: int = 0
    url_count: int = 0
    last_modified: datetime | None = None
    sections: list[Section] = field(default_factory=list)
    alternates: list[Alternate] = field(default_factory=list)


# ── Parsing (pure) ────────────────────────────────────────────────────────────


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sitemap(data: bytes) -> tuple[list[tuple[str, datetime | None]], list[str]]:
    """([(page URL, lastmod)], child sitemap URLs) from a urlset or sitemapindex.

    The XML is untrusted: the size cap in ``fetch`` and expat's own
    entity-amplification limits (expat 2.4 and later) bound what a hostile
    sitemap can cost.
    """
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    root = ET.fromstring(data)
    pages, children = [], []
    is_index = _local(root.tag) == "sitemapindex"
    for entry in root:
        loc = lastmod = None
        for child in entry:
            name = _local(child.tag)
            if name == "loc" and child.text:
                loc = child.text.strip()
            elif name == "lastmod" and child.text:
                lastmod = parse_lastmod(child.text.strip())
        if loc and is_index:
            children.append(loc)
        elif loc:
            pages.append((loc, lastmod))
    return pages, children


def parse_lastmod(text: str) -> datetime | None:
    """W3C datetime; a date alone, or no offset, is taken as UTC so all compare."""
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def group_sections(urls: list[str]) -> list[Section]:
    """Pages per section, looking past a language or shared base segment (scope.detect_prefix)."""
    paths = [urlsplit(u).path for u in urls]
    prefix = detect_prefix(paths)
    counts = Counter(path_section(p, prefix) for p in paths)
    return [Section(path, n) for path, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


class _AlternateParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        if "alternate" in a.get("rel", "").lower().split() and a.get("hreflang") and a.get("href"):
            self.found.append((a["hreflang"].strip(), a["href"].strip()))


def parse_hreflang(html: str, base_url: str) -> list[Alternate]:
    """Language alternates declared on a page, without x-default or duplicates."""
    parser = _AlternateParser()
    parser.feed(html)
    seen, out = set(), []
    for lang, href in parser.found:
        tag = lang.replace("_", "-")
        if tag.lower() == "x-default" or tag.lower() in seen:
            continue
        seen.add(tag.lower())
        out.append(Alternate(tag, urljoin(base_url, href)))
    return out


def same_site(url: str, start_url: str) -> bool:
    return urlsplit(url).hostname == urlsplit(start_url).hostname


# ── Fetching ──────────────────────────────────────────────────────────────────


def client(**kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=httpx.Timeout(15.0),
        **kwargs,
    )


async def fetch(http: httpx.AsyncClient, url: str) -> httpx.Response | None:
    """The response, None for a 404/410, Blocked when the site refuses us."""
    response = await http.get(url)
    if response.status_code in BLOCKED_STATUSES:
        raise Blocked(refusal(response))
    if response.status_code in (404, 410):
        return None
    response.raise_for_status()
    if len(response.content) > MAX_BYTES:
        raise ValueError(f"{url} is larger than {MAX_BYTES // 1_000_000} MB")
    return response


async def robots(http: httpx.AsyncClient, start_url: str) -> RobotFileParser:
    rp = RobotFileParser()
    try:
        response = await fetch(http, urljoin(start_url, "/robots.txt"))
    except Blocked:
        response = None
    rp.parse(response.text.splitlines() if response is not None else [])
    return rp


@dataclass
class SitemapEntry:
    url: str
    lastmod: datetime | None
    sitemap: str  # the sitemap file that listed it


async def read_sitemaps(http: httpx.AsyncClient, url: str) -> tuple[list[SitemapEntry], int] | None:
    """Every page under a sitemap or sitemap index, and how many sitemap files
    were read; None when the sitemap doesn't exist."""
    queue, entries, read = [url], [], 0
    while queue and read < MAX_SITEMAPS:
        source = queue.pop(0)
        response = await fetch(http, source)
        if response is None:
            if read == 0:
                return None
            continue
        read += 1
        pages, children = parse_sitemap(response.content)
        entries += [SitemapEntry(loc, lastmod, source) for loc, lastmod in pages]
        queue += children
    return entries, read


async def find_sitemap(
    http: httpx.AsyncClient, start_url: str, sitemap_url: str, rules: RobotFileParser
) -> tuple[str, list[SitemapEntry], int] | None:
    """The given sitemap, else those robots.txt names, else /sitemap.xml:
    (its URL, its entries on the start URL's host, files read)."""
    candidates = [sitemap_url] if sitemap_url else [*(rules.site_maps() or []), urljoin(start_url, "/sitemap.xml")]
    for candidate in dict.fromkeys(candidates):
        result = await read_sitemaps(http, candidate)
        if result is not None:
            entries, count = result
            seen, kept = set(), []
            for e in entries:
                if same_site(e.url, start_url) and e.url not in seen:
                    seen.add(e.url)
                    kept.append(e)
            return candidate, kept, count
    return None


async def detect(start_url: str, sitemap_url: str = "", respect_robots: bool = True, http=None) -> Discovery:
    """Sitemap, sections and hreflang alternates for a site's start URL."""
    own = http is None
    http = http or client()
    host = urlsplit(start_url).hostname
    try:
        rules = await robots(http, start_url)
        if respect_robots and not rules.can_fetch(USER_AGENT, start_url):
            return Discovery("blocked", f"robots.txt on {host} disallows crawling the start URL")

        alternates = []
        page = await fetch(http, start_url)
        if page is not None and "html" in page.headers.get("content-type", "html"):
            alternates = parse_hreflang(page.text, str(page.url))

        found = await find_sitemap(http, start_url, sitemap_url, rules)
        if found:
            candidate, entries, count = found
            pages = [e.url for e in entries]
            dates = [e.lastmod for e in entries if e.lastmod]
            sections = group_sections(pages)
            return Discovery(
                "ok",
                f"Sitemap found: {len(pages):,} URLs in {len(sections)} sections",
                sitemap_url=candidate,
                sitemap_count=count,
                url_count=len(pages),
                last_modified=max(dates) if dates else None,
                sections=sections,
                alternates=alternates,
            )
        if sitemap_url:
            return Discovery("no_sitemap", f"No sitemap at {sitemap_url}", alternates=alternates)
        return Discovery("no_sitemap", "No sitemap found; pages are found from the start URL", alternates=alternates)
    except Blocked as exc:
        return Discovery("blocked", str(exc))
    except ET.ParseError:
        return Discovery("unreachable", "The sitemap is not valid XML")
    except (httpx.HTTPError, ValueError, OSError) as exc:
        return Discovery("unreachable", f"Could not reach {host}: {type(exc).__name__}")
    finally:
        if own:
            await http.aclose()
