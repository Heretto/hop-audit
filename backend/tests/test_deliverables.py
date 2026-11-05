"""Prospect deliverables: the Collateral Writer's copy, the one-sheets and the hand-off."""

import base64
import json

import pytest
from hop_core.agents import AiProviderError, AiProviderRegistry, GenerationResponse

import pdf
from tests.test_integrity import (  # noqa: F401  fixtures
    integrity_site,
    mock,
    model,
    run_integrity,
    serve_site,
)
from tests.test_runs import make_site

COPY = {
    "industry": "Software",
    "headline_line1": "One answer, in every",
    "headline_line2": "language, on every page",
    "subhead_lead": "Structured content means a fix made once appears everywhere it's used.",
    "exec_headline": "Support content needs a single source",
    "lead_sentence": "Structured content is critical to controlling cost; without it, every answer is fixed twice.",
    "why": [
        {"imperative": "Cost", "lead": "Customers act on it.", "text": "Two support numbers send calls astray.",
         "codes": ["C-01", "Z-99"]},
        {"imperative": "Customer Retention", "lead": "Translations drift.", "text": "German readers get the "
         "opposite answer.", "codes": ["T-01"]},
        {"imperative": "Risk", "ai": True, "lead": "AI assistants repeat it.", "text": "Answers inherit every "
         "conflict.", "codes": []},
    ],
    "impacts": [
        {"tone": "cost", "label": "Cost to serve", "title": "Customers call the wrong number",
         "body": "Two numbers for one support line.", "evidence": "“555-0146” and “555-0164”.", "codes": ["C-01"]},
    ],
}  # fmt: skip


@pytest.fixture
def writer(model):  # noqa: F811
    """The integrity fake, answering the Collateral Writer's request with COPY."""
    replies = [json.dumps(COPY)]

    async def fake(api_key, model_name, request):
        if "Write the copy for two one-sheets" in request.user_prompt:
            writer.prompts.append(request.user_prompt)
            reply = replies[0] if replies else json.dumps(COPY)
            if isinstance(reply, Exception):
                raise reply
            return GenerationResponse(content=reply, input_tokens=100, output_tokens=50)
        return await model(api_key, model_name, request)

    writer.prompts, writer.replies = [], replies
    AiProviderRegistry.register("anthropic", fake)
    return writer


async def prospect_run(client, user, db, mock, confirm=True, picks=3):  # noqa: F811
    serve_site(mock)
    site, agents = integrity_site(client, user)
    h = user["headers"]
    cred = client.get("/api/v1/credentials", headers=h).json()
    cred_id = next(c["id"] for c in (cred.get("items", cred) if isinstance(cred, dict) else cred))
    client.put(f"/api/v1/agents/{agents['deliverables']}", json={"ai_configuration_id": cred_id}, headers=h)
    run = await run_integrity(db, site, user)
    view = client.get(f"/api/v1/runs/{run.id}/integrity", headers=h).json()
    firm = [f for f in view["findings"] if f["tier"] == "firm"]
    for f in firm[:picks]:
        client.patch(f"/api/v1/integrity-findings/{f['id']}", json={"example": True}, headers=h)
    if confirm:
        assert client.post(f"/api/v1/runs/{run.id}/triage/confirm", headers=h).status_code == 200
    return run, site


def url(run, rest=""):
    return f"/api/v1/runs/{run.id}/deliverables{rest}"


async def test_deliverables_build_before_the_triage_is_confirmed(client, user, db, mock, writer):  # noqa: F811
    run, _ = await prospect_run(client, user, db, mock, confirm=False)
    h = user["headers"]
    v = client.get(url(run), headers=h).json()
    assert v["available"] and v["reason"] == ""
    assert {s["key"]: s["status"] for s in v["steps"]} == {
        "assess": "done", "triage": "now", "build": "now", "handoff": "todo",
    }  # fmt: skip
    assert next(s for s in v["steps"] if s["key"] == "triage")["detail"].endswith("· not confirmed yet")
    assert v["internal_note"].startswith("X Help Help Center Content Integrity Review")

    v = client.post(url(run, "/build"), headers=h).json()
    assert v["copy"]["headline_line1"] == "One answer, in every"
    triage = next(c for c in v["checklist"] if c["key"] == "triage")
    assert not triage["ok"] and triage["text"].startswith("The triage isn't confirmed yet")
    assert client.get(url(run, "/lead.html"), headers=h).status_code == 200

    assert client.post(f"/api/v1/runs/{run.id}/triage/confirm", headers=h).status_code == 200
    v = client.get(url(run), headers=h).json()
    assert next(c for c in v["checklist"] if c["key"] == "triage")["ok"]
    assert "· confirmed" in next(s for s in v["steps"] if s["key"] == "triage")["detail"]


