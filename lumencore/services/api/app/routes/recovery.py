from __future__ import annotations

from fastapi import APIRouter, Body, Query

from ..services.recovery.control import evaluate_recovery, get_recovery_summary, list_recovery_events

router = APIRouter(prefix='/api/recovery', tags=['recovery'])


@router.get('/summary')
def recovery_summary() -> dict:
    return get_recovery_summary()


@router.get('/events')
def recovery_events(limit: int = Query(default=20, ge=1, le=200)) -> dict:
    return {'limit': limit, 'items': list_recovery_events(limit=limit)}


@router.post('/evaluate')
def recovery_evaluate(payload: dict | None = Body(default=None)) -> dict:
    body = payload or {}
    return evaluate_recovery(
        task_id=body.get('task_id'),
        execute=bool(body.get('execute', False)),
        source=str(body.get('source') or 'recovery_route'),
    )
