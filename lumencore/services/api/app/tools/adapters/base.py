from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..models import ToolDefinition, ToolRequest

if TYPE_CHECKING:
    from ..service import ToolExecutionContext


class ToolAdapter(ABC):
    @abstractmethod
    def supports(self, tool_definition: ToolDefinition) -> bool:
        raise NotImplementedError

    @abstractmethod
    def execute_tool(
        self,
        tool_definition: ToolDefinition,
        request: ToolRequest,
        context: ToolExecutionContext,
    ) -> dict:
        raise NotImplementedError
