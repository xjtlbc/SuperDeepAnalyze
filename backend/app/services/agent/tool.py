"""Tool interface for Agent reAct loop.

Inspired by OpenHarness tools/base.py:BaseTool. Tools define a Pydantic
input_model for automatic schema generation and input validation.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.services.agent.context import AgentContext


class Tool(ABC):
    """Base class for Agent tools with Pydantic schema support.

    Subclasses must define:
      - name: unique tool identifier
      - description: natural-language description for the LLM
      - input_model: Pydantic BaseModel for argument validation (if None, uses
        raw dict passthrough)
      - is_readonly: whether the tool has no side effects (for concurrency)
      - execute(**kwargs): the tool implementation
    """

    name: str = ""
    description: str = ""
    is_readonly: bool = True

    # Pydantic model class for input validation. If None, input_schema dict is
    # used as a fallback for OpenAI function definition generation only.
    input_model: Optional[type[BaseModel]] = None

    # Legacy input_schema dict for tools that haven't migrated to Pydantic yet.
    input_schema: dict = {}

    # Reference to the current AgentContext, set before each execution.
    _context: Optional["AgentContext"] = None

    def set_context(self, ctx: "AgentContext") -> None:
        """Set the AgentContext for this execution cycle."""
        self._context = ctx

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        """Execute the tool with given parameters."""
        ...

    def validate_input(self, raw_input: dict) -> dict:
        """Validate and coerce raw input dict using the Pydantic input_model.

        Returns the validated dict (via model_dump) or the raw input unchanged
        if no input_model is defined.
        """
        if self.input_model is None:
            return raw_input
        instance = self.input_model.model_validate(raw_input)
        return instance.model_dump()

    def to_openai_tool(self) -> dict:
        """Convert to OpenAI function calling format.

        If input_model is defined, the schema is auto-generated from the
        Pydantic model. Otherwise, falls back to the legacy input_schema dict.
        """
        if self.input_model is not None:
            schema = self.input_model.model_json_schema()
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": schema,
                },
            }
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }
