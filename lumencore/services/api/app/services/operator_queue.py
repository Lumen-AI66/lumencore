from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import CommandRun

MAX_QUEUE_SIZE = 100
OPERATOR_QUEUE_BUCKETS = ["awaiting_approval", "retryable", "denied", "failed"]
OPERATOR_QUEUE_PRECEDENCE = ["awaiting_approval", "denied", "retryable", "failed"]


def _is_truthfully_retryable(run: CommandRun) -> bool:
    requested_mode = str(run.requested_mode or "").strip().lower()
    status = str(run.status or "").strip().lower()
    execution_decision = str(run.execution_decision or "").strip().lower()

    return (
        requested_mode == "workflow_job"
        and status in {"cancelled", "failed"}
        and execution_decision != "denied"
    )


def classify_operator_queue_bucket(run: CommandRun) -> str | None:
    status = str(run.status or "").strip().lower()
    execution_decision = str(run.execution_decision or "").strip().lower()
    approval_status = str(run.approval_status or "").strip().lower()

    if (
        execution_decision == "approval_required"
        and bool(run.approval_required)
        and approval_status == "required"
        and status == "pending"
        and not run.job_id
    ):
        return "awaiting_approval"

    if execution_decision == "denied" or status == "denied":
        return "denied"

    if _is_truthfully_retryable(run):
        return "retryable"

    if status == "failed":
        return "failed"

    return None


def list_operator_queue_items(session: Session, *, bucket: str | None = None, limit: int = 20) -> list[CommandRun]:
    safe_limit = max(1, min(int(limit), 100))
    normalized_bucket = str(bucket or "").strip().lower() or None
    runs = list(session.execute(select(CommandRun).order_by(CommandRun.created_at.desc())).scalars())
    items: list[CommandRun] = []
    for run in runs:
        derived_bucket = classify_operator_queue_bucket(run)
        if derived_bucket is None:
            continue
        if normalized_bucket and derived_bucket != normalized_bucket:
            continue
        items.append(run)
        if len(items) >= safe_limit:
            break
    return items


def get_operator_queue_snapshot(session: Session) -> dict:
    runs = list(session.execute(select(CommandRun)).scalars())
    by_bucket = {key: 0 for key in OPERATOR_QUEUE_BUCKETS}
    for run in runs:
        bucket = classify_operator_queue_bucket(run)
        if bucket is not None:
            by_bucket[bucket] += 1

    return {
        "current_totals": {
            "attention_command_total": int(sum(by_bucket.values())),
        },
        "state_summary": {
            "by_bucket": by_bucket,
            "precedence": OPERATOR_QUEUE_PRECEDENCE,
        },
    }


def partition_operator_runtime_queue(runs: list[CommandRun], *, limit: int = 20) -> dict[str, list[CommandRun]]:
    safe_limit = max(1, min(int(limit), MAX_QUEUE_SIZE))
    ordered_runs = sorted(runs, key=lambda run: (run.created_at or 0, run.id))
    queued_statuses = {"queued", "pending"}
    running_statuses = {"running"}
    queued_commands: list[CommandRun] = []
    running_commands: list[CommandRun] = []

    for run in ordered_runs:
        status = str(run.status or "").strip().lower()
        if status in queued_statuses and len(queued_commands) < safe_limit:
            queued_commands.append(run)
        elif status in running_statuses and len(running_commands) < safe_limit:
            running_commands.append(run)

    return {
        "queued_commands": queued_commands,
        "running_commands": running_commands,
    }


def get_operator_queue_size(session: Session) -> int:
    total = session.execute(
        select(func.count(CommandRun.id)).where(CommandRun.status.in_(["queued", "pending"]))
    ).scalar_one()
    return int(total)
