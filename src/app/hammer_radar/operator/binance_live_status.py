"""Safe Binance live API readiness metadata for Hammer Radar.

This module checks configuration presence only. It never connects to Binance,
never signs payloads, and never exposes credential values.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

LIVE_ENV_FILE_EXPECTED_PATH = Path("/home/josue/.config/hammer-radar/binance-live.env")

ENV_API_KEY = "BINANCE_API_KEY"
ENV_API_SECRET = "BINANCE_API_SECRET"
ENV_BINANCE_LIVE_ENABLED = "HAMMER_BINANCE_LIVE_ENABLED"
ENV_LIVE_EXECUTION_ENABLED = "HAMMER_LIVE_EXECUTION_ENABLED"
ENV_ALLOW_LIVE_ORDERS = "HAMMER_ALLOW_LIVE_ORDERS"
ENV_GLOBAL_KILL_SWITCH = "HAMMER_GLOBAL_KILL_SWITCH"
ENV_ALLOWED_SYMBOLS = "HAMMER_LIVE_ALLOWED_SYMBOLS"
ENV_MAX_POSITION_USD = "HAMMER_LIVE_MAX_POSITION_USD"
ENV_MAX_LEVERAGE = "HAMMER_LIVE_MAX_LEVERAGE"
ENV_MARGIN_MODE = "HAMMER_LIVE_MARGIN_MODE"

DEFAULT_ALLOWED_SYMBOLS = ["BTCUSDT"]
DEFAULT_MAX_POSITION_USD = 44.0
DEFAULT_MAX_LEVERAGE = 3.0
DEFAULT_MARGIN_MODE = "isolated"
LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False


def build_binance_live_status(
    env: Mapping[str, str] | None = None,
    *,
    live_env_file_expected_path: str | Path = LIVE_ENV_FILE_EXPECTED_PATH,
) -> dict[str, Any]:
    source = os.environ if env is None else env
    expected_path = Path(live_env_file_expected_path).expanduser()

    api_key_present = bool(_env_value(source, ENV_API_KEY))
    api_secret_present = bool(_env_value(source, ENV_API_SECRET))
    configured_live_execution_enabled = _env_bool(source, ENV_LIVE_EXECUTION_ENABLED, default=False)
    configured_allow_live_orders = _env_bool(source, ENV_ALLOW_LIVE_ORDERS, default=False)
    global_kill_switch = _env_bool(source, ENV_GLOBAL_KILL_SWITCH, default=True)
    allowed_symbols = _allowed_symbols(_env_value(source, ENV_ALLOWED_SYMBOLS))
    max_position_usd = _env_float(source, ENV_MAX_POSITION_USD, DEFAULT_MAX_POSITION_USD)
    max_leverage = _env_float(source, ENV_MAX_LEVERAGE, DEFAULT_MAX_LEVERAGE)
    margin_mode = _env_value(source, ENV_MARGIN_MODE).lower() or DEFAULT_MARGIN_MODE

    blockers = [
        "live execution disabled by application default",
        "global kill switch active",
        "live order placement is not implemented",
    ]
    if not api_key_present:
        blockers.append("BINANCE_API_KEY missing")
    if not api_secret_present:
        blockers.append("BINANCE_API_SECRET missing")
    if allowed_symbols != DEFAULT_ALLOWED_SYMBOLS:
        blockers.append("HAMMER_LIVE_ALLOWED_SYMBOLS must remain BTCUSDT only")
    if max_position_usd != DEFAULT_MAX_POSITION_USD:
        blockers.append("HAMMER_LIVE_MAX_POSITION_USD must remain 44.0")
    if max_leverage != DEFAULT_MAX_LEVERAGE:
        blockers.append("HAMMER_LIVE_MAX_LEVERAGE must remain 3.0")
    if margin_mode != DEFAULT_MARGIN_MODE:
        blockers.append("HAMMER_LIVE_MARGIN_MODE must remain isolated")

    return {
        "connector_name": "binance_live_readiness",
        "api_key_present": api_key_present,
        "api_secret_present": api_secret_present,
        "live_env_file_expected_path": str(expected_path),
        "live_env_loaded": False,
        "live_env_file_exists": _path_exists(expected_path),
        "binance_live_enabled": _env_bool(source, ENV_BINANCE_LIVE_ENABLED, default=False),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED and configured_live_execution_enabled,
        "allow_live_orders": False and configured_allow_live_orders,
        "global_kill_switch": True if global_kill_switch else True,
        "allowed_symbols": DEFAULT_ALLOWED_SYMBOLS,
        "configured_allowed_symbols": allowed_symbols,
        "max_position_usd": DEFAULT_MAX_POSITION_USD,
        "configured_max_position_usd": max_position_usd,
        "max_leverage": DEFAULT_MAX_LEVERAGE,
        "configured_max_leverage": max_leverage,
        "margin_mode": DEFAULT_MARGIN_MODE,
        "configured_margin_mode": margin_mode,
        "order_placed": ORDER_PLACED,
        "secrets_shown": False,
        "readiness": "BLOCKED",
        "read_only_status_check": True,
        "network_used": False,
        "order_payload_created": False,
        "blockers": blockers,
    }


def _env_value(source: Mapping[str, str], key: str) -> str:
    return str(source.get(key) or "").strip()


def _env_bool(source: Mapping[str, str], key: str, *, default: bool) -> bool:
    value = _env_value(source, key).lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _env_float(source: Mapping[str, str], key: str, default: float) -> float:
    value = _env_value(source, key)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _allowed_symbols(value: str) -> list[str]:
    if not value:
        return list(DEFAULT_ALLOWED_SYMBOLS)
    symbols = [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
    return symbols or list(DEFAULT_ALLOWED_SYMBOLS)


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False
