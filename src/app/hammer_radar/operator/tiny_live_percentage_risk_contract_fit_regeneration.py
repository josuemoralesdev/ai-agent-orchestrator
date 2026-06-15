"""R262B percentage risk-contract fit regeneration.

This phase converts the official tiny-live contract to an equivalent
percentage model and, only after exact confirmation, runs the existing
R253/R253B/R254/R255/R261 review chain to regenerate a contract-fit triplet.
It never submits, places orders, arms controls, calls private Binance
endpoints, or loosens the R267 resolved 80 USDT notional / 10x leverage /
derived 8 USDT margin / 4.44 USDT max-loss model.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_actual_submit_gate import (
    DRY_PREVIEW_CONFIRMATION_PHRASE,
    RISK_CONTRACT_CONFIG_PATH,
    build_tiny_live_actual_submit_gate,
)
from src.app.hammer_radar.operator.tiny_live_controls_arming import (
    REVIEW_CONFIRMATION_PHRASE,
    build_tiny_live_controls_review,
    load_tiny_live_risk_contract,
)
from src.app.hammer_radar.operator.tiny_live_final_readonly_mark_price_refresh_gate import (
    CONFIRM_TINY_LIVE_FINAL_READONLY_REFRESH_PHRASE,
    build_tiny_live_final_readonly_mark_price_refresh_gate,
)
from src.app.hammer_radar.operator.tiny_live_fresh_context_signed_request_regeneration_gate import (
    CONFIRM_TINY_LIVE_FRESH_CONTEXT_REGENERATION_PHRASE,
    build_tiny_live_fresh_context_signed_request_regeneration_gate,
    compute_fresh_contract_fit_quantity,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_validation import (
    DEFAULT_MAX_LEVERAGE,
    DEFAULT_MAX_POSITION_NOTIONAL_USDT,
    EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE,
    PROPER_TINY_LIVE_CONTRACT_MODE,
    R267_MAX_LEVERAGE,
    R267_MAX_POSITION_NOTIONAL_USDT,
    build_tiny_live_risk_contract_validation_summary,
)
from src.app.hammer_radar.operator.tiny_live_submit_gate_preview import (
    CONFIRM_TINY_LIVE_SUBMIT_GATE_PREVIEW_PHRASE,
    build_tiny_live_submit_gate_preview,
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R262B_TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_TRIPLET"
EVENT_TYPE = "TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT"
LEDGER_FILENAME = "tiny_live_percentage_risk_contract_fit.ndjson"

CONTRACT_FIT_CONFIRMATION_PHRASE = (
    "I CONFIRM TINY LIVE PERCENTAGE RISK CONTRACT FIT REGENERATION ONLY; "
    "80 USDT NOTIONAL CAP, DERIVED 8 USDT MARGIN, 10X LEVERAGE, "
    "KEEP RISK SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE ORDER CALL."
)

TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_READY = "TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_READY"
TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_RECORDED = "TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_RECORDED"
TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_REJECTED = "TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_REJECTED"
TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED = "TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED"
TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_ERROR = "TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_ERROR"

TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_READY_FOR_CONFIRMATION = (
    "TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_READY_FOR_CONFIRMATION"
)
TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_RECORDED_CONTROLS_REVIEW_REQUIRED = (
    "TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_RECORDED_CONTROLS_REVIEW_REQUIRED"
)
TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_RECORDED_RISK_VALID = (
    "TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_RECORDED_RISK_VALID"
)
TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED_UNSAFE_RISK_CHANGE = (
    "TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED_UNSAFE_RISK_CHANGE"
)
TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED_BY_SIZING = (
    "TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED_BY_SIZING"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/tiny_live_risk_contract_fix.py",
    "src/app/hammer_radar/operator/tiny_live_final_readonly_mark_price_refresh_gate.py",
    "src/app/hammer_radar/operator/tiny_live_fresh_context_signed_request_regeneration_gate.py",
    "src/app/hammer_radar/operator/tiny_live_submit_gate_preview.py",
    "src/app/hammer_radar/operator/tiny_live_actual_submit_gate.py",
    "src/app/hammer_radar/operator/tiny_live_controls_arming.py",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_percentage_risk_contract_fit_regeneration(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    run_contract_fit_regeneration: bool = False,
    record_contract_fit_regeneration: bool = False,
    confirm_contract_fit_regeneration: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    confirmation_valid = confirm_contract_fit_regeneration == CONTRACT_FIT_CONFIRMATION_PHRASE
    symbol, timeframe, direction, _entry_mode = _lane_parts(official_lane_key)
    try:
        current = load_current_tiny_live_risk_contract(
            risk_contract_config_path=risk_path,
            official_lane_key=official_lane_key,
        )
        percentage_model = derive_percentage_risk_contract_model(current)
        resolved = resolve_percentage_risk_contract_values(percentage_model)
        percentage_model["resolved_values"] = dict(resolved)
        risk_interpretation = build_tiny_live_risk_contract_validation_summary(
            risk_contract=current,
            require_live_execution_enabled=False,
        )
        same_or_stricter = validate_percentage_contract_same_or_stricter(
            current_contract=current.get("contract") if isinstance(current.get("contract"), Mapping) else {},
            resolved_values=resolved,
            risk_interpretation=risk_interpretation,
        )
        sizing_plan = build_contract_fit_sizing_plan(
            fresh_mark_price=None,
            resolved_values=resolved,
            step_size=None,
            min_notional=None,
        )
        step_results = _empty_step_results()
        schema_update = step_results["percentage_schema_update"]
        if run_contract_fit_regeneration and not confirmation_valid:
            overall = TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_REJECTED_BAD_CONFIRMATION
            status = TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_REJECTED
        elif run_contract_fit_regeneration and same_or_stricter.get("valid") is not True:
            overall = TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED_UNSAFE_RISK_CHANGE
            status = TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED
            schema_update["blocked_by"] = list(same_or_stricter.get("blocked_by") or [])
        elif run_contract_fit_regeneration and confirmation_valid:
            schema_update = apply_percentage_risk_contract_schema_update(
                risk_contract_config_path=risk_path,
                percentage_contract_model=percentage_model,
                resolved_values=resolved,
                safety_validation=same_or_stricter,
                confirmation_valid=confirmation_valid,
                official_lane_key=official_lane_key,
                now=generated_at,
            )
            step_results["percentage_schema_update"] = schema_update
            if schema_update["succeeded"]:
                step_results["readonly_refresh"] = run_contract_fit_readonly_refresh(
                    log_dir=resolved_log_dir,
                    official_lane_key=official_lane_key,
                )
                readonly = step_results["readonly_refresh"]
                sizing_plan = build_contract_fit_sizing_plan(
                    fresh_mark_price=readonly.get("fresh_mark_price"),
                    resolved_values=resolved,
                    step_size=readonly.get("step_size"),
                    min_notional=readonly.get("min_notional"),
                )
                risk_interpretation = build_tiny_live_risk_contract_validation_summary(
                    risk_contract=current,
                    candidate_qty=sizing_plan.get("candidate_qty"),
                    candidate_reference_price=readonly.get("fresh_mark_price"),
                    candidate_notional_usdt=sizing_plan.get("candidate_notional_usdt"),
                    candidate_estimated_loss_usdt=sizing_plan.get("candidate_estimated_loss_usdt"),
                    step_size=readonly.get("step_size"),
                    min_notional=readonly.get("min_notional"),
                    require_live_execution_enabled=False,
                )
            if schema_update["succeeded"] and not sizing_plan.get("blocked_by"):
                step_results["signed_regeneration"] = run_contract_fit_signed_regeneration(
                    log_dir=resolved_log_dir,
                    official_lane_key=official_lane_key,
                )
            if step_results["signed_regeneration"]["succeeded"]:
                step_results["submit_preview"] = run_contract_fit_submit_preview(
                    log_dir=resolved_log_dir,
                    official_lane_key=official_lane_key,
                )
            if step_results["submit_preview"]["succeeded"]:
                step_results["dry_preview"] = run_contract_fit_dry_preview(
                    log_dir=resolved_log_dir,
                    official_lane_key=official_lane_key,
                )
            if step_results["dry_preview"]["succeeded"] or step_results["dry_preview"].get("risk_contract_valid"):
                step_results["controls_review"] = run_contract_fit_controls_review(
                    log_dir=resolved_log_dir,
                    official_lane_key=official_lane_key,
                )
            validation = build_contract_fit_output_validation(
                sizing_plan=sizing_plan,
                step_results=step_results,
                same_or_stricter=same_or_stricter,
                risk_interpretation=risk_interpretation,
            )
            overall = classify_tiny_live_percentage_contract_fit_status(
                run_requested=run_contract_fit_regeneration,
                record_requested=record_contract_fit_regeneration,
                confirmation_valid=confirmation_valid,
                recorded=record_contract_fit_regeneration and confirmation_valid,
                output_validation=validation,
                step_results=step_results,
            )
            status = _top_level_status(
                run_requested=run_contract_fit_regeneration,
                record_requested=record_contract_fit_regeneration,
                confirmation_valid=confirmation_valid,
                output_validation=validation,
                recorded=record_contract_fit_regeneration and confirmation_valid,
            )
        else:
            validation = build_contract_fit_output_validation(
                sizing_plan=sizing_plan,
                step_results=step_results,
                same_or_stricter=same_or_stricter,
                risk_interpretation=risk_interpretation,
            )
            overall = TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_READY_FOR_CONFIRMATION
            status = TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_READY

        validation = locals().get("validation") or build_contract_fit_output_validation(
            sizing_plan=sizing_plan,
            step_results=step_results,
            same_or_stricter=same_or_stricter,
            risk_interpretation=risk_interpretation,
        )
        packet = build_contract_fit_go_no_go_packet(
            output_validation=validation,
            step_results=step_results,
        )
        matrix = build_contract_fit_matrix(
            percentage_model=percentage_model,
            sizing_plan=sizing_plan,
            output_validation=validation,
            step_results=step_results,
        )
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "run_contract_fit_regeneration_requested": bool(run_contract_fit_regeneration),
                "record_contract_fit_regeneration_requested": bool(record_contract_fit_regeneration),
                "confirmation_valid": bool(confirmation_valid),
                "contract_fit_regeneration_recorded": bool(
                    record_contract_fit_regeneration and confirmation_valid
                ),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "percentage_risk_contract_fit_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                },
                "operator_intervention_model": build_operator_intervention_model(resolved),
                "risk_contract_interpretation": risk_interpretation,
                "percentage_contract_model": percentage_model,
                "contract_fit_sizing_plan": sizing_plan,
                "step_results": step_results,
                "output_validation": validation,
                "go_no_go_packet": packet,
                "contract_fit_matrix": matrix,
                "contract_fit_overall_status": overall,
                "recommended_next_operator_move": _recommended_operator_move(packet),
                "recommended_next_engineering_move": _recommended_engineering_move(packet, validation),
                "do_not_run_yet": [
                    "real submit from R262B",
                    "real submit before controls arming",
                    "real submit before final console",
                    "duplicate live submit",
                ],
                "safety": build_contract_fit_safety(
                    risk_contract_config_written=schema_update.get("risk_contract_config_written") is True,
                    readonly_refresh_ran=step_results["readonly_refresh"]["attempted"],
                    signed_regeneration_ran=step_results["signed_regeneration"]["succeeded"],
                ),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if record_contract_fit_regeneration and confirmation_valid:
            payload = append_tiny_live_percentage_contract_fit_record(payload, log_dir=resolved_log_dir)
        return payload
    except Exception as exc:  # pragma: no cover - defensive operator JSON surface
        return _sanitize(
            {
                "status": TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_ERROR,
                "generated_at": generated_at.isoformat(),
                "run_contract_fit_regeneration_requested": bool(run_contract_fit_regeneration),
                "record_contract_fit_regeneration_requested": bool(record_contract_fit_regeneration),
                "confirmation_valid": False,
                "contract_fit_regeneration_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "percentage_risk_contract_fit_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                },
                "error": exc.__class__.__name__,
                "safety": build_contract_fit_safety(
                    risk_contract_config_written=False,
                    readonly_refresh_ran=False,
                    signed_regeneration_ran=False,
                ),
            }
        )


def load_current_tiny_live_risk_contract(
    *,
    risk_contract_config_path: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    return load_tiny_live_risk_contract(
        risk_contract_config_path=risk_contract_config_path,
        official_lane_key=official_lane_key,
    )


def derive_percentage_risk_contract_model(current_contract: Mapping[str, Any]) -> dict[str, Any]:
    contract = current_contract.get("contract") if isinstance(current_contract.get("contract"), Mapping) else current_contract
    mode = str(contract.get("tiny_live_contract_mode") or PROPER_TINY_LIVE_CONTRACT_MODE)
    configured_notional = _number(contract.get("max_position_notional_usdt") or contract.get("max_notional_usdt"))
    leverage_cap = R267_MAX_LEVERAGE if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE else DEFAULT_MAX_LEVERAGE
    leverage = min(_number(contract.get("leverage")) or leverage_cap, leverage_cap)
    if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE:
        max_notional = min(configured_notional or R267_MAX_POSITION_NOTIONAL_USDT, R267_MAX_POSITION_NOTIONAL_USDT)
        margin = _number(contract.get("margin_budget_usdt") or contract.get("tiny_live_margin_usdt"))
        margin = margin if margin is not None else round(max_notional / leverage, 8)
    else:
        max_notional = min(configured_notional or DEFAULT_MAX_POSITION_NOTIONAL_USDT, DEFAULT_MAX_POSITION_NOTIONAL_USDT)
        margin = _number(contract.get("tiny_live_margin_usdt") or contract.get("margin_budget_usdt")) or 44.0
    isolated_wallet = _number(contract.get("isolated_risk_wallet_usdt")) or max(margin * 2, margin)
    max_loss = _number(contract.get("max_loss_usdt")) or 4.44
    return {
        "uses_percentage_model": True,
        "tiny_live_contract_mode": mode,
        "isolated_wallet_reference_pct": 1.0,
        "isolated_risk_wallet_usdt": isolated_wallet,
        "position_margin_pct_of_isolated_wallet": margin / isolated_wallet if isolated_wallet else 0.5,
        "max_notional_multiplier_of_position_margin": leverage,
        "explicit_max_notional_usdt": max_notional,
        "max_loss_pct_of_position_margin": max_loss / margin if margin else None,
        "resolved_values": {},
    }


def resolve_percentage_risk_contract_values(model: Mapping[str, Any]) -> dict[str, Any]:
    isolated = _number(model.get("isolated_risk_wallet_usdt")) or 88.0
    margin_pct = _number(model.get("position_margin_pct_of_isolated_wallet")) or 0.5
    margin = round(isolated * margin_pct, 8)
    leverage = _number(model.get("max_notional_multiplier_of_position_margin")) or 10.0
    explicit_max_notional = _number(model.get("explicit_max_notional_usdt"))
    max_loss_pct = _number(model.get("max_loss_pct_of_position_margin"))
    max_loss = round(margin * max_loss_pct, 8) if max_loss_pct is not None else 4.44
    max_notional_ceiling = (
        R267_MAX_POSITION_NOTIONAL_USDT
        if model.get("tiny_live_contract_mode") == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE
        else DEFAULT_MAX_POSITION_NOTIONAL_USDT
    )
    return {
        "isolated_risk_wallet_usdt": isolated,
        "position_margin_pct_of_wallet": margin_pct,
        "resolved_position_margin_usdt": margin,
        "leverage": leverage,
        "resolved_max_notional_usdt": min(
            explicit_max_notional if explicit_max_notional is not None else round(margin * leverage, 8),
            max_notional_ceiling,
        ),
        "wallet_buffer_usdt": round(isolated - margin, 8),
        "wallet_buffer_pct_of_wallet": round(1 - margin_pct, 8),
        "resolved_max_loss_usdt": max_loss,
        "max_loss_pct_of_position_margin": max_loss_pct,
    }


def validate_percentage_contract_same_or_stricter(
    *,
    current_contract: Mapping[str, Any],
    resolved_values: Mapping[str, Any],
    risk_interpretation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blocked: list[str] = []
    mode = str(current_contract.get("tiny_live_contract_mode") or PROPER_TINY_LIVE_CONTRACT_MODE)
    current_notional = _number(current_contract.get("max_notional_usdt") or current_contract.get("max_position_notional_usdt")) or (
        R267_MAX_POSITION_NOTIONAL_USDT
        if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE
        else DEFAULT_MAX_POSITION_NOTIONAL_USDT
    )
    current_loss = _number(current_contract.get("max_loss_usdt")) or 4.44
    current_leverage = _number(current_contract.get("leverage")) or (
        R267_MAX_LEVERAGE if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE else DEFAULT_MAX_LEVERAGE
    )
    derived_margin = round(current_notional / current_leverage, 8) if current_leverage else 44.0
    current_margin = (
        _number(
            current_contract.get("tiny_live_margin_usdt")
            or current_contract.get("margin_budget_usdt")
            or current_contract.get("max_margin_usdt")
        )
        or derived_margin
    )
    margin_cap = derived_margin if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE else min(current_margin, 44.0)
    notional_cap = (
        min(current_notional, R267_MAX_POSITION_NOTIONAL_USDT)
        if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE
        else min(current_notional, DEFAULT_MAX_POSITION_NOTIONAL_USDT)
    )
    leverage_cap = (
        min(current_leverage, R267_MAX_LEVERAGE)
        if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE
        else min(current_leverage, DEFAULT_MAX_LEVERAGE)
    )
    if (_number(resolved_values.get("resolved_position_margin_usdt")) or 0) > margin_cap + 0.000001:
        blocked.append("position_margin_above_current_or_44")
    if (_number(resolved_values.get("resolved_max_notional_usdt")) or 0) > notional_cap + 0.000001:
        blocked.append(
            "max_notional_above_current_or_80"
            if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE
            else "max_notional_above_current_or_44"
        )
    if (_number(resolved_values.get("resolved_max_loss_usdt")) or 0) > min(current_loss, 4.44) + 0.000001:
        blocked.append("max_loss_above_current_or_4_44")
    if (_number(resolved_values.get("leverage")) or 0) > leverage_cap + 0.000001:
        blocked.append(
            "leverage_above_current_or_10"
            if mode == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE
            else "leverage_above_current_or_3"
        )
    if risk_interpretation and risk_interpretation.get("valid") is not True:
        blocked.extend(str(item) for item in risk_interpretation.get("blocked_by") or [])
    return {
        "valid": not blocked,
        "no_risk_limit_increase": not blocked,
        "blocked_by": _dedupe(blocked),
    }


def build_contract_fit_sizing_plan(
    *,
    fresh_mark_price: Any,
    resolved_values: Mapping[str, Any],
    step_size: Any,
    min_notional: Any,
) -> dict[str, Any]:
    max_notional = _number(resolved_values.get("resolved_max_notional_usdt")) or 440.0
    max_loss = _number(resolved_values.get("resolved_max_loss_usdt")) or 4.44
    quantity_result = compute_contract_fit_quantity(
        fresh_mark_price=fresh_mark_price,
        max_notional_usdt=max_notional,
        step_size=step_size,
        min_notional=min_notional,
    )
    qty = _number(quantity_result.get("candidate_qty"))
    mark = _number(fresh_mark_price)
    notional = round(mark * qty, 4) if mark is not None and qty is not None else None
    margin = round(notional / (_number(resolved_values.get("leverage")) or 10.0), 4) if notional is not None else None
    estimated_loss = max_loss if qty else None
    blocked = list(quantity_result.get("blocked_by") or [])
    return {
        "fresh_mark_price": mark,
        "max_notional_usdt": max_notional,
        "candidate_qty": qty,
        "candidate_notional_usdt": notional,
        "candidate_margin_usdt": margin,
        "candidate_estimated_loss_usdt": estimated_loss,
        "fits_max_notional": bool(notional is None or notional <= max_notional),
        "fits_max_loss": bool(estimated_loss is None or estimated_loss <= max_loss + 0.001),
        "fits_binance_step_size": quantity_result.get("fits_binance_step_size") is not False,
        "fits_binance_min_notional": quantity_result.get("fits_binance_min_notional") is not False,
        "blocked_by": _dedupe(blocked),
    }


def compute_contract_fit_quantity(
    *,
    fresh_mark_price: Any,
    max_notional_usdt: Any,
    step_size: Any,
    min_notional: Any,
) -> dict[str, Any]:
    if _number(fresh_mark_price) is None:
        return {
            "candidate_qty": None,
            "fits_binance_step_size": False,
            "fits_binance_min_notional": False,
            "blocked_by": [],
        }
    result = compute_fresh_contract_fit_quantity(
        reference_price=fresh_mark_price,
        max_notional_usdt=max_notional_usdt,
        step_size=step_size,
        min_notional=min_notional,
        default_quantity=0.007,
    )
    return {
        "candidate_qty": result.get("quantity"),
        "fits_binance_step_size": result.get("fits_binance_step_size") is True,
        "fits_binance_min_notional": result.get("fits_binance_min_notional") is True,
        "blocked_by": list(result.get("blocked_by") or []),
    }


def validate_quantity_fits_contract(
    *,
    quantity: Any,
    mark_price: Any,
    resolved_values: Mapping[str, Any],
    step_size: Any = 0.001,
    min_notional: Any = 5,
) -> dict[str, Any]:
    qty = _number(quantity)
    mark = _number(mark_price)
    max_notional = _number(resolved_values.get("resolved_max_notional_usdt")) or 440.0
    notional = round(qty * mark, 4) if qty is not None and mark is not None else None
    blocked: list[str] = []
    if notional is None:
        blocked.append("notional_unavailable")
    elif notional > max_notional:
        blocked.append("notional_exceeds_max_notional")
    if qty is None or qty <= 0:
        blocked.append("quantity_invalid")
    step = _number(step_size) or 0.001
    if qty is not None and abs((qty / step) - round(qty / step)) > 1e-9:
        blocked.append("quantity_step_invalid")
    if notional is not None and notional < (_number(min_notional) or 5.0):
        blocked.append("notional_below_min_notional")
    return {
        "valid": not blocked,
        "notional_usdt": notional,
        "blocked_by": _dedupe(blocked),
    }


def apply_percentage_risk_contract_schema_update(
    *,
    risk_contract_config_path: str | Path,
    percentage_contract_model: Mapping[str, Any],
    resolved_values: Mapping[str, Any],
    safety_validation: Mapping[str, Any],
    confirmation_valid: bool,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    result = {"attempted": True, "succeeded": False, "risk_contract_config_written": False, "blocked_by": []}
    if not confirmation_valid:
        result["blocked_by"] = ["bad_confirmation"]
        return result
    if safety_validation.get("valid") is not True:
        result["blocked_by"] = list(safety_validation.get("blocked_by") or ["unsafe_risk_change"])
        return result
    path = Path(risk_contract_config_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    updated = deepcopy(raw)
    contracts = updated.get("risk_contracts") if isinstance(updated.get("risk_contracts"), list) else []
    for contract in contracts:
        if isinstance(contract, dict) and _contract_lane_key(contract) == official_lane_key:
            contract["contract_version"] = "tiny_live_percentage_risk_contract_v2"
            contract["uses_percentage_model"] = True
            contract["tiny_live_contract_mode"] = str(
                percentage_contract_model.get("tiny_live_contract_mode") or PROPER_TINY_LIVE_CONTRACT_MODE
            )
            contract["isolated_risk_wallet_usdt"] = resolved_values["isolated_risk_wallet_usdt"]
            contract["position_margin_pct_of_isolated_wallet"] = resolved_values[
                "position_margin_pct_of_wallet"
            ]
            contract["max_notional_multiplier_of_position_margin"] = resolved_values["leverage"]
            contract["max_loss_pct_of_position_margin"] = resolved_values[
                "max_loss_pct_of_position_margin"
            ]
            contract["resolved_percentage_contract_values"] = dict(resolved_values)
            contract["tiny_live_margin_usdt"] = resolved_values["resolved_position_margin_usdt"]
            contract["margin_budget_usdt"] = resolved_values["resolved_position_margin_usdt"]
            contract["max_margin_usdt"] = resolved_values["resolved_position_margin_usdt"]
            contract["leverage"] = resolved_values["leverage"]
            contract["max_notional_usdt"] = resolved_values["resolved_max_notional_usdt"]
            contract["max_position_notional_usdt"] = resolved_values["resolved_max_notional_usdt"]
            contract["max_loss_usdt"] = resolved_values["resolved_max_loss_usdt"]
            contract["updated_by_phase"] = (
                "R267_BTCUSDT_10X_80_NOTIONAL_TINY_LIVE_CONTRACT_APPLY_GATE"
                if contract["tiny_live_contract_mode"] == EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE
                else CREATED_BY_PHASE
            )
            contract["updated_at"] = (now or datetime.now(UTC)).isoformat()
            path.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            result.update({"succeeded": True, "risk_contract_config_written": True})
            return result
    result["blocked_by"] = ["official_contract_missing"]
    return result


def run_contract_fit_readonly_refresh(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    payload = build_tiny_live_final_readonly_mark_price_refresh_gate(
        log_dir=log_dir,
        fetch_final_readonly_market=True,
        confirm_tiny_live_final_readonly_refresh=CONFIRM_TINY_LIVE_FINAL_READONLY_REFRESH_PHRASE,
        official_lane_key=official_lane_key,
    )
    context = payload.get("fresh_market_context_summary") if isinstance(payload.get("fresh_market_context_summary"), Mapping) else {}
    return {
        "attempted": True,
        "succeeded": payload.get("final_readonly_market_fetched") is True,
        "fresh_mark_price": context.get("mark_price"),
        "step_size": context.get("step_size"),
        "min_notional": context.get("min_notional"),
        "blocked_by": list((payload.get("final_readonly_refresh_gate_matrix") or {}).get("blocked_by") or []),
    }


def run_contract_fit_signed_regeneration(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    payload = build_tiny_live_fresh_context_signed_request_regeneration_gate(
        log_dir=log_dir,
        regenerate_fresh_context_signed_request=True,
        confirm_tiny_live_fresh_context_regeneration=CONFIRM_TINY_LIVE_FRESH_CONTEXT_REGENERATION_PHRASE,
        official_lane_key=official_lane_key,
    )
    summary = payload.get("fresh_signed_request_artifact_summary") if isinstance(payload.get("fresh_signed_request_artifact_summary"), Mapping) else {}
    return {
        "attempted": True,
        "succeeded": payload.get("fresh_context_regeneration_written") is True,
        "signed_requests_count": summary.get("signed_requests_count"),
        "blocked_by": list((payload.get("fresh_regeneration_gate_matrix") or {}).get("blocked_by") or []),
    }


def run_contract_fit_submit_preview(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    payload = build_tiny_live_submit_gate_preview(
        log_dir=log_dir,
        record_submit_gate_preview=True,
        confirm_tiny_live_submit_gate_preview=CONFIRM_TINY_LIVE_SUBMIT_GATE_PREVIEW_PHRASE,
        official_lane_key=official_lane_key,
    )
    return {
        "attempted": True,
        "succeeded": payload.get("submit_gate_preview_recorded") is True,
        "blocked_by": list((payload.get("submit_gate_preview_matrix") or {}).get("blocked_by") or []),
    }


def run_contract_fit_dry_preview(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    payload = build_tiny_live_actual_submit_gate(
        log_dir=log_dir,
        dry_run_actual_submit_gate=True,
        record_actual_submit_gate_preview=True,
        confirm_tiny_live_actual_submit_gate_preview=DRY_PREVIEW_CONFIRMATION_PHRASE,
        official_lane_key=official_lane_key,
    )
    matrix = payload.get("actual_submit_gate_matrix") if isinstance(payload.get("actual_submit_gate_matrix"), Mapping) else {}
    risk = payload.get("risk_contract_submit_summary") if isinstance(payload.get("risk_contract_submit_summary"), Mapping) else {}
    blocked_by = list(matrix.get("blocked_by") or [])
    risk_valid = risk.get("within_tiny_live_contract") is True or matrix.get("risk_contract_valid") is True
    only_expected_controls_blockers = set(blocked_by).issubset(
        {"official_lane_not_tiny_live", "live_execution_not_enabled"}
    )
    return {
        "attempted": True,
        "succeeded": payload.get("actual_submit_gate_preview_recorded") is True
        or bool(risk_valid and only_expected_controls_blockers),
        "risk_contract_valid": risk_valid,
        "blocked_by": blocked_by,
    }


def run_contract_fit_controls_review(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    payload = build_tiny_live_controls_review(
        log_dir=log_dir,
        record_controls_review=True,
        confirm_tiny_live_controls_review=REVIEW_CONFIRMATION_PHRASE,
        arm_tiny_live_controls=False,
        official_lane_key=official_lane_key,
    )
    packet = payload.get("controls_review_packet") if isinstance(payload.get("controls_review_packet"), Mapping) else {}
    return {
        "attempted": True,
        "succeeded": payload.get("controls_review_recorded") is True,
        "operator_should_arm_controls": packet.get("operator_should_arm_controls") is True,
        "blocked_by": list((payload.get("controls_arming_matrix") or {}).get("blocked_by") or []),
    }


def build_contract_fit_output_validation(
    *,
    sizing_plan: Mapping[str, Any],
    step_results: Mapping[str, Any],
    same_or_stricter: Mapping[str, Any],
    risk_interpretation: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    dry = step_results.get("dry_preview") if isinstance(step_results.get("dry_preview"), Mapping) else {}
    signed = step_results.get("signed_regeneration") if isinstance(step_results.get("signed_regeneration"), Mapping) else {}
    if same_or_stricter.get("valid") is not True:
        errors.append("unsafe_risk_change")
    if risk_interpretation.get("valid") is not True:
        errors.extend(str(item) for item in risk_interpretation.get("blocked_by") or [])
    if sizing_plan.get("blocked_by"):
        errors.extend(str(item) for item in sizing_plan.get("blocked_by") or [])
    notional_ok = sizing_plan.get("fits_max_notional") is True
    loss_ok = sizing_plan.get("fits_max_loss") is True
    return {
        "valid": not errors and (not dry.get("attempted") or dry.get("risk_contract_valid") is True),
        "risk_contract_valid_after": dry.get("risk_contract_valid") is True,
        "fresh_signed_request_available": signed.get("signed_requests_count") == 3,
        "signed_request_fresh_enough_for_dry_preview": dry.get("succeeded") is True,
        "notional_within_contract": notional_ok,
        "loss_within_contract": loss_ok,
        "risk_contract_interpretation_valid": risk_interpretation.get("valid") is True,
        "risk_contract_interpretation": dict(risk_interpretation),
        "no_risk_limit_increase": same_or_stricter.get("no_risk_limit_increase") is True,
        "errors": _dedupe(errors),
        "warnings": [],
    }


def build_contract_fit_go_no_go_packet(
    *, output_validation: Mapping[str, Any], step_results: Mapping[str, Any]
) -> dict[str, Any]:
    controls = step_results.get("controls_review") if isinstance(step_results.get("controls_review"), Mapping) else {}
    regenerated_valid = bool(
        output_validation.get("valid")
        and output_validation.get("risk_contract_valid_after")
        and output_validation.get("fresh_signed_request_available")
        and output_validation.get("signed_request_fresh_enough_for_dry_preview")
    )
    attempted = any(isinstance(result, Mapping) and result.get("attempted") for result in step_results.values())
    if regenerated_valid and controls.get("operator_should_arm_controls"):
        next_step = "ARM_CONTROLS"
    elif regenerated_valid:
        next_step = "R263_FINAL_CONSOLE"
    elif output_validation.get("errors"):
        next_step = "FIX_BLOCKER"
    elif not attempted:
        next_step = "WAIT"
    else:
        next_step = "RERUN_CONTRACT_FIT"
    return {
        "go_for_manual_submit_now": False,
        "go_for_controls_arming": bool(regenerated_valid and controls.get("operator_should_arm_controls")),
        "go_for_r263_final_console": bool(regenerated_valid),
        "next_required_step": next_step,
        "operator_should_submit_now": False,
    }


def append_tiny_live_percentage_contract_fit_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_percentage_contract_fit_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "contract_fit_record_id": record.get("contract_fit_record_id")
            or f"r262b_percentage_contract_fit_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_percentage_contract_fit_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_percentage_contract_fit_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def classify_tiny_live_percentage_contract_fit_status(
    *,
    run_requested: bool,
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
    output_validation: Mapping[str, Any],
    step_results: Mapping[str, Any],
) -> str:
    if run_requested and not confirmation_valid:
        return TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_REJECTED_BAD_CONFIRMATION
    if output_validation.get("no_risk_limit_increase") is not True:
        return TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED_UNSAFE_RISK_CHANGE
    if output_validation.get("notional_within_contract") is not True or output_validation.get("loss_within_contract") is not True:
        return TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED_BY_SIZING
    if recorded and output_validation.get("risk_contract_valid_after") is True:
        return TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_RECORDED_RISK_VALID
    if recorded:
        return TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_RECORDED_CONTROLS_REVIEW_REQUIRED
    if not record_requested:
        return TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_READY_FOR_CONFIRMATION
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def build_operator_intervention_model(resolved: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "isolated_risk_wallet_usdt": resolved.get("isolated_risk_wallet_usdt"),
        "position_margin_pct_of_wallet": resolved.get("position_margin_pct_of_wallet"),
        "resolved_position_margin_usdt": resolved.get("resolved_position_margin_usdt"),
        "leverage": resolved.get("leverage"),
        "resolved_max_notional_usdt": resolved.get("resolved_max_notional_usdt"),
        "wallet_buffer_usdt": resolved.get("wallet_buffer_usdt"),
        "wallet_buffer_pct_of_wallet": resolved.get("wallet_buffer_pct_of_wallet"),
        "full_wallet_is_not_position_margin": True,
    }


def build_contract_fit_matrix(
    *,
    percentage_model: Mapping[str, Any],
    sizing_plan: Mapping[str, Any],
    output_validation: Mapping[str, Any],
    step_results: Mapping[str, Any],
) -> dict[str, Any]:
    blocked = list(output_validation.get("errors") or [])
    for result in step_results.values():
        if isinstance(result, Mapping):
            blocked.extend(str(item) for item in result.get("blocked_by") or [])
    return {
        "percentage_model_ready": percentage_model.get("uses_percentage_model") is True,
        "sizing_fit_ready": not sizing_plan.get("blocked_by") and sizing_plan.get("fits_max_notional") is True,
        "risk_contract_valid": output_validation.get("risk_contract_valid_after") is True,
        "fresh_cycle_valid": step_results.get("dry_preview", {}).get("succeeded") is True,
        "controls_review_ready": step_results.get("controls_review", {}).get("succeeded") is True,
        "submit_allowed": False,
        "order_placed": False,
        "blocked_by": _dedupe(blocked),
    }


def build_contract_fit_safety(
    *,
    risk_contract_config_written: bool,
    readonly_refresh_ran: bool,
    signed_regeneration_ran: bool,
) -> dict[str, Any]:
    return {
        **SAFETY_FALSE,
        "env_written": False,
        "env_mutated": False,
        "external_env_file_written": False,
        "risk_contract_config_written": bool(risk_contract_config_written),
        "lane_controls_written": False,
        "live_config_written": False,
        "percentage_risk_contract_fit_only": True,
        "hmac_signature_created": bool(signed_regeneration_ran),
        "signed_request_written": bool(signed_regeneration_ran),
        "signed_order_request_created": bool(signed_regeneration_ran),
        "signed_trading_request_created": bool(signed_regeneration_ran),
        "submit_allowed": False,
        "submit_attempted": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "binance_order_endpoint_called": False,
        "binance_test_order_endpoint_called": False,
        "binance_account_endpoint_called": False,
        "binance_exchange_info_endpoint_called": bool(readonly_refresh_ran),
        "binance_mark_price_endpoint_called": bool(readonly_refresh_ran),
        "private_binance_endpoint_called": False,
        "signed_binance_endpoint_called": False,
        "network_allowed": bool(readonly_refresh_ran),
        "transfer_endpoint_called": False,
        "withdraw_endpoint_called": False,
        "kill_switch_disabled": False,
        "live_controls_armed_by_phase": False,
        "secrets_shown": False,
        "secrets_persisted": False,
        "secret_values_in_output": False,
        "global_live_flags_changed": False,
        "paper_live_separation_intact": True,
        "official_tiny_live_lane_changed": False,
    }


def tiny_live_percentage_contract_fit_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_percentage_risk_contract_fit_regeneration_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _empty_step_results() -> dict[str, dict[str, Any]]:
    return {
        "percentage_schema_update": {
            "attempted": False,
            "succeeded": False,
            "risk_contract_config_written": False,
            "blocked_by": [],
        },
        "readonly_refresh": {"attempted": False, "succeeded": False, "fresh_mark_price": None, "blocked_by": []},
        "signed_regeneration": {
            "attempted": False,
            "succeeded": False,
            "signed_requests_count": None,
            "blocked_by": [],
        },
        "submit_preview": {"attempted": False, "succeeded": False, "blocked_by": []},
        "dry_preview": {"attempted": False, "succeeded": False, "risk_contract_valid": False, "blocked_by": []},
        "controls_review": {
            "attempted": False,
            "succeeded": False,
            "operator_should_arm_controls": False,
            "blocked_by": [],
        },
    }


def _top_level_status(
    *,
    run_requested: bool,
    record_requested: bool,
    confirmation_valid: bool,
    output_validation: Mapping[str, Any],
    recorded: bool,
) -> str:
    if run_requested and not confirmation_valid:
        return TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_REJECTED
    if output_validation.get("errors"):
        return TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_BLOCKED
    if recorded:
        return TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_RECORDED
    return TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_READY


def _recommended_operator_move(packet: Mapping[str, Any]) -> str:
    step = packet.get("next_required_step")
    if step == "ARM_CONTROLS":
        return "Review R262B output, then arm controls in R261 if the operator accepts the regenerated contract-fit triplet."
    if step == "R263_FINAL_CONSOLE":
        return "Open the R263 final submit console for review only; do not submit from R262B."
    if step == "FIX_BLOCKER":
        return "Fix the listed blocker before any controls arming or final console review."
    return "Wait or rerun R262B with exact confirmation when ready."


def _recommended_engineering_move(packet: Mapping[str, Any], validation: Mapping[str, Any]) -> str:
    if packet.get("go_for_r263_final_console"):
        return "Build R263 final console against the latest regenerated quantity and R262B ledger."
    if validation.get("errors"):
        return "Resolve R262B validation errors without loosening risk limits."
    return "Keep R262B in preview until the operator confirms regeneration."


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key).split("|")
    return (parts + ["", "", "", ""])[:4]  # type: ignore[return-value]


def _contract_lane_key(contract: Mapping[str, Any]) -> str:
    return str(
        contract.get("official_lane_key")
        or "|".join(
            str(contract.get(key) or "")
            for key in ("symbol", "timeframe", "direction", "entry_mode")
        )
    )


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(items: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
