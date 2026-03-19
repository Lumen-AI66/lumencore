from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..agents.agent_registry import AGENT_REGISTRY, get_agent_definition, get_agent_key_for_id, list_agent_definitions
from ..models import Agent, AgentCapability, AgentPolicy, AgentRun


READY_AGENT_STATUSES = {"active", "idle"}


def _load_agent_rows(session: Session) -> dict[str, Agent]:
    agents = session.execute(select(Agent)).scalars()
    return {str(agent.id): agent for agent in agents}


def _load_agent_capabilities(session: Session) -> dict[str, list[str]]:
    rows = session.execute(select(AgentCapability.agent_id, AgentCapability.task_type)).all()
    capabilities: dict[str, list[str]] = {}
    for agent_id, task_type in rows:
        capabilities.setdefault(str(agent_id), []).append(str(task_type))
    return {agent_id: sorted(values) for agent_id, values in capabilities.items()}


def list_agents(session: Session) -> list[dict]:
    agents = list(session.execute(select(Agent).order_by(Agent.created_at.asc())).scalars())
    items: list[dict] = []
    for agent in agents:
        caps = list(
            session.execute(
                select(AgentCapability.task_type)
                .where(AgentCapability.agent_id == agent.id)
                .order_by(AgentCapability.task_type.asc())
            ).scalars()
        )
        meta = dict(agent.metadata_json or {})
        items.append(
            {
                "agent_id": str(agent.id),
                "tenant_id": str(getattr(agent, "tenant_id", "owner") or "owner"),
                "name": agent.name,
                "description": str(meta.get("description", "")),
                "status": str(agent.status),
                "capabilities": caps,
                "created_at": agent.created_at,
            }
        )
    return items


def _build_registry_item(
    definition,
    *,
    agent_row: Agent | None,
    persisted_task_types: list[str],
) -> dict:
    record_status = str(agent_row.status) if agent_row else "missing"
    runtime_bound = bool(definition.runtime_binding and definition.runtime_binding in AGENT_REGISTRY)
    available = bool(
        definition.enabled
        and runtime_bound
        and agent_row is not None
        and str(agent_row.status).lower() in READY_AGENT_STATUSES
    )

    if not definition.enabled:
        runtime_status = "disabled"
    elif agent_row is None:
        runtime_status = "unknown"
    elif not runtime_bound:
        runtime_status = "unavailable"
    elif str(agent_row.status).lower() in READY_AGENT_STATUSES:
        runtime_status = "ready"
    else:
        runtime_status = "unavailable"

    metadata = dict(definition.metadata or {})
    if agent_row and agent_row.metadata_json:
        metadata.update(dict(agent_row.metadata_json or {}))

    capability_keys = [capability.key for capability in definition.capabilities]
    capability_details = [
        {
            "key": capability.key,
            "name": capability.name,
            "description": capability.description,
            "version": capability.version,
            "enabled": capability.enabled,
        }
        for capability in definition.capabilities
    ]

    return {
        "agent_key": definition.agent_key,
        "agent_id": definition.agent_id,
        "tenant_id": str(getattr(agent_row, "tenant_id", "owner") or "owner"),
        "name": definition.name,
        "description": definition.description,
        "agent_type": definition.agent_type,
        "version": definition.version,
        "enabled": definition.enabled,
        "visibility": definition.visibility,
        "source": definition.source,
        "status": record_status,
        "runtime_status": runtime_status,
        "registered": True,
        "available": available,
        "last_error": None,
        "capabilities": capability_keys,
        "capability_details": capability_details,
        "metadata": metadata,
        "runtime_metadata": {
            "runtime_binding": definition.runtime_binding,
            "persisted_task_types": persisted_task_types,
        },
        "registered_at": agent_row.created_at if agent_row else None,
        "updated_at": agent_row.updated_at if agent_row else None,
        "created_at": agent_row.created_at if agent_row else None,
    }


def list_registry_agents(
    session: Session,
    *,
    enabled: bool | None = None,
    capability: str | None = None,
    runtime_status: str | None = None,
) -> dict:
    agent_rows = _load_agent_rows(session)
    persisted_capabilities = _load_agent_capabilities(session)
    items = []

    for definition in list_agent_definitions():
        item = _build_registry_item(
            definition,
            agent_row=agent_rows.get(definition.agent_id),
            persisted_task_types=persisted_capabilities.get(definition.agent_id, []),
        )
        if enabled is not None and item["enabled"] != enabled:
            continue
        if capability and capability not in item["capabilities"]:
            continue
        if runtime_status and item["runtime_status"] != runtime_status:
            continue
        items.append(item)

    items.sort(key=lambda item: item["agent_key"])
    counts_by_status = dict(Counter(item["runtime_status"] for item in items))
    return {
        "total": len(items),
        "counts_by_status": counts_by_status,
        "items": items,
    }


def get_registry_agent(session: Session, agent_key: str) -> dict:
    definition = get_agent_definition(agent_key)
    agent_rows = _load_agent_rows(session)
    persisted_capabilities = _load_agent_capabilities(session)
    return _build_registry_item(
        definition,
        agent_row=agent_rows.get(definition.agent_id),
        persisted_task_types=persisted_capabilities.get(definition.agent_id, []),
    )


def get_registry_agent_status(session: Session, agent_key: str) -> dict:
    item = get_registry_agent(session, agent_key)
    return {
        "agent_key": item["agent_key"],
        "registered": item["registered"],
        "enabled": item["enabled"],
        "available": item["available"],
        "status": item["runtime_status"],
        "last_error": item["last_error"],
        "runtime_metadata": item["runtime_metadata"],
    }


def list_policies(session: Session) -> list[dict]:
    rows = session.execute(select(AgentPolicy).order_by(AgentPolicy.agent_id.asc())).scalars()
    items = []
    for policy in rows:
        items.append(
            {
                "agent_id": str(policy.agent_id),
                "agent_key": get_agent_key_for_id(str(policy.agent_id)),
                "execution_allowed": policy.execution_allowed,
                "max_runtime_seconds": policy.max_runtime_seconds,
                "allowed_task_types": policy.allowed_task_types or [],
                "owner_only_execution": policy.owner_only_execution,
                "future_budget_limit": float(policy.future_budget_limit) if policy.future_budget_limit is not None else None,
                "updated_at": policy.updated_at,
            }
        )
    return items


def get_agent_status_summary(session: Session) -> dict:
    total_agents = session.execute(select(func.count(Agent.id))).scalar_one()
    active_agents = session.execute(select(func.count(Agent.id)).where(Agent.status.in_(["active", "idle"]))).scalar_one()
    disabled_agents = int(total_agents) - int(active_agents)

    total_runs = session.execute(select(func.count(AgentRun.id))).scalar_one()
    last_run_at = session.execute(select(func.max(AgentRun.updated_at))).scalar_one_or_none()

    return {
        "total_agents": int(total_agents),
        "active_agents": int(active_agents),
        "disabled_agents": int(disabled_agents),
        "last_run_at": last_run_at,
        "total_runs": int(total_runs),
    }
