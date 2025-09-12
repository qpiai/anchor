import os
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
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    anthropic_model: str = "claude-3-sonnet-20240229"
    
    # vLLM/OpenAI Custom Endpoint Support
    openai_base_url: Optional[str] = os.getenv("OPENAI_BASE_URL")
    
    class Config:
        env_file = ".env"

settings = Settings()

def get_openai_api_params(max_tokens: int = None, temperature: float = 0.3) -> dict:
    """
    Returns the correct API parameters for OpenAI calls based on the model.
    GPT-5 models use reasoning_effort instead of max_tokens and temperature.
    """
    model = settings.openai_model.lower()
    
    # GPT-5 series models that use reasoning_effort parameter
    gpt5_models = ['gpt-5']
    
    if any(gpt5_model in model for gpt5_model in gpt5_models):
        # GPT-5 uses reasoning_effort instead of max_tokens and temperature
        return {
            "reasoning_effort": "low"
        }
    else:
        # Standard GPT-4 and other models
        return {
            "max_tokens": max_tokens,
            "temperature": temperature
        } 