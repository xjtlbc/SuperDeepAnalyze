"""Sub-Agent Orchestrator: Plan → Execute → Synthesize workflow.

Inspired by leohc/DeepAnalyze orchestrator.ts. For complex queries,
decomposes the problem into sub-tasks, runs them in parallel with
independent sub-agents, then synthesizes results with dedup.

Three-stage pipeline:
  1. Plan: Coordinator LLM decomposes query into sub-tasks
  2. Execute: Sub-tasks run in parallel with restricted tool sets
  3. Synthesize: Results merged, deduplicated, and summarized
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field

from app.config import flags
from app.models.config import RoleType

logger = logging.getLogger("app.agent.orchestrator")

# Tool restrictions for sub-agents (prevent recursion)
BLOCKED_SUBAGENT_TOOLS = frozenset({
    "agent_orchestrator", "coordinate_research", "workflow_pipeline",
    "workflow_parallel", "workflow_verify",
})

MAX_SUBAGENT_ITERATIONS = 5
MAX_SUBAGENTS = 4
SUBAGENT_TIMEOUT_SECONDS = 120


@dataclass
class SubAgentResult:
    """Result from a single sub-agent execution."""
    sub_query: str
    success: bool
    findings: str = ""
    entities_found: list[str] = field(default_factory=list)
    docs_accessed: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class OrchestrationResult:
    """Aggregated result from all sub-agents."""
    results: list[SubAgentResult]
    merged_findings: str = ""
    dedup_entities: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)


async def run_orchestrator(
    user_query: str,
    kb_id: str,
    llm_client,
    tool_registry,
) -> OrchestrationResult:
    """Run the full Plan → Execute → Synthesize orchestration workflow."""
    if not flags.agent_orchestrator:
        return OrchestrationResult(results=[])

    # ── Stage 1: Plan ──────────────────────────────────────────────
    sub_queries = await _plan_subtasks(user_query, llm_client)
    if not sub_queries:
        logger.info("Orchestrator: planning produced no sub-tasks, skipping")
        return OrchestrationResult(results=[])

    logger.info("Orchestrator: planned %d sub-tasks for query '%s'", len(sub_queries), user_query[:50])

    # ── Stage 2: Execute (parallel) ─────────────────────────────────
    results = await _execute_parallel(
        sub_queries=sub_queries,
        kb_id=kb_id,
        llm_client=llm_client,
        tool_registry=tool_registry,
    )

    # ── Stage 3: Synthesize ─────────────────────────────────────────
    merged = _synthesize_results(results, llm_client)

    return merged


async def _plan_subtasks(user_query: str, llm_client) -> list[str]:
    """Use a lightweight LLM to decompose query into sub-tasks."""
    plan_prompt = (
        "你是案情分析任务规划师。请将以下复杂查询分解为2-4个独立的子任务。"
        "每个子任务应该可以独立搜索和回答。"
        "只输出JSON数组，每个元素是子任务的查询字符串。\n\n"
        f"用户查询: {user_query}\n\n"
        '输出格式: ["子任务1 query", "子任务2 query", ...]'
    )

    try:
        response = await llm_client.chat(
            role=RoleType.LIGHTWEIGHT,
            messages=[{"role": "user", "content": plan_prompt}],
            temperature=0.2,
        )
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        # Extract JSON array from response
        if "```" in content:
            start = content.index("[")
            end = content.rindex("]") + 1
            content = content[start:end]
        sub_queries = json.loads(content.strip())
        return sub_queries[:MAX_SUBAGENTS]
    except Exception as e:
        logger.warning("Orchestrator planning failed: %s", e)
        return []


async def _execute_parallel(
    sub_queries: list[str],
    kb_id: str,
    llm_client,
    tool_registry,
) -> list[SubAgentResult]:
    """Execute all sub-tasks in parallel with restricted tool sets."""

    async def _run_one(sub_query: str) -> SubAgentResult:
        try:
            # Build restricted tool defs (exclude management tools)
            restricted_tools = {
                name: tool for name, tool in tool_registry._tools.items()
                if name not in BLOCKED_SUBAGENT_TOOLS
            }

            # Run a bounded agent loop for this sub-task
            from app.services.agent.loop import AgentLoop
            from app.services.agent.registry import ToolRegistry

            sub_registry = ToolRegistry()
            for name, tool in restricted_tools.items():
                sub_registry.register(name, tool)

            sub_loop = AgentLoop(
                llm_client=llm_client,
                tool_registry=sub_registry,
                max_iterations=MAX_SUBAGENT_ITERATIONS,
            )

            findings_parts: list[str] = []
            entities_found: list[str] = []
            docs_accessed: list[str] = []

            async for event in sub_loop.run(
                user_query=sub_query,
                kb_id=kb_id,
                session_id=f"sub_{hash(sub_query) & 0xFFFF:04x}",
            ):
                if event.get("type") == "final_answer":
                    content = event.get("content", "")
                    if content:
                        findings_parts.append(content[:1000])
                elif event.get("type") == "tool_call":
                    if event.get("tool") in ("read_l1", "read_l2", "expand"):
                        doc_id = event.get("input", {}).get("doc_id", "")
                        if doc_id and doc_id not in docs_accessed:
                            docs_accessed.append(doc_id)

            findings = "\n".join(findings_parts)
            # Extract entities from findings text
            from app.services.agent.utils import extract_entities
            entities_found = list(extract_entities(findings))[:10]

            return SubAgentResult(
                sub_query=sub_query,
                success=True,
                findings=findings or f"[子任务完成: {sub_query[:50]}...]",
                entities_found=entities_found,
                docs_accessed=docs_accessed,
            )

        except asyncio.TimeoutError:
            return SubAgentResult(
                sub_query=sub_query, success=False,
                error=f"子任务超时 ({SUBAGENT_TIMEOUT_SECONDS}s)",
            )
        except Exception as e:
            logger.warning("Sub-agent failed for '%s': %s", sub_query[:50], e)
            return SubAgentResult(
                sub_query=sub_query, success=False,
                error=str(e),
            )

    tasks = [asyncio.wait_for(_run_one(q), timeout=SUBAGENT_TIMEOUT_SECONDS)
             for q in sub_queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    resolved: list[SubAgentResult] = []
    for r in results:
        if isinstance(r, Exception):
            resolved.append(SubAgentResult(sub_query="", success=False, error=str(r)))
        else:
            resolved.append(r)

    return resolved


def _synthesize_results(
    results: list[SubAgentResult],
    llm_client=None,
) -> OrchestrationResult:
    """Merge sub-agent results: dedup entities, detect conflicts, build summary."""
    all_entities: dict[str, set[str]] = {}  # entity → {source sub-queries}
    all_docs: set[str] = set()
    findings_list: list[str] = []

    for r in results:
        if not r.success:
            continue
        for e in r.entities_found:
            all_entities.setdefault(e, set()).add(r.sub_query[:30])
        all_docs.update(r.docs_accessed)
        if r.findings:
            findings_list.append(f"### 子任务: {r.sub_query[:60]}\n{r.findings[:500]}")

    # Dedup entities (keep those found by multiple sub-agents)
    dedup_entities = [e for e, sources in all_entities.items() if len(sources) > 1]
    if not dedup_entities:
        dedup_entities = list(all_entities.keys())[:20]

    # Detect conflicts (entities mentioned with different descriptions)
    conflicts = []
    entity_descriptions: dict[str, list[str]] = {}
    for r in results:
        if not r.success:
            continue
        for e in r.entities_found:
            entity_descriptions.setdefault(e, []).append(r.findings[:200])

    for ent, descs in entity_descriptions.items():
        if len(set(descs)) > 1 and len(descs) > 1:
            conflicts.append({
                "entity": ent,
                "source_count": len(descs),
                "descriptions": descs[:3],
            })

    merged = "\n\n".join(findings_list)
    successful = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    if successful == 0:
        merged = "[所有子任务执行失败]"

    summary_header = (
        f"并行分析完成: {successful}/{len(results)} 子任务成功"
    )
    if failed:
        summary_header += f", {failed} 失败"
    if dedup_entities:
        summary_header += f"\n跨任务实体: {', '.join(dedup_entities[:10])}"

    merged = f"{summary_header}\n\n{merged}"

    return OrchestrationResult(
        results=results,
        merged_findings=merged,
        dedup_entities=dedup_entities,
        conflicts=conflicts,
    )
