"""SEO and metadata checks on a page's extraction (the checklist in the SEO
Analyst's context file). Each check is ok, warn or error with a short
detail; anything not ok counts as one SEO issue."""

from collections import Counter
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

TITLE = (30, 60)
DESCRIPTION = (70, 160)


@dataclass
class Check:
    key: str
    label: str
    status: str  # ok | warn | error
    detail: str


def _length(value: str | None, bounds: tuple[int, int], what: str, duplicates: Counter) -> tuple[str, str]:
    if not value:
        return "error", "Missing"
    n = len(value)
    if duplicates[value] > 1:
        return "warn", f"Same {what} on {duplicates[value]} pages"
    low, high = bounds
    if n < low or n > high:
        return "warn", f"{n} chars (aim for {low}–{high})"
    return "ok", f"{n} chars"


def check(content: dict, url: str, titles: Counter, descriptions: Counter) -> list[Check]:
    """``titles`` and ``descriptions`` count each value across the run's pages."""
    checks = []
    status, detail = _length(content.get("title"), TITLE, "title", titles)
    checks.append(Check("title", "Title", status, detail))
    status, detail = _length(content.get("description"), DESCRIPTION, "description", descriptions)
    checks.append(Check("description", "Meta description", status, detail))

    canonical = content.get("canonical")
    if not canonical:
        checks.append(Check("canonical", "Canonical URL", "warn", "Missing"))
    elif urlsplit(canonical).hostname != urlsplit(url).hostname:
        checks.append(Check("canonical", "Canonical URL", "warn", f"Points to another host: {canonical}"))
    elif canonical.rstrip("/") != url.rstrip("/"):
        checks.append(Check("canonical", "Canonical URL", "ok", f"Points to {urlsplit(canonical).path}"))
    else:
        checks.append(Check("canonical", "Canonical URL", "ok", "OK"))

    headings = content.get("headings", [])
    h1 = sum(1 for level, _ in headings if level == 1)
    checks.append(Check("h1", "H1", "ok" if h1 == 1 else "error" if h1 == 0 else "warn", str(h1)))

    skips = [(a, b) for (a, _), (b, _) in zip(headings, headings[1:], strict=False) if b > a + 1]
    if skips:
        a, b = skips[0]
        more = f" (+{len(skips) - 1} more)" if len(skips) > 1 else ""
        checks.append(Check("heading_order", "Heading order", "warn", f"H{a} → H{b} skip{more}"))
    else:
        checks.append(Check("heading_order", "Heading order", "ok", "OK"))

    images = content.get("images", [])
    missing = sum(1 for img in images if img.get("alt") is None)
    checks.append(
        Check(
            "image_alt",
            "Images without alt",
            "error" if missing else "ok",
            f"{missing} of {len(images)}" if images else "No images",
        )
    )

    og = content.get("og", {})
    absent = [k for k in ("title", "description") if not og.get(k)]
    checks.append(
        Check(
            "open_graph", "Open Graph", "warn" if absent else "ok", f"No og:{', og:'.join(absent)}" if absent else "OK"
        )
    )

    noindex = "noindex" in (content.get("robots") or "")
    checks.append(Check("indexable", "Indexable", "error" if noindex else "ok", "noindex" if noindex else "Yes"))
    return checks


def as_json(checks: list[Check]) -> list[dict]:
    return [asdict(c) for c in checks]


def issues(checks: list[Check] | list[dict]) -> int:
    return sum(1 for c in checks if (c.status if isinstance(c, Check) else c["status"]) != "ok")
