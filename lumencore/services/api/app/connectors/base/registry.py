from __future__ import annotations

from dataclasses import dataclass, field

from .connector import Connector


@dataclass
class ConnectorRegistry:
    _connectors: dict[str, Connector] = field(default_factory=dict)

    def register_connector(self, connector: Connector) -> None:
        name = getattr(connector, "connector_name", "").strip()
        if not name:
            raise ValueError("connector_name is required")
        self._connectors[name] = connector

    def get_connector(self, name: str) -> Connector:
        key = (name or "").strip()
        if key not in self._connectors:
            raise KeyError(f"connector not registered: {key}")
        return self._connectors[key]

    def list_connectors(self) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for name in sorted(self._connectors):
            connector = self._connectors[name]
            items.append(
                {
                    "connector_name": connector.connector_name,
                    "connector_type": connector.connector_type,
                }
            )
        return items

    def list_connector_instances(self) -> list[Connector]:
        return [self._connectors[name] for name in sorted(self._connectors)]


_REGISTRY = ConnectorRegistry()


def register_connector(connector: Connector) -> None:
    _REGISTRY.register_connector(connector)


def get_connector(name: str) -> Connector:
    return _REGISTRY.get_connector(name)


def list_connectors() -> list[dict[str, str]]:
    return _REGISTRY.list_connectors()


def list_connector_instances() -> list[Connector]:
    return _REGISTRY.list_connector_instances()

def get_registry() -> ConnectorRegistry:
    return _REGISTRY
