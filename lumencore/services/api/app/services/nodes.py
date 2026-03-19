from __future__ import annotations

from datetime import datetime, timezone
import socket

from redis import Redis
from redis.exceptions import RedisError

from ..config import load_yaml_config, settings
from ..db import check_db
from ..schemas.nodes import NodeItem, NodeListResponse, NodeStatusResponse
from ..worker_tasks import celery_app

SCHEDULER_HEARTBEAT_KEY = "lumencore:scheduler:heartbeat"
SCHEDULER_HEARTBEAT_MAX_AGE_SECONDS = 120


def _check_redis() -> dict:
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


def _check_worker() -> dict:
    try:
        inspector = celery_app.control.inspect(timeout=2)
        pong = inspector.ping() if inspector else None
        ok = bool(pong)
        return {"ok": ok, "message": "worker reachable" if ok else "no worker ping response"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def _check_scheduler() -> dict:
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
            return {"ok": False, "message": "scheduler heartbeat missing", "last_heartbeat_at": None}

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
        return {"ok": False, "message": str(exc), "last_heartbeat_at": None}


def _load_node_definitions() -> dict[str, dict]:
    raw = load_yaml_config("nodes.yaml")
    nodes = raw.get("NODES") or {}
    if not isinstance(nodes, dict):
        return {}
    normalized: dict[str, dict] = {}
    for key, value in nodes.items():
        safe_key = str(key).strip()
        if not safe_key or not isinstance(value, dict):
            continue
        normalized[safe_key] = dict(value)
    return normalized


def _build_local_node_item(node_key: str, definition: dict) -> NodeItem:
    db_status = check_db()
    redis_status = _check_redis()
    worker_status = _check_worker()
    scheduler_status = _check_scheduler()
    healthy = bool(db_status.get("ok") and redis_status.get("ok") and worker_status.get("ok") and scheduler_status.get("ok"))
    return NodeItem(
        node_key=node_key,
        name=str(definition.get("name") or node_key),
        kind=str(definition.get("kind") or "control_plane"),
        source=str(definition.get("source") or "builtin"),
        enabled=bool(definition.get("enabled", True)),
        registered=True,
        status="local" if bool(definition.get("enabled", True)) else "disabled",
        healthy=healthy if bool(definition.get("enabled", True)) else False,
        capabilities=[str(item) for item in list(definition.get("capabilities") or [])],
        last_heartbeat_at=None,
        metadata={
            "local": True,
        },
        runtime_metadata={
            "hostname": socket.gethostname(),
            "heartbeat_backed": False,
            "components": {
                "database": db_status,
                "redis": redis_status,
                "worker": worker_status,
                "scheduler": scheduler_status,
            },
        },
    )


def _build_remote_placeholder_item(node_key: str, definition: dict) -> NodeItem:
    enabled = bool(definition.get("enabled", True))
    return NodeItem(
        node_key=node_key,
        name=str(definition.get("name") or node_key),
        kind=str(definition.get("kind") or "remote"),
        source=str(definition.get("source") or "config"),
        enabled=enabled,
        registered=True,
        status="offline" if enabled else "disabled",
        healthy=False,
        capabilities=[str(item) for item in list(definition.get("capabilities") or [])],
        last_heartbeat_at=None,
        metadata={
            "local": False,
        },
        runtime_metadata={
            "heartbeat_backed": False,
            "placeholder": True,
        },
    )


def list_nodes() -> NodeListResponse:
    definitions = _load_node_definitions()
    items: list[NodeItem] = []
    for node_key in sorted(definitions):
        definition = definitions[node_key]
        if bool(definition.get("local")):
            items.append(_build_local_node_item(node_key, definition))
        else:
            items.append(_build_remote_placeholder_item(node_key, definition))
    return NodeListResponse(total=len(items), items=items)


def get_node(node_key: str) -> NodeItem | None:
    safe_key = str(node_key or "").strip()
    if not safe_key:
        return None
    snapshot = list_nodes()
    for item in snapshot.items:
        if item.node_key == safe_key:
            return item
    return None


def get_node_status(node_key: str) -> NodeStatusResponse | None:
    item = get_node(node_key)
    if item is None:
        return None
    return NodeStatusResponse(
        node_key=item.node_key,
        enabled=item.enabled,
        registered=item.registered,
        status=item.status,
        healthy=item.healthy,
        last_heartbeat_at=item.last_heartbeat_at,
        runtime_metadata=item.runtime_metadata,
    )
