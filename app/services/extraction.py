"""Process-wide variable extractor selection."""

from __future__ import annotations

import time
from typing import Any

from ..core.config import settings
from .jev_extractor import JevVariableExtractor
from .variable_extractor import VariableExtractorService

_cached: tuple[str, Any] | None = None


def resolved_extractor_mode() -> str:
    """Return the extractor actually in effect: 'jev' or 'llm'."""
    choice = (settings.variable_extractor or "auto").strip().lower()
    if choice == "jev":
        return "jev"
    if choice == "llm":
        return "llm"
    return "jev" if settings.typesafe_api_key else "llm"


def reset_variable_extractor() -> None:
    global _cached
    _cached = None


def get_variable_extractor():
    """Return the process-wide extractor for the current settings."""
    global _cached
    mode = resolved_extractor_mode()
    if _cached is None or _cached[0] != mode:
        if mode == "jev":
            extractor = JevVariableExtractor()
        else:
            extractor = LlmVariableExtractor()
        _cached = (mode, extractor)
    return _cached[1]


class LlmVariableExtractor:
    """GPT/Claude extractor with the same detailed-result shape as Jev."""

    def __init__(self, inner: VariableExtractorService | None = None):
        self._inner = inner if inner is not None else VariableExtractorService()

    async def extract_variables(self, question: str, answer: str, policy_variables: list[dict]) -> dict:
        return await self._inner.extract_variables(question, answer, policy_variables)

    async def validate_extracted_variables(self, variables: dict, policy_variables: list[dict]) -> list[str]:
        return await self._inner.validate_extracted_variables(variables, policy_variables)

    async def extract_detailed(
        self,
        question: str,
        answer: str,
        policy_variables: list[dict],
        policy_context: dict | None = None,
    ) -> dict:
        del policy_context
        started = time.perf_counter()
        values = await self._inner.extract_raw(question, answer, policy_variables)
        variables = self._inner._apply_default_values(values, policy_variables)
        names = [var["name"] for var in policy_variables]
        return {
            "variables": variables,
            "values": values,
            "confidence": {name: None for name in names},
            "sources": {name: "llm" for name in names},
            "guards": None,
            "model": settings.openai_model,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "fallback_used": False,
            "fallback_reason": None,
        }


async def extract_detailed(
    question: str,
    answer: str,
    policy_variables: list[dict],
    policy_context: dict | None = None,
) -> dict:
    extractor = get_variable_extractor()
    return await extractor.extract_detailed(
        question, answer, policy_variables, policy_context=policy_context
    )


def extractor_public_status() -> dict:
    """Status fields that are safe to expose. Never includes API keys."""
    return {
        "extractor_mode": resolved_extractor_mode(),
        "variable_extractor": settings.variable_extractor,
        "jev_configured": bool(settings.typesafe_api_key),
        "jev_model": settings.jev_model,
        "jev_guards_enabled": settings.jev_guards_enabled,
        "jev_llm_fallback": settings.jev_llm_fallback,
    }
