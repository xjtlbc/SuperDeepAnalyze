"""KB compilation state detection for graceful degradation.

Determines what compilation levels are available for a knowledge base
and provides guidance on which tools should be registered and how
the system prompt should be adjusted.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.models.database import get_connection

logger = logging.getLogger("app.agent")


@dataclass
class KBCompilationState:
    """Snapshot of what compilation data is available for a KB."""

    kb_id: str
    has_l2: bool = False          # chunks + FTS5 index
    has_l1: bool = False          # L1 summaries
    has_entities: bool = False    # entities + timeline
    has_wiki: bool = False        # Wiki pages
    doc_count: int = 0
    chunk_count: int = 0
    entity_count: int = 0

    @classmethod
    def check(cls, kb_id: str) -> "KBCompilationState":
        """Detect compilation state by checking filesystem and database."""
        state = cls(kb_id=kb_id)
        kb_dir = settings.KB_DIR / kb_id

        # Check document count and parse status
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM documents WHERE kb_id = ? AND parse_status = 'completed'",
                (kb_id,),
            ).fetchone()
            state.doc_count = row["cnt"] if row else 0

            # Check compile status
            row = conn.execute(
                "SELECT compile_status FROM knowledge_bases WHERE id = ?",
                (kb_id,),
            ).fetchone()
            compile_status = row["compile_status"] if row else None
        finally:
            conn.close()

        if state.doc_count == 0:
            return state

        # Check L2: any chunk files exist?
        docs_dir = kb_dir / "documents"
        if docs_dir.exists():
            for doc_dir in docs_dir.iterdir():
                if doc_dir.is_dir():
                    l2_dir = doc_dir / "l2_chunks"
                    if l2_dir.exists():
                        chunk_files = list(l2_dir.glob("*.md"))
                        if chunk_files:
                            state.has_l2 = True
                            state.chunk_count += len(chunk_files)
                    # Also check parsed.md
                    if (doc_dir / "parsed.md").exists() and not state.has_l2:
                        state.has_l2 = True  # Parsed content available even without explicit chunks

        # Check L1: any l1_summaries.json files?
        if docs_dir.exists():
            for doc_dir in docs_dir.iterdir():
                if doc_dir.is_dir() and (doc_dir / "l1_summaries.json").exists():
                    state.has_l1 = True
                    break

        # Check entities/timeline (L0 data)
        l0_dir = kb_dir / "l0"
        if l0_dir.exists():
            entities_file = l0_dir / "entities.json"
            timeline_file = l0_dir / "timeline.json"
            if entities_file.exists():
                import json
                try:
                    with open(entities_file) as f:
                        entities = json.load(f)
                    state.entity_count = len(entities)
                    if state.entity_count > 0:
                        state.has_entities = True
                except Exception:
                    pass
            if timeline_file.exists():
                state.has_entities = state.has_entities  # Already set above

        # Check wiki
        wiki_dir = kb_dir / "wiki"
        if wiki_dir.exists() and (wiki_dir / "catalog.json").exists():
            state.has_wiki = True

        logger.info(
            "KB state %s: docs=%d chunks=%d L2=%s L1=%s entities=%d wiki=%s",
            kb_id, state.doc_count, state.chunk_count,
            state.has_l2, state.has_l1, state.entity_count, state.has_wiki,
        )
        return state

    def get_available_tools(self) -> list[str]:
        """Return list of tool names that should be registered based on state."""
        tools = [
            "search_keyword",
            "assess_complexity",
            "report_findings",
            "batch_expand_abstracts",
            "recall_grep",
            "recall_expand",
            "recall_describe",
        ]

        if self.has_l2:
            tools.extend(["read_l2"])

        if self.has_l1:
            tools.extend(["read_l1", "progressive_search", "batch_expand_l1", "read_section"])

        if self.has_entities:
            tools.extend(["read_l0", "expand_entity", "get_timeline"])

        if self.has_l2 and self.has_l1:
            tools.extend(["search_vector"])

        return tools

    def get_system_prompt_mods(self) -> str:
        """Return prompt modifications based on compilation state."""
        if self.doc_count == 0:
            return (
                "\n\n[系统提示] 当前知识库中没有任何文档。"
                "请告知用户需要先上传文档，然后等待编译完成后才能进行分析。"
            )

        if not self.has_l2 and not self.has_l1:
            return (
                "\n\n[系统提示] 知识库文档已上传但尚未编译。"
                "请使用 search_keyword 工具搜索原始文档文本。"
                "搜索能力受限，建议用户触发编译以获得更好的分析体验。"
            )

        if self.has_l2 and not self.has_l1:
            return (
                "\n\n[系统提示] 知识库已完成L2索引（原始文本分块+关键词搜索）。"
                "可使用 search_keyword 和 read_l2 进行检索。"
                "L1摘要尚未生成，建议用户触发编译以获得更高效的分析能力。"
            )

        if self.has_l1 and not self.has_entities:
            return (
                "\n\n[系统提示] 知识库已完成L2+L1编译（含摘要）。"
                "可使用 search_keyword、search_vector、read_l1、read_l2 进行多级检索。"
                "全局实体图谱尚未生成，实体分析功能暂不可用。"
            )

        # Fully compiled
        return ""

    @property
    def is_fully_compiled(self) -> bool:
        return self.has_l2 and self.has_l1 and self.has_entities
