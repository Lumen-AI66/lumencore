from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.agent_registry import get_agent_id, resolve_registry_definition_for_agent_task
from ..execution import create_execution_scheduler
from ..planning import create_plan_runtime
from ..workflows import create_workflow_runtime
from ..models import CommandRun, Job, JobStatus
from ..policy_engine.audit_logger import write_tool_audit_event
from ..services.agents import get_agent_status_summary
from ..services.observability import get_job_status_counts, record_operator_event
from ..tools import ToolRequest, create_tool_mediation_service
from .agent_selector import select_agent_for_task
from .intent_parser import parse_command
from .task_planner import plan_from_intent

_COMMAND_TOOL_AGENT_ID = "command-system"
_TOOL_STATUS_TO_COMMAND_STATUS = {
    "success": "completed",
    "denied": "denied",
    "failed": "failed",
    "timeout": "timeout",
}
_AGENT_STATUS_TO_COMMAND_STATUS = {
    "completed": "completed",
    "denied": "denied",
    "failed": "failed",
    "timeout": "timeout",
}
_WORKFLOW_STATUS_TO_COMMAND_STATUS = {
    "completed": "completed",
    "failed": "failed",
    "pending": "pending",
    "running": "running",
}


def _is_operator_command(run: CommandRun) -> bool:
    return bool(dict(run.result_summary or {}).get("operator_intake"))


