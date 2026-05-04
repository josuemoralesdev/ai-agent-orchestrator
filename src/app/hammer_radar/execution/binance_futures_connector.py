"""Default-blocked Binance Futures tiny-live connector for Hammer Radar.

R43 adds connector gating, audit records, and sanitized payload previews. It
does not read or expose secrets, does not sign payloads in dry-run mode, and
does not place a live order unless an explicit future adapter is supplied after
all live gates are enabled.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.binance_live_status import (
    ENV_ALLOW_LIVE_ORDERS,
    ENV_API_KEY,
    ENV_API_SECRET,
    ENV_BINANCE_LIVE_ENABLED,
    ENV_GLOBAL_KILL_SWITCH,
    ENV_LIVE_EXECUTION_ENABLED,
)
from src.app.hammer_radar.operator.live_approval import load_live_approval_requests
from src.app.hammer_radar.operator.live_preflight import (
    PREFLIGHT_READY_BUT_EXECUTION_DISABLED,
    PROMOTED_STRATEGY_KEY,
    build_promoted_strategy_preflight,
)

DRY_RUN_ONLY = "DRY_RUN_ONLY"
TEST_ORDER_ONLY = "TEST_ORDER_ONLY"
LIVE_ORDER_ENABLED = "LIVE_ORDER_ENABLED"
CONNECTOR_MODES = {DRY_RUN_ONLY, TEST_ORDER_ONLY, LIVE_ORDER_ENABLED}

ENV_CONNECTOR_MODE = "HAMMER_BINANCE_CONNECTOR_MODE"
ENV_ALLOWED_SYMBOLS = "HAMMER_LIVE_ALLOWED_SYMBOLS"
ENV_MAX_POSITION_USD = "HAMMER_LIVE_MAX_POSITION_USD"
ENV_MAX_LEVERAGE = "HAMMER_LIVE_MAX_LEVERAGE"
ENV_MARGIN_MODE = "HAMMER_LIVE_MARGIN_MODE"
ENV_REQUIRE_EXACT_APPROVAL = "HAMMER_LIVE_REQUIRE_EXACT_APPROVAL"
ENV_MAX_TRADES_PER_DAY = "HAMMER_LIVE_MAX_TRADES_PER_DAY"

ATTEMPTS_FILENAME = "binance_live_connector_attempts.ndjson"
CONNECTOR_NAME = "binance_futures_tiny_live"
DEFAULT_ALLOWED_SYMBOLS = ["BTCUSDT"]
DEFAULT_MAX_POSITION_USD = 44.0
DEFAULT_MAX_LEVERAGE = 3.0
DEFAULT_MARGIN_MODE = "isolated"
DEFAULT_MAX_TRADES_PER_DAY = 1


class BinanceOrderAdapter(Protocol):
    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit a sanitized payload through an explicit future adapter."""


