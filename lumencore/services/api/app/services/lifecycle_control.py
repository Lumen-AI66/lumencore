from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LifecycleTransitionDecision:
    outcome: str
    reason: str


def evaluate_command_transition(*, requested_mode: str | None, status: str, approval_required: bool, approval_status: str, job_id: str | None, action: str) -> LifecycleTransitionDecision:
    normalized_mode = str(requested_mode or "").strip().lower()
    normalized_status = str(status or "").strip().lower()
    normalized_approval = str(approval_status or "").strip().lower()
    normalized_action = str(action or "").strip().lower()

    if normalized_action == "cancel":
        if normalized_mode != "workflow_job":
            return LifecycleTransitionDecision("unsupported", "cancel is only supported for workflow_job commands")
        if normalized_status == "pending" and approval_required and normalized_approval == "required" and not job_id:
            return LifecycleTransitionDecision("allowed", "pending workflow_job can be cancelled before approval")
        return LifecycleTransitionDecision("invalid_transition", "cancel is only allowed while a workflow_job is awaiting approval")

    if normalized_action == "retry":
        if normalized_mode != "workflow_job":
            return LifecycleTransitionDecision("unsupported", "retry is only supported for workflow_job commands")
        if normalized_status in {"cancelled", "failed"}:
            return LifecycleTransitionDecision("allowed", "workflow_job can be re-issued from a cancelled or failed state")
        return LifecycleTransitionDecision("invalid_transition", "retry is only allowed for cancelled or failed workflow_job commands")

    return LifecycleTransitionDecision("unsupported", "lifecycle action is not supported")
