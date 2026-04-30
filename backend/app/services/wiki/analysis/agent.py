"""Analysis Agent: reAct loop for deep knowledge analysis."""

from __future__ import annotations
import json
import asyncio
from pathlib import Path

from app.config import settings
from app.models.config import RoleType
from app.services.wiki.analysis.report import AnalysisReport
from app.services.wiki.analysis.tools import AnalysisToolbox
from app.services.wiki.analysis.prompts import SYSTEM_PROMPT, format_analysis_overview


class AnalysisAgent:
    """Agent that performs deep analysis on compiled KB data."""

    def __init__(self, llm_client, kb_id: str):
        self._llm_client = llm_client
        self._kb_id = kb_id
        self._report = AnalysisReport(kb_id=kb_id)
        self._toolbox = AnalysisToolbox(self._report)
        self._max_iterations = 30
        self._zero_gain_count = 0

    async def run(self, progress_cb=None) -> AnalysisReport:
        """Run the analysis reAct loop."""
        if progress_cb:
            await _cb(progress_cb, {"phase": "analysis", "message": "初始化分析Agent..."})

        context = self._gather_context()
        prompt = format_analysis_overview(
            kb_id=self._kb_id,
            entity_summary=context["entity_summary"],
            timeline_summary=context["timeline_summary"],
            summary_stats=context["summary_stats"],
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        iteration = 0
        tools_used = []

        while iteration < self._max_iterations:
            iteration += 1
            if progress_cb:
                await _cb(progress_cb, {"phase": "analysis", "iteration": iteration, "message": f"分析迭代 {iteration}/{self._max_iterations}"})

            tool_definitions = self._get_tool_definitions()
            response = await self._llm_client.chat(
                role=RoleType.MAIN,
                messages=messages,
                temperature=0.3,
                tools=tool_definitions,
            )

            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})
            tool_calls = message.get("tool_calls", None)
            content = message.get("content", "")

            if tool_calls:
                for tc in tool_calls:
                    tc_id = tc["id"]
                    tc_name = tc["function"]["name"]
                    tc_args = json.loads(tc["function"]["arguments"])
                    result = self._execute_tool(tc_name, tc_args)

                    messages.append({
                        "role": "assistant",
                        "tool_calls": [tc],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                    tools_used.append(tc_name)

                self._zero_gain_count = 0
            else:
                if content and len(content.strip()) > 10:
                    messages.append({"role": "assistant", "content": content})
                    self._zero_gain_count = 0
                else:
                    self._zero_gain_count += 1

                if self._zero_gain_count >= 3:
                    if progress_cb:
                        await _cb(progress_cb, {"phase": "analysis", "message": "信息饱和，分析完成"})
                    break

            if len(tools_used) > 50:
                break

        self._assign_communities()

        if progress_cb:
            await _cb(progress_cb, {
                "phase": "analysis",
                "message": f"分析完成: {len(self._report.entities)} 实体, "
                          f"{len(self._report.contradictions)} 矛盾, "
                          f"{len(self._report.knowledge_gaps)} 缺口",
            })

        return self._report

    def _gather_context(self) -> dict:
        """Gather existing L0/L1 data as analysis context."""
        kb_dir = settings.KB_DIR / self._kb_id

        entity_summary = ""
        entities_path = kb_dir / "l0" / "entities.json"
        if entities_path.exists():
            entities = json.loads(entities_path.read_text(encoding="utf-8"))
            lines = [f"- {e['name']} ({e.get('type', 'unknown')})" for e in entities[:50]]
            entity_summary = "\n".join(lines)
            if len(entities) > 50:
                entity_summary += f"\n... 共 {len(entities)} 个实体"

        timeline_summary = ""
        timeline_path = kb_dir / "l0" / "timeline.json"
        if timeline_path.exists():
            events = json.loads(timeline_path.read_text(encoding="utf-8"))
            lines = [f"- {e.get('time', '?')}: {e.get('description', '')}" for e in events[:30]]
            timeline_summary = "\n".join(lines)

        summary_stats = ""
        total_summaries = 0
        total_chunks = 0
        l1_dir = kb_dir / "documents"
        if l1_dir.exists():
            for doc_dir in l1_dir.iterdir():
                l1_path = doc_dir / "l1_summaries.json"
                if l1_path.exists():
                    summaries = json.loads(l1_path.read_text(encoding="utf-8"))
                    total_summaries += len(summaries)
                    for s in summaries:
                        total_chunks += len(s.get("chunk_ids", []))
        summary_stats = f"共 {total_summaries} 批摘要, 覆盖 {total_chunks} 个文本块"

        return {
            "entity_summary": entity_summary,
            "timeline_summary": timeline_summary,
            "summary_stats": summary_stats,
        }

    def _get_tool_definitions(self) -> list[dict]:
        """Return OpenAI function-calling definitions for record tools."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "record_entity",
                    "description": "记录一个实体到分析报告",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "实体名称"},
                            "entity_type": {
                                "type": "string",
                                "enum": ["person", "organization", "location", "event", "evidence", "document"],
                                "description": "实体类型",
                            },
                            "aliases": {"type": "array", "items": {"type": "string"}, "description": "别名列表"},
                            "attributes": {"type": "object", "description": "属性，如角色、职业、年龄"},
                            "importance": {"type": "number", "description": "重要性评分 (0-1)"},
                            "confidence": {"type": "number", "description": "置信度 (0-1)"},
                        },
                        "required": ["name", "entity_type"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "record_relation",
                    "description": "记录两个实体之间的关系",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source_name": {"type": "string", "description": "源实体名称"},
                            "target_name": {"type": "string", "description": "目标实体名称"},
                            "relation_type": {"type": "string", "description": "关系类型，如'同伙'、'上下级'、'亲属'、'对立'"},
                            "evidence": {"type": "string", "description": "原文证据引用"},
                            "confidence": {"type": "number", "description": "置信度 (0-1)"},
                            "sources": {"type": "array", "items": {"type": "string"}, "description": "来源chunk_ids"},
                        },
                        "required": ["source_name", "target_name", "relation_type", "evidence"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "record_contradiction",
                    "description": "记录一个矛盾点",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "contradiction_type": {
                                "type": "string",
                                "enum": ["time_conflict", "statement_conflict", "evidence_conflict", "logical_gap"],
                            },
                            "description": {"type": "string", "description": "矛盾描述"},
                            "involved_entities": {"type": "array", "items": {"type": "string"}, "description": "涉及的实体名称"},
                            "sources": {"type": "array", "items": {"type": "string"}, "description": "来源"},
                            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                        },
                        "required": ["contradiction_type", "description", "involved_entities"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "record_concept",
                    "description": "记录一个抽象概念",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "概念名称"},
                            "description": {"type": "string", "description": "概念描述"},
                            "related_entities": {"type": "array", "items": {"type": "string"}, "description": "相关实体"},
                            "sources": {"type": "array", "items": {"type": "string"}, "description": "来源"},
                        },
                        "required": ["name", "description"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "record_gap",
                    "description": "记录一个知识缺口",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string", "description": "缺口描述"},
                            "gap_type": {
                                "type": "string",
                                "enum": ["isolated_entity", "missing_relation", "unanswered_question", "sparse_community"],
                            },
                            "suggestion": {"type": "string", "description": "建议"},
                            "related_entities": {"type": "array", "items": {"type": "string"}, "description": "相关实体"},
                        },
                        "required": ["description", "gap_type", "suggestion"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "record_thread",
                    "description": "记录一个叙事线索",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "线索标题"},
                            "description": {"type": "string", "description": "线索描述"},
                            "key_entities": {"type": "array", "items": {"type": "string"}, "description": "关键实体名称"},
                            "timeline_events": {"type": "array", "items": {"type": "string"}, "description": "相关时间线事件"},
                            "thread_type": {"type": "string", "enum": ["main", "subplot"], "description": "线索类型"},
                        },
                        "required": ["title", "description", "key_entities"],
                    },
                },
            },
        ]

    def _execute_tool(self, name: str, args: dict) -> dict:
        """Execute a record tool by name."""
        toolbox = self._toolbox
        try:
            if name == "record_entity":
                eid = toolbox.record_entity(
                    name=args["name"], entity_type=args["entity_type"],
                    aliases=args.get("aliases", []), attributes=args.get("attributes", {}),
                    importance=args.get("importance", 0.5), confidence=args.get("confidence", 1.0),
                )
                return {"entity_id": eid, "status": "ok"}
            elif name == "record_relation":
                result = toolbox.record_relation(
                    source_name=args["source_name"], target_name=args["target_name"],
                    relation_type=args["relation_type"], evidence=args["evidence"],
                    confidence=args.get("confidence", 0.8), sources=args.get("sources", []),
                )
                return result
            elif name == "record_contradiction":
                cid = toolbox.record_contradiction(
                    contradiction_type=args["contradiction_type"],
                    description=args["description"],
                    involved_entities=args["involved_entities"],
                    sources=args.get("sources", []),
                    severity=args.get("severity", "medium"),
                )
                return {"contradiction_id": cid, "status": "ok"}
            elif name == "record_concept":
                cid = toolbox.record_concept(
                    name=args["name"], description=args["description"],
                    related_entities=args.get("related_entities", []),
                    sources=args.get("sources", []),
                )
                return {"concept_id": cid, "status": "ok"}
            elif name == "record_gap":
                gid = toolbox.record_gap(
                    description=args["description"], gap_type=args["gap_type"],
                    suggestion=args["suggestion"],
                    related_entities=args.get("related_entities", []),
                )
                return {"gap_id": gid, "status": "ok"}
            elif name == "record_thread":
                tid = toolbox.record_thread(
                    title=args["title"], description=args["description"],
                    key_entities=args["key_entities"],
                    timeline_events=args.get("timeline_events", []),
                    thread_type=args.get("thread_type", "subplot"),
                )
                return {"thread_id": tid, "status": "ok"}
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"error": str(e)}

    def _assign_communities(self):
        """Run Louvain community detection on entities."""
        from app.services.retrieval.community import assign_communities

        entity_data = []
        for e in self._report.entities:
            entity_data.append({
                "id": e.id,
                "relations": [{"target_id": r.target_id, "confidence": r.confidence} for r in e.relations],
            })

        partition = assign_communities(entity_data)
        for e in self._report.entities:
            e.community_id = partition.get(e.id, 0)


async def _cb(cb, data: dict):
    """Handle sync/async callback."""
    result = cb(data)
    if asyncio.iscoroutine(result):
        await result
