from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Job, JobStatus

SUPPORTED_JOB_TYPES = {"ping", "echo", "agent_task", "workflow_task", "operator_command"}


def create_job(session: Session, job_type: str, payload: dict, tenant_id: str = "owner") -> Job:
    if job_type not in SUPPORTED_JOB_TYPES:
        raise ValueError(f"unsupported job_type: {job_type}")

    job = Job(
        tenant_id=tenant_id or "owner",
        job_type=job_type,
        status=JobStatus.pending,
        payload=payload or {},
    )
    session.add(job)
    session.flush()
    return job


def mark_job_queued(session: Session, job: Job, queue_task_id: str) -> Job:
    if job.status == JobStatus.pending:
        job.status = JobStatus.queued
        job.updated_at = datetime.now(timezone.utc)

    if not job.queue_task_id:
        job.queue_task_id = queue_task_id

    session.add(job)
    session.flush()
    return job


def get_job(session: Session, job_id: str) -> Job | None:
    return session.get(Job, job_id)


