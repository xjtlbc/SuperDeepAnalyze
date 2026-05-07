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
            "assess_complexity",
            "report_findings",
            "batch_expand_abstracts",
            "recall_grep",
            "recall_expand",
            "recall_describe",
        ]

        # Raw document tools always available (no pre-indexing needed)
        tools.extend(["grep_docs", "read_doc", "list_docs", "doc_grep", "raw_search", "expand"])

        # FTS5 search only useful when L2 chunks exist
        if self.has_l2:
            tools.append("search_keyword")
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
                f"\n\n[重要: 无预编译搜索模式] 该知识库有 {self.doc_count} 个文档，已上传但未预编译。"
                "你拥有完整的原始文档搜索能力，请按以下策略工作：\n"
                "1. 先用 list_docs 了解知识库中有哪些文档\n"
                "2. 用 grep_docs 搜索关键词(人名、地名、案件要素等)，先以 files_with_matches 模式查看分布\n"
                "3. 用 read_doc 读取相关文档的关键段落（grep会返回行号）\n"
                "4. 对于复杂问题，自动将问题分解为2-3个子问题，分别用grep搜索不同关键词\n"
                "5. 综合所有发现回答用户，标注信息来源于哪个文档\n"
                "禁止说'无法搜索'或'需要先编译'，你拥有grep_docs+read_doc+list_docs三个工具可以完成搜索。"
            )

        if self.has_l2 and not self.has_l1:
            return (
                f"\n\n[重要] 知识库有 {self.doc_count} 个文档，L2分块已完成但无L1摘要。"
                "推荐优先使用以下工具搜索原始文档（更可靠）：\n"
                "1. grep_docs — 全文正则搜索，直接在原始文档中查找关键词\n"
                "2. read_doc — 按行号读取文档内容\n"
                "3. list_docs — 浏览文档列表\n"
                "提示：grep_docs扫描所有parsed.md原文，比search_keyword(仅FTS5索引)覆盖更全面。"
                "遇到搜索无结果时，请尝试grep_docs用不同关键词重试。"
            )

        if self.has_l1 and not self.has_entities:
            return (
                "\n\n[系统提示] 知识库已完成L2+L1编译（含摘要）。"
                "可使用 grep_docs(原文搜索)、search_keyword、read_l1、read_l2 进行多级检索。"
                "全局实体图谱尚未生成，实体分析功能暂不可用。"
                "提示：grep_docs直接搜索原文，是关键词搜索最可靠的工具。"
            )

        # Fully compiled
        return ""

    @property
    def is_fully_compiled(self) -> bool:
        return self.has_l2 and self.has_l1 and self.has_entities
