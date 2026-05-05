"""Tool Registry for Agent."""

from app.services.agent.tool import Tool


class ToolRegistry:
    """Registry for Agent tools with deferred loading support."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._deferred: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def register_deferred(self, tool: Tool) -> None:
        """Register a tool as deferred (not included in initial definitions).

        Available via tool_discover for on-demand loading.
        """
        self._deferred[tool.name] = tool

    def discover_tools(self, names: list[str] | None = None) -> list[str]:
        """Load deferred tools into the active registry.

        If names is None, loads all deferred tools.
        Returns list of newly loaded tool names.
        """
        loaded = []
        to_load = names if names else list(self._deferred.keys())
        for name in to_load:
            if name in self._deferred and name not in self._tools:
                self._tools[name] = self._deferred.pop(name)
                loaded.append(name)
        return loaded

    def get_deferred_tool_names(self) -> list[str]:
        """Return names of tools available for deferred loading."""
        return list(self._deferred.keys())

    def unregister(self, name: str) -> None:
        """Unregister a tool."""
        self._tools.pop(name, None)

    def get_tool_definitions(self) -> list[dict]:
        """Get all active tool definitions in OpenAI format."""
        return [tool.to_openai_tool() for tool in self._tools.values()]

    async def execute(self, name: str, **kwargs) -> str:
        """Execute a tool by name with input validation."""
        # Auto-load deferred tool if needed
        if name not in self._tools and name in self._deferred:
            self.discover_tools([name])

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
