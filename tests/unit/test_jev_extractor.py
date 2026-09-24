import asyncio

import pytest
from typesafe_sdk import TypeSafeError

from app.core.config import settings
from app.services import jev_extractor as je
from app.services.jev_extractor import (
    ExtractorUnavailableError,
    JevVariableExtractor,
    _INJECTION,
    _IN_SCOPE,
)


class _Choice:
    def __init__(self, choice, confidence):
        self.choice = choice
        self.confidence = confidence
        self.probabilities = {choice: confidence}


class _Noul:
    def __init__(self, noul):
        self.noul = noul


class _Response:
    def __init__(self, choices=None, nouls=None, model="jev-test"):
        self.choices = choices or {}
        self.nouls = nouls or {}
        self.model = model
        self.usage = None


class _FakeLLM:
    def __init__(self, configured=True, values=None):
        self.openai_client = object() if configured else None
        self.anthropic_client = None
        self.values = values or {}
        self.calls = []

    async def extract_variables(self, question, answer, policy_variables):
        self.calls.append([var["name"] for var in policy_variables])
        if self.values:
            return dict(self.values)
        return {var["name"]: "from-llm" for var in policy_variables}

    async def validate_extracted_variables(self, variables, policy_variables):
        return []


def _ask_returning(response):
    async def _ask(state, questions):
        _ask.questions = questions
        _ask.state = state
        return {"response": response, "latency_ms": 12.0, "usage": None, "model": response.model}

    _ask.questions = None
    return _ask


@pytest.fixture
def thresholds(monkeypatch):
    monkeypatch.setattr(settings, "jev_confidence_threshold", 0.5)
    monkeypatch.setattr(settings, "jev_number_confidence_threshold", None)
    monkeypatch.setattr(settings, "jev_guards_enabled", False)


def _enum():
    return {
        "name": "employee_type",
        "type": "enum",
        "description": "Employment type",
        "possible_values": ["full_time", "contractor"],
        "is_mandatory": True,
    }


def _bool(mandatory=True):
    return {
        "name": "approved",
        "type": "boolean",
        "description": "The request is approved",
        "is_mandatory": mandatory,
    }


def _number(mandatory=True):
    return {
        "name": "leave_days",
        "type": "number",
        "description": "Days of leave",
        "is_mandatory": mandatory,
    }


@pytest.mark.asyncio
async def test_enum_pick(monkeypatch, thresholds):
    ask = _ask_returning(_Response(choices={"employee_type": _Choice("full_time", 0.91)}))
    monkeypatch.setattr("app.services.jev_extractor.ask", ask)
    result = await JevVariableExtractor(_FakeLLM()).extract_detailed("q", "full time", [_enum()])
    assert result["variables"]["employee_type"] == "full_time"
    assert result["values"]["employee_type"] == "full_time"
    assert result["confidence"]["employee_type"] == 0.91
    assert result["sources"]["employee_type"] == "jev"
    assert result["fallback_used"] is False


@pytest.mark.asyncio
async def test_boolean_false(monkeypatch, thresholds):
    ask = _ask_returning(_Response(choices={"approved": _Choice("false", 0.8)}))
    monkeypatch.setattr("app.services.jev_extractor.ask", ask)
    result = await JevVariableExtractor(_FakeLLM()).extract_detailed(
        "Is it approved?", "No, it was not approved", [_bool()]
    )
    assert result["values"]["approved"] is False
    assert result["variables"]["approved"] is False


@pytest.mark.asyncio
async def test_number_candidate(monkeypatch, thresholds):
    ask = _ask_returning(_Response(choices={"leave_days": _Choice("c0", 0.88)}))
    monkeypatch.setattr("app.services.jev_extractor.ask", ask)
    result = await JevVariableExtractor(_FakeLLM()).extract_detailed(
        "How long?", "10 days", [_number()]
    )
    assert result["values"]["leave_days"] == 10
    assert result["sources"]["leave_days"] == "jev"


@pytest.mark.asyncio
async def test_not_stated_markers(monkeypatch, thresholds):
    optional = _number(mandatory=False)
    optional["name"] = "optional_days"
    ask = _ask_returning(_Response(choices={
        "leave_days": _Choice("not_stated", 0.95),
        "optional_days": _Choice("not_stated", 0.95),
    }))
    monkeypatch.setattr("app.services.jev_extractor.ask", ask)
    result = await JevVariableExtractor(_FakeLLM()).extract_detailed(
        "q", "nothing numeric here wait 1 day is stated but we pick not_stated",
        [_number(), optional],
    )
    assert result["values"]["leave_days"] is None
    assert result["variables"]["leave_days"] == "MISSING_MANDATORY"
    assert result["variables"]["optional_days"] == "SKIP_RULE"


