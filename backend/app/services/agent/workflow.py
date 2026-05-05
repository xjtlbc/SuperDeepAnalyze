"""WorkflowEngine: unified interface for sub-agent orchestration.

Three modes:
  - pipeline: sequential steps, each feeding into the next
  - parallel: independent subtasks running concurrently
  - verify: adversarial verification of a claim

The engine manages context isolation, progress tracking, and result synthesis.
Each sub-agent operates with its own context window.

Reference: claude-code Coordinator + leohc/DeepAnalyze Orchestrator.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.models.config import RoleType
from app.utils.logging_config import get_logger

logger = get_logger("app.agent.workflow")


class WorkflowMode(str, Enum):
    PIPELINE = "pipeline"
    PARALLEL = "parallel"
    VERIFY = "verify"


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    step_id: str
    description: str
    query: str
    status: str = "pending"  # pending | running | completed | failed
    result: str = ""
    entities: list[str] = field(default_factory=list)
    duration: float = 0.0


@dataclass
class WorkflowResult:
    """Final result of a workflow execution."""
    mode: WorkflowMode
    steps: list[WorkflowStep]
    synthesis: str = ""
    total_entities: list[str] = field(default_factory=list)
    total_evidence: list[str] = field(default_factory=list)
    total_duration: float = 0.0
    success: bool = True

    def to_event(self) -> dict:
        """Convert to WebSocket event for frontend."""
        return {
            "type": "workflow_result",
            "mode": self.mode.value,
            "steps": [
                {
                    "step_id": s.step_id,
                    "description": s.description,
                    "status": s.status,
                    "duration": round(s.duration, 2),
                    "entity_count": len(s.entities),
                }
                for s in self.steps
            ],
            "synthesis_preview": self.synthesis[:300] if self.synthesis else "",
            "total_entities": len(self.total_entities),
            "total_duration": round(self.total_duration, 2),
        }


class WorkflowEngine:
    """Orchestrates sub-agent workflows with context isolation."""

    def __init__(
        self,
        kb_id: str,
        llm_client,
        tool_registry,
        max_concurrent: int = 3,
        timeout_per_step: int = 60,
    ):
        self._kb_id = kb_id
        self._llm = llm_client
        self._registry = tool_registry
        self._max_concurrent = max_concurrent
        self._timeout = timeout_per_step

    async def execute(
        self,
        mode: WorkflowMode,
        task: str,
        subtasks: list[str] | None = None,
        claim: str | None = None,
        progress_callback=None,
    ) -> WorkflowResult:
        """Execute a workflow in the specified mode."""
        start = time.time()

        if mode == WorkflowMode.PIPELINE:
            result = await self._run_pipeline(task, subtasks or [task], progress_callback)
        elif mode == WorkflowMode.PARALLEL:
            result = await self._run_parallel(task, subtasks or [task], progress_callback)
        elif mode == WorkflowMode.VERIFY:
            result = await self._run_verify(claim or task, progress_callback)
        else:
            result = WorkflowResult(mode=mode, steps=[], success=False)

        result.total_duration = time.time() - start
        return result

    async def _run_pipeline(
        self,
        task: str,
        steps: list[str],
        progress_callback=None,
    ) -> WorkflowResult:
        """Sequential pipeline: each step builds on previous results."""
        workflow_steps = []
        accumulated_context = ""

        for i, step_query in enumerate(steps):
            ws = WorkflowStep(
                step_id=f"pipe_{i}",
                description=step_query,
                query=step_query,
                status="running",
            )

            if progress_callback:
                await progress_callback(ws)

            step_start = time.time()
            try:
                # Run research for this step
                from app.services.agent.parallel import _execute_research
                research = await asyncio.wait_for(
                    _execute_research(
                        query=step_query,
                        kb_id=self._kb_id,
                        llm_client=self._llm,
                        tool_registry=self._registry,
                    ),
                    timeout=self._timeout,
                )
                ws.result = research.findings
                ws.entities = research.entities_found
                ws.status = "completed"

                # Accumulate context for next step
                accumulated_context += f"\n[步骤{i+1}: {step_query}]\n{research.findings[:500]}\n"

            except asyncio.TimeoutError:
                ws.result = f"步骤超时 ({self._timeout}s)"
                ws.status = "failed"
            except Exception as e:
                ws.result = f"步骤失败: {e}"
                ws.status = "failed"

            ws.duration = time.time() - step_start
            workflow_steps.append(ws)

        # Synthesize pipeline results
        synthesis = await self._synthesize(task, workflow_steps, accumulated_context)

        all_entities = []
        for ws in workflow_steps:
            all_entities.extend(ws.entities)

        return WorkflowResult(
            mode=WorkflowMode.PIPELINE,
            steps=workflow_steps,
            synthesis=synthesis,
            total_entities=list(set(all_entities)),
        )

    async def _run_parallel(
        self,
        task: str,
        subtasks: list[str],
        progress_callback=None,
    ) -> WorkflowResult:
        """Parallel execution: independent subtasks running concurrently."""
        from app.services.agent.parallel import run_parallel_research

        # Create step descriptors
        workflow_steps = [
            WorkflowStep(step_id=f"par_{i}", description=st, query=st, status="pending")
            for i, st in enumerate(subtasks)
        ]

        # Notify start
        if progress_callback:
            for ws in workflow_steps:
                ws.status = "running"
                await progress_callback(ws)

        # Run parallel research
        research_results = await run_parallel_research(
            sub_queries=subtasks[:self._max_concurrent],
            kb_id=self._kb_id,
            llm_client=self._llm,
            tool_registry=self._registry,
            max_per_query_seconds=self._timeout,
            max_concurrent=self._max_concurrent,
        )

        # Map results back to steps
        all_entities = []
        accumulated = ""
        for i, (ws, rr) in enumerate(zip(workflow_steps, research_results)):
            ws.status = "completed" if rr.success else "failed"
            ws.result = rr.findings if rr.success else f"失败: {rr.error}"
            ws.entities = rr.entities_found
            ws.duration = rr.elapsed_seconds
            all_entities.extend(rr.entities_found)
            accumulated += f"\n[子任务{i+1}: {rr.sub_query}]\n{rr.findings[:500]}\n"

        synthesis = await self._synthesize(task, workflow_steps, accumulated)

        return WorkflowResult(
            mode=WorkflowMode.PARALLEL,
            steps=workflow_steps,
            synthesis=synthesis,
            total_entities=list(set(all_entities)),
        )

    async def _run_verify(
        self,
        claim: str,
        progress_callback=None,
    ) -> WorkflowResult:
        """Adversarial verification of a claim."""
        from app.services.agent.sub_agents import run_verification

        ws = WorkflowStep(
            step_id="verify_0",
            description=f"验证: {claim[:100]}",
            query=claim,
            status="running",
        )
        if progress_callback:
            await progress_callback(ws)

        step_start = time.time()
        verification = await run_verification(
            claim=claim,
            kb_id=self._kb_id,
            llm_client=self._llm,
            tool_registry=self._registry,
            timeout_seconds=self._timeout,
        )
        ws.duration = time.time() - step_start

        # Build result
        status_parts = []
        if verification.supporting_evidence:
            status_parts.append(f"支持证据 {len(verification.supporting_evidence)} 条")
        if verification.contradicting_evidence:
            status_parts.append(f"矛盾证据 {len(verification.contradicting_evidence)} 条")

        ws.status = "completed" if verification.verified else "completed"
        ws.result = (
            f"验证结果: {'成立' if verification.verified else '存疑'} "
            f"(置信度 {verification.confidence:.0%})\n"
            + "; ".join(status_parts)
        )

        evidence = verification.supporting_evidence + verification.contradicting_evidence
        ws.entities = [claim[:30]]

        return WorkflowResult(
            mode=WorkflowMode.VERIFY,
            steps=[ws],
            synthesis=ws.result,
            total_evidence=evidence,
        )

    async def _synthesize(
        self,
        task: str,
        steps: list[WorkflowStep],
        accumulated_context: str,
    ) -> str:
        """Synthesize workflow step results into a coherent summary."""
        if not accumulated_context.strip():
            return ""

        synthesis_prompt = (
            f"你是综合分析协调员。以下是关于「{task}」的工作流执行结果。\n"
            "请综合所有步骤的发现，给出结构化摘要。\n"
            "要求：\n"
            "1. 整合不同步骤的发现\n"
            "2. 标注矛盾或不一致之处\n"
            "3. 标注信息缺口\n"
            "用中文输出，200字以内。\n\n"
            f"执行结果：\n{accumulated_context[:8000]}"
        )

        try:
            response = await self._llm.chat(
                role=RoleType.LIGHTWEIGHT,
                messages=[{"role": "user", "content": synthesis_prompt}],
                temperature=0.2,
            )
            return response.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.warning("Workflow synthesis failed: %s", e)
            # Fallback: concatenate step results
            return "\n".join(
                f"[{s.step_id}] {s.result[:200]}"
                for s in steps if s.status == "completed"
            )
