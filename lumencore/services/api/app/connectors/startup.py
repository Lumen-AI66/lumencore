from __future__ import annotations

from .base.registry import ConnectorRegistry, get_registry
from .claude.claude_connector import ClaudeConnector
from .git.git_connector import GitConnector
from .n8n.n8n_connector import N8nConnector
from .openai.openai_connector import OpenAIConnector
from .search.search_connector import SearchConnector


def register_default_connectors(registry: ConnectorRegistry | None = None) -> ConnectorRegistry:
    """Register framework connectors. Intended to be called from API startup."""
    target = registry or get_registry()
    target.register_connector(GitConnector())
    target.register_connector(SearchConnector())
    target.register_connector(OpenAIConnector())
    target.register_connector(ClaudeConnector())
    target.register_connector(N8nConnector())
    return target

