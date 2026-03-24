from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic
from typing import Any
import uuid

from sqlalchemy.orm import Session

from ..models import AgentRun, AgentRunStatus
from ..policy_engine.audit_logger import write_audit_event, write_tool_audit_event
from ..sandbox.sandbox_executor import SandboxExecutor, allow_governed_network_calls
from ..secrets.secret_manager import SecretManager
from ..tools import ToolRequest, create_tool_mediation_service
from .agent_loop import run_agent
from .agent_policy import validate_agent_policy
from .agent_registry import get_agent, get_agent_id, resolve_registry_definition_for_agent_task
from .agent_router import resolve_agent_for_task
from .agent_types import AgentStep
from .state_models import AgentRuntimeStateStatus
from .state_store import get_agent_state_store


SUPPORTED_AGENT_TASK_TYPES = {"agent.ping", "agent.echo"}


def _execute_controlled_task(task_type: str, payload: dict, secret_manager: SecretManager) -> dict:
    _ = secret_manager

    if task_type == "agent.ping":
        return {"ok": True, "task_type": task_type, "message": payload.get("message", "")}
    if task_type == "agent.echo":
        return {"ok": True, "task_type": task_type, "payload": payload}
    raise ValueError(f"unsupported agent task_type: {task_type}")


def _sanitize_error(exc: Exception) -> tuple[str, str, str]:
    if isinstance(exc, RuntimeError) and str(exc) == "Agent step limit exceeded":
        return "agent_step_limit_exceeded", "agent execution exceeded the configured step limit", "failed"
    if isinstance(exc, TimeoutError):
        return "agent_timeout", "agent execution timed out", "timeout"
    if isinstance(exc, PermissionError):
        return "agent_denied", "agent execution denied", "denied"
    return "agent_execution_failed", "agent execution failed", "failed"


def _build_tool_request(
    *,
    command_id: str | None,
    run_id: str,
    correlation_id: str,
    agent_id: str,
    step: AgentStep,
    task: dict[str, Any],
) -> ToolRequest:
    return ToolRequest(
        request_id=str(uuid.uuid4()),
        command_id=command_id,
        agent_id=agent_id,
        run_id=run_id,
        tool_name=step.tool_name,
        connector_name=step.connector_name,
        action=step.action,
        payload=step.payload,
        correlation_id=correlation_id,
        metadata={
            "execution_mode": "agent_sync",
            "agent_task_type": task.get("task_type"),
            "agent_type": task.get("agent_type"),
            "task_id": task.get("task_id"),
            "registry_key": task.get("registry_key"),
        },
    )


