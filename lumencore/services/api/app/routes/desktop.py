"""Desktop execution queue — allows the laptop agent to poll and execute commands."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.orm import Session

from ..db import Base, session_scope

router = APIRouter(prefix="/api/desktop", tags=["desktop"])


# --- Model ---

class DesktopTask(Base):
    __tablename__ = "desktop_tasks"
    __table_args__ = {"extend_existing": True}

    id = Column(String(36), primary_key=True)
    command = Column(Text, nullable=False)
    status = Column(String(32), default="pending")   # pending | running | done | failed
    result = Column(Text, nullable=True)
    telegram_chat_id = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# --- Schemas ---

class QueueRequest(BaseModel):
    command: str
    telegram_chat_id: str | None = None


class TaskResponse(BaseModel):
    id: str
    command: str
    status: str
    result: str | None = None
    created_at: datetime


class ResultRequest(BaseModel):
    result: str
    status: str = "done"   # done | failed


# --- Routes ---

@router.post("/queue", response_model=TaskResponse, status_code=202)
def queue_command(req: QueueRequest):
    """Queue a command for the desktop agent to execute."""
    with session_scope() as session:
        task = DesktopTask(
            id=str(uuid.uuid4()),
            command=req.command.strip(),
            status="pending",
            telegram_chat_id=req.telegram_chat_id,
        )
        session.add(task)
        session.flush()
        return TaskResponse(
            id=task.id,
            command=task.command,
            status=task.status,
            result=task.result,
            created_at=task.created_at,
        )


@router.get("/queue/next", response_model=TaskResponse | None)
def poll_next():
    """Desktop agent polls this to get the next pending command."""
    with session_scope() as session:
        task = (
            session.query(DesktopTask)
            .filter(DesktopTask.status == "pending")
            .order_by(DesktopTask.created_at.asc())
            .first()
        )
        if not task:
            return None
        task.status = "running"
        task.updated_at = datetime.now(timezone.utc)
        session.flush()
        return TaskResponse(
            id=task.id,
            command=task.command,
            status=task.status,
            result=task.result,
            created_at=task.created_at,
        )


@router.post("/queue/{task_id}/result", response_model=TaskResponse)
def submit_result(task_id: str, req: ResultRequest):
    """Desktop agent submits the execution result."""
    with session_scope() as session:
        task = session.query(DesktopTask).filter(DesktopTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="task not found")
        task.result = req.result
        task.status = req.status
        task.updated_at = datetime.now(timezone.utc)
        session.flush()
        return TaskResponse(
            id=task.id,
            command=task.command,
            status=task.status,
            result=task.result,
            created_at=task.created_at,
        )


@router.get("/queue/{task_id}", response_model=TaskResponse)
def get_task(task_id: str):
    """Check status of a queued task."""
    with session_scope() as session:
        task = session.query(DesktopTask).filter(DesktopTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="task not found")
        return TaskResponse(
            id=task.id,
            command=task.command,
            status=task.status,
            result=task.result,
            created_at=task.created_at,
        )