async def test_no_deliverables_without_content_integrity(client, user, db, mock):  # noqa: F811
    serve_site(mock)
    site, _ = integrity_site(client, user)
    run = await run_integrity(db, site, user, analyses=["links"])
    h = user["headers"]
    v = client.get(url(run), headers=h).json()
    assert not v["available"] and "Content integrity hasn't run" in v["reason"]
    assert v["internal_note"] == "" and not v["report_ready"]
    assert client.post(url(run, "/build"), headers=h).status_code == 409


async def test_own_docs_sites_have_no_deliverables(client, user, db, mock):  # noqa: F811
    serve_site(mock)
    site = make_site(client, user)
    run = await run_integrity(db, site, user, analyses=["links"])
    v = client.get(url(run), headers=user["headers"]).json()
    assert not v["available"] and "prospect reviews" in v["reason"]
    r = client.patch(url(run), json={"prospect": {"company": "X"}}, headers=user["headers"])
    assert r.status_code == 409


async def test_build_writes_the_copy_and_the_sheets(client, user, db, mock, writer):  # noqa: F811
    run, _ = await prospect_run(client, user, db, mock)
    h = user["headers"]
    client.patch(url(run), json={"prospect": {"company": "Lumen", "sender_name": "Pat", "sender_title": "AE"}},
                 headers=h)  # fmt: skip
    v = client.post(url(run, "/build"), headers=h).json()

    prompt = writer.prompts[0]
    assert "Prospect: Lumen" in prompt and "Confirmed findings:" in prompt and "- C-01 · High" in prompt
    assert v["agent_name"] == "Collateral Writer" and v["built_by"] == user["email"]
    assert v["copy"]["why"][0]["codes"] == ["C-01"]  # unknown codes are dropped
    assert v["copy"]["headline_line1"] == "One answer, in every"
    assert {s["key"]: s["status"] for s in v["steps"]}["build"] == "done"
    assert v["problems"] == []
    fits = next(c for c in v["checklist"] if c["key"] == "fits")
    assert not fits["ok"] and fits["text"] == "The one-sheets are measured when their previews load on this page."
    assert len(v["examples"]) == 3
    assert v["internal_note"].startswith("Lumen Help Center Content Integrity Review: what it assessed")
    assert "Result: " in v["internal_note"] and "Contradictions between articles:" in v["internal_note"]

    lead = client.get(url(run, "/lead.html"), headers=h)
    assert lead.headers["content-type"].startswith("text/html")
    html = lead.text
    assert "Content Integrity Snapshot · Lumen Help Center" in html
    assert "One answer, in every<br>language, on every page" in html
    assert "Structured content means a fix made once appears everywhere it&#39;s used. A review of Lumen&#39;s" in html
    assert "Customers act on it." in html and "Lumen logo" in html  # no logo: the labelled placeholder
    assert "Pat, AE" in html and "[email]" in html
    assert "Heretto is not affiliated with Lumen" in html
    assert "German and English don&#39;t match" in html  # the T category, named by language

    exec_ = client.get(url(run, "/exec.html"), headers=h).text
    assert "Executive Brief · Lumen Help Center Content" in exec_
    assert "Support content needs a single source" in exec_ and "Customers call the wrong number" in exec_
    assert "Worth 20 minutes to walk through what we found?" in exec_
    assert client.get(url(run, "/other.html"), headers=h).status_code == 404


