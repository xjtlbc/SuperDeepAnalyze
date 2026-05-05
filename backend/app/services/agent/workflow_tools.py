"""Workflow tools: expose WorkflowEngine to the Agent.

These tools are registered as deferred tools (loaded via tool_discover).
They inherit from Tool to match the registry interface.
"""

import json
from typing import Optional

from pydantic import BaseModel, Field

from app.services.agent.tool import Tool
from app.services.agent.workflow import WorkflowEngine, WorkflowMode
from app.utils.logging_config import get_logger

logger = get_logger("app.agent.workflow_tools")


async def _execute_workflow(
    mode: WorkflowMode,
    kb_id: str,
    task: str,
    subtasks: list[str] | None = None,
) -> str:
    """Execute a workflow and return formatted results."""
    from app.models.config import get_model_router
    from app.services.agent.registry import ToolRegistry
    from app.services.agent.tools import register_all_tools

    try:
        router = get_model_router()
        registry = ToolRegistry()
        register_all_tools(registry, kb_id=kb_id)
    except Exception as e:
        return json.dumps({"error": f"无法初始化工作流引擎: {e}", "mode": mode.value}, ensure_ascii=False)

    engine = WorkflowEngine(
        kb_id=kb_id,
        llm_client=router,
        tool_registry=registry,
    )

    result = await engine.execute(
        mode=mode,
        task=task,
        subtasks=subtasks,
    )

    return json.dumps({
        "mode": result.mode.value,
        "success": result.success,
        "total_duration": round(result.total_duration, 2),
        "step_count": len(result.steps),
        "steps": [
            {
                "id": s.step_id,
                "description": s.description[:80],
                "status": s.status,
                "duration": round(s.duration, 2),
                "entity_count": len(s.entities),
                "result_preview": s.result[:200],
            }
            for s in result.steps
        ],
        "synthesis": result.synthesis,
        "total_entities": result.total_entities[:20],
    }, ensure_ascii=False, indent=2)


class WorkflowPipelineInput(BaseModel):
    query: str
    kb_id: str
    steps: list[str]


class WorkflowParallelInput(BaseModel):
    query: str
    kb_id: str
    subtasks: list[str]


class WorkflowVerifyInput(BaseModel):
    claim: str
    kb_id: str


class WorkflowPipelineTool(Tool):
    """Execute a sequential pipeline of analysis steps."""
    name = "workflow_pipeline"
    description = (
        "顺序执行多步分析管道。每步的结果会传递给下一步。"
        "适用于需要逐步深入的分析任务。"
    )
    input_model = WorkflowPipelineInput
    is_readonly = True

    async def execute(self, **kwargs) -> str:
        query = kwargs.get("query", "")
        kb_id = kwargs.get("kb_id", "")
        steps = kwargs.get("steps", [])
        return await _execute_workflow(WorkflowMode.PIPELINE, kb_id, query, steps)


class WorkflowParallelTool(Tool):
    """Execute independent subtasks in parallel."""
    name = "workflow_parallel"
    description = (
        "并行执行多个独立分析子任务。各子任务独立运行，结果最终综合。"
        "适用于多方向、多文档对比等任务。"
    )
    input_model = WorkflowParallelInput
    is_readonly = True

    async def execute(self, **kwargs) -> str:
        query = kwargs.get("query", "")
        kb_id = kwargs.get("kb_id", "")
        subtasks = kwargs.get("subtasks", [])
        return await _execute_workflow(WorkflowMode.PARALLEL, kb_id, query, subtasks)


class WorkflowVerifyTool(Tool):
    """Adversarial verification of a claim."""
    name = "workflow_verify"
    description = (
        "对分析结论进行对抗性验证。"
        "搜索支持和反对的证据，评估结论的可信度。"
        "适用于验证关键推断或矛盾结论。"
    )
    input_model = WorkflowVerifyInput
    is_readonly = True

    async def execute(self, **kwargs) -> str:
        claim = kwargs.get("claim", "")
        kb_id = kwargs.get("kb_id", "")
        return await _execute_workflow(WorkflowMode.VERIFY, kb_id, claim)
