from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..commands.command_service import extract_command_result_metadata, update_command_run_for_job
from ..models import AgentRun, AgentRunStatus, CommandRun, Job, JobStatus
from ..services.observability import (
    get_agent_run_counts,
    get_job_status_counts,
    get_operator_event_snapshot,
)
from ..services.operator_queue import (
    OPERATOR_QUEUE_BUCKETS,
    OPERATOR_QUEUE_PRECEDENCE,
    classify_operator_queue_bucket,
    partition_operator_runtime_queue,
)
from ..services.runtime_health import get_runtime_health_snapshot


def _resolve_agent_label(run: CommandRun) -> str | None:
    if run.selected_agent_id:
        return str(run.selected_agent_id)
    result_summary = dict(run.result_summary or {})
    agent_result = dict(result_summary.get("agent_result") or {})
    if agent_result.get("agent_type"):
        return str(agent_result["agent_type"])
    if run.planned_task_type:
        return str(run.planned_task_type)
    return None


def _resolve_registry_key(run: CommandRun) -> str | None:
    result_summary = dict(run.result_summary or {})
    if result_summary.get("registry_key"):
        return str(result_summary["registry_key"])
    agent_result = dict(result_summary.get("agent_result") or {})
    if agent_result.get("registry_key"):
        return str(agent_result["registry_key"])
    nested_result = dict(agent_result.get("result") or {})
    if nested_result.get("registry_key"):
        return str(nested_result["registry_key"])
    return None


def _normalize_operator_status(run: CommandRun) -> str:
    status = str(run.status or "").strip().lower()
    if status in {"queued", "running", "completed", "failed"}:
        return status
    if status == "pending":
        return "queued"
    if status in {"denied", "cancelled", "timeout"}:
        return "failed"
    return "failed"


def _is_currently_awaiting_approval(run: CommandRun) -> bool:
    status = str(run.status or "").strip().lower()
    approval_status = str(run.approval_status or "").strip().lower()
    return approval_status == "required" and status == "pending" and not run.job_id


def build_operator_command_item(run: CommandRun) -> dict[str, Any]:
    timestamp = run.updated_at or run.created_at
    runtime_status = str(run.status or "").strip().lower() or None
    trace = extract_command_result_metadata(run.result_summary)
    return {
        "command_id": run.id,
        "tenant_id": run.tenant_id,
        "command_text": run.command_text,
        "status": _normalize_operator_status(run),
        "runtime_status": runtime_status,
        "result": run.result_summary,
        "timestamp": timestamp.isoformat() if timestamp else None,
        "agent": _resolve_agent_label(run),
        "planned_task_type": run.planned_task_type,
        "requested_mode": run.requested_mode,
        "selected_agent_id": str(run.selected_agent_id) if run.selected_agent_id else None,
        "execution_decision": run.execution_decision,
        "approval_required": _is_currently_awaiting_approval(run),
        "approval_status": run.approval_status,
        "policy_reason": run.policy_reason,
        "job_id": run.job_id,
        "queue_bucket": classify_operator_queue_bucket(run),
        "registry_key": _resolve_registry_key(run),
        "request_id": trace.get("request_id"),
        "run_id": trace.get("run_id"),
        "correlation_id": trace.get("correlation_id"),
        "connector_name": trace.get("connector_name"),
        "error_code": trace.get("error_code"),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


def _result_payload(record: AgentRun) -> dict[str, Any]:
    return dict(record.result or {}) if isinstance(record.result, dict) else {}


def _to_operator_agent_run_item(record: AgentRun) -> dict[str, Any]:
    result = _result_payload(record)
    return {
        "run_id": record.id,
        "tenant_id": record.tenant_id,
        "command_id": result.get("command_id"),
        "agent_id": str(record.agent_id),
        "agent_type": result.get("agent_type"),
        "task_type": record.task_type,
        "status": record.status.value if isinstance(record.status, AgentRunStatus) else str(record.status),
        "started_at": record.started_at.isoformat() if record.started_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "completed_at": record.finished_at.isoformat() if record.finished_at else None,
        "duration_ms": result.get("duration_ms"),
        "steps_executed": result.get("steps_executed"),
        "tools_used": list(result.get("tools_used", [])) if isinstance(result.get("tools_used", []), list) else [],
        "error": result.get("error_message") or record.error,
        "registry_key": result.get("registry_key"),
    }


def _to_operator_job_item(job: Job) -> dict[str, Any]:
    payload = dict(job.payload or {})
    result = dict(job.result or {}) if isinstance(job.result, dict) else None
    return {
        "job_id": job.id,
        "job_type": job.job_type,
        "status": job.status.value if isinstance(job.status, JobStatus) else str(job.status),
        "command_id": payload.get("command_id"),
        "queue_task_id": job.queue_task_id,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "error": job.error,
        "result": result,
    }


def _load_recent_commands(session: Session, *, limit: int = 20, status: str | None = None, approval_status: str | None = None) -> list[CommandRun]:
    safe_limit = max(1, min(int(limit), 200))
    stmt = select(CommandRun).order_by(CommandRun.created_at.desc()).limit(safe_limit)
    items = list(session.execute(stmt).scalars())
    for item in items:
        update_command_run_for_job(session, item)

    filtered: list[CommandRun] = []
    safe_status = str(status or "").strip().lower() or None
    safe_approval = str(approval_status or "").strip().lower() or None
    for item in items:
        if safe_status and _normalize_operator_status(item) != safe_status:
            continue
        if safe_approval and str(item.approval_status or "").strip().lower() != safe_approval:
            continue
        filtered.append(item)
    return filtered[:safe_limit]


def _load_hydrated_summary_commands(session: Session, *, recent_limit: int = 10) -> list[CommandRun]:
    sample_limit = max(50, min(max(int(recent_limit), 1) * 20, 500))
    stmt = select(CommandRun).order_by(CommandRun.created_at.desc()).limit(sample_limit)
    items = list(session.execute(stmt).scalars())
    for item in items:
        update_command_run_for_job(session, item)
    return items


def _build_hydrated_command_summary(runs: list[CommandRun], *, recent_limit: int) -> dict[str, Any]:
    recent_items = runs[: max(1, min(int(recent_limit), 100))]

    raw_counts: dict[str, int] = {}
    normalized_counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0}
    by_bucket = {key: 0 for key in OPERATOR_QUEUE_BUCKETS}
    approval_required_total = 0
    denied_total = 0
    queue_size = 0

    for run in runs:
        runtime_status = str(run.status or "").strip().lower() or "unknown"
        raw_counts[runtime_status] = int(raw_counts.get(runtime_status, 0)) + 1

        normalized_status = _normalize_operator_status(run)
        normalized_counts[normalized_status] = int(normalized_counts.get(normalized_status, 0)) + 1

        if _is_currently_awaiting_approval(run):
            approval_required_total += 1

        if str(run.execution_decision or "").strip().lower() == "denied" or runtime_status == "denied":
            denied_total += 1

        if runtime_status in {"pending", "queued"}:
            queue_size += 1

        bucket = classify_operator_queue_bucket(run)
        if bucket is not None:
            by_bucket[bucket] += 1

    return {
        "recent_commands": [build_operator_command_item(item) for item in recent_items],
        "counts": normalized_counts,
        "queue_size": int(queue_size),
        "commands": {
            "counts_by_status": raw_counts,
            "approval_required_total": int(approval_required_total),
            "denied_total": int(denied_total),
        },
        "operator_attention": {
            "current_totals": {
                "attention_command_total": int(sum(by_bucket.values())),
            },
            "state_summary": {
                "by_bucket": by_bucket,
                "precedence": OPERATOR_QUEUE_PRECEDENCE,
            },
        },
    }


