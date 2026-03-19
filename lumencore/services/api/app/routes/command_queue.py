from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..commands.command_service import update_command_run_for_job
from ..db import session_scope
from ..schemas.commands import CommandHistoryResponse, CommandRunResponse
from ..services.operator_queue import OPERATOR_QUEUE_BUCKETS, classify_operator_queue_bucket, list_operator_queue_items

router = APIRouter(prefix="/api/command-queue", tags=["command-queue"])


def _to_response(item) -> CommandRunResponse:
    return CommandRunResponse(
        id=item.id,
        tenant_id=item.tenant_id,
        command_text=item.command_text,
        normalized_command=item.normalized_command,
        intent=item.intent,
        planned_task_type=item.planned_task_type,
        requested_mode=item.requested_mode,
        selected_agent_id=str(item.selected_agent_id) if item.selected_agent_id else None,
        status=item.status,
        execution_decision=item.execution_decision,
        approval_required=item.approval_required,
        approval_status=item.approval_status,
        policy_reason=item.policy_reason,
        queue_bucket=classify_operator_queue_bucket(item),
        last_control_action=item.last_control_action,
        last_control_reason=item.last_control_reason,
        cancelled_at=item.cancelled_at,
        retried_from_id=item.retried_from_id,
        job_id=item.job_id,
        result_summary=item.result_summary,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=CommandHistoryResponse)
def command_queue(bucket: str | None = Query(default=None, max_length=32), limit: int = Query(default=20, ge=1, le=100)) -> CommandHistoryResponse:
    normalized_bucket = str(bucket or "").strip().lower() or None
    if normalized_bucket and normalized_bucket not in OPERATOR_QUEUE_BUCKETS:
        raise HTTPException(status_code=400, detail="unsupported queue bucket")

    with session_scope() as session:
        items = list_operator_queue_items(session, bucket=normalized_bucket, limit=limit)
        for item in items:
            update_command_run_for_job(session, item)
        return CommandHistoryResponse(limit=limit, items=[_to_response(x) for x in items])
