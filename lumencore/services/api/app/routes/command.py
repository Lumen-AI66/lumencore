from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query, status

from ..commands.command_runtime import build_command_run_response, execute_command_request
from ..commands.command_service import (
    build_workflow_job_payload,
    create_retried_command_run,
    get_command_run,
    interpret_command,
    list_command_runs,
    mark_command_cancelled,
    update_command_run_for_job,
)
from ..db import session_scope
from ..services.jobs import create_job, mark_job_queued
from ..worker_tasks import execute_job
from ..schemas.commands import CommandHistoryResponse, CommandRunRequest, CommandRunResponse
from ..services.lifecycle_control import evaluate_command_transition

router = APIRouter(prefix="/api/command", tags=["command"])


def _to_response(item) -> CommandRunResponse:
    return build_command_run_response(item)


@router.post("/run", response_model=CommandRunResponse, status_code=status.HTTP_202_ACCEPTED)
def command_run(req: CommandRunRequest, x_lumencore_owner_approval: str | None = Header(default=None), x_lumencore_internal_route: str | None = Header(default=None)) -> CommandRunResponse:
    return execute_command_request(req, x_lumencore_owner_approval, x_lumencore_internal_route)


@router.post("/{command_id}/approve", response_model=CommandRunResponse, status_code=status.HTTP_202_ACCEPTED)
def command_approve(command_id: str) -> CommandRunResponse:
    with session_scope() as session:
        run = get_command_run(session, command_id)
        if not run:
            raise HTTPException(status_code=404, detail="command not found")
        run = update_command_run_for_job(session, run)

        if run.execution_decision == "denied" or run.status == "denied":
            raise HTTPException(status_code=409, detail="denied commands cannot be approved")
        if not run.approval_required:
            raise HTTPException(status_code=409, detail="command does not require approval")
        if run.approval_status == "approved":
            raise HTTPException(status_code=409, detail="command is already approved")
        if run.status == "completed":
            raise HTTPException(status_code=409, detail="command is already completed")
        if run.approval_status != "required":
            raise HTTPException(status_code=409, detail="command is not awaiting approval")

        command = interpret_command(run.command_text, mode=run.requested_mode)
        plan = command["plan"]
        if plan["execution_mode"] != "workflow_job":
            raise HTTPException(status_code=409, detail="approval is only supported for workflow_job commands")

        payload = build_workflow_job_payload(
            run=run,
            plan=plan,
            tenant_id=run.tenant_id,
            project_id=(run.result_summary or {}).get("project_id"),
        )
        job = create_job(session, "workflow_task", payload, tenant_id=run.tenant_id)
        task = execute_job.delay(job.id)
        job = mark_job_queued(session, job, task.id)
        run.job_id = job.id
        run.status = job.status.value
        run.approval_required = False
        run.approval_status = "approved"
        run.last_control_action = "approve"
        run.last_control_reason = "workflow_job approved"
        run.updated_at = datetime.now(timezone.utc)
        run.result_summary = {
            "approval_status": "approved",
            "policy_reason": run.policy_reason,
            "job_id": job.id,
            "control_status": "approved",
            "control_reason": "workflow_job approved",
            "project_id": (run.result_summary or {}).get("project_id"),
        }
        session.add(run)
        session.flush()
        return _to_response(run)




@router.post("/{command_id}/cancel", response_model=CommandRunResponse, status_code=status.HTTP_202_ACCEPTED)
def command_cancel(command_id: str) -> CommandRunResponse:
    with session_scope() as session:
        run = get_command_run(session, command_id)
        if not run:
            raise HTTPException(status_code=404, detail="command not found")
        run = update_command_run_for_job(session, run)

        decision = evaluate_command_transition(
            requested_mode=run.requested_mode,
            status=run.status,
            approval_required=run.approval_required,
            approval_status=run.approval_status,
            job_id=run.job_id,
            action="cancel",
        )
        if decision.outcome == "unsupported":
            raise HTTPException(status_code=409, detail=decision.reason)
        if decision.outcome == "invalid_transition":
            raise HTTPException(status_code=409, detail=decision.reason)

        run = mark_command_cancelled(session, run, reason=decision.reason)
        return _to_response(run)


@router.post("/{command_id}/retry", response_model=CommandRunResponse, status_code=status.HTTP_202_ACCEPTED)
def command_retry(command_id: str) -> CommandRunResponse:
    with session_scope() as session:
        run = get_command_run(session, command_id)
        if not run:
            raise HTTPException(status_code=404, detail="command not found")
        run = update_command_run_for_job(session, run)

        decision = evaluate_command_transition(
            requested_mode=run.requested_mode,
            status=run.status,
            approval_required=run.approval_required,
            approval_status=run.approval_status,
            job_id=run.job_id,
            action="retry",
        )
        if decision.outcome == "unsupported":
            raise HTTPException(status_code=409, detail=decision.reason)
        if decision.outcome == "invalid_transition":
            raise HTTPException(status_code=409, detail=decision.reason)

        retried = create_retried_command_run(session, run)
        return _to_response(retried)


@router.get("/history", response_model=CommandHistoryResponse)
def command_history(limit: int = Query(default=20, ge=1, le=100)) -> CommandHistoryResponse:
    with session_scope() as session:
        items = list_command_runs(session, limit=limit)
        for item in items:
            update_command_run_for_job(session, item)
        return CommandHistoryResponse(limit=limit, items=[_to_response(x) for x in items])


@router.get("/{command_id}", response_model=CommandRunResponse)
def command_get(command_id: str) -> CommandRunResponse:
    with session_scope() as session:
        item = get_command_run(session, command_id)
        if not item:
            raise HTTPException(status_code=404, detail="command not found")
        item = update_command_run_for_job(session, item)
        return _to_response(item)


