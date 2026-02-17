"""Abstract base adapter with retry strategy, circuit breaker, and capability metadata."""
import time
import random
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── Capability Metadata ──────────────────────────────────

@dataclass
class ModelCapability:
    """Metadata describing what a model supports."""
    max_tokens: int = 4096
    context_window: int = 8192
    supports_json_mode: bool = False
    supports_streaming: bool = False
    supports_function_calling: bool = False
    cost_per_1k_input: float | None = None    # None = free / local
    cost_per_1k_output: float | None = None
    recommended_for: list[str] = field(default_factory=lambda: ["both"])


# ── Retry Configuration ──────────────────────────────────

@dataclass
class RetryConfig:
    """Retry strategy with exponential backoff + jitter."""
    max_retries: int = 3
    base_delay: float = 1.0       # seconds
    max_delay: float = 30.0       # cap
    backoff_factor: float = 2.0
    retryable_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504)


# ── Circuit Breaker ──────────────────────────────────────

@dataclass
class CircuitBreaker:
    """Trips after consecutive failures, auto-resets after cooldown."""
    failure_threshold: int = 5
    reset_timeout: float = 60.0   # seconds

    _failure_count: int = field(default=0, init=False, repr=False)
    _last_failure_time: float = field(default=0.0, init=False, repr=False)
    _is_open: bool = field(default=False, init=False, repr=False)

    @property
    def is_open(self) -> bool:
        if self._is_open and (time.time() - self._last_failure_time) > self.reset_timeout:
            # Auto-reset: move to half-open
            self._is_open = False
            self._failure_count = 0
            logger.info("Circuit breaker reset (cooldown elapsed)")
        return self._is_open

    def record_success(self) -> None:
        self._failure_count = 0
        self._is_open = False

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._is_open = True
            logger.warning(
                "Circuit breaker OPEN after %d consecutive failures", self._failure_count
            )


# ── Errors ────────────────────────────────────────────────

class AdapterError(Exception):
    """Base error for adapter failures."""


class ProviderUnavailableError(AdapterError):
    """Provider is not reachable or not configured."""


class CircuitOpenError(AdapterError):
    """Circuit breaker is open — provider temporarily blocked."""


class PrivacyViolationError(AdapterError):
    """Attempted to use an external provider when ALLOW_EXTERNAL_CALLS=false."""


# ── Abstract Base Adapter ─────────────────────────────────

class ModelAdapter(ABC):
    """
    Base class for all LLM provider adapters.

    Subclasses implement `_do_chat`, `is_available`, and `list_models`.
    The public `chat` method wraps `_do_chat` with retry + circuit breaker.
    """

    name: str = "base"
    is_local: bool = False    # True = no external network calls

    def __init__(self, retry_config: RetryConfig | None = None):
        self.retry_config = retry_config or RetryConfig()
        self.circuit_breaker = CircuitBreaker()
        self._capabilities: dict[str, ModelCapability] = {}

    # ── Public API ────────────────────────────────────────

    def chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> str:
        """
        Send a chat completion request with retry + circuit breaker.

        Args:
            messages: Chat messages in OpenAI format [{role, content}]
            model: Model identifier (provider-specific)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            Generated text response

        Raises:
            CircuitOpenError: If circuit breaker is tripped
            AdapterError: After all retries exhausted
        """
        if self.circuit_breaker.is_open:
            raise CircuitOpenError(
                f"Circuit breaker is open for {self.name}. "
                f"Provider has failed too many times. Will retry after cooldown."
            )

        last_error: Exception | None = None
        cfg = self.retry_config

        for attempt in range(cfg.max_retries + 1):
            try:
                result = self._do_chat(messages, model, temperature, max_tokens)
                self.circuit_breaker.record_success()
                return result

            except Exception as e:
                last_error = e
                self.circuit_breaker.record_failure()

                if attempt < cfg.max_retries:
                    delay = min(
                        cfg.base_delay * (cfg.backoff_factor ** attempt),
                        cfg.max_delay,
                    )
                    # Add jitter (±25%)
                    delay *= 0.75 + random.random() * 0.5
                    logger.warning(
                        "[%s] Attempt %d/%d failed: %s — retrying in %.1fs",
                        self.name, attempt + 1, cfg.max_retries + 1, str(e)[:100], delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "[%s] All %d attempts failed. Last error: %s",
                        self.name, cfg.max_retries + 1, str(e)[:200],
                    )

        raise AdapterError(
            f"[{self.name}] Failed after {cfg.max_retries + 1} attempts: {last_error}"
        )

    def get_capability(self, model: str) -> ModelCapability:
        """Get capability metadata for a model. Returns defaults if unknown."""
        return self._capabilities.get(model, ModelCapability())

    def register_capability(self, model: str, capability: ModelCapability) -> None:
        """Register capability metadata for a model."""
        self._capabilities[model] = capability

    def status(self) -> dict:
        """Return provider status summary."""
        return {
            "name": self.name,
            "is_local": self.is_local,
            "available": self.is_available(),
            "circuit_breaker_open": self.circuit_breaker.is_open,
        }

    # ── Abstract Methods ──────────────────────────────────

    @abstractmethod
    def _do_chat(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Execute the actual chat completion. Implemented by each provider."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is reachable and configured."""

    @abstractmethod
    def list_models(self) -> list[str]:
        """List available models from this provider."""
