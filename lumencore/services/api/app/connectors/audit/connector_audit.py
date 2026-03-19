from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid


@dataclass(frozen=True)
class ConnectorAuditEvent:
    event_type: str
    tenant_id: str
    connector_name: str
    action: str
    agent_id: str | None
    project_id: str | None
    status: str
    reason: str | None
    reason_code: str | None
    operation: str | None
    provider: str | None
    duration_ms: float | None
    payload: dict


CONNECTOR_METRICS = {
    "connector_calls_total": 0,
    "connector_denied_total": 0,
    "connector_errors_total": 0,
    "connector_success_total": 0,
    "connector_missing_secret_total": 0,
    "connector_timeout_total": 0,
    "connector_validation_failure_total": 0,
    "connector_provider_failure_total": 0,
    "duration_ms_total": 0.0,
    "duration_ms_count": 0,
    "last_execution_at": None,
    "by_connector": {},
    "by_provider": {},
    "by_operation": {},
    "denial_reasons": {},
    "failure_reasons": {},
}

_REDACTED_KEYS = {"api_key", "authorization", "key", "secret", "token"}


def _sanitize(value):
    if isinstance(value, dict):
        sanitized: dict = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.strip().lower() in _REDACTED_KEYS:
                sanitized[key_text] = "***redacted***"
            else:
                sanitized[key_text] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _increment(metric_key: str, amount: int = 1) -> None:
    CONNECTOR_METRICS[metric_key] = int(CONNECTOR_METRICS.get(metric_key, 0)) + amount


def _increment_bucket(bucket_key: str, name: str | None) -> None:
    bucket = CONNECTOR_METRICS[bucket_key]
    label = str(name or "unknown")
    bucket[label] = int(bucket.get(label, 0)) + 1


def _record_duration(duration_ms: float | None) -> None:
    if duration_ms is None:
        return
    CONNECTOR_METRICS["duration_ms_total"] = float(CONNECTOR_METRICS.get("duration_ms_total", 0.0)) + float(duration_ms)
    CONNECTOR_METRICS["duration_ms_count"] = int(CONNECTOR_METRICS.get("duration_ms_count", 0)) + 1
    CONNECTOR_METRICS["last_execution_at"] = datetime.now(timezone.utc).isoformat()


def get_connector_metrics() -> dict[str, int]:
    return {
        "connector_calls_total": int(CONNECTOR_METRICS["connector_calls_total"]),
        "connector_denied_total": int(CONNECTOR_METRICS["connector_denied_total"]),
        "connector_errors_total": int(CONNECTOR_METRICS["connector_errors_total"]),
    }


def get_connector_execution_summary() -> dict:
    duration_count = int(CONNECTOR_METRICS["duration_ms_count"])
    duration_total = float(CONNECTOR_METRICS["duration_ms_total"])
    avg_duration_ms = round(duration_total / duration_count, 2) if duration_count else 0.0
    return {
        "totals": {
            "connector_calls_total": int(CONNECTOR_METRICS["connector_calls_total"]),
            "connector_denied_total": int(CONNECTOR_METRICS["connector_denied_total"]),
            "connector_errors_total": int(CONNECTOR_METRICS["connector_errors_total"]),
            "connector_success_total": int(CONNECTOR_METRICS["connector_success_total"]),
            "connector_missing_secret_total": int(CONNECTOR_METRICS["connector_missing_secret_total"]),
            "connector_timeout_total": int(CONNECTOR_METRICS["connector_timeout_total"]),
            "connector_validation_failure_total": int(CONNECTOR_METRICS["connector_validation_failure_total"]),
            "connector_provider_failure_total": int(CONNECTOR_METRICS["connector_provider_failure_total"]),
        },
        "by_connector": dict(CONNECTOR_METRICS["by_connector"]),
        "by_provider": dict(CONNECTOR_METRICS["by_provider"]),
        "by_operation": dict(CONNECTOR_METRICS["by_operation"]),
        "denial_reasons": dict(CONNECTOR_METRICS["denial_reasons"]),
        "failure_reasons": dict(CONNECTOR_METRICS["failure_reasons"]),
        "avg_duration_ms": avg_duration_ms,
        "last_execution_at": CONNECTOR_METRICS["last_execution_at"],
    }


