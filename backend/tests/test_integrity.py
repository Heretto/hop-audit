"""Content integrity: the three passes, code findings, verification, stable codes, triage."""

import json
import re
import uuid
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
import respx
from hop_core.agents import AiProviderRegistry, GenerationResponse
from hop_core.models.agent import Agent

import integrity
import review
from claims import Claim
from integrity import Candidate, counterparts, merge, pairings, verify, verify_group
from models import AuditRun, ClaimGroupReview, IntegrityFinding, Page
from scope import Root
from tests.fake_site import BASE, serve
from tests.fake_site import page as html_page
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


def test_verify_group_takes_statements_from_the_claims():
    a = Claim(uuid.uuid4(), f"{BASE}a", "a", EN.id, "support phone", "Call 555-0146.")
    b = Claim(uuid.uuid4(), f"{BASE}b", "b", EN.id, "support phone", "Call 555-0164.")
    refs = {"S1": a, "S2": b}
    raw = [
        {"category": "c", "severity": "High", "title": "Two numbers", "statements": ["S1", "S2"], "tier": "firm"},
        {"category": "C", "severity": "High", "title": "One statement", "statements": ["S1"]},
        {"category": "O", "severity": "Low", "title": "Not a cross-article category", "statements": ["S1", "S2"]},
        {"category": "D", "severity": "Low", "title": "Disabled", "statements": ["S1", "S2"]},
        "not an object",
    ]
    found, malformed = verify_group(raw, refs, {"C", "O"})
    assert malformed == 4 and len(found) == 1
    q = found[0].quotes
    assert [(x["label"], x["text"], x["slug"], x["verified"]) for x in q] == [
        ("A", "Call 555-0146.", "a", True),
        ("B", "Call 555-0164.", "b", True),
    ]


def test_claims_must_be_on_the_page():
    p = page("/a", text="Call support at 555-0146 any weekday. " * 3)
    raw = [
        {"subject": "support phone", "statement": "Call support at 555-0146 any weekday."},
        {"subject": "support phone", "statement": "Call support at 555-9999 any weekday."},
        {"subject": "", "statement": "Call support at 555-0146 any weekday."},
        "nope",
    ]
    assert integrity._claims(raw, p) == [
        {"subject": "support phone", "statement": "Call support at 555-0146 any weekday."}
    ]
    assert len(integrity._claims([raw[0]] * 50, p)) == integrity.MAX_CLAIMS


# ── Runs ──────────────────────────────────────────────────────────────────────

PHONE_A = "Call support at 555-0146 any weekday."
PHONE_B = "Call support at 555-0164 any weekday."
FILLER = " ".join([QUOTE] * 8)


class FakeReviewer:
    """Answers the three kinds of integrity request; ``extra`` adds an issue inside /authoring/a."""

    def __init__(self):
        self.calls: list[str] = []
        self.extra = True

    def kind(self, prompt: str) -> str:
        if "Compare the translation (P2)" in prompt:
            return "pair"
        if prompt.count("\nS1 · ") or "\nSubject: " in prompt:
            return "group"
        return "article"

    async def __call__(self, api_key, model, request):
        prompt = request.user_prompt
        self.calls.append(prompt)
        kind = self.kind(prompt)
        if kind == "pair":
            out = [{"category": "T", "severity": "High", "title": "German says the opposite", "tier": "firm",
                    "quotes": [{"label": "EN", "page": "P1", "text": QUOTE},
                               {"label": "DE", "page": "P2", "text": QUOTE, "note": "(same)"}],
                    "why": "A German reader is told the opposite."}]  # fmt: skip
        elif kind == "group":
            out = [{"category": "C", "severity": "High", "title": "Two support numbers", "statements": ["S1", "S2"],
                    "why": "One of them is wrong.", "tier": "firm"}]  # fmt: skip
        else:
            text = prompt.split("\n### P1", 1)[-1]
            phones = re.findall(r"Call support at 555-\d+ any weekday\.", text)
            claims = [{"subject": "support phone number", "statement": s} for s in dict.fromkeys(phones)]
            issues = []
            if "· authoring/a ·" in text and self.extra:
                issues.append(
                    {
                        "category": "X",
                        "severity": "Medium",
                        "title": "Internal note published",
                        "tier": "firm",
                        "quotes": [{"page": "P1", "text": PHONE_A}],
                        "why": "Agent text.",
                    }
                )
            if "· archive/old ·" in text:
                issues.append(
                    {
                        "category": "O",
                        "severity": "Low",
                        "title": "Invented quote",
                        "tier": "firm",
                        "quotes": [{"page": "P1", "text": "Not on this page."}],
                        "why": "Should go to review.",
                    }
                )
            out = {"issues": issues, "claims": claims}  # fmt: skip
        return GenerationResponse(content=json.dumps(out), input_tokens=500, output_tokens=100)

    def count(self, kind: str) -> int:
        return sum(1 for c in self.calls if self.kind(c) == kind)


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


