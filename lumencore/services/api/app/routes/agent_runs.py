from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from ..db import session_scope
from ..models import AgentRun
from ..schemas.agent_runs import AgentRunListResponse, AgentRunResponse

router = APIRouter(prefix="/api/agent-runs", tags=["agent-runs"])


def _result_payload(record: AgentRun) -> dict:
    return dict(record.result or {}) if isinstance(record.result, dict) else {}


def _to_response(record: AgentRun) -> AgentRunResponse:
    result = _result_payload(record)
    return AgentRunResponse(
        run_id=record.id,
        tenant_id=record.tenant_id,
        command_id=result.get("command_id"),
        agent_id=str(record.agent_id),
        agent_type=result.get("agent_type"),
        task_type=record.task_type,
        status=record.status,
        started_at=record.started_at,
        updated_at=record.updated_at,
        completed_at=record.finished_at,
        duration_ms=result.get("duration_ms"),
        steps_executed=result.get("steps_executed"),
        tools_used=list(result.get("tools_used", [])) if isinstance(result.get("tools_used", []), list) else [],
        error=result.get("error_message") or record.error,
    )


@router.get("", response_model=AgentRunListResponse)
def list_agent_runs(limit: int = Query(default=20, ge=1, le=100)) -> AgentRunListResponse:
    with session_scope() as session:
        stmt = select(AgentRun).order_by(AgentRun.updated_at.desc()).limit(max(1, min(int(limit), 100)))
        runs = list(session.execute(stmt).scalars())
        items = [_to_response(run) for run in runs]
    return AgentRunListResponse(limit=limit, items=items)


@router.get("/{run_id}", response_model=AgentRunResponse)
def get_agent_run(run_id: str) -> AgentRunResponse:
    with session_scope() as session:
        run = session.get(AgentRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="agent run not found")
        return _to_response(run)
