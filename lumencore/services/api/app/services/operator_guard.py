from __future__ import annotations


def validate_operator_command(command: str) -> str:
    normalized = str(command or "").strip()
    if not normalized:
        raise ValueError("operator command cannot be empty")
    if len(normalized) > 500:
        raise ValueError("operator command exceeds 500 characters")
    return normalized
