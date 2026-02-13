"""OpenRouter adapter — cloud LLM gateway via OpenAI-compatible API."""
import logging
from openai import OpenAI

from adapters.base import ModelAdapter, ModelCapability, RetryConfig, ProviderUnavailableError
from config import get_settings

logger = logging.getLogger(__name__)


class OpenRouterAdapter(ModelAdapter):
    """
    OpenRouter adapter for accessing 100+ models via a single API key.

    Uses OpenAI-compatible client pointing to openrouter.ai.
    is_local = False — requires external network access.
    """

    name = "openrouter"
    is_local = False

    def __init__(self, retry_config: RetryConfig | None = None):
        super().__init__(retry_config)
        # Register known model capabilities
        self._register_known_models()

    def _get_client(self) -> OpenAI:
        settings = get_settings()
        if not settings.openrouter_api_key:
            raise ProviderUnavailableError(
                "OpenRouter API key not configured. "
                "Set OPENROUTER_API_KEY in .env or via the settings panel."
            )
        return OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            timeout=30.0,  # 30 second timeout for API calls
        )

    def _do_chat(self, messages: list[dict], model: str, temperature: float, max_tokens: int) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    def is_available(self) -> bool:
        settings = get_settings()
        return bool(settings.openrouter_api_key)

    def list_models(self) -> list[str]:
        """Return commonly used OpenRouter models."""
        return [
            "google/gemini-2.0-flash-001",
            "deepseek/deepseek-chat-v3-0324:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "qwen/qwen-2.5-coder-32b-instruct:free",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o-mini",
        ]

    def _register_known_models(self) -> None:
        self.register_capability("google/gemini-2.0-flash-001", ModelCapability(
            max_tokens=8192, context_window=1_000_000,
            supports_json_mode=True, supports_streaming=True,
            supports_function_calling=True,
            cost_per_1k_input=0.0001, cost_per_1k_output=0.0004,
            recommended_for=["parsing"],
        ))
        self.register_capability("deepseek/deepseek-chat-v3-0324:free", ModelCapability(
            max_tokens=8192, context_window=65536,
            supports_json_mode=True, supports_streaming=True,
            supports_function_calling=False,
            cost_per_1k_input=None, cost_per_1k_output=None,
            recommended_for=["generation"],
        ))
        self.register_capability("meta-llama/llama-3.3-70b-instruct:free", ModelCapability(
            max_tokens=4096, context_window=131072,
            supports_json_mode=False, supports_streaming=True,
            supports_function_calling=False,
            cost_per_1k_input=None, cost_per_1k_output=None,
            recommended_for=["both"],
        ))
        self.register_capability("qwen/qwen-2.5-coder-32b-instruct:free", ModelCapability(
            max_tokens=4096, context_window=32768,
            supports_json_mode=True, supports_streaming=True,
            supports_function_calling=False,
            cost_per_1k_input=None, cost_per_1k_output=None,
            recommended_for=["generation"],
        ))
