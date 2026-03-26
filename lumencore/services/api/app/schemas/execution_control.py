from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ..schemas.execution_tasks import ExecutionTaskResponse


class ExecutionControlActionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    source: str = Field(default="operator", min_length=1, max_length=64)


class ExecutionControlStateResponse(BaseModel):
    task_id: str
    control_status: str
    control_reason: str | None = None
    control_source: str
    updated_at: datetime
    execution_allowed: bool


class ExecutionControlActionResponse(BaseModel):
    action: str
    task_id: str
    execution_control: ExecutionControlStateResponse
    task: ExecutionTaskResponse
