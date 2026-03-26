from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..db import session_scope
from ..models import CommandRun
from ..execution import get_execution_task_store
from ..schemas.execution_tasks import ExecutionTaskListResponse, ExecutionTaskResponse
from ..services.execution_control import get_execution_control_state
from ..services.read_models import build_execution_task_read_model

router = APIRouter(prefix="/api/execution-tasks", tags=["execution-tasks"])
task_store = get_execution_task_store()


def _to_response(session, item) -> ExecutionTaskResponse:
    command_run = session.get(CommandRun, item.command_id) if item.command_id else None
    control_state = get_execution_control_state(session, item.task_id)
    policy_state = dict((item.task_metadata or {}).get('execution_policy') or {}) or None
    return ExecutionTaskResponse(**build_execution_task_read_model(
        item,
        command_run,
        execution_control=control_state.model_dump(mode="json"),
        execution_policy=policy_state,
    ))


@router.get("", response_model=ExecutionTaskListResponse)
def list_execution_tasks(limit: int = Query(default=20, ge=1, le=100)) -> ExecutionTaskListResponse:
    with session_scope() as session:
        tasks = task_store.list_recent_tasks(session, limit=limit)
        items = [_to_response(session, item) for item in tasks]
    return ExecutionTaskListResponse(limit=limit, items=items)


@router.get("/{task_id}", response_model=ExecutionTaskResponse)
def get_execution_task(task_id: str) -> ExecutionTaskResponse:
    with session_scope() as session:
        task = task_store.get_task(session, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="execution task not found")
        return _to_response(session, task)
