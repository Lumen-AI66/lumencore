from __future__ import annotations

from datetime import datetime, timezone
import time

from billiard.exceptions import SoftTimeLimitExceeded
from celery import Celery
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from .agents.agent_registry import ensure_agent_registry_seeded
from .agents.agent_runtime import execute_agent_task
from .commands.command_service import execute_existing_command_run, get_command_run
from .config import settings
from .db import session_scope
from .models import JobStatus
from .services.jobs import get_job
from .services.observability import record_operator_event
from .tools import register_placeholder_tools
from .workflows import create_workflow_runtime


TASK_MAX_RETRIES = 3
TASK_SOFT_TIME_LIMIT_SECONDS = 20
TASK_HARD_TIME_LIMIT_SECONDS = 30
TASK_EXECUTION_TIMEOUT_SECONDS = 20
SCHEDULER_HEARTBEAT_KEY = "lumencore:scheduler:heartbeat"
SCHEDULER_HEARTBEAT_TTL_SECONDS = 180


celery_app = Celery("lumencore", broker=settings.redis_url, backend=settings.redis_result_url)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={"scheduler-heartbeat": {"task": "lumencore.scheduler_heartbeat", "schedule": 30.0}},
)

app = celery_app


def _load_job_with_retry(job_id: str, retries: int = 6, delay_s: float = 0.2):
    for _ in range(retries):
        with session_scope() as session:
            job = get_job(session, job_id)
            if job:
                return job.id
        time.sleep(delay_s)
    return None


def _mark_job_failed(job_id: str, reason: str) -> None:
    with session_scope() as session:
        job = get_job(session, job_id)
        if not job:
            return
        finished = datetime.now(timezone.utc)
        job.status = JobStatus.failed
        job.error = reason
        job.finished_at = finished
        job.updated_at = finished


def _optional_delay(payload: dict) -> None:
    raw = payload.get("delay_seconds", 0)
    try:
        delay_seconds = int(raw)
    except (TypeError, ValueError):
        raise ValueError("payload.delay_seconds must be an integer")

    if delay_seconds < 0 or delay_seconds > 60:
        raise ValueError("payload.delay_seconds must be between 0 and 60")
    if delay_seconds > TASK_EXECUTION_TIMEOUT_SECONDS:
        raise TimeoutError("job execution timed out")
    if delay_seconds > 0:
        time.sleep(delay_seconds)


def _build_result(job_type: str, payload: dict) -> dict:
    _optional_delay(payload)
    if job_type == "ping":
        return {"ok": True, "job_type": "ping", "message": payload.get("message", "")}
    if job_type == "echo":
        return {"ok": True, "job_type": "echo", "payload": payload}
    raise ValueError(f"unsupported job_type: {job_type}")


def _record_scheduler_heartbeat() -> str:
    now = datetime.now(timezone.utc).isoformat()
    client = Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password or None,
        db=settings.celery_broker_db,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )
    client.set(SCHEDULER_HEARTBEAT_KEY, now, ex=SCHEDULER_HEARTBEAT_TTL_SECONDS)
    return now


@celery_app.task(name="lumencore.scheduler_heartbeat")
def scheduler_heartbeat() -> dict:
    try:
        heartbeat_at = _record_scheduler_heartbeat()
        return {"ok": True, "heartbeat_at": heartbeat_at, "key": SCHEDULER_HEARTBEAT_KEY}
    except RedisError as exc:
        return {"ok": False, "error": str(exc), "key": SCHEDULER_HEARTBEAT_KEY}


