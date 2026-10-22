from types import SimpleNamespace

from scoring import mean_of, page_score, run_metrics

ERR = {"status": "error"}
WARN = {"status": "warn"}
OK = {"status": "ok"}


def test_page_score():
    assert page_score(200, 70, 0, 0, 0, [OK]) == 100
    assert page_score(200, 44.2, 2, 1, 1, [WARN, ERR, WARN, OK]) == 100 - 12 - 19 - 1 - 12  # 56
    assert page_score(200, -40, 10, 10, 10, [ERR] * 10) == 100 - 30 - 30 - 5 - 30
    assert page_score(200, None, 0, 0, 0, None) == 100  # nothing measured, nothing lost
    assert page_score(404, 70, 0, 0, 0, []) is None


def test_run_metrics():
    def page(status, flesch, score, seo):
        return SimpleNamespace(http_status=status, flesch=flesch, score=score, seo_issues=seo)

    pages = [page(200, 62.0, 90, 1), page(200, 41.0, 60, 3), page(200, None, 81, 0), page(404, None, None, None)]
    m = run_metrics(pages, 2, {"ok": 10, "broken": 2, "redirect": 3, "anchor": 1})
    assert m == {
        "score": 77,
        "pages": 3,
        "pages_failed": 1,
        "new_pages": 2,
        "flesch": 51.5,
        "under_50": 1,
        "broken": 2,
        "redirects": 3,
        "anchors": 1,
        "blocked_links": 0,
        "links": 16,
        "seo_issues": 4,
    }
    assert mean_of([None]) is None
