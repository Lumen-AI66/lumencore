#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, '/opt/lumencore/deployment')
import recovery_executor

LOCK_PATH = Path('/tmp/lumencore_recovery_request_runner.lock')
MAX_ATTEMPTS = 3
PROCESSING_TIMEOUT = timedelta(seconds=300)


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def recoverable_processing(request: dict) -> bool:
    if str(request.get('status')) != 'processing':
        return False
    started = parse_iso(request.get('processing_started_at'))
    if started is None:
        return True
    return started <= now() - PROCESSING_TIMEOUT


def processable_requests(requests: list[dict]) -> list[dict]:
    items = []
    for request in requests:
        status = str(request.get('status') or '')
        if status == 'pending' or recoverable_processing(request):
            items.append(request)
    items.sort(key=lambda item: str(item.get('requested_at') or ''))
    return items


def mark_processing(request: dict) -> dict:
    attempts = int(request.get('attempt_count') or 0) + 1
    request['attempt_count'] = attempts
    request['processing_started_at'] = now_iso()
    request['status'] = 'processing'
    request['result'] = 'processing'
    request['error'] = None
    request['message'] = None
    return request


def fail_request(request: dict, *, result: str, error: str) -> dict:
    timestamp = now_iso()
    request['status'] = 'failed'
    request['result'] = result
    request['error'] = error
    request['message'] = error
    request['processed_at'] = timestamp
    request['executed_at'] = timestamp
    return request


def run() -> dict:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open('w') as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'locked', 'processed': [], 'pending_remaining': None}

        requests = recovery_executor.read_requests()
        candidates = processable_requests(requests)
        processed = []

        for request in candidates:
            attempts = int(request.get('attempt_count') or 0)
            if attempts >= MAX_ATTEMPTS:
                processed.append(fail_request(request, result='max_attempts_exceeded', error='max recovery attempts exceeded'))
                continue

            request_id = str(request.get('request_id'))
            mark_processing(request)
            recovery_executor.write_requests(requests)
            result = recovery_executor.process_request(request_id)
            processed.append(result)
            requests = recovery_executor.read_requests()

        pending_remaining = sum(1 for item in recovery_executor.read_requests() if str(item.get('status')) == 'pending')
        return {'status': 'ok', 'processed': processed, 'pending_remaining': pending_remaining}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
