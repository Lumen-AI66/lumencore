from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from ..db import session_scope
from ..schemas.memory import (
    DecisionLogListResponse,
    DecisionLogResponse,
    MemoryCreateRequest,
    MemoryListResponse,
    MemoryResponse,
    SkillMemoryListResponse,
    SkillMemoryResponse,
)
from ..services.memory import (
    list_decision_logs,
    list_skills,
    search_memory,
    store_memory,
)

router = APIRouter(prefix="/api/memory", tags=["memory"])


def _mem_response(r) -> MemoryResponse:
    return MemoryResponse(
        id=r.id,
        type=r.type,
        key=r.key,
        content=r.content,
        metadata=r.metadata_json,
        source_task_id=r.source_task_id,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _skill_response(s) -> SkillMemoryResponse:
    return SkillMemoryResponse(
        id=s.id,
        name=s.name,
        description=s.description,
        pattern=s.pattern,
        success_count=s.success_count,
        last_used_at=s.last_used_at,
        created_at=s.created_at,
    )


def _decision_response(d) -> DecisionLogResponse:
    return DecisionLogResponse(
        id=d.id,
        task_id=d.task_id,
        agent=d.agent,
        decision=d.decision,
        reasoning=d.reasoning,
        outcome=d.outcome,
        created_at=d.created_at,
    )


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(req: MemoryCreateRequest) -> MemoryResponse:
    with session_scope() as session:
        record = store_memory(
            session,
            type=req.type,
            key=req.key,
            content=req.content,
            metadata=req.metadata,
            source_task_id=req.source_task_id,
        )
        return _mem_response(record)


@router.get("", response_model=MemoryListResponse)
def get_memory(
    query: str | None = Query(default=None),
    type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MemoryListResponse:
    if type and type not in {"fact", "preference", "context", "system"}:
        raise HTTPException(status_code=400, detail=f"invalid type: {type}")
    with session_scope() as session:
        items, total = search_memory(session, query=query, type=type, limit=limit, offset=offset)
        return MemoryListResponse(total=total, items=[_mem_response(r) for r in items])


@router.get("/skills", response_model=SkillMemoryListResponse)
def get_skills(limit: int = Query(default=50, ge=1, le=200)) -> SkillMemoryListResponse:
    with session_scope() as session:
        items, total = list_skills(session, limit=limit)
        return SkillMemoryListResponse(total=total, items=[_skill_response(s) for s in items])


@router.get("/decisions", response_model=DecisionLogListResponse)
def get_decisions(
    task_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DecisionLogListResponse:
    with session_scope() as session:
        items, total = list_decision_logs(session, task_id=task_id, limit=limit, offset=offset)
        return DecisionLogListResponse(total=total, items=[_decision_response(d) for d in items])
