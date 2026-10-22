import uuid

from claims import Claim, embedding_groups, group_key, keyword_groups, trim, words, worth_asking

CENTER = uuid.uuid4()


def claim(subject, statement, page=None):
    page = page or uuid.uuid4()
    return Claim(page, f"https://x/{page}", str(page), CENTER, subject, statement)


def test_words_are_lowercased_stemmed_and_without_stopwords():
    assert words("The late payment fees") == {"late", "payment", "fee"}
    assert words("Paying by card") == {"pay", "card"}
    assert words("Policies") == {"policy"}


def test_keyword_groups():
    a = claim("late payment fee", "The fee is $10.")
    b = claim("Late payment fees", "The fee is $15.")
    c = claim("support phone number", "Call 555-0146.")
    d = claim("support phone", "Call 555-0164.")
    e = claim("refund window", "Refunds within 30 days.")
    groups = sorted((sorted(x.statement for x in g) for g in keyword_groups([a, b, c, d, e])), key=len)
    assert ["Call 555-0146.", "Call 555-0164."] in groups
    assert ["The fee is $10.", "The fee is $15."] in groups
    assert ["Refunds within 30 days."] in groups


def test_embedding_groups():
    a, b, c = claim("x", "one"), claim("y", "two"), claim("z", "three")
    groups = embedding_groups([a, b, c], [[1, 0, 0], [0.99, 0.1, 0], [0, 0, 1]])
    assert sorted(len(g) for g in groups) == [1, 2]
    assert embedding_groups([], []) == []


def test_worth_asking_and_trim():
    page = uuid.uuid4()
    assert not worth_asking([claim("fee", "$10", page), claim("fee", "$15", page)])  # one article
    assert not worth_asking([claim("fee", "The fee is $10."), claim("fee", "the fee is  $10")])  # same statement
    assert worth_asking([claim("fee", "$10"), claim("fee", "$15")])
    many = [claim("fee", "$10")] * 10 + [claim("fee", f"${i}") for i in range(10)]
    trimmed = trim(many)
    assert len(trimmed) == 12 and len({c.statement for c in trimmed}) == 11  # distinct wordings first


def test_group_key_ignores_order_and_spacing():
    a, b = claim("fee", "The fee is $10."), claim("fee", "The fee is $15.")
    same_b = Claim(b.page_id, b.url, b.slug, b.center_id, "other subject", "the fee is  $15.")
    assert group_key([a, b]) == group_key([same_b, a])
    assert group_key([a, b]) != group_key([a, claim("fee", "The fee is $20.")])
