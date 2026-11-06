"""Discover and fetch the pages of one audit run.

``plan()`` reads each host's robots.txt and sitemap, checks every help
center's root and applies the site's rules and the run's scope. ``Crawler``
then fetches the pages with the site's concurrency and delay, reuses pages
the last run already read when they haven't changed, and follows links within
the help centers.

A help center that refuses us is reported and skipped. HOP Audit identifies
itself honestly and never retries a refusal another way; it only slows down
and retries server errors, timeouts and rate limits.
"""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from uuid import UUID

import httpx

import discovery
from discovery import BLOCKED_STATUSES, MAX_BYTES, USER_AGENT, Blocked
from extract import PageContent, checksum, extract, page_url
from schemas.site import CrawlRules
from scope import (
    Prefix,
    Root,
    allowed,
    breadcrumb_section,
    describe_prefix,
    detect_prefix,
    help_center_for,
    listed_urls,
    path_section,
    relative_path,
    sitemap_section,
)

Log = Callable[[str, str, str], None]  # (stage, level, message)
RETRYABLE = {500, 502, 503, 504, 429}
NOT_PAGES = (".pdf", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".mp4", ".css", ".js", ".json", ".xml")
SHELL_WARNING = 5  # pages that look like JavaScript shells before the run warns
REFUSALS_TO_BLOCK = 5  # refusals, with no page read, before a help center counts as blocked


class Cancelled(Exception):
    pass


class Control:
    """Pause, resume and cancel, checked between pages."""

    def __init__(self):
        self._running = asyncio.Event()
        self._running.set()
        self.cancelled = False

    def pause(self):
        self._running.clear()

    def resume(self):
        self._running.set()

    def cancel(self):
        self.cancelled = True
        self._running.set()

    @property
    def paused(self) -> bool:
        return not self._running.is_set()

    async def checkpoint(self):
        if self.cancelled:
            raise Cancelled
        await self._running.wait()
        if self.cancelled:
            raise Cancelled


@dataclass
class Previous:
    """A page from the last completed run, for reuse and change detection."""

    id: UUID
    lastmod: datetime | None
    content_hash: str | None
    http_status: int | None
    title: str
    word_count: int
    content: dict


@dataclass
class Target:
    url: str
    root: Root
    section: str
    lastmod: datetime | None = None
    depth: int = 1


@dataclass
class Result:
    target: Target
    section: str
    http_status: int | None = None
    content: dict = field(default_factory=dict)
    content_hash: str | None = None
    title: str = ""
    word_count: int = 0
    error: str | None = None
    reused_from: UUID | None = None
    fetched: bool = True


@dataclass
class Plan:
    targets: list[Target]
    roots: list[Root]
    robots: dict[str, RobotFileParser]
    blocked: dict[UUID, str]
    sitemaps: dict[str, str | None]  # host -> sitemap URL
    listed: int  # sitemap URLs on the help centers before rules and scope
    follow: bool
    per_root: Counter = field(default_factory=Counter)  # root id -> targets
    sections: Counter = field(default_factory=Counter)  # section -> targets
    prefixes: dict[UUID, Prefix] = field(default_factory=dict)  # root id -> segments before the section


