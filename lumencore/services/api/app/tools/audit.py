from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid


@dataclass(frozen=True)
class ToolAuditEvent:
    event_type: str
    tenant_id: str
    tool_name: str
    connector_name: str
    action: str
    agent_id: str | None
    request_id: str | None
    command_id: str | None
    run_id: str | None
    correlation_id: str | None
    status: str
    policy_reference: str | None
    error_code: str | None
    duration_ms: float | None


TOOL_METRICS = {
    "tool_requests_total": 0,
    "tool_success_total": 0,
    "tool_denied_total": 0,
    "tool_failed_total": 0,
    "tool_timeout_total": 0,
    "tool_duration_seconds_total": 0.0,
    "tool_duration_count": 0,
    "last_execution_at": None,
    "by_tool": {},
    "by_connector": {},
    "by_agent": {},
}


def _increment(metric_key: str, amount: int = 1) -> None:
    TOOL_METRICS[metric_key] = int(TOOL_METRICS.get(metric_key, 0)) + amount


def _increment_bucket(bucket_key: str, label: str | None) -> None:
    bucket = TOOL_METRICS[bucket_key]
    key = str(label or "unknown")
    bucket[key] = int(bucket.get(key, 0)) + 1


def _record_dimensions(event: ToolAuditEvent) -> None:
    _increment_bucket("by_tool", event.tool_name)
    _increment_bucket("by_connector", event.connector_name)
    _increment_bucket("by_agent", event.agent_id)


def _record_duration(duration_ms: float | None) -> None:
    if duration_ms is None:
        return
    TOOL_METRICS["tool_duration_seconds_total"] = float(TOOL_METRICS.get("tool_duration_seconds_total", 0.0)) + (float(duration_ms) / 1000.0)
    TOOL_METRICS["tool_duration_count"] = int(TOOL_METRICS.get("tool_duration_count", 0)) + 1
    TOOL_METRICS["last_execution_at"] = datetime.now(timezone.utc).isoformat()


def get_tool_metrics() -> dict[str, int]:
    return {
        "tool_requests_total": int(TOOL_METRICS["tool_requests_total"]),
        "tool_success_total": int(TOOL_METRICS["tool_success_total"]),
        "tool_denied_total": int(TOOL_METRICS["tool_denied_total"]),
        "tool_failed_total": int(TOOL_METRICS["tool_failed_total"]),
        "tool_timeout_total": int(TOOL_METRICS["tool_timeout_total"]),
    }


def get_tool_execution_summary() -> dict:
    duration_count = int(TOOL_METRICS["tool_duration_count"])
    duration_total = float(TOOL_METRICS["tool_duration_seconds_total"])
    avg_duration_seconds = round(duration_total / duration_count, 4) if duration_count else 0.0
    return {
        "totals": {
            "tool_requests_total": int(TOOL_METRICS["tool_requests_total"]),
            "tool_success_total": int(TOOL_METRICS["tool_success_total"]),
            "tool_denied_total": int(TOOL_METRICS["tool_denied_total"]),
            "tool_failed_total": int(TOOL_METRICS["tool_failed_total"]),
            "tool_timeout_total": int(TOOL_METRICS["tool_timeout_total"]),
        },
        "by_tool": dict(TOOL_METRICS["by_tool"]),
        "by_connector": dict(TOOL_METRICS["by_connector"]),
        "by_agent": dict(TOOL_METRICS["by_agent"]),
        "avg_duration_seconds": avg_duration_seconds,
        "last_execution_at": TOOL_METRICS["last_execution_at"],
    }


def build_tool_audit_row(event: ToolAuditEvent) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tenant_id": event.tenant_id,
        "agent_id": event.agent_id,
        "action": event.action,
        "policy_result": event.status,
        "metadata": {
            "event_type": event.event_type,
            "tool_name": event.tool_name,
            "connector_name": event.connector_name,
            "request_id": event.request_id,
            "command_id": event.command_id,
            "run_id": event.run_id,
            "correlation_id": event.correlation_id,
            "policy_decision_reference": event.policy_reference,
            "error_code": event.error_code,
            "duration_ms": event.duration_ms,
        },
    }


