"""Agent review, against a fake model registered in hop-core's provider registry."""

import json
from uuid import UUID

import httpx
import pytest
import respx
from hop_core.agents import AiProviderError, AiProviderRegistry, GenerationResponse
from hop_core.models.agent import Agent

import review
from models import AgentFinding, AuditRun, Page
from review import FindingIn, instructions, link_groups, parse_findings, quote_found
from tests.fake_site import BASE, page, serve
from tests.test_runs import add_run, execute, fast_retries, make_site  # noqa: F401

QUOTE = "Steady useful documentation words."


class FakeModel:
    """Answers each kind of batch; scripted failures go first."""

    def __init__(self):
        self.calls: list[str] = []
        self.temperatures: list = []
        self.budgets: list = []
        self.failures: list = []  # AiProviderError or a raw reply, consumed in order

    async def __call__(self, api_key, model, request):
        prompt = request.user_prompt
        self.calls.append(prompt)
        self.temperatures.append(request.temperature)
        self.budgets.append(request.max_tokens)
        if self.failures:
            failure = self.failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            if isinstance(failure, GenerationResponse):
                return failure
            return GenerationResponse(content=failure, input_tokens=10, output_tokens=1)
        if "for readability" in prompt:
            findings = [
                {
                    "page": "P1",
                    "severity": "High",
                    "title": "Repetitive sentences",
                    "body": "Vary them.",
                    "quote": QUOTE,
                    "suggestion": "Useful words.",
                    "on_focus": True,
                },
                {"page": "P2", "severity": "Low", "title": "Invented quote", "quote": "Not on the page at all"},
                {"page": "P99", "severity": "Low", "title": "Unknown page"},
                {"page": "P1", "severity": "Critical", "title": "Bad severity"},
            ]
        elif "SEO and metadata" in prompt:
            findings = [
                {
                    "page": "P1",
                    "severity": "Medium",
                    "title": "Description too short",
                    "suggestion": "A longer description that fits.",
                }
            ]
        else:
            target = next(line[4:] for line in prompt.splitlines() if line.startswith("### "))
            findings = [
                {
                    "target": target,
                    "severity": "High",
                    "title": "Broken link",
                    "body": "Restore it.",
                    "fix": "restore",
                    "suggestion": "",
                }
            ]
        reply = "Here you go:\n```json\n" + json.dumps(findings) + "\n```"
        return GenerationResponse(content=reply, input_tokens=1000, output_tokens=200)


@pytest.fixture
def model(monkeypatch):
    fake = FakeModel()
    saved = AiProviderRegistry.get("anthropic")
    AiProviderRegistry.register("anthropic", fake)
    monkeypatch.setattr(review, "RETRY_DELAY", 0)
    yield fake
    if saved:
        AiProviderRegistry.register("anthropic", saved)


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        yield m


def configured_site(client, user, focus="Flag repetition."):
    """A site whose readability, SEO and link agents run on the fake model."""
    h = user["headers"]
    agents = client.post("/api/v1/setup", headers=h).json()["seeded_agents"]
    cred = client.post(
        "/api/v1/credentials",
        json={"type": "anthropic", "name": "Claude", "credentials": {"api_key": "sk-test", "model": "claude-test"}},
        headers=h,
    )
    assert cred.status_code in (200, 201), cred.text
    for key in ("readability", "seo", "links"):
        r = client.put(f"/api/v1/agents/{agents[key]}", json={"ai_configuration_id": cred.json()["id"]}, headers=h)
        assert r.status_code == 200, r.text
    site = make_site(client, user)
    body = {**{k: v for k, v in site.items() if k not in ("id", "created_at", "updated_at")}}
    body.update(agent_assignments=agents, focus=focus)
    assert client.put(f"/api/v1/sites/{site['id']}", json=body, headers=h).status_code == 200
    return site, agents


# ── Units ─────────────────────────────────────────────────────────────────────


def test_parse_findings():
    assert parse_findings('[{"a": 1}]') == [{"a": 1}]
    assert parse_findings('Sure!\n```json\n[{"a": 1}]\n```\nDone.') == [{"a": 1}]
    assert parse_findings("[]") == []
    assert parse_findings("No problems found.") is None
    assert parse_findings('{"a": 1}') is None
    assert parse_findings("[not json]") is None


def test_quote_found():
    text = "Open the “Publish” dialog.\nThen  choose   a preset."
    assert quote_found('Open the "Publish" dialog.', text)
    assert quote_found("then choose a preset", text)
    assert quote_found("", text)
    assert not quote_found("Close the dialog", text)


