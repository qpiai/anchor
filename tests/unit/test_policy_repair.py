import pytest

from app.services.policy_repair import ensure_policy_compiles


def _broken():
    return {
        "policy_name": "mail",
        "domain": "legal",
        "version": "1.0",
        "description": "mail",
        "variables": [{"name": "employee_type", "type": "string", "description": "type"}],
        "rules": [{
            "id": "channel",
            "description": "Email only",
            "condition": "request_method == 'email'",
            "conclusion": "invalid",
        }],
        "constraints": [],
    }


def _fixed():
    policy = _broken()
    policy["variables"] = [
        {"name": "request_method", "type": "string", "description": "How the request arrived"},
    ]
    return policy


@pytest.mark.asyncio
async def test_repair_round_then_compile():
    calls = []

    async def repair(policy, errors):
        calls.append(errors)
        return _fixed()

    policy, errors = await ensure_policy_compiles(_broken(), repair)
    assert errors == []
    assert calls and "request_method" in calls[0][0]
    assert any(var["name"] == "request_method" for var in policy["variables"])


@pytest.mark.asyncio
async def test_auto_declare_when_repair_does_not_fix():
    async def repair(policy, errors):
        return policy

    policy, errors = await ensure_policy_compiles(_broken(), repair)
    assert errors == []
    names = {var["name"] for var in policy["variables"]}
    assert "request_method" in names


def _leave_policy(rules):
    return {
        "policy_name": "leave", "domain": "hr", "version": "1.0",
        "variables": [
            {"name": "employee_type", "type": "enum", "possible_values": ["full_time", "contractor"],
             "description": "type", "is_mandatory": True},
            {"name": "leave_days", "type": "number", "description": "days", "is_mandatory": True},
            {"name": "has_manager_approval", "type": "boolean", "description": "approval", "is_mandatory": False},
        ],
        "rules": rules, "constraints": [],
    }


LIMIT_AS_PERMIT = [
    {"id": "eligible", "description": "Full-time may take leave", "condition": "employee_type == 'full_time'", "conclusion": "valid"},
    {"id": "max_30", "description": "Up to 30 days", "condition": "leave_days <= 30", "conclusion": "valid"},
]
LIMIT_AS_DENY = [
    LIMIT_AS_PERMIT[0],
    {"id": "max_30", "description": "Over 30 days needs approval",
     "condition": "leave_days > 30 AND has_manager_approval != true", "conclusion": "invalid"},
]


def test_leaky_permit_is_detected_and_deny_form_is_clean():
    from app.services.policy_repair import leaky_permits

    assert leaky_permits(_leave_policy(LIMIT_AS_PERMIT)) == ["max_30"]
    assert leaky_permits(_leave_policy(LIMIT_AS_DENY)) == []


def test_semantics_repair_round_uses_repair_output():
    import asyncio
    from app.services.policy_repair import ensure_policy_semantics

    seen = []

    async def repair(policy, problems):
        seen.append(problems[0])
        return _leave_policy(LIMIT_AS_DENY)

    fixed, leaky = asyncio.run(ensure_policy_semantics(_leave_policy(LIMIT_AS_PERMIT), repair))
    assert leaky == [] and "max_30" in seen[0]
    assert fixed["rules"][1]["conclusion"] == "invalid"
