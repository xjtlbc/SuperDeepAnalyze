"""Hybrid query router — direct simple queries to fast RAG, complex ones to Agent loop.

Classifies query complexity and routes accordingly:
- SIMPLE + FACTUAL → single hybrid_search + single LLM synthesis (no iteration)
- MEDIUM/COMPLEX → full agentic reAct loop

Inspired by DigitalApplied's hybrid routing pattern for production Agentic RAG.
"""

import json
from typing import Optional

from app.models.config import RoleType
from app.services.agent.intent_analyzer import QueryPlan, Complexity, QuestionType
from app.utils.logging_config import get_logger

logger = get_logger("app.agent.router")


class RouteDecision:
    SIMPLE_RAG = "simple_rag"
    AGENTIC_LOOP = "agentic_loop"


def should_use_simple_rag(query_plan: QueryPlan) -> bool:
    """Determine if a query can be answered via simple RAG without the Agent loop."""
    # Simple + factual → fast path
    if query_plan.complexity == Complexity.SIMPLE and query_plan.question_type == QuestionType.FACTUAL:
        return True
    # Simple + any type with single sub-query → fast path
    if query_plan.complexity == Complexity.SIMPLE and len(query_plan.sub_queries) <= 1:
        return True
    return False


async def run_simple_rag(
    llm_client,
    user_query: str,
    kb_id: str,
    tool_registry=None,
) -> dict:
    """Execute a single RAG pass: hybrid search → LLM synthesis.

    Returns a dict with 'content' and 'evidence_refs' suitable for
    yielding as a final_answer event.
    """
    search_results = []

    # Step 1: Search using available tools
    if tool_registry:
        try:
            from app.services.agent.tools import ProgressiveSearchTool
            for tool in tool_registry._tools.values():
                if isinstance(tool, ProgressiveSearchTool):
                    result = await tool.execute(query=user_query, kb_id=kb_id)
                    search_results.append(result)
                    break
        except Exception as e:
            logger.warning("Simple RAG search failed: %s", e)

    # Step 2: Single LLM synthesis
    if not search_results:
        search_text = "（未找到相关搜索结果）"
    else:
        # Take first result, cap at 3000 chars
        search_text = str(search_results[0])[:3000]

    messages = [
        {
            "role": "system",
            "content": (
                "你是知识库分析助手。基于以下检索结果，简洁准确地回答用户问题。\n"
                "如果检索结果不足以回答，请如实说明。\n"
                "在回答末尾列出引用的文档来源。"
            ),
        },
        {
            "role": "user",
            "content": f"检索结果:\n{search_text}\n\n用户问题: {user_query}",
        },
    ]

    try:
        response = await llm_client.chat(
            role=RoleType.MAIN,
            messages=messages,
            temperature=0.3,
        )
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        content = f"搜索完成但合成失败: {e}"

    return {
        "content": content,
        "evidence_refs": [],
        "tool_calls_made": 1,
        "iterations": 1,
    }
