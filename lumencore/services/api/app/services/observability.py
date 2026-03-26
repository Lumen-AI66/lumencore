from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Lock

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..execution import get_execution_scheduler_metrics, get_execution_scheduler_summary
from ..models import (
    AgentAuditEvent,
    AgentRun,
    AgentRunStateRecord,
    AgentRunStatus,
    AgentStateEventRecord,
    AgentTaskStateRecord,
    CommandRun,
    ExecutionTaskRecord,
    ExecutionTaskStatus,
    Job,
    JobStatus,
    OperatorEventRecord,
    PlanRunRecord,
    PlanRunStatus,
    PlanStepRecord,
    PlanStepStatus,
    WorkflowRunRecord,
    WorkflowRunStatus,
)
from ..planning import get_plan_runtime_metrics, get_plan_runtime_summary
from ..services.operator_queue import get_operator_queue_snapshot
from ..workflows import get_workflow_runtime_metrics, get_workflow_runtime_summary
from .execution import build_execution_truth
from .execution_control import get_execution_control_snapshot, get_execution_control_state
from .policy_engine import get_execution_policy_snapshot
from .read_models import build_execution_task_read_model
ALL_STATUSES = [JobStatus.pending, JobStatus.queued, JobStatus.running, JobStatus.completed, JobStatus.failed]
AGENT_RUN_STATUSES = [AgentRunStatus.pending, AgentRunStatus.running, AgentRunStatus.completed, AgentRunStatus.failed]
EXECUTION_TASK_STATUSES = [ExecutionTaskStatus.pending, ExecutionTaskStatus.running, ExecutionTaskStatus.completed, ExecutionTaskStatus.failed, ExecutionTaskStatus.retrying]
PLAN_RUN_STATUSES = [PlanRunStatus.pending, PlanRunStatus.running, PlanRunStatus.completed, PlanRunStatus.failed]
PLAN_STEP_STATUSES = [PlanStepStatus.pending, PlanStepStatus.queued, PlanStepStatus.running, PlanStepStatus.completed, PlanStepStatus.failed]
WORKFLOW_RUN_STATUSES = [WorkflowRunStatus.pending, WorkflowRunStatus.running, WorkflowRunStatus.completed, WorkflowRunStatus.failed]
_AGENT_STATE_STATUSES = ["pending", "running", "completed", "failed", "cancelled"]

_EXECUTION_GATE_DECISIONS = ["allowed", "approval_required", "denied"]
_APPROVAL_STATUSES = ["not_required", "required", "approved", "cancelled"]
_CONTROL_ACTIONS = ["cancel", "retry"]
_OPERATOR_EVENT_TYPES = [
    "OPERATOR_COMMAND_RECEIVED",
    "OPERATOR_COMMAND_QUEUED",
    "OPERATOR_COMMAND_STARTED",
    "OPERATOR_COMMAND_COMPLETED",
    "OPERATOR_COMMAND_FAILED",
]
_OPERATOR_EVENT_LIMIT = 50
_operator_event_lock = Lock()
_operator_event_counters: dict[str, int] = {key: 0 for key in _OPERATOR_EVENT_TYPES}
_operator_recent_events = deque(maxlen=_OPERATOR_EVENT_LIMIT)
_operator_last_event_at: str | None = None


def _record_runtime_operator_event(key: str, timestamp: str, command_id: str | None) -> None:
    global _operator_last_event_at
    with _operator_event_lock:
        _operator_event_counters[key] = int(_operator_event_counters.get(key, 0)) + 1
        _operator_last_event_at = timestamp
        _operator_recent_events.append(
            {
                "event_type": key,
                "command_id": command_id,
                "timestamp": timestamp,
            }
        )


