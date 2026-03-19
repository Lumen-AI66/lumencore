from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionGateDecision:
    execution_decision: str
    approval_required: bool
    approval_status: str
    policy_reason: str


def evaluate_execution_gate(*, plan: dict, requested_mode: str | None = None) -> ExecutionGateDecision:
    execution_mode = str(plan.get("execution_mode") or "").strip().lower()
    normalized_mode = str(requested_mode or "").strip().lower()

    if normalized_mode == "workflow_job":
        if execution_mode == "workflow_job":
            return ExecutionGateDecision(
                execution_decision="approval_required",
                approval_required=True,
                approval_status="required",
                policy_reason="workflow_job requires approval",
            )
        return ExecutionGateDecision(
            execution_decision="denied",
            approval_required=False,
            approval_status="not_required",
            policy_reason="workflow_job is only supported for bounded research workflow execution",
        )

    if execution_mode in {"sync_read", "tool_sync", "agent_sync", "plan_sync", "workflow_sync", "agent_job"}:
        return ExecutionGateDecision(
            execution_decision="allowed",
            approval_required=False,
            approval_status="not_required",
            policy_reason="execution allowed by fixed policy",
        )

    if execution_mode == "workflow_job":
        return ExecutionGateDecision(
            execution_decision="approval_required",
            approval_required=True,
            approval_status="required",
            policy_reason="workflow_job requires approval",
        )

    return ExecutionGateDecision(
        execution_decision="denied",
        approval_required=False,
        approval_status="not_required",
        policy_reason="execution mode not allowed by fixed policy",
    )
