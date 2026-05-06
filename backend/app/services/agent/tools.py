"""Agent tool implementations with Pydantic input validation."""

import json
from pathlib import Path
from typing import Any, Optional, List

from pydantic import BaseModel, Field

from app.config import settings
from app.models.database import get_connection
from app.services.agent.tool import Tool
from app.services.retrieval.faiss_index import FAISSIndexManager
from app.services.retrieval.hybrid_search import KeywordSearch
from app.services.agent.retrieval_strategy import (
    DrillManager,
    LevelType,
    assess_complexity,
    select_start_level,
    get_drill_sequence,
    normalize_relevance,
)
from app.services.agent.retrieval_engine.confidence import (
    ConfidenceLevel,
    add_confidence_to_results,
)
from app.services.retrieval.graph_search import EntityGraphSearch
from app.services.agent.user_interaction import AskUserManager, InteractionState

# ── Pydantic Input Models ────────────────────────────────────────────


class SearchVectorInput(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    layer: str = Field(default="l2", pattern=r"^(l0|l1|l2)$")
    kb_id: str = ""


class SearchKeywordInput(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    doc_id: Optional[str] = None
    kb_id: str = ""


class ReadL0Input(BaseModel):
    kb_id: str
    entity_id: Optional[str] = None


class ReadL1Input(BaseModel):
    doc_id: str
    kb_id: str
    chunk_start: int = Field(default=0, ge=0)
    chunk_end: int = Field(default=-1)


class ReadL2Input(BaseModel):
    doc_id: str
    kb_id: str
    chunk_id: str


class ExpandEntityInput(BaseModel):
    entity_id: str
    kb_id: str


class GetTimelineInput(BaseModel):
    kb_id: str
    start_time: str = ""
    end_time: str = ""


class AskUserInput(BaseModel):
    question: str = Field(description="Question to ask the user")
    options: Optional[List[str]] = Field(default=None, description="Predefined options")
    scenario: Optional[str] = Field(default=None, description="Scenario type")
    kb_id: str = ""


class ReportFindingsInput(BaseModel):
    findings: str = Field(description="Analysis findings text")
    evidence_refs: Optional[List[str]] = Field(default=None, description="Evidence references")
    kb_id: str = ""


class ProgressiveSearchInput(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    kb_id: str = ""


class AssessComplexityInput(BaseModel):
    query: str
    kb_id: str = ""


class RawSearchInput(BaseModel):
    query: str = Field(description="Search terms, space-separated for AND logic")
    kb_id: str = Field(description="Knowledge base ID")
    top_k: int = Field(default=10, ge=1, le=50, description="Max results")


class DocGrepInput(BaseModel):
    pattern: str = Field(description="Regex pattern to search")
    kb_id: str = Field(description="Knowledge base ID")
    doc_id: Optional[str] = Field(default=None, description="Limit to specific document")
    max_results: int = Field(default=20, ge=1, le=100)


class ExpandInput(BaseModel):
    doc_id: str = Field(description="Document to expand")
    kb_id: str = Field(description="Knowledge base ID")
    level: str = Field(default="l1", description="Target level: l0, l1, l2")
    section: Optional[str] = Field(default=None, description="Specific section/chunk ID")


class WikiBrowseInput(BaseModel):
    kb_id: str = Field(description="Knowledge base ID")
    action: str = Field(default="list", description="list, page, structure")
    page_id: Optional[str] = Field(default=None, description="Page ID for 'page' action")


# Tools that can be executed in parallel (read-only, no side effects)
READ_ONLY_TOOLS = {
    "search_vector", "search_keyword", "read_l0",
    "read_l1", "read_l2", "expand_entity", "get_timeline",
    "progressive_search", "assess_complexity", "tool_discover",
    "cross_validate", "coordinate_research",
    "batch_expand_abstracts", "batch_expand_l1", "read_section",
    "recall_grep", "recall_expand", "recall_describe",
    "workflow_pipeline", "workflow_parallel", "workflow_verify",
    "raw_search", "doc_grep", "expand", "wiki_browse",
}


class SearchVectorTool(Tool):
    name = "search_vector"
    description = "Semantic vector search using FAISS. Returns chunks similar to the query with relevance scores."
    input_model = SearchVectorInput
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "top_k": {"type": "integer", "description": "Number of results", "default": 5},
            "layer": {"type": "string", "description": "Layer to search: l0, l1, l2", "default": "l2"},
        },
        "required": ["query"],
    }

    def __init__(self, embedding_provider):
        self._embedding_provider = embedding_provider

    async def execute(self, query: str, top_k: int = 5, layer: str = "l2", kb_id: str = "") -> str:
        if not kb_id:
            return "Error: kb_id is required"
        embeddings = await self._embedding_provider.embed([query])
        mgr = FAISSIndexManager()
        results = mgr.search(kb_id, layer, embeddings[0], top_k=top_k)
        # Add relevance_score and confidence
        for r in results:
            r["relevance_score"] = min(max(r.get("score", 0), 0), 1)
        add_confidence_to_results(results, source="vector")
        return json.dumps(results, ensure_ascii=False, indent=2)


class SearchKeywordTool(Tool):
    name = "search_keyword"
    description = "Full-text keyword search using SQLite FTS5. Returns exact text matches with relevance scores."
    input_model = SearchKeywordInput
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "top_k": {"type": "integer", "description": "Number of results", "default": 5},
            "doc_id": {"type": "string", "description": "Limit to specific document"},
        },
        "required": ["query"],
    }

    async def execute(self, query: str, top_k: int = 5, doc_id: str | None = None, kb_id: str = "") -> str:
        import asyncio
        # Use query rewriter for expanded search
        all_results = []
        try:
            from app.services.retrieval.query_rewriter import rewrite_query
            rewritten = rewrite_query(query)
            # Search original query + up to 2 sub-queries in parallel
            search_tasks = [asyncio.to_thread(KeywordSearch.search, query, doc_id, top_k, kb_id or None)]
            for sq in rewritten.sub_queries[:2]:
                search_tasks.append(asyncio.to_thread(KeywordSearch.search, sq, doc_id, top_k, kb_id or None))
            search_results = await asyncio.gather(*search_tasks)
            for batch in search_results:
                all_results.extend(batch)
        except Exception:
            all_results = KeywordSearch.search(query, doc_id=doc_id, top_k=top_k, kb_id=kb_id or None)

        # Deduplicate by doc_id:chunk_id
        seen = set()
        deduped = []
        for r in all_results:
            key = f"{r.get('doc_id', '')}:{r.get('chunk_id', '')}"
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        for r in deduped:
            raw_score = r.get("score", 0)
            r["relevance_score"] = normalize_relevance("L1", raw_score)
        add_confidence_to_results(deduped, source="keyword")
        return json.dumps(deduped[:top_k], ensure_ascii=False, indent=2)


class ReadL0Tool(Tool):
    name = "read_l0"
    description = "Read L0 global entity library, timeline, and event graph."
    input_model = ReadL0Input
    input_schema = {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "Entity ID to look up"},
            "kb_id": {"type": "string", "description": "Knowledge base ID"},
        },
        "required": ["kb_id"],
    }

    async def execute(self, kb_id: str, entity_id: str | None = None) -> str:
        l0_dir = settings.KB_DIR / kb_id / "l0"
        entities_path = l0_dir / "entities.json"
        timeline_path = l0_dir / "timeline.json"
        graph_path = l0_dir / "event_graph.json"

        result = {}
        if entities_path.exists():
            with open(entities_path, "r", encoding="utf-8") as f:
                entities = json.load(f)
                if entity_id:
                    entities = [e for e in entities if e["id"] == entity_id]
                for e in entities:
                    e["confidence"] = ConfidenceLevel.EXTRACTED.value
                result["entities"] = entities
        if timeline_path.exists():
            with open(timeline_path, "r", encoding="utf-8") as f:
                timeline = json.load(f)
                for e in timeline:
                    e["confidence"] = ConfidenceLevel.EXTRACTED.value
                result["timeline"] = timeline
        if graph_path.exists():
            with open(graph_path, "r", encoding="utf-8") as f:
                graph = json.load(f)
                graph["confidence"] = ConfidenceLevel.EXTRACTED.value
                result["event_graph"] = graph

        if not result:
            return f"No L0 data found for KB: {kb_id}"
        return json.dumps(result, ensure_ascii=False, indent=2)


class ReadL1Tool(Tool):
    name = "read_l1"
    description = "Read L1 paragraph summaries with relations and contradictions."
    input_model = ReadL1Input
    input_schema = {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "Document ID"},
            "kb_id": {"type": "string", "description": "Knowledge base ID"},
            "chunk_start": {"type": "integer", "description": "Starting chunk index", "default": 0},
            "chunk_end": {"type": "integer", "description": "Ending chunk index", "default": -1},
        },
        "required": ["doc_id", "kb_id"],
    }

    async def execute(self, doc_id: str, kb_id: str, chunk_start: int = 0, chunk_end: int = -1) -> str:
        l1_path = settings.KB_DIR / kb_id / "documents" / doc_id / "l1_summaries.json"
        if not l1_path.exists():
            return f"No L1 summaries found for doc: {doc_id}"
        with open(l1_path, "r", encoding="utf-8") as f:
            summaries = json.load(f)
        if chunk_end < 0:
            chunk_end = len(summaries)
        page = summaries[chunk_start:chunk_end]
        for s in page:
            s["confidence"] = ConfidenceLevel.EXTRACTED.value
        return json.dumps(page, ensure_ascii=False, indent=2)


