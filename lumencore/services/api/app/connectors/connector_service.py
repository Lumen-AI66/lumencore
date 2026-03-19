from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import TYPE_CHECKING

from .audit.connector_audit import (
    log_connector_allowed,
    log_connector_call,
    log_connector_denied,
    log_connector_failed,
)
from .base.registry import get_connector
from .policy.agent_connector_permissions import evaluate_agent_connector_permission
from .policy.connector_policy import evaluate_connector_policy
from ..secrets.secret_manager import SecretManager

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ConnectorExecutionResult:
    allowed: bool
    reason: str
    result: dict | None
    audit_events: list[dict]
    connector_name: str
    operation: str | None
    provider: str | None


def audit_writer_from_session(session: "Session") -> Callable[[dict], None]:
    from ..policy_engine.audit_logger import write_connector_audit_event

    def _writer(event: dict) -> None:
        write_connector_audit_event(session, event)

    return _writer


def _emit_audit_event(event: dict, audit_writer: Callable[[dict], None] | None) -> None:
    if audit_writer is not None:
        audit_writer(event)


def _sanitize_failure(reason: str) -> str:
    return str(reason or "connector execution failed").strip() or "connector execution failed"


def _classify_failure(reason: str) -> str:
    text = _sanitize_failure(reason)
    if text.startswith("timeout:"):
        return "timeout"
    if text.startswith("provider_error:"):
        return "provider_error"
    if text.startswith("validation_error:"):
        return "validation_failed"
    return "provider_error"


