"""LumenClaw Telegram Bot — routes operator commands to Lumencore via Openclaw agent."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("lumenclaw")

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_OWNER_CHAT_ID = int(os.environ["TELEGRAM_OWNER_CHAT_ID"])
LUMENCORE_API_URL = os.environ.get("LUMENCORE_API_URL", "http://lumencore-api:8000")
OPENCLAW_AGENT_ID = "55555555-5555-4555-8555-555555555555"
POLL_INTERVAL = 1.5
POLL_TIMEOUT = 60


def _is_owner(update: Update) -> bool:
    return update.effective_chat is not None and update.effective_chat.id == TELEGRAM_OWNER_CHAT_ID


async def _send_command(text: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{LUMENCORE_API_URL}/api/command/run",
            json={
                "command_text": text,
                "tenant_id": "telegram",
                "requested_agent_id": OPENCLAW_AGENT_ID,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def _poll_result(command_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + POLL_TIMEOUT
    async with httpx.AsyncClient(timeout=10) as client:
        while time.monotonic() < deadline:
            resp = await client.get(f"{LUMENCORE_API_URL}/api/command/{command_id}")
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "")
                if status in {"completed", "failed", "denied", "timeout", "cancelled"}:
                    return data
            await asyncio.sleep(POLL_INTERVAL)
    return {"status": "timeout", "result": None}


def _extract_result(data: dict[str, Any]) -> str:
    status = data.get("status", "unknown")

    if status == "completed":
        result = data.get("result")
        if result:
            return str(result)
        summary = data.get("result_summary") or {}
        if isinstance(summary, dict):
            output = summary.get("output_text") or summary.get("answer") or summary.get("result")
            if output:
                return str(output)
        return "Commando uitgevoerd."

    if status == "denied":
        reason = data.get("policy_reason") or "policy blocked"
        return f"Geweigerd: {reason}"

    if status == "failed":
        summary = data.get("result_summary") or {}
        err = summary.get("error") if isinstance(summary, dict) else None
        return f"Mislukt: {err or 'onbekende fout'}"

    if status == "timeout":
        return "Timeout: commando duurde te lang."

    return f"Status: {status}"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    await update.message.reply_text("Verwerken...")

    try:
        run = await _send_command(text)
        command_id = run.get("id")
        if not command_id:
            await update.message.reply_text("Fout: geen command ID ontvangen.")
            return

        result_data = await _poll_result(command_id)
        reply = _extract_result(result_data)
        await update.message.reply_text(reply, parse_mode="Markdown")

    except httpx.HTTPStatusError as exc:
        logger.error("API error: %s", exc)
        await update.message.reply_text(f"API fout: {exc.response.status_code}")
    except Exception as exc:
        logger.error("Unexpected error: %s", exc)
        await update.message.reply_text("Interne fout. Controleer de logs.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{LUMENCORE_API_URL}/health")
            data = resp.json()
            status = data.get("status", "unknown")
        await update.message.reply_text(f"Lumencore status: `{status}`", parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"Niet bereikbaar: {exc}")


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{LUMENCORE_API_URL}/api/command/history?limit=10")
            data = resp.json()
        items = data.get("items", [])
        telegram_items = [i for i in items if i.get("tenant_id") == "telegram"]
        if not telegram_items:
            await update.message.reply_text("Geen Telegram-commando's gevonden.")
            return
        lines = []
        for item in telegram_items[:5]:
            ts = (item.get("created_at") or "")[:16].replace("T", " ")
            status = item.get("status", "?")
            cmd = (item.get("command_text") or "")[:50]
            lines.append(f"`{ts}` [{status}] {cmd}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"Fout: {exc}")


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("LumenClaw bot gestart. Wachten op commando's van chat_id=%d", TELEGRAM_OWNER_CHAT_ID)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
