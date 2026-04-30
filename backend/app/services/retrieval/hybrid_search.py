"""Hybrid retrieval engine: vector search + FTS5 keyword search + RRF fusion."""

import json
from app.models.database import get_connection
from app.services.retrieval.faiss_index import FAISSIndexManager
from app.services.agent.retrieval_engine.confidence import (
    ConfidenceLevel,
    add_confidence_to_results,
)
from app.services.agent.retrieval_engine.rrf import (
    RRFConfig,
    reciprocal_rank_fusion,
)


class KeywordSearch:
    """SQLite FTS5 keyword search."""

    @staticmethod
    def search(query: str, doc_id: str | None = None, top_k: int = 10) -> list[dict]:
        """Search FTS5 index for keyword matches."""
        conn = get_connection()
        try:
            if doc_id:
                cursor = conn.execute(
                    """SELECT doc_id, chunk_id, content, rank
                       FROM fts_content
                       WHERE fts_content MATCH ? AND doc_id = ?
                       ORDER BY rank
                       LIMIT ?""",
                    (query, doc_id, top_k),
                )
            else:
                cursor = conn.execute(
                    """SELECT doc_id, chunk_id, content, rank
                       FROM fts_content
                       WHERE fts_content MATCH ?
                       ORDER BY rank
                       LIMIT ?""",
                    (query, top_k),
                )
            rows = cursor.fetchall()
            return [
                {
                    "doc_id": row["doc_id"],
                    "chunk_id": row["chunk_id"],
                    "content": row["content"][:200],
                    "score": row["rank"],
                }
                for row in rows
            ]
        finally:
            conn.close()


def rrf_merge(results_a: list[dict], results_b: list[dict], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion: merge two ranked result lists."""
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for rank, item in enumerate(results_a, 1):
        key = f"{item['doc_id']}:{item.get('chunk_id', '')}"
        scores[key] = scores.get(key, 0) + 1 / (k + rank)
        items[key] = item

    for rank, item in enumerate(results_b, 1):
        key = f"{item['doc_id']}:{item.get('chunk_id', '')}"
        scores[key] = scores.get(key, 0) + 1 / (k + rank)
        if key not in items:
            items[key] = item

    # Sort by RRF score descending
    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [items[key] | {"rrf_score": score} for key, score in merged]


def hybrid_search(
    query: str,
    kb_id: str,
    top_k: int = 10,
    rrf_k: int = 60,
    doc_id: str | None = None,
    add_confidence: bool = True,
    embedding_provider=None,
) -> list[dict]:
    """Combined hybrid search: vector + keyword + RRF fusion.

    Args:
        query: Search query string
        kb_id: Knowledge base ID
        top_k: Number of results to return
        rrf_k: RRF constant parameter
        doc_id: Optional document ID to limit search scope
        add_confidence: Whether to add confidence labels to results
        embedding_provider: Optional LLM client for computing query embeddings

    Returns:
        Merged and ranked search results with confidence levels
    """
    # Vector search
    vec_results = []
    if embedding_provider is not None:
        try:
            import asyncio
            query_embedding = asyncio.get_event_loop().run_until_complete(
                embedding_provider.embed([query])
            )
            if query_embedding:
                faiss_mgr = FAISSIndexManager()
                index = faiss_mgr.load_index(kb_id, "l2")
                if index is not None:
                    vec_results_raw = faiss_mgr.search(kb_id, "l2", query_embedding[0], top_k=top_k * 2)
                    if vec_results_raw:
                        vec_results = vec_results_raw
        except Exception as e:
            import logging
            logging.getLogger("app.retrieval.hybrid_search").warning("Vector search failed: %s", e)

    # Keyword search
    kw_results = KeywordSearch.search(query, doc_id=doc_id, top_k=top_k * 2)

    # RRF merge (when both results available)
    merged = rrf_merge(vec_results, kw_results, k=rrf_k)

    # Add confidence labels if requested
    if add_confidence:
        merged = add_confidence_to_results(merged, source="hybrid")

    return merged[:top_k]


def hybrid_search_with_graph(
    query: str,
    kb_id: str,
    vector_results: list[dict] | None = None,
    keyword_results: list[dict] | None = None,
    graph_results: list[dict] | None = None,
    config: RRFConfig | None = None,
    add_confidence: bool = True,
) -> list[dict]:
    """Enhanced hybrid search with graph results integration.

    Args:
        query: Search query string (for keyword search if not provided)
        kb_id: Knowledge base ID
        vector_results: Pre-computed vector search results
        keyword_results: Pre-computed keyword search results
        graph_results: Pre-computed graph search results
        config: RRF configuration
        add_confidence: Whether to add confidence labels

    Returns:
        Merged and ranked results with confidence levels
    """
    if config is None:
        config = RRFConfig()

    # Perform keyword search if results not provided
    if keyword_results is None and query:
        keyword_results = KeywordSearch.search(query, top_k=config.top_k * 2)

    # Merge using RRF
    merged = reciprocal_rank_fusion(
        vector_results=vector_results or [],
        keyword_results=keyword_results or [],
        graph_results=graph_results,
        config=config,
    )

    # Add confidence labels
    if add_confidence:
        merged = add_confidence_to_results(merged, source="hybrid")

    return merged
