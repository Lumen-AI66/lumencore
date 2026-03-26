from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from ...db import session_scope
from ...execution import ExecutionTaskStatus, get_execution_task_store
from ..runtime_health import check_worker
from .actions import get_recovery_request, list_recovery_requests, run_recovery_action

_EVENTS_PATH = Path('/opt/lumencore/deployment/recovery_events.json')
_EVENT_LIMIT = 200
_SUPPRESS_THRESHOLD = 3
_SUPPRESS_WINDOW = timedelta(minutes=15)

task_store = get_execution_task_store()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _copy_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _copy_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_value(item) for item in value]
    return value


def _ensure_events_file() -> None:
    _EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _EVENTS_PATH.exists():
        _write_events([])


def _write_events(events: list[dict[str, Any]]) -> None:
    _EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _EVENTS_PATH.with_suffix(_EVENTS_PATH.suffix + '.tmp')
    tmp.write_text(json.dumps(events[-_EVENT_LIMIT:], indent=2) + '\n')
    os.replace(tmp, _EVENTS_PATH)


def _enrich_action_result(action_result: dict[str, Any] | None) -> dict[str, Any]:
    enriched = _copy_value(action_result) if isinstance(action_result, dict) else {}
    request_id = enriched.get('request_id')
    request = get_recovery_request(str(request_id)) if request_id else None
    if request:
        enriched['request'] = {
            'request_id': request.get('request_id'),
            'action': request.get('action'),
            'status': request.get('status'),
            'requested_at': request.get('requested_at'),
            'executed_at': request.get('executed_at'),
            'result': request.get('result'),
            'message': request.get('message'),
            'executor': request.get('executor'),
        }
        enriched['request_status'] = request.get('status')
        enriched['request_result'] = request.get('result')
    return enriched


def list_recovery_events(limit: int = 50) -> list[dict[str, Any]]:
    _ensure_events_file()
    try:
        events = json.loads(_EVENTS_PATH.read_text())
    except Exception:
        events = []
        _write_events(events)
    safe_limit = max(1, min(int(limit), 200))
    items = list(events)[-safe_limit:][::-1]
    enriched: list[dict[str, Any]] = []
    for event in items:
        copied = _copy_value(event)
        copied['action_result'] = _enrich_action_result(copied.get('action_result'))
        enriched.append(copied)
    return enriched


def _append_event(event: dict[str, Any]) -> dict[str, Any]:
    events = list_recovery_events(limit=_EVENT_LIMIT)
    events.reverse()
    base_events = []
    for item in events:
        copied = _copy_value(item)
        if isinstance(copied.get('action_result'), dict):
            copied['action_result'].pop('request', None)
            copied['action_result'].pop('request_status', None)
            copied['action_result'].pop('request_result', None)
        base_events.append(copied)
    base_events.append(event)
    _write_events(base_events)
    return _copy_value(event)


def _probe(url: str, *, timeout: int = 3) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode()
        return {'ok': True, 'url': url, 'status_code': 200, 'body': body[:300], 'error': None}
    except URLError as exc:
        return {'ok': False, 'url': url, 'status_code': None, 'body': None, 'error': str(exc)}
    except Exception as exc:
        return {'ok': False, 'url': url, 'status_code': None, 'body': None, 'error': str(exc)}


def probe_direct_api_health() -> dict[str, Any]:
    return _probe('http://127.0.0.1:8000/health')


def probe_proxied_health() -> dict[str, Any]:
    return _probe('http://lumencore-proxy/api/system/health')


def _retryable_task_snapshot(task_id: str | None) -> dict[str, Any] | None:
    if not task_id:
        return None
    with session_scope() as session:
        task = task_store.get_task(session, task_id)
        if task is None:
            return None
        if task.status != ExecutionTaskStatus.failed:
            return {
                'task_id': task.task_id,
                'status': task.status.value,
                'retryable': False,
                'reason': 'task is not failed',
                'retries': int(task.retries),
                'max_retries': int(task.max_retries),
            }
        retryable = int(task.retries) < int(task.max_retries)
        return {
            'task_id': task.task_id,
            'status': task.status.value,
            'retryable': retryable,
            'reason': 'transient execution failure' if retryable else 'retry threshold exceeded',
            'retries': int(task.retries),
            'max_retries': int(task.max_retries),
        }


