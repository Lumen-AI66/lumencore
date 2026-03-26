from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class CommandRunRequest(BaseModel):
    command_text: str | None = Field(default=None, min_length=1, max_length=500)
    command: str | None = Field(default=None, min_length=1, max_length=500)
    mode: str | None = Field(default=None, max_length=32)
    tenant_id: str = "owner"
    project_id: str = "default"
    requested_agent_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_command_input(self) -> "CommandRunRequest":
        if self.command_text and self.command:
            raise ValueError("send only command_text; legacy command cannot be combined with command_text")
        if not (self.command_text or self.command):
            raise ValueError("command_text is required")
        return self

    def resolved_command_text(self) -> str:
        return (self.command_text or self.command or "").strip()

    def uses_legacy_command_field(self) -> bool:
        return bool(self.command and not self.command_text)


class CommandRunResponse(BaseModel):
    id: str
    tenant_id: str
    command_text: str
    normalized_command: str
    intent: str
    planned_task_type: str | None = None
    requested_mode: str | None = None
    selected_agent_id: str | None = None
    status: str
    execution_task_id: str | None = None
    execution_task_status: str | None = None
    result: str | None = None
    execution_decision: str
    approval_required: bool
    approval_status: str
    policy_reason: str | None = None
    queue_bucket: str | None = None
    last_control_action: str | None = None
    last_control_reason: str | None = None
    cancelled_at: datetime | None = None
    retried_from_id: str | None = None
    job_id: str | None = None
    request_id: str | None = None
    run_id: str | None = None
    correlation_id: str | None = None
    connector_name: str | None = None
    error_code: str | None = None
    execution_lineage: dict[str, Any] | None = None
    result_summary: dict[str, Any] | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CommandHistoryResponse(BaseModel):
    limit: int
    items: list[CommandRunResponse]




