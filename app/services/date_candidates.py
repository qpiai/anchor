"""Absolute and relative date spans for a later Choice question."""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_SMALL = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}

_ISO = re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})\b")
_MDY = re.compile(
    r"\b(?P<month>january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+"
    r"(?P<d>\d{1,2})(?:st|nd|rd|th)?(?:,)?\s+(?P<y>\d{4})\b",
    re.IGNORECASE,
)
_DMY = re.compile(
    r"\b(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(?P<month>january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(?P<y>\d{4})\b",
    re.IGNORECASE,
)
_RELATIVE = re.compile(
    r"\b(?P<span>today|tomorrow|yesterday|next\s+"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"in\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+days?)\b",
    re.IGNORECASE,
)


def _iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _next_weekday(today: date, weekday: int) -> date:
    delta = (weekday - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta)


def _relative_iso(span: str, today: date) -> str | None:
    text = re.sub(r"\s+", " ", span.strip().lower())
    if text == "today":
        return today.isoformat()
    if text == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    if text == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    next_day = re.fullmatch(r"next\s+([a-z]+)", text)
    if next_day and next_day.group(1) in _WEEKDAYS:
        return _next_weekday(today, _WEEKDAYS[next_day.group(1)]).isoformat()
    in_days = re.fullmatch(r"in\s+(\d+|[a-z]+)\s+days?", text)
    if in_days:
        raw = in_days.group(1)
        count = int(raw) if raw.isdigit() else _SMALL.get(raw)
        if count is None:
            return None
        return (today + timedelta(days=count)).isoformat()
    return None


def find_date_candidates(text: str, today: date | None = None) -> list[dict]:
    """Return deduped absolute and relative dates as ISO strings."""
    if not text:
        return []
    today = today or date.today()
    hits: list[tuple[int, int, str, str]] = []

    def add_absolute(match: re.Match[str], year: int, month: int, day: int) -> None:
        iso = _iso(year, month, day)
        if iso:
            hits.append((match.start(), match.end(), match.group(0), iso))

    for match in _ISO.finditer(text):
        add_absolute(match, int(match.group("y")), int(match.group("m")), int(match.group("d")))
    for pattern in (_MDY, _DMY):
        for match in pattern.finditer(text):
            month = _MONTHS[match.group("month").lower()]
            add_absolute(match, int(match.group("y")), month, int(match.group("d")))
    for match in _RELATIVE.finditer(text):
        span = match.group("span")
        iso = _relative_iso(span, today)
        if iso:
            hits.append((match.start(), match.end(), span, iso))

    hits.sort(key=lambda item: (-(item[1] - item[0]), item[0]))
    taken: list[tuple[int, int]] = []
    found: list[dict] = []
    seen: set[str] = set()
    for start, end, span, iso in hits:
        if any(not (end <= left or start >= right) for left, right in taken):
            continue
        taken.append((start, end))
        if iso in seen:
            continue
        seen.add(iso)
        found.append({"span": span, "iso": iso})
    found.sort(key=lambda item: text.lower().find(item["span"].lower()))
    return found


def year_choices(today: date | None = None, radius: int = 5) -> list[int]:
    today = today or date.today()
    return list(range(today.year - radius, today.year + radius + 1))


def month_name(month: int) -> str:
    return calendar.month_name[month]
