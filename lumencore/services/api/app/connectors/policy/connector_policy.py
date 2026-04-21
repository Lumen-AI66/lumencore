from __future__ import annotations

from dataclasses import dataclass

from ...config import load_yaml_config


@dataclass(frozen=True)
class ConnectorPolicyResult:
    allowed: bool
    reason: str
    reason_code: str


_DEFAULT_ENABLEMENT: dict[str, bool] = {
    "git": False,
    "search": False,
    "openai": False,
    "claude": False,
}


def load_connector_enablement() -> dict[str, bool]:
    config = dict(_DEFAULT_ENABLEMENT)
    raw = load_yaml_config("connectors.yaml").get("CONNECTOR_ENABLEMENT", {})
    if not isinstance(raw, dict):
        return config

    # Apply all keys from yaml, not just defaults
    for name, val in raw.items():
        config[str(name).strip()] = bool(val)
    return config


def evaluate_connector_policy(
    *,
    connector_name: str,
    tenant_id: str,
    agent_id: str | None,
    project_id: str | None,
    allowed_agent_ids: set[str] | None = None,
    allowed_project_ids: set[str] | None = None,
) -> ConnectorPolicyResult:
    normalized_tenant = (tenant_id or "").strip() or "owner"
    if normalized_tenant not in {"owner", "telegram"}:
        return ConnectorPolicyResult(False, "tenant is not allowed in current phase", "tenant_not_allowed")

    enablement = load_connector_enablement()
    connector_key = (connector_name or "").strip()
    is_enabled = bool(enablement.get(connector_key, False))
    if not is_enabled:
        return ConnectorPolicyResult(False, "connector is disabled by policy", "connector_disabled")

    if allowed_agent_ids is not None:
        normalized_agent = (agent_id or "").strip()
        if not normalized_agent or normalized_agent not in allowed_agent_ids:
            return ConnectorPolicyResult(False, "agent is not allowed for connector", "agent_not_allowed")

    if allowed_project_ids is not None:
        normalized_project = (project_id or "").strip()
        if not normalized_project or normalized_project not in allowed_project_ids:
            return ConnectorPolicyResult(False, "project scope is not allowed for connector", "project_not_allowed")

    return ConnectorPolicyResult(True, "connector policy approved", "connector_policy_approved")

