"""Phase-aware decision point detection for ask_user triggering.

Replaces purely numerical quality gating with scenario-based triggers
that consider exploration progress, information gain, and specific
decision points where human judgment is genuinely needed.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class DecisionPoint:
    """A specific scenario where the Agent should ask the user for input."""

    scenario: str  # "search_space_large" | "info_saturated" | "contradiction" | "missing_dimension"
    question: str
    options: list[str] = None

    def __post_init__(self):
        if self.options is None:
            self.options = []

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "question": self.question,
            "options": self.options,
        }


class DecisionPointManager:
    """Phase-aware decision point detection.

    Replaces the purely numerical QualityGater with scenario-based triggers
    that consider exploration progress, information gain, and specific
    decision points where human judgment is needed.

    Design principles:
      - Agent should exhaust automated search before asking human
      - Minimum exploration rounds before first ask (default 5)
      - Scenario-specific triggers, not a single numerical threshold
      - Cooldown between asks to avoid spamming
      - Max 3 asks per session
    """

    def __init__(
        self,
        total_docs: int = 1,
        min_exploration_rounds: int = 12,
        max_asks: int = 3,
        cooldown_rounds: int = 5,
        min_docs_read: int = 3,
    ):
        self._total_docs = max(total_docs, 1)
        self._min_exploration_rounds = min_exploration_rounds
        self._min_docs_read = min_docs_read
        self._max_asks = max_asks
        self._cooldown_period = cooldown_rounds
        self._asked_count = 0
        self._cooldown_remaining = 0
        self._last_scenario: Optional[str] = None

    def evaluate(
        self,
        iteration: int,
        entity_count: int,
        relation_count: int,
        docs_with_results: int,
        docs_read_count: int,
        is_saturated: bool,
        contradiction_count: int = 0,
    ) -> Optional[DecisionPoint]:
        """Evaluate whether a decision point has been reached.

        Returns a DecisionPoint if ask_user should fire, or None.
        Checks scenarios in priority order: D2 > D3 > D1 > D4.
        """
        if self._asked_count >= self._max_asks:
            return None

        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return None

        if iteration < self._min_exploration_rounds:
            return None

        # Guard: Agent must have read at least min_docs_read documents before any ask_user
        if docs_read_count < self._min_docs_read:
            return None

        # D2: Information saturation (highest priority — Agent has done its job)
        if is_saturated and iteration >= 10:
            dp = DecisionPoint(
                scenario="info_saturated",
                question=(
                    f"信息趋于饱和——已发现 {entity_count} 个实体、{relation_count} 个关系，"
                    f"最近几轮未发现新信息。是否基于已有信息生成报告？"
                ),
                options=["基于已有信息生成报告", "继续搜索更多信息"],
            )
            self._record_ask("info_saturated")
            return dp

        # D3: Contradictory information
        if contradiction_count >= 2:
            dp = DecisionPoint(
                scenario="contradiction",
                question=(
                    f"发现 {contradiction_count} 处矛盾信息，"
                    f"不同文档对同一事实的描述存在冲突。如何处理这些矛盾？"
                ),
                options=[
                    "优先采信最新文档",
                    "优先采信最相关文档",
                    "列出所有矛盾供人工判断",
                    "忽略矛盾继续分析",
                ],
            )
            self._record_ask("contradiction")
            return dp

        # D1: Search space too large — Agent has read some docs but still many unread
        if docs_with_results > 15 and docs_read_count <= 5 and iteration >= 15:
            dp = DecisionPoint(
                scenario="search_space_large",
                question=(
                    f"发现 {docs_with_results} 份相关文档，"
                    f"目前仅深入读取了 {docs_read_count} 份。"
                    f"是否聚焦某个子集深入分析，还是继续自动读取？"
                ),
                options=[
                    "继续自动读取全部文档",
                    "先读取前10份最高相关性的文档",
                    "由你指定重点文档",
                ],
            )
            self._record_ask("search_space_large")
            return dp

        # D4: Missing critical dimension — entities found but no relationships
        if entity_count >= 5 and relation_count == 0 and docs_read_count >= 3 and iteration >= 12:
            dp = DecisionPoint(
                scenario="missing_dimension",
                question=(
                    f"已发现 {entity_count} 个实体，但尚未发现实体间关系。"
                    f"是否需要我重点搜索特定类型的关系？"
                ),
                options=[
                    "搜索人物-事件关系",
                    "搜索组织-人物关系",
                    "搜索时间线关联",
                    "继续自主搜索",
                ],
            )
            self._record_ask("missing_dimension")
            return dp

        return None

    def _record_ask(self, scenario: str) -> None:
        self._asked_count += 1
        self._cooldown_remaining = self._cooldown_period
        self._last_scenario = scenario

    def get_stats(self) -> dict:
        """Return decision point statistics for observability."""
        return {
            "asks_made": self._asked_count,
            "max_asks": self._max_asks,
            "cooldown_remaining": self._cooldown_remaining,
            "last_scenario": self._last_scenario,
            "min_exploration_rounds": self._min_exploration_rounds,
        }


# Backward-compatible alias for existing imports
QualityGater = DecisionPointManager