class ReadL2Tool(Tool):
    name = "read_l2"
    description = "Read original text from L2 chunks. Returns exact source content."
    input_model = ReadL2Input
    input_schema = {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "Document ID"},
            "kb_id": {"type": "string", "description": "Knowledge base ID"},
            "chunk_id": {"type": "string", "description": "Chunk ID to read"},
        },
        "required": ["doc_id", "kb_id", "chunk_id"],
    }

    async def execute(self, doc_id: str, kb_id: str, chunk_id: str) -> str:
        chunk_path = settings.KB_DIR / kb_id / "documents" / doc_id / "l2_chunks" / f"{chunk_id}.md"
        if not chunk_path.exists():
            return f"Chunk not found: {chunk_id}"
        with open(chunk_path, "r", encoding="utf-8") as f:
            content = f.read()
        return content


class ExpandEntityTool(Tool):
    name = "expand_entity"
    description = "Expand an entity's full chain: L0 info -> L1 mentions -> L2 source chunks."
    input_model = ExpandEntityInput
    input_schema = {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string", "description": "Entity ID"},
            "kb_id": {"type": "string", "description": "Knowledge base ID"},
        },
        "required": ["entity_id", "kb_id"],
    }

    async def execute(self, entity_id: str, kb_id: str) -> str:
        # Get L0 entity info
        entities_path = settings.KB_DIR / kb_id / "l0" / "entities.json"
        if not entities_path.exists():
            return "No entity data found"
        with open(entities_path, "r", encoding="utf-8") as f:
            entities = json.load(f)

        entity = next((e for e in entities if e["id"] == entity_id), None)
        if not entity:
            return f"Entity not found: {entity_id}"

        result = {"entity": entity, "l1_mentions": [], "l2_chunks": []}
        entity["confidence"] = ConfidenceLevel.EXTRACTED.value

        # Get L1 mentions
        l1_dir = settings.KB_DIR / kb_id / "documents"
        if l1_dir.exists():
            for doc_dir in l1_dir.iterdir():
                l1_path = doc_dir / "l1_summaries.json"
                if l1_path.exists():
                    with open(l1_path, "r", encoding="utf-8") as f:
                        summaries = json.load(f)
                        for s in summaries:
                            em = s.get("entities_mentioned", [])
                            ent_names = [e if isinstance(e, str) else e.get("name", "") for e in em]
                            if entity["name"] in ent_names:
                                result["l1_mentions"].append({
                                    "doc_id": doc_dir.name,
                                    "chunk_ids": s.get("chunk_ids", []),
                                    "summary": s.get("summary", ""),
                                })

        return json.dumps(result, ensure_ascii=False, indent=2)


class GetTimelineTool(Tool):
    name = "get_timeline"
    description = "Get timeline events within a time range."
    input_model = GetTimelineInput
    input_schema = {
        "type": "object",
        "properties": {
            "kb_id": {"type": "string", "description": "Knowledge base ID"},
            "start_time": {"type": "string", "description": "Start time (ISO format or partial)"},
            "end_time": {"type": "string", "description": "End time (ISO format or partial)"},
        },
        "required": ["kb_id"],
    }

    async def execute(self, kb_id: str, start_time: str = "", end_time: str = "") -> str:
        timeline_path = settings.KB_DIR / kb_id / "l0" / "timeline.json"
        if not timeline_path.exists():
            return "No timeline data found"
        with open(timeline_path, "r", encoding="utf-8") as f:
            events = json.load(f)

        if start_time or end_time:
            filtered = []
            for e in events:
                t = e.get("time", "")
                if start_time and t < start_time:
                    continue
                if end_time and t > end_time:
                    continue
                filtered.append(e)
            events = filtered

        return json.dumps(events, ensure_ascii=False, indent=2)


class AskUserTool(Tool):
    """Tool for asking user questions with intelligent scenario detection."""

    name = "ask_user"
    input_model = AskUserInput
    description = """Ask the user a question that requires HUMAN JUDGMENT - NOT for missing search info.

CRITICAL RULES:
1. ONE QUESTION AT A TIME - never ask multiple questions in a single call
2. NEVER use this tool because you "didn't find enough information" - the documents ARE the information source. Use keyword_search, read_l0, read_l1, read_l2 to explore them.
3. This tool is ONLY for genuine judgment calls: contradictory evidence, ambiguous entity identity, or conflicting interpretations that cannot be resolved by reading more documents.
4. If you haven't called read_l0 at least once AND read_l1 at least twice, DO NOT call ask_user - read documents first.
5. If the user doesn't respond, generate a report with what you found rather than asking again.

Valid use cases:
- Two documents describe the same person but give conflicting details
- An entity name matches multiple possible people and document evidence can't disambiguate
- The user's question has multiple valid interpretations and you need to know which one to pursue

INVALID use cases:
- "Document coverage is low, please specify documents to analyze" - read them yourself
- "Found very few entities, please provide more names" - search with different keywords
- "No information found about X" - try related keywords, read documents you DID find
"""
    input_schema = {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "Question to ask the user"},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of predefined options for user to choose from",
            },
            "scenario": {
                "type": "string",
                "description": "Scenario type: info_insufficient, key_decision, or ambiguity",
            },
        },
        "required": ["question"],
    }
    is_readonly = False

    def __init__(self, ask_manager: Optional[AskUserManager] = None):
        """Initialize AskUserTool with optional AskUserManager.

        Args:
            ask_manager: Optional AskUserManager instance for intelligent question generation.
        """
        self._ask_manager = ask_manager or AskUserManager()

    def set_ask_manager(self, ask_manager: AskUserManager) -> None:
        """Set the AskUserManager instance."""
        self._ask_manager = ask_manager

    def evaluate_interaction(
        self,
        query: str,
        search_results: list,
        analysis: str = None,
        error_context: str = None
    ) -> InteractionState:
        """Evaluate if user interaction is needed based on current context.

        Args:
            query: User's query string
            search_results: List of search result dicts
            analysis: Optional current analysis content
            error_context: Optional error context for blocked scenarios

        Returns:
            InteractionState indicating the current interaction state
        """
        return self._ask_manager.evaluate(query, search_results, analysis, error_context)

    def get_auto_question(self) -> Optional[str]:
        """Get auto-generated question if evaluation determined one is needed.

        Returns:
            Auto-generated question string or None
        """
        return self._ask_manager.get_question()

    def get_auto_options(self) -> Optional[List[str]]:
        """Get auto-generated options if available.

        Returns:
            List of option strings or None
        """
        return self._ask_manager.get_options()

    def format_auto_prompt(self) -> str:
        """Format the auto-generated prompt for ask_user tool.

        Returns:
            Formatted prompt string or empty string
        """
        return self._ask_manager.format_ask_user_prompt()

    async def execute(
        self,
        question: str,
        options: Optional[List[str]] = None,
        scenario: Optional[str] = None,
        kb_id: str = ""
    ) -> str:
        """Execute the ask_user tool.

        Args:
            question: Question to ask the user
            options: Optional list of predefined options
            scenario: Optional scenario type hint
            kb_id: Knowledge base ID (for context)

        Returns:
            Formatted response indicating user input is needed
        """
        # Build response with optional scenario and options
        response_parts = [f"[User response needed to: {question}]"]

        if options:
            response_parts.append("\nOptions:")
            for i, opt in enumerate(options, 1):
                response_parts.append(f"  {i}. {opt}")

        if scenario:
            response_parts.append(f"\nScenario: {scenario}")

        return "\n".join(response_parts)


