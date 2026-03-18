"""
Configuration management for AutoAuth Agent
"""
from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

VALID_PROVIDERS = {"anthropic", "gemini", "openai"}


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # LLM Provider Configuration
    llm_provider: str = "anthropic"
    llm_model: str = "auto"
    max_tokens: int = 2048
    temperature: float = 0.0

    # API Keys
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

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
        # Map environment variable names to field names
        fields = {
            "max_tokens": {"env": "LLM_MAX_TOKENS"},
            "temperature": {"env": "LLM_TEMPERATURE"},
            "llm_provider": {"env": "LLM_PROVIDER"},
            "llm_model": {"env": "LLM_MODEL"},
        }

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("llm_provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in VALID_PROVIDERS:
            raise ValueError(
                f"Invalid LLM_PROVIDER '{v}'. Must be one of: {sorted(VALID_PROVIDERS)}"
            )
        return v

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"temperature must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        if v < 1 or v > 32_768:
            raise ValueError(f"max_tokens must be between 1 and 32768, got {v}")
        return v

    @model_validator(mode="after")
    def validate_api_key_present(self) -> "Settings":
        """Warn (not crash) if the selected provider's API key is missing."""
        key_map = {
            "anthropic": self.anthropic_api_key,
            "gemini": self.gemini_api_key,
            "openai": self.openai_api_key,
        }
        key = key_map.get(self.llm_provider)
        if not key:
            logger.warning(
                "API key for provider '%s' is not set. "
                "Set the corresponding environment variable before making LLM calls.",
                self.llm_provider,
            )
        return self

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def claude_model(self) -> str:
        """Backward compatibility shim."""
        return self.llm_model if self.llm_provider == "anthropic" else "claude-sonnet-4-20250514"


def _load_settings() -> Settings:
    """Load settings and create required directories, with a clear error on misconfiguration."""
    try:
        s = Settings()
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load application settings: {exc}\n"
            "Check your .env file or environment variables."
        ) from exc

    for path in (s.mock_data_dir, s.policies_dir, s.output_dir):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            logger.warning("Could not create directory '%s': %s", path, exc)

    return s


# Singleton instance — raises RuntimeError at import time if config is broken,
# giving an immediate, actionable message rather than a cryptic pydantic error.
settings = _load_settings()
