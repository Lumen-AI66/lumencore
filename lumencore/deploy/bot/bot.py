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
DESKTOP_POLL_TIMEOUT = 120


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


async def _queue_desktop(command: str, chat_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{LUMENCORE_API_URL}/api/desktop/queue",
            json={"command": command, "telegram_chat_id": str(chat_id)},
        )
        resp.raise_for_status()
        return resp.json()


async def _poll_desktop_result(task_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + DESKTOP_POLL_TIMEOUT
    async with httpx.AsyncClient(timeout=10) as client:
        while time.monotonic() < deadline:
            resp = await client.get(f"{LUMENCORE_API_URL}/api/desktop/queue/{task_id}")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") in {"done", "failed"}:
                    return data
            await asyncio.sleep(2)
    return {"status": "timeout", "result": None}


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


# ── Trading commands ──────────────────────────────────────────────────────────

async def _call_trading(method: str, path: str, body: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        if method == "GET":
            resp = await client.get(f"{LUMENCORE_API_URL}/api/trading/{path}")
        else:
            resp = await client.post(f"{LUMENCORE_API_URL}/api/trading/{path}", json=body or {})
        resp.raise_for_status()
        return resp.json()


async def _handle_trading_command(text: str, update: Update) -> bool:
    """Handle trading-specific commands. Returns True if handled."""
    t = text.lower().strip()

    if t in ("start", "starten", "trade start", "trading start"):
        result = await _call_trading("POST", "start")
        await update.message.reply_text(
            f"🟢 *Trading gestart*\n{result.get('message', '')}", parse_mode="Markdown"
        )
        return True

    if t in ("stop", "stoppen", "trade stop", "trading stop"):
        result = await _call_trading("POST", "stop")
        await update.message.reply_text(
            f"🔴 *Trading gestopt*\n{result.get('message', '')}", parse_mode="Markdown"
        )
        return True

    if t in ("pause", "pauzeren", "trading pause"):
        await _call_trading("POST", "pause")
        await update.message.reply_text("⏸️ Trading gepauzeerd.", parse_mode="Markdown")
        return True

    if t in ("hervatten", "resume", "trading resume"):
        await _call_trading("POST", "resume")
        await update.message.reply_text("▶️ Trading hervat.", parse_mode="Markdown")
        return True

    if t in ("trading status", "trade status", "status trading"):
        s = await _call_trading("GET", "status")
        state = "🟢 ACTIEF" if s["running"] else "🔴 GESTOPT"
        if s.get("paused"):
            state = "⏸️ GEPAUZEERD"
        wins = s.get("wins_today", 0)
        losses = s.get("losses_today", 0)
        await update.message.reply_text(
            f"📊 *Trading Status*\n"
            f"Status: {state}\n"
            f"Balance: ${s.get('current_balance_usdt', 0):,.2f} USDT\n"
            f"PnL vandaag: {s.get('daily_pnl_pct', 0):+.2f}% (${s.get('daily_pnl_usdt', 0):+.2f})\n"
            f"Trades: {s.get('trades_today', 0)} ({wins}W / {losses}L)\n"
            f"Open posities: {s.get('open_positions', 0)}",
            parse_mode="Markdown"
        )
        return True

    if t in ("balance", "saldo", "mexc balance", "mexc saldo"):
        try:
            data = await _call_trading("GET", "mexc/balance")
            lines = ["💰 *MEXC Wallet*"]
            for b in data.get("all_balances", []):
                free = float(b.get("free", 0))
                locked = float(b.get("locked", 0))
                if free > 0 or locked > 0:
                    lines.append(f"• {b['asset']}: {free:.4f} (vrij) + {locked:.4f} (locked)")
            usdt = data.get("usdt_total", 0)
            lines.append(f"\nTotaal USDT: ${usdt:,.2f}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        except Exception as exc:
            await update.message.reply_text(f"Balance fout: {exc}")
        return True

    return False


# ── Message handler ───────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not _is_owner(update):
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    # Trading commando's — directe verwerking, geen AI overhead
    if await _handle_trading_command(text, update):
        return

    # Desktop execution: commando's die starten met ! worden lokaal uitgevoerd
    if text.startswith("!"):
        command = text[1:].strip()
        if not command:
            await update.message.reply_text("Gebruik: `! <commando>`  bijv. `! dir C:\\`", parse_mode="Markdown")
            return

        await update.message.reply_text(f"Uitvoeren op desktop: `{command}`", parse_mode="Markdown")
        try:
            task = await _queue_desktop(command, str(chat_id))
            task_id = task.get("id")
            result_data = await _poll_desktop_result(task_id)
            status = result_data.get("status", "?")
            output = result_data.get("result") or "(geen output)"
            output = output[:3800]
            reply = f"```\n{output}\n```\n_Status: {status}_"
            await update.message.reply_text(reply, parse_mode="Markdown")
        except Exception as exc:
            logger.error("Desktop queue error: %s", exc)
            await update.message.reply_text(f"Desktop fout: {exc}")
        return

    # AI commando via Openclaw
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


async def cmd_pc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Snelkoppeling: /pc <commando> voert direct uit op desktop."""
    if not _is_owner(update):
        return
    args = context.args
    if not args:
        await update.message.reply_text("Gebruik: `/pc <commando>`", parse_mode="Markdown")
        return
    command = " ".join(args)
    chat_id = str(update.effective_chat.id)
    await update.message.reply_text(f"Uitvoeren: `{command}`", parse_mode="Markdown")
    try:
        task = await _queue_desktop(command, chat_id)
        task_id = task.get("id")
        result_data = await _poll_desktop_result(task_id)
        output = (result_data.get("result") or "(geen output)")[:3800]
        status = result_data.get("status", "?")
        await update.message.reply_text(f"```\n{output}\n```\n_Status: {status}_", parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"Fout: {exc}")


async def cmd_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Snelkoppeling: /trade start|stop|status|balance"""
    if not _is_owner(update):
        return
    args = context.args
    sub = args[0].lower() if args else "status"
    await _handle_trading_command(sub if sub in ("start", "stop", "balance") else f"trading {sub}", update)


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("pc", cmd_pc))
    app.add_handler(CommandHandler("trade", cmd_trade))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("LumenClaw bot gestart. Wachten op commando's van chat_id=%d", TELEGRAM_OWNER_CHAT_ID)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
