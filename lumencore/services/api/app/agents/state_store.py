from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AgentRunStateRecord, AgentStateEventRecord, AgentTaskStateRecord
from .state_models import AgentRunState, AgentRuntimeStateStatus, AgentStateEvent, TaskState


def _truncate(value: Any, limit: int = 240) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else f"{value[:limit]}..."
    if isinstance(value, list):
        return [_truncate(item, limit=limit) for item in value[:10]]
    if isinstance(value, dict):
        summary: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 20:
                summary["truncated"] = True
                break
            summary[str(key)] = _truncate(item, limit=limit)
        return summary
    return value


def _to_run_state(record: AgentRunStateRecord) -> AgentRunState:
    return AgentRunState(
        run_id=record.run_id,
        tenant_id=record.tenant_id,
        agent_id=str(record.agent_id) if record.agent_id else None,
        agent_type=record.agent_type,
        command_id=record.command_id,
        task_id=record.task_id,
        status=AgentRuntimeStateStatus(str(record.status)),
        current_step=record.current_step,
        last_decision=record.last_decision,
        retry_count=int(record.retry_count),
        started_at=record.started_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
        last_error=record.last_error,
    )


def _to_task_state(record: AgentTaskStateRecord) -> TaskState:
    return TaskState(
        task_id=record.task_id,
        run_id=record.run_id,
        tenant_id=record.tenant_id,
        task_type=record.task_type,
        status=AgentRuntimeStateStatus(str(record.status)),
        input_summary=record.input_summary,
        output_summary=record.output_summary,
        failure_metadata=record.failure_metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


def _to_event(record: AgentStateEventRecord) -> AgentStateEvent:
    return AgentStateEvent(
        id=record.id,
        run_id=record.run_id,
        tenant_id=record.tenant_id,
        task_id=record.task_id,
        event_type=record.event_type,
        step_name=record.step_name,
        message=record.message,
        payload_summary=record.payload_summary,
        severity=record.severity,
        created_at=record.created_at,
    )


class AgentStateStore:
    def create_run(
        self,
        session: Session,
        *,
        run_id: str,
        tenant_id: str,
        agent_id: str | None,
        agent_type: str,
        command_id: str | None,
        task_id: str,
        status: AgentRuntimeStateStatus,
        current_step: str | None = None,
        last_decision: dict[str, Any] | None = None,
        retry_count: int = 0,
        last_error: str | None = None,
    ) -> AgentRunState:
        now = datetime.now(timezone.utc)
        record = AgentRunStateRecord(
            run_id=run_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            agent_type=agent_type,
            command_id=command_id,
            task_id=task_id,
            status=status.value,
            current_step=current_step,
            last_decision=_truncate(last_decision or {}),
            retry_count=retry_count,
            started_at=now if status == AgentRuntimeStateStatus.running else None,
            updated_at=now,
            completed_at=now if status in {AgentRuntimeStateStatus.completed, AgentRuntimeStateStatus.failed, AgentRuntimeStateStatus.cancelled} else None,
            last_error=last_error,
        )
        session.add(record)
        session.flush()
        return _to_run_state(record)

    def get_run(self, session: Session, run_id: str) -> AgentRunState | None:
        record = session.get(AgentRunStateRecord, run_id)
        return _to_run_state(record) if record else None

    def update_run_status(
        self,
        session: Session,
        *,
        run_id: str,
        status: AgentRuntimeStateStatus,
        last_decision: dict[str, Any] | None = None,
        last_error: str | None = None,
    ) -> AgentRunState:
        record = session.get(AgentRunStateRecord, run_id)
        if record is None:
            raise ValueError(f"agent run state not found: {run_id}")
        now = datetime.now(timezone.utc)
        record.status = status.value
        record.updated_at = now
        record.last_error = last_error
        if last_decision is not None:
            record.last_decision = _truncate(last_decision)
        if record.started_at is None and status == AgentRuntimeStateStatus.running:
            record.started_at = now
        if status in {AgentRuntimeStateStatus.completed, AgentRuntimeStateStatus.failed, AgentRuntimeStateStatus.cancelled}:
            record.completed_at = now
        session.add(record)
        session.flush()
        return _to_run_state(record)

    def update_current_step(
        self,
        session: Session,
        *,
        run_id: str,
        current_step: str | None,
        last_decision: dict[str, Any] | None = None,
    ) -> AgentRunState:
        record = session.get(AgentRunStateRecord, run_id)
        if record is None:
            raise ValueError(f"agent run state not found: {run_id}")
        record.current_step = current_step
        record.updated_at = datetime.now(timezone.utc)
        if last_decision is not None:
            record.last_decision = _truncate(last_decision)
        session.add(record)
        session.flush()
        return _to_run_state(record)

    def append_event(
        self,
        session: Session,
        *,
        run_id: str,
        tenant_id: str,
        task_id: str | None,
        event_type: str,
        message: str,
        step_name: str | None = None,
        payload_summary: dict[str, Any] | None = None,
        severity: str = "info",
    ) -> AgentStateEvent:
        record = AgentStateEventRecord(
            id=str(uuid.uuid4()),
            run_id=run_id,
            tenant_id=tenant_id,
            task_id=task_id,
            event_type=event_type,
            step_name=step_name,
            message=message,
            payload_summary=_truncate(payload_summary or {}),
            severity=severity,
            created_at=datetime.now(timezone.utc),
        )
        session.add(record)
        session.flush()
        return _to_event(record)

    def create_task(
        self,
        session: Session,
        *,
        task_id: str,
        run_id: str,
        tenant_id: str,
        task_type: str,
        status: AgentRuntimeStateStatus,
        input_summary: dict[str, Any] | None = None,
    ) -> TaskState:
        now = datetime.now(timezone.utc)
        record = AgentTaskStateRecord(
            task_id=task_id,
            run_id=run_id,
            tenant_id=tenant_id,
            task_type=task_type,
            status=status.value,
            input_summary=_truncate(input_summary or {}),
            output_summary=None,
            failure_metadata=None,
            created_at=now,
            updated_at=now,
            completed_at=now if status in {AgentRuntimeStateStatus.completed, AgentRuntimeStateStatus.failed, AgentRuntimeStateStatus.cancelled} else None,
        )
        session.add(record)
        session.flush()
        return _to_task_state(record)

    def update_task(
        self,
        session: Session,
        *,
        task_id: str,
        status: AgentRuntimeStateStatus,
        output_summary: dict[str, Any] | None = None,
        failure_metadata: dict[str, Any] | None = None,
    ) -> TaskState:
        record = session.get(AgentTaskStateRecord, task_id)
        if record is None:
            raise ValueError(f"agent task state not found: {task_id}")
        now = datetime.now(timezone.utc)
        record.status = status.value
        record.updated_at = now
        if output_summary is not None:
            record.output_summary = _truncate(output_summary)
        if failure_metadata is not None:
            record.failure_metadata = _truncate(failure_metadata)
        if status in {AgentRuntimeStateStatus.completed, AgentRuntimeStateStatus.failed, AgentRuntimeStateStatus.cancelled}:
            record.completed_at = now
        session.add(record)
        session.flush()
        return _to_task_state(record)

    def list_run_events(self, session: Session, run_id: str, limit: int = 100) -> list[AgentStateEvent]:
        safe_limit = max(1, min(int(limit), 500))
        rows = session.execute(
            select(AgentStateEventRecord)
            .where(AgentStateEventRecord.run_id == run_id)
            .order_by(AgentStateEventRecord.created_at.asc())
            .limit(safe_limit)
        ).scalars()
        return [_to_event(record) for record in rows]

    def get_latest_checkpoint(self, session: Session, run_id: str) -> dict[str, Any] | None:
        run_state = self.get_run(session, run_id)
        if run_state is None:
            return None
        latest_event = session.execute(
            select(AgentStateEventRecord)
            .where(AgentStateEventRecord.run_id == run_id)
            .order_by(AgentStateEventRecord.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return {
            "run": run_state.model_dump(mode="json"),
            "latest_event": _to_event(latest_event).model_dump(mode="json") if latest_event else None,
        }


_state_store = AgentStateStore()


def get_agent_state_store() -> AgentStateStore:
    return _state_store
