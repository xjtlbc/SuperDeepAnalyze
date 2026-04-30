from typing import AsyncIterator

import httpx
import tiktoken
from openai import AsyncOpenAI

from app.models.provider import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible LLM provider."""

    def __init__(self, base_url: str, model_name: str, api_key: str, **kwargs):
        self.model_name = model_name
        self.max_tokens = kwargs.get("max_tokens", 8192)
        self._dimension = kwargs.get("dimension")
        normalized_url = base_url.rstrip("/")
        if normalized_url.endswith("/embeddings"):
            normalized_url = normalized_url[:-len("/embeddings")]
        self._client = AsyncOpenAI(
            base_url=normalized_url,
            api_key=api_key,
            timeout=httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0),
            max_retries=3,
        )

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        tools: list[dict] | None = None,
    ) -> dict:
        params: dict = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            params["tools"] = tools
        if self.max_tokens:
            params["max_tokens"] = self.max_tokens

        response = await self._client.chat.completions.create(**params)
        return response.model_dump()

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Stream chat with tool call support.

        Yields dicts:
          - {"type": "text_delta", "content": "..."}   for text chunks
          - {"type": "tool_use_block", "index": int, "id": str, "name": str, "arguments": str}
        """
        params: dict = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            params["tools"] = tools
        if self.max_tokens:
            params["max_tokens"] = self.max_tokens

        stream = await self._client.chat.completions.create(**params)
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue
            if delta.content:
                yield {"type": "text_delta", "content": delta.content}
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    yield {
                        "type": "tool_use_block",
                        "index": tc.index or 0,
                        "id": tc.id or "",
                        "name": tc.function.name if tc.function else "",
                        "arguments": tc.function.arguments if tc.function else "",
                    }

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self.model_name,
            input=texts,
        )
        return [item.embedding for item in response.data]

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """CJK-aware token estimation. Uses tiktoken for accuracy."""
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            # Fallback: CJK chars count as ~1.5 tokens, ASCII words as ~1.3
            cjk_count = sum(1 for c in text if ord(c) > 0x2E80)
            ascii_text = "".join(c for c in text if ord(c) <= 0x2E80)
            ascii_words = len(ascii_text.split())
            return int(cjk_count * 1.5 + ascii_words * 1.3)
