from __future__ import annotations

from typing import Any

MAX_PLAN_STEPS = 3


def decompose_plan(*, intent: str, plan_type: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    normalized_intent = str(intent or "").strip().lower()
    normalized_plan_type = str(plan_type or "").strip().lower()
    task_payload = dict(payload or {})
    objective = str(task_payload.get("objective") or task_payload.get("query") or "").strip()

    if normalized_plan_type == "research_linear" and normalized_intent == "agent.runtime.research":
        if not objective:
            raise ValueError("research plan requires an objective")
        steps = [
            {
                "step_index": 0,
                "step_type": "agent_task",
                "agent_type": "research",
                "title": "Collect research observations",
                "payload": {
                    "objective": objective,
                    "query": objective,
                    "phase": "research",
                },
            },
            {
                "step_index": 1,
                "step_type": "agent_task",
                "agent_type": "analysis",
                "title": "Summarize research observations",
                "payload": {
                    "objective": f"Summarize findings for: {objective}",
                    "query": objective,
                    "phase": "analysis",
                },
            },
        ]
        if len(steps) > MAX_PLAN_STEPS:
            raise RuntimeError("plan step limit exceeded")
        return steps

    raise ValueError(f"unsupported plan_type: {plan_type}")
