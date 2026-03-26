from __future__ import annotations
from datetime import datetime, timezone

_recovery_state = {
    "recoverable": True,
    "last_recovery_attempt": None,
}

def check_system_recoverable() -> dict:
    return _recovery_state

def trigger_safe_recovery() -> dict:
    _recovery_state["last_recovery_attempt"] = datetime.now(timezone.utc).isoformat()
    return _recovery_state

def get_recovery_status() -> dict:
    return _recovery_state
