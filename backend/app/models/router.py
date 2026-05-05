"""Model router with multi-adapter support and circuit breaker."""

import logging
import time

from app.models.config import ModelConfig, ModelConfigs, RoleType
from app.models.openai_provider import OpenAIProvider
from app.models.anthropic_provider import AnthropicProvider
from app.models.embedding_fallback import HashEmbeddingProvider
from app.models.provider import LLMProvider

logger = logging.getLogger("app.models.router")


class CircuitBreaker:
    """Simple circuit breaker: closed -> open -> half_open."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 60.0):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._state = "closed"  # closed, open, half_open
        self._opened_at: float = 0.0

    @property
    def state(self) -> str:
        if self._state == "open" and time.monotonic() - self._opened_at > self._recovery_timeout:
            self._state = "half_open"
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._state = "open"
            self._opened_at = time.monotonic()
            logger.warning("Circuit breaker OPENED after %d failures", self._failure_count)

    def is_open(self) -> bool:
        return self.state == "open"


class ModelRouter:
    """Routes model requests by role using configured providers with circuit breaker."""

    def __init__(self):
        self._providers: dict[str, LLMProvider | HashEmbeddingProvider] = {}
        self._breakers: dict[str, CircuitBreaker] = {}
        self._hash_fallback: HashEmbeddingProvider | None = None

    def _create_provider(self, config: ModelConfig) -> LLMProvider:
        if config.provider_type == "anthropic":
            return AnthropicProvider(
                base_url=config.base_url,
                model_name=config.model_name,
                api_key=config.api_key,
                max_tokens=config.max_tokens,
                dimension=config.dimension,
            )
        return OpenAIProvider(
            base_url=config.base_url,
            model_name=config.model_name,
            api_key=config.api_key,
            max_tokens=config.max_tokens,
            dimension=config.dimension,
        )

    def register(self, configs: ModelConfigs) -> None:
        """Register providers from ModelConfigs."""
        self._providers.clear()
        self._breakers.clear()

        for role, config in [
            (RoleType.MAIN, configs.main),
            (RoleType.LIGHTWEIGHT, configs.lightweight),
            (RoleType.EMBEDDING, configs.embedding),
            (RoleType.VLM, configs.vlm),
        ]:
            if config is None:
                continue
            self._providers[role.value] = self._create_provider(config)
            self._breakers[role.value] = CircuitBreaker()

        # Setup hash fallback for embedding
        if configs.embedding and configs.embedding.dimension:
            self._hash_fallback = HashEmbeddingProvider(dimension=configs.embedding.dimension)
        else:
            self._hash_fallback = HashEmbeddingProvider()

    def get_provider(self, role) -> LLMProvider | HashEmbeddingProvider | None:
        # Accept both RoleType enum and plain string
        role_key = role.value if hasattr(role, "value") else str(role)
        breaker = self._breakers.get(role_key)
        provider = self._providers.get(role_key)

        if provider is None:
            if role_key in ("LIGHTWEIGHT", "VLM") or role in (RoleType.LIGHTWEIGHT, RoleType.VLM):
                return self._providers.get(RoleType.MAIN.value)
            if role_key == "EMBEDDING" or role == RoleType.EMBEDDING:
                return self._hash_fallback
            raise ValueError(f"No provider registered for role: {role_key}")

        if breaker and breaker.is_open():
            logger.warning("Circuit breaker OPEN for %s, using fallback", role_key)
            if role_key == "EMBEDDING" or role == RoleType.EMBEDDING:
                return self._hash_fallback
            # For chat roles, try fallback to main
            if role_key != "MAIN" and role != RoleType.MAIN:
                main_provider = self._providers.get(RoleType.MAIN.value)
                main_breaker = self._breakers.get(RoleType.MAIN.value)
                if main_provider and (not main_breaker or not main_breaker.is_open()):
                    return main_provider
            return None

        return provider

    def record_success(self, role) -> None:
        role_key = role.value if hasattr(role, "value") else str(role)
        breaker = self._breakers.get(role_key)
        if breaker:
            breaker.record_success()

    def record_failure(self, role) -> None:
        role_key = role.value if hasattr(role, "value") else str(role)
        breaker = self._breakers.get(role_key)
        if breaker:
            breaker.record_failure()

    @property
    def hash_fallback(self) -> HashEmbeddingProvider | None:
        return self._hash_fallback
