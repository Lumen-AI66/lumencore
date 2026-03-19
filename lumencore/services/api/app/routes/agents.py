from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query, status

from ..db import session_scope
from ..policy_engine.policy_engine import PolicyEngine
from ..schemas.agents import (
    AgentItem,
    AgentListResponse,
    AgentPoliciesResponse,
    AgentPolicyItem,
    AgentRegistryItem,
    AgentRegistryListResponse,
    AgentRegistryStatusResponse,
    AgentRunRequest,
    AgentRunResponse,
    AgentStatusResponse,
)
from ..services.agents import (
    get_agent_status_summary,
    get_registry_agent,
    get_registry_agent_status,
    list_agents,
    list_policies,
    list_registry_agents,
)
from ..services.jobs import create_job, get_job, mark_job_queued
from ..security import internal_route_boundary
from ..tenancy.tenant_guard import enforce_owner_tenant
from ..worker_tasks import execute_job

router = APIRouter(prefix="/api/agents", tags=["agents"])
policy_engine = PolicyEngine()


@router.get("", response_model=AgentListResponse)
def agents_root_list() -> AgentListResponse:
    with session_scope() as session:
        items = list_agents(session)
    return AgentListResponse(total=len(items), items=[AgentItem(**item) for item in items])


@router.get("/list", response_model=AgentListResponse)
def agents_list() -> AgentListResponse:
    return agents_root_list()


@router.get("/registry", response_model=AgentRegistryListResponse)
def agents_registry(
    enabled: bool | None = Query(default=None),
    capability: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> AgentRegistryListResponse:
    with session_scope() as session:
        result = list_registry_agents(session, enabled=enabled, capability=capability, runtime_status=status_filter)
    return AgentRegistryListResponse(
        total=result["total"],
        counts_by_status=result["counts_by_status"],
        items=[AgentRegistryItem(**item) for item in result["items"]],
    )


@router.get("/status", response_model=AgentStatusResponse)
def agents_status() -> AgentStatusResponse:
    with session_scope() as session:
        summary = get_agent_status_summary(session)
    return AgentStatusResponse(**summary)


@router.get("/policies", response_model=AgentPoliciesResponse)
def agents_policies() -> AgentPoliciesResponse:
    with session_scope() as session:
        rows = list_policies(session)
    return AgentPoliciesResponse(total=len(rows), items=[AgentPolicyItem(**row) for row in rows])


@router.get("/registry/{agent_key}/status", response_model=AgentRegistryStatusResponse)
def agent_detail_status(agent_key: str) -> AgentRegistryStatusResponse:
    try:
        with session_scope() as session:
            item = get_registry_agent_status(session, agent_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AgentRegistryStatusResponse(**item)


@router.get("/registry/{agent_key}", response_model=AgentRegistryItem)
def agent_detail(agent_key: str) -> AgentRegistryItem:
    try:
        with session_scope() as session:
            item = get_registry_agent(session, agent_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AgentRegistryItem(**item)


@router.post("/run", response_model=AgentRunResponse, status_code=status.HTTP_202_ACCEPTED)
def agents_run(
    req: AgentRunRequest,
    x_lumencore_owner_approval: str | None = Header(default=None),
    x_lumencore_internal_route: str | None = Header(default=None),
) -> AgentRunResponse:
    internal_route_boundary(x_lumencore_internal_route)
    owner_approved = (x_lumencore_owner_approval or "").strip().lower() == "true"

    try:
        tenant_id = enforce_owner_tenant(req.tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    payload = {
        "task_type": req.task_type,
        "payload": req.payload,
        "owner_approved": owner_approved,
        "agent_id": req.agent_id,
        "tenant_id": tenant_id,
        "project_id": req.project_id,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        denial_reason: str | None = None

        with session_scope() as session:
            validation = policy_engine.validate_agent_request(
                session,
                tenant_id=tenant_id,
                project_id=req.project_id,
                task_type=req.task_type,
                requested_agent_id=req.agent_id,
                owner_approved=owner_approved,
                estimated_cost=req.estimated_cost,
            )
            if not validation.allowed:
                denial_reason = validation.reason
                job_id = None
                created_at = None
            else:
                job = create_job(session, "agent_task", payload, tenant_id=tenant_id)
                job_id = job.id
                created_at = job.created_at

        if denial_reason:
            raise HTTPException(status_code=403, detail=denial_reason)

        task = execute_job.delay(job_id)

        with session_scope() as session:
            job = get_job(session, job_id)
            if not job:
                raise HTTPException(status_code=500, detail="agent run job disappeared after creation")
            job = mark_job_queued(session, job, task.id)

            return AgentRunResponse(
                id=job.id,
                job_type=job.job_type,
                status=job.status.value,
                queue_task_id=job.queue_task_id,
                created_at=created_at,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
