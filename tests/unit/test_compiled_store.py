import base64
import pickle

from app.services.compiled_store import clear_compiled_cache, dumps_compilation
from app.services.rule_compiler import RuleCompiler
from app.services.verification import VerificationService


def _policy():
    return {
        "policy_name": "unit",
        "domain": "test",
        "version": "1.0",
        "variables": [{"name": "amount", "type": "number", "description": "usd"}],
        "rules": [{
            "id": "cap",
            "description": "Over 10 is invalid",
            "condition": "amount > 10",
            "conclusion": "invalid",
        }],
        "constraints": [],
    }


def test_json_round_trip():
    clear_compiled_cache()
    policy = _policy()
    compiled = RuleCompiler().compile_policy(policy)
    blob = dumps_compilation(policy, compiled)
    assert blob.startswith("{")
    result = VerificationService().verify_scenario(
        {"amount": 12},
        blob,
        policy["rules"],
        compilation_id="json-1",
    )
    again = VerificationService().verify_scenario(
        {"amount": 12},
        blob,
        policy["rules"],
        compilation_id="json-1",
    )
    assert result["result"] == "INVALID"
    assert again["result"] == "INVALID"


def test_legacy_blob_does_not_unpickle(monkeypatch):
    policy = _policy()
    blob = base64.b64encode(pickle.dumps({"original_policy": policy})).decode("utf-8")

    def _boom(*args, **kwargs):
        raise AssertionError("pickle.loads was called")

    monkeypatch.setattr(pickle, "loads", _boom)
    result = VerificationService().verify_scenario(
        {"amount": 3},
        blob,
        policy["rules"],
        compilation_id="legacy-1",
        fallback_policy=policy,
    )
    assert result["result"] == "NEEDS_CLARIFICATION"
