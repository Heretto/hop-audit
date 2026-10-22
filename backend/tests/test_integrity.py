"""Content integrity: batching, verification, stable codes, triage."""

import json
import uuid
from types import SimpleNamespace
from uuid import UUID

import pytest
import respx
from hop_core.agents import AiProviderRegistry, GenerationResponse
from hop_core.models.agent import Agent

import integrity
import review
from integrity import Candidate, article_batches, counterparts, merge, pairings, verify
from models import AuditRun, IntegrityFinding
from scope import Root
from tests.fake_site import BASE, serve
from tests.test_runs import add_run, execute, fast_retries, make_site  # noqa: F401

QUOTE = "Steady useful documentation words."
EN = Root(uuid.uuid4(), "US English", BASE, "en", True)
DE = Root(uuid.uuid4(), "Deutsch", f"{BASE}de/", "de", False)


def page(path, section="/a", text=QUOTE * 3, title="T", root=EN, alternates=()):
    return SimpleNamespace(
        id=uuid.uuid4(),
        url=f"{root.url.rstrip('/')}{path}",
        path=path,
        section=section,
        title=title,
        help_center_id=root.id,
        content={"text": text, "alternates": [{"language": "x", "url": u} for u in alternates]},
    )


# ── Units ─────────────────────────────────────────────────────────────────────


def test_article_batches_keep_sections_together_within_budget():
    pages = [page("/a/1", "/a", "x" * 30), page("/a/2", "/a", "x" * 30), page("/b/1", "/b", "x" * 30)]
    assert [len(b) for b in article_batches(pages, budget=100)] == [3]
    assert [[p.path for p in b] for b in article_batches(pages, budget=70)] == [["/a/1", "/a/2"], ["/b/1"]]


def test_pairings():
    fr = Root(uuid.uuid4(), "Français", "https://x/fr/", "fr", False)
    fr_ca = Root(uuid.uuid4(), "Canada FR", "https://x/ca/fr/", "fr-CA", False)
    pairs = {(a.name, b.name) for a, b in pairings([EN, fr, fr_ca])}
    assert pairs == {("Français", "US English"), ("Canada FR", "US English"), ("Canada FR", "Français")}


def test_counterparts_by_path_and_hreflang():
    en_a, en_b = page("/authoring/a"), page("/other")
    de_a = page("/authoring/a", root=DE)
    de_b = page("/anders", root=DE, alternates=[f"{BASE}other"])
    de_c = page("/only-de", root=DE)
    pairs = counterparts([en_a, en_b], EN, [de_a, de_b, de_c], DE)
    assert [(a.path, b.path) for a, b in pairs] == [("/authoring/a", "/authoring/a"), ("/other", "/anders")]


def test_verify():
    p1, p2 = page("/a"), page("/b", text="Something else entirely.")
    refs = {"P1": (p1, EN), "P2": (p2, EN)}
    raw = [
        {"category": "c", "severity": "High", "title": "Two answers", "tier": "firm",
         "quotes": [{"label": "A", "page": "P1", "text": QUOTE},
                    {"label": "B", "page": "P2", "text": "else entirely"}]},
        {"category": "X", "severity": "Low", "title": "Invented", "tier": "firm",
         "quotes": [{"page": "P1", "text": "Not on the page"}]},
        {"category": "D", "severity": "Low", "title": "Disabled category", "quotes": [{"page": "P1", "text": QUOTE}]},
        {"category": "C", "severity": "Low", "title": "Unknown page", "quotes": [{"page": "P9", "text": QUOTE}]},
        {"category": "C", "severity": "Critical", "title": "Bad", "quotes": [{"page": "P1", "text": QUOTE}]},
    ]  # fmt: skip
    found, malformed = verify(raw, refs, {"C", "X"})
    assert malformed == 3
    first, second = found
    assert first.category == "C" and first.tier == "firm" and [q["verified"] for q in first.quotes] == [True, True]
    assert first.quotes[0]["slug"] == "a" and first.center_ids == [EN.id]
    assert second.tier == "review" and "couldn't be found" in second.reason


def test_merge_keeps_the_most_severe_of_duplicates():
    q = [{"slug": "a", "text": QUOTE}]
    low = Candidate("C", "Low", "Dup low", q, "", "firm", "")
    high = Candidate("C", "High", "Dup high", q + [{"slug": "b", "text": "x"}], "", "firm", "")
    other = Candidate("U", "Low", "Same quote, other category", q, "", "firm", "")
    assert [c.title for c in merge([low, high, other])] == ["Dup high", "Same quote, other category"]


