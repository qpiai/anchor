from app.core.config import settings
from app.services.extraction import (
    LlmVariableExtractor,
    get_variable_extractor,
    reset_variable_extractor,
    resolved_extractor_mode,
)
from app.services.jev_extractor import JevVariableExtractor


def setup_function():
    reset_variable_extractor()


def teardown_function():
    reset_variable_extractor()


def test_auto_uses_jev_when_key_present(monkeypatch):
    monkeypatch.setattr(settings, "variable_extractor", "auto")
    monkeypatch.setattr(settings, "typesafe_api_key", "test-key")
    reset_variable_extractor()
    assert resolved_extractor_mode() == "jev"
    assert isinstance(get_variable_extractor(), JevVariableExtractor)


def test_auto_uses_llm_without_key(monkeypatch):
    monkeypatch.setattr(settings, "variable_extractor", "auto")
    monkeypatch.setattr(settings, "typesafe_api_key", None)
    reset_variable_extractor()
    assert resolved_extractor_mode() == "llm"
    assert isinstance(get_variable_extractor(), LlmVariableExtractor)


def test_explicit_jev_and_llm(monkeypatch):
    monkeypatch.setattr(settings, "typesafe_api_key", None)
    monkeypatch.setattr(settings, "variable_extractor", "jev")
    reset_variable_extractor()
    assert isinstance(get_variable_extractor(), JevVariableExtractor)
    monkeypatch.setattr(settings, "variable_extractor", "llm")
    reset_variable_extractor()
    assert isinstance(get_variable_extractor(), LlmVariableExtractor)


def test_singleton_reused(monkeypatch):
    monkeypatch.setattr(settings, "variable_extractor", "llm")
    reset_variable_extractor()
    first = get_variable_extractor()
    second = get_variable_extractor()
    assert first is second