def execute_agent(
    session: Session,
    *,
    task: dict[str, Any],
    tenant_id: str = "owner",
    project_id: str | None = None,
    command_id: str | None = None,
) -> dict:
    state_store = get_agent_state_store()
    task_payload = dict(task or {})
    agent_type = str(task_payload.get("agent_type") or "automation").strip().lower() or "automation"
    requested_agent_id = str(task_payload.get("requested_agent_id") or get_agent_id(agent_type))
    registry_definition = resolve_registry_definition_for_agent_task(agent_type=agent_type, requested_agent_id=requested_agent_id)
    deterministic_agent = get_agent(registry_definition.agent_type)
    task_id = str(task_payload.get("task_id") or command_id or str(uuid.uuid4()))
    correlation_id = str(task_payload.get("correlation_id") or command_id or task_id)
    task_payload.update(
        {
            "agent_type": registry_definition.agent_type,
            "task_id": task_id,
            "command_id": command_id,
            "registry_key": registry_definition.agent_key,
            "resolved_agent_id": registry_definition.agent_id,
        }
    )

    agent_record, policy = resolve_agent_for_task(
        session,
        task_type="agent_task",
        requested_agent_id=registry_definition.agent_id,
    )
    if str(agent_record.id) != registry_definition.agent_id:
        raise ValueError("resolved persisted agent does not match registry-backed agent_task target")

    decision = validate_agent_policy(
        agent=agent_record,
        policy=policy,
        task_type="agent_task",
        owner_approved=True,
    )
    if not decision.allowed:
        write_audit_event(
            session,
            tenant_id=tenant_id,
            agent_id=agent_record.id,
            action="agent.runtime.denied",
            policy_result="deny",
            metadata={
                "task_id": task_id,
                "command_id": command_id,
                "correlation_id": correlation_id,
                "agent_name": deterministic_agent.name,
                "agent_type": deterministic_agent.agent_type,
                "registry_key": registry_definition.agent_key,
                "reason": decision.reason,
            },
        )
        return {
            "tenant_id": tenant_id,
            "agent_id": str(agent_record.id),
            "registry_key": registry_definition.agent_key,
            "agent_name": deterministic_agent.name,
            "agent_type": deterministic_agent.agent_type,
            "agent_run_id": None,
            "task_id": task_id,
            "task_type": "agent_task",
            "status": "denied",
            "steps_executed": 0,
            "tools_used": [],
            "duration_ms": 0.0,
            "error_code": "agent_policy_denied",
            "error_message": "agent execution denied",
            "result": {
                "registry_key": registry_definition.agent_key,
                "agent_name": deterministic_agent.name,
                "agent_type": deterministic_agent.agent_type,
                "task_id": task_id,
                "steps_executed": 0,
                "tools_used": [],
                "duration_ms": 0.0,
                "reason": decision.reason,
            },
        }

    now = datetime.now(timezone.utc)
    run = AgentRun(
        tenant_id=tenant_id or "owner",
        agent_id=agent_record.id,
        job_id=None,
        task_type="agent_task",
        status=AgentRunStatus.running,
        input_payload=task_payload,
        started_at=now,
        updated_at=now,
    )
    session.add(run)
    session.flush()

    state_store.create_run(
        session,
        run_id=run.id,
        tenant_id=tenant_id,
        agent_id=str(agent_record.id),
        agent_type=deterministic_agent.agent_type,
        command_id=command_id,
        task_id=task_id,
        status=AgentRuntimeStateStatus.running,
        current_step="agent.plan",
        last_decision={"agent_type": deterministic_agent.agent_type, "registry_key": registry_definition.agent_key, "policy": "allowed"},
    )
    state_store.create_task(
        session,
        task_id=task_id,
        run_id=run.id,
        tenant_id=tenant_id,
        task_type="agent_task",
        status=AgentRuntimeStateStatus.running,
        input_summary={
            "command_id": command_id,
            "objective": task_payload.get("objective") or task_payload.get("query"),
            "agent_type": deterministic_agent.agent_type,
            "registry_key": registry_definition.agent_key,
        },
    )
    state_store.append_event(
        session,
        run_id=run.id,
        tenant_id=tenant_id,
        task_id=task_id,
        event_type="run_started",
        step_name="agent.plan",
        message="agent runtime started",
        payload_summary={
            "agent_name": deterministic_agent.name,
            "agent_type": deterministic_agent.agent_type,
            "registry_key": registry_definition.agent_key,
            "command_id": command_id,
        },
    )

    write_audit_event(
        session,
        tenant_id=tenant_id,
        agent_id=agent_record.id,
        action="agent.runtime.started",
        policy_result="allow",
        metadata={
            "task_id": task_id,
            "command_id": command_id,
            "run_id": run.id,
            "correlation_id": correlation_id,
            "agent_name": deterministic_agent.name,
            "agent_type": deterministic_agent.agent_type,
            "registry_key": registry_definition.agent_key,
        },
    )

    sandbox = SandboxExecutor()
    secret_manager = SecretManager()
    _ = secret_manager
    mediation = create_tool_mediation_service(audit_writer=lambda event: write_tool_audit_event(session, event))
    started = monotonic()
    step_index = 0

    try:
        def _execute_step(step: AgentStep):
            nonlocal step_index
            step_index += 1
            step_name = f"step_{step_index}:{step.tool_name}"
            state_store.update_current_step(
                session,
                run_id=run.id,
                current_step=step_name,
                last_decision={
                    "tool_name": step.tool_name,
                    "connector_name": step.connector_name,
                    "action": step.action,
                    "registry_key": registry_definition.agent_key,
                },
            )
            state_store.append_event(
                session,
                run_id=run.id,
                tenant_id=tenant_id,
                task_id=task_id,
                event_type="step_started",
                step_name=step_name,
                message="agent step started",
                payload_summary={
                    "tool_name": step.tool_name,
                    "connector_name": step.connector_name,
                    "action": step.action,
                },
            )
            tool_request = _build_tool_request(
                command_id=command_id,
                run_id=run.id,
                correlation_id=correlation_id,
                agent_id=agent_record.id,
                step=step,
                task=task_payload,
            )
            with allow_governed_network_calls():
                tool_result = mediation.mediate(
                    tool_request,
                    tenant_id=tenant_id,
                    project_id=project_id,
                )
            state_store.append_event(
                session,
                run_id=run.id,
                tenant_id=tenant_id,
                task_id=task_id,
                event_type="step_result",
                step_name=step_name,
                message="agent step completed",
                payload_summary={
                    "tool_status": tool_result.status.value,
                    "tool_name": tool_result.tool_name,
                    "error_code": tool_result.error_code,
                },
                severity="error" if tool_result.status.value in {"failed", "timeout"} else "info",
            )
            return tool_result

        loop_result = run_agent(
            deterministic_agent,
            task_payload,
            step_executor=_execute_step,
            plan_executor=sandbox.execute,
            act_executor=sandbox.execute,
        )
        elapsed_seconds = monotonic() - started
        if elapsed_seconds > policy.max_runtime_seconds:
            raise TimeoutError("agent run exceeded max_runtime_seconds")

        finished = datetime.now(timezone.utc)
        result_payload = {
            "registry_key": registry_definition.agent_key,
            "agent_name": deterministic_agent.name,
            "agent_type": deterministic_agent.agent_type,
            "task_id": task_id,
            "command_id": command_id,
            "agent_run_id": run.id,
            "steps_executed": loop_result.steps_executed,
            "tools_used": loop_result.tools_used,
            "duration_ms": loop_result.duration_ms,
            "results": loop_result.step_results,
        }
        run.status = AgentRunStatus.completed if loop_result.status == "completed" else AgentRunStatus.failed
        run.result = result_payload
        run.error = None if loop_result.status == "completed" else loop_result.status
        run.finished_at = finished
        run.updated_at = finished
        session.add(run)
        session.flush()

        final_state = AgentRuntimeStateStatus.completed if loop_result.status == "completed" else AgentRuntimeStateStatus.failed
        state_store.update_run_status(
            session,
            run_id=run.id,
            status=final_state,
            last_decision={
                "status": loop_result.status,
                "registry_key": registry_definition.agent_key,
                "steps_executed": loop_result.steps_executed,
                "tools_used": loop_result.tools_used,
            },
            last_error=None if loop_result.status == "completed" else loop_result.status,
        )
        state_store.update_task(
            session,
            task_id=task_id,
            status=final_state,
            output_summary={
                "registry_key": registry_definition.agent_key,
                "steps_executed": loop_result.steps_executed,
                "tools_used": loop_result.tools_used,
                "duration_ms": loop_result.duration_ms,
            },
            failure_metadata=None if loop_result.status == "completed" else {"status": loop_result.status},
        )
        state_store.append_event(
            session,
            run_id=run.id,
            tenant_id=tenant_id,
            task_id=task_id,
            event_type="run_completed" if loop_result.status == "completed" else "run_finished",
            step_name=None,
            message="agent runtime finished",
            payload_summary={
                "status": loop_result.status,
                "registry_key": registry_definition.agent_key,
                "steps_executed": loop_result.steps_executed,
                "tools_used": loop_result.tools_used,
                "duration_ms": loop_result.duration_ms,
            },
            severity="error" if loop_result.status != "completed" else "info",
        )

        policy_result = "allow" if loop_result.status == "completed" else "deny" if loop_result.status == "denied" else "error"
        write_audit_event(
            session,
            tenant_id=tenant_id,
            agent_id=agent_record.id,
            action="agent.runtime.completed" if loop_result.status == "completed" else "agent.runtime.finished",
            policy_result=policy_result,
            metadata={
                "task_id": task_id,
                "command_id": command_id,
                "run_id": run.id,
                "correlation_id": correlation_id,
                "agent_name": deterministic_agent.name,
                "agent_type": deterministic_agent.agent_type,
                "registry_key": registry_definition.agent_key,
                "steps_executed": loop_result.steps_executed,
                "tools_used": loop_result.tools_used,
                "duration_ms": loop_result.duration_ms,
                "status": loop_result.status,
            },
        )

        return {
            "tenant_id": run.tenant_id,
            "agent_id": str(agent_record.id),
            "registry_key": registry_definition.agent_key,
            "agent_name": deterministic_agent.name,
            "agent_type": deterministic_agent.agent_type,
            "agent_run_id": run.id,
            "task_id": task_id,
            "task_type": "agent_task",
            "status": loop_result.status,
            "steps_executed": loop_result.steps_executed,
            "tools_used": loop_result.tools_used,
            "duration_ms": loop_result.duration_ms,
            "result": result_payload,
        }

    except Exception as exc:
        error_code, error_message, status = _sanitize_error(exc)
        finished = datetime.now(timezone.utc)
        duration_ms = round((monotonic() - started) * 1000, 2)
        run.status = AgentRunStatus.failed
        run.error = error_message
        run.result = {
            "registry_key": registry_definition.agent_key,
            "agent_name": deterministic_agent.name,
            "agent_type": deterministic_agent.agent_type,
            "task_id": task_id,
            "command_id": command_id,
            "agent_run_id": run.id,
            "steps_executed": step_index,
            "tools_used": [],
            "duration_ms": duration_ms,
            "error_code": error_code,
        }
        run.finished_at = finished
        run.updated_at = finished
        session.add(run)
        session.flush()
        state_store.update_run_status(
            session,
            run_id=run.id,
            status=AgentRuntimeStateStatus.failed,
            last_decision={"status": status, "registry_key": registry_definition.agent_key, "error_code": error_code},
            last_error=error_message,
        )
        state_store.update_task(
            session,
            task_id=task_id,
            status=AgentRuntimeStateStatus.failed,
            output_summary={"registry_key": registry_definition.agent_key, "steps_executed": step_index, "duration_ms": duration_ms},
            failure_metadata={"status": status, "error_code": error_code},
        )
        state_store.append_event(
            session,
            run_id=run.id,
            tenant_id=tenant_id,
            task_id=task_id,
            event_type="run_failed",
            step_name=None,
            message="agent runtime failed",
            payload_summary={
                "status": status,
                "registry_key": registry_definition.agent_key,
                "error_code": error_code,
                "duration_ms": duration_ms,
                "steps_executed": step_index,
            },
            severity="error",
        )
        write_audit_event(
            session,
            tenant_id=tenant_id,
            agent_id=agent_record.id,
            action="agent.runtime.failed" if status == "failed" else "agent.runtime.finished",
            policy_result="deny" if status == "denied" else "error",
            metadata={
                "task_id": task_id,
                "command_id": command_id,
                "run_id": run.id,
                "correlation_id": correlation_id,
                "agent_name": deterministic_agent.name,
                "agent_type": deterministic_agent.agent_type,
                "registry_key": registry_definition.agent_key,
                "steps_executed": step_index,
                "tools_used": [],
                "duration_ms": duration_ms,
                "error_code": error_code,
                "status": status,
            },
        )
        return {
            "tenant_id": run.tenant_id,
            "agent_id": str(agent_record.id),
            "registry_key": registry_definition.agent_key,
            "agent_name": deterministic_agent.name,
            "agent_type": deterministic_agent.agent_type,
            "agent_run_id": run.id,
            "task_id": task_id,
            "task_type": "agent_task",
            "status": status,
            "steps_executed": step_index,
            "tools_used": [],
            "duration_ms": duration_ms,
            "error_code": error_code,
            "error_message": error_message,
            "result": run.result,
        }


