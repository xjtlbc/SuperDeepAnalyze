"""Reciprocal Rank Fusion (RRF) for hybrid search result merging.

RRF formula: score(d) = sum(1 / (k + rank(d))) for each ranking list
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class RRFConfig:
    """RRF fusion configuration with 4-signal support."""
    vector_weight: float = 3.0     # Signal 1: Semantic vector search
    keyword_weight: float = 2.0    # Signal 2: Keyword/FTS5 search
    graph_weight: float = 4.0      # Signal 3: Entity graph relations (highest)
    affinity_weight: float = 1.5   # Signal 4: Entity affinity/co-occurrence
    k: int = 60  # RRF constant
    top_k: int = 20  # Number of results to return


def reciprocal_rank_fusion(
    vector_results: List[Dict[str, Any]],
    keyword_results: List[Dict[str, Any]],
    graph_results: Optional[List[Dict[str, Any]]] = None,
    affinity_results: Optional[List[Dict[str, Any]]] = None,
    config: Optional[RRFConfig] = None
) -> List[Dict[str, Any]]:
    """Fuse vector, keyword, graph, and affinity retrieval results using RRF.

    Args:
        vector_results: Results from vector similarity search
        keyword_results: Results from keyword/full-text search
        graph_results: Results from knowledge graph search (optional)
        affinity_results: Results from entity affinity search (optional)
        config: RRF configuration

    Returns:
        Merged and ranked results with RRF scores
    """
    if config is None:
        config = RRFConfig()

    # Accumulate RRF scores per document
    scores: Dict[str, float] = {}
    result_data: Dict[str, Dict[str, Any]] = {}

    def get_doc_id(result: Dict[str, Any], idx: int) -> str:
        """Extract document ID from result."""
        return result.get('id') or result.get('chunk_id') or f"doc_{idx}"

    def merge_result_data(doc_id: str, result: Dict[str, Any], source: str) -> None:
        """Merge result data, preserving all fields."""
        if doc_id not in result_data:
            result_data[doc_id] = result.copy()
        else:
            existing = result_data[doc_id]
            if 'vector_score' not in existing and source == 'vector':
                existing['vector_score'] = result.get('score', result.get('similarity_score', 0))
            if 'keyword_score' not in existing and source == 'keyword':
                existing['keyword_score'] = result.get('score', 0)
            if 'graph_score' not in existing and source == 'graph':
                existing['graph_score'] = result.get('score', 0)
            if 'affinity_score' not in existing and source == 'affinity':
                existing['affinity_score'] = result.get('score', 0)

    # Process vector results (Signal 1)
    for rank, result in enumerate(vector_results, 1):
        doc_id = get_doc_id(result, rank)
        scores[doc_id] = scores.get(doc_id, 0) + config.vector_weight / (config.k + rank)
        merge_result_data(doc_id, result, 'vector')

    # Process keyword results (Signal 2)
    for rank, result in enumerate(keyword_results, 1):
        doc_id = get_doc_id(result, rank)
        scores[doc_id] = scores.get(doc_id, 0) + config.keyword_weight / (config.k + rank)
        merge_result_data(doc_id, result, 'keyword')

    # Process graph results (Signal 3)
    if graph_results:
        for rank, result in enumerate(graph_results, 1):
            entity_id = get_doc_id(result, rank)
            scores[entity_id] = scores.get(entity_id, 0) + config.graph_weight / (config.k + rank)
            merge_result_data(entity_id, result, 'graph')

    # Process affinity results (Signal 4)
    if affinity_results:
        for rank, result in enumerate(affinity_results, 1):
            doc_id = get_doc_id(result, rank)
            scores[doc_id] = scores.get(doc_id, 0) + config.affinity_weight / (config.k + rank)
            merge_result_data(doc_id, result, 'affinity')

    # Sort by RRF score descending
    ranked_ids = sorted(
        scores.keys(),
        key=lambda x: scores[x],
        reverse=True
    )

    # Assemble final results
    final_results = []
    for doc_id in ranked_ids[:config.top_k]:
        result = result_data.get(doc_id, {})
        result['rrf_score'] = scores[doc_id]
        result['id'] = doc_id
        final_results.append(result)

    return final_results


def weighted_rerank(
    results: List[Dict[str, Any]],
    recency_boost: float = 0.1,
    authority_boost: float = 0.1,
    diversity_penalty: float = 0.05
) -> List[Dict[str, Any]]:
    """Apply weighted re-ranking to fused results.

    Args:
        results: RRF fused results
        recency_boost: Boost for recent documents (0-1)
        authority_boost: Boost for authoritative sources (0-1)
        diversity_penalty: Penalty for similar consecutive results (0-1)

    Returns:
        Re-ranked results
    """
    if not results:
        return results

    reranked = []
    seen_content_hashes = set()

    for result in results:
        score = result.get('rrf_score', 0)

        # Apply recency boost
        if result.get('is_recent', False):
            score *= (1 + recency_boost)

        # Apply authority boost
        if result.get('is_authoritative', False):
            score *= (1 + authority_boost)

        # Apply diversity penalty
        content_hash = hash(result.get('content', '')[:100])
        if content_hash in seen_content_hashes and diversity_penalty > 0:
            score *= (1 - diversity_penalty)

        seen_content_hashes.add(content_hash)
        result['final_score'] = score
        reranked.append(result)

    # Re-sort by final score
    reranked.sort(key=lambda x: x.get('final_score', 0), reverse=True)
    return reranked


def calculate_rrf_metrics(
    vector_count: int,
    keyword_count: int,
    graph_count: int,
    merged_count: int
) -> Dict[str, Any]:
    """Calculate RRF fusion metrics.

    Args:
        vector_count: Number of vector results
        keyword_count: Number of keyword results
        graph_count: Number of graph results
        merged_count: Number of merged unique results

    Returns:
        Metrics dict with overlap and coverage info
    """
    total_input = vector_count + keyword_count + graph_count
    overlap_ratio = 1 - (merged_count / total_input) if total_input > 0 else 0

    return {
        "vector_count": vector_count,
        "keyword_count": keyword_count,
        "graph_count": graph_count,
        "merged_count": merged_count,
        "overlap_ratio": overlap_ratio,
        "deduplication_rate": overlap_ratio,
    }