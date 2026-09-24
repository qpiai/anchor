"""AppTest coverage for the Streamlit pages. The API client is mocked."""

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from pathlib import Path

from streamlit_ui.api import ApiError

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "streamlit_ui" / "views" / "verify.py"
POLICIES = ROOT / "streamlit_ui" / "views" / "policies.py"
HISTORY = ROOT / "streamlit_ui" / "views" / "history.py"

POLICY = {
    "id": "p1",
    "name": "Expense",
    "domain": "finance",
    "status": "compiled",
    "version": "1.0",
    "description": "Expenses",
    "variables": [
        {
            "name": "amount",
            "type": "number",
            "description": "Amount",
            "is_mandatory": True,
            "default_value": None,
            "possible_values": None,
        }
    ],
    "rules": [
        {
            "id": "r1",
            "description": "Amounts over 100 are invalid",
            "condition": "amount > 100",
            "conclusion": "invalid",
            "priority": 1,
        }
    ],
    "constraints": [],
    "examples": [],
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-02T00:00:00",
    "document_id": None,
}

DETAILS = {
    "extractor": "jev",
    "model": "jev-1",
    "fallback_used": False,
    "fallback_reason": None,
    "confidence": {"amount": 0.92},
    "sources": {"amount": "jev"},
    "guards": {"in_scope": 0.99, "injection": 0.01},
    "flags": {"out_of_scope": False, "injection_suspected": False},
    "latency_ms": {"extract": 12, "verify": 4, "total": 16},
    "rule_results": [{"rule_id": "r1", "result": "pass"}],
    "failed_rules": [],
    "missing_mandatory_vars": [],
    "policy_version": "1.0",
}


@pytest.fixture(autouse=True)
def _clear_cache():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def _patch_lists(monkeypatch):
    monkeypatch.setattr("streamlit_ui.api.list_policies", lambda limit=200: [POLICY])
    monkeypatch.setattr("streamlit_ui.api.get_policy", lambda policy_id: POLICY)


def _verify_page(monkeypatch, payload):
    _patch_lists(monkeypatch)
    monkeypatch.setattr("streamlit_ui.api.verify", lambda policy_id, question, answer, facts=None: payload)
    at = AppTest.from_file(VERIFY, default_timeout=15)
    at.run()
    at.text_area(key="verify_request").set_value("Can I expense a license?").run()
    at.text_area(key="verify_answer").set_value("Yes, it costs $75.").run()
    at.button(key="verify_btn").click().run()
    assert not at.exception
    return at


def test_verify_valid_with_details(monkeypatch):
    payload = {
        "verification_id": "v1",
        "result": "VALID",
        "extracted_variables": {"amount": 75},
        "explanation": "Within policy.",
        "suggestions": [],
        "details": DETAILS,
    }
    at = _verify_page(monkeypatch, payload)
    text = _text(at)
    assert "VALID" in text
    assert "Within policy." in text
    assert "jev" in text
    assert "Amounts over 100 are invalid" in text


def test_verify_needs_clarification(monkeypatch):
    payload = {
        "verification_id": "v2",
        "result": "NEEDS_CLARIFICATION",
        "extracted_variables": {},
        "explanation": "Amount is missing.",
        "suggestions": ["What is the amount?"],
        "details": {**DETAILS, "missing_mandatory_vars": ["amount"]},
    }
    at = _verify_page(monkeypatch, payload)
    text = _text(at)
    assert "NEEDS CLARIFICATION" in text
    assert "What is the amount?" in text


def test_verify_without_details(monkeypatch):
    payload = {
        "verification_id": "v3",
        "result": "INVALID",
        "extracted_variables": {"amount": 250},
        "explanation": "Over the cap.",
        "suggestions": [],
    }
    at = _verify_page(monkeypatch, payload)
    text = _text(at)
    assert "INVALID" in text
    assert "Over the cap." in text
    assert not at.exception


def test_verify_api_unreachable(monkeypatch):
    message = (
        "Cannot reach the API at http://localhost:9066. "
        "Start it with: uvicorn app.main:app --port 9066"
    )
    monkeypatch.setattr(
        "streamlit_ui.api.list_policies",
        lambda limit=200: (_ for _ in ()).throw(ApiError(message)),
    )
    at = AppTest.from_file(VERIFY, default_timeout=15)
    at.run()
    assert not at.exception
    assert at.error
    assert "uvicorn app.main:app --port 9066" in at.error[0].value
    assert "http://localhost:9066" in at.error[0].value


def test_policies_lists_policies(monkeypatch):
    _patch_lists(monkeypatch)
    at = AppTest.from_file(POLICIES, default_timeout=15)
    at.run()
    assert not at.exception
    assert "Expense" in _text(at)


def test_history_renders(monkeypatch):
    _patch_lists(monkeypatch)
    row = {
        "id": "h1",
        "policy_id": "p1",
        "question": "Can I expense a license?",
        "answer": "Yes, $75.",
        "extracted_variables": {"amount": 75},
        "verification_result": "VALID",
        "explanation": "Within policy.",
        "suggestions": [],
        "verified_at": "2026-01-02T12:00:00",
        "details": DETAILS,
    }
    monkeypatch.setattr("streamlit_ui.api.list_verifications", lambda policy_id, limit=50: [row])
    at = AppTest.from_file(HISTORY, default_timeout=15)
    at.run()
    assert not at.exception
    text = _text(at)
    assert "Can I expense a license?" in text
    assert "VALID" in text
    assert "Within policy." in text


def _text(at: AppTest) -> str:
    chunks = []
    for group in (at.markdown, at.text, at.caption, at.warning, at.success, at.error, at.subheader):
        for item in group:
            chunks.append(str(getattr(item, "value", item)))
    for frame in at.dataframe:
        chunks.append(str(frame.value))
    return "\n".join(chunks)