def execute_connector_request(
    *,
    connector_name: str,
    payload: dict,
    tenant_id: str,
    project_id: str | None = None,
    agent_id: str | None = None,
    allowed_agent_ids: set[str] | None = None,
    allowed_project_ids: set[str] | None = None,
    audit_writer: Callable[[dict], None] | None = None,
    secret_manager: SecretManager | None = None,
) -> ConnectorExecutionResult:
    audit_events: list[dict] = []
    secrets = secret_manager or SecretManager()
    operation = str((payload or {}).get("operation") or (payload or {}).get("action") or "").strip() or None
    provider = str((payload or {}).get("provider") or "").strip().lower() or None

    call_event = log_connector_call(
        tenant_id=tenant_id,
        connector_name=connector_name,
        agent_id=agent_id,
        project_id=project_id,
        payload=payload,
        operation=operation,
        provider=provider,
    )
    audit_events.append(call_event)
    _emit_audit_event(call_event, audit_writer)

    try:
        connector = get_connector(connector_name)
    except KeyError:
        denied_event = log_connector_denied(
            tenant_id=tenant_id,
            connector_name=connector_name,
            agent_id=agent_id,
            project_id=project_id,
            reason="connector is not registered",
            reason_code="connector_not_registered",
            payload=payload,
            operation=operation,
            provider=provider,
        )
        audit_events.append(denied_event)
        _emit_audit_event(denied_event, audit_writer)
        return ConnectorExecutionResult(False, "connector is not registered", None, audit_events, connector_name, operation, provider)

    operation = connector.resolve_operation(payload)
    provider = connector.resolve_provider(payload, context={"secret_manager": secrets})

    decision = evaluate_connector_policy(
        connector_name=connector_name,
        tenant_id=tenant_id,
        agent_id=agent_id,
        project_id=project_id,
        allowed_agent_ids=allowed_agent_ids,
        allowed_project_ids=allowed_project_ids,
    )
    if not decision.allowed:
        denied_event = log_connector_denied(
            tenant_id=tenant_id,
            connector_name=connector_name,
            agent_id=agent_id,
            project_id=project_id,
            reason=decision.reason,
            reason_code=decision.reason_code,
            payload=payload,
            operation=operation,
            provider=provider,
        )
        audit_events.append(denied_event)
        _emit_audit_event(denied_event, audit_writer)
        return ConnectorExecutionResult(False, decision.reason, None, audit_events, connector_name, operation, provider)

    permission = evaluate_agent_connector_permission(
        agent_id=agent_id,
        connector_name=connector_name,
        operation=operation,
    )
    if not permission.allowed:
        denied_event = log_connector_denied(
            tenant_id=tenant_id,
            connector_name=connector_name,
            agent_id=agent_id,
            project_id=project_id,
            reason=permission.reason,
            reason_code=permission.reason_code,
            payload=payload,
            operation=operation,
            provider=provider,
        )
        audit_events.append(denied_event)
        _emit_audit_event(denied_event, audit_writer)
        return ConnectorExecutionResult(False, permission.reason, None, audit_events, connector_name, operation, provider)

    if connector.provider_required(operation) and not provider:
        denied_event = log_connector_denied(
            tenant_id=tenant_id,
            connector_name=connector_name,
            agent_id=agent_id,
            project_id=project_id,
            reason="connector provider is not configured",
            reason_code="missing_secret",
            payload=payload,
            operation=operation,
            provider=provider,
        )
        audit_events.append(denied_event)
        _emit_audit_event(denied_event, audit_writer)
        return ConnectorExecutionResult(False, "connector provider is not configured", None, audit_events, connector_name, operation, provider)

    runtime_context = {
        "secret_manager": secrets,
        "operation": operation,
        "provider": provider,
    }
    required_secret_names = connector.required_secret_names(
        payload,
        operation=operation,
        provider=provider,
        context=runtime_context,
    )
    resolved_secrets, missing_secret_names = secrets.resolve_env_secrets(required_secret_names)
    if missing_secret_names:
        denied_event = log_connector_denied(
            tenant_id=tenant_id,
            connector_name=connector_name,
            agent_id=agent_id,
            project_id=project_id,
            reason="required connector secrets are not configured",
            reason_code="missing_secret",
            payload=payload,
            operation=operation,
            provider=provider,
        )
        audit_events.append(denied_event)
        _emit_audit_event(denied_event, audit_writer)
        return ConnectorExecutionResult(False, "required connector secrets are not configured", None, audit_events, connector_name, operation, provider)

    if not connector.validate(payload):
        failed_event = log_connector_failed(
            tenant_id=tenant_id,
            connector_name=connector_name,
            agent_id=agent_id,
            project_id=project_id,
            reason="payload validation failed",
            reason_code="validation_failed",
            payload=payload,
            operation=operation,
            provider=provider,
        )
        audit_events.append(failed_event)
        _emit_audit_event(failed_event, audit_writer)
        return ConnectorExecutionResult(False, "payload validation failed", None, audit_events, connector_name, operation, provider)

    runtime_context["resolved_secrets"] = resolved_secrets
    started = time.monotonic()
    try:
        result = connector.execute(payload=payload, tenant_id=tenant_id, agent_id=agent_id, context=runtime_context)
    except ValueError as exc:
        duration_ms = round((time.monotonic() - started) * 1000, 2)
        failure_reason = _sanitize_failure(str(exc))
        failed_event = log_connector_failed(
            tenant_id=tenant_id,
            connector_name=connector_name,
            agent_id=agent_id,
            project_id=project_id,
            reason=failure_reason,
            reason_code="validation_failed",
            payload=payload,
            operation=operation,
            provider=provider,
            duration_ms=duration_ms,
        )
        audit_events.append(failed_event)
        _emit_audit_event(failed_event, audit_writer)
        return ConnectorExecutionResult(False, failure_reason, None, audit_events, connector_name, operation, provider)
    except Exception as exc:
        duration_ms = round((time.monotonic() - started) * 1000, 2)
        failure_reason = _sanitize_failure(str(exc))
        failure_code = _classify_failure(failure_reason)
        failed_event = log_connector_failed(
            tenant_id=tenant_id,
            connector_name=connector_name,
            agent_id=agent_id,
            project_id=project_id,
            reason=failure_reason,
            reason_code=failure_code,
            payload=payload,
            operation=operation,
            provider=provider,
            duration_ms=duration_ms,
        )
        audit_events.append(failed_event)
        _emit_audit_event(failed_event, audit_writer)
        return ConnectorExecutionResult(False, failure_reason, None, audit_events, connector_name, operation, provider)

    duration_ms = round((time.monotonic() - started) * 1000, 2)
    allowed_event = log_connector_allowed(
        tenant_id=tenant_id,
        connector_name=connector_name,
        agent_id=agent_id,
        project_id=project_id,
        payload=payload,
        operation=operation,
        provider=provider,
        duration_ms=duration_ms,
    )
    audit_events.append(allowed_event)
    _emit_audit_event(allowed_event, audit_writer)
    return ConnectorExecutionResult(True, "connector execution completed", result, audit_events, connector_name, operation, provider)
