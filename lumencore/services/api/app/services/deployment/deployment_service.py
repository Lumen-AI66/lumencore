from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_STATE_PATH = Path("/opt/lumencore/deployment/deployment_state.json")
_UNSET = object()
_DEFAULT_STATE = {
    "last_restart_at": None,
    "last_deploy_at": None,
    "last_known_good_release": None,
    "restart_count": 0,
    "failed_restarts": 0,
}


def _normalized_state(raw: dict[str, Any] | None) -> dict[str, Any]:
    state = dict(_DEFAULT_STATE)
    if isinstance(raw, dict):
        state.update({key: raw.get(key, value) for key, value in _DEFAULT_STATE.items()})
    state["restart_count"] = int(state.get("restart_count") or 0)
    state["failed_restarts"] = int(state.get("failed_restarts") or 0)
    return state


def _ensure_state_file() -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _STATE_PATH.exists():
        _write_state(_DEFAULT_STATE)


def _write_state(state: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalized_state(state)
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _STATE_PATH.with_suffix(_STATE_PATH.suffix + ".tmp")
    tmp_path.write_text(json.dumps(normalized, indent=2) + "\n")
    os.replace(tmp_path, _STATE_PATH)
    return normalized


def get_deployment_state() -> dict[str, Any]:
    _ensure_state_file()
    try:
        raw = json.loads(_STATE_PATH.read_text())
    except Exception:
        raw = dict(_DEFAULT_STATE)
        _write_state(raw)
    return _normalized_state(raw)


def update_deployment_state(
    *,
    last_restart_at: str | None | object = _UNSET,
    last_deploy_at: str | None | object = _UNSET,
    last_known_good_release: str | None | object = _UNSET,
    restart_count: int | object = _UNSET,
    failed_restarts: int | object = _UNSET,
) -> dict[str, Any]:
    state = get_deployment_state()
    if last_restart_at is not _UNSET:
        state["last_restart_at"] = last_restart_at
    if last_deploy_at is not _UNSET:
        state["last_deploy_at"] = last_deploy_at
    if last_known_good_release is not _UNSET:
        state["last_known_good_release"] = last_known_good_release
    if restart_count is not _UNSET:
        state["restart_count"] = int(restart_count)
    if failed_restarts is not _UNSET:
        state["failed_restarts"] = int(failed_restarts)
    return _write_state(state)


def record_restart() -> dict[str, Any]:
    state = get_deployment_state()
    return update_deployment_state(
        last_restart_at=datetime.now(timezone.utc).isoformat(),
        restart_count=int(state.get("restart_count", 0)) + 1,
    )


def record_deploy(release_id: str | None = None) -> dict[str, Any]:
    return update_deployment_state(
        last_deploy_at=datetime.now(timezone.utc).isoformat(),
        last_known_good_release=release_id,
    )


def mark_failed_restart() -> dict[str, Any]:
    state = get_deployment_state()
    return update_deployment_state(
        failed_restarts=int(state.get("failed_restarts", 0)) + 1,
    )
