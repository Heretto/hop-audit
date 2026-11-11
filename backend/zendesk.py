"""Zendesk help centers read through Zendesk's Help Center API, the site's
other source of pages (crawl rule ``source: "zendesk"``).

Zendesk publishes that API for programs to read a help center's published
articles: ``/api/v2/help_center/<locale>/articles.json`` with each article's
body, title, URL and edit date, plus its section and category. Some sites put
their article pages behind bot protection but leave the API open; this reads
the API the site offers, with the crawler's honest user agent, robots.txt and
delay. A refusal of the API is reported like any other.

Articles become pages: the body under the title, the category and section as
the breadcrumb (and the category as the page's section). The page itself, with
its title tag and meta tags, isn't read, so SEO checks skip these pages.
"""

import asyncio
import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from discovery import BLOCKED_STATUSES, USER_AGENT, Blocked, refusal

API = "/api/v2/help_center"
PER_PAGE = 100
MAX_LISTING_PAGES = 1000  # 100,000 articles; a guard against a pagination loop
RETRIES = 2
MAX_WAIT = 60.0  # seconds; longer Retry-After waits fail the listing instead
SOURCE = "zendesk"  # PageContent.source for pages read this way
LOCALE_IN_PATH = re.compile(r"/hc/([A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*)(?:/|$)")


@dataclass
class Info:
    """What detection found: the help center's locales and how many articles the default one has."""

    locales: list[str]
    default_locale: str
    articles: int


@dataclass
class Article:
    url: str
    title: str
    body: str
    locale: str
    edited: datetime | None
    category: str = ""
    section: str = ""


@dataclass
class Listing:
    locale: str
    articles: list[Article] = field(default_factory=list)
    requests: int = 0


def origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def allowed(rules: RobotFileParser | None, url: str) -> bool:
    return rules is None or rules.can_fetch(USER_AGENT, url)


async def _get(http: httpx.AsyncClient, url: str, wait=asyncio.sleep) -> httpx.Response:
    """The API's answer; waits out rate limits (Retry-After) and retries server errors."""
    for attempt in range(RETRIES + 1):
        response = await http.get(url, headers={"Accept": "application/json"})
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == RETRIES:
                break
            try:
                delay = float(response.headers.get("retry-after", "") or 5 * (attempt + 1))
            except ValueError:
                delay = 5.0 * (attempt + 1)
            if delay > MAX_WAIT:
                break
            await wait(delay)
            continue
        break
    if response.status_code in BLOCKED_STATUSES:
        raise Blocked(refusal(response))
    response.raise_for_status()
    return response


async def probe(http: httpx.AsyncClient, start_url: str, rules: RobotFileParser | None = None) -> Info | None:
    """The help center's Zendesk locales and article count, or None when it isn't Zendesk (or says no)."""
    base = origin(start_url)
    url = f"{base}{API}/locales.json"
    if not allowed(rules, url):
        return None
    try:
        response = await http.get(url, headers={"Accept": "application/json"})
        if response.status_code != 200:
            return None
        data = response.json()
        locales, default = data["locales"], data["default_locale"]
        locale = locale_for(start_url, "", locales, default) or default
        count_url = f"{base}{API}/{locale}/articles.json?per_page=1"
        count = 0
        if allowed(rules, count_url):
            counted = await http.get(count_url, headers={"Accept": "application/json"})
            if counted.status_code == 200:
                count = int(counted.json().get("count") or 0)
        return Info(locales=list(locales), default_locale=default, articles=count)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


def locale_for(url: str, language: str, locales: list[str], default: str) -> str | None:
    """The Zendesk locale for a help center: from its /hc/<locale> URL, else its language
    (exactly, or en for en-us), else None."""
    known = {loc.lower(): loc for loc in locales}
    if match := LOCALE_IN_PATH.search(urlsplit(url).path):
        if found := known.get(match.group(1).lower()):
            return found
    language = language.lower()
    if not language:
        return default if default.lower() in known else None
    if found := known.get(language):
        return found
    prefixed = [loc for key, loc in known.items() if key.split("-")[0] == language.split("-")[0]]
    if default in prefixed:
        return default
    return prefixed[0] if prefixed else None


def _parse_time(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


async def _all(http, url: str, key: str, rules, delay: float, listing: Listing) -> list[dict]:
    """Every item of a paginated listing, following next_page."""
    items: list[dict] = []
    seen: set[str] = set()
    for _ in range(MAX_LISTING_PAGES):
        if url in seen:  # a next_page that points back: stop rather than loop
            break
        seen.add(url)
        if not allowed(rules, url):
            raise Blocked(f"robots.txt on {urlsplit(url).hostname} disallows {urlsplit(url).path}")
        response = await _get(http, url)
        listing.requests += 1
        data = response.json()
        items += data.get(key) or []
        url = data.get("next_page")
        if not url:
            break
        await asyncio.sleep(delay)
    return items


async def articles(
    http: httpx.AsyncClient, root_url: str, locale: str, rules: RobotFileParser | None = None, delay: float = 0.25
) -> Listing:
    """The locale's published articles, each with its category and section names."""
    base = f"{origin(root_url)}{API}/{locale}"
    listing = Listing(locale)
    sections = await _all(http, f"{base}/sections.json?per_page={PER_PAGE}", "sections", rules, delay, listing)
    categories = await _all(http, f"{base}/categories.json?per_page={PER_PAGE}", "categories", rules, delay, listing)
    found = await _all(http, f"{base}/articles.json?per_page={PER_PAGE}", "articles", rules, delay, listing)
    category_names = {c["id"]: c.get("name") or "" for c in categories}
    section_of = {s["id"]: (s.get("name") or "", category_names.get(s.get("category_id"), "")) for s in sections}
    for a in found:
        if a.get("draft") or not a.get("html_url"):
            continue
        section, category = section_of.get(a.get("section_id"), ("", ""))
        listing.articles.append(
            Article(
                url=urljoin(root_url, a["html_url"]),
                title=a.get("title") or "",
                body=a.get("body") or "",
                locale=a.get("locale") or locale,
                edited=_parse_time(a.get("edited_at") or a.get("updated_at")),
                category=category,
                section=section,
            )
        )
    return listing


def page_html(article: Article) -> str:
    """The article as a page for extract(): its title, its body, and its place as a breadcrumb."""
    crumbs = "".join(f"<li>{html.escape(c)}</li>" for c in (article.category, article.section) if c)
    return (
        f'<html lang="{html.escape(article.locale)}"><head><title>{html.escape(article.title)}</title></head>'
        f'<body><nav aria-label="Breadcrumb"><ol>{crumbs}</ol></nav>'
        f"<main><h1>{html.escape(article.title)}</h1>{article.body}</main></body></html>"
    )
