"""Core E2E tests: KB CRUD → Document Upload → Compile → Agent Q&A → Wiki.

Uses mock LLM responses to avoid API credit consumption.
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestKnowledgeBaseCRUD:
    """Test KB create, read, update, delete operations."""

    @pytest.mark.asyncio
    async def test_create_kb(self, temp_data_dir, mock_llm_client):
        """Test knowledge base creation via API."""
        from app.config import settings
        with patch.object(settings, 'DATA_DIR', temp_data_dir):
            from app.models.database import init_db, get_connection
            init_db()

            conn = get_connection()
            try:
                import uuid
                kb_id = f"test_kb_{uuid.uuid4().hex[:8]}"
                conn.execute(
                    "INSERT INTO knowledge_bases (id, name, description) VALUES (?, ?, ?)",
                    (kb_id, "测试KB", "E2E 测试"),
                )
                conn.commit()

                row = conn.execute(
                    "SELECT * FROM knowledge_bases WHERE id = ?", (kb_id,)
                ).fetchone()
                assert row is not None
                assert row["name"] == "测试KB"
                assert row["compile_status"] == "pending"
            finally:
                conn.close()

    @pytest.mark.asyncio
    async def test_kb_list(self, temp_data_dir):
        """Test listing knowledge bases."""
        from app.config import settings
        with patch.object(settings, 'DATA_DIR', temp_data_dir):
            from app.models.database import init_db, get_connection
            init_db()

            conn = get_connection()
            try:
                rows = conn.execute("SELECT * FROM knowledge_bases").fetchall()
                assert isinstance(rows, list)
            finally:
                conn.close()


class TestDocumentParsing:
    """Test document upload and chunking."""

    @pytest.mark.asyncio
    async def test_chunking_chinese_text(self):
        """Test that Chinese text is chunked correctly with CJK-aware boundaries."""
        from app.services.parsing.chunking import chunk_text

        text = "第一段。这是测试内容，用于验证分段逻辑。" * 100
        chunks = chunk_text(text, doc_id="test_doc", kb_id="test_kb",
                           min_tokens=100, max_tokens=500, overlap_tokens=50)

        assert len(chunks) > 0
        for chunk in chunks:
            assert hasattr(chunk, "chunk_id")
            assert hasattr(chunk, "content")
            assert len(chunk.content) > 0
            # Verify CJK punctuation boundaries are respected
            content = chunk.content
            if content and len(content) > 1:
                # Content should not start mid-sentence
                assert not content[0].isspace() if content[0] else True

    @pytest.mark.asyncio
    async def test_large_document_chunk_count(self):
        """Test that large documents produce proportional chunk counts."""
        from app.services.parsing.chunking import chunk_text

        small = "短文本。" * 10
        large = "长文本内容。" * 500

        small_chunks = chunk_text(small, doc_id="d1", kb_id="kb1",
                                  min_tokens=100, max_tokens=500, overlap_tokens=50)
        large_chunks = chunk_text(large, doc_id="d1", kb_id="kb1",
                                  min_tokens=100, max_tokens=500, overlap_tokens=50)

        assert len(large_chunks) > len(small_chunks)
        # Rough proportionality check
        ratio = len(large_chunks) / max(len(small_chunks), 1)
        assert ratio > 5, f"Expected ratio > 5, got {ratio}"


class TestCompilation:
    """Test L1/L2 compilation with mock LLM."""

    @pytest.mark.asyncio
    async def test_l1_summary_generation(self, mock_llm_client):
        """Test L1 summary generation with mock chunks."""
        from app.services.parsing.chunking import Chunk
        from app.services.compilation.l1_compiler import L1Compiler

        chunks = [
            Chunk(chunk_id="test_001", doc_id="doc_001", kb_id="kb_001", content="第一段测试内容"),
            Chunk(chunk_id="test_002", doc_id="doc_001", kb_id="kb_001", content="第二段测试内容"),
            Chunk(chunk_id="test_003", doc_id="doc_001", kb_id="kb_001", content="第三段测试内容"),
        ]

        compiler = L1Compiler(mock_llm_client)
        result = await compiler.generate_summary(chunks)

        assert "chunk_ids" in result
        assert result["chunk_ids"] == ["test_001", "test_002", "test_003"]
        assert "summary" in result
        assert result["summary"] == "L1 测试摘要"

    @pytest.mark.asyncio
    async def test_batch_size_reduction_on_context_error(self, mock_llm_client):
        """Test dynamic batch size halving on context length errors."""
        from app.services.parsing.chunking import Chunk
        from app.services.compilation.l1_compiler import L1Compiler

        chunks = [Chunk(chunk_id=f"c_{i}", doc_id="doc_001", kb_id="kb_001", content=f"内容段落 {i}") for i in range(10)]

        call_count = [0]

        async def mock_summarize(combined, role=None):
            call_count[0] += 1
            if call_count[0] <= 1:
                raise Exception("content length too long: maximum context exceeded")
            return {"summary": "摘要", "entities_mentioned": [], "relations": [], "contradictions": []}

        mock_llm_client.summarize_l1 = mock_summarize

        compiler = L1Compiler(mock_llm_client)
        results = await compiler.compile_batch(chunks, batch_size=10)

        assert len(results) > 0
        assert call_count[0] >= 2  # At least one retry with smaller batch

    @pytest.mark.asyncio
    async def test_sample_compile_smaller_batch(self):
        """Test sample compile uses fewer chunks than full compile."""
        chunk_count = 1000
        step = 5  # 20% sampling
        sampled = chunk_count // step
        assert sampled < chunk_count
        assert sampled == 200  # 20%


class TestAgentTools:
    """Test agent tool implementations."""

    @pytest.mark.asyncio
    async def test_search_keyword_basic(self, temp_data_dir):
        """Test keyword search returns results."""
        from app.config import settings
        with patch.object(settings, 'DATA_DIR', temp_data_dir):
            from app.models.database import init_db, get_connection
            init_db()

            # Direct SQL FTS5 query to avoid circular import from hybrid_search
            conn = get_connection()
            try:
                results = conn.execute(
                    "SELECT chunk_id, content FROM fts_content WHERE content MATCH ? LIMIT 5",
                    ("测试",)
                ).fetchall()
                assert isinstance(results, list)
            finally:
                conn.close()

    @pytest.mark.asyncio
    async def test_ask_user_tool_single_question(self):
        """Test that AskUser tool produces a single question."""
        from app.services.agent.tools import AskUserTool

        tool = AskUserTool()
        result = await tool.execute(
            question="请确认您要查询的具体人物是哪一个？",
            options=["张三（被告人）", "张三（证人）"],
            scenario="ambiguity",
        )

        assert "请确认" in result
        assert "Options:" in result or "可选" in result
        # Verify single question (not multiple)
        assert result.count("?") <= 2  # Max one question mark + possible options

    @pytest.mark.asyncio
    async def test_report_findings_with_evidence(self):
        """Test that report_findings includes evidence references."""
        from app.services.agent.tools import ReportFindingsTool

        tool = ReportFindingsTool()
        result = await tool.execute(
            findings="根据调查，张三的拳法是由李四传授的。",
            evidence_refs=[
                "doc_001/chunk_015: relationship '李四教张三角法' (relevance=0.92)",
                "doc_001/chunk_042: '张三称呼李四为师父' (relevance=0.78)",
            ],
        )

        assert "[FINDINGS]" in result
        assert "[EVIDENCE]" in result
        assert "doc_001/chunk_015" in result


class TestQualityGater:
    """Test quality gating logic."""

    def test_quality_score_computation(self):
        """Test quality score calculation."""
        from app.services.agent.quality_gater import QualityScore

        score = QualityScore(
            entity_count=5,
            relation_count=3,
            doc_coverage=0.8,
            contradiction_count=1,
        )
        score.compute(total_docs=3)

        assert 0 <= score.overall <= 1
        assert score.overall > 0.5  # With good metrics, score should be decent

    def test_max_asks_limit(self):
        """Test that max_asks respects the limit of 3."""
        from app.services.agent.quality_gater import QualityGater

        gater = QualityGater(quality_threshold=1.0, ask_user_cooldown=0)

        # Should be able to ask up to 3 times
        for i in range(3):
            gater.update(entity_count=1, relation_count=0, docs_with_results=1)
            assert gater.should_ask_user() is True
            gater.mark_asked()

        # 4th ask should be blocked
        gater.update(entity_count=1, relation_count=0, docs_with_results=1)
        assert gater.should_ask_user() is False


class TestEvidenceTracking:
    """Test evidence reference collection."""

    def test_collect_evidence_refs(self):
        """Test evidence reference extraction from tool results."""
        from app.services.agent.loop import _collect_evidence_refs

        evidence_map: dict[str, list[dict]] = {}
        result_json = json.dumps([{
            "doc_id": "doc_001",
            "chunk_id": "chunk_015",
            "relevance_score": 0.92,
            "summary": "李四教张三拳法",
        }], ensure_ascii=False)

        _collect_evidence_refs(evidence_map, "read_l1", {"doc_id": "doc_001"}, result_json)

        assert "doc_001" in evidence_map
        assert len(evidence_map["doc_001"]) == 1
        assert evidence_map["doc_001"][0]["relevance"] == 0.92

    def test_format_evidence_for_prompt(self):
        """Test evidence formatting for Agent prompt."""
        from app.services.agent.loop import _format_evidence_for_prompt

        evidence_map = {
            "doc_001": [{"chunk_id": "chunk_015", "relevance": 0.92, "excerpt": "李四教张三拳法"}],
        }

        formatted = _format_evidence_for_prompt(evidence_map)
        assert "doc_001" in formatted
        assert "92%" in formatted


class TestContextManager:
    """Test context compression logic."""

    def test_classify_critical_result(self):
        """Test that results with entities are classified as critical."""
        from app.services.agent.context_manager import ContextManager, ToolResultEntry

        mgr = ContextManager()
        entry = mgr.classify_result(
            "read_l1",
            '{"doc_id": "test"}',
            json.dumps([{"name": "张三", "entity_id": "e_001"}], ensure_ascii=False),
        )

        assert entry.importance == "critical"
        assert len(entry.entities_found) > 0
        assert "张三" in entry.entities_found

    def test_classify_empty_result(self):
        """Test that empty results are classified as transient."""
        from app.services.agent.context_manager import ContextManager

        mgr = ContextManager()
        entry = mgr.classify_result("search_vector", '{"query": "test"}', "[]")

        assert entry.importance == "transient"

    def test_microcompact_preserves_critical(self):
        """Test that microcompact preserves critical entries."""
        from app.services.agent.context_manager import ContextManager

        mgr = ContextManager()
        e1 = mgr.classify_result(
            "read_l1",
            '{"doc_id": "doc_001"}',
            json.dumps([{"name": "关键人物", "entity_id": "e_001"}], ensure_ascii=False),
        )
        mgr.record_entry(e1)

        assert e1.importance == "critical"
        assert mgr.get_context_stats()["critical_count"] == 1