def build_connector_status(
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    source = os.environ if env is None else env
    config = _config(source)
    return _connector_status_from_config(config, log_dir=get_log_dir(log_dir, use_env=True))


def _connector_status_from_config(config: dict[str, Any], *, log_dir: Path) -> dict[str, Any]:
    blockers = _status_blockers(config)
    readiness = "BLOCKED"
    if not blockers and config["connector_mode"] == TEST_ORDER_ONLY:
        readiness = "READY_FOR_TEST_ORDER"
    if not blockers and config["connector_mode"] == LIVE_ORDER_ENABLED:
        readiness = "READY_FOR_LIVE_ORDER"

    return {
        "connector_name": CONNECTOR_NAME,
        "connector_mode": config["connector_mode"],
        "api_key_present": config["api_key_present"],
        "api_secret_present": config["api_secret_present"],
        "secrets_shown": False,
        "network_used": False,
        "binance_live_enabled": config["binance_live_enabled"],
        "live_execution_enabled": config["live_execution_enabled"],
        "allow_live_orders": config["allow_live_orders"],
        "global_kill_switch": config["global_kill_switch"],
        "allowed_symbols": DEFAULT_ALLOWED_SYMBOLS,
        "configured_allowed_symbols": config["configured_allowed_symbols"],
        "max_position_usd": DEFAULT_MAX_POSITION_USD,
        "configured_max_position_usd": config["max_position_usd"],
        "max_leverage": DEFAULT_MAX_LEVERAGE,
        "configured_max_leverage": config["max_leverage"],
        "margin_mode": DEFAULT_MARGIN_MODE,
        "configured_margin_mode": config["margin_mode"],
        "max_trades_per_day": DEFAULT_MAX_TRADES_PER_DAY,
        "configured_max_trades_per_day": config["max_trades_per_day"],
        "require_exact_approval": config["require_exact_approval"],
        "order_placed": False,
        "execution_attempted": False,
        "order_payload_created": False,
        "readiness": readiness,
        "blockers": blockers,
        "attempts_path": str(connector_attempts_path(log_dir)),
    }


def preview_payload(
    *,
    preflight_pack: dict[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    pack = preflight_pack or build_promoted_strategy_preflight(log_dir=resolved_log_dir)
    config = _config(os.environ if env is None else env)
    payload, blockers = _payload_preview_from_pack(pack, config=config)
    status = "PAYLOAD_PREVIEW_CREATED" if payload is not None and not blockers else "BLOCKED"
    record = _attempt_record(
        action="payload_preview",
        connector_mode=config["connector_mode"],
        signal_id=_signal_id(pack),
        preflight_id=pack.get("preflight_id"),
        status=status,
        blockers=blockers,
        network_used=False,
        order_payload_created=payload is not None and not blockers,
        execution_attempted=False,
        order_placed=False,
        config=config,
        payload_preview=payload,
    )
    if persist:
        append_connector_attempt(record, log_dir=resolved_log_dir)
    return _response(record, connector_status=_connector_status_from_config(config, log_dir=resolved_log_dir))


def submit_test_order(
    *,
    preflight_pack: dict[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    config = _config(source)
    pack = preflight_pack or build_promoted_strategy_preflight(log_dir=resolved_log_dir)
    payload, blockers = _payload_preview_from_pack(pack, config=config)
    if config["connector_mode"] != TEST_ORDER_ONLY:
        blockers.append("connector_mode must be TEST_ORDER_ONLY for test-order")
    if not config["api_key_present"] or not config["api_secret_present"]:
        blockers.append("Binance API key and secret must be present for test-order")
    status = "BLOCKED" if blockers else "TEST_ORDER_SENT"
    record = _attempt_record(
        action="test_order",
        connector_mode=config["connector_mode"],
        signal_id=_signal_id(pack),
        preflight_id=pack.get("preflight_id"),
        status=status,
        blockers=blockers,
        network_used=False,
        order_payload_created=payload is not None and not blockers,
        execution_attempted=not blockers,
        order_placed=False,
        config=config,
        payload_preview=payload if not blockers else None,
        exchange_response={"local_test_adapter": True, "sent": False} if not blockers else None,
    )
    if persist:
        append_connector_attempt(record, log_dir=resolved_log_dir)
    return _response(record, connector_status=_connector_status_from_config(config, log_dir=resolved_log_dir))


def execute_live_order(
    *,
    preflight_pack: dict[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
    adapter: BinanceOrderAdapter | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    config = _config(source)
    pack = preflight_pack or build_promoted_strategy_preflight(log_dir=resolved_log_dir)
    payload, blockers = _payload_preview_from_pack(pack, config=config)
    blockers.extend(_execute_blockers(pack, config=config, log_dir=resolved_log_dir))
    if adapter is None:
        blockers.append("live Binance order adapter is not configured")

    exchange_response = None
    network_used = False
    order_placed = False
    execution_attempted = False
    status = "BLOCKED"
    if not blockers and payload is not None and adapter is not None:
        execution_attempted = True
        try:
            exchange_response = _sanitize_exchange_response(adapter.submit_order(payload))
            network_used = bool(exchange_response.get("network_used"))
            order_placed = bool(exchange_response.get("order_placed"))
            status = "LIVE_ORDER_SENT" if order_placed else "ERROR"
        except Exception as exc:  # pragma: no cover - defensive adapter boundary
            status = "ERROR"
            exchange_response = {"error": exc.__class__.__name__, "message": "adapter failed without exposing secrets"}

    record = _attempt_record(
        action="execute",
        connector_mode=config["connector_mode"],
        signal_id=_signal_id(pack),
        preflight_id=pack.get("preflight_id"),
        status=status,
        blockers=blockers,
        network_used=network_used,
        order_payload_created=payload is not None and not blockers,
        execution_attempted=execution_attempted,
        order_placed=order_placed,
        config=config,
        payload_preview=payload if payload is not None and not blockers else None,
        exchange_response=exchange_response,
    )
    if persist:
        append_connector_attempt(record, log_dir=resolved_log_dir)
    return _response(record, connector_status=_connector_status_from_config(config, log_dir=resolved_log_dir))


def append_connector_attempt(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = connector_attempts_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_connector_attempts(
    *,
    limit: int = 50,
    attempt_id: str | None = None,
    signal_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = connector_attempts_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if attempt_id is not None and record.get("attempt_id") != attempt_id:
                continue
            if signal_id is not None and record.get("signal_id") != signal_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def connector_attempts_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / ATTEMPTS_FILENAME


def _payload_preview_from_pack(
    pack: dict[str, Any],
    *,
    config: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    blockers = _preflight_blockers(pack, config=config)
    candidate = pack.get("candidate") or {}
    entry = _float_or_none(candidate.get("entry"))
    if entry is None or entry <= 0.0:
        blockers.append("candidate entry price is required for payload preview")
    quantity = round(float(config["max_position_usd"]) / entry, 6) if entry else None
    if quantity is None or quantity <= 0.0:
        blockers.append("quantity is unavailable")
    if blockers:
        return None, list(dict.fromkeys(blockers))
    side = "BUY"
    payload = {
        "symbol": candidate.get("symbol"),
        "side": side,
        "position_side": "LONG",
        "order_type": "LIMIT",
        "quantity": quantity,
        "price": entry,
        "stop_price": candidate.get("stop"),
        "take_profit_price": candidate.get("take_profit"),
        "leverage": config["max_leverage"],
        "margin_mode": config["margin_mode"],
        "reduce_only": False,
        "preview_only": True,
        "sent": False,
        "signed": False,
        "signature_present": False,
        "order_payload_created": True,
    }
    return payload, []


def _preflight_blockers(pack: dict[str, Any], *, config: dict[str, Any]) -> list[str]:
    candidate = pack.get("candidate") or {}
    blockers: list[str] = []
    if pack.get("promoted_strategy_ready") is not True:
        blockers.append("promoted strategy is not ready")
    if pack.get("matching_fresh_signal_found") is not True:
        blockers.append("no fresh promoted signal is available")
    if pack.get("strategy_key") != PROMOTED_STRATEGY_KEY:
        blockers.append(f"strategy_key must be {PROMOTED_STRATEGY_KEY}")
    if candidate.get("symbol") != "BTCUSDT":
        blockers.append("symbol must be BTCUSDT")
    if candidate.get("timeframe") != "13m":
        blockers.append("timeframe must be 13m")
    if candidate.get("direction") != "long":
        blockers.append("direction must be long")
    if pack.get("readiness_status") != "READY":
        blockers.append(f"readiness_status is {pack.get('readiness_status', 'UNKNOWN')}")
    if pack.get("ticket_status") != "PROPOSED":
        blockers.append(f"ticket_status is {pack.get('ticket_status', 'UNKNOWN')}")
    if pack.get("dry_run_status") != "VALID":
        blockers.append(f"dry_run_status is {pack.get('dry_run_status', 'UNKNOWN')}")
    if pack.get("preflight_status") != PREFLIGHT_READY_BUT_EXECUTION_DISABLED:
        blockers.append(f"preflight_status is {pack.get('preflight_status', 'UNKNOWN')}")
    if config["configured_allowed_symbols"] != DEFAULT_ALLOWED_SYMBOLS:
        blockers.append("HAMMER_LIVE_ALLOWED_SYMBOLS must remain BTCUSDT only")
    if float(config["max_position_usd"]) > DEFAULT_MAX_POSITION_USD:
        blockers.append("HAMMER_LIVE_MAX_POSITION_USD exceeds 44")
    if float(config["max_leverage"]) > DEFAULT_MAX_LEVERAGE:
        blockers.append("HAMMER_LIVE_MAX_LEVERAGE exceeds 3")
    if config["margin_mode"] != DEFAULT_MARGIN_MODE:
        blockers.append("HAMMER_LIVE_MARGIN_MODE must be isolated")
    return list(dict.fromkeys(blockers))


def _execute_blockers(pack: dict[str, Any], *, config: dict[str, Any], log_dir: Path) -> list[str]:
    signal_id = _signal_id(pack)
    blockers = []
    if config["connector_mode"] != LIVE_ORDER_ENABLED:
        blockers.append("connector_mode must be LIVE_ORDER_ENABLED")
    if config["binance_live_enabled"] is not True:
        blockers.append("HAMMER_BINANCE_LIVE_ENABLED is false")
    if config["live_execution_enabled"] is not True:
        blockers.append("live_execution_enabled is false")
    if config["allow_live_orders"] is not True:
        blockers.append("allow_live_orders is false")
    if config["global_kill_switch"] is not False:
        blockers.append("global kill switch is active")
    if not config["api_key_present"] or not config["api_secret_present"]:
        blockers.append("Binance API key and secret must be present")
    if config["require_exact_approval"] is True and not _has_exact_approval(signal_id, log_dir=log_dir):
        blockers.append("exact LIVE APPROVE <signal_id> is missing")
    blockers.extend(_one_trade_lock_blockers(signal_id, config=config, log_dir=log_dir))
    return list(dict.fromkeys(blockers))


def _one_trade_lock_blockers(signal_id: str | None, *, config: dict[str, Any], log_dir: Path) -> list[str]:
    blockers = []
    today = datetime.now(UTC).date()
    live_order_records = [
        record
        for record in load_connector_attempts(limit=0, log_dir=log_dir)
        if record.get("status") == "LIVE_ORDER_SENT" or record.get("order_placed") is True
    ]
    if signal_id and any(record.get("signal_id") == signal_id for record in live_order_records):
        blockers.append(f"live order already recorded for signal_id {signal_id}")
    todays_orders = [record for record in live_order_records if _record_date(record) == today]
    if len(todays_orders) >= int(config["max_trades_per_day"]):
        blockers.append("max live trades per day already reached")
    return blockers


def _has_exact_approval(signal_id: str | None, *, log_dir: Path) -> bool:
    if not signal_id:
        return False
    for record in load_live_approval_requests(limit=0, signal_id=signal_id, log_dir=log_dir):
        if (
            record.get("normalized_action") == "live_approve_exact"
            and record.get("parse_status") == "ACCEPTED"
            and record.get("approval_gate_status") in {"READY_BUT_EXECUTION_DISABLED", "BLOCKED"}
            and record.get("signal_id") == signal_id
        ):
            return True
    return False


def _attempt_record(
    *,
    action: str,
    connector_mode: str,
    signal_id: str | None,
    preflight_id: str | None,
    status: str,
    blockers: list[str],
    network_used: bool,
    order_payload_created: bool,
    execution_attempted: bool,
    order_placed: bool,
    config: dict[str, Any],
    payload_preview: dict[str, Any] | None = None,
    exchange_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "attempt_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "endpoint": action,
        "action": action,
        "connector_name": CONNECTOR_NAME,
        "connector_mode": connector_mode,
        "signal_id": signal_id,
        "preflight_id": preflight_id,
        "status": status,
        "blockers": list(dict.fromkeys(blockers)),
        "network_used": network_used,
        "order_payload_created": order_payload_created,
        "execution_attempted": execution_attempted,
        "order_placed": order_placed,
        "live_execution_enabled": config["live_execution_enabled"],
        "allow_live_orders": config["allow_live_orders"],
        "global_kill_switch": config["global_kill_switch"],
        "secrets_shown": False,
        "payload_preview": _sanitize_payload(payload_preview),
        "exchange_response": _sanitize_exchange_response(exchange_response),
    }


def _response(record: dict[str, Any], *, connector_status: dict[str, Any]) -> dict[str, Any]:
    return {
        "connector_name": CONNECTOR_NAME,
        "connector_mode": record["connector_mode"],
        "status": record["status"],
        "attempt": record,
        "blockers": record["blockers"],
        "network_used": record["network_used"],
        "order_payload_created": record["order_payload_created"],
        "execution_attempted": record["execution_attempted"],
        "order_placed": record["order_placed"],
        "live_execution_enabled": record["live_execution_enabled"],
        "allow_live_orders": record["allow_live_orders"],
        "global_kill_switch": record["global_kill_switch"],
        "secrets_shown": False,
        "payload_preview": record.get("payload_preview"),
        "exchange_response": record.get("exchange_response"),
        "connector_status": connector_status,
    }


def _config(source: Mapping[str, str]) -> dict[str, Any]:
    mode = _env_value(source, ENV_CONNECTOR_MODE).upper() or DRY_RUN_ONLY
    if mode not in CONNECTOR_MODES:
        mode = DRY_RUN_ONLY
    return {
        "connector_mode": mode,
        "api_key_present": bool(_env_value(source, ENV_API_KEY)),
        "api_secret_present": bool(_env_value(source, ENV_API_SECRET)),
        "binance_live_enabled": _env_bool(source, ENV_BINANCE_LIVE_ENABLED, default=False),
        "live_execution_enabled": _env_bool(source, ENV_LIVE_EXECUTION_ENABLED, default=False),
        "allow_live_orders": _env_bool(source, ENV_ALLOW_LIVE_ORDERS, default=False),
        "global_kill_switch": _env_bool(source, ENV_GLOBAL_KILL_SWITCH, default=True),
        "configured_allowed_symbols": _allowed_symbols(_env_value(source, ENV_ALLOWED_SYMBOLS)),
        "max_position_usd": _env_float(source, ENV_MAX_POSITION_USD, DEFAULT_MAX_POSITION_USD),
        "max_leverage": _env_float(source, ENV_MAX_LEVERAGE, DEFAULT_MAX_LEVERAGE),
        "margin_mode": (_env_value(source, ENV_MARGIN_MODE).lower() or DEFAULT_MARGIN_MODE),
        "require_exact_approval": _env_bool(source, ENV_REQUIRE_EXACT_APPROVAL, default=True),
        "max_trades_per_day": int(_env_float(source, ENV_MAX_TRADES_PER_DAY, DEFAULT_MAX_TRADES_PER_DAY)),
    }


def _status_blockers(config: dict[str, Any]) -> list[str]:
    blockers = []
    if config["connector_mode"] == DRY_RUN_ONLY:
        blockers.append("connector_mode is DRY_RUN_ONLY")
    if config["configured_allowed_symbols"] != DEFAULT_ALLOWED_SYMBOLS:
        blockers.append("HAMMER_LIVE_ALLOWED_SYMBOLS must remain BTCUSDT only")
    if config["max_position_usd"] != DEFAULT_MAX_POSITION_USD:
        blockers.append("HAMMER_LIVE_MAX_POSITION_USD must remain 44")
    if config["max_leverage"] != DEFAULT_MAX_LEVERAGE:
        blockers.append("HAMMER_LIVE_MAX_LEVERAGE must remain 3")
    if config["margin_mode"] != DEFAULT_MARGIN_MODE:
        blockers.append("HAMMER_LIVE_MARGIN_MODE must remain isolated")
    if config["connector_mode"] == LIVE_ORDER_ENABLED:
        if config["binance_live_enabled"] is not True:
            blockers.append("HAMMER_BINANCE_LIVE_ENABLED is false")
        if config["live_execution_enabled"] is not True:
            blockers.append("live_execution_enabled is false")
        if config["allow_live_orders"] is not True:
            blockers.append("allow_live_orders is false")
        if config["global_kill_switch"] is not False:
            blockers.append("global kill switch is active")
    if config["connector_mode"] in {TEST_ORDER_ONLY, LIVE_ORDER_ENABLED}:
        if not config["api_key_present"]:
            blockers.append("BINANCE_API_KEY missing")
        if not config["api_secret_present"]:
            blockers.append("BINANCE_API_SECRET missing")
    return list(dict.fromkeys(blockers))


def _sanitize_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    sanitized = dict(payload)
    for key in ("apiKey", "api_key", "secret", "signature"):
        sanitized.pop(key, None)
    sanitized["signed"] = False
    sanitized["signature_present"] = False
    return sanitized


def _sanitize_exchange_response(response: dict[str, Any] | None) -> dict[str, Any] | None:
    if response is None:
        return None
    sanitized = dict(response)
    for key in ("apiKey", "api_key", "secret", "signature"):
        sanitized.pop(key, None)
    return sanitized


def _record_date(record: dict[str, Any]) -> object:
    try:
        return datetime.fromisoformat(str(record.get("created_at"))).date()
    except ValueError:
        return None


def _signal_id(pack: dict[str, Any]) -> str | None:
    value = pack.get("candidate_signal_id") or pack.get("signal_id")
    return str(value) if value else None


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
