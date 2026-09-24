"""Authoring-time check: does a source passage support each rule?"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from typesafe_sdk import Choice, Noul

from ..core.config import settings
from .jev_extractor import ask

logger = logging.getLogger(__name__)

SUPPORT = "Does `passage` support `rule` exactly (same thresholds, conditions and outcome)?"
FLAG_BELOW = 0.3
_CACHE: dict[tuple, dict] = {}
_TOKEN = re.compile(r"[a-z0-9]+")


def split_paragraphs(text: str) -> list[str]:
    """Split source text into passages. Wrapped PDF lines are reflowed into chunks."""
    if not text:
        return []
    blocks = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(blocks) > 1 and (sum(len(block) for block in blocks) / len(blocks)) >= 80:
        return blocks
    chunks: list[str] = []
    buffer: list[str] = []
    size = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if buffer:
                chunks.append(" ".join(buffer))
                buffer, size = [], 0
            continue
        buffer.append(line)
        size += len(line) + 1
        if size >= 500:
            chunks.append(" ".join(buffer))
            buffer, size = [], 0
    if buffer:
        chunks.append(" ".join(buffer))
    return chunks


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def best_paragraph(rule_text: str, paragraphs: list[str]) -> tuple[int, str]:
    if not paragraphs:
        return -1, ""
    rule_tokens = _tokens(rule_text)
    best_index = 0
    best_score = -1.0
    for index, paragraph in enumerate(paragraphs):
        paragraph_tokens = _tokens(paragraph)
        if len(paragraph) < 40 or not rule_tokens or not paragraph_tokens:
            score = 0.0
        else:
            score = len(rule_tokens & paragraph_tokens) / len(rule_tokens)
        if score > best_score:
            best_score = score
            best_index = index
    return best_index, paragraphs[best_index]


def rule_text(rule: dict) -> str:
    return (
        f"{rule.get('description', '')} Condition: {rule.get('condition', '')}. "
        f"Conclusion: {rule.get('conclusion', '')}."
    )


def _cache_key(policy_id: str, updated_at: datetime | None) -> tuple:
    stamp = updated_at.isoformat() if isinstance(updated_at, datetime) else str(updated_at)
    return (policy_id, stamp)


async def check_rules(
    policy_id: str,
    rules: list[dict],
    source_text: str,
    updated_at: datetime | None = None,
) -> dict:
    key = _cache_key(policy_id, updated_at)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    paragraphs = split_paragraphs(source_text)
    usable = [rule for rule in rules if isinstance(rule, dict) and rule.get("id")]
    chosen: dict[str, dict] = {}
    for rule in usable:
        text = rule_text(rule)
        index, passage = best_paragraph(text, paragraphs)
        chosen[rule["id"]] = {"index": index, "passage": passage, "rule": text}

    questions: dict[str, Any] = {}
    state: dict[str, Any] = {"rules": {}}
    use_choice = 0 < len(paragraphs) <= 60
    if use_choice:
        state["paragraphs"] = {f"p{index}": paragraph for index, paragraph in enumerate(paragraphs)}
    for rule_id, item in chosen.items():
        state["rules"][rule_id] = {"passage": item["passage"], "rule": item["rule"]}
        questions[f"support_{rule_id}"] = Noul(
            instructions=(
                f"For rules.{rule_id}, {SUPPORT} "
                f"`passage` is rules.{rule_id}.passage and `rule` is rules.{rule_id}.rule."
            )
        )
        if use_choice:
            criteria = {f"p{index}": paragraph[:180] for index, paragraph in enumerate(paragraphs)}
            criteria["none"] = "No paragraph states this rule."
            questions[f"passage_{rule_id}"] = Choice(
                instructions=f"Which paragraph id in `paragraphs` is the best source for rules.{rule_id}.rule?",
                criteria=criteria,
            )

    scores: dict[str, float | None] = {rule_id: None for rule_id in chosen}
    if questions:
        result = await ask(state, questions)
        response = result["response"]
        nouls = response.nouls or {}
        choices = response.choices or {}
        for rule_id, item in chosen.items():
            answer = nouls.get(f"support_{rule_id}")
            scores[rule_id] = None if answer is None else float(answer.noul)
            if not use_choice:
                continue
            picked = choices.get(f"passage_{rule_id}")
            if picked is None:
                continue
            label = picked.choice
            if (
                label in state["paragraphs"]
                and float(picked.confidence) >= settings.jev_confidence_threshold
            ):
                item["passage"] = state["paragraphs"][label]
                item["index"] = int(label[1:])

    rows = []
    for rule_id, item in chosen.items():
        probability = scores[rule_id]
        rows.append({
            "rule_id": rule_id,
            "supported_probability": probability,
            "passage": item["passage"],
            "flag": probability is None or probability < FLAG_BELOW,
        })
    payload = {"policy_id": policy_id, "rules": rows, "paragraphs": len(paragraphs)}
    _CACHE[key] = payload
    logger.info("Grounding checked %s rules for policy %s", len(rows), policy_id)
    return payload


def clear_grounding_cache() -> None:
    _CACHE.clear()
