"""KB-level persistent memory that survives across sessions.

Stores key findings, entity summaries, and search patterns so the Agent
can leverage prior knowledge instead of searching from scratch.

Also provides session-level memory extraction via LLM, producing structured
notes that can be injected into the next turn's system prompt.
"""

import json
import uuid
from datetime import datetime, timezone

from app.models.database import get_connection
from app.models.config import RoleType
from app.utils.logging_config import get_logger

logger = get_logger("app.agent.memory")

_SESSION_NOTES_MAX_TOKENS = 400  # Rough cap for injected notes


async def extract_session_notes(
    messages: list[dict],
    llm_client,
    max_notes: int = 8,
) -> list[dict]:
    """Extract structured session notes from conversation history via LLM.

    Returns a list of {topic, summary, entities} dicts suitable for
    injection into the next turn's system prompt.
    """
    # Collect recent assistant and tool content for summarization
    parts = []
    for msg in messages[-30:]:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "assistant" and isinstance(content, str) and len(content) > 50:
            parts.append(f"[分析] {content[:300]}")
        elif role == "tool" and isinstance(content, str) and len(content) > 30:
            parts.append(f"[搜索结果] {content[:200]}")

    if len(parts) < 3:
        return []

    source_text = "\n".join(parts[:20])

    prompt = (
        "请从以下分析对话中提取关键发现，以JSON数组格式返回。每条发现包含：\n"
        '- {"topic": "主题", "summary": "简述(30字以内)", "entities": ["相关实体"]}\n'
        f"最多{max_notes}条。只返回JSON数组，不要其他文字。\n\n"
        f"对话内容：\n{source_text[:12000]}"
    )

    try:
        response = await llm_client.chat(
            role=RoleType.LIGHTWEIGHT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        text = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Extract JSON from response (may be wrapped in ```json ... ```)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        notes = json.loads(text)
        if isinstance(notes, list):
            return [
                {
                    "topic": n.get("topic", ""),
                    "summary": n.get("summary", ""),
                    "entities": n.get("entities", []),
                }
                for n in notes[:max_notes]
                if isinstance(n, dict) and n.get("topic")
            ]
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.debug("Session note extraction parse error: %s", e)
    except Exception as e:
        logger.warning("Session note extraction failed: %s", e)

    return []


class AsyncSessionMemoryExtractor:
    """Non-blocking session memory extraction.

    Inspired by leohc/DeepAnalyze AsyncSessionMemoryExtractor.
    Extracts notes in a background task, making results available
    on the next extraction call without blocking the agent loop.
    """

    def __init__(self, min_token_increment: int = 15000):
        self._min_increment = min_token_increment
        self._last_extracted_tokens = 0
        self._is_extracting = False
        self._pending_notes: list[dict] = []

    def should_extract(self, current_tokens: int) -> bool:
        """Check if enough new tokens have accumulated to warrant extraction."""
        if self._is_extracting:
            return False
        increment = current_tokens - self._last_extracted_tokens
        return increment >= self._min_increment

    async def extract_background(self, messages: list[dict], llm_client) -> None:
        """Run extraction in the background, storing results for later retrieval."""
        if self._is_extracting:
            return
        self._is_extracting = True
        try:
            notes = await extract_session_notes(messages, llm_client)
            if notes:
                self._pending_notes = notes
            self._last_extracted_tokens = sum(
                len(m.get("content", "")) for m in messages
            )
        except Exception as e:
            logger.debug("Background session extraction failed: %s", e)
        finally:
            self._is_extracting = False

    def get_pending_notes(self) -> list[dict]:
        """Return and clear any pending notes from background extraction."""
        notes = self._pending_notes
        self._pending_notes = []
        return notes


def format_session_notes(notes: list[dict]) -> str:
    """Format extracted session notes into 5-section structured Markdown.

    Sections: 关键信息, 已完成工作, 当前任务, 决策与结论, 待办事项
    Inspired by leohc/DeepAnalyze session-memory.ts 5-section format.
    """
    if not notes:
        return ""

    key_info: list[str] = []
    work_done: list[str] = []
    current_task: list[str] = []
    decisions: list[str] = []
    pending: list[str] = []

    for n in notes:
        topic = n.get("topic", "")
        summary = n.get("summary", "")
        entities = n.get("entities", [])[:5]
        importance = n.get("importance", "")

        marker = "[关键]" if importance == "critical" else "[重要]"
        entities_str = ", ".join(entities) if entities else ""
        line = f"- {marker} {topic}: {summary}"
        if entities_str:
            line += f" (相关: {entities_str})"

        # Categorize into sections based on topic/type
        note_type = n.get("type", "finding")
        if note_type == "finding" or note_type == "entity":
            key_info.append(line)
        elif note_type == "action" or note_type == "tool_call":
            work_done.append(line)
        elif note_type == "decision":
            decisions.append(line)
        elif note_type == "pending":
            pending.append(line)
        else:
            # Default: put in key_info for backward compat
            if importance == "critical":
                key_info.append(line)
            else:
                work_done.append(line)

    sections = []
    if key_info:
        sections.append("## 关键信息\n" + "\n".join(key_info))
    if work_done:
        sections.append("## 已完成工作\n" + "\n".join(work_done))
    if current_task:
        sections.append("## 当前任务\n" + "\n".join(current_task))
    if decisions:
        sections.append("## 决策与结论\n" + "\n".join(decisions))
    if pending:
        sections.append("## 待办事项\n" + "\n".join(pending))

    text = "<!-- SESSION_MEMORY_START -->\n" + "\n\n".join(sections) + "\n<!-- SESSION_MEMORY_END -->"
    return text


class KBMemory:
    """Persistent KB-level memory that survives across sessions."""

    def __init__(self, kb_id: str):
        self._kb_id = kb_id

    def save_turn(self, session_id: str, turn_summary: dict) -> None:
        """Extract and save key findings from a turn summary."""
        entities = turn_summary.get("entities_discovered", [])
        relations = turn_summary.get("relations_discovered", [])
        docs = turn_summary.get("docs_read", [])
        evidence = turn_summary.get("evidence_map", {})

        if not entities and not evidence:
            return

        conn = get_connection()
        try:
            # Save entity knowledge
            if entities:
                entity_content = f"实体发现: {', '.join(entities[:30])}"
                self._upsert_memory(
                    conn, "entity_summary", entity_content, session_id,
                    min(1.0, len(entities) / 10.0),
                )

            # Save relation knowledge
            if relations:
                rel_content = f"关系发现: {', '.join(relations[:20])}"
                self._upsert_memory(
                    conn, "relation_summary", rel_content, session_id,
                    min(1.0, len(relations) / 10.0),
                )

            # Save key finding (from evidence)
            if evidence:
                finding_parts = []
                for doc_id, refs in list(evidence.items())[:5]:
                    for r in refs[:2]:
                        finding_parts.append(f"{doc_id}/chunk={r.get('chunk_id', '')} rel={r.get('relevance', 0):.0%}")
                if finding_parts:
                    self._upsert_memory(
                        conn, "key_finding",
                        "证据来源: " + "; ".join(finding_parts),
                        session_id, 0.8,
                    )

            conn.commit()
        finally:
            conn.close()

    def get_relevant(self, query: str, limit: int = 10) -> list[dict]:
        """Retrieve memories relevant to a query using CJK-aware matching.

        For Chinese text, splits into 2-char sliding windows since
        space-based tokenization is ineffective.
        """
        conn = get_connection()
        try:
            # CJK-aware tokenization: extract 2-char bigrams for Chinese
            query_chars = list(query)
            tokens = set()
            # Space-separated tokens (for English/mixed)
            for word in query.split():
                if len(word) >= 2:
                    tokens.add(word.lower())
            # CJK bigrams (for Chinese)
            for i in range(len(query_chars) - 1):
                bigram = query_chars[i] + query_chars[i + 1]
                if any('一' <= c <= '鿿' for c in bigram):
                    tokens.add(bigram)

            if not tokens:
                # Fallback: single CJK chars
                tokens = {c for c in query if '一' <= c <= '鿿'}

            results = []
            cursor = conn.execute(
                """SELECT id, memory_type, content, relevance_score, source_sessions
                   FROM kb_memory
                   WHERE kb_id = ?
                   ORDER BY relevance_score DESC, updated_at DESC
                   LIMIT ?""",
                (self._kb_id, limit * 3),
            )
            for row in cursor.fetchall():
                content = row["content"]
                content_lower = content.lower()
                overlap = sum(1 for tok in tokens if tok in content_lower)
                if overlap > 0:
                    results.append({
                        "id": row["id"],
                        "type": row["memory_type"],
                        "content": content,
                        "relevance": row["relevance_score"] * (1 + overlap * 0.2),
                    })
                elif len(results) < limit // 3:
                    results.append({
                        "id": row["id"],
                        "type": row["memory_type"],
                        "content": content,
                        "relevance": row["relevance_score"] * 0.3,
                    })
            results.sort(key=lambda x: x["relevance"], reverse=True)
            return results[:limit]
        finally:
            conn.close()

    def get_entity_summary(self, entity_name: str) -> str | None:
        """Get accumulated knowledge about an entity from previous sessions."""
        conn = get_connection()
        try:
            cursor = conn.execute(
                """SELECT content FROM kb_memory
                   WHERE kb_id = ? AND memory_type = 'entity_summary'
                   AND content LIKE ?
                   LIMIT 1""",
                (self._kb_id, f"%{entity_name}%"),
            )
            row = cursor.fetchone()
            return row["content"] if row else None
        finally:
            conn.close()

    def _upsert_memory(
        self, conn, memory_type: str, content: str, session_id: str, score: float,
    ) -> None:
        """Insert or update a memory entry."""
        # Check if similar memory already exists
        cursor = conn.execute(
            """SELECT id, source_sessions FROM kb_memory
               WHERE kb_id = ? AND memory_type = ? AND content = ?""",
            (self._kb_id, memory_type, content),
        )
        row = cursor.fetchone()
        if row:
            # Update: merge session IDs and bump relevance
            sessions = json.loads(row["source_sessions"])
            if session_id not in sessions:
                sessions.append(session_id)
            conn.execute(
                """UPDATE kb_memory
                   SET source_sessions = ?, relevance_score = MIN(1.0, ? + 0.1),
                       updated_at = ?
                   WHERE id = ?""",
                (json.dumps(sessions), score, datetime.now(timezone.utc).isoformat(), row["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO kb_memory (id, kb_id, memory_type, content, source_sessions, relevance_score)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (f"mem_{uuid.uuid4().hex[:12]}", self._kb_id, memory_type, content,
                 json.dumps([session_id]), score),
            )
