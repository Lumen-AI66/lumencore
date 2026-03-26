from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

from sqlalchemy.orm import Session

from ..agents.agent_runtime import execute_agent
from .retry_policy import ExecutionRetryPolicy
from .task_models import ExecutionTask, ExecutionTaskStatus
from ..models import CommandRun
from ..services.execution_control import is_execution_allowed
from ..services.policy_engine import evaluate_execution_policy, persist_policy_state
from .task_queue import ExecutionTaskQueue, get_execution_task_queue
from .task_store import ExecutionTaskStore, get_execution_task_store


_metrics_lock = Lock()
_scheduler_metrics: dict[str, int] = {
    "task_created_total": 0,
    "task_started_total": 0,
    "task_retry_total": 0,
    "task_failed_total": 0,
    "task_completed_total": 0,
}
_scheduler_summary: dict[str, Any] = {
    "by_status": {},
    "by_agent": {},
    "by_task_type": {},
    "last_transition_at": None,
}


def _increment(mapping: dict[str, int], key: str | None) -> None:
    if not key:
        return
    mapping[key] = int(mapping.get(key, 0)) + 1


def _record_scheduler_event(event_type: str, task: ExecutionTask) -> None:
    metric_key = f"{event_type}_total"
    with _metrics_lock:
        if metric_key in _scheduler_metrics:
            _scheduler_metrics[metric_key] += 1
        _increment(_scheduler_summary.setdefault("by_status", {}), task.status.value)
        _increment(_scheduler_summary.setdefault("by_agent", {}), task.agent_id or task.agent_type)
        _increment(_scheduler_summary.setdefault("by_task_type", {}), task.task_type)
        _scheduler_summary["last_transition_at"] = datetime.now(timezone.utc).isoformat()



def get_execution_scheduler_metrics() -> dict[str, int]:
    with _metrics_lock:
        return {key: int(value) for key, value in _scheduler_metrics.items()}


def get_execution_scheduler_summary() -> dict[str, Any]:
    with _metrics_lock:
        return {
            "by_status": dict(_scheduler_summary.get("by_status", {})),
            "by_agent": dict(_scheduler_summary.get("by_agent", {})),
            "by_task_type": dict(_scheduler_summary.get("by_task_type", {})),
            "last_transition_at": _scheduler_summary.get("last_transition_at"),
        }


