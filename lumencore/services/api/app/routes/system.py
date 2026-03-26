from __future__ import annotations

from datetime import datetime, timezone
import socket
import time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from ..config import settings
from ..db import session_scope
from ..models import Agent, CommandRun
from ..security import internal_observability_boundary
from ..services.deployment.deployment_service import get_deployment_state
from ..services.observability import
from ..services.recovery.recovery_service import get_recovery_status (
    get_agent_run_counts,
    get_agent_runtime_snapshot,
    get_agent_state_snapshot,
    get_command_run_stats,
    get_connector_execution_snapshot,
    get_connector_metrics_snapshot,
    get_execution_gate_snapshot,
    get_execution_scheduler_metrics_snapshot,
    get_execution_scheduler_summary_snapshot,
    get_execution_control_snapshot_view,
    get_execution_policy_snapshot_view,
    get_execution_task_snapshot,
    get_job_status_counts,
    get_latest_agent_run_activity,
    get_latest_job_activity,
    get_lifecycle_control_snapshot,
    get_operator_event_snapshot,
    get_operator_queue_snapshot,
    get_plan_runtime_metrics_snapshot,
    get_plan_runtime_summary_snapshot,
    get_plan_snapshot,
    get_policy_denies_total,
    get_tool_execution_snapshot,
    get_tool_metrics_snapshot,
    get_workflow_failed_total,
    get_workflow_runtime_metrics_snapshot,
    get_workflow_runtime_summary_snapshot,
    get_workflow_snapshot,
)
from ..services.runtime_health import get_runtime_health_snapshot

router = APIRouter(prefix="/api/system", tags=["system"])

SYSTEM_START_TIME = time.monotonic()


@router.get("/health")
def system_health() -> dict:
    health = get_runtime_health_snapshot()
    deployment = get_deployment_state()
    return {
        "status": health["status"],
        "service": "lumencore-api",
        "phase": settings.system_phase,
        "release": {
            "release_id": settings.release_id,
            "manifest_sha256": settings.release_manifest_sha256 or None,
        },
        "components": {
            "database": health["api"]["database"],
            "redis": health["api"]["redis"],
            "worker": health["worker"],
            "scheduler": health["scheduler"],
        },
        "recovery": get_recovery_status(),
        "deployment": {
            "last_restart_at": deployment.get("last_restart_at"),
            "restart_count": int(deployment.get("restart_count", 0)),
            "failed_restarts": int(deployment.get("failed_restarts", 0)),
        },
    }


@router.get("/info")
def system_info() -> dict:
    return {
        "service": "lumencore-api",
        "phase": settings.system_phase,
        "release": {
            "release_id": settings.release_id,
            "manifest_sha256": settings.release_manifest_sha256 or None,
        },
        "environment": settings.app_env,
        "hostname": socket.gethostname(),
        "api_port": settings.api_port,
    }


@router.get("/overview")
def system_overview() -> dict:
    health = get_runtime_health_snapshot()

    with session_scope() as session:
        agents = int(session.execute(select(func.count(Agent.id))).scalar_one())
        command_rows = session.execute(select(CommandRun.status, func.count()).group_by(CommandRun.status)).all()
        status_counts = {str(status or "unknown"): int(count) for status, count in command_rows}

    return {
        "agents": agents,
        "commands_total": int(sum(status_counts.values())),
        "commands_running": int(status_counts.get("running", 0)),
        "commands_failed": int(status_counts.get("failed", 0)),
        "queue_size": int(status_counts.get("pending", 0) + status_counts.get("queued", 0)),
        "uptime_seconds": int(max(0, time.monotonic() - SYSTEM_START_TIME)),
        "release_id": settings.release_id,
        "redis_status": "healthy" if health["api"]["redis"]["ok"] else "degraded",
        "database_status": "healthy" if health["api"]["database"]["ok"] else "degraded",
        "system_status": "healthy" if health["status"] == "ok" else "degraded",
    }