@pytest.mark.asyncio
async def test_threshold_gates_low_confidence(monkeypatch, thresholds):
    ask = _ask_returning(_Response(choices={"employee_type": _Choice("full_time", 0.2)}))
    monkeypatch.setattr("app.services.jev_extractor.ask", ask)
    result = await JevVariableExtractor(_FakeLLM()).extract_detailed("q", "maybe", [_enum()])
    assert result["values"]["employee_type"] is None
    assert result["confidence"]["employee_type"] == 0.2
    assert result["variables"]["employee_type"] == "MISSING_MANDATORY"


@pytest.mark.asyncio
async def test_number_threshold(monkeypatch, thresholds):
    monkeypatch.setattr(settings, "jev_number_confidence_threshold", 0.3)
    ask = _ask_returning(_Response(choices={"leave_days": _Choice("c0", 0.4)}))
    monkeypatch.setattr("app.services.jev_extractor.ask", ask)
    kept = await JevVariableExtractor(_FakeLLM()).extract_detailed("q", "two weeks", [_number()])
    assert kept["values"]["leave_days"] == 14 or kept["values"]["leave_days"] == 2

    ask_low = _ask_returning(_Response(choices={"leave_days": _Choice("c0", 0.2)}))
    monkeypatch.setattr("app.services.jev_extractor.ask", ask_low)
    gated = await JevVariableExtractor(_FakeLLM()).extract_detailed("q", "two weeks", [_number()])
    assert gated["values"]["leave_days"] is None
    assert gated["variables"]["leave_days"] == "MISSING_MANDATORY"


@pytest.mark.asyncio
async def test_unsupported_delegated_to_llm(monkeypatch, thresholds):
    monkeypatch.setattr(settings, "jev_llm_fallback", True)
    blob = {"name": "note", "type": "blob", "description": "Note", "is_mandatory": False}
    llm = _FakeLLM(values={"note": "hello"})
    ask = _ask_returning(_Response(choices={"employee_type": _Choice("full_time", 0.9)}))
    monkeypatch.setattr("app.services.jev_extractor.ask", ask)
    result = await JevVariableExtractor(llm).extract_detailed("q", "a note", [blob, _enum()])
    assert llm.calls == [["note"]]
    assert result["sources"]["note"] == "llm"
    assert result["variables"]["note"] == "hello"
    assert result["sources"]["employee_type"] == "jev"


@pytest.mark.asyncio
async def test_jev_error_falls_back(monkeypatch, thresholds):
    async def _boom(state, questions):
        raise TypeSafeError("upstream failed")

    monkeypatch.setattr("app.services.jev_extractor.ask", _boom)
    monkeypatch.setattr(settings, "jev_llm_fallback", True)
    llm = _FakeLLM(values={"employee_type": "full_time"})
    result = await JevVariableExtractor(llm).extract_detailed("q", "a", [_enum()])
    assert result["fallback_used"] is True
    assert result["fallback_reason"]
    assert result["sources"]["employee_type"] == "llm"
    assert result["variables"]["employee_type"] == "full_time"
    assert "TypeSafeError" in result["fallback_reason"]


@pytest.mark.asyncio
async def test_guards_parsed(monkeypatch, thresholds):
    monkeypatch.setattr(settings, "jev_guards_enabled", True)
    response = _Response(
        choices={"employee_type": _Choice("contractor", 0.99)},
        nouls={_IN_SCOPE: _Noul(0.82), _INJECTION: _Noul(0.1)},
    )
    ask = _ask_returning(response)
    monkeypatch.setattr("app.services.jev_extractor.ask", ask)
    result = await JevVariableExtractor(_FakeLLM()).extract_detailed(
        "q",
        "a",
        [_enum()],
        policy_context={"name": "Leave", "description": "HR leave", "domain": "hr"},
    )
    assert _IN_SCOPE in ask.questions
    assert _INJECTION in ask.questions
    injection = ask.questions[_INJECTION]
    assert "by instruction rather than by stating a fact" in injection.criteria["true"]
    assert "not an injection" in injection.criteria["false"]
    assert result["guards"]["in_scope"] == 0.82
    assert result["guards"]["injection"] == 0.1

    ask_no_ctx = _ask_returning(_Response(nouls={_INJECTION: _Noul(0.2)}))
    monkeypatch.setattr("app.services.jev_extractor.ask", ask_no_ctx)
    await JevVariableExtractor(_FakeLLM()).extract_detailed("q", "a", [_enum()])
    assert _IN_SCOPE not in ask_no_ctx.questions
    assert _INJECTION in ask_no_ctx.questions


def _date_var():
    return {"name": "start_date", "type": "date", "description": "Start date", "is_mandatory": True}


def _note():
    return {"name": "note", "type": "string", "description": "A free-text note", "is_mandatory": False}