class ExecutionScheduler:
    def __init__(
        self,
        *,
        queue: ExecutionTaskQueue | None = None,
        store: ExecutionTaskStore | None = None,
        retry_policy: ExecutionRetryPolicy | None = None,
    ) -> None:
        self.queue = queue or get_execution_task_queue()
        self.store = store or get_execution_task_store()
        self.retry_policy = retry_policy or ExecutionRetryPolicy()

    def submit_agent_task(
        self,
        session: Session,
        *,
        tenant_id: str,
        agent_id: str | None,
        agent_type: str,
        task_type: str,
        payload: dict[str, Any],
        project_id: str | None,
        command_id: str | None = None,
        priority: int = 100,
        max_retries: int = 0,
        task_metadata: dict[str, Any] | None = None,
    ) -> ExecutionTask:
        task = self.queue.enqueue(
            session,
            tenant_id=tenant_id,
            command_id=command_id,
            agent_id=agent_id,
            agent_type=agent_type,
            task_type=task_type,
            payload_json={"task": payload or {}, "project_id": project_id},
            priority=priority,
            max_retries=max_retries,
            task_metadata=task_metadata or {},
        )
        _record_scheduler_event("task_created", task)
        return task

    def _sanitize_error(self, exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "scheduled task execution timed out"
        if isinstance(exc, PermissionError):
            return "scheduled task execution denied"
        return "scheduled task execution failed"

    def _build_result_summary(self, *, task: ExecutionTask, agent_execution: dict[str, Any] | None, scheduler_status: str, retry_delay_seconds: int | None = None, error: str | None = None) -> dict[str, Any]:
        summary = {
            "execution_task_id": task.task_id,
            "scheduler_status": scheduler_status,
            "retries": task.retries,
            "max_retries": task.max_retries,
            "agent_execution": agent_execution,
        }
        if retry_delay_seconds is not None:
            summary["retry_delay_seconds"] = retry_delay_seconds
        if error:
            summary["error"] = error
        return summary

    def _build_attempt_task_id(self, task: ExecutionTask, task_payload: dict[str, Any]) -> str:
        base_task_id = str(task_payload.get("task_id") or task.command_id or task.task_id)
        if int(task.retries) <= 0:
            return base_task_id[:64]
        retry_task_id = f"{base_task_id}-r{int(task.retries)}"
        return retry_task_id[:64]

    def _process_loaded_task(self, session: Session, task: ExecutionTask, *, retry_on_failure: bool) -> ExecutionTask:
        command_run = session.get(CommandRun, task.command_id) if task.command_id else None
        decision = evaluate_execution_policy(command_run, task)
        persist_policy_state(session, task.task_id, decision)
        if not decision.allowed:
            refreshed = self.store.get_task(session, task.task_id)
            if refreshed is None:
                raise ValueError(f"execution task not found: {task.task_id}")
            return refreshed

        task = self.store.mark_running(session, task_id=task.task_id)
        _record_scheduler_event("task_started", task)

        payload = dict(task.payload_json or {})
        task_payload = dict(payload.get("task") or {})
        task_payload["task_id"] = self._build_attempt_task_id(task, task_payload)
        project_id = payload.get("project_id")

        try:
            with session.begin_nested():
                agent_execution = execute_agent(
                    session,
                    task=task_payload,
                    tenant_id=task.tenant_id,
                    project_id=project_id,
                    command_id=task.command_id,
                )
            agent_status = str(agent_execution.get("status") or "failed").strip().lower()
            if agent_status == "completed":
                task = self.store.mark_completed(
                    session,
                    task_id=task.task_id,
                    result_summary=self._build_result_summary(task=task, agent_execution=agent_execution, scheduler_status=ExecutionTaskStatus.completed.value),
                )
                _record_scheduler_event("task_completed", task)
                return task

            error = str(agent_execution.get("error_message") or agent_execution.get("error_code") or agent_status)
            if retry_on_failure and agent_status in {"failed", "timeout"}:
                decision = self.retry_policy.evaluate(task)
                if decision.should_retry and decision.next_available_at is not None:
                    task = self.store.mark_retrying(
                        session,
                        task_id=task.task_id,
                        next_available_at=decision.next_available_at,
                        error=error,
                        result_summary=self._build_result_summary(
                            task=task,
                            agent_execution=agent_execution,
                            scheduler_status=ExecutionTaskStatus.retrying.value,
                            retry_delay_seconds=decision.delay_seconds,
                            error=error,
                        ),
                    )
                    _record_scheduler_event("task_retry", task)
                    return task

            task = self.store.mark_failed(
                session,
                task_id=task.task_id,
                error=error,
                result_summary=self._build_result_summary(
                    task=task,
                    agent_execution=agent_execution,
                    scheduler_status=ExecutionTaskStatus.failed.value,
                    error=error,
                ),
            )
            _record_scheduler_event("task_failed", task)
            return task
        except Exception as exc:
            error = self._sanitize_error(exc)
            if retry_on_failure:
                decision = self.retry_policy.evaluate(task)
                if decision.should_retry and decision.next_available_at is not None:
                    task = self.store.mark_retrying(
                        session,
                        task_id=task.task_id,
                        next_available_at=decision.next_available_at,
                        error=error,
                        result_summary=self._build_result_summary(
                            task=task,
                            agent_execution=None,
                            scheduler_status=ExecutionTaskStatus.retrying.value,
                            retry_delay_seconds=decision.delay_seconds,
                            error=error,
                        ),
                    )
                    _record_scheduler_event("task_retry", task)
                    return task

            task = self.store.mark_failed(
                session,
                task_id=task.task_id,
                error=error,
                result_summary=self._build_result_summary(
                    task=task,
                    agent_execution=None,
                    scheduler_status=ExecutionTaskStatus.failed.value,
                    error=error,
                ),
            )
            _record_scheduler_event("task_failed", task)
            return task

    def process_task(self, session: Session, *, task_id: str, retry_on_failure: bool = True) -> ExecutionTask:
        allowed, _control_reason = is_execution_allowed(session, task_id)
        if not allowed:
            task = self.store.get_task(session, task_id)
            if task is None:
                raise ValueError(f"execution task not found: {task_id}")
            return task
        ready_tasks = self.queue.pop_ready(session, limit=1, task_id=task_id)
        if not ready_tasks:
            task = self.store.get_task(session, task_id)
            if task is None:
                raise ValueError(f"execution task not found: {task_id}")
            return task
        return self._process_loaded_task(session, ready_tasks[0], retry_on_failure=retry_on_failure)

    def tick(self, session: Session, *, limit: int = 1, retry_on_failure: bool = True) -> list[ExecutionTask]:
        ready_tasks = self.queue.pop_ready(session, limit=limit)
        return [self._process_loaded_task(session, task, retry_on_failure=retry_on_failure) for task in ready_tasks]


_scheduler = ExecutionScheduler()


def create_execution_scheduler() -> ExecutionScheduler:
    return _scheduler


