"""Binance read-only connector status helpers for Hammer Radar.

This module never places orders, never imports an exchange SDK, never reads
secrets from disk, and never prints raw credentials. It only reports whether the
current process environment is configured for read-only checks.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from src.app.hammer_radar.operator.exchange_dry_run import BTCUSDT_RULES

CONNECTOR_NAME = "binance_readonly"
REQUIRED_CONNECTOR_MODE = "read_only"
CONNECTOR_STATUS_READY = "READY_READ_ONLY"
CONNECTOR_STATUS_MISSING_ENV = "MISSING_ENV"
CONNECTOR_STATUS_BLOCKED = "BLOCKED"
CONNECTOR_STATUS_ERROR = "ERROR"
LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False
READ_ONLY = True

ENV_API_KEY = "BINANCE_API_KEY"
ENV_API_SECRET = "BINANCE_API_SECRET"
ENV_CONNECTOR_MODE = "BINANCE_CONNECTOR_MODE"
ENV_LIVE_TRADING_ENABLED = "BINANCE_LIVE_TRADING_ENABLED"

FORBIDDEN_ACTIONS = [
    "place_order",
    "cancel_order",
    "transfer",
    "withdraw",
    "enable_live_trading",
]


def build_binance_readonly_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    api_key = _env_value(source, ENV_API_KEY)
    api_secret = _env_value(source, ENV_API_SECRET)
    connector_mode = _env_value(source, ENV_CONNECTOR_MODE)
    live_trading_env = _env_value(source, ENV_LIVE_TRADING_ENABLED)

    api_key_present = bool(api_key)
    api_secret_present = bool(api_secret)
    blockers: list[str] = []
    warnings: list[str] = []

    if connector_mode != REQUIRED_CONNECTOR_MODE:
        if connector_mode:
            blockers.append(f"BINANCE_CONNECTOR_MODE must be read_only, got {connector_mode}")
        else:
            blockers.append("BINANCE_CONNECTOR_MODE missing")
    if live_trading_env.lower() != "false":
        if live_trading_env:
            blockers.append("BINANCE_LIVE_TRADING_ENABLED must remain false")
        else:
            blockers.append("BINANCE_LIVE_TRADING_ENABLED missing")
    if not api_key_present:
        warnings.append("BINANCE_API_KEY missing; signed read-only checks unavailable")
    if not api_secret_present:
        warnings.append("BINANCE_API_SECRET missing; signed read-only checks unavailable")

    missing_env = not (api_key_present and api_secret_present and connector_mode and live_trading_env)
    if blockers and (connector_mode not in {"", REQUIRED_CONNECTOR_MODE} or live_trading_env.lower() not in {"", "false"}):
        connector_status = CONNECTOR_STATUS_BLOCKED
    elif missing_env:
        connector_status = CONNECTOR_STATUS_MISSING_ENV
    elif blockers:
        connector_status = CONNECTOR_STATUS_BLOCKED
    else:
        connector_status = CONNECTOR_STATUS_READY

    allowed_actions = ["read_exchange_info"]
    if api_key_present and api_secret_present:
        allowed_actions.append("read_account_status")

    return {
        "connector_name": CONNECTOR_NAME,
        "connector_mode": connector_mode or None,
        "connector_status": connector_status,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "read_only": READ_ONLY,
        "api_key_present": api_key_present,
        "api_secret_present": api_secret_present,
        "api_key_preview": _preview_api_key(api_key),
        "live_trading_env": live_trading_env or None,
        "blockers": blockers,
        "warnings": warnings,
        "allowed_actions": allowed_actions,
        "forbidden_actions": FORBIDDEN_ACTIONS,
    }


def build_binance_exchange_info(symbol: str = "BTCUSDT") -> dict[str, Any]:
    normalized_symbol = symbol.upper()
    rules = BTCUSDT_RULES if normalized_symbol == "BTCUSDT" else None
    blockers = [] if rules else [f"symbol not available in static read-only rules: {normalized_symbol}"]
    return {
        "connector_name": CONNECTOR_NAME,
        "connector_mode": REQUIRED_CONNECTOR_MODE,
        "connector_status": "STATIC_RULES" if rules else CONNECTOR_STATUS_BLOCKED,
        "symbol": normalized_symbol,
        "read_only": READ_ONLY,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "network_used": False,
        "source": "static_rules",
        "rules": dict(rules) if rules else None,
        "blockers": blockers,
        "forbidden_actions": FORBIDDEN_ACTIONS,
    }


def build_binance_readonly_status_text(env: Mapping[str, str] | None = None) -> str:
    payload = build_binance_readonly_status(env=env)
    lines = [
        "HAMMER RADAR BINANCE READ-ONLY CONNECTOR",
        f"connector_status: {payload['connector_status']}",
        f"connector_mode: {payload.get('connector_mode') or 'n/a'}",
        f"api_key_present: {str(payload['api_key_present']).lower()}",
        f"api_secret_present: {str(payload['api_secret_present']).lower()}",
        f"api_key_preview: {payload.get('api_key_preview') or 'n/a'}",
        f"live_trading_env: {payload.get('live_trading_env') or 'n/a'}",
        f"blockers: {'; '.join(payload['blockers']) if payload['blockers'] else 'none'}",
        f"warnings: {'; '.join(payload['warnings']) if payload['warnings'] else 'none'}",
        f"allowed_actions: {', '.join(payload['allowed_actions'])}",
        f"forbidden_actions: {', '.join(payload['forbidden_actions'])}",
        "live_execution_enabled: false",
        "order_placed: false",
        "Read-only connector. No order placement exists.",
        "Secrets are never shown.",
        "Live trading env must remain false.",
    ]
    return "\n".join(lines)


def _env_value(source: Mapping[str, str], key: str) -> str:
    return str(source.get(key) or "").strip()


def _preview_api_key(api_key: str) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 8:
        return f"{api_key[:2]}...{api_key[-2:]}"
    return f"{api_key[:4]}...{api_key[-4:]}"
