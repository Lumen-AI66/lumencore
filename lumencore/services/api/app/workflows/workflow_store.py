from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import PlanRunRecord, PlanStepRecord, WorkflowRunRecord
from .workflow_models import WorkflowRun, WorkflowRunStatus


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


def _to_workflow(record: WorkflowRunRecord) -> WorkflowRun:
    return WorkflowRun(
        workflow_id=record.workflow_id,
        tenant_id=record.tenant_id,
        command_id=record.command_id,
        workflow_type=record.workflow_type,
        status=record.status if isinstance(record.status, WorkflowRunStatus) else WorkflowRunStatus(record.status.value if hasattr(record.status, "value") else str(record.status)),
        linked_plan_id=record.linked_plan_id,
        input_summary=record.input_summary,
        workflow_metadata=record.workflow_metadata,
        result_summary=record.result_summary,
        error=record.error,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


class WorkflowStore:
    def create_workflow(
        self,
        session: Session,
        *,
        tenant_id: str,
        command_id: str | None,
        workflow_type: str,
        input_summary: dict[str, Any],
        workflow_metadata: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        now = datetime.now(timezone.utc)
        record = WorkflowRunRecord(
            tenant_id=tenant_id,
            command_id=command_id,
            workflow_type=workflow_type,
            status=WorkflowRunStatus.pending,
            linked_plan_id=None,
            input_summary=_truncate(input_summary or {}),
            workflow_metadata=_truncate(workflow_metadata or {}),
            result_summary=None,
            error=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        session.add(record)
        session.flush()
        return _to_workflow(record)

    def get_workflow(self, session: Session, workflow_id: str) -> WorkflowRun | None:
        record = session.get(WorkflowRunRecord, workflow_id)
        return _to_workflow(record) if record else None

    def mark_running(self, session: Session, *, workflow_id: str, linked_plan_id: str | None = None) -> WorkflowRun:
        record = session.get(WorkflowRunRecord, workflow_id)
        if record is None:
            raise ValueError(f"workflow not found: {workflow_id}")
        record.status = WorkflowRunStatus.running
        if linked_plan_id:
            record.linked_plan_id = linked_plan_id
        record.updated_at = datetime.now(timezone.utc)
        session.add(record)
        session.flush()
        return _to_workflow(record)

    def mark_completed(self, session: Session, *, workflow_id: str, linked_plan_id: str | None, result_summary: dict[str, Any]) -> WorkflowRun:
        record = session.get(WorkflowRunRecord, workflow_id)
        if record is None:
            raise ValueError(f"workflow not found: {workflow_id}")
        now = datetime.now(timezone.utc)
        record.status = WorkflowRunStatus.completed
        record.linked_plan_id = linked_plan_id
        record.result_summary = _truncate(result_summary or {})
        record.error = None
        record.updated_at = now
        record.completed_at = now
        session.add(record)
        session.flush()
        return _to_workflow(record)

    def mark_failed(self, session: Session, *, workflow_id: str, linked_plan_id: str | None, error: str, result_summary: dict[str, Any] | None = None) -> WorkflowRun:
        record = session.get(WorkflowRunRecord, workflow_id)
        if record is None:
            raise ValueError(f"workflow not found: {workflow_id}")
        now = datetime.now(timezone.utc)
        record.status = WorkflowRunStatus.failed
        record.linked_plan_id = linked_plan_id
        record.error = error
        if result_summary is not None:
            record.result_summary = _truncate(result_summary)
        record.updated_at = now
        record.completed_at = now
        session.add(record)
        session.flush()
        return _to_workflow(record)

    def get_counts(self, session: Session) -> tuple[dict[str, int], int]:
        rows = session.execute(select(WorkflowRunRecord.status, func.count()).group_by(WorkflowRunRecord.status)).all()
        counts = {status.value: 0 for status in WorkflowRunStatus}
        for status, count in rows:
            key = status.value if isinstance(status, WorkflowRunStatus) else str(status)
            counts[key] = int(count)
        return counts, sum(counts.values())

    def get_latest(self, session: Session) -> WorkflowRun | None:
        record = session.execute(
            select(WorkflowRunRecord).order_by(WorkflowRunRecord.updated_at.desc()).limit(1)
        ).scalar_one_or_none()
        return _to_workflow(record) if record else None

    def list_workflows(self, session: Session, *, limit: int = 20) -> list[WorkflowRun]:
        stmt = (
            select(WorkflowRunRecord)
            .order_by(WorkflowRunRecord.updated_at.desc())
            .limit(max(1, min(int(limit), 100)))
        )
        return [_to_workflow(record) for record in session.execute(stmt).scalars()]

    def get_linked_plan_summary(self, session: Session, *, linked_plan_id: str | None) -> dict[str, Any] | None:
        if not linked_plan_id:
            return None

        plan = session.get(PlanRunRecord, linked_plan_id)
        if plan is None:
            return None

        latest_step = session.execute(
            select(PlanStepRecord)
            .where(PlanStepRecord.plan_id == linked_plan_id)
            .order_by(PlanStepRecord.step_index.desc())
            .limit(1)
        ).scalar_one_or_none()

        return {
            "linked_plan_id": plan.plan_id,
            "plan_status": plan.status.value if hasattr(plan.status, "value") else str(plan.status),
            "total_steps": int(plan.total_steps),
            "current_step_index": int(plan.current_step_index),
            "latest_step_status": (
                latest_step.status.value if latest_step is not None and hasattr(latest_step.status, "value")
                else (str(latest_step.status) if latest_step is not None else None)
            ),
        }


_workflow_store = WorkflowStore()


def get_workflow_store() -> WorkflowStore:
    return _workflow_store

