from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.connectors import ConnectorItem, ConnectorListResponse, ConnectorStatusResponse
from ..services.connectors import get_connector_registry_item, get_connector_status, list_connector_registry_items


router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@router.get("", response_model=ConnectorListResponse)
def list_connectors() -> ConnectorListResponse:
    return list_connector_registry_items()


@router.get("/{connector_key}", response_model=ConnectorItem)
def get_connector(connector_key: str) -> ConnectorItem:
    item = get_connector_registry_item(connector_key)
    if item is None:
        raise HTTPException(status_code=404, detail="connector not found")
    return item


@router.get("/{connector_key}/status", response_model=ConnectorStatusResponse)
def get_connector_runtime_status(connector_key: str) -> ConnectorStatusResponse:
    status = get_connector_status(connector_key)
    if status is None:
        raise HTTPException(status_code=404, detail="connector not found")
    return status
