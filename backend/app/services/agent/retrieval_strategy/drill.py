"""Drill-down logic for progressive disclosure retrieval strategy."""

from typing import List, Optional
from dataclasses import dataclass, field

from app.services.agent.retrieval_strategy.selector import (
    LevelType,
    should_drill_down,
    get_drill_sequence,
)


@dataclass
class DrillResult:
    """Result from a single level retrieval."""
    level: LevelType
    result: dict
    relevance: float


@dataclass
class DrillManager:
    """Manage the iterative drill-down retrieval process.

    This class orchestrates the progressive disclosure strategy by
    tracking the current retrieval level and determining when to
    drill down to more detailed levels.

    Attributes:
        start_level: The starting retrieval level.
        sequence: The ordered sequence of levels to drill through.
        current_idx: Current position in the drill sequence.
        results: Accumulated results from each level.
        drill_log: Human-readable log of the drill process.
    """
    start_level: LevelType
    sequence: List[LevelType] = field(default_factory=list)
    current_idx: int = 0
    results: List[DrillResult] = field(default_factory=list)
    drill_log: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Initialize the drill sequence after dataclass init."""
        if not self.sequence:
            self.sequence = get_drill_sequence(self.start_level)

    def current_level(self) -> LevelType:
        """Get the current retrieval level.

        Returns:
            LevelType: The current level in the drill sequence.
        """
        return self.sequence[self.current_idx]

    def record_result(self, result: dict, relevance: float) -> bool:
        """Record retrieval result and decide if drilling is needed.

        Args:
            result: The retrieval result from the current level.
            relevance: The relevance score (0-1) for this result.

        Returns:
            bool: True if should continue drilling, False if done.
        """
        level = self.current_level()
        self.results.append(DrillResult(
            level=level,
            result=result,
            relevance=relevance
        ))
        self.drill_log.append(f"{level}: relevance={relevance:.2f}")

        # Decide if we need to drill down
        if should_drill_down(relevance) and self.can_drill_down():
            self.current_idx += 1
            return True
        return False

    def can_drill_down(self) -> bool:
        """Check if we can drill down to the next level.

        Returns:
            bool: True if there's a deeper level available.
        """
        return self.current_idx < len(self.sequence) - 1

    def get_final_results(self) -> List[dict]:
        """Get all accumulated retrieval results.

        Returns:
            List[dict]: List of results with level and relevance info.
        """
        return [
            {
                'level': r.level,
                'result': r.result,
                'relevance': r.relevance
            }
            for r in self.results
        ]

    def get_drill_path(self) -> List[str]:
        """Get the human-readable drill path.

        Returns:
            List[str]: List of log entries showing the drill progression.
        """
        return self.drill_log.copy()

    def get_best_result(self) -> Optional[dict]:
        """Get the result with the highest relevance score.

        Returns:
            Optional[dict]: The best result with level info, or None if no results.
        """
        if not self.results:
            return None

        best = max(self.results, key=lambda r: r.relevance)
        return {
            'level': best.level,
            'result': best.result,
            'relevance': best.relevance
        }

    def get_summary(self) -> dict:
        """Get a summary of the drill process.

        Returns:
            dict: Summary containing levels searched, best result, and path.
        """
        return {
            'start_level': self.start_level,
            'levels_searched': [r.level for r in self.results],
            'drill_path': self.drill_log,
            'best_result': self.get_best_result(),
            'total_results': len(self.results),
        }