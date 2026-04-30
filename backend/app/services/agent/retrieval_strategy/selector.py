"""Level selector for progressive disclosure retrieval strategy."""

import math
from typing import Literal

from app.services.agent.retrieval_strategy.complexity import (
    QuestionComplexity,
    assess_complexity,
)


LevelType = Literal['L0', 'L1', 'L2']

# Unified drill-down threshold: drill if normalized relevance < this value
_DRILL_THRESHOLD = 0.4


def normalize_relevance(level: LevelType, raw_score: float, match_count: int = 0) -> float:
    """Normalize relevance scores to a unified 0.0-1.0 scale across all layers.

    Each layer has different scoring characteristics:
      - L0: Based on entity/keyword match count (0..N)
      - L1: FTS5 rank scores (typically -20..0)
      - L2: FAISS cosine similarity (0.0-1.0)

    This function normalizes them to a common scale so thresholds are comparable.
    """
    if level == 'L0':
        # L0: match-count based — sigmoid around 3 matches
        return 1.0 / (1.0 + math.exp(-(match_count - 2.0)))
    elif level == 'L1':
        # L1: FTS5 negative rank scores — sigmoid normalization
        # Typical FTS5 rank scores range from -20 (worst) to 0 (best)
        # Map -10 → ~0.5, -5 → ~0.73, 0 → ~0.88
        return 1.0 / (1.0 + math.exp(-(raw_score + 10.0) / 3.5))
    elif level == 'L2':
        # L2: FAISS cosine similarity — already 0.0-1.0, clamp to ensure
        return max(0.0, min(1.0, raw_score))
    return 0.0


def select_start_level(query: str) -> LevelType:
    """Select the starting retrieval level based on question complexity.

    Args:
        query: The user's question string.

    Returns:
        LevelType: The starting level for retrieval.
            - L0: Global entity graph (for simple questions)
            - L1: Paragraph summaries (for medium questions)
            - L2: Original text chunks (for complex questions)
    """
    complexity = assess_complexity(query)

    mapping = {
        QuestionComplexity.SIMPLE: 'L0',    # Simple: start from global graph
        QuestionComplexity.MEDIUM: 'L1',    # Medium: start from summaries
        QuestionComplexity.COMPLEX: 'L2',   # Complex: go directly to source
    }

    return mapping[complexity]


def should_drill_down(relevance_score: float, threshold: float | None = None) -> bool:
    """Determine if drilling down to next level is needed based on relevance score.

    Args:
        relevance_score: The normalized relevance score from current level retrieval
            (0.0-1.0, already normalized via normalize_relevance).
        threshold: Optional custom threshold. Defaults to _DRILL_THRESHOLD (0.4).

    Returns:
        bool: True if drilling down is recommended, False otherwise.

    Decision logic:
        - relevance < 0.4: Must drill down (insufficient information)
        - relevance >= 0.4: Sufficient information, stop drilling
    """
    t = threshold if threshold is not None else _DRILL_THRESHOLD
    return relevance_score < t


def get_drill_sequence(start_level: LevelType) -> list[LevelType]:
    """Get the drill-down sequence starting from the given level.

    Args:
        start_level: The starting level for retrieval.

    Returns:
        list[LevelType]: The sequence of levels to drill through.
            e.g., ['L1', 'L2'] if starting from L1.
    """
    all_levels: list[LevelType] = ['L0', 'L1', 'L2']
    start_idx = all_levels.index(start_level)
    return all_levels[start_idx:]