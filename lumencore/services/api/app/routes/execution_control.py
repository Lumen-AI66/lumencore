from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from ..db import session_scope
from ..execution import ExecutionTaskStatus, get_execution_task_store
from ..models import CommandRun
from ..schemas.execution_control import (
    ExecutionControlActionRequest,
    ExecutionControlActionResponse,
    ExecutionControlStateResponse,
)
from ..schemas.execution_tasks import ExecutionTaskResponse
from ..services.execution_control import (
    ExecutionControlStatus,
    get_execution_control_state,
    set_execution_control_state,
)
from ..services.read_models import build_execution_task_read_model

router = APIRouter(prefix="/api/execution-control", tags=["execution-control"])
task_store = get_execution_task_store()


def _copy_dict(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    copied: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            copied[str(key)] = _copy_dict(item)
        elif isinstance(item, list):
            copied[str(key)] = list(item)
        else:
            copied[str(key)] = item
    return copied


def _merge_dicts(base: dict[str, Any] | None, updates: dict[str, Any] | None) -> dict[str, Any]:
    merged = _copy_dict(base)
    for key, value in _copy_dict(updates).items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def _load_task(session, task_id: str):
    task = task_store.get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="execution task not found")
    return task


def _build_response(session, *, action: str, task):
    command_run = session.get(CommandRun, task.command_id) if task.command_id else None
    control_state = get_execution_control_state(session, task.task_id)
    task_response = ExecutionTaskResponse(
        **build_execution_task_read_model(task, command_run, execution_control=control_state.model_dump(mode="json"))
    )
    return ExecutionControlActionResponse(
        action=action,
        task_id=task.task_id,
        execution_control=ExecutionControlStateResponse(
            **control_state.model_dump(),
            execution_allowed=control_state.control_status == ExecutionControlStatus.allowed,
        ),
        task=task_response,
    )


def _control_summary(task, control_state, *, action: str) -> dict[str, Any]:
    return _merge_dicts(
        task.result_summary,
        {
            "execution_control": control_state.model_dump(mode="json"),
            "control_action": action,
        },
    )


@router.post("/{task_id}/pause", response_model=ExecutionControlActionResponse)
def pause_execution_task(task_id: str, request: ExecutionControlActionRequest | None = None) -> ExecutionControlActionResponse:
    with session_scope() as session:
        task = _load_task(session, task_id)
        if task.status == ExecutionTaskStatus.completed:
            raise HTTPException(status_code=409, detail="completed tasks cannot be paused")
        if task.status == ExecutionTaskStatus.running:
            raise HTTPException(status_code=409, detail="running tasks cannot be paused safely")
        reason = (request.reason if request else None) or "paused by operator"
        set_execution_control_state(session, task_id, ExecutionControlStatus.paused, reason=reason, source=(request.source if request else "operator"))
        task = _load_task(session, task_id)
        return _build_response(session, action="pause", task=task)


@router.post("/{task_id}/resume", response_model=ExecutionControlActionResponse)
def resume_execution_task(task_id: str, request: ExecutionControlActionRequest | None = None) -> ExecutionControlActionResponse:
    with session_scope() as session:
        task = _load_task(session, task_id)
        if task.status == ExecutionTaskStatus.completed:
            raise HTTPException(status_code=409, detail="completed tasks cannot be resumed")
        current = get_execution_control_state(session, task_id)
        if current.control_status not in {ExecutionControlStatus.paused, ExecutionControlStatus.blocked}:
            raise HTTPException(status_code=409, detail="task is not paused or blocked")
        reason = (request.reason if request else None) or "resumed by operator"
        set_execution_control_state(session, task_id, ExecutionControlStatus.allowed, reason=reason, source=(request.source if request else "operator"))
        task = _load_task(session, task_id)
        return _build_response(session, action="resume", task=task)


@router.post("/{task_id}/cancel", response_model=ExecutionControlActionResponse)
def cancel_execution_task(task_id: str, request: ExecutionControlActionRequest | None = None) -> ExecutionControlActionResponse:
    with session_scope() as session:
        task = _load_task(session, task_id)
        if task.status == ExecutionTaskStatus.completed:
            raise HTTPException(status_code=409, detail="completed tasks cannot be cancelled")
        if task.status == ExecutionTaskStatus.running:
            raise HTTPException(status_code=409, detail="running tasks cannot be cancelled safely")
        reason = (request.reason if request else None) or "cancelled by operator"
        control_state = set_execution_control_state(session, task_id, ExecutionControlStatus.cancelled, reason=reason, source=(request.source if request else "operator"))
        if task.status in {ExecutionTaskStatus.pending, ExecutionTaskStatus.retrying}:
            task = task_store.mark_failed(
                session,
                task_id=task_id,
                error=reason,
                result_summary=_control_summary(task, control_state, action="cancel"),
            )
        else:
            task = _load_task(session, task_id)
        return _build_response(session, action="cancel", task=task)


@router.post("/{task_id}/retry", response_model=ExecutionControlActionResponse)
def retry_execution_task(task_id: str, request: ExecutionControlActionRequest | None = None) -> ExecutionControlActionResponse:
    with session_scope() as session:
        task = _load_task(session, task_id)
        current = get_execution_control_state(session, task_id)
        if task.status == ExecutionTaskStatus.completed:
            raise HTTPException(status_code=409, detail="completed tasks cannot be retried")
        if task.status == ExecutionTaskStatus.running:
            raise HTTPException(status_code=409, detail="running tasks cannot be retried safely")
        if task.status != ExecutionTaskStatus.failed and current.control_status not in {ExecutionControlStatus.cancelled, ExecutionControlStatus.blocked}:
            raise HTTPException(status_code=409, detail="retry is only supported for failed, cancelled, or blocked tasks")
        reason = (request.reason if request else None) or "retry requested by operator"
        control_state = set_execution_control_state(session, task_id, ExecutionControlStatus.allowed, reason=reason, source=(request.source if request else "operator"))
        task = task_store.requeue_task(
            session,
            task_id=task_id,
            next_available_at=datetime.now(timezone.utc),
            result_summary=_control_summary(task, control_state, action="retry"),
        )
        return _build_response(session, action="retry", task=task)
