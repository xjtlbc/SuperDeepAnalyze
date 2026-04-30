"""KB-level persistent memory that survives across sessions.

Stores key findings, entity summaries, and search patterns so the Agent
can leverage prior knowledge instead of searching from scratch.
"""

import json
import uuid
from datetime import datetime, timezone

from app.models.database import get_connection
from app.utils.logging_config import get_logger

logger = get_logger("app.agent.memory")


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
