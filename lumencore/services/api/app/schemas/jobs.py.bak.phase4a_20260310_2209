from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..models import JobStatus


class JobCreateRequest(BaseModel):
    job_type: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class JobCreateResponse(BaseModel):
    id: str
    job_type: str
    status: JobStatus
    created_at: datetime
    queue_task_id: str | None = None


class JobResponse(BaseModel):
    id: str
    job_type: str
    status: JobStatus
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    queue_task_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class JobSummaryResponse(BaseModel):
    counts_by_status: dict[str, int]
    total_jobs: int
    latest_job_activity: datetime | None = None


class RecentJobItem(BaseModel):
    id: str
    job_type: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
    queue_task_id: str | None = None


class RecentJobsResponse(BaseModel):
    limit: int
    items: list[RecentJobItem]


class RecentFailuresResponse(BaseModel):
    limit: int
    items: list[RecentJobItem]
