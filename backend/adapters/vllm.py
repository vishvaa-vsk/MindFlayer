"""vLLM adapter — local inference via OpenAI-compatible API."""
import logging
from openai import OpenAI

from adapters.base import ModelAdapter, ModelCapability, RetryConfig, ProviderUnavailableError
from config import get_settings

logger = logging.getLogger(__name__)


class VLLMAdapter(ModelAdapter):
    """
    vLLM adapter for locally hosted models with OpenAI-compatible API.

    Connects to vLLM's OpenAI-compatible server (default: http://localhost:8001).
    is_local = True — no external network calls.
    """

    name = "vllm"
    is_local = True

    def __init__(self, retry_config: RetryConfig | None = None):
        super().__init__(retry_config)

    def _get_client(self) -> OpenAI:
        settings = get_settings()
        base_url = f"{settings.vllm_base_url}/v1"
        return OpenAI(
            base_url=base_url,
            api_key="not-needed",  # vLLM doesn't require auth locally
            timeout=30.0,  # 30 second timeout for API calls
        )

    def _do_chat(self, messages: list[dict], model: str, temperature: float, max_tokens: int) -> str:
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if "Connection" in str(e) or "connect" in str(e).lower():
                settings = get_settings()
                raise ProviderUnavailableError(
                    f"Cannot connect to vLLM at {settings.vllm_base_url}. "
                    "Is vLLM running? Start with: python -m vllm.entrypoints.openai.api_server"
                )
            raise

    def is_available(self) -> bool:
        try:
            import httpx
            settings = get_settings()
            resp = httpx.get(f"{settings.vllm_base_url}/v1/models", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List models served by vLLM."""
        try:
            import httpx
            settings = get_settings()
            resp = httpx.get(f"{settings.vllm_base_url}/v1/models", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                return [m["id"] for m in data.get("data", [])]
        except Exception:
            pass
        return []

    def get_capability(self, model: str) -> ModelCapability:
        if model in self._capabilities:
            return self._capabilities[model]
        return ModelCapability(
            max_tokens=4096,
            context_window=16384,
            supports_json_mode=True,
            supports_streaming=True,
            supports_function_calling=False,
            cost_per_1k_input=None,
            cost_per_1k_output=None,
            recommended_for=["both"],
        )
