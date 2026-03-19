from __future__ import annotations

from .models import ToolDefinition, ToolRiskLevel
from .registry import ToolRegistry, get_tool_registry


PLACEHOLDER_TOOLS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        tool_name="system.echo",
        connector_name="system",
        action="echo",
        description="Structural placeholder tool for policy and registry validation only.",
        risk_level=ToolRiskLevel.low,
        read_only=True,
        enabled_by_default=False,
        tags=("internal", "placeholder"),
        capability_metadata={"phase": "7a", "external_execution": False},
        audit_category="tool.placeholder",
    ),
    ToolDefinition(
        tool_name="system.health_read",
        connector_name="system",
        action="health_read",
        description="Structural placeholder tool for future safe health-read requests.",
        risk_level=ToolRiskLevel.low,
        read_only=True,
        enabled_by_default=False,
        tags=("internal", "health", "placeholder"),
        capability_metadata={"phase": "7a", "external_execution": False},
        timeout_seconds=5,
        audit_category="tool.placeholder",
    ),
    ToolDefinition(
        tool_name="search.web_search",
        connector_name="search",
        action="web_search",
        description="Bounded read-only web search through the governed search connector.",
        risk_level=ToolRiskLevel.low,
        read_only=True,
        enabled_by_default=False,
        tags=("search", "connector", "read_only"),
        capability_metadata={"phase": "27", "external_execution": True},
        timeout_seconds=8,
        audit_category="tool.connector",
    ),
)


def register_placeholder_tools(registry: ToolRegistry | None = None) -> ToolRegistry:
    target = registry or get_tool_registry()
    for tool in PLACEHOLDER_TOOLS:
        if not target.has_tool(tool.tool_name):
            target.register_tool(tool)
    return target
