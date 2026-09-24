"""Pull numeric spans out of text for a later Choice question."""

from __future__ import annotations

import re

_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
_MULTS = {"k": 1_000, "thousand": 1_000, "grand": 1_000, "m": 1_000_000, "million": 1_000_000, "b": 1_000_000_000, "billion": 1_000_000_000}

_UNIT_WORDS = (
    "percent|dollars?|usd|days?|hours?|hrs?|h|weeks?|months?|years?|minutes?"
)
_WORD = (
    r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundred|thousand|million|billion|dozen"
)

_NUMERIC = re.compile(
    rf"""
    (?<![A-Za-z0-9])
    (?P<span>
        (?P<currency>\$\s*)?
        (?P<number>\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?)
        (?:\s*(?P<mult>k|m|b|grand|thousand|million|billion))?
        (?:\s*(?P<unit>%|{_UNIT_WORDS}))?
    )
    (?![A-Za-z0-9])
    """,
    re.IGNORECASE | re.VERBOSE,
)

_WORDS = re.compile(
    rf"""
    (?<![A-Za-z0-9])
    (?P<span>
        (?:half\s+)?(?:a|an)\s+dozen
        |
        dozen
        |
        (?:(?:a|an)\s+)?
        (?:{_WORD})
        (?:(?:\s+|-|\s+and\s+)+(?:{_WORD}))*
        (?:\s+(?:{_UNIT_WORDS}))?
    )
    (?![A-Za-z0-9])
    """,
    re.IGNORECASE | re.VERBOSE,
)

_UNIT_SUFFIX = re.compile(rf"\s+(?P<unit>{_UNIT_WORDS})\s*$", re.IGNORECASE)


def _canon_unit(raw: str | None, currency: bool = False) -> str | None:
    if currency:
        return "$"
    if not raw:
        return None
    token = raw.lower()
    if token in {"$", "dollar", "dollars", "usd"}:
        return "$"
    if token in {"%", "percent"}:
        return "%"
    plurals = {
        "day": "days", "days": "days",
        "hour": "hours", "hours": "hours", "h": "hours", "hr": "hours", "hrs": "hours",
        "week": "weeks", "weeks": "weeks",
        "month": "months", "months": "months",
        "year": "years", "years": "years",
        "minute": "minutes", "minutes": "minutes",
    }
    return plurals.get(token, token)


def _words_to_number(tokens: list[str]) -> float | None:
    if tokens in (["dozen"], ["a", "dozen"], ["an", "dozen"]):
        return 12.0
    if tokens in (["half", "a", "dozen"], ["half", "dozen"]):
        return 6.0
    total = 0
    current = 0
    seen = False
    for tok in tokens:
        if tok in {"a", "an"}:
            if current == 0:
                current = 1
                seen = True
            continue
        if tok == "and":
            continue
        if tok in _ONES:
            current += _ONES[tok]
            seen = True
        elif tok in _TENS:
            current += _TENS[tok]
            seen = True
        elif tok == "hundred":
            current = (current or 1) * 100
            seen = True
        elif tok in _SCALES:
            total += (current or 1) * _SCALES[tok]
            current = 0
            seen = True
        elif tok == "dozen":
            current = (current or 1) * 12
            seen = True
        else:
            return None
    if not seen:
        return None
    return float(total + current)


def _parse_word_span(span: str) -> tuple[float, str | None] | None:
    unit = None
    body = span
    unit_match = _UNIT_SUFFIX.search(span)
    if unit_match:
        unit = _canon_unit(unit_match.group("unit"))
        body = span[: unit_match.start()]
    tokens = re.findall(r"[A-Za-z]+", body.lower().replace("-", " "))
    value = _words_to_number(tokens)
    if value is None:
        return None
    return value, unit


def _parse_numeric(match: re.Match[str]) -> tuple[float, str | None]:
    value = float(match.group("number").replace(",", ""))
    mult = (match.group("mult") or "").lower()
    if mult:
        value *= _MULTS[mult]
    unit = _canon_unit(match.group("unit"), currency=bool(match.group("currency")))
    return value, unit


def _overlaps(start: int, end: int, taken: list[tuple[int, int]]) -> bool:
    return any(not (end <= left or start >= right) for left, right in taken)


def find_number_candidates(text: str) -> list[dict]:
    """Return deduped numeric spans. Weeks also yield a derived day count."""
    if not text:
        return []

    hits: list[tuple[int, int, str, float, str | None]] = []
    for match in _NUMERIC.finditer(text):
        value, unit = _parse_numeric(match)
        hits.append((match.start(), match.end(), match.group("span"), value, unit))
    for match in _WORDS.finditer(text):
        parsed = _parse_word_span(match.group("span"))
        if parsed is None:
            continue
        value, unit = parsed
        hits.append((match.start(), match.end(), match.group("span"), value, unit))

    hits.sort(key=lambda item: (-(item[1] - item[0]), item[0]))
    taken: list[tuple[int, int]] = []
    kept: list[tuple[int, int, str, float, str | None]] = []
    for hit in hits:
        if _overlaps(hit[0], hit[1], taken):
            continue
        taken.append((hit[0], hit[1]))
        kept.append(hit)
    kept.sort(key=lambda item: item[0])

    found: list[dict] = []
    seen: set[tuple[str, float, str | None, bool]] = set()

    def add(span: str, value: float, unit: str | None, derived: bool) -> None:
        key = (span, value, unit, derived)
        if key in seen:
            return
        seen.add(key)
        found.append({"span": span, "value": value, "unit": unit, "derived": derived})

    for _start, _end, span, value, unit in kept:
        add(span, value, unit, False)
        if unit == "weeks":
            add(span, value * 7, "days", True)
    return found
