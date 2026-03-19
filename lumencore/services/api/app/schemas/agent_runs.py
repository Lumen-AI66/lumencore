from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ..models import AgentRunStatus


class AgentRunResponse(BaseModel):
    run_id: str
    tenant_id: str
    command_id: str | None = None
    agent_id: str
    agent_type: str | None = None
    task_type: str
    status: AgentRunStatus
    started_at: datetime | None = None
    updated_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None
    steps_executed: int | None = None
    tools_used: list[str] = []
    error: str | None = None


class AgentRunListResponse(BaseModel):
    limit: int = Field(ge=1, le=100)
    items: list[AgentRunResponse]
