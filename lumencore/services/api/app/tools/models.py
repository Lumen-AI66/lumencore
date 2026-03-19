from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolRiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ToolResultStatus(str, Enum):
    success = "success"
    denied = "denied"
    failed = "failed"
    timeout = "timeout"


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str = Field(min_length=3, max_length=128)
    connector_name: str = Field(min_length=2, max_length=64)
    action: str = Field(min_length=2, max_length=128)
    description: str = Field(min_length=1, max_length=500)
    input_schema_version: str = Field(min_length=1, max_length=32, default="1.0")
    risk_level: ToolRiskLevel = ToolRiskLevel.low
    read_only: bool = True
    enabled_by_default: bool = False
    tags: tuple[str, ...] = Field(default_factory=tuple)
    capability_metadata: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, gt=0, le=300)
    audit_category: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("tool_name", "connector_name", "action")
    @classmethod
    def _normalize_identifier(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("identifier may not be empty")
        return normalized

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: Any) -> tuple[str, ...]:
        if value in (None, ""):
            return ()
        if isinstance(value, str):
            return (value.strip().lower(),) if value.strip() else ()
        if isinstance(value, (list, tuple, set)):
            normalized = []
            for item in value:
                text = str(item).strip().lower()
                if text:
                    normalized.append(text)
            return tuple(dict.fromkeys(normalized))
        raise ValueError("tags must be a string or iterable of strings")


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    command_id: str | None = Field(default=None, max_length=64)
    agent_id: str = Field(min_length=1, max_length=64)
    run_id: str | None = Field(default=None, max_length=64)
    tool_name: str = Field(min_length=3, max_length=128)
    connector_name: str = Field(min_length=2, max_length=64)
    action: str = Field(min_length=2, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tool_name", "connector_name", "action")
    @classmethod
    def _normalize_identifiers(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("identifier may not be empty")
        return normalized


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=64)
    command_id: str | None = Field(default=None, max_length=64)
    agent_id: str = Field(min_length=1, max_length=64)
    run_id: str | None = Field(default=None, max_length=64)
    status: ToolResultStatus
    tool_name: str = Field(min_length=3, max_length=128)
    connector_name: str = Field(min_length=2, max_length=64)
    action: str = Field(min_length=2, max_length=128)
    output: dict[str, Any] | None = None
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=500)
    duration_ms: float | None = Field(default=None, ge=0)
    correlation_id: str = Field(min_length=1, max_length=64)
    audit_reference: str | None = Field(default=None, max_length=128)
    policy_decision_reference: str | None = Field(default=None, max_length=128)
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("tool_name", "connector_name", "action")
    @classmethod
    def _normalize_result_identifiers(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("identifier may not be empty")
        return normalized
