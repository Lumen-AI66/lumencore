from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..planning.plan_models import PlanRunStatus, PlanStepStatus


class PlanStepResponse(BaseModel):
    step_id: str
    step_index: int
    step_type: str
    agent_type: str
    status: PlanStepStatus
    execution_task_id: str | None = None
    error: str | None = None
    updated_at: datetime
    completed_at: datetime | None = None


class PlanListItemResponse(BaseModel):
    plan_id: str
    tenant_id: str
    command_id: str | None = None
    plan_type: str
    intent: str | None = None
    status: PlanRunStatus
    total_steps: int
    current_step_index: int
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class PlanDetailResponse(PlanListItemResponse):
    steps: list[PlanStepResponse]
    result_summary: dict[str, Any] | None = None


class PlanListResponse(BaseModel):
    limit: int = Field(ge=1, le=100)
    items: list[PlanListItemResponse]