def test_missing_translations_are_listed_for_review():
    en_a, en_b = page("/a"), page("/b", title="Only English")
    de_a = page("/a", root=DE)
    roots = {EN.id: EN, DE.id: DE}
    found = integrity.missing_translations({(DE.id, EN.id): [(en_a, de_a)]}, roots, {EN.id: [en_a, en_b]})
    assert len(found) == 1
    c = found[0]
    assert c.category == "T" and c.tier == "review" and c.title == "1 US English articles have no Deutsch version"
    assert c.quotes[0]["text"] == "Only English" and c.quotes[0]["note"] == "no Deutsch version"


def test_triage_feedback_lists_only_changed_calls():
    f = lambda code, proposed, tier, note="": SimpleNamespace(  # noqa: E731
        code=code, title="T", severity="High", proposed_tier=proposed, tier=tier, triage_note=note, proposed_reason=""
    )
    text = integrity.triage_feedback([f("C-01", "firm", "firm"), f("C-02", "firm", "review", "Policy")], "X", 3)
    assert "C-02" in text and "C-01" not in text and "proposed firm, judged review. Note: Policy" in text
    assert integrity.triage_feedback([f("C-01", "firm", "firm")], "X", 3) == ""


# ── Runs ──────────────────────────────────────────────────────────────────────


class FakeReviewer:
    """Answers content-integrity batches; ``extra`` adds a second article finding."""

    def __init__(self):
        self.calls: list[str] = []
        self.extra = True

    async def __call__(self, api_key, model, request):
        prompt = request.user_prompt
        self.calls.append(prompt)
        if "## Pair 1" in prompt:
            out = [{"category": "T", "severity": "High", "title": "German says the opposite", "tier": "firm",
                    "quotes": [{"label": "EN", "page": "P1", "text": QUOTE},
                               {"label": "DE", "page": "P2", "text": QUOTE, "note": "(same)"}],
                    "why": "A German reader is told the opposite."}]  # fmt: skip
        elif "Help center: US English" in prompt:
            out = [
                {
                    "category": "C",
                    "severity": "Medium",
                    "title": "Two answers",
                    "tier": "firm",
                    "quotes": [{"label": "A", "page": "P1", "text": QUOTE}],
                    "why": "Customers get two answers.",
                }
            ]
            if self.extra:
                out.append(
                    {
                        "category": "X",
                        "severity": "Low",
                        "title": "Internal note published",
                        "tier": "firm",
                        "quotes": [{"page": "P2", "text": QUOTE}],
                        "why": "Agent text is public.",
                    }
                )
        else:
            out = []
        return GenerationResponse(content=json.dumps(out), input_tokens=500, output_tokens=100)


@pytest.fixture
def model(monkeypatch):
    fake = FakeReviewer()
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


def integrity_site(client, user, categories=None):
    h = user["headers"]
    agents = client.post("/api/v1/setup", headers=h).json()["seeded_agents"]
    cred = client.post(
        "/api/v1/credentials",
        json={"type": "anthropic", "name": "Claude", "credentials": {"api_key": "k", "model": "claude-test"}},
        headers=h,
    ).json()
    client.put(f"/api/v1/agents/{agents['content_integrity']}", json={"ai_configuration_id": cred["id"]}, headers=h)
    site = make_site(client, user)
    body = {k: v for k, v in site.items() if k not in ("id", "created_at", "updated_at")}
    body.update(agent_assignments=agents, purpose="prospect")
    if categories is not None:
        body["integrity_categories"] = categories
    assert client.put(f"/api/v1/sites/{site['id']}", json=body, headers=h).status_code == 200
    return site, agents


async def run_integrity(db, site, user, number=1) -> AuditRun:
    run = await execute(db, add_run(db, site, user, number=number, analyses=["content_integrity"], reuse_crawl=False))
    assert run.status == "completed", run.error
    return run


def findings(db, run):
    return {f.code: f for f in db.query(IntegrityFinding).filter(IntegrityFinding.run_id == run.id)}


async def test_review_logs_candidates_with_codes(client, user, db, mock, model):
    serve(mock)
    site, _ = integrity_site(client, user)
    run = await run_integrity(db, site, user)

    stage = next(s for s in run.stages if s["key"] == "content_integrity")
    assert stage["status"] == "done" and "candidates" in stage["detail"]
    assert any("Help center: Deutsch" in c for c in model.calls)  # each help center read
    assert any("## Pair 1" in c for c in model.calls)  # and translations compared
    assert all("Log these categories only" in c for c in model.calls)

    found = findings(db, run)
    assert set(found) == {"C-01", "X-01", "T-01", "T-02"}
    assert found["C-01"].tier == "firm" and found["C-01"].first_seen == 1 and found["C-01"].locale == "US English"
    assert found["T-01"].locale == "Deutsch vs. US English" or found["T-02"].locale == "Deutsch vs. US English"
    missing = next(f for f in found.values() if "have no Deutsch version" in f.title)
    assert missing.tier == "review"
    assert found["X-01"].quotes[0]["slug"] == "api/c"  # articles go by section: P2 is /api/c

    assert run.triage == {"status": "pending"}
    m = run.metrics["integrity"]
    assert m["candidates"] == 4 and m["confirmed"] is False


