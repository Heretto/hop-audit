"""Statements articles make (claims), grouped by subject so the reviewer can
compare what different articles say about the same thing (content integrity,
pass 3).

Two ways to group: by keywords (subject words in common; no extra service)
or by embeddings (similar meaning; needs an OpenAI or Gemini key). Either
way, a group is only worth a request when it spans two articles and its
statements don't all say the same thing.
"""

import hashlib
import re
from dataclasses import dataclass
from uuid import UUID

import numpy as np

KEYWORD_OVERLAP = 0.5  # Jaccard of subject words
EMBEDDING_SIMILARITY = 0.82  # cosine
MAX_GROUP = 12  # statements sent per group
STOPWORDS = {
    "a", "an", "the", "of", "for", "to", "in", "on", "and", "or", "your", "you", "our", "is", "are", "be",
    "with", "by", "at", "from", "how", "what", "when", "can", "do", "does", "it", "its", "this", "that",
}  # fmt: skip


@dataclass
class Claim:
    page_id: UUID
    url: str
    slug: str
    center_id: UUID
    subject: str
    statement: str

    @property
    def text(self) -> str:
        """What embeddings compare."""
        return f"{self.subject}: {self.statement}"


def normalize(text: str) -> str:
    """For telling statements apart: quotes, spacing, case and end punctuation don't count."""
    return re.sub(r"\s+", " ", re.sub(r"[“”‘’\"']", "", text)).strip().rstrip(".!;:,").strip().lower()


def words(subject: str) -> frozenset[str]:
    """Subject words, lowercased and lightly stemmed (fees -> fee, paying -> pay)."""
    out = set()
    for w in re.findall(r"[^\W_]+", subject.lower()):
        if w in STOPWORDS:
            continue
        for suffix in ("ing", "ies", "es", "s"):
            if len(w) > len(suffix) + 2 and w.endswith(suffix):
                w = w[: -len(suffix)] + ("y" if suffix == "ies" else "")
                break
        out.add(w)
    return frozenset(out)


class _Sets:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def join(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)

    def groups(self) -> list[list[int]]:
        out: dict[int, list[int]] = {}
        for i in range(len(self.parent)):
            out.setdefault(self.find(i), []).append(i)
        return list(out.values())


def keyword_groups(claims: list[Claim]) -> list[list[Claim]]:
    """Claims whose subjects share most of their words. Only claims that share
    a word are compared, so this stays fast on large sites."""
    tokens = [words(c.subject) for c in claims]
    index: dict[str, list[int]] = {}
    for i, t in enumerate(tokens):
        for w in t:
            index.setdefault(w, []).append(i)
    sets = _Sets(len(claims))
    for i, t in enumerate(tokens):
        seen = {j for w in t for j in index[w] if j > i}
        for j in seen:
            union = len(t | tokens[j])
            if union and len(t & tokens[j]) / union >= KEYWORD_OVERLAP:
                sets.join(i, j)
    return [[claims[i] for i in g] for g in sets.groups()]


def embedding_groups(claims: list[Claim], vectors: list[list[float]]) -> list[list[Claim]]:
    """Claims whose subject and statement mean nearly the same (cosine similarity)."""
    if not claims:
        return []
    m = np.asarray(vectors, dtype=np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-12
    sets = _Sets(len(claims))
    for start in range(0, len(m), 1024):  # chunked: memory stays small on large sites
        block = m[start : start + 1024] @ m.T
        rows, cols = np.nonzero(block >= EMBEDDING_SIMILARITY)
        for r, c in zip(rows.tolist(), cols.tolist(), strict=True):
            if start + r < c:
                sets.join(start + r, c)
    return [[claims[i] for i in g] for g in sets.groups()]


def worth_asking(group: list[Claim]) -> bool:
    """Two articles or more, and not every statement the same: identical
    repetition is not an issue (it may even be single-sourced content)."""
    return len({c.page_id for c in group}) > 1 and len({normalize(c.statement) for c in group}) > 1


def trim(group: list[Claim]) -> list[Claim]:
    """At most MAX_GROUP statements, one per distinct wording first."""
    seen, first, rest = set(), [], []
    for c in group:
        (rest if normalize(c.statement) in seen else first).append(c)
        seen.add(normalize(c.statement))
    return (first + rest)[:MAX_GROUP]


def group_key(group: list[Claim]) -> str:
    """Same statements on the same pages: same key, so the verdict can be reused."""
    material = sorted(f"{c.url}\n{normalize(c.statement)}" for c in group)
    return hashlib.sha256("\n\n".join(material).encode()).hexdigest()
