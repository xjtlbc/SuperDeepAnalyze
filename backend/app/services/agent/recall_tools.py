"""Recall tools for accessing compressed context from the DAG.

Provides three tools for the Agent to retrieve information that was
compressed during context management:
  - recall_grep: Search compressed summaries by pattern
  - recall_expand: Expand a summary node to see its children
  - recall_describe: View a specific summary node's content

Inspired by Lossless-Claw's retrieval engine (grep/expand/describe).
"""

import json
from typing import Optional, List

from pydantic import BaseModel, Field

from app.services.agent.tool import Tool


# ── Pydantic Input Models ──────────────────────────────────────────


class RecallGrepInput(BaseModel):
    pattern: str = Field(description="Search pattern (regex or keyword) to find in compressed context")
    kb_id: str = ""


class RecallExpandInput(BaseModel):
    node_id: str = Field(description="Summary node ID to expand")
    depth: int = Field(default=1, ge=0, le=3, description="How many levels deep to expand")
    kb_id: str = ""


class RecallDescribeInput(BaseModel):
    node_id: str = Field(description="Summary node ID to describe")
    kb_id: str = ""


class RecallGrepTool(Tool):
    """Search compressed context summaries for a pattern."""

    name = "recall_grep"
    description = (
        "在已被压缩的上下文中搜索关键词或正则表达式。"
        "当你需要找回之前搜索过但被上下文压缩移除的信息时使用此工具。"
        "返回匹配的摘要节点列表。"
    )
    input_model = RecallGrepInput
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "搜索模式（关键词或正则表达式）",
            },
        },
        "required": ["pattern"],
    }

    def __init__(self, context_manager=None):
        self._ctx_mgr = context_manager

    def set_context_manager(self, ctx_mgr) -> None:
        self._ctx_mgr = ctx_mgr

    async def execute(self, pattern: str, kb_id: str = "") -> str:
        if not self._ctx_mgr:
            return "Error: context manager not available"

        results = self._ctx_mgr.search_dag(pattern)
        if not results:
            return json.dumps({
                "found": False,
                "message": f"在已压缩的上下文中未找到匹配 '{pattern}' 的内容",
                "total_nodes_searched": len(self._ctx_mgr._summary_dag),
            }, ensure_ascii=False)

        return json.dumps({
            "found": True,
            "matches": [
                {"node_id": nid, "preview": content[:300]}
                for nid, content in results[:10]
            ],
            "total_matches": len(results),
            "total_nodes_searched": len(self._ctx_mgr._summary_dag),
        }, ensure_ascii=False, indent=2)


class RecallExpandTool(Tool):
    """Expand a compressed summary node to see its source content."""

    name = "recall_expand"
    description = (
        "展开一个被压缩的摘要节点，查看其原始内容或子节点。"
        "当你需要恢复之前搜索结果中被压缩掉的详细信息时使用此工具。"
    )
    input_model = RecallExpandInput
    input_schema = {
        "type": "object",
        "properties": {
            "node_id": {
                "type": "string",
                "description": "要展开的摘要节点ID（格式: sum_xxxxxxxx）",
            },
            "depth": {
                "type": "integer",
                "description": "展开深度（0=仅自身, 1=包含子节点, 2=递归展开）",
                "default": 1,
            },
        },
        "required": ["node_id"],
    }

    def __init__(self, context_manager=None):
        self._ctx_mgr = context_manager

    def set_context_manager(self, ctx_mgr) -> None:
        self._ctx_mgr = ctx_mgr

    async def execute(self, node_id: str, depth: int = 1, kb_id: str = "") -> str:
        if not self._ctx_mgr:
            return "Error: context manager not available"

        results = self._ctx_mgr.expand_node(node_id, depth)
        if not results:
            return json.dumps({
                "found": False,
                "message": f"未找到节点: {node_id}",
            }, ensure_ascii=False)

        return json.dumps({
            "found": True,
            "nodes": [
                {
                    "node_id": r["node_id"],
                    "content": r["content"][:800],
                    "depth": r["depth"],
                }
                for r in results[:15]
            ],
            "total_nodes": len(results),
        }, ensure_ascii=False, indent=2)


class RecallDescribeTool(Tool):
    """View a specific compressed summary node's content."""

    name = "recall_describe"
    description = (
        "查看一个被压缩的摘要节点的详细内容。"
        "当你需要快速浏览某个压缩摘要包含什么信息时使用此工具。"
    )
    input_model = RecallDescribeInput
    input_schema = {
        "type": "object",
        "properties": {
            "node_id": {
                "type": "string",
                "description": "要查看的摘要节点ID",
            },
        },
        "required": ["node_id"],
    }

    def __init__(self, context_manager=None):
        self._ctx_mgr = context_manager

    def set_context_manager(self, ctx_mgr) -> None:
        self._ctx_mgr = ctx_mgr

    async def execute(self, node_id: str, kb_id: str = "") -> str:
        if not self._ctx_mgr:
            return "Error: context manager not available"

        node = self._ctx_mgr.get_summary_node(node_id)
        if not node:
            return json.dumps({
                "found": False,
                "message": f"未找到节点: {node_id}",
            }, ensure_ascii=False)

        return json.dumps({
            "found": True,
            **node.to_dict(),
        }, ensure_ascii=False, indent=2)
