from collections import Counter

from seo import as_json, check, issues

URL = "https://help.x.com/publish"
GOOD = {
    "title": "Publish a map to Deploy | Heretto Help",
    "description": "Publish a map to Deploy: choose an output preset, start the job and follow its progress to done.",
    "canonical": URL,
    "headings": [[1, "Publish"], [2, "Steps"], [3, "Options"], [2, "Next"]],
    "images": [{"src": "a.png", "alt": "Dialog"}, {"src": "b.png", "alt": ""}],
    "og": {"title": "Publish", "description": "How to publish"},
    "robots": "",
}


def run(content, titles=None, descriptions=None):
    return {c.key: (c.status, c.detail) for c in check(content, URL, titles or Counter(), descriptions or Counter())}


def test_a_good_page_passes_everything():
    result = check(GOOD, URL, Counter(), Counter())
    assert issues(result) == 0
    assert as_json(result)[0] == {"key": "title", "label": "Title", "status": "ok", "detail": "38 chars"}


def test_problems():
    page = {
        **GOOD,
        "title": "Reuse content with conrefs | Authoring | Heretto Help Center | Heretto CCMS",
        "description": None,
        "canonical": "https://other.com/x",
        "headings": [[2, "No h1"], [4, "Jump"]],
        "images": [{"src": "a.png", "alt": None}, {"src": "b.png", "alt": "x"}],
        "og": {"title": "x"},
        "robots": "noindex, follow",
    }
    r = run(page)
    assert r["title"] == ("warn", "75 chars (aim for 30–60)")
    assert r["description"] == ("error", "Missing")
    assert r["canonical"][0] == "warn" and "another host" in r["canonical"][1]
    assert r["h1"] == ("error", "0")
    assert r["heading_order"] == ("warn", "H2 → H4 skip")
    assert r["image_alt"] == ("error", "1 of 2")
    assert r["open_graph"] == ("warn", "No og:description")
    assert r["indexable"] == ("error", "noindex")
    assert issues(as_json(check(page, URL, Counter(), Counter()))) == 8


def test_duplicates_and_edge_cases():
    r = run(GOOD, titles=Counter({GOOD["title"]: 3}))
    assert r["title"] == ("warn", "Same title on 3 pages")
    r = run({**GOOD, "headings": [[1, "a"], [1, "b"]], "images": [], "canonical": None})
    assert r["h1"] == ("warn", "2") and r["image_alt"] == ("ok", "No images") and r["canonical"] == ("warn", "Missing")
    assert run({**GOOD, "canonical": "https://help.x.com/en/publish"})["canonical"] == ("ok", "Points to /en/publish")
