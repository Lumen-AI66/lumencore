from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..execution.task_models import ExecutionTaskStatus


class ExecutionTaskResponse(BaseModel):
    task_id: str
    tenant_id: str
    command_id: str | None = None
    agent_id: str | None = None
    agent_type: str
    task_type: str
    status: ExecutionTaskStatus
    priority: int
    retries: int
    max_retries: int
    available_at: datetime
    started_at: datetime | None = None
    updated_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    execution_task_id: str | None = None
    execution_task_status: str | None = None
    result: str | None = None
    agent_result: dict[str, Any] | None = None
    connector_name: str | None = None
    error_code: str | None = None
    execution_control: dict[str, Any] | None = None
    execution_policy: dict[str, Any] | None = None
    execution_lineage: dict[str, Any] | None = None
    result_summary: dict[str, Any] | None = None


class ExecutionTaskListResponse(BaseModel):
    limit: int = Field(ge=1, le=100)
    items: list[ExecutionTaskResponse]
