from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .base import ToolAdapter
from ..models import ToolDefinition, ToolRequest

if TYPE_CHECKING:
    from ..service import ToolExecutionContext


_ALLOWED_SYSTEM_TOOLS = {"system.echo", "system.health_read"}


class SystemToolAdapter(ToolAdapter):
    def supports(self, tool_definition: ToolDefinition) -> bool:
        return tool_definition.tool_name in _ALLOWED_SYSTEM_TOOLS and tool_definition.connector_name == "system"

    def execute_tool(
        self,
        tool_definition: ToolDefinition,
        request: ToolRequest,
        context: ToolExecutionContext,
    ) -> dict[str, Any]:
        if tool_definition.tool_name == "system.echo":
            return self._echo(tool_definition, request, context)
        if tool_definition.tool_name == "system.health_read":
            return self._health_read(tool_definition, request, context)
        raise ValueError("unsupported system tool")

    @staticmethod
    def _echo(
        tool_definition: ToolDefinition,
        request: ToolRequest,
        context: ToolExecutionContext,
    ) -> dict[str, Any]:
        payload = request.payload if isinstance(request.payload, dict) else {}
        return {
            "tool_name": tool_definition.tool_name,
            "action": tool_definition.action,
            "read_only": True,
            "echoed_payload": payload,
            "context": {
                "command_id": context.command_id,
                "agent_id": context.agent_id,
                "run_id": context.run_id,
                "correlation_id": context.correlation_id,
            },
        }

    @staticmethod
    def _health_read(
        tool_definition: ToolDefinition,
        request: ToolRequest,
        context: ToolExecutionContext,
    ) -> dict[str, Any]:
        _ = request
        return {
            "tool_name": tool_definition.tool_name,
            "action": tool_definition.action,
            "read_only": True,
            "status": "ok",
            "scope": "internal",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "context": {
                "command_id": context.command_id,
                "agent_id": context.agent_id,
                "run_id": context.run_id,
                "correlation_id": context.correlation_id,
            },
        }
