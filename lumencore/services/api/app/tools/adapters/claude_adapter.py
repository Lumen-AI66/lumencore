from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...secrets.secret_manager import SecretManager
from .base import ToolAdapter
from ..models import ToolDefinition, ToolRequest

if TYPE_CHECKING:
    from ..service import ToolExecutionContext

ANTHROPIC_API_KEY_ENV = "LUMENCORE_ANTHROPIC_API_KEY"

OPENCLAW_SYSTEM_PROMPT = """You are Openclaw — the primary AI executor of Lumencore, a modular AI control plane.

You receive operator commands and execute them with precision. Your role:
- Understand what the operator wants to do
- Execute the command or provide the requested output
- Be direct, actionable, and concise
- For analytical tasks: analyze and report findings
- For automation tasks: describe the exact steps you would take or have taken
- For information requests: provide accurate, structured information
- Always respond in the same language the operator used

You have awareness of the Lumencore system: agents, tasks, workflows, jobs, connectors, and the control plane.
Format responses clearly. Use markdown where helpful."""


class ClaudeToolAdapter(ToolAdapter):
    def supports(self, tool_definition: ToolDefinition) -> bool:
        return (
            tool_definition.tool_name == "tool.claude.complete"
            and tool_definition.connector_name == "claude"
            and tool_definition.action == "complete"
        )

    def execute_tool(
        self,
        tool_definition: ToolDefinition,
        request: ToolRequest,
        context: ToolExecutionContext,
    ) -> dict[str, Any]:
        _ = context
        if not self.supports(tool_definition):
            raise RuntimeError("provider_error:unsupported claude tool definition")

        try:
            import anthropic
        except Exception as exc:
            raise RuntimeError("adapter_not_configured:anthropic package is not installed") from exc

        secret_manager = SecretManager()
        if not secret_manager.has_env_secret(ANTHROPIC_API_KEY_ENV):
            raise RuntimeError(f"missing_secret:{ANTHROPIC_API_KEY_ENV} is not configured")

        payload = dict(request.payload or {})
        prompt = str(payload.get("prompt") or payload.get("objective") or payload.get("query") or "").strip()
        if not prompt:
            raise ValueError("prompt is required")

        model = str(payload.get("model") or "claude-haiku-4-5-20251001").strip()
        max_tokens = int(payload.get("max_tokens") or payload.get("max_output_tokens") or 1024)
        system_prompt = str(payload.get("system") or OPENCLAW_SYSTEM_PROMPT).strip()

        client = anthropic.Anthropic(api_key=secret_manager.get_env_secret(ANTHROPIC_API_KEY_ENV))

        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise RuntimeError(f"provider_error:{exc}") from exc

        output_text = ""
        if response.content:
            parts = [block.text for block in response.content if hasattr(block, "text")]
            output_text = "\n".join(parts).strip()

        usage = response.usage
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0

        return {
            "provider": "anthropic",
            "model": model,
            "output_text": output_text,
            "tokens_used": input_tokens + output_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
