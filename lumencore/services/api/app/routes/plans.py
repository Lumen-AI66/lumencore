from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..db import session_scope
from ..planning import get_plan_store
from ..schemas.plans import PlanDetailResponse, PlanListItemResponse, PlanListResponse, PlanStepResponse

router = APIRouter(prefix="/api/plans", tags=["plans"])
plan_store = get_plan_store()


def _get_intent(plan_metadata: dict | None) -> str | None:
    if isinstance(plan_metadata, dict):
        intent = plan_metadata.get("intent")
        return str(intent) if isinstance(intent, str) else None
    return None


@router.get("", response_model=PlanListResponse)
def list_plans(limit: int = Query(default=20, ge=1, le=100)) -> PlanListResponse:
    with session_scope() as session:
        plans = plan_store.list_plans(session, limit=limit)
        items = [
            PlanListItemResponse(
                plan_id=item.plan_id,
                tenant_id=item.tenant_id,
                command_id=item.command_id,
                plan_type=item.plan_type,
                intent=_get_intent(item.plan_metadata),
                status=item.status,
                total_steps=item.total_steps,
                current_step_index=item.current_step_index,
                error=item.error,
                created_at=item.created_at,
                updated_at=item.updated_at,
                completed_at=item.completed_at,
            )
            for item in plans
        ]
    return PlanListResponse(limit=limit, items=items)


@router.get("/{plan_id}", response_model=PlanDetailResponse)
def get_plan(plan_id: str) -> PlanDetailResponse:
    with session_scope() as session:
        plan = plan_store.get_plan(session, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="plan not found")

        steps = plan_store.list_steps(session, plan.plan_id)
        return PlanDetailResponse(
            plan_id=plan.plan_id,
            tenant_id=plan.tenant_id,
            command_id=plan.command_id,
            plan_type=plan.plan_type,
            intent=_get_intent(plan.plan_metadata),
            status=plan.status,
            total_steps=plan.total_steps,
            current_step_index=plan.current_step_index,
            error=plan.error,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            completed_at=plan.completed_at,
            result_summary=plan.result_summary,
            steps=[
                PlanStepResponse(
                    step_id=step.step_id,
                    step_index=step.step_index,
                    step_type=step.step_type,
                    agent_type=step.agent_type,
                    status=step.status,
                    execution_task_id=step.execution_task_id,
                    error=step.error,
                    updated_at=step.updated_at,
                    completed_at=step.completed_at,
                )
                for step in steps
            ],
        )
