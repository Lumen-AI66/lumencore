from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Task, TaskStatus

RISKY_TASK_TYPES = {"deploy", "delete", "drop_table", "reset", "purge", "shutdown"}

# Allowed status transitions
_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.queued:      {TaskStatus.running},
    TaskStatus.running:     {TaskStatus.done, TaskStatus.failed},
    TaskStatus.needs_input: {TaskStatus.queued, TaskStatus.failed},
    TaskStatus.done:        set(),
    TaskStatus.failed:      set(),
}


def _transition(task: Task, new_status: TaskStatus) -> None:
    allowed = _VALID_TRANSITIONS.get(task.status, set())
    if new_status not in allowed:
        raise ValueError(
            f"invalid status transition: {task.status} → {new_status} "
            f"(allowed: {', '.join(s.value for s in allowed) or 'none'})"
        )
    task.status = new_status
    task.updated_at = datetime.now(timezone.utc)


def create_task(
    session: Session,
    task_type: str,
    payload: dict,
    agent: str | None = None,
    priority: int = 0,
    requires_approval: bool = False,
) -> Task:
    approval_required = requires_approval or task_type in RISKY_TASK_TYPES
    task = Task(
        task_type=task_type,
        agent=agent,
        priority=priority,
        payload=payload or {},
        approval_required=approval_required,
        approval_status="pending_approval" if approval_required else "not_required",
        status=TaskStatus.needs_input if approval_required else TaskStatus.queued,
    )
    session.add(task)
    session.flush()
    return task


def get_task(session: Session, task_id: str) -> Task | None:
    return session.get(Task, task_id)


def list_tasks(session: Session, limit: int = 50, offset: int = 0) -> tuple[list[Task], int]:
    items = list(session.scalars(
        select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)
    ))
    total = session.scalar(select(func.count(Task.id))) or 0
    return items, total


def approve_task(session: Session, task: Task, approved: bool, reason: str | None = None) -> Task:
    if task.status != TaskStatus.needs_input:
        raise ValueError(f"task is not awaiting approval (status={task.status})")
    now = datetime.now(timezone.utc)
    if approved:
        _transition(task, TaskStatus.queued)
        task.approval_status = "approved"
    else:
        task.status = TaskStatus.failed  # direct — rejection bypasses normal running flow
        task.approval_status = "rejected"
        task.error = reason or "rejected by operator"
        task.updated_at = now
    session.add(task)
    session.flush()
    return task


def mark_task_running(session: Session, task: Task, execution_task_id: str) -> Task:
    _transition(task, TaskStatus.running)
    task.execution_task_id = execution_task_id
    session.add(task)
    session.flush()
    return task


def mark_task_done(session: Session, task: Task, result: dict) -> Task:
    _transition(task, TaskStatus.done)
    task.result = result
    session.add(task)
    session.flush()
    return task


def mark_task_failed(session: Session, task: Task, error: str) -> Task:
    _transition(task, TaskStatus.failed)
    task.error = error
    session.add(task)
    session.flush()
    return task