def build_agent_audit_row(event: ConnectorAuditEvent) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tenant_id": event.tenant_id,
        "agent_id": event.agent_id,
        "action": event.action,
        "policy_result": event.status,
        "metadata": {
            "event_type": event.event_type,
            "connector_name": event.connector_name,
            "project_id": event.project_id,
            "reason": event.reason,
            "reason_code": event.reason_code,
            "operation": event.operation,
            "provider": event.provider,
            "duration_ms": event.duration_ms,
            "payload": _sanitize(event.payload),
        },
    }


def _register_event(event: ConnectorAuditEvent) -> dict:
    if event.event_type != "connector.call":
        _increment_bucket("by_connector", event.connector_name)
        _increment_bucket("by_operation", event.operation)
        if event.provider:
            _increment_bucket("by_provider", event.provider)
    if event.status == "deny":
        _increment_bucket("denial_reasons", event.reason_code or "unspecified")
    if event.status == "error":
        _increment_bucket("failure_reasons", event.reason_code or "unspecified")
    if event.reason_code == "missing_secret":
        _increment("connector_missing_secret_total")
    if event.reason_code == "timeout":
        _increment("connector_timeout_total")
    if event.reason_code == "validation_failed":
        _increment("connector_validation_failure_total")
    if event.reason_code == "provider_error":
        _increment("connector_provider_failure_total")
    _record_duration(event.duration_ms)
    return build_agent_audit_row(event)


def log_connector_call(*, tenant_id: str, connector_name: str, agent_id: str | None, project_id: str | None, payload: dict, operation: str | None = None, provider: str | None = None) -> dict:
    _increment("connector_calls_total")
    event = ConnectorAuditEvent(
        event_type="connector.call",
        tenant_id=tenant_id,
        connector_name=connector_name,
        action="connector.call",
        agent_id=agent_id,
        project_id=project_id,
        status="allow",
        reason=None,
        reason_code=None,
        operation=operation,
        provider=provider,
        duration_ms=None,
        payload=payload,
    )
    return _register_event(event)


def log_connector_allowed(*, tenant_id: str, connector_name: str, agent_id: str | None, project_id: str | None, payload: dict, operation: str | None = None, provider: str | None = None, duration_ms: float | None = None) -> dict:
    _increment("connector_success_total")
    event = ConnectorAuditEvent(
        event_type="connector.allowed",
        tenant_id=tenant_id,
        connector_name=connector_name,
        action="connector.allowed",
        agent_id=agent_id,
        project_id=project_id,
        status="allow",
        reason=None,
        reason_code=None,
        operation=operation,
        provider=provider,
        duration_ms=duration_ms,
        payload=payload,
    )
    return _register_event(event)


def log_connector_denied(*, tenant_id: str, connector_name: str, agent_id: str | None, project_id: str | None, reason: str, payload: dict, reason_code: str | None = None, operation: str | None = None, provider: str | None = None) -> dict:
    _increment("connector_denied_total")
    event = ConnectorAuditEvent(
        event_type="connector.denied",
        tenant_id=tenant_id,
        connector_name=connector_name,
        action="connector.denied",
        agent_id=agent_id,
        project_id=project_id,
        status="deny",
        reason=reason,
        reason_code=reason_code,
        operation=operation,
        provider=provider,
        duration_ms=None,
        payload=payload,
    )
    return _register_event(event)


def log_connector_failed(*, tenant_id: str, connector_name: str, agent_id: str | None, project_id: str | None, reason: str, payload: dict, reason_code: str | None = None, operation: str | None = None, provider: str | None = None, duration_ms: float | None = None) -> dict:
    _increment("connector_errors_total")
    event = ConnectorAuditEvent(
        event_type="connector.failed",
        tenant_id=tenant_id,
        connector_name=connector_name,
        action="connector.failed",
        agent_id=agent_id,
        project_id=project_id,
        status="error",
        reason=reason,
        reason_code=reason_code,
        operation=operation,
        provider=provider,
        duration_ms=duration_ms,
        payload=payload,
    )
    return _register_event(event)
