"""LLM-based reranker for search result quality improvement.

Uses the LIGHTWEIGHT model to score result relevance, then re-sorts.
Designed to work with any OpenAI-compatible LLM (Qwen, Zhipu, etc.).
"""

import json
from typing import Optional

from app.models.config import RoleType
from app.utils.logging_config import get_logger

logger = get_logger("app.retrieval.reranker")

_RERANK_PROMPT = """评估以下段落与查询的相关性。为每个段落打分（0-10），输出严格JSON数组。

查询: {query}

段落:
{passages}

输出格式（仅JSON数组，不要其他文字）:
[{{"index": 0, "score": 8, "reason": "简要原因"}}]"""


class LLMReranker:
    """Score and rerank search results using a lightweight LLM call."""

    def __init__(self, batch_size: int = 5):
        self._batch_size = batch_size

    async def rerank(
        self,
        query: str,
        results: list[dict],
        top_k: int = 10,
        llm_client=None,
    ) -> list[dict]:
        """Rerank results by LLM-assessed relevance.

        Args:
            query: The search query.
            results: Search results (each must have 'content' key).
            top_k: Number of results to return.
            llm_client: LLM client for scoring. If None, returns results unchanged.

        Returns:
            Results sorted by relevance score (descending).
        """
        if not results or not llm_client:
            return results[:top_k]

        scored_results = []
        # Process in batches to stay within prompt limits
        for batch_start in range(0, len(results), self._batch_size):
            batch = results[batch_start:batch_start + self._batch_size]
            passages = ""
            for i, r in enumerate(batch):
                content = str(r.get("content", r.get("summary", "")))[:300]
                passages += f"\n[{i}] {content}"

            prompt = _RERANK_PROMPT.format(query=query, passages=passages)
            messages = [{"role": "user", "content": prompt}]

            try:
                response = await llm_client.chat(
                    role=RoleType.LIGHTWEIGHT,
                    messages=messages,
                    temperature=0.1,
                )
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                scores = self._parse_scores(content, len(batch))
            except Exception as e:
                logger.warning("Rerank batch failed: %s", e)
                scores = [5.0] * len(batch)  # Neutral fallback

            for i, r in enumerate(batch):
                score = scores[i] if i < len(scores) else 5.0
                r_copy = dict(r)
                r_copy["rerank_score"] = score
                scored_results.append(r_copy)

        scored_results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return scored_results[:top_k]

    @staticmethod
    def _parse_scores(raw: str, expected_count: int) -> list[float]:
        """Parse LLM rerank output into score list."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start:end])
                except json.JSONDecodeError:
                    return [5.0] * expected_count
            else:
                return [5.0] * expected_count

        scores = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    scores.append(float(item.get("score", 5.0)))
                elif isinstance(item, (int, float)):
                    scores.append(float(item))
        return scores if scores else [5.0] * expected_count