def serve_site(mock, **extra):
    """The fake help center with two articles that disagree on the support number."""
    return serve(
        mock,
        **{
            "authoring/a": httpx.Response(200, html=html_page("Topic A", f"{PHONE_A} {FILLER}",
                                                              links=["/nowhere", "/de/authoring/a"])),
            "authoring/b": httpx.Response(200, html=html_page("Topic B", f"{PHONE_B} {FILLER}")),
            "api/c": httpx.Response(200, html=html_page("Topic A")),  # duplicate title
            "nowhere": httpx.Response(404),
            **extra,
        },
    )  # fmt: skip


def integrity_site(client, user, categories=None, claim_matching=None):
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
    if claim_matching is not None:
        body["claim_matching"] = claim_matching
    r = client.put(f"/api/v1/sites/{site['id']}", json=body, headers=h)
    assert r.status_code == 200, r.text
    return site, agents


async def run_integrity(db, site, user, number=1, **fields) -> AuditRun:
    analyses = fields.pop("analyses", ["links", "content_integrity"])
    run = await execute(db, add_run(db, site, user, number=number, analyses=analyses, reuse_crawl=False, **fields))
    assert run.status == "completed", run.error
    return run


def findings(db, run):
    return {f.code: f for f in db.query(IntegrityFinding).filter(IntegrityFinding.run_id == run.id)}


def by_title(found):
    return {f.title: f for f in found.values()}


def stage(run):
    return next(s for s in run.stages if s["key"] == "content_integrity")


async def test_three_passes_and_code_findings(client, user, db, mock, model):
    serve_site(mock)
    site, _ = integrity_site(client, user)
    run = await run_integrity(db, site, user)

    # One request per article (7 with enough text), per translation pair (2), per disagreeing group (1).
    assert model.count("article") == 7 and model.count("pair") == 2 and model.count("group") == 1
    assert all(c.count("### P1") == 1 for c in model.calls if model.kind(c) == "article")
    group_prompt = next(c for c in model.calls if model.kind(c) == "group")
    assert "Subject: support phone number" in group_prompt and PHONE_A in group_prompt and PHONE_B in group_prompt

    found = by_title(findings(db, run))
    two = found["Two support numbers"]  # pass 3, across articles
    assert two.category == "C" and {q["slug"] for q in two.quotes} == {"authoring/a", "authoring/b"}
    assert found["Internal note published"].category == "X"  # pass 1
    assert found["German says the opposite"].category == "T"  # pass 2
    assert found["Invented quote"].tier == "review"  # quote not on the page
    assert any("no Deutsch version" in t for t in found), list(found)  # code
    assert found['2 articles share the title "Topic A"'].category == "N"  # code
    wrong = next(f for t, f in found.items() if "links into the Deutsch help center" in t)  # code
    assert wrong.quotes[0]["text"] == "/de/authoring/a" and wrong.locale == "US English, Deutsch"
    broken = next(f for t, f in found.items() if t.startswith("Broken link"))  # code, from the link check
    assert broken.quotes[0]["text"] == "/nowhere" and broken.tier == "firm"

    detail = stage(run)["detail"]
    assert "7 articles (0 unchanged kept), 2 translation pairs (0 kept), 1 statement groups by keywords" in detail
    assert db.query(ClaimGroupReview).count() >= 1


