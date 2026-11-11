"""What HOP Audit keeps of a page: its main text and the structure the
analyses need (headings, links, images, metadata). Raw HTML isn't stored.

Hidden and collapsed content (``<details>``, accordions) is in the served
HTML, so it is read like any other text. Pages a browser would have to
render with JavaScript come back nearly empty, with scripts and no headings;
``looks_like_shell`` flags them so the run can say so.

``follow`` holds every link on the page, navigation and footers included,
for the crawler to follow; ``links`` (main content only)
is what the link check reads. ``follow`` isn't stored.

``asks_sign_in`` flags a sign-in wall served as a normal page (HTTP 200):
little text with a password field, or wording such as "requires
authentication" or "please sign in". The crawler reports those, never reads
them.

``blocks`` keeps the main content's shape for people reading it on the page
screen: headings, paragraphs, list items, table rows, code, quotes, collapsed
sections, and where images and other media sat. The analyses read ``text``;
blocks aren't in the checksum, so keeping them changes no page's identity.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import urldefrag, urljoin

from bs4 import BeautifulSoup, Tag

DROP = ("script", "style", "noscript", "template", "svg", "iframe")
CHROME = ("nav", "header", "footer", "aside")  # dropped only when there's no <main>/<article>
SHELL_WORDS = 30
SIGN_IN_WORDS = 80  # a sign-in wall says little else
SIGN_IN = re.compile(
    r"requires? (authentication|(a )?(sign|log)[- ]?in)|please (sign|log) ?in|(sign|log) ?in to continue"
    r"|you (must|need to) (be )?(sign|log)(ged)? ?in",
    re.I,
)
NOT_FOLLOWED = ("javascript:", "mailto:", "tel:", "#")
BLOCKS = (
    "p",
    "div",
    "li",
    "dt",
    "dd",
    "pre",
    "blockquote",
    "section",
    "article",
    "summary",
    "details",
    "table",
    "tr",
    "td",
    "th",
    "figcaption",
    "br",
    "hr",
    "ul",
    "ol",
    "dl",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
)


@dataclass
class PageContent:
    title: str = ""
    description: str | None = None
    canonical: str | None = None
    robots: str = ""
    lang: str = ""
    og: dict[str, str] = field(default_factory=dict)
    alternates: list[dict[str, str]] = field(default_factory=list)  # [{language, url}]
    headings: list[list] = field(default_factory=list)  # [[level, text]]
    images: list[dict] = field(default_factory=list)  # [{src, alt}]; alt None when missing
    links: list[dict[str, str]] = field(default_factory=list)  # [{url, text}], main content only
    anchors: list[str] = field(default_factory=list)  # element ids and <a name>, for #fragment checks
    final_url: str | None = None  # set by the crawler when the page was reached through a redirect
    breadcrumb: list[str] = field(default_factory=list)
    text: str = ""
    word_count: int = 0
    looks_like_shell: bool = False
    asks_sign_in: bool = False
    source: str = ""  # "zendesk" for an article read through Zendesk's API; "" for a page
    blocks: list[dict] = field(default_factory=list)  # see _blocks
    follow: list[str] = field(default_factory=list)  # for the crawler; not stored

    def as_json(self) -> dict:
        stored = asdict(self)
        del stored["follow"]
        return stored


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# Everything the analyses read. A page whose checksum matches the last audit's
# keeps its readability and SEO results instead of being evaluated again.
CHECKSUM_FIELDS = (
    "title", "description", "canonical", "robots", "lang", "og", "alternates",
    "headings", "images", "links", "anchors", "breadcrumb", "text",
)  # fmt: skip


def checksum(content: dict) -> str:
    """SHA-256 of what the analyses read, whitespace-normalized, so markup
    churn (scripts, classes, layout) doesn't read as a change."""
    material = {k: content.get(k) for k in CHECKSUM_FIELDS}
    material["text"] = squash(material["text"] or "")
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _meta(soup: BeautifulSoup, **attrs) -> str | None:
    tag = soup.find("meta", attrs=attrs)
    return squash(tag.get("content", "")) if isinstance(tag, Tag) and tag.has_attr("content") else None