async def test_editing_the_copy_and_the_checklist(client, user, db, mock, writer):  # noqa: F811
    run, _ = await prospect_run(client, user, db, mock)
    h = user["headers"]
    client.post(url(run, "/build"), headers=h)
    copy = {**COPY, "exec_headline": "Your help center needs one source, everywhere you sell"}
    v = client.patch(url(run), json={"copy": copy, "heights": {"lead": 1000, "exec": 1100}}, headers=h).json()
    assert v["copy"]["exec_headline"].startswith("Your help center")
    assert any("Executive headline is" in p for p in v["problems"])
    assert 'The executive headline says "you" or "your"' in v["problems"]
    checks = {c["key"]: c for c in v["checklist"]}
    assert not checks["fits"]["ok"] and "executive brief by 44 px" in checks["fits"]["text"]
    assert not checks["placeholders"]["ok"] and "prospect logo" in checks["placeholders"]["text"]
    assert checks["counts"]["ok"] and checks["examples"]["ok"]
    assert checks["spot_checked"]["toggle"] and len(checks["spot_checked"]["quotes"]) >= 3

    v = client.patch(url(run), json={"heights": {"exec": 1040}, "spot_checked": True, "marketing_ok": True},
                     headers=h).json()  # fmt: skip
    checks = {c["key"]: c for c in v["checklist"]}
    assert checks["fits"]["ok"] and checks["fits"]["text"] == (
        "Both one-sheets fit on one page (lead 1,000 px, exec 1,040 px of 1,056)."
    )
    assert checks["spot_checked"]["ok"] and checks["marketing_ok"]["ok"]
    assert "no overflow" in {s["key"]: s["detail"] for s in v["steps"]}["build"]

    # A later change to the triage shows as a mismatch.
    findings = client.get(f"/api/v1/runs/{run.id}/integrity", headers=h).json()["findings"]
    firm = next(f for f in findings if f["tier"] == "firm" and f["example_rank"] is None)
    client.patch(f"/api/v1/integrity-findings/{firm['id']}", json={"tier": "drop"}, headers=h)
    client.post(f"/api/v1/runs/{run.id}/triage/confirm", headers=h)
    checks = {c["key"]: c for c in client.get(url(run), headers=h).json()["checklist"]}
    assert not checks["counts"]["ok"] and "triage changed" in checks["counts"]["text"]


async def test_prospect_logo(client, user, db, mock, writer):  # noqa: F811
    run, _ = await prospect_run(client, user, db, mock)
    h = user["headers"]
    client.post(url(run, "/build"), headers=h)
    png = "data:image/png;base64," + base64.b64encode(b"\x89PNG fake").decode()
    v = client.put(url(run, "/logo"), json={"data_uri": png}, headers=h).json()
    assert v["prospect"]["logo"] == png
    assert f'src="{png}"' in client.get(url(run, "/lead.html"), headers=h).text
    assert client.put(url(run, "/logo"), json={"data_uri": "data:text/html;base64,PGI+"}, headers=h).status_code == 422
    assert client.delete(url(run, "/logo"), headers=h).json()["prospect"]["logo"] is None


async def test_sheet_pdfs_and_overflow(client, user, db, mock, writer, monkeypatch):  # noqa: F811
    run, _ = await prospect_run(client, user, db, mock)
    h = user["headers"]
    client.post(url(run, "/build"), headers=h)
    heights = iter([1000, 1100])

    async def fake(html):
        return pdf.Rendered(b"%PDF-1.7 sheet", next(heights))

    monkeypatch.setattr(pdf, "sheet", fake)
    r = client.get(url(run, "/lead.pdf"), headers=h)
    assert r.status_code == 200 and r.headers["content-disposition"].endswith('content-integrity-snapshot.pdf"')
    r = client.get(url(run, "/exec.pdf"), headers=h)
    assert r.status_code == 409 and "overflows the page by 44 px" in r.json()["detail"]
    assert client.get(url(run), headers=h).json()["heights"] == {"lead": 1000, "exec": 1100}

    async def unavailable(html):
        raise pdf.PdfUnavailable("PDFs need Chromium on the server")

    monkeypatch.setattr(pdf, "sheet", unavailable)
    assert client.get(url(run, "/lead.pdf"), headers=h).status_code == 503


async def test_writer_failures_are_reported(client, user, db, mock, writer):  # noqa: F811
    run, site = await prospect_run(client, user, db, mock)
    h = user["headers"]
    writer.replies[:] = [AiProviderError("Anthropic returned HTTP 400: bad request", 400)]
    r = client.post(url(run, "/build"), headers=h)
    assert r.status_code == 502 and "Collateral Writer couldn't write the copy" in r.json()["detail"]
    assert "HTTP 400" in r.json()["detail"]

    writer.replies[:] = ['{"why": "not a list"}']
    r = client.post(url(run, "/build"), headers=h)
    assert r.status_code == 502 and "expected fields" in r.json()["detail"]

    body = {k: v for k, v in site.items() if k not in ("id", "created_at", "updated_at")}
    agents = client.get(f"/api/v1/sites/{site['id']}", headers=h).json()["agent_assignments"]
    body.update(purpose="prospect", agent_assignments={**agents, "deliverables": None})
    client.put(f"/api/v1/sites/{site['id']}", json=body, headers=h)
    r = client.post(url(run, "/build"), headers=h)
    assert r.status_code == 502 and "no agent is assigned" in r.json()["detail"]
