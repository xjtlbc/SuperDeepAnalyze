from abc import ABC, abstractmethod
from typing import AsyncIterator


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        tools: list[dict] | None = None,
    ) -> dict:
        """Synchronous-style chat completion."""
        ...

    @abstractmethod
    def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """Streaming chat completion."""
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        ...
