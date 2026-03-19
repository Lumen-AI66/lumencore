from __future__ import annotations

from .exceptions import DuplicateToolRegistrationError, InvalidToolDefinitionError, UnknownToolError
from .models import ToolDefinition


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register_tool(self, tool: ToolDefinition) -> ToolDefinition:
        if not isinstance(tool, ToolDefinition):
            raise InvalidToolDefinitionError("tool must be a ToolDefinition instance")
        if tool.tool_name in self._tools:
            raise DuplicateToolRegistrationError(f"tool '{tool.tool_name}' is already registered")
        self._tools[tool.tool_name] = tool
        return tool

    def has_tool(self, tool_name: str) -> bool:
        return tool_name.strip().lower() in self._tools

    def get_tool(self, tool_name: str) -> ToolDefinition:
        normalized = tool_name.strip().lower()
        try:
            return self._tools[normalized]
        except KeyError as exc:
            raise UnknownToolError(f"tool '{normalized}' is not registered") from exc

    def list_tools(self) -> list[ToolDefinition]:
        return sorted(self._tools.values(), key=lambda item: item.tool_name)

    def list_tools_by_connector(self, connector_name: str) -> list[ToolDefinition]:
        normalized = connector_name.strip().lower()
        return [tool for tool in self.list_tools() if tool.connector_name == normalized]

    def clear(self) -> None:
        self._tools.clear()


_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    return _registry
