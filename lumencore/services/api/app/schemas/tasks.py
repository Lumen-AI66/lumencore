from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..models import TaskStatus


class TaskCreateRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=64)
    agent: str | None = Field(default=None, max_length=128)
    priority: int = Field(default=0, ge=0, le=1000)
    payload: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False


class TaskResponse(BaseModel):
    id: str
    task_type: str
    status: TaskStatus
    agent: str | None = None
    priority: int
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    approval_required: bool
    approval_status: str
    execution_task_id: str | None = None
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    total: int
    items: list[TaskResponse]


class TaskApproveRequest(BaseModel):
    approved: bool
    reason: str | None = None
