"""Pages rendered in Chromium, for help centers that build their content with
JavaScript (the site's Render JavaScript rule).

The crawler still fetches each page itself, so robots.txt, refusals, retries
and the page limit work the same with or without rendering. Chromium is then
handed that response for the page's URL, runs the page's own scripts (which
load whatever the page loads, as a visitor's browser would, with the same
honest user agent) and returns the DOM once the network settles. Images,
media, fonts and stylesheets are skipped: they never change the text.

Chromium is the one the PDFs use (pdf.py); without it ``start`` raises
RenderUnavailable and the run reads pages as served.
"""

import asyncio

from discovery import USER_AGENT

MAX_TABS = 3  # pages rendering at once; each tab can take a few hundred MB
LOAD_TIMEOUT = 20_000  # ms for the page's load event
SETTLE_TIMEOUT = 10_000  # ms more for its scripts' requests to finish
SKIPPED = {"image", "media", "font", "stylesheet"}


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
                await page.goto(url, wait_until="load", timeout=LOAD_TIMEOUT)
                try:
                    await page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT)
                except PlaywrightTimeout:
                    pass  # pages that poll never go idle; take what has rendered
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
        browser = await playwright.chromium.launch()
    except PlaywrightError as exc:
        await playwright.stop()
        raise RenderUnavailable(
            "JavaScript rendering needs Chromium on the server: run `playwright install --with-deps chromium` "
            "(the Docker image includes it)."
        ) from exc
    context = await browser.new_context(user_agent=USER_AGENT, service_workers="block")
    return Renderer(playwright, browser, context, max(1, min(tabs, MAX_TABS)))
