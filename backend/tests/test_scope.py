import uuid

import pytest

from scope import (
    Level,
    Root,
    allowed,
    breadcrumb_section,
    describe_prefix,
    detect_prefix,
    glob_regex,
    help_center_for,
    is_language,
    listed_urls,
    path_section,
    relative_path,
    sitemap_section,
)

EN = Root(uuid.uuid4(), "US English", "https://help.x.com/", "en", True)
DE = Root(uuid.uuid4(), "Deutsch", "https://help.x.com/de", "de", False)
CA = Root(uuid.uuid4(), "Canada", "https://help.x.ca/fr/", "fr-CA", False)
ROOTS = [EN, DE, CA]


@pytest.mark.parametrize(
    "url, root",
    [
        ("https://help.x.com/authoring/a", EN),
        ("https://help.x.com/de/authoring/a", DE),
        ("https://help.x.com/de", DE),
        ("http://HELP.x.com/de/", DE),
        ("https://help.x.com/designer", EN),  # /de is a folder, not a prefix of /designer
        ("https://help.x.ca/fr/a", CA),
        ("https://help.x.ca/en/a", None),
        ("https://other.com/", None),
    ],
)
def test_help_center_for(url, root):
    assert help_center_for(url, ROOTS) == root


def test_relative_paths_and_sections():
    assert relative_path("https://help.x.com/de/authoring/x", DE) == "/authoring/x"
    assert relative_path("https://help.x.com/de/", DE) == "/"
    assert path_section("/authoring/x") == "/authoring"
    assert path_section("/") == "/"
    assert sitemap_section("https://a.com/sitemaps/sitemap-api.xml.gz") == "sitemap-api"
    assert breadcrumb_section(["Home", "Authoring", "Reuse"], "/authoring") == "Authoring"
    assert breadcrumb_section([], "/authoring") == "/authoring"


def test_is_language():
    for segment in ("en", "DE", "pt-br", "en_US", "zh-Hans", "es-419"):
        assert is_language(segment), segment
    for segment in ("api", "ui", "js", "e", "english", "en-", "guide", "en-us-x"):
        assert not is_language(segment), segment


HERETTO = ["/en/", "/en/ccms/a", "/en/ccms/b", "/en/portal/c", "/de/ccms/a", "/de/", "/"]


def test_detect_prefix_languages():
    prefix = detect_prefix(HERETTO)
    assert prefix == (Level(frozenset({"en", "de"}), languages=True),)
    assert path_section("/en/ccms/a", prefix) == "/ccms"
    assert path_section("/de/ccms/a", prefix) == "/ccms"
    assert path_section("/fr-ca/portal/x", prefix) == "/portal"  # a language found later by following links
    assert path_section("/en/", prefix) == "/"  # a language's landing page is the home section
    assert path_section("/search", prefix) == "/search"
    assert describe_prefix(prefix) == "a language (de, en)"


def test_detect_prefix_single_language_and_shared_base():
    assert detect_prefix(["/en/a/1", "/en/b/1"]) == (Level(frozenset({"en"}), languages=True),)
    docs = detect_prefix(["/docs/", "/docs/a/1", "/docs/b/1", "/docs/b/2"])
    assert docs == (Level(frozenset({"docs"})),)
    assert path_section("/docs/b/2", docs) == "/b"
    both = detect_prefix(["/docs/en/a/1", "/docs/en/b/1", "/docs/de/a/1"])
    assert describe_prefix(both) == "/docs and a language (de, en)"
    assert path_section("/docs/de/a/1", both) == "/a"


def test_detect_prefix_leaves_ordinary_sites_alone():
    assert detect_prefix([]) == ()
    assert detect_prefix(["/authoring/a", "/authoring/b", "/api/c", "/"]) == ()
    # Two-letter sections that look like languages, but too few of them.
    assert detect_prefix(["/it/setup", "/guide/a", "/guide/b", "/api/c", "/faq/d"]) == ()
    # Everything in one folder with nothing below it to group by: keep the folder.
    assert detect_prefix(["/guide/a", "/guide/b"]) == ()
    assert path_section("/authoring/x", ()) == "/authoring"


@pytest.mark.parametrize(
    "pattern, path, match",
    [
        ("/docs/**", "/docs/a/b", True),
        ("/docs/**", "/docs", False),
        ("/docs/**", "/api/docs/a", False),
        ("/docs/*", "/docs/a", True),
        ("/docs/*", "/docs/a/b", False),
        ("/**/print/**", "/a/b/print/c", True),
        ("/**/print/**", "/print/c", True),
        ("*.pdf", "/files/guide.pdf", True),
        ("*.pdf", "/files/guide.pdf.html", False),
        ("/a?c", "/abc", True),
        ("/a.c", "/abc", False),
    ],
)
def test_globs(pattern, path, match):
    assert bool(glob_regex(pattern).match(path)) is match


def test_allowed():
    assert allowed("/x", [], [])
    assert allowed("/docs/a", ["/docs/**", "/api/**"], ["/docs/archive/**"])
    assert not allowed("/docs/archive/a", ["/docs/**"], ["/docs/archive/**"])
    assert not allowed("/blog/a", ["/docs/**"], [])


def test_listed_urls():
    lines = ["/authoring/reuse", "api/v2", "https://help.x.ca/fr/a", "", "/authoring/reuse"]
    assert listed_urls(lines, EN) == [
        "https://help.x.com/authoring/reuse",
        "https://help.x.com/api/v2",
        "https://help.x.ca/fr/a",
    ]