def _suppression_count(incident_key: str, action: str) -> int:
    cutoff = _now() - _SUPPRESS_WINDOW
    count = 0
    for event in list_recovery_events(limit=_EVENT_LIMIT):
        if event.get('incident_key') != incident_key or event.get('selected_action') != action:
            continue
        occurred_at = event.get('occurred_at')
        try:
            when = datetime.fromisoformat(str(occurred_at))
        except Exception:
            continue
        if when >= cutoff:
            count += 1
    return count


def _decide_action(*, proxied: dict[str, Any], direct: dict[str, Any], worker: dict[str, Any], task_snapshot: dict[str, Any] | None) -> tuple[str, str, str | None]:
    if task_snapshot and bool(task_snapshot.get('retryable')):
        return 'retry_execution_task', 'transient execution failure', str(task_snapshot.get('task_id'))
    if not proxied.get('ok') and bool(direct.get('ok')):
        return 'reload_nginx', 'proxied health failed while direct API health is ok', None
    if not proxied.get('ok') and not direct.get('ok'):
        return 'restart_api_container', 'proxied and direct API health probes both failed', None
    if not worker.get('ok'):
        return 'restart_worker_container', 'worker probe failed', None
    return 'none', 'no recovery action required', None


def evaluate_recovery(*, task_id: str | None = None, execute: bool = False, source: str = 'recovery_route') -> dict[str, Any]:
    proxied = probe_proxied_health()
    direct = probe_direct_api_health()
    worker = check_worker()
    task_snapshot = _retryable_task_snapshot(task_id)
    action, reason, effective_task_id = _decide_action(proxied=proxied, direct=direct, worker=worker, task_snapshot=task_snapshot)
    incident_key = effective_task_id and f'task:{effective_task_id}:transient_failure' or (
        'proxy_direct_mismatch' if (not proxied.get('ok') and direct.get('ok')) else
        'api_unhealthy' if (not proxied.get('ok') and not direct.get('ok')) else
        'worker_unreachable' if not worker.get('ok') else
        'none'
    )
    suppression_count = _suppression_count(incident_key, action) if action not in {'none'} else 0
    suppressed = action != 'none' and suppression_count >= _SUPPRESS_THRESHOLD
    selected_action = 'suppress' if suppressed else action
    action_result = {
        'attempted': False,
        'succeeded': False,
        'result': 'not_requested' if not execute else 'no_action',
        'message': None,
        'executed_at': None,
    }
    if selected_action not in {'none', 'suppress'} and execute:
        action_result = run_recovery_action(selected_action, task_id=effective_task_id, reason=reason)
    event = {
        'event_id': str(uuid.uuid4()),
        'occurred_at': _now_iso(),
        'source': source,
        'incident_key': incident_key,
        'selected_action': selected_action,
        'reason': reason,
        'suppressed': suppressed,
        'suppression_count': suppression_count,
        'task_id': effective_task_id,
        'probes': {
            'proxied_health': proxied,
            'direct_api_health': direct,
            'worker': worker,
            'task': task_snapshot,
        },
        'action_result': action_result,
    }
    stored = _append_event(event)
    stored['action_result'] = _enrich_action_result(stored.get('action_result'))
    return stored


def get_recovery_summary() -> dict[str, Any]:
    events = list_recovery_events(limit=_EVENT_LIMIT)
    counts_by_action: dict[str, int] = {}
    counts_by_result: dict[str, int] = {}
    requests_by_status: dict[str, int] = {}
    suppressed_total = 0
    requests = list_recovery_requests(limit=_EVENT_LIMIT)
    for request in requests:
        status = str(request.get('status') or 'unknown')
        requests_by_status[status] = int(requests_by_status.get(status, 0)) + 1
    for event in events:
        action = str(event.get('selected_action') or 'unknown')
        counts_by_action[action] = int(counts_by_action.get(action, 0)) + 1
        action_result = _enrich_action_result(event.get('action_result'))
        result = str(action_result.get('request_result') or action_result.get('result') or 'unknown')
        counts_by_result[result] = int(counts_by_result.get(result, 0)) + 1
        if bool(event.get('suppressed')):
            suppressed_total += 1
    latest = events[0] if events else None
    latest_request = requests[0] if requests else None
    return {
        'recoverable': True,
        'last_recovery_attempt': latest.get('occurred_at') if latest else None,
        'last_selected_action': latest.get('selected_action') if latest else None,
        'suppressed_total': suppressed_total,
        'counts_by_action': counts_by_action,
        'counts_by_result': counts_by_result,
        'requests_by_status': requests_by_status,
        'latest_request': latest_request,
        'latest_event': latest,
    }
