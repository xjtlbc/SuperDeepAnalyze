"""AgentContext — unified dependency injection for the Agent Loop.

Inspired by OpenHarness's QueryContext pattern. Bundles all dependencies
the agent loop needs into one injectable object, replacing ad-hoc local
variable initialization.
"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

# ask_user_callback: called when Agent needs user input. The callback receives
# {"question": str, "options": list[str], "scenario": str, "event_id": str}
# and must return the user's answer as a string. Implementation is responsible
# for suspending the loop (e.g. via asyncio.Future) until the user responds.
AskUserCallback = Callable[[dict], Awaitable[str]]

# stream_callback: called for real-time streaming events.
# Signature: (event_type: str, content: str) -> None
StreamCallback = Callable[[str, str], Awaitable[None]]


@dataclass
class AgentContext:
    """Immutable-ish context bundle for AgentLoop.run()."""

    kb_id: str
    session_id: str

    # Model routing — must support .chat() and optionally .stream_chat()
    model_router: Any

    # Tool registry — must support .get_tool_definitions(), .execute()
    tool_registry: Any

    # Embedding provider for vector search tools (optional)
    embedding_provider: Any = None

    # Loop control
    max_iterations: int = 50
    context_window: int = 128_000

    # Human-in-the-loop: bidirectional ask_user callback
    ask_user_callback: Optional[AskUserCallback] = None

    # Streaming output: real-time chunk delivery callback
    stream_callback: Optional[StreamCallback] = None

    # Historical messages from previous turns in this session (for multi-turn memory)
    history_messages: list[dict] = field(default_factory=list)

    # KB compilation state for graceful degradation (optional)
    kb_state: Any = None

    # Extra metadata for observability
    metadata: dict = field(default_factory=dict)

    @property
    def has_interactive_mode(self) -> bool:
        """Whether bidirectional user interaction is available."""
        return self.ask_user_callback is not None
