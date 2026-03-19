from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

from sqlalchemy.orm import Session

from ..execution import create_execution_scheduler
from ..models import ExecutionTaskStatus
from .decomposer import decompose_plan
from .plan_models import PlanRunStatus, PlanStepStatus
from .plan_store import PlanStore, get_plan_store


_metrics_lock = Lock()
_plan_runtime_metrics: dict[str, int] = {
    "plan_created_total": 0,
    "plan_started_total": 0,
    "plan_step_queued_total": 0,
    "plan_step_completed_total": 0,
    "plan_step_failed_total": 0,
    "plan_completed_total": 0,
    "plan_failed_total": 0,
}
_plan_runtime_summary: dict[str, Any] = {
    "by_plan_status": {},
    "by_step_status": {},
    "by_plan_type": {},
    "last_transition_at": None,
}


def _increment(mapping: dict[str, int], key: str | None) -> None:
    if not key:
        return
    mapping[key] = int(mapping.get(key, 0)) + 1


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _record_plan_event(metric_key: str, *, plan_type: str | None = None, plan_status: str | None = None, step_status: str | None = None) -> None:
    with _metrics_lock:
        if metric_key in _plan_runtime_metrics:
            _plan_runtime_metrics[metric_key] += 1
        _increment(_plan_runtime_summary.setdefault("by_plan_type", {}), plan_type)
        _increment(_plan_runtime_summary.setdefault("by_plan_status", {}), plan_status)
        _increment(_plan_runtime_summary.setdefault("by_step_status", {}), step_status)
        _plan_runtime_summary["last_transition_at"] = datetime.now(timezone.utc).isoformat()


def get_plan_runtime_metrics() -> dict[str, int]:
    with _metrics_lock:
        return {key: int(value) for key, value in _plan_runtime_metrics.items()}


def get_plan_runtime_summary() -> dict[str, Any]:
    with _metrics_lock:
        return {
            "by_plan_status": dict(_plan_runtime_summary.get("by_plan_status", {})),
            "by_step_status": dict(_plan_runtime_summary.get("by_step_status", {})),
            "by_plan_type": dict(_plan_runtime_summary.get("by_plan_type", {})),
            "last_transition_at": _plan_runtime_summary.get("last_transition_at"),
        }


