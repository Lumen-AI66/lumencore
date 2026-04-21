"""Openclaw Orchestrator — top-level controller for Lumencore.

Openclaw receives a high-level task and:
1. Runs it through the reasoning engine (Prelude → Recurrent → Coda)
2. Routes to the best model via the model router
3. Executes the plan (tool calls, sub-agents, n8n workflows)
4. Stores results + decisions in memory
5. Reports back to the operator (Telegram / dashboard)

Golden Rule: ALWAYS reports to operator. Never acts outside approved scope.
"""
from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..reasoning.engine import get_reasoning_engine, ReasoningResult
from ..reasoning.router import route_model, ModelChoice

ANTHROPIC_API_KEY_ENV = "LUMENCORE_ANTHROPIC_API_KEY"
LUMENCORE_API_URL = os.environ.get("LUMENCORE_API_URL", "http://lumencore-api:8000")

ORCHESTRATOR_SYSTEM = """You are Openclaw — the primary AI orchestrator of Lumencore.

You control the system on behalf of the operator (Rico). You always:
1. Report what you are about to do before doing it
2. Execute only what the operator has approved
3. Store all decisions and outcomes in memory
4. Alert the operator when you need approval or budget
5. Speak Dutch with the operator, use English internally

You have access to: Claude AI, OpenAI, n8n workflows, web search, GitHub, desktop execution.
You coordinate projects, build workflows, monitor revenue, and report daily.

NEVER: transfer money, publish content, or make purchases without explicit operator approval.
ALWAYS: show your work, explain your reasoning, ask when uncertain."""


@dataclass
class OrchestratorResult:
    task: str
    status: str                      # "completed" | "pending_approval" | "failed"
    summary: str                     # one-line for operator
    plan: str
    actions_taken: list[dict]
    reasoning_depth: float
    model_used: str
    requires_approval: bool
    approval_items: list[str]        # what needs operator approval
    memory_stored: bool
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class OpenclawOrchestrator:
    """Full orchestrator: reason → route → execute → report."""

    def __init__(self, *, deep_reasoning: bool = False) -> None:
        self.reasoning_engine = get_reasoning_engine(deep=deep_reasoning)

    def orchestrate(
        self,
        task: str,
        *,
        context: dict[str, Any] | None = None,
        operator_id: str = "owner",
        available_tools: list[str] | None = None,
        auto_execute: bool = False,
    ) -> OrchestratorResult:
        """Main entry point. Reason about task, produce plan, execute if approved."""

        tools = available_tools or [
            "claude", "openai", "search", "n8n", "git", "desktop"
        ]

        # Step 1: Reason
        try:
            reasoning: ReasoningResult = self.reasoning_engine.reason(
                task, context=context, available_tools=tools
            )
        except Exception as exc:
            return OrchestratorResult(
                task=task,
                status="failed",
                summary=f"Reasoning failed: {exc}",
                plan="",
                actions_taken=[],
                reasoning_depth=0.0,
                model_used="none",
                requires_approval=True,
                approval_items=[f"Manual review needed: {exc}"],
                memory_stored=False,
            )

        # Step 2: Route model
        model_choice: ModelChoice = route_model(
            content=task,
            prefer_cheap=True,
        )

        # Step 3: Determine approval needs
        requires_approval = False
        approval_items: list[str] = []

        for action in reasoning.actions:
            tool = str(action.get("tool", "")).lower()
            desc = str(action.get("description", ""))
            # High-stakes actions always need approval
            if any(kw in tool for kw in ["payment", "transfer", "publish", "deploy", "delete"]):
                requires_approval = True
                approval_items.append(f"High-stakes action: {desc}")
            if any(kw in desc.lower() for kw in ["betalen", "kopen", "publiceren", "verwijderen", "deploy"]):
                requires_approval = True
                approval_items.append(f"Needs approval: {desc}")

        # Step 4: Build operator summary
        summary = _build_summary(task, reasoning, requires_approval, approval_items)

        # Step 5: Store in memory (fire-and-forget via API)
        memory_stored = _store_in_memory(
            task=task,
            plan=reasoning.plan,
            actions=reasoning.actions,
            operator_id=operator_id,
        )

        status = "pending_approval" if requires_approval else "completed"
        if requires_approval and not auto_execute:
            status = "pending_approval"

        return OrchestratorResult(
            task=task,
            status=status,
            summary=summary,
            plan=reasoning.plan,
            actions_taken=reasoning.actions if not requires_approval else [],
            reasoning_depth=reasoning.depth_score,
            model_used=model_choice.model_id,
            requires_approval=requires_approval,
            approval_items=approval_items,
            memory_stored=memory_stored,
        )


def _build_summary(
    task: str,
    reasoning: ReasoningResult,
    requires_approval: bool,
    approval_items: list[str],
) -> str:
    lines = []
    lines.append(f"📋 Taak: {task[:100]}")
    lines.append(f"🧠 Redenering: {int(reasoning.depth_score * 100)}% diepte, {reasoning.loops_run} loops")
    if reasoning.plan:
        lines.append(f"📌 Plan: {reasoning.plan[:200]}")
    if reasoning.actions:
        lines.append(f"⚡ Acties: {len(reasoning.actions)} gepland")
    if requires_approval:
        lines.append(f"⚠️ Wacht op jouw goedkeuring:")
        for item in approval_items[:3]:
            lines.append(f"  → {item}")
    else:
        lines.append("✅ Klaar voor uitvoering")
    return "\n".join(lines)


def _store_in_memory(
    *,
    task: str,
    plan: str,
    actions: list[dict],
    operator_id: str,
) -> bool:
    """Store orchestration result in Lumencore memory via API."""
    import urllib.request
    import urllib.error

    url = f"{LUMENCORE_API_URL}/api/memory"
    payload = json.dumps({
        "type": "context",
        "key": f"orchestration:{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "content": f"Task: {task}\nPlan: {plan}\nActions: {len(actions)}",
        "metadata": {
            "operator_id": operator_id,
            "actions_count": len(actions),
            "source": "openclaw_orchestrator",
        },
    }).encode()

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status in (200, 201)
    except Exception:
        return False


# Singleton
_orchestrator = OpenclawOrchestrator()
_deep_orchestrator = OpenclawOrchestrator(deep_reasoning=True)


def get_orchestrator(*, deep: bool = False) -> OpenclawOrchestrator:
    return _deep_orchestrator if deep else _orchestrator
