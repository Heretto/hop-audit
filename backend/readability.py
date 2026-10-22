"""Readability measured from a page's text.

Flesch Reading Ease and its language adaptations all take the same two
inputs (words per sentence, syllables per word), so one counter feeds every
formula. Languages written without spaces or vowels-as-syllables (Japanese,
Chinese, Korean, Thai…) have no Flesch formula; those pages get no score
rather than a meaningless one. Passive voice is detected for English only.
"""

import re
from dataclasses import asdict, dataclass

# (constant, words-per-sentence weight, syllables-per-word weight)
FORMULAS = {
    "en": (206.835, 1.015, 84.6),  # Flesch
    "de": (180.0, 1.0, 58.5),  # Amstad
    "fr": (207.0, 1.015, 73.6),  # Kandel & Moles
    "es": (206.84, 1.02, 60.0),  # Fernández Huerta (per-100-word form rewritten per word)
    "it": (217.0, 1.3, 60.0),  # Flesch–Vacca
    "nl": (206.835, 0.93, 77.0),  # Douma
    "pt": (248.835, 1.015, 84.6),  # Martins et al.
}
VOWELS = "aeiouyàáâãäåæèéêëìíîïòóôõöøùúûüýÿœ"
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[\"'“‘(\[]?[A-ZÀ-ÖØ-Þ0-9])")
WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.UNICODE)
TO_BE = r"(?:am|is|are|was|were|be|been|being|get|gets|got|gotten)"
IRREGULAR = (
    "built|chosen|done|drawn|driven|found|given|held|hidden|kept|known|left|lost|made|meant|paid|read|run|"
    "seen|sent|set|shown|sold|spent|taken|told|thrown|understood|written|broken|put|cut|shut|split|spread"
)
PASSIVE = re.compile(rf"\b{TO_BE}\s+(?:\w+ly\s+)?(?:\w+ed|{IRREGULAR})\b", re.IGNORECASE)
MIN_WORDS = 30  # fewer and the score says more about the sample than the page
HEADING_WORDS = 4  # unpunctuated lines this short are headings and labels, not sentences


@dataclass
class Readability:
    flesch: float | None
    grade: float | None  # Flesch–Kincaid grade level; English only
    words_per_sentence: float | None
    passive_pct: float | None  # English only
    sentences: int
    words: int

    def as_json(self) -> dict:
        return asdict(self)


def language_of(tag: str) -> str:
    return (tag or "en").split("-")[0].lower()


def syllables(word: str, language: str = "en") -> int:
    word = word.lower()
    groups = re.findall(f"[{VOWELS}]+", word)
    count = len(groups)
    if language == "en":
        if word.endswith("e") and not word.endswith(("le", "ee", "ye")) and count > 1:
            count -= 1  # silent e: "make", "home"
        if word.endswith(("ed", "es")) and count > 1 and not re.search(r"[td]ed$|[sxz]es$|[cs]hes$", word):
            count -= 1  # "jumped", "makes"
    return max(1, count)


def sentences(text: str) -> list[str]:
    """Each line is a block; short unpunctuated lines (headings, labels) are skipped."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line.split()) < HEADING_WORDS and not line.endswith((".", "!", "?", ":", "…")):
            continue
        out += [s for s in SENTENCE_END.split(line) if WORD.search(s)]
    return out


def measure(text: str, language_tag: str = "en") -> Readability:
    language = language_of(language_tag)
    found = sentences(text)
    words = [w for s in found for w in WORD.findall(s)]
    n_sentences, n_words = len(found), len(words)
    if n_words < MIN_WORDS or not n_sentences:
        return Readability(None, None, None, None, n_sentences, n_words)
    wps = n_words / n_sentences
    passive = None
    if language == "en":
        passive = round(100 * sum(1 for s in found if PASSIVE.search(s)) / n_sentences, 1)
    formula = FORMULAS.get(language)
    if formula is None:
        return Readability(None, None, round(wps, 1), passive, n_sentences, n_words)
    spw = sum(syllables(w, language) for w in words) / n_words
    constant, a, b = formula
    flesch = round(constant - a * wps - b * spw, 1)
    grade = round(0.39 * wps + 11.8 * spw - 15.59, 1) if language == "en" else None
    return Readability(flesch, grade, round(wps, 1), passive, n_sentences, n_words)


def band(flesch: float | None) -> str:
    """The label the dashboard uses: plain, fairly difficult, difficult."""
    if flesch is None:
        return "not measured"
    if flesch >= 60:
        return "plain"
    if flesch >= 50:
        return "fairly difficult"
    return "difficult"
