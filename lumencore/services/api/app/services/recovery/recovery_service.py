from __future__ import annotations

from .control import evaluate_recovery, get_recovery_summary


def check_system_recoverable() -> dict:
    return get_recovery_summary()


def trigger_safe_recovery() -> dict:
    return evaluate_recovery(execute=True, source='recovery_service')


def get_recovery_status() -> dict:
    return get_recovery_summary()
