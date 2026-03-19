from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.nodes import NodeItem, NodeListResponse, NodeStatusResponse
from ..services.nodes import get_node, get_node_status, list_nodes


router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("", response_model=NodeListResponse)
def list_nodes_route() -> NodeListResponse:
    return list_nodes()


@router.get("/{node_key}", response_model=NodeItem)
def get_node_route(node_key: str) -> NodeItem:
    item = get_node(node_key)
    if item is None:
        raise HTTPException(status_code=404, detail="node not found")
    return item


@router.get("/{node_key}/status", response_model=NodeStatusResponse)
def get_node_status_route(node_key: str) -> NodeStatusResponse:
    status = get_node_status(node_key)
    if status is None:
        raise HTTPException(status_code=404, detail="node not found")
    return status