@pytest.mark.asyncio
async def test_date_absolute_components(monkeypatch, thresholds):
    monkeypatch.setattr("app.services.jev_extractor.find_date_candidates", lambda text, today=None: [])
    ask = _ask_returning(_Response(choices={
        "start_date__year": _Choice("2024", 0.9),
        "start_date__month": _Choice("3", 0.9),
        "start_date__day": _Choice("15", 0.9),
    }))
    monkeypatch.setattr("app.services.jev_extractor.ask", ask)
    result = await JevVariableExtractor(_FakeLLM()).extract_detailed("q", "March 15, 2024", [_date_var()])
    assert result["values"]["start_date"] == "2024-03-15"
    assert result["sources"]["start_date"] == "jev"


@pytest.mark.asyncio
async def test_date_relative_candidate(monkeypatch, thresholds):
    monkeypatch.setattr(
        "app.services.jev_extractor.find_date_candidates",
        lambda text, today=None: [{"span": "tomorrow", "iso": "2026-09-25"}],
    )
    ask = _ask_returning(_Response(choices={"start_date__when": _Choice("d0", 0.8)}))
    monkeypatch.setattr("app.services.jev_extractor.ask", ask)
    result = await JevVariableExtractor(_FakeLLM()).extract_detailed("q", "tomorrow", [_date_var()])
    assert result["values"]["start_date"] == "2026-09-25"
    assert result["sources"]["start_date"] == "jev"


@pytest.mark.asyncio
async def test_date_missing_day_is_none(monkeypatch, thresholds):
    monkeypatch.setattr("app.services.jev_extractor.find_date_candidates", lambda text, today=None: [])
    ask = _ask_returning(_Response(choices={
        "start_date__year": _Choice("2024", 0.9),
        "start_date__month": _Choice("3", 0.9),
        "start_date__day": _Choice("not_stated", 0.9),
    }))
    monkeypatch.setattr("app.services.jev_extractor.ask", ask)
    result = await JevVariableExtractor(_FakeLLM()).extract_detailed("q", "March 2024", [_date_var()])
    assert result["values"]["start_date"] is None
    assert result["sources"]["start_date"] == "jev"


@pytest.mark.asyncio
async def test_string_email_and_code(monkeypatch, thresholds):
    email = {**_note(), "name": "contact"}
    code = {**_note(), "name": "ticket"}
    ask = _ask_returning(_Response(choices={
        "contact": _Choice("s0", 0.93),
        "ticket": _Choice("s0", 0.93),
    }))
    monkeypatch.setattr("app.services.jev_extractor.ask", ask)
    email_result = await JevVariableExtractor(_FakeLLM()).extract_detailed(
        "q", "contact ada@example.com please", [email]
    )
    code_result = await JevVariableExtractor(_FakeLLM()).extract_detailed(
        "q", "ref ABC-1234 is open", [code]
    )
    assert email_result["values"]["contact"] == "ada@example.com"
    assert email_result["sources"]["contact"] == "jev"
    assert code_result["values"]["ticket"] == "ABC-1234"
    assert code_result["sources"]["ticket"] == "jev"


@pytest.mark.asyncio
async def test_string_with_no_candidates_is_none(monkeypatch, thresholds):
    ask = _ask_returning(_Response())
    monkeypatch.setattr("app.services.jev_extractor.ask", ask)
    result = await JevVariableExtractor(_FakeLLM()).extract_detailed("q", "nothing to extract", [_note()])
    assert result["values"]["note"] is None
    assert result["sources"]["note"] == "none"
    assert ask.questions is None


@pytest.mark.asyncio
async def test_fallback_off_raises(monkeypatch, thresholds):
    async def _boom(state, questions):
        raise TypeSafeError("upstream failed")

    monkeypatch.setattr("app.services.jev_extractor.ask", _boom)
    monkeypatch.setattr(settings, "jev_llm_fallback", False)
    llm = _FakeLLM(values={"employee_type": "full_time"})
    with pytest.raises(ExtractorUnavailableError):
        await JevVariableExtractor(llm).extract_detailed("q", "a", [_enum()])
    assert llm.calls == []


@pytest.mark.asyncio
async def test_fallback_off_skips_llm_for_unsupported(monkeypatch, thresholds):
    monkeypatch.setattr(settings, "jev_llm_fallback", False)
    blob = {"name": "note", "type": "blob", "description": "Note", "is_mandatory": False}
    llm = _FakeLLM()
    result = await JevVariableExtractor(llm).extract_detailed("q", "a", [blob])
    assert llm.calls == []
    assert result["values"]["note"] is None
    assert result["sources"]["note"] == "none"


def test_client_is_recreated_per_event_loop(monkeypatch):
    import asyncio

    created = []

    class DummyClient:
        def __init__(self, **kwargs):
            created.append(self)

    monkeypatch.setattr(je, "AsyncTypeSafeClient", DummyClient)
    monkeypatch.setattr(je, "_client", None)
    monkeypatch.setattr(je, "_client_loop", None)

    async def grab():
        return je._get_client(), je._get_client()

    first_a, first_b = asyncio.run(grab())
    second_a, _ = asyncio.run(grab())
    assert first_a is first_b
    assert second_a is not first_a
    assert len(created) == 2