def record_operator_event(event_type: str, *, command_id: str | None = None, metadata: dict | None = None) -> None:
    key = str(event_type or "").strip().upper()
    if key not in _operator_event_counters:
        return
    timestamp = datetime.now(timezone.utc).isoformat()

    if not command_id:
        _record_runtime_operator_event(key, timestamp, command_id)
        return

    session = SessionLocal()
    try:
        existing = session.execute(
            select(OperatorEventRecord.id)
            .where(OperatorEventRecord.command_id == command_id, OperatorEventRecord.event_type == key)
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            return

        session.add(
            OperatorEventRecord(
                command_id=command_id,
                event_type=key,
                timestamp=datetime.fromisoformat(timestamp),
                metadata_json=metadata,
            )
        )
        session.commit()
        _record_runtime_operator_event(key, timestamp, command_id)
    except SQLAlchemyError:
        session.rollback()
    finally:
        session.close()


def _serialize_operator_event(row: OperatorEventRecord) -> dict:
    return {
        "event_type": row.event_type,
        "command_id": row.command_id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
    }


def list_operator_events(session: Session, *, command_id: str | None = None, limit: int = 20) -> list[dict]:
    safe_limit = max(1, min(int(limit), 100))
    fetch_limit = min(safe_limit * 5, 500)
    stmt = select(OperatorEventRecord)
    if command_id:
        stmt = stmt.where(OperatorEventRecord.command_id == command_id)
    rows = list(session.execute(stmt.order_by(OperatorEventRecord.timestamp.desc()).limit(fetch_limit)).scalars())

    deduped: list[OperatorEventRecord] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.command_id, row.event_type)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
        if len(deduped) >= safe_limit:
            break

    deduped.reverse()
    return [_serialize_operator_event(row) for row in deduped]


def get_operator_event_snapshot(session: Session, *, limit: int = 20) -> dict:
    counts = {key: 0 for key in _OPERATOR_EVENT_TYPES}
    rows = session.execute(select(OperatorEventRecord.event_type, func.count(func.distinct(OperatorEventRecord.command_id))).group_by(OperatorEventRecord.event_type)).all()
    for event_type, count in rows:
        key = str(event_type or "").strip().upper()
        if key in counts:
            counts[key] = int(count)

    recent_events = list_operator_events(session, limit=limit)
    return {
        "counts": counts,
        "recent_events": recent_events,
    }


def get_job_status_counts(session: Session) -> tuple[dict[str, int], int]:
    rows = session.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    counts = {status.value: 0 for status in ALL_STATUSES}
    for status, count in rows:
        key = status.value if isinstance(status, JobStatus) else str(status)
        counts[key] = int(count)
    return counts, sum(counts.values())


def get_agent_run_counts(session: Session) -> tuple[dict[str, int], int]:
    rows = session.execute(select(AgentRun.status, func.count()).group_by(AgentRun.status)).all()
    counts = {status.value: 0 for status in AGENT_RUN_STATUSES}
    for status, count in rows:
        key = status.value if isinstance(status, AgentRunStatus) else str(status)
        counts[key] = int(count)
    return counts, sum(counts.values())


def get_execution_task_counts(session: Session) -> tuple[dict[str, int], int]:
    rows = session.execute(select(ExecutionTaskRecord.status, func.count()).group_by(ExecutionTaskRecord.status)).all()
    counts = {status.value: 0 for status in EXECUTION_TASK_STATUSES}
    for status, count in rows:
        key = status.value if isinstance(status, ExecutionTaskStatus) else str(status)
        counts[key] = int(count)
    return counts, sum(counts.values())


def get_plan_run_counts(session: Session) -> tuple[dict[str, int], int]:
    rows = session.execute(select(PlanRunRecord.status, func.count()).group_by(PlanRunRecord.status)).all()
    counts = {status.value: 0 for status in PLAN_RUN_STATUSES}
    for status, count in rows:
        key = status.value if isinstance(status, PlanRunStatus) else str(status)
        counts[key] = int(count)
    return counts, sum(counts.values())


def get_plan_step_counts(session: Session) -> tuple[dict[str, int], int]:
    rows = session.execute(select(PlanStepRecord.status, func.count()).group_by(PlanStepRecord.status)).all()
    counts = {status.value: 0 for status in PLAN_STEP_STATUSES}
    for status, count in rows:
        key = status.value if isinstance(status, PlanStepStatus) else str(status)
        counts[key] = int(count)
    return counts, sum(counts.values())


