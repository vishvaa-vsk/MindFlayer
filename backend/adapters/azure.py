"""Azure OpenAI adapter — enterprise Azure-hosted models."""
import logging
from openai import AzureOpenAI

from adapters.base import ModelAdapter, ModelCapability, RetryConfig, ProviderUnavailableError
from config import get_settings

logger = logging.getLogger(__name__)


class AzureAdapter(ModelAdapter):
    """
    Azure OpenAI adapter for enterprise Azure-hosted models.

    Uses deployment names instead of model IDs.
    is_local = False — requires Azure cloud access.
    """

    name = "azure"
    is_local = False

    def __init__(self, retry_config: RetryConfig | None = None):
        super().__init__(retry_config)
        self._register_known_models()

    def _get_client(self) -> AzureOpenAI:
        settings = get_settings()
        if not settings.azure_endpoint or not settings.azure_api_key:
            raise ProviderUnavailableError(
                "Azure OpenAI not configured. "
                "Set AZURE_ENDPOINT and AZURE_API_KEY in settings."
            )
        return AzureOpenAI(
            azure_endpoint=settings.azure_endpoint,
            api_key=settings.azure_api_key,
            api_version=settings.azure_api_version,
            timeout=30.0,  # 30 second timeout for API calls
        )

    def _resolve_deployment(self, model: str) -> str:
        """
        Resolve model identifier to Azure deployment name.

        Azure uses deployment names, not model IDs. Users can either:
        - Pass the deployment name directly
        - Use config-level deployment mappings (azure_deployment_parsing, azure_deployment_generation)
        """
        settings = get_settings()
        # If the model matches a config deployment, use it
        if model == settings.parsing_model and settings.azure_deployment_parsing:
            return settings.azure_deployment_parsing
        if model == settings.generation_model and settings.azure_deployment_generation:
            return settings.azure_deployment_generation
        # Otherwise assume the model string IS the deployment name
        return model

    def _do_chat(self, messages: list[dict], model: str, temperature: float, max_tokens: int) -> str:
        client = self._get_client()
        deployment = self._resolve_deployment(model)

        try:
            response = client.chat.completions.create(
                model=deployment,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            if "DeploymentNotFound" in str(e):
                raise ProviderUnavailableError(
                    f"Azure deployment '{deployment}' not found. "
                    "Check your deployment name in Azure Portal."
                )
            raise

    def is_available(self) -> bool:
        settings = get_settings()
        return bool(settings.azure_endpoint and settings.azure_api_key)

    def list_models(self) -> list[str]:
        """Return configured Azure deployments."""
        settings = get_settings()
        models = []
        if settings.azure_deployment_parsing:
            models.append(settings.azure_deployment_parsing)
        if settings.azure_deployment_generation:
            models.append(settings.azure_deployment_generation)
        # Deduplicate
        return list(dict.fromkeys(models)) if models else ["gpt-4o", "gpt-4o-mini"]

    def _register_known_models(self) -> None:
        self.register_capability("gpt-4o", ModelCapability(
            max_tokens=16384, context_window=128000,
            supports_json_mode=True, supports_streaming=True,
            supports_function_calling=True,
            cost_per_1k_input=0.005, cost_per_1k_output=0.015,
            recommended_for=["both"],
        ))
        self.register_capability("gpt-4o-mini", ModelCapability(
            max_tokens=16384, context_window=128000,
            supports_json_mode=True, supports_streaming=True,
            supports_function_calling=True,
            cost_per_1k_input=0.00015, cost_per_1k_output=0.0006,
            recommended_for=["parsing", "generation"],
        ))
        self.register_capability("gpt-35-turbo", ModelCapability(
            max_tokens=4096, context_window=16384,
            supports_json_mode=True, supports_streaming=True,
            supports_function_calling=True,
            cost_per_1k_input=0.0005, cost_per_1k_output=0.0015,
            recommended_for=["parsing"],
        ))
