"""Agent reAct loop with state machine, context management, and parallel execution.

Inspired by Claude Code query.ts state machine and OpenHarness query.py phases.
"""

import asyncio
import json
import time
from typing import AsyncIterator, Optional

from app.models.config import RoleType
from app.services.agent.context import AgentContext
from app.services.agent.states import LoopPhase, TerminalReason, LoopState
from app.services.agent.registry import ToolRegistry
from app.services.agent.prompt_builder import build_system_prompt
from app.services.agent.agent_loop_display import AgentEventEmitter
from app.services.agent.context_manager import ContextManager
from app.services.agent.information_tracker import InformationTracker
from app.services.agent.quality_gater import DecisionPointManager
from app.services.agent.tools import READ_ONLY_TOOLS
from app.services.agent.intent_analyzer import analyze_intent_simple, analyze_intent_with_llm
from app.services.agent.reflection import reflect as _run_reflection
from app.services.agent.router import should_use_simple_rag, run_simple_rag
from app.services.agent.memory import KBMemory, extract_session_notes, format_session_notes, AsyncSessionMemoryExtractor
from app.config import settings, flags
from app.utils.logging_config import get_logger


def _extract_confidence(result: str) -> Optional[str]:
    """Extract confidence level from tool result JSON if present."""
    try:
        data = json.loads(result[:2000])
        if isinstance(data, list) and data:
            return data[0].get("confidence")
        if isinstance(data, dict):
            return data.get("confidence")
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _collect_evidence_refs(
    evidence_map: dict[str, list[dict]],
    tool_name: str,
    tool_input: dict,
    result: str,
) -> None:
    """Extract evidence references from tool results for citation tracking."""
    try:
        data = json.loads(result[:5000])
        doc_id = tool_input.get("doc_id", "")
        chunk_id = tool_input.get("chunk_id", "")

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    item_doc = item.get("doc_id", doc_id)
                    item_chunk = item.get("chunk_id", chunk_id)
                    item_score = item.get("relevance_score", item.get("score", 0))
                    excerpt = str(item.get("summary", item.get("content", "")))[:120]
                    if item_doc or item_chunk:
                        key = item_doc or "unknown"
                        if key not in evidence_map:
                            evidence_map[key] = []
                        if len(evidence_map[key]) < 10:
                            evidence_map[key].append({
                                "chunk_id": str(item_chunk) if item_chunk else "",
                                "relevance": round(float(item_score) if item_score else 0, 2),
                                "excerpt": excerpt,
                            })
        elif isinstance(data, dict):
            doc = data.get("doc_id", doc_id)
            chunk = data.get("chunk_id", chunk_id)
            score = data.get("relevance_score", 0)
            if doc or chunk:
                key = doc or "unknown"
                if key not in evidence_map:
                    evidence_map[key] = []
                if len(evidence_map[key]) < 10:
                    evidence_map[key].append({
                        "chunk_id": str(chunk) if chunk else "",
                        "relevance": round(float(score) if score else 0, 2),
                        "excerpt": str(data.get("summary", ""))[:120],
                    })
    except (json.JSONDecodeError, ValueError, TypeError):
        pass


def _format_evidence_for_prompt(evidence_map: dict[str, list[dict]]) -> str:
    """Format evidence map into a prompt-friendly string for the Agent."""
    if not evidence_map:
        return "（暂无结构化证据引用）"
    lines = []
    for doc_id, refs in list(evidence_map.items())[:5]:
        refs_sorted = sorted(refs, key=lambda r: r.get("relevance", 0), reverse=True)[:3]
        ref_strs = []
        for r in refs_sorted:
            chunk = r.get("chunk_id", "")
            rel = r.get("relevance", 0)
            excerpt = r.get("excerpt", "")[:60]
            ref_strs.append(f"    chunk={chunk}, relevance={rel:.0%}, excerpt=\"{excerpt}\"")
        lines.append(f"  文档 {doc_id}:\n" + "\n".join(ref_strs))
    return "\n".join(lines)