async def test_unchanged_articles_pairs_and_groups_are_kept(client, user, db, mock, model):
    serve_site(mock)
    site, _ = integrity_site(client, user)
    first = await run_integrity(db, site, user)
    calls = len(model.calls)
    mock.routes.clear()
    serve_site(mock)
    second = await run_integrity(db, site, user, number=2)
    assert len(model.calls) == calls  # nothing changed: no requests
    assert (
        "7 articles (7 unchanged kept), 2 translation pairs (2 kept), 1 statement groups by keywords (1 kept)"
        in (stage(second)["detail"])
    )
    assert set(by_title(findings(db, second))) == set(by_title(findings(db, first)))

    # An article's wording changes elsewhere: it alone is read again; its statements, and so the group, are the same.
    mock.routes.clear()
    serve_site(mock, **{"authoring/b": httpx.Response(200, html=html_page("Topic B", f"{PHONE_B} Updated. {FILLER}"))})
    calls = len(model.calls)
    await run_integrity(db, site, user, number=3)
    asked = [model.kind(c) for c in model.calls[calls:]]
    assert asked == ["article"] and "Updated." in model.calls[-1]

    # Its statement changes: the group is compared again.
    mock.routes.clear()
    new_phone = PHONE_B.replace("0164", "0199")
    serve_site(mock, **{"authoring/b": httpx.Response(200, html=html_page("Topic B", f"{new_phone} {FILLER}"))})
    calls = len(model.calls)
    await run_integrity(db, site, user, number=4)
    asked = model.calls[calls:]
    assert [model.kind(c) for c in asked] == ["article", "group"] and "555-0199" in asked[-1]

    calls = len(model.calls)
    await run_integrity(db, site, user, number=5, force_reevaluate=True)
    assert model.calls[calls:] and [model.kind(c) for c in model.calls[calls:]].count("article") == 7


async def test_claims_matched_by_embeddings_when_a_key_exists(client, user, db, mock, model):
    serve_site(mock)
    h = user["headers"]
    client.post(
        "/api/v1/credentials",
        json={"type": "openai", "name": "OpenAI key", "credentials": {"api_key": "sk-o", "model": "gpt-5"}},
        headers=h,
    )

    def embed(request):
        texts = json.loads(request.content)["input"]
        vectors = [[1.0, 0.0] if "phone" in t else [0.0, 1.0] for t in texts]
        return httpx.Response(200, json={"data": [{"index": i, "embedding": v} for i, v in enumerate(vectors)]})

    route = mock.post("https://api.openai.com/v1/embeddings").mock(side_effect=embed)
    site, _ = integrity_site(client, user)
    run = await run_integrity(db, site, user)
    assert route.called and route.calls[0].request.headers["authorization"] == "Bearer sk-o"
    assert "statement groups by embeddings (OpenAI · OpenAI key)" in stage(run)["detail"]
    assert "Two support numbers" in by_title(findings(db, run))


async def test_embedding_failure_falls_back_to_keywords(client, user, db, mock, model):
    serve_site(mock)
    h = user["headers"]
    client.post(
        "/api/v1/credentials",
        json={"type": "gemini", "name": "Gemini key", "credentials": {"api_key": "g", "model": "gemini-2.5-pro"}},
        headers=h,
    )
    mock.post(url__startswith="https://generativelanguage.googleapis.com/").respond(500)
    site, _ = integrity_site(client, user)
    run = await run_integrity(db, site, user)
    assert "by keywords" in stage(run)["detail"]
    assert any("Embedding failed (Gemini · Gemini key returned HTTP 500)" in e.message for e in run.log)
    assert "Two support numbers" in by_title(findings(db, run))


async def test_keywords_setting_skips_embeddings(client, user, db, mock, model):
    serve_site(mock)
    h = user["headers"]
    client.post(
        "/api/v1/credentials",
        json={"type": "openai", "name": "OpenAI key", "credentials": {"api_key": "sk-o", "model": "gpt-5"}},
        headers=h,
    )
    route = mock.post("https://api.openai.com/v1/embeddings").respond(500)
    site, _ = integrity_site(client, user, claim_matching="keywords")
    run = await run_integrity(db, site, user)
    assert not route.called and "by keywords" in stage(run)["detail"]


def test_claim_matching_setting_is_validated(client, user):
    h = user["headers"]
    site = make_site(client, user)
    body = {k: v for k, v in site.items() if k not in ("id", "created_at", "updated_at")}
    claude = client.post(
        "/api/v1/credentials",
        json={"type": "anthropic", "name": "Claude", "credentials": {"api_key": "k", "model": "m"}},
        headers=h,
    ).json()
    for value, code in [("nonsense", 422), (str(uuid.uuid4()), 422), (claude["id"], 422), ("keywords", 200)]:
        r = client.put(f"/api/v1/sites/{site['id']}", json={**body, "claim_matching": value}, headers=h)
        assert r.status_code == code, (value, r.text)


