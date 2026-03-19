from __future__ import annotations

from typing import Any


SUPPORTED_WORKFLOWS = {"research_brief"}


def derive_plan_request(*, workflow_type: str, intent: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = str(workflow_type or "").strip().lower()
    if normalized != "research_brief":
        raise ValueError(f"unsupported workflow_type: {workflow_type}")

    return {
        "plan_type": "research_linear",
        "intent": intent,
        "payload": dict(payload or {}),
        "workflow_metadata": {
            "workflow_type": normalized,
            "source": "workflow_sync",
        },
    }
