from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

from sqlalchemy.orm import Session

from ..planning import create_plan_runtime
from .workflow_definitions import derive_plan_request
from .workflow_models import WorkflowRunStatus
from .workflow_store import WorkflowStore, get_workflow_store


_metrics_lock = Lock()
_workflow_metrics: dict[str, int] = {
    "workflow_created_total": 0,
    "workflow_started_total": 0,
    "workflow_completed_total": 0,
    "workflow_failed_total": 0,
}
_workflow_summary: dict[str, Any] = {
    "by_status": {},
    "by_workflow_type": {},
    "last_transition_at": None,
}


def _increment(mapping: dict[str, int], key: str | None) -> None:
    if not key:
        return
    mapping[key] = int(mapping.get(key, 0)) + 1


def _record_workflow_event(metric_key: str, *, workflow_type: str | None = None, workflow_status: str | None = None) -> None:
    with _metrics_lock:
        if metric_key in _workflow_metrics:
            _workflow_metrics[metric_key] += 1
        _increment(_workflow_summary.setdefault("by_workflow_type", {}), workflow_type)
        _increment(_workflow_summary.setdefault("by_status", {}), workflow_status)
        _workflow_summary["last_transition_at"] = datetime.now(timezone.utc).isoformat()


def _truncate_error(value: Any, limit: int = 400) -> str:
    text = str(value or "workflow execution failed").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def get_workflow_runtime_metrics() -> dict[str, int]:
    with _metrics_lock:
        return {key: int(value) for key, value in _workflow_metrics.items()}


def get_workflow_runtime_summary() -> dict[str, Any]:
    with _metrics_lock:
        return {
            "by_status": dict(_workflow_summary.get("by_status", {})),
            "by_workflow_type": dict(_workflow_summary.get("by_workflow_type", {})),
            "last_transition_at": _workflow_summary.get("last_transition_at"),
        }


class WorkflowRuntime:
    def __init__(self, *, store: WorkflowStore | None = None) -> None:
        self.store = store or get_workflow_store()
        self.plan_runtime = create_plan_runtime()

    def execute_workflow(
        self,
        session: Session,
        *,
        tenant_id: str,
        command_id: str | None,
        workflow_type: str,
        intent: str,
        payload: dict[str, Any],
        project_id: str | None,
    ) -> dict[str, Any]:
        workflow = self.store.create_workflow(
            session,
            tenant_id=tenant_id,
            command_id=command_id,
            workflow_type=workflow_type,
            input_summary=payload,
            workflow_metadata={"intent": intent, "source": "workflow_sync"},
        )
        _record_workflow_event("workflow_created_total", workflow_type=workflow.workflow_type, workflow_status=workflow.status.value)

        created_plan_id: str | None = None

        try:
            plan_request = derive_plan_request(workflow_type=workflow_type, intent=intent, payload=payload)
            created_plan, _ = self.plan_runtime.create_plan(
                session,
                tenant_id=tenant_id,
                command_id=command_id or workflow.workflow_id,
                plan_type=plan_request["plan_type"],
                intent=plan_request["intent"],
                payload=plan_request["payload"],
            )
            created_plan_id = created_plan.plan_id
            workflow = self.store.mark_running(session, workflow_id=workflow.workflow_id, linked_plan_id=created_plan_id)
            _record_workflow_event("workflow_started_total", workflow_type=workflow.workflow_type, workflow_status=workflow.status.value)

            plan_execution = self.plan_runtime.process_plan(
                session,
                plan_id=created_plan_id,
                tenant_id=tenant_id,
                project_id=project_id,
            )
        except Exception as exc:
            error = _truncate_error(exc)
            workflow = self.store.mark_failed(
                session,
                workflow_id=workflow.workflow_id,
                linked_plan_id=created_plan_id,
                error=error,
                result_summary={
                    "workflow_type": workflow.workflow_type,
                    "linked_plan_id": created_plan_id,
                    "plan_status": "failed_exception",
                },
            )
            _record_workflow_event("workflow_failed_total", workflow_type=workflow.workflow_type, workflow_status=workflow.status.value)
            return {
                "workflow_id": workflow.workflow_id,
                "command_id": workflow.command_id,
                "workflow_type": workflow.workflow_type,
                "status": workflow.status.value,
                "linked_plan_id": workflow.linked_plan_id,
                "error": workflow.error,
                "result_summary": workflow.result_summary,
            }

        if str(plan_execution.get("status") or "").strip().lower() == WorkflowRunStatus.completed.value:
            workflow = self.store.mark_completed(
                session,
                workflow_id=workflow.workflow_id,
                linked_plan_id=created_plan_id,
                result_summary={
                    "workflow_type": workflow.workflow_type,
                    "linked_plan_id": created_plan_id,
                    "plan_status": plan_execution.get("status"),
                    "total_steps": plan_execution.get("total_steps"),
                    "current_step_index": plan_execution.get("current_step_index"),
                    "plan_result": plan_execution,
                },
            )
            _record_workflow_event("workflow_completed_total", workflow_type=workflow.workflow_type, workflow_status=workflow.status.value)
        else:
            error = _truncate_error(plan_execution.get("error") or plan_execution.get("status") or "workflow execution failed")
            workflow = self.store.mark_failed(
                session,
                workflow_id=workflow.workflow_id,
                linked_plan_id=created_plan_id,
                error=error,
                result_summary={
                    "workflow_type": workflow.workflow_type,
                    "linked_plan_id": created_plan_id,
                    "plan_status": plan_execution.get("status"),
                    "total_steps": plan_execution.get("total_steps"),
                    "current_step_index": plan_execution.get("current_step_index"),
                    "plan_result": plan_execution,
                },
            )
            _record_workflow_event("workflow_failed_total", workflow_type=workflow.workflow_type, workflow_status=workflow.status.value)

        return {
            "workflow_id": workflow.workflow_id,
            "command_id": workflow.command_id,
            "workflow_type": workflow.workflow_type,
            "status": workflow.status.value,
            "linked_plan_id": workflow.linked_plan_id,
            "error": workflow.error,
            "result_summary": workflow.result_summary,
        }


_workflow_runtime = WorkflowRuntime()


def create_workflow_runtime() -> WorkflowRuntime:
    return _workflow_runtime
