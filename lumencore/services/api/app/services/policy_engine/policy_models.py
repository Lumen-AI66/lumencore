from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CommandPolicyDecision:
    outcome: str
    source: str
    execution_decision: str
    approval_required: bool
    approval_status: str
    policy_reason: str
    evaluated_at: datetime


@dataclass(frozen=True)
class ExecutionPolicyDecision:
    allowed: bool
    reason: str | None
    risk_level: str
    requires_approval: bool
    evaluated_at: datetime
