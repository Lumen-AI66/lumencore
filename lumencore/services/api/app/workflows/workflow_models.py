from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkflowRunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class WorkflowRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64, default="owner")
    command_id: str | None = Field(default=None, max_length=64)
    workflow_type: str = Field(min_length=1, max_length=64)
    status: WorkflowRunStatus
    linked_plan_id: str | None = Field(default=None, max_length=64)
    input_summary: dict[str, Any] | None = None
    workflow_metadata: dict[str, Any] | None = None
    result_summary: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
