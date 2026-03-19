from __future__ import annotations

from dataclasses import dataclass

from ..config import load_yaml_config
from ..connectors.base.registry import get_connector
from ..connectors.policy.agent_connector_permissions import evaluate_agent_connector_permission
from ..connectors.policy.connector_policy import evaluate_connector_policy
from .models import ToolDefinition, ToolRequest
from .registry import ToolRegistry, get_tool_registry

_ALLOWED_WILDCARDS = {"*", "all"}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    policy_reference: str


def load_tool_enablement() -> dict[str, bool]:
    raw = load_yaml_config("tools.yaml").get("TOOL_ENABLEMENT", {})
    normalized: dict[str, bool] = {}
    if not isinstance(raw, dict):
        return normalized
    for tool_name, enabled in raw.items():
        key = str(tool_name).strip().lower()
        if key:
            normalized[key] = bool(enabled)
    return normalized


def load_agent_tool_permissions() -> dict[str, set[str]]:
    raw = load_yaml_config("tools.yaml").get("AGENT_TOOL_PERMISSIONS", {})
    normalized: dict[str, set[str]] = {}
    if not isinstance(raw, dict):
        return normalized
    for agent_id, tools in raw.items():
        agent_key = str(agent_id).strip()
        if not agent_key:
            continue
        if isinstance(tools, list):
            normalized[agent_key] = {str(item).strip().lower() for item in tools if str(item).strip()}
        else:
            normalized[agent_key] = set()
    return normalized


def evaluate_agent_tool_permission(*, agent_id: str | None, tool_name: str) -> PolicyDecision:
    normalized_agent = str(agent_id or "").strip()
    if not normalized_agent:
        return PolicyDecision(False, "agent_id is required for tool execution", "tool.policy.agent_id_missing")

    normalized_tool = str(tool_name or "").strip().lower()
    if not normalized_tool:
        return PolicyDecision(False, "tool_name is required for tool execution", "tool.policy.tool_name_missing")

    permissions = load_agent_tool_permissions()
    allowed_tools = permissions.get(normalized_agent) or permissions.get("*") or set()
    if not allowed_tools:
        return PolicyDecision(False, "agent is not permitted for tool execution", "tool.policy.agent_tool_denied")

    if normalized_tool in allowed_tools or allowed_tools.intersection(_ALLOWED_WILDCARDS):
        return PolicyDecision(True, "agent tool permission approved", "tool.policy.agent_tool_allowed")

    return PolicyDecision(False, "agent is not permitted for this tool", "tool.policy.agent_tool_denied")


def resolve_tool_definition(tool_name: str, registry: ToolRegistry | None = None) -> ToolDefinition | None:
    target = registry or get_tool_registry()
    normalized = str(tool_name or "").strip().lower()
    if not normalized or not target.has_tool(normalized):
        return None
    return target.get_tool(normalized)


def is_internal_tool(tool_definition: ToolDefinition) -> bool:
    return tool_definition.connector_name == "system" and tool_definition.capability_metadata.get("external_execution") is False


def evaluate_tool_policy(
    *,
    request: ToolRequest,
    tenant_id: str = "owner",
    project_id: str | None = None,
    registry: ToolRegistry | None = None,
    allowed_agent_ids: set[str] | None = None,
    allowed_project_ids: set[str] | None = None,
) -> PolicyDecision:
    definition = resolve_tool_definition(request.tool_name, registry)
    if definition is None:
        return PolicyDecision(False, "tool is not registered", "tool.policy.tool_not_registered")

    if not request.command_id:
        return PolicyDecision(False, "tool execution requires a command context", "tool.policy.command_context_required")

    if request.connector_name != definition.connector_name or request.action != definition.action:
        return PolicyDecision(False, "tool request does not match registered tool definition", "tool.policy.definition_mismatch")

    effective_enabled = load_tool_enablement().get(definition.tool_name, definition.enabled_by_default)
    if not effective_enabled:
        return PolicyDecision(False, "tool is disabled by policy", "tool.policy.tool_disabled")

    if not definition.read_only:
        return PolicyDecision(False, "non-read-only tools are not allowed in current phase", "tool.policy.write_not_allowed")

    if bool((request.metadata or {}).get("requested_write", False)):
        return PolicyDecision(False, "tool request attempts write access against a read-only tool", "tool.policy.read_only_enforced")

    tool_permission = evaluate_agent_tool_permission(agent_id=request.agent_id, tool_name=definition.tool_name)
    if not tool_permission.allowed:
        return tool_permission

    if is_internal_tool(definition):
        return PolicyDecision(True, "internal tool policy approved", "tool.policy.internal_allowed")

    try:
        get_connector(definition.connector_name)
    except KeyError:
        return PolicyDecision(False, "connector is not registered", "tool.policy.connector_not_registered")

    connector_policy = evaluate_connector_policy(
        connector_name=definition.connector_name,
        tenant_id=tenant_id,
        agent_id=request.agent_id,
        project_id=project_id,
        allowed_agent_ids=allowed_agent_ids,
        allowed_project_ids=allowed_project_ids,
    )
    if not connector_policy.allowed:
        return PolicyDecision(False, connector_policy.reason, f"tool.policy.{connector_policy.reason_code}")

    connector_permission = evaluate_agent_connector_permission(
        agent_id=request.agent_id,
        connector_name=definition.connector_name,
        operation=definition.action,
    )
    if not connector_permission.allowed:
        return PolicyDecision(False, connector_permission.reason, f"tool.policy.{connector_permission.reason_code}")

    return PolicyDecision(True, "tool policy approved", "tool.policy.allowed")
