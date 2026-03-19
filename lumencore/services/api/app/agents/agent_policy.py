from __future__ import annotations

from dataclasses import dataclass

from ..models import Agent, AgentPolicy


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


def validate_agent_policy(
    *,
    agent: Agent,
    policy: AgentPolicy,
    task_type: str,
    owner_approved: bool,
) -> PolicyDecision:
    if not policy.execution_allowed:
        return PolicyDecision(False, "policy denies execution")

    if str(agent.status).lower() not in {"active", "idle"}:
        return PolicyDecision(False, "agent is not active")

    allowed_task_types = policy.allowed_task_types or []
    if allowed_task_types and task_type not in allowed_task_types:
        return PolicyDecision(False, f"task_type not allowed by policy: {task_type}")

    if policy.owner_only_execution and not owner_approved:
        return PolicyDecision(False, "owner approval required")

    if policy.max_runtime_seconds <= 0:
        return PolicyDecision(False, "invalid max_runtime_seconds policy")

    return PolicyDecision(True, "allowed")
