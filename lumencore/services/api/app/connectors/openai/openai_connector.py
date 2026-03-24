from __future__ import annotations

from ..base.connector import Connector
from ...secrets.secret_manager import OPENAI_API_KEY_ENV


class OpenAIConnector(Connector):
    connector_name = "openai"
    connector_type = "llm"

    def supported_actions(self) -> tuple[str, ...]:
        return ("complete",)

    def resolve_operation(self, payload: dict) -> str:
        operation = super().resolve_operation(payload)
        return operation or "complete"

    def required_secret_names(
        self,
        payload: dict,
        *,
        operation: str,
        provider: str | None,
        context: dict | None = None,
    ) -> tuple[str, ...]:
        _ = payload, operation, provider, context
        return (OPENAI_API_KEY_ENV,)

    def execute(self, payload: dict, tenant_id: str, agent_id: str | None = None, context: dict | None = None):
        _ = payload, tenant_id, agent_id, context
        raise RuntimeError("provider_error:openai connector executes through the governed tool adapter")

