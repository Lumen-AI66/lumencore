from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..db import session_scope
from ..execution import get_execution_task_store
from ..schemas.execution_tasks import ExecutionTaskListResponse, ExecutionTaskResponse

router = APIRouter(prefix="/api/execution-tasks", tags=["execution-tasks"])
task_store = get_execution_task_store()


@router.get("", response_model=ExecutionTaskListResponse)
def list_execution_tasks(limit: int = Query(default=20, ge=1, le=100)) -> ExecutionTaskListResponse:
    with session_scope() as session:
        tasks = task_store.list_recent_tasks(session, limit=limit)
        items = [
            ExecutionTaskResponse(
                task_id=item.task_id,
                tenant_id=item.tenant_id,
                command_id=item.command_id,
                agent_id=item.agent_id,
                agent_type=item.agent_type,
                task_type=item.task_type,
                status=item.status,
                priority=item.priority,
                retries=item.retries,
                max_retries=item.max_retries,
                available_at=item.available_at,
                started_at=item.started_at,
                updated_at=item.updated_at,
                finished_at=item.finished_at,
                error=item.error,
            )
            for item in tasks
        ]
    return ExecutionTaskListResponse(limit=limit, items=items)


@router.get("/{task_id}", response_model=ExecutionTaskResponse)
def get_execution_task(task_id: str) -> ExecutionTaskResponse:
    with session_scope() as session:
        task = task_store.get_task(session, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="execution task not found")
        return ExecutionTaskResponse(
            task_id=task.task_id,
            tenant_id=task.tenant_id,
            command_id=task.command_id,
            agent_id=task.agent_id,
            agent_type=task.agent_type,
            task_type=task.task_type,
            status=task.status,
            priority=task.priority,
            retries=task.retries,
            max_retries=task.max_retries,
            available_at=task.available_at,
            started_at=task.started_at,
            updated_at=task.updated_at,
            finished_at=task.finished_at,
            error=task.error,
        )
