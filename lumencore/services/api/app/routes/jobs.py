from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..db import session_scope
from ..schemas.jobs import (
    JobCreateRequest,
    JobCreateResponse,
    JobResponse,
    JobSummaryResponse,
    RecentFailuresResponse,
    RecentJobItem,
    RecentJobsResponse,
)
from ..security import internal_observability_boundary
from ..services.jobs import create_job, get_job, mark_job_queued
from ..services.observability import (
    get_job_status_counts,
    get_latest_job_activity,
    list_recent_failures,
    list_recent_jobs,
)
from ..worker_tasks import execute_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_job(req: JobCreateRequest) -> JobCreateResponse:
    try:
        # First transaction: persist pending job.
        with session_scope() as session:
            job = create_job(session, req.job_type, req.payload)
            job_id = job.id
            created_at = job.created_at

        # Dispatch after pending state is committed.
        task = execute_job.delay(job_id)

        # Second transaction: mark queued, unless worker already progressed status.
        with session_scope() as session:
            job = get_job(session, job_id)
            if not job:
                raise HTTPException(status_code=500, detail="job disappeared after creation")
            job = mark_job_queued(session, job, task.id)

            return JobCreateResponse(
                id=job.id,
                job_type=job.job_type,
                status=job.status,
                created_at=created_at,
                queue_task_id=job.queue_task_id,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/summary",
    response_model=JobSummaryResponse,
    dependencies=[Depends(internal_observability_boundary)],
)
def jobs_summary() -> JobSummaryResponse:
    with session_scope() as session:
        counts, total = get_job_status_counts(session)
        latest_activity = get_latest_job_activity(session)

    return JobSummaryResponse(
        counts_by_status=counts,
        total_jobs=total,
        latest_job_activity=latest_activity,
    )


@router.get(
    "/recent",
    response_model=RecentJobsResponse,
    dependencies=[Depends(internal_observability_boundary)],
)
def jobs_recent(limit: int = Query(default=10, ge=1, le=100)) -> RecentJobsResponse:
    with session_scope() as session:
        jobs = list_recent_jobs(session, limit=limit)
        items = [
            RecentJobItem(
                id=job.id,
                job_type=job.job_type,
                status=job.status,
                created_at=job.created_at,
                updated_at=job.updated_at,
                finished_at=job.finished_at,
                queue_task_id=job.queue_task_id,
            )
            for job in jobs
        ]

    return RecentJobsResponse(limit=limit, items=items)


@router.get(
    "/recent-failures",
    response_model=RecentFailuresResponse,
    dependencies=[Depends(internal_observability_boundary)],
)
def jobs_recent_failures(limit: int = Query(default=10, ge=1, le=100)) -> RecentFailuresResponse:
    with session_scope() as session:
        failures = list_recent_failures(session, limit=limit)
        items = [
            RecentJobItem(
                id=job.id,
                job_type=job.job_type,
                status=job.status,
                created_at=job.created_at,
                updated_at=job.updated_at,
                finished_at=job.finished_at,
                queue_task_id=job.queue_task_id,
            )
            for job in failures
        ]

    return RecentFailuresResponse(limit=limit, items=items)


@router.get("/{job_id}", response_model=JobResponse)
def fetch_job(job_id: str) -> JobResponse:
    with session_scope() as session:
        job = get_job(session, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")

        return JobResponse(
            id=job.id,
            job_type=job.job_type,
            status=job.status,
            payload=job.payload,
            result=job.result,
            error=job.error,
            queue_task_id=job.queue_task_id,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            updated_at=job.updated_at,
        )