def get_workflow_run_counts(session: Session) -> tuple[dict[str, int], int]:
    rows = session.execute(select(WorkflowRunRecord.status, func.count()).group_by(WorkflowRunRecord.status)).all()
    counts = {status.value: 0 for status in WORKFLOW_RUN_STATUSES}
    for status, count in rows:
        key = status.value if isinstance(status, WorkflowRunStatus) else str(status)
        counts[key] = int(count)
    return counts, sum(counts.values())


def get_workflow_failed_total(session: Session) -> int:
    total = session.execute(
        select(func.count(WorkflowRunRecord.workflow_id)).where(WorkflowRunRecord.status == WorkflowRunStatus.failed)
    ).scalar_one()
    return int(total)


def get_execution_gate_snapshot(session: Session) -> dict:
    decision_rows = session.execute(
        select(CommandRun.execution_decision, func.count()).group_by(CommandRun.execution_decision)
    ).all()
    approval_rows = session.execute(
        select(CommandRun.approval_status, func.count()).group_by(CommandRun.approval_status)
    ).all()

    by_decision = {key: 0 for key in _EXECUTION_GATE_DECISIONS}
    for value, count in decision_rows:
        if value is not None:
            by_decision[str(value)] = int(count)

    by_approval_status = {key: 0 for key in _APPROVAL_STATUSES}
    for value, count in approval_rows:
        if value is not None:
            by_approval_status[str(value)] = int(count)

    current_totals = {
        "policy_evaluated_total": int(sum(by_decision.values())),
        "execution_allowed_total": int(by_decision.get("allowed", 0)),
        "approval_required_total": int(by_decision.get("approval_required", 0)),
        "approval_granted_total": int(by_approval_status.get("approved", 0)),
        "execution_denied_total": int(by_decision.get("denied", 0)),
    }

    return {
        "current_totals": current_totals,
        "state_summary": {
            "by_decision": by_decision,
            "by_approval_status": by_approval_status,
        },
    }




def get_lifecycle_control_snapshot(session: Session) -> dict:
    action_rows = session.execute(
        select(CommandRun.last_control_action, func.count()).where(CommandRun.last_control_action.is_not(None)).group_by(CommandRun.last_control_action)
    ).all()
    cancelled_total = session.execute(
        select(func.count(CommandRun.id)).where(CommandRun.status == "cancelled")
    ).scalar_one()
    retried_total = session.execute(
        select(func.count(CommandRun.id)).where(CommandRun.retried_from_id.is_not(None))
    ).scalar_one()

    by_last_control_action = {key: 0 for key in _CONTROL_ACTIONS}
    for value, count in action_rows:
        if value is not None:
            by_last_control_action[str(value)] = int(count)

    return {
        "current_totals": {
            "controlled_command_total": int(sum(by_last_control_action.values())),
            "cancelled_command_total": int(cancelled_total),
            "retried_command_total": int(retried_total),
        },
        "state_summary": {
            "by_last_control_action": by_last_control_action,
        },
    }
def get_command_run_stats(session: Session) -> tuple[int, datetime | None]:
    total = session.execute(select(func.count(CommandRun.id))).scalar_one()
    latest = session.execute(select(func.max(CommandRun.updated_at))).scalar_one_or_none()
    return int(total), latest


def get_command_status_counts(session: Session) -> dict[str, int]:
    rows = session.execute(select(CommandRun.status, func.count()).group_by(CommandRun.status)).all()
    counts: dict[str, int] = {}
    for status, count in rows:
        key = str(status or "unknown")
        counts[key] = int(count)
    return counts

def get_policy_denies_total(session: Session) -> int:
    total = session.execute(
        select(func.count(AgentAuditEvent.id)).where(AgentAuditEvent.policy_result == "deny")
    ).scalar_one()
    return int(total)


