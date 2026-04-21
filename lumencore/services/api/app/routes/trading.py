"""Trading routes — start/stop/status + Telegram webhook handler."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import urllib.request
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..trading.engine import (
    get_trading_status,
    pause_trading,
    resume_trading,
    start_trading,
    stop_trading,
)
from ..connectors.mexc.mexc_connector import MexcConnector, MEXC_API_KEY_ENV, MEXC_API_SECRET_ENV

logger = logging.getLogger("trading_routes")

router = APIRouter(prefix="/api/trading", tags=["trading"])

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_CHAT_ID = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "")

# ── Models ───────────────────────────────────────────────────────────────────

class TradingStartRequest(BaseModel):
    symbols: list[str] | None = None
    risk_per_trade_pct: float | None = None
    daily_profit_target_pct: float | None = None
    scan_interval_seconds: int | None = None


class MexcOrderRequest(BaseModel):
    action: str
    symbol: str
    side: str | None = None
    type: str = "LIMIT"
    quantity: str | None = None
    price: str | None = None
    order_id: str | None = None


# ── Trading control endpoints ─────────────────────────────────────────────

@router.post("/start")
def start(req: TradingStartRequest = TradingStartRequest()) -> dict:
    config = {}
    if req.symbols:
        config["symbols"] = req.symbols
    if req.risk_per_trade_pct is not None:
        config["risk_per_trade_pct"] = req.risk_per_trade_pct
    if req.daily_profit_target_pct is not None:
        config["daily_profit_target_pct"] = req.daily_profit_target_pct
    if req.scan_interval_seconds is not None:
        config["scan_interval_seconds"] = req.scan_interval_seconds
    return start_trading(config or None)


@router.post("/stop")
def stop() -> dict:
    return stop_trading()


@router.post("/pause")
def pause() -> dict:
    return pause_trading()


@router.post("/resume")
def resume() -> dict:
    return resume_trading()


@router.get("/status")
def status() -> dict:
    return get_trading_status()


# ── MEXC proxy endpoints (used by trading engine) ────────────────────────────

@router.get("/mexc/balance")
def mexc_balance() -> dict:
    connector = MexcConnector()
    api_key = os.environ.get(MEXC_API_KEY_ENV, "")
    secret = os.environ.get(MEXC_API_SECRET_ENV, "")
    ctx = {"resolved_secrets": {MEXC_API_KEY_ENV: api_key, MEXC_API_SECRET_ENV: secret}}
    result = connector.execute({"action": "account.balance"}, tenant_id="system", context=ctx)
    # Find USDT balance
    usdt_free = usdt_locked = 0.0
    for b in result.get("balances", []):
        if b.get("asset") == "USDT":
            usdt_free = float(b.get("free", 0))
            usdt_locked = float(b.get("locked", 0))
    return {
        "usdt_free": usdt_free,
        "usdt_locked": usdt_locked,
        "usdt_total": usdt_free + usdt_locked,
        "all_balances": result.get("balances", []),
    }


@router.post("/mexc/order")
def mexc_order(req: MexcOrderRequest) -> dict:
    connector = MexcConnector()
    api_key = os.environ.get(MEXC_API_KEY_ENV, "")
    secret = os.environ.get(MEXC_API_SECRET_ENV, "")
    ctx = {"resolved_secrets": {MEXC_API_KEY_ENV: api_key, MEXC_API_SECRET_ENV: secret}}
    payload = req.model_dump(exclude_none=True)
    return connector.execute(payload, tenant_id="system", context=ctx)


# ── Telegram webhook ─────────────────────────────────────────────────────────

def _send_telegram(msg: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_OWNER_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_OWNER_CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown",
    }).encode()
    try:
        req = urllib.request.Request(url, data=payload, method="POST",
                                      headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def _handle_telegram_command(text: str, chat_id: str) -> str:
    """Process trading commands from Telegram. Returns response message."""
    t = text.strip().upper()

    if t in ("START", "STARTEN", "TRADE", "TRADING START", "/START"):
        result = start_trading()
        return result["message"]

    if t in ("STOP", "STOPPEN", "TRADING STOP", "/STOP"):
        result = stop_trading("Telegram operator commando")
        return result["message"]

    if t in ("PAUSE", "PAUZEREN", "/PAUSE"):
        result = pause_trading()
        return "Trading gepauzeerd."

    if t in ("HERVATTEN", "RESUME", "/RESUME"):
        result = resume_trading()
        return "Trading hervat."

    if t in ("STATUS", "TRADING STATUS", "/STATUS"):
        s = get_trading_status()
        state = "🟢 ACTIEF" if s["running"] else "🔴 GESTOPT"
        if s.get("paused"):
            state = "⏸️ GEPAUZEERD"
        return (
            f"📊 *Trading Status*\n"
            f"Status: {state}\n"
            f"Balance: ${s['current_balance_usdt']:,.2f}\n"
            f"PnL vandaag: {s['daily_pnl_pct']:+.2f}% (${s['daily_pnl_usdt']:+.2f})\n"
            f"Trades: {s['trades_today']} ({s['wins_today']}W / {s['losses_today']}L)\n"
            f"Open posities: {s['open_positions']}"
        )

    if t in ("BALANCE", "SALDO", "/BALANCE"):
        connector = MexcConnector()
        api_key = os.environ.get(MEXC_API_KEY_ENV, "")
        secret = os.environ.get(MEXC_API_SECRET_ENV, "")
        ctx = {"resolved_secrets": {MEXC_API_KEY_ENV: api_key, MEXC_API_SECRET_ENV: secret}}
        result = connector.execute({"action": "account.balance"}, tenant_id="system", context=ctx)
        lines = ["💰 *MEXC Wallet Balances*"]
        for b in result.get("balances", []):
            free = float(b.get("free", 0))
            locked = float(b.get("locked", 0))
            lines.append(f"• {b['asset']}: {free:.4f} (vrij) + {locked:.4f} (vergrendeld)")
        return "\n".join(lines) if len(lines) > 1 else "Geen saldo gevonden."

    return None  # not a trading command


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict:
    """Receive Telegram updates and handle trading commands."""
    try:
        body = await request.json()
    except Exception:
        return {"ok": True}

    message = body.get("message") or body.get("edited_message") or {}
    text = (message.get("text") or "").strip()
    chat_id = str(message.get("chat", {}).get("id", ""))

    if not text or not chat_id:
        return {"ok": True}

    # Only respond to owner
    if chat_id != str(TELEGRAM_OWNER_CHAT_ID):
        return {"ok": True}

    response = _handle_telegram_command(text, chat_id)
    if response:
        _send_telegram(response)

    return {"ok": True}
