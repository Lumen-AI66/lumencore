from __future__ import annotations

from datetime import datetime, timezone

from redis import Redis
from redis.exceptions import RedisError

from ..config import settings
from ..db import check_db
from ..worker_tasks import celery_app

SCHEDULER_HEARTBEAT_KEY = "lumencore:scheduler:heartbeat"
SCHEDULER_HEARTBEAT_MAX_AGE_SECONDS = 120


def check_redis() -> dict:
    try:
        client = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.celery_broker_db,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        pong = client.ping()
        return {"ok": bool(pong), "message": "redis reachable" if pong else "redis ping failed"}
    except RedisError as exc:
        return {"ok": False, "message": str(exc)}


def check_worker() -> dict:
    try:
        inspector = celery_app.control.inspect(timeout=2)
        pong = inspector.ping() if inspector else None
        ok = bool(pong)
        return {"ok": ok, "message": "worker reachable" if ok else "no worker ping response"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def check_scheduler() -> dict:
    try:
        client = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.celery_broker_db,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        raw = client.get(SCHEDULER_HEARTBEAT_KEY)
        if not raw:
            return {"ok": False, "message": "scheduler heartbeat missing"}

        heartbeat_at = datetime.fromisoformat(raw)
        if heartbeat_at.tzinfo is None:
            heartbeat_at = heartbeat_at.replace(tzinfo=timezone.utc)

        age_seconds = (datetime.now(timezone.utc) - heartbeat_at).total_seconds()
        ok = age_seconds <= SCHEDULER_HEARTBEAT_MAX_AGE_SECONDS
        return {
            "ok": ok,
            "message": f"scheduler heartbeat age {age_seconds:.1f}s" if ok else f"scheduler heartbeat stale {age_seconds:.1f}s",
            "last_heartbeat_at": heartbeat_at.isoformat(),
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def get_runtime_health_snapshot() -> dict:
    db_status = check_db()
    redis_status = check_redis()
    worker_status = check_worker()
    scheduler_status = check_scheduler()
    api_ok = bool(db_status["ok"] and redis_status["ok"])
    overall_ok = bool(api_ok and worker_status["ok"] and scheduler_status["ok"])
    status = "ok" if overall_ok else "degraded"
    return {
        "status": status,
        "api_ok": api_ok,
        "api": {"ok": api_ok, "database": db_status, "redis": redis_status},
        "worker": worker_status,
        "scheduler": scheduler_status,
    }
