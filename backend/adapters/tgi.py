"""HuggingFace Text Generation Inference (TGI) adapter — local inference."""
import logging
import httpx

from adapters.base import ModelAdapter, ModelCapability, RetryConfig, ProviderUnavailableError
from config import get_settings

logger = logging.getLogger(__name__)


class TGIAdapter(ModelAdapter):
    """
    HuggingFace TGI adapter for locally hosted models.

    Connects to TGI's REST API (default: http://localhost:8080).
    is_local = True — no external network calls.
    """

    name = "tgi"
    is_local = True

    def __init__(self, retry_config: RetryConfig | None = None):
        super().__init__(retry_config)

    def _get_base_url(self) -> str:
        return get_settings().tgi_base_url

    def _do_chat(self, messages: list[dict], model: str, temperature: float, max_tokens: int) -> str:
        base_url = self._get_base_url()

        # TGI Messages API (v1.4+)
        # Try chat-compatible endpoint first, fall back to /generate
        try:
            return self._chat_messages_api(base_url, messages, model, temperature, max_tokens)
        except (httpx.HTTPStatusError, KeyError):
            return self._generate_api(base_url, messages, temperature, max_tokens)

    def _chat_messages_api(
        self, base_url: str, messages: list[dict],
        model: str, temperature: float, max_tokens: int,
    ) -> str:
        """Use TGI's OpenAI-compatible /v1/chat/completions endpoint."""
        response = httpx.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    def _generate_api(
        self, base_url: str, messages: list[dict],
        temperature: float, max_tokens: int,
    ) -> str:
        """Fallback: use TGI's native /generate endpoint."""
        # Flatten messages into a single prompt
        prompt = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
        )
        prompt += "\nassistant:"

        try:
            response = httpx.post(
                f"{base_url}/generate",
                json={
                    "inputs": prompt,
                    "parameters": {
                        "temperature": temperature,
                        "max_new_tokens": max_tokens,
                        "return_full_text": False,
                    },
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()

            # TGI returns list or dict depending on version
            if isinstance(data, list):
                return data[0].get("generated_text", "").strip()
            return data.get("generated_text", "").strip()
        except httpx.ConnectError:
            raise ProviderUnavailableError(
                f"Cannot connect to TGI at {base_url}. "
                "Is TGI running? Start with: text-generation-launcher --model-id <model>"
            )

    def is_available(self) -> bool:
        try:
            base_url = self._get_base_url()
            resp = httpx.get(f"{base_url}/info", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """TGI serves a single model — return it from /info."""
        try:
            base_url = self._get_base_url()
            resp = httpx.get(f"{base_url}/info", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                model_id = data.get("model_id", "")
                return [model_id] if model_id else []
        except Exception:
            pass
        return []

    def get_capability(self, model: str) -> ModelCapability:
        if model in self._capabilities:
            return self._capabilities[model]
        return ModelCapability(
            max_tokens=2048,
            context_window=8192,
            supports_json_mode=False,
            supports_streaming=True,
            supports_function_calling=False,
            cost_per_1k_input=None,
            cost_per_1k_output=None,
            recommended_for=["both"],
        )