async def test_categories_follow_site_settings(client, user, db, mock, model):
    serve(mock)
    site, _ = integrity_site(client, user, categories=["C"])
    run = await run_integrity(db, site, user)
    assert set(findings(db, run)) == {"C-01"}  # X dropped, no translation pass
    assert not any("## Pair" in c for c in model.calls)


async def test_codes_are_stable_and_triage_carries_over(client, user, db, mock, model):
    serve(mock)
    site, agents = integrity_site(client, user)
    first = await run_integrity(db, site, user)
    h = user["headers"]
    c01 = findings(db, first)["C-01"]
    client.patch(f"/api/v1/integrity-findings/{c01.id}", json={"tier": "review", "triage_note": "Policy"}, headers=h)
    assert client.post(f"/api/v1/runs/{first.id}/triage/confirm", headers=h).status_code == 200

    model.extra = False  # X-01 is fixed on the site
    mock.routes.clear()
    serve(mock)
    second = await run_integrity(db, site, user, number=2)
    again = findings(db, second)
    assert again["C-01"].first_seen == 1 and again["C-01"].tier == "review" and again["C-01"].carried_from == 1
    assert again["C-01"].triage_note == "Policy"
    assert "X-01" not in again
    assert second.metrics["integrity"]["resolved"] == ["X-01"]

    # Compare shows integrity counts only for runs whose triage is confirmed.
    rows = {
        r["key"]: r for r in client.get(f"/api/v1/runs/compare?a={first.id}&b={second.id}", headers=h).json()["rows"]
    }
    assert rows["integrity_firm"]["a"] == 2  # T-01 and X-01; C-01 moved to review
    assert rows["integrity_firm"]["b"] is None and rows["integrity_firm"]["delta"] is None

    model.extra = True  # it came back: a new code, the numbering continues
    mock.routes.clear()
    serve(mock)
    third = await run_integrity(db, site, user, number=3)
    assert "X-02" in findings(db, third)


