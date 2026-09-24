"""Thin HTTP client for the Anchor API."""

from __future__ import annotations

import os
import time
from typing import Any

import requests

DEFAULT_BASE = "http://localhost:9066"
PREFIX = "/api/v1"


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def env_base_url() -> str:
    return os.environ.get("ANCHOR_API_URL", DEFAULT_BASE).rstrip("/")


def base_url() -> str:
    try:
        import streamlit as st

        override = st.session_state.get("api_base_url")
        if override:
            return str(override).rstrip("/")
    except Exception:
        pass
    return env_base_url()


def _unreachable(url: str) -> ApiError:
    return ApiError(
        f"Cannot reach the API at {url}. "
        "Start it with: uvicorn app.main:app --port 9066"
    )


def _detail(response: requests.Response) -> str:
    try:
        body = response.json()
    except Exception:
        text = (response.text or "").strip()
        return text or f"Request failed ({response.status_code})"
    detail = body.get("detail", body) if isinstance(body, dict) else body
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict):
                parts.append(str(item.get("msg") or item))
            else:
                parts.append(str(item))
        return "; ".join(parts) or f"Request failed ({response.status_code})"
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("error") or detail)
    return str(detail)


def _request(method: str, path: str, timeout: float = 30, **kwargs: Any) -> Any:
    url = f"{base_url()}{path}"
    try:
        response = requests.request(method, url, timeout=timeout, **kwargs)
    except requests.ConnectionError as exc:
        raise _unreachable(base_url()) from exc
    except requests.Timeout as exc:
        raise ApiError(f"The API at {base_url()} timed out.") from exc
    except requests.RequestException as exc:
        raise _unreachable(base_url()) from exc
    if not response.ok:
        raise ApiError(_detail(response), response.status_code)
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def health() -> dict:
    return _request("GET", "/health", timeout=10)


def status() -> dict:
    return _request("GET", "/status", timeout=15)


def config() -> dict:
    return _request("GET", "/config", timeout=10)


def list_policies(limit: int = 200) -> list:
    return _request("GET", f"{PREFIX}/policies/", params={"limit": limit}) or []


def get_policy(policy_id: str) -> dict:
    return _request("GET", f"{PREFIX}/policies/{policy_id}")


def update_policy(policy_id: str, payload: dict) -> dict:
    return _request("PUT", f"{PREFIX}/policies/{policy_id}", json=payload, timeout=30)


def delete_policy(policy_id: str) -> dict:
    return _request("DELETE", f"{PREFIX}/policies/{policy_id}")


def patch_variable(
    policy_id: str,
    name: str,
    *,
    is_mandatory: bool | None = None,
    default_value: str | None = None,
) -> dict:
    body: dict[str, Any] = {}
    if is_mandatory is not None:
        body["is_mandatory"] = is_mandatory
    if default_value is not None:
        body["default_value"] = default_value
    return _request(
        "PATCH", f"{PREFIX}/policies/{policy_id}/variables/{name}", json=body
    )


def compile_policy(policy_id: str) -> dict:
    return _request("POST", f"{PREFIX}/policies/{policy_id}/compile", timeout=60)


def variable_analysis(policy_id: str) -> dict:
    return _request("GET", f"{PREFIX}/policies/{policy_id}/variable-analysis")


def rule_grounding(policy_id: str) -> dict:
    return _request("GET", f"{PREFIX}/policies/{policy_id}/grounding", timeout=60)


def fix_missing_variables(policy_id: str, auto_add: bool = True) -> dict:
    return _request(
        "POST",
        f"{PREFIX}/policies/{policy_id}/fix-missing-variables",
        params={"auto_add": auto_add},
        timeout=30,
    )


def run_test_scenarios(policy_id: str) -> dict:
    return _request(
        "POST",
        f"{PREFIX}/policies/{policy_id}/test-scenarios",
        json={"max_scenarios_per_category": 2},
        timeout=180,
    )


def upload_document(filename: str, content: bytes, domain: str) -> dict:
    return _request(
        "POST",
        f"{PREFIX}/documents/upload",
        files={"file": (filename, content)},
        data={"domain": domain},
        timeout=60,
    )


def policies_for_document(document_id: str) -> list:
    return _request("GET", f"{PREFIX}/policies/by-document/{document_id}") or []


def wait_for_policy(document_id: str, timeout: float = 40, interval: float = 2) -> dict:
    deadline = time.time() + timeout
    while True:
        found = policies_for_document(document_id)
        if found:
            return found[0]
        if time.time() >= deadline:
            raise ApiError(
                "The document uploaded, but no policy was ready yet. Refresh the list shortly."
            )
        time.sleep(interval)


def verify(policy_id: str, question: str, answer: str, facts: dict | None = None) -> dict:
    body = {"question": question, "answer": answer}
    if facts:
        body["facts"] = facts
    return _request(
        "POST",
        f"{PREFIX}/policies/{policy_id}/verify",
        json=body,
        timeout=90,
    )


def list_verifications(policy_id: str, limit: int = 50) -> list:
    return _request(
        "GET",
        f"{PREFIX}/policies/{policy_id}/verifications",
        params={"limit": limit},
    ) or []
