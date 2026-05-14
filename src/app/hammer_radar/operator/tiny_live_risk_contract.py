"""R84.1 local tiny-live risk contract configuration.

This module loads and validates non-secret local risk/funding config. It never
fetches balances, calls Binance, creates order payloads, or enables execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PHASE = "R84.1"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "TINY_LIVE_RISK_CONTRACT_CONFIG_ONLY_NO_ORDER"

DEFAULT_CANDIDATE_ID = "normal|BTCUSDT|13m|long|ladder_close_50_618"
CONFIG_PATH = Path("configs/hammer_radar/tiny_live_risk_contracts.json")

RISK_CONTRACT_VALID_FOR_PREFLIGHT = "RISK_CONTRACT_VALID_FOR_PREFLIGHT"
RISK_CONTRACT_INVALID = "RISK_CONTRACT_INVALID"
RISK_CONTRACT_NOT_FOUND = "RISK_CONTRACT_NOT_FOUND"
FUNDING_CONFIG_PRESENT = "FUNDING_CONFIG_PRESENT"
FUNDING_CONFIG_MISSING = "FUNDING_CONFIG_MISSING"
LOCAL_CONFIG_ONLY_NO_NETWORK = "LOCAL_CONFIG_ONLY_NO_NETWORK"

MAX_MARGIN_USDT = 44.0
MAX_LOSS_USDT = 4.44
MAX_POSITION_NOTIONAL_USDT = 44.0
MIN_RISK_REWARD_RATIO = 1.5

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R84.1 validates local non-secret risk config only. No orders, no network, no Binance."


def build_tiny_live_risk_contract_payload(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(config_path) if config_path is not None else CONFIG_PATH
    source = load_tiny_live_risk_config(config_path=path)
    contract = find_risk_contract(source, candidate_id=candidate_id)
    funding = funding_config(source)
    validation = validate_risk_contract(contract, candidate_id=candidate_id)
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "config_path": str(path),
            "candidate_id": candidate_id,
            "risk_contract": contract or {},
            "validation": validation,
            "funding_config": funding,
            "notes": [NO_ORDER_NOTE],
            **_safety_fields(),
        }
    )


def load_tiny_live_risk_config(*, config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path is not None else CONFIG_PATH
    if not path.exists():
        return {"risk_contracts": [], "funding_config": {}}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {"risk_contracts": [], "funding_config": {}}


def find_risk_contract(source: Mapping[str, Any], *, candidate_id: str) -> dict[str, Any] | None:
    contracts = source.get("risk_contracts") if isinstance(source.get("risk_contracts"), list) else []
    for contract in contracts:
        if isinstance(contract, dict) and contract.get("candidate_id") == candidate_id:
            return dict(contract)
    return None


def funding_config(source: Mapping[str, Any]) -> dict[str, Any]:
    config = source.get("funding_config") if isinstance(source.get("funding_config"), dict) else {}
    present = config.get("funding_config_present") is True
    return _sanitize(
        {
            "funding_status": FUNDING_CONFIG_PRESENT if present else FUNDING_CONFIG_MISSING,
            "funding_config_present": present,
            "funding_check_mode": config.get("funding_check_mode") or LOCAL_CONFIG_ONLY_NO_NETWORK,
            "account_balance_checked": False,
            "account_balance_source": config.get("account_balance_source") or "not_checked_no_network",
            "max_margin_usdt": _float_or_none(config.get("max_margin_usdt")),
            "max_loss_usdt": _float_or_none(config.get("max_loss_usdt")),
            "funding_note": config.get("funding_note"),
            "blockers": [] if present else ["funding_config_missing"],
            **_safety_fields(),
        }
    )


def validate_risk_contract(contract: Mapping[str, Any] | None, *, candidate_id: str) -> dict[str, Any]:
    blockers: list[str] = []
    if not contract:
        return _validation(RISK_CONTRACT_NOT_FOUND, ["risk_contract_not_found"])
    if contract.get("candidate_id") != candidate_id:
        blockers.append("candidate_id_mismatch")
    if contract.get("candidate_id") != DEFAULT_CANDIDATE_ID:
        blockers.append("candidate_id_not_supported_for_tiny_live_preflight")
    expected = {
        "symbol": "BTCUSDT",
        "timeframe": "13m",
        "direction": "long",
        "entry_mode": "ladder_close_50_618",
    }
    for key, value in expected.items():
        if contract.get(key) != value:
            blockers.append(f"{key}_mismatch")
    if contract.get("enabled_for_preflight") is not True:
        blockers.append("enabled_for_preflight_not_true")
    stop_distance = _float_or_none(contract.get("stop_distance_pct"))
    take_profit_distance = _float_or_none(contract.get("take_profit_distance_pct"))
    stop_price = _float_or_none(contract.get("stop_price"))
    take_profit_price = _float_or_none(contract.get("take_profit_price"))
    if stop_distance is None and stop_price is None:
        blockers.append("missing_stop_price_or_stop_distance_pct")
    if take_profit_distance is None and take_profit_price is None:
        blockers.append("missing_take_profit_price_or_take_profit_distance_pct")
    if stop_distance is not None and stop_distance <= 0:
        blockers.append("stop_distance_pct must be positive")
    if take_profit_distance is not None and take_profit_distance <= 0:
        blockers.append("take_profit_distance_pct must be positive")
    risk_reward = _float_or_none(contract.get("risk_reward_ratio"))
    if risk_reward is None and stop_distance and take_profit_distance:
        risk_reward = round(take_profit_distance / stop_distance, 4)
    if risk_reward is None or risk_reward < MIN_RISK_REWARD_RATIO:
        blockers.append(f"risk_reward_ratio below {MIN_RISK_REWARD_RATIO}")
    max_margin = _float_or_none(contract.get("max_margin_usdt"))
    max_loss = _float_or_none(contract.get("max_loss_usdt"))
    max_position = _float_or_none(contract.get("max_position_notional_usdt"))
    leverage = _float_or_none(contract.get("leverage"))
    if max_margin is None or max_margin <= 0 or max_margin > MAX_MARGIN_USDT:
        blockers.append("max_margin_usdt outside tiny-live cap")
    if max_loss is None or max_loss <= 0 or max_loss > MAX_LOSS_USDT:
        blockers.append("max_loss_usdt outside tiny-live cap")
    if max_position is None or max_position <= 0 or max_position > MAX_POSITION_NOTIONAL_USDT:
        blockers.append("max_position_notional_usdt outside tiny-live cap")
    if leverage is None or leverage <= 0 or leverage > 3:
        blockers.append("leverage missing or unsafe")
    if str(contract.get("margin_mode") or "").upper() != "ISOLATED_REQUIRED":
        blockers.append("margin_mode must be ISOLATED_REQUIRED")
    if contract.get("protective_stop_required") is not True:
        blockers.append("protective_stop_required must be true")
    if contract.get("take_profit_required") is not True:
        blockers.append("take_profit_required must be true")
    if str(contract.get("order_type") or "") != "not_created":
        blockers.append("order_type must remain not_created")
    status = RISK_CONTRACT_VALID_FOR_PREFLIGHT if not blockers else RISK_CONTRACT_INVALID
    return _validation(status, blockers)


def format_tiny_live_risk_contract_text(payload: Mapping[str, Any]) -> str:
    contract = payload.get("risk_contract") if isinstance(payload.get("risk_contract"), dict) else {}
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    funding = payload.get("funding_config") if isinstance(payload.get("funding_config"), dict) else {}
    return "\n".join(
        [
            f"R84.1 Tiny Live Risk Contract: {payload.get('status')}",
            str(payload.get("execution_mode")),
            f"candidate_id: {payload.get('candidate_id')}",
            f"stop_distance_pct: {contract.get('stop_distance_pct')}",
            f"take_profit_distance_pct: {contract.get('take_profit_distance_pct')}",
            f"max_margin_usdt: {contract.get('max_margin_usdt')}",
            f"max_loss_usdt: {contract.get('max_loss_usdt')}",
            f"leverage: {contract.get('leverage')}",
            f"margin_mode: {contract.get('margin_mode')}",
            f"funding_check_mode: {funding.get('funding_check_mode')}",
            f"validation_status: {validation.get('validation_status')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            NO_ORDER_NOTE,
        ]
    )


def _validation(status: str, blockers: list[str]) -> dict[str, Any]:
    return _sanitize(
        {
            "validation_status": status,
            "valid_for_preflight": status == RISK_CONTRACT_VALID_FOR_PREFLIGHT,
            "blockers": blockers,
            **_safety_fields(),
        }
    )


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safety_fields() -> dict[str, Any]:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "order_payload_created": ORDER_PAYLOAD_CREATED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in (
            "live_execution_enabled",
            "allow_live_orders",
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "order_payload_created",
            "network_allowed",
            "secrets_shown",
        ):
            if key in sanitized:
                sanitized[key] = False
        if "global_kill_switch" in sanitized:
            sanitized["global_kill_switch"] = True
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
