"""Mythos-style looped reasoning engine for Lumencore.

Architecture:
  Prelude  → understand the task, extract context
  Recurrent → deepen reasoning in N loops (more loops = deeper thinking)
  Coda     → produce final plan + actions

This runs entirely via Claude — no external model needed.
Depth is controlled by max_loops (1=fast, 3=deep, 5=very deep).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

ANTHROPIC_API_KEY_ENV = "LUMENCORE_ANTHROPIC_API_KEY"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEEP_MODEL = "claude-sonnet-4-6"


@dataclass
class ReasoningResult:
    plan: str
    actions: list[dict[str, Any]]
    loops_run: int
    depth_score: float          # 0.0–1.0, how deep the reasoning went
    reasoning_trace: list[str]  # trace of each loop's output
    model_used: str


def _call_claude(prompt: str, system: str, model: str, max_tokens: int = 1024) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed")

    api_key = os.environ.get(ANTHROPIC_API_KEY_ENV, "")
    if not api_key:
        raise RuntimeError(f"{ANTHROPIC_API_KEY_ENV} not configured")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text if response.content else ""


PRELUDE_SYSTEM = """You are the Prelude phase of a Mythos-style reasoning engine inside Lumencore.
Your job: analyze the incoming task and produce a structured understanding.
Output a JSON object with:
- "task_type": one of [analysis, planning, execution, research, automation]
- "complexity": one of [low, medium, high]
- "key_constraints": list of strings
- "required_context": list of what information is needed
- "initial_approach": brief description of how to tackle this
Output ONLY valid JSON, no explanation."""

RECURRENT_SYSTEM = """You are the Recurrent reasoning loop of a Mythos-style reasoning engine.
You receive the task, previous reasoning, and loop number.
Deepen the reasoning: find what was missed, challenge assumptions, add specifics.
Output a JSON object with:
- "refined_understanding": updated task understanding
- "new_insights": list of new insights this loop found
- "adjusted_approach": how the approach should change
- "confidence": 0.0-1.0 confidence in the current plan
Output ONLY valid JSON, no explanation."""

CODA_SYSTEM = """You are the Coda phase of a Mythos-style reasoning engine inside Lumencore.
You are Openclaw — the AI executor. You receive full reasoning context and produce the final response.
Output a JSON object with:
- "plan": step-by-step execution plan as a string
- "actions": list of action objects, each with "tool", "description", "priority" (1-5)
- "summary": one-sentence summary of what will be done
- "requires_human_approval": true/false
- "estimated_cost_eur": estimated cost in euros (0 if free)
Output ONLY valid JSON, no explanation."""


class ReasoningEngine:
    """Mythos-style looped reasoning: Prelude → Recurrent (N loops) → Coda."""

    def __init__(self, *, max_loops: int = 2, use_deep_model: bool = False) -> None:
        self.max_loops = max(1, min(max_loops, 5))
        self.model = DEEP_MODEL if use_deep_model else DEFAULT_MODEL

    def reason(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        available_tools: list[str] | None = None,
    ) -> ReasoningResult:
        ctx_str = ""
        if context:
            ctx_str = f"\nContext: {context}"
        tools_str = ""
        if available_tools:
            tools_str = f"\nAvailable tools: {', '.join(available_tools)}"

        trace: list[str] = []

        # === PRELUDE ===
        prelude_prompt = f"Task: {task}{ctx_str}{tools_str}"
        try:
            prelude_raw = _call_claude(prelude_prompt, PRELUDE_SYSTEM, self.model, 512)
            prelude_data = _safe_json(prelude_raw)
        except Exception as exc:
            prelude_data = {"task_type": "unknown", "complexity": "medium", "initial_approach": str(exc)}
        trace.append(f"PRELUDE: {prelude_data}")

        # === RECURRENT LOOPS ===
        current_reasoning = prelude_data
        confidence = 0.5
        for loop_num in range(self.max_loops):
            loop_prompt = (
                f"Task: {task}\n"
                f"Loop: {loop_num + 1}/{self.max_loops}\n"
                f"Previous reasoning: {current_reasoning}"
            )
            try:
                loop_raw = _call_claude(loop_prompt, RECURRENT_SYSTEM, self.model, 512)
                loop_data = _safe_json(loop_raw)
                confidence = float(loop_data.get("confidence", confidence))
                current_reasoning = loop_data
            except Exception as exc:
                loop_data = {"error": str(exc)}
            trace.append(f"LOOP {loop_num + 1}: {loop_data}")

        # === CODA ===
        coda_prompt = (
            f"Task: {task}{ctx_str}{tools_str}\n"
            f"Full reasoning trace: {trace}"
        )
        try:
            coda_raw = _call_claude(coda_prompt, CODA_SYSTEM, self.model, 1024)
            coda_data = _safe_json(coda_raw)
        except Exception as exc:
            coda_data = {
                "plan": f"Direct execution: {task}",
                "actions": [{"tool": "claude", "description": task, "priority": 1}],
                "summary": task,
                "requires_human_approval": False,
                "estimated_cost_eur": 0,
            }
        trace.append(f"CODA: {coda_data}")

        depth_score = round(min(1.0, (self.max_loops * 0.3) + (confidence * 0.4)), 2)

        return ReasoningResult(
            plan=str(coda_data.get("plan", task)),
            actions=list(coda_data.get("actions", [])),
            loops_run=self.max_loops,
            depth_score=depth_score,
            reasoning_trace=trace,
            model_used=self.model,
        )


def _safe_json(raw: str) -> dict:
    import json
    import re
    # Extract JSON from markdown code blocks if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if match:
        raw = match.group(1)
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


# Singleton
_engine = ReasoningEngine(max_loops=2)
_deep_engine = ReasoningEngine(max_loops=4, use_deep_model=True)


def get_reasoning_engine(*, deep: bool = False) -> ReasoningEngine:
    return _deep_engine if deep else _engine
