from app.services.number_candidates import find_number_candidates


def _one(text: str) -> dict:
    found = find_number_candidates(text)
    assert len(found) == 1, found
    return found[0]


def test_plain_int():
    item = _one("150")
    assert item == {"span": "150", "value": 150.0, "unit": None, "derived": False}


def test_decimal():
    item = _one("3.14")
    assert item["value"] == 3.14 and item["unit"] is None and item["derived"] is False


def test_commas():
    assert _one("1,000")["value"] == 1000


def test_commas_and_cents():
    assert _one("1,234.50")["value"] == 1234.5


def test_dollars():
    item = _one("$150")
    assert item["span"] == "$150" and item["value"] == 150 and item["unit"] == "$"


def test_million_suffix():
    item = _one("$1.5M")
    assert item["span"] == "$1.5M" and item["value"] == 1_500_000 and item["unit"] == "$"


def test_k_suffix():
    item = _one("$2k")
    assert item["value"] == 2000 and item["unit"] == "$" and item["span"] == "$2k"


def test_million_dollars_phrase():
    item = _one("2 million dollars")
    assert item["span"] == "2 million dollars"
    assert item["value"] == 2_000_000 and item["unit"] == "$"


def test_bare_k():
    item = _one("500K")
    assert item["span"] == "500K" and item["value"] == 500_000 and item["unit"] is None


def test_percent_sign():
    item = _one("15%")
    assert item["value"] == 15 and item["unit"] == "%" and item["span"] == "15%"


def test_percent_word():
    item = _one("15 percent")
    assert item["span"] == "15 percent" and item["value"] == 15 and item["unit"] == "%"


def test_word_five():
    assert _one("five")["value"] == 5


def test_twenty_one():
    item = _one("twenty one")
    assert item["span"] == "twenty one" and item["value"] == 21


def test_hyphenated():
    item = _one("twenty-one")
    assert item["span"] == "twenty-one" and item["value"] == 21


def test_one_hundred_fifty():
    item = _one("one hundred fifty")
    assert item["span"] == "one hundred fifty" and item["value"] == 150


def test_dozen():
    item = _one("a dozen")
    assert item["span"] == "a dozen" and item["value"] == 12


def test_two_weeks_derives_days():
    found = find_number_candidates("two weeks")
    assert found == [
        {"span": "two weeks", "value": 2.0, "unit": "weeks", "derived": False},
        {"span": "two weeks", "value": 14.0, "unit": "days", "derived": True},
    ]


def test_plain_days_not_derived():
    item = _one("5 days")
    assert item == {"span": "5 days", "value": 5.0, "unit": "days", "derived": False}


def test_empty_text():
    assert find_number_candidates("nothing to see here") == []


def test_mixed_amount_and_duration():
    found = find_number_candidates("$150 and 5 days")
    assert {"span": "$150", "value": 150.0, "unit": "$", "derived": False} in found
    assert {"span": "5 days", "value": 5.0, "unit": "days", "derived": False} in found
    assert len(found) == 2


def test_hundred_and():
    assert _one("one hundred and fifty")["value"] == 150


def test_notice_phrase_keeps_verbatim_span():
    found = find_number_candidates("I gave two weeks notice")
    assert found[0]["span"] == "two weeks"
    assert found[1] == {"span": "two weeks", "value": 14.0, "unit": "days", "derived": True}


def test_hours():
    item = _one("3 hours")
    assert item["value"] == 3 and item["unit"] == "hours"


def test_dollar_word_million():
    item = _one("$2 million")
    assert item["value"] == 2_000_000 and item["unit"] == "$"


def test_currency_does_not_also_emit_inner_number():
    assert len(find_number_candidates("$1,500")) == 1
    assert find_number_candidates("$1,500")[0]["value"] == 1500


def test_one_week_derives_seven_days():
    found = find_number_candidates("1 week")
    assert found[0]["unit"] == "weeks" and found[0]["value"] == 1
    assert found[1]["derived"] is True and found[1]["value"] == 7 and found[1]["unit"] == "days"


def test_five_hundred_thousand():
    assert _one("five hundred thousand")["value"] == 500_000


def test_dedup_identical_spans():
    found = find_number_candidates("$150 then $150")
    assert found == [{"span": "$150", "value": 150.0, "unit": "$", "derived": False}]


def test_hour_abbreviations():
    for text in ("40h weeks", "like 40hrs/wk", "a 10 hr shift"):
        found = find_number_candidates(text)
        assert found and found[0]["unit"] == "hours", text


def test_grand():
    assert find_number_candidates("contract is 75 grand")[0]["value"] == 75000
