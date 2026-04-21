"""n8n tool adapter — allows Openclaw to create and trigger n8n workflows."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import ToolAdapter
from ..models import ToolDefinition, ToolRequest
from ...connectors.n8n.n8n_connector import N8nConnector, N8N_API_TOKEN_ENV, N8N_BASE_URL_ENV, DEFAULT_N8N_URL
from ...secrets.secret_manager import SecretManager

if TYPE_CHECKING:
    from ..service import ToolExecutionContext

import os
import json
import urllib.request
import urllib.error

N8N_ACTIONS = {
    "n8n.workflow.list", "n8n.workflow.get", "n8n.workflow.create",
    "n8n.workflow.activate", "n8n.workflow.deactivate", "n8n.workflow.execute",
    "n8n.execution.list", "n8n.execution.get",
}


class N8nToolAdapter(ToolAdapter):
    def supports(self, tool_definition: ToolDefinition) -> bool:
        return tool_definition.tool_name in N8N_ACTIONS

    def execute_tool(
        self,
        tool_definition: ToolDefinition,
        request: ToolRequest,
        context: "ToolExecutionContext",
    ) -> dict[str, Any]:
        secret_manager = SecretManager()
        token = secret_manager.get_env_secret(N8N_API_TOKEN_ENV) if secret_manager.has_env_secret(N8N_API_TOKEN_ENV) else ""
        if not token:
            raise RuntimeError(f"missing_secret:{N8N_API_TOKEN_ENV} is not configured")

        base_url = os.environ.get(N8N_BASE_URL_ENV, DEFAULT_N8N_URL).rstrip("/")
        payload = dict(request.payload or {})
        action = tool_definition.tool_name  # e.g. "n8n.workflow.create"

        connector = N8nConnector()
        payload["action"] = action.replace("n8n.", "", 1)  # strip "n8n." prefix

        # Build resolved_secrets context for connector
        ctx = {"resolved_secrets": {N8N_API_TOKEN_ENV: token}}
        result = connector.execute(payload, tenant_id="system", context=ctx)
        return result
