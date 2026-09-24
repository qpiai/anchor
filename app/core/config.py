import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/reasoning")
    
    # API Keys
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    
    # App Settings
    app_name: str = "Anchor"
    debug: bool = os.getenv("DEBUG", "False").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    # File Upload
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    upload_dir: str = "uploads"
    
    # API Settings
    api_v1_prefix: str = "/api/v1"
    
    # LLM Settings
    default_llm_provider: str = os.getenv("DEFAULT_LLM_PROVIDER", "openai")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    anthropic_model: str = "claude-3-sonnet-20240229"
    
    # vLLM/OpenAI Custom Endpoint Support
    openai_base_url: Optional[str] = os.getenv("OPENAI_BASE_URL")

    # TypeSafe (Jev) Settings
    typesafe_api_key: Optional[str] = os.getenv("TYPESAFE_API_KEY")
    jev_model: str = os.getenv("JEV_MODEL", "jev-latest")
    # "auto" (jev when TYPESAFE_API_KEY is set, else llm), "jev", or "llm"
    variable_extractor: str = os.getenv("VARIABLE_EXTRACTOR", "auto")
    jev_confidence_threshold: float = float(os.getenv("JEV_CONFIDENCE_THRESHOLD", "0.55"))
    # Derived numbers ("two weeks" -> 14 days) come back with low confidence even when correct
    jev_number_confidence_threshold: Optional[float] = float(
        os.getenv("JEV_NUMBER_CONFIDENCE_THRESHOLD", "0.25")
    )
    jev_guards_enabled: bool = os.getenv("JEV_GUARDS_ENABLED", "true").lower() == "true"
    jev_block_out_of_scope: bool = os.getenv("JEV_BLOCK_OUT_OF_SCOPE", "false").lower() == "true"
    jev_scope_threshold: float = float(os.getenv("JEV_SCOPE_THRESHOLD", "0.3"))
    jev_injection_threshold: float = float(os.getenv("JEV_INJECTION_THRESHOLD", "0.7"))
    jev_timeout_seconds: float = float(os.getenv("JEV_TIMEOUT_SECONDS", "10"))
    # When false, extraction never calls GPT. A Jev outage is a hard error.
    jev_llm_fallback: bool = os.getenv("JEV_LLM_FALLBACK", "true").lower() == "true"
    # Hybrid, tuned by benchmark (see bench/RESULTS.md).
    # GPT fills empty mandatory facts Jev was below this confidence on. Empty string disables.
    hybrid_escalate_below: Optional[float] = (
        float(os.getenv("HYBRID_ESCALATE_BELOW", "0.6")) if os.getenv("HYBRID_ESCALATE_BELOW", "0.6") else None
    )
    # GPT must agree before a VALID stands, when any fact behind it is below HYBRID_CHECK_BELOW.
    # 0.9 let a dangerous approval through on the tune split; 0.95 did not.
    hybrid_confirm_approvals: bool = os.getenv("HYBRID_CONFIRM_APPROVALS", "true").lower() == "true"
    hybrid_check_below: float = float(os.getenv("HYBRID_CHECK_BELOW", "0.95"))
    # gpt-6-luna reasoning effort. Extraction has its own knob.
    openai_reasoning_effort: str = os.getenv("OPENAI_REASONING_EFFORT", "low")
    # "none" was the fastest and most accurate extraction effort in the bench.
    extraction_reasoning_effort: str = os.getenv("EXTRACTION_REASONING_EFFORT", "none")
    # If the approval check cannot run (GPT down), hold the approval instead of trusting Jev alone.
    hybrid_fail_closed: bool = os.getenv("HYBRID_FAIL_CLOSED", "true").lower() == "true"
    # A suspected injection never ends in VALID; denials and questions are unaffected.
    jev_injection_holds_approval: bool = os.getenv("JEV_INJECTION_HOLDS_APPROVAL", "true").lower() == "true"
    
    class Config:
        # Absolute so MCP clients that launch from another cwd still load the repo's .env
        env_file = str(Path(__file__).resolve().parents[2] / ".env")

settings = Settings()

def get_openai_api_params(max_tokens: int = None, temperature: float = 0.3, effort: str | None = None) -> dict:
    """
    Returns the correct API parameters for OpenAI calls based on the model.
    Reasoning models (gpt-5*, gpt-6*, o-series) reject max_tokens and temperature.
    """
    model = settings.openai_model.lower()

    reasoning_prefixes = ("gpt-5", "gpt-6", "o1", "o3", "o4")

    if model.startswith(reasoning_prefixes):
        return {
            "reasoning_effort": effort or settings.openai_reasoning_effort
        }
    else:
        # Standard GPT-4 and other models
        return {
            "max_tokens": max_tokens,
            "temperature": temperature
        } 