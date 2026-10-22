"""Sites and help centers: CRUD, validation, organization scoping."""

import uuid

import pytest

from catalog import CATEGORY_CODES
from models import HelpCenter
from tests.conftest import make_user

URL = "/api/v1/sites"


def payload(**overrides) -> dict:
    body = {
        "name": "Heretto Help Center",
        "start_url": "https://help.heretto.com/",
        "description": "Public help site",
        "help_centers": [
            {"name": "US English", "url": "https://help.heretto.com/", "language": "en", "is_primary": True},
            {"name": "Deutsch", "url": "https://help.heretto.com/de/", "language": "de"},
        ],
    }
    return body | overrides


def create(client, user, **overrides) -> dict:
    r = client.post(URL, json=payload(**overrides), headers=user["headers"])
    assert r.status_code == 201, r.text
    return r.json()


def test_requires_auth(client):
    assert client.get(URL).status_code == 401
    assert client.post(URL, json=payload()).status_code == 401


def test_create_applies_defaults(client, user):
    site = create(client, user)
    assert site["purpose"] == "own"
    assert site["analyses"] == ["readability", "links", "seo", "content_integrity", "summary"]
    assert site["integrity_categories"] == list(CATEGORY_CODES)
    assert site["crawl"]["max_pages"] == 2000 and site["crawl"]["respect_robots"] is True
    assert site["schedule"] == {"frequency": "manual", "day": 1, "time": "07:00", "timezone": "UTC"}
    assert [hc["name"] for hc in site["help_centers"]] == ["US English", "Deutsch"]


def test_list_and_read(client, user):
    a = create(client, user, name="B site")
    create(client, user, name="A site", start_url="https://a.example.com/")
    listed = client.get(URL, headers=user["headers"]).json()
    assert [s["name"] for s in listed] == ["A site", "B site"]
    assert listed[1]["help_centers"][0]["language"] == "en"
    assert client.get(f"{URL}/{a['id']}", headers=user["headers"]).json()["name"] == "B site"


def test_update_keeps_help_center_ids(client, user):
    site = create(client, user)
    us, de = site["help_centers"]
    body = payload(
        name="Renamed",
        focus="Flag Heretto Publisher.",
        help_centers=[
            us,
            {**de, "name": "German"},
            {"name": "日本語", "url": "https://help.heretto.com/ja/", "language": "ja"},
        ],
    )
    r = client.put(f"{URL}/{site['id']}", json=body, headers=user["headers"])
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["name"] == "Renamed" and updated["focus"] == "Flag Heretto Publisher."
    assert [hc["id"] for hc in updated["help_centers"][:2]] == [us["id"], de["id"]]
    assert updated["help_centers"][1]["name"] == "German"
    assert updated["help_centers"][2]["language"] == "ja"


def test_update_drops_removed_help_centers(client, user, db):
    site = create(client, user)
    us = site["help_centers"][0]
    r = client.put(f"{URL}/{site['id']}", json=payload(help_centers=[us]), headers=user["headers"])
    assert len(r.json()["help_centers"]) == 1
    assert db.query(HelpCenter).filter(HelpCenter.site_id == uuid.UUID(site["id"])).count() == 1


def test_delete_cascades(client, user, db):
    site = create(client, user)
    r = client.delete(f"{URL}/{site['id']}", headers=user["headers"])
    assert r.status_code == 204
    assert client.get(f"{URL}/{site['id']}", headers=user["headers"]).status_code == 404
    assert db.query(HelpCenter).filter(HelpCenter.site_id == uuid.UUID(site["id"])).count() == 0


def test_other_organizations_cannot_see_or_change(client, user):
    site = create(client, user)
    other = make_user(client)
    assert client.get(URL, headers=other["headers"]).json() == []
    for method in ("get", "put", "delete"):
        kwargs = {"json": payload()} if method == "put" else {}
        r = getattr(client, method)(f"{URL}/{site['id']}", headers=other["headers"], **kwargs)
        assert r.status_code == 404, method


