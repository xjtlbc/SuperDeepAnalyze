"""Anthropic Messages API provider adapter."""

import json
import logging
from typing import AsyncIterator

import httpx

from app.models.provider import LLMProvider

logger = logging.getLogger("app.models.anthropic")


class AnthropicProvider(LLMProvider):
    """Anthropic Claude Messages API provider."""

    def __init__(self, base_url: str, model_name: str, api_key: str, **kwargs):
        self.model_name = model_name
        self.max_tokens = kwargs.get("max_tokens", 8192)
        self._dimension = kwargs.get("dimension")
        self._base_url = base_url.rstrip("/")
        # Auto-fix: common Anthropic-compatible services need /v1 before /messages
        if not self._base_url.endswith("/v1") and "/v" not in self._base_url.split("/")[-1]:
            self._base_url += "/v1"
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=900.0, write=120.0, pool=10.0),
        )

    def _headers(self) -> dict:
        return {
            "anthropic-version": "2023-06-01",
            "x-api-key": self._api_key,
            "content-type": "application/json",
        }

    def _build_body(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        tools: list[dict] | None = None,
        stream: bool = False,
    ) -> dict:
        system_parts = []
        chat_messages = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_parts.append(content)
            elif role == "tool":
                chat_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": content,
                    }],
                })
            elif role == "assistant" and msg.get("tool_calls"):
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": content})
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": json.loads(fn.get("arguments", "{}")),
                    })
                chat_messages.append({"role": "assistant", "content": blocks})
            else:
                chat_messages.append({"role": role, "content": content})

        body: dict = {
            "model": self.model_name,
            "messages": chat_messages,
            "max_tokens": self.max_tokens,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        if stream:
            body["stream"] = True
        if temperature is not None:
            body["temperature"] = temperature
        if tools:
            body["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}}),
                }
                for t in tools
            ]

        return body

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        tools: list[dict] | None = None,
    ) -> dict:
        body = self._build_body(messages, temperature, tools, stream=False)
        resp = await self._client.post(
            f"{self._base_url}/messages",
            headers=self._headers(),
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()

        # Map Anthropic response to OpenAI-compatible format
        content_text = ""
        tool_calls = []
        for block in data.get("content", []):
            if block["type"] == "text":
                content_text += block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append({
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })

        finish_reason = _map_stop_reason(data.get("stop_reason", "end_turn"))

        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": content_text or None,
                    **({"tool_calls": tool_calls} if tool_calls else {}),
                },
                "finish_reason": finish_reason,
            }],
            "usage": {
                "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
            },
        }

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        body = self._build_body(messages, temperature, tools, stream=True)
        tool_call_accumulators: dict[int, dict] = {}

        async with self._client.stream(
            "POST",
            f"{self._base_url}/messages",
            headers=self._headers(),
            json=body,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    return
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield {"type": "text_delta", "content": delta["text"]}
                    elif delta.get("type") == "input_json_delta":
                        idx = event.get("index", 0)
                        if idx in tool_call_accumulators:
                            tool_call_accumulators[idx]["arguments"] += delta.get("partial_json", "")

                elif event_type == "content_block_start":
                    block = event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        idx = event.get("index", 0)
                        tool_call_accumulators[idx] = {
                            "id": block.get("id", ""),
                            "name": block.get("name", ""),
                            "arguments": "",
                        }

                elif event_type == "content_block_stop":
                    idx = event.get("index", 0)
                    if idx in tool_call_accumulators:
                        tc = tool_call_accumulators.pop(idx)
                        yield {
                            "type": "tool_use_block",
                            "index": idx,
                            "id": tc["id"],
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                        }

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("Anthropic does not provide embedding models")


def _map_stop_reason(reason: str) -> str:
    mapping = {
        "end_turn": "stop",
        "tool_use": "tool_calls",
        "max_tokens": "length",
        "stop_sequence": "stop",
    }
    return mapping.get(reason, reason)