def list_operator_command_items(session: Session, *, limit: int = 20, status: str | None = None, approval_status: str | None = None) -> list[dict[str, Any]]:
    items = _load_recent_commands(session, limit=limit, status=status, approval_status=approval_status)
    return [build_operator_command_item(item) for item in items]


def list_operator_job_items(session: Session, *, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 100))
    stmt = select(Job).order_by(Job.updated_at.desc()).limit(safe_limit * 3)
    items = list(session.execute(stmt).scalars())
    safe_status = str(status or "").strip().lower() or None
    filtered: list[Job] = []
    for item in items:
        item_status = item.status.value if isinstance(item.status, JobStatus) else str(item.status)
        if safe_status and item_status.lower() != safe_status:
            continue
        filtered.append(item)
        if len(filtered) >= safe_limit:
            break
    return [_to_operator_job_item(item) for item in filtered]


def list_operator_agent_run_items(session: Session, *, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 100))
    stmt = select(AgentRun).order_by(AgentRun.updated_at.desc()).limit(safe_limit * 3)
    items = list(session.execute(stmt).scalars())
    safe_status = str(status or "").strip().lower() or None
    filtered: list[AgentRun] = []
    for item in items:
        item_status = item.status.value if isinstance(item.status, AgentRunStatus) else str(item.status)
        if safe_status and item_status.lower() != safe_status:
            continue
        filtered.append(item)
        if len(filtered) >= safe_limit:
            break
    return [_to_operator_agent_run_item(item) for item in filtered]


def build_operator_queue_view(session: Session, *, limit: int = 20) -> dict[str, list[dict[str, Any]]]:
    safe_limit = max(1, min(int(limit), 100))
    items = list(
        session.execute(
            select(CommandRun)
            .where(CommandRun.status.in_(["pending", "queued", "running"]))
            .order_by(CommandRun.created_at.desc())
        ).scalars()
    )
    for item in items:
        update_command_run_for_job(session, item)
    active_items = [
        item for item in items
        if str(item.status or "").strip().lower() in {"pending", "queued", "running"}
    ]
    partitioned = partition_operator_runtime_queue(active_items, limit=safe_limit)
    return {
        "queued_commands": [build_operator_command_item(item) for item in partitioned["queued_commands"]],
        "running_commands": [build_operator_command_item(item) for item in partitioned["running_commands"]],
    }


def generate_operator_summary(session: Session, *, limit: int = 10) -> dict[str, Any]:
    hydrated_commands = _load_hydrated_summary_commands(session, recent_limit=limit)
    hydrated_summary = _build_hydrated_command_summary(hydrated_commands, recent_limit=limit)
    job_counts, total_jobs = get_job_status_counts(session)
    agent_run_counts, total_agent_runs = get_agent_run_counts(session)
    runtime_health = get_runtime_health_snapshot()

    return {
        "recent_commands": hydrated_summary["recent_commands"],
        "counts": hydrated_summary["counts"],
        "queue_size": hydrated_summary["queue_size"],
        "system_health": runtime_health["status"],
        "operator_events": get_operator_event_snapshot(session, limit=20),
        "commands": hydrated_summary["commands"],
        "jobs": {
            "counts_by_status": job_counts,
            "total_jobs": total_jobs,
        },
        "agent_runs": {
            "counts_by_status": agent_run_counts,
            "total_runs": total_agent_runs,
        },
        "operator_attention": hydrated_summary["operator_attention"],
    }