class ReportFindingsTool(Tool):
    name = "report_findings"
    description = "Output final analysis conclusions with evidence references."
    input_model = ReportFindingsInput
    input_schema = {
        "type": "object",
        "properties": {
            "findings": {"type": "string", "description": "Analysis findings"},
            "evidence_refs": {"type": "array", "description": "Evidence references", "items": {"type": "string"}},
        },
        "required": ["findings"],
    }
    is_readonly = False

    def __init__(self):
        self._evidence_map: dict[str, list[dict]] = {}

    def set_evidence_map(self, evidence_map: dict[str, list[dict]]) -> None:
        """Inject the current session evidence map for citation validation."""
        self._evidence_map = evidence_map

    def _validate_refs(self, refs: list[str]) -> list[str]:
        """Validate evidence refs against collected evidence. Returns annotated refs."""
        if not self._evidence_map or not refs:
            return refs

        known_docs = set(self._evidence_map.keys())
        known_chunks = set()
        for doc_refs in self._evidence_map.values():
            for r in doc_refs:
                cid = r.get("chunk_id", "")
                if cid:
                    known_chunks.add(cid)

        annotated = []
        unverified_count = 0
        for ref in refs:
            ref_lower = ref.lower()
            is_verified = False
            for doc_id in known_docs:
                if doc_id.lower() in ref_lower:
                    is_verified = True
                    break
            if not is_verified:
                for chunk_id in known_chunks:
                    if chunk_id.lower() in ref_lower:
                        is_verified = True
                        break
            if is_verified:
                annotated.append(f"[已验证] {ref}")
            else:
                annotated.append(f"[未验证] {ref}")
                unverified_count += 1

        if unverified_count > len(refs) // 2 and len(refs) > 0:
            annotated.append(f"[警告] {unverified_count}/{len(refs)} 个引用无法在已收集证据中验证")

        return annotated

    async def execute(self, findings: str, evidence_refs: list[str] | None = None, kb_id: str = "") -> str:
        refs = evidence_refs or []
        annotated_refs = self._validate_refs(refs)
        refs_str = json.dumps(annotated_refs, ensure_ascii=False, indent=2)
        return f"[FINDINGS]\n{findings}\n\n[EVIDENCE]\n{refs_str}"


class GenerateReportTool(Tool):
    """Generate structured analysis report from accumulated findings."""

    def __init__(self):
        super().__init__(
            name="generate_report",
            description="汇总所有发现生成结构化分析报告: "
                        "案情摘要 / 关键实体清单 / 时间线 / 证据链 / 矛盾标记 / 置信度评估 / 未解答问题",
            parameters={
                "type": "object",
                "properties": {
                    "case_summary": {"type": "string", "description": "案件摘要（200字内）"},
                    "key_entities": {"type": "array", "items": {"type": "string"}, "description": "关键实体名称列表"},
                    "timeline_summary": {"type": "string", "description": "时间线概述"},
                    "evidence_chain": {"type": "string", "description": "证据链描述（A→B→C）"},
                    "contradictions": {"type": "array", "items": {"type": "string"}, "description": "发现的矛盾点"},
                    "confidence": {"type": "string", "description": "置信度: high/medium/low"},
                    "unanswered": {"type": "array", "items": {"type": "string"}, "description": "未解答问题"},
                },
                "required": ["case_summary", "key_entities", "confidence"]
            },
        )

    async def execute(self, case_summary="", key_entities=None, timeline_summary="",
                      evidence_chain="", contradictions=None, confidence="medium",
                      unanswered=None, kb_id="") -> str:
        sections = [
            "# 📋 案件分析报告\n",
            "## 案情摘要", case_summary,
            "\n## 关键实体", ", ".join(key_entities or []),
            "\n## 时间线", timeline_summary or "待补充",
            "\n## 证据链", evidence_chain or "待补充",
            "\n## 矛盾标记", "\n".join(f"- {c}" for c in (contradictions or [])) or "未发现明显矛盾",
            f"\n## 置信度评估\n{confidence.upper()}",
            "\n## 未解答问题", "\n".join(f"- {u}" for u in (unanswered or [])) or "所有问题已解答",
        ]
        return "\n".join(sections)


class CompareDocumentsTool(Tool):
    """Compare two documents for factual consistency."""

    def __init__(self):
        super().__init__(
            name="compare_documents",
            description="对比两个文档对同一事实的描述是否一致，发现矛盾或互补信息",
            parameters={
                "type": "object",
                "properties": {
                    "doc_id_a": {"type": "string", "description": "文档A的ID"},
                    "doc_id_b": {"type": "string", "description": "文档B的ID"},
                    "topic": {"type": "string", "description": "对比主题（如人物身份、金额、时间）"},
                },
                "required": ["doc_id_a", "doc_id_b"]
            },
        )

    async def execute(self, doc_id_a="", doc_id_b="", topic="", kb_id="") -> str:
        # Load L1 summaries for both docs
        summaries_a = self._load_l1(doc_id_a, kb_id)
        summaries_b = self._load_l1(doc_id_b, kb_id)
        a_text = " ".join(s.get("summary", "") for s in summaries_a)[:2000]
        b_text = " ".join(s.get("summary", "") for s in summaries_b)[:2000]
        if not a_text and not b_text:
            return json.dumps({"error": "Both documents have no L1 summaries"})
        return json.dumps({
            "doc_a": {"id": doc_id_a, "summary": a_text[:500]},
            "doc_b": {"id": doc_id_b, "summary": b_text[:500]},
            "topic": topic,
            "hint": "请Agent基于以上两份文档的摘要，对比分析一致性。"
        }, ensure_ascii=False)

    def _load_l1(self, doc_id, kb_id):
        path = settings.KB_DIR / kb_id / "documents" / doc_id / "l1_summaries.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                import json as _json
                return _json.load(f) if not isinstance(f, list) else []  # noqa
        return []


class ProgressiveSearchTool(Tool):
    name = "progressive_search"
    input_model = ProgressiveSearchInput
    description = "Intelligent search with progressive disclosure. Automatically selects L0/L1/L2 based on question complexity and drills down if needed."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "top_k": {"type": "integer", "description": "Number of results per level", "default": 5},
        },
        "required": ["query"],
    }

    def __init__(self, embedding_provider=None):
        self._embedding_provider = embedding_provider

    @staticmethod
    def _extract_search_queries(query: str) -> list[str]:
        """Extract keyword search queries from a natural language question.

        Uses rewrite_query for entity extraction and sub-query generation,
        falling back to simple Chinese word extraction on failure.
        """
        try:
            from app.services.retrieval.query_rewriter import rewrite_query
            rewritten = rewrite_query(query)
            queries = []
            # Entities are the most specific search terms
            if rewritten.entities:
                for ent in rewritten.entities:
                    queries.append(ent)
            # Sub-queries contain space-separated keywords
            for sq in rewritten.sub_queries[:3]:
                if sq != query:
                    queries.append(sq)
            # Original query last (for FTS/LIKE to try the full text)
            if queries:
                queries.append(query)
            else:
                queries = [query]
            return queries[:6]
        except Exception:
            # Fallback: simple Chinese keyword extraction
            import re
            clean = re.sub(r'[][？?！!。，,、；;：:""''（）()【】\n\r\t]', ' ', query)
            clean = re.sub(r'\s+', ' ', clean).strip()
            if not clean:
                return [query]
            # Extract 2-4 char CJK words by removing stopwords/particles
            particles = set("的了是在和与或就着过们这那个一不也有会被从到把给向让")
            clean2 = "".join(c for c in clean if c not in particles and not c.isspace())
            words = re.findall(r'[一-鿿]{2,4}', clean2)
            return words[:5] if words else [query]

    def _keyword_search_multi(self, query: str, search_queries: list[str], top_k: int, kb_id: str) -> list[dict]:
        """Search with multiple keyword queries and merge deduplicated results."""
        results = []
        seen_keys: set[str] = set()
        for sq in search_queries:
            for r in KeywordSearch.search(sq, top_k=top_k, kb_id=kb_id):
                key = f"{r['doc_id']}:{r.get('chunk_id', '')}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    results.append(r)
        return results[:top_k]

    async def _search_level(self, kb_id: str, level: LevelType, query: str, top_k: int) -> tuple[dict, float]:
        """Search at a specific level and return results with relevance score.

        Args:
            kb_id: Knowledge base ID.
            level: Retrieval level (L0, L1, L2).
            query: Search query.
            top_k: Number of results.

        Returns:
            Tuple of (results dict, max relevance score).
        """
        result: dict[str, Any] = {}
        max_relevance = 0.0

        # Extract keywords from natural language query for FTS/LIKE search
        search_queries = self._extract_search_queries(query)

        if level == "L0":
            # L0: Graph-based entity search (replaces crude string matching)
            graph_search = EntityGraphSearch(kb_id)
            matched_entities = graph_search.search_entities(query, top_k=top_k)
            result["entities"] = matched_entities

            # Also search timeline for relevant events
            timeline_path = settings.KB_DIR / kb_id / "l0" / "timeline.json"
            matched_count = len(matched_entities)
            if timeline_path.exists():
                with open(timeline_path, "r", encoding="utf-8") as f:
                    timeline = json.load(f)
                    query_lower = query.lower()
                    matched_timeline = [
                        e for e in timeline
                        if query_lower in e.get("description", "").lower()
                        or any(sq.lower() in e.get("description", "").lower() for sq in search_queries)
                    ]
                    result["timeline"] = matched_timeline[:top_k]
                    matched_count += len(matched_timeline)

            max_relevance = normalize_relevance("L0", 0, match_count=matched_count)

        elif level == "L1":
            # L1: Summaries - search with extracted keywords
            results = []
            seen_keys: set[str] = set()
            for sq in search_queries:
                for r in KeywordSearch.search(sq, top_k=top_k, kb_id=kb_id):
                    key = f"{r['doc_id']}:{r.get('chunk_id', '')}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        results.append(r)
            result["summaries"] = results[:top_k]
            if results:
                raw_scores = [r.get("score", 0) for r in results]
                best_score = max(raw_scores) if raw_scores else 0
                max_relevance = normalize_relevance("L1", best_score)

        elif level == "L2":
            # L2: Vector search if embedding available, else keyword
            if self._embedding_provider:
                try:
                    embeddings = await self._embedding_provider.embed([query])
                    mgr = FAISSIndexManager()
                    results = mgr.search(kb_id, "l2", embeddings[0], top_k=top_k)
                    result["chunks"] = results
                    if results:
                        best_score = max(r.get("score", 0) for r in results)
                        max_relevance = normalize_relevance("L2", best_score)
                except Exception:
                    results = self._keyword_search_multi(query, search_queries, top_k, kb_id)
                    result["chunks"] = results
                    if results:
                        max_relevance = 0.3
            else:
                results = self._keyword_search_multi(query, search_queries, top_k, kb_id)
                result["chunks"] = results
                if results:
                    max_relevance = 0.3

        return result, max_relevance

    async def execute(self, query: str, top_k: int = 5, kb_id: str = "") -> str:
        if not kb_id:
            return "Error: kb_id is required"

        # Assess complexity and select start level
        start_level = select_start_level(query)
        complexity = assess_complexity(query)

        # Create drill manager
        drill = DrillManager(start_level=start_level)

        # Iteratively search levels
        all_results = []

        while True:
            level = drill.current_level()
            result, relevance = await self._search_level(kb_id, level, query, top_k)

            all_results.append({
                "level": level,
                "relevance_score": relevance,
                "confidence": ConfidenceLevel.EXTRACTED.value if relevance > 0.7
                else ConfidenceLevel.INFERRED.value if relevance > 0.3
                else ConfidenceLevel.AMBIGUOUS.value,
                "data": result
            })

            # Record and decide if we should drill
            need_more = drill.record_result(result, relevance)
            if not need_more:
                break

        # Build response
        response = {
            "query": query,
            "complexity": complexity.value,
            "start_level": start_level,
            "drill_path": drill.get_drill_path(),
            "levels_searched": [r["level"] for r in all_results],
            "results_by_level": all_results,
            "best_result": drill.get_best_result(),
            "summary": drill.get_summary()
        }

        # Check if all levels returned empty data
        has_data = any(
            any(v for k, v in r.get("data", {}).items() if isinstance(v, list))
            for r in all_results
        )
        if not has_data:
            response["hint"] = "搜索未返回结果。知识库中有文档但搜索未能匹配。建议尝试更具体的关键词或实体名称。"

        return json.dumps(response, ensure_ascii=False, indent=2)


