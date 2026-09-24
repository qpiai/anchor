"""Heuristic spans for free-text string variables."""

from __future__ import annotations

import re

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_URL = re.compile(r"https?://[^\s<>\"']+")
_CODE = re.compile(r"\b[A-Za-z]{1,10}-\d{2,}\b")
_QUOTED = re.compile(r'"([^"\n]{1,120})"|\'([^\'\n]{1,120})\'')
_NAME = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b")
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")


def _overlaps(start: int, end: int, taken: list[tuple[int, int]]) -> bool:
    return any(not (end <= left or start >= right) for left, right in taken)


def find_string_candidates(text: str) -> list[dict]:
    """Emails, URLs, codes, quotes, names, and numbers. Empty when nothing matches."""
    if not text:
        return []
    hits: list[tuple[int, int, str, str]] = []
    for match in _EMAIL.finditer(text):
        hits.append((match.start(), match.end(), match.group(0), "email"))
    for match in _URL.finditer(text):
        hits.append((match.start(), match.end(), match.group(0).rstrip(".,);"), "url"))
    for match in _CODE.finditer(text):
        hits.append((match.start(), match.end(), match.group(0), "code"))
    for match in _QUOTED.finditer(text):
        value = match.group(1) if match.group(1) is not None else match.group(2)
        hits.append((match.start(), match.end(), value, "quote"))
    for match in _NAME.finditer(text):
        hits.append((match.start(), match.end(), match.group(0), "name"))
    for match in _NUMBER.finditer(text):
        hits.append((match.start(), match.end(), match.group(0), "number"))

    hits.sort(key=lambda item: (-(item[1] - item[0]), item[0]))
    taken: list[tuple[int, int]] = []
    found: list[dict] = []
    seen: set[str] = set()
    for start, end, value, kind in hits:
        if _overlaps(start, end, taken) or value in seen:
            continue
        taken.append((start, end))
        seen.add(value)
        found.append({"span": value, "value": value, "kind": kind})
    found.sort(key=lambda item: text.find(item["span"]))
    return found
