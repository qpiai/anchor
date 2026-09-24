import pytest

from app.services.grounding import check_rules, clear_grounding_cache


class _Noul:
    def __init__(self, noul):
        self.noul = noul


class _Choice:
    def __init__(self, choice, confidence):
        self.choice = choice
        self.confidence = confidence


class _Response:
    def __init__(self, nouls=None, choices=None):
        self.nouls = nouls or {}
        self.choices = choices or {}
        self.model = "jev-test"
        self.usage = None


@pytest.mark.asyncio
async def test_grounding_flags_low_support(monkeypatch):
    clear_grounding_cache()

    async def _ask(state, questions):
        assert "support_real" in questions
        assert "support_fake" in questions
        return {
            "response": _Response(nouls={
                "support_real": _Noul(0.91),
                "support_fake": _Noul(0.12),
            }),
            "latency_ms": 1,
            "usage": None,
            "model": "jev-test",
        }

    monkeypatch.setattr("app.services.grounding.ask", _ask)
    source = "Employees may take 10 days of leave.\n\nContractors are not eligible for leave."
    rules = [
        {"id": "real", "description": "Ten days of leave", "condition": "days <= 10", "conclusion": "valid"},
        {"id": "fake", "description": "Unlimited leave", "condition": "days > 0", "conclusion": "valid"},
    ]
    report = await check_rules("policy-1", rules, source)
    by_id = {row["rule_id"]: row for row in report["rules"]}
    assert by_id["real"]["flag"] is False
    assert by_id["fake"]["flag"] is True
    assert by_id["fake"]["supported_probability"] == 0.12
    assert by_id["real"]["passage"]
