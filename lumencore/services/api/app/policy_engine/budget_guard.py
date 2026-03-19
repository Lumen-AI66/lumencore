from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ProjectBudget


def check_budget(*, session: Session, tenant_id: str, project_id: str, estimated_cost: float) -> tuple[bool, str]:
    safe_cost = float(estimated_cost)
    if safe_cost < 0:
        return False, 'estimated_cost cannot be negative'

    budget = session.execute(
        select(ProjectBudget).where(
            ProjectBudget.tenant_id == tenant_id,
            ProjectBudget.project_id == project_id,
        )
    ).scalar_one_or_none()

    # Phase 4A.2 framework only: do not enforce hard limit yet.
    if not budget:
        return True, 'budget framework pass (no project budget configured)'

    if budget.monthly_limit is not None and (budget.current_spend + safe_cost) > budget.monthly_limit:
        return True, 'budget framework pass (limit exceeded but enforcement disabled)'

    return True, 'budget framework pass'
