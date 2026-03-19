from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConnectorItem(BaseModel):
    connector_key: str
    name: str
    kind: str
    source: str
    enabled: bool
    configured: bool
    status: str
    healthy: bool | None = None
    allowed_for_execution: bool
    supported_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)


class ConnectorListResponse(BaseModel):
    total: int
    items: list[ConnectorItem]


class ConnectorStatusResponse(BaseModel):
    connector_key: str
    enabled: bool
    configured: bool
    status: str
    healthy: bool | None = None
    allowed_for_execution: bool
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)