def _build_persisted_execution_audit_snapshot() -> tuple[dict, dict]:
    session = SessionLocal()
    try:
        records = list(session.execute(select(ExecutionTaskRecord).where(ExecutionTaskRecord.result_summary.is_not(None))).scalars())
    finally:
        session.close()

    tool_totals = {
        "tool_requests_total": 0,
        "tool_success_total": 0,
        "tool_denied_total": 0,
        "tool_failed_total": 0,
        "tool_timeout_total": 0,
    }
    tool_by_tool: dict[str, int] = {}
    tool_by_connector: dict[str, int] = {}
    tool_by_agent: dict[str, int] = {}
    tool_duration_total = 0.0
    tool_duration_count = 0
    tool_last_execution_at: str | None = None

    connector_totals = {
        "connector_calls_total": 0,
        "connector_denied_total": 0,
        "connector_errors_total": 0,
        "connector_success_total": 0,
        "connector_missing_secret_total": 0,
        "connector_timeout_total": 0,
        "connector_validation_failure_total": 0,
        "connector_provider_failure_total": 0,
    }
    connector_by_connector: dict[str, int] = {}
    connector_by_provider: dict[str, int] = {}
    connector_by_operation: dict[str, int] = {}
    denial_reasons: dict[str, int] = {}
    failure_reasons: dict[str, int] = {}
    connector_duration_total = 0.0
    connector_duration_count = 0
    connector_last_execution_at: str | None = None

    def _increment(bucket: dict[str, int], key: str | None) -> None:
        label = str(key or "unknown")
        bucket[label] = int(bucket.get(label, 0)) + 1

    for record in records:
        truth = build_execution_truth(None, record)
        task_summary = dict(record.result_summary or {})
        agent_execution = dict(task_summary.get("agent_execution") or {})
        result_payload = dict(agent_execution.get("result") or {})
        results = result_payload.get("results") or []

        for entry in results:
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("status") or "").strip().lower()
            tool_name = str(entry.get("tool_name") or "").strip() or None
            connector_name = str(entry.get("connector_name") or truth.get("connector_name") or "").strip() or None
            output = dict(entry.get("output") or {})
            provider = output.get("provider") or connector_name
            operation = entry.get("action")
            agent_id = entry.get("agent_id") or record.agent_id
            error_code = entry.get("error_code") or truth.get("error_code")
            duration_ms = entry.get("duration_ms")
            completed_at = entry.get("completed_at") or (record.updated_at.isoformat() if record.updated_at else None)

            if tool_name:
                tool_totals["tool_requests_total"] += 1
                _increment(tool_by_tool, tool_name)
                _increment(tool_by_connector, connector_name)
                _increment(tool_by_agent, agent_id)
                if status == "success":
                    tool_totals["tool_success_total"] += 1
                elif status == "denied":
                    tool_totals["tool_denied_total"] += 1
                elif status == "timeout" or error_code == "tool_timeout":
                    tool_totals["tool_timeout_total"] += 1
                else:
                    tool_totals["tool_failed_total"] += 1
                if duration_ms is not None:
                    tool_duration_total += float(duration_ms) / 1000.0
                    tool_duration_count += 1
                if completed_at and (tool_last_execution_at is None or completed_at > tool_last_execution_at):
                    tool_last_execution_at = completed_at

            if connector_name:
                connector_totals["connector_calls_total"] += 1
                _increment(connector_by_connector, connector_name)
                _increment(connector_by_provider, provider)
                _increment(connector_by_operation, operation)
                if status == "success":
                    connector_totals["connector_success_total"] += 1
                elif status == "denied":
                    connector_totals["connector_denied_total"] += 1
                    _increment(denial_reasons, error_code or "denied")
                else:
                    connector_totals["connector_errors_total"] += 1
                    _increment(failure_reasons, error_code or "error")
                if error_code == "missing_secret":
                    connector_totals["connector_missing_secret_total"] += 1
                elif error_code in {"timeout", "tool_timeout"}:
                    connector_totals["connector_timeout_total"] += 1
                elif error_code == "validation_failed":
                    connector_totals["connector_validation_failure_total"] += 1
                elif error_code == "provider_error":
                    connector_totals["connector_provider_failure_total"] += 1
                if duration_ms is not None:
                    connector_duration_total += float(duration_ms)
                    connector_duration_count += 1
                if completed_at and (connector_last_execution_at is None or completed_at > connector_last_execution_at):
                    connector_last_execution_at = completed_at

    tool_execution = {
        "totals": tool_totals,
        "by_tool": tool_by_tool,
        "by_connector": tool_by_connector,
        "by_agent": tool_by_agent,
        "avg_duration_seconds": round(tool_duration_total / tool_duration_count, 4) if tool_duration_count else 0.0,
        "last_execution_at": tool_last_execution_at,
    }
    connector_execution = {
        "totals": connector_totals,
        "by_connector": connector_by_connector,
        "by_provider": connector_by_provider,
        "by_operation": connector_by_operation,
        "denial_reasons": denial_reasons,
        "failure_reasons": failure_reasons,
        "avg_duration_ms": round(connector_duration_total / connector_duration_count, 2) if connector_duration_count else 0.0,
        "last_execution_at": connector_last_execution_at,
    }
    return tool_execution, connector_execution


