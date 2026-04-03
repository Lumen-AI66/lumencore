from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from ..db import session_scope

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _row(r: Any) -> dict:
    return dict(r._mapping)


class WorkspaceCreate(BaseModel):
    name: str
    description: str = ""
    config: dict[str, Any] = {}


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    config: dict[str, Any] | None = None


class WorkflowCreate(BaseModel):
    name: str
    trigger_type: str = "manual"
    trigger_config: dict[str, Any] = {}
    steps: list[dict[str, Any]] = []


@router.get("")
def list_workspaces():
    with session_scope() as session:
        rows = session.execute(
            text("SELECT * FROM public.workspaces ORDER BY created_at DESC")
        ).fetchall()
    return [_row(r) for r in rows]


@router.post("", status_code=201)
def create_workspace(body: WorkspaceCreate):
    wid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        session.execute(
            text(
                """
                INSERT INTO public.workspaces (id, name, description, config_json, created_at, updated_at)
                VALUES (:id, :name, :description, :config::jsonb, :now, :now)
                """
            ),
            {
                "id": wid,
                "name": body.name,
                "description": body.description,
                "config": json.dumps(body.config),
                "now": now,
            },
        )
    return {"id": wid, "name": body.name}


@router.put("/{workspace_id}")
def update_workspace(workspace_id: str, body: WorkspaceUpdate):
    with session_scope() as session:
        row = session.execute(
            text("SELECT id FROM public.workspaces WHERE id = :id"),
            {"id": workspace_id},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workspace not found")

        updates = []
        params: dict[str, Any] = {"id": workspace_id, "now": datetime.now(timezone.utc)}
        if body.name is not None:
            updates.append("name = :name")
            params["name"] = body.name
        if body.description is not None:
            updates.append("description = :description")
            params["description"] = body.description
        if body.status is not None:
            updates.append("status = :status")
            params["status"] = body.status

        if updates:
            updates.append("updated_at = :now")
            session.execute(
                text(f"UPDATE public.workspaces SET {', '.join(updates)} WHERE id = :id"),
                params,
            )
    return {"id": workspace_id, "updated": True}


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: str):
    with session_scope() as session:
        result = session.execute(
            text("DELETE FROM public.workspaces WHERE id = :id"),
            {"id": workspace_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Workspace not found")


@router.get("/{workspace_id}/workflows")
def list_workflows(workspace_id: str):
    with session_scope() as session:
        ws = session.execute(
            text("SELECT id FROM public.workspaces WHERE id = :id"),
            {"id": workspace_id},
        ).fetchone()
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace not found")
        rows = session.execute(
            text(
                "SELECT * FROM public.workspace_workflows WHERE workspace_id = :wid ORDER BY created_at DESC"
            ),
            {"wid": workspace_id},
        ).fetchall()
    return [_row(r) for r in rows]


@router.post("/{workspace_id}/workflows", status_code=201)
def create_workflow(workspace_id: str, body: WorkflowCreate):
    with session_scope() as session:
        ws = session.execute(
            text("SELECT id FROM public.workspaces WHERE id = :id"),
            {"id": workspace_id},
        ).fetchone()
        if not ws:
            raise HTTPException(status_code=404, detail="Workspace not found")

        wf_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        session.execute(
            text(
                """
                INSERT INTO public.workspace_workflows
                    (id, workspace_id, name, trigger_type, trigger_config, steps_json, created_at, updated_at)
                VALUES
                    (:id, :workspace_id, :name, :trigger_type, :trigger_config::jsonb, :steps_json::jsonb, :now, :now)
                """
            ),
            {
                "id": wf_id,
                "workspace_id": workspace_id,
                "name": body.name,
                "trigger_type": body.trigger_type,
                "trigger_config": json.dumps(body.trigger_config),
                "steps_json": json.dumps(body.steps),
                "now": now,
            },
        )
    return {"id": wf_id, "workspace_id": workspace_id, "name": body.name}


@router.post("/{workspace_id}/workflows/{workflow_id}/run")
def run_workflow(workspace_id: str, workflow_id: str):
    with session_scope() as session:
        row = session.execute(
            text(
                "SELECT * FROM public.workspace_workflows WHERE id = :id AND workspace_id = :wid"
            ),
            {"id": workflow_id, "wid": workspace_id},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workflow not found")
        session.execute(
            text(
                "UPDATE public.workspace_workflows SET last_run_at = :now WHERE id = :id"
            ),
            {"now": datetime.now(timezone.utc), "id": workflow_id},
        )
    return {"ok": True, "workflow_id": workflow_id, "message": "Workflow triggered (manual run)"}
