"""MCP over STDIO, launched from another cwd like an MCP client would. Skips unless the API is reachable."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest
import requests
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

ROOT = Path(__file__).resolve().parents[2]
API_BASE_URL = os.getenv("ANCHOR_API_URL", "http://localhost:9066").rstrip("/")
API = f"{API_BASE_URL}/api/v1"


def _reachable() -> bool:
    try:
        return requests.get(f"{API_BASE_URL}/ping", timeout=2).status_code == 200
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(not _reachable(), reason="Anchor API is not reachable")


@pytest.fixture
def agent_policy_id():
    source = json.loads((ROOT / "tests" / "fixtures" / "agent_actions.json").read_text())
    payload = {
        "name": "mcp_test_agent_actions",
        "description": source.get("description") or "Rules for actions an AI support agent may take.",
        "domain": source.get("domain") or "support",
        "variables": source["variables"],
        "rules": source["rules"],
        "constraints": source.get("constraints") or [],
    }
    created = requests.post(f"{API}/policies/", json=payload, timeout=30)
    assert created.status_code == 200, created.text
    policy_id = created.json()["id"]
    compiled = requests.post(f"{API}/policies/{policy_id}/compile", timeout=60)
    assert compiled.status_code == 200 and compiled.json()["status"].lower() == "success", compiled.text
    yield policy_id
    requests.delete(f"{API}/policies/{policy_id}", timeout=30)


def _data(result):
    if getattr(result, "structured_content", None):
        return result.structured_content
    return json.loads(result.content[0].text)


async def _run(policy_id: str) -> dict:
    transport = PythonStdioTransport(
        script_path=str(ROOT / "run_mcp_server.py"),
        cwd=tempfile.gettempdir(),
        python_cmd=str(ROOT / ".venv" / "bin" / "python"),
    )
    async with Client(transport) as client:
        tools = {tool.name for tool in await client.list_tools()}
        listed = _data(await client.call_tool("list_policies", {}))
        allowed = _data(await client.call_tool("verify_response", {
            "policy_id": policy_id,
            "question": "Refund $40 to the customer's own order.",
            "answer": (
                "Action: refund of 40 USD. Identity verified. No human approval. "
                "Legitimate business purpose: refund on the customer's own order."
            ),
        }))
        blocked = _data(await client.call_tool("verify_response", {
            "policy_id": policy_id,
            "question": "Delete this customer's data now.",
            "answer": "Action: delete customer data. Identity not verified. No human approval. Customer's own account.",
        }))
        unclear = _data(await client.call_tool("verify_response", {
            "policy_id": policy_id,
            "question": "Can you do something with my account?",
        }))
        batch = _data(await client.call_tool("batch_verify", {
            "policy_id": policy_id,
            "qa_pairs": [
                {"question": "Look up the status of my own order.", "answer": "Read-only lookup, own account."},
                {"question": "Pay $500 to my friend's account.", "answer": "Payment of 500 USD, no approval, for a third party."},
            ],
        }))
        audit = _data(await client.call_tool("get_verification", {"verification_id": allowed["verification_id"]}))
        info = _data(await client.call_tool("get_policy_info", {"policy_id": policy_id}))
    return {"tools": tools, "listed": listed, "allowed": allowed, "blocked": blocked,
            "unclear": unclear, "batch": batch, "audit": audit, "info": info}


def test_mcp_tools_end_to_end(agent_policy_id):
    out = asyncio.run(_run(agent_policy_id))

    assert {"list_policies", "verify_response", "batch_verify", "get_policy_info", "get_verification"} <= out["tools"]
    listed_ids = [policy["id"] for policy in out["listed"]["policies"]]
    assert listed_ids.count(agent_policy_id) == 1

    assert out["allowed"]["result"] == "VALID", out["allowed"]
    assert out["allowed"]["extractor"] in ("jev", "llm")
    assert out["allowed"]["facts"]["action_type"]["value"] == "refund"
    assert out["blocked"]["result"] == "INVALID", out["blocked"]
    assert out["blocked"]["failed_rules"]
    assert out["unclear"]["result"] == "NEEDS_CLARIFICATION", out["unclear"]
    assert out["unclear"]["missing_facts"]

    summary = out["batch"]["summary"]
    assert summary["total"] == 2
    assert summary["valid"] + summary["invalid"] + summary["needs_clarification"] == 2
    assert summary["errors"] == 0

    assert out["audit"]["success"] and out["audit"]["verification"]["result"] == "VALID"
    assert out["audit"]["verification"]["details"]["latency_ms"]["total"] > 0
    assert out["info"]["policy"]["is_compiled"] is True
