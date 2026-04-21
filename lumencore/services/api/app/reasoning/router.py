"""Multi-model router — selects the best AI model per task type.

Rules:
  - Simple/fast tasks → Claude Haiku (cheap, fast)
  - Complex reasoning → Claude Sonnet (powerful)
  - Code generation → Claude Sonnet
  - Research/summarization → Claude Haiku or OpenAI
  - Fallback → Claude Haiku

Cost awareness: cheaper model first, escalate only when needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelChoice:
    model_id: str
    provider: str           # "anthropic" | "openai"
    reason: str
    estimated_cost_per_1k: float   # EUR per 1k tokens (approximate)


# Model catalogue
MODELS = {
    "claude-haiku": ModelChoice(
        model_id="claude-haiku-4-5-20251001",
        provider="anthropic",
        reason="Fast and cheap for simple tasks",
        estimated_cost_per_1k=0.0003,
    ),
    "claude-sonnet": ModelChoice(
        model_id="claude-sonnet-4-6",
        provider="anthropic",
        reason="Powerful reasoning and complex tasks",
        estimated_cost_per_1k=0.004,
    ),
    "gpt-4o-mini": ModelChoice(
        model_id="gpt-4o-mini",
        provider="openai",
        reason="Good balance of speed and quality",
        estimated_cost_per_1k=0.0002,
    ),
}

# Task type → preferred model
TASK_MODEL_MAP: dict[str, str] = {
    "simple_question": "claude-haiku",
    "summarization": "claude-haiku",
    "translation": "claude-haiku",
    "classification": "claude-haiku",
    "data_extraction": "claude-haiku",
    "complex_reasoning": "claude-sonnet",
    "planning": "claude-sonnet",
    "code_generation": "claude-sonnet",
    "code_review": "claude-sonnet",
    "strategy": "claude-sonnet",
    "analysis": "claude-sonnet",
    "research": "claude-haiku",
    "automation": "claude-haiku",
    "trading": "claude-sonnet",      # high stakes
    "financial": "claude-sonnet",    # high stakes
    "default": "claude-haiku",
}

# Complexity → model escalation
COMPLEXITY_ESCALATION: dict[str, str] = {
    "low": "claude-haiku",
    "medium": "claude-haiku",
    "high": "claude-sonnet",
}


def route_model(
    task_type: str | None = None,
    complexity: str | None = None,
    content: str | None = None,
    prefer_cheap: bool = True,
) -> ModelChoice:
    """Choose the best model for a given task."""

    # Complexity override (high complexity always gets sonnet)
    if complexity == "high" and not prefer_cheap:
        return MODELS["claude-sonnet"]

    # Task type routing
    normalized = (task_type or "default").lower().strip()
    model_key = TASK_MODEL_MAP.get(normalized, "claude-haiku")

    # Content heuristics — escalate if keywords suggest complexity
    if content:
        content_lower = content.lower()
        complex_signals = [
            "analyseer", "analyse", "strategie", "plan", "code", "schrijf",
            "trading", "financieel", "ontwerp", "architect", "optimize",
            "analyze", "strategy", "design", "complex",
        ]
        if any(sig in content_lower for sig in complex_signals) and not prefer_cheap:
            model_key = "claude-sonnet"

    return MODELS.get(model_key, MODELS["claude-haiku"])


def estimate_cost(tokens: int, model_key: str = "claude-haiku") -> float:
    """Estimate cost in EUR for a given token count."""
    model = MODELS.get(model_key, MODELS["claude-haiku"])
    return round((tokens / 1000) * model.estimated_cost_per_1k, 6)


def get_available_models() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "model_id": m.model_id,
            "provider": m.provider,
            "reason": m.reason,
            "cost_per_1k_eur": m.estimated_cost_per_1k,
        }
        for key, m in MODELS.items()
    ]
