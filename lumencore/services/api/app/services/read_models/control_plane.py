from __future__ import annotations

from typing import Any

from ..execution import build_execution_lineage, build_execution_truth
from ..operator_queue import classify_operator_queue_bucket


def _status_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, 'value', value))


def build_command_read_model(command_run, execution_task=None) -> dict[str, Any]:
    truth = build_execution_truth(command_run, execution_task)
    lineage = build_execution_lineage(command_run, execution_task)
    return {
        'id': command_run.id,
        'tenant_id': command_run.tenant_id,
        'command_text': command_run.command_text,
        'normalized_command': command_run.normalized_command,
        'intent': command_run.intent,
        'planned_task_type': command_run.planned_task_type,
        'requested_mode': command_run.requested_mode,
        'selected_agent_id': str(command_run.selected_agent_id) if command_run.selected_agent_id else None,
        'status': _status_string(command_run.status),
        'execution_decision': command_run.execution_decision,
        'approval_required': command_run.approval_required,
        'approval_status': command_run.approval_status,
        'policy_reason': command_run.policy_reason,
        'queue_bucket': classify_operator_queue_bucket(command_run),
        'last_control_action': command_run.last_control_action,
        'last_control_reason': command_run.last_control_reason,
        'cancelled_at': command_run.cancelled_at,
        'retried_from_id': command_run.retried_from_id,
        'job_id': command_run.job_id,
        'request_id': truth.get('request_id'),
        'run_id': truth.get('run_id'),
        'correlation_id': truth.get('correlation_id'),
        'connector_name': truth.get('connector_name'),
        'error_code': truth.get('error_code'),
        'execution_lineage': lineage,
        'execution_task_id': truth.get('execution_task_id'),
        'execution_task_status': truth.get('execution_task_status'),
        'result': truth.get('result'),
        'result_summary': truth.get('result_summary'),
        'started_at': command_run.started_at,
        'finished_at': command_run.finished_at,
        'created_at': command_run.created_at,
        'updated_at': command_run.updated_at,
    }


def build_execution_task_read_model(execution_task, command_run=None, execution_control=None, execution_policy=None) -> dict[str, Any]:
    truth = build_execution_truth(command_run, execution_task)
    lineage = build_execution_lineage(command_run, execution_task)
    return {
        'task_id': execution_task.task_id,
        'tenant_id': execution_task.tenant_id,
        'command_id': execution_task.command_id,
        'agent_id': execution_task.agent_id,
        'agent_type': execution_task.agent_type,
        'task_type': execution_task.task_type,
        'status': execution_task.status,
        'priority': execution_task.priority,
        'retries': execution_task.retries,
        'max_retries': execution_task.max_retries,
        'available_at': execution_task.available_at,
        'started_at': execution_task.started_at,
        'updated_at': execution_task.updated_at,
        'finished_at': execution_task.finished_at,
        'error': truth.get('error') or execution_task.error,
        'execution_task_id': truth.get('execution_task_id') or execution_task.task_id,
        'execution_task_status': truth.get('execution_task_status') or _status_string(execution_task.status),
        'result': truth.get('result'),
        'agent_result': truth.get('agent_result'),
        'connector_name': truth.get('connector_name'),
        'error_code': truth.get('error_code'),
        'execution_control': execution_control,
        'execution_policy': execution_policy,
        'execution_lineage': lineage,
        'result_summary': truth.get('result_summary'),
    }
