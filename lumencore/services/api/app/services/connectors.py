from __future__ import annotations

from typing import Any

from ..config import load_yaml_config
from ..connectors.base.connector import Connector
from ..connectors.base.registry import list_connector_instances
from ..connectors.claude.claude_connector import ClaudeConnector, ANTHROPIC_API_KEY_ENV
from ..connectors.git.git_connector import GitConnector
from ..connectors.n8n.n8n_connector import N8nConnector, N8N_API_TOKEN_ENV
from ..connectors.openai.openai_connector import OpenAIConnector
from ..connectors.search.search_connector import SUPPORTED_SEARCH_PROVIDERS, SearchConnector
from ..schemas.connectors import ConnectorItem, ConnectorListResponse, ConnectorStatusResponse
from ..secrets.secret_manager import GITHUB_TOKEN_ENV, OPENAI_API_KEY_ENV, SEARCH_PROVIDER_SECRET_ENV, SecretManager


def _load_connector_enablement() -> dict[str, bool]:
    config = load_yaml_config("connectors.yaml")
    raw = config.get("CONNECTOR_ENABLEMENT") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(key).strip(): bool(value) for key, value in raw.items() if str(key).strip()}


def _build_runtime_status(
    connector: Connector,
    *,
    enabled: bool,
    secret_manager: SecretManager,
) -> tuple[str, bool | None, dict[str, Any]]:
    runtime_metadata: dict[str, Any] = {}

    if isinstance(connector, GitConnector):
        required_secret = GITHUB_TOKEN_ENV
        configured = secret_manager.has_env_secret(required_secret)
        runtime_metadata = {
            "required_env_secrets": [required_secret],
            "configured_env_secrets": [required_secret] if configured else [],
        }
        if not enabled:
            return "disabled", False, runtime_metadata
        if configured:
            return "ready", True, runtime_metadata
        return "misconfigured", False, runtime_metadata

    if isinstance(connector, SearchConnector):
        available_providers = secret_manager.available_search_providers()
        runtime_metadata = {
            "supported_providers": list(SUPPORTED_SEARCH_PROVIDERS),
            "available_providers": available_providers,
            "provider_env_requirements": dict(SEARCH_PROVIDER_SECRET_ENV),
        }
        if not enabled:
            return "disabled", False, runtime_metadata
        if available_providers:
            return "ready", True, runtime_metadata
        return "misconfigured", False, runtime_metadata

    if isinstance(connector, ClaudeConnector):
        configured = secret_manager.has_env_secret(ANTHROPIC_API_KEY_ENV)
        runtime_metadata = {
            "required_env_secrets": [ANTHROPIC_API_KEY_ENV],
            "configured_env_secrets": [ANTHROPIC_API_KEY_ENV] if configured else [],
        }
        if not enabled:
            return "disabled", False, runtime_metadata
        if configured:
            return "ready", True, runtime_metadata
        return "misconfigured", False, runtime_metadata

    if isinstance(connector, OpenAIConnector):
        configured = secret_manager.has_env_secret(OPENAI_API_KEY_ENV)
        runtime_metadata = {
            "required_env_secrets": [OPENAI_API_KEY_ENV],
            "configured_env_secrets": [OPENAI_API_KEY_ENV] if configured else [],
        }
        if not enabled:
            return "disabled", False, runtime_metadata
        if configured:
            return "ready", True, runtime_metadata
        return "misconfigured", False, runtime_metadata

    if isinstance(connector, N8nConnector):
        configured = secret_manager.has_env_secret(N8N_API_TOKEN_ENV)
        runtime_metadata = {
            "required_env_secrets": [N8N_API_TOKEN_ENV],
            "configured_env_secrets": [N8N_API_TOKEN_ENV] if configured else [],
        }
        if not enabled:
            return "disabled", False, runtime_metadata
        if configured:
            return "ready", True, runtime_metadata
        return "misconfigured", False, runtime_metadata

    if not enabled:
        return "disabled", False, runtime_metadata
    return "unknown", None, runtime_metadata


def _build_connector_item(connector: Connector, *, enablement: dict[str, bool], secret_manager: SecretManager) -> ConnectorItem:
    connector_key = connector.connector_name
    enabled = bool(enablement.get(connector_key, True))
    status, healthy, runtime_metadata = _build_runtime_status(
        connector,
        enabled=enabled,
        secret_manager=secret_manager,
    )
    supported_actions = list(connector.supported_actions())
    return ConnectorItem(
        connector_key=connector_key,
        name=connector.connector_name,
        kind=connector.connector_type,
        source=getattr(connector, "connector_source", "builtin"),
        enabled=enabled,
        configured=True,
        status=status,
        healthy=healthy,
        allowed_for_execution=bool(enabled and healthy is True),
        supported_actions=supported_actions,
        metadata={
            "provider_type": connector.connector_type,
        },
        runtime_metadata=runtime_metadata,
    )


def list_connector_registry_items() -> ConnectorListResponse:
    enablement = _load_connector_enablement()
    secret_manager = SecretManager()
    items = [
        _build_connector_item(connector, enablement=enablement, secret_manager=secret_manager)
        for connector in list_connector_instances()
    ]
    return ConnectorListResponse(total=len(items), items=items)


def get_connector_registry_item(connector_key: str) -> ConnectorItem | None:
    safe_key = str(connector_key or "").strip()
    if not safe_key:
        return None
    snapshot = list_connector_registry_items()
    for item in snapshot.items:
        if item.connector_key == safe_key:
            return item
    return None


def get_connector_status(connector_key: str) -> ConnectorStatusResponse | None:
    item = get_connector_registry_item(connector_key)
    if item is None:
        return None
    return ConnectorStatusResponse(
        connector_key=item.connector_key,
        enabled=item.enabled,
        configured=item.configured,
        status=item.status,
        healthy=item.healthy,
        allowed_for_execution=item.allowed_for_execution,
        runtime_metadata=item.runtime_metadata,
    )
