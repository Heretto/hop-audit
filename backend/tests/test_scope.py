import uuid

import pytest

from scope import (
    Root,
    allowed,
    breadcrumb_section,
    glob_regex,
    help_center_for,
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
