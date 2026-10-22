from extract import content_hash, extract

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


def test_hash_ignores_whitespace_only_changes():
    assert content_hash("A  b\nc") == content_hash("A b c")
    assert content_hash("A b c") != content_hash("A b d")