def _breadcrumb(soup: BeautifulSoup) -> list[str]:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type") == "BreadcrumbList":
                elements = sorted(item.get("itemListElement", []), key=lambda e: e.get("position", 0))
                names = [e.get("name") or (e.get("item") or {}).get("name") for e in elements]
                return [squash(n) for n in names if n]
    trail = soup.find(attrs={"aria-label": re.compile("breadcrumb", re.I)}) or soup.find(
        class_=re.compile("breadcrumb", re.I)
    )
    if isinstance(trail, Tag):
        items = trail.find_all("li") or trail.find_all("a")
        return [t for t in (squash(i.get_text(" ")) for i in items) if t]
    return []


def _main(soup: BeautifulSoup) -> Tag:
    main = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article")
    if isinstance(main, Tag):
        return main
    body = soup.body or soup
    for tag in body.find_all(CHROME):
        tag.decompose()
    return body


MEDIA = ("video", "audio", "embed", "object", "hop-frame")  # hop-frame: an iframe, before DROP removes it
LISTS = ("ul", "ol")
CELLS = ("td", "th")
MAX_BLOCKS = 2000  # a page longer than this is cut off on screen; the text is whole


def _src(tag: Tag, url: str) -> str:
    source = tag.get("src") or tag.get("data") or ""
    if not source and (child := tag.find("source", src=True)):
        source = child["src"]
    return urljoin(url, source.strip()) if source.strip() else ""


def _blocks(main: Tag, url: str) -> list[dict]:
    """The main content in reading order, one entry per block:
    ``{"t": "h1".."h6" | "p" | "li" | "term" | "summary" | "quote", "x": text}``
    (list items also carry ``d``, their depth, and ``n`` when numbered),
    ``{"t": "pre", "x": text}`` with its whitespace, ``{"t": "row", "cells": [...],
    "head": bool}``, ``{"t": "img", "src", "alt", "d"}`` (alt None when missing)
    and ``{"t": "media", "kind", "src", "title", "d"}``. Headings carry no depth."""
    out: list[dict] = []
    buf: list[str] = []
    ctx = {"t": "p", "d": 0}  # what the next run of inline text becomes

    def image(img: Tag) -> dict:
        alt = img.get("alt")
        src = urljoin(url, (img.get("src") or "").strip())
        return {"t": "img", "src": src, "alt": alt.strip() if alt is not None else None, "d": ctx.get("d", 0)}

    def flush():
        text = squash("".join(buf))
        buf.clear()
        if text:
            out.append({**ctx, "x": text})
            if ctx["t"] == "li":  # more text in the same item reads as its continuation
                ctx.update(t="p", d=ctx.get("d", 0))
                ctx.pop("n", None)

    def within(node: Tag, **c):
        nonlocal ctx
        flush()
        saved, ctx = ctx, {**c}
        walk(node)
        flush()
        ctx = saved

    def walk(node: Tag):
        for child in node.children:
            if len(out) >= MAX_BLOCKS:
                return
            if not isinstance(child, Tag):
                buf.append(str(child))
                continue
            name = child.name
            if re.fullmatch(r"h[1-6]", name):
                within(child, t=name)
            elif name == "img":
                flush()
                out.append(image(child))
            elif name in MEDIA:
                flush()
                kind = "iframe" if name == "hop-frame" else name
                title = child.get("title") or ""
                out.append({"t": "media", "kind": kind, "src": _src(child, url), "title": title, "d": ctx.get("d", 0)})
            elif name == "pre":
                flush()
                if text := child.get_text().strip("\n"):
                    out.append({"t": "pre", "x": text})
            elif name in LISTS:
                flush()
                depth = ctx.get("d", 0) + 1
                for i, li in enumerate(child.find_all("li", recursive=False), 1):
                    within(li, t="li", d=depth, **({"n": i} if name == "ol" else {}))
            elif name == "tr":
                flush()
                cells = child.find_all(CELLS, recursive=False)
                texts = [squash(c.get_text(" ")) for c in cells]
                if any(texts):
                    out.append({"t": "row", "cells": texts, "head": all(c.name == "th" for c in cells)})
                out.extend(image(img) for img in child.find_all("img"))
            elif name == "blockquote":
                within(child, t="quote", d=ctx.get("d", 0))
            elif name == "summary":
                within(child, t="summary", d=ctx.get("d", 0))
            elif name == "dt":
                within(child, t="term", d=ctx.get("d", 0))
            elif name == "dd":
                within(child, t="p", d=ctx.get("d", 0) + 1)
            elif name == "br":
                flush()
            elif name in BLOCKS:
                flush()
                walk(child)
                flush()
            else:  # inline: links, emphasis, code
                walk(child)

    walk(main)
    flush()
    return out


