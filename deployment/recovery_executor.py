#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REQUESTS_PATH = Path('/opt/lumencore/deployment/recovery_requests.json')
REQUEST_LIMIT = 200
ALLOWED_ACTIONS = {
    'reload_nginx': ['docker', 'exec', 'lumencore-proxy', 'nginx', '-s', 'reload'],
    'restart_api_container': ['docker', 'restart', 'lumencore-api'],
    'restart_worker_container': ['docker', 'restart', 'lumencore-worker'],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_requests_file() -> None:
    REQUESTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not REQUESTS_PATH.exists():
        write_requests([])


def read_requests() -> list[dict]:
    ensure_requests_file()
    try:
        data = json.loads(REQUESTS_PATH.read_text())
    except Exception:
        data = []
        write_requests(data)
    return list(data)


def write_requests(requests: list[dict]) -> None:
    REQUESTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = REQUESTS_PATH.with_suffix(REQUESTS_PATH.suffix + '.tmp')
    tmp.write_text(json.dumps(requests[-REQUEST_LIMIT:], indent=2) + '\n')
    os.replace(tmp, REQUESTS_PATH)


def process_pending() -> dict:
    requests = read_requests()
    processed = []
    for request in requests:
        if str(request.get('status')) != 'pending':
            continue
        action = str(request.get('action') or '')
        command = ALLOWED_ACTIONS.get(action)
        request['executed_at'] = now_iso()
        if not command:
            request['status'] = 'failed'
            request['result'] = 'unsupported'
            request['message'] = 'unsupported recovery action'
            processed.append(request)
            continue
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        request['status'] = 'completed' if completed.returncode == 0 else 'failed'
        request['result'] = 'executed' if completed.returncode == 0 else 'failed'
        request['message'] = (completed.stderr or completed.stdout or '').strip() or None
        processed.append(request)
    write_requests(requests)
    return {'processed': processed, 'pending_remaining': sum(1 for item in requests if str(item.get('status')) == 'pending')}


if __name__ == '__main__':
    print(json.dumps(process_pending(), indent=2))
