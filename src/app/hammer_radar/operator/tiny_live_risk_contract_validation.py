"""Shared R265 tiny-live risk-contract interpretation.

This module is deliberately read-only. It normalizes tiny-live contract values
for operator surfaces and submit gates without enabling execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PROPER_TINY_LIVE_CONTRACT_MODE = "position_notional_cap"
EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE = "explicit_notional_cap_with_leverage"
MARGIN_BUDGET_CONTRACT_MODE = "margin_budget_cap"
DEFAULT_MAX_POSITION_NOTIONAL_USDT = 44.0
DEFAULT_MAX_MARGIN_BUDGET_USDT = 44.0
DEFAULT_MAX_LOSS_USDT = 4.44
DEFAULT_MAX_LEVERAGE = 3.0
R267_MAX_POSITION_NOTIONAL_USDT = 80.0
R267_MAX_LEVERAGE = 10.0
DEFAULT_RISK_CONTRACT_CONFIG_PATH = Path("configs/hammer_radar/tiny_live_risk_contracts.json")
DEFAULT_OFFICIAL_LANE_KEY = "BTCUSDT|8m|short|ladder_close_50_618"


def load_tiny_live_risk_contract_for_lane(
    *,
    risk_contract_config_path: str | Path | None = None,
    official_lane_key: str = DEFAULT_OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    path = Path(risk_contract_config_path) if risk_contract_config_path is not None else DEFAULT_RISK_CONTRACT_CONFIG_PATH
    if not path.exists():
        return {"found": False, "path": str(path), "contract": {}, "official_contract_found": False}
    raw = json.loads(path.read_text(encoding="utf-8"))
    contract = _matching_contract(raw, official_lane_key)
    return {
        "found": True,
        "path": str(path),
        "raw": raw,
        "contract": contract,
        "official_contract_found": bool(contract),
    }


def build_tiny_live_risk_contract_validation_summary(
    *,
    risk_contract: Mapping[str, Any],
    candidate_qty: Any = None,
    candidate_reference_price: Any = None,
    candidate_notional_usdt: Any = None,
    candidate_estimated_loss_usdt: Any = None,
    stop_distance_loss_usdt: Any = None,
    step_size: Any = None,
    min_notional: Any = None,
    require_live_execution_enabled: bool = False,
) -> dict[str, Any]:
    contract = _contract_row(risk_contract)
    mode = str(contract.get("tiny_live_contract_mode") or PROPER_TINY_LIVE_CONTRACT_MODE)
    margin_budget = _num(
        contract.get("margin_budget_usdt")
        or contract.get("tiny_live_margin_usdt")
        or contract.get("max_margin_usdt")
    )
    leverage = _num(contract.get("leverage"))
    configured_notional = _num(
        contract.get("max_position_notional_usdt")
        or contract.get("max_notional_usdt")
    )
    max_loss = _num(contract.get("max_loss_usdt"))
    candidate_notional = _resolve_candidate_notional(
        candidate_notional_usdt=candidate_notional_usdt,
        candidate_qty=candidate_qty,
        candidate_reference_price=candidate_reference_price,
    )
    estimated_loss = _num(candidate_estimated_loss_usdt)
    stop_loss = _num(stop_distance_loss_usdt)
    effective_loss = stop_loss if stop_loss is not None else estimated_loss
    effective_notional_cap = _effective_notional_cap(mode=mode, configured_notional=configured_notional)
    derived_margin = _derived_margin_budget(
        mode=mode,
        configured_notional=configured_notional,
        effective_notional_cap=effective_notional_cap,
        leverage=leverage,
    )

    blockers: list[str] = []
    if not contract:
        blockers.append("risk_contract_config_missing")
    if contract.get("symbol") != "BTCUSDT":
        blockers.append("risk_contract_symbol_not_BTCUSDT")
    if max_loss is None:
        blockers.append("risk_contract_max_loss_missing")
    elif max_loss > DEFAULT_MAX_LOSS_USDT + 0.000001:
        blockers.append("risk_contract_max_loss_exceeds_4_44")
    if margin_budget is None:
        blockers.append("risk_contract_margin_budget_missing")
    elif mode != EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE and margin_budget > DEFAULT_MAX_MARGIN_BUDGET_USDT + 0.000001:
        blockers.append("risk_contract_margin_budget_exceeds_44")
    if leverage is None:
        blockers.append("risk_contract_leverage_missing")
    elif leverage > _max_leverage_for_mode(mode) + 0.000001:
        blockers.append(_leverage_exceeds_blocker(mode))
    if mode not in {
        PROPER_TINY_LIVE_CONTRACT_MODE,
        EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE,
        MARGIN_BUDGET_CONTRACT_MODE,
    }:
        blockers.append("risk_contract_mode_unknown")
    if mode == MARGIN_BUDGET_CONTRACT_MODE:
        blockers.append("margin_budget_contract_mode_requires_future_manual_acceptance")
    if configured_notional is None:
        blockers.append("risk_contract_notional_cap_missing")
    elif configured_notional > _max_notional_for_mode(mode) + 0.000001:
        blockers.append(_notional_cap_exceeds_blocker(mode))
    if (
        mode == PROPER_TINY_LIVE_CONTRACT_MODE
        and margin_budget is not None
        and leverage is not None
        and margin_budget * leverage > DEFAULT_MAX_POSITION_NOTIONAL_USDT + 0.000001
    ):
        blockers.append("margin_budget_times_leverage_exceeds_position_notional_cap")
    if (
        mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE
        and margin_budget is not None
        and derived_margin is not None
        and abs(margin_budget - derived_margin) > 0.01
    ):
        blockers.append("margin_budget_must_match_notional_divided_by_leverage")
    if require_live_execution_enabled and contract.get("live_execution_enabled") is not True:
        blockers.append("risk_contract_live_execution_not_enabled")
    if candidate_notional is not None and effective_notional_cap is not None:
        if candidate_notional > effective_notional_cap + 0.000001:
            blockers.append("candidate_notional_exceeds_position_notional_cap")
    if effective_loss is not None and max_loss is not None and effective_loss > max_loss + 0.000001:
        blockers.append("candidate_loss_exceeds_max_loss")
    minimum_order_notional = _minimum_order_notional(
        candidate_reference_price=candidate_reference_price,
        step_size=step_size,
        min_notional=min_notional,
    )
    clears_exchange_minimum = (
        minimum_order_notional is not None
        and effective_notional_cap is not None
        and minimum_order_notional <= effective_notional_cap + 0.000001
    )
    if minimum_order_notional is not None and effective_notional_cap is not None and not clears_exchange_minimum:
        blockers.append("proper_tiny_live_below_exchange_minimum")

    valid = not blockers
    meaning = (
        "80 USDT is interpreted as maximum position/notional; 10x leverage derives about 8 USDT margin and cannot expand notional above 80."
        if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE
        else "44 USDT is interpreted as maximum position/notional, not margin multiplied by leverage."
        if mode == PROPER_TINY_LIVE_CONTRACT_MODE
        else "44 USDT is configured as margin budget; R265 does not accept the implied higher notional."
    )
    if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE:
        meaning = (
            "R267 operator decision: 10x is intentional, but BTCUSDT tiny live is capped at "
            "80 USDT notional, not hidden margin expansion."
        )
    return {
        "valid": valid,
        "risk_contract_valid": valid,
        "tiny_live_contract_mode": mode,
        "contract_mode_explicit": "tiny_live_contract_mode" in contract,
        "forty_four_usdt_meaning": meaning,
        "max_position_notional_usdt": effective_notional_cap,
        "configured_max_position_notional_usdt": configured_notional,
        "configured_max_notional_usdt": _num(contract.get("max_notional_usdt")),
        "margin_budget_usdt": margin_budget,
        "derived_margin_budget_usdt": derived_margin,
        "leverage": leverage,
        "max_loss_usdt": max_loss,
        "candidate_qty": _num(candidate_qty),
        "candidate_reference_price": _num(candidate_reference_price),
        "candidate_notional_usdt": candidate_notional,
        "candidate_estimated_loss_usdt": estimated_loss,
        "stop_distance_loss_usdt": stop_loss,
        "minimum_order_notional_usdt": minimum_order_notional,
        "clears_exchange_minimum": clears_exchange_minimum,
        "live_execution_enabled": contract.get("live_execution_enabled") is True,
        "require_live_execution_enabled": bool(require_live_execution_enabled),
        "higher_notional_interpretation_rejected": bool(
            mode == MARGIN_BUDGET_CONTRACT_MODE
            or (
                configured_notional is not None
                and effective_notional_cap is not None
                and configured_notional > effective_notional_cap + 0.000001
            )
        ),
        "blocked_by": _dedupe(blockers),
    }


def _contract_row(risk_contract: Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(risk_contract.get("contract"), Mapping):
        return risk_contract["contract"]  # type: ignore[return-value]
    return risk_contract


def _matching_contract(raw: Mapping[str, Any], official_lane_key: str) -> dict[str, Any]:
    for row in raw.get("risk_contracts", []) if isinstance(raw.get("risk_contracts"), list) else []:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("official_lane_key") or "") == official_lane_key:
            return dict(row)
        if _lane_key_from_row(row) == official_lane_key:
            return dict(row)
    return {}


def _lane_key_from_row(row: Mapping[str, Any]) -> str:
    return "|".join(
        str(row.get(key) or "")
        for key in ("symbol", "timeframe", "direction", "entry_mode")
    )


def _effective_notional_cap(*, mode: str, configured_notional: float | None) -> float | None:
    if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE:
        if configured_notional is None:
            return R267_MAX_POSITION_NOTIONAL_USDT
        return min(configured_notional, R267_MAX_POSITION_NOTIONAL_USDT)
    if mode == PROPER_TINY_LIVE_CONTRACT_MODE:
        if configured_notional is None:
            return DEFAULT_MAX_POSITION_NOTIONAL_USDT
        return min(configured_notional, DEFAULT_MAX_POSITION_NOTIONAL_USDT)
    return configured_notional


def _max_notional_for_mode(mode: str) -> float:
    if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE:
        return R267_MAX_POSITION_NOTIONAL_USDT
    return DEFAULT_MAX_POSITION_NOTIONAL_USDT


def _max_leverage_for_mode(mode: str) -> float:
    if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE:
        return R267_MAX_LEVERAGE
    return DEFAULT_MAX_LEVERAGE


def _notional_cap_exceeds_blocker(mode: str) -> str:
    if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE:
        return "risk_contract_notional_cap_exceeds_80"
    return "risk_contract_notional_cap_exceeds_44"


def _leverage_exceeds_blocker(mode: str) -> str:
    if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE:
        return "risk_contract_leverage_exceeds_10"
    return "risk_contract_leverage_exceeds_3"


def _derived_margin_budget(
    *,
    mode: str,
    configured_notional: float | None,
    effective_notional_cap: float | None,
    leverage: float | None,
) -> float | None:
    if mode != EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE or leverage is None or leverage <= 0:
        return None
    notional = configured_notional if configured_notional is not None else effective_notional_cap
    if notional is None:
        return None
    return round(notional / leverage, 8)


def _resolve_candidate_notional(
    *, candidate_notional_usdt: Any, candidate_qty: Any, candidate_reference_price: Any
) -> float | None:
    notional = _num(candidate_notional_usdt)
    if notional is not None:
        return notional
    qty = _num(candidate_qty)
    price = _num(candidate_reference_price)
    if qty is None or price is None:
        return None
    return round(qty * price, 8)


def _minimum_order_notional(*, candidate_reference_price: Any, step_size: Any, min_notional: Any) -> float | None:
    price = _num(candidate_reference_price)
    step = _num(step_size)
    exchange_min = _num(min_notional)
    minimums: list[float] = []
    if exchange_min is not None:
        minimums.append(exchange_min)
    if price is not None and step is not None and price > 0 and step > 0:
        minimums.append(price * step)
    return max(minimums) if minimums else None


def _num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(items: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))
