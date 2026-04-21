"""MEXC tool adapter — allows Openclaw to trade and monitor on MEXC exchange."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from .base import ToolAdapter
from ..models import ToolDefinition, ToolRequest
from ...connectors.mexc.mexc_connector import MexcConnector, MEXC_API_KEY_ENV, MEXC_API_SECRET_ENV
from ...secrets.secret_manager import SecretManager

if TYPE_CHECKING:
    from ..service import ToolExecutionContext

MEXC_ACTIONS = {
    "mexc.account.balance",
    "mexc.account.info",
    "mexc.market.ticker",
    "mexc.market.orderbook",
    "mexc.market.klines",
    "mexc.order.place",
    "mexc.order.cancel",
    "mexc.order.get",
    "mexc.order.list_open",
    "mexc.order.list_history",
    "mexc.position.list",
}


class MexcToolAdapter(ToolAdapter):
    def supports(self, tool_definition: ToolDefinition) -> bool:
        return tool_definition.tool_name in MEXC_ACTIONS

    def execute_tool(
        self,
        tool_definition: ToolDefinition,
        request: ToolRequest,
        context: "ToolExecutionContext",
    ) -> dict[str, Any]:
        secret_manager = SecretManager()
        api_key = secret_manager.get_env_secret(MEXC_API_KEY_ENV) if secret_manager.has_env_secret(MEXC_API_KEY_ENV) else ""
        api_secret = secret_manager.get_env_secret(MEXC_API_SECRET_ENV) if secret_manager.has_env_secret(MEXC_API_SECRET_ENV) else ""

        payload = dict(request.payload or {})
        # Strip "mexc." prefix to get the action for the connector
        payload["action"] = tool_definition.tool_name.replace("mexc.", "", 1)

        ctx = {"resolved_secrets": {
            MEXC_API_KEY_ENV: api_key,
            MEXC_API_SECRET_ENV: api_secret,
        }}

        connector = MexcConnector()
        return connector.execute(payload, tenant_id="system", context=ctx)
