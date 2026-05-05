"""Agent Loop state machine — LoopPhase, TerminalReason, and LoopState.

Inspired by Claude Code query.ts State object and OpenHarness query.py phases.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LoopPhase(str, Enum):
    """Phases of the Agent reAct loop state machine."""

    INTERPRETING = "interpreting"      # Understanding the query, initial assessment
    PLANNING = "planning"              # Generating search plan based on intent analysis
    SEARCHING = "searching"            # Executing tool calls
    EVALUATING = "evaluating"          # Assessing information quality, deciding next action
    REPORTING = "reporting"            # Generating the final structured report
    WAITING_USER = "waiting_user"      # Paused — waiting for human answer via ask_user
    COMPACTING = "compacting"          # Context compression in progress


class TerminalReason(str, Enum):
    """Reasons the Agent loop terminated."""

    COMPLETED = "completed"              # LLM returned final answer (no tool_calls)
    MAX_ITERATIONS = "max_iterations"    # Hit the iteration limit
    INFO_SATURATED = "info_saturated"    # No new information being discovered
    USER_INTERRUPTED = "user_interrupted"  # User cancelled
    CONTEXT_OVERFLOW = "context_overflow"  # Could not compress context
    ERROR = "error"                      # Unrecoverable error


@dataclass
class LoopState:
    """Mutable state carried across loop iterations."""

    phase: LoopPhase = LoopPhase.INTERPRETING
    messages: list[dict] = field(default_factory=list)
    iteration: int = 0
    tool_calls_log: list[dict] = field(default_factory=list)
    call_history: set[str] = field(default_factory=set)
    consecutive_empty: int = 0
    evidence_map: dict[str, list[dict]] = field(default_factory=dict)
    saturation_prompt_sent: bool = False
    # Intent analysis results
    query_plan: Optional[dict] = None
    # Reflection engine state
    reflection_history: list[dict] = field(default_factory=list)
    last_confidence: float = 0.0
    # Nudge tracking
    _read_nudge_sent: bool = False
    # Stuck detection
    stuck_count: int = 0
    recent_tool_patterns: list[str] = field(default_factory=list)
