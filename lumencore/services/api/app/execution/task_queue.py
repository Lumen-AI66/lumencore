from __future__ import annotations

from sqlalchemy.orm import Session

from .task_models import ExecutionTask
from .task_store import ExecutionTaskStore, get_execution_task_store


class ExecutionTaskQueue:
    def __init__(self, store: ExecutionTaskStore | None = None) -> None:
        self.store = store or get_execution_task_store()

    def enqueue(self, session: Session, **kwargs) -> ExecutionTask:
        return self.store.create_task(session, **kwargs)

    def pop_ready(self, session: Session, *, limit: int = 1, task_id: str | None = None) -> list[ExecutionTask]:
        return self.store.list_ready_tasks(session, limit=limit, task_id=task_id)


_task_queue = ExecutionTaskQueue()


def get_execution_task_queue() -> ExecutionTaskQueue:
    return _task_queue