class AgentLoop:
    """reAct tool-use loop with state machine phases for deep analysis."""

    def __init__(
        self,
        llm_client=None,
        tool_registry: Optional[ToolRegistry] = None,
        max_iterations: int = 50,
        emitter: Optional[AgentEventEmitter] = None,
    ):
        self._llm_client = llm_client
        self._registry = tool_registry
        self._max_iterations = max_iterations
        self._emitter = emitter
        self._logger = get_logger("app.agent.loop")

    # ── Public API ──────────────────────────────────────────────────────

    async def run(
        self,
        user_query: str = "",
        kb_id: str = "",
        session_id: str = "",
        ctx: Optional[AgentContext] = None,
    ) -> AsyncIterator[dict]:
        """Run the Agent reAct loop with state machine phases.

        Accepts either an AgentContext (new path) or legacy kwarg-style
        arguments. When ctx is provided, kb_id/session_id are read from ctx.
        """
        # ── Resolve context ──────────────────────────────────────────
        if ctx is not None:
            _kb_id = ctx.kb_id
            _session_id = ctx.session_id
            _max_iter = ctx.max_iterations
            _llm = ctx.model_router
            _registry = ctx.tool_registry
            _ask_user_cb = ctx.ask_user_callback
            _stream_cb = ctx.stream_callback
            _history = ctx.history_messages
        else:
            _kb_id = kb_id
            _session_id = session_id
            _max_iter = self._max_iterations
            _llm = self._llm_client
            _registry = self._registry
            _ask_user_cb = None
            _stream_cb = None
            _history = []

        # ── Build initial messages ───────────────────────────────────
        _kb_state = ctx.kb_state if ctx else None
        messages = [{"role": "system", "content": build_system_prompt(_kb_id, kb_state=_kb_state)}]
        for h_msg in _history:
            messages.append(h_msg)
        messages.append({"role": "user", "content": user_query})

        # ── Initialize state & context manager ─────────────────────
        state = LoopState(
            phase=LoopPhase.INTERPRETING,
            messages=messages,
        )

        # Context management & quality gating
        ctx_mgr = ContextManager(model_context_window=(
            ctx.context_window if ctx else 128_000
        ))

        # Inject KB state-aware context (compiled/partial/uncompiled hints)
        messages = ctx_mgr.inject_kb_context(messages, _kb_id, _kb_state)
        state.messages = messages

        # Inject context_manager into recall tools (if registered)
        if _registry:
            from app.services.agent.recall_tools import RecallGrepTool, RecallExpandTool, RecallDescribeTool
            from app.services.agent.tools import ReportFindingsTool
            for tool in _registry._tools.values():
                if isinstance(tool, (RecallGrepTool, RecallExpandTool, RecallDescribeTool)):
                    tool.set_context_manager(ctx_mgr)
                elif isinstance(tool, ReportFindingsTool):
                    tool.set_evidence_map(state.evidence_map)

        info_tracker = InformationTracker()
        total_docs = ctx.metadata.get("total_docs", 1) if ctx else 1
        dp_manager = DecisionPointManager(
            total_docs=total_docs,
            min_exploration_rounds=12,
            max_asks=3,
            cooldown_rounds=5,
            min_docs_read=3,
        )
        docs_read_count = 0
        last_context_action = ""
        final_reason = TerminalReason.COMPLETED

        yield {"type": "thinking", "content": f"正在分析问题: {user_query}"}

        # ── Stuck detector and output store ─────────────────────
        from app.services.agent.output_store import ToolOutputStore
        stuck_detector = StuckDetector()
        output_store = ToolOutputStore(_kb_id, _session_id) if _kb_id and _session_id else None

        # ── Session notes (LLM-extracted, injected periodically) ──
        _session_notes: list[dict] = []

        # ── Intent analysis (new) ────────────────────────────────────
        state.phase = LoopPhase.PLANNING
        yield {"type": "phase", "phase": LoopPhase.PLANNING.value}

        try:
            if _llm:
                query_plan = await analyze_intent_with_llm(user_query, _llm)
            else:
                query_plan = analyze_intent_simple(user_query)
        except Exception:
            query_plan = analyze_intent_simple(user_query)

        state.query_plan = {
            "question_type": query_plan.question_type.value,
            "complexity": query_plan.complexity.value,
            "search_mode": query_plan.search_mode.value,
            "target_entities": query_plan.target_entities,
            "suggested_start_level": query_plan.suggested_start_level,
            "sub_queries": [
                {"query": sq.query, "layer": sq.target_layer, "priority": sq.priority}
                for sq in query_plan.sub_queries
            ],
        }

        yield {
            "type": "intent_analysis",
            "question_type": query_plan.question_type.value,
            "complexity": query_plan.complexity.value,
            "search_mode": query_plan.search_mode.value,
            "target_entities": query_plan.target_entities,
            "start_level": query_plan.suggested_start_level,
            "sub_queries": [
                {"query": sq.query, "layer": sq.target_layer, "priority": sq.priority}
                for sq in query_plan.sub_queries
            ],
        }
        yield {"type": "thinking", "content": f"意图分析完成: {query_plan.question_type.value}, 复杂度={query_plan.complexity.value}"}

        # ── Load KB persistent memory ────────────────────────────
        _kb_memory = KBMemory(_kb_id)
        prior_memories = _kb_memory.get_relevant(user_query, limit=5)
        if prior_memories:
            memory_text = "\n".join(f"- [{m['type']}] {m['content']}" for m in prior_memories)
            state.messages.append({
                "role": "system",
                "content": f"以下是从之前分析中积累的知识：\n{memory_text}\n请利用这些已有知识，避免重复搜索。",
            })
            yield {"type": "thinking", "content": f"已加载 {len(prior_memories)} 条历史记忆"}

        # ── Hybrid routing: simple queries → fast RAG ────────────
        if should_use_simple_rag(query_plan) and _llm:
            yield {"type": "thinking", "content": "简单查询，使用快速检索模式..."}
            try:
                rag_result = await run_simple_rag(
                    llm_client=_llm,
                    user_query=user_query,
                    kb_id=_kb_id,
                    tool_registry=_registry,
                )
                yield {
                    "type": "final_answer",
                    "content": rag_result["content"],
                    "tool_calls_made": rag_result["tool_calls_made"],
                    "iterations": rag_result["iterations"],
                    "terminal_reason": TerminalReason.COMPLETED.value,
                    "evidence_refs": rag_result.get("evidence_refs", []),
                }
                return
            except Exception as e:
                self._logger.warning("Simple RAG failed, falling back to agent loop: %s", e)

        # ── Dynamic iteration budget based on complexity ──────────
        _complexity = query_plan.complexity.value
        if _complexity == "simple":
            _effective_budget = settings.agent_iteration_budget_simple
        elif _complexity == "complex":
            _effective_budget = settings.agent_iteration_budget_complex
        else:
            _effective_budget = _max_iter
        _start_time = time.time()

        # ── Parallel research for multi-direction queries ────
        sub_queries = [sq.query for sq in query_plan.sub_queries if sq.query]
        if _complexity in ("complex", "medium") and len(sub_queries) >= 3 and _llm:
            try:
                from app.services.agent.parallel import run_parallel_research

                yield {"type": "thinking", "content": f"启动并行研究：{len(sub_queries)} 个子查询"}

                research_results = await run_parallel_research(
                    sub_queries=sub_queries[:3],  # Max 3 parallel
                    kb_id=_kb_id,
                    llm_client=_llm,
                    tool_registry=_registry,
                    max_per_query_seconds=180,
                )

                # Inject research summaries as context
                successful = [r for r in research_results if r.success]
                if successful:
                    research_summary_parts = []
                    for r in successful:
                        part = f"### 子查询: {r.sub_query}\n{r.findings}"
                        if r.entities_found:
                            part += f"\n发现的实体: {', '.join(r.entities_found[:10])}"
                        if r.docs_accessed:
                            part += f"\n相关文档: {', '.join(r.docs_accessed[:5])}"
                        research_summary_parts.append(part)

                    research_context = "\n\n".join(research_summary_parts)
                    state.messages.append({
                        "role": "system",
                        "content": (
                            f"以下是并行研究的初步结果，请在此基础上深入分析：\n\n{research_context}\n\n"
                            "请利用这些结果，避免重复搜索相同内容。如果需要更深入的信息，"
                            "使用 expand_entity 追踪具体实体，或用 read_l1/read_l2 读取原文细节。"
                        ),
                    })

                    # Track discovered entities and docs
                    for r in successful:
                        info_tracker.all_entities.update(r.entities_found)
                        info_tracker.all_docs.update(r.docs_accessed)

                failed = [r for r in research_results if not r.success]
                if failed:
                    self._logger.warning("并行研究部分失败: %s", [r.error for r in failed])

            except Exception as e:
                self._logger.warning("并行研究启动失败，继续使用单Agent循环: %s", e)

        # ── State machine loop ───────────────────────────────────────
        while True:
            current_iter = state.iteration + 1
            state.iteration = current_iter

            # ── Progress ──────────────────────────────────────────
            yield {
                "type": "progress",
                "iteration": current_iter,
                "max_iterations": _max_iter,
                "tool_calls_count": len(state.tool_calls_log),
            }

            # ── Phase: INTERPRETING → SEARCHING ───────────────────
            if state.phase == LoopPhase.INTERPRETING:
                yield {"type": "phase", "phase": LoopPhase.INTERPRETING.value}
                state.phase = LoopPhase.SEARCHING
            elif state.phase == LoopPhase.PLANNING:
                # Planning already done above, move to searching
                state.phase = LoopPhase.SEARCHING

            # ── Context management (runs every iteration) ──────────
            if ctx_mgr.should_microcompact(state.messages):
                prev_phase = state.phase
                state.phase = LoopPhase.COMPACTING
                thinking_msg = "上下文增长较快，正在压缩早期搜索结果..."
                yield {"type": "thinking", "content": thinking_msg}
                if self._emitter:
                    self._emitter.emit_thinking(thinking_msg)
                state.messages = ctx_mgr.microcompact(state.messages)
                last_context_action = "microcompact"
                state.phase = prev_phase

            # Proactive reactive compact: when context exceeds 90%
            if ctx_mgr.should_reactive_compact(state.messages) and _llm:
                prev_phase = state.phase
                state.phase = LoopPhase.COMPACTING
                thinking_msg = "上下文接近上限(90%)，正在主动压缩..."
                yield {"type": "thinking", "content": thinking_msg}
                if self._emitter:
                    self._emitter.emit_thinking(thinking_msg)
                state.messages = await ctx_mgr.reactive_compact(state.messages, _llm)
                last_context_action = "reactive_compact"
                state.phase = prev_phase

            if ctx_mgr.should_auto_compact(state.messages):
                prev_phase = state.phase
                state.phase = LoopPhase.COMPACTING
                thinking_msg = "上下文接近上限，正在生成对话摘要..."
                yield {"type": "thinking", "content": thinking_msg}
                if self._emitter:
                    self._emitter.emit_thinking(thinking_msg)
                state.messages = await ctx_mgr.auto_compact(state.messages, _llm)
                last_context_action = "auto_compact"
                state.phase = prev_phase

            total_tokens = ctx_mgr.estimate_total_tokens(state.messages)
            limit = ctx_mgr._model_context_window

            # Cache edit: truncate old tool results when approaching threshold
            cache_edit_threshold = int(limit * settings.agent_cache_edit_threshold)
            if total_tokens > cache_edit_threshold:
                state.messages = ctx_mgr.cache_edit(state.messages)
                total_tokens = ctx_mgr.estimate_total_tokens(state.messages)

            yield {
                "type": "context_update",
                "token_usage": total_tokens,
                "token_limit": limit,
                "action": last_context_action,
            }
            last_context_action = ""

            # ── Wall-clock timeout check ───────────────────────────
            elapsed = time.time() - _start_time
            if elapsed > settings.agent_max_wall_seconds:
                self._logger.info("Wall-clock timeout (%.1fs), forcing REPORTING", elapsed)
                yield {"type": "thinking", "content": f"搜索时间已达上限({settings.agent_max_wall_seconds}秒)，正在整理已有发现..."}
                state.messages.append({
                    "role": "system",
                    "content": "搜索时间已达上限，请立即基于已有信息调用 report_findings 给出最终答案。",
                })

            # ── Advisory + Hard turn limits ────────────────────────
            advisory_limit = min(_effective_budget, _max_iter)
            hard_limit = min(_effective_budget * 3, _max_iter * 2, 100)

            if current_iter == advisory_limit:
                # Advisory: suggest wrap-up
                state.messages.append({
                    "role": "system",
                    "content": (
                        f"[提示] 已达到建议迭代次数({advisory_limit})。"
                        "请整理已有发现，调用 report_findings 生成最终报告。"
                        "如仍需深入分析，可以继续，但有硬性上限。"
                    ),
                })
            elif current_iter > hard_limit:
                # Hard limit: force termination
                final_reason = TerminalReason.MAX_ITERATIONS
                break

            # ── Streaming LLM call with model fallback ──────
            response = None
            _llm_role = RoleType.MAIN
            _used_fallback = False

            # Fallback chain: MAIN → LIGHTWEIGHT → emergency compact + LIGHTWEIGHT
            for _attempt in range(3):
                try:
                    all_tools = _registry.get_tool_definitions()
                    async for se in self._streaming_llm_call(
                        _llm, state.messages, all_tools, role=_llm_role,
                    ):
                        if se["type"] == "_response":
                            response = se["response"]
                        else:
                            yield se  # Forward chunk events
                    break  # Success
                except Exception as e:
                    error_str = str(e).lower()
                    is_context_error = "prompt" in error_str and ("too long" in error_str or "exceed" in error_str)

                    if _attempt == 0:
                        # First failure: try lightweight model
                        self._logger.warning("Main model failed (%s), trying lightweight fallback", e)
                        _llm_role = RoleType.LIGHTWEIGHT
                        _used_fallback = True
                        if is_context_error:
                            state.messages = await ctx_mgr.reactive_compact(state.messages, _llm)
                    elif _attempt == 1:
                        # Second failure: SM compact (zero API cost) if notes available, else emergency
                        self._logger.warning("Lightweight model also failed (%s), compacting context", e)
                        if _session_notes:
                            state.messages = ctx_mgr.sm_compact(state.messages, _session_notes)
                        else:
                            state.messages = ctx_mgr.emergency_compact(state.messages)
                        yield {"type": "thinking", "content": "上下文过大，正在进行紧急压缩..."}
                    else:
                        # Third failure: give up
                        final_reason = TerminalReason.ERROR
                        yield {
                            "type": "final_answer",
                            "content": f"LLM 调用失败（已尝试模型降级和紧急压缩）: {e}",
                            "tool_calls_made": len(state.tool_calls_log),
                            "iterations": current_iter,
                            "terminal_reason": final_reason.value,
                        }
                        return

            # Notify if using fallback model
            if _used_fallback:
                state.messages.append({
                    "role": "system",
                    "content": "[提示] 当前使用轻量模型，回答可能较简略，请优先基于已有信息生成报告。",
                })

            if response is None:
                return

            message = response.get("choices", [{}])[0].get("message", {})
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", []) or []

            # ── max_tokens auto-continuation ─────────────────────
            finish_reason = response.get("choices", [{}])[0].get("finish_reason", "")
            if finish_reason == "length" and not tool_calls:
                state._continuation_count = getattr(state, '_continuation_count', 0) + 1
                if state._continuation_count <= 3:
                    yield {"type": "thinking", "content": "回答被截断，正在自动续写..."}
                    state.messages.append({"role": "assistant", "content": content})
                    state.messages.append({
                        "role": "user",
                        "content": "请从刚才断点继续输出，不要重复已写内容。直接接着写即可。",
                    })
                    continue
                else:
                    # Exhausted continuations, deliver what we have
                    pass
            else:
                state._continuation_count = 0

            # ── Think-only stuck detection ───────────────────────
            if not tool_calls and content:
                stuck_detector.record_text_only()
                if stuck_detector.check_text_only():
                    intervention = stuck_detector.get_intervention()
                    state.messages.append({"role": "assistant", "content": content})
                    state.messages.append({"role": "user", "content": intervention})
                    yield {"type": "thinking", "content": "检测到连续分析无行动，注入搜索引导..."}
                    continue

            # ── Tool call handling ─────────────────────────────────
            if tool_calls:
                state.phase = LoopPhase.SEARCHING
                # Record tool names for stuck detection
                for tc in tool_calls:
                    tn = tc.get("function", {}).get("name", "")
                    stuck_detector.record_tool_call(tn)

                # Execute tools (parallel for read-only)
                results, stuck_hits = await self._execute_tool_calls(
                    tool_calls, _kb_id, state.call_history,
                    output_store=output_store, stuck_detector=stuck_detector,
                )

                # Accumulate stuck count and force report if persistently stuck
                state.stuck_count += stuck_hits
                if state.stuck_count >= 3:
                    state.messages.append({
                        "role": "system",
                        "content": (
                            "[系统强制终止] Agent已连续多次重复相同搜索策略。"
                            "请立即使用 report_findings 工具，基于已收集的信息生成最终分析报告。"
                            "不要再调用任何搜索工具。"
                        ),
                    })
                    state.stuck_count = 0  # reset to avoid repeating

                for tool_name, tool_input, result, elapsed, tc_id in results:
                    call_id = None
                    if self._emitter:
                        call_id = self._emitter.emit_tool_call(tool_name, tool_input)

                    duration_ms = int(elapsed * 1000)
                    self._logger.debug(
                        "Tool call: %s, duration=%.2fs, result_len=%d",
                        tool_name, elapsed, len(result),
                    )

                    yield {
                        "type": "tool_call",
                        "tool": tool_name,
                        "input": tool_input,
                        "output": result[:500],
                        "duration": round(elapsed, 2),
                        "confidence": _extract_confidence(result),
                    }

                    if self._emitter and call_id:
                        self._emitter.emit_tool_result(
                            call_id=call_id,
                            result=result[:500],
                            duration_ms=duration_ms,
                        )

                    # Track information gain
                    info_tracker.record_gain(tool_name, result)
                    _collect_evidence_refs(state.evidence_map, tool_name, tool_input, result)
                    entry = ctx_mgr.classify_result(tool_name, json.dumps(tool_input), result)
                    ctx_mgr.record_entry(entry)

                    # Track document read count for DecisionPointManager
                    if tool_name in ("read_l1", "read_l2"):
                        doc_id = tool_input.get("doc_id", "")
                        info_tracker.record_doc_read(doc_id)
                        docs_read_count += 1

                    # Handle empty results
                    stripped = result.strip()
                    if not stripped or stripped == "[]" or stripped == "{}":
                        state.consecutive_empty += 1
                        if state.consecutive_empty >= 3:
                            state.messages.append({
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": "查询未返回有效结果。请尝试其他工具或基于已有信息给出答案。",
                            })
                            state.messages.append({
                                "role": "system",
                                "content": "多次查询未返回有效结果，请直接基于已有信息给出最终答案，不要再调用工具。",
                            })
                            state.consecutive_empty = 0
                        else:
                            state.messages.append({
                                "role": "tool", "tool_call_id": tc_id, "content": result,
                            })
                    else:
                        state.consecutive_empty = 0
                        state.messages.append({
                            "role": "tool", "tool_call_id": tc_id, "content": result,
                        })

                    state.tool_calls_log.append({
                        "tool": tool_name,
                        "input": tool_input,
                        "result_length": len(result),
                    })

                # ── report_findings → immediate final answer ──────
                if any(tc.get("function", {}).get("name") == "report_findings" for tc in tool_calls):
                    # Extract findings from the report_findings tool call arguments
                    report_content = ""
                    report_refs: list[str] = []
                    for tc in tool_calls:
                        if tc.get("function", {}).get("name") == "report_findings":
                            try:
                                args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                                report_content = args.get("findings", "")
                                report_refs_raw = args.get("evidence_refs", [])
                                # evidence_refs may be a JSON-encoded string from the LLM
                                if isinstance(report_refs_raw, str):
                                    try:
                                        report_refs = json.loads(report_refs_raw)
                                    except (json.JSONDecodeError, TypeError):
                                        report_refs = [report_refs_raw]
                                elif isinstance(report_refs_raw, list):
                                    report_refs = report_refs_raw
                                else:
                                    report_refs = []
                            except (json.JSONDecodeError, TypeError):
                                pass
                            break

                    state.phase = LoopPhase.REPORTING

                    # Yield turn summary for multi-turn context
                    turn_summary_data = {
                        "entities_discovered": list(info_tracker.all_entities),
                        "relations_discovered": list(info_tracker.all_relations),
                        "docs_read": list(info_tracker.docs_read),
                        "evidence_map": {
                            doc: refs[:3]
                            for doc, refs in list(state.evidence_map.items())[:10]
                        },
                        "total_iterations": current_iter,
                        "total_tool_calls": len(state.tool_calls_log),
                    }
                    yield {"type": "turn_summary", **turn_summary_data}

                    # Persist findings to KB memory
                    try:
                        _kb_memory.save_turn(_session_id, turn_summary_data)
                    except Exception as e:
                        self._logger.warning("Failed to save KB memory: %s", e)

                    # Use the report content as final answer
                    display_content = report_content or f"分析完成，共调用 {len(state.tool_calls_log)} 次工具，发现 {len(info_tracker.all_entities)} 个实体、{len(info_tracker.all_relations)} 个关系。"
                    if report_refs:
                        display_content += "\n\n**引用来源:**\n" + "\n".join(f"- {r}" for r in report_refs)

                    yield {
                        "type": "final_answer",
                        "content": display_content,
                        "tool_calls_made": len(state.tool_calls_log),
                        "iterations": current_iter,
                        "terminal_reason": TerminalReason.COMPLETED.value,
                        "evidence_refs": report_refs,
                    }
                    return

                # ── Phase: EVALUATING ─────────────────────────────
                state.phase = LoopPhase.EVALUATING

                # System nudge: if Agent discovers many docs but hasn't read them,
                # prompt it to read instead of asking the user
                docs_discovered = len(info_tracker.all_docs)
                if (
                    docs_discovered >= 10
                    and docs_read_count <= 2
                    and current_iter >= 5
                    and not state._read_nudge_sent
                ):
                    state._read_nudge_sent = True
                    nudge_msg = (
                        f"检测到 {docs_discovered} 份相关文档，但仅深入读取了 {docs_read_count} 份。"
                        f"请使用 read_l1 或 read_l2 逐份读取这些文档以获取详细信息，"
                        f"不要急于向用户提问。每份文档的深度信息都在 l1 和 l2 层中。"
                    )
                    yield {"type": "thinking", "content": nudge_msg}
                    state.messages.append({"role": "system", "content": nudge_msg})

                # Phase-aware decision point detection
                dp = dp_manager.evaluate(
                    iteration=current_iter,
                    entity_count=len(info_tracker.all_entities),
                    relation_count=len(info_tracker.all_relations),
                    docs_with_results=len(info_tracker.all_docs),
                    docs_read_count=docs_read_count,
                    is_saturated=info_tracker.is_saturated(),
                    contradiction_count=len(info_tracker.contradictions),
                )

                if dp is not None:
                    dp_stats = dp_manager.get_stats()
                    if _ask_user_cb is not None:
                        # ── Bidirectional: yield event, pause via callback ──
                        prev_phase = state.phase
                        state.phase = LoopPhase.WAITING_USER
                        ask_event = {
                            "type": "ask_user",
                            "content": dp.question,
                            "question": dp.question,
                            "options": dp.options,
                            "scenario": dp.scenario,
                            "asks_made": dp_stats.get("asks_made", 0),
                        }
                        yield ask_event
                        try:
                            user_answer = await _ask_user_cb(ask_event)
                            state.messages.append({
                                "role": "user",
                                "content": f"[用户反馈] {user_answer}",
                            })
                        except Exception:
                            pass  # Timeout or cancellation — continue without user input
                        state.phase = prev_phase
                    else:
                        # Legacy: emit ask_user event and continue
                        yield {
                            "type": "ask_user",
                            "content": dp.question,
                            "question": dp.question,
                            "options": dp.options,
                            "scenario": dp.scenario,
                            "asks_made": dp_stats.get("asks_made", 0),
                        }
                        yield {"type": "thinking", "content": f"触发决策点 ({dp.scenario})，正在调整搜索策略..."}
                        if self._emitter:
                            self._emitter.emit_thinking(f"决策点触发: {dp.scenario}")
                        state.messages.append({
                            "role": "system",
                            "content": (
                                f"决策点触发 ({dp.scenario}): {dp.question}\n"
                                f"已发现 {len(info_tracker.all_entities)} 个实体、"
                                f"{len(info_tracker.all_relations)} 个关系。"
                                "请尝试使用不同的工具组合，或扩大搜索范围。"
                            ),
                        })

                # Information saturation check (independent of decision points)
                if info_tracker.is_saturated() and not state.saturation_prompt_sent:
                    thinking_msg = "信息趋于饱和，最近几轮没有获得新的实体或关系，正在整理答案..."
                    yield {"type": "thinking", "content": thinking_msg}
                    if self._emitter:
                        self._emitter.emit_thinking(thinking_msg)
                    evidence_summary = _format_evidence_for_prompt(state.evidence_map)
                    state.messages.append({
                        "role": "system",
                        "content": (
                            "最近几轮搜索没有发现任何新的实体、关系或文档。"
                            "说明已穷尽了有用信息。请基于已有信息直接给出最终答案。"
                            f"已发现的实体: {list(info_tracker.all_entities)[:10]}"
                            f"已发现的关系: {list(info_tracker.all_relations)[:10]}"
                            f"\n\n可引用的证据来源：\n{evidence_summary}"
                            "\n\n请在 report_findings 时使用 evidence_refs 字段列出所有引用的证据来源。"
                        ),
                    })
                    state.saturation_prompt_sent = True

                # ── Structured reflection (every N iterations) ────────
                if (
                    current_iter >= settings.agent_reflection_interval
                    and current_iter % settings.agent_reflection_interval == 0
                    and _llm
                ):
                    try:
                        refl = await _run_reflection(
                            llm_client=_llm,
                            user_query=user_query,
                            entities_found=list(info_tracker.all_entities),
                            relations_found=list(info_tracker.all_relations),
                            docs_read=list(info_tracker.docs_read),
                            evidence_map=state.evidence_map,
                            iteration=current_iter,
                            tool_calls_count=len(state.tool_calls_log),
                        )
                    except Exception as e:
                        self._logger.warning("Reflection error: %s", e)
                        refl = None

                    if refl is not None:
                        state.last_confidence = refl.confidence
                        state.reflection_history.append({
                            "iteration": current_iter,
                            "confidence": refl.confidence,
                            "answered": refl.answered_aspects,
                            "missing": refl.missing_aspects,
                            "next_query": refl.next_query,
                            "evidence_strength": refl.evidence_strength,
                        })

                        yield {
                            "type": "reflection",
                            "confidence": refl.confidence,
                            "answered_aspects": refl.answered_aspects,
                            "missing_aspects": refl.missing_aspects,
                            "next_query": refl.next_query,
                            "evidence_strength": refl.evidence_strength,
                            "iteration": current_iter,
                        }

                        # Convergence: high confidence → force REPORTING
                        should_stop = False
                        if refl.confidence >= settings.agent_confidence_threshold:
                            should_stop = True
                            reason = f"置信度达到 {refl.confidence:.0%}"
                        elif refl.confidence >= 0.60 and not refl.missing_aspects:
                            should_stop = True
                            reason = f"置信度 {refl.confidence:.0%} 且无缺失信息"
                        elif not refl.next_query.strip():
                            should_stop = True
                            reason = "反思未产生新的搜索方向"

                        if should_stop:
                            yield {"type": "thinking", "content": f"自我评估: {reason}，正在整理最终答案..."}
                            evidence_summary = _format_evidence_for_prompt(state.evidence_map)
                            state.messages.append({
                                "role": "system",
                                "content": (
                                    f"自我评估结论: {reason}。\n"
                                    f"已解答: {', '.join(refl.answered_aspects[:5])}\n"
                                    f"证据强度: {refl.evidence_strength}\n"
                                    f"可引用的证据来源：\n{evidence_summary}\n"
                                    "请立即调用 report_findings 给出最终结构化答案。"
                                ),
                            })
                        elif refl.next_query.strip():
                            # Inject next search direction as hint
                            hint_msg = f"反思建议: 仍有未解答的方面({', '.join(refl.missing_aspects[:3])})，建议搜索「{refl.next_query}」"
                            yield {"type": "thinking", "content": hint_msg}
                            state.messages.append({
                                "role": "system",
                                "content": hint_msg,
                            })

                state.phase = LoopPhase.SEARCHING  # Continue searching if more tool calls needed

                # ── Session notes extraction (periodic, async background) ────
                if _llm and current_iter > 0:
                    # Initialize async extractor if not yet created
                    if not hasattr(state, '_async_mem_extractor'):
                        state._async_mem_extractor = AsyncSessionMemoryExtractor()

                    extractor = state._async_mem_extractor
                    # Check if pending notes from background extraction
                    pending = extractor.get_pending_notes()
                    if pending:
                        _session_notes.clear()
                        _session_notes.extend(pending)
                        notes_text = format_session_notes(_session_notes)
                        found_notes = False
                        for i, m in enumerate(state.messages):
                            if (m.get("role") == "system"
                                    and "本次会话已积累的关键发现" in m.get("content", "")):
                                state.messages[i] = {"role": "system", "content": notes_text}
                                found_notes = True
                                break
                        if not found_notes:
                            state.messages.append({"role": "system", "content": notes_text})

                    # Trigger background extraction periodically
                    if current_iter % settings.agent_session_notes_interval == 0:
                        total_chars = sum(len(m.get("content", "")) for m in state.messages)
                        if extractor.should_extract(total_chars):
                            import asyncio
                            asyncio.ensure_future(
                                extractor.extract_background(state.messages, _llm)
                            )

                continue

            # ── No tool calls → REPORTING phase → final answer ─────
            state.phase = LoopPhase.REPORTING

            # Fallback: if no content and no tool calls, try a quick search
            if not content.strip() and len(state.tool_calls_log) < 2:
                self._logger.info("Empty answer with few tool calls, executing fallback search")
                try:
                    from app.services.retrieval.hybrid_search import KeywordSearch, _extract_chinese_words
                    words = _extract_chinese_words(user_query)
                    if words:
                        fallback_results = KeywordSearch.search(
                            " ".join(words), top_k=5, kb_id=_kb_id,
                        )
                        if fallback_results:
                            parts = []
                            for r in fallback_results[:5]:
                                doc_id = r.get("doc_id", "")
                                snippet = r.get("content", "")[:300]
                                parts.append(f"[{doc_id}] {snippet}")
                            content = (
                                f"搜索未找到充分信息，以下是关键词匹配结果：\n\n"
                                + "\n".join(parts)
                                + "\n\n请尝试用更具体的关键词提问。"
                            )
                except Exception as e:
                    self._logger.warning("Fallback search failed: %s", e)

                if not content.strip():
                    content = "抱歉，经过多轮搜索未能找到相关信息。请尝试用更具体的关键词提问。"

            if self._emitter:
                self._emitter.emit_final_answer(content)

            # Yield turn summary for multi-turn context
            turn_summary_data2 = {
                "entities_discovered": list(info_tracker.all_entities),
                "relations_discovered": list(info_tracker.all_relations),
                "docs_read": list(info_tracker.docs_read),
                "evidence_map": {
                    doc: refs[:3]
                    for doc, refs in list(state.evidence_map.items())[:10]
                },
                "total_iterations": current_iter,
                "total_tool_calls": len(state.tool_calls_log),
            }
            yield {"type": "turn_summary", **turn_summary_data2}

            # Persist findings to KB memory
            try:
                _kb_memory.save_turn(_session_id, turn_summary_data2)
            except Exception as e:
                self._logger.warning("Failed to save KB memory: %s", e)

            yield {
                "type": "final_answer",
                "content": content,
                "tool_calls_made": len(state.tool_calls_log),
                "iterations": current_iter,
                "terminal_reason": TerminalReason.COMPLETED.value,
            }
            return

        # ── Loop exhausted (max iterations) ──────────────────────────
        stats = info_tracker.get_stats()
        synthesized = (
            f"经过 {_max_iter} 轮搜索，共调用了 {len(state.tool_calls_log)} 次工具。\n"
            f"已发现 {stats['total_entities']} 个实体、"
            f"{stats['total_relations']} 个关系、"
            f"{stats['total_docs']} 个文档。\n\n"
            f"搜索记录：\n"
        )
        for i, entry in enumerate(state.tool_calls_log, 1):
            synthesized += f"{i}. {entry['tool']}: {entry['input']}\n"
        synthesized += "\n请根据以上搜索结果获取更多信息。"

        if self._emitter:
            self._emitter.emit_final_answer(synthesized)
        yield {
            "type": "final_answer",
            "content": synthesized,
            "tool_calls_made": len(state.tool_calls_log),
            "iterations": _max_iter,
            "terminal_reason": final_reason.value,
        }

    # ── Streaming LLM call ─────────────────────────────────────────────

    _TRANSIENT_ERROR_SUBSTRINGS = (
        "rate_limit", "429", "503", "529", "timeout",
        "econnrefused", "econnreset", "connection error",
        "server error", "overloaded", "capacity",
    )
    _MAX_TRANSIENT_RETRIES = 5

    async def _streaming_llm_call(
        self, _llm, messages: list[dict], tools: list[dict],
        role=RoleType.MAIN,
    ) -> AsyncIterator[dict]:
        """Stream LLM response with transient error retry.

        Yields chunk events and finishes with the assembled response
        dict (type="_response"). Retries on transient errors (429, 500,
        timeout) with exponential backoff before giving up.
        """
        for attempt in range(self._MAX_TRANSIENT_RETRIES + 1):
            content_parts: list[str] = []
            tc_accum: dict[int, dict] = {}
            streaming_tasks: dict[str, asyncio.Task] = {}

            # Store the streaming tasks dict on self for _execute_tool_calls
            self._streaming_tasks = streaming_tasks

            try:
                stream = _llm.chat_stream(
                    role=role,
                    messages=messages,
                    tools=tools,
                    temperature=0.3,
                )
                # Track tool-def-hint for pre-execution
                tool_idx_to_name: dict[int, str] = {}

                async for delta in stream:
                    if delta["type"] == "text_delta":
                        content_parts.append(delta["content"])
                        yield {"type": "chunk", "content": delta["content"]}

                    elif delta["type"] == "tool_use_block":
                        idx = delta["index"]
                        if idx not in tc_accum:
                            tc_accum[idx] = {
                                "id": delta.get("id", ""),
                                "name": "",
                                "arguments_str": "",
                            }
                        acc = tc_accum[idx]
                        if delta.get("id"):
                            acc["id"] = delta["id"]
                        if delta.get("name"):
                            acc["name"] += delta["name"]
                            # Once name is complete, pre-execute if it's read-only
                            if acc["name"] in READ_ONLY_TOOLS and flags.agent_streaming_tool_execution:
                                tool_idx_to_name[idx] = acc["name"]
                        if delta.get("arguments"):
                            acc["arguments_str"] += delta["arguments"]
                            # When arguments are complete, start read-only tools immediately
                            if (flags.agent_streaming_tool_execution
                                    and idx in tool_idx_to_name
                                    and acc["arguments_str"].strip().endswith("}")):
                                try:
                                    args = json.loads(acc["arguments_str"])
                                    args["kb_id"] = self._kb_id if hasattr(self, '_kb_id') else ""
                                    task = asyncio.create_task(
                                        self._registry.execute(acc["name"], **args)
                                    )
                                    streaming_tasks[acc["id"]] = task
                                    yield {"type": "tool_start", "tool": acc["name"], "input": args}
                                except (json.JSONDecodeError, TypeError):
                                    pass  # Arguments incomplete, wait for more

                # Stream completed successfully
                break

            except Exception as e:
                error_str = str(e).lower()
                is_transient = any(s in error_str for s in self._TRANSIENT_ERROR_SUBSTRINGS)

                if is_transient and attempt < self._MAX_TRANSIENT_RETRIES:
                    delay = min(5000, 1000 * (2 ** attempt))
                    self._logger.warning(
                        "Transient error (attempt %d/%d), retrying in %dms: %s",
                        attempt + 1, self._MAX_TRANSIENT_RETRIES, delay, e,
                    )
                    await asyncio.sleep(delay / 1000)
                    continue

                # Non-transient or exhausted retries
                self._logger.warning("Streaming LLM call failed: %s", e)
                yield {"type": "_response", "response": None}
                return

        content = "".join(content_parts)
        tool_calls = []
        for idx in sorted(tc_accum.keys()):
            acc = tc_accum[idx]
            tool_calls.append({
                "id": acc["id"] or f"tc_{idx}",
                "type": "function",
                "function": {
                    "name": acc["name"],
                    "arguments": acc["arguments_str"],
                },
            })

        response = {
            "choices": [{
                "message": {
                    "content": content,
                    "tool_calls": tool_calls if tool_calls else None,
                }
            }]
        }
        yield {"type": "_response", "response": response}

    # ── Tool execution helpers ──────────────────────────────────────────

    async def _execute_tool_calls(
        self,
        tool_calls: list[dict],
        kb_id: str,
        call_history: set[str],
        output_store=None,
        stuck_detector=None,
        streaming_tasks: dict[str, asyncio.Task] | None = None,
    ) -> tuple[list[tuple[str, dict, str, float, str]], int]:
        """Execute tool calls with parallel support for read-only tools.

        If streaming_tasks is provided, merges pre-started streaming results
        with newly executed tools. This enables tools to start executing
        before the model finishes its response (streaming tool execution).

        Returns (results, stuck_count) where results is a list of
        (tool_name, tool_input, result, elapsed_seconds, tool_call_id)
        and stuck_count is how many tool calls triggered stuck detection.
        """
        read_tasks = []
        write_tasks = []

        for tc in tool_calls:
            tool_name = tc.get("function", {}).get("name", "unknown")
            try:
                tool_input = json.loads(tc.get("function", {}).get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                tool_input = {}
            tool_input["kb_id"] = kb_id
            tc_id = tc.get("id", "")

            query_sig = f"{tool_name}:{json.dumps(tool_input, sort_keys=True)}"
            task_info = (tc, tool_name, tool_input, query_sig, tc_id)

            if tool_name in READ_ONLY_TOOLS:
                read_tasks.append(task_info)
            else:
                write_tasks.append(task_info)

        semaphore = asyncio.Semaphore(5)
        all_results: list[tuple] = []
        stuck_count = 0

        async def _run_read(tc, tool_name, tool_input, query_sig, tc_id):
            async with semaphore:
                name, inp, res, elapsed, tid, is_stuck = await self._run_single_tool(
                    tool_name, tool_input, query_sig, call_history, tc_id,
                    output_store=output_store, stuck_detector=stuck_detector,
                )
                return (name, inp, res, elapsed, tid), is_stuck

        if read_tasks:
            read_results = await asyncio.gather(
                *[_run_read(*t) for t in read_tasks],
                return_exceptions=True,
            )
            for r in read_results:
                if isinstance(r, Exception):
                    err_msg = str(r)
                    recovery = _suggest_recovery("unknown", err_msg)
                    all_results.append(("unknown", {}, f"工具执行错误: {err_msg}。建议: {recovery}", 0, ""))
                else:
                    result_tuple, is_stuck = r
                    all_results.append(result_tuple)
                    if is_stuck:
                        stuck_count += 1

        for tc, tn, ti, qs, tid in write_tasks:
            try:
                name, inp, res, elapsed, tc_id_out, is_stuck = await self._run_single_tool(
                    tn, ti, qs, call_history, tid,
                    output_store=output_store, stuck_detector=stuck_detector,
                )
                all_results.append((name, inp, res, elapsed, tc_id_out))
                if is_stuck:
                    stuck_count += 1
            except Exception as e:
                err_msg = str(e)
                recovery = _suggest_recovery(tn, err_msg)
                all_results.append((tn, ti, f"工具执行错误: {err_msg}。建议: {recovery}", 0, ""))

        return all_results, stuck_count

    async def _run_single_tool(
        self,
        tool_name: str,
        tool_input: dict,
        query_sig: str,
        call_history: set[str],
        tool_call_id: str = "",
        output_store=None,
        stuck_detector=None,
    ) -> tuple[str, dict, str, float, str, bool]:
        """Execute a single tool call. Returns (tool_name, tool_input, result, elapsed, tool_call_id, is_stuck)."""
        if query_sig in call_history:
            return (
                tool_name,
                tool_input,
                "该查询已执行过，请使用已有结果继续分析，或尝试不同的查询角度。",
                0,
                tool_call_id,
                False,
            )

        call_history.add(query_sig)

        start = time.time()
        try:
            result = await self._registry.execute(tool_name, **tool_input)
        except Exception as e:
            err_msg = str(e)
            recovery = _suggest_recovery(tool_name, err_msg)
            result = f"工具执行错误: {err_msg}。建议: {recovery}"
        elapsed = time.time() - start

        # Externalize large outputs (tool result budgeting)
        # Per-tool budgets: expand/read tools get more, others capped
        _TOOL_BUDGETS = {
            "expand_entity": 12000,
            "read_l2": 10000,
            "read_l1": 10000,
            "read_l0": 8000,
            "batch_expand_l1": 12000,
            "batch_expand_abstracts": 12000,
        }
        budget = _TOOL_BUDGETS.get(tool_name, 6000)
        if isinstance(result, str) and len(result) > budget:
            result = result[:budget] + f"\n...[结果已截断至{budget}字符，原始长度{len(result)}]"

        # Persist very large results to disk
        if output_store and isinstance(result, str) and len(result) > 4000:
            result = output_store.store(tool_name, result)

        # Stuck detection
        is_stuck = False
        if stuck_detector:
            result_hash = str(hash(result[:200]))
            if stuck_detector.check(tool_name, result_hash):
                is_stuck = True
                result = stuck_detector.get_intervention(tool_name) + "\n\n" + result[:500]

        return (tool_name, tool_input, result, elapsed, tool_call_id, is_stuck)


def _suggest_recovery(tool_name: str, error_msg: str) -> str:
    """Generate recovery hints for tool execution errors."""
    err_lower = error_msg.lower()

    if "not found" in err_lower or "no " in err_lower:
        if "vector" in tool_name or "search" in tool_name:
            return "尝试 search_keyword 换用不同关键词，或扩大搜索范围"
        if "read_l" in tool_name:
            return "检查文档ID是否正确，或先用 search 定位相关文档"
        return "尝试不同的搜索参数或工具"

    if "timeout" in err_lower or "timed out" in err_lower:
        return "搜索耗时过长，尝试缩小查询范围或减少 top_k"

    if "kb_id" in err_lower or "required" in err_lower:
        return "缺少必要参数，检查工具输入是否完整"

    if "embedding" in err_lower or "faiss" in err_lower:
        return "向量搜索不可用，改用 search_keyword 进行关键词搜索"

    return "换用其他搜索工具或调整查询参数"


class StuckDetector:
    """Detect when the Agent is stuck with four detection patterns.

    Inspired by leohc/DeepAnalyze agent-runner.ts StuckDetector.
    Patterns:
      - Think-only loop: 8 consecutive think/text responses with no tool calls
      - Frequency threshold: same tool called >= threshold times in recent window
      - Consecutive streak: same tool called N times in a row
      - Empty-result streak: N consecutive empty results → force strategy change
    """

    THINK_ONLY_WINDOW = 8
    THINK_ONLY_THRESHOLD = 8
    FREQUENCY_THRESHOLD = 5
    FREQUENCY_WINDOW = 8
    CONSECUTIVE_THRESHOLD = 5
    EMPTY_RESULT_THRESHOLD = 3
    MAX_INTERVENTIONS = 2
    EXEMPT_TOOLS = {"expand", "batch_expand_abstracts"}

    def __init__(self):
        self._history: list[str] = []  # tool_name entries
        self._text_only_count: int = 0  # consecutive text-only turns
        self._intervention_count: int = 0
        self._empty_result_count: int = 0  # consecutive empty results
        self._result_hashes: set[str] = set()  # semantic dedup via result hashes

    def record_text_only(self):
        """Record a turn where the model produced text but no tool calls."""
        self._text_only_count += 1

    def record_tool_call(self, tool_name: str):
        """Record a tool call."""
        self._text_only_count = 0
        self._history.append(tool_name)
        if len(self._history) > 20:
            self._history = self._history[-20:]

    def check(self, tool_name: str, result_hash: str) -> bool:
        """Return True if a stuck pattern is detected."""
        if self._intervention_count >= self.MAX_INTERVENTIONS:
            return False
        if tool_name in self.EXEMPT_TOOLS:
            return False

        # Track empty result streak
        if not result_hash or result_hash == str(hash("")):
            self._empty_result_count += 1
        else:
            self._empty_result_count = 0

        # Check empty-result streak
        if self._empty_result_count >= self.EMPTY_RESULT_THRESHOLD:
            self._intervention_count += 1
            self._empty_result_count = 0
            return True

        # Check semantic duplicate (same result hash seen before)
        if result_hash in self._result_hashes and len(self._result_hashes) > 3:
            # Same exact result from different tool calls → stuck
            self._intervention_count += 1
            return True
        self._result_hashes.add(result_hash)

        return self._detect_pattern(tool_name)

    def check_text_only(self) -> bool:
        """Return True if the agent is in a think-only loop."""
        if self._intervention_count >= self.MAX_INTERVENTIONS:
            return False
        return self._text_only_count >= self.THINK_ONLY_THRESHOLD

    def _detect_pattern(self, tool_name: str) -> bool:
        """Check frequency and consecutive patterns."""
        if not self._history:
            return False

        # Pattern 1: Consecutive streak
        recent = self._history[-self.CONSECUTIVE_THRESHOLD:]
        if len(recent) >= self.CONSECUTIVE_THRESHOLD and all(t == tool_name for t in recent):
            self._intervention_count += 1
            return True

        # Pattern 2: Frequency threshold
        window = self._history[-(self.FREQUENCY_WINDOW + 3):]
        count = sum(1 for t in window if t == tool_name)
        if count >= self.FREQUENCY_THRESHOLD:
            self._intervention_count += 1
            return True

        return False

    def get_intervention(self, tool_name: str = "") -> str:
        """Return a tool-specific intervention message."""
        # Empty-result intervention (highest priority)
        if self._empty_result_count >= self.EMPTY_RESULT_THRESHOLD:
            return (
                "[系统干预] 连续多次搜索返回空结果。"
                "请立即执行以下操作：\n"
                "1. 扩大搜索范围（使用更宽泛的关键词）\n"
                "2. 尝试搜索不同维度的信息\n"
                "3. 如果确实无法找到更多信息，调用 report_findings 总结已有发现\n"
                "不要继续使用相同的搜索参数。"
            )

        # Think-only intervention
        if self._text_only_count >= self.THINK_ONLY_THRESHOLD:
            return (
                "[系统干预] 检测到连续多轮仅分析未执行搜索。"
                "请立即执行以下操作之一：\n"
                "1. 调用 search_keyword 搜索相关内容\n"
                "2. 调用 progressive_search 进行多层级搜索\n"
                "3. 调用 report_findings 基于已有信息生成报告\n"
                "不要再继续分析，必须执行具体搜索操作。"
            )

        # Tool-specific interventions
        tool_hints = {
            "search_keyword": "换用不同的关键词，或尝试 progressive_search 多层级搜索",
            "progressive_search": "尝试 search_keyword 换用不同关键词，或使用 coordinate_research 多角度分析",
            "read_l2": "检查是否已经获取了足够信息，考虑调用 report_findings 生成报告",
            "read_l1": "尝试用 search_keyword 搜索更多相关段落",
            "expand_entity": "已充分了解该实体，尝试搜索其他实体或生成报告",
        }
        hint = tool_hints.get(tool_name, "换用完全不同的搜索策略或工具")

        return (
            f"[系统干预] 检测到对工具 '{tool_name}' 的重复调用。{hint}。\n"
            "如果已有足够信息，请调用 report_findings 生成最终报告。"
        )
