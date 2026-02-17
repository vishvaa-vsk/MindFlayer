"""Adapter registry — factory + privacy enforcement."""
import logging
from typing import Type

from adapters.base import (
    ModelAdapter,
    RetryConfig,
    PrivacyViolationError,
    ProviderUnavailableError,
)
from config import get_settings

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular dependencies
_ADAPTER_CLASSES: dict[str, str] = {
    "openrouter": "adapters.openrouter.OpenRouterAdapter",
    "ollama": "adapters.ollama.OllamaAdapter",
    "vllm": "adapters.vllm.VLLMAdapter",
    "tgi": "adapters.tgi.TGIAdapter",
    "azure": "adapters.azure.AzureAdapter",
}

# Cache instantiated adapters
_adapter_cache: dict[str, ModelAdapter] = {}


def _import_adapter_class(dotpath: str) -> Type[ModelAdapter]:
    """Dynamically import an adapter class from its dotpath."""
    module_path, class_name = dotpath.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_adapter(provider: str | None = None) -> ModelAdapter:
    """
    Get an adapter instance by provider name.

    Enforces ALLOW_EXTERNAL_CALLS — blocks non-local providers when disabled.

    Args:
        provider: Provider name. If None, uses config default.

    Returns:
        Configured ModelAdapter instance

    Raises:
        PrivacyViolationError: If trying to use external provider with ALLOW_EXTERNAL_CALLS=false
        ProviderUnavailableError: If provider is unknown
    """
    settings = get_settings()
    provider = provider or settings.llm_provider

    if provider not in _ADAPTER_CLASSES:
        raise ProviderUnavailableError(
            f"Unknown provider '{provider}'. "
            f"Available: {', '.join(_ADAPTER_CLASSES.keys())}"
        )

    # Privacy enforcement
    if not settings.allow_external_calls:
        adapter_cls = _import_adapter_class(_ADAPTER_CLASSES[provider])
        # Check if adapter is local by inspecting class attribute
        if not getattr(adapter_cls, 'is_local', False):
            local_providers = [
                name for name, path in _ADAPTER_CLASSES.items()
                if getattr(_import_adapter_class(path), 'is_local', False)
            ]
            raise PrivacyViolationError(
                f"Provider '{provider}' makes external API calls, but "
                f"ALLOW_EXTERNAL_CALLS is disabled. "
                f"Use a local provider: {', '.join(local_providers)}"
            )

    # Return cached or create new
    if provider not in _adapter_cache:
        retry_config = RetryConfig(
            max_retries=settings.llm_max_retries,
            base_delay=settings.llm_retry_base_delay,
        )
        adapter_cls = _import_adapter_class(_ADAPTER_CLASSES[provider])
        _adapter_cache[provider] = adapter_cls(retry_config=retry_config)
        logger.info("Initialized adapter: %s (local=%s)", provider, _adapter_cache[provider].is_local)

    return _adapter_cache[provider]


def clear_adapter_cache() -> None:
    """Clear cached adapters (used when settings change)."""
    _adapter_cache.clear()


def list_available_providers() -> list[dict]:
    """
    Return all registered providers with their status.

    Returns:
        List of dicts with name, is_local, available, models
    """
    settings = get_settings()
    providers = []

    for name, dotpath in _ADAPTER_CLASSES.items():
        try:
            adapter_cls = _import_adapter_class(dotpath)
            is_local = getattr(adapter_cls, 'is_local', False)

            # Check if blocked by privacy mode
            blocked = not settings.allow_external_calls and not is_local

            if blocked:
                providers.append({
                    "name": name,
                    "is_local": is_local,
                    "available": False,
                    "blocked_by_privacy": True,
                    "models": [],
                })
            else:
                try:
                    adapter = get_adapter(name)
                    providers.append({
                        "name": name,
                        "is_local": is_local,
                        "available": adapter.is_available(),
                        "blocked_by_privacy": False,
                        "models": adapter.list_models(),
                    })
                except Exception:
                    providers.append({
                        "name": name,
                        "is_local": is_local,
                        "available": False,
                        "blocked_by_privacy": False,
                        "models": [],
                    })
        except Exception as e:
            logger.warning("Failed to check provider %s: %s", name, e)
            providers.append({
                "name": name,
                "is_local": False,
                "available": False,
                "blocked_by_privacy": False,
                "models": [],
                "error": str(e),
            })

    return providers
