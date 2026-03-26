from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...db import session_scope
from ...execution import ExecutionTaskStatus, get_execution_task_store
from ..execution_control import ExecutionControlStatus, set_execution_control_state

task_store = get_execution_task_store()

_REQUESTS_PATH = Path('/opt/lumencore/deployment/recovery_requests.json')
_REQUEST_LIMIT = 200
_ALLOWED_INFRA_ACTIONS = {
    'reload_nginx',
    'restart_api_container',
    'restart_worker_container',
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_requests_file() -> None:
    _REQUESTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _REQUESTS_PATH.exists():
        _write_requests([])


def _write_requests(requests: list[dict[str, Any]]) -> None:
    _REQUESTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _REQUESTS_PATH.with_suffix(_REQUESTS_PATH.suffix + '.tmp')
    tmp.write_text(json.dumps(requests[-_REQUEST_LIMIT:], indent=2) + '\n')
    os.replace(tmp, _REQUESTS_PATH)


def list_recovery_requests(limit: int = 200) -> list[dict[str, Any]]:
    _ensure_requests_file()
    try:
        requests = json.loads(_REQUESTS_PATH.read_text())
    except Exception:
        requests = []
        _write_requests(requests)
    safe_limit = max(1, min(int(limit), _REQUEST_LIMIT))
    return list(requests)[-safe_limit:][::-1]


def _append_request(request: dict[str, Any]) -> dict[str, Any]:
    requests = list_recovery_requests(limit=_REQUEST_LIMIT)
    requests.reverse()
    requests.append(request)
    _write_requests(requests)
    return request


def get_recovery_request(request_id: str | None) -> dict[str, Any] | None:
    if not request_id:
        return None
    for request in list_recovery_requests(limit=_REQUEST_LIMIT):
        if str(request.get('request_id')) == str(request_id):
            return request
    return None


def _request_infra_action(action: str, *, task_id: str | None = None, reason: str | None = None) -> dict[str, Any]:
    normalized = str(action or '').strip().lower()
    if normalized not in _ALLOWED_INFRA_ACTIONS:
        return {
            'attempted': False,
            'succeeded': False,
            'result': 'unsupported',
            'message': 'unsupported recovery action',
            'executed_at': _now_iso(),
            'request_id': None,
            'request_status': None,
        }
    request = {
        'request_id': str(uuid.uuid4()),
        'action': normalized,
        'task_id': task_id,
        'reason': reason,
        'status': 'pending',
        'requested_at': _now_iso(),
        'executed_at': None,
        'result': 'pending',
        'message': None,
        'executor': 'host_recovery_executor',
    }
    _append_request(request)
    return {
        'attempted': True,
        'succeeded': True,
        'result': 'requested',
        'message': 'host recovery request recorded',
        'executed_at': None,
        'request_id': request['request_id'],
        'request_status': request['status'],
    }


def _run_retry_execution_task(task_id: str, *, reason: str) -> dict[str, Any]:
    with session_scope() as session:
        task = task_store.get_task(session, task_id)
        if task is None:
            return {'attempted': False, 'succeeded': False, 'result': 'missing_task', 'message': 'execution task not found', 'executed_at': _now_iso()}
        if task.status == ExecutionTaskStatus.completed:
            return {'attempted': False, 'succeeded': False, 'result': 'not_retryable', 'message': 'completed tasks cannot be retried', 'executed_at': _now_iso()}
        if task.status == ExecutionTaskStatus.running:
            return {'attempted': False, 'succeeded': False, 'result': 'not_retryable', 'message': 'running tasks cannot be retried safely', 'executed_at': _now_iso()}
        if task.status != ExecutionTaskStatus.failed:
            return {'attempted': False, 'succeeded': False, 'result': 'not_retryable', 'message': 'task is not failed', 'executed_at': _now_iso()}
        if int(task.retries) >= int(task.max_retries):
            return {'attempted': False, 'succeeded': False, 'result': 'retry_exhausted', 'message': 'task has exceeded retry threshold', 'executed_at': _now_iso()}
        set_execution_control_state(session, task_id, ExecutionControlStatus.allowed, reason=reason, source='recovery')
        task_store.requeue_task(
            session,
            task_id=task_id,
            result_summary={
                'recovery': {
                    'action': 'retry_execution_task',
                    'reason': reason,
                    'requested_at': _now_iso(),
                }
            },
        )
        return {'attempted': True, 'succeeded': True, 'result': 'executed', 'message': None, 'executed_at': _now_iso()}


def run_recovery_action(action: str, *, task_id: str | None = None, reason: str | None = None) -> dict[str, Any]:
    normalized = str(action or '').strip().lower()
    if normalized == 'retry_execution_task':
        if not task_id:
            return {'attempted': False, 'succeeded': False, 'result': 'missing_task', 'message': 'task_id is required for retry_execution_task', 'executed_at': _now_iso()}
        return _run_retry_execution_task(task_id, reason=reason or 'transient execution failure')
    return _request_infra_action(normalized, task_id=task_id, reason=reason)
