from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Agent, AgentCapability, AgentPolicy
from .agent_types import AnalysisAgent, AutomationAgent, BaseAgent, OpenclawAgent, ResearchAgent

DEFAULT_AGENT_ID = "11111111-1111-4111-8111-111111111111"


@dataclass(frozen=True)
class RegistryCapability:
    key: str
    name: str
    description: str | None = None
    version: str | None = None
    enabled: bool = True


@dataclass(frozen=True)
class AgentDefinition:
    agent_key: str
    agent_id: str
    agent_type: str
    name: str
    description: str
    version: str | None = None
    enabled: bool = True
    visibility: str = "system"
    capabilities: tuple[RegistryCapability, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = "builtin"
    runtime_binding: str | None = None
    task_types: tuple[str, ...] = ()
    owner_only_execution: bool = False
    max_runtime_seconds: int = 15
    future_budget_limit: float | None = 0.0


_AGENT_INSTANCES: tuple[BaseAgent, ...] = (
    ResearchAgent(),
    AutomationAgent(),
    AnalysisAgent(),
    OpenclawAgent(),
)

AGENT_REGISTRY: dict[str, BaseAgent] = {agent.agent_type: agent for agent in _AGENT_INSTANCES}
AGENT_IDS_BY_TYPE: dict[str, str] = {agent.agent_type: agent.agent_id for agent in _AGENT_INSTANCES}

BUILTIN_AGENT_DEFINITIONS: tuple[AgentDefinition, ...] = (
    AgentDefinition(
        agent_key="research.default",
        agent_id=ResearchAgent.agent_id,
        agent_type=ResearchAgent.agent_type,
        name=ResearchAgent.name,
        description=ResearchAgent.description,
        version="1",
        capabilities=(
            RegistryCapability("research", "Research", "Handles bounded research-oriented agent tasks."),
            RegistryCapability("tool_use", "Tool Use", "Uses governed internal tools during execution."),
            RegistryCapability("sync_response", "Synchronous Response", "Completes bounded runs inline."),
            RegistryCapability("registry_visible", "Registry Visible", "Exposed through the agent registry surface."),
        ),
        metadata={"tools": list(ResearchAgent.tools), "task_types": ["agent_task"]},
        runtime_binding=ResearchAgent.agent_type,
        task_types=("agent_task",),
    ),
    AgentDefinition(
        agent_key="automation.default",
        agent_id=AutomationAgent.agent_id,
        agent_type=AutomationAgent.agent_type,
        name=AutomationAgent.name,
        description=AutomationAgent.description,
        version="1",
        capabilities=(
            RegistryCapability("automation", "Automation", "Handles bounded automation-oriented agent tasks."),
            RegistryCapability("tool_use", "Tool Use", "Uses governed internal tools during execution."),
            RegistryCapability("sync_response", "Synchronous Response", "Completes bounded runs inline."),
            RegistryCapability("registry_visible", "Registry Visible", "Exposed through the agent registry surface."),
        ),
        metadata={"tools": list(AutomationAgent.tools), "task_types": ["agent_task"]},
        runtime_binding=AutomationAgent.agent_type,
        task_types=("agent_task",),
    ),
    AgentDefinition(
        agent_key="analysis.default",
        agent_id=AnalysisAgent.agent_id,
        agent_type=AnalysisAgent.agent_type,
        name=AnalysisAgent.name,
        description=AnalysisAgent.description,
        version="1",
        capabilities=(
            RegistryCapability("analysis", "Analysis", "Handles bounded analysis-oriented agent tasks."),
            RegistryCapability("tool_use", "Tool Use", "Uses governed internal tools during execution."),
            RegistryCapability("sync_response", "Synchronous Response", "Completes bounded runs inline."),
            RegistryCapability("registry_visible", "Registry Visible", "Exposed through the agent registry surface."),
        ),
        metadata={"tools": list(AnalysisAgent.tools), "task_types": ["agent_task"]},
        runtime_binding=AnalysisAgent.agent_type,
        task_types=("agent_task",),
    ),
    AgentDefinition(
        agent_key="openclaw.default",
        agent_id=OpenclawAgent.agent_id,
        agent_type=OpenclawAgent.agent_type,
        name=OpenclawAgent.name,
        description=OpenclawAgent.description,
        version="1",
        capabilities=(
            RegistryCapability("execution", "Execution", "Executes operator commands via Claude AI."),
            RegistryCapability("tool_use", "Tool Use", "Uses governed Claude tool during execution."),
            RegistryCapability("sync_response", "Synchronous Response", "Completes bounded runs inline."),
            RegistryCapability("registry_visible", "Registry Visible", "Exposed through the agent registry surface."),
            RegistryCapability("telegram", "Telegram", "Handles commands from the Telegram operator interface."),
        ),
        metadata={"tools": list(OpenclawAgent.tools), "task_types": ["agent_task"], "source": "telegram"},
        runtime_binding=OpenclawAgent.agent_type,
        task_types=("agent_task",),
    ),
)

AGENT_DEFINITIONS_BY_KEY: dict[str, AgentDefinition] = {
    definition.agent_key: definition for definition in BUILTIN_AGENT_DEFINITIONS
}
AGENT_DEFINITIONS_BY_TYPE: dict[str, AgentDefinition] = {
    definition.agent_type: definition for definition in BUILTIN_AGENT_DEFINITIONS
}
AGENT_KEYS_BY_ID: dict[str, str] = {
    definition.agent_id: definition.agent_key for definition in BUILTIN_AGENT_DEFINITIONS
}
REGISTRY_BACKED_AGENT_IDS: frozenset[str] = frozenset(AGENT_KEYS_BY_ID.keys())

DEFAULT_AGENTS = [
    {
        "id": OpenclawAgent.agent_id,
        "name": OpenclawAgent.name,
        "description": OpenclawAgent.description,
        "agent_type": OpenclawAgent.agent_type,
        "status": "active",
        "capabilities": ["agent_task"],
        "policy": {
            "execution_allowed": True,
            "max_runtime_seconds": 60,
            "allowed_task_types": ["agent_task"],
            "owner_only_execution": True,
            "future_budget_limit": 0.10,
        },
    },
    {
        "id": DEFAULT_AGENT_ID,
        "name": "core-agent-runner",
        "description": "Policy-bound internal agent executor for safe deterministic tasks.",
        "agent_type": "runtime",
        "status": "active",
        "capabilities": ["agent.ping", "agent.echo"],
        "policy": {
            "execution_allowed": True,
            "max_runtime_seconds": 20,
            "allowed_task_types": ["agent.ping", "agent.echo"],
            "owner_only_execution": True,
            "future_budget_limit": 0.0,
        },
    },
    {
        "id": ResearchAgent.agent_id,
        "name": ResearchAgent.name,
        "description": ResearchAgent.description,
        "agent_type": ResearchAgent.agent_type,
        "status": "active",
        "capabilities": ["agent_task"],
        "policy": {
            "execution_allowed": True,
            "max_runtime_seconds": 15,
            "allowed_task_types": ["agent_task"],
            "owner_only_execution": False,
            "future_budget_limit": 0.0,
        },
    },
    {
        "id": AutomationAgent.agent_id,
        "name": AutomationAgent.name,
        "description": AutomationAgent.description,
        "agent_type": AutomationAgent.agent_type,
        "status": "active",
        "capabilities": ["agent_task"],
        "policy": {
            "execution_allowed": True,
            "max_runtime_seconds": 15,
            "allowed_task_types": ["agent_task"],
            "owner_only_execution": False,
            "future_budget_limit": 0.0,
        },
    },
    {
        "id": AnalysisAgent.agent_id,
        "name": AnalysisAgent.name,
        "description": AnalysisAgent.description,
        "agent_type": AnalysisAgent.agent_type,
        "status": "active",
        "capabilities": ["agent_task"],
        "policy": {
            "execution_allowed": True,
            "max_runtime_seconds": 15,
            "allowed_task_types": ["agent_task"],
            "owner_only_execution": False,
            "future_budget_limit": 0.0,
        },
    },
]


def get_agent(agent_type: str) -> BaseAgent:
    normalized = str(agent_type or "automation").strip().lower() or "automation"
    try:
        return AGENT_REGISTRY[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported agent_type: {normalized}") from exc


def get_agent_id(agent_type: str) -> str:
    return get_agent(agent_type).agent_id


def list_agent_definitions() -> list[AgentDefinition]:
    return list(BUILTIN_AGENT_DEFINITIONS)


def get_agent_definition(agent_key: str) -> AgentDefinition:
    normalized = str(agent_key or "").strip().lower()
    try:
        return AGENT_DEFINITIONS_BY_KEY[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported agent_key: {normalized}") from exc


def get_agent_definition_by_type(agent_type: str) -> AgentDefinition:
    normalized = str(agent_type or "").strip().lower()
    try:
        return AGENT_DEFINITIONS_BY_TYPE[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported registry-backed agent_type: {normalized}") from exc


def get_agent_key_for_id(agent_id: str | None) -> str | None:
    if not agent_id:
        return None
    return AGENT_KEYS_BY_ID.get(str(agent_id))


def list_registry_backed_agent_ids() -> list[str]:
    return list(REGISTRY_BACKED_AGENT_IDS)


def is_registry_backed_agent_id(agent_id: str | None) -> bool:
    return bool(agent_id and str(agent_id) in REGISTRY_BACKED_AGENT_IDS)


def resolve_registry_definition_for_agent_task(*, agent_type: str | None = None, requested_agent_id: str | None = None) -> AgentDefinition:
    if requested_agent_id:
        normalized_agent_id = str(requested_agent_id)
        registry_key = get_agent_key_for_id(normalized_agent_id)
        if not registry_key:
            raise ValueError("requested agent_id is not registry-backed for agent_task")
        definition = get_agent_definition(registry_key)
        if agent_type and str(definition.agent_type).lower() != str(agent_type).strip().lower():
            raise ValueError("requested agent_id does not match the planned built-in agent_type")
        return definition

    if agent_type:
        return get_agent_definition_by_type(agent_type)

    raise ValueError("agent_task resolution requires agent_type or requested_agent_id")


def _upsert_capability(session: Session, *, agent_id: str, task_type: str) -> None:
    existing = session.execute(
        select(AgentCapability).where(
            AgentCapability.agent_id == agent_id,
            AgentCapability.task_type == task_type,
        )
    ).scalar_one_or_none()
    if existing:
        return
    session.add(AgentCapability(agent_id=agent_id, task_type=task_type))


def ensure_agent_registry_seeded(session: Session) -> None:
    now = datetime.now(timezone.utc)
    for seed in DEFAULT_AGENTS:
        agent = session.execute(select(Agent).where(Agent.id == seed["id"])).scalar_one_or_none()
        if not agent:
            agent = Agent(
                id=seed["id"],
                name=seed["name"],
                agent_type=seed["agent_type"],
                status=seed["status"],
                metadata_json={"description": seed["description"]},
                created_at=now,
                updated_at=now,
            )
            session.add(agent)
        else:
            agent.name = seed["name"]
            agent.agent_type = seed["agent_type"]
            if str(agent.status).lower() not in {"active", "idle"}:
                agent.status = seed["status"]
            meta = dict(agent.metadata_json or {})
            meta["description"] = seed["description"]
            agent.metadata_json = meta
            agent.updated_at = now

        for capability in seed["capabilities"]:
            _upsert_capability(session, agent_id=seed["id"], task_type=capability)

        policy_cfg = seed["policy"]
        policy = session.get(AgentPolicy, seed["id"])
        if not policy:
            session.add(
                AgentPolicy(
                    agent_id=seed["id"],
                    execution_allowed=policy_cfg["execution_allowed"],
                    max_runtime_seconds=policy_cfg["max_runtime_seconds"],
                    allowed_task_types=policy_cfg["allowed_task_types"],
                    owner_only_execution=policy_cfg["owner_only_execution"],
                    future_budget_limit=policy_cfg["future_budget_limit"],
                    updated_at=now,
                )
            )
        else:
            policy.execution_allowed = policy_cfg["execution_allowed"]
            policy.max_runtime_seconds = policy_cfg["max_runtime_seconds"]
            policy.allowed_task_types = policy_cfg["allowed_task_types"]
            policy.owner_only_execution = policy_cfg["owner_only_execution"]
            policy.future_budget_limit = policy_cfg["future_budget_limit"]
            policy.updated_at = now
