from __future__ import annotations

from typing import Any


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


def _merge_dicts(base: dict[str, Any] | None, updates: dict[str, Any] | None) -> dict[str, Any]:
    merged = _copy_dict(base)
    for key, value in _copy_dict(updates).items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def _summary_from(obj: Any) -> dict[str, Any]:
    return _copy_dict(getattr(obj, 'result_summary', None))


def _status_from(obj: Any) -> str | None:
    value = getattr(obj, 'status', None)
    if value is None:
        return None
    return str(getattr(value, 'value', value))


def _task_id_from(obj: Any) -> str | None:
    return getattr(obj, 'task_id', None)


def _task_payload_bits(task_summary: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    agent_execution = _copy_dict(task_summary.get('agent_execution') or {})
    result_payload = _copy_dict(agent_execution.get('result') or {})
    results = result_payload.get('results') or []
    first_result = _copy_dict(results[0]) if results and isinstance(results[0], dict) else {}
    output = _copy_dict(first_result.get('output') or {})
    return agent_execution, result_payload, first_result, output


def build_execution_truth(command_run, execution_task=None) -> dict[str, Any]:
    command_summary = _summary_from(command_run)
    task_summary = _summary_from(execution_task)
    merged_summary = _merge_dicts(command_summary, task_summary)

    agent_execution, result_payload, first_result, tool_output = _task_payload_bits(task_summary)

    derived_agent_result: dict[str, Any] = {}
    if tool_output:
        derived_agent_result = {
            'provider': tool_output.get('provider') or merged_summary.get('provider'),
            'model': tool_output.get('model'),
            'output_text': tool_output.get('output_text') or '',
            'tokens_used': int(tool_output.get('tokens_used') or 0),
            'input_tokens': tool_output.get('input_tokens'),
            'output_tokens': tool_output.get('output_tokens'),
            'duration_ms': agent_execution.get('duration_ms') or first_result.get('duration_ms'),
        }
    agent_result = _merge_dicts(derived_agent_result, merged_summary.get('agent_result'))
    if agent_result:
        merged_summary['agent_result'] = agent_result

    execution_task_id = (
        merged_summary.get('execution_task_id')
        or task_summary.get('execution_task_id')
        or _task_id_from(execution_task)
    )
    execution_task_status = (
        merged_summary.get('execution_task_status')
        or task_summary.get('execution_task_status')
        or task_summary.get('scheduler_status')
        or _status_from(execution_task)
    )
    if execution_task_id:
        merged_summary['execution_task_id'] = execution_task_id
    if execution_task_status:
        merged_summary['execution_task_status'] = execution_task_status

    request_id = first_result.get('request_id') or merged_summary.get('request_id')
    run_id = first_result.get('run_id') or agent_execution.get('agent_run_id') or merged_summary.get('run_id')
    correlation_id = first_result.get('correlation_id') or result_payload.get('command_id') or agent_execution.get('task_id') or merged_summary.get('correlation_id')
    connector_name = first_result.get('connector_name') or merged_summary.get('connector_name')
    error_code = (
        first_result.get('error_code')
        or agent_execution.get('error_code')
        or merged_summary.get('error_code')
    )

    error = (
        merged_summary.get('error')
        or merged_summary.get('job_error')
        or merged_summary.get('error_message')
        or task_summary.get('error')
        or getattr(execution_task, 'error', None)
        or first_result.get('error_message')
    )
    result_text = (
        agent_result.get('output_text')
        or merged_summary.get('result')
        or ''
    )

    return {
        'result_summary': merged_summary or None,
        'execution_task_id': execution_task_id,
        'execution_task_status': execution_task_status,
        'result': result_text,
        'error': error,
        'agent_result': agent_result or None,
        'request_id': request_id,
        'run_id': run_id,
        'correlation_id': correlation_id,
        'connector_name': connector_name,
        'error_code': error_code,
    }
