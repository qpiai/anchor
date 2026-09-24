"""Compile a generated policy and repair it when the compiler rejects it."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from ..api.policy_validation import (
    extract_variables_from_rules,
    infer_variable_type_and_description,
)
from .rule_compiler import RuleCompiler

logger = logging.getLogger(__name__)

RepairFn = Callable[[dict, list[str]], Awaitable[dict]]


def compile_errors(policy: dict) -> list[str]:
    try:
        RuleCompiler().compile_policy(policy)
    except Exception as exc:
        return [f"{type(exc).__name__}: {exc}"]
    return []


def declare_missing_variables(policy: dict) -> dict:
    """Add variables referenced by rules but not declared. Reuses validation inference."""
    defined = {var.get("name") for var in policy.get("variables") or [] if isinstance(var, dict)}
    missing = extract_variables_from_rules(policy.get("rules") or []) - defined
    if not missing:
        return policy
    updated = dict(policy)
    variables = list(policy.get("variables") or [])
    added = []
    for name in sorted(missing):
        var_type, description = infer_variable_type_and_description(name)
        variable = {
            "name": name,
            "type": var_type,
            "description": description,
            "possible_values": ["true", "false"] if var_type == "boolean" else [],
            "is_mandatory": True,
        }
        variables.append(variable)
        added.append(name)
    updated["variables"] = variables
    logger.info("Auto-declared missing variables: %s", ", ".join(added))
    return updated


async def ensure_policy_compiles(
    policy: dict,
    repair: RepairFn | None,
    *,
    rounds: int = 2,
) -> tuple[dict, list[str]]:
    """Compile, ask for up to two repairs, then auto-declare missing variables."""
    current = policy
    errors = compile_errors(current)
    if not errors:
        logger.info("Generated policy compiled on the first attempt")
        return current, []

    for attempt in range(1, rounds + 1):
        logger.info("Policy compile failed (round %s): %s", attempt, errors)
        if repair is None:
            break
        try:
            repaired = await repair(current, errors)
        except Exception as exc:
            logger.warning("Policy repair round %s failed: %s", attempt, type(exc).__name__)
            break
        if not isinstance(repaired, dict):
            logger.warning("Policy repair round %s did not return a policy object", attempt)
            break
        current = repaired
        errors = compile_errors(current)
        if not errors:
            logger.info("Policy compiled after repair round %s", attempt)
            return current, []

    logger.info("Falling back to auto-declaring missing variables")
    current = declare_missing_variables(current)
    errors = compile_errors(current)
    if errors:
        logger.warning("Policy still does not compile after repair: %s", errors)
    else:
        logger.info("Policy compiled after auto-declaring missing variables")
    return current, errors


def leaky_permits(policy: dict) -> list[str]:
    """Permit rules that look like limits but never restrict anything.

    VALID needs one permit and no deny, so permits are alternatives. A permit that tests only
    numbers or booleans (a cap, a minimum, an approval) and can be bypassed by another permit
    with no deny rule catching the gap is almost always a limit written the wrong way round,
    e.g. "leave_days <= 30 -> valid" next to "employee_type == 'full_time' -> valid".
    """
    from z3 import And, Not, Or, Solver, sat

    try:
        compiled = RuleCompiler().compile_policy(policy)
    except Exception:
        return []
    types = {var.get("name"): var.get("type") for var in policy.get("variables") or [] if isinstance(var, dict)}
    rules = compiled["rules"]
    permits = [r for r in rules if str(r.get("conclusion")).lower() == "valid"]
    denies = [r["constraint"] for r in rules if str(r.get("conclusion")).lower() == "invalid"]
    if len(permits) < 2:
        return []
    leaky = []
    for rule in permits:
        names = extract_variables_from_rules([rule.get("original_rule") or {"condition": ""}])
        if not names or any(types.get(name) in ("enum", "string") for name in names):
            continue  # categorical permits are eligibility alternatives, not limits
        others = [r["constraint"] for r in permits if r is not rule]
        solver = Solver()
        solver.add(*compiled["constraints"])
        solver.add(Not(rule["constraint"]), Or(*others))
        if denies:
            solver.add(Not(Or(*denies)))
        if solver.check() == sat:
            leaky.append(rule["id"])
    return leaky


SEMANTICS_REPAIR_NOTE = (
    "These \"valid\" rules look like limits or requirements, but the verifier approves a request "
    "when ANY \"valid\" rule applies and no \"invalid\" rule applies, so a request that breaks them "
    "is still approved through another rule: {ids}. Rewrite each limit, cap, or required approval as "
    "an \"invalid\" rule that describes the breach (for example \"leave_days > 30 AND "
    "has_manager_approval != true\" -> \"invalid\"). Keep a rule as \"valid\" only if it is a complete, "
    "standalone reason to approve. If a rule is approval routing the variables cannot express, add "
    "the variable needed or drop the rule; never leave it as a standalone permission."
)


async def ensure_policy_semantics(policy: dict, repair: RepairFn | None) -> tuple[dict, list[str]]:
    """One repair round for limits written as permits. Returns (policy, rule ids still leaky)."""
    leaky = leaky_permits(policy)
    if not leaky or repair is None:
        return policy, leaky
    logger.info("Leaky permit rules: %s", leaky)
    try:
        repaired = await repair(policy, [SEMANTICS_REPAIR_NOTE.format(ids=", ".join(leaky))])
    except Exception as exc:
        logger.warning("Semantics repair failed: %s", type(exc).__name__)
        return policy, leaky
    if not isinstance(repaired, dict) or compile_errors(repaired):
        return policy, leaky
    return repaired, leaky_permits(repaired)