def test_unknown_site_is_404(client, user):
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=user["headers"]).status_code == 404


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"name": "  "}, "required"),
        ({"start_url": "help.heretto.com"}, "http(s) URL"),
        ({"start_url": "ftp://help.heretto.com"}, "http(s) URL"),
        ({"help_centers": []}, "at least 1"),
        (
            {"help_centers": [{"name": "A", "url": "https://a.com", "language": "en"}]},
            "exactly one help center must be primary",
        ),
        (
            {
                "help_centers": [
                    {"name": "A", "url": "https://a.com", "language": "en", "is_primary": True},
                    {"name": "B", "url": "https://a.com/", "language": "de"},
                ]
            },
            "own URL",
        ),
        (
            {"help_centers": [{"name": "A", "url": "https://a.com", "language": "English", "is_primary": True}]},
            "language tag",
        ),
        ({"analyses": ["readability", "spelling"]}, "unknown analyses: spelling"),
        ({"integrity_categories": ["C", "Z"]}, "unknown categories: Z"),
        ({"integrity_categories": []}, "at least one category"),
        ({"purpose": "partner"}, "own"),
        ({"crawl": {"max_pages": 0}}, "greater than or equal to 1"),
        ({"crawl": {"concurrency": 99}}, "less than or equal to 16"),
        ({"crawl": {"sitemap_url": "sitemap.xml"}}, "http(s) URL"),
        ({"schedule": {"frequency": "weekly", "day": 9}}, "0 (Monday) to 6"),
        ({"schedule": {"frequency": "monthly", "day": 0}}, "1 to 28"),
        ({"schedule": {"time": "7am"}}, "HH:MM"),
        ({"schedule": {"timezone": "Mars/Base"}}, "unknown time zone"),
        ({"agent_assignments": {"spelling": None}}, "unknown analyses"),
    ],
)
def test_validation(client, user, overrides, message):
    r = client.post(URL, json=payload(**overrides), headers=user["headers"])
    assert r.status_code == 422
    assert message in r.text, r.text


def test_normalizes_input(client, user):
    site = create(
        client,
        user,
        name="  Docs  ",
        help_centers=[{"name": "FR", "url": " https://a.com/fr ", "language": "fr_CA", "is_primary": True}],
        crawl={"include": ["/docs/**", "  ", ""], "exclude": [" *.pdf "]},
        analyses=["summary", "links"],
    )
    assert site["name"] == "Docs"
    assert site["help_centers"][0] == {**site["help_centers"][0], "url": "https://a.com/fr", "language": "fr-CA"}
    assert site["crawl"]["include"] == ["/docs/**"] and site["crawl"]["exclude"] == ["*.pdf"]
    assert site["analyses"] == ["links", "summary"]


def test_content_integrity_off_allows_no_categories(client, user):
    site = create(client, user, analyses=["links"], integrity_categories=[])
    assert site["integrity_categories"] == []


def test_agent_assignments(client, user):
    agents = client.post("/api/v1/setup", headers=user["headers"]).json()["seeded_agents"]
    site = create(client, user, agent_assignments={"seo": agents["seo"], "links": None})
    assert site["agent_assignments"] == {"seo": agents["seo"], "links": None}

    other = make_user(client)
    foreign = client.post("/api/v1/setup", headers=other["headers"]).json()["seeded_agents"]
    r = client.post(URL, json=payload(agent_assignments={"seo": foreign["seo"]}), headers=user["headers"])
    assert r.status_code == 422 and "Unknown agent" in r.text


def test_defaults_assign_seeded_agents(client, user):
    agents = client.post("/api/v1/setup", headers=user["headers"]).json()["seeded_agents"]
    client.delete(f"/api/v1/agents/{agents['seo']}", headers=user["headers"])
    d = client.get(f"{URL}/defaults", headers=user["headers"]).json()
    assert d["name"] == "" and d["help_centers"] == []
    assert d["analyses"] == ["readability", "links", "seo", "content_integrity", "summary"]
    assert d["crawl"]["max_pages"] == 2000
    assert set(d["agent_assignments"]) == set(agents) - {"seo"}  # deleted agents aren't offered


def test_defaults_before_setup(client, user):
    assert client.get(f"{URL}/defaults", headers=user["headers"]).json()["agent_assignments"] == {}