def extract(html: str, url: str) -> PageContent:
    soup = BeautifulSoup(html, "html.parser")
    page = PageContent(breadcrumb=_breadcrumb(soup))
    scripts = len(soup.find_all("script"))
    for frame in soup.find_all("iframe"):  # a marker where it sat; DROP removes the frame itself
        frame.insert_before(soup.new_tag("hop-frame", attrs={k: frame[k] for k in ("src", "title") if frame.get(k)}))
    for tag in soup.find_all(DROP):
        tag.decompose()

    head_title = soup.find("title")
    page.title = squash(head_title.get_text()) if head_title else ""
    page.description = _meta(soup, name="description")
    page.robots = (_meta(soup, name="robots") or "").lower()
    page.og = {k: v for k in ("title", "description", "image") if (v := _meta(soup, property=f"og:{k}"))}
    html_tag = soup.find("html")
    page.lang = html_tag.get("lang", "").strip() if isinstance(html_tag, Tag) else ""
    for link in soup.find_all("link", href=True):
        rel = [r.lower() for r in link.get("rel", [])]
        if "canonical" in rel and page.canonical is None:
            page.canonical = urljoin(url, link["href"].strip())
        elif "alternate" in rel and link.get("hreflang"):
            page.alternates.append({"language": link["hreflang"].strip(), "url": urljoin(url, link["href"].strip())})

    # Headings and images count across the page, as search engines see it.
    page.headings = [[int(h.name[1]), squash(h.get_text(" "))] for h in soup.find_all(re.compile(r"^h[1-6]$"))]
    page.images = [
        {"src": urljoin(url, img.get("src", "")), "alt": img.get("alt").strip() if img.has_attr("alt") else None}
        for img in soup.find_all("img")
    ]

    page.anchors = sorted(
        {t["id"] for t in soup.find_all(id=True)} | {a["name"] for a in soup.find_all("a", attrs={"name": True})}
    )
    # Every link on the page, before _main drops the chrome: navigation and tables of contents
    # often sit outside <main>, and a site without a sitemap is only found through them.
    hrefs = (a["href"].strip() for a in soup.find_all("a", href=True))
    page.follow = list(dict.fromkeys(urljoin(url, h) for h in hrefs if h and not h.startswith(NOT_FOLLOWED)))
    password = soup.find("input", attrs={"type": re.compile("^password$", re.I)}) is not None
    main = _main(soup)
    page.blocks = _blocks(main, url)
    for a in main.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:")):
            continue
        page.links.append({"url": urljoin(url, href), "text": squash(a.get_text(" "))})
    # Line breaks at block boundaries only, so inline markup doesn't split sentences.
    for block in main.find_all(BLOCKS):
        block.insert_after("\n")
        block.insert_before("\n")
    lines = (squash(line) for line in main.get_text().splitlines())
    page.text = "\n".join(line for line in lines if line)
    page.word_count = len(page.text.split())
    # Few words, scripts, and no headings; or no main text at all (a heading in the chrome isn't content).
    few_words = page.word_count < SHELL_WORDS and not page.headings
    page.looks_like_shell = scripts > 0 and (page.word_count == 0 or few_words)
    page.asks_sign_in = page.word_count < SIGN_IN_WORDS and (password or bool(SIGN_IN.search(page.text)))
    return page


def page_url(url: str) -> str:
    """A crawlable page URL: no fragment."""
    return urldefrag(url)[0]
