from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ExecutionTaskRecord, ExecutionTaskStatus
from .task_models import ExecutionTask


def _truncate(value: Any, limit: int = 400) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else f"{value[:limit]}..."
    if isinstance(value, list):
        return [_truncate(item, limit=limit) for item in value[:20]]
    if isinstance(value, dict):
        summary: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 25:
                summary["truncated"] = True
                break
            summary[str(key)] = _truncate(item, limit=limit)
        return summary
    return value


def _to_task(record: ExecutionTaskRecord) -> ExecutionTask:
    return ExecutionTask(
        task_id=record.task_id,
        tenant_id=record.tenant_id,
        command_id=record.command_id,
        agent_id=str(record.agent_id) if record.agent_id else None,
        agent_type=record.agent_type,
        task_type=record.task_type,
        payload_json=record.payload_json or {},
        status=record.status if isinstance(record.status, ExecutionTaskStatus) else ExecutionTaskStatus(record.status.value if hasattr(record.status, "value") else str(record.status)),
        priority=int(record.priority),
        retries=int(record.retries),
        max_retries=int(record.max_retries),
        available_at=record.available_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        error=record.error,
        result_summary=record.result_summary,
        task_metadata=record.task_metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class ExecutionTaskStore:
    def create_task(
        self,
        session: Session,
        *,
        tenant_id: str,
        agent_id: str | None,
        agent_type: str,
        task_type: str,
        payload_json: dict[str, Any],
        command_id: str | None = None,
        priority: int = 100,
        max_retries: int = 0,
        task_metadata: dict[str, Any] | None = None,
    ) -> ExecutionTask:
        now = datetime.now(timezone.utc)
        record = ExecutionTaskRecord(
            tenant_id=tenant_id,
            command_id=command_id,
            agent_id=agent_id,
            agent_type=agent_type,
            task_type=task_type,
            payload_json=_truncate(payload_json or {}),
            status=ExecutionTaskStatus.pending,
            priority=max(0, int(priority)),
            retries=0,
            max_retries=max(0, int(max_retries)),
            available_at=now,
            started_at=None,
            finished_at=None,
            error=None,
            result_summary=None,
            task_metadata=_truncate(task_metadata or {}),
            created_at=now,
            updated_at=now,
        )
        session.add(record)
        session.flush()
        return _to_task(record)

    def get_task(self, session: Session, task_id: str) -> ExecutionTask | None:
        record = session.get(ExecutionTaskRecord, task_id)
        return _to_task(record) if record else None

    def list_ready_tasks(self, session: Session, *, limit: int = 10, task_id: str | None = None) -> list[ExecutionTask]:
        safe_limit = max(1, min(int(limit), 100))
        now = datetime.now(timezone.utc)
        stmt = select(ExecutionTaskRecord).where(ExecutionTaskRecord.available_at <= now)
        if task_id:
            stmt = stmt.where(ExecutionTaskRecord.task_id == task_id)
        else:
            stmt = stmt.where(ExecutionTaskRecord.status.in_([ExecutionTaskStatus.pending, ExecutionTaskStatus.retrying]))
        stmt = stmt.order_by(ExecutionTaskRecord.priority.asc(), ExecutionTaskRecord.created_at.asc()).limit(safe_limit)
        return [_to_task(record) for record in session.execute(stmt).scalars()]

    def mark_running(self, session: Session, *, task_id: str) -> ExecutionTask:
        record = session.get(ExecutionTaskRecord, task_id)
        if record is None:
            raise ValueError(f"execution task not found: {task_id}")
        now = datetime.now(timezone.utc)
        record.status = ExecutionTaskStatus.running
        record.started_at = record.started_at or now
        record.updated_at = now
        session.add(record)
        session.flush()
        return _to_task(record)

    def mark_completed(self, session: Session, *, task_id: str, result_summary: dict[str, Any] | None = None) -> ExecutionTask:
        record = session.get(ExecutionTaskRecord, task_id)
        if record is None:
            raise ValueError(f"execution task not found: {task_id}")
        now = datetime.now(timezone.utc)
        record.status = ExecutionTaskStatus.completed
        record.result_summary = _truncate(result_summary or {})
        record.error = None
        record.finished_at = now
        record.updated_at = now
        session.add(record)
        session.flush()
        return _to_task(record)

    def mark_retrying(
        self,
        session: Session,
        *,
        task_id: str,
        next_available_at: datetime,
        error: str | None = None,
        result_summary: dict[str, Any] | None = None,
    ) -> ExecutionTask:
        record = session.get(ExecutionTaskRecord, task_id)
        if record is None:
            raise ValueError(f"execution task not found: {task_id}")
        now = datetime.now(timezone.utc)
        record.status = ExecutionTaskStatus.retrying
        record.retries = int(record.retries) + 1
        record.available_at = next_available_at
        record.error = error
        if result_summary is not None:
            record.result_summary = _truncate(result_summary)
        record.updated_at = now
        session.add(record)
        session.flush()
        return _to_task(record)

    def mark_failed(
        self,
        session: Session,
        *,
        task_id: str,
        error: str | None = None,
        result_summary: dict[str, Any] | None = None,
    ) -> ExecutionTask:
        record = session.get(ExecutionTaskRecord, task_id)
        if record is None:
            raise ValueError(f"execution task not found: {task_id}")
        now = datetime.now(timezone.utc)
        record.status = ExecutionTaskStatus.failed
        record.error = error
        if result_summary is not None:
            record.result_summary = _truncate(result_summary)
        record.finished_at = now
        record.updated_at = now
        session.add(record)
        session.flush()
        return _to_task(record)

    def list_recent_tasks(self, session: Session, limit: int = 10) -> list[ExecutionTask]:
        safe_limit = max(1, min(int(limit), 100))
        stmt = select(ExecutionTaskRecord).order_by(ExecutionTaskRecord.created_at.desc()).limit(safe_limit)
        return [_to_task(record) for record in session.execute(stmt).scalars()]


_task_store = ExecutionTaskStore()


def get_execution_task_store() -> ExecutionTaskStore:
    return _task_store

