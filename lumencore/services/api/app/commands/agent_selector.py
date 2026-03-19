from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..agents.agent_registry import list_registry_backed_agent_ids
from ..models import Agent, AgentCapability


def select_agent_for_task(session: Session, task_type: str) -> str | None:
    stmt = (
        select(Agent.id)
        .join(AgentCapability, AgentCapability.agent_id == Agent.id)
        .where(or_(Agent.status == "active", Agent.status == "idle"))
        .where(AgentCapability.task_type == task_type)
        .order_by(Agent.created_at.asc())
        .limit(1)
    )
    if task_type == "agent_task":
        stmt = stmt.where(Agent.id.in_(list_registry_backed_agent_ids()))
    row = session.execute(stmt).scalar_one_or_none()
    return str(row) if row else None
