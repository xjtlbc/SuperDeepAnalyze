"""Sub-agent spawning for parallel document analysis.

Inspired by leohc/DeepAnalyze skill invocation pattern.
Each sub-agent runs an independent analysis loop with its own context
window and tool set, merging results back to the parent.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.models.config import RoleType
from app.utils.logging_config import get_logger

logger = get_logger("app.agent.sub_agent")

_MAX_SUB_AGENT_TURNS = 10
_MAX_CONCURRENT_SUB_AGENTS = 3


@dataclass
class SubAgentTask:
    """A task for a sub-agent to execute."""
    query: str
    kb_id: str
    doc_ids: list[str] = field(default_factory=list)
    context_hint: str = ""  # Extra context to guide the sub-agent


@dataclass
class SubAgentResult:
    """Result from a sub-agent execution."""
    task_query: str
    content: str
    doc_ids_searched: list[str] = field(default_factory=list)
    entities_found: list[str] = field(default_factory=list)
    success: bool = True
    error: str = ""


def _build_sub_agent_prompt(task: SubAgentTask) -> str:
    """Build system prompt for a sub-agent."""
    doc_scope = ""
    if task.doc_ids:
        doc_scope = f"\n限定搜索范围：仅分析文档 {', '.join(task.doc_ids[:5])}"

    hint = f"\n额外提示：{task.context_hint}" if task.context_hint else ""

    return (
        "你是一个专注的分析助手。你的任务是对指定文档进行深入分析，提取关键信息。\n"
        "要求：\n"
        "1. 使用 search_keyword 搜索相关内容\n"
        "2. 使用 read_l2 读取具体章节\n"
        "3. 整理发现并以结构化格式返回\n"
        "4. 列出找到的关键实体和事实\n\n"
        f"分析任务: {task.query}{doc_scope}{hint}\n"
    )


async def run_sub_agent(
    task: SubAgentTask,
    llm_client,
    tool_registry=None,
) -> SubAgentResult:
    """Run a single sub-agent to analyze documents.

    The sub-agent gets a focused system prompt and limited turns.
    It uses the same tool registry as the parent.
    """
    if tool_registry is None:
        return SubAgentResult(
            task_query=task.query,
            content="",
            success=False,
            error="No tool registry available",
        )

    messages = [
        {"role": "system", "content": _build_sub_agent_prompt(task)},
        {"role": "user", "content": f"请分析: {task.query}"},
    ]

    entities_found = []
    doc_ids_searched = []
    final_content = ""

    for turn in range(_MAX_SUB_AGENT_TURNS):
        try:
            response = await llm_client.chat(
                role=RoleType.LIGHTWEIGHT,
                messages=messages,
                tools=tool_registry.get_tool_definitions() if tool_registry else None,
                temperature=0.3,
            )
        except Exception as e:
            logger.warning("Sub-agent LLM call failed at turn %d: %s", turn, e)
            break

        message = response.get("choices", [{}])[0].get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", []) or []

        # If no tool calls, this is the final answer
        if not tool_calls:
            final_content = content
            break

        # Process tool calls
        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

        for tc in tool_calls[:3]:  # Limit to 3 tool calls per turn
            tc_id = tc.get("id", "")
            tool_name = tc.get("function", {}).get("name", "")
            try:
                tool_input = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except json.JSONDecodeError:
                tool_input = {}

            tool_input["kb_id"] = task.kb_id

            # Track searched docs
            if doc_id := tool_input.get("doc_id"):
                if doc_id not in doc_ids_searched:
                    doc_ids_searched.append(doc_id)

            try:
                result = await tool_registry.execute(tool_name, **tool_input)
                # Extract entities from results
                try:
                    data = json.loads(result[:2000])
                    if isinstance(data, dict):
                        for ent in data.get("entities", []):
                            name = ent.get("name", "") if isinstance(ent, dict) else str(ent)
                            if name and name not in entities_found:
                                entities_found.append(name)
                except (json.JSONDecodeError, ValueError):
                    pass
            except Exception as e:
                result = f"工具执行失败: {e}"

            # Truncate large results
            if len(result) > 3000:
                result = result[:3000] + "\n...[结果已截断]"

            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": result,
            })

    if not final_content:
        final_content = "子分析未产生结论。"

    return SubAgentResult(
        task_query=task.query,
        content=final_content,
        doc_ids_searched=doc_ids_searched,
        entities_found=entities_found[:20],
        success=True,
    )


async def run_parallel_sub_agents(
    tasks: list[SubAgentTask],
    llm_client,
    tool_registry=None,
) -> list[SubAgentResult]:
    """Run multiple sub-agents in parallel with concurrency control.

    Uses semaphore to limit concurrent sub-agents.
    Inspired by leohc/DeepAnalyze's Promise.allSettled pattern.
    """
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SUB_AGENTS)

    async def _guarded_run(task: SubAgentTask) -> SubAgentResult:
        async with semaphore:
            try:
                return await run_sub_agent(task, llm_client, tool_registry)
            except Exception as e:
                logger.warning("Sub-agent crashed for task '%s': %s", task.query[:50], e)
                return SubAgentResult(
                    task_query=task.query,
                    content="",
                    success=False,
                    error=str(e),
                )

    results = await asyncio.gather(
        *[_guarded_run(t) for t in tasks],
        return_exceptions=False,  # Errors handled inside _guarded_run
    )
    return list(results)


def merge_sub_agent_results(results: list[SubAgentResult]) -> str:
    """Merge sub-agent results into a formatted summary for the parent agent."""
    parts = []
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    if successful:
        parts.append(f"== 子分析完成 ({len(successful)}/{len(results)}) ==\n")
        for i, r in enumerate(successful, 1):
            parts.append(f"### 分析 {i}: {r.task_query[:60]}")
            if r.entities_found:
                parts.append(f"发现实体: {', '.join(r.entities_found[:10])}")
            if r.doc_ids_searched:
                parts.append(f"搜索文档: {', '.join(r.doc_ids_searched[:5])}")
            parts.append(r.content[:1000])
            parts.append("")

    if failed:
        parts.append(f"\n⚠ {len(failed)} 个分析任务失败:")
        for r in failed:
            parts.append(f"  - {r.task_query[:50]}: {r.error[:100]}")

    return "\n".join(parts)