def get_connector_metrics_snapshot() -> dict[str, int]:
    _tool_execution, connector_execution = _build_persisted_execution_audit_snapshot()
    totals = connector_execution.get("totals", {})
    return {
        "connector_calls_total": int(totals.get("connector_calls_total", 0)),
        "connector_denied_total": int(totals.get("connector_denied_total", 0)),
        "connector_errors_total": int(totals.get("connector_errors_total", 0)),
    }


def get_connector_execution_snapshot() -> dict:
    _tool_execution, connector_execution = _build_persisted_execution_audit_snapshot()
    return connector_execution


def get_tool_metrics_snapshot() -> dict[str, int]:
    tool_execution, _connector_execution = _build_persisted_execution_audit_snapshot()
    totals = tool_execution.get("totals", {})
    return {
        "tool_requests_total": int(totals.get("tool_requests_total", 0)),
        "tool_success_total": int(totals.get("tool_success_total", 0)),
        "tool_denied_total": int(totals.get("tool_denied_total", 0)),
        "tool_failed_total": int(totals.get("tool_failed_total", 0)),
        "tool_timeout_total": int(totals.get("tool_timeout_total", 0)),
    }


def get_tool_execution_snapshot() -> dict:
    tool_execution, _connector_execution = _build_persisted_execution_audit_snapshot()
    return tool_execution


def get_execution_scheduler_metrics_snapshot() -> dict[str, int]:
    return get_execution_scheduler_metrics()


def get_execution_scheduler_summary_snapshot() -> dict:
    return get_execution_scheduler_summary()


def get_plan_runtime_metrics_snapshot() -> dict[str, int]:
    return get_plan_runtime_metrics()


def get_plan_runtime_summary_snapshot() -> dict:
    return get_plan_runtime_summary()


def get_workflow_runtime_metrics_snapshot() -> dict[str, int]:
    return get_workflow_runtime_metrics()


def get_workflow_runtime_summary_snapshot() -> dict:
    return get_workflow_runtime_summary()


def list_recent_jobs(session: Session, limit: int = 10) -> list[Job]:
    safe_limit = max(1, min(int(limit), 100))
    return list(session.execute(select(Job).order_by(Job.created_at.desc()).limit(safe_limit)).scalars())


def list_recent_failures(session: Session, limit: int = 10) -> list[Job]:
    safe_limit = max(1, min(int(limit), 100))
    stmt = select(Job).where(Job.status == JobStatus.failed).order_by(Job.updated_at.desc()).limit(safe_limit)
    return list(session.execute(stmt).scalars())


def get_latest_job_activity(session: Session) -> datetime | None:
    return session.execute(select(func.max(Job.updated_at))).scalar_one_or_none()


def get_latest_agent_run_activity(session: Session) -> datetime | None:
    return session.execute(select(func.max(AgentRun.updated_at))).scalar_one_or_none()


