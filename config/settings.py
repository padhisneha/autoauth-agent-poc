"""
Configuration management for AutoAuth Agent
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # LLM Provider Configuration
    llm_provider: str = os.getenv("LLM_PROVIDER")  # Options: anthropic, gemini, openai
    llm_model: str = os.getenv("LLM_MODEL")  # "auto" uses provider's default, or specify model name
    max_tokens: int = os.getenv("LLM_MAX_TOKENS")
    temperature: float = os.getenv("LLM_TEMPERATURE")
    
    # API Keys (only the one you're using needs to be set)
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    openai_api_key: Optional[str] = None
    
    # Legacy field names (for backward compatibility)
    @property
    def claude_model(self) -> str:
        """Backward compatibility"""
        return self.llm_model if self.llm_provider == "anthropic" else "claude-sonnet-4-20250514"
    
    # Application Settings
    environment: str = "development"
    log_level: str = "INFO"
    
    # FHIR Settings
    fhir_base_url: str = "http://localhost:8080/fhir"
    
    # Database (for future use)
    database_url: Optional[str] = None
    
    # Paths
    data_dir: str = "data"
    mock_data_dir: str = "data/mock_data"
    policies_dir: str = "data/policies"
    output_dir: str = "data/output"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton instance
settings = Settings()

# Create necessary directories
os.makedirs(settings.mock_data_dir, exist_ok=True)
os.makedirs(settings.policies_dir, exist_ok=True)
os.makedirs(settings.output_dir, exist_ok=True)