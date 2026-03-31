from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from ..db import session_scope
from ..models import TaskStatus
from ..schemas.tasks import (
    TaskApproveRequest,
    TaskCreateRequest,
    TaskListResponse,
    TaskResponse,
)
from ..services.task_dispatch import dispatch_task
from ..services.tasks import approve_task, create_task, get_task, list_tasks

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _to_response(task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        task_type=task.task_type,
        status=task.status,
        agent=task.agent,
        priority=task.priority,
        payload=task.payload,
        result=task.result,
        error=task.error,
        approval_required=task.approval_required,
        approval_status=task.approval_status,
        execution_task_id=task.execution_task_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def submit_task(req: TaskCreateRequest) -> TaskResponse:
    with session_scope() as session:
        task = create_task(
            session,
            task_type=req.task_type,
            payload=req.payload,
            agent=req.agent,
            priority=req.priority,
            requires_approval=req.requires_approval,
        )
        # Dispatch immediately if no approval needed.
        if task.status == TaskStatus.queued:
            task = dispatch_task(session, task)
        return _to_response(task)


@router.get("", response_model=TaskListResponse)
def fetch_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TaskListResponse:
    with session_scope() as session:
        items, total = list_tasks(session, limit=limit, offset=offset)
        return TaskListResponse(total=total, items=[_to_response(t) for t in items])


@router.get("/{task_id}", response_model=TaskResponse)
def fetch_task(task_id: str) -> TaskResponse:
    with session_scope() as session:
        task = get_task(session, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="task not found")
        return _to_response(task)


@router.post("/{task_id}/approve", response_model=TaskResponse)
def approve_task_action(task_id: str, req: TaskApproveRequest) -> TaskResponse:
    with session_scope() as session:
        task = get_task(session, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="task not found")
        try:
            task = approve_task(session, task, approved=req.approved, reason=req.reason)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # If approved, dispatch into execution immediately.
        if task.status == TaskStatus.queued:
            task = dispatch_task(session, task)
        return _to_response(task)
