"""Which pages a run covers: help-center assignment, sections, include and
exclude rules, and the run's scope (whole site, sections, changed, listed).

Paths are taken relative to each help center's root, so /de/authoring/x and
/authoring/x are both in section /authoring and match the same patterns.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urljoin, urlsplit
from uuid import UUID

ScopeMode = str  # site | sections | changed | pages


@dataclass(frozen=True)
class Root:
    """A help center as the crawler sees it."""

    id: UUID
    name: str
    url: str
    language: str
    is_primary: bool

    @property
    def key(self) -> str:
        return _key(self.url if self.url.endswith("/") else self.url + "/")


def _key(url: str) -> str:
    """Host and path, scheme-insensitive: http and https are the same page here."""
    parts = urlsplit(url)
    return f"{(parts.hostname or '').lower()}{parts.path or '/'}"


def help_center_for(url: str, roots: list[Root]) -> Root | None:
    """The help center whose root is the longest prefix of the URL."""
    key = _key(url)
    matches = [r for r in roots if key.startswith(r.key) or key + "/" == r.key]
    return max(matches, key=lambda r: len(r.key), default=None)


def relative_path(url: str, root: Root) -> str:
    """/authoring/x for https://help.x.com/de/authoring/x under the /de/ root."""
    rest = _key(url)[len(root.key) :]
    return "/" + rest.lstrip("/")


def path_section(relative: str) -> str:
    segment = relative.strip("/").split("/", 1)[0]
    return f"/{segment}" if segment else "/"


def sitemap_section(sitemap_url: str) -> str:
    """sitemap-api.xml -> sitemap-api: one section per sitemap file."""
    name = urlsplit(sitemap_url).path.rsplit("/", 1)[-1]
    return re.sub(r"\.xml(\.gz)?$", "", name) or "sitemap"


def breadcrumb_section(crumbs: list[str], fallback: str) -> str:
    """The first crumb below the home crumb; the path section until a page is read."""
    crumbs = [c for c in crumbs if c.lower() not in ("home", "help center", "docs", "documentation")]
    return crumbs[0] if crumbs else fallback


@lru_cache(maxsize=512)
def glob_regex(pattern: str) -> re.Pattern:
    """Glob over relative paths: ** crosses folders, * and ? don't. A pattern
    without a leading slash matches at any depth (*.pdf, print/**)."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    prefix = "" if pattern.startswith("/") else "(?:.*/)?"
    return re.compile(f"^{prefix}{out}$")


def allowed(relative: str, include: list[str], exclude: list[str]) -> bool:
    if include and not any(glob_regex(p).match(relative) for p in include):
        return False
    return not any(glob_regex(p).match(relative) for p in exclude)


def listed_urls(lines: list[str], primary: Root) -> list[str]:
    """Listed pages: full URLs as given, paths under the primary help center."""
    base = primary.url if primary.url.endswith("/") else primary.url + "/"
    urls = []
    for line in (raw.strip() for raw in lines):
        if not line:
            continue
        urls.append(line if urlsplit(line).scheme in ("http", "https") else urljoin(base, line.lstrip("/")))
    return list(dict.fromkeys(urls))
