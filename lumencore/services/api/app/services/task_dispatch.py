from __future__ import annotations

"""
Task Dispatch — Phase 1.5 integration bridge.

Connects the Task control layer to the existing ExecutionTaskStore + ExecutionScheduler.
Called from routes/tasks.py after a Task enters `queued` status.
"""

from sqlalchemy.orm import Session

from ..execution import ExecutionTaskStatus, create_execution_scheduler, get_execution_task_store
from ..models import Task, TaskStatus
from .tasks import mark_task_done, mark_task_failed, mark_task_running

_DEFAULT_AGENT_TYPE = "runtime"


def dispatch_task(session: Session, task: Task) -> Task:
    """
    Dispatch a queued Task into the execution layer.

    - Creates an ExecutionTaskRecord (pending) linked to this Task.
    - Marks Task as running.
    - Runs the scheduler synchronously (same session).
    - Syncs result/error back to Task.

    Must only be called when task.status == TaskStatus.queued.
    """
    if task.status != TaskStatus.queued:
        raise ValueError(
            f"dispatch_task called on task with status={task.status!r}; must be queued"
        )

    store = get_execution_task_store()
    scheduler = create_execution_scheduler()

    agent_type = task.agent or _DEFAULT_AGENT_TYPE

    # Build task_metadata that links back to the Phase-1 Task id.
    task_metadata = {
        "source": "task_control",
        "task_id": task.id,
        "task_type": task.task_type,
    }

    execution_task = store.create_task(
        session,
        tenant_id="owner",
        agent_id=None,
        agent_type=agent_type,
        task_type=task.task_type,
        payload_json={"task": task.payload or {}, "project_id": None},
        priority=task.priority,
        max_retries=0,
        task_metadata=task_metadata,
    )

    # Transition Task → running and store the execution link.
    task = mark_task_running(session, task, execution_task.task_id)

    # Run the scheduler synchronously; it will mark the ExecutionTaskRecord
    # completed/failed and return the final state.
    try:
        processed = scheduler.process_task(
            session,
            task_id=execution_task.task_id,
            retry_on_failure=False,
        )
    except Exception as exc:
        task = mark_task_failed(session, task, str(exc))
        return task

    final_status = processed.status
    if final_status == ExecutionTaskStatus.completed:
        result = dict(processed.result_summary or {})
        result["execution_task_id"] = processed.task_id
        task = mark_task_done(session, task, result)
    else:
        error = processed.error or f"execution ended with status={final_status.value}"
        task = mark_task_failed(session, task, error)

    return task