async def test_categories_follow_site_settings(client, user, db, mock, model):
    serve_site(mock)
    site, _ = integrity_site(client, user, categories=["C"])
    run = await run_integrity(db, site, user)
    assert {f.category for f in findings(db, run).values()} == {"C"}
    assert model.count("pair") == 0  # no T: no translation pass


async def test_codes_are_stable_and_triage_carries_over(client, user, db, mock, model):
    serve_site(mock)
    site, _ = integrity_site(client, user)
    first = await run_integrity(db, site, user)
    h = user["headers"]
    c = by_title(findings(db, first))["Two support numbers"]
    x = by_title(findings(db, first))["Internal note published"]
    client.patch(f"/api/v1/integrity-findings/{c.id}", json={"tier": "review", "triage_note": "Policy"}, headers=h)
    assert client.post(f"/api/v1/runs/{first.id}/triage/confirm", headers=h).status_code == 200

    model.extra = False  # the internal note is fixed on the site
    mock.routes.clear()
    serve_site(mock)
    second = await run_integrity(db, site, user, number=2, force_reevaluate=True)
    again = by_title(findings(db, second))
    assert again["Two support numbers"].code == c.code and again["Two support numbers"].tier == "review"
    assert again["Two support numbers"].carried_from == 1 and again["Two support numbers"].triage_note == "Policy"
    assert "Internal note published" not in again
    assert second.metrics["integrity"]["resolved"] == [x.code]

    rows = {
        r["key"]: r for r in client.get(f"/api/v1/runs/compare?a={first.id}&b={second.id}", headers=h).json()["rows"]
    }
    assert rows["integrity_firm"]["a"] is not None and rows["integrity_firm"]["b"] is None


async def test_triage_rules(client, user, db, mock, model):
    serve_site(mock)
    site, agents = integrity_site(client, user)
    run = await run_integrity(db, site, user)
    h = user["headers"]
    found = by_title(findings(db, run))
    url = lambda title: f"/api/v1/integrity-findings/{found[title].id}"  # noqa: E731

    assert client.patch(url("Invented quote"), json={"example": True}, headers=h).status_code == 422  # review tier
    r = client.patch(url("Internal note published"), json={"example": True}, headers=h)
    assert r.status_code == 200 and r.json()["example_rank"] == 1
    assert client.patch(url("Two support numbers"), json={"example": True}, headers=h).json()["example_rank"] == 2
    assert client.patch(url("Internal note published"), json={"tier": "drop"}, headers=h).json()["example_rank"] is None

    view = client.get(f"/api/v1/runs/{run.id}/integrity", headers=h).json()
    assert view["triage"] == {"status": "in_progress"} and view["purpose"] == "prospect"
    assert [c["name"] for c in view["help_centers"]] == ["US English", "Deutsch"]

    confirmed = client.post(f"/api/v1/runs/{run.id}/triage/confirm", headers=h).json()
    assert confirmed["triage"]["status"] == "confirmed"
    db.expire_all()
    m = db.get(AuditRun, run.id).metrics["integrity"]
    assert m["confirmed"] and m["firm"] + m["review"] + m["drop"] == m["candidates"]
    memory = db.get(Agent, UUID(agents["content_integrity"])).feedback_memory
    assert "Internal note published" in memory and "proposed firm, judged drop" in memory

    page_id = found["Two support numbers"].quotes[0]["page_id"]
    on_page = client.get(f"/api/v1/pages/{page_id}", headers=h).json()["integrity_findings"]
    assert "Two support numbers" in {f["title"] for f in on_page}

    client.patch(url("Two support numbers"), json={"triage_note": "Checked"}, headers=h)
    db.expire_all()
    assert db.get(AuditRun, run.id).triage == {"status": "in_progress"}

    csv = client.get(f"/api/v1/runs/{run.id}/integrity.csv", headers=h)
    assert csv.text.startswith("code,severity,category") and "Two support numbers" in csv.text

    from tests.conftest import make_user

    other = make_user(client)
    assert client.get(f"/api/v1/runs/{run.id}/integrity", headers=other["headers"]).status_code == 404


