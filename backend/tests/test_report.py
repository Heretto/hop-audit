"""The full findings report and its exports, from a triaged run of the fake site."""

import json
from io import BytesIO

import pytest
from docx import Document

import pdf
from tests.test_integrity import (  # noqa: F401  fixtures
    PHONE_A,
    integrity_site,
    mock,
    model,
    run_integrity,
    serve_site,
)
from tests.test_runs import make_site


@pytest.fixture
async def triaged(client, user, db, mock, model):  # noqa: F811  (fixtures from test_integrity)
    serve_site(mock)
    site, _ = integrity_site(client, user)
    run = await run_integrity(db, site, user, analyses=["readability", "links", "seo", "content_integrity"])
    assert client.post(f"/api/v1/runs/{run.id}/triage/confirm", headers=user["headers"]).status_code == 200
    return run


def cell_text(cell) -> str:
    return "".join(r["text"] for r in cell)


async def test_report_follows_the_skill_structure(client, user, triaged):
    r = client.get(f"/api/v1/runs/{triaged.id}/report", headers=user["headers"]).json()
    assert r["ready"] and r["title"] == "X Help — Content Integrity Review"
    assert r["author"] == user["email"]  # who confirmed the triage, without a sender
    ids = [s["id"] for s in r["sections"]]
    assert ids == ["summary", "categories", "contradictions", "translation", "remaining", "review"]
    sections = {s["id"]: s for s in r["sections"]}

    summary = sections["summary"]
    assert summary["lead"].startswith("A review of 7 articles across X Help's two public help centers found")
    assert "listed for review and excluded from every total" in summary["lead"]
    centers = summary["tables"][0]
    assert [cell_text(row[0]) for row in centers["rows"]] == ["US English", "Deutsch"]
    assert cell_text(centers["total"][2]) == "7"

    categories = sections["categories"]["tables"][0]
    labels = [cell_text(row[0]) for row in categories["rows"]]
    assert "German and English versions don't match" in labels and "Contradictions between articles" in labels
    assert cell_text(categories["total"][1]) == str(r["counts"]["firm"])
    assert sections["categories"]["after"].startswith("High: a customer could act on wrong information")

    conflict = sections["contradictions"]["tables"][0]["rows"][0]
    assert [c["label"] for c in sections["contradictions"]["tables"][0]["columns"]][-1] == "Conflicting text (article)"
    assert cell_text(conflict[3]) == "Two support numbers"
    assert {"kind": "quote", "text": PHONE_A} in conflict[4] and {"kind": "slug", "text": "authoring/a"} in conflict[4]
    assert conflict[1] == [{"kind": "sev", "text": "High"}]

    translation = sections["translation"]
    assert translation["title"].startswith("German and English versions don't match (")
    assert [c["label"] for c in translation["tables"][0]["columns"]][3:] == ["English", "German (article)"]

    remaining = sections["remaining"]
    assert [t["heading"].split(" (")[0] for t in remaining["tables"]] == [
        "Links and duplicates",
        "Structure and publishing errors",
    ]
    assert "Internal note published" in json.dumps(remaining)

    review = sections["review"]
    assert review["lead"] == "These may be accurate depending on internal policy, so they are not counted."
    assert "Invented quote" in json.dumps(review)
    assert {m["label"] for m in r["appendix"]} == {
        "Avg Flesch Reading Ease",
        "Pages under Flesch 50",
        "Broken links",
        "SEO issues",
    }