class PlanRuntime:
    def __init__(self, *, store: PlanStore | None = None) -> None:
        self.store = store or get_plan_store()
        self.scheduler = create_execution_scheduler()

    def create_plan(
        self,
        session: Session,
        *,
        tenant_id: str,
        command_id: str,
        plan_type: str,
        intent: str,
        payload: dict[str, Any],
    ) -> tuple[Any, list[Any]]:
        step_defs = decompose_plan(intent=intent, plan_type=plan_type, payload=payload)
        plan = self.store.create_plan(
            session,
            tenant_id=tenant_id,
            command_id=command_id,
            plan_type=plan_type,
            total_steps=len(step_defs),
            plan_metadata={"intent": intent, "payload": payload},
        )
        _record_plan_event("plan_created_total", plan_type=plan.plan_type, plan_status=plan.status.value)
        steps = [
            self.store.create_step(
                session,
                plan_id=plan.plan_id,
                step_index=step["step_index"],
                step_type=step["step_type"],
                agent_type=step["agent_type"],
                title=step["title"],
                payload_json=step["payload"],
            )
            for step in step_defs
        ]
        return plan, steps

    def submit_next_step(self, session: Session, *, plan_id: str, tenant_id: str, project_id: str | None) -> tuple[Any, Any] | tuple[None, None]:
        step = self.store.get_next_pending_step(session, plan_id)
        if step is None:
            return None, None

        plan = self.store.get_plan(session, plan_id)
        if plan is None:
            raise ValueError(f"plan not found: {plan_id}")
        was_pending = plan.status == PlanRunStatus.pending
        plan = self.store.mark_plan_running(session, plan_id=plan_id, current_step_index=step.step_index)
        if was_pending:
            _record_plan_event("plan_started_total", plan_type=plan.plan_type, plan_status=PlanRunStatus.running.value)
        execution_task = self.scheduler.submit_agent_task(
            session,
            tenant_id=tenant_id,
            command_id=plan.command_id,
            agent_id=None,
            agent_type=step.agent_type,
            task_type=step.step_type,
            payload={
                **dict(step.payload_json or {}),
                "task_type": step.step_type,
                "agent_type": step.agent_type,
                "task_id": step.step_id,
                "correlation_id": step.step_id,
            },
            project_id=project_id,
            priority=20 + step.step_index,
            max_retries=0,
            task_metadata={
                "source": "planning.plan_sync",
                "plan_id": plan_id,
                "plan_step_id": step.step_id,
                "step_index": step.step_index,
                "title": step.title,
            },
        )
        step = self.store.mark_step_queued(session, step_id=step.step_id, execution_task_id=execution_task.task_id)
        _record_plan_event("plan_step_queued_total", plan_type=plan.plan_type, plan_status=PlanRunStatus.running.value, step_status=step.status.value)
        return step, execution_task

    def process_plan(self, session: Session, *, plan_id: str, tenant_id: str, project_id: str | None) -> dict[str, Any]:
        plan = self.store.get_plan(session, plan_id)
        if plan is None:
            raise ValueError(f"plan not found: {plan_id}")

        completed_steps: list[dict[str, Any]] = []

        while True:
            next_step = self.store.get_next_pending_step(session, plan_id)
            if next_step is None:
                plan = self.store.mark_plan_completed(
                    session,
                    plan_id=plan_id,
                    result_summary={
                        "completed_steps": completed_steps,
                        "total_steps": plan.total_steps,
                    },
                )
                _record_plan_event("plan_completed_total", plan_type=plan.plan_type, plan_status=plan.status.value)
                return self.get_plan_summary(session, plan_id)

            step, execution_task = self.submit_next_step(session, plan_id=plan_id, tenant_id=tenant_id, project_id=project_id)
            if step is None or execution_task is None:
                raise RuntimeError("failed to submit next plan step")

            self.store.mark_step_running(session, step_id=step.step_id)
            processed_task = self.scheduler.process_task(session, task_id=execution_task.task_id, retry_on_failure=False)
            task_status = _status_value(processed_task.status)
            task_result = dict(processed_task.result_summary or {})
            agent_execution = dict(task_result.get("agent_execution") or {})

            if task_status == ExecutionTaskStatus.completed.value:
                completed_step = self.store.mark_step_completed(
                    session,
                    step_id=step.step_id,
                    result_summary={
                        "execution_task_id": processed_task.task_id,
                        "execution_task_status": task_status,
                        "agent_execution": agent_execution,
                    },
                )
                completed_steps.append({
                    "step_id": completed_step.step_id,
                    "step_index": completed_step.step_index,
                    "agent_type": completed_step.agent_type,
                    "title": completed_step.title,
                    "execution_task_id": processed_task.task_id,
                    "status": completed_step.status.value,
                })
                _record_plan_event("plan_step_completed_total", plan_type=plan.plan_type, plan_status=PlanRunStatus.running.value, step_status=PlanStepStatus.completed.value)
                continue

            error = str(agent_execution.get("error_message") or processed_task.error or task_status)
            failed_step = self.store.mark_step_failed(
                session,
                step_id=step.step_id,
                error=error,
                result_summary={
                    "execution_task_id": processed_task.task_id,
                    "execution_task_status": task_status,
                    "agent_execution": agent_execution,
                },
            )
            plan = self.store.mark_plan_failed(
                session,
                plan_id=plan_id,
                current_step_index=failed_step.step_index,
                error=error,
                result_summary={
                    "failed_step_id": failed_step.step_id,
                    "failed_step_index": failed_step.step_index,
                    "execution_task_id": processed_task.task_id,
                    "execution_task_status": task_status,
                    "completed_steps": completed_steps,
                },
            )
            _record_plan_event("plan_step_failed_total", plan_type=plan.plan_type, plan_status=plan.status.value, step_status=PlanStepStatus.failed.value)
            _record_plan_event("plan_failed_total", plan_type=plan.plan_type, plan_status=plan.status.value)
            return self.get_plan_summary(session, plan_id)

    def get_plan_summary(self, session: Session, plan_id: str) -> dict[str, Any]:
        plan = self.store.get_plan(session, plan_id)
        if plan is None:
            raise ValueError(f"plan not found: {plan_id}")
        steps = self.store.list_steps(session, plan_id)
        return {
            "plan_id": plan.plan_id,
            "command_id": plan.command_id,
            "plan_type": plan.plan_type,
            "status": plan.status.value,
            "total_steps": plan.total_steps,
            "current_step_index": plan.current_step_index,
            "error": plan.error,
            "result_summary": plan.result_summary,
            "steps": [step.model_dump(mode="json") for step in steps],
        }


_plan_runtime = PlanRuntime()


def create_plan_runtime() -> PlanRuntime:
    return _plan_runtime
