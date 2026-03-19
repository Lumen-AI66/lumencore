from __future__ import annotations

from abc import ABC, abstractmethod


class Connector(ABC):
    connector_name: str
    connector_type: str
    connector_source: str = "builtin"

    def resolve_operation(self, payload: dict) -> str:
        return str((payload or {}).get("operation") or (payload or {}).get("action") or "").strip()

    def resolve_provider(self, payload: dict, context: dict | None = None) -> str | None:
        _ = context
        value = str((payload or {}).get("provider") or "").strip().lower()
        return value or None

    def provider_required(self, operation: str) -> bool:
        _ = operation
        return False

    def required_secret_names(
        self,
        payload: dict,
        *,
        operation: str,
        provider: str | None,
        context: dict | None = None,
    ) -> tuple[str, ...]:
        _ = payload, operation, provider, context
        return ()

    @abstractmethod
    def execute(
        self,
        payload: dict,
        tenant_id: str,
        agent_id: str | None = None,
        context: dict | None = None,
    ):
        raise NotImplementedError()

    def validate(self, payload: dict):
        return True

    def supported_actions(self) -> tuple[str, ...]:
        return ()
