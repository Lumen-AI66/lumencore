from .base import ToolAdapter
from .openai_adapter import OpenAIToolAdapter
from .search_adapter import SearchToolAdapter
from .system_adapter import SystemToolAdapter
from ..models import ToolDefinition


_DEFAULT_ADAPTERS: tuple[ToolAdapter, ...] = (
    SystemToolAdapter(),
    SearchToolAdapter(),
    OpenAIToolAdapter(),
)


def resolve_tool_adapter(tool_definition: ToolDefinition) -> ToolAdapter | None:
    for adapter in _DEFAULT_ADAPTERS:
        if adapter.supports(tool_definition):
            return adapter
    return None


__all__ = [
    "ToolAdapter",
    "OpenAIToolAdapter",
    "SearchToolAdapter",
    "SystemToolAdapter",
    "resolve_tool_adapter",
]

