"""A small Zendesk help center's Help Center API, served through respx."""

import respx

ZD = "https://support.z.com"
API = f"{ZD}/api/v2/help_center"

SECTIONS = [{"id": 11, "name": "Getting started", "category_id": 1}, {"id": 12, "name": "Billing", "category_id": 2}]
CATEGORIES = [{"id": 1, "name": "Basics"}, {"id": 2, "name": "Accounts"}]


def article(i: int, section: int = 11, locale: str = "en-us", draft: bool = False, edited="2026-10-01T10:00:00Z"):
    words = " ".join(["Clear steady documentation words for the reader."] * 6)
    return {
        "id": i,
        "title": f"Article {i}",
        "body": f"<p>{words}</p><h2>Steps</h2><ol><li>Open it.</li></ol><a href='{ZD}/hc/{locale}/articles/2'>Next</a>",
        "html_url": f"{ZD}/hc/{locale}/articles/{i}-article-{i}",
        "locale": locale,
        "section_id": section,
        "draft": draft,
        "edited_at": edited,
    }


def serve(mock: respx.MockRouter, articles=None, locales=("en-us", "de"), robots="User-agent: *\nAllow: /\n"):
    """The API; articles come two to a page, to exercise next_page."""
    articles = articles if articles is not None else [article(1), article(2, 12), article(3, draft=True)]
    mock.get(f"{ZD}/robots.txt").respond(text=robots)
    mock.get(f"{API}/locales.json").respond(json={"locales": list(locales), "default_locale": locales[0]})
    for locale in locales:
        mine = [a for a in articles if a["locale"] == locale]
        base = f"{API}/{locale}"
        mock.get(f"{base}/sections.json", params={"per_page": "100"}).respond(json={"sections": SECTIONS})
        mock.get(f"{base}/categories.json", params={"per_page": "100"}).respond(json={"categories": CATEGORIES})
        counted = {"count": len(mine), "articles": mine[:1]}
        mock.get(f"{base}/articles.json", params={"per_page": "1"}).respond(json=counted)
        pages = [mine[i : i + 2] for i in range(0, len(mine), 2)] or [[]]
        # Later pages first: respx matches params as a subset, so page 1's route would match them all.
        for n, chunk in reversed(list(enumerate(pages, 1))):
            more = f"{base}/articles.json?page={n + 1}&per_page=100" if n < len(pages) else None
            params = {"per_page": "100"} if n == 1 else {"page": str(n), "per_page": "100"}
            mock.get(f"{base}/articles.json", params=params).respond(
                json={"articles": chunk, "next_page": more, "count": len(mine)}
            )
    return mock
