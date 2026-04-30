"""AskUser manager for intelligent question generation."""

from typing import Optional, List, Any

from .states import InteractionState, AskUserScenario
from .scenarios import (
    check_info_sufficient,
    check_ambiguity,
    should_confirm_decision,
    detect_blocked_scenario,
)


class AskUserManager:
    """Manager for agent-to-user question scenarios.

    This class manages when and how an agent should ask the user questions,
    including scenario detection, question formatting, and state tracking.
    """

    def __init__(self):
        """Initialize the AskUserManager."""
        self.pending_question: Optional[str] = None
        self.options: Optional[List[str]] = None
        self.scenario: Optional[AskUserScenario] = None
        self._context: dict = {}

    def evaluate(
        self,
        query: str,
        search_results: list,
        analysis: str = None,
        error_context: str = None
    ) -> InteractionState:
        """Evaluate current state and decide if user question is needed.

        Args:
            query: User's query string
            search_results: List of search result dicts
            analysis: Optional current analysis content
            error_context: Optional error context for blocked scenarios

        Returns:
            InteractionState indicating the current interaction state
        """
        # Clear previous state
        self.clear()

        # 1. Check for blocked scenarios first (highest priority)
        if error_context:
            state, hint = detect_blocked_scenario(query, error_context)
            if state == InteractionState.BLOCKED:
                self.pending_question = hint
                self._context['blocked'] = True
                return state

        # 2. Check if information is sufficient
        state, hint = check_info_sufficient(query, search_results)
        if state != InteractionState.CONTINUE:
            self.pending_question = hint
            self.scenario = AskUserScenario.INFO_INSUFFICIENT
            return state

        # 3. Check for ambiguity
        state, hint, options = check_ambiguity(query)
        if state != InteractionState.CONTINUE:
            self.pending_question = hint
            self.options = options
            self.scenario = AskUserScenario.AMBIGUITY
            return state

        # 4. Check if decision confirmation is needed
        if analysis:
            state, hint = should_confirm_decision(query, analysis)
            if state != InteractionState.CONTINUE:
                self.pending_question = hint
                self.scenario = AskUserScenario.KEY_DECISION
                return state

        return InteractionState.CONTINUE

    def get_question(self) -> Optional[str]:
        """Get the pending question content.

        Returns:
            The pending question string or None
        """
        return self.pending_question

    def get_options(self) -> Optional[List[str]]:
        """Get the multiple choice options.

        Returns:
            List of option strings or None
        """
        return self.options

    def get_scenario(self) -> Optional[AskUserScenario]:
        """Get the current scenario type.

        Returns:
            Current AskUserScenario or None
        """
        return self.scenario

    def get_state(self) -> InteractionState:
        """Get the current interaction state.

        Returns:
            Current InteractionState
        """
        if self._context.get('blocked'):
            return InteractionState.BLOCKED
        if self.pending_question:
            if self.scenario == AskUserScenario.KEY_DECISION:
                return InteractionState.CONFIRMING
            elif self.scenario == AskUserScenario.AMBIGUITY:
                return InteractionState.CLARIFYING
            else:
                return InteractionState.NEEDS_CONTEXT
        return InteractionState.CONTINUE

    def clear(self) -> None:
        """Clear pending question and reset state."""
        self.pending_question = None
        self.options = None
        self.scenario = None
        self._context = {}

    def set_context(self, key: str, value: Any) -> None:
        """Set a context value.

        Args:
            key: Context key
            value: Context value
        """
        self._context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get a context value.

        Args:
            key: Context key
            default: Default value if key not found

        Returns:
            The context value or default
        """
        return self._context.get(key, default)

    def format_ask_user_prompt(self) -> str:
        """Format the ask_user tool prompt content.

        Returns:
            Formatted prompt string or empty string if no pending question
        """
        if not self.pending_question:
            return ""

        prompt = self.pending_question
        if self.options:
            prompt += "\n可选答案：\n" + "\n".join(
                [f"{i+1}. {opt}" for i, opt in enumerate(self.options)]
            )

        return prompt

    def is_interaction_needed(self) -> bool:
        """Check if user interaction is needed.

        Returns:
            True if pending question exists, False otherwise
        """
        return self.pending_question is not None

    def create_ask_response(self) -> dict:
        """Create a structured response for ask_user tool.

        Returns:
            Dict with question, options, and scenario info
        """
        return {
            "question": self.pending_question,
            "options": self.options,
            "scenario": self.scenario.value if self.scenario else None,
            "state": self.get_state().value,
        }