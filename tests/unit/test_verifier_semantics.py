"""Verifier semantics: verdict casing, fail-closed permission, constraints, reals."""

import json
from pathlib import Path

from app.services.rule_compiler import RuleCompiler
from app.services.variable_extractor import VariableExtractorService
from app.services.verification import VerificationService

ROOT = Path(__file__).resolve().parents[2]
POLICIES = ROOT / "data" / "policies"


def _verify(policy, variables):
    from app.services.compiled_store import dumps_compilation

    compiled = RuleCompiler().compile_policy(policy)
    blob = dumps_compilation(policy, compiled)
    return VerificationService().verify_scenario(variables, blob, policy["rules"])


def _policy(variables, rules, constraints=None):
    return {
        "policy_name": "unit",
        "domain": "test",
        "version": "1.0",
        "variables": variables,
        "rules": rules,
        "constraints": constraints or [],
    }


def test_missing_mandatory_verdict_is_uppercase():
    policy = _policy(
        [{"name": "employee_id", "type": "string", "description": "id", "is_mandatory": True}],
        [{
            "id": "known",
            "description": "Any known employee is allowed",
            "condition": "employee_id != ''",
            "conclusion": "valid",
        }],
    )
    result = _verify(policy, {"employee_id": "MISSING_MANDATORY"})
    assert result["result"] == "NEEDS_CLARIFICATION"
    assert result["result"] not in {"needs_clarification", "valid", "invalid"}
    assert result["missing_mandatory_vars"] == ["employee_id"]


def test_skipped_rules_are_not_permission():
    policy = _policy(
        [
            {"name": "action_type", "type": "string", "description": "action", "is_mandatory": True},
            {"name": "amount", "type": "number", "description": "usd", "is_mandatory": False},
        ],
        [{
            "id": "small_refund_allowed",
            "description": "Refunds of 100 or less are allowed",
            "condition": "action_type == 'refund' AND amount <= 100",
            "conclusion": "valid",
        }],
    )
    result = _verify(policy, {"action_type": "refund", "amount": "SKIP_RULE"})
    assert result["result"] == "NEEDS_CLARIFICATION"
    assert result["missing_mandatory_vars"] == ["amount"]
    assert result["explanation"] == "Missing required information for: amount"


def test_valid_requires_a_satisfied_allow_rule():
    policy = _policy(
        [
            {"name": "action_type", "type": "string", "description": "action", "is_mandatory": True},
            {"name": "amount", "type": "number", "description": "usd", "is_mandatory": False},
        ],
        [
            {
                "id": "small_refund_allowed",
                "description": "Refunds of 100 or less are allowed",
                "condition": "action_type == 'refund' AND amount <= 100",
                "conclusion": "valid",
            },
            {
                "id": "lookup_allowed",
                "description": "Read-only lookup is allowed",
                "condition": "action_type == 'read_only_lookup'",
                "conclusion": "valid",
            },
        ],
    )
    result = _verify(policy, {"action_type": "read_only_lookup", "amount": "SKIP_RULE"})
    assert result["result"] == "VALID"
    assert "uncovered" not in result


def test_known_invalid_beats_missing_mandatory():
    policy = _policy(
        [
            {"name": "employee_type", "type": "string", "description": "type", "is_mandatory": True},
            {"name": "days", "type": "number", "description": "days", "is_mandatory": True},
        ],
        [{
            "id": "no_contractors",
            "description": "Contractors are not eligible",
            "condition": "employee_type == 'contractor'",
            "conclusion": "invalid",
        }],
    )
    denied = _verify(policy, {"employee_type": "contractor", "days": "MISSING_MANDATORY"})
    assert denied["result"] == "INVALID"
    assert "no_contractors" in denied["failed_rules"]

    unknown = _verify(policy, {"employee_type": "full_time", "days": "MISSING_MANDATORY"})
    assert unknown["result"] == "NEEDS_CLARIFICATION"
    assert unknown["missing_mandatory_vars"] == ["days"]


def test_global_constraint_violation_is_invalid():
    policy = _policy(
        [{"name": "contract_value", "type": "number", "description": "value", "is_mandatory": True}],
        [{
            "id": "under_cap",
            "description": "Contracts at or under 50000 are allowed",
            "condition": "contract_value <= 50000",
            "conclusion": "valid",
        }],
        ["contract_value > 0"],
    )
    result = _verify(policy, {"contract_value": 0})
    assert result["result"] == "INVALID"
    assert "contract_value > 0" in result["failed_rules"]
    assert any(item["rule_id"] == "contract_value > 0" and item["result"] == "fail"
               for item in result["rule_results"])


def test_fractional_number_evaluates():
    policy = _policy(
        [{"name": "equipment_usage_hours", "type": "number", "description": "hours", "is_mandatory": True}],
        [
            {
                "id": "short_use_allowed",
                "description": "Up to 8 hours is allowed",
                "condition": "equipment_usage_hours <= 8",
                "conclusion": "valid",
            },
            {
                "id": "over_limit",
                "description": "More than 8 hours is not allowed",
                "condition": "equipment_usage_hours > 8",
                "conclusion": "invalid",
            },
        ],
    )
    half_hour = _verify(policy, {"equipment_usage_hours": 0.5})
    assert half_hour["result"] == "VALID"
    assert half_hour["failed_rules"] == []

    compiled = RuleCompiler().compile_policy(policy)
    assert compiled["variables"]["equipment_usage_hours"].sort().name() == "Real"


