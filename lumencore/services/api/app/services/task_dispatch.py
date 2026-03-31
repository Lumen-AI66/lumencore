from __future__ import annotations

"""
Task Dispatch — Phase 1.5 + 2 integration bridge.

Connects the Task control layer to the existing ExecutionTaskStore + ExecutionScheduler.
Phase 2 adds:
  - pre-execution: retrieve_relevant_memory() enriches task context (non-breaking)
  - post-execution: record_task_outcome() logs decision + extracts memory
"""

from sqlalchemy.orm import Session

from ..execution import ExecutionTaskStatus, create_execution_scheduler, get_execution_task_store
from ..models import Task, TaskStatus
from .memory import record_task_outcome, retrieve_relevant_memory
from .tasks import mark_task_done, mark_task_failed, mark_task_running

_DEFAULT_AGENT_TYPE = "runtime"


def dispatch_task(session: Session, task: Task) -> Task:
    """
    Dispatch a queued Task into the execution layer.

    Phase 1.5:
    - Creates an ExecutionTaskRecord (pending) linked to this Task.
    - Marks Task as running.
    - Runs the scheduler synchronously (same session).
    - Syncs result/error back to Task.

    Phase 2 additions (non-breaking):
    - Retrieves relevant memory before execution and attaches to payload context.
    - Records decision log + extracts memory after execution.

    Must only be called when task.status == TaskStatus.queued.
    """
    if task.status != TaskStatus.queued:
        raise ValueError(
            f"dispatch_task called on task with status={task.status!r}; must be queued"
        )

    store = get_execution_task_store()
    scheduler = create_execution_scheduler()

    agent_type = task.agent or _DEFAULT_AGENT_TYPE

    # ------------------------------------------------------------------
    # Phase 2 — pre-execution retrieval hook (non-breaking)
    # ------------------------------------------------------------------
    task_context = {"task_type": task.task_type, "payload": task.payload or {}}
    relevant_memory = retrieve_relevant_memory(session, task_context, limit=5)
    memory_context = [
        {"key": m.key, "type": m.type, "content": m.content[:500]}
        for m in relevant_memory
    ]

    # Build task_metadata that links back to the Phase-1 Task id.
    # Memory context is attached here for observability only — execution
    # behavior is unchanged (scheduler ignores unknown metadata keys).
    task_metadata = {
        "source": "task_control",
        "task_id": task.id,
        "task_type": task.task_type,
        "memory_context": memory_context,
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
        _record_outcome(session, task, error=str(exc))
        return task

    final_status = processed.status
    if final_status == ExecutionTaskStatus.completed:
        result = dict(processed.result_summary or {})
        result["execution_task_id"] = processed.task_id
        task = mark_task_done(session, task, result)
        _record_outcome(session, task, result=result)
    else:
        error = processed.error or f"execution ended with status={final_status.value}"
        task = mark_task_failed(session, task, error)
        _record_outcome(session, task, error=error)

    return task


def _record_outcome(
    session: Session,
    task: Task,
    *,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    """
    Phase 2 post-execution hook. Never raises — memory failure must not
    break task execution results.
    """
    try:
        outcome = "success" if task.status == TaskStatus.done else "failure"
        record_task_outcome(
            session,
            task_id=task.id,
            task_type=task.task_type,
            agent=task.agent,
            result=result,
            error=error,
            outcome=outcome,
        )
    except Exception:
        pass  # memory write failure is non-fatal
