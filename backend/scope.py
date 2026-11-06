"""Which pages a run covers: help-center assignment, sections, include and
exclude rules, and the run's scope (whole site, sections, changed, listed).

Paths are taken relative to each help center's root, so /de/authoring/x and
/authoring/x are both in section /authoring and match the same patterns.
"""

import re
from collections import Counter
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


# ISO 639-1 language codes: the first part of a locale segment (en, de-DE, zh_Hans, pt-br).
LANGUAGES = frozenset(
    "aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy da de "
    "dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id "
    "ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu "
    "lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu "
    "rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr "
    "ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu".split()
)
_LOCALE = re.compile(r"([a-z]{2})(?:[-_](?:[a-z]{2}|[0-9]{3}|[a-z]{4}))?", re.I)
LANGUAGE_SHARE = 0.8  # of a help center's pages under language segments before they count as such


def is_language(segment: str) -> bool:
    match = _LOCALE.fullmatch(segment)
    return bool(match) and match.group(1).lower() in LANGUAGES


@dataclass(frozen=True)
class Level:
    """A leading path segment that isn't a section: one of these values, or
    with ``languages`` any language code (pages found later may add one)."""

    values: frozenset[str]
    languages: bool = False

    def skips(self, segment: str) -> bool:
        return segment in self.values or (self.languages and is_language(segment))


Prefix = tuple[Level, ...]


def detect_prefix(paths: list[str], depth: int = 2) -> Prefix:
    """The leading segments to look past when grouping pages into sections.

    A segment level is skipped when most pages sit under language codes
    (/en/guide/x: Heretto portals and many help centers), or when every page
    shares one base folder that holds several folders (/docs/a/x, /docs/b/y).
    Otherwise the first segment is the section, as on most sites.
    """
    rows = [p.strip("/").split("/") for p in paths]
    levels: list[Level] = []
    for _ in range(depth):
        rows = [r for r in rows if len(r) > 1]  # a landing page (/en/) says nothing about what's below
        if not rows:
            break
        firsts = Counter(r[0] for r in rows)
        spoken = {s for s in firsts if is_language(s)}
        if sum(firsts[s] for s in spoken) >= LANGUAGE_SHARE * len(rows):
            level = Level(frozenset(spoken), languages=True)
        elif len(firsts) == 1 and len({r[1] for r in rows if len(r) > 2}) > 1:  # folders below, not pages
            level = Level(frozenset(firsts))
        else:
            break
        levels.append(level)
        rows = [r[1:] for r in rows if level.skips(r[0])]
    return tuple(levels)


def describe_prefix(prefix: Prefix) -> str:
    """ "a language (de, en)", "/docs" and "a language (en)", for the run log."""
    parts = [
        f"a language ({', '.join(sorted(lv.values))})" if lv.languages else f"/{next(iter(lv.values))}" for lv in prefix
    ]
    return " and ".join(parts)


def path_section(relative: str, prefix: Prefix = ()) -> str:
    """/authoring for /authoring/x; with a language prefix, /authoring for /en/authoring/x too."""
    parts = [p for p in relative.strip("/").split("/") if p]
    for level in prefix:
        if parts and level.skips(parts[0]):
            parts = parts[1:]
    return f"/{parts[0]}" if parts else "/"


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
