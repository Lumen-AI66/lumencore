from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PlanRunRecord, PlanRunStatus, PlanStepRecord, PlanStepStatus
from .plan_models import PlanRun, PlanStep


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


def _to_plan(record: PlanRunRecord) -> PlanRun:
    status = record.status if isinstance(record.status, PlanRunStatus) else PlanRunStatus(record.status.value if hasattr(record.status, "value") else str(record.status))
    return PlanRun(
        plan_id=record.plan_id,
        tenant_id=record.tenant_id,
        command_id=record.command_id,
        plan_type=record.plan_type,
        status=status,
        total_steps=int(record.total_steps),
        current_step_index=int(record.current_step_index),
        error=record.error,
        result_summary=record.result_summary,
        plan_metadata=record.plan_metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


def _to_step(record: PlanStepRecord) -> PlanStep:
    status = record.status if isinstance(record.status, PlanStepStatus) else PlanStepStatus(record.status.value if hasattr(record.status, "value") else str(record.status))
    return PlanStep(
        step_id=record.step_id,
        plan_id=record.plan_id,
        step_index=int(record.step_index),
        step_type=record.step_type,
        agent_type=record.agent_type,
        title=record.title,
        payload_json=record.payload_json or {},
        status=status,
        execution_task_id=record.execution_task_id,
        error=record.error,
        result_summary=record.result_summary,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


class PlanStore:
    def create_plan(
        self,
        session: Session,
        *,
        tenant_id: str,
        command_id: str | None,
        plan_type: str,
        total_steps: int,
        plan_metadata: dict[str, Any] | None = None,
    ) -> PlanRun:
        now = datetime.now(timezone.utc)
        record = PlanRunRecord(
            plan_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            command_id=command_id,
            plan_type=plan_type,
            status=PlanRunStatus.pending,
            total_steps=max(0, min(int(total_steps), 5)),
            current_step_index=0,
            error=None,
            result_summary=None,
            plan_metadata=_truncate(plan_metadata or {}),
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        session.add(record)
        session.flush()
        return _to_plan(record)

    def get_plan(self, session: Session, plan_id: str) -> PlanRun | None:
        record = session.get(PlanRunRecord, plan_id)
        return _to_plan(record) if record else None

    def list_plans(self, session: Session, *, limit: int = 20) -> list[PlanRun]:
        stmt = (
            select(PlanRunRecord)
            .order_by(PlanRunRecord.updated_at.desc())
            .limit(max(1, min(int(limit), 100)))
        )
        return [_to_plan(record) for record in session.execute(stmt).scalars()]

    def create_step(
        self,
        session: Session,
        *,
        plan_id: str,
        step_index: int,
        step_type: str,
        agent_type: str,
        title: str,
        payload_json: dict[str, Any],
    ) -> PlanStep:
        now = datetime.now(timezone.utc)
        record = PlanStepRecord(
            step_id=str(uuid.uuid4()),
            plan_id=plan_id,
            step_index=int(step_index),
            step_type=step_type,
            agent_type=agent_type,
            title=title,
            payload_json=_truncate(payload_json or {}),
            status=PlanStepStatus.pending,
            execution_task_id=None,
            error=None,
            result_summary=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        session.add(record)
        session.flush()
        return _to_step(record)

    def list_steps(self, session: Session, plan_id: str) -> list[PlanStep]:
        stmt = select(PlanStepRecord).where(PlanStepRecord.plan_id == plan_id).order_by(PlanStepRecord.step_index.asc())
        return [_to_step(record) for record in session.execute(stmt).scalars()]

    def get_step(self, session: Session, step_id: str) -> PlanStep | None:
        record = session.get(PlanStepRecord, step_id)
        return _to_step(record) if record else None

    def get_next_pending_step(self, session: Session, plan_id: str) -> PlanStep | None:
        stmt = (
            select(PlanStepRecord)
            .where(PlanStepRecord.plan_id == plan_id, PlanStepRecord.status == PlanStepStatus.pending)
            .order_by(PlanStepRecord.step_index.asc())
            .limit(1)
        )
        record = session.execute(stmt).scalar_one_or_none()
        return _to_step(record) if record else None

    def mark_plan_running(self, session: Session, *, plan_id: str, current_step_index: int) -> PlanRun:
        record = session.get(PlanRunRecord, plan_id)
        if record is None:
            raise ValueError(f"plan not found: {plan_id}")
        record.status = PlanRunStatus.running
        record.current_step_index = int(current_step_index)
        record.updated_at = datetime.now(timezone.utc)
        session.add(record)
        session.flush()
        return _to_plan(record)

    def mark_plan_completed(self, session: Session, *, plan_id: str, result_summary: dict[str, Any] | None = None) -> PlanRun:
        record = session.get(PlanRunRecord, plan_id)
        if record is None:
            raise ValueError(f"plan not found: {plan_id}")
        now = datetime.now(timezone.utc)
        record.status = PlanRunStatus.completed
        record.current_step_index = int(record.total_steps)
        record.error = None
        record.result_summary = _truncate(result_summary or {})
        record.updated_at = now
        record.completed_at = now
        session.add(record)
        session.flush()
        return _to_plan(record)

    def mark_plan_failed(self, session: Session, *, plan_id: str, current_step_index: int, error: str, result_summary: dict[str, Any] | None = None) -> PlanRun:
        record = session.get(PlanRunRecord, plan_id)
        if record is None:
            raise ValueError(f"plan not found: {plan_id}")
        now = datetime.now(timezone.utc)
        record.status = PlanRunStatus.failed
        record.current_step_index = int(current_step_index)
        record.error = error
        if result_summary is not None:
            record.result_summary = _truncate(result_summary)
        record.updated_at = now
        record.completed_at = now
        session.add(record)
        session.flush()
        return _to_plan(record)

    def mark_step_queued(self, session: Session, *, step_id: str, execution_task_id: str) -> PlanStep:
        record = session.get(PlanStepRecord, step_id)
        if record is None:
            raise ValueError(f"plan step not found: {step_id}")
        record.status = PlanStepStatus.queued
        record.execution_task_id = execution_task_id
        record.updated_at = datetime.now(timezone.utc)
        session.add(record)
        session.flush()
        return _to_step(record)

    def mark_step_running(self, session: Session, *, step_id: str) -> PlanStep:
        record = session.get(PlanStepRecord, step_id)
        if record is None:
            raise ValueError(f"plan step not found: {step_id}")
        record.status = PlanStepStatus.running
        record.updated_at = datetime.now(timezone.utc)
        session.add(record)
        session.flush()
        return _to_step(record)

    def mark_step_completed(self, session: Session, *, step_id: str, result_summary: dict[str, Any] | None = None) -> PlanStep:
        record = session.get(PlanStepRecord, step_id)
        if record is None:
            raise ValueError(f"plan step not found: {step_id}")
        now = datetime.now(timezone.utc)
        record.status = PlanStepStatus.completed
        record.error = None
        record.result_summary = _truncate(result_summary or {})
        record.updated_at = now
        record.completed_at = now
        session.add(record)
        session.flush()
        return _to_step(record)

    def mark_step_failed(self, session: Session, *, step_id: str, error: str, result_summary: dict[str, Any] | None = None) -> PlanStep:
        record = session.get(PlanStepRecord, step_id)
        if record is None:
            raise ValueError(f"plan step not found: {step_id}")
        now = datetime.now(timezone.utc)
        record.status = PlanStepStatus.failed
        record.error = error
        if result_summary is not None:
            record.result_summary = _truncate(result_summary)
        record.updated_at = now
        record.completed_at = now
        session.add(record)
        session.flush()
        return _to_step(record)


_plan_store = PlanStore()


def get_plan_store() -> PlanStore:
    return _plan_store
