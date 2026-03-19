from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentItem(BaseModel):
    agent_id: str
    tenant_id: str = "owner"
    name: str
    description: str
    status: str
    capabilities: list[str]
    created_at: datetime


class AgentListResponse(BaseModel):
    total: int
    items: list[AgentItem]


class AgentRegistryCapabilityItem(BaseModel):
    key: str
    name: str
    description: str | None = None
    version: str | None = None
    enabled: bool = True


class AgentRegistryItem(BaseModel):
    agent_key: str
    agent_id: str
    tenant_id: str = "owner"
    name: str
    description: str
    agent_type: str
    version: str | None = None
    enabled: bool = True
    visibility: str
    source: str
    status: str
    runtime_status: str
    registered: bool = True
    available: bool = False
    last_error: str | None = None
    capabilities: list[str]
    capability_details: list[AgentRegistryCapabilityItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)
    registered_at: datetime | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None


class AgentRegistryListResponse(BaseModel):
    total: int
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    items: list[AgentRegistryItem]


class AgentPolicyItem(BaseModel):
    agent_id: str
    agent_key: str | None = None
    execution_allowed: bool
    max_runtime_seconds: int
    allowed_task_types: list[str]
    owner_only_execution: bool
    future_budget_limit: float | None
    updated_at: datetime


class AgentPoliciesResponse(BaseModel):
    total: int
    items: list[AgentPolicyItem]


class AgentStatusResponse(BaseModel):
    total_agents: int
    active_agents: int
    disabled_agents: int
    last_run_at: datetime | None = None
    total_runs: int


class AgentRegistryStatusResponse(BaseModel):
    agent_key: str
    registered: bool
    enabled: bool
    available: bool
    status: str
    last_error: str | None = None
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = None
    tenant_id: str = "owner"
    project_id: str = "default"
    estimated_cost: float = 0.0


class AgentRunResponse(BaseModel):
    id: str
    job_type: str
    status: str
    queue_task_id: str | None
    created_at: datetime