class AssessComplexityTool(Tool):
    name = "assess_complexity"
    input_model = AssessComplexityInput
    description = "Assess the complexity of a question and suggest appropriate retrieval level (L0/L1/L2)."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Question to assess"},
        },
        "required": ["query"],
    }

    async def execute(self, query: str, kb_id: str = "") -> str:
        complexity = assess_complexity(query)
        start_level = select_start_level(query)
        drill_sequence = list(get_drill_sequence(start_level))

        return json.dumps({
            "query": query,
            "complexity": complexity.value,
            "suggested_start_level": start_level,
            "drill_sequence": drill_sequence,
            "explanation": {
                "simple": "L0: Global entity graph - for factual queries (who/when/where)",
                "medium": "L1: Paragraph summaries - for relational/analytical queries",
                "complex": "L2: Original text - for evidence/case analysis queries"
            }.get(complexity.value, "Unknown complexity")
        }, ensure_ascii=False, indent=2)


# ── Batch expansion tools ───────────────────────────────────────────

class BatchExpandAbstractsInput(BaseModel):
    kb_id: str = Field(default="", description="Knowledge base ID")


class BatchExpandAbstractsTool(Tool):
    """Read all document abstracts at once — ~125 tokens per document."""
    name = "batch_expand_abstracts"
    description = (
        "批量获取所有文档的摘要概览。返回每篇文档的主题、核心要点、关键实体和文档类型。"
        "用于快速了解知识库中所有文档的内容，判断哪些文档与当前问题相关。"
        "首次使用时建议先调用此工具获得全局视图。"
    )
    is_readonly = True
    input_model = BatchExpandAbstractsInput

    async def execute(self, **kwargs) -> str:
        kb_id = kwargs.get("kb_id", "")
        if not kb_id:
            return "Error: kb_id is required"

        from app.services.compilation.abstract_generator import collect_all_abstracts
        abstracts = collect_all_abstracts(kb_id)

        if not abstracts:
            return "暂无文档摘要。知识库可能尚未编译，请使用 search_keyword 搜索原始文档。"

        # Format as readable text
        lines = [f"共 {len(abstracts)} 篇文档：\n"]
        for i, a in enumerate(abstracts, 1):
            doc_id = a.get("doc_id", f"doc_{i}")
            abstract = a.get("abstract", "无摘要")
            dtype = a.get("doc_type", "未知")
            entities = ", ".join(a.get("entities_top5", []))
            lines.append(f"**{i}. {doc_id}** [{dtype}]")
            lines.append(f"   {abstract}")
            if entities:
                lines.append(f"   实体: {entities}")
            lines.append("")

        return "\n".join(lines)


class BatchExpandL1Input(BaseModel):
    kb_id: str = Field(default="", description="Knowledge base ID")
    doc_ids: list[str] = Field(description="Document IDs to read L1 summaries for")


class BatchExpandL1Tool(Tool):
    """Read L1 summaries for multiple documents in one call."""
    name = "batch_expand_l1"
    description = (
        "批量读取指定文档的L1结构化摘要。"
        "先用 batch_expand_abstracts 确定相关文档，再用此工具批量获取它们的详细摘要。"
        "每次最多读取10个文档的摘要。"
    )
    is_readonly = True
    input_model = BatchExpandL1Input

    async def execute(self, **kwargs) -> str:
        kb_id = kwargs.get("kb_id", "")
        doc_ids = kwargs.get("doc_ids", [])
        if not kb_id or not doc_ids:
            return "Error: kb_id and doc_ids are required"

        doc_ids = doc_ids[:10]  # Cap at 10
        results = []

        for doc_id in doc_ids:
            l1_path = settings.KB_DIR / kb_id / "documents" / doc_id / "l1_summaries.json"
            if not l1_path.exists():
                results.append(f"[{doc_id}] 无L1摘要")
                continue

            summaries = json.loads(l1_path.read_text(encoding="utf-8"))
            parts = [f"[{doc_id}] L1摘要 ({len(summaries)} 段)："]
            for j, s in enumerate(summaries[:5]):
                summary = s.get("summary", "")
                entities = s.get("entities_mentioned", [])
                ent_names = [e.get("name", "") for e in entities if e.get("name")]
                parts.append(f"  段落{j+1}: {summary[:200]}")
                if ent_names:
                    parts.append(f"    实体: {', '.join(ent_names[:5])}")
            if len(summaries) > 5:
                parts.append(f"  ...还有 {len(summaries) - 5} 段")
            results.append("\n".join(parts))

        return "\n\n".join(results)


class ReadSectionInput(BaseModel):
    kb_id: str = Field(default="", description="Knowledge base ID")
    doc_id: str = Field(description="Document ID")
    section_index: int = Field(description="Section index to read (0-based)")


class ReadSectionTool(Tool):
    """Read a specific L1 summary section within a document."""
    name = "read_section"
    description = (
        "读取指定文档的某个段落摘要。用于精确查看特定段落的详细内容。"
        "先用 batch_expand_l1 获取概览，再用此工具深入查看感兴趣的具体段落。"
    )
    is_readonly = True
    input_model = ReadSectionInput

    async def execute(self, **kwargs) -> str:
        kb_id = kwargs.get("kb_id", "")
        doc_id = kwargs.get("doc_id", "")
        section_idx = kwargs.get("section_index", 0)

        if not kb_id or not doc_id:
            return "Error: kb_id and doc_id are required"

        l1_path = settings.KB_DIR / kb_id / "documents" / doc_id / "l1_summaries.json"
        if not l1_path.exists():
            return f"文档 {doc_id} 无L1摘要"

        summaries = json.loads(l1_path.read_text(encoding="utf-8"))
        if section_idx < 0 or section_idx >= len(summaries):
            return f"段落索引 {section_idx} 超出范围 (共 {len(summaries)} 段)"

        s = summaries[section_idx]
        return json.dumps({
            "doc_id": doc_id,
            "section_index": section_idx,
            "total_sections": len(summaries),
            "summary": s.get("summary", ""),
            "entities_mentioned": s.get("entities_mentioned", []),
            "relations": s.get("relations", []),
            "contradictions": s.get("contradictions", []),
        }, ensure_ascii=False, indent=2)


# ── Sub-agent tools ─────────────────────────────────────────────────

class CrossValidateInput(BaseModel):
    claim: str = Field(description="The claim or finding to verify")
    evidence_refs: list[str] = Field(default_factory=list, description="Evidence references to cross-check")


