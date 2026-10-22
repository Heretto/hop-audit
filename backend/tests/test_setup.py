"""Agent seeding: six agents once per organization, never resurrected."""

import pytest

from catalog import AGENT_ANALYSES
from seed import AGENT_SEEDS, context_files
from tests.conftest import make_user


def agents(client, user):
    r = client.get("/api/v1/agents", headers=user["headers"])
    assert r.status_code == 200
    return r.json()


def test_setup_seeds_six_agents(client, user):
    r = client.post("/api/v1/setup", headers=user["headers"])
    assert r.status_code == 200
    body = r.json()
    assert set(body["seeded_agents"]) == set(AGENT_ANALYSES)  # no Link Validator: links need no agent

    listed = agents(client, user)
    assert sorted(a["name"] for a in listed) == sorted(s.name for s in AGENT_SEEDS)
    assert {a["id"] for a in listed} == set(body["seeded_agents"].values())
    assert all(a["context_file_count"] >= 1 and a["is_active"] for a in listed)
    assert all(a["ai_configuration_id"] is None for a in listed)  # chosen by the user


def test_setup_is_idempotent(client, user):
    first = client.post("/api/v1/setup", headers=user["headers"]).json()
    second = client.post("/api/v1/setup", headers=user["headers"]).json()
    assert first == second
    assert len(agents(client, user)) == len(AGENT_SEEDS)


def test_deleted_agent_is_not_recreated(client, user):
    mapping = client.post("/api/v1/setup", headers=user["headers"]).json()["seeded_agents"]
    r = client.delete(f"/api/v1/agents/{mapping['seo']}", headers=user["headers"])
    assert r.status_code == 200
    client.post("/api/v1/setup", headers=user["headers"])
    assert len(agents(client, user)) == len(AGENT_SEEDS) - 1


def test_organizations_are_isolated(client, user):
    other = make_user(client)
    mine = client.post("/api/v1/setup", headers=user["headers"]).json()["seeded_agents"]
    theirs = client.post("/api/v1/setup", headers=other["headers"]).json()["seeded_agents"]
    assert set(mine.values()).isdisjoint(theirs.values())
    assert {a["id"] for a in agents(client, other)} == set(theirs.values())


def test_seeded_agent_has_context_contents(client, user):
    mapping = client.post("/api/v1/setup", headers=user["headers"]).json()["seeded_agents"]
    agent = client.get(f"/api/v1/agents/{mapping['content_integrity']}", headers=user["headers"]).json()
    names = [f["name"] for f in agent["context_files"]]
    assert names == ["Assessment", "Counting and severity", "Triage tiers"]
    assert "Contradictions" in agent["context_files"][0]["content"]


@pytest.mark.parametrize("seed", AGENT_SEEDS, ids=lambda s: s.slug)
def test_context_files_exist_and_are_clean(seed):
    files = context_files(seed.slug)
    assert files, f"no context files for {seed.slug}"
    for f in files:
        assert f.content.strip()
        # HOP Audit's crawler replaces the skill's browser and script steps.
        for leftover in ("Claude in Chrome", "build_onesheet.py", "/mnt/user-data"):
            assert leftover not in f.content, (seed.slug, f.name, leftover)


def test_assessment_names_all_categories():
    from catalog import INTEGRITY_CATEGORIES

    text = context_files("content-integrity-reviewer")[0].content
    for code in ("C-01", "U-", "T-", "TM-", "D-", "L-", "S-", "O-", "N-", "X-"):
        assert code in text
    assert len(INTEGRITY_CATEGORIES) == 10
