from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlanRunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class PlanStepStatus(str, Enum):
    pending = "pending"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class PlanRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64, default="owner")
    command_id: str | None = Field(default=None, max_length=64)
    plan_type: str = Field(min_length=1, max_length=64)
    status: PlanRunStatus
    total_steps: int = Field(default=0, ge=0, le=5)
    current_step_index: int = Field(default=0, ge=0, le=5)
    error: str | None = Field(default=None, max_length=500)
    result_summary: dict[str, Any] | None = None
    plan_metadata: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1, max_length=64)
    plan_id: str = Field(min_length=1, max_length=64)
    step_index: int = Field(ge=0, le=5)
    step_type: str = Field(min_length=1, max_length=64)
    agent_type: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    status: PlanStepStatus
    execution_task_id: str | None = Field(default=None, max_length=64)
    error: str | None = Field(default=None, max_length=500)
    result_summary: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
