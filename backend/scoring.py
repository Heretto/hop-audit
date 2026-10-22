"""Page, section and site scores, and a run's headline metrics.

A page starts at 100 and loses points for what the analyses found; the
dashboard footnote states the same rules. Pages the crawl couldn't read
(errors, non-200) aren't scored. Section and site scores are the mean of
their pages' scores.
"""

from statistics import mean

READABLE = 60  # Flesch target before a page loses points (the site's focus can ask for more)


def page_score(
    http_status: int | None,
    flesch: float | None,
    broken: int,
    redirects: int,
    anchors: int,
    seo: list[dict] | None,
) -> int | None:
    if http_status != 200:
        return None
    score = 100.0
    if flesch is not None and flesch < READABLE:
        score -= min(30, (READABLE - flesch) * 0.75)
    score -= min(30, broken * 8 + anchors * 3)
    score -= min(5, redirects)
    if seo:
        score -= min(30, sum(6 if c["status"] == "error" else 3 if c["status"] == "warn" else 0 for c in seo))
    return max(0, round(score))


def mean_of(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(mean(values), 1) if values else None


def run_metrics(pages: list, new_pages: int | None, links: dict[str, int]) -> dict:
    """Headline numbers for a run. ``pages`` are Page rows; ``links`` counts
    link outcomes (each link on each page)."""
    read = [p for p in pages if p.http_status == 200]
    flesch = [p.flesch for p in read if p.flesch is not None]
    score = mean_of(p.score for p in read)
    return {
        "score": round(score) if score is not None else None,
        "pages": len(read),
        "pages_failed": len(pages) - len(read),
        "new_pages": new_pages,
        "flesch": mean_of(flesch),
        "under_50": sum(1 for f in flesch if f < 50),
        "broken": links.get("broken", 0),
        "redirects": links.get("redirect", 0),
        "anchors": links.get("anchor", 0),
        "blocked_links": links.get("blocked", 0),
        "links": sum(links.values()),
        "seo_issues": sum(p.seo_issues or 0 for p in read),
    }
