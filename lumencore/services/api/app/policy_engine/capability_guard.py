from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..agents.agent_registry import list_registry_backed_agent_ids
from ..models import Agent, AgentCapability


def check_capability(session: Session, *, task_type: str, requested_agent_id: str | None) -> tuple[bool, str]:
    stmt = (
        select(AgentCapability.id)
        .join(Agent, Agent.id == AgentCapability.agent_id)
        .where(or_(Agent.status == "active", Agent.status == "idle"))
        .where(AgentCapability.task_type == task_type)
    )

    if task_type == "agent_task":
        registry_ids = list_registry_backed_agent_ids()
        if requested_agent_id and str(requested_agent_id) not in registry_ids:
            return False, "requested agent_id is not registry-backed for agent_task"
        stmt = stmt.where(Agent.id.in_(registry_ids))

    if requested_agent_id:
        stmt = stmt.where(Agent.id == requested_agent_id)

    exists = session.execute(stmt.limit(1)).scalar_one_or_none()
    if not exists:
        return False, f"no capable active agent for task_type: {task_type}"
    return True, "capability allowed"
