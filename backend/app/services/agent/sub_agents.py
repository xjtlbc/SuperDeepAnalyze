"""Sub-agent coordinator for parallel research, verification, and task orchestration.

Modes:
  - verify: Adversarial verification — cross-checks a claim with restricted tools
  - coordinate: Decompose complex task → parallel sub-agents → synthesize results

Reference: leohc/DeepAnalyze Orchestrator + claude-code Coordinator pattern.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from app.models.config import RoleType
from app.utils.logging_config import get_logger

logger = get_logger("app.agent.sub_agents")


@dataclass
class VerificationResult:
    """Result from an adversarial verification sub-agent."""
    claim: str
    verified: bool = False
    confidence: float = 0.0
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


@dataclass
class CoordinatedResult:
    """Result from a coordinated multi-sub-agent task."""
    task: str
    subtask_results: list[dict] = field(default_factory=list)
    synthesis: str = ""
    total_entities: list[str] = field(default_factory=list)
    total_evidence_refs: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


async def run_verification(
    claim: str,
    kb_id: str,
    llm_client,
    tool_registry,
    evidence_to_check: list[str] | None = None,
    timeout_seconds: int = 60,
) -> VerificationResult:
    """Run adversarial verification on a claim.

    The verification sub-agent:
    1. Searches for evidence supporting the claim
    2. Searches for evidence contradicting the claim
    3. Assesses confidence and identifies gaps

    Uses lightweight model to save costs.
    """
    result = VerificationResult(claim=claim)
    start = time.time()

    try:
        # Step 1: Search for supporting and contradicting evidence
        support_prompt = (
            f"在知识库中搜索支持以下主张的证据：\n"
            f"「{claim}」\n\n"
            "请列出：\n"
            "1. 支持该主张的证据（引用文档和具体内容）\n"
            "2. 支持证据的可信度（高/中/低）\n"
            "3. 证据来源是否独立（多个独立来源 > 单一来源）"
        )
        contradict_prompt = (
            f"在知识库中搜索与以下主张矛盾或不一致的证据：\n"
            f"「{claim}」\n\n"
            "请列出：\n"
            "1. 矛盾或不一致的证据\n"
            "2. 矛盾的程度（直接矛盾 / 部分不一致 / 可合理解释）\n"
            "3. 矛盾证据的来源"
        )

        # Run both searches in parallel
        support_task = llm_client.chat(
            role=RoleType.LIGHTWEIGHT,
            messages=[{"role": "user", "content": support_prompt}],
            temperature=0.2,
        )
        contradict_task = llm_client.chat(
            role=RoleType.LIGHTWEIGHT,
            messages=[{"role": "user", "content": contradict_prompt}],
            temperature=0.2,
        )

        support_resp, contradict_resp = await asyncio.wait_for(
            asyncio.gather(support_task, contradict_task, return_exceptions=True),
            timeout=timeout_seconds,
        )

        # Extract supporting evidence
        if isinstance(support_resp, dict):
            support_text = support_resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            if support_text:
                result.supporting_evidence = _extract_evidence_items(support_text)

        # Extract contradicting evidence
        if isinstance(contradict_resp, dict):
            contradict_text = contradict_resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            if contradict_text:
                result.contradicting_evidence = _extract_evidence_items(contradict_text)

        # Step 2: Assess verification confidence
        has_support = len(result.supporting_evidence) > 0
        has_contradict = len(result.contradicting_evidence) > 0

        if has_support and not has_contradict:
            result.verified = True
            result.confidence = min(0.95, 0.6 + 0.1 * len(result.supporting_evidence))
        elif has_support and has_contradict:
            result.verified = False
            result.confidence = 0.3
            result.gaps.append("存在矛盾证据，需要进一步调查")
        elif not has_support:
            result.verified = False
            result.confidence = 0.1
            result.gaps.append("未找到支持性证据")

    except asyncio.TimeoutError:
        result.gaps.append(f"验证超时 ({timeout_seconds}s)")
    except Exception as e:
        logger.warning("Verification failed for '%s': %s", claim[:50], e)
        result.gaps.append(f"验证过程出错: {e}")

    result.elapsed_seconds = time.time() - start
    return result


async def run_coordinated(
    task: str,
    subtasks: list[str],
    kb_id: str,
    llm_client,
    tool_registry,
    max_concurrent: int = 3,
    timeout_per_subtask: int = 60,
) -> CoordinatedResult:
    """Run coordinated multi-sub-agent task.

    1. Each subtask is handled by a lightweight research sub-agent
    2. Results are synthesized by the main model into a coherent answer

    Reference: claude-code Coordinator pattern — "never delegate understanding".
    """
    result = CoordinatedResult(task=task)
    start = time.time()

    try:
        # Phase 1: Execute subtasks in parallel
        from app.services.agent.parallel import run_parallel_research

        research_results = await run_parallel_research(
            sub_queries=subtasks[:max_concurrent],
            kb_id=kb_id,
            llm_client=llm_client,
            tool_registry=tool_registry,
            max_per_query_seconds=timeout_per_subtask,
            max_concurrent=max_concurrent,
        )

        # Collect subtask results
        for r in research_results:
            subtask_dict = {
                "query": r.sub_query,
                "success": r.success,
                "findings": r.findings[:500] if r.success else f"失败: {r.error}",
                "entities": r.entities_found[:10],
                "docs": r.docs_accessed[:5],
            }
            result.subtask_results.append(subtask_dict)
            result.total_entities.extend(r.entities_found)
            result.total_evidence_refs.extend(r.evidence_refs)

        # Phase 2: Synthesize results using main model
        if any(r.success for r in research_results):
            synthesis_parts = []
            for i, r in enumerate(research_results, 1):
                status = "成功" if r.success else "失败"
                synthesis_parts.append(
                    f"### 子任务{i}: {r.sub_query} [{status}]\n"
                    f"{r.findings[:800] if r.success else r.error}"
                )

            synthesis_prompt = (
                f"你是一个综合分析协调员。以下是关于「{task}」的多个并行研究结果。\n"
                "请综合所有结果，给出一个完整的分析报告。\n"
                "要求：\n"
                "1. 整合不同子任务的发现\n"
                "2. 标注信息来源\n"
                "3. 指出矛盾或不一致之处\n"
                "4. 标注信息缺口\n\n"
                + "\n---\n".join(synthesis_parts)
            )

            try:
                response = await llm_client.chat(
                    role=RoleType.MAIN,
                    messages=[{"role": "user", "content": synthesis_prompt}],
                    temperature=0.3,
                )
                result.synthesis = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            except Exception as e:
                # Fallback: concatenate findings
                result.synthesis = "\n\n".join(
                    f"[{r.sub_query}] {r.findings[:300]}"
                    for r in research_results if r.success
                )
                logger.warning("Synthesis failed, using concatenation: %s", e)

    except Exception as e:
        logger.warning("Coordinated task failed: %s", e)
        result.synthesis = f"协调任务执行失败: {e}"

    result.elapsed_seconds = time.time() - start
    return result


def _extract_evidence_items(text: str) -> list[str]:
    """Extract individual evidence items from verification response text."""
    items = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Match numbered or bulleted items
        if line[0].isdigit() or line.startswith("-") or line.startswith("•") or line.startswith("*"):
            clean = line.lstrip("0123456789.-) •*").strip()
            if clean and len(clean) > 5:
                items.append(clean)
    return items[:10]  # Cap at 10 items
