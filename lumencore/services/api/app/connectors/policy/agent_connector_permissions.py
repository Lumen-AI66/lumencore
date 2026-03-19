from __future__ import annotations

from dataclasses import dataclass

from ...config import load_yaml_config


@dataclass(frozen=True)
class AgentConnectorPermissionResult:
    allowed: bool
    reason: str
    reason_code: str


_ALLOWED_WILDCARDS = {"*", "all"}


def load_agent_connector_permissions() -> dict[str, dict[str, set[str]]]:
    raw = load_yaml_config("connectors.yaml").get("AGENT_CONNECTOR_PERMISSIONS", {})
    normalized: dict[str, dict[str, set[str]]] = {}

    if not isinstance(raw, dict):
        return normalized

    for agent_id, connectors in raw.items():
        if not isinstance(connectors, dict):
            continue
        agent_key = str(agent_id).strip()
        if not agent_key:
            continue
        normalized[agent_key] = {}
        for connector_name, operations in connectors.items():
            connector_key = str(connector_name).strip()
            if not connector_key:
                continue
            if isinstance(operations, list):
                normalized[agent_key][connector_key] = {str(item).strip() for item in operations if str(item).strip()}
            else:
                normalized[agent_key][connector_key] = set()
    return normalized


def evaluate_agent_connector_permission(
    *,
    agent_id: str | None,
    connector_name: str,
    operation: str,
) -> AgentConnectorPermissionResult:
    normalized_agent = str(agent_id or "").strip()
    if not normalized_agent:
        return AgentConnectorPermissionResult(False, "agent_id is required for connector execution", "agent_id_missing")

    normalized_connector = str(connector_name or "").strip()
    normalized_operation = str(operation or "").strip()
    if not normalized_connector or not normalized_operation:
        return AgentConnectorPermissionResult(False, "connector and operation are required", "connector_context_missing")

    permissions = load_agent_connector_permissions()
    effective = permissions.get(normalized_agent) or permissions.get("*") or {}
    allowed_operations = effective.get(normalized_connector, set())
    if not allowed_operations:
        return AgentConnectorPermissionResult(False, "agent is not permitted for connector", "agent_connector_denied")

    if normalized_operation in allowed_operations or allowed_operations.intersection(_ALLOWED_WILDCARDS):
        return AgentConnectorPermissionResult(True, "agent connector permission approved", "agent_connector_allowed")

    return AgentConnectorPermissionResult(False, "agent is not permitted for connector operation", "agent_operation_denied")