async def test_triage_rules(client, user, db, mock, model):
    serve(mock)
    site, agents = integrity_site(client, user)
    run = await run_integrity(db, site, user)
    h = user["headers"]
    found = findings(db, run)
    url = lambda code: f"/api/v1/integrity-findings/{found[code].id}"  # noqa: E731
    missing = next(f for f in found.values() if f.tier == "review")

    # Examples only from firm; leaving firm clears it; ranks follow the picking order.
    r = client.patch(f"/api/v1/integrity-findings/{missing.id}", json={"example": True}, headers=h)
    assert r.status_code == 422
    r = client.patch(url("X-01"), json={"example": True}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["example_rank"] == 1
    assert client.patch(url("C-01"), json={"example": True}, headers=h).json()["example_rank"] == 2
    assert client.patch(url("X-01"), json={"tier": "drop"}, headers=h).json()["example_rank"] is None

    view = client.get(f"/api/v1/runs/{run.id}/integrity", headers=h).json()
    assert view["triage"] == {"status": "in_progress"} and view["purpose"] == "prospect"
    assert [c["name"] for c in view["help_centers"]] == ["US English", "Deutsch"]
    assert view["help_centers"][0]["articles"] == 5
    assert [f["severity"] for f in view["findings"]] == sorted(
        [f["severity"] for f in view["findings"]], key=["High", "Medium", "Low"].index
    )

    confirmed = client.post(f"/api/v1/runs/{run.id}/triage/confirm", headers=h).json()
    assert confirmed["triage"]["status"] == "confirmed" and confirmed["triage"]["confirmed_by"] == user["email"]
    db.expire_all()
    m = db.get(AuditRun, run.id).metrics["integrity"]
    assert m["confirmed"] and m["drop"] == 1 and m["firm"] == m["high"] + m["medium"] + m["low"]
    assert m["firm"] + m["review"] + m["drop"] == m["candidates"]
    memory = db.get(Agent, UUID(agents["content_integrity"])).feedback_memory
    assert "X-01" in memory and "proposed firm, judged drop" in memory and memory.startswith("### Triage ")

    # Any change reopens a confirmed triage.
    client.patch(url("C-01"), json={"triage_note": "Checked"}, headers=h)
    db.expire_all()
    assert db.get(AuditRun, run.id).triage == {"status": "in_progress"}
    assert db.get(AuditRun, run.id).metrics["integrity"]["confirmed"] is False

    page_id = found["C-01"].quotes[0]["page_id"]
    on_page = client.get(f"/api/v1/pages/{page_id}", headers=h).json()["integrity_findings"]
    assert "C-01" in [f["code"] for f in on_page] and "X-01" not in [f["code"] for f in on_page]  # dropped

    csv = client.get(f"/api/v1/runs/{run.id}/integrity.csv", headers=h)
    assert csv.text.startswith("code,severity,category") and "C-01" in csv.text
    assert "x-help-audit-1-integrity.csv" in csv.headers["content-disposition"]

    from tests.conftest import make_user

    other = make_user(client)
    assert client.get(f"/api/v1/runs/{run.id}/integrity", headers=other["headers"]).status_code == 404
    assert client.patch(url("C-01"), json={"tier": "firm"}, headers=other["headers"]).status_code == 404


async def test_no_reviewer_means_no_candidates(client, user, db, mock):
    serve(mock)
    site = make_site(client, user)
    run = await run_integrity(db, site, user)
    stage = next(s for s in run.stages if s["key"] == "content_integrity")
    assert stage["status"] == "skipped" and stage["detail"].startswith("Not reviewed: no agent is assigned")
    r = client.post(f"/api/v1/runs/{run.id}/triage/confirm", headers=user["headers"])
    assert r.status_code == 409


async def test_reanalysis_keeps_a_triage(client, user, db, mock, model):
    import crawler
    import discovery
    import runner

    serve(mock)
    site, _ = integrity_site(client, user)
    run = await run_integrity(db, site, user)
    ids = set(f.id for f in findings(db, run).values())
    calls = len(model.calls)
    async with discovery.client() as http:
        await runner.reanalyze(run.id, crawler.Control(), http=http)
    db.expire_all()
    assert {f.id for f in findings(db, run).values()} == ids and len(model.calls) == calls


async def test_failed_review_is_not_a_clean_result(client, user, db, mock, model, monkeypatch):
    """Every batch failing (as with the 'temperature is deprecated' 400s) must not read as 'no issues'."""
    from hop_core.agents import AiProviderError

    import crawler
    import discovery
    import runner

    serve(mock)
    site, _ = integrity_site(client, user)
    first = await run_integrity(db, site, user)  # X-01 and friends exist from a good run
    client.post(f"/api/v1/runs/{first.id}/triage/confirm", headers=user["headers"])

    async def always_400(api_key, model_name, request):
        raise AiProviderError("Anthropic returned HTTP 400: `temperature` is deprecated for this model.", 400)

    AiProviderRegistry.register("anthropic", always_400)
    run = await run_integrity(db, site, user, number=2)
    stage = next(s for s in run.stages if s["key"] == "content_integrity")
    assert stage["status"] == "failed" and "didn't review this audit" in stage["detail"]
    assert findings(db, run) == {}
    assert "integrity" not in run.metrics  # no counts, no 'resolved'
    assert (run.triage or {}).get("status") != "confirmed"
    assert any(e.level == "error" and "temperature" in e.message for e in run.log)

    # Fixed: analyzing again reviews it, since triage never started.
    AiProviderRegistry.register("anthropic", model)
    async with discovery.client() as http:
        await runner.reanalyze(run.id, crawler.Control(), http=http)
    db.expire_all()
    run = db.get(AuditRun, run.id)
    assert next(s for s in run.stages if s["key"] == "content_integrity")["status"] == "done"
    assert "C-01" in findings(db, run) and run.metrics["integrity"]["candidates"] > 0


async def test_partial_failure_never_confirms_itself(client, user, db, mock, monkeypatch):
    from hop_core.agents import AiProviderError

    calls = []

    async def first_fails(api_key, model_name, request):
        calls.append(1)
        if len(calls) == 1:
            raise AiProviderError("overloaded", 400)
        return GenerationResponse(content="[]", input_tokens=1, output_tokens=1)

    saved = AiProviderRegistry.get("anthropic")
    AiProviderRegistry.register("anthropic", first_fails)
    monkeypatch.setattr(review, "RETRY_DELAY", 0)
    try:
        serve(mock)
        site, _ = integrity_site(client, user, categories=["C"])
        run = await run_integrity(db, site, user)
    finally:
        if saved:
            AiProviderRegistry.register("anthropic", saved)
    stage = next(s for s in run.stages if s["key"] == "content_integrity")
    assert stage["status"] == "done" and "1 failed batches" in stage["detail"]
    assert run.triage == {"status": "pending"}  # nothing found, but not everything was read
    assert run.metrics["integrity"]["confirmed"] is False
