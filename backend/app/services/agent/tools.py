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

# Tools that can be executed in parallel (read-only, no side effects)
READ_ONLY_TOOLS = {
    "search_vector", "search_keyword", "read_l0",
    "read_l1", "read_l2", "expand_entity", "get_timeline",
    "progressive_search", "assess_complexity",
    "recall_grep", "recall_expand", "recall_describe",
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
            search_tasks = [asyncio.to_thread(KeywordSearch.search, query, doc_id, top_k)]
            for sq in rewritten.sub_queries[:2]:
                search_tasks.append(asyncio.to_thread(KeywordSearch.search, sq, doc_id, top_k))
            search_results = await asyncio.gather(*search_tasks)
            for batch in search_results:
                all_results.extend(batch)
        except Exception:
            all_results = KeywordSearch.search(query, doc_id=doc_id, top_k=top_k)

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
                            if entity["name"] in s.get("entities_mentioned", []):
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
                    ]
                    result["timeline"] = matched_timeline[:top_k]
                    matched_count += len(matched_timeline)

            max_relevance = normalize_relevance("L0", 0, match_count=matched_count)

        elif level == "L1":
            # L1: Summaries - use keyword search
            results = KeywordSearch.search(query, top_k=top_k)
            result["summaries"] = results
            if results:
                # Calculate relevance from FTS5 scores using unified normalization
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
                    results = KeywordSearch.search(query, top_k=top_k)
                    result["chunks"] = results
                    if results:
                        max_relevance = 0.3
            else:
                results = KeywordSearch.search(query, top_k=top_k)
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


def register_all_tools(
    registry: "ToolRegistry",
    kb_id: str,
    embedding_provider=None,
    context_manager=None,
) -> None:
    """Register all agent tools into the given registry."""
    from app.models.config import RoleType
    from app.services.agent.recall_tools import (
        RecallGrepTool,
        RecallExpandTool,
        RecallDescribeTool,
    )

    # Read-only tools (no provider needed)
    registry.register(ReadL0Tool())
    registry.register(ReadL1Tool())
    registry.register(ReadL2Tool())
    registry.register(ExpandEntityTool())
    registry.register(GetTimelineTool())
    registry.register(SearchKeywordTool())
    registry.register(AssessComplexityTool())
    registry.register(ProgressiveSearchTool(embedding_provider=embedding_provider))

    # SearchVectorTool needs embedding provider
    if embedding_provider:
        registry.register(SearchVectorTool(embedding_provider=embedding_provider))

    # Recall tools (need context manager for DAG access)
    recall_grep = RecallGrepTool(context_manager=context_manager)
    recall_expand = RecallExpandTool(context_manager=context_manager)
    recall_describe = RecallDescribeTool(context_manager=context_manager)
    registry.register(recall_grep)
    registry.register(recall_expand)
    registry.register(recall_describe)

    # Interactive tools
    # NOTE: AskUserTool is intentionally NOT registered. The DecisionPointManager
    # in loop.py is the sole ask_user trigger — it enforces guard clauses
    # (min_exploration_rounds, min_docs_read) that the LLM cannot bypass.
    # registry.register(AskUserTool())
    registry.register(ReportFindingsTool())
