import json
from typing import AsyncIterator

from app.models.config import RoleType
from app.models.router import ModelRouter
from app.services.llm.prompts import Prompts


def _extract_json_object(text: str) -> str | None:
    """Find a balanced JSON object in text by brace counting."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_string:
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


class LLMClient:
    """High-level LLM call wrapper with role-based routing."""

    def __init__(self, router: ModelRouter):
        self._router = router

    async def chat(
        self,
        role: RoleType,
        messages: list[dict],
        temperature: float = 0.7,
        tools: list[dict] | None = None,
    ) -> dict:
        """Route chat request by role."""
        provider = self._router.get_provider(role)
        return await provider.chat(messages, temperature, tools)

    async def chat_stream(
        self,
        role: RoleType,
        messages: list[dict],
        temperature: float = 0.7,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Route streaming chat by role. Yields structured deltas."""
        provider = self._router.get_provider(role)
        async for chunk in provider.chat_stream(messages, temperature, tools):
            yield chunk

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via embedding model."""
        provider = self._router.get_provider(RoleType.EMBEDDING)
        return await provider.embed(texts)

    async def analyze_document(self, content: str, role: RoleType = RoleType.LIGHTWEIGHT) -> dict:
        """Analyze document and extract key info."""
        prompt = Prompts.format("DOCUMENT_ANALYSIS", content=content)
        messages = [{"role": "user", "content": prompt}]
        response = await self.chat(role, messages, temperature=0.3)
        return self._extract_content(response)

    async def summarize_l1(self, content: str, role: RoleType = RoleType.LIGHTWEIGHT, kb_id: str = "") -> dict:
        """Generate L1 paragraph summary with relations and contradictions."""
        if kb_id:
            prompt = Prompts.format_for_kb("L1_SUMMARY", kb_id, content=content)
        else:
            prompt = Prompts.format("L1_SUMMARY", content=content)
        messages = [{"role": "user", "content": prompt}]
        response = await self.chat(role, messages, temperature=0.3)
        return self._extract_content(response)

    async def build_l0(self, summaries: str, kb_id: str = "") -> dict:
        """Build L0 global entities, timeline, and event graph."""
        if kb_id:
            prompt = Prompts.format_for_kb("L0_ENTITY", kb_id, summaries=summaries)
        else:
            prompt = Prompts.format("L0_ENTITY", summaries=summaries)
        messages = [{"role": "user", "content": prompt}]
        response = await self.chat(RoleType.MAIN, messages, temperature=0.3)
        return self._extract_content(response)

    def _extract_content(self, response: dict) -> dict:
        """Extract content from LLM response, handling JSON in text."""
        message = response.get("choices", [{}])[0].get("message", {})
        content = message.get("content", "")

        # Extract JSON block from markdown first (more reliable)
        if "```json" in content:
            try:
                start = content.index("```json") + 7
                end = content.index("```", start)
                return json.loads(content[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass

        # Try to parse as JSON directly
        if content.strip().startswith("{"):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # Try to find balanced JSON object
                obj = _extract_json_object(content)
                if obj:
                    try:
                        return json.loads(obj)
                    except json.JSONDecodeError:
                        pass

        return {"raw": content}
