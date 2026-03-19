from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..agents.agent_registry import list_registry_backed_agent_ids
from ..models import Agent, AgentCapability, AgentPolicy


def resolve_agent_for_task(
    session: Session,
    *,
    task_type: str,
    requested_agent_id: str | None = None,
) -> tuple[Agent, AgentPolicy]:
    stmt = (
        select(Agent, AgentPolicy)
        .join(AgentCapability, AgentCapability.agent_id == Agent.id)
        .join(AgentPolicy, AgentPolicy.agent_id == Agent.id)
        .where(or_(Agent.status == "active", Agent.status == "idle"))
        .where(AgentCapability.task_type == task_type)
        .order_by(Agent.created_at.asc())
    )

    if task_type == "agent_task":
        registry_ids = list_registry_backed_agent_ids()
        if requested_agent_id and str(requested_agent_id) not in registry_ids:
            raise ValueError("requested agent_id is not registry-backed for agent_task")
        stmt = stmt.where(Agent.id.in_(registry_ids))

    if requested_agent_id:
        stmt = stmt.where(Agent.id == requested_agent_id)

    row = session.execute(stmt).first()
    if not row:
        raise ValueError(f"no active agent found for task_type: {task_type}")

    agent, policy = row
    return agent, policy
