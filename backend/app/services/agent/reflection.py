"""Structured reflection engine for Agent self-assessment.

After EVALUATING phase, the engine prompts the LLM to assess information
sufficiency with a strict JSON schema. This enables convergence control:
the agent knows what it does NOT know and can stop when confidence is high.

Inspired by DigitalApplied's 2026 Agentic RAG patterns research.
"""

import json
from dataclasses import dataclass
from typing import Optional

from app.models.config import RoleType
from app.utils.logging_config import get_logger

logger = get_logger("app.agent.reflection")

_REFLECTION_SYSTEM = """你是一个信息充分性评估器。根据当前搜索进展，严格输出以下JSON格式：

{
  "answered_aspects": ["已解答的方面列表"],
  "missing_aspects": ["仍然缺失的信息列表"],
  "next_query": "下一轮应搜索的具体查询，如已充分则为空字符串",
  "confidence": 0.0,
  "evidence_strength": "strong|partial|weak|none"
}

规则：
- confidence 范围 0.0-1.0，表示对回答用户问题的信心
- 已收集足够证据回答全部问题时 confidence 应 >= 0.8
- evidence_strength: strong=多个来源交叉验证, partial=部分来源支持, weak=仅单一来源, none=无直接证据
- next_query 必须具体（如"张三3月15日的行踪"而非"更多信息"）
- 只输出JSON，不要其他文字"""


@dataclass
class ReflectionResult:
    answered_aspects: list[str]
    missing_aspects: list[str]
    next_query: str
    confidence: float
    evidence_strength: str  # strong | partial | weak | none
    raw_json: dict


async def reflect(
    llm_client,
    user_query: str,
    entities_found: list[str],
    relations_found: list[str],
    docs_read: list[str],
    evidence_map: dict[str, list[dict]],
    iteration: int,
    tool_calls_count: int,
) -> Optional[ReflectionResult]:
    """Run structured reflection to assess information sufficiency.

    Uses LIGHTWEIGHT model for cost efficiency. Returns None on parse failure.
    """
    # Build concise context (cap to avoid bloating the prompt)
    entities_str = ", ".join(entities_found[:15]) if entities_found else "无"
    relations_str = ", ".join(relations_found[:10]) if relations_found else "无"
    docs_str = ", ".join(docs_read[:8]) if docs_read else "无"

    # Summarize evidence
    evidence_parts = []
    for doc_id, refs in list(evidence_map.items())[:5]:
        top_refs = sorted(refs, key=lambda r: r.get("relevance", 0), reverse=True)[:2]
        for r in top_refs:
            evidence_parts.append(f"  {doc_id}/chunk={r.get('chunk_id', '')} rel={r.get('relevance', 0):.0%}")
    evidence_str = "\n".join(evidence_parts) if evidence_parts else "  暂无结构化证据"

    user_prompt = f"""用户问题: {user_query}

当前进展 (第{iteration}轮, 共{tool_calls_count}次工具调用):
- 已发现实体: {entities_str}
- 已发现关系: {relations_str}
- 已读文档: {docs_str}
- 证据来源:
{evidence_str}

请评估当前信息是否足以回答用户问题。"""

    messages = [
        {"role": "system", "content": _REFLECTION_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = await llm_client.chat(
            role=RoleType.LIGHTWEIGHT,
            messages=messages,
            temperature=0.1,
        )
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        return _parse_reflection_json(content)
    except Exception as e:
        logger.warning("Reflection failed: %s", e)
        return None


def _parse_reflection_json(raw: str) -> Optional[ReflectionResult]:
    """Parse LLM output into ReflectionResult with multi-level fallback.

    Level 1: Direct JSON parse
    Level 2: Strip markdown fences, retry
    Level 3: Extract JSON object from surrounding text
    Level 4: Regex extract key fields (confidence, next_query)
    Level 5: Return None (skip reflection)
    """
    text = raw.strip()

    # Level 1: Direct parse
    try:
        data = json.loads(text)
        return _build_result(data)
    except json.JSONDecodeError:
        pass

    # Level 2: Strip markdown fences
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        try:
            data = json.loads(text)
            return _build_result(data)
        except json.JSONDecodeError:
            pass

    # Level 3: Find JSON object in text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end])
            return _build_result(data)
        except json.JSONDecodeError:
            pass

    # Level 4: Regex extract key fields
    import re
    conf_match = re.search(r'"confidence"\s*:\s*([0-9.]+)', text)
    next_match = re.search(r'"next_query"\s*:\s*"([^"]*)"', text)
    if conf_match:
        return ReflectionResult(
            answered_aspects=[],
            missing_aspects=[],
            next_query=next_match.group(1) if next_match else "",
            confidence=max(0.0, min(1.0, float(conf_match.group(1)))),
            evidence_strength="partial",
            raw_json={"_parsed_from_regex": True},
        )

    # Level 5: Give up
    logger.warning("Could not parse reflection output: %s", text[:200])
    return None


def _build_result(data: dict) -> ReflectionResult:
    """Build ReflectionResult from parsed JSON dict."""
    return ReflectionResult(
        answered_aspects=data.get("answered_aspects", []),
        missing_aspects=data.get("missing_aspects", []),
        next_query=data.get("next_query", ""),
        confidence=max(0.0, min(1.0, float(data.get("confidence", 0.0)))),
        evidence_strength=data.get("evidence_strength", "none"),
        raw_json=data,
    )
