from __future__ import annotations

"""
Memory Service — Phase 2.

Structured, queryable, auditable memory. No LLM calls. No embeddings.
All retrieval is deterministic (keyword + type filter).
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..models import DecisionLog, MemoryRecord, SkillMemory


# ---------------------------------------------------------------------------
# MemoryRecord
# ---------------------------------------------------------------------------

def store_memory(
    session: Session,
    *,
    type: str,
    key: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    source_task_id: str | None = None,
) -> MemoryRecord:
    record = MemoryRecord(
        type=type,
        key=key,
        content=content,
        metadata_json=metadata or {},
        source_task_id=source_task_id,
    )
    session.add(record)
    session.flush()
    return record


def search_memory(
    session: Session,
    *,
    query: str | None = None,
    type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[MemoryRecord], int]:
    stmt = select(MemoryRecord)

    if type:
        stmt = stmt.where(MemoryRecord.type == type)

    if query:
        pattern = f"%{query}%"
        stmt = stmt.where(
            or_(
                MemoryRecord.key.ilike(pattern),
                MemoryRecord.content.ilike(pattern),
            )
        )

    stmt = stmt.order_by(MemoryRecord.created_at.desc())
    total = session.scalar(
        select(func.count(MemoryRecord.id)).where(
            *_build_filters(type=type, query=query)
        )
    ) or 0
    items = list(session.scalars(stmt.limit(limit).offset(offset)))
    return items, total


def retrieve_relevant_memory(
    session: Session,
    task_context: dict[str, Any],
    *,
    limit: int = 10,
) -> list[MemoryRecord]:
    """
    Retrieve memory relevant to a task context.
    Uses task_type and keys from payload as search terms.
    Non-breaking — returns empty list on any error.
    """
    try:
        task_type = str(task_context.get("task_type") or "")
        terms: list[str] = [t for t in [task_type] if t]

        payload = task_context.get("payload") or {}
        for v in payload.values():
            if isinstance(v, str) and len(v) <= 128:
                terms.append(v)

        if not terms:
            return []

        conditions = [
            or_(
                MemoryRecord.key.ilike(f"%{term}%"),
                MemoryRecord.content.ilike(f"%{term}%"),
            )
            for term in terms[:3]  # cap to 3 terms
        ]
        stmt = (
            select(MemoryRecord)
            .where(or_(*conditions))
            .order_by(MemoryRecord.created_at.desc())
            .limit(limit)
        )
        return list(session.scalars(stmt))
    except Exception:
        return []


def _build_filters(*, type: str | None, query: str | None):
    filters = []
    if type:
        filters.append(MemoryRecord.type == type)
    if query:
        pattern = f"%{query}%"
        filters.append(
            or_(
                MemoryRecord.key.ilike(pattern),
                MemoryRecord.content.ilike(pattern),
            )
        )
    return filters


# ---------------------------------------------------------------------------
# SkillMemory
# ---------------------------------------------------------------------------

def store_skill_memory(
    session: Session,
    *,
    name: str,
    description: str = "",
    pattern: dict[str, Any] | None = None,
) -> SkillMemory:
    existing = session.scalar(select(SkillMemory).where(SkillMemory.name == name))
    if existing:
        existing.success_count = existing.success_count + 1
        existing.last_used_at = datetime.now(timezone.utc)
        if pattern is not None:
            existing.pattern = pattern
        session.add(existing)
        session.flush()
        return existing

    skill = SkillMemory(
        name=name,
        description=description,
        pattern=pattern or {},
        success_count=1,
        last_used_at=datetime.now(timezone.utc),
    )
    session.add(skill)
    session.flush()
    return skill


def list_skills(session: Session, *, limit: int = 50) -> tuple[list[SkillMemory], int]:
    items = list(session.scalars(
        select(SkillMemory).order_by(SkillMemory.success_count.desc()).limit(limit)
    ))
    total = session.scalar(select(func.count(SkillMemory.id))) or 0
    return items, total


# ---------------------------------------------------------------------------
# DecisionLog
# ---------------------------------------------------------------------------

def store_decision_log(
    session: Session,
    *,
    task_id: str | None,
    agent: str | None,
    decision: str,
    reasoning: str = "",
    outcome: str = "unknown",
) -> DecisionLog:
    log = DecisionLog(
        task_id=task_id,
        agent=agent,
        decision=decision,
        reasoning=reasoning,
        outcome=outcome,
    )
    session.add(log)
    session.flush()
    return log


def list_decision_logs(
    session: Session,
    *,
    task_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[DecisionLog], int]:
    stmt = select(DecisionLog)
    count_stmt = select(func.count(DecisionLog.id))

    if task_id:
        stmt = stmt.where(DecisionLog.task_id == task_id)
        count_stmt = count_stmt.where(DecisionLog.task_id == task_id)

    total = session.scalar(count_stmt) or 0
    items = list(session.scalars(
        stmt.order_by(DecisionLog.created_at.desc()).limit(limit).offset(offset)
    ))
    return items, total


# ---------------------------------------------------------------------------
# Post-task memory extraction (called from task_dispatch)
# ---------------------------------------------------------------------------

def record_task_outcome(
    session: Session,
    *,
    task_id: str,
    task_type: str,
    agent: str | None,
    result: dict[str, Any] | None,
    error: str | None,
    outcome: str,
) -> None:
    """
    Called after a task completes (done or failed).
    Stores a DecisionLog and, for successful tasks, a fact MemoryRecord.
    Simple rule-based — no LLM.
    """
    reasoning = ""
    if result:
        reasoning = f"Task completed with result keys: {', '.join(str(k) for k in result.keys())}"
    elif error:
        reasoning = f"Task failed: {error[:500]}"

    store_decision_log(
        session,
        task_id=task_id,
        agent=agent,
        decision=f"task_type={task_type} outcome={outcome}",
        reasoning=reasoning,
        outcome=outcome,
    )

    # Store result as fact memory if task succeeded.
    if outcome == "success" and result:
        store_memory(
            session,
            type="fact",
            key=f"task_result:{task_type}",
            content=reasoning,
            metadata={"task_id": task_id, "task_type": task_type, "result_keys": list(result.keys())},
            source_task_id=task_id,
        )

    # Store failure pattern as context memory.
    if outcome == "failure" and error:
        store_memory(
            session,
            type="context",
            key=f"task_failure:{task_type}",
            content=f"Failure pattern for {task_type}: {error[:500]}",
            metadata={"task_id": task_id, "task_type": task_type},
            source_task_id=task_id,
        )
