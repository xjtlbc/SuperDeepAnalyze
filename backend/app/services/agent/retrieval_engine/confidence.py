"""Confidence level annotation for retrieval results.

Reference: graphify confidence scoring approach
"""

from enum import Enum
from typing import Dict, Any, List


class ConfidenceLevel(str, Enum):
    """Confidence level for retrieval results."""
    EXTRACTED = "EXTRACTED"    # Source code/document explicitly exists (high confidence)
    INFERRED = "INFERRED"      # Reasonable inference (medium confidence)
    AMBIGUOUS = "AMBIGUOUS"    # Uncertain (low confidence)


def calculate_confidence(result: Dict[str, Any], source: str = "") -> ConfidenceLevel:
    """Calculate confidence level for a retrieval result.

    Args:
        result: Retrieval result dict with optional keys:
            - exact_match: bool - if True, high confidence
            - similarity_score: float - vector similarity score (0-1)
            - keyword_score: float - keyword match score
            - is_structured: bool - if from structured data (graph/entity)
        source: Source type identifier (vector, keyword, graph)

    Returns:
        ConfidenceLevel enum value
    """
    # Direct exact match gets highest confidence
    if result.get('exact_match', False):
        return ConfidenceLevel.EXTRACTED

    # Structured data (from knowledge graph) has high confidence
    if result.get('is_structured', False) or source == 'graph':
        return ConfidenceLevel.EXTRACTED

    similarity = result.get('similarity_score', result.get('relevance_score', 0))
    keyword_score = result.get('keyword_score', result.get('score', 0))

    # High similarity vector match
    if similarity > 0.7:
        return ConfidenceLevel.EXTRACTED

    # Medium similarity or good keyword match
    if similarity > 0.5 or keyword_score > 0.6:
        return ConfidenceLevel.INFERRED

    # Low matching scores
    if similarity > 0.3 or keyword_score > 0.3:
        return ConfidenceLevel.INFERRED

    # Very low confidence
    return ConfidenceLevel.AMBIGUOUS


def add_confidence_to_results(results: List[Dict[str, Any]], source: str = "") -> List[Dict[str, Any]]:
    """Add confidence level labels to retrieval results.

    Args:
        results: List of retrieval result dicts
        source: Source type identifier

    Returns:
        Results with added 'confidence' field
    """
    for result in results:
        result['confidence'] = calculate_confidence(result, source or result.get('source', ''))
    return results


def get_confidence_distribution(results: List[Dict[str, Any]]) -> Dict[str, int]:
    """Get distribution of confidence levels in results.

    Args:
        results: List of retrieval results with confidence levels

    Returns:
        Dict mapping confidence level to count
    """
    distribution = {level.value: 0 for level in ConfidenceLevel}
    for result in results:
        conf = result.get('confidence', ConfidenceLevel.AMBIGUOUS.value)
        if isinstance(conf, ConfidenceLevel):
            conf = conf.value
        distribution[conf] = distribution.get(conf, 0) + 1
    return distribution


def _to_confidence_level(value: Any) -> ConfidenceLevel:
    """Safely convert a value to ConfidenceLevel, falling back to AMBIGUOUS."""
    if isinstance(value, ConfidenceLevel):
        return value
    if isinstance(value, str):
        upper = value.upper()
        if upper in ConfidenceLevel.__members__:
            return ConfidenceLevel.__members__[upper]
        for member in ConfidenceLevel:
            if member.value == value:
                return member
        return ConfidenceLevel.AMBIGUOUS
    return ConfidenceLevel.AMBIGUOUS


def filter_by_confidence(
    results: List[Dict[str, Any]],
    min_level: ConfidenceLevel = ConfidenceLevel.INFERRED
) -> List[Dict[str, Any]]:
    """Filter results by minimum confidence level.

    Args:
        results: List of retrieval results
        min_level: Minimum acceptable confidence level

    Returns:
        Filtered results meeting minimum confidence
    """
    level_order = {
        ConfidenceLevel.EXTRACTED: 3,
        ConfidenceLevel.INFERRED: 2,
        ConfidenceLevel.AMBIGUOUS: 1,
    }
    min_order = level_order.get(min_level, 2)

    return [
        r for r in results
        if level_order.get(_to_confidence_level(r.get('confidence')), 1) >= min_order
    ]