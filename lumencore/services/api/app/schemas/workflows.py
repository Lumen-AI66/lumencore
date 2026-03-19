from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..workflows.workflow_models import WorkflowRunStatus


class WorkflowPlanSummaryResponse(BaseModel):
    linked_plan_id: str | None = None
    plan_status: str | None = None
    total_steps: int | None = None
    current_step_index: int | None = None
    latest_step_status: str | None = None


class WorkflowListItemResponse(BaseModel):
    workflow_id: str
    tenant_id: str
    command_id: str | None = None
    workflow_type: str
    status: WorkflowRunStatus
    linked_plan_id: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    result_summary: dict[str, Any] | None = None


class WorkflowDetailResponse(WorkflowListItemResponse):
    linked_plan_summary: WorkflowPlanSummaryResponse | None = None


class WorkflowListResponse(BaseModel):
    limit: int = Field(ge=1, le=100)
    items: list[WorkflowListItemResponse]
