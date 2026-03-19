from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..commands.command_service import (
    create_operator_command_run,
    get_command_run,
    update_command_run_for_job,
)
from ..db import session_scope
from ..services.jobs import create_job, mark_job_queued
from ..services.observability import list_operator_events, record_operator_event
from ..services.operator_guard import validate_operator_command
from ..security import internal_route_boundary
from ..services.operator_queue import MAX_QUEUE_SIZE, get_operator_queue_size
from ..services.operator_summary import (
    build_operator_command_item,
    build_operator_queue_view,
    generate_operator_summary,
    list_operator_agent_run_items,
    list_operator_command_items,
    list_operator_job_items,
)
from ..worker_tasks import execute_job

router = APIRouter()


class OperatorCommandRequest(BaseModel):
    command: str = Field()


class OperatorEventResponse(BaseModel):
    event_type: str
    command_id: str | None = None
    timestamp: str | None = None


class OperatorEventSnapshotResponse(BaseModel):
    counts: dict[str, int]
    recent_events: list[OperatorEventResponse]


class OperatorCommandIntakeResponse(BaseModel):
    command_id: str
    status: str


class OperatorCommandStatusResponse(BaseModel):
    command_id: str
    tenant_id: str | None = None
    command_text: str | None = None
    status: str
    runtime_status: str | None = None
    result: dict[str, Any] | None = None
    timestamp: str | None = None
    agent: str | None = None
    planned_task_type: str | None = None
    requested_mode: str | None = None
    selected_agent_id: str | None = None
    execution_decision: str | None = None
    approval_required: bool | None = None
    approval_status: str | None = None
    policy_reason: str | None = None
    job_id: str | None = None
    queue_bucket: str | None = None
    registry_key: str | None = None
    request_id: str | None = None
    run_id: str | None = None
    correlation_id: str | None = None
    connector_name: str | None = None
    error_code: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    events: list[OperatorEventResponse] = Field(default_factory=list)


class OperatorQueueResponse(BaseModel):
    queued_commands: list[OperatorCommandStatusResponse]
    running_commands: list[OperatorCommandStatusResponse]


class OperatorSummarySectionResponse(BaseModel):
    counts_by_status: dict[str, int]
    total: int | None = None


class OperatorAttentionResponse(BaseModel):
    current_totals: dict[str, int]
    state_summary: dict[str, Any]


class OperatorSummaryResponse(BaseModel):
    recent_commands: list[OperatorCommandStatusResponse]
    counts: dict[str, int]
    queue_size: int
    system_health: str
    operator_events: OperatorEventSnapshotResponse
    commands: dict[str, Any]
    jobs: OperatorSummarySectionResponse
    agent_runs: OperatorSummarySectionResponse
    operator_attention: OperatorAttentionResponse


class OperatorCommandListResponse(BaseModel):
    limit: int
    items: list[OperatorCommandStatusResponse]


class OperatorJobItemResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    command_id: str | None = None
    queue_task_id: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None


class OperatorJobListResponse(BaseModel):
    limit: int
    items: list[OperatorJobItemResponse]


class OperatorAgentRunItemResponse(BaseModel):
    run_id: str
    tenant_id: str
    command_id: str | None = None
    agent_id: str
    agent_type: str | None = None
    task_type: str
    status: str
    started_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    steps_executed: int | None = None
    tools_used: list[str] = Field(default_factory=list)
    error: str | None = None
    registry_key: str | None = None


class OperatorAgentRunListResponse(BaseModel):
    limit: int
    items: list[OperatorAgentRunItemResponse]


def _to_status_response(item, *, events: list[dict[str, Any]] | None = None) -> OperatorCommandStatusResponse:
    payload = dict(item) if isinstance(item, dict) else item
    if isinstance(payload, dict):
        payload = dict(payload)
        payload["events"] = [OperatorEventResponse.model_validate(event) for event in (events or payload.get("events") or [])]
        return OperatorCommandStatusResponse.model_validate(payload)
    raise ValueError("unsupported operator command payload")


@router.post('/command', response_model=OperatorCommandIntakeResponse, status_code=status.HTTP_202_ACCEPTED)
def operator_command(req: OperatorCommandRequest, x_lumencore_internal_route: str | None = Header(default=None)):
    internal_route_boundary(x_lumencore_internal_route)
    try:
        command_text = validate_operator_command(req.command)
        command_id = str(uuid4())

        with session_scope() as session:
            if get_operator_queue_size(session) >= MAX_QUEUE_SIZE:
                return JSONResponse(status_code=429, content={"error": "operator queue full"})

            run = create_operator_command_run(
                session,
                command_text=command_text,
                tenant_id='owner',
                project_id='default',
                command_id=command_id,
            )
            payload = {
                "command_id": run.id,
                "project_id": "default",
            }
            job = create_job(session, "operator_command", payload, tenant_id=run.tenant_id)
            task = execute_job.delay(job.id)
            job = mark_job_queued(session, job, task.id)
            run.job_id = job.id
            session.add(run)
            session.flush()

        record_operator_event("OPERATOR_COMMAND_RECEIVED", command_id=command_id)
        record_operator_event("OPERATOR_COMMAND_QUEUED", command_id=command_id)
        return OperatorCommandIntakeResponse(command_id=command_id, status="queued")
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception:
        return JSONResponse(status_code=500, content={"error": "operator command intake failed"})


