"""Check every link in a run's main content, once per target.

Targets the crawl already read take its result: its HTTP status, its
redirect, and its element ids for #fragment checks. Other targets get a
HEAD (then GET, for servers that refuse HEAD), retried once on timeouts
and server errors. A refusal (401/403/429…) means the link couldn't be
checked, not that it's broken. External results are cached per
organization for a week unless the run asks to re-check them.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urldefrag, urlsplit

import httpx

from discovery import BLOCKED_STATUSES

CACHE_DAYS = 7
CHECK_CONCURRENCY = 8
NO_HEAD = {403, 405, 501}  # servers that refuse HEAD but answer GET
IGNORED_FRAGMENTS = {"", "top", "main", "content"}


@dataclass
class Outcome:
    """What a target URL (no fragment) answered."""

    outcome: str  # ok | redirect | broken | blocked
    status: int | None
    final_url: str | None = None
    note: str = ""


@dataclass
class Known:
    """A target the crawl read."""

    status: int | None
    final_url: str | None
    anchors: list[str] | None  # None: read before anchors were recorded


def classify(status: int | None, final_url: str | None, url: str, error: str = "") -> Outcome:
    if status is None:
        return Outcome("broken", None, None, error or "No response")
    if status in BLOCKED_STATUSES:
        return Outcome("blocked", status, None, f"Couldn't check: the site refused (HTTP {status})")
    if status >= 400:
        return Outcome("broken", status, None, f"HTTP {status}")
    if final_url and urldefrag(final_url)[0].rstrip("/") != url.rstrip("/"):
        return Outcome("redirect", status, final_url, f"Redirects to {final_url}")
    return Outcome("ok", status)


async def probe(http: httpx.AsyncClient, url: str) -> Outcome:
    """HEAD, falling back to GET; one retry on timeouts and server errors."""
    error = ""
    for attempt in range(2):
        try:
            response = await http.head(url)
            if response.status_code in NO_HEAD:
                async with http.stream("GET", url) as streamed:
                    response = streamed
            if response.status_code >= 500 and attempt == 0:
                continue
            final = str(response.url) if response.history else None
            return classify(response.status_code, final, url)
        except httpx.TimeoutException:
            error = "Timed out"
        except httpx.HTTPError as exc:
            error = f"Could not connect ({type(exc).__name__})"
            break
    return classify(None, None, url, error)


@dataclass
class LinkRow:
    page_id: object
    url: str  # as linked, with any fragment
    text: str
    internal: bool
    outcome: str  # ok | redirect | broken | blocked | anchor
    status: int | None
    final_url: str | None
    note: str


def fragment_outcome(target: Outcome, fragment: str, known: Known | None) -> tuple[str, str]:
    """An ok target whose #fragment matches no id on it is an anchor problem."""
    if (
        target.outcome == "ok"
        and fragment not in IGNORED_FRAGMENTS
        and known is not None
        and known.anchors is not None
        and fragment not in known.anchors
    ):
        return "anchor", f"#{fragment} not found on the target page"
    return target.outcome, target.note


async def check(
    http: httpx.AsyncClient,
    pages: list[tuple[object, list[dict]]],  # (page id, its content links)
    internal_hosts: set[str],
    known: dict[str, Known],
    cache: dict[str, tuple[Outcome, datetime]],
    recheck_external: bool,
    on_progress: Callable[[int, int], None] = lambda done, total: None,
    checkpoint: Callable = None,
) -> tuple[list[LinkRow], dict[str, Outcome]]:
    """Every link row, and the external outcomes probed now (to cache)."""
    targets = {urldefrag(link["url"])[0] for _, links in pages for link in links}
    targets = {t for t in targets if urlsplit(t).scheme in ("http", "https")}
    fresh = datetime.now(UTC) - timedelta(days=CACHE_DAYS)
    outcomes: dict[str, Outcome] = {}
    to_probe = []
    for url in targets:
        if url in known:
            k = known[url]
            outcomes[url] = classify(k.status, k.final_url, url)
        elif not recheck_external and url in cache and cache[url][1] > fresh and _host(url) not in internal_hosts:
            outcomes[url] = cache[url][0]
        else:
            to_probe.append(url)

    probed: dict[str, Outcome] = {}
    done = len(outcomes)
    total = len(targets)
    on_progress(done, total)
    limit = asyncio.Semaphore(CHECK_CONCURRENCY)

    async def one(url: str):
        nonlocal done
        async with limit:
            if checkpoint:
                await checkpoint()
            probed[url] = outcomes[url] = await probe(http, url)
            done += 1
            on_progress(done, total)

    await asyncio.gather(*(one(u) for u in sorted(to_probe)))

    rows = []
    for page_id, links in pages:
        for link in links:
            url, fragment = urldefrag(link["url"])
            if url not in outcomes:
                continue
            outcome, note = fragment_outcome(outcomes[url], fragment, known.get(url))
            o = outcomes[url]
            rows.append(
                LinkRow(
                    page_id,
                    link["url"],
                    link.get("text", ""),
                    _host(url) in internal_hosts,
                    outcome,
                    o.status,
                    o.final_url,
                    note,
                )
            )
    external = {u: o for u, o in probed.items() if _host(u) not in internal_hosts}
    return rows, external


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()
