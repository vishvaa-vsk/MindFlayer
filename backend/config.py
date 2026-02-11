"""MindFlayer configuration management."""
import os
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # OpenRouter
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # LLM Models
    parsing_model: str = "google/gemini-2.0-flash-001"
    generation_model: str = "deepseek/deepseek-chat-v3-0324:free"

    # LLM Parameters
    parsing_temperature: float = 0.3
    generation_temperature: float = 0.4

    # Server
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # App
    app_name: str = "MindFlayer"
    app_version: str = "1.0.0"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def has_api_key(self) -> bool:
        return bool(self.openrouter_api_key)


# Singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def update_settings(**kwargs) -> Settings:
    """Update settings at runtime (e.g., from UI settings panel)."""
    global _settings
    current = get_settings()
    updated_data = current.model_dump()
    updated_data.update(kwargs)
    _settings = Settings(**updated_data)
    return _settings
