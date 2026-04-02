from __future__ import annotations

# Research intent trigger words — any command starting with these routes to research agent
_RESEARCH_PREFIXES = (
    "research ", "find ", "look up ", "lookup ", "what is ", "what are ",
    "explain ", "tell me ", "describe ", "how does ", "how do ", "why is ",
    "why does ", "who is ", "where is ", "when did ", "summarize ", "summary ",
    "give me ", "show me ", "list ", "compare ", "define ",
)

# Analysis intent trigger words
_ANALYSIS_PREFIXES = (
    "analyze ", "analyse ", "analysis ", "evaluate ", "assess ", "review ",
    "check ", "examine ", "inspect ", "diagnose ", "audit ",
)

# Automation intent trigger words
_AUTOMATION_PREFIXES = (
    "automate ", "run ", "execute ", "do ", "perform ", "process ",
    "generate ", "create ", "build ", "make ", "write ", "draft ",
)


def parse_command(command_text: str) -> dict:
    raw = (command_text or "").strip()
    normalized = " ".join(raw.lower().split())
    if not normalized:
        raise ValueError("command_text is required")

    # --- System / utility commands (exact match first) ---

    if normalized in {"ping agent", "agent ping", "ping"}:
        return {"intent": "agent.ping", "normalized_command": normalized, "payload": {"message": "ping"}}

    if normalized in {"tool health", "tool system health", "tool health read"}:
        return {"intent": "tool.system.health_read", "normalized_command": normalized, "payload": {}}

    if normalized in {"show system status", "system status", "status", "health", "system health"}:
        return {"intent": "system.status", "normalized_command": normalized, "payload": {}}

    if normalized in {"show jobs summary", "jobs summary", "job summary", "jobs"}:
        return {"intent": "jobs.summary", "normalized_command": normalized, "payload": {}}

    if normalized in {"show agent status", "show agents status", "agent status", "agents status", "agents"}:
        return {"intent": "agents.status", "normalized_command": normalized, "payload": {}}

    # --- Prefix-based commands ---

    if normalized.startswith("echo "):
        message = raw[5:].strip()
        return {"intent": "agent.echo", "normalized_command": normalized, "payload": {"value": message, "message": message}}

    if normalized.startswith("tool echo "):
        message = raw[len("tool echo "):].strip()
        return {"intent": "tool.system.echo", "normalized_command": normalized, "payload": {"message": message, "value": message}}

    if normalized.startswith("search "):
        query = raw[len("search "):].strip()
        return {"intent": "tool.search.web_search", "normalized_command": normalized, "payload": {"query": query, "limit": 5}}

    # --- Research agent (broad natural language support) ---

    for prefix in _RESEARCH_PREFIXES:
        if normalized.startswith(prefix):
            objective = raw[len(prefix):].strip() or raw
            return {
                "intent": "agent.runtime.research",
                "normalized_command": normalized,
                "payload": {"query": objective, "objective": objective},
            }

    # --- Analysis agent ---

    for prefix in _ANALYSIS_PREFIXES:
        if normalized.startswith(prefix):
            objective = raw[len(prefix):].strip() or raw
            return {
                "intent": "agent.runtime.analysis",
                "normalized_command": normalized,
                "payload": {"query": objective, "objective": objective},
            }

    # --- Automation agent ---

    for prefix in _AUTOMATION_PREFIXES:
        if normalized.startswith(prefix):
            objective = raw[len(prefix):].strip() or raw
            return {
                "intent": "agent.runtime.automation",
                "normalized_command": normalized,
                "payload": {"query": objective, "objective": objective},
            }

    # --- Fallback: treat any free text as a research question ---
    # This means anything typed in the dashboard will work, routed to research agent.
    return {
        "intent": "agent.runtime.research",
        "normalized_command": normalized,
        "payload": {"query": raw, "objective": raw},
    }
