from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentStep:
    tool_name: str
    connector_name: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)


class BaseAgent:
    agent_type: str = "base"
    agent_id: str = ""
    name: str = "base-agent"
    description: str = "Deterministic base agent."
    tools: tuple[str, ...] = ()

    def plan(self, task: dict[str, Any]) -> list[AgentStep]:
        raise NotImplementedError()

    def act(self, step: AgentStep) -> AgentStep:
        return step

    def _build_echo_step(self, task: dict[str, Any], *, task_label: str) -> AgentStep:
        objective = str(task.get("objective") or task.get("query") or task.get("message") or "").strip()
        payload = {
            "agent_type": self.agent_type,
            "agent_name": self.name,
            "task_label": task_label,
            "objective": objective,
            "task": {
                "task_id": task.get("task_id"),
                "command_id": task.get("command_id"),
                "run_id": task.get("run_id"),
            },
            "read_only": True,
        }
        return AgentStep(
            tool_name="system.echo",
            connector_name="system",
            action="echo",
            payload=payload,
        )

    def _build_openai_step(self, task: dict[str, Any], *, task_label: str) -> AgentStep:
        objective = str(task.get("objective") or task.get("query") or task.get("message") or "").strip()
        query = str(task.get("query") or objective).strip()
        prompt = str(task.get("prompt") or objective or query).strip()
        payload = {
            "prompt": prompt,
            "objective": objective,
            "query": query,
            "model": str(task.get("model") or "gpt-4.1-mini"),
            "max_output_tokens": int(task.get("max_output_tokens") or 700),
            "read_only": True,
            "task_label": task_label,
            "agent_type": self.agent_type,
            "agent_name": self.name,
        }
        return AgentStep(
            tool_name="tool.openai.complete",
            connector_name="openai",
            action="complete",
            payload=payload,
        )


class ResearchAgent(BaseAgent):
    agent_type = "research"
    agent_id = "22222222-2222-4222-8222-222222222222"
    name = "research-agent"
    description = "Deterministic research planner that routes safe read-only tasks to governed tools."
    tools = ("tool.openai.complete",)

    def plan(self, task: dict[str, Any]) -> list[AgentStep]:
        return [self._build_openai_step(task, task_label="research-observation")]


class AutomationAgent(BaseAgent):
    agent_type = "automation"
    agent_id = "33333333-3333-4333-8333-333333333333"
    name = "automation-agent"
    description = "Deterministic automation planner that selects one safe internal tool step."
    tools = ("system.echo",)

    def plan(self, task: dict[str, Any]) -> list[AgentStep]:
        return [self._build_echo_step(task, task_label="automation-plan")]


class AnalysisAgent(BaseAgent):
    agent_type = "analysis"
    agent_id = "44444444-4444-4444-8444-444444444444"
    name = "analysis-agent"
    description = "Deterministic analysis planner that emits one governed read-only tool step."
    tools = ("tool.openai.complete",)

    def plan(self, task: dict[str, Any]) -> list[AgentStep]:
        return [self._build_openai_step(task, task_label="analysis-observation")]

