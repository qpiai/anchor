"""One decision path (extract -> guards -> Z3 -> audit row) shared by the REST API and MCP."""

from __future__ import annotations

import logging
import re
import time
import uuid

from sqlalchemy.orm import Session

from ..core.config import settings
from ..models.database import CompilationStatus, Policy, PolicyCompilation, Verification, VerificationResult
from .compiled_store import policy_dict_from_row
from .extraction import LlmVariableExtractor, extract_detailed, resolved_extractor_mode
from .jev_extractor import ExtractorUnavailableError
from .number_candidates import find_number_candidates
from .verification import VerificationService

logger = logging.getLogger(__name__)

INJECTION_SUGGESTION = (
    "Request contains instructions aimed at the decision system; facts were evaluated independently."
)
INJECTION_HOLD_EXPLANATION = (
    "The facts support approval, but the request also tries to instruct the decision system. "
    "Held for human review."
)
OUT_OF_SCOPE_EXPLANATION = "Request appears unrelated to this policy."

_verification_service = VerificationService()
_llm_extractor: LlmVariableExtractor | None = None


def _llm() -> LlmVariableExtractor:
    global _llm_extractor
    if _llm_extractor is None:
        _llm_extractor = LlmVariableExtractor()
    return _llm_extractor


class PolicyNotFoundError(LookupError):
    pass


class PolicyNotCompiledError(RuntimeError):
    pass


def load_compiled_policy(db: Session, policy_id: uuid.UUID) -> tuple[Policy, PolicyCompilation]:
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        raise PolicyNotFoundError("Policy not found")
    compilation = (
        db.query(PolicyCompilation)
        .filter(PolicyCompilation.policy_id == policy_id)
        .filter(PolicyCompilation.compilation_status == CompilationStatus.SUCCESS)
        .order_by(PolicyCompilation.compiled_at.desc())
        .first()
    )
    if not compilation:
        raise PolicyNotCompiledError(
            "Policy must be compiled before verification. Please compile the policy first."
        )
    return policy, compilation


def result_enum(value) -> VerificationResult:
    if isinstance(value, VerificationResult):
        return value
    try:
        return VerificationResult(str(value).upper())
    except ValueError:
        return VerificationResult.ERROR


def _policy_context(policy: Policy) -> dict:
    return {"name": policy.name, "description": policy.description, "domain": policy.domain}


def _guard_flags(detailed: dict) -> dict:
    guards = detailed.get("guards") if isinstance(detailed.get("guards"), dict) else {}
    in_scope = guards.get("in_scope")
    injection = guards.get("injection")
    return {
        "out_of_scope": in_scope is not None and in_scope < settings.jev_scope_threshold,
        "injection_suspected": injection is not None and injection >= settings.jev_injection_threshold,
    }


def _details(policy, detailed, flags, verification_result, extract_ms, verify_ms, total_ms) -> dict:
    result = verification_result or {}
    return {
        "extractor": resolved_extractor_mode(),
        "model": detailed.get("model"),
        "fallback_used": bool(detailed.get("fallback_used")),
        "fallback_reason": detailed.get("fallback_reason"),
        "confidence": detailed.get("confidence"),
        "sources": detailed.get("sources"),
        "guards": detailed.get("guards"),
        "flags": flags,
        "latency_ms": {"extract": extract_ms, "verify": verify_ms, "total": total_ms},
        "rule_results": result.get("rule_results") or [],
        "failed_rules": result.get("failed_rules") or [],
        "missing_mandatory_vars": result.get("missing_mandatory_vars") or [],
        "uncovered": bool(result.get("uncovered")),
        "policy_version": policy.version,
    }


