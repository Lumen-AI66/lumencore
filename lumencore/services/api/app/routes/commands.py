from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..commands.command_runtime import build_command_run_response
from ..commands.command_service import get_command_run, list_command_runs, update_command_run_for_job
from ..db import session_scope
from ..execution import get_execution_task_store
from ..schemas.commands import CommandHistoryResponse, CommandRunResponse

router = APIRouter(prefix="/api/commands", tags=["commands"])
task_store = get_execution_task_store()


def _linked_execution_task(session, item):
    summary = item.result_summary or {}
    task_id = summary.get("execution_task_id") if isinstance(summary, dict) else None
    if not task_id:
        return None
    return task_store.get_task(session, task_id)


def _to_response(session, item) -> CommandRunResponse:
    return build_command_run_response(item, _linked_execution_task(session, item))


@router.get("", response_model=CommandHistoryResponse)
def list_commands(limit: int = Query(default=20, ge=1, le=100)) -> CommandHistoryResponse:
    with session_scope() as session:
        items = list_command_runs(session, limit=limit)
        for item in items:
            update_command_run_for_job(session, item)
        return CommandHistoryResponse(limit=limit, items=[_to_response(session, x) for x in items])


@router.get("/{command_id}", response_model=CommandRunResponse)
def get_command(command_id: str) -> CommandRunResponse:
    with session_scope() as session:
        item = get_command_run(session, command_id)
        if not item:
            raise HTTPException(status_code=404, detail="command not found")
        item = update_command_run_for_job(session, item)
        return _to_response(session, item)




