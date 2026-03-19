from __future__ import annotations


def parse_command(command_text: str) -> dict:
    raw = (command_text or "").strip()
    normalized = " ".join(raw.lower().split())
    if not normalized:
        raise ValueError("command_text is required")

    if normalized.startswith("research "):
        objective = raw[len("research "):].strip()
        if not objective:
            raise ValueError("research command requires a value")
        return {
            "intent": "agent.runtime.research",
            "normalized_command": normalized,
            "payload": {"query": objective, "objective": objective},
        }

    if normalized.startswith("analyze "):
        objective = raw[len("analyze "):].strip()
        if not objective:
            raise ValueError("analyze command requires a value")
        return {
            "intent": "agent.runtime.analysis",
            "normalized_command": normalized,
            "payload": {"query": objective, "objective": objective},
        }

    if normalized.startswith("automate "):
        objective = raw[len("automate "):].strip()
        if not objective:
            raise ValueError("automate command requires a value")
        return {
            "intent": "agent.runtime.automation",
            "normalized_command": normalized,
            "payload": {"query": objective, "objective": objective},
        }

    if normalized in {"ping agent", "agent ping", "ping"}:
        return {"intent": "agent.ping", "normalized_command": normalized, "payload": {"message": "ping"}}

    if normalized.startswith("echo "):
        message = raw[5:].strip()
        if not message:
            raise ValueError("echo command requires a value")
        return {
            "intent": "agent.echo",
            "normalized_command": normalized,
            "payload": {"value": message, "message": message},
        }

    if normalized.startswith("tool echo "):
        message = raw[len("tool echo "):].strip()
        if not message:
            raise ValueError("tool echo command requires a value")
        return {
            "intent": "tool.system.echo",
            "normalized_command": normalized,
            "payload": {"message": message, "value": message},
        }

    if normalized.startswith("search "):
        query = raw[len("search "):].strip()
        if not query:
            raise ValueError("search command requires a value")
        return {
            "intent": "tool.search.web_search",
            "normalized_command": normalized,
            "payload": {"query": query, "limit": 5},
        }

    if normalized in {"tool health", "tool system health", "tool health read"}:
        return {
            "intent": "tool.system.health_read",
            "normalized_command": normalized,
            "payload": {},
        }

    if normalized in {"show system status", "system status", "status"}:
        return {"intent": "system.status", "normalized_command": normalized, "payload": {}}

    if normalized in {"show jobs summary", "jobs summary", "job summary"}:
        return {"intent": "jobs.summary", "normalized_command": normalized, "payload": {}}

    if normalized in {"show agent status", "show agents status", "agent status", "agents status"}:
        return {"intent": "agents.status", "normalized_command": normalized, "payload": {}}

    raise ValueError(f"unsupported command: {raw}")
