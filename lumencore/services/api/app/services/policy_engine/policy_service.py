from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import ExecutionTaskRecord
from .policy_models import ExecutionPolicyDecision

_POLICY_KEY = "execution_policy"
_DANGEROUS_TERMS = ("delete", "shutdown", "drop")


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


def _payload_task(execution_task) -> dict[str, Any]:
    payload = _copy_dict(getattr(execution_task, 'payload_json', None))
    return _copy_dict(payload.get('task') or payload)


def _infer_connector_name(command_run, execution_task) -> str | None:
    task = _payload_task(execution_task)
    explicit = str(task.get('connector_name') or '').strip().lower()
    if explicit:
        return explicit
    tool_name = str(task.get('tool_name') or '').strip().lower()
    if tool_name == 'tool.openai.complete':
        return 'openai'
    model = str(task.get('model') or '').strip()
    if model:
        return 'openai'
    agent_type = str(getattr(execution_task, 'agent_type', None) or task.get('agent_type') or '').strip().lower()
    if agent_type in {'research', 'analysis'}:
        return 'openai'
    if agent_type == 'automation':
        return 'system'
    summary = _copy_dict(getattr(command_run, 'result_summary', None))
    agent_result = _copy_dict(summary.get('agent_result') or {})
    connector_name = str(agent_result.get('provider') or summary.get('connector_name') or '').strip().lower()
    return connector_name or None


def _command_text(command_run) -> str:
    return str(getattr(command_run, 'command_text', '') or '').strip().lower()


def _decision_dict(decision: ExecutionPolicyDecision) -> dict[str, Any]:
    return {
        'allowed': bool(decision.allowed),
        'reason': decision.reason,
        'risk_level': decision.risk_level,
        'requires_approval': bool(decision.requires_approval),
        'evaluated_at': decision.evaluated_at.isoformat(),
    }


def evaluate_execution_policy(command_run, execution_task) -> ExecutionPolicyDecision:
    now = datetime.now(timezone.utc)
    allowed = True
    reason: str | None = None
    risk_level = 'low'
    requires_approval = False

    connector_name = _infer_connector_name(command_run, execution_task)
    task_type = str(getattr(execution_task, 'task_type', '') or '').strip().lower()
    command_text = _command_text(command_run)

    if connector_name == 'openai':
        risk_level = 'medium'

    if task_type == 'automation':
        risk_level = 'high'

    if any(term in command_text for term in _DANGEROUS_TERMS):
        allowed = False
        reason = 'dangerous command'

    if risk_level == 'high':
        requires_approval = True
        allowed = False
        if reason is None:
            reason = 'approval required'

    return ExecutionPolicyDecision(
        allowed=allowed,
        reason=reason,
        risk_level=risk_level,
        requires_approval=requires_approval,
        evaluated_at=now,
    )


def persist_policy_state(session: Session, task_id: str, decision: ExecutionPolicyDecision) -> dict[str, Any]:
    record = _record(session, task_id)
    metadata = _copy_dict(record.task_metadata)
    metadata[_POLICY_KEY] = _decision_dict(decision)
    record.task_metadata = metadata
    record.updated_at = datetime.now(timezone.utc)
    session.add(record)
    session.flush()
    return _copy_dict(metadata.get(_POLICY_KEY))


def is_policy_allowed(session: Session, task_id: str) -> tuple[bool, str | None]:
    record = _record(session, task_id)
    metadata = _copy_dict(record.task_metadata)
    payload = _copy_dict(metadata.get(_POLICY_KEY) or {})
    if not payload:
        return True, None
    allowed = bool(payload.get('allowed', True))
    reason = payload.get('reason')
    return allowed, reason


def get_execution_policy_snapshot(session: Session) -> dict[str, Any]:
    rows = list(session.execute(select(ExecutionTaskRecord).order_by(ExecutionTaskRecord.updated_at.desc())).scalars())
    counts_by_risk_level = {'low': 0, 'medium': 0, 'high': 0}
    blocked_tasks: list[dict[str, Any]] = []
    approval_required_tasks: list[dict[str, Any]] = []

    for record in rows:
        payload = _copy_dict(_copy_dict(record.task_metadata).get(_POLICY_KEY) or {})
        if not payload:
            continue
        risk = str(payload.get('risk_level') or 'low').strip().lower()
        if risk not in counts_by_risk_level:
            counts_by_risk_level[risk] = 0
        counts_by_risk_level[risk] = int(counts_by_risk_level.get(risk, 0)) + 1

        item = {
            'task_id': record.task_id,
            'command_id': record.command_id,
            'status': str(getattr(record.status, 'value', record.status)),
            'risk_level': risk,
            'reason': payload.get('reason'),
            'requires_approval': bool(payload.get('requires_approval', False)),
            'allowed': bool(payload.get('allowed', True)),
            'evaluated_at': payload.get('evaluated_at'),
        }
        if not item['allowed']:
            blocked_tasks.append(item)
        if item['requires_approval']:
            approval_required_tasks.append(item)

    return {
        'counts_by_risk_level': counts_by_risk_level,
        'blocked_tasks': blocked_tasks[:20],
        'approval_required_tasks': approval_required_tasks[:20],
        'total_evaluated_tasks': int(sum(counts_by_risk_level.values())),
    }