def create_command_run(session: Session, *, tenant_id: str, command_text: str, normalized_command: str, intent: str, planned_task_type: str | None, selected_agent_id: str | None, status: str, requested_mode: str | None = None, execution_decision: str = "allowed", approval_required: bool = False, approval_status: str = "not_required", policy_reason: str | None = None, job_id: str | None = None, result_summary: dict | None = None, command_id: str | None = None) -> CommandRun:
    now = datetime.now(timezone.utc)
    run = CommandRun(
        id=command_id or str(uuid.uuid4()),
        tenant_id=tenant_id,
        command_text=command_text,
        normalized_command=normalized_command,
        intent=intent,
        planned_task_type=planned_task_type,
        requested_mode=requested_mode,
        selected_agent_id=selected_agent_id,
        status=status,
        execution_decision=execution_decision,
        approval_required=approval_required,
        approval_status=approval_status,
        policy_reason=policy_reason,
        last_control_action=None,
        last_control_reason=None,
        cancelled_at=None,
        retried_from_id=None,
        job_id=job_id,
        result_summary=result_summary,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    session.flush()
    return run


def update_command_run_for_job(session: Session, run: CommandRun) -> CommandRun:
    if not run.job_id:
        return run
    job = session.get(Job, run.job_id)
    if not job:
        return run
    run.status = str(job.status.value if isinstance(job.status, JobStatus) else job.status)
    run.started_at = run.started_at or job.started_at
    run.finished_at = job.finished_at or run.finished_at
    run.updated_at = datetime.now(timezone.utc)
    if job.job_type == "workflow_task" and isinstance(job.result, dict):
        workflow_execution = job.result.get("workflow_execution") or {}
        if workflow_execution:
            run.result_summary = _build_workflow_result_summary(workflow_execution)
            run.result_summary["job_status"] = run.status
            run.result_summary["job_id"] = job.id
            if job.error:
                run.result_summary["job_error"] = job.error
    elif job.job_type == "operator_command" and isinstance(job.result, dict):
        persisted_summary = dict(job.result.get("result_summary") or run.result_summary or {})
        if persisted_summary:
            run.result_summary = persisted_summary
            run.result_summary["job_status"] = run.status
            run.result_summary["job_id"] = job.id
            if job.error:
                run.result_summary["job_error"] = job.error
    elif job.status == JobStatus.completed and run.result_summary is None:
        run.result_summary = {"job_status": run.status}
    elif job.status == JobStatus.failed:
        run.result_summary = {"job_status": run.status, "error": job.error}
    session.add(run)
    session.flush()
    return run


def build_read_only_result(session: Session, intent: str) -> dict:
    if intent == "system.status":
        return {"status": "ok", "service": "lumencore-api", "generated_at": datetime.now(timezone.utc).isoformat()}
    if intent == "jobs.summary":
        counts, total = get_job_status_counts(session)
        return {"counts_by_status": counts, "total_jobs": total}
    if intent == "agents.status":
        summary = get_agent_status_summary(session)
        last_run_at = summary.get("last_run_at")
        if isinstance(last_run_at, datetime):
            summary["last_run_at"] = last_run_at.isoformat()
        return summary
    raise ValueError(f"unsupported read-only intent: {intent}")


def interpret_command(command_text: str, mode: str | None = None) -> dict:
    parsed = parse_command(command_text)
    plan = plan_from_intent(parsed, mode=mode)
    return {"parsed": parsed, "plan": plan}


def select_agent_if_needed(session: Session, plan: dict, requested_agent_id: str | None = None) -> str | None:
    if plan["execution_mode"] == "agent_sync":
        definition = resolve_registry_definition_for_agent_task(
            agent_type=plan["agent_type"],
            requested_agent_id=requested_agent_id,
        )
        return definition.agent_id
    if plan["execution_mode"] in {"plan_sync", "workflow_sync", "workflow_job", "tool_sync"}:
        return None
    if plan["execution_mode"] == "agent_job":
        if requested_agent_id:
            return requested_agent_id
        return select_agent_for_task(session, plan["task_type"])
    return None


def build_tool_request(*, run: CommandRun, plan: dict, agent_id: str) -> ToolRequest:
    return ToolRequest(
        request_id=str(uuid.uuid4()),
        command_id=run.id,
        agent_id=agent_id,
        run_id=run.id,
        tool_name=plan["tool_name"],
        connector_name=plan["connector_name"],
        action=plan["action"],
        payload=plan.get("payload", {}),
        correlation_id=run.id,
        metadata={
            "command_intent": plan["intent"],
            "execution_mode": plan["execution_mode"],
            "command_run_id": run.id,
        },
    )


def _map_tool_status_to_command_status(tool_status: str) -> str:
    normalized = str(tool_status or "").strip().lower()
    return _TOOL_STATUS_TO_COMMAND_STATUS.get(normalized, "failed")


def _map_agent_status_to_command_status(agent_status: str) -> str:
    normalized = str(agent_status or "").strip().lower()
    return _AGENT_STATUS_TO_COMMAND_STATUS.get(normalized, "failed")


def _build_tool_result_summary(tool_result) -> dict:
    payload = tool_result.model_dump(mode="json")
    summary = {
        "tool_status": tool_result.status.value,
        "tool_result": payload,
    }
    if tool_result.error_code:
        summary["error_code"] = tool_result.error_code
    if tool_result.policy_decision_reference:
        summary["policy_decision_reference"] = tool_result.policy_decision_reference
    return summary


def _build_agent_result_summary(agent_execution: dict, execution_task_id: str | None = None, execution_task_status: str | None = None, execution_task_retries: int | None = None, execution_task_max_retries: int | None = None) -> dict:
    summary = {
        "agent_status": agent_execution["status"],
        "agent_result": agent_execution,
        "steps_executed": agent_execution.get("steps_executed", 0),
        "tools_used": agent_execution.get("tools_used", []),
        "duration_ms": agent_execution.get("duration_ms"),
        "task_id": agent_execution.get("task_id"),
        "registry_key": agent_execution.get("registry_key"),
    }
    if execution_task_id:
        summary["execution_task_id"] = execution_task_id
    if execution_task_status:
        summary["execution_task_status"] = execution_task_status
    if execution_task_retries is not None:
        summary["execution_task_retries"] = execution_task_retries
    if execution_task_max_retries is not None:
        summary["execution_task_max_retries"] = execution_task_max_retries
    if agent_execution.get("error_code"):
        summary["error_code"] = agent_execution["error_code"]
    if agent_execution.get("error_message"):
        summary["error_message"] = agent_execution["error_message"]
    return summary


def _build_plan_result_summary(plan_execution: dict) -> dict:
    steps = list(plan_execution.get("steps") or [])
    summary = {
        "plan_status": plan_execution["status"],
        "plan_id": plan_execution.get("plan_id"),
        "plan_type": plan_execution.get("plan_type"),
        "total_steps": plan_execution.get("total_steps", len(steps)),
        "current_step_index": plan_execution.get("current_step_index", 0),
        "plan_result": plan_execution,
    }
    if steps:
        summary["latest_step_status"] = steps[-1].get("status")
        summary["execution_task_ids"] = [step.get("execution_task_id") for step in steps if step.get("execution_task_id")]
    if plan_execution.get("error"):
        summary["error"] = plan_execution["error"]
    return summary


def _build_workflow_result_summary(workflow_execution: dict) -> dict:
    summary = {
        "workflow_status": workflow_execution["status"],
        "workflow_id": workflow_execution.get("workflow_id"),
        "workflow_type": workflow_execution.get("workflow_type"),
        "linked_plan_id": workflow_execution.get("linked_plan_id"),
        "workflow_result": workflow_execution,
    }
    result_summary = dict(workflow_execution.get("result_summary") or {})
    if result_summary.get("plan_status"):
        summary["plan_status"] = result_summary.get("plan_status")
    if result_summary.get("total_steps") is not None:
        summary["total_steps"] = result_summary.get("total_steps")
    if workflow_execution.get("error"):
        summary["error"] = workflow_execution["error"]
    return summary


def extract_command_result_metadata(result_summary: dict | None) -> dict[str, str | None]:
    summary = dict(result_summary or {})
    tool_result = dict(summary.get("tool_result") or {})
    if tool_result:
        return {
            "request_id": tool_result.get("request_id"),
            "run_id": tool_result.get("run_id"),
            "correlation_id": tool_result.get("correlation_id"),
            "connector_name": tool_result.get("connector_name"),
            "error_code": tool_result.get("error_code") or summary.get("error_code"),
        }

    agent_result = dict(summary.get("agent_result") or {})
    nested_result = dict(agent_result.get("result") or {})
    results = nested_result.get("results") or []
    first_result = dict(results[0]) if results and isinstance(results[0], dict) else {}
    return {
        "request_id": first_result.get("request_id"),
        "run_id": agent_result.get("agent_run_id") or first_result.get("run_id"),
        "correlation_id": first_result.get("correlation_id") or nested_result.get("command_id") or agent_result.get("task_id"),
        "connector_name": first_result.get("connector_name"),
        "error_code": agent_result.get("error_code") or first_result.get("error_code") or summary.get("error_code"),
    }


def _map_plan_status_to_command_status(plan_status: str) -> str:
    normalized = str(plan_status or "").strip().lower()
    if normalized == "completed":
        return "completed"
    if normalized == "failed":
        return "failed"
    if normalized == "pending":
        return "pending"
    if normalized == "running":
        return "running"
    return "failed"


def _map_workflow_status_to_command_status(workflow_status: str) -> str:
    normalized = str(workflow_status or "").strip().lower()
    return _WORKFLOW_STATUS_TO_COMMAND_STATUS.get(normalized, "failed")


def execute_tool_command(*, session: Session, run: CommandRun, plan: dict, tenant_id: str, project_id: str, agent_id: str) -> dict:
    service = create_tool_mediation_service(audit_writer=lambda event: write_tool_audit_event(session, event))
    tool_request = build_tool_request(run=run, plan=plan, agent_id=agent_id)
    tool_result = service.mediate(
        tool_request,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    summary = _build_tool_result_summary(tool_result)
    status_value = _map_tool_status_to_command_status(tool_result.status.value)
    return {
        "status": status_value,
        "result_summary": summary,
    }


def execute_agent_command(*, session: Session, run: CommandRun, plan: dict, tenant_id: str, project_id: str, agent_id: str) -> dict:
    scheduler = create_execution_scheduler()
    registry_definition = resolve_registry_definition_for_agent_task(
        agent_type=plan["agent_type"],
        requested_agent_id=agent_id,
    )
    payload = dict(plan.get("payload") or {})
    payload.update(
        {
            "task_type": plan["task_type"],
            "agent_type": registry_definition.agent_type,
            "requested_agent_id": registry_definition.agent_id,
            "registry_key": registry_definition.agent_key,
            "resolved_agent_id": registry_definition.agent_id,
            "task_id": run.id,
            "correlation_id": run.id,
        }
    )
    execution_task = scheduler.submit_agent_task(
        session,
        tenant_id=tenant_id,
        command_id=run.id,
        agent_id=registry_definition.agent_id,
        agent_type=registry_definition.agent_type,
        task_type=plan["task_type"],
        payload=payload,
        project_id=project_id,
        priority=10,
        max_retries=1,
        task_metadata={
            "source": "operator.command" if _is_operator_command(run) else "command.agent_sync",
            "intent": plan["intent"],
            "registry_key": registry_definition.agent_key,
            "registry_agent_id": registry_definition.agent_id,
            "registry_agent_type": registry_definition.agent_type,
        },
    )
    processed_task = scheduler.process_task(session, task_id=execution_task.task_id, retry_on_failure=False)
    execution_summary = dict(processed_task.result_summary or {})
    agent_execution = execution_summary.get("agent_execution") or {
        "status": "failed",
        "error_message": processed_task.error or "agent execution failed",
        "task_id": run.id,
    }
    status_value = _map_agent_status_to_command_status(agent_execution.get("status", "failed"))
    return {
        "status": status_value,
        "result_summary": _build_agent_result_summary(
            agent_execution,
            execution_task_id=processed_task.task_id,
            execution_task_status=processed_task.status.value,
            execution_task_retries=processed_task.retries,
            execution_task_max_retries=processed_task.max_retries,
        ),
    }


def execute_plan_command(*, session: Session, run: CommandRun, plan: dict, tenant_id: str, project_id: str) -> dict:
    runtime = create_plan_runtime()
    created_plan, _ = runtime.create_plan(
        session,
        tenant_id=tenant_id,
        command_id=run.id,
        plan_type=plan["plan_type"],
        intent=plan["intent"],
        payload=plan.get("payload", {}),
    )
    plan_execution = runtime.process_plan(
        session,
        plan_id=created_plan.plan_id,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    status_value = _map_plan_status_to_command_status(plan_execution.get("status", "failed"))
    return {
        "status": status_value,
        "result_summary": _build_plan_result_summary(plan_execution),
    }


def execute_workflow_command(*, session: Session, run: CommandRun, plan: dict, tenant_id: str, project_id: str) -> dict:
    runtime = create_workflow_runtime()
    workflow_execution = runtime.execute_workflow(
        session,
        tenant_id=tenant_id,
        command_id=run.id,
        workflow_type=plan["workflow_type"],
        intent=plan["intent"],
        payload=plan.get("payload", {}),
        project_id=project_id,
    )
    status_value = _map_workflow_status_to_command_status(workflow_execution.get("status", "failed"))
    return {
        "status": status_value,
        "result_summary": _build_workflow_result_summary(workflow_execution),
    }


def build_workflow_job_payload(*, run: CommandRun, plan: dict, tenant_id: str, project_id: str | None) -> dict:
    return {
        "workflow_type": plan["workflow_type"],
        "intent": plan["intent"],
        "payload": plan.get("payload") or {},
        "tenant_id": tenant_id,
        "project_id": project_id,
        "command_id": run.id,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "source": "command.workflow_job",
    }


def mark_command_cancelled(session: Session, run: CommandRun, *, reason: str) -> CommandRun:
    now = datetime.now(timezone.utc)
    run.status = "cancelled"
    run.approval_status = "cancelled"
    run.last_control_action = "cancel"
    run.last_control_reason = reason
    run.cancelled_at = now
    run.updated_at = now
    run.result_summary = {
        "control_status": "cancelled",
        "control_reason": reason,
        "project_id": (run.result_summary or {}).get("project_id"),
    }
    session.add(run)
    session.flush()
    return run


def create_retried_command_run(session: Session, source: CommandRun) -> CommandRun:
    retried = create_command_run(
        session,
        tenant_id=source.tenant_id,
        command_text=source.command_text,
        normalized_command=source.normalized_command,
        intent=source.intent,
        planned_task_type=source.planned_task_type,
        selected_agent_id=str(source.selected_agent_id) if source.selected_agent_id else None,
        status="pending",
        requested_mode=source.requested_mode,
        execution_decision=source.execution_decision,
        approval_required=source.approval_required,
        approval_status="required" if source.approval_required else "not_required",
        policy_reason=source.policy_reason,
        result_summary={
            "control_status": "retried",
            "retried_from_id": source.id,
            "project_id": (source.result_summary or {}).get("project_id"),
        },
    )
    retried.retried_from_id = source.id
    session.add(retried)

    source.last_control_action = "retry"
    source.last_control_reason = f"retried as {retried.id}"
    source.updated_at = datetime.now(timezone.utc)
    session.add(source)
    session.flush()
    return retried


def get_command_run(session: Session, command_id: str) -> CommandRun | None:
    return session.get(CommandRun, command_id)


def list_command_runs(session: Session, limit: int = 20) -> list[CommandRun]:
    safe = max(1, min(int(limit), 100))
    return list(session.execute(select(CommandRun).order_by(CommandRun.created_at.desc()).limit(safe)).scalars())


def create_operator_command_run(session: Session, *, command_text: str, tenant_id: str = "owner", project_id: str = "default", command_id: str | None = None) -> CommandRun:
    command = interpret_command(command_text, mode=None)
    parsed = command["parsed"]
    plan = command["plan"]
    selected_agent_id = select_agent_if_needed(session, plan, None)
    return create_command_run(
        session,
        tenant_id=tenant_id,
        command_text=command_text,
        normalized_command=parsed["normalized_command"],
        intent=plan["intent"],
        planned_task_type=plan["task_type"],
        selected_agent_id=selected_agent_id,
        status="queued",
        requested_mode=None,
        execution_decision="allowed",
        approval_required=False,
        approval_status="not_required",
        policy_reason=None,
        result_summary={"project_id": project_id, "operator_intake": True},
        command_id=command_id,
    )


def execute_existing_command_run(session: Session, *, run: CommandRun, project_id: str = "default") -> CommandRun:
    now = datetime.now(timezone.utc)
    run.status = "running"
    run.started_at = run.started_at or now
    run.updated_at = now
    session.add(run)
    session.flush()

    try:
        command = interpret_command(run.command_text, mode=run.requested_mode)
        plan = command["plan"]
        tenant_id = run.tenant_id
        selected_agent_id = str(run.selected_agent_id) if run.selected_agent_id else select_agent_if_needed(session, plan, None)

        if plan["execution_mode"] == "sync_read":
            result_summary = build_read_only_result(session, plan["intent"])
            status_value = "completed"
        elif plan["execution_mode"] == "tool_sync":
            execution = execute_tool_command(
                session=session,
                run=run,
                plan=plan,
                tenant_id=tenant_id,
                project_id=project_id,
                agent_id=selected_agent_id or _COMMAND_TOOL_AGENT_ID,
            )
            status_value = execution["status"]
            result_summary = execution["result_summary"]
        elif plan["execution_mode"] == "agent_sync":
            execution = execute_agent_command(
                session=session,
                run=run,
                plan=plan,
                tenant_id=tenant_id,
                project_id=project_id,
                agent_id=selected_agent_id or "",
            )
            status_value = execution["status"]
            result_summary = execution["result_summary"]
        elif plan["execution_mode"] == "plan_sync":
            execution = execute_plan_command(
                session=session,
                run=run,
                plan=plan,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            status_value = execution["status"]
            result_summary = execution["result_summary"]
        elif plan["execution_mode"] == "workflow_sync":
            execution = execute_workflow_command(
                session=session,
                run=run,
                plan=plan,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            status_value = execution["status"]
            result_summary = execution["result_summary"]
        else:
            raise ValueError("operator command execution mode is not supported")

        finished = datetime.now(timezone.utc)
        run.status = status_value
        run.result_summary = result_summary
        run.finished_at = finished
        run.updated_at = finished
        session.add(run)
        session.flush()
        if run.status == "completed":
            record_operator_event("OPERATOR_COMMAND_COMPLETED", command_id=run.id)
        else:
            record_operator_event("OPERATOR_COMMAND_FAILED", command_id=run.id)
        return run
    except Exception as exc:
        finished = datetime.now(timezone.utc)
        run.status = "failed"
        run.result_summary = {"error": str(exc)}
        run.finished_at = finished
        run.updated_at = finished
        session.add(run)
        session.flush()
        record_operator_event("OPERATOR_COMMAND_FAILED", command_id=run.id)
        raise





