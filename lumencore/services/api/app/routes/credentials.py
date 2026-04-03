from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from ..db import session_scope

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


def _obfuscate(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def _deobfuscate(value: str) -> str:
    try:
        return base64.b64decode(value.encode()).decode()
    except Exception:
        return value


def _mask(value_encrypted: str) -> str:
    try:
        raw = _deobfuscate(value_encrypted)
        if len(raw) <= 4:
            return "****"
        return "****" + raw[-4:]
    except Exception:
        return "****"


class CredentialCreate(BaseModel):
    name: str
    service: str
    credential_type: str
    value: str
    metadata: dict[str, Any] = {}


class CredentialUpdate(BaseModel):
    name: str | None = None
    service: str | None = None
    credential_type: str | None = None
    value: str | None = None
    metadata: dict[str, Any] | None = None


def _row_to_dict(row: Any, mask_value: bool = True) -> dict:
    d = dict(row._mapping)
    if mask_value:
        d["value_masked"] = _mask(d.get("value_encrypted", ""))
        del d["value_encrypted"]
    return d


@router.get("")
def list_credentials():
    with session_scope() as session:
        rows = session.execute(
            text("SELECT * FROM public.credential_vault ORDER BY created_at DESC")
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("", status_code=201)
def create_credential(body: CredentialCreate):
    cid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        session.execute(
            text(
                """
                INSERT INTO public.credential_vault
                    (id, name, service, credential_type, value_encrypted, metadata_json, created_at, updated_at)
                VALUES
                    (:id, :name, :service, :credential_type, :value_encrypted, :metadata_json::jsonb, :now, :now)
                """
            ),
            {
                "id": cid,
                "name": body.name,
                "service": body.service,
                "credential_type": body.credential_type,
                "value_encrypted": _obfuscate(body.value),
                "metadata_json": str(body.metadata).replace("'", '"'),
                "now": now,
            },
        )
    return {"id": cid, "name": body.name, "service": body.service, "credential_type": body.credential_type}


@router.put("/{credential_id}")
def update_credential(credential_id: str, body: CredentialUpdate):
    with session_scope() as session:
        row = session.execute(
            text("SELECT id FROM public.credential_vault WHERE id = :id"),
            {"id": credential_id},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Credential not found")

        updates = []
        params: dict[str, Any] = {"id": credential_id, "now": datetime.now(timezone.utc)}
        if body.name is not None:
            updates.append("name = :name")
            params["name"] = body.name
        if body.service is not None:
            updates.append("service = :service")
            params["service"] = body.service
        if body.credential_type is not None:
            updates.append("credential_type = :credential_type")
            params["credential_type"] = body.credential_type
        if body.value is not None:
            updates.append("value_encrypted = :value_encrypted")
            params["value_encrypted"] = _obfuscate(body.value)

        if updates:
            updates.append("updated_at = :now")
            session.execute(
                text(f"UPDATE public.credential_vault SET {', '.join(updates)} WHERE id = :id"),
                params,
            )
    return {"id": credential_id, "updated": True}


@router.delete("/{credential_id}", status_code=204)
def delete_credential(credential_id: str):
    with session_scope() as session:
        result = session.execute(
            text("DELETE FROM public.credential_vault WHERE id = :id"),
            {"id": credential_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Credential not found")


@router.post("/test/{credential_id}")
def test_credential(credential_id: str):
    with session_scope() as session:
        row = session.execute(
            text("SELECT * FROM public.credential_vault WHERE id = :id"),
            {"id": credential_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")
    # Basic connectivity test — for now just confirm it can be decoded
    try:
        _deobfuscate(row._mapping["value_encrypted"])
        return {"ok": True, "message": "Credential is readable"}
    except Exception as e:
        return {"ok": False, "message": str(e)}