def _record(db: Session, policy: Policy, question: str, answer: str, outcome: dict, commit: bool) -> dict:
    row = Verification(
        policy_id=policy.id,
        question=question,
        answer=answer,
        extracted_variables=outcome["extracted_variables"],
        verification_result=outcome["result"],
        explanation=outcome["explanation"],
        suggestions=outcome["suggestions"],
        details=outcome["details"],
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    outcome["verification_id"] = row.id
    return outcome


def _coerce(value, var_type):
    if var_type == "boolean" and isinstance(value, str):
        return {"true": True, "false": False}.get(value.strip().lower(), value)
    if var_type == "number" and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def apply_trusted_facts(detailed: dict, policy_variables: list[dict], facts: dict | None) -> frozenset:
    """Overlay trusted facts on the extraction. Returns the names that are now fixed.

    Variables marked trusted_only (approvals, identity checks) are never taken from the text:
    they are empty unless the caller supplies them, so claiming "my manager approved" does nothing.
    """
    types = {var["name"]: var.get("type") for var in policy_variables}
    values = dict(detailed.get("values") or {})
    confidence = dict(detailed.get("confidence") or {})
    sources = dict(detailed.get("sources") or {})
    fixed = set()
    for var in policy_variables:
        if var.get("trusted_only"):
            values[var["name"]] = None
            confidence[var["name"]] = 1.0  # confidently unknown: ask, do not escalate
            sources[var["name"]] = "trusted"
            fixed.add(var["name"])
    for name, value in (facts or {}).items():
        if name in types:
            values[name] = _coerce(value, types[name])
            confidence[name] = 1.0
            sources[name] = "trusted"
            fixed.add(name)
    if fixed:
        detailed["values"], detailed["confidence"], detailed["sources"] = values, confidence, sources
        detailed["variables"] = _llm()._inner._apply_default_values(values, policy_variables)
        detailed["ignored_facts"] = sorted(set(facts or {}) - set(types))
    return frozenset(fixed)


_ZERO_WORDS = re.compile(r"\b(zero|none|nothing|free|no charge)\b", re.IGNORECASE)


def _unzero(values: dict, policy_variables: list[dict], text: str) -> dict:
    """GPT writes 0 for 'no amount given', and a $0 refund passes 'amount <= 100'.
    A 0 counts only when the text says 0, zero, none, or free."""
    numbers = {var["name"] for var in policy_variables if var.get("type") == "number"}
    stated_zero = _ZERO_WORDS.search(text) or any(c["value"] == 0 for c in find_number_candidates(text))
    return {
        name: (None if name in numbers and value == 0 and not stated_zero else value)
        for name, value in values.items()
    }


async def hybrid_check(
    question, answer, policy_variables, detailed, result, run, llm, fixed: frozenset = frozenset()
) -> tuple[dict, dict, dict]:
    """Jev when it is sure, GPT's whole reading when it is not. Returns (result, variables, info).

    GPT is called when Jev would ask and a mandatory fact came back empty below
    HYBRID_ESCALATE_BELOW, or when Jev would approve and any fact behind it is below
    HYBRID_CHECK_BELOW. Trusted facts are never replaced. Tuned in bench/RESULTS.md.
    """
    values = detailed["values"]
    conf = detailed.get("confidence") or {}
    verdict = result.get("result")
    info = {"reason": None, "jev_verdict": verdict, "gpt_ms": None, "gpt_error": None}

    below = settings.hybrid_escalate_below
    if verdict == VerificationResult.NEEDS_CLARIFICATION.value and below is not None:
        if any(
            var.get("is_mandatory") and var["name"] not in fixed and values.get(var["name"]) is None
            and conf.get(var["name"]) is not None and conf[var["name"]] < below
            for var in policy_variables
        ):
            info["reason"] = "uncertain_fact"
    elif verdict == VerificationResult.VALID.value and settings.hybrid_confirm_approvals:
        # A fact with no Jev confidence (fallback, unsupported type) counts as unsure.
        used = [name for name, value in values.items() if value is not None and name not in fixed]
        weakest = min((conf.get(name) if conf.get(name) is not None else 0.0) for name in used) if used else 0.0
        if weakest < settings.hybrid_check_below:
            info["reason"] = "unsure_approval"
    if info["reason"] is None:
        return result, detailed["variables"], info

    started = time.perf_counter()
    try:
        gpt = (await llm.extract_detailed(question, answer, policy_variables))["values"]
    except Exception as exc:  # noqa: BLE001 - GPT down: keep Jev's answer, but never its unchecked approval
        info["gpt_error"] = f"{type(exc).__name__}: {exc}"
        info["gpt_ms"] = (time.perf_counter() - started) * 1000
        if info["reason"] == "unsure_approval" and settings.hybrid_fail_closed:
            return {
                **result,
                "result": VerificationResult.NEEDS_CLARIFICATION.value,
                "explanation": "Approval check is unavailable; retry, or route to human review.",
                "suggestions": [],
            }, detailed["variables"], info
        return result, detailed["variables"], info
    info["gpt_ms"] = (time.perf_counter() - started) * 1000
    gpt = _unzero(gpt, policy_variables, f"{question}\n{answer}")
    gpt.update({name: values.get(name) for name in fixed})
    new_result, variables = run(gpt)
    return new_result, variables, info


async def decide(
    db: Session,
    policy: Policy,
    compilation: PolicyCompilation,
    question: str,
    answer: str,
    commit: bool = True,
    facts: dict | None = None,
) -> dict:
    """Run one decision and store it. Raises ExtractorUnavailableError after storing an ERROR row."""
    started = time.perf_counter()
    try:
        detailed = await extract_detailed(
            question, answer, policy.variables or [], policy_context=_policy_context(policy)
        )
    except ExtractorUnavailableError as exc:
        logger.warning("Extractor unavailable: %s", exc)
        _record(db, policy, question, answer, _error_outcome(str(exc)), commit)
        raise
    except Exception as exc:
        logger.exception("Variable extraction failed")
        return _record(db, policy, question, answer, _error_outcome(f"Variable extraction failed: {exc}"), commit)

    extract_ms = (time.perf_counter() - started) * 1000
    fixed = apply_trusted_facts(detailed, policy.variables or [], facts)
    flags = _guard_flags(detailed)
    extracted = detailed["variables"]

    if flags["out_of_scope"] and settings.jev_block_out_of_scope:
        total_ms = (time.perf_counter() - started) * 1000
        outcome = {
            "result": VerificationResult.NEEDS_CLARIFICATION.value,
            "explanation": OUT_OF_SCOPE_EXPLANATION,
            "suggestions": [],
            "extracted_variables": extracted,
            "details": _details(policy, detailed, flags, None, extract_ms, 0.0, total_ms),
        }
        return _record(db, policy, question, answer, outcome, commit)

    policy_variables = policy.variables or []

    def run(values: dict) -> tuple[dict, dict]:
        variables = _llm()._inner._apply_default_values(values, policy_variables)
        return _verification_service.verify_scenario(
            variables,
            compilation.z3_constraints,
            policy.rules or [],
            compilation_id=str(compilation.id),
            fallback_policy=policy_dict_from_row(policy),
        ), variables

    verify_started = time.perf_counter()
    hybrid = None
    try:
        verification_result = _verification_service.verify_scenario(
            extracted,
            compilation.z3_constraints,
            policy.rules or [],
            compilation_id=str(compilation.id),
            fallback_policy=policy_dict_from_row(policy),
        )
        if resolved_extractor_mode() == "jev" and not detailed.get("fallback_used") and "values" in detailed:
            verification_result, extracted, hybrid = await hybrid_check(
                question, answer, policy_variables, detailed, verification_result, run, _llm(), fixed
            )
    except Exception as exc:
        logger.exception("Z3 verification failed")
        return _record(db, policy, question, answer, _error_outcome(f"Z3 verification failed: {exc}"), commit)
    verify_ms = (time.perf_counter() - verify_started) * 1000

    if (
        flags["injection_suspected"]
        and settings.jev_injection_holds_approval
        and result_enum(verification_result.get("result")) == VerificationResult.VALID
    ):
        # Flag-only for denials; an approval that came with instructions to the decider waits for a human.
        verification_result = {
            **verification_result,
            "result": VerificationResult.NEEDS_CLARIFICATION.value,
            "explanation": INJECTION_HOLD_EXPLANATION,
        }
    suggestions = list(verification_result.get("suggestions") or [])
    if flags["injection_suspected"]:
        suggestions.append(INJECTION_SUGGESTION)
    total_ms = (time.perf_counter() - started) * 1000
    outcome = {
        "result": result_enum(verification_result.get("result")).value,
        "explanation": verification_result.get("explanation") or "",
        "suggestions": suggestions,
        "extracted_variables": extracted,
        "details": {**_details(policy, detailed, flags, verification_result, extract_ms, verify_ms, total_ms),
                    "hybrid": hybrid, "trusted_facts": sorted(fixed),
                    "ignored_facts": detailed.get("ignored_facts") or []},
    }
    return _record(db, policy, question, answer, outcome, commit)


def _error_outcome(explanation: str) -> dict:
    return {
        "result": VerificationResult.ERROR.value,
        "explanation": explanation,
        "suggestions": [],
        "extracted_variables": {},
        "details": None,
    }


def summarize(results: list[dict]) -> dict:
    summary = {"total": len(results), "valid": 0, "invalid": 0, "needs_clarification": 0, "errors": 0}
    for item in results:
        result = str(item.get("result", "")).upper()
        if result == VerificationResult.VALID.value:
            summary["valid"] += 1
        elif result == VerificationResult.INVALID.value:
            summary["invalid"] += 1
        elif result == VerificationResult.NEEDS_CLARIFICATION.value:
            summary["needs_clarification"] += 1
        else:
            summary["errors"] += 1
    return summary