@router.get("/execution-summary", dependencies=[Depends(internal_observability_boundary)])
def execution_summary() -> dict:
    health = get_runtime_health_snapshot()
    deployment = get_deployment_state()

    with session_scope() as session:
        job_counts, total_jobs = get_job_status_counts(session)
        latest_job_activity = get_latest_job_activity(session)
        agent_run_counts, total_agent_runs = get_agent_run_counts(session)
        latest_agent_run_activity = get_latest_agent_run_activity(session)
        total_commands, latest_command_activity = get_command_run_stats(session)
        execution_gate = get_execution_gate_snapshot(session)
        lifecycle_control = get_lifecycle_control_snapshot(session)
        operator_queue = get_operator_queue_snapshot(session)
        operator_events = get_operator_event_snapshot(session, limit=20)
        policy_denies_total = get_policy_denies_total(session)
        agent_runtime = get_agent_runtime_snapshot(session)
        agent_state = get_agent_state_snapshot(session)
        execution_tasks = get_execution_task_snapshot(session)
        execution_control = get_execution_control_snapshot_view(session)
        execution_policy = get_execution_policy_snapshot_view(session)
        planning = get_plan_snapshot(session)
        workflows = get_workflow_snapshot(session)
        workflow_failed_total = get_workflow_failed_total(session)

    connector_metrics = get_connector_metrics_snapshot()
    connector_execution = get_connector_execution_snapshot()
    connector_totals = connector_execution.get("totals", {})
    tool_metrics = get_tool_metrics_snapshot()
    tool_execution = get_tool_execution_snapshot()
    execution_scheduler_metrics = get_execution_scheduler_metrics_snapshot()
    execution_scheduler = get_execution_scheduler_summary_snapshot()
    plan_runtime_metrics = get_plan_runtime_metrics_snapshot()
    plan_runtime = get_plan_runtime_summary_snapshot()
    workflow_runtime_metrics = get_workflow_runtime_metrics_snapshot()
    workflow_runtime = get_workflow_runtime_summary_snapshot()

    return {
        "status": health["status"],
        "service": "lumencore-api",
        "phase": settings.system_phase,
        "release": {
            "release_id": settings.release_id,
            "manifest_sha256": settings.release_manifest_sha256 or None,
        },
        "recovery": get_recovery_status(),
        "deployment": {
            "last_deploy_at": deployment.get("last_deploy_at"),
            "last_known_good_release": deployment.get("last_known_good_release"),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "health": {
            "api": health["api"],
            "worker": health["worker"],
            "scheduler": health["scheduler"],
        },
        "jobs": {
            "counts_by_status": job_counts,
            "total_jobs": total_jobs,
            "latest_job_activity": latest_job_activity.isoformat() if latest_job_activity else None,
        },
        "agents": {
            "run_counts_by_status": agent_run_counts,
            "total_runs": total_agent_runs,
            "latest_agent_activity": latest_agent_run_activity.isoformat() if latest_agent_run_activity else None,
        },
        "agent_runtime": agent_runtime,
        "agent_state": agent_state,
        "execution_tasks": execution_tasks,
        "execution_control": execution_control,
        "execution_policy": execution_policy,
        "execution_scheduler": execution_scheduler,
        "planning": planning,
        "planning_events": {"event_counters": plan_runtime_metrics, "event_summary": plan_runtime},
        "plan_runtime": plan_runtime,
        "workflows": workflows,
        "workflow_events": {"event_counters": workflow_runtime_metrics, "event_summary": workflow_runtime},
        "workflow_runtime": workflow_runtime,
        "commands": {
            "total_commands": total_commands,
            "latest_command_activity": latest_command_activity.isoformat() if latest_command_activity else None,
        },
        "execution_gate": execution_gate,
        "lifecycle_control": lifecycle_control,
        "operator_queue": operator_queue,
        "operator_events": operator_events,
        "connectors": connector_metrics,
        "connector_execution": connector_execution,
        "tools": tool_metrics,
        "tool_execution": tool_execution,
        "agent_run_total": total_agent_runs,
        "agent_run_failed": int(agent_run_counts.get("failed", 0)),
        "policy_denies_total": policy_denies_total,
        "command_run_total": total_commands,
        "current_policy_evaluated_total": int(execution_gate.get("current_totals", {}).get("policy_evaluated_total", 0)),
        "current_execution_allowed_total": int(execution_gate.get("current_totals", {}).get("execution_allowed_total", 0)),
        "current_approval_required_total": int(execution_gate.get("current_totals", {}).get("approval_required_total", 0)),
        "current_approval_granted_total": int(execution_gate.get("current_totals", {}).get("approval_granted_total", 0)),
        "current_execution_denied_total": int(execution_gate.get("current_totals", {}).get("execution_denied_total", 0)),
        "current_controlled_command_total": int(lifecycle_control.get("current_totals", {}).get("controlled_command_total", 0)),
        "current_cancelled_command_total": int(lifecycle_control.get("current_totals", {}).get("cancelled_command_total", 0)),
        "current_retried_command_total": int(lifecycle_control.get("current_totals", {}).get("retried_command_total", 0)),
        "current_attention_command_total": int(operator_queue.get("current_totals", {}).get("attention_command_total", 0)),
        "connector_calls_total": int(connector_metrics.get("connector_calls_total", 0)),
        "connector_denied_total": int(connector_metrics.get("connector_denied_total", 0)),
        "connector_errors_total": int(connector_metrics.get("connector_errors_total", 0)),
        "connector_success_total": int(connector_totals.get("connector_success_total", 0)),
        "connector_missing_secret_total": int(connector_totals.get("connector_missing_secret_total", 0)),
        "connector_timeout_total": int(connector_totals.get("connector_timeout_total", 0)),
        "connector_validation_failure_total": int(connector_totals.get("connector_validation_failure_total", 0)),
        "connector_provider_failure_total": int(connector_totals.get("connector_provider_failure_total", 0)),
        "tool_requests_total": int(tool_metrics.get("tool_requests_total", 0)),
        "tool_success_total": int(tool_metrics.get("tool_success_total", 0)),
        "tool_denied_total": int(tool_metrics.get("tool_denied_total", 0)),
        "tool_failed_total": int(tool_metrics.get("tool_failed_total", 0)),
        "tool_timeout_total": int(tool_metrics.get("tool_timeout_total", 0)),
        "execution_task_total": int(execution_tasks.get("total_tasks", 0)),
        "task_created_total": int(execution_scheduler_metrics.get("task_created_total", 0)),
        "task_started_total": int(execution_scheduler_metrics.get("task_started_total", 0)),
        "task_retry_total": int(execution_scheduler_metrics.get("task_retry_total", 0)),
        "task_failed_total": int(execution_scheduler_metrics.get("task_failed_total", 0)),
        "task_completed_total": int(execution_scheduler_metrics.get("task_completed_total", 0)),
        "plan_run_total": int(planning.get("plan_runs", {}).get("total_plans", 0)),
        "plan_step_total": int(planning.get("plan_steps", {}).get("total_steps", 0)),
        "plan_event_created_total": int(plan_runtime_metrics.get("plan_created_total", 0)),
        "plan_event_started_total": int(plan_runtime_metrics.get("plan_started_total", 0)),
        "plan_event_step_queued_total": int(plan_runtime_metrics.get("plan_step_queued_total", 0)),
        "plan_event_step_completed_total": int(plan_runtime_metrics.get("plan_step_completed_total", 0)),
        "plan_event_step_failed_total": int(plan_runtime_metrics.get("plan_step_failed_total", 0)),
        "plan_event_completed_total": int(plan_runtime_metrics.get("plan_completed_total", 0)),
        "plan_event_failed_total": int(plan_runtime_metrics.get("plan_failed_total", 0)),
        "workflow_run_total": int(workflows.get("workflow_runs", {}).get("total_workflows", 0)),
        "workflow_event_created_total": int(workflow_runtime_metrics.get("workflow_created_total", 0)),
        "workflow_event_started_total": int(workflow_runtime_metrics.get("workflow_started_total", 0)),
        "workflow_event_completed_total": int(workflow_runtime_metrics.get("workflow_completed_total", 0)),
        "workflow_event_failed_total": workflow_failed_total,
    }
