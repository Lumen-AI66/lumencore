from __future__ import annotations


class ToolRegistryError(Exception):
    """Base error for tool registration and lookup failures."""


class DuplicateToolRegistrationError(ToolRegistryError):
    """Raised when a tool name is registered more than once."""


class UnknownToolError(ToolRegistryError):
    """Raised when a requested tool name is not present in the registry."""


class InvalidToolDefinitionError(ToolRegistryError):
    """Raised when a tool definition is structurally invalid."""
