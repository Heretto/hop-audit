import pytest

from readability import band, language_of, measure, sentences, syllables

PLAIN = " ".join(["The cat sat on the mat. We like it a lot."] * 6)
HARD = " ".join(
    [
        "Administrators configuring organizational authentication must additionally consider the "
        "interoperability implications of federated identity providers."
    ]
    * 6
)


@pytest.mark.parametrize(
    "word, n",
    [("cat", 1), ("make", 1), ("table", 2), ("jumped", 1), ("wanted", 2), ("documentation", 5), ("free", 1)],
)
def test_english_syllables(word, n):
    assert syllables(word) == n


def test_other_languages_count_vowel_groups():
    assert syllables("wiederverwenden", "de") == 5
    assert syllables("café", "fr") == 2


def test_sentences_skip_headings_and_split_on_punctuation():
    text = "Publish a map\nOpen the map. Then choose Publish!\nNote: this is a long line without an end"
    assert sentences(text) == ["Open the map.", "Then choose Publish!", "Note: this is a long line without an end"]


def test_plain_text_scores_high_and_hard_text_low():
    plain, hard = measure(PLAIN), measure(HARD)
    assert plain.flesch > 90 and band(plain.flesch) == "plain"
    assert hard.flesch < 0 and band(hard.flesch) == "difficult"
    assert plain.grade < hard.grade
    assert plain.words_per_sentence == 5.5 and plain.sentences == 12 and plain.words == 66


def test_passive_voice_in_english():
    text = " ".join(["The file is uploaded by the server. You open the map. The map was quickly built."] * 4)
    r = measure(text)
    assert r.passive_pct == pytest.approx(66.7)


def test_language_formulas_and_unsupported_languages():
    de = measure(" ".join(["Der Hund läuft schnell nach Hause. Die Katze schläft."] * 6), "de-DE")
    assert de.flesch is not None and de.grade is None and de.passive_pct is None
    ja = measure(" ".join(["This page is ignored for Flesch."] * 10), "ja")
    assert ja.flesch is None and ja.words_per_sentence is not None
    assert language_of("fr-CA") == "fr" and language_of("") == "en"


def test_too_little_text_is_not_scored():
    r = measure("Short page. Only a few words here.")
    assert r.flesch is None and band(r.flesch) == "not measured"
