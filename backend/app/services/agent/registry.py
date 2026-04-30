"""Tool Registry for Agent."""

from app.services.agent.tool import Tool


class ToolRegistry:
    """Registry for Agent tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool."""
        self._tools.pop(name, None)

    def get_tool_definitions(self) -> list[dict]:
        """Get all tool definitions in OpenAI format."""
        return [tool.to_openai_tool() for tool in self._tools.values()]

    async def execute(self, name: str, **kwargs) -> str:
        """Execute a tool by name with input validation."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: Tool '{name}' not found. Available: {', '.join(self._tools.keys())}"

        # Validate input via Pydantic model if available
        validated = tool.validate_input(kwargs)
        return await tool.execute(**validated)

    def get_readonly_tools(self) -> list[Tool]:
        """Get all read-only tools (can be executed concurrently)."""
        return [t for t in self._tools.values() if t.is_readonly]

    def list_tools(self) -> list[dict]:
        """List all registered tools."""
        return [
            {"name": t.name, "description": t.description, "readonly": t.is_readonly}
            for t in self._tools.values()
        ]