def execute_agent_task(
    session: Session,
    *,
    job_id: str,
    task_type: str,
    payload: dict,
    owner_approved: bool,
    tenant_id: str = "owner",
    requested_agent_id: str | None = None,
) -> dict:
    state_store = get_agent_state_store()
    if task_type not in SUPPORTED_AGENT_TASK_TYPES:
        raise ValueError(f"unsupported agent task_type: {task_type}")

    agent, policy = resolve_agent_for_task(session, task_type=task_type, requested_agent_id=requested_agent_id)

    decision = validate_agent_policy(
        agent=agent,
        policy=policy,
        task_type=task_type,
        owner_approved=owner_approved,
    )
    if not decision.allowed:
        raise PermissionError(decision.reason)

    task_id = str(payload.get("task_id") or job_id)
    correlation_id = str(payload.get("correlation_id") or job_id)
    now = datetime.now(timezone.utc)
    run = AgentRun(
        tenant_id=tenant_id or "owner",
        agent_id=agent.id,
        job_id=job_id,
        task_type=task_type,
        status=AgentRunStatus.running,
        input_payload=payload or {},
        started_at=now,
        updated_at=now,
    )
    session.add(run)
    session.flush()

    state_store.create_run(
        session,
        run_id=run.id,
        tenant_id=tenant_id,
        agent_id=str(agent.id),
        agent_type=str(agent.agent_type or "runtime"),
        command_id=None,
        task_id=task_id,
        status=AgentRuntimeStateStatus.running,
        current_step=task_type,
        last_decision={"task_type": task_type, "policy": "allowed"},
    )
    state_store.create_task(
        session,
        task_id=task_id,
        run_id=run.id,
        tenant_id=tenant_id,
        task_type=task_type,
        status=AgentRuntimeStateStatus.running,
        input_summary={"job_id": job_id, "task_type": task_type},
    )
    state_store.append_event(
        session,
        run_id=run.id,
        tenant_id=tenant_id,
        task_id=task_id,
        event_type="run_started",
        step_name=task_type,
        message="legacy agent task started",
        payload_summary={"job_id": job_id, "correlation_id": correlation_id},
    )

    sandbox = SandboxExecutor()
    secret_manager = SecretManager()
    start = monotonic()

    try:
        result = sandbox.execute(lambda: _execute_controlled_task(task_type, payload or {}, secret_manager))
        elapsed = monotonic() - start
        if elapsed > policy.max_runtime_seconds:
            raise TimeoutError("agent run exceeded max_runtime_seconds")

        finished = datetime.now(timezone.utc)
        run.status = AgentRunStatus.completed
        run.result = result
        run.error = None
        run.finished_at = finished
        run.updated_at = finished
        session.add(run)
        session.flush()

        state_store.update_run_status(
            session,
            run_id=run.id,
            status=AgentRuntimeStateStatus.completed,
            last_decision={"task_type": task_type, "status": "completed"},
        )
        state_store.update_task(
            session,
            task_id=task_id,
            status=AgentRuntimeStateStatus.completed,
            output_summary={"job_id": job_id, "task_type": task_type},
        )
        state_store.append_event(
            session,
            run_id=run.id,
            tenant_id=tenant_id,
            task_id=task_id,
            event_type="run_completed",
            step_name=task_type,
            message="legacy agent task completed",
            payload_summary={"duration_ms": round(elapsed * 1000, 2)},
        )

        return {
            "tenant_id": run.tenant_id,
            "agent_id": str(agent.id),
            "agent_name": agent.name,
            "agent_run_id": run.id,
            "task_type": task_type,
            "status": run.status.value,
            "result": result,
        }

    except Exception as exc:
        finished = datetime.now(timezone.utc)
        error_code, error_message, status = _sanitize_error(exc)
        duration_ms = round((monotonic() - start) * 1000, 2)
        run.status = AgentRunStatus.failed
        run.error = error_message
        run.finished_at = finished
        run.updated_at = finished
        session.add(run)
        session.flush()
        state_store.update_run_status(
            session,
            run_id=run.id,
            status=AgentRuntimeStateStatus.failed,
            last_decision={"task_type": task_type, "status": status, "error_code": error_code},
            last_error=error_message,
        )
        state_store.update_task(
            session,
            task_id=task_id,
            status=AgentRuntimeStateStatus.failed,
            failure_metadata={"status": status, "error_code": error_code, "job_id": job_id},
        )
        state_store.append_event(
            session,
            run_id=run.id,
            tenant_id=tenant_id,
            task_id=task_id,
            event_type="run_failed",
            step_name=task_type,
            message="legacy agent task failed",
            payload_summary={"status": status, "error_code": error_code, "duration_ms": duration_ms},
            severity="error",
        )
        raise

