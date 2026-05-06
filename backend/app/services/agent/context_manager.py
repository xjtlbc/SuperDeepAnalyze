"""ContextManager: DAG-based context lifecycle management for Agent loop.

Three-layer compression with DAG reference preservation:
  Layer 1: Tool result classification (critical/normal/transient)
  Layer 2: Leaf compaction — summarize consumed tool results into DAG leaf nodes
  Layer 3: Condensed compaction — merge leaf summaries into higher-level summaries

Inspired by Lossless-Claw's DAG-based compaction engine.
"""

import json
import re
import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional

from app.models.config import RoleType
from app.services.agent.utils import extract_entities
from app.utils.logging_config import get_logger

logger = get_logger("app.agent.context_manager")


@dataclass
class ToolResultEntry:
    """Tracks a single tool execution result with metadata."""
    tool_name: str
    query: str
    result_text: str
    summary: str = ""
    importance: str = "normal"  # critical | normal | transient
    consumed: bool = False
    entities_found: set = field(default_factory=set)
    relations_found: set = field(default_factory=set)
    docs_referenced: set = field(default_factory=set)


@dataclass
class SummaryNode:
    """A node in the compression DAG.

    Leaf nodes (depth=0) summarize raw tool results.
    Condensed nodes (depth>=1) summarize multiple leaf/condensed nodes.
    """
    node_id: str
    depth: int
    content: str
    children_ids: list[str] = field(default_factory=list)
    source_text_preview: str = ""
    token_count: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "depth": self.depth,
            "content": self.content,
            "children_ids": self.children_ids,
            "source_text_preview": self.source_text_preview[:200],
            "token_count": self.token_count,
        }


@dataclass
class CompactResult:
    """Result of a compaction operation."""
    action: str          # "microcompact" | "leaf_compact" | "condensed_compact" | "none"
    tokens_before: int = 0
    tokens_after: int = 0
    nodes_created: int = 0


# Token threshold multipliers (relative to context window)
_MICROCOMPACT_RATIO = 0.40
_AUTOCOMPACT_RATIO = 0.80
_LEAF_COMPACT_RATIO = 0.60

# Fresh tail: protect the most recent N tool-result blocks from compaction
_FRESH_TAIL_BLOCKS = 2

# Escalation thresholds
_FALLBACK_MAX_CHARS = 2048  # Deterministic truncation fallback

# Tool result budget: max chars per single tool result
MAX_TOOL_RESULT_CHARS = 8000
MAX_TOOL_RESULT_CHARS_STRUCTURED = 12000  # L0/L1 results (entities, summaries)

# CJK token estimation: 1.8 tokens/char for CJK, 0.25 for ASCII
_CJK_TOKEN_RATIO = 1.8
_ASCII_TOKEN_RATIO = 0.25

# Circuit breaker: stop retrying compaction after N consecutive failures
_MAX_COMPACT_FAILURES = 3


def _estimate_tokens_cjk(text: str) -> int:
    """Estimate tokens with CJK awareness."""
    cjk_count = sum(1 for c in text if '一' <= c <= '鿿' or '　' <= c <= '〿')
    ascii_count = len(text) - cjk_count
    return int(cjk_count * _CJK_TOKEN_RATIO + ascii_count * _ASCII_TOKEN_RATIO)


def _generate_node_id(content: str) -> str:
    """Generate a unique summary node ID."""
    digest = hashlib.sha256((content + str(time.time())).encode()).hexdigest()[:16]
    return f"sum_{digest}"


def _detect_excel_docs(kb_id: str) -> list[str]:
    """Detect Excel/spreadsheet documents in a KB by checking for excel_analysis.json files."""
    try:
        from pathlib import Path
        from app.config import settings
        docs_dir = settings.KB_DIR / kb_id / "documents"
        if not docs_dir.exists():
            return []
        excel_docs = []
        for doc_dir in docs_dir.iterdir():
            if (doc_dir / "excel_analysis.json").exists():
                excel_docs.append(doc_dir.name)
        return excel_docs
    except Exception:
        return []