def get_agent_runtime_snapshot(session: Session) -> dict:
    total = session.execute(
        select(func.count(AgentRun.id)).where(AgentRun.task_type == "agent_task")
    ).scalar_one()
    latest_run = session.execute(
        select(AgentRun).where(AgentRun.task_type == "agent_task").order_by(AgentRun.updated_at.desc()).limit(1)
    ).scalar_one_or_none()
    if not latest_run:
        return {
            "total_agent_tasks": int(total),
            "latest_run": None,
        }

    result_payload = dict(latest_run.result or {})
    return {
        "total_agent_tasks": int(total),
        "latest_run": {
            "agent_run_id": latest_run.id,
            "agent_id": str(latest_run.agent_id),
            "task_type": latest_run.task_type,
            "status": latest_run.status.value if isinstance(latest_run.status, AgentRunStatus) else str(latest_run.status),
            "task_id": result_payload.get("task_id"),
            "agent_name": result_payload.get("agent_name"),
            "agent_type": result_payload.get("agent_type"),
            "steps_executed": result_payload.get("steps_executed"),
            "tools_used": result_payload.get("tools_used", []),
            "duration_ms": result_payload.get("duration_ms"),
            "updated_at": latest_run.updated_at.isoformat() if latest_run.updated_at else None,
        },
    }


def get_agent_state_snapshot(session: Session) -> dict:
    rows = session.execute(
        select(AgentRunStateRecord.status, func.count()).group_by(AgentRunStateRecord.status)
    ).all()
    counts = {status: 0 for status in _AGENT_STATE_STATUSES}
    for status, count in rows:
        counts[str(status)] = int(count)

    latest_state = session.execute(
        select(AgentRunStateRecord).order_by(AgentRunStateRecord.updated_at.desc()).limit(1)
    ).scalar_one_or_none()
    latest_task = session.execute(
        select(AgentTaskStateRecord).order_by(AgentTaskStateRecord.updated_at.desc()).limit(1)
    ).scalar_one_or_none()
    latest_event = session.execute(
        select(AgentStateEventRecord).order_by(AgentStateEventRecord.created_at.desc()).limit(1)
    ).scalar_one_or_none()

    return {
        "counts_by_status": counts,
        "latest_run": None if latest_state is None else {
            "run_id": latest_state.run_id,
            "task_id": latest_state.task_id,
            "agent_type": latest_state.agent_type,
            "status": latest_state.status,
            "current_step": latest_state.current_step,
            "retry_count": latest_state.retry_count,
            "updated_at": latest_state.updated_at.isoformat() if latest_state.updated_at else None,
            "completed_at": latest_state.completed_at.isoformat() if latest_state.completed_at else None,
            "last_error": latest_state.last_error,
        },
        "latest_task": None if latest_task is None else {
            "task_id": latest_task.task_id,
            "run_id": latest_task.run_id,
            "task_type": latest_task.task_type,
            "status": latest_task.status,
            "updated_at": latest_task.updated_at.isoformat() if latest_task.updated_at else None,
            "completed_at": latest_task.completed_at.isoformat() if latest_task.completed_at else None,
        },
        "latest_event": None if latest_event is None else {
            "id": latest_event.id,
            "run_id": latest_event.run_id,
            "task_id": latest_event.task_id,
            "event_type": latest_event.event_type,
            "step_name": latest_event.step_name,
            "severity": latest_event.severity,
            "created_at": latest_event.created_at.isoformat() if latest_event.created_at else None,
        },
    }


def get_execution_control_snapshot_view(session: Session) -> dict:
    return get_execution_control_snapshot(session)


def get_execution_policy_snapshot_view(session: Session) -> dict:
    return get_execution_policy_snapshot(session)