def _register_event(event: ToolAuditEvent) -> dict:
    if event.event_type != "tool.requested":
        _record_dimensions(event)
    _record_duration(event.duration_ms)
    return build_tool_audit_row(event)


def log_tool_requested(*, tenant_id: str, tool_name: str, connector_name: str, action: str, agent_id: str | None, request_id: str | None, command_id: str | None, run_id: str | None, correlation_id: str | None) -> dict:
    _increment("tool_requests_total")
    event = ToolAuditEvent(
        event_type="tool.requested",
        tenant_id=tenant_id,
        tool_name=tool_name,
        connector_name=connector_name,
        action="tool_requested",
        agent_id=agent_id,
        request_id=request_id,
        command_id=command_id,
        run_id=run_id,
        correlation_id=correlation_id,
        status="allow",
        policy_reference=None,
        error_code=None,
        duration_ms=None,
    )
    return _register_event(event)


def log_tool_denied(*, tenant_id: str, tool_name: str, connector_name: str, agent_id: str | None, request_id: str | None, command_id: str | None, run_id: str | None, correlation_id: str | None, policy_reference: str | None, error_code: str | None) -> dict:
    _increment("tool_denied_total")
    event = ToolAuditEvent(
        event_type="tool.denied",
        tenant_id=tenant_id,
        tool_name=tool_name,
        connector_name=connector_name,
        action="tool_denied",
        agent_id=agent_id,
        request_id=request_id,
        command_id=command_id,
        run_id=run_id,
        correlation_id=correlation_id,
        status="deny",
        policy_reference=policy_reference,
        error_code=error_code,
        duration_ms=None,
    )
    return _register_event(event)


def log_tool_failed(*, tenant_id: str, tool_name: str, connector_name: str, agent_id: str | None, request_id: str | None, command_id: str | None, run_id: str | None, correlation_id: str | None, policy_reference: str | None, error_code: str | None, duration_ms: float | None) -> dict:
    _increment("tool_failed_total")
    event = ToolAuditEvent(
        event_type="tool.failed",
        tenant_id=tenant_id,
        tool_name=tool_name,
        connector_name=connector_name,
        action="tool_failed",
        agent_id=agent_id,
        request_id=request_id,
        command_id=command_id,
        run_id=run_id,
        correlation_id=correlation_id,
        status="error",
        policy_reference=policy_reference,
        error_code=error_code,
        duration_ms=duration_ms,
    )
    return _register_event(event)


def log_tool_success(*, tenant_id: str, tool_name: str, connector_name: str, agent_id: str | None, request_id: str | None, command_id: str | None, run_id: str | None, correlation_id: str | None, policy_reference: str | None, duration_ms: float | None) -> dict:
    _increment("tool_success_total")
    event = ToolAuditEvent(
        event_type="tool.success",
        tenant_id=tenant_id,
        tool_name=tool_name,
        connector_name=connector_name,
        action="tool_success",
        agent_id=agent_id,
        request_id=request_id,
        command_id=command_id,
        run_id=run_id,
        correlation_id=correlation_id,
        status="allow",
        policy_reference=policy_reference,
        error_code=None,
        duration_ms=duration_ms,
    )
    return _register_event(event)


def log_tool_timeout(*, tenant_id: str, tool_name: str, connector_name: str, agent_id: str | None, request_id: str | None, command_id: str | None, run_id: str | None, correlation_id: str | None, policy_reference: str | None, duration_ms: float | None) -> dict:
    _increment("tool_timeout_total")
    event = ToolAuditEvent(
        event_type="tool.timeout",
        tenant_id=tenant_id,
        tool_name=tool_name,
        connector_name=connector_name,
        action="tool_timeout",
        agent_id=agent_id,
        request_id=request_id,
        command_id=command_id,
        run_id=run_id,
        correlation_id=correlation_id,
        status="error",
        policy_reference=policy_reference,
        error_code="tool_timeout",
        duration_ms=duration_ms,
    )
    return _register_event(event)
