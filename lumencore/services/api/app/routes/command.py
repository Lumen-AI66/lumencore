from __future__ import annotations

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Header, HTTPException, Query, status

from ..commands.command_service import (
    build_read_only_result,
    build_workflow_job_payload,
    create_command_run,
    create_retried_command_run,
    execute_agent_command,
    execute_plan_command,
    execute_tool_command,
    execute_workflow_command,
    get_command_run,
    mark_command_cancelled,
    interpret_command,
    list_command_runs,
    select_agent_if_needed,
    update_command_run_for_job,
    extract_command_result_metadata,
)
from ..db import session_scope
from ..policy_engine.policy_engine import PolicyEngine
from ..schemas.commands import CommandHistoryResponse, CommandRunRequest, CommandRunResponse
from ..services.execution_gate import evaluate_execution_gate
from ..services.lifecycle_control import evaluate_command_transition
from ..services.jobs import create_job, mark_job_queued
from ..services.operator_queue import classify_operator_queue_bucket
from ..security import internal_route_boundary
from ..tenancy.tenant_guard import enforce_owner_tenant
from ..worker_tasks import execute_job

router = APIRouter(prefix="/api/command", tags=["command"])
policy_engine = PolicyEngine()
logger = logging.getLogger(__name__)


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


def _base_run_kwargs(*, tenant_id: str, command_text: str, parsed: dict, plan: dict, selected_agent_id: str | None, gate, status_value: str) -> dict:
    return {
        "tenant_id": tenant_id,
        "command_text": command_text,
        "normalized_command": parsed["normalized_command"],
        "intent": plan["intent"],
        "planned_task_type": plan["task_type"],
        "requested_mode": parsed.get("requested_mode"),
        "selected_agent_id": selected_agent_id,
        "status": status_value,
        "execution_decision": gate.execution_decision,
        "approval_required": gate.approval_required,
        "approval_status": gate.approval_status,
        "policy_reason": gate.policy_reason,
    }


def _build_command_http_error(*, status_code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "message": message,
            "canonical_route": "/api/command/run",
            "canonical_field": "command_text",
        },
    )


def _classify_command_value_error(exc: ValueError) -> tuple[int, str]:
    message = str(exc)
    lowered = message.lower()

    if "unsupported command" in lowered:
        return 400, "unsupported_command"
    if "requires a value" in lowered:
        return 400, "invalid_command_request"
    if "command_text is required" in lowered:
        return 422, "missing_command_text"
    if "legacy command cannot be combined" in lowered:
        return 422, "ambiguous_command_payload"
    if "unsupported registry-backed agent_type" in lowered or "requested agent_id" in lowered:
        return 400, "invalid_agent_selection"
    return 400, "invalid_command_request"


