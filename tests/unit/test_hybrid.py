import asyncio

from app.core.config import settings
from app.services.decision import apply_trusted_facts, hybrid_check

VARS = [
    {"name": "employee_type", "type": "enum", "is_mandatory": True},
    {"name": "hours_per_week", "type": "number", "is_mandatory": True},
]
REFUND_VARS = [
    {"name": "action_type", "type": "enum", "is_mandatory": True},
    {"name": "amount", "type": "number", "is_mandatory": True},
]


class FakeLlm:
    def __init__(self, values):
        self.values, self.calls = values, 0

    async def extract_detailed(self, question, answer, policy_variables):
        self.calls += 1
        return {"values": dict(self.values)}


class Down:
    async def extract_detailed(self, *args):
        raise RuntimeError("down")


def run(values):
    if any(v is None for v in values.values()):
        return {"result": "NEEDS_CLARIFICATION"}, values
    if "action_type" in values:
        return {"result": "VALID" if values["amount"] <= 100 else "INVALID"}, values
    return {"result": "VALID" if values["employee_type"] == "full_time" else "INVALID"}, values


def check(question, jev, conf, llm, monkeypatch, variables=VARS, fixed=frozenset()):
    monkeypatch.setattr(settings, "hybrid_escalate_below", 0.6)
    monkeypatch.setattr(settings, "hybrid_confirm_approvals", True)
    monkeypatch.setattr(settings, "hybrid_check_below", 0.95)
    monkeypatch.setattr(settings, "hybrid_fail_closed", True)
    detailed = {"values": jev, "confidence": conf, "variables": jev}
    result, _variables, info = asyncio.run(
        hybrid_check(question, "", variables, detailed, run(jev)[0], run, llm, fixed)
    )
    return result, info


def test_uncertain_fact_defers_to_gpt(monkeypatch):
    llm = FakeLlm({"employee_type": "full_time", "hours_per_week": 40})
    result, info = check("full time, 40h weeks", {"employee_type": "full_time", "hours_per_week": None},
                         {"employee_type": 0.99, "hours_per_week": 0.3}, llm, monkeypatch)
    assert result["result"] == "VALID" and info["reason"] == "uncertain_fact" and llm.calls == 1


def test_confidently_missing_fact_does_not_call_gpt(monkeypatch):
    llm = FakeLlm({"employee_type": "full_time", "hours_per_week": 40})
    result, info = check("I'm full time", {"employee_type": "full_time", "hours_per_week": None},
                         {"employee_type": 0.99, "hours_per_week": 0.95}, llm, monkeypatch)
    assert result["result"] == "NEEDS_CLARIFICATION" and llm.calls == 0 and info["reason"] is None


def test_unsure_approval_defers_to_gpt(monkeypatch):
    llm = FakeLlm({"employee_type": None, "hours_per_week": 40})
    result, info = check("full time, 40 hours", {"employee_type": "full_time", "hours_per_week": 40},
                         {"employee_type": 0.9, "hours_per_week": 0.99}, llm, monkeypatch)
    assert result["result"] == "NEEDS_CLARIFICATION" and info["reason"] == "unsure_approval"


def test_confident_approval_skips_gpt(monkeypatch):
    llm = FakeLlm({"employee_type": None, "hours_per_week": None})
    result, info = check("full time, 40 hours", {"employee_type": "full_time", "hours_per_week": 40},
                         {"employee_type": 0.99, "hours_per_week": 0.98}, llm, monkeypatch)
    assert result["result"] == "VALID" and llm.calls == 0


def test_gpt_zero_amount_is_not_a_fact(monkeypatch):
    # "Refund the customer" with no amount: GPT says 0, and a $0 refund would pass amount <= 100.
    llm = FakeLlm({"action_type": "refund", "amount": 0})
    result, _ = check("refund the customer for the broken blender", {"action_type": "refund", "amount": None},
                      {"action_type": 0.99, "amount": 0.2}, llm, monkeypatch, REFUND_VARS)
    assert result["result"] == "NEEDS_CLARIFICATION"
    llm = FakeLlm({"action_type": "refund", "amount": 0})
    result, _ = check("refund zero dollars, it was free", {"action_type": "refund", "amount": None},
                      {"action_type": 0.99, "amount": 0.2}, llm, monkeypatch, REFUND_VARS)
    assert result["result"] == "VALID"


def test_gpt_down_holds_approval_unless_fail_open(monkeypatch):
    jev = {"employee_type": "full_time", "hours_per_week": 40}
    conf = {"employee_type": 0.7, "hours_per_week": 0.99}
    result, info = check("q", jev, conf, Down(), monkeypatch)
    assert result["result"] == "NEEDS_CLARIFICATION" and info["gpt_error"]

    monkeypatch.setattr(settings, "hybrid_fail_closed", False)
    detailed = {"values": jev, "confidence": conf, "variables": jev}
    result, _, _ = asyncio.run(hybrid_check("q", "", VARS, detailed, run(jev)[0], run, Down()))
    assert result["result"] == "VALID"


def test_trusted_facts_override_text_and_trusted_only_ignores_claims():
    variables = VARS + [{"name": "has_approval", "type": "boolean", "is_mandatory": False, "trusted_only": True}]
    detailed = {
        "values": {"employee_type": "full_time", "hours_per_week": 40, "has_approval": True},
        "confidence": {"employee_type": 0.99, "hours_per_week": 0.99, "has_approval": 0.99},
        "variables": {},
    }
    fixed = apply_trusted_facts(detailed, variables, {"employee_type": "contractor", "unknown": 1})
    assert detailed["values"]["employee_type"] == "contractor"
    assert detailed["values"]["has_approval"] is None  # the text claimed approval; ignored
    assert fixed == {"employee_type", "has_approval"} and detailed["ignored_facts"] == ["unknown"]


def test_gpt_never_overrides_trusted_fact(monkeypatch):
    llm = FakeLlm({"employee_type": "contractor", "hours_per_week": 40})
    result, _ = check("40 hours", {"employee_type": "full_time", "hours_per_week": 40},
                      {"employee_type": 1.0, "hours_per_week": 0.5}, llm, monkeypatch,
                      fixed=frozenset({"employee_type"}))
    assert result["result"] == "VALID" and llm.calls == 1