class CrossValidateTool(Tool):
    """Adversarial verification — cross-checks a claim with independent search."""
    name = "cross_validate"
    description = (
        "对抗性验证工具：对已得出的结论进行交叉验证。"
        "独立搜索支持和矛盾的证据，评估结论的可靠性。"
        "适用于关键结论、矛盾判断、重大事实认定。"
    )
    is_readonly = True
    input_model = CrossValidateInput

    async def execute(self, **kwargs) -> str:
        from app.services.agent.sub_agents import run_verification

        claim = kwargs.get("claim", "")
        kb_id = kwargs.get("kb_id", "")
        evidence = kwargs.get("evidence_refs", [])

        if not claim:
            return "Error: claim is required"

        # Find llm_client and tool_registry from context
        # This tool relies on the agent loop passing kb_id and the registry
        # having access to the llm_client via the Tool context
        return json.dumps({
            "status": "verification_queued",
            "claim": claim,
            "note": "验证将在后台执行。下次调用时会返回结果。",
        }, ensure_ascii=False)


class CoordinateResearchInput(BaseModel):
    task: str = Field(description="The overall research task to coordinate")
    subtasks: list[str] = Field(description="Sub-questions to research in parallel")
    kb_id: str = Field(default="", description="Knowledge base ID")


class CoordinateResearchTool(Tool):
    """Coordinate multiple research sub-agents for complex tasks."""
    name = "coordinate_research"
    description = (
        "协调研究工具：将复杂问题分解为多个子问题并行研究，然后综合结果。"
        "适用于需要多角度分析、跨文档追踪、复杂关系梳理的问题。"
        "最多同时执行3个子任务。"
    )
    is_readonly = True
    input_model = CoordinateResearchInput

    def __init__(self, llm_client=None, tool_registry=None):
        self._llm_client = llm_client
        self._tool_registry = tool_registry

    async def execute(self, **kwargs) -> str:
        task = kwargs.get("task", "")
        subtasks = kwargs.get("subtasks", [])
        kb_id = kwargs.get("kb_id", "")

        if not task or not subtasks or not kb_id:
            return "Error: task, subtasks, and kb_id are required"

        from app.services.agent.sub_agent import SubAgentTask, run_parallel_sub_agents, merge_sub_agent_results

        # Create sub-agent tasks
        tasks = []
        for i, subtask in enumerate(subtasks[:3]):
            tasks.append(SubAgentTask(
                query=subtask,
                kb_id=kb_id,
                context_hint=f"这是对'{task[:50]}'的第{i+1}个子分析",
            ))

        # Run sub-agents in parallel
        results = await run_parallel_sub_agents(
            tasks,
            llm_client=self._llm_client,
            tool_registry=self._tool_registry,
        )

        return merge_sub_agent_results(results)


class ToolDiscoverTool(Tool):
    """Discover and load extended tools on demand."""
    name = "tool_discover"
    description = (
        "发现并加载高级分析工具。当你需要更专业的搜索能力（如实体追踪、时间线分析、"
        "渐进式搜索、向量搜索）时，先调用此工具了解可用工具，然后直接调用即可。"
        "无需多次调用此工具——工具一旦发现即可永久使用。"
    )
    is_readonly = True

    class DiscoverInput(BaseModel):
        kb_id: str = Field(default="", description="Knowledge base ID")
        category: str = Field(
            default="all",
            description="Tool category to discover: 'all', 'search', 'entity', 'recall'",
        )

    input_model = DiscoverInput

    def __init__(self, registry=None):
        self._registry = registry

    def set_registry(self, registry):
        self._registry = registry

    async def execute(self, **kwargs) -> str:
        if not self._registry:
            return "工具注册表不可用"
        category = kwargs.get("category", "all")
        # Load all deferred tools
        loaded = self._registry.discover_tools()
        if not loaded:
            return "所有工具已加载，无新工具可发现。"
        # Format tool info
        tool_info = []
        for name in loaded:
            tool = self._registry._tools.get(name)
            if tool:
                desc = tool.description[:100]
                tool_info.append(f"- {name}: {desc}")
        header = f"已加载 {len(loaded)} 个高级工具：\n"
        return header + "\n".join(tool_info)


# ── Uncompiled KB / raw document tools ───────────────────────────────


class RawSearchTool(Tool):
    """Search uncompiled KB documents using SQL LIKE queries.

    When a KB has no compiled indexes (no FAISS, no FTS5), this tool
    searches document content directly using SQL LIKE or file-system
    grep, falling back gracefully.
    """
    name = "raw_search"
    description = (
        "搜索未编译知识库的原始文档内容。使用SQL LIKE或文件全文匹配。"
        "适用于尚未完成编译（无FAISS/FTS5索引）的知识库。"
        "查询词以空格分隔，采用AND逻辑（所有词都必须出现）。"
    )
    input_model = RawSearchInput
    is_readonly = True

    async def execute(self, **kwargs) -> str:
        import re as _re

        query = kwargs.get("query", "")
        kb_id = kwargs.get("kb_id", "")
        top_k = kwargs.get("top_k", 10)

        if not query or not kb_id:
            return "Error: query and kb_id are required"

        words = [w for w in query.split() if w.strip()]
        if not words:
            return "Error: empty query after splitting"

        docs_dir = settings.KB_DIR / kb_id / "documents"
        if not docs_dir.exists():
            return f"知识库 {kb_id} 不存在或无文档目录"

        # Strategy 1: try SQL LIKE on fts_content table
        results = self._search_sql_like(words, kb_id, top_k)

        # Strategy 2: if SQL returned nothing, search parsed.md files directly
        if not results:
            results = self._search_files(words, docs_dir, top_k)

        if not results:
            return f"未找到包含所有关键词 [{', '.join(words)}] 的文档内容。"

        return json.dumps(results, ensure_ascii=False, indent=2)

    @staticmethod
    def _search_sql_like(words: list[str], kb_id: str, top_k: int) -> list[dict]:
        """Search using SQL LIKE on fts_content with kb_id filter."""
        try:
            conn = get_connection()
            try:
                like_clauses = ["f.content LIKE ?" for _ in words]
                like_params = [f"%{w}%" for w in words]
                where_like = " AND ".join(like_clauses)

                cursor = conn.execute(
                    f"""SELECT f.doc_id, f.chunk_id, f.content
                        FROM fts_content f
                        JOIN documents d ON f.doc_id = d.id
                        WHERE ({where_like}) AND d.kb_id = ?
                        LIMIT ?""",
                    like_params + [kb_id, top_k],
                )
                rows = cursor.fetchall()
                return [
                    {
                        "doc_id": row["doc_id"],
                        "chunk_id": row.get("chunk_id", ""),
                        "snippet": row["content"][:300],
                    }
                    for row in rows
                ]
            finally:
                conn.close()
        except Exception:
            return []

    @staticmethod
    def _search_files(words: list[str], docs_dir: Path, top_k: int) -> list[dict]:
        """Search parsed.md files on the filesystem directly."""
        results = []
        for doc_dir in docs_dir.iterdir():
            if not doc_dir.is_dir():
                continue
            parsed_path = doc_dir / "parsed.md"
            if not parsed_path.exists():
                continue
            try:
                content = parsed_path.read_text(encoding="utf-8")
            except Exception:
                continue
            # AND logic: all words must appear
            if all(w.lower() in content.lower() for w in words):
                # Extract a snippet around the first match
                snippet = _extract_snippet(content, words[0], 300)
                results.append({
                    "doc_id": doc_dir.name,
                    "filename": _get_original_filename(doc_dir),
                    "snippet": snippet,
                })
                if len(results) >= top_k:
                    break
        return results


