from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..db import session_scope
from ..schemas.workflows import WorkflowDetailResponse, WorkflowListItemResponse, WorkflowListResponse, WorkflowPlanSummaryResponse
from ..workflows import get_workflow_store

router = APIRouter(prefix="/api/workflows", tags=["workflows"])
workflow_store = get_workflow_store()


@router.get("", response_model=WorkflowListResponse)
def list_workflows(limit: int = Query(default=20, ge=1, le=100)) -> WorkflowListResponse:
    with session_scope() as session:
        workflows = workflow_store.list_workflows(session, limit=limit)
        items = [
            WorkflowListItemResponse(
                workflow_id=item.workflow_id,
                tenant_id=item.tenant_id,
                command_id=item.command_id,
                workflow_type=item.workflow_type,
                status=item.status,
                linked_plan_id=item.linked_plan_id,
                error=item.error,
                created_at=item.created_at,
                updated_at=item.updated_at,
                completed_at=item.completed_at,
                result_summary=item.result_summary,
            )
            for item in workflows
        ]
    return WorkflowListResponse(limit=limit, items=items)


@router.get("/{workflow_id}", response_model=WorkflowDetailResponse)
def get_workflow(workflow_id: str) -> WorkflowDetailResponse:
    with session_scope() as session:
        workflow = workflow_store.get_workflow(session, workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="workflow not found")

        linked_plan_summary = workflow_store.get_linked_plan_summary(session, linked_plan_id=workflow.linked_plan_id)

        return WorkflowDetailResponse(
            workflow_id=workflow.workflow_id,
            tenant_id=workflow.tenant_id,
            command_id=workflow.command_id,
            workflow_type=workflow.workflow_type,
            status=workflow.status,
            linked_plan_id=workflow.linked_plan_id,
            error=workflow.error,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
            completed_at=workflow.completed_at,
            result_summary=workflow.result_summary,
            linked_plan_summary=WorkflowPlanSummaryResponse(**linked_plan_summary) if linked_plan_summary else None,
        )