async def test_no_reviewer_means_no_candidates(client, user, db, mock):
    serve_site(mock)
    site = make_site(client, user)
    run = await run_integrity(db, site, user)
    assert stage(run)["status"] == "skipped" and stage(run)["detail"].startswith("Not reviewed: no agent is assigned")
    assert client.post(f"/api/v1/runs/{run.id}/triage/confirm", headers=user["headers"]).status_code == 409


async def test_failed_review_is_not_a_clean_result(client, user, db, mock, model):
    from hop_core.agents import AiProviderError

    import crawler
    import discovery
    import runner

    serve_site(mock)
    site, _ = integrity_site(client, user)

    async def always_400(api_key, model_name, request):
        raise AiProviderError("Anthropic returned HTTP 400: `temperature` is deprecated for this model.", 400)

    AiProviderRegistry.register("anthropic", always_400)
    run = await run_integrity(db, site, user)
    assert stage(run)["status"] == "failed" and "didn't review this audit" in stage(run)["detail"]
    assert findings(db, run) == {} and "integrity" not in run.metrics
    assert (run.triage or {}).get("status") != "confirmed"

    AiProviderRegistry.register("anthropic", model)
    async with discovery.client() as http:
        await runner.reanalyze(run.id, crawler.Control(), http=http)
    db.expire_all()
    run = db.get(AuditRun, run.id)
    assert stage(run)["status"] == "done" and run.metrics["integrity"]["candidates"] > 0


async def test_partial_failure_never_confirms_itself(client, user, db, mock, monkeypatch):
    from hop_core.agents import AiProviderError

    calls = []

    async def first_fails(api_key, model_name, request):
        calls.append(1)
        if len(calls) == 1:
            raise AiProviderError("overloaded", 400)
        return GenerationResponse(content='{"issues": [], "claims": []}', input_tokens=1, output_tokens=1)

    saved = AiProviderRegistry.get("anthropic")
    AiProviderRegistry.register("anthropic", first_fails)
    monkeypatch.setattr(review, "RETRY_DELAY", 0)
    monkeypatch.setattr(review, "AGENT_CONCURRENCY", 1)
    try:
        serve_site(mock)
        site, _ = integrity_site(client, user, categories=["C"])
        run = await run_integrity(db, site, user, analyses=["content_integrity"])
    finally:
        if saved:
            AiProviderRegistry.register("anthropic", saved)
    assert stage(run)["status"] == "done" and "1 failed requests" in stage(run)["detail"]
    assert run.triage == {"status": "pending"} and run.metrics["integrity"]["confirmed"] is False


async def test_reanalysis_keeps_a_triage(client, user, db, mock, model):
    import crawler
    import discovery
    import runner

    serve_site(mock)
    site, _ = integrity_site(client, user)
    run = await run_integrity(db, site, user)
    ids = {f.id for f in findings(db, run).values()}
    calls = len(model.calls)
    async with discovery.client() as http:
        await runner.reanalyze(run.id, crawler.Control(), http=http)
    db.expire_all()
    assert {f.id for f in findings(db, run).values()} == ids and len(model.calls) == calls


async def test_broken_links_last_until_a_link_check_finds_them_fixed(client, user, db, mock, model):
    serve_site(mock)
    site, _ = integrity_site(client, user)
    first = await run_integrity(db, site, user)
    broken = next(f for f in findings(db, first).values() if f.title.startswith(integrity.BROKEN_LINK))
    mock.routes.clear()
    serve_site(mock)
    second = await run_integrity(db, site, user, number=2, analyses=["content_integrity"])
    kept = findings(db, second)[broken.code]  # not checked this time: the last check still stands
    assert kept.title == broken.title and broken.code not in second.metrics["integrity"]["resolved"]
    page_ids = {str(p.id) for p in db.query(Page).filter(Page.run_id == second.id)}
    assert kept.quotes[0]["page_id"] in page_ids
    mock.routes.clear()
    serve_site(mock, nowhere=httpx.Response(200, html=html_page("Back again")))
    third = await run_integrity(db, site, user, number=3)
    assert broken.code in third.metrics["integrity"]["resolved"]