@celery_app.task(
    name="lumencore.execute_job",
    bind=True,
    soft_time_limit=TASK_SOFT_TIME_LIMIT_SECONDS,
    time_limit=TASK_HARD_TIME_LIMIT_SECONDS,
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_job(self, job_id: str) -> dict:
    found_job_id = _load_job_with_retry(job_id)
    if not found_job_id:
        raise ValueError(f"job not found: {job_id}")

    now = datetime.now(timezone.utc)
    with session_scope() as session:
        job = get_job(session, job_id)
        if not job:
            raise ValueError(f"job not found during start: {job_id}")
        job.status = JobStatus.running
        job.started_at = now
        job.updated_at = now

    try:
        with session_scope() as session:
            job = get_job(session, job_id)
            if not job:
                raise ValueError(f"job not found during execution: {job_id}")

            payload = job.payload or {}
            if payload.get("_force_transient_retry_once") and self.request.retries == 0:
                raise SQLAlchemyError("forced transient retry for validation")

            if job.job_type == "agent_task":
                ensure_agent_registry_seeded(session)
                register_placeholder_tools()
                task_type = str(payload.get("task_type", "")).strip()
                if not task_type:
                    raise ValueError("agent_task requires payload.task_type")

                result = execute_agent_task(
                    session,
                    job_id=job.id,
                    task_type=task_type,
                    payload=payload.get("payload") or {},
                    owner_approved=bool(payload.get("owner_approved", False)),
                    tenant_id=str(payload.get("tenant_id", "owner")),
                    requested_agent_id=payload.get("agent_id") or None,
                )
            elif job.job_type == "operator_command":
                command_id = str(payload.get("command_id") or "").strip()
                if not command_id:
                    raise ValueError("operator_command requires payload.command_id")
                ensure_agent_registry_seeded(session)
                register_placeholder_tools()
                run = get_command_run(session, command_id)
                if not run:
                    raise ValueError(f"command run not found: {command_id}")
                record_operator_event("OPERATOR_COMMAND_STARTED", command_id=command_id)
                run = execute_existing_command_run(
                    session,
                    run=run,
                    project_id=str(payload.get("project_id") or "default"),
                )
                result = {
                    "command_id": run.id,
                    "status": run.status,
                    "result_summary": run.result_summary,
                }
                if run.status != "completed":
                    finished = datetime.now(timezone.utc)
                    job.status = JobStatus.failed
                    job.result = result
                    job.error = str((run.result_summary or {}).get("error") or "operator command failed")
                    job.finished_at = finished
                    job.updated_at = finished
                    return {"job_id": job.id, "status": job.status.value, "result": result}
            elif job.job_type == "workflow_task":
                workflow_type = str(payload.get("workflow_type", "")).strip()
                intent = str(payload.get("intent", "")).strip()
                if not workflow_type:
                    raise ValueError("workflow_task requires payload.workflow_type")
                if not intent:
                    raise ValueError("workflow_task requires payload.intent")

                register_placeholder_tools()
                workflow_runtime = create_workflow_runtime()
                workflow_execution = workflow_runtime.execute_workflow(
                    session,
                    tenant_id=str(payload.get("tenant_id", "owner")),
                    command_id=payload.get("command_id") or None,
                    workflow_type=workflow_type,
                    intent=intent,
                    payload=payload.get("payload") or {},
                    project_id=payload.get("project_id") or None,
                )
                result = {
                    "workflow_status": workflow_execution.get("status"),
                    "workflow_execution": workflow_execution,
                }
                if str(workflow_execution.get("status") or "").strip().lower() != "completed":
                    finished = datetime.now(timezone.utc)
                    job.status = JobStatus.failed
                    job.result = result
                    job.error = str(workflow_execution.get("error") or workflow_execution.get("status") or "workflow execution failed")
                    job.finished_at = finished
                    job.updated_at = finished
                    return {"job_id": job.id, "status": job.status.value, "result": result}
            else:
                result = _build_result(job.job_type, payload)

            finished = datetime.now(timezone.utc)
            job.status = JobStatus.completed
            job.result = result
            job.error = None
            job.finished_at = finished
            job.updated_at = finished
            return {"job_id": job.id, "status": job.status.value, "result": result}

    except (SoftTimeLimitExceeded, TimeoutError) as exc:
        _mark_job_failed(job_id, "job execution timed out")
        raise exc
    except SQLAlchemyError as exc:
        if self.request.retries < TASK_MAX_RETRIES:
            countdown = min(2 ** (self.request.retries + 1), 10)
            raise self.retry(exc=exc, countdown=countdown)
        _mark_job_failed(job_id, f"transient persistence failure after retries: {exc}")
        raise
    except Exception as exc:
        _mark_job_failed(job_id, str(exc))
        raise


@celery_app.task(name="lumencore.ping")
def ping() -> dict:
    return {"status": "ok", "service": "lumencore-worker", "phase": 4}
