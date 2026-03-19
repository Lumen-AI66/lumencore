from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentRuntimeStateStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AgentRunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64, default="owner")
    agent_id: str | None = Field(default=None, max_length=64)
    agent_type: str = Field(min_length=1, max_length=64)
    command_id: str | None = Field(default=None, max_length=64)
    task_id: str = Field(min_length=1, max_length=64)
    status: AgentRuntimeStateStatus
    current_step: str | None = Field(default=None, max_length=128)
    last_decision: dict[str, Any] | None = None
    retry_count: int = Field(default=0, ge=0)
    started_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    last_error: str | None = Field(default=None, max_length=500)


class TaskState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=64)
    run_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64, default="owner")
    task_type: str = Field(min_length=1, max_length=64)
    status: AgentRuntimeStateStatus
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    failure_metadata: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


class AgentStateEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    run_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64, default="owner")
    task_id: str | None = Field(default=None, max_length=64)
    event_type: str = Field(min_length=1, max_length=128)
    step_name: str | None = Field(default=None, max_length=128)
    message: str = Field(min_length=1, max_length=500)
    payload_summary: dict[str, Any] | None = None
    severity: str = Field(default="info", max_length=32)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