def test_instructions_carry_both_focuses_and_the_format():
    text = instructions("readability", "Flag Heretto Publisher.", "Renamed workspaces.")
    assert "Focus for this site" in text and "Flag Heretto Publisher." in text
    assert "Focus for this run only:\nRenamed workspaces." in text
    assert '"page": "P1"' in text and "JSON array" in text
    assert "Focus for this run" not in instructions("seo", "", "")


def test_finding_validation():
    assert FindingIn.model_validate({"severity": "High", "title": "x"}).on_focus is False
    with pytest.raises(ValueError):
        FindingIn.model_validate({"severity": "Critical", "title": "x"})


def test_link_groups():
    from types import SimpleNamespace
    from uuid import uuid4

    a, b = uuid4(), uuid4()
    pages = {
        a: SimpleNamespace(path="/authoring/reuse", http_status=200),
        b: SimpleNamespace(path="/authoring/keys-and-keydefs", http_status=200),
    }
    rows = [
        SimpleNamespace(
            url=f"{BASE}authoring/keys",
            outcome="broken",
            status=404,
            note="HTTP 404",
            internal=True,
            page_id=a,
            text="keys",
        ),
        SimpleNamespace(
            url=f"{BASE}authoring/keys",
            outcome="broken",
            status=404,
            note="HTTP 404",
            internal=True,
            page_id=b,
            text="keys",
        ),
        SimpleNamespace(
            url="https://x.org/", outcome="redirect", status=200, note="", internal=False, page_id=a, text=""
        ),
        SimpleNamespace(url="https://y.org/", outcome="ok", status=200, note="", internal=False, page_id=a, text=""),
    ]
    groups = link_groups(rows, pages)
    assert [g.target for g in groups] == [f"{BASE}authoring/keys", "https://x.org/"]
    assert groups[0].page_ids == [a, b] and groups[0].texts == ["keys"]
    assert groups[0].candidates[0] == "/authoring/keys-and-keydefs"  # closest path first


def test_unavailable_agents(client, user, db):
    agents = client.post("/api/v1/setup", headers=user["headers"]).json()["seeded_agents"]
    org = db.get(Agent, UUID(agents["seo"])).organization_id
    with pytest.raises(review.AgentUnavailable, match="no agent is assigned"):
        review.load_agent(db, org, None)
    with pytest.raises(review.AgentUnavailable, match="no AI configuration"):
        review.load_agent(db, org, agents["seo"])
    client.delete(f"/api/v1/agents/{agents['seo']}", headers=user["headers"])
    with pytest.raises(review.AgentUnavailable, match="was deleted"):
        review.load_agent(db, org, agents["seo"])


# ── A run with agents ─────────────────────────────────────────────────────────

ANALYSES = ["readability", "seo", "links"]


async def test_run_with_agent_review(client, user, db, mock, model):
    serve(mock, **{"nowhere": httpx.Response(404)})
    mock.get(f"{BASE}authoring/a").respond(
        html=__import__("tests.fake_site").fake_site.page("Topic A", links=["/nowhere"])
    )
    site, agents = configured_site(client, user)
    run = await execute(db, add_run(db, site, user, analyses=ANALYSES))
    assert run.status == "completed", run.error

    stages = {s["key"]: s for s in run.stages}
    assert "Readability Reviewer: " in stages["readability"]["detail"]
    assert "quotes not on the page removed" in stages["readability"]["detail"]
    assert "SEO Analyst: " in stages["seo"]["detail"]
    assert "Link Validator: 1 finding (0 on focus)" in stages["links"]["detail"]

    # No temperature is sent: newer models reject the parameter.
    assert model.temperatures and set(model.temperatures) == {None}

    # The focus and the page text reach the agent.
    readability_prompt = next(c for c in model.calls if "for readability" in c)
    assert (
        "Flag repetition." in readability_prompt
        and QUOTE in readability_prompt
        and "Metrics: Flesch" in readability_prompt
    )

    findings = db.query(AgentFinding).filter(AgentFinding.run_id == run.id).all()
    by_title = {f.title: f for f in findings}
    assert "Bad severity" not in by_title and "Unknown page" not in by_title
    kept = by_title["Repetitive sentences"]
    assert kept.quote == QUOTE and kept.on_focus and kept.agent_name == "Readability Reviewer"
    assert kept.model == "claude-test" and kept.page_id is not None
    assert by_title["Invented quote"].quote == ""  # not on the page: removed
    link = by_title["Broken link"]
    assert link.page_id is None and link.target == f"{BASE}nowhere" and link.suggestion == "restore"
    assert len(link.page_ids) == 1

    stats = run.agent_stats[agents["readability"]]
    assert stats["name"] == "Readability Reviewer" and stats["tokens"] > 0 and stats["errors"] == 0
    assert run.tokens[agents["readability"]] == stats["tokens"]
    assert run.metrics["agent_findings"] == len(findings) and run.metrics["focus_findings"] == 1
    assert run.metrics["tokens"] == sum(run.tokens.values())

    detail_api = client.get(f"/api/v1/runs/{run.id}", headers=user["headers"]).json()
    assert detail_api["agent_stats"][agents["readability"]]["name"] == "Readability Reviewer"

    # Routes: the page list counts findings; page detail lists them, link findings included.
    rows = client.get(f"/api/v1/runs/{run.id}/pages", headers=user["headers"]).json()
    a = next(r for r in rows if r["path"] == "/authoring/a")
    detail = client.get(f"/api/v1/pages/{a['id']}", headers=user["headers"]).json()
    titles = {f["title"] for f in detail["agent_findings"]}
    assert "Broken link" in titles
    assert a["findings"] == len(detail["agent_findings"])


