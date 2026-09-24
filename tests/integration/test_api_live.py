"""Live API checks. Skips unless Anchor is reachable at ANCHOR_API_URL."""

import json
import os
import time

import pytest
import requests

API_BASE_URL = os.getenv("ANCHOR_API_URL", "http://localhost:9066").rstrip("/")
API = f"{API_BASE_URL}/api/v1"
PDF = os.path.join(os.path.dirname(__file__), "..", "..", "data", "hr_policy.pdf")
HR_POLICY = os.path.join(os.path.dirname(__file__), "..", "..", "data", "policies", "hr.json")


def _reachable() -> bool:
    try:
        response = requests.get(f"{API_BASE_URL}/ping", timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(not _reachable(), reason="Anchor API is not reachable")


def _wait_for_policy(document_id: str, timeout: float = 180) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        response = requests.get(f"{API}/documents/{document_id}/policies", timeout=30)
        response.raise_for_status()
        policies = response.json()
        if policies:
            return policies[0]
        last = response.text
        time.sleep(2)
    raise AssertionError(f"policy was not generated for {document_id}: {last}")


def _compile(policy_id: str) -> None:
    compiled = requests.post(f"{API}/policies/{policy_id}/compile", timeout=60)
    assert compiled.status_code == 200, compiled.text
    assert compiled.json()["status"] in ("success", "SUCCESS")


def _hr_create_body() -> dict:
    with open(HR_POLICY, encoding="utf-8") as handle:
        return {**json.load(handle), "name": "live_test_hr"}


def test_hr_upload_compiles():
    document_id = None
    try:
        with open(PDF, "rb") as handle:
            upload = requests.post(
                f"{API}/documents/upload",
                files={"file": ("hr_policy.pdf", handle, "application/pdf")},
                data={"domain": "hr"},
                timeout=60,
            )
        assert upload.status_code == 200, upload.text
        document_id = upload.json()["document_id"]
        policy = _wait_for_policy(document_id)
        policy_id = policy["id"]
        _compile(policy_id)
        analysis = requests.get(f"{API}/policies/{policy_id}/variable-analysis", timeout=30)
        assert analysis.status_code == 200, analysis.text
    finally:
        if document_id:
            requests.delete(f"{API}/documents/{document_id}", timeout=30)


def test_handwritten_hr_verdicts():
    created = requests.post(f"{API}/policies/", json=_hr_create_body(), timeout=30)
    assert created.status_code == 200, created.text
    policy_id = created.json()["id"]
    try:
        _compile(policy_id)
        cases = [
            (
                "Can a full-time employee who works 40 hours a week take 10 days of leave?",
                "Yes. The employee is full-time, works 40 hours per week, requests 10 days of leave, and submitted the request by email to HR.",
                "VALID",
            ),
            (
                "Can a contractor who works 40 hours a week take 10 days of leave?",
                "The person is a contractor, works 40 hours per week, and requests 10 days of leave.",
                "INVALID",
            ),
            (
                "Can I take leave?",
                "I want to take leave.",
                "NEEDS_CLARIFICATION",
            ),
        ]
        for question, answer, expected in cases:
            verified = requests.post(
                f"{API}/policies/{policy_id}/verify",
                json={"question": question, "answer": answer},
                timeout=120,
            )
            assert verified.status_code == 200, verified.text
            body = verified.json()
            assert body["result"] == expected, body
            details = body["details"]
            assert details["extractor"] in ("jev", "llm")
            assert "sources" in details
            assert "extract" in details["latency_ms"]
            assert "verify" in details["latency_ms"]
            assert "total" in details["latency_ms"]
            if expected == "NEEDS_CLARIFICATION":
                missing = details.get("missing_mandatory_vars") or []
                assert missing, body
                assert body["suggestions"]

        history = requests.get(f"{API}/policies/{policy_id}/verifications", timeout=30)
        assert history.status_code == 200, history.text
        rows = history.json()
        assert rows
        assert rows[0]["details"] is not None
        assert "extractor" in rows[0]["details"]

        grounding = requests.get(f"{API}/policies/{policy_id}/grounding", timeout=60)
        assert grounding.status_code == 200, grounding.text
    finally:
        requests.delete(f"{API}/policies/{policy_id}", timeout=30)
