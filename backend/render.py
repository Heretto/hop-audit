"""Pages rendered in Chromium, for help centers that build their content with
JavaScript (the site's Render JavaScript rule).

The crawler still fetches each page itself, so robots.txt, refusals, retries
and the page limit work the same with or without rendering. Chromium is then
handed that response for the page's URL, runs the page's own scripts (which
load whatever the page loads, as a visitor's browser would, with the same
honest user agent) and returns the DOM once its text stops changing. Images,
media, fonts and stylesheets are skipped: they never change the text.

It doesn't wait for the network to go quiet: apps such as Salesforce
Experience Cloud help centers poll and stream analytics, so they never do.

Chromium is the one the PDFs use (pdf.py); without it ``start`` raises
RenderUnavailable and the run reads pages as served.
"""

import asyncio

from discovery import USER_AGENT

MAX_TABS = 2  # pages rendering at once; a heavy app's tab takes 300–500 MB
LOAD_TIMEOUT = 20_000  # ms for the HTML to be parsed
SETTLE_TIMEOUT = 15_000  # ms more for the scripts to build the content
SKIPPED = {"image", "media", "font", "stylesheet"}
# Docker gives containers 64 MB of /dev/shm, which Chromium otherwise fills and stalls on.
CHROMIUM_ARGS = ["--disable-dev-shm-usage", "--disable-gpu", "--disable-extensions", "--mute-audio"]

# True once the page's text has stopped changing: for `quiet` ms when there's a
# page's worth of it, or `longQuiet` ms when there's little (a spinner can sit
# still while the app loads). Polled from the page; state lives on window.
SETTLED = """({quiet, longQuiet, enough}) => {
  const n = document.body ? document.body.textContent.length : 0;
  const s = window.__hopSettle || (window.__hopSettle = {n: -1, at: Date.now()});
  if (n !== s.n) { s.n = n; s.at = Date.now(); return false; }
  const still = Date.now() - s.at;
  return still >= (n >= enough ? quiet : longQuiet);
}"""
SETTLE_ARG = {"quiet": 1000, "longQuiet": 4000, "enough": 2000}
POLL = 250  # ms


class RenderUnavailable(Exception):
    """No browser to render with; the message says how to install one."""


class Renderer:
    """One Chromium for a run; ``html`` renders a page the crawler fetched."""

    def __init__(self, playwright, browser, context, tabs: int):
        self._playwright, self._browser, self._context = playwright, browser, context
        self._tabs = asyncio.Semaphore(tabs)

    async def html(self, url: str, body: bytes, content_type: str) -> str:
        """The page's DOM after its scripts ran, ``body`` served as ``url``."""
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        async with self._tabs:
            page = await self._context.new_page()
            served = False

            async def route(r):
                nonlocal served
                req = r.request
                if not served and req.is_navigation_request() and req.frame == page.main_frame:
                    served = True  # the response the crawler already has
                    await r.fulfill(status=200, body=body, content_type=content_type)
                elif req.resource_type in SKIPPED:
                    await r.abort()
                else:
                    await r.continue_()

            try:
                await page.route("**/*", route)
                await page.goto(url, wait_until="domcontentloaded", timeout=LOAD_TIMEOUT)
                try:
                    await page.wait_for_function(SETTLED, arg=SETTLE_ARG, polling=POLL, timeout=SETTLE_TIMEOUT)
                except PlaywrightTimeout:
                    pass  # still changing (a ticker, a feed); take what has rendered
                return await page.content()
            finally:
                await page.close()

    async def close(self) -> None:
        try:
            await self._browser.close()
        finally:
            await self._playwright.stop()


async def start(tabs: int = MAX_TABS) -> Renderer:
    """Chromium, ready to render up to ``tabs`` pages at once."""
    try:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - a dependency of the app
        raise RenderUnavailable("Playwright isn't installed on the server.") from exc
    playwright = await async_playwright().start()
    try:
        browser = await playwright.chromium.launch(args=CHROMIUM_ARGS)
    except PlaywrightError as exc:
        await playwright.stop()
        raise RenderUnavailable(
            "JavaScript rendering needs Chromium on the server: run `playwright install --with-deps chromium` "
            "(the Docker image includes it)."
        ) from exc
    context = await browser.new_context(user_agent=USER_AGENT, service_workers="block")
    return Renderer(playwright, browser, context, max(1, min(tabs, MAX_TABS)))
