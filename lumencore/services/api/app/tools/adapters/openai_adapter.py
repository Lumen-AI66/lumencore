from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...secrets.secret_manager import OPENAI_API_KEY_ENV, SecretManager
from .base import ToolAdapter
from ..models import ToolDefinition, ToolRequest

if TYPE_CHECKING:
    from ..service import ToolExecutionContext


class OpenAIToolAdapter(ToolAdapter):
    def supports(self, tool_definition: ToolDefinition) -> bool:
        return (
            tool_definition.tool_name == "tool.openai.complete"
            and tool_definition.connector_name == "openai"
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
            raise RuntimeError("provider_error:unsupported openai tool definition")

        try:
            from openai import OpenAI
        except Exception as exc:
            raise RuntimeError("adapter_not_configured:openai package is not installed") from exc

        secret_manager = SecretManager()
        if not secret_manager.has_env_secret(OPENAI_API_KEY_ENV):
            raise RuntimeError(f"missing_secret:{OPENAI_API_KEY_ENV} is not configured")

        payload = dict(request.payload or {})
        prompt = str(payload.get("prompt") or payload.get("objective") or payload.get("query") or "").strip()
        if not prompt:
            raise ValueError("prompt is required")

        model = str(payload.get("model") or "gpt-4.1-mini").strip() or "gpt-4.1-mini"
        max_output_tokens = int(payload.get("max_output_tokens") or 700)
        client = OpenAI(api_key=secret_manager.get_env_secret(OPENAI_API_KEY_ENV))

        try:
            response = client.responses.create(
                model=model,
                input=prompt,
                max_output_tokens=max_output_tokens,
            )
        except Exception as exc:
            raise RuntimeError(f"provider_error:{exc}") from exc

        output_text = getattr(response, "output_text", None)
        if output_text is None and hasattr(response, "model_dump"):
            data = response.model_dump()
            output_text = self._extract_output_text(data)
            usage = data.get("usage") or {}
        else:
            data = response.model_dump() if hasattr(response, "model_dump") else {}
            usage = data.get("usage") or getattr(response, "usage", None) or {}

        if output_text is None:
            output_text = self._extract_output_text(data)
        if output_text is None:
            output_text = ""

        if hasattr(usage, "model_dump"):
            usage = usage.model_dump()
        total_tokens = int((usage or {}).get("total_tokens") or 0)
        input_tokens = int((usage or {}).get("input_tokens") or 0)
        output_tokens = int((usage or {}).get("output_tokens") or 0)

        return {
            "provider": "openai",
            "model": model,
            "output_text": str(output_text),
            "tokens_used": total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    def _extract_output_text(self, data: dict[str, Any]) -> str | None:
        output = data.get("output") or []
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content") or []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") in {"output_text", "text"} and block.get("text"):
                    parts.append(str(block["text"]))
        if parts:
            return "\n".join(parts).strip()
        return None

