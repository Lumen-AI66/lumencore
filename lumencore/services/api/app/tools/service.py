from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any

from .adapters import resolve_tool_adapter
from .audit import (
    log_tool_denied,
    log_tool_failed,
    log_tool_requested,
    log_tool_success,
    log_tool_timeout,
)
from .models import ToolDefinition, ToolRequest, ToolResult, ToolResultStatus
from .policy import evaluate_tool_policy, resolve_tool_definition
from .registry import ToolRegistry, get_tool_registry


@dataclass(frozen=True)
class ToolExecutionContext:
    tenant_id: str
    project_id: str | None
    command_id: str | None
    agent_id: str
    run_id: str | None
    correlation_id: str
    request_id: str
    policy_reference: str | None = None


ToolExecutor = Callable[[ToolDefinition, ToolRequest, ToolExecutionContext], dict[str, Any] | None]
ToolExecutorResolver = Callable[[ToolDefinition], ToolExecutor | None]
ToolAuditWriter = Callable[[dict], None]


class ToolMediationService:
    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        executor_resolver: ToolExecutorResolver | None = None,
        audit_writer: ToolAuditWriter | None = None,
    ) -> None:
        self._registry = registry or get_tool_registry()
        self._executor_resolver = executor_resolver or self._resolve_executor_from_adapter
        self._audit_writer = audit_writer

    def mediate(
        self,
        request: ToolRequest,
        *,
        tenant_id: str = "owner",
        project_id: str | None = None,
        allowed_agent_ids: set[str] | None = None,
        allowed_project_ids: set[str] | None = None,
    ) -> ToolResult:
        definition = resolve_tool_definition(request.tool_name, self._registry)
        requested_event = log_tool_requested(
            tenant_id=tenant_id,
            tool_name=definition.tool_name if definition else request.tool_name,
            connector_name=definition.connector_name if definition else request.connector_name,
            action=definition.action if definition else request.action,
            agent_id=request.agent_id,
            request_id=request.request_id,
            command_id=request.command_id,
            run_id=request.run_id,
            correlation_id=request.correlation_id,
        )
        self._emit_audit_event(requested_event)

        if definition is None:
            result = self._build_result(
                request,
                status=ToolResultStatus.denied,
                tool_name=request.tool_name,
                connector_name=request.connector_name,
                action=request.action,
                error_code="tool_not_registered",
                error_message="tool is not registered",
                policy_reference="tool.policy.tool_not_registered",
            )
            denied_event = log_tool_denied(
                tenant_id=tenant_id,
                tool_name=result.tool_name,
                connector_name=result.connector_name,
                agent_id=result.agent_id,
                request_id=result.request_id,
                command_id=result.command_id,
                run_id=result.run_id,
                correlation_id=result.correlation_id,
                policy_reference=result.policy_decision_reference,
                error_code=result.error_code,
            )
            self._emit_audit_event(denied_event)
            return result

        decision = evaluate_tool_policy(
            request=request,
            tenant_id=tenant_id,
            project_id=project_id,
            registry=self._registry,
            allowed_agent_ids=allowed_agent_ids,
            allowed_project_ids=allowed_project_ids,
        )
        if not decision.allowed:
            result = self._build_result(
                request,
                status=ToolResultStatus.denied,
                tool_name=definition.tool_name,
                connector_name=definition.connector_name,
                action=definition.action,
                error_code=self._error_code_from_reference(decision.policy_reference),
                error_message=decision.reason,
                policy_reference=decision.policy_reference,
            )
            denied_event = log_tool_denied(
                tenant_id=tenant_id,
                tool_name=result.tool_name,
                connector_name=result.connector_name,
                agent_id=result.agent_id,
                request_id=result.request_id,
                command_id=result.command_id,
                run_id=result.run_id,
                correlation_id=result.correlation_id,
                policy_reference=result.policy_decision_reference,
                error_code=result.error_code,
            )
            self._emit_audit_event(denied_event)
            return result

        executor = self._executor_resolver(definition)
        if executor is None:
            result = self._build_result(
                request,
                status=ToolResultStatus.failed,
                tool_name=definition.tool_name,
                connector_name=definition.connector_name,
                action=definition.action,
                error_code="adapter_not_configured",
                error_message="tool execution is not available",
                policy_reference=decision.policy_reference,
            )
            failed_event = log_tool_failed(
                tenant_id=tenant_id,
                tool_name=result.tool_name,
                connector_name=result.connector_name,
                agent_id=result.agent_id,
                request_id=result.request_id,
                command_id=result.command_id,
                run_id=result.run_id,
                correlation_id=result.correlation_id,
                policy_reference=result.policy_decision_reference,
                error_code=result.error_code,
                duration_ms=result.duration_ms,
            )
            self._emit_audit_event(failed_event)
            return result

        context = ToolExecutionContext(
            tenant_id=tenant_id,
            project_id=project_id,
            command_id=request.command_id,
            agent_id=request.agent_id,
            run_id=request.run_id,
            correlation_id=request.correlation_id,
            request_id=request.request_id,
            policy_reference=decision.policy_reference,
        )

        started = monotonic()
        try:
            output = executor(definition, request, context)
        except ValueError as exc:
            result = self._build_result(
                request,
                status=ToolResultStatus.failed,
                tool_name=definition.tool_name,
                connector_name=definition.connector_name,
                action=definition.action,
                error_code="validation_failed",
                error_message=str(exc),
                duration_ms=self._duration_ms(started),
                policy_reference=decision.policy_reference,
            )
            failed_event = log_tool_failed(
                tenant_id=tenant_id,
                tool_name=result.tool_name,
                connector_name=result.connector_name,
                agent_id=result.agent_id,
                request_id=result.request_id,
                command_id=result.command_id,
                run_id=result.run_id,
                correlation_id=result.correlation_id,
                policy_reference=result.policy_decision_reference,
                error_code=result.error_code,
                duration_ms=result.duration_ms,
            )
            self._emit_audit_event(failed_event)
            return result
        except RuntimeError as exc:
            code, message, status = self._classify_runtime_error(exc)
            result = self._build_result(
                request,
                status=status,
                tool_name=definition.tool_name,
                connector_name=definition.connector_name,
                action=definition.action,
                error_code=code,
                error_message=message,
                duration_ms=self._duration_ms(started),
                policy_reference=decision.policy_reference,
            )
            audit_event = log_tool_timeout if status == ToolResultStatus.timeout else log_tool_failed
            emitted = audit_event(
                tenant_id=tenant_id,
                tool_name=result.tool_name,
                connector_name=result.connector_name,
                agent_id=result.agent_id,
                request_id=result.request_id,
                command_id=result.command_id,
                run_id=result.run_id,
                correlation_id=result.correlation_id,
                policy_reference=result.policy_decision_reference,
                error_code=result.error_code,
                duration_ms=result.duration_ms,
            )
            self._emit_audit_event(emitted)
            return result
        except TimeoutError:
            result = self._build_result(
                request,
                status=ToolResultStatus.timeout,
                tool_name=definition.tool_name,
                connector_name=definition.connector_name,
                action=definition.action,
                error_code="tool_timeout",
                error_message="tool execution timed out",
                duration_ms=self._duration_ms(started),
                policy_reference=decision.policy_reference,
            )
            timeout_event = log_tool_timeout(
                tenant_id=tenant_id,
                tool_name=result.tool_name,
                connector_name=result.connector_name,
                agent_id=result.agent_id,
                request_id=result.request_id,
                command_id=result.command_id,
                run_id=result.run_id,
                correlation_id=result.correlation_id,
                policy_reference=result.policy_decision_reference,
                duration_ms=result.duration_ms,
            )
            self._emit_audit_event(timeout_event)
            return result
        except Exception:
            result = self._build_result(
                request,
                status=ToolResultStatus.failed,
                tool_name=definition.tool_name,
                connector_name=definition.connector_name,
                action=definition.action,
                error_code="tool_execution_failed",
                error_message="tool execution failed",
                duration_ms=self._duration_ms(started),
                policy_reference=decision.policy_reference,
            )
            failed_event = log_tool_failed(
                tenant_id=tenant_id,
                tool_name=result.tool_name,
                connector_name=result.connector_name,
                agent_id=result.agent_id,
                request_id=result.request_id,
                command_id=result.command_id,
                run_id=result.run_id,
                correlation_id=result.correlation_id,
                policy_reference=result.policy_decision_reference,
                error_code=result.error_code,
                duration_ms=result.duration_ms,
            )
            self._emit_audit_event(failed_event)
            return result

        result = self._build_result(
            request,
            status=ToolResultStatus.success,
            tool_name=definition.tool_name,
            connector_name=definition.connector_name,
            action=definition.action,
            output=self._normalize_output(output),
            duration_ms=self._duration_ms(started),
            policy_reference=decision.policy_reference,
        )
        success_event = log_tool_success(
            tenant_id=tenant_id,
            tool_name=result.tool_name,
            connector_name=result.connector_name,
            agent_id=result.agent_id,
            request_id=result.request_id,
            command_id=result.command_id,
            run_id=result.run_id,
            correlation_id=result.correlation_id,
            policy_reference=result.policy_decision_reference,
            duration_ms=result.duration_ms,
        )
        self._emit_audit_event(success_event)
        return result

    def _emit_audit_event(self, event: dict) -> None:
        if self._audit_writer is not None:
            self._audit_writer(event)

    @staticmethod
    def _resolve_executor_from_adapter(definition: ToolDefinition) -> ToolExecutor | None:
        adapter = resolve_tool_adapter(definition)
        if adapter is None:
            return None
        return lambda tool_definition, request, context: adapter.execute_tool(tool_definition, request, context)

    @staticmethod
    def _normalize_output(output: dict[str, Any] | None) -> dict[str, Any]:
        if output is None:
            return {}
        if not isinstance(output, dict):
            return {"result": str(output)}
        return output

    @staticmethod
    def _duration_ms(started: float) -> float:
        return round((monotonic() - started) * 1000, 2)

    @staticmethod
    def _error_code_from_reference(policy_reference: str) -> str:
        tail = (policy_reference or "tool.policy.denied").rsplit(".", 1)[-1].strip().lower()
        return tail or "denied"

    @staticmethod
    def _classify_runtime_error(exc: RuntimeError) -> tuple[str, str, ToolResultStatus]:
        raw = str(exc or "").strip() or "tool execution failed"
        code, separator, message = raw.partition(":")
        normalized_code = (code or "tool_execution_failed").strip().lower()
        normalized_message = (message if separator else raw).strip() or raw
        if normalized_code == "timeout":
            return "tool_timeout", normalized_message, ToolResultStatus.timeout
        return normalized_code, normalized_message, ToolResultStatus.failed

    @staticmethod
    def _build_result(
        request: ToolRequest,
        *,
        status: ToolResultStatus,
        tool_name: str,
        connector_name: str,
        action: str,
        output: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        duration_ms: float | None = None,
        policy_reference: str | None = None,
        audit_reference: str | None = None,
    ) -> ToolResult:
        return ToolResult(
            request_id=request.request_id,
            command_id=request.command_id,
            agent_id=request.agent_id,
            run_id=request.run_id,
            status=status,
            tool_name=tool_name,
            connector_name=connector_name,
            action=action,
            output=output,
            error_code=error_code,
            error_message=error_message,
            duration_ms=duration_ms,
            correlation_id=request.correlation_id,
            audit_reference=audit_reference,
            policy_decision_reference=policy_reference,
        )


def create_tool_mediation_service(
    *,
    registry: ToolRegistry | None = None,
    executor_resolver: ToolExecutorResolver | None = None,
    audit_writer: ToolAuditWriter | None = None,
) -> ToolMediationService:
    return ToolMediationService(registry=registry, executor_resolver=executor_resolver, audit_writer=audit_writer)
