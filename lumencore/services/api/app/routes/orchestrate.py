"""Orchestration endpoint — Openclaw full reasoning + planning + execution."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any

from ..orchestrator.openclaw_orchestrator import get_orchestrator

router = APIRouter(prefix="/api/orchestrate", tags=["orchestrate"])


class OrchestrateRequest(BaseModel):
    task: str
    context: dict[str, Any] | None = None
    deep: bool = False
    operator_id: str = "owner"


class OrchestrateResponse(BaseModel):
    task: str
    status: str
    summary: str
    plan: str
    actions_taken: list[dict]
    reasoning_depth: float
    model_used: str
    requires_approval: bool
    approval_items: list[str]
    memory_stored: bool
    timestamp: str


@router.post("", response_model=OrchestrateResponse)
def orchestrate(req: OrchestrateRequest) -> OrchestrateResponse:
    """Run a task through Openclaw's full reasoning + planning pipeline."""
    orchestrator = get_orchestrator(deep=req.deep)
    result = orchestrator.orchestrate(
        req.task,
        context=req.context,
        operator_id=req.operator_id,
    )
    return OrchestrateResponse(
        task=result.task,
        status=result.status,
        summary=result.summary,
        plan=result.plan,
        actions_taken=result.actions_taken,
        reasoning_depth=result.reasoning_depth,
        model_used=result.model_used,
        requires_approval=result.requires_approval,
        approval_items=result.approval_items,
        memory_stored=result.memory_stored,
        timestamp=result.timestamp,
    )
