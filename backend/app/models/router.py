from app.models.config import ModelConfigs, RoleType
from app.models.openai_provider import OpenAIProvider


class ModelRouter:
    """Routes model requests by role using configured providers."""

    def __init__(self):
        self._providers: dict[str, OpenAIProvider] = {}

    def register(self, configs: ModelConfigs) -> None:
        """Register providers from ModelConfigs."""
        self._providers[RoleType.MAIN.value] = OpenAIProvider(
            base_url=configs.main.base_url,
            model_name=configs.main.model_name,
            api_key=configs.main.api_key,
            max_tokens=configs.main.max_tokens,
        )

        if configs.lightweight:
            self._providers[RoleType.LIGHTWEIGHT.value] = OpenAIProvider(
                base_url=configs.lightweight.base_url,
                model_name=configs.lightweight.model_name,
                api_key=configs.lightweight.api_key,
                max_tokens=configs.lightweight.max_tokens,
            )

        if configs.embedding:
            self._providers[RoleType.EMBEDDING.value] = OpenAIProvider(
                base_url=configs.embedding.base_url,
                model_name=configs.embedding.model_name,
                api_key=configs.embedding.api_key,
                dimension=configs.embedding.dimension,
            )

        if configs.vlm:
            self._providers[RoleType.VLM.value] = OpenAIProvider(
                base_url=configs.vlm.base_url,
                model_name=configs.vlm.model_name,
                api_key=configs.vlm.api_key,
            )

    def get_provider(self, role: RoleType) -> OpenAIProvider | None:
        provider = self._providers.get(role.value)
        if provider is None:
            # Fallback: lightweight and vlm use main if not configured
            if role in (RoleType.LIGHTWEIGHT, RoleType.VLM):
                return self._providers.get(RoleType.MAIN.value)
            # Embedding is optional — return None if not configured
            if role == RoleType.EMBEDDING:
                return None
            raise ValueError(f"No provider registered for role: {role.value}")
        return provider