async def test_unchanged_checksum_keeps_readability_and_seo(client, user, db, mock, model):
    """Pages whose checksum hasn't changed keep last audit's metrics and findings,
    whatever changed in the agent or the focus; a forced run evaluates everything."""
    serve(mock)
    site, _ = configured_site(client, user)
    analyses = ["readability", "seo"]
    first = await execute(db, add_run(db, site, user, analyses=analyses))
    first_count = db.query(AgentFinding).filter(AgentFinding.run_id == first.id).count()
    before = {p.url: (p.flesch, p.seo) for p in db.query(Page).filter(Page.run_id == first.id)}
    calls = len(model.calls)

    # A new focus alone doesn't re-evaluate unchanged pages.
    body = client.get(f"/api/v1/sites/{site['id']}", headers=user["headers"]).json()
    body["focus"] = "Something else."
    client.put(f"/api/v1/sites/{site['id']}", json=body, headers=user["headers"])
    second = await execute(db, add_run(db, site, user, number=2, analyses=analyses, reuse_crawl=False))
    assert len(model.calls) == calls  # fetched again, same checksum: no new batches
    assert db.query(AgentFinding).filter(AgentFinding.run_id == second.id).count() == first_count
    stages = {s["key"]: s["detail"] for s in second.stages}
    assert (
        "7 unchanged pages kept" in stages["readability"] and "unchanged pages' findings kept" in stages["readability"]
    )
    assert "unchanged pages kept" in stages["seo"]
    after = {p.url: (p.flesch, p.seo) for p in db.query(Page).filter(Page.run_id == second.id)}
    assert after == before

    # A changed page is evaluated again; the rest are kept.
    mock.routes.clear()
    serve(mock, **{"authoring/b": httpx.Response(200, html=page("Topic B, rewritten"))})
    third = await execute(db, add_run(db, site, user, number=3, analyses=analyses, reuse_crawl=False))
    asked = model.calls[calls:]
    assert asked and all("Topic B, rewritten" in c for c in asked if "for readability" in c)
    assert "6 unchanged pages kept" in {s["key"]: s["detail"] for s in third.stages}["readability"]

    # Forcing evaluates every page again.
    calls = len(model.calls)
    forced = await execute(db, add_run(db, site, user, number=4, analyses=analyses, force_reevaluate=True))
    assert len(model.calls) > calls
    assert "unchanged pages kept" not in {s["key"]: s["detail"] for s in forced.stages}["readability"]
    assert any("Re-evaluating every page" in e.message for e in forced.log)


async def test_retries_rate_limits_and_asks_again_for_json(client, user, db, mock, model):
    serve(mock)
    site, _ = configured_site(client, user)
    model.failures = [AiProviderError("slow down", status_code=429), "I found some issues, see above."]
    run = await execute(db, add_run(db, site, user, analyses=["readability"]))
    stats = next(iter(run.agent_stats.values()))
    assert stats["retries"] == 1 and stats["errors"] == 0 and stats["findings"] > 0
    messages = [e.message for e in run.log]
    assert any("anthropic returned 429 on batch 1; retried after 0 s." in m for m in messages)
    assert any("reply wasn't JSON; asked again" in m for m in messages)


