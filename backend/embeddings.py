"""Text embeddings for matching statements across articles (content
integrity, pass 3). hop-core has no embeddings, so HOP Audit calls OpenAI or
Gemini directly with the organization's AI configuration (its API key; the
configuration's chat model is not used here). Anthropic has no embeddings
API: organizations with only Claude match statements by keywords instead.
"""

from dataclasses import dataclass
from uuid import UUID

import httpx
from hop_core.core.security import decrypt_credentials
from hop_core.models.credential import Credential
from sqlalchemy import select
from sqlalchemy.orm import Session

PROVIDERS = ("openai", "gemini")
MODELS = {"openai": "text-embedding-3-small", "gemini": "gemini-embedding-001"}
BATCH = {"openai": 512, "gemini": 100}  # texts per request
TIMEOUT = 60.0


class EmbeddingError(Exception):
    """Embedding failed; content integrity falls back to keywords."""


@dataclass
class Embedder:
    provider: str  # openai | gemini
    credential_name: str
    api_key: str

    @property
    def label(self) -> str:
        return f"{'OpenAI' if self.provider == 'openai' else 'Gemini'} · {self.credential_name}"

    async def embed(self, texts: list[str], http: httpx.AsyncClient | None = None) -> list[list[float]]:
        own = http is None
        http = http or httpx.AsyncClient(timeout=TIMEOUT)
        try:
            vectors: list[list[float]] = []
            size = BATCH[self.provider]
            for start in range(0, len(texts), size):
                vectors += await self._batch(http, texts[start : start + size])
            return vectors
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"{self.label}: {type(exc).__name__}") from exc
        finally:
            if own:
                await http.aclose()

    async def _batch(self, http: httpx.AsyncClient, texts: list[str]) -> list[list[float]]:
        if self.provider == "openai":
            response = await http.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": MODELS["openai"], "input": texts},
            )
            self._check(response)
            return [item["embedding"] for item in sorted(response.json()["data"], key=lambda d: d["index"])]
        model = MODELS["gemini"]
        response = await http.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents",
            headers={"x-goog-api-key": self.api_key},
            json={"requests": [{"model": f"models/{model}", "content": {"parts": [{"text": t}]}} for t in texts]},
        )
        self._check(response)
        return [e["values"] for e in response.json()["embeddings"]]

    def _check(self, response: httpx.Response) -> None:
        if response.status_code != 200:
            raise EmbeddingError(f"{self.label} returned HTTP {response.status_code}")


def choose(db: Session, organization_id: UUID, setting: str) -> Embedder | None:
    """The embedder for a site's ``claim_matching`` setting, or None for keywords.

    "auto" takes the organization's first OpenAI, then Gemini, configuration;
    a credential id takes that one; "keywords" (or nothing usable) is None.
    """
    if setting == "keywords":
        return None
    query = select(Credential).where(Credential.organization_id == organization_id, Credential.type.in_(PROVIDERS))
    if setting != "auto":
        try:
            query = query.where(Credential.id == UUID(setting))
        except ValueError:
            return None
    candidates = sorted(db.scalars(query), key=lambda c: (PROVIDERS.index(c.type), c.name))
    for credential in candidates:
        try:
            key = decrypt_credentials(credential.encrypted_data).get("api_key")
        except Exception:
            continue
        if key:
            return Embedder(credential.type, credential.name, key)
    return None
