"""R84 live funding and final arming preflight.

This module is a read-only final preflight contract. It consumes local R83
quality evidence and local non-secret config only. It never places orders,
signs payloads, calls Binance, or enables live execution.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.miro_fish_quality_gate import (
    MIRO_FISH_SUPPORTS_CANDIDATE,
    build_miro_fish_quality_gate,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import (
    FUNDING_CONFIG_PRESENT as RISK_FUNDING_CONFIG_PRESENT,
    RISK_CONTRACT_VALID_FOR_PREFLIGHT,
    build_tiny_live_risk_contract_payload,
)

PHASE = "R84"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "LIVE_ARMING_PREFLIGHT_ONLY_NO_ORDER"

READY_FOR_OPERATOR_LIVE_ARMING_REVIEW = "READY_FOR_OPERATOR_LIVE_ARMING_REVIEW"
BLOCKED_BY_MISSING_RISK_CONTRACT = "BLOCKED_BY_MISSING_RISK_CONTRACT"
BLOCKED_BY_FUNDING_CONFIG = "BLOCKED_BY_FUNDING_CONFIG"
BLOCKED_BY_POSITION_SIZE = "BLOCKED_BY_POSITION_SIZE"
BLOCKED_BY_KILL_SWITCH = "BLOCKED_BY_KILL_SWITCH"
BLOCKED_BY_LIVE_ENV_LOCKS = "BLOCKED_BY_LIVE_ENV_LOCKS"
BLOCKED_BY_MISSING_OPERATOR_APPROVAL = "BLOCKED_BY_MISSING_OPERATOR_APPROVAL"
BLOCKED_BY_STRATEGY_QUALITY = "BLOCKED_BY_STRATEGY_QUALITY"
BLOCKED_BY_REGIME = "BLOCKED_BY_REGIME"
BLOCKED_BY_DATA_INTEGRITY = "BLOCKED_BY_DATA_INTEGRITY"
BLOCKED_BY_BETRAYAL_PENDING = "BLOCKED_BY_BETRAYAL_PENDING"
PREFLIGHT_OPERATOR_REVIEW_ONLY = "PREFLIGHT_OPERATOR_REVIEW_ONLY"

RISK_CONTRACT_COMPLETE = "RISK_CONTRACT_COMPLETE"
RISK_CONTRACT_PRESENT = "RISK_CONTRACT_PRESENT"
RISK_CONTRACT_VALID_FOR_PREFLIGHT_STATUS = "RISK_CONTRACT_VALID_FOR_PREFLIGHT"
RISK_CONTRACT_MISSING = "RISK_CONTRACT_MISSING"
RISK_CONTRACT_INVALID = "RISK_CONTRACT_INVALID"

FUNDING_CONFIG_PRESENT = "FUNDING_CONFIG_PRESENT"
FUNDING_CONFIG_MISSING = "FUNDING_CONFIG_MISSING"
FUNDING_CHECK_DEFERRED_NO_NETWORK = "FUNDING_CHECK_DEFERRED_NO_NETWORK"
FUNDING_BLOCKED_BY_LIVE_ENV_LOCKS = "FUNDING_BLOCKED_BY_LIVE_ENV_LOCKS"

LIVE_ENV_LOCKED_SAFE_FOR_PREFLIGHT = "LIVE_ENV_LOCKED_SAFE_FOR_PREFLIGHT"
LIVE_ENV_UNSAFE_FOR_PREFLIGHT = "LIVE_ENV_UNSAFE_FOR_PREFLIGHT"

MISSING_OPERATOR_APPROVAL = "MISSING_OPERATOR_APPROVAL"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_MAX_MARGIN_USDT = 44.0
DEFAULT_MAX_LOSS_USDT = 4.44
DEFAULT_MAX_POSITION_NOTIONAL_USDT = 44.0
ISOLATED_REQUIRED = "ISOLATED_REQUIRED"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R84 is preflight/readiness only. No orders, no signed payloads, no Binance."


def build_live_arming_preflight(
    *,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str | None = None,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    generated_at = datetime.now(UTC).isoformat()
    quality = build_miro_fish_quality_gate(
        symbol=symbol,
        timeframe=timeframe,
        family="NORMAL",
        log_dir=resolved_log_dir,
    )
    supported = [
        row
        for row in quality.get("top_supported_candidates", [])
        if isinstance(row, dict)
        and row.get("final_quality_status") == MIRO_FISH_SUPPORTS_CANDIDATE
        and (candidate_id is None or row.get("candidate_id") == candidate_id)
    ]
    candidate = supported[0] if supported else None
    live_env = build_live_env_preflight(env=source)
    risk_contract = build_risk_contract(candidate=candidate, env=source)
    funding = build_funding_preflight(env=source, live_env=live_env, risk_contract=risk_contract)
    approval = build_operator_approval_preflight(candidate=candidate)
    top_candidate = _top_candidate_preflight(
        candidate=candidate,
        risk_contract=risk_contract,
        funding=funding,
        live_env=live_env,
        approval=approval,
    )
    blockers = list(
        dict.fromkeys(
            [
                *top_candidate.get("blockers", []),
                *risk_contract.get("blockers", []),
                *funding.get("blockers", []),
                *live_env.get("blockers", []),
                *approval.get("blockers", []),
            ]
        )
    )
    final_status = _final_status(
        candidate=candidate,
        risk_contract=risk_contract,
        funding=funding,
        live_env=live_env,
    )
    top_candidate["final_preflight_status"] = final_status
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at,
            "archive_log_dir": str(resolved_log_dir),
            "config": {
                "symbol": symbol,
                "timeframe": timeframe,
                "candidate_id": candidate_id,
                "default_max_margin_usdt": DEFAULT_MAX_MARGIN_USDT,
                "default_max_loss_usdt": DEFAULT_MAX_LOSS_USDT,
                "default_max_position_notional_usdt": DEFAULT_MAX_POSITION_NOTIONAL_USDT,
                "network_check": "disabled",
                "risk_contract_source": risk_contract.get("risk_contract_source"),
            },
            "candidate_source_summary": {
                "phase": quality.get("phase"),
                "execution_mode": quality.get("execution_mode"),
                "supported_candidates": len(quality.get("top_supported_candidates") or []),
                "selected_candidate_id": candidate.get("candidate_id") if candidate else None,
            },
            "top_candidate_preflight": top_candidate,
            "risk_contract": risk_contract,
            "funding_preflight": funding,
            "live_env_preflight": live_env,
            "operator_approval_preflight": approval,
            "final_preflight_status": final_status,
            "blockers": blockers,
            "notes": [
                NO_ORDER_NOTE,
                "READY_FOR_OPERATOR_LIVE_ARMING_REVIEW is review readiness only, not approval to execute.",
                "Exact operator approval, funding verification, protective orders, and env arming remain future gated steps.",
            ],
            **_safety_fields(),
        }
    )


def build_risk_contract(*, candidate: Mapping[str, Any] | None, env: Mapping[str, str]) -> dict[str, Any]:
    candidate_id = str(candidate.get("candidate_id") or "") if candidate else ""
    config_payload = build_tiny_live_risk_contract_payload(candidate_id=candidate_id or "missing_candidate")
    config_contract = config_payload.get("risk_contract") if isinstance(config_payload.get("risk_contract"), dict) else {}
    config_validation = config_payload.get("validation") if isinstance(config_payload.get("validation"), dict) else {}
    if candidate is not None and config_validation.get("validation_status") == RISK_CONTRACT_VALID_FOR_PREFLIGHT:
        return _risk_contract_from_config(candidate=candidate, config_payload=config_payload)
    stop_price = _float_or_none(env.get("HAMMER_R84_STOP_PRICE"))
    take_profit_price = _float_or_none(env.get("HAMMER_R84_TAKE_PROFIT_PRICE"))
    stop_distance = _float_or_none(env.get("HAMMER_R84_STOP_DISTANCE_PCT"))
    take_profit_distance = _float_or_none(env.get("HAMMER_R84_TAKE_PROFIT_DISTANCE_PCT"))
    max_position = _float_or_none(env.get("HAMMER_R84_MAX_POSITION_NOTIONAL_USDT")) or DEFAULT_MAX_POSITION_NOTIONAL_USDT
    max_margin = _float_or_none(env.get("HAMMER_R84_MAX_MARGIN_USDT")) or DEFAULT_MAX_MARGIN_USDT
    max_loss = _float_or_none(env.get("HAMMER_R84_MAX_LOSS_USDT")) or DEFAULT_MAX_LOSS_USDT
    leverage = _float_or_none(env.get("HAMMER_R84_LEVERAGE"))
    margin_mode = str(env.get("HAMMER_R84_MARGIN_MODE") or ISOLATED_REQUIRED).upper()
    blockers: list[str] = []
    if candidate is None:
        blockers.append("no_miro_fish_supported_candidate")
    if stop_price is None and stop_distance is None:
        blockers.append("missing_stop_price_or_stop_distance_pct")
    if take_profit_price is None and take_profit_distance is None:
        blockers.append("missing_take_profit_price_or_take_profit_distance_pct")
    if stop_distance is not None and stop_distance <= 0:
        blockers.append("stop_distance_pct must be positive")
    if take_profit_distance is not None and take_profit_distance <= 0:
        blockers.append("take_profit_distance_pct must be positive")
    risk_reward = round(take_profit_distance / stop_distance, 4) if stop_distance and take_profit_distance else None
    if risk_reward is not None and risk_reward < 1.0:
        blockers.append("risk_reward_ratio below 1.0")
    if max_position > DEFAULT_MAX_POSITION_NOTIONAL_USDT:
        blockers.append("max_position_notional_usdt exceeds tiny-live cap")
    if max_margin > DEFAULT_MAX_MARGIN_USDT:
        blockers.append("max_margin_usdt exceeds tiny-live cap")
    if max_loss > DEFAULT_MAX_LOSS_USDT:
        blockers.append("max_loss_usdt exceeds tiny-live cap")
    if margin_mode not in {"ISOLATED", ISOLATED_REQUIRED}:
        blockers.append("margin_mode must be isolated")
    missing = any(item.startswith("missing_") for item in blockers)
    position_blocker = any("exceeds tiny-live cap" in item for item in blockers)
    status = RISK_CONTRACT_MISSING if missing else RISK_CONTRACT_INVALID if blockers else RISK_CONTRACT_COMPLETE
    if position_blocker:
        status = BLOCKED_BY_POSITION_SIZE
    return _sanitize(
        {
            "risk_contract_status": status,
            "risk_contract_source": "env_fallback",
            "risk_contract_loaded": False,
            "risk_contract_validation": config_validation,
            "symbol": candidate.get("symbol") if candidate else None,
            "timeframe": candidate.get("timeframe") if candidate else None,
            "direction": candidate.get("direction") if candidate else None,
            "entry_mode": candidate.get("entry_mode") if candidate else None,
            "entry_price_source": env.get("HAMMER_R84_ENTRY_PRICE_SOURCE") or "operator_supplied_or_future_ticket_builder",
            "stop_price": stop_price,
            "take_profit_price": take_profit_price,
            "stop_distance_pct": stop_distance,
            "take_profit_distance_pct": take_profit_distance,
            "risk_reward_ratio": risk_reward,
            "max_position_notional_usdt": max_position,
            "max_margin_usdt": max_margin,
            "max_loss_usdt": max_loss,
            "leverage": leverage,
            "margin_mode": margin_mode,
            "reduce_only_allowed": True,
            "protective_stop_required": True,
            "take_profit_required": True,
            "order_type": "not_created",
            "blockers": blockers,
            **_safety_fields(),
        }
    )


def build_funding_preflight(
    *,
    env: Mapping[str, str],
    live_env: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
) -> dict[str, Any]:
    if risk_contract.get("funding_config_loaded") is True:
        present = risk_contract.get("funding_status") == FUNDING_CONFIG_PRESENT
        return _sanitize(
            {
                "funding_status": FUNDING_CONFIG_PRESENT if present else FUNDING_CONFIG_MISSING,
                "funding_check_mode": risk_contract.get("funding_check_mode"),
                "funding_config_present": present,
                "funding_config_loaded": True,
                "account_balance_checked": False,
                "account_balance_source": "not_checked_no_network",
                "effective_max_margin_usdt": risk_contract.get("max_margin_usdt"),
                "effective_max_loss_usdt": risk_contract.get("max_loss_usdt"),
                "network_allowed": False,
                "blockers": [] if present else ["funding_config_missing"],
                **_safety_fields(),
            }
        )
    present = _env_bool(env.get("HAMMER_R84_FUNDING_CONFIG_PRESENT"), default=False)
    blockers = []
    if live_env.get("live_env_status") == LIVE_ENV_UNSAFE_FOR_PREFLIGHT:
        status = FUNDING_BLOCKED_BY_LIVE_ENV_LOCKS
        blockers.append("live_env_locks_unsafe")
    elif not present:
        status = FUNDING_CONFIG_MISSING
        blockers.append("funding_config_missing")
    else:
        status = FUNDING_CONFIG_PRESENT
    return _sanitize(
        {
            "funding_status": status,
            "funding_check_mode": FUNDING_CHECK_DEFERRED_NO_NETWORK,
            "funding_config_present": present,
            "funding_config_loaded": False,
            "account_balance_checked": False,
            "account_balance_source": "not_checked_no_network",
            "effective_max_margin_usdt": None,
            "effective_max_loss_usdt": None,
            "network_allowed": False,
            "blockers": blockers,
            **_safety_fields(),
        }
    )


def build_live_env_preflight(*, env: Mapping[str, str]) -> dict[str, Any]:
    binance_live_enabled = _env_bool(env.get("HAMMER_BINANCE_LIVE_ENABLED"), default=False)
    configured_live_execution_enabled = _env_bool(env.get("HAMMER_LIVE_EXECUTION_ENABLED"), default=False)
    configured_allow_live_orders = _env_bool(env.get("HAMMER_ALLOW_LIVE_ORDERS"), default=False)
    configured_global_kill_switch = _env_bool(env.get("HAMMER_GLOBAL_KILL_SWITCH"), default=True)
    blockers = []
    if binance_live_enabled:
        blockers.append("HAMMER_BINANCE_LIVE_ENABLED is true during R84 preflight")
    if configured_live_execution_enabled:
        blockers.append("HAMMER_LIVE_EXECUTION_ENABLED is true during R84 preflight")
    if configured_allow_live_orders:
        blockers.append("HAMMER_ALLOW_LIVE_ORDERS is true during R84 preflight")
    if not configured_global_kill_switch:
        blockers.append("HAMMER_GLOBAL_KILL_SWITCH is false during R84 preflight")
    status = LIVE_ENV_UNSAFE_FOR_PREFLIGHT if blockers else LIVE_ENV_LOCKED_SAFE_FOR_PREFLIGHT
    return _sanitize(
        {
            "live_env_status": status,
            "binance_live_enabled": binance_live_enabled,
            "configured_live_execution_enabled": configured_live_execution_enabled,
            "configured_allow_live_orders": configured_allow_live_orders,
            "configured_global_kill_switch": configured_global_kill_switch,
            "live_execution_enabled": LIVE_EXECUTION_ENABLED,
            "allow_live_orders": ALLOW_LIVE_ORDERS,
            "global_kill_switch": GLOBAL_KILL_SWITCH,
            "blockers": blockers,
            **_safety_fields(),
        }
    )


def build_operator_approval_preflight(*, candidate: Mapping[str, Any] | None) -> dict[str, Any]:
    return _sanitize(
        {
            "operator_approval_required": True,
            "exact_candidate_id_required": True,
            "exact_risk_contract_required": True,
            "approval_token_required": True,
            "approval_record_required": True,
            "ticket_required": True,
            "ticket_builder_status": "R85_NON_EXECUTABLE_TICKET_REQUIRED",
            "approval_status": MISSING_OPERATOR_APPROVAL,
            "candidate_id": candidate.get("candidate_id") if candidate else None,
            "blockers": ["missing_operator_approval"],
            **_safety_fields(),
        }
    )


def format_live_arming_preflight_text(payload: Mapping[str, Any]) -> str:
    top = payload.get("top_candidate_preflight") if isinstance(payload.get("top_candidate_preflight"), dict) else {}
    risk = payload.get("risk_contract") if isinstance(payload.get("risk_contract"), dict) else {}
    funding = payload.get("funding_preflight") if isinstance(payload.get("funding_preflight"), dict) else {}
    live_env = payload.get("live_env_preflight") if isinstance(payload.get("live_env_preflight"), dict) else {}
    approval = payload.get("operator_approval_preflight") if isinstance(payload.get("operator_approval_preflight"), dict) else {}
    blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
    return "\n".join(
        [
            f"R84 Live Arming Preflight: {payload.get('status')}",
            str(payload.get("execution_mode")),
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            f"top_candidate: {top.get('candidate_id') or 'none'}",
            f"miro_fish: {top.get('miro_fish_status') or 'n/a'} score={top.get('miro_fish_score')}",
            f"risk_contract_status: {risk.get('risk_contract_status')}",
            f"funding_status: {funding.get('funding_status')}",
            f"live_env_status: {live_env.get('live_env_status')} kill_switch={live_env.get('configured_global_kill_switch')}",
            f"operator_approval_status: {approval.get('approval_status')}",
            f"final_preflight_status: {payload.get('final_preflight_status')}",
            f"blockers: {', '.join(str(item) for item in blockers) if blockers else 'none'}",
            NO_ORDER_NOTE,
        ]
    )


def _top_candidate_preflight(
    *,
    candidate: Mapping[str, Any] | None,
    risk_contract: Mapping[str, Any],
    funding: Mapping[str, Any],
    live_env: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    blockers = []
    if candidate is None:
        blockers.append("no_supported_miro_fish_candidate")
    if risk_contract.get("risk_contract_status") not in {RISK_CONTRACT_COMPLETE, RISK_CONTRACT_VALID_FOR_PREFLIGHT_STATUS}:
        blockers.append("risk_contract_incomplete")
    if funding.get("funding_status") != FUNDING_CONFIG_PRESENT:
        blockers.append("funding_config_not_ready")
    if live_env.get("live_env_status") != LIVE_ENV_LOCKED_SAFE_FOR_PREFLIGHT:
        blockers.append("live_env_locks_unsafe")
    if approval.get("approval_status") == MISSING_OPERATOR_APPROVAL:
        blockers.append("missing_operator_approval")
    return _sanitize(
        {
            "candidate_id": candidate.get("candidate_id") if candidate else None,
            "symbol": candidate.get("symbol") if candidate else None,
            "timeframe": candidate.get("timeframe") if candidate else None,
            "direction": candidate.get("direction") if candidate else None,
            "entry_mode": candidate.get("entry_mode") if candidate else None,
            "miro_fish_status": candidate.get("final_quality_status") if candidate else None,
            "miro_fish_score": candidate.get("final_quality_score") if candidate else None,
            "markov_regime": candidate.get("markov_regime") if candidate else None,
            "markov_gate_status": candidate.get("markov_gate_status") if candidate else None,
            "source_recommendation": candidate.get("source_recommendation") if candidate else None,
            "risk_contract_status": risk_contract.get("risk_contract_status"),
            "funding_status": funding.get("funding_status"),
            "live_env_status": live_env.get("live_env_status"),
            "operator_approval_status": approval.get("approval_status"),
            "final_preflight_status": None,
            "blockers": blockers,
            "operator_note": "Review only. Exact future approval and ticket builder still required.",
            **_safety_fields(),
        }
    )


def _final_status(
    *,
    candidate: Mapping[str, Any] | None,
    risk_contract: Mapping[str, Any],
    funding: Mapping[str, Any],
    live_env: Mapping[str, Any],
) -> str:
    if candidate is None:
        return BLOCKED_BY_STRATEGY_QUALITY
    if risk_contract.get("risk_contract_status") == BLOCKED_BY_POSITION_SIZE:
        return BLOCKED_BY_POSITION_SIZE
    if risk_contract.get("risk_contract_status") not in {RISK_CONTRACT_COMPLETE, RISK_CONTRACT_VALID_FOR_PREFLIGHT_STATUS}:
        return BLOCKED_BY_MISSING_RISK_CONTRACT
    if funding.get("funding_status") != FUNDING_CONFIG_PRESENT:
        return BLOCKED_BY_FUNDING_CONFIG
    if live_env.get("live_env_status") != LIVE_ENV_LOCKED_SAFE_FOR_PREFLIGHT:
        if live_env.get("configured_global_kill_switch") is False:
            return BLOCKED_BY_KILL_SWITCH
        return BLOCKED_BY_LIVE_ENV_LOCKS
    return BLOCKED_BY_MISSING_OPERATOR_APPROVAL


def _risk_contract_from_config(
    *,
    candidate: Mapping[str, Any],
    config_payload: Mapping[str, Any],
) -> dict[str, Any]:
    contract = config_payload.get("risk_contract") if isinstance(config_payload.get("risk_contract"), dict) else {}
    funding = config_payload.get("funding_config") if isinstance(config_payload.get("funding_config"), dict) else {}
    validation = config_payload.get("validation") if isinstance(config_payload.get("validation"), dict) else {}
    return _sanitize(
        {
            "risk_contract_status": RISK_CONTRACT_VALID_FOR_PREFLIGHT_STATUS,
            "risk_contract_source": config_payload.get("config_path"),
            "risk_contract_loaded": True,
            "risk_contract_validation": validation,
            "funding_config_loaded": True,
            "funding_status": FUNDING_CONFIG_PRESENT
            if funding.get("funding_status") == RISK_FUNDING_CONFIG_PRESENT
            else FUNDING_CONFIG_MISSING,
            "funding_check_mode": funding.get("funding_check_mode"),
            "symbol": contract.get("symbol") or candidate.get("symbol"),
            "timeframe": contract.get("timeframe") or candidate.get("timeframe"),
            "direction": contract.get("direction") or candidate.get("direction"),
            "entry_mode": contract.get("entry_mode") or candidate.get("entry_mode"),
            "entry_price_source": contract.get("entry_price_source"),
            "stop_price": contract.get("stop_price"),
            "take_profit_price": contract.get("take_profit_price"),
            "stop_distance_pct": contract.get("stop_distance_pct"),
            "take_profit_distance_pct": contract.get("take_profit_distance_pct"),
            "risk_reward_ratio": contract.get("risk_reward_ratio"),
            "max_position_notional_usdt": contract.get("max_position_notional_usdt"),
            "max_margin_usdt": contract.get("max_margin_usdt"),
            "max_loss_usdt": contract.get("max_loss_usdt"),
            "leverage": contract.get("leverage"),
            "margin_mode": contract.get("margin_mode"),
            "reduce_only_allowed": contract.get("reduce_only_allowed") is True,
            "protective_stop_required": contract.get("protective_stop_required") is True,
            "take_profit_required": contract.get("take_profit_required") is True,
            "order_type": contract.get("order_type"),
            "effective_max_margin_usdt": contract.get("max_margin_usdt"),
            "effective_max_loss_usdt": contract.get("max_loss_usdt"),
            "effective_leverage": contract.get("leverage"),
            "effective_margin_mode": contract.get("margin_mode"),
            "blockers": [],
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


def _env_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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
