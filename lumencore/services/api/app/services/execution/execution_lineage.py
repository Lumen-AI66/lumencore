from __future__ import annotations

from typing import Any

from .execution_truth import build_execution_truth


def _copy_dict(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    copied: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            copied[str(key)] = _copy_dict(item)
        elif isinstance(item, list):
            copied[str(key)] = list(item)
        else:
            copied[str(key)] = item
    return copied


def _summary_from(obj: Any) -> dict[str, Any]:
    return _copy_dict(getattr(obj, 'result_summary', None))


def _status_from(obj: Any) -> str | None:
    value = getattr(obj, 'status', None)
    if value is None:
        return None
    return str(getattr(value, 'value', value))


def _task_id_from(obj: Any) -> str | None:
    return getattr(obj, 'task_id', None)


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _task_payload_bits(task_summary: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    agent_execution = _copy_dict(task_summary.get('agent_execution') or {})
    result_payload = _copy_dict(agent_execution.get('result') or {})
    results = result_payload.get('results') or []
    first_result = _copy_dict(results[0]) if results and isinstance(results[0], dict) else {}
    output = _copy_dict(first_result.get('output') or {})
    return agent_execution, result_payload, first_result, output


def build_execution_lineage(command_run=None, execution_task=None) -> dict[str, Any]:
    truth = build_execution_truth(command_run, execution_task)
    command_summary = _summary_from(command_run)
    task_summary = _summary_from(execution_task)
    merged_summary = _copy_dict(command_summary)
    for key, value in task_summary.items():
        if value is not None:
            merged_summary[key] = value

    agent_execution, result_payload, first_result, tool_output = _task_payload_bits(task_summary)
    agent_result = truth.get('agent_result') or _copy_dict(merged_summary.get('agent_result'))

    command_id = _stringify(
        getattr(command_run, 'id', None)
        or getattr(execution_task, 'command_id', None)
        or merged_summary.get('command_id')
        or result_payload.get('command_id')
    )
    execution_task_id = _stringify(
        truth.get('execution_task_id')
        or merged_summary.get('execution_task_id')
        or _task_id_from(execution_task)
    )
    execution_task_status = _stringify(
        truth.get('execution_task_status')
        or merged_summary.get('execution_task_status')
        or merged_summary.get('scheduler_status')
        or _status_from(execution_task)
    )
    agent_id = _stringify(
        getattr(execution_task, 'agent_id', None)
        or first_result.get('agent_id')
        or getattr(command_run, 'selected_agent_id', None)
    )
    agent_type = _stringify(
        getattr(execution_task, 'agent_type', None)
        or agent_execution.get('agent_type')
    )
    agent_run_id = _stringify(
        agent_execution.get('agent_run_id')
        or merged_summary.get('agent_run_id')
        or truth.get('run_id')
    )
    tool_name = _stringify(
        first_result.get('tool_name')
        or merged_summary.get('tool_name')
    )
    connector_name = _stringify(
        truth.get('connector_name')
        or first_result.get('connector_name')
        or merged_summary.get('connector_name')
    )
    provider = _stringify(
        (agent_result or {}).get('provider')
        or tool_output.get('provider')
        or merged_summary.get('provider')
    )
    request_id = _stringify(
        truth.get('request_id')
        or first_result.get('request_id')
        or merged_summary.get('request_id')
    )
    run_id = _stringify(
        truth.get('run_id')
        or first_result.get('run_id')
        or merged_summary.get('run_id')
    )
    correlation_id = _stringify(
        truth.get('correlation_id')
        or first_result.get('correlation_id')
        or result_payload.get('command_id')
        or merged_summary.get('correlation_id')
    )
    job_id = _stringify(
        getattr(command_run, 'job_id', None)
        or merged_summary.get('job_id')
    )
    final_status = _stringify(
        _status_from(command_run)
        or execution_task_status
        or _status_from(execution_task)
    )

    return {
        'command_id': command_id,
        'job_id': job_id,
        'execution_task_id': execution_task_id,
        'execution_task_status': execution_task_status,
        'agent_id': agent_id,
        'agent_type': agent_type,
        'agent_run_id': agent_run_id,
        'tool_name': tool_name,
        'connector_name': connector_name,
        'provider': provider,
        'request_id': request_id,
        'run_id': run_id,
        'correlation_id': correlation_id,
        'final_status': final_status,
    }
