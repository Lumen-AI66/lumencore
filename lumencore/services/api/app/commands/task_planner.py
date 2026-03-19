from __future__ import annotations


def plan_from_intent(parsed: dict, mode: str | None = None) -> dict:
    intent = parsed["intent"]
    payload = parsed.get("payload", {})
    normalized_mode = (mode or "").strip().lower()

    if intent == "agent.runtime.research" and normalized_mode == "workflow_job":
        return {
            "intent": intent,
            "execution_mode": "workflow_job",
            "task_type": "workflow_task",
            "workflow_type": "research_brief",
            "payload": payload,
            "requires_owner_approval": False,
            "read_only": True,
        }

    if intent == "agent.runtime.research" and normalized_mode == "workflow":
        return {
            "intent": intent,
            "execution_mode": "workflow_sync",
            "task_type": "workflow_task",
            "workflow_type": "research_brief",
            "payload": payload,
            "requires_owner_approval": False,
            "read_only": True,
        }

    if intent == "agent.runtime.research" and normalized_mode == "plan":
        return {
            "intent": intent,
            "execution_mode": "plan_sync",
            "task_type": "agent_task",
            "plan_type": "research_linear",
            "payload": payload,
            "requires_owner_approval": False,
            "read_only": True,
        }

    if intent in {"agent.runtime.research", "agent.runtime.analysis", "agent.runtime.automation"}:
        agent_type = intent.rsplit(".", 1)[-1]
        return {
            "intent": intent,
            "execution_mode": "agent_sync",
            "task_type": "agent_task",
            "agent_type": agent_type,
            "payload": payload,
            "requires_owner_approval": False,
            "read_only": True,
        }

    if intent in {"agent.ping", "agent.echo"}:
        return {
            "intent": intent,
            "execution_mode": "agent_job",
            "task_type": intent,
            "payload": payload,
            "requires_owner_approval": True,
            "read_only": False,
        }

    if intent == "tool.system.echo":
        return {
            "intent": intent,
            "execution_mode": "tool_sync",
            "task_type": "tool.system.echo",
            "tool_name": "system.echo",
            "connector_name": "system",
            "action": "echo",
            "payload": payload,
            "requires_owner_approval": False,
            "read_only": True,
        }

    if intent == "tool.system.health_read":
        return {
            "intent": intent,
            "execution_mode": "tool_sync",
            "task_type": "tool.system.health_read",
            "tool_name": "system.health_read",
            "connector_name": "system",
            "action": "health_read",
            "payload": payload,
            "requires_owner_approval": False,
            "read_only": True,
        }

    if intent == "tool.search.web_search":
        return {
            "intent": intent,
            "execution_mode": "tool_sync",
            "task_type": "tool.search.web_search",
            "tool_name": "search.web_search",
            "connector_name": "search",
            "action": "web_search",
            "payload": payload,
            "requires_owner_approval": False,
            "read_only": True,
        }

    if intent in {"system.status", "jobs.summary", "agents.status"}:
        return {
            "intent": intent,
            "execution_mode": "sync_read",
            "task_type": None,
            "payload": payload,
            "requires_owner_approval": False,
            "read_only": True,
        }

    raise ValueError(f"unsupported intent for planning: {intent}")

