"""Ollama adapter — fully local LLM inference via Ollama API."""
import logging
import httpx

from adapters.base import ModelAdapter, ModelCapability, RetryConfig, ProviderUnavailableError
from config import get_settings

logger = logging.getLogger(__name__)


class OllamaAdapter(ModelAdapter):
    """
    Ollama adapter for locally hosted models.

    Connects to Ollama's REST API (default: http://localhost:11434).
    is_local = True — zero external network calls, fully air-gapped safe.
    """

    name = "ollama"
    is_local = True

    def __init__(self, retry_config: RetryConfig | None = None):
        super().__init__(retry_config)

    def _get_base_url(self) -> str:
        return get_settings().ollama_base_url

    def _do_chat(self, messages: list[dict], model: str, temperature: float, max_tokens: int) -> str:
        base_url = self._get_base_url()
        try:
            response = httpx.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "").strip()
        except httpx.ConnectError:
            raise ProviderUnavailableError(
                f"Cannot connect to Ollama at {base_url}. "
                "Is Ollama running? Start with: ollama serve"
            )

    def is_available(self) -> bool:
        try:
            resp = httpx.get(f"{self._get_base_url()}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List models currently pulled in Ollama."""
        try:
            resp = httpx.get(f"{self._get_base_url()}/api/tags", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return []

    def get_capability(self, model: str) -> ModelCapability:
        """Local models — no cost, capabilities depend on model."""
        if model in self._capabilities:
            return self._capabilities[model]
        # Reasonable defaults for local models
        return ModelCapability(
            max_tokens=4096,
            context_window=8192,
            supports_json_mode=False,
            supports_streaming=True,
            supports_function_calling=False,
            cost_per_1k_input=None,
            cost_per_1k_output=None,
            recommended_for=["both"],
        )