class ContextManager:
    """Manages conversation context to prevent window overflow using DAG-based compression."""

    def __init__(self, model_context_window: int = 128_000):
        self._model_context_window = model_context_window
        self._entries: list[ToolResultEntry] = []
        self._summary_dag: dict[str, SummaryNode] = {}
        self._consecutive_compact_failures = 0
        self._compact_count = 0

    @property
    def _microcompact_threshold(self) -> int:
        return int(self._model_context_window * _MICROCOMPACT_RATIO)

    @property
    def _autocompact_threshold(self) -> int:
        return int(self._model_context_window * _AUTOCOMPACT_RATIO)

    @property
    def _leaf_compact_threshold(self) -> int:
        return int(self._model_context_window * _LEAF_COMPACT_RATIO)

    def get_summary_node(self, node_id: str) -> Optional[SummaryNode]:
        """Retrieve a summary node by ID (for recall tools)."""
        return self._summary_dag.get(node_id)

    def search_dag(self, pattern: str) -> list[tuple[str, str]]:
        """Search all summary nodes for a pattern. Returns [(node_id, matching_content)]."""
        results = []
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        for node_id, node in self._summary_dag.items():
            if regex.search(node.content) or regex.search(node.source_text_preview):
                results.append((node_id, node.content[:500]))
        return results

    def expand_node(self, node_id: str, depth: int = 1) -> list[dict]:
        """Expand a summary node, returning its children's content."""
        node = self._summary_dag.get(node_id)
        if not node:
            return []

        results = [{"node_id": node_id, "content": node.content, "depth": node.depth}]

        if depth > 0:
            for child_id in node.children_ids:
                child_results = self.expand_node(child_id, depth - 1)
                results.extend(child_results)

        return results

    def classify_result(
        self,
        tool_name: str,
        query: str,
        result_text: str,
    ) -> ToolResultEntry:
        """Classify a tool result into critical/normal/transient.

        Applies tool result budgeting: oversized results are truncated.
        """
        # Apply tool result budget before classification
        result_text = self._budget_tool_result(tool_name, result_text)

        entry = ToolResultEntry(
            tool_name=tool_name,
            query=query,
            result_text=result_text,
        )

        stripped = result_text.strip()
        if not stripped or stripped == "[]" or stripped == "{}":
            entry.importance = "transient"
            return entry

        try:
            data = json.loads(result_text)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        entry.entities_found.update(_extract_json_entities(item))
                        entry.relations_found.update(_extract_json_relations(item))
                        entry.docs_referenced.update(_extract_json_docs(item))
            elif isinstance(data, dict):
                entry.entities_found.update(_extract_json_entities(data))
                entry.relations_found.update(_extract_json_relations(data))
                entry.docs_referenced.update(_extract_json_docs(data))
        except (json.JSONDecodeError, ValueError):
            entry.entities_found.update(extract_entities(result_text))

        has_findings = bool(
            entry.entities_found or entry.relations_found or entry.docs_referenced
        )
        if has_findings:
            entry.importance = "critical"
        elif len(result_text) > 100:
            entry.importance = "normal"
        else:
            entry.importance = "transient"

        preview = result_text[:150].replace("\n", " ")
        if entry.importance == "critical":
            entry.summary = (
                f"{tool_name} 查询了 '{query[:50]}，"
                f"发现 {len(entry.entities_found)} 个实体, "
                f"{len(entry.relations_found)} 个关系"
            )
        else:
            entry.summary = (
                f"[已压缩] {tool_name} 查询了 '{query[:50]}，"
                f"返回 {len(result_text)} 字符"
            )

        return entry

    def record_entry(self, entry: ToolResultEntry) -> None:
        """Store a classified entry. Skip transient ones."""
        if entry.importance != "transient":
            self._entries.append(entry)

    def _budget_tool_result(self, tool_name: str, result_text: str) -> str:
        """Truncate oversized tool results to stay within budget.

        L0/L1 structured results get a higher budget than L2 raw text.
        """
        if not result_text or len(result_text) <= MAX_TOOL_RESULT_CHARS:
            return result_text

        is_structured = tool_name in ("read_l0", "read_l1", "expand_entity", "get_timeline")
        limit = MAX_TOOL_RESULT_CHARS_STRUCTURED if is_structured else MAX_TOOL_RESULT_CHARS

        if len(result_text) <= limit:
            return result_text

        head = result_text[:int(limit * 0.7)]
        tail = result_text[-int(limit * 0.2):]
        truncated_count = len(result_text) - len(head) - len(tail)
        return f"{head}\n\n[... 已截断 {truncated_count} 字符 ...]\n\n{tail}"

    def snip(self, messages: list[dict]) -> list[dict]:
        """Remove stale markers, empty results, and duplicate system messages.

        Layer 0 of the context management pipeline. Runs before compaction.
        """
        cleaned = []
        seen_system_content = set()

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Deduplicate system messages
            if role == "system":
                if content in seen_system_content:
                    continue
                seen_system_content.add(content)

            # Skip empty tool results
            if role == "tool" and isinstance(content, str):
                stripped = content.strip()
                if not stripped or stripped in ("[]", "{}", "null", "None"):
                    continue

            cleaned.append(msg)

        removed = len(messages) - len(cleaned)
        if removed > 0:
            logger.debug("Snip removed %d stale messages", removed)

        return cleaned

    def estimate_total_tokens(self, messages: list[dict]) -> int:
        """Estimate total tokens in messages list."""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += _estimate_tokens_cjk(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        total += _estimate_tokens_cjk(text)
        return total

    def estimate_tool_result_tokens(self, messages: list[dict]) -> int:
        """Estimate tokens from tool-result messages only."""
        total = 0
        for msg in messages:
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                if isinstance(content, str):
                    total += _estimate_tokens_cjk(content)
        return total

    def should_microcompact(self, messages: list[dict]) -> bool:
        return self.estimate_tool_result_tokens(messages) > self._microcompact_threshold

    def should_auto_compact(self, messages: list[dict]) -> bool:
        total = self.estimate_total_tokens(messages)
        return total > self._autocompact_threshold

    def should_reactive_compact(self, messages: list[dict]) -> bool:
        """Proactive check: tokens > 90% of context window (before error occurs)."""
        total = self.estimate_total_tokens(messages)
        return total > int(self._model_context_window * 0.90)

    def should_leaf_compact(self, messages: list[dict]) -> bool:
        total = self.estimate_total_tokens(messages)
        return total > self._leaf_compact_threshold

    def microcompact(self, messages: list[dict]) -> list[dict]:
        """Compress consumed tool results to summaries with DAG tracking.

        Preserves:
        - All critical results (never compress)
        - Results from the most recent N tool-result blocks (fresh tail)
        Replaces older normal results with their summaries, creating DAG leaf nodes.
        """
        tool_indices = _find_tool_result_indices(messages)
        if not tool_indices:
            return messages

        iteration_boundaries = _find_iteration_boundaries(messages)
        fresh_start = (
            iteration_boundaries[-_FRESH_TAIL_BLOCKS]
            if len(iteration_boundaries) >= _FRESH_TAIL_BLOCKS
            else 0
        )

        new_messages = list(messages)
        compressed_count = 0

        for msg_idx in tool_indices:
            if msg_idx < fresh_start:
                msg = messages[msg_idx]
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 300:
                    entry = self._find_matching_entry(msg)
                    if entry and entry.importance == "normal" and not entry.consumed:
                        entry.consumed = True

                        # Create DAG leaf node
                        node_id = _generate_node_id(content)
                        node = SummaryNode(
                            node_id=node_id,
                            depth=0,
                            content=entry.summary,
                            source_text_preview=content[:500],
                            token_count=_estimate_tokens_cjk(content),
                        )
                        self._summary_dag[node_id] = node

                        new_messages[msg_idx] = {
                            "role": "tool",
                            "tool_call_id": msg.get("tool_call_id", ""),
                            "content": f"[压缩:{node_id}] {entry.summary}",
                        }
                        compressed_count += 1

        if compressed_count > 0:
            self._compact_count += 1
        return new_messages

    async def auto_compact(
        self,
        messages: list[dict],
        llm_client,
    ) -> list[dict]:
        """Layered context compression: snip → microcompact → leaf_compact → full_compact.

        Uses three-level escalation within each LLM step: normal → aggressive → fallback.
        Includes circuit breaker after _MAX_COMPACT_FAILURES consecutive failures.
        """
        if self._consecutive_compact_failures >= _MAX_COMPACT_FAILURES:
            logger.warning("Circuit breaker: skipping compact after %d failures", _MAX_COMPACT_FAILURES)
            return messages

        try:
            # Layer 0: Snip — remove stale markers and empty results
            messages = self.snip(messages)
            if self.estimate_total_tokens(messages) < self._autocompact_threshold:
                return messages

            # Layer 1: Microcompact — compress consumed normal results to DAG leaves
            messages = self.microcompact(messages)
            if self.estimate_total_tokens(messages) < self._autocompact_threshold:
                return messages

            # Layer 2: Leaf compaction — LLM summary of consumed entries
            if self._has_consumed_entries():
                messages = await self._leaf_compact(messages, llm_client)
                if self.estimate_total_tokens(messages) < self._autocompact_threshold:
                    return messages

            # Layer 3: Full auto-compact with LLM summary
            messages = await self._full_compact(messages, llm_client)

            self._consecutive_compact_failures = 0
            self._compact_count += 1
            return messages

        except Exception as e:
            logger.warning("自动压缩失败: %s", e)
            self._consecutive_compact_failures += 1
            return messages

    async def reactive_compact(
        self,
        messages: list[dict],
        llm_client,
    ) -> list[dict]:
        """Emergency compaction triggered by context overflow errors.

        More aggressive than auto_compact: skips snip/microcompact,
        goes straight to full_compact with shorter limits.
        """
        if self._consecutive_compact_failures >= _MAX_COMPACT_FAILURES:
            return messages

        try:
            # Strip oversized content first
            messages = self.snip(messages)
            messages = self.microcompact(messages)

            # Force full compact with aggressive settings
            messages = await self._full_compact(messages, llm_client)
            self._consecutive_compact_failures = 0
            return messages
        except Exception as e:
            logger.warning("Reactive compact failed: %s", e)
            self._consecutive_compact_failures += 1
            return messages

    def emergency_compact(self, messages: list[dict], keep_last_n: int = 6) -> list[dict]:
        """Zero-API-cost emergency compaction: strip all old tool results.

        Keeps: system prompt + last N messages (typically 3 turns).
        Replaces all tool results with compact placeholders.
        No LLM call needed — pure string manipulation.
        """
        new_messages = []
        preserved_entities: set[str] = set()
        preserved_docs: set[str] = set()
        tool_count = 0

        # First pass: extract key entities and docs from all entries
        for entry in self._entries:
            preserved_entities.update(entry.entities_found)
            preserved_docs.update(entry.docs_referenced)

        # Collect entity summary (D2-level: coarse, ~100 tokens)
        entity_names = ", ".join(sorted(preserved_entities)[:30])
        doc_names = ", ".join(sorted(preserved_docs)[:15])

        compact_summary = "[系统紧急压缩]"
        if entity_names:
            compact_summary += f"\n已发现实体: {entity_names}"
        if doc_names:
            compact_summary += f"\n已读取文档: {doc_names}"

        # Second pass: build compressed message list
        system_msg = None
        user_msg = None
        for msg in messages:
            role = msg.get("role", "")
            if role == "system" and system_msg is None:
                system_msg = msg
            elif role == "user" and user_msg is None:
                user_msg = msg

        # Rebuild: system + user + compact summary + last N messages
        if system_msg:
            new_messages.append(system_msg)
        if user_msg:
            new_messages.append(user_msg)

        new_messages.append({
            "role": "assistant",
            "content": compact_summary,
        })

        # Keep last N messages (recent turns)
        tail = messages[-keep_last_n:] if len(messages) > keep_last_n else messages
        # Filter out system/user messages we already added
        seen_content = {json.dumps(m, sort_keys=True, ensure_ascii=False) for m in new_messages}
        for msg in tail:
            msg_key = json.dumps(msg, sort_keys=True, ensure_ascii=False)
            if msg_key not in seen_content:
                new_messages.append(msg)
                seen_content.add(msg_key)

        # Count how many tool results were stripped
        stripped = sum(1 for m in messages if m.get("role") == "tool") - \
                   sum(1 for m in new_messages if m.get("role") == "tool")
        if stripped > 0:
            logger.info("Emergency compact stripped %d tool results", stripped)

        return new_messages

    def sm_compact(
        self,
        messages: list[dict],
        session_notes: list[dict],
        keep_last_n: int = 10,
    ) -> list[dict]:
        """Session-Memory compact: replace old messages with accumulated notes.

        Zero-API-cost: uses already-extracted session notes to replace early
        conversation messages. Keeps system prompt + session notes block +
        last N messages intact.

        Inspired by Claude Code's SM-compact in compact.ts.
        """
        if not session_notes:
            return messages

        # Format notes as system context
        from app.services.agent.memory import format_session_notes
        notes_text = format_session_notes(session_notes)
        notes_block = {
            "role": "system",
            "content": f"[会话摘要] 以下是从之前对话中提取的关键发现:\n\n{notes_text}\n\n请利用这些已有发现，避免重复搜索。"
        }

        # Keep system prompt(s) + notes + last N messages
        new_messages = []
        system_msgs = [m for m in messages if m.get("role") == "system"]

        if keep_last_n >= len(messages):
            return messages

        # Keep all system messages at the front
        new_messages.extend(system_msgs)

        # Add notes block after system messages
        new_messages.append(notes_block)

        # Keep last N non-system messages
        non_system = [m for m in messages if m.get("role") != "system"]
        new_messages.extend(non_system[-keep_last_n:])

        stripped = len(messages) - len(new_messages)
        logger.info("SM compact: reduced %d → %d messages (removed %d)",
                     len(messages), len(new_messages), stripped)

        return new_messages

    async def _leaf_compact(
        self, messages: list[dict], llm_client
    ) -> list[dict]:
        """Summarize consumed tool results via LLM into DAG leaf nodes."""
        consumed_entries = [e for e in self._entries if e.consumed and e.importance == "normal"]
        if not consumed_entries:
            return messages

        # Build content to summarize — up to 15000 chars (much more than old 5000 limit)
        parts = []
        total_chars = 0
        for entry in consumed_entries[:20]:
            snippet = f"[{entry.tool_name}] {entry.result_text[:800]}"
            parts.append(snippet)
            total_chars += len(snippet)
            if total_chars > 15000:
                break

        content_to_summarize = "\n---\n".join(parts)

        summary_prompt = (
            "你是知识库分析助手。请将以下工具搜索结果压缩为结构化摘要。\n"
            "保留所有实体名称、关系描述、文档ID和关键时间点。\n"
            "用中文输出，200字以内。\n\n"
            f"搜索结果：\n{content_to_summarize}"
        )

        summary = await self._summarize_with_escalation(
            llm_client, content_to_summarize, summary_prompt
        )

        if not summary:
            return messages

        # Create condensed DAG node
        node_id = _generate_node_id(summary)
        node = SummaryNode(
            node_id=node_id,
            depth=1,
            content=summary,
            source_text_preview=content_to_summarize[:500],
            token_count=_estimate_tokens_cjk(content_to_summarize),
        )
        self._summary_dag[node_id] = node

        # Replace the corresponding messages with summary references
        return _inject_compact_summary(messages, summary, node_id)

    async def _full_compact(
        self, messages: list[dict], llm_client
    ) -> list[dict]:
        """Full auto-compact with hierarchical D2/D1 summary."""
        content_to_summarize = _extract_compressable_content(messages)
        if not content_to_summarize.strip():
            return messages

        # D1-level: 9-section structured summary (~300 tokens)
        d1_prompt = (
            "你是知识库分析助手。请将以下对话历史压缩为结构化摘要，包含以下9个部分：\n"
            "1. 主请求（用户的核心问题/目标）\n"
            "2. 关键概念（讨论中的重要概念和术语）\n"
            "3. 已发现实体（找到的人物、地点、事件等）\n"
            "4. 已发现关系（实体之间的关系）\n"
            "5. 已检查文档（搜索和阅读过的文档列表）\n"
            "6. 错误和问题（遇到的错误或困难）\n"
            "7. 问题解决进展（已解决和未解决的方面）\n"
            "8. 当前工作状态（正在进行的搜索或分析）\n"
            "9. 下一步建议（建议的后续搜索方向）\n"
            "直接输出markdown格式的摘要，不要使用工具，300字以内。\n\n"
            f"搜索历史：\n{content_to_summarize[:15000]}"
        )

        d1_summary = await self._summarize_with_escalation(
            llm_client, content_to_summarize, d1_prompt
        )

        # D2-level: coarse summary (~100 tokens) — extract just entity names
        d2_summary = _extract_coarse_summary(content_to_summarize, self._entries)

        # Use D1 if available, fallback to D2
        summary = d1_summary or d2_summary
        if not summary:
            return messages

        node_id = _generate_node_id(summary)
        node = SummaryNode(
            node_id=node_id,
            depth=2,
            content=summary,
            source_text_preview=content_to_summarize[:500],
            token_count=_estimate_tokens_cjk(content_to_summarize),
        )
        self._summary_dag[node_id] = node

        return _build_post_compact_messages(messages, summary, node_id)

    async def _summarize_with_escalation(
        self, llm_client, source_text: str, prompt: str
    ) -> Optional[str]:
        """Four-level escalation: normal → PTL retry → aggressive → fallback.

        Level 1.5: If the summarization request itself hits prompt-too-long,
        truncate source to 50% and retry (up to 3 times). Inspired by
        Claude Code compact.ts PTL retry pattern.
        """
        # Level 1: Normal
        try:
            response = await llm_client.chat(
                role=RoleType.LIGHTWEIGHT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            summary = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if summary and _estimate_tokens_cjk(summary) < _estimate_tokens_cjk(source_text):
                return summary
        except Exception:
            pass

        # Level 1.5: PTL retry — truncate source and retry (up to 3 times)
        truncated = source_text
        for ptl_attempt in range(3):
            try:
                short_prompt = prompt.replace(
                    source_text[:len(truncated)] if len(truncated) < len(source_text) else source_text[:len(truncated)],
                    truncated[:len(truncated)]
                ) if len(truncated) < len(source_text) else prompt.replace(source_text, truncated)
                response = await llm_client.chat(
                    role=RoleType.LIGHTWEIGHT,
                    messages=[{"role": "user", "content": short_prompt}],
                    temperature=0.3,
                )
                summary = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                if summary and _estimate_tokens_cjk(summary) < _estimate_tokens_cjk(source_text):
                    return summary
            except Exception:
                pass
            truncated = truncated[:len(truncated) // 2]
            if len(truncated) < 500:
                break

        # Level 2: Aggressive — shorter prompt, explicit instruction
        try:
            aggressive_prompt = (
                "请用100字以内概括以下内容，只保留实体名称和关键关系：\n"
                f"{source_text[:8000]}"
            )
            response = await llm_client.chat(
                role=RoleType.LIGHTWEIGHT,
                messages=[{"role": "user", "content": aggressive_prompt}],
                temperature=0.1,
            )
            summary = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if summary:
                return summary
        except Exception:
            pass

        # Level 3: Fallback — deterministic truncation
        return source_text[:_FALLBACK_MAX_CHARS] + f"\n[截断自 {_estimate_tokens_cjk(source_text)} tokens]"

    def _has_consumed_entries(self) -> bool:
        return any(e.consumed and e.importance == "normal" for e in self._entries)

    def _find_matching_entry(self, msg: dict) -> Optional[ToolResultEntry]:
        """Find the ContextManager entry matching a tool result message."""
        content = msg.get("content", "")
        # Strip DAG reference prefix for matching
        clean_content = re.sub(r'^\[压缩:sum_[a-f0-9]+\]\s*', '', content)
        for entry in reversed(self._entries):
            if not entry.consumed and (
                entry.result_text == clean_content or entry.result_text == content
            ):
                return entry
        for entry in reversed(self._entries):
            if not entry.consumed:
                return entry
        return None

    def cache_edit(self, messages: list[dict], max_tool_result_chars: int = 2000) -> list[dict]:
        """Truncate old tool results in-place without changing message count.

        Preserves the message array structure (role, tool_call_id, etc.) so
        the API's prompt cache stays valid. Only shortens tool content strings.
        The most recent 6 tool results are left untouched.
        """
        tool_indices = _find_tool_result_indices(messages)
        if len(tool_indices) <= 6:
            return messages

        old_indices = tool_indices[:-6]  # Protect the newest 6
        new_messages = list(messages)
        edited = 0

        for idx in old_indices:
            msg = new_messages[idx]
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > max_tool_result_chars:
                truncated = content[:max_tool_result_chars]
                new_messages[idx] = {
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id", ""),
                    "content": truncated + "\n[cache_edit截断]",
                }
                edited += 1

        if edited:
            logger.debug("Cache edit truncated %d old tool results", edited)
        return new_messages

    def sm_compact(self, messages: list[dict], session_notes: list[dict]) -> list[dict]:
        """Session Memory compression — replace old messages with notes summary.

        Zero API cost. Keeps: system prompt + session notes block + last 4 turns.
        Replaces: everything in between with compact notes summary.
        """
        if not session_notes:
            return messages

        notes_text = "## 会话积累的关键发现\n\n"
        for note in session_notes:
            note_type = note.get("type", "info")
            content = note.get("content", "")
            if content:
                notes_text += f"- [{note_type}] {content}\n"

        result = []
        # Keep first system message
        if messages and messages[0].get("role") == "system":
            result.append(messages[0])

        # Insert session notes block
        result.append({"role": "system", "content": notes_text})

        # Keep last 8 messages (4 turns: user+assistant pairs)
        tail = messages[-8:] if len(messages) > 8 else messages[1:]
        result.extend(tail)

        return result

    def inject_kb_context(self, messages: list[dict], kb_id: str, kb_state) -> list[dict]:
        """Inject KB state-aware context based on compilation status.

        - Compiled KB: inject L0 summary (max 30% of context window)
        - Partially compiled: inject available summaries + raw_search hint
        - Uncompiled: inject degradation hint + document list
        """
        if not kb_id:
            return messages

        context_block = ""

        if kb_state:
            has_l0 = getattr(kb_state, "has_entities", False)
            has_l1 = getattr(kb_state, "has_l1_summaries", False)
            has_l2 = getattr(kb_state, "has_l2_chunks", False)

            if has_l0 and has_l1 and has_l2:
                # Fully compiled — inject L0 summary
                try:
                    from app.config import settings
                    import json
                    entities_path = settings.KB_DIR / kb_id / "l0" / "entities.json"
                    if entities_path.exists():
                        with open(entities_path, "r", encoding="utf-8") as f:
                            entities = json.load(f)
                        entity_names = [e.get("name", "") for e in entities[:30] if e.get("name")]
                        if entity_names:
                            max_chars = int(self._model_context_window * 0.3)
                            context_block = (
                                f"知识库已完整编译。已知实体（前30个）: {', '.join(entity_names)}\n"
                                "可使用 search_keyword, read_l0/l1/l2, expand_entity 等工具高效检索。"
                            )

                    # Detect Excel/table documents and add search_excel guidance
                    excel_docs = _detect_excel_docs(kb_id)
                    if excel_docs:
                        context_block += (
                            f"\n⚠️ 重要：知识库包含 {len(excel_docs)} 个 Excel/表格文档: {', '.join(excel_docs[:5])}。"
                            "\n遇到表格相关的统计、排名、筛选、分组问题时，必须优先使用 search_excel 工具！"
                            "\nsearch_excel 能：查看列结构、按列匹配数据、执行 GROUP BY 聚合统计。"
                            "\n直接用 search_keyword 文本搜索表格数据是无效的（只能搜到片段表头，无法统计）。"
                        )

                    if len(context_block) > max_chars:
                        context_block = context_block[:max_chars] + "..."
                except Exception:
                    pass
            elif has_l2:
                context_block = (
                    "知识库已部分编译（有L2索引但缺少摘要）。\n"
                    "可使用 search_keyword 搜索，用 raw_search 作为补充。"
                )
                excel_docs = _detect_excel_docs(kb_id)
                if excel_docs:
                    context_block += (
                        f"\n⚠️ 包含 {len(excel_docs)} 个表格文档: {', '.join(excel_docs[:5])}。"
                        "\n表格查询必须使用 search_excel 工具，不要用 search_keyword！"
                    )
            else:
                context_block = (
                    "知识库尚未编译，无预建索引。\n"
                    "请使用 raw_search 或 doc_grep 直接搜索文档原文。"
                    "也可以用 wiki_browse list 查看可用文档列表。"
                )

        if context_block:
            # Find or create KB context message
            kb_msg_found = False
            for i, msg in enumerate(messages):
                if msg.get("role") == "system" and "知识库" in msg.get("content", ""):
                    messages[i] = {"role": "system", "content": context_block}
                    kb_msg_found = True
                    break
            if not kb_msg_found:
                # Insert after first system message
                messages.insert(1, {"role": "system", "content": context_block})

        return messages

    def get_context_stats(self) -> dict:
        return {
            "total_entries": len(self._entries),
            "critical_count": sum(1 for e in self._entries if e.importance == "critical"),
            "normal_count": sum(1 for e in self._entries if e.importance == "normal"),
            "consumed_count": sum(1 for e in self._entries if e.consumed),
            "compact_count": self._compact_count,
            "dag_nodes": len(self._summary_dag),
        }


# ── Helper functions ──────────────────────────────────────────────

def _extract_json_entities(item: dict) -> set:
    entities = set()
    for key, value in item.items():
        if isinstance(value, str) and len(value) >= 2:
            if any(k in key.lower() for k in ["name", "entity", "person", "title"]):
                entities.add(value)
        elif isinstance(value, list):
            for v in value:
                if isinstance(v, str) and 2 <= len(v) <= 20:
                    entities.add(v)
    return entities


def _extract_json_relations(item: dict) -> set:
    relations = set()
    for key, value in item.items():
        if isinstance(value, str) and any(
            k in key.lower() for k in ["relation", "role", "type", "connection"]
        ):
            relations.add(value)
    return relations


def _extract_json_docs(item: dict) -> set:
    docs = set()
    for key, value in item.items():
        if isinstance(value, str) and any(
            k in key.lower() for k in ["doc_id", "document", "source"]
        ):
            docs.add(value)
    return docs


def _find_iteration_boundaries(messages: list[dict]) -> list[int]:
    boundaries = []
    in_tool_block = False
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        if role == "tool" and not in_tool_block:
            boundaries.append(i)
            in_tool_block = True
        elif role != "tool":
            in_tool_block = False
    return boundaries


def _find_tool_result_indices(messages: list[dict]) -> list[int]:
    return [i for i, msg in enumerate(messages) if msg.get("role") == "tool"]


def _extract_compressable_content(messages: list[dict]) -> str:
    """Extract tool results and assistant content for summarization."""
    parts = []
    for msg in messages:
        role = msg.get("role", "")
        if role == "tool":
            content = msg.get("content", "")
            # Strip DAG reference prefix
            clean = re.sub(r'^\[压缩:sum_[a-f0-9]+\]\s*', '', content)
            if isinstance(clean, str) and len(clean) > 50:
                parts.append(f"[搜索结果] {clean[:500]}")
        elif role == "assistant" and msg.get("content"):
            content = msg["content"]
            if len(content) > 100 and not content.startswith("[上下文已压缩]"):
                parts.append(f"[分析] {content[:300]}")
    return "\n".join(parts)


def _inject_compact_summary(
    messages: list[dict], summary: str, node_id: str
) -> list[dict]:
    """Replace consumed tool results with a single summary message."""
    new_messages = []
    summary_inserted = False

    for msg in messages:
        if msg.get("role") == "tool":
            content = msg.get("content", "")
            # Skip messages that are already compressed
            if content.startswith("[压缩:") or content.startswith("[上下文已压缩]"):
                if not summary_inserted:
                    new_messages.append({
                        "role": "assistant",
                        "content": f"[上下文已压缩:{node_id}] 之前的搜索发现：\n{summary}",
                    })
                    summary_inserted = True
                continue
        new_messages.append(msg)

    if not summary_inserted:
        # No compressed messages found, inject before the last few messages
        keep_count = min(5, len(new_messages))
        prefix = new_messages[:-keep_count] if keep_count < len(new_messages) else []
        suffix = new_messages[-keep_count:] if keep_count < len(new_messages) else []
        prefix.append({
            "role": "assistant",
            "content": f"[上下文已压缩:{node_id}] 之前的搜索发现：\n{summary}",
        })
        new_messages = prefix + suffix

    return new_messages


def _build_post_compact_messages(
    messages: list[dict],
    summary: str,
    node_id: str,
) -> list[dict]:
    """Build messages after full auto-compact."""
    system_msg = next((m for m in messages if m.get("role") == "system"), None)
    user_msg = next((m for m in messages if m.get("role") == "user"), None)

    new_messages = []
    if system_msg:
        new_messages.append(system_msg)
    if user_msg:
        new_messages.append(user_msg)

    new_messages.append({
        "role": "assistant",
        "content": f"[上下文已压缩:{node_id}] 之前的搜索发现：\n{summary}",
    })

    keep_count = min(5, len(messages))
    new_messages.extend(messages[-keep_count:])

    return new_messages


def _extract_coarse_summary(content: str, entries: list[ToolResultEntry]) -> str:
    """D2-level coarse summary: extract entity names, doc IDs, tool usage stats.

    Zero LLM call — pure string extraction, ~100 tokens.
    """
    all_entities: set[str] = set()
    all_docs: set[str] = set()
    tool_counts: dict[str, int] = {}

    for entry in entries:
        all_entities.update(entry.entities_found)
        all_docs.update(entry.docs_referenced)
        tool_counts[entry.tool_name] = tool_counts.get(entry.tool_name, 0) + 1

    parts = ["[搜索摘要]"]
    if all_entities:
        parts.append(f"实体: {', '.join(sorted(all_entities)[:25])}")
    if all_docs:
        parts.append(f"文档: {', '.join(sorted(all_docs)[:15])}")
    if tool_counts:
        tool_str = ", ".join(f"{k}×{v}" for k, v in sorted(tool_counts.items()))
        parts.append(f"搜索: {tool_str}")

    return "\n".join(parts)
