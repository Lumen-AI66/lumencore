from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NodeItem(BaseModel):
    node_key: str
    name: str
    kind: str
    source: str
    enabled: bool
    registered: bool
    status: str
    healthy: bool | None = None
    capabilities: list[str] = Field(default_factory=list)
    last_heartbeat_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)


class NodeListResponse(BaseModel):
    total: int
    items: list[NodeItem]


class NodeStatusResponse(BaseModel):
    node_key: str
    enabled: bool
    registered: bool
    status: str
    healthy: bool | None = None
    last_heartbeat_at: datetime | None = None
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)
