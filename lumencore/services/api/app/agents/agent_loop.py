from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any

from ..tools.models import ToolResult, ToolResultStatus
from .agent_types import AgentStep, BaseAgent


MAX_AGENT_STEPS = 5

StepExecutor = Callable[[AgentStep], ToolResult]


@dataclass(frozen=True)
class AgentLoopResult:
    status: str
    steps_executed: int
    tools_used: list[str]
    step_results: list[dict[str, Any]]
    duration_ms: float


def _derive_status(results: list[ToolResult]) -> str:
    statuses = [result.status for result in results]
    if any(status is ToolResultStatus.timeout for status in statuses):
        return "timeout"
    if any(status is ToolResultStatus.failed for status in statuses):
        return "failed"
    if any(status is ToolResultStatus.denied for status in statuses):
        return "denied"
    return "completed"


def run_agent(agent: BaseAgent, task: dict[str, Any], *, step_executor: StepExecutor) -> AgentLoopResult:
    planned_steps = agent.plan(task or {})
    if len(planned_steps) > MAX_AGENT_STEPS:
        raise RuntimeError("Agent step limit exceeded")

    started = monotonic()
    tool_results: list[ToolResult] = []
    tools_used: list[str] = []

    for step in planned_steps:
        executed_step = agent.act(step)
        tool_result = step_executor(executed_step)
        tool_results.append(tool_result)
        tools_used.append(executed_step.tool_name)

    duration_ms = round((monotonic() - started) * 1000, 2)
    step_results = [item.model_dump(mode="json") for item in tool_results]
    return AgentLoopResult(
        status=_derive_status(tool_results),
        steps_executed=len(tool_results),
        tools_used=tools_used,
        step_results=step_results,
        duration_ms=duration_ms,
    )