def _base(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/"


def changed(target: Target, previous: dict[str, Previous]) -> bool:
    """Might have changed since the last run: new, or no lastmod to say otherwise."""
    prev = previous.get(target.url)
    return prev is None or target.lastmod is None or prev.lastmod is None or target.lastmod > prev.lastmod


async def plan(
    http: httpx.AsyncClient,
    roots: list[Root],
    rules: CrawlRules,
    scope: dict,
    previous: dict[str, Previous],
    log: Log,
) -> Plan:
    mode = scope.get("mode", "site")
    robots: dict[str, RobotFileParser] = {}
    sitemaps: dict[str, str | None] = {}
    entries: list[discovery.SitemapEntry] = []
    for base in dict.fromkeys(_base(r.url) for r in roots):
        host = urlsplit(base).hostname or base
        robots[host] = await discovery.robots(http, base)
        given = rules.sitemap_url if rules.sitemap_url and _base(rules.sitemap_url) == base else ""
        found = await discovery.find_sitemap(http, base, given, robots[host])
        sitemaps[host] = found[0] if found else None
        if found:
            entries += found[1]
            log("discover", "info", f"Read {found[0]}: {len(found[1]):,} URLs in {found[2]} sitemap file(s).")
        else:
            log("discover", "warn", f"No sitemap on {host}; pages are found by following links from each help center.")

    blocked: dict[UUID, str] = {}
    for root in roots:
        host = urlsplit(root.url).hostname or ""
        if rules.respect_robots and not robots[host].can_fetch(USER_AGENT, root.url):
            blocked[root.id] = f"robots.txt on {host} disallows crawling {root.url}"
        else:
            try:
                await discovery.fetch(http, root.url)
            except Blocked as exc:
                blocked[root.id] = str(exc)
            except (httpx.HTTPError, ValueError) as exc:
                blocked[root.id] = f"could not reach {root.url} ({type(exc).__name__})"
        if root.id in blocked:
            log("discover", "error", f"{root.name}: {blocked[root.id]}. Reported, not worked around; skipped.")

    # Sections start below a language or shared base segment, found per help center from its sitemap URLs.
    listed_paths: dict[UUID, list[str]] = {r.id: [] for r in roots}
    for e in entries:
        if root := help_center_for(e.url, roots):
            listed_paths[root.id].append(relative_path(e.url, root))
    prefixes = {r.id: detect_prefix(listed_paths[r.id]) for r in roots}
    for root in roots:
        if prefixes[root.id] and rules.section_grouping != "sitemap":
            log(
                "discover",
                "info",
                f"{root.name}: paths start with {describe_prefix(prefixes[root.id])}, so sections are read below it.",
            )

    def target(url: str, lastmod=None, sitemap: str | None = None, depth=1) -> Target | None:
        root = help_center_for(url, roots)
        if root is None or root.id in blocked:
            return None
        relative = relative_path(url, root)
        if not allowed(relative, rules.include, rules.exclude):
            return None
        host = urlsplit(url).hostname or ""
        if rules.respect_robots and host in robots and not robots[host].can_fetch(USER_AGENT, url):
            return None
        section = (
            sitemap_section(sitemap)
            if rules.section_grouping == "sitemap" and sitemap
            else path_section(relative, prefixes[root.id])
        )
        return Target(page_url(url), root, section, lastmod, depth)

    listed = sum(1 for e in entries if help_center_for(e.url, roots))
    if mode == "pages":
        primary = next((r for r in roots if r.is_primary), roots[0])
        candidates = [target(u) for u in listed_urls(scope.get("pages", []), primary)]
    else:
        candidates = [target(e.url, e.lastmod, e.sitemap) for e in entries]
        covered = {t.root.id for t in candidates if t}
        # A help center the sitemap doesn't cover is crawled from its root.
        candidates += [target(r.url, depth=0) for r in roots if r.id not in covered]
    targets = list({t.url: t for t in candidates if t}.values())

    if mode == "sections":
        wanted = set(scope.get("sections", []))
        targets = [t for t in targets if t.section in wanted or t.depth == 0]
    elif mode == "changed":
        targets = [t for t in targets if changed(t, previous)]
    if len(targets) > rules.max_pages:
        log("discover", "warn", f"Max pages is {rules.max_pages:,}; {len(targets) - rules.max_pages:,} pages left out.")
        targets = targets[: rules.max_pages]

    follow = mode in ("site", "sections") and (rules.follow_links or any(t.depth == 0 for t in targets))
    return Plan(
        targets=targets,
        roots=roots,
        robots=robots,
        blocked=blocked,
        sitemaps=sitemaps,
        listed=listed,
        follow=follow,
        per_root=Counter(t.root.id for t in targets),
        sections=Counter(t.section for t in targets if t.depth > 0),
        prefixes=prefixes,
    )


@dataclass
class Stats:
    fetched: int = 0
    reused: int = 0
    unchanged: int = 0  # changed-scope pages whose content turned out the same
    failed: int = 0
    skipped: int = 0  # not HTML
    found: int = 0  # pages added by following links
    links: int = 0
    shells: int = 0


class Crawler:
    def __init__(
        self,
        http: httpx.AsyncClient,
        rules: CrawlRules,
        scope: dict,
        previous: dict[str, Previous],
        reuse: bool,
        log: Log,
        control: Control,
        on_page: Callable[[Result], Awaitable[None]],
        on_total: Callable[[int], None] = lambda total: None,
        retries: int = 2,
        retry_delay: float = 30.0,
    ):
        self.http, self.rules, self.previous, self.reuse = http, rules, previous, reuse
        self.mode = scope.get("mode", "site")
        self.sections = set(scope.get("sections", []))
        self.log, self.control, self.on_page, self.on_total = log, control, on_page, on_total
        self.retries, self.retry_delay = retries, retry_delay
        self.stats = Stats()
        self._read = Counter()  # root id -> pages read
        self._refused = Counter()  # root id -> refusals

    async def run(self, plan: Plan) -> Stats:
        self.plan = plan
        self.seen = {t.url for t in plan.targets}
        self.on_total(len(self.seen))
        queue: asyncio.Queue[Target] = asyncio.Queue()
        for t in plan.targets:
            queue.put_nowait(t)
        self.failure: BaseException | None = None
        workers = [asyncio.create_task(self._worker(queue)) for _ in range(self.rules.concurrency)]
        joined = asyncio.create_task(queue.join())
        await asyncio.wait([joined, *workers], return_when=asyncio.FIRST_COMPLETED)
        for task in [joined, *workers]:
            task.cancel()
        await asyncio.gather(joined, *workers, return_exceptions=True)
        if self.failure:
            raise self.failure
        if self.stats.shells >= SHELL_WARNING:
            self.log(
                "crawl",
                "warn",
                f"{self.stats.shells} pages had almost no text but load scripts: they may need JavaScript "
                "to render, so their content can't be reviewed as served.",
            )
        return self.stats

    async def _worker(self, queue: asyncio.Queue):
        while True:
            target = await queue.get()
            try:
                await self.control.checkpoint()
                result = await self._visit(target)
                if result:
                    await self.on_page(result)
                    for link in self._links(result):
                        queue.put_nowait(link)
            except BaseException as exc:  # first failure (or cancel) ends the crawl
                self.failure = self.failure or exc
                return
            finally:
                queue.task_done()

    # ── One page ─────────────────────────────────────────────────────────────

    async def _visit(self, target: Target) -> Result | None:
        if target.root.id in self.plan.blocked:
            return None
        prev = self.previous.get(target.url)
        if (
            self.reuse
            and prev
            and prev.http_status == 200
            and target.lastmod
            and prev.lastmod
            and target.lastmod <= prev.lastmod
        ):
            self.stats.reused += 1
            # Same content as last time; it counts as unchanged when the checksum
            # agrees (a checksum from an older definition doesn't).
            digest = checksum(prev.content)
            return Result(
                target,
                section=target.section,
                http_status=prev.http_status,
                content=prev.content,
                content_hash=digest,
                title=prev.title,
                word_count=prev.word_count,
                reused_from=prev.id if digest == prev.content_hash else None,
                fetched=False,
            )

        response, error = await self._fetch(target)
        await asyncio.sleep(self.rules.delay_ms / 1000)
        if response is None:
            self.stats.failed += 1
            return Result(target, target.section, error=error)
        if response.status_code in BLOCKED_STATUSES:
            self._refused[target.root.id] += 1
            self._maybe_block(target.root)
            self.stats.failed += 1
            return Result(target, target.section, response.status_code, error=f"Refused (HTTP {response.status_code})")
        if response.status_code >= 400:
            self.stats.failed += 1
            return Result(target, target.section, response.status_code, error=f"HTTP {response.status_code}")
        if "html" not in response.headers.get("content-type", "text/html"):
            self.stats.skipped += 1
            return None
        if len(response.content) > MAX_BYTES:
            self.stats.failed += 1
            return Result(target, target.section, response.status_code, error="Larger than the 20 MB page limit")

        self._read[target.root.id] += 1
        content: PageContent = extract(response.text, str(response.url))
        if page_url(str(response.url)) != target.url:
            content.final_url = str(response.url)  # reached through a redirect
        digest = checksum(content.as_json())
        unchanged = prev is not None and prev.content_hash == digest
        if self.mode == "changed" and unchanged:
            self.stats.unchanged += 1
            return None
        self.stats.fetched += 1
        self.stats.links += len(content.links)
        self.stats.shells += content.looks_like_shell
        section = (
            breadcrumb_section(content.breadcrumb, target.section)
            if self.rules.section_grouping == "breadcrumb"
            else target.section
        )
        return Result(
            target,
            section,
            response.status_code,
            content.as_json(),
            digest,
            content.title,
            content.word_count,
            reused_from=prev.id if unchanged else None,
        )

    async def _fetch(self, target: Target) -> tuple[httpx.Response | None, str | None]:
        """The response after retrying server errors, timeouts and rate limits."""
        path = urlsplit(target.url).path or "/"
        problem, waited = "", 0.0
        for attempt in range(self.retries + 1):
            if attempt:
                wait = self.retry_delay * attempt
                waited += wait
                await asyncio.sleep(wait)
                await self.control.checkpoint()
            try:
                response = await self.http.get(target.url)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                problem = f"failed ({type(exc).__name__})"
                continue
            if response.status_code not in RETRYABLE:
                if attempt:
                    times = "once" if attempt == 1 else "twice" if attempt == 2 else f"{attempt} times"
                    self.log("crawl", "warn", f"{path} {problem} {times}; retried after {waited:g} s and succeeded.")
                return response, None
            problem = f"returned {response.status_code}"
        self.log("crawl", "error", f"{path} {problem} on {self.retries + 1} attempts; gave up.")
        return None, f"Failed after {self.retries + 1} attempts ({problem})"

    def _maybe_block(self, root: Root):
        if (
            self._read[root.id] == 0
            and self._refused[root.id] >= REFUSALS_TO_BLOCK
            and root.id not in self.plan.blocked
        ):
            message = f"refused {self._refused[root.id]} requests in a row"
            self.plan.blocked[root.id] = message
            self.log("crawl", "error", f"{root.name}: {message}. Reported, not worked around; skipped.")

    # ── Following links ──────────────────────────────────────────────────────

    def _links(self, result: Result) -> list[Target]:
        t = result.target
        if not self.plan.follow or not result.content or t.depth >= self.rules.max_depth:
            return []
        found = []
        for link in result.content.get("links", []):
            url = page_url(link["url"])
            if url in self.seen or len(self.seen) >= self.rules.max_pages:
                continue
            if urlsplit(url).path.lower().endswith(NOT_PAGES):
                continue
            root = help_center_for(url, self.plan.roots)
            if root is None or root.id in self.plan.blocked:
                continue
            relative = relative_path(url, root)
            if not allowed(relative, self.rules.include, self.rules.exclude):
                continue
            host = urlsplit(url).hostname or ""
            robots = self.plan.robots.get(host)
            if self.rules.respect_robots and robots and not robots.can_fetch(USER_AGENT, url):
                continue
            section = path_section(relative, self.plan.prefixes.get(root.id, ()))
            if self.mode == "sections" and section not in self.sections:
                continue
            self.seen.add(url)
            found.append(Target(url, root, section, None, t.depth + 1))
        if found:
            self.stats.found += len(found)
            self.on_total(len(self.seen))
        return found
