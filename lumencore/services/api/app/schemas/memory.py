from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

MEMORY_TYPES = {"fact", "preference", "context", "system"}
OUTCOME_VALUES = {"success", "failure", "unknown"}


class MemoryCreateRequest(BaseModel):
    type: str = Field(default="fact", pattern="^(fact|preference|context|system)$")
    key: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_task_id: str | None = None


class MemoryResponse(BaseModel):
    id: str
    type: str
    key: str
    content: str
    metadata: dict[str, Any] | None = None
    source_task_id: str | None = None
    created_at: datetime
    updated_at: datetime


class MemoryListResponse(BaseModel):
    total: int
    items: list[MemoryResponse]


class SkillMemoryResponse(BaseModel):
    id: str
    name: str
    description: str
    pattern: dict[str, Any] | None = None
    success_count: int
    last_used_at: datetime | None = None
    created_at: datetime


class SkillMemoryListResponse(BaseModel):
    total: int
    items: list[SkillMemoryResponse]


class DecisionLogResponse(BaseModel):
    id: str
    task_id: str | None = None
    agent: str | None = None
    decision: str
    reasoning: str
    outcome: str
    created_at: datetime


class DecisionLogListResponse(BaseModel):
    total: int
    items: list[DecisionLogResponse]