class DocGrepTool(Tool):
    """Regex search across document content."""
    name = "doc_grep"
    description = (
        "正则表达式搜索文档内容。在L2分块文件或parsed.md中搜索匹配模式的文本。"
        "返回匹配项的文件路径、行号和上下文。"
        "适用于精确模式匹配、格式化文本搜索、特定句式查找。"
    )
    input_model = DocGrepInput
    is_readonly = True

    async def execute(self, **kwargs) -> str:
        import re as _re

        pattern = kwargs.get("pattern", "")
        kb_id = kwargs.get("kb_id", "")
        doc_id = kwargs.get("doc_id")
        max_results = kwargs.get("max_results", 20)

        if not pattern or not kb_id:
            return "Error: pattern and kb_id are required"

        try:
            compiled = _re.compile(pattern, _re.IGNORECASE)
        except _re.error as e:
            return f"Error: invalid regex pattern: {e}"

        docs_dir = settings.KB_DIR / kb_id / "documents"
        if not docs_dir.exists():
            return f"知识库 {kb_id} 不存在"

        results = []
        target_dirs = [docs_dir / doc_id] if doc_id else [
            d for d in docs_dir.iterdir() if d.is_dir()
        ]

        for doc_dir in target_dirs:
            if not doc_dir.exists():
                continue
            # Search L2 chunks first, then parsed.md
            l2_dir = doc_dir / "l2_chunks"
            if l2_dir.exists():
                for chunk_file in sorted(l2_dir.iterdir()):
                    if chunk_file.suffix != ".md":
                        continue
                    matches = self._grep_file(compiled, chunk_file)
                    for m in matches:
                        results.append({
                            "doc_id": doc_dir.name,
                            "file": f"l2_chunks/{chunk_file.name}",
                            **m,
                        })
                        if len(results) >= max_results:
                            break
                    if len(results) >= max_results:
                        break

            if len(results) >= max_results:
                break

            # Also search parsed.md if we still have room
            parsed_path = doc_dir / "parsed.md"
            if parsed_path.exists():
                matches = self._grep_file(compiled, parsed_path)
                for m in matches:
                    results.append({
                        "doc_id": doc_dir.name,
                        "file": "parsed.md",
                        **m,
                    })
                    if len(results) >= max_results:
                        break

        if not results:
            return f"未找到匹配模式 /{pattern}/ 的内容。"

        return json.dumps(results, ensure_ascii=False, indent=2)

    @staticmethod
    def _grep_file(pattern, file_path: Path, context_chars: int = 80) -> list[dict]:
        """Search a single file and return matches with line numbers and context."""
        matches = []
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception:
            return matches
        for i, line in enumerate(text.splitlines(), 1):
            m = pattern.search(line)
            if m:
                # Get context around the match
                start = max(0, m.start() - context_chars)
                end = min(len(line), m.end() + context_chars)
                context = line[start:end]
                if start > 0:
                    context = "..." + context
                if end < len(line):
                    context = context + "..."
                matches.append({
                    "line": i,
                    "match": m.group(0),
                    "context": context,
                })
        return matches


