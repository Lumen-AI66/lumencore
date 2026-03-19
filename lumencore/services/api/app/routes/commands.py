from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..commands.command_service import extract_command_result_metadata, get_command_run, list_command_runs, update_command_run_for_job
from ..db import session_scope
from ..schemas.commands import CommandHistoryResponse, CommandRunResponse
from ..services.operator_queue import classify_operator_queue_bucket

router = APIRouter(prefix="/api/commands", tags=["commands"])


def _to_response(item) -> CommandRunResponse:
    trace = extract_command_result_metadata(item.result_summary)
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
        request_id=trace.get("request_id"),
        run_id=trace.get("run_id"),
        correlation_id=trace.get("correlation_id"),
        connector_name=trace.get("connector_name"),
        error_code=trace.get("error_code"),
        result_summary=item.result_summary,
        started_at=item.started_at,
        finished_at=item.finished_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=CommandHistoryResponse)
def list_commands(limit: int = Query(default=20, ge=1, le=100)) -> CommandHistoryResponse:
    with session_scope() as session:
        items = list_command_runs(session, limit=limit)
        for item in items:
            update_command_run_for_job(session, item)
        return CommandHistoryResponse(limit=limit, items=[_to_response(x) for x in items])


@router.get("/{command_id}", response_model=CommandRunResponse)
def get_command(command_id: str) -> CommandRunResponse:
    with session_scope() as session:
        item = get_command_run(session, command_id)
        if not item:
            raise HTTPException(status_code=404, detail="command not found")
        item = update_command_run_for_job(session, item)
        return _to_response(item)




