"""JSON compilation blobs. Pickle is never read or written."""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from typing import Any

from .rule_compiler import RuleCompiler

logger = logging.getLogger(__name__)

JSON_FORMAT = "json-v1"
_CACHE: OrderedDict[str, dict] = OrderedDict()
_CACHE_MAX = 32


def policy_dict_from_row(policy) -> dict:
    return {
        "policy_name": policy.name,
        "domain": policy.domain,
        "version": policy.version,
        "description": policy.description or "",
        "variables": policy.variables or [],
        "rules": policy.rules or [],
        "constraints": policy.constraints or [],
        "examples": policy.examples or [],
    }


def dumps_compilation(policy_dict: dict, compiled: dict | None = None) -> str:
    summary = {}
    if compiled is not None:
        summary = {
            "variables": list((compiled.get("variables") or {}).keys()),
            "rules": len(compiled.get("rules") or []),
            "constraints": len(compiled.get("constraints") or []),
        }
    return json.dumps({"format": JSON_FORMAT, "policy": policy_dict, "summary": summary})


def resolve_stored_policy(blob: str | None, fallback_policy: dict | None) -> dict:
    """Return the policy dict to recompile. Legacy non-JSON blobs are never unpickled."""
    if blob:
        text = blob.strip()
        if text.startswith("{"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and payload.get("format") == JSON_FORMAT and isinstance(payload.get("policy"), dict):
                return payload["policy"]
    logger.warning(
        "Compilation blob is not json-v1; recompiling from the current policy without unpickling"
    )
    if not fallback_policy:
        raise ValueError(
            "Compilation is not JSON and no current policy is available to recompile"
        )
    return fallback_policy


def get_compiled(cache_key: str | None, policy_dict: dict) -> dict:
    if cache_key and cache_key in _CACHE:
        _CACHE.move_to_end(cache_key)
        return _CACHE[cache_key]
    compiled = RuleCompiler().compile_policy(policy_dict)
    if cache_key:
        _CACHE[cache_key] = compiled
        _CACHE.move_to_end(cache_key)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
    return compiled


def clear_compiled_cache() -> None:
    _CACHE.clear()
