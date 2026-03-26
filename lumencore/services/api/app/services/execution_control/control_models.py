from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ExecutionControlStatus(str, Enum):
    allowed = "allowed"
    paused = "paused"
    blocked = "blocked"
    cancelled = "cancelled"


class ExecutionControlState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=64)
    control_status: ExecutionControlStatus = ExecutionControlStatus.allowed
    control_reason: str | None = Field(default=None, max_length=500)
    control_source: str = Field(default="system", min_length=1, max_length=64)
    updated_at: datetime
