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
    app_name: str = "Automated Reasoning Backend"
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