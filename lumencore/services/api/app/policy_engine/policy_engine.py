from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .approval_guard import check_owner_approval
from .audit_logger import write_audit_event
from .budget_guard import check_budget
from .capability_guard import check_capability


@dataclass(frozen=True)
class PolicyValidationResult:
    allowed: bool
    reason: str


class PolicyEngine:
    def validate_agent_request(
        self,
        session: Session,
        *,
        tenant_id: str,
        task_type: str,
        requested_agent_id: str | None,
        owner_approved: bool,
        estimated_cost: float,
        project_id: str = "default",
    ) -> PolicyValidationResult:
        checks: list[tuple[bool, str]] = []
        checks.append(check_owner_approval(owner_approved))
        checks.append(check_capability(session, task_type=task_type, requested_agent_id=requested_agent_id))
        checks.append(check_budget(session=session, tenant_id=tenant_id, project_id=project_id, estimated_cost=estimated_cost))

        failed = next((reason for ok, reason in checks if not ok), None)
        allowed = failed is None
        reason = "policy checks passed" if allowed else failed

        write_audit_event(
            session,
            tenant_id=tenant_id,
            agent_id=requested_agent_id,
            action="agent.run.request",
            policy_result="allow" if allowed else "deny",
            metadata={
                "task_type": task_type,
                "project_id": project_id,
                "owner_approved": owner_approved,
                "estimated_cost": estimated_cost,
                "checks": [{"ok": ok, "reason": msg} for ok, msg in checks],
            },
        )
        return PolicyValidationResult(allowed=allowed, reason=reason)
