from __future__ import annotations

ALLOWED_SCOPES = {"system", "projects", "agents"}


def validate_scope(scope: str) -> str:
    normalized = (scope or "").strip().lower()
    if normalized not in ALLOWED_SCOPES:
        raise ValueError(f"invalid secret scope: {scope}")
    return normalized
