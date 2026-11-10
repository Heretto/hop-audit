"""Chromium rendering. Runs only where Chromium is installed (the Docker image);
the crawler's use of it is tested with a fake in test_crawler.py."""

import pytest

import render

SHELL = b"""<html><body><div id="app"></div><img src="/big.png">
<script>document.getElementById('app').innerHTML = '<main><h1>Built by script</h1><p>' +
  navigator.userAgent + '</p></main>';</script></body></html>"""


@pytest.fixture
async def renderer():
    try:
        r = await render.start(2)
    except render.RenderUnavailable as exc:
        pytest.skip(str(exc))
    yield r
    await r.close()


async def test_renders_the_fetched_page_with_its_scripts(renderer):
    html = await renderer.html("https://help.x.com/api/c", SHELL, "text/html; charset=utf-8")
    assert "<h1>Built by script</h1>" in html
    assert "HOP-Audit/0.1" in html  # the same honest user agent as the crawler


async def test_start_without_chromium_says_how_to_install_it(monkeypatch):
    from playwright.async_api import Error as PlaywrightError

    class Chromium:
        async def launch(self):
            raise PlaywrightError("Executable doesn't exist at /ms-playwright/chromium")

    class Playwright:
        chromium = Chromium()
        stopped = False

        async def stop(self):
            Playwright.stopped = True

    class Starter:
        async def start(self):
            return Playwright()

    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: Starter())
    with pytest.raises(render.RenderUnavailable, match="playwright install --with-deps chromium"):
        await render.start()
    assert Playwright.stopped