async def test_report_follows_the_tiers_as_they_stand(client, user, db, mock, model):  # noqa: F811
    serve_site(mock)
    site, _ = integrity_site(client, user)
    run = await run_integrity(db, site, user)
    h = user["headers"]
    r = client.get(f"/api/v1/runs/{run.id}/report", headers=h).json()
    assert r["ready"] and not r["confirmed"]  # no confirmed triage needed
    assert r["author"] == ""  # nobody confirmed, no sender

    findings = client.get(f"/api/v1/runs/{run.id}/integrity", headers=h).json()["findings"]
    two = next(f for f in findings if f["title"] == "Two support numbers")
    note = next(f for f in findings if f["title"] == "Internal note published")
    client.patch(f"/api/v1/integrity-findings/{two['id']}", json={"tier": "drop"}, headers=h)
    client.patch(f"/api/v1/integrity-findings/{note['id']}", json={"tier": "review"}, headers=h)
    r = client.get(f"/api/v1/runs/{run.id}/report", headers=h).json()
    text = json.dumps(r["sections"])
    assert "Two support numbers" not in text  # dropped: left out
    assert "contradictions" not in [s["id"] for s in r["sections"]]
    review = next(s for s in r["sections"] if s["id"] == "review")
    assert "Internal note published" in json.dumps(review)  # for review: listed, not counted
    assert r["counts"]["review"] == sum(1 for f in findings if f["tier"] == "review") + 1
    assert client.get(f"/api/v1/runs/{run.id}/report.docx", headers=h).status_code == 200


async def test_no_report_without_content_integrity(client, user, db, mock):  # noqa: F811
    serve_site(mock)
    site = make_site(client, user)
    run = await run_integrity(db, site, user, analyses=["links"])
    h = user["headers"]
    r = client.get(f"/api/v1/runs/{run.id}/report", headers=h).json()
    assert not r["ready"] and "Content integrity hasn't run" in r["reason"] and r["sections"] == []
    for export in ("report.pdf", "report.docx"):
        assert client.get(f"/api/v1/runs/{run.id}/{export}", headers=h).status_code == 409


async def test_report_as_word(client, user, triaged):
    r = client.get(f"/api/v1/runs/{triaged.id}/report.docx", headers=user["headers"])
    assert r.headers["content-disposition"] == 'attachment; filename="x-help-audit-1-report.docx"'
    doc = Document(BytesIO(r.content))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "X Help — Content Integrity Review" in text and "Items for review" in text
    first = doc.tables[0].rows[0].cells
    assert [c.text for c in first] == ["Help center", "Site", "Articles reviewed"]
    assert first[0]._tc.tcPr.xml.count('w:fill="EDF3FA"') == 1  # shaded header row


async def test_report_as_pdf(client, user, triaged, monkeypatch):
    seen = {}

    async def fake(html):
        seen["html"] = html
        return pdf.Rendered(b"%PDF-1.7 fake")

    monkeypatch.setattr(pdf, "document", fake)
    r = client.get(f"/api/v1/runs/{triaged.id}/report.pdf", headers=user["headers"])
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and r.headers["content-type"] == "application/pdf"
    assert "<h1>X Help — Content Integrity Review</h1>" in seen["html"]
    assert 'src="data:image/png;base64,' in seen["html"]  # the wordmark travels with the page
    assert '<span class="sev High">High</span>' in seen["html"]

    async def unavailable(html):
        raise pdf.PdfUnavailable("PDFs need Chromium on the server")

    monkeypatch.setattr(pdf, "document", unavailable)
    r = client.get(f"/api/v1/runs/{triaged.id}/report.pdf", headers=user["headers"])
    assert r.status_code == 503 and "Chromium" in r.json()["detail"]


async def test_full_audit_json(client, user, triaged):
    r = client.get(f"/api/v1/runs/{triaged.id}/audit.json", headers=user["headers"])
    data = r.json()
    assert r.headers["content-disposition"].endswith('audit-1-audit.json"')
    assert data["site"]["name"] == "X Help" and len(data["help_centers"]) == 2
    assert data["run"]["number"] == 1 and "stages" not in data["run"]
    assert len(data["pages"]) >= 7 and {"url", "flesch", "score"} <= set(data["pages"][0])
    tiers = {f["tier"] for f in data["integrity_findings"]}
    assert tiers <= {"firm", "review", "drop"} and "review" in tiers


async def test_other_organizations_get_404(client, triaged):
    from tests.conftest import make_user

    other = make_user(client)["headers"]
    for path in ("report", "report.docx", "report.pdf", "audit.json"):
        assert client.get(f"/api/v1/runs/{triaged.id}/{path}", headers=other).status_code == 404
