"""Outbound notifications (Telegram).

Uses urllib stdlib so we add zero new dependencies to the API service.
All failures are swallowed and logged — notifications must never break the
request pipeline (webhook ACKs are higher priority than alerts).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


def _telegram_enabled() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_OWNER_CHAT_ID"))


def send_telegram(message: str, parse_mode: str = "Markdown") -> bool:
    """Fire-and-forget Telegram notification to the operator chat.

    Returns True on HTTP 200, False otherwise. Never raises.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_OWNER_CHAT_ID")
    if not token or not chat_id:
        logger.info("telegram notification skipped — env not configured")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            ok = resp.status == 200
            if not ok:
                body = resp.read().decode("utf-8", errors="ignore")
                logger.warning("telegram non-200 status=%s body=%s", resp.status, body[:300])
            return ok
    except Exception as exc:  # noqa: BLE001 — never break callers
        logger.warning("telegram send failed: %s", exc)
        return False


def notify_revenue_event(
    *,
    workspace_name: str,
    amount_cents: int,
    currency: str,
    source: str,
    reference: str,
    customer_email: str | None,
    mtd_cents: int,
) -> bool:
    amount = amount_cents / 100.0
    mtd = mtd_cents / 100.0
    cust = f" | {customer_email}" if customer_email else ""
    msg = (
        f"💰 *+{currency} {amount:,.2f}*  _{workspace_name}_\n"
        f"{source} · `{reference}`{cust}\n"
        f"MTD: *{currency} {mtd:,.2f}*"
    )
    return send_telegram(msg)


def notify_payment_required(
    *,
    workspace_name: str,
    reason: str,
    amount_hint: str | None = None,
    context_url: str | None = None,
    job_id: str | None = None,
) -> bool:
    amt = f"\nEstimated cost: *{amount_hint}*" if amount_hint else ""
    ctx = f"\nContext: {context_url}" if context_url else ""
    job = f"\nApprove: `/ok_{job_id}` · Reject: `/no_{job_id}`" if job_id else ""
    msg = (
        f"🔔 *PAYMENT GATE* — _{workspace_name}_\n"
        f"{reason}{amt}{ctx}{job}"
    )
    return send_telegram(msg)
