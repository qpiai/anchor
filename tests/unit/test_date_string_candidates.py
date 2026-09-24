from datetime import date

from app.services.date_candidates import find_date_candidates
from app.services.string_candidates import find_string_candidates


def test_relative_and_absolute_dates():
    today = date(2026, 9, 24)
    found = find_date_candidates(
        "Meet tomorrow, next Monday, or in 3 days. Also 2024-03-15.",
        today=today,
    )
    by_span = {item["span"].lower(): item["iso"] for item in found}
    assert by_span["tomorrow"] == "2026-09-25"
    assert by_span["next monday"] == "2026-09-28"
    assert by_span["in 3 days"] == "2026-09-27"
    assert by_span["2024-03-15"] == "2024-03-15"


def test_invalid_calendar_date_dropped():
    assert find_date_candidates("2024-02-31", today=date(2026, 1, 1)) == []


def test_string_spans_and_empty():
    found = find_string_candidates('Write ada@example.com about ABC-1234 and "north wing".')
    values = [item["value"] for item in found]
    assert "ada@example.com" in values
    assert "ABC-1234" in values
    assert "north wing" in values
    assert find_string_candidates("nothing here") == []