@router.post("/run", response_model=CommandRunResponse, status_code=status.HTTP_202_ACCEPTED)
def command_run(req: CommandRunRequest, x_lumencore_owner_approval: str | None = Header(default=None), x_lumencore_internal_route: str | None = Header(default=None)) -> CommandRunResponse:
    try:
        tenant_id = enforce_owner_tenant(req.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if req.uses_legacy_command_field():
        internal_route_boundary(x_lumencore_internal_route)

    with session_scope() as session:
        try:
            command_text = req.resolved_command_text()
            command = interpret_command(command_text, mode=req.mode)
            parsed = command["parsed"]
            parsed["requested_mode"] = req.mode
            plan = command["plan"]
            owner_approved = (x_lumencore_owner_approval or "").strip().lower() == "true"

            selected_agent_id = select_agent_if_needed(session, plan, req.requested_agent_id)
            gate = evaluate_execution_gate(plan=plan, requested_mode=req.mode)

            if gate.execution_decision == "denied":
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=gate,
                        status_value="denied",
                    ),
                    result_summary={"error": gate.policy_reason, "error_code": "execution_denied"},
                )
                return _to_response(run)

            if gate.execution_decision == "approval_required":
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=gate,
                        status_value="pending",
                    ),
                    result_summary={"approval_status": gate.approval_status, "policy_reason": gate.policy_reason, "project_id": req.project_id},
                )
                return _to_response(run)

            if plan["execution_mode"] == "sync_read":
                summary = build_read_only_result(session, plan["intent"])
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=gate,
                        status_value="completed",
                    ),
                    result_summary=summary,
                )
                completed_at = datetime.now(timezone.utc)
                run.started_at = completed_at
                run.finished_at = completed_at
                run.updated_at = completed_at
                session.add(run)
                session.flush()
                return _to_response(run)

            if plan["execution_mode"] == "tool_sync":
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=gate,
                        status_value="pending",
                    ),
                )
                run.started_at = datetime.now(timezone.utc)
                session.add(run)
                session.flush()
                tool_execution = execute_tool_command(
                    session=session,
                    run=run,
                    plan=plan,
                    tenant_id=tenant_id,
                    project_id=req.project_id,
                    agent_id=selected_agent_id or "command-system",
                )
                finished_at = datetime.now(timezone.utc)
                run.status = tool_execution["status"]
                run.result_summary = tool_execution["result_summary"]
                run.finished_at = finished_at
                run.updated_at = finished_at
                session.add(run)
                session.flush()
                return _to_response(run)

            if plan["execution_mode"] == "agent_sync":
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=gate,
                        status_value="pending",
                    ),
                )
                run.started_at = datetime.now(timezone.utc)
                session.add(run)
                session.flush()
                agent_execution = execute_agent_command(
                    session=session,
                    run=run,
                    plan=plan,
                    tenant_id=tenant_id,
                    project_id=req.project_id,
                    agent_id=selected_agent_id or "",
                )
                finished_at = datetime.now(timezone.utc)
                run.status = agent_execution["status"]
                run.result_summary = agent_execution["result_summary"]
                run.finished_at = finished_at
                run.updated_at = finished_at
                session.add(run)
                session.flush()
                return _to_response(run)

            if plan["execution_mode"] == "plan_sync":
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=gate,
                        status_value="pending",
                    ),
                )
                run.started_at = datetime.now(timezone.utc)
                session.add(run)
                session.flush()
                plan_execution = execute_plan_command(
                    session=session,
                    run=run,
                    plan=plan,
                    tenant_id=tenant_id,
                    project_id=req.project_id,
                )
                finished_at = datetime.now(timezone.utc)
                run.status = plan_execution["status"]
                run.result_summary = plan_execution["result_summary"]
                run.finished_at = finished_at
                run.updated_at = finished_at
                session.add(run)
                session.flush()
                return _to_response(run)

            if plan["execution_mode"] == "workflow_sync":
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=gate,
                        status_value="pending",
                    ),
                )
                run.started_at = datetime.now(timezone.utc)
                session.add(run)
                session.flush()
                workflow_execution = execute_workflow_command(
                    session=session,
                    run=run,
                    plan=plan,
                    tenant_id=tenant_id,
                    project_id=req.project_id,
                )
                finished_at = datetime.now(timezone.utc)
                run.status = workflow_execution["status"]
                run.result_summary = workflow_execution["result_summary"]
                run.finished_at = finished_at
                run.updated_at = finished_at
                session.add(run)
                session.flush()
                return _to_response(run)

            validation = policy_engine.validate_agent_request(
                session,
                tenant_id=tenant_id,
                project_id=req.project_id,
                task_type=plan["task_type"],
                requested_agent_id=selected_agent_id,
                owner_approved=owner_approved,
                estimated_cost=0.0,
            )

            if not validation.allowed:
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=gate,
                        status_value="failed",
                    ),
                    result_summary={"error": validation.reason, "error_code": "policy_denied"},
                )
                _ = _to_response(run)
                raise HTTPException(status_code=403, detail=validation.reason)

            payload = {
                "task_type": plan["task_type"],
                "payload": plan["payload"],
                "owner_approved": owner_approved,
                "agent_id": selected_agent_id,
                "tenant_id": tenant_id,
                "project_id": req.project_id,
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "command": parsed["normalized_command"],
            }
            job = create_job(session, "agent_task", payload, tenant_id=tenant_id)
            task = execute_job.delay(job.id)
            job = mark_job_queued(session, job, task.id)
            run = create_command_run(
                session,
                **_base_run_kwargs(
                    tenant_id=tenant_id,
                    command_text=command_text,
                    parsed=parsed,
                    plan=plan,
                    selected_agent_id=selected_agent_id,
                    gate=gate,
                    status_value=job.status.value,
                ),
                job_id=job.id,
            )
            return _to_response(run)
        except ValueError as exc:
            status_code, error_code = _classify_command_value_error(exc)
            logger.warning(
                "Canonical command ingress rejected: error_code=%s tenant_id=%s project_id=%s legacy_field=%s message=%s",
                error_code,
                tenant_id,
                req.project_id,
                req.uses_legacy_command_field(),
                str(exc),
            )
            raise _build_command_http_error(status_code=status_code, error_code=error_code, message=str(exc)) from exc


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
        run.approval_status = "approved"
        run.updated_at = datetime.now(timezone.utc)
        run.result_summary = {
            "approval_status": "approved",
            "policy_reason": run.policy_reason,
            "job_id": job.id,
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


