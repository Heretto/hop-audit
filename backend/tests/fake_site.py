"""A small help center served through respx: English at /, German at /de/."""

import respx

BASE = "https://help.x.com/"


def page(title: str, body: str = "", links: list[str] = (), extra_head: str = "") -> str:
    anchors = "".join(f'<a href="{href}">{href}</a> ' for href in links)
    words = " ".join(["Steady useful documentation words."] * 10)
    return (
        f"<html lang='en'><head><title>{title}</title>"
        f'<meta name="description" content="About {title}">{extra_head}</head>'
        f"<body><nav><a href='/nav-only'>Nav</a></nav><main><h1>{title}</h1>"
        f"<p>{body or words}</p>{anchors}</main></body></html>"
    )


def sitemap(entries: list[tuple[str, str | None]]) -> str:
    urls = "".join(
        f"<url><loc>{BASE}{path}</loc>{f'<lastmod>{lastmod}</lastmod>' if lastmod else ''}</url>"
        for path, lastmod in entries
    )
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


SITEMAP = [
    ("", "2026-10-01"),
    ("authoring/a", "2026-10-01"),
    ("authoring/b", "2026-10-01"),
    ("api/c", "2026-10-01"),
    ("de/", "2026-10-01"),
    ("de/authoring/a", "2026-10-01"),
    ("archive/old", "2026-10-01"),
]


def serve(mock: respx.MockRouter, entries=SITEMAP, robots: str = "User-agent: *\nAllow: /\n", **overrides) -> dict:
    """Routes for the fake site; ``overrides`` replace a path's response."""
    routes = {
        "robots.txt": mock.get(f"{BASE}robots.txt").respond(text=robots),
        "sitemap.xml": mock.get(f"{BASE}sitemap.xml").respond(text=sitemap(entries)),
    }
    pages = {
        "": page("Home", links=["/authoring/a", "/hidden/extra"]),
        "authoring/a": page("Topic A", links=["/authoring/b#step-2", "https://elsewhere.org/x"]),
        "authoring/b": page("Topic B"),
        "api/c": page("API C"),
        "de/": page("Startseite"),
        "de/authoring/a": page("Thema A"),
        "archive/old": page("Old"),
        "hidden/extra": page("Not in sitemap", links=["/hidden/deeper"]),
        "hidden/deeper": page("Deeper"),
        "nav-only": page("Linked from navigation only"),
    }
    for path, html in pages.items():
        routes[path] = mock.get(f"{BASE}{path}").respond(html=html)
    for path, response in overrides.items():
        route = mock.get(f"{BASE}{path}")  # respx returns the existing route for the same pattern
        sequence = isinstance(response, list) or callable(response)
        routes[path] = route.mock(side_effect=response) if sequence else route.mock(return_value=response)
        if not sequence:  # link checks HEAD what the crawl didn't read
            mock.head(f"{BASE}{path}").respond(response.status_code)
    routes["external"] = mock.head("https://elsewhere.org/x").respond(200)
    routes["head"] = mock.head(url__startswith=BASE).respond(200)
    return routes
