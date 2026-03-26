from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import ExecutionTaskRecord
from .control_models import ExecutionControlState, ExecutionControlStatus

_CONTROL_KEY = "execution_control"
_CONTROL_HOLD_SECONDS = 3600


def _copy_dict(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    copied: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            copied[str(key)] = _copy_dict(item)
        elif isinstance(item, list):
            copied[str(key)] = list(item)
        else:
            copied[str(key)] = item
    return copied


def _record(session: Session, task_id: str) -> ExecutionTaskRecord:
    record = session.get(ExecutionTaskRecord, task_id)
    if record is None:
        raise ValueError(f"execution task not found: {task_id}")
    return record


def _state_dict(state: ExecutionControlState) -> dict[str, Any]:
    return {
        "task_id": state.task_id,
        "control_status": state.control_status.value,
        "control_reason": state.control_reason,
        "control_source": state.control_source,
        "updated_at": state.updated_at.isoformat(),
    }


def _state_from_record(record: ExecutionTaskRecord) -> ExecutionControlState:
    metadata = _copy_dict(record.task_metadata)
    payload = _copy_dict(metadata.get(_CONTROL_KEY) or {})
    raw_updated_at = payload.get("updated_at")
    updated_at = record.updated_at or datetime.now(timezone.utc)
    if isinstance(raw_updated_at, str):
        try:
            updated_at = datetime.fromisoformat(raw_updated_at)
        except ValueError:
            updated_at = record.updated_at or datetime.now(timezone.utc)
    raw_status = str(payload.get("control_status") or ExecutionControlStatus.allowed.value).strip().lower()
    try:
        control_status = ExecutionControlStatus(raw_status)
    except ValueError:
        control_status = ExecutionControlStatus.allowed
    control_reason = payload.get("control_reason")
    control_source = str(payload.get("control_source") or "system")
    return ExecutionControlState(
        task_id=record.task_id,
        control_status=control_status,
        control_reason=control_reason,
        control_source=control_source,
        updated_at=updated_at,
    )


def _apply_control_availability(record: ExecutionTaskRecord, control_status: ExecutionControlStatus) -> None:
    now = datetime.now(timezone.utc)
    current_status = str(getattr(record.status, "value", record.status or "")).strip().lower()
    if current_status not in {"pending", "retrying"}:
        return
    if control_status in {ExecutionControlStatus.paused, ExecutionControlStatus.blocked}:
        record.available_at = max(record.available_at or now, now + timedelta(seconds=_CONTROL_HOLD_SECONDS))
    elif control_status == ExecutionControlStatus.allowed:
        record.available_at = now


def get_execution_control_state(session: Session, task_id: str) -> ExecutionControlState:
    return _state_from_record(_record(session, task_id))


def set_execution_control_state(
    session: Session,
    task_id: str,
    control_status,
    reason: str | None = None,
    source: str = "operator",
) -> ExecutionControlState:
    record = _record(session, task_id)
    existing = _state_from_record(record)
    normalized_status = control_status if isinstance(control_status, ExecutionControlStatus) else ExecutionControlStatus(str(control_status).strip().lower())
    now = datetime.now(timezone.utc)
    state = ExecutionControlState(
        task_id=record.task_id,
        control_status=normalized_status,
        control_reason=reason if reason is not None else existing.control_reason,
        control_source=str(source or existing.control_source or "operator"),
        updated_at=now,
    )
    metadata = _copy_dict(record.task_metadata)
    metadata[_CONTROL_KEY] = _state_dict(state)
    record.task_metadata = metadata
    _apply_control_availability(record, normalized_status)
    record.updated_at = now
    session.add(record)
    session.flush()
    return state


def is_execution_allowed(session: Session, task_id: str) -> tuple[bool, str | None]:
    state = get_execution_control_state(session, task_id)
    if state.control_status == ExecutionControlStatus.allowed:
        return True, None
    return False, state.control_status.value


def get_execution_control_snapshot(session: Session) -> dict[str, Any]:
    rows = list(session.execute(select(ExecutionTaskRecord).order_by(ExecutionTaskRecord.updated_at.desc())).scalars())
    counts = {status.value: 0 for status in ExecutionControlStatus}
    latest_controlled: dict[str, Any] | None = None

    for record in rows:
        state = _state_from_record(record)
        counts[state.control_status.value] = int(counts.get(state.control_status.value, 0)) + 1
        metadata = _copy_dict(record.task_metadata)
        has_explicit_control = _CONTROL_KEY in metadata
        if latest_controlled is None and has_explicit_control:
            latest_controlled = _state_dict(state)

    return {
        "counts_by_status": counts,
        "total_tasks": len(rows),
        "latest_controlled_task": latest_controlled,
    }
