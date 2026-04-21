"""Daily Update Module — ingests new knowledge and project status into Lumencore memory.

Runs once per day (via Celery beat or cron).
Reports summary to operator via Telegram.
Stores insights in memory for Openclaw to use.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

LUMENCORE_API_URL = os.environ.get("LUMENCORE_API_URL", "http://lumencore-api:8000")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_CHAT_ID = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "")
ANTHROPIC_API_KEY_ENV = "LUMENCORE_ANTHROPIC_API_KEY"


def _api_post(path: str, payload: dict) -> dict:
    url = f"{LUMENCORE_API_URL}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        return {"error": str(exc)}


def _api_get(path: str) -> dict:
    url = f"{LUMENCORE_API_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        return {"error": str(exc)}


def _send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_OWNER_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_OWNER_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST",
                                  headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def _get_system_health() -> dict:
    return _api_get("/health")


def _get_recent_commands(limit: int = 10) -> list:
    data = _api_get(f"/api/commands?limit={limit}")
    return data.get("items", []) if isinstance(data, dict) else []


def _get_memory_count() -> int:
    data = _api_get("/api/memory?limit=1")
    return data.get("total", 0) if isinstance(data, dict) else 0


def _store_daily_snapshot(snapshot: dict) -> None:
    _api_post("/api/memory", {
        "type": "context",
        "key": f"daily_snapshot:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "content": json.dumps(snapshot),
        "metadata": {"source": "daily_updater", "type": "daily_snapshot"},
    })


def _generate_insights(snapshot: dict) -> str:
    """Ask Claude to generate insights from the daily snapshot."""
    api_key = os.environ.get(ANTHROPIC_API_KEY_ENV, "")
    if not api_key:
        return "No AI key configured for insights."

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = f"""Analyze this Lumencore daily snapshot and give 3 short actionable insights in Dutch:
{json.dumps(snapshot, indent=2)}

Format: numbered list, max 2 sentences each."""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text if response.content else "No insights generated."
    except Exception as exc:
        return f"Insights error: {exc}"


def run_daily_update() -> dict[str, Any]:
    """Main daily update function. Run this once per day."""
    now = datetime.now(timezone.utc)
    report: dict[str, Any] = {"date": now.isoformat(), "sections": {}}

    # 1. System health
    health = _get_system_health()
    report["sections"]["health"] = health.get("status", "unknown")

    # 2. Recent activity
    commands = _get_recent_commands(10)
    completed = sum(1 for c in commands if c.get("status") == "completed")
    failed = sum(1 for c in commands if c.get("status") == "failed")
    report["sections"]["activity"] = {
        "total_commands": len(commands),
        "completed": completed,
        "failed": failed,
    }

    # 3. Memory stats
    mem_count = _get_memory_count()
    report["sections"]["memory_entries"] = mem_count

    # 4. AI insights
    insights = _generate_insights(report)
    report["sections"]["insights"] = insights

    # 5. Store snapshot
    _store_daily_snapshot(report)

    # 6. Report to operator via Telegram
    msg = (
        f"📊 *Lumencore Dagrapport — {now.strftime('%d %b %Y')}*\n\n"
        f"🟢 Status: {report['sections']['health']}\n"
        f"⚡ Commando's: {completed} geslaagd, {failed} mislukt\n"
        f"🧠 Geheugen: {mem_count} items\n\n"
        f"💡 *Inzichten:*\n{insights}"
    )
    _send_telegram(msg)

    return report


if __name__ == "__main__":
    result = run_daily_update()
    print(json.dumps(result, indent=2))
