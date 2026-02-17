"""MindFlayer configuration management."""
import os
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── LLM Provider ──────────────────────────────────────
    llm_provider: str = "openrouter"  # openrouter | ollama | vllm | tgi | azure

    # ── OpenRouter ────────────────────────────────────────
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # ── Azure OpenAI ──────────────────────────────────────
    azure_endpoint: str = Field(default="", alias="AZURE_ENDPOINT")
    azure_api_key: str = Field(default="", alias="AZURE_API_KEY")
    azure_api_version: str = "2024-02-01"
    azure_deployment_parsing: str = ""
    azure_deployment_generation: str = ""

    # ── Local Provider URLs ───────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    vllm_base_url: str = "http://localhost:8001"
    tgi_base_url: str = "http://localhost:8080"

    # ── LLM Models ────────────────────────────────────────
    parsing_model: str = "google/gemini-2.0-flash-001"
    generation_model: str = "deepseek/deepseek-chat-v3-0324:free"

    # ── LLM Parameters ───────────────────────────────────
    parsing_temperature: float = 0.3
    generation_temperature: float = 0.4

    # ── Retry Strategy ────────────────────────────────────
    llm_max_retries: int = 3
    llm_retry_base_delay: float = 1.0

    # ── Security / Data Privacy ───────────────────────────
    allow_external_calls: bool = True  # False = block openrouter + azure

    # ── Server ────────────────────────────────────────────
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # ── App ───────────────────────────────────────────────
    app_name: str = "MindFlayer"
    app_version: str = "2.0.0"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def has_api_key(self) -> bool:
        """Check if the current provider has a valid API key configured."""
        if self.llm_provider == "openrouter":
            return bool(self.openrouter_api_key)
        if self.llm_provider == "azure":
            return bool(self.azure_api_key and self.azure_endpoint)
        # Local providers don't need API keys
        if self.llm_provider in ("ollama", "vllm", "tgi"):
            return True
        return False


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

    # Clear adapter cache when settings change
    try:
        from adapters.registry import clear_adapter_cache
        clear_adapter_cache()
    except ImportError:
        pass

    return _settings
