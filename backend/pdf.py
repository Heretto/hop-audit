"""Letter PDFs from HTML, rendered by Chromium through Playwright, the way the
skill's `build_onesheet.py` does: the report (paged Letter with margins) and
the one-sheets (one fixed 816×1056 px page, measured for overflow).

The browser is installed apart from the Python package (`playwright install
chromium`; the Dockerfile does it). Without it every call raises
PdfUnavailable with a message the API passes on, rather than a stack trace.
"""

from dataclasses import dataclass

PAGE_W, PAGE_H = 816, 1056  # Letter at 96 dpi
LOAD_TIMEOUT = 20_000  # ms; fonts come from Google Fonts

# The one-sheet's natural height: its root without the fixed height, as the skill measures it.
NATURAL_HEIGHT = """() => {
  const r = document.body.firstElementChild;
  const prev = r.style.height; r.style.height = 'auto';
  const h = r.scrollHeight; r.style.height = prev; return h; }"""


class PdfUnavailable(Exception):
    """No browser to render with; the message says how to install one."""


@dataclass
class Rendered:
    pdf: bytes
    height: int | None = None  # natural content height of a one-page sheet


async def _render(html: str, sheet: bool) -> Rendered:
    try:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - a dependency of the app
        raise PdfUnavailable("Playwright isn't installed on the server.") from exc
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page(viewport={"width": PAGE_W, "height": PAGE_H})
                await page.set_content(html, wait_until="networkidle", timeout=LOAD_TIMEOUT)
                if sheet:
                    height = await page.evaluate(NATURAL_HEIGHT)
                    pdf = await page.pdf(width=f"{PAGE_W}px", height=f"{PAGE_H}px", print_background=True)
                    return Rendered(pdf, height)
                pdf = await page.pdf(
                    format="Letter",
                    print_background=True,
                    margin={"top": "0.6in", "bottom": "0.6in", "left": "0.6in", "right": "0.6in"},
                )
                return Rendered(pdf)
            finally:
                await browser.close()
    except PlaywrightError as exc:
        if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
            raise PdfUnavailable(
                "PDFs need Chromium on the server: run `playwright install --with-deps chromium` "
                "(the Docker image includes it)."
            ) from exc
        raise


async def sheet(html: str) -> Rendered:
    """A one-page Letter sheet (816×1056 px) and its natural content height."""
    return await _render(html, sheet=True)


async def document(html: str) -> Rendered:
    """A paged Letter document with 0.6 in margins."""
    return await _render(html, sheet=False)