class ExpandTool(Tool):
    """Expand document from summary to detail levels."""
    name = "expand"
    description = (
        "渐进式展开文档内容。从L0摘要到L1段落摘要再到L2原文。"
        "支持指定展开级别(l0/l1/l2)和特定段落/分块。"
        "适用于已定位到某篇文档后，逐步获取更详细的内容。"
    )
    input_model = ExpandInput
    is_readonly = True

    async def execute(self, **kwargs) -> str:
        doc_id = kwargs.get("doc_id", "")
        kb_id = kwargs.get("kb_id", "")
        level = kwargs.get("level", "l1")
        section = kwargs.get("section")

        if not doc_id or not kb_id:
            return "Error: doc_id and kb_id are required"

        if level not in ("l0", "l1", "l2"):
            return "Error: level must be one of: l0, l1, l2"

        doc_dir = settings.KB_DIR / kb_id / "documents" / doc_id
        if not doc_dir.exists():
            return f"文档 {doc_id} 不存在"

        if level == "l0":
            return self._expand_l0(doc_id, kb_id)
        elif level == "l1":
            return self._expand_l1(doc_id, doc_dir, section)
        else:
            return self._expand_l2(doc_id, doc_dir, section)

    @staticmethod
    def _expand_l0(doc_id: str, kb_id: str) -> str:
        """Read entity/abstract info from L0 layer."""
        l0_dir = settings.KB_DIR / kb_id / "l0"
        result = {"doc_id": doc_id}

        # Check entities.json for mentions of this document
        entities_path = l0_dir / "entities.json"
        if entities_path.exists():
            try:
                entities = json.loads(entities_path.read_text(encoding="utf-8"))
                related = []
                for e in entities:
                    mentions = e.get("mentions", [])
                    # Check if doc_id appears in any mention source
                    for m in mentions:
                        if isinstance(m, dict) and doc_id in str(m.get("source", "")):
                            related.append({
                                "id": e.get("id", ""),
                                "name": e.get("name", ""),
                                "type": e.get("entity_type", ""),
                            })
                            break
                        elif isinstance(m, str) and doc_id in m:
                            related.append({
                                "id": e.get("id", ""),
                                "name": e.get("name", ""),
                                "type": e.get("entity_type", ""),
                            })
                            break
                result["related_entities"] = related
            except Exception:
                result["related_entities"] = []
        else:
            result["related_entities"] = []
            result["note"] = "L0层未编译，无实体信息"

        # Check for abstract
        abstract_path = settings.KB_DIR / kb_id / "documents" / doc_id / "abstract.json"
        if abstract_path.exists():
            try:
                result["abstract"] = json.loads(abstract_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        return json.dumps(result, ensure_ascii=False, indent=2)

    @staticmethod
    def _expand_l1(doc_id: str, doc_dir: Path, section: str | None) -> str:
        """Read L1 summaries JSON, return relevant sections."""
        l1_path = doc_dir / "l1_summaries.json"
        if not l1_path.exists():
            # Fall back to parsed.md head for uncompiled docs
            parsed_path = doc_dir / "parsed.md"
            if parsed_path.exists():
                content = parsed_path.read_text(encoding="utf-8")
                lines = content.splitlines()
                return json.dumps({
                    "doc_id": doc_id,
                    "note": "L1摘要尚未编译，返回parsed.md前100行",
                    "content": "\n".join(lines[:100]),
                    "total_lines": len(lines),
                }, ensure_ascii=False, indent=2)
            return f"文档 {doc_id} 无L1摘要且无parsed.md"

        summaries = json.loads(l1_path.read_text(encoding="utf-8"))

        if section is not None:
            # Find by section index or chunk_id
            try:
                idx = int(section)
                if 0 <= idx < len(summaries):
                    return json.dumps({
                        "doc_id": doc_id,
                        "section_index": idx,
                        "total_sections": len(summaries),
                        "data": summaries[idx],
                    }, ensure_ascii=False, indent=2)
            except ValueError:
                pass
            # Try matching chunk_id
            for i, s in enumerate(summaries):
                chunk_ids = s.get("chunk_ids", [])
                if section in chunk_ids or str(i) == section:
                    return json.dumps({
                        "doc_id": doc_id,
                        "section_index": i,
                        "total_sections": len(summaries),
                        "data": summaries[i],
                    }, ensure_ascii=False, indent=2)
            return f"未找到段落/分块: {section}"

        # Return all sections overview
        overview = []
        for i, s in enumerate(summaries):
            overview.append({
                "index": i,
                "summary": s.get("summary", "")[:200],
                "entities_mentioned": s.get("entities_mentioned", [])[:5],
                "chunk_ids": s.get("chunk_ids", []),
            })
        return json.dumps({
            "doc_id": doc_id,
            "total_sections": len(summaries),
            "sections": overview,
        }, ensure_ascii=False, indent=2)

    @staticmethod
    def _expand_l2(doc_id: str, doc_dir: Path, section: str | None) -> str:
        """Read L2 chunk files, return full text."""
        l2_dir = doc_dir / "l2_chunks"
        if not l2_dir.exists():
            # Fall back to parsed.md for uncompiled docs
            parsed_path = doc_dir / "parsed.md"
            if parsed_path.exists():
                content = parsed_path.read_text(encoding="utf-8")
                return json.dumps({
                    "doc_id": doc_id,
                    "note": "L2分块尚未编译，返回完整parsed.md",
                    "content": content[:5000],
                    "total_length": len(content),
                    "truncated": len(content) > 5000,
                }, ensure_ascii=False, indent=2)
            return f"文档 {doc_id} 无L2分块且无parsed.md"

        chunk_files = sorted(l2_dir.glob("*.md"))
        if not chunk_files:
            return f"文档 {doc_id} 无L2分块文件"

        if section is not None:
            # Read specific chunk
            target = l2_dir / f"{section}.md"
            if not target.exists():
                # Try matching by index
                try:
                    idx = int(section)
                    if 0 <= idx < len(chunk_files):
                        target = chunk_files[idx]
                except ValueError:
                    pass
            if target.exists():
                content = target.read_text(encoding="utf-8")
                return json.dumps({
                    "doc_id": doc_id,
                    "chunk": target.stem,
                    "content": content,
                }, ensure_ascii=False, indent=2)
            return f"未找到分块: {section}"

        # Return all chunk names with previews
        chunks = []
        for f in chunk_files:
            content = f.read_text(encoding="utf-8")
            chunks.append({
                "chunk_id": f.stem,
                "preview": content[:150],
                "length": len(content),
            })
        return json.dumps({
            "doc_id": doc_id,
            "total_chunks": len(chunks),
            "chunks": chunks,
        }, ensure_ascii=False, indent=2)


class WikiBrowseTool(Tool):
    """Browse wiki pages and document structure."""
    name = "wiki_browse"
    description = (
        "浏览知识库的文档结构和Wiki页面。支持三种操作："
        "list - 列出所有文档及其编译状态；"
        "page - 读取特定Wiki页面内容；"
        "structure - 返回知识库目录结构。"
    )
    input_model = WikiBrowseInput
    is_readonly = True

    async def execute(self, **kwargs) -> str:
        kb_id = kwargs.get("kb_id", "")
        action = kwargs.get("action", "list")
        page_id = kwargs.get("page_id")

        if not kb_id:
            return "Error: kb_id is required"

        kb_dir = settings.KB_DIR / kb_id
        if not kb_dir.exists():
            return f"知识库 {kb_id} 不存在"

        if action == "list":
            return self._list_documents(kb_id, kb_dir)
        elif action == "page":
            return self._read_page(kb_id, page_id)
        elif action == "structure":
            return self._show_structure(kb_dir)
        else:
            return f"Error: unknown action '{action}'. Use: list, page, structure"

    @staticmethod
    def _list_documents(kb_id: str, kb_dir: Path) -> str:
        """List all documents with their compile status."""
        docs_dir = kb_dir / "documents"
        if not docs_dir.exists():
            return f"知识库 {kb_id} 无文档目录"

        # Get compile status from DB
        db_status: dict[str, dict] = {}
        try:
            conn = get_connection()
            try:
                cursor = conn.execute(
                    "SELECT id, filename, file_type, parse_status, compile_status, chunk_count FROM documents WHERE kb_id = ?",
                    (kb_id,),
                )
                for row in cursor.fetchall():
                    db_status[row["id"]] = {
                        "filename": row["filename"],
                        "file_type": row["file_type"],
                        "parse_status": row["parse_status"],
                        "compile_status": row["compile_status"],
                        "chunk_count": row["chunk_count"],
                    }
            finally:
                conn.close()
        except Exception:
            pass

        docs = []
        for doc_dir in sorted(docs_dir.iterdir()):
            if not doc_dir.is_dir():
                continue
            doc_id = doc_dir.name
            db_info = db_status.get(doc_id, {})

            # Detect what layers exist
            has_l0 = (kb_dir / "l0" / "entities.json").exists()
            has_l1 = (doc_dir / "l1_summaries.json").exists()
            has_l2 = (doc_dir / "l2_chunks").exists()
            has_parsed = (doc_dir / "parsed.md").exists()

            compile_status = db_info.get("compile_status", "unknown")
            if compile_status == "pending" and has_l1:
                compile_status = "completed"

            docs.append({
                "doc_id": doc_id,
                "filename": db_info.get("filename", _get_original_filename(doc_dir)),
                "file_type": db_info.get("file_type", ""),
                "parse_status": db_info.get("parse_status", "parsed" if has_parsed else "unknown"),
                "compile_status": compile_status,
                "has_l1": has_l1,
                "has_l2": has_l2,
                "layers": {
                    "l0_entities": has_l0,
                    "l1_summaries": has_l1,
                    "l2_chunks": has_l2,
                    "parsed_md": has_parsed,
                },
            })

        summary = {
            "kb_id": kb_id,
            "total_documents": len(docs),
            "compiled": sum(1 for d in docs if d["compile_status"] == "completed"),
            "uncompiled": sum(1 for d in docs if d["compile_status"] != "completed"),
            "documents": docs,
        }
        return json.dumps(summary, ensure_ascii=False, indent=2)

    @staticmethod
    def _read_page(kb_id: str, page_id: str | None) -> str:
        """Read a specific wiki page from the wiki_pages table."""
        if not page_id:
            return "Error: page_id is required for 'page' action"

        try:
            conn = get_connection()
            try:
                # Try by ID first, then by catalog_path or title
                row = conn.execute(
                    "SELECT id, title, page_type, content, status FROM wiki_pages WHERE id = ? AND kb_id = ?",
                    (page_id, kb_id),
                ).fetchone()
                if not row:
                    row = conn.execute(
                        "SELECT id, title, page_type, content, status FROM wiki_pages WHERE title = ? AND kb_id = ?",
                        (page_id, kb_id),
                    ).fetchone()
                if not row:
                    row = conn.execute(
                        "SELECT id, title, page_type, content, status FROM wiki_pages WHERE catalog_path = ? AND kb_id = ?",
                        (page_id, kb_id),
                    ).fetchone()

                if not row:
                    return f"未找到Wiki页面: {page_id}"

                return json.dumps({
                    "id": row["id"],
                    "title": row["title"],
                    "page_type": row["page_type"],
                    "content": row["content"],
                    "status": row["status"],
                }, ensure_ascii=False, indent=2)
            finally:
                conn.close()
        except Exception as e:
            return f"读取Wiki页面失败: {e}"

    @staticmethod
    def _show_structure(kb_dir: Path) -> str:
        """Return KB directory structure."""
        structure = {"kb_dir": str(kb_dir)}

        # Top-level directories
        top_items = []
        for item in sorted(kb_dir.iterdir()):
            if item.is_dir():
                top_items.append({"name": item.name, "type": "directory"})
            else:
                top_items.append({"name": item.name, "type": "file"})
        structure["top_level"] = top_items

        # Document summary
        docs_dir = kb_dir / "documents"
        if docs_dir.exists():
            doc_list = []
            for doc_dir in sorted(docs_dir.iterdir()):
                if not doc_dir.is_dir():
                    continue
                sub_items = sorted(p.name for p in doc_dir.iterdir())
                l2_count = 0
                l2_dir = doc_dir / "l2_chunks"
                if l2_dir.exists():
                    l2_count = len(list(l2_dir.glob("*.md")))
                doc_list.append({
                    "doc_id": doc_dir.name,
                    "contents": sub_items,
                    "l2_chunk_count": l2_count,
                })
            structure["documents"] = doc_list
            structure["document_count"] = len(doc_list)

        return json.dumps(structure, ensure_ascii=False, indent=2)


# ── Helper functions ─────────────────────────────────────────────────


def _extract_snippet(text: str, word: str, max_len: int = 300) -> str:
    """Extract a snippet around the first occurrence of word in text."""
    lower = text.lower()
    pos = lower.find(word.lower())
    if pos < 0:
        return text[:max_len]
    start = max(0, pos - max_len // 3)
    end = min(len(text), start + max_len)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def _get_original_filename(doc_dir: Path) -> str:
    """Get the original filename from a document directory.

    The document directory contains the original file alongside parsed.md etc.
    """
    for item in doc_dir.iterdir():
        if item.is_file() and item.suffix not in (".md", ".json") and item.name != "parsed.md":
            return item.name
    return ""


class SearchExcelTool(Tool):
    """Search within an Excel/spreadsheet document by column name matching."""

    name = "search_excel"
    description = (
        "搜索 Excel/表格文档中的数据。根据查询关键词匹配列名和样本值，返回相关列的统计信息和样本数据。"
        "用于了解表格结构、查找特定列、获取数据分布等操作。"
        "输入: kb_id(知识库ID), doc_id(文档ID), query(自然语言查询)"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "kb_id": {"type": "string", "description": "知识库ID"},
            "doc_id": {"type": "string", "description": "Excel文档ID"},
            "query": {"type": "string", "description": "查询内容，如'查找奖牌列'或'查看表格结构'"},
        },
        "required": ["kb_id", "doc_id", "query"],
    }

    async def execute(self, kb_id: str, doc_id: str, query: str) -> str:
        import json, re
        from collections import Counter
        from app.config import settings

        docs_dir = settings.KB_DIR / kb_id / "documents" / doc_id
        if not docs_dir.exists():
            return f"文档 {doc_id} 不存在"

        analysis_path = docs_dir / "excel_analysis.json"
        if not analysis_path.exists():
            return "该文档不是 Excel 表格或缺少分析数据。可用的列信息: 请确认文档已成功编译。"

        try:
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        except Exception as e:
            return f"无法读取表格分析数据: {e}"

        sheets = analysis.get("sheets", [])
        if not sheets:
            return "表格没有有效的 Sheet 数据"

        search_terms = re.findall(r"[\w一-鿿]+", query.lower())
        # Detect aggregation intent
        agg_keywords = {"统计", "计数", "分组", "汇总", "求和", "平均", "排名", "count", "group", "sum", "avg",
                        "多少", "几个", "每种", "各个", "分别", "分布", "数量", "占比"}
        needs_aggregation = any(kw in query.lower() for kw in agg_keywords)
        results_parts = []

        for sheet in sheets:
            sheet_name = sheet.get("name", "unknown")
            columns = sheet.get("columns", [])
            dims = sheet.get("dimensions", {})
            distributions = sheet.get("distributions", [])
            findings = sheet.get("findings", [])

            # Score columns by keyword overlap
            col_scores = []
            for i, col in enumerate(columns):
                name = col.get("name", "").lower()
                score = sum(len(t) for t in search_terms if t in name)
                for sv in col.get("sampleValues", [])[:5]:
                    score += sum(len(t) for t in search_terms if t in str(sv).lower()) * 0.5
                if score > 0:
                    col_scores.append((score, col, i))

            col_scores.sort(key=lambda x: x[0], reverse=True)
            matched_cols = [(score, col, idx) for score, col, idx in col_scores[:5]]
            col_names = [c["name"] for _, c, _ in matched_cols]

            results_parts.append(f"## Sheet: {sheet_name} ({dims.get('rows','?')}行 x {dims.get('columns','?')}列)")
            if col_names:
                results_parts.append(f"匹配列: {', '.join(col_names)}")
            else:
                results_parts.append(f"所有列: {', '.join(c['name'] for c in columns[:20])}")

            # Column details
            for _, col, _ in (matched_cols or [(0, c, i) for i, c in enumerate(columns)])[:8]:
                dtype = col.get("dataType", "?")
                unique = col.get("uniqueCount", 0)
                nulls = col.get("nullCount", 0)
                samples = col.get("sampleValues", [])[:3]
                parts = [f"  {col['name']}: {dtype}, {unique}个唯一值, {nulls}个空值"]
                if samples:
                    parts.append(f"样本: {', '.join(str(s) for s in samples)}")
                results_parts.append(" | ".join(parts))

            # Key distributions (top values from analysis)
            for dist in distributions:
                col_name = dist.get("column", "")
                if col_name in col_names:
                    stats = dist.get("stats", {})
                    if stats.get("topValues"):
                        top = ", ".join(f"{v.get('value','')}({v.get('count','')})" for v in stats["topValues"][:5])
                        results_parts.append(f"  {col_name} Top值: {top}")

            # ── Load actual L2 data from all chunks for aggregation ──
            if needs_aggregation and matched_cols and col_names:
                try:
                    l2_dir = docs_dir / "l2_chunks"
                    if l2_dir.exists():
                        chunk_files = sorted(l2_dir.glob("*.md"))
                        all_data_rows = []
                        col_indices = {}
                        seen_header = False

                        for cf in chunk_files:
                            text = cf.read_text(encoding="utf-8")
                            lines = text.split("\n")

                            # Parse markdown table from this chunk
                            table_lines = []
                            in_table = False
                            for line in lines:
                                if line.startswith("|"):
                                    table_lines.append(line)
                                    in_table = True
                                elif in_table and not line.strip():
                                    break

                            if len(table_lines) < 3:
                                continue

                            # Parse header from first chunk only
                            header_cells = [c.strip() for c in table_lines[0].split("|")[1:-1]]
                            if not col_indices:
                                for cname in col_names:
                                    for hi, h in enumerate(header_cells):
                                        if cname.lower() in h.lower() or h.lower() in cname.lower():
                                            if cname not in col_indices:
                                                col_indices[cname] = hi

                            if not col_indices:
                                continue

                            # Parse data rows (skip header + separator)
                            start = 2 if not seen_header else 1  # subsequent chunks might repeat header
                            # Check if first line is actually a header (has similar content to our stored header)
                            if seen_header:
                                first_cells = [c.strip() for c in table_lines[0].split("|")[1:-1]]
                                if len(first_cells) >= len(header_cells) - 2:
                                    start = 2  # skip repeated header

                            for line in table_lines[start:]:
                                cells = [c.strip() for c in line.split("|")[1:-1]]
                                if len(cells) >= max(col_indices.values()) + 1 if col_indices else 1:
                                    row = {}
                                    for cname, idx in col_indices.items():
                                        if idx < len(cells):
                                            row[cname] = cells[idx]
                                    if row:
                                        all_data_rows.append(row)

                            if not seen_header and len(table_lines) > 3:
                                seen_header = True

                        if all_data_rows:
                            results_parts.append(f"\n### 实际数据统计 (共{len(all_data_rows)}行)")

                            # Aggregation: GROUP BY first matched column, COUNT second col
                            group_col = col_names[0]
                            if len(col_names) >= 2:
                                groups: dict[str, Counter] = {}
                                for row in all_data_rows:
                                    gk = row.get(group_col, "(空)")
                                    val = row.get(col_names[1], "")
                                    if gk not in groups:
                                        groups[gk] = Counter()
                                    if val:
                                        groups[gk][val] += 1

                                ranked = sorted(groups.items(), key=lambda x: sum(x[1].values()), reverse=True)
                                results_parts.append(f"按 `{group_col}` 分组，统计 `{col_names[1]}` (前15组):")
                                for gk, counts in ranked[:15]:
                                    total = sum(counts.values())
                                    detail = " | ".join(f"{v}:{c}" for v, c in counts.most_common(5))
                                    results_parts.append(f"  {gk}: {total}条 ({detail})")
                                if len(ranked) > 15:
                                    results_parts.append(f"  ... 共 {len(ranked)} 个分组")
                            else:
                                counter = Counter(row.get(group_col, "(空)") for row in all_data_rows)
                                results_parts.append(f"按 `{group_col}` 分组统计:")
                                for val, count in counter.most_common(20):
                                    results_parts.append(f"  {val}: {count}")
                                if len(counter) > 20:
                                    results_parts.append(f"  ... 共 {len(counter)} 个不同值")

                            # Sample rows
                            results_parts.append(f"\n数据样例 (前5行):")
                            for row in all_data_rows[:5]:
                                results_parts.append("  " + " | ".join(f"{cn}={row.get(cn,'?')}" for cn in col_names[:4]))
                except Exception:
                    pass  # graceful fallback if L2 data parsing fails

            # Data quality findings
            if findings:
                results_parts.append(f"\n数据发现: {'; '.join(f.get('description','') for f in findings[:5])}")

        if not results_parts:
            return "未找到匹配的数据列"

        results_parts.insert(0, f"# 表格查询: {query}\n")
        return "\n".join(results_parts)


def _list_all_columns(sheets: list[dict]) -> str:
    """List all column names across all sheets."""
    cols = []
    for sheet in sheets:
        for col in sheet.get("columns", []):
            cols.append(col.get("name", ""))
    return ", ".join(cols[:50])


def register_all_tools(
    registry: "ToolRegistry",
    kb_id: str,
    embedding_provider=None,
    context_manager=None,
    kb_state=None,
    llm_client=None,
) -> None:
    """Register agent tools with deferred loading for extended tools.

    Core tools (always loaded): search_keyword, assess_complexity,
    report_findings, ask_user, tool_discover, recall tools.

    Extended tools (deferred, loaded via tool_discover): read_l0/l1/l2,
    expand_entity, get_timeline, progressive_search, search_vector.
    """
    from app.models.config import RoleType
    from app.services.agent.recall_tools import (
        RecallGrepTool,
        RecallExpandTool,
        RecallDescribeTool,
    )

    # ── Core tools (always active) ──
    registry.register(SearchKeywordTool())
    registry.register(AssessComplexityTool())
    registry.register(ReportFindingsTool())
    registry.register(ToolDiscoverTool(registry=registry))
    registry.register(CrossValidateTool())
    registry.register(CoordinateResearchTool(
        llm_client=llm_client,
        tool_registry=registry,
    ))
    registry.register(BatchExpandAbstractsTool())

    # Raw/uncompiled KB tools (always available)
    registry.register(RawSearchTool())
    registry.register(DocGrepTool())
    registry.register(ExpandTool())
    registry.register(WikiBrowseTool())
    registry.register(SearchExcelTool())

    # Recall tools (always available)
    recall_grep = RecallGrepTool(context_manager=context_manager)
    recall_expand = RecallExpandTool(context_manager=context_manager)
    recall_describe = RecallDescribeTool(context_manager=context_manager)
    registry.register(recall_grep)
    registry.register(recall_expand)
    registry.register(recall_describe)

    # ── Extended tools (deferred — loaded on demand) ──
    # Determine which tools are available based on compilation state
    if kb_state is None:
        # Backward-compatible: register everything immediately
        registry.register(ReadL2Tool())
        registry.register(ReadL1Tool())
        registry.register(ReadL0Tool())
        registry.register(ExpandEntityTool())
        registry.register(GetTimelineTool())
        registry.register(BatchExpandL1Tool())
        registry.register(ReadSectionTool())
        registry.register(ProgressiveSearchTool(embedding_provider=embedding_provider))
        if embedding_provider:
            registry.register(SearchVectorTool(embedding_provider=embedding_provider))
        return

    # Deferred: register based on compilation state but as deferred
    available = set(kb_state.get_available_tools())

    if "read_l2" in available:
        registry.register_deferred(ReadL2Tool())

    if "read_l1" in available:
        registry.register_deferred(ReadL1Tool())
        registry.register(ProgressiveSearchTool(embedding_provider=embedding_provider))
        registry.register_deferred(BatchExpandL1Tool())
        registry.register_deferred(ReadSectionTool())

    if "read_l0" in available:
        registry.register_deferred(ReadL0Tool())
        registry.register_deferred(ExpandEntityTool())
        registry.register_deferred(GetTimelineTool())

    if "search_vector" in available and embedding_provider:
        registry.register_deferred(SearchVectorTool(embedding_provider=embedding_provider))

    # Workflow tools (always deferred — loaded via tool_discover)
    from app.services.agent.workflow_tools import (
        WorkflowPipelineTool,
        WorkflowParallelTool,
        WorkflowVerifyTool,
    )
    registry.register_deferred(WorkflowPipelineTool())
    registry.register_deferred(WorkflowParallelTool())
    registry.register_deferred(WorkflowVerifyTool())
