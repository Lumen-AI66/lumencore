from __future__ import annotations

from datetime import datetime, timezone
import uuid
from uuid import UUID

from sqlalchemy.orm import Session

from ..models import AgentAuditEvent


def _normalize_uuid_agent_id(agent_id: str | None) -> str | None:
    value = str(agent_id or '').strip()
    if not value:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def write_audit_event(session: Session, *, tenant_id: str, agent_id: str | None, action: str, policy_result: str, metadata: dict) -> None:
    event = AgentAuditEvent(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        tenant_id=tenant_id,
        agent_id=agent_id,
        action=action,
        policy_result=policy_result,
        event_metadata=metadata or {},
    )
    session.add(event)


def write_connector_audit_event(session: Session, event: dict) -> None:
    """Map connector audit rows into the existing audit pipeline writer."""
    write_audit_event(
        session,
        tenant_id=str(event.get("tenant_id") or "owner"),
        agent_id=_normalize_uuid_agent_id(event.get("agent_id")),
        action=str(event.get("action") or "connector.event"),
        policy_result=str(event.get("policy_result") or "deny"),
        metadata=dict(event.get("metadata") or {}),
    )


def write_tool_audit_event(session: Session, event: dict) -> None:
    """Map tool audit rows into the existing audit pipeline writer."""
    write_audit_event(
        session,
        tenant_id=str(event.get("tenant_id") or "owner"),
        agent_id=_normalize_uuid_agent_id(event.get("agent_id")),
        action=str(event.get("action") or "tool.event"),
        policy_result=str(event.get("policy_result") or "deny"),
        metadata=dict(event.get("metadata") or {}),
    )