def test_optional_default_is_applied_and_bare_optional_skips():
    variables = [
        {"name": "has_manager_approval", "type": "boolean", "description": "approval",
         "is_mandatory": False, "default_value": False},
        {"name": "amount", "type": "number", "description": "usd", "is_mandatory": False,
         "default_value": "1.5"},
        {"name": "note", "type": "string", "description": "note", "is_mandatory": False},
        {"name": "employee_id", "type": "string", "description": "id", "is_mandatory": True},
    ]
    applied = VariableExtractorService()._apply_default_values({}, variables)
    assert applied["has_manager_approval"] is False
    assert applied["amount"] == 1.5
    assert applied["note"] == "SKIP_RULE"
    assert applied["employee_id"] == "MISSING_MANDATORY"

    policy = _policy(
        variables[:2],
        [{
            "id": "needs_approval",
            "description": "Unapproved requests are invalid",
            "condition": "has_manager_approval == false",
            "conclusion": "invalid",
        }],
    )
    result = _verify(policy, applied)
    assert result["result"] == "INVALID"
    assert "needs_approval" in result["failed_rules"]


def test_shipped_policies_compile_without_leaks():
    from app.services.policy_repair import leaky_permits

    for path in sorted(POLICIES.glob("*.json")):
        policy = json.loads(path.read_text())
        numeric = {v["name"] for v in policy["variables"] if v["type"] == "number"}
        RuleCompiler().compile_policy(policy)
        assert leaky_permits(policy) == [], path.name
        for constraint in policy.get("constraints") or []:
            assert VerificationService._is_range_constraint(constraint, numeric), (path.name, constraint)


def test_deny_rule_on_unknown_optional_blocks_approval():
    # Before three-valued evaluation this was VALID: the deny rule was skipped, the permit fired.
    policy = _policy(
        [
            {"name": "employee_type", "type": "enum", "possible_values": ["full_time", "contractor"],
             "description": "type", "is_mandatory": True},
            {"name": "bonus_amount", "type": "number", "description": "bonus", "is_mandatory": False},
        ],
        [
            {"id": "ft", "description": "Full-time is eligible", "condition": "employee_type == 'full_time'",
             "conclusion": "valid"},
            {"id": "cap", "description": "Bonus above 1000 is not allowed", "condition": "bonus_amount > 1000",
             "conclusion": "invalid"},
        ],
    )
    result = _verify(policy, {"employee_type": "full_time", "bonus_amount": "SKIP_RULE"})
    assert result["result"] == "NEEDS_CLARIFICATION"
    assert result["missing_mandatory_vars"] == ["bonus_amount"]
    assert _verify(policy, {"employee_type": "full_time", "bonus_amount": 500})["result"] == "VALID"


def test_deny_that_must_fire_is_invalid_despite_unknowns():
    policy = _policy(
        [
            {"name": "employee_type", "type": "enum", "possible_values": ["full_time", "contractor"],
             "description": "type", "is_mandatory": True},
            {"name": "hours_per_week", "type": "number", "description": "hours", "is_mandatory": True},
        ],
        [
            {"id": "ft", "description": "Full-time over 20h", "condition":
             "employee_type == 'full_time' AND hours_per_week > 20", "conclusion": "valid"},
            {"id": "no_contractors", "description": "Contractors or under 5h are not eligible",
             "condition": "employee_type == 'contractor' OR hours_per_week < 5", "conclusion": "invalid"},
        ],
    )
    result = _verify(policy, {"employee_type": "contractor", "hours_per_week": "MISSING_MANDATORY"})
    assert result["result"] == "INVALID"


def test_business_rule_in_constraints_is_not_assumed():
    # GPT sometimes writes a limit as a global constraint. Assuming it would set the unknown
    # approval to true and approve 45 days; it must ask instead.
    policy = _policy(
        [
            {"name": "leave_days", "type": "number", "description": "days", "is_mandatory": True},
            {"name": "has_manager_approval", "type": "boolean", "description": "approval", "is_mandatory": False},
        ],
        [{"id": "any", "description": "Leave is allowed", "condition": "leave_days > 0", "conclusion": "valid"}],
        constraints=["leave_days > 0", "leave_days <= 30 OR has_manager_approval == true"],
    )
    result = _verify(policy, {"leave_days": 45, "has_manager_approval": "SKIP_RULE"})
    assert result["result"] == "NEEDS_CLARIFICATION"
    assert result["missing_mandatory_vars"] == ["has_manager_approval"]
    assert _verify(policy, {"leave_days": 45, "has_manager_approval": False})["result"] == "INVALID"
    assert _verify(policy, {"leave_days": 10, "has_manager_approval": "SKIP_RULE"})["result"] == "VALID"
