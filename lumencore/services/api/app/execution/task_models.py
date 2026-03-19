from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionTaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    retrying = "retrying"


class ExecutionTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64, default="owner")
    command_id: str | None = Field(default=None, max_length=64)
    agent_id: str | None = Field(default=None, max_length=64)
    agent_type: str = Field(min_length=1, max_length=64)
    task_type: str = Field(min_length=1, max_length=64)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    status: ExecutionTaskStatus
    priority: int = Field(default=100, ge=0, le=1000)
    retries: int = Field(default=0, ge=0)
    max_retries: int = Field(default=0, ge=0, le=10)
    available_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = Field(default=None, max_length=500)
    result_summary: dict[str, Any] | None = None
    task_metadata: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