def get_execution_task_snapshot(session: Session) -> dict:
    counts, total = get_execution_task_counts(session)
    latest_task = session.execute(
        select(ExecutionTaskRecord).order_by(ExecutionTaskRecord.updated_at.desc()).limit(1)
    ).scalar_one_or_none()
    latest_command = session.get(CommandRun, latest_task.command_id) if latest_task and latest_task.command_id else None
    latest_control_state = get_execution_control_state(session, latest_task.task_id) if latest_task is not None else None
    latest_policy_state = dict((latest_task.task_metadata or {}).get('execution_policy') or {}) or None if latest_task is not None else None
    latest_task_model = build_execution_task_read_model(
        latest_task,
        latest_command,
        execution_control=latest_control_state.model_dump(mode="json") if latest_control_state is not None else None,
        execution_policy=latest_policy_state,
    ) if latest_task is not None else None
    return {
        "counts_by_status": counts,
        "total_tasks": total,
        "latest_task": None if latest_task_model is None else {
            "task_id": latest_task_model.get("task_id"),
            "command_id": latest_task_model.get("command_id"),
            "agent_id": latest_task_model.get("agent_id"),
            "agent_type": latest_task_model.get("agent_type"),
            "task_type": latest_task_model.get("task_type"),
            "status": latest_task_model.get("status"),
            "priority": latest_task_model.get("priority"),
            "retries": latest_task_model.get("retries"),
            "max_retries": latest_task_model.get("max_retries"),
            "available_at": latest_task_model.get("available_at").isoformat() if latest_task_model.get("available_at") else None,
            "updated_at": latest_task_model.get("updated_at").isoformat() if latest_task_model.get("updated_at") else None,
            "finished_at": latest_task_model.get("finished_at").isoformat() if latest_task_model.get("finished_at") else None,
            "error": latest_task_model.get("error"),
        },
        "latest_execution_lineage": None if latest_task_model is None else latest_task_model.get("execution_lineage"),
    }


def get_plan_snapshot(session: Session) -> dict:
    run_counts, total_plans = get_plan_run_counts(session)
    step_counts, total_steps = get_plan_step_counts(session)
    latest_plan = session.execute(
        select(PlanRunRecord).order_by(PlanRunRecord.updated_at.desc()).limit(1)
    ).scalar_one_or_none()
    latest_step = session.execute(
        select(PlanStepRecord).order_by(PlanStepRecord.updated_at.desc()).limit(1)
    ).scalar_one_or_none()
    return {
        "plan_runs": {
            "counts_by_status": run_counts,
            "total_plans": total_plans,
            "latest_plan": None if latest_plan is None else {
                "plan_id": latest_plan.plan_id,
                "command_id": latest_plan.command_id,
                "plan_type": latest_plan.plan_type,
                "status": latest_plan.status.value if isinstance(latest_plan.status, PlanRunStatus) else str(latest_plan.status),
                "total_steps": latest_plan.total_steps,
                "current_step_index": latest_plan.current_step_index,
                "updated_at": latest_plan.updated_at.isoformat() if latest_plan.updated_at else None,
                "completed_at": latest_plan.completed_at.isoformat() if latest_plan.completed_at else None,
                "error": latest_plan.error,
            },
        },
        "plan_steps": {
            "counts_by_status": step_counts,
            "total_steps": total_steps,
            "latest_step": None if latest_step is None else {
                "step_id": latest_step.step_id,
                "plan_id": latest_step.plan_id,
                "step_index": latest_step.step_index,
                "step_type": latest_step.step_type,
                "agent_type": latest_step.agent_type,
                "status": latest_step.status.value if isinstance(latest_step.status, PlanStepStatus) else str(latest_step.status),
                "execution_task_id": latest_step.execution_task_id,
                "updated_at": latest_step.updated_at.isoformat() if latest_step.updated_at else None,
                "completed_at": latest_step.completed_at.isoformat() if latest_step.completed_at else None,
                "error": latest_step.error,
            },
        },
    }


def get_workflow_snapshot(session: Session) -> dict:
    counts, total = get_workflow_run_counts(session)
    latest_workflow = session.execute(
        select(WorkflowRunRecord).order_by(WorkflowRunRecord.updated_at.desc()).limit(1)
    ).scalar_one_or_none()
    return {
        "workflow_runs": {
            "counts_by_status": counts,
            "total_workflows": total,
            "latest_workflow": None if latest_workflow is None else {
                "workflow_id": latest_workflow.workflow_id,
                "command_id": latest_workflow.command_id,
                "workflow_type": latest_workflow.workflow_type,
                "status": latest_workflow.status.value if isinstance(latest_workflow.status, WorkflowRunStatus) else str(latest_workflow.status),
                "linked_plan_id": latest_workflow.linked_plan_id,
                "updated_at": latest_workflow.updated_at.isoformat() if latest_workflow.updated_at else None,
                "completed_at": latest_workflow.completed_at.isoformat() if latest_workflow.completed_at else None,
                "error": latest_workflow.error,
            },
        }
    }