@router.get('/queue', response_model=OperatorQueueResponse)
def operator_queue(limit: int = Query(default=20, ge=1, le=100)):
    try:
        with session_scope() as session:
            view = build_operator_queue_view(session, limit=limit)
            return OperatorQueueResponse(
                queued_commands=[OperatorCommandStatusResponse.model_validate(item) for item in view['queued_commands']],
                running_commands=[OperatorCommandStatusResponse.model_validate(item) for item in view['running_commands']],
            )
    except Exception:
        return JSONResponse(status_code=500, content={"error": "operator queue unavailable"})


@router.get('/commands', response_model=OperatorCommandListResponse)
def operator_commands(
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    approval_status: str | None = Query(default=None),
):
    try:
        with session_scope() as session:
            items = list_operator_command_items(session, limit=limit, status=status, approval_status=approval_status)
            return OperatorCommandListResponse(
                limit=limit,
                items=[OperatorCommandStatusResponse.model_validate(item) for item in items],
            )
    except Exception:
        return JSONResponse(status_code=500, content={"error": "operator commands unavailable"})


@router.get('/jobs', response_model=OperatorJobListResponse)
def operator_jobs(limit: int = Query(default=20, ge=1, le=100), status: str | None = Query(default=None)):
    try:
        with session_scope() as session:
            items = list_operator_job_items(session, limit=limit, status=status)
            return OperatorJobListResponse(
                limit=limit,
                items=[OperatorJobItemResponse.model_validate(item) for item in items],
            )
    except Exception:
        return JSONResponse(status_code=500, content={"error": "operator jobs unavailable"})


@router.get('/agent-runs', response_model=OperatorAgentRunListResponse)
def operator_agent_runs(limit: int = Query(default=20, ge=1, le=100), status: str | None = Query(default=None)):
    try:
        with session_scope() as session:
            items = list_operator_agent_run_items(session, limit=limit, status=status)
            return OperatorAgentRunListResponse(
                limit=limit,
                items=[OperatorAgentRunItemResponse.model_validate(item) for item in items],
            )
    except Exception:
        return JSONResponse(status_code=500, content={"error": "operator agent runs unavailable"})


@router.get('/command/{command_id}', response_model=OperatorCommandStatusResponse)
def operator_command_status(command_id: str):
    try:
        with session_scope() as session:
            item = get_command_run(session, command_id)
            if not item:
                return JSONResponse(status_code=404, content={"error": "command not found"})
            item = update_command_run_for_job(session, item)
            events = list_operator_events(session, command_id=command_id, limit=20)
            match = build_operator_command_item(item)
            return _to_status_response(match, events=events)
    except Exception:
        return JSONResponse(status_code=500, content={"error": "operator command status unavailable"})


@router.get('/summary', response_model=OperatorSummaryResponse)
def operator_summary(limit: int = Query(default=10, ge=1, le=100)):
    try:
        with session_scope() as session:
            summary = generate_operator_summary(session, limit=limit)
            return OperatorSummaryResponse(
                recent_commands=[OperatorCommandStatusResponse.model_validate(item) for item in summary['recent_commands']],
                counts=summary['counts'],
                queue_size=summary['queue_size'],
                system_health=summary['system_health'],
                operator_events=OperatorEventSnapshotResponse(
                    counts=summary['operator_events']['counts'],
                    recent_events=[OperatorEventResponse.model_validate(event) for event in summary['operator_events']['recent_events']],
                ),
                commands=summary['commands'],
                jobs=OperatorSummarySectionResponse(
                    counts_by_status=summary['jobs']['counts_by_status'],
                    total=summary['jobs']['total_jobs'],
                ),
                agent_runs=OperatorSummarySectionResponse(
                    counts_by_status=summary['agent_runs']['counts_by_status'],
                    total=summary['agent_runs']['total_runs'],
                ),
                operator_attention=OperatorAttentionResponse(
                    current_totals=summary['operator_attention']['current_totals'],
                    state_summary=summary['operator_attention']['state_summary'],
                ),
            )
    except Exception:
        return JSONResponse(status_code=500, content={"error": "operator summary unavailable"})