async def test_agent_stops_after_three_failed_batches(client, user, db, mock, model, monkeypatch):
    serve(mock)
    monkeypatch.setitem(review.BATCH_SIZE, "readability", 1)
    site, _ = configured_site(client, user)
    model.failures = [AiProviderError("bad request", status_code=400)] * 10
    run = await execute(db, add_run(db, site, user, analyses=["readability"]))
    assert run.status == "completed"  # metrics still stand
    stats = next(iter(run.agent_stats.values()))
    assert stats["errors"] == 3 and stats["status"] == "stopped"
    assert "stopped after 3 failed batches in a row" in run.stages[2]["detail"]
    assert run.stages[2]["status"] == "failed" and "analyze again" in run.stages[2]["detail"]
    assert db.query(Page).filter(Page.run_id == run.id, Page.flesch.isnot(None)).count() > 0


async def test_dismissing_teaches_the_agent(client, user, db, mock, model):
    serve(mock)
    site, agents = configured_site(client, user)
    run = await execute(db, add_run(db, site, user, analyses=["readability"]))
    finding = (
        db.query(AgentFinding)
        .filter(AgentFinding.run_id == run.id, AgentFinding.title == "Repetitive sentences")
        .first()
    )
    url = f"/api/v1/findings/{finding.id}"
    r = client.patch(
        url,
        json={"dismissed": True, "reason": "Repetition is intended here."},
        headers=user["headers"],
    )
    assert r.status_code == 200 and r.json()["dismissed"]
    memory = db.get(Agent, UUID(agents["readability"]))
    db.refresh(memory)
    assert '"Repetitive sentences" (High, /' in memory.feedback_memory
    assert "Repetition is intended here." in memory.feedback_memory
    assert memory.feedback_memory.startswith("### Dismissed ")

    restored = client.patch(url, json={"dismissed": False}, headers=user["headers"])
    assert not restored.json()["dismissed"] and restored.json()["dismissed_reason"] == ""

    from tests.conftest import make_user

    other = make_user(client)
    assert (
        client.patch(f"/api/v1/findings/{finding.id}", json={"dismissed": True}, headers=other["headers"]).status_code
        == 404
    )


async def test_reanalysis_replaces_findings(client, user, db, mock, model):
    serve(mock)
    site, _ = configured_site(client, user)
    run = await execute(db, add_run(db, site, user, analyses=["readability"]))
    before = db.query(AgentFinding).filter(AgentFinding.run_id == run.id).count()
    import crawler
    import discovery
    import runner

    async with discovery.client() as http:
        await runner.reanalyze(run.id, crawler.Control(), http=http)
    db.expire_all()
    assert db.query(AgentFinding).filter(AgentFinding.run_id == run.id).count() == before
    assert db.get(AuditRun, run.id).status == "completed"


def out_of_room(budget):
    """hop-core's error when thinking used up max_tokens before any text."""
    return AiProviderError(
        f"Anthropic ran out of room before writing a reply: the {budget:,}-token max_tokens budget was used up, "
        f"{budget:,} of them thinking. Raise max_tokens."
    )


async def test_reply_that_runs_out_of_room_is_asked_again_with_more(client, user, db, mock, model):
    serve(mock)
    site, _ = configured_site(client, user)
    cut = GenerationResponse(content='[{"page": "P1", "severity": "Hi', stop_reason="max_tokens", output_tokens=16384)
    model.failures = [out_of_room(8192), cut]
    run = await execute(db, add_run(db, site, user, analyses=["readability"]))
    assert model.budgets[:3] == [8192, 16384, 32768]  # no text, then cut off mid-JSON, then it fits
    stats = next(iter(run.agent_stats.values()))
    assert stats["errors"] == 0 and stats["findings"] > 0
    messages = [e.message for e in run.log]
    assert sum("didn't fit in" in m for m in messages) == 2
    assert not any("wasn't JSON" in m for m in messages)  # a cut-off reply isn't asked for "JSON only"


async def test_reply_that_never_fits_fails_the_batch(client, user, db, mock, model, monkeypatch):
    serve(mock)
    monkeypatch.setitem(review.BATCH_SIZE, "readability", 100)  # one batch
    site, _ = configured_site(client, user)
    model.failures = [out_of_room(b) for b in (8192, 16384, 32768, 65536)]
    run = await execute(db, add_run(db, site, user, analyses=["readability"]))
    assert model.budgets == [8192, 16384, 32768, 65536]
    errors = [e.message for e in run.log if e.level == "error"]
    assert any("didn't fit even in 65,536 tokens; skipped" in m for m in errors)
    assert not any("Raise max_tokens" in m for m in errors)  # nothing the user can raise
    assert run.stages[2]["status"] == "failed"


def test_budgets_start_by_analysis():
    assert review.REPLY_BUDGET["content_integrity"] > review.REPLY_BUDGET["readability"] >= 8192
