"""What HOP Audit keeps of a page: its main text and the structure the
analyses need (headings, links, images, metadata). Raw HTML isn't stored.

Hidden and collapsed content (``<details>``, accordions) is in the served
HTML, so it is read like any other text. Pages a browser would have to
render with JavaScript come back nearly empty, with scripts and no headings;
``looks_like_shell`` flags them so the run can say so.
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

    def as_json(self) -> dict:
        return asdict(self)


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


def extract(html: str, url: str) -> PageContent:
    soup = BeautifulSoup(html, "html.parser")
    page = PageContent(breadcrumb=_breadcrumb(soup))
    scripts = len(soup.find_all("script"))
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
    main = _main(soup)
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
    page.looks_like_shell = page.word_count < SHELL_WORDS and scripts > 0 and not page.headings
    return page


def page_url(url: str) -> str:
    """A crawlable page URL: no fragment."""
    return urldefrag(url)[0]
