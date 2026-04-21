"""MEXC Exchange Connector — allows Openclaw to trade and monitor positions on MEXC.

Supported actions:
  account.balance       — get wallet balances
  account.info          — account info + permissions
  market.ticker         — get current price for a symbol
  market.orderbook      — get order book depth
  market.klines         — get OHLCV candlestick data
  order.place           — place a new order (REQUIRES OPERATOR APPROVAL)
  order.cancel          — cancel an open order (REQUIRES OPERATOR APPROVAL)
  order.get             — get status of a specific order
  order.list_open       — list all open orders
  order.list_history    — get order history for a symbol
  position.list         — list open positions (futures)

SAFETY RULES:
- order.place and order.cancel always set requires_approval=True in orchestrator
- All trading actions are logged with full payload for audit
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..base.connector import Connector

MEXC_API_KEY_ENV = "MEXC_API_KEY"
MEXC_API_SECRET_ENV = "MEXC_API_SECRET"
MEXC_BASE_URL = "https://api.mexc.com"


class MexcConnector(Connector):
    connector_name = "mexc"
    connector_type = "exchange"

    def supported_actions(self) -> tuple[str, ...]:
        return (
            "account.balance",
            "account.info",
            "market.ticker",
            "market.orderbook",
            "market.klines",
            "order.place",
            "order.cancel",
            "order.get",
            "order.list_open",
            "order.list_history",
            "position.list",
        )

    def required_secret_names(self, payload, *, operation, provider, context=None):
        # Public market data doesn't need auth
        if operation in ("market.ticker", "market.orderbook", "market.klines"):
            return ()
        return (MEXC_API_KEY_ENV, MEXC_API_SECRET_ENV)

    def _get_credentials(self, context: dict | None) -> tuple[str, str]:
        secrets = (context or {}).get("resolved_secrets") or {}
        api_key = secrets.get(MEXC_API_KEY_ENV) or os.environ.get(MEXC_API_KEY_ENV, "")
        api_secret = secrets.get(MEXC_API_SECRET_ENV) or os.environ.get(MEXC_API_SECRET_ENV, "")
        return api_key, api_secret

    def _sign(self, params: dict, secret: str) -> str:
        query = urllib.parse.urlencode(sorted(params.items()))
        return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()

    def _public_request(self, path: str, params: dict | None = None) -> Any:
        url = f"{MEXC_BASE_URL}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"MEXC API error {exc.code}: {exc.read().decode()}") from exc
        except Exception as exc:
            raise RuntimeError(f"MEXC connection error: {exc}") from exc

    def _signed_request(self, method: str, path: str, api_key: str, secret: str, params: dict | None = None, body: dict | None = None) -> Any:
        params = params or {}
        params["timestamp"] = str(int(time.time() * 1000))
        params["recvWindow"] = "5000"
        params["signature"] = self._sign(params, secret)

        url = f"{MEXC_BASE_URL}{path}?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "X-MEXC-APIKEY": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"MEXC API error {exc.code}: {exc.read().decode()}") from exc
        except Exception as exc:
            raise RuntimeError(f"MEXC connection error: {exc}") from exc

    def execute(self, payload: dict, tenant_id: str, agent_id: str | None = None, context: dict | None = None) -> dict:
        action = str(payload.get("action") or payload.get("operation") or "").strip()
        api_key, secret = self._get_credentials(context)

        # ── PUBLIC MARKET DATA ───────────────────────────────────────────────

        if action == "market.ticker":
            symbol = str(payload.get("symbol", "")).upper()
            if not symbol:
                raise ValueError("symbol is required for market.ticker")
            result = self._public_request("/api/v3/ticker/price", {"symbol": symbol})
            return {"symbol": symbol, "price": result.get("price"), "raw": result}

        if action == "market.orderbook":
            symbol = str(payload.get("symbol", "")).upper()
            limit = int(payload.get("limit", 20))
            result = self._public_request("/api/v3/depth", {"symbol": symbol, "limit": limit})
            return {
                "symbol": symbol,
                "bids": result.get("bids", [])[:5],
                "asks": result.get("asks", [])[:5],
                "raw": result,
            }

        if action == "market.klines":
            symbol = str(payload.get("symbol", "")).upper()
            interval = str(payload.get("interval", "1h"))
            limit = int(payload.get("limit", 24))
            result = self._public_request("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
            candles = [
                {
                    "open_time": c[0],
                    "open": c[1],
                    "high": c[2],
                    "low": c[3],
                    "close": c[4],
                    "volume": c[5],
                }
                for c in (result or [])
            ]
            return {"symbol": symbol, "interval": interval, "candles": candles}

        # ── AUTHENTICATED ACCOUNT ────────────────────────────────────────────

        if not api_key or not secret:
            raise RuntimeError("MEXC_API_KEY and MEXC_API_SECRET are required for this action")

        if action == "account.info":
            result = self._signed_request("GET", "/api/v3/account", api_key, secret)
            return {
                "account_type": result.get("accountType"),
                "can_trade": result.get("canTrade"),
                "can_withdraw": result.get("canWithdraw"),
                "can_deposit": result.get("canDeposit"),
                "permissions": result.get("permissions", []),
                "raw": result,
            }

        if action == "account.balance":
            result = self._signed_request("GET", "/api/v3/account", api_key, secret)
            balances = [
                b for b in result.get("balances", [])
                if float(b.get("free", 0)) > 0 or float(b.get("locked", 0)) > 0
            ]
            return {"balances": balances, "total_assets": len(balances)}

        # ── ORDERS (HIGH-STAKES — always require operator approval in orchestrator) ──

        if action == "order.place":
            symbol = str(payload.get("symbol", "")).upper()
            side = str(payload.get("side", "")).upper()          # BUY or SELL
            order_type = str(payload.get("type", "LIMIT")).upper()
            quantity = str(payload.get("quantity", ""))
            price = str(payload.get("price", ""))

            if not all([symbol, side, quantity]):
                raise ValueError("symbol, side, and quantity are required for order.place")
            if order_type == "LIMIT" and not price:
                raise ValueError("price is required for LIMIT orders")

            params: dict = {
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "quantity": quantity,
            }
            if price:
                params["price"] = price
            if order_type == "LIMIT":
                params["timeInForce"] = payload.get("time_in_force", "GTC")

            result = self._signed_request("POST", "/api/v3/order", api_key, secret, params=params)
            return {
                "order_id": result.get("orderId"),
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "quantity": quantity,
                "price": price,
                "status": result.get("status"),
                "raw": result,
            }

        if action == "order.cancel":
            symbol = str(payload.get("symbol", "")).upper()
            order_id = str(payload.get("order_id", ""))
            if not symbol or not order_id:
                raise ValueError("symbol and order_id are required for order.cancel")
            result = self._signed_request("DELETE", "/api/v3/order", api_key, secret, params={"symbol": symbol, "orderId": order_id})
            return {"order_id": order_id, "status": result.get("status"), "raw": result}

        if action == "order.get":
            symbol = str(payload.get("symbol", "")).upper()
            order_id = str(payload.get("order_id", ""))
            result = self._signed_request("GET", "/api/v3/order", api_key, secret, params={"symbol": symbol, "orderId": order_id})
            return {
                "order_id": result.get("orderId"),
                "symbol": symbol,
                "side": result.get("side"),
                "status": result.get("status"),
                "price": result.get("price"),
                "quantity": result.get("origQty"),
                "executed": result.get("executedQty"),
                "raw": result,
            }

        if action == "order.list_open":
            symbol = str(payload.get("symbol", "")).upper()
            params = {"symbol": symbol} if symbol else {}
            result = self._signed_request("GET", "/api/v3/openOrders", api_key, secret, params=params)
            return {"open_orders": result if isinstance(result, list) else [], "count": len(result) if isinstance(result, list) else 0}

        if action == "order.list_history":
            symbol = str(payload.get("symbol", "")).upper()
            limit = int(payload.get("limit", 50))
            params = {"symbol": symbol, "limit": limit}
            result = self._signed_request("GET", "/api/v3/allOrders", api_key, secret, params=params)
            return {"orders": result if isinstance(result, list) else [], "count": len(result) if isinstance(result, list) else 0}

        if action == "position.list":
            # Futures positions — requires futures API endpoint
            result = self._signed_request("GET", "/api/v1/private/position/open_positions", api_key, secret)
            positions = result.get("data", result) if isinstance(result, dict) else result
            return {"positions": positions, "count": len(positions) if isinstance(positions, list) else 0}

        raise ValueError(f"unsupported MEXC action: {action}")
