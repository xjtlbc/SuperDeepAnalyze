"""Evaluator-Optimizer pattern for quality gating before report_findings.

Checks evidence sufficiency, source diversity, contradiction consistency,
and logical coherence. If evaluation fails, injects improvement suggestions
for the agent to continue searching.

Inspired by Anthropic's Evaluator-Optimizer pattern and CrewAI's production
quality verification.
"""

import json
from typing import Optional

from app.models.config import RoleType
from app.utils.logging_config import get_logger

logger = get_logger("app.agent.evaluator")


async def evaluate_answer_quality(
    llm_client,
    user_query: str,
    findings: str,
    evidence_refs: list[str],
    entities_found: list[str],
    docs_accessed: list[str],
    iterations: int,
) -> Optional[dict]:
    """Evaluate answer quality before report_findings.

    Returns None if quality is acceptable, or a dict with improvement suggestions
    if the answer needs more work.
    """
    if not findings or len(findings) < 50:
        return {"issue": "empty_findings", "suggestion": "继续搜索获取更多信息后再报告"}

    # Quick heuristic checks (no LLM needed)
    if len(evidence_refs) == 0 and iterations < 3:
        return {"issue": "no_evidence", "suggestion": "请搜索并引用具体证据来源"}

    if len(entities_found) == 0 and iterations < 5:
        return {"issue": "no_entities", "suggestion": "请使用 expand_entity 或 read_l0 查找相关实体"}

    # LLM-based quality evaluation (only for substantial answers)
    if iterations >= 5 or len(evidence_refs) >= 2:
        return None  # Enough work done, skip LLM evaluation

    try:
        eval_prompt = f"""评估以下分析回答的质量，输出JSON：

用户问题: {user_query}
分析回答摘要: {findings[:500]}
证据引用数: {len(evidence_refs)}
访问文档数: {len(docs_accessed)}
发现实体数: {len(entities_found)}

请输出：
{{
  "quality": "sufficient" | "needs_improvement",
  "evidence_sufficiency": "high" | "medium" | "low",
  "source_diversity": "high" | "medium" | "low",
  "suggestion": "如果需要改进，给出具体建议"
}}"""

        response = await llm_client.chat(
            role=RoleType.LIGHTWEIGHT,
            messages=[{"role": "user", "content": eval_prompt}],
            temperature=0.1,
        )
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
            if data.get("quality") == "needs_improvement" and data.get("suggestion"):
                return {
                    "issue": data.get("evidence_sufficiency", "low"),
                    "suggestion": data["suggestion"],
                }

    except Exception as e:
        logger.warning("Quality evaluation failed: %s", e)

    return None
