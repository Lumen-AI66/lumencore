from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING, Any

from ...connectors.audit.connector_audit import log_connector_allowed, log_connector_call, log_connector_denied, log_connector_failed
from ...connectors.base.registry import get_connector
from ...services.connectors import get_connector_registry_item
from ...secrets.secret_manager import SecretManager
from .base import ToolAdapter
from ..models import ToolDefinition, ToolRequest

if TYPE_CHECKING:
    from ..service import ToolExecutionContext


class SearchToolAdapter(ToolAdapter):
    def supports(self, tool_definition: ToolDefinition) -> bool:
        return tool_definition.tool_name == "search.web_search" and tool_definition.connector_name == "search"

    def execute_tool(
        self,
        tool_definition: ToolDefinition,
        request: ToolRequest,
        context: ToolExecutionContext,
    ) -> dict[str, Any]:
        connector = get_connector("search")
        secret_manager = SecretManager()
        payload = dict(request.payload or {})
        operation = connector.resolve_operation(payload) or tool_definition.action
        provider = connector.resolve_provider(payload, context={"secret_manager": secret_manager})
        connector_item = get_connector_registry_item("search")

        log_connector_call(
            tenant_id=context.tenant_id,
            connector_name="search",
            agent_id=context.agent_id,
            project_id=context.project_id,
            payload=payload,
            operation=operation,
            provider=provider,
        )

        if connector_item is None:
            log_connector_denied(
                tenant_id=context.tenant_id,
                connector_name="search",
                agent_id=context.agent_id,
                project_id=context.project_id,
                reason="connector is not registered",
                reason_code="connector_not_registered",
                payload=payload,
                operation=operation,
                provider=provider,
            )
            raise RuntimeError("connector_not_registered:search connector is not registered")

        if not connector_item.enabled:
            log_connector_denied(
                tenant_id=context.tenant_id,
                connector_name="search",
                agent_id=context.agent_id,
                project_id=context.project_id,
                reason="connector is disabled by policy",
                reason_code="connector_disabled",
                payload=payload,
                operation=operation,
                provider=provider,
            )
            raise RuntimeError("connector_disabled:search connector is disabled")

        if connector_item.healthy is not True:
            log_connector_failed(
                tenant_id=context.tenant_id,
                connector_name="search",
                agent_id=context.agent_id,
                project_id=context.project_id,
                reason="search connector is not ready",
                reason_code="missing_secret",
                payload=payload,
                operation=operation,
                provider=provider,
            )
            raise RuntimeError("missing_secret:search connector is not ready")

        required_secrets = connector.required_secret_names(
            payload,
            operation=operation,
            provider=provider,
            context={"secret_manager": secret_manager},
        )
        resolved_secrets, missing_secrets = secret_manager.resolve_env_secrets(required_secrets)
        if missing_secrets:
            log_connector_failed(
                tenant_id=context.tenant_id,
                connector_name="search",
                agent_id=context.agent_id,
                project_id=context.project_id,
                reason="required search provider secret is missing",
                reason_code="missing_secret",
                payload={**payload, "missing_secrets": missing_secrets},
                operation=operation,
                provider=provider,
            )
            raise RuntimeError("missing_secret:required search provider secret is missing")

        started = monotonic()
        try:
            result = connector.execute(
                payload,
                tenant_id=context.tenant_id,
                agent_id=context.agent_id,
                context={
                    "provider": provider,
                    "secret_manager": secret_manager,
                    "resolved_secrets": resolved_secrets,
                    "timeout_seconds": tool_definition.timeout_seconds,
                },
            )
        except ValueError as exc:
            log_connector_failed(
                tenant_id=context.tenant_id,
                connector_name="search",
                agent_id=context.agent_id,
                project_id=context.project_id,
                reason=str(exc),
                reason_code="validation_failed",
                payload=payload,
                operation=operation,
                provider=provider,
                duration_ms=round((monotonic() - started) * 1000, 2),
            )
            raise RuntimeError(f"validation_failed:{exc}") from exc
        except RuntimeError as exc:
            raw = str(exc)
            reason_code, _, reason = raw.partition(":")
            mapped_code = reason_code or "provider_error"
            log_connector_failed(
                tenant_id=context.tenant_id,
                connector_name="search",
                agent_id=context.agent_id,
                project_id=context.project_id,
                reason=reason or raw,
                reason_code=mapped_code,
                payload=payload,
                operation=operation,
                provider=provider,
                duration_ms=round((monotonic() - started) * 1000, 2),
            )
            raise RuntimeError(raw) from exc

        duration_ms = round((monotonic() - started) * 1000, 2)
        log_connector_allowed(
            tenant_id=context.tenant_id,
            connector_name="search",
            agent_id=context.agent_id,
            project_id=context.project_id,
            payload=payload,
            operation=operation,
            provider=provider,
            duration_ms=duration_ms,
        )
        return result
