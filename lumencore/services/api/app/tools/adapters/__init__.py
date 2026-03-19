from .base import ToolAdapter
from .search_adapter import SearchToolAdapter
from .system_adapter import SystemToolAdapter
from ..models import ToolDefinition


_DEFAULT_ADAPTERS: tuple[ToolAdapter, ...] = (
    SystemToolAdapter(),
    SearchToolAdapter(),
)


def resolve_tool_adapter(tool_definition: ToolDefinition) -> ToolAdapter | None:
    for adapter in _DEFAULT_ADAPTERS:
        if adapter.supports(tool_definition):
            return adapter
    return None


__all__ = [
    "ToolAdapter",
    "SearchToolAdapter",
    "SystemToolAdapter",
    "resolve_tool_adapter",
]
