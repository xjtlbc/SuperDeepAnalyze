"""State definitions for user interaction."""

from enum import Enum


class InteractionState(str, Enum):
    """Interaction state indicating whether agent needs user input."""
    CONTINUE = "continue"           # Continue execution
    NEEDS_CONTEXT = "needs_context" # Need user to provide more information
    BLOCKED = "blocked"             # Cannot continue, requires human intervention
    CONFIRMING = "confirming"       # Waiting for user to confirm key decision
    CLARIFYING = "clarifying"       # Clarifying ambiguity


class AskUserScenario(str, Enum):
    """Scenario types for asking user questions."""
    INFO_INSUFFICIENT = "info_insufficient"  # Insufficient information
    KEY_DECISION = "key_decision"            # Key decision confirmation
    AMBIGUITY = "ambiguity"                  # Ambiguity clarification