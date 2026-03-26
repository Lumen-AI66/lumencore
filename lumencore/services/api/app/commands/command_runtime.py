from __future__ import annotations

from datetime import datetime, timezone
import logging

from fastapi import HTTPException

from ..commands.command_service import (
    build_read_only_result,
    create_command_run,
    execute_agent_command,
    execute_plan_command,
    execute_tool_command,
    execute_workflow_command,
    interpret_command,
    select_agent_if_needed,
)
from ..db import session_scope
from ..schemas.commands import CommandRunRequest, CommandRunResponse
from ..services.read_models import build_command_read_model
from ..services.jobs import create_job, mark_job_queued
from ..security import internal_route_boundary
from ..services.policy_engine.policy_service import evaluate_command_policy, merge_command_policy_summary
from ..tenancy.tenant_guard import enforce_owner_tenant
from ..worker_tasks import execute_job

logger = logging.getLogger(__name__)


def build_command_run_response(item, execution_task=None) -> CommandRunResponse:
    return CommandRunResponse(**build_command_read_model(item, execution_task))


def _with_policy_decision_summary(summary: dict | None, policy_decision) -> dict:
    return merge_command_policy_summary(summary, policy_decision)


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


def execute_command_request(
    req: CommandRunRequest,
    x_lumencore_owner_approval: str | None = None,
    x_lumencore_internal_route: str | None = None,
) -> CommandRunResponse:
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
            policy_decision = evaluate_command_policy(
                session,
                tenant_id=tenant_id,
                project_id=req.project_id,
                task_type=plan["task_type"],
                requested_agent_id=selected_agent_id,
                owner_approved=owner_approved,
                estimated_cost=0.0,
                plan=plan,
                requested_mode=req.mode,
            )

            if policy_decision.outcome == "deny" and policy_decision.source == "execution_gate":
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=policy_decision,
                        status_value="denied",
                    ),
                    result_summary=_with_policy_decision_summary({"error": policy_decision.policy_reason, "error_code": "execution_denied"}, policy_decision),
                )
                return build_command_run_response(run)

            if policy_decision.outcome == "require_approval":
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=policy_decision,
                        status_value="pending",
                    ),
                    result_summary=_with_policy_decision_summary({"approval_status": policy_decision.approval_status, "policy_reason": policy_decision.policy_reason, "project_id": req.project_id}, policy_decision),
                )
                return build_command_run_response(run)

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
                        gate=policy_decision,
                        status_value="completed",
                    ),
                    result_summary=_with_policy_decision_summary(summary, policy_decision),
                )
                completed_at = datetime.now(timezone.utc)
                run.started_at = completed_at
                run.finished_at = completed_at
                run.updated_at = completed_at
                session.add(run)
                session.flush()
                return build_command_run_response(run)

            if plan["execution_mode"] == "tool_sync":
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=policy_decision,
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
                run.result_summary = _with_policy_decision_summary(tool_execution["result_summary"], policy_decision)
                run.finished_at = finished_at
                run.updated_at = finished_at
                session.add(run)
                session.flush()
                return build_command_run_response(run)

            if plan["execution_mode"] == "agent_sync":
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=policy_decision,
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
                run.result_summary = _with_policy_decision_summary(agent_execution["result_summary"], policy_decision)
                run.finished_at = finished_at
                run.updated_at = finished_at
                session.add(run)
                session.flush()
                return build_command_run_response(run)

            if plan["execution_mode"] == "plan_sync":
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=policy_decision,
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
                run.result_summary = _with_policy_decision_summary(plan_execution["result_summary"], policy_decision)
                run.finished_at = finished_at
                run.updated_at = finished_at
                session.add(run)
                session.flush()
                return build_command_run_response(run)

            if plan["execution_mode"] == "workflow_sync":
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=policy_decision,
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
                run.result_summary = _with_policy_decision_summary(workflow_execution["result_summary"], policy_decision)
                run.finished_at = finished_at
                run.updated_at = finished_at
                session.add(run)
                session.flush()
                return build_command_run_response(run)

            if policy_decision.outcome == "deny":
                run = create_command_run(
                    session,
                    **_base_run_kwargs(
                        tenant_id=tenant_id,
                        command_text=command_text,
                        parsed=parsed,
                        plan=plan,
                        selected_agent_id=selected_agent_id,
                        gate=policy_decision,
                        status_value="failed",
                    ),
                    result_summary=_with_policy_decision_summary({"error": policy_decision.policy_reason, "error_code": "policy_denied"}, policy_decision),
                )
                _ = build_command_run_response(run)
                raise HTTPException(status_code=403, detail=policy_decision.policy_reason)

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
                    gate=policy_decision,
                    status_value=job.status.value,
                ),
                job_id=job.id,
                result_summary=_with_policy_decision_summary(None, policy_decision),
            )
            return build_command_run_response(run)
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

