from extract import checksum, extract

HTML = """<html lang="de-DE"><head>
<title> Publish a  map </title>
<meta name="description" content="How to publish.">
<meta name="robots" content="NOINDEX">
<meta property="og:title" content="Publish">
<link rel="canonical" href="/en/publish">
<link rel="alternate" hreflang="fr" href="/fr/publish">
<script type="application/ld+json">{"@type": "BreadcrumbList", "itemListElement": [
  {"position": 2, "name": "Publishing"}, {"position": 1, "name": "Home"}]}</script>
<style>.x{}</style>
</head><body>
<nav><a href="/nav">Nav link</a></nav>
<main>
  <h1>Publish a map</h1>
  <p>First you <b>open</b> the map.</p>
  <details><summary>More</summary><p>Hidden but served text.</p></details>
  <img src="/a.png" alt=" Diagram "><img src="b.png">
  <a href="/en/next#part">Next</a> <a href="mailto:x@y.z">Mail</a> <a href="javascript:void(0)">JS</a>
  <h3 id="limits">Skipped level</h3><a name="old-anchor"></a>
  <script>var tracking = 1;</script>
</main>
<footer>Footer text</footer>
</body></html>"""


def test_extracts_main_content_and_metadata():
    p = extract(HTML, "https://help.x.com/de/publish")
    assert p.title == "Publish a map"
    assert p.description == "How to publish."
    assert p.robots == "noindex"
    assert p.canonical == "https://help.x.com/en/publish"
    assert p.alternates == [{"language": "fr", "url": "https://help.x.com/fr/publish"}]
    assert p.og == {"title": "Publish"}
    assert p.lang == "de-DE"
    assert p.breadcrumb == ["Home", "Publishing"]
    assert p.headings == [[1, "Publish a map"], [3, "Skipped level"]]
    assert p.images == [
        {"src": "https://help.x.com/a.png", "alt": "Diagram"},
        {"src": "https://help.x.com/de/b.png", "alt": None},
    ]
    assert p.links == [{"url": "https://help.x.com/en/next#part", "text": "Next"}]
    assert "Hidden but served text." in p.text  # collapsed sections are read
    assert "Nav link" not in p.text and "Footer text" not in p.text and "tracking" not in p.text
    assert p.text.splitlines()[:2] == ["Publish a map", "First you open the map."]
    assert p.word_count == len(p.text.split())
    assert not p.looks_like_shell
    assert p.anchors == ["limits", "old-anchor"]


def test_falls_back_to_body_without_chrome():
    p = extract("<body><header>Top</header><p>Body words here.</p><aside>Side</aside></body>", "https://a.com/")
    assert p.text == "Body words here."
    assert p.title == "" and p.description is None and p.canonical is None


def test_aria_breadcrumb():
    html = '<body><ol aria-label="Breadcrumb"><li>Home</li><li> API </li></ol><main>x</main></body>'
    assert extract(html, "https://a.com/").breadcrumb == ["Home", "API"]


def test_short_real_pages_are_not_shells():
    html = "<html><body><main><h1>Glossary: map</h1><p>A map orders topics.</p></main><script></script></body></html>"
    assert not extract(html, "https://a.com/").looks_like_shell


def test_flags_javascript_shells():
    p = extract(
        '<html><body><div id="app">Loading</div><script src="/app.js"></script></body></html>', "https://a.com/"
    )
    assert p.looks_like_shell and p.word_count == 1


def test_checksum_covers_what_the_analyses_read():
    page = extract(HTML, "https://help.x.com/de/publish").as_json()
    same = checksum(page)
    assert checksum({**page, "text": page["text"].replace(" ", "  ")}) == same  # whitespace only
    assert checksum({**page, "final_url": "https://x"}) == same  # not something the analyses read
    for field, value in [
        ("text", page["text"] + " More."),
        ("title", "Another title"),
        ("description", None),
        ("images", []),
        ("headings", [[1, "Publish a map"]]),
        ("links", []),
    ]:
        assert checksum({**page, field: value}) != same, field
    assert len(same) == 64


STRUCTURED = """<html><body><nav>Menu</nav><main>
<h1>Title</h1><p>Intro <b>bold</b> text.<img src="/a.png" alt=" Diagram "> after</p>
<ul><li>One<ul><li>Nested</li></ul></li><li>Two <img src="b.png"></li></ul>
<ol><li>First</li><li>Second</li></ol>
<pre>code
  indented</pre>
<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>
<details><summary>More</summary><p>Hidden</p></details><blockquote>Quote</blockquote>
<iframe src="https://video.example/embed/x" title="Demo"></iframe><video><source src="v.mp4"></video>
<dl><dt>Term</dt><dd>Def</dd></dl>
</main></body></html>"""


def test_blocks_keep_the_main_content_shape_and_where_media_sat():
    p = extract(STRUCTURED, "https://h.x/a/")
    assert p.blocks == [
        {"t": "h1", "x": "Title"},
        {"t": "p", "d": 0, "x": "Intro bold text."},
        {"t": "img", "src": "https://h.x/a.png", "alt": "Diagram", "d": 0},
        {"t": "p", "d": 0, "x": "after"},
        {"t": "li", "d": 1, "x": "One"},
        {"t": "li", "d": 2, "x": "Nested"},
        {"t": "li", "d": 1, "x": "Two"},
        {"t": "img", "src": "https://h.x/a/b.png", "alt": None, "d": 1},
        {"t": "li", "d": 1, "n": 1, "x": "First"},
        {"t": "li", "d": 1, "n": 2, "x": "Second"},
        {"t": "pre", "x": "code\n  indented"},
        {"t": "row", "cells": ["A", "B"], "head": True},
        {"t": "row", "cells": ["1", "2"], "head": False},
        {"t": "summary", "d": 0, "x": "More"},
        {"t": "p", "d": 0, "x": "Hidden"},
        {"t": "quote", "d": 0, "x": "Quote"},
        {"t": "media", "kind": "iframe", "src": "https://video.example/embed/x", "title": "Demo", "d": 0},
        {"t": "media", "kind": "video", "src": "https://h.x/a/v.mp4", "title": "", "d": 0},
        {"t": "term", "d": 0, "x": "Term"},
        {"t": "p", "d": 1, "x": "Def"},
    ]
    assert "Menu" not in str(p.blocks)  # navigation stays out, as in the text


def test_blocks_leave_the_text_and_checksum_as_they_were():
    p = extract(STRUCTURED, "https://h.x/a/")
    assert p.text.startswith("Title\nIntro bold text. after\nOne\nNested\nTwo\nFirst")
    without = {**p.as_json(), "blocks": []}
    assert checksum(p.as_json()) == checksum(without)
    assert not any("hop-frame" in t for t in p.text.split())  # the iframe marker adds no text


def test_blocks_stop_at_the_limit(monkeypatch):
    import extract as ex

    monkeypatch.setattr(ex, "MAX_BLOCKS", 3)
    p = extract("<main>" + "".join(f"<p>Para {i}</p>" for i in range(10)) + "</main>", "https://h.x/")
    assert len(p.blocks) <= 4 and p.word_count == 20  # the text is whole
