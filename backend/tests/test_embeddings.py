import json

import httpx
import pytest
import respx

import embeddings
from embeddings import Embedder, EmbeddingError


@pytest.fixture
def mock():
    with respx.mock(assert_all_called=False) as m:
        yield m


async def test_openai_embeddings_in_batches(mock, monkeypatch):
    monkeypatch.setitem(embeddings.BATCH, "openai", 2)

    def reply(request):
        body = json.loads(request.content)
        assert body["model"] == "text-embedding-3-small"
        data = [{"index": i, "embedding": [len(t), i]} for i, t in reversed(list(enumerate(body["input"])))]
        return httpx.Response(200, json={"data": data})

    route = mock.post("https://api.openai.com/v1/embeddings").mock(side_effect=reply)
    vectors = await Embedder("openai", "Key", "sk").embed(["a", "bb", "ccc"])
    assert vectors == [[1, 0], [2, 1], [3, 0]] and route.call_count == 2


async def test_gemini_embeddings(mock):
    route = mock.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"
    ).respond(200, json={"embeddings": [{"values": [0.1]}, {"values": [0.2]}]})
    assert await Embedder("gemini", "G", "g").embed(["a", "b"]) == [[0.1], [0.2]]
    assert route.calls[0].request.headers["x-goog-api-key"] == "g"


async def test_errors(mock):
    mock.post("https://api.openai.com/v1/embeddings").respond(401)
    with pytest.raises(EmbeddingError, match="OpenAI · Key returned HTTP 401"):
        await Embedder("openai", "Key", "sk").embed(["a"])


def test_choose(client, user, db):
    from uuid import UUID

    from hop_core.models.organization import OrganizationMember
    from hop_core.models.user import User

    h = user["headers"]
    member = db.query(User).filter(User.email == user["email"]).one()
    org = db.query(OrganizationMember).filter(OrganizationMember.user_id == member.id).one().organization_id
    assert embeddings.choose(db, org, "auto") is None  # no OpenAI or Gemini: keywords

    def add(type_, name):
        return client.post(
            "/api/v1/credentials",
            json={"type": type_, "name": name, "credentials": {"api_key": f"key-{name}", "model": "m"}},
            headers=h,
        ).json()["id"]

    gemini = add("gemini", "G")
    add("openai", "O")
    add("anthropic", "C")
    chosen = embeddings.choose(db, org, "auto")
    assert (chosen.provider, chosen.api_key) == ("openai", "key-O")  # OpenAI first
    assert embeddings.choose(db, org, gemini).provider == "gemini"
    assert embeddings.choose(db, org, "keywords") is None
    assert embeddings.choose(db, org, str(UUID(int=1))) is None
