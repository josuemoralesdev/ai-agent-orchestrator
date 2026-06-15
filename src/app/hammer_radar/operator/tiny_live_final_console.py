"""R263 tiny-live final console and lane-intelligence arming surface.

This module is a local final-console cockpit only. It does not submit, sign,
call Binance, regenerate signed requests, mutate risk contracts, or change
strategy/paper/performance ledgers. The only config write it can perform is
the official 8m short lane row in lane_controls.json after the exact R263
experimental-lane acceptance phrase.
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
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, normalize_lane_key
from src.app.hammer_radar.operator.readiness import build_readiness_payload
from src.app.hammer_radar.operator.strategy_promotion_watcher import build_strategy_promotion_status
from src.app.hammer_radar.operator.tiny_live_actual_submit_gate import (
    LANE_CONTROLS_PATH,
    RISK_CONTRACT_CONFIG_PATH,
)
from src.app.hammer_radar.operator.tiny_live_controls_arming import (
    load_tiny_live_lane_controls as _load_r261_lane_controls,
    load_tiny_live_risk_contract,
    summarize_tiny_live_controls_state,
    summarize_tiny_live_risk_contract_state,
)
from src.app.hammer_radar.operator.tiny_live_percentage_risk_contract_fit_regeneration import (
    load_tiny_live_percentage_contract_fit_records,
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R263_TINY_LIVE_FINAL_CONSOLE_LANE_INTELLIGENCE_CONTROLS_ARMING"
LEDGER_FILENAME = "tiny_live_final_console.ndjson"
EVENT_TYPE_REVIEW = "TINY_LIVE_FINAL_CONSOLE_REVIEW"
EVENT_TYPE_ARMING = "TINY_LIVE_FINAL_CONSOLE_CONTROLS_ARMING"

FINAL_CONSOLE_REVIEW_CONFIRMATION_PHRASE = (
    "I CONFIRM TINY LIVE FINAL CONSOLE REVIEW RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
)
FINAL_CONSOLE_CONTROLS_ARMING_CONFIRMATION_PHRASE = (
    "I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT EXPERIMENTAL LANE ONLY; "
    "I ACCEPT 8M SHORT IS PAPER-ONLY/PROMOTION-MISMATCHED; NO SUBMIT; NO ORDER; NO BINANCE CALL."
)

TINY_LIVE_FINAL_CONSOLE_READY = "TINY_LIVE_FINAL_CONSOLE_READY"
TINY_LIVE_FINAL_CONSOLE_REVIEW_RECORDED = "TINY_LIVE_FINAL_CONSOLE_REVIEW_RECORDED"
TINY_LIVE_FINAL_CONSOLE_CONTROLS_ARMED = "TINY_LIVE_FINAL_CONSOLE_CONTROLS_ARMED"
TINY_LIVE_FINAL_CONSOLE_ARMING_REJECTED = "TINY_LIVE_FINAL_CONSOLE_ARMING_REJECTED"
TINY_LIVE_FINAL_CONSOLE_BLOCKED = "TINY_LIVE_FINAL_CONSOLE_BLOCKED"
TINY_LIVE_FINAL_CONSOLE_ERROR = "TINY_LIVE_FINAL_CONSOLE_ERROR"

TINY_LIVE_FINAL_CONSOLE_READY_FOR_REVIEW = "TINY_LIVE_FINAL_CONSOLE_READY_FOR_REVIEW"
TINY_LIVE_FINAL_CONSOLE_REVIEW_RECORDED_ARMING_REQUIRED = (
    "TINY_LIVE_FINAL_CONSOLE_REVIEW_RECORDED_ARMING_REQUIRED"
)
TINY_LIVE_FINAL_CONSOLE_ARMED_R264_ACTUAL_SUBMIT_CHECKPOINT_REQUIRED = (
    "TINY_LIVE_FINAL_CONSOLE_ARMED_R264_ACTUAL_SUBMIT_CHECKPOINT_REQUIRED"
)
TINY_LIVE_FINAL_CONSOLE_BLOCKED_BY_MISSING_R262B = "TINY_LIVE_FINAL_CONSOLE_BLOCKED_BY_MISSING_R262B"
TINY_LIVE_FINAL_CONSOLE_BLOCKED_BY_CONTRACT_INVALID = "TINY_LIVE_FINAL_CONSOLE_BLOCKED_BY_CONTRACT_INVALID"
TINY_LIVE_FINAL_CONSOLE_BLOCKED_BY_LANE_INTELLIGENCE = "TINY_LIVE_FINAL_CONSOLE_BLOCKED_BY_LANE_INTELLIGENCE"
TINY_LIVE_FINAL_CONSOLE_ARMING_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_FINAL_CONSOLE_ARMING_REJECTED_BAD_CONFIRMATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

PROMOTED_LANE_KEYS = [
    "BTCUSDT|13m|long|ladder_close_50_618",
    "BTCUSDT|44m|long|ladder_close_50_618",
]

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/tiny_live_percentage_risk_contract_fit_regeneration.py",
    "src/app/hammer_radar/operator/tiny_live_controls_arming.py",
    "src/app/hammer_radar/operator/readiness.py",
    "src/app/hammer_radar/operator/strategy_promotion_watcher.py",
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "logs/hammer_radar_forward/tiny_live_percentage_risk_contract_fit.ndjson",
    "logs/hammer_radar_forward/tiny_live_controls_arming.ndjson",
    "logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_final_console(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    record_final_console_review: bool = False,
    confirm_final_console_review: str | None = None,
    arm_controls_from_final_console: bool = False,
    confirm_final_console_controls_arming: str | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    lane_path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    review_confirmation_valid = confirm_final_console_review == FINAL_CONSOLE_REVIEW_CONFIRMATION_PHRASE
    arming_confirmation_valid = (
        confirm_final_console_controls_arming == FINAL_CONSOLE_CONTROLS_ARMING_CONFIRMATION_PHRASE
    )
    confirmation_valid = bool(
        (record_final_console_review and review_confirmation_valid)
        or (arm_controls_from_final_console and arming_confirmation_valid)
    )
    symbol, timeframe, direction, _entry_mode = _lane_parts(official_lane_key)
    try:
        latest_r262b = load_latest_percentage_contract_fit_record(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_controls = load_latest_controls_arming_record(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        lane_controls = load_tiny_live_lane_controls(
            lane_controls_path=lane_path,
            official_lane_key=official_lane_key,
        )
        risk_contract = load_tiny_live_risk_contract(
            risk_contract_config_path=risk_path,
            official_lane_key=official_lane_key,
        )
        promotion_snapshot = load_strategy_promotion_status_snapshot(log_dir=resolved_log_dir)
        readiness_snapshot = load_readiness_snapshot(log_dir=resolved_log_dir)
        lane_context = load_lane_fisherman_context(
            lane_controls=lane_controls,
            promotion_snapshot=promotion_snapshot,
            readiness_snapshot=readiness_snapshot,
            official_lane_key=official_lane_key,
        )

        contract_fit_panel = summarize_contract_fit_panel(latest_r262b)
        signed_triplet_panel = summarize_signed_triplet_panel(log_dir=resolved_log_dir, latest_r262b=latest_r262b)
        controls_panel = summarize_controls_panel(
            lane_controls=lane_controls,
            risk_contract=risk_contract,
            latest_controls=latest_controls,
        )
        lane_intelligence_panel = summarize_lane_intelligence_panel(
            lane_context=lane_context,
            readiness_snapshot=readiness_snapshot,
            promotion_snapshot=promotion_snapshot,
        )
        experimental_lane_acceptance_recorded = _lane_experimental_acceptance_recorded(lane_controls)
        if experimental_lane_acceptance_recorded:
            lane_intelligence_panel["operator_acceptance_required"] = False
        promotion_readiness_panel = summarize_promotion_readiness_panel(
            promotion_snapshot=promotion_snapshot,
            readiness_snapshot=readiness_snapshot,
        )
        operator_choice_panel = build_operator_choice_panel(
            experimental_lane_acceptance_recorded=experimental_lane_acceptance_recorded,
            selected_choice="ACCEPT_8M_SHORT_EXPERIMENTAL_LANE"
            if experimental_lane_acceptance_recorded
            else None,
        )
        validation = validate_final_console_controls_arming_request(
            arm_controls_from_final_console=arm_controls_from_final_console,
            confirmation_valid=arming_confirmation_valid,
            contract_fit_panel=contract_fit_panel,
            lane_intelligence_panel=lane_intelligence_panel,
            official_lane_key=official_lane_key,
        )
        controls_arming_result = {
            "attempted": bool(arm_controls_from_final_console),
            "succeeded": False,
            "lane_controls_written": False,
            "blocked_by": list(validation.get("blocked_by") or []),
            "before": {},
            "after": {},
        }
        final_console_review_recorded = bool(record_final_console_review and review_confirmation_valid)
        final_console_controls_armed = False
        if arm_controls_from_final_console and arming_confirmation_valid and validation["valid"]:
            controls_arming_result = apply_final_console_controls_arming_request(
                lane_controls_path=lane_path,
                official_lane_key=official_lane_key,
                operator_id=operator_id,
                reason=reason,
                now=generated_at,
            )
            final_console_controls_armed = controls_arming_result["succeeded"]
            if final_console_controls_armed:
                lane_controls = load_tiny_live_lane_controls(
                    lane_controls_path=lane_path,
                    official_lane_key=official_lane_key,
                )
                controls_panel = summarize_controls_panel(
                    lane_controls=lane_controls,
                    risk_contract=risk_contract,
                    latest_controls=latest_controls,
                    armed_by_this_phase=True,
                )
                operator_choice_panel = build_operator_choice_panel(
                    experimental_lane_acceptance_recorded=True,
                    selected_choice="ACCEPT_8M_SHORT_EXPERIMENTAL_LANE",
                )
                lane_intelligence_panel["operator_acceptance_required"] = False

        go_no_go = build_final_console_go_no_go_packet(
            contract_fit_panel=contract_fit_panel,
            signed_triplet_panel=signed_triplet_panel,
            controls_panel=controls_panel,
            lane_intelligence_panel=lane_intelligence_panel,
            experimental_lane_acceptance_recorded=operator_choice_panel[
                "experimental_lane_acceptance_recorded"
            ],
        )
        matrix = _build_final_console_matrix(
            contract_fit_panel=contract_fit_panel,
            signed_triplet_panel=signed_triplet_panel,
            lane_intelligence_panel=lane_intelligence_panel,
            controls_panel=controls_panel,
            experimental_lane_acceptance_recorded=operator_choice_panel[
                "experimental_lane_acceptance_recorded"
            ],
            blocked_by=controls_arming_result["blocked_by"],
        )
        overall = classify_tiny_live_final_console_status(
            r262b_found=contract_fit_panel["r262b_found"],
            risk_contract_valid=contract_fit_panel["risk_contract_valid"],
            record_requested=record_final_console_review,
            review_confirmation_valid=review_confirmation_valid,
            review_recorded=final_console_review_recorded,
            arm_requested=arm_controls_from_final_console,
            arming_confirmation_valid=arming_confirmation_valid,
            controls_armed=final_console_controls_armed or controls_panel["controls_armed"],
            operator_acceptance_required=lane_intelligence_panel["operator_acceptance_required"],
            operator_acceptance_recorded=operator_choice_panel["experimental_lane_acceptance_recorded"],
        )
        status = _top_status(
            record_requested=record_final_console_review,
            arm_requested=arm_controls_from_final_console,
            review_confirmation_valid=review_confirmation_valid,
            arming_confirmation_valid=arming_confirmation_valid,
            review_recorded=final_console_review_recorded,
            controls_armed=final_console_controls_armed,
            blocked_by=controls_arming_result["blocked_by"],
        )
        safety = _safety(
            lane_controls_written=controls_arming_result["lane_controls_written"],
            experimental_lane_acceptance_recorded=operator_choice_panel[
                "experimental_lane_acceptance_recorded"
            ],
        )
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "record_final_console_review_requested": bool(record_final_console_review),
                "arm_controls_from_final_console_requested": bool(arm_controls_from_final_console),
                "confirmation_valid": bool(confirmation_valid),
                "final_console_review_recorded": bool(final_console_review_recorded),
                "final_console_controls_armed": bool(final_console_controls_armed),
                "operator_intent": {
                    "operator_id": str(operator_id or "local_operator"),
                    "reason": str(reason or ""),
                    "source_phase": "R263",
                },
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "final_console_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                },
                "contract_fit_panel": contract_fit_panel,
                "signed_triplet_panel": signed_triplet_panel,
                "controls_panel": controls_panel,
                "lane_intelligence_panel": lane_intelligence_panel,
                "promotion_readiness_panel": promotion_readiness_panel,
                "operator_choice_panel": operator_choice_panel,
                "controls_arming_result": controls_arming_result,
                "final_console_go_no_go_packet": go_no_go,
                "final_console_matrix": matrix,
                "final_console_overall_status": overall,
                "recommended_next_operator_move": _recommended_next_operator_move(go_no_go, overall),
                "recommended_next_engineering_move": _recommended_next_engineering_move(go_no_go, overall),
                "do_not_run_yet": [
                    "real submit from R263",
                    "real submit before R264 checkpoint",
                    "real submit without controls armed",
                    "real submit while lane/fisherman warning is unaccepted",
                    "duplicate live submit",
                ],
                "safety": safety,
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if final_console_review_recorded:
            payload = append_tiny_live_final_console_record(payload, log_dir=resolved_log_dir, event_type=EVENT_TYPE_REVIEW)
        if arm_controls_from_final_console:
            payload = append_tiny_live_final_console_record(payload, log_dir=resolved_log_dir, event_type=EVENT_TYPE_ARMING)
        return payload
    except Exception as exc:  # pragma: no cover - defensive operator JSON surface
        return _sanitize(
            {
                "status": TINY_LIVE_FINAL_CONSOLE_ERROR,
                "generated_at": generated_at.isoformat(),
                "record_final_console_review_requested": bool(record_final_console_review),
                "arm_controls_from_final_console_requested": bool(arm_controls_from_final_console),
                "confirmation_valid": False,
                "final_console_review_recorded": False,
                "final_console_controls_armed": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "final_console_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                },
                "error": exc.__class__.__name__,
                "safety": _safety(lane_controls_written=False, experimental_lane_acceptance_recorded=False),
            }
        )


def load_latest_percentage_contract_fit_record(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_percentage_contract_fit_records(log_dir=log_dir, limit=50):
        if _record_lane(record) == official_lane_key:
            return record
    return {}


def load_latest_controls_arming_record(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in _load_ndjson(Path(get_log_dir(log_dir, use_env=True)) / "tiny_live_controls_arming.ndjson"):
        if _record_lane(record) == official_lane_key:
            return record
    return {}


def load_tiny_live_lane_controls(
    *, lane_controls_path: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_r261_lane_controls(
        lane_controls_path=lane_controls_path,
        official_lane_key=official_lane_key,
    )


def load_strategy_promotion_status_snapshot(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    try:
        snapshot = build_strategy_promotion_status(log_dir=resolved_log_dir)
    except Exception:
        snapshot = {}
    fallback = _latest_file_record(Path(resolved_log_dir) / "strategy_promotion_status.ndjson")
    if fallback and not snapshot.get("promotion_ready"):
        merged = {**fallback, **snapshot}
        merged["promotion_ready"] = fallback.get("promotion_ready") or fallback.get("ready") or []
        return _sanitize(merged)
    return _sanitize(snapshot)


def load_readiness_snapshot(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    try:
        snapshot = build_readiness_payload(log_dir=resolved_log_dir)
    except Exception:
        snapshot = {}
    fallback = _latest_file_record(Path(resolved_log_dir) / "readiness_status.ndjson")
    return _sanitize(snapshot or fallback)


def load_lane_fisherman_context(
    *,
    lane_controls: Mapping[str, Any],
    promotion_snapshot: Mapping[str, Any],
    readiness_snapshot: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    lane = lane_controls.get("official_lane") if isinstance(lane_controls.get("official_lane"), Mapping) else {}
    mode = str(lane.get("mode") or "").lower()
    promoted = _promotion_ready_lanes(promotion_snapshot)
    timeframe = _lane_parts(official_lane_key)[1]
    direction = _lane_parts(official_lane_key)[2]
    if timeframe in {"13m", "44m"}:
        timeframe_status = "allowed_tiny_live"
    elif timeframe in {"4m", "8m", "88m"}:
        timeframe_status = "paper_only"
    elif timeframe in {"22m", "55m", "222m", "444m"}:
        timeframe_status = "blocked"
    else:
        timeframe_status = "unknown"
    promotion_status = "promotion_ready" if official_lane_key in promoted else "not_promotion_ready"
    direction_status = "promoted" if promotion_status == "promotion_ready" else (
        "experimental_short" if direction == "short" else "unknown"
    )
    return {
        "execution_lane": official_lane_key,
        "lane_control_mode": mode or "unknown",
        "execution_lane_timeframe_status": timeframe_status,
        "execution_lane_promotion_status": promotion_status,
        "execution_lane_direction_status": direction_status,
        "promoted_lanes": promoted,
        "readiness_status": readiness_snapshot.get("readiness_status") or "UNKNOWN",
        "fisherman_warning": promotion_status != "promotion_ready" or timeframe_status != "allowed_tiny_live",
        "operator_acceptance_required": promotion_status != "promotion_ready",
    }


def summarize_contract_fit_panel(latest_r262b: Mapping[str, Any]) -> dict[str, Any]:
    model = latest_r262b.get("percentage_contract_model") if isinstance(latest_r262b.get("percentage_contract_model"), Mapping) else {}
    resolved = model.get("resolved_values") if isinstance(model.get("resolved_values"), Mapping) else {}
    intervention = latest_r262b.get("operator_intervention_model") if isinstance(latest_r262b.get("operator_intervention_model"), Mapping) else {}
    sizing = latest_r262b.get("contract_fit_sizing_plan") if isinstance(latest_r262b.get("contract_fit_sizing_plan"), Mapping) else {}
    validation = latest_r262b.get("output_validation") if isinstance(latest_r262b.get("output_validation"), Mapping) else {}
    r262b_found = bool(latest_r262b)
    risk_valid = validation.get("risk_contract_valid_after") is True or latest_r262b.get("contract_fit_matrix", {}).get("risk_contract_valid") is True
    fits = bool(
        r262b_found
        and risk_valid
        and validation.get("valid") is True
        and sizing.get("fits_max_notional") is True
        and sizing.get("fits_max_loss") is True
        and sizing.get("fits_binance_step_size") is True
        and sizing.get("fits_binance_min_notional") is True
    )
    return {
        "r262b_found": r262b_found,
        "risk_contract_valid": bool(risk_valid),
        "percentage_model_ready": model.get("uses_percentage_model") is True,
        "isolated_risk_wallet_usdt": resolved.get("isolated_risk_wallet_usdt") or intervention.get("isolated_risk_wallet_usdt"),
        "position_margin_usdt": resolved.get("resolved_position_margin_usdt") or intervention.get("resolved_position_margin_usdt"),
        "wallet_buffer_usdt": resolved.get("wallet_buffer_usdt") or intervention.get("wallet_buffer_usdt"),
        "leverage": resolved.get("leverage") or intervention.get("leverage"),
        "candidate_qty": sizing.get("candidate_qty"),
        "candidate_notional_usdt": sizing.get("candidate_notional_usdt"),
        "candidate_margin_usdt": sizing.get("candidate_margin_usdt"),
        "candidate_estimated_loss_usdt": sizing.get("candidate_estimated_loss_usdt"),
        "fits_contract": fits,
    }


def summarize_signed_triplet_panel(
    *, log_dir: str | Path | None = None, latest_r262b: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    latest_submit = _latest_file_record(Path(get_log_dir(log_dir, use_env=True)) / "tiny_live_submit_gate_preview.ndjson")
    latest_dry = _latest_file_record(Path(get_log_dir(log_dir, use_env=True)) / "tiny_live_actual_submit_gate.ndjson")
    signed = latest_submit.get("fresh_signed_request_summary") if isinstance(latest_submit.get("fresh_signed_request_summary"), Mapping) else {}
    orders = latest_dry.get("actual_submit_dry_run_preview", {}).get("orders") if isinstance(latest_dry.get("actual_submit_dry_run_preview"), Mapping) else {}
    main = orders.get("main_order") if isinstance(orders, Mapping) and isinstance(orders.get("main_order"), Mapping) else {}
    stop = orders.get("stop_order") if isinstance(orders, Mapping) and isinstance(orders.get("stop_order"), Mapping) else {}
    take = orders.get("take_profit_order") if isinstance(orders, Mapping) and isinstance(orders.get("take_profit_order"), Mapping) else {}
    dry_risk = latest_dry.get("risk_contract_submit_summary") if isinstance(latest_dry.get("risk_contract_submit_summary"), Mapping) else {}
    step_results = (latest_r262b or {}).get("step_results") if isinstance((latest_r262b or {}).get("step_results"), Mapping) else {}
    signed_count = signed.get("signed_requests_count") or step_results.get("signed_regeneration", {}).get("signed_requests_count")
    return {
        "signed_triplet_available": signed_count == 3 or latest_submit.get("submit_gate_preview_recorded") is True,
        "signed_requests_count": signed_count,
        "main_order_side": main.get("side"),
        "stop_reduce_only": stop.get("reduceOnly") is True,
        "take_profit_reduce_only": take.get("reduceOnly") is True,
        "submit_preview_recorded": latest_submit.get("submit_gate_preview_recorded") is True,
        "dry_preview_recorded": latest_dry.get("actual_submit_gate_preview_recorded") is True,
        "dry_preview_risk_contract_valid": dry_risk.get("within_tiny_live_contract") is True,
    }


def summarize_controls_panel(
    *,
    lane_controls: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    latest_controls: Mapping[str, Any] | None = None,
    armed_by_this_phase: bool = False,
) -> dict[str, Any]:
    state = summarize_tiny_live_controls_state(
        lane_controls=lane_controls,
        risk_contract=risk_contract,
        armed_by_this_phase=armed_by_this_phase,
    )
    risk_state = summarize_tiny_live_risk_contract_state(risk_contract=risk_contract)
    controls_armed = state.get("official_lane_allowed") is True
    return {
        "official_lane_allowed": controls_armed,
        "live_execution_enabled": state.get("live_execution_enabled") is True,
        "kill_switch_allows_tiny_live": state.get("kill_switch_allows_tiny_live") is True,
        "controls_armed": controls_armed,
        "controls_arming_required": not controls_armed,
        "latest_controls_record_found": bool(latest_controls),
        "risk_contract_valid": risk_state.get("risk_contract_valid") is True or _risk_contract_limits_valid(risk_contract),
    }


def summarize_lane_intelligence_panel(
    *,
    lane_context: Mapping[str, Any],
    readiness_snapshot: Mapping[str, Any],
    promotion_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    state = readiness_snapshot.get("current_state") if isinstance(readiness_snapshot.get("current_state"), Mapping) else {}
    warnings: list[str] = []
    if lane_context.get("execution_lane_timeframe_status") == "paper_only":
        warnings.append("execution lane timeframe is paper-only by promotion config")
    if lane_context.get("execution_lane_promotion_status") != "promotion_ready":
        warnings.append("execution lane is not promotion-ready")
    if lane_context.get("execution_lane_direction_status") == "experimental_short":
        warnings.append("8m short is a manual experimental lane, not fisherman-promoted")
    if readiness_snapshot.get("readiness_status") == "NOT_READY":
        warnings.append("readiness is NOT_READY")
    return {
        "execution_lane": lane_context.get("execution_lane"),
        "execution_lane_timeframe_status": lane_context.get("execution_lane_timeframe_status") or "unknown",
        "execution_lane_promotion_status": lane_context.get("execution_lane_promotion_status") or "unknown",
        "execution_lane_direction_status": lane_context.get("execution_lane_direction_status") or "unknown",
        "promoted_lanes": _promotion_ready_lanes(promotion_snapshot),
        "readiness_status": readiness_snapshot.get("readiness_status") or "UNKNOWN",
        "fresh_eligible_count": state.get("fresh_eligible_count"),
        "expired_eligible_count": state.get("expired_eligible_count"),
        "paper_only_count": state.get("paper_only_count"),
        "fisherman_warning": bool(lane_context.get("fisherman_warning")),
        "operator_acceptance_required": bool(lane_context.get("operator_acceptance_required")),
        "warnings": _dedupe(warnings),
    }


def summarize_promotion_readiness_panel(
    *, promotion_snapshot: Mapping[str, Any], readiness_snapshot: Mapping[str, Any]
) -> dict[str, Any]:
    state = readiness_snapshot.get("current_state") if isinstance(readiness_snapshot.get("current_state"), Mapping) else {}
    return {
        "strategy_performance_endpoint_available": True,
        "promotion_ready": list(promotion_snapshot.get("promotion_ready") or []),
        "readiness_blockers": list(readiness_snapshot.get("blockers") or []),
        "latest_candidate_age_minutes": state.get("latest_candidate_age_minutes"),
        "live_execution_enabled": readiness_snapshot.get("live_execution_enabled") is True,
        "global_kill_switch": True,
    }


def build_operator_choice_panel(
    *, experimental_lane_acceptance_recorded: bool, selected_choice: str | None
) -> dict[str, Any]:
    return {
        "choices": [
            "ACCEPT_8M_SHORT_EXPERIMENTAL_LANE",
            "WAIT_FOR_FRESH_ELIGIBLE_TINY_LIVE",
            "SWITCH_TO_PROMOTED_13M_LONG_LATER",
            "SWITCH_TO_PROMOTED_44M_LONG_LATER",
        ],
        "selected_choice": selected_choice,
        "experimental_lane_acceptance_recorded": bool(experimental_lane_acceptance_recorded),
        "submit_still_forbidden": True,
    }


def validate_final_console_controls_arming_request(
    *,
    arm_controls_from_final_console: bool,
    confirmation_valid: bool,
    contract_fit_panel: Mapping[str, Any],
    lane_intelligence_panel: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    blocked_by: list[str] = []
    if not arm_controls_from_final_console:
        return {"valid": False, "blocked_by": []}
    if not confirmation_valid:
        blocked_by.append("bad_confirmation")
    if official_lane_key != OFFICIAL_LANE_KEY:
        blocked_by.append("official_lane_change_forbidden")
    if not contract_fit_panel.get("r262b_found"):
        blocked_by.append("missing_r262b")
    if not contract_fit_panel.get("risk_contract_valid") or not contract_fit_panel.get("fits_contract"):
        blocked_by.append("contract_fit_invalid")
    if lane_intelligence_panel.get("operator_acceptance_required") and not confirmation_valid:
        blocked_by.append("experimental_lane_acceptance_required")
    return {"valid": not blocked_by, "blocked_by": _dedupe(blocked_by)}


def apply_final_console_controls_arming_request(
    *,
    lane_controls_path: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    operator_id: str = "local_operator",
    reason: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    updated = deepcopy(raw)
    lanes = updated.get("lanes")
    if not isinstance(lanes, list):
        return _arming_result(False, ["lane_controls_schema_missing_lanes"])
    for lane in lanes:
        if isinstance(lane, dict) and _lane_key_from_row(lane) == official_lane_key:
            before = deepcopy(lane)
            lane["mode"] = "tiny_live"
            lane["tiny_live_armed_by_phase"] = "R263"
            lane["tiny_live_armed_at_utc"] = generated_at.isoformat()
            lane["tiny_live_armed_by_operator_id"] = str(operator_id or "local_operator")
            lane["tiny_live_arming_reason"] = str(reason or "")
            lane["experimental_lane_acceptance_recorded"] = True
            lane["experimental_lane_acceptance_phase"] = "R263"
            lane["experimental_lane_acceptance_note"] = (
                "8m short accepted as paper-only/promotion-mismatched manual experimental lane; no submit from R263."
            )
            after = deepcopy(lane)
            path.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return {
                "attempted": True,
                "succeeded": True,
                "lane_controls_written": True,
                "blocked_by": [],
                "before": before,
                "after": after,
            }
    return _arming_result(False, ["official_lane_missing"])


def build_final_console_go_no_go_packet(
    *,
    contract_fit_panel: Mapping[str, Any],
    signed_triplet_panel: Mapping[str, Any],
    controls_panel: Mapping[str, Any],
    lane_intelligence_panel: Mapping[str, Any],
    experimental_lane_acceptance_recorded: bool,
) -> dict[str, Any]:
    r262b_valid = contract_fit_panel.get("r262b_found") and contract_fit_panel.get("risk_contract_valid") and contract_fit_panel.get("fits_contract")
    if not r262b_valid:
        next_step = "RERUN_R262B"
    elif lane_intelligence_panel.get("operator_acceptance_required") and not experimental_lane_acceptance_recorded:
        next_step = "ARM_CONTROLS"
    elif not controls_panel.get("controls_armed"):
        next_step = "ARM_CONTROLS"
    elif controls_panel.get("controls_armed"):
        next_step = "R264_ACTUAL_SUBMIT_CHECKPOINT"
    elif lane_intelligence_panel.get("readiness_status") != "READY":
        next_step = "WAIT_FOR_FRESH_CANDIDATE"
    else:
        next_step = "FIX_BLOCKER"
    return {
        "go_for_actual_submit_now": False,
        "go_for_r264_actual_submit_checkpoint": bool(
            r262b_valid and signed_triplet_panel.get("signed_triplet_available") and controls_panel.get("controls_armed")
        ),
        "go_for_controls_arming": bool(
            r262b_valid and not controls_panel.get("controls_armed")
        ),
        "operator_should_submit_now": False,
        "next_required_step": next_step,
    }


def append_tiny_live_final_console_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    event_type: str,
) -> dict[str, Any]:
    path = tiny_live_final_console_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    key = "final_console_arming_record_id" if event_type == EVENT_TYPE_ARMING else "final_console_review_record_id"
    prefix = "r263_final_console_arming" if event_type == EVENT_TYPE_ARMING else "r263_final_console_review"
    payload = _sanitize(
        {
            "event_type": event_type,
            key: record.get(key) or f"{prefix}_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "created_by_phase": CREATED_BY_PHASE,
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_final_console_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_final_console_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def classify_tiny_live_final_console_status(
    *,
    r262b_found: bool,
    risk_contract_valid: bool,
    record_requested: bool,
    review_confirmation_valid: bool,
    review_recorded: bool,
    arm_requested: bool,
    arming_confirmation_valid: bool,
    controls_armed: bool,
    operator_acceptance_required: bool,
    operator_acceptance_recorded: bool,
) -> str:
    if arm_requested and not arming_confirmation_valid:
        return TINY_LIVE_FINAL_CONSOLE_ARMING_REJECTED_BAD_CONFIRMATION
    if not r262b_found:
        return TINY_LIVE_FINAL_CONSOLE_BLOCKED_BY_MISSING_R262B
    if not risk_contract_valid:
        return TINY_LIVE_FINAL_CONSOLE_BLOCKED_BY_CONTRACT_INVALID
    if controls_armed and (not operator_acceptance_required or operator_acceptance_recorded):
        return TINY_LIVE_FINAL_CONSOLE_ARMED_R264_ACTUAL_SUBMIT_CHECKPOINT_REQUIRED
    if operator_acceptance_required and not operator_acceptance_recorded and not (record_requested or arm_requested):
        return TINY_LIVE_FINAL_CONSOLE_BLOCKED_BY_LANE_INTELLIGENCE
    if review_recorded or (record_requested and review_confirmation_valid):
        return TINY_LIVE_FINAL_CONSOLE_REVIEW_RECORDED_ARMING_REQUIRED
    if r262b_found and risk_contract_valid:
        return TINY_LIVE_FINAL_CONSOLE_READY_FOR_REVIEW
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def format_tiny_live_final_console_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def tiny_live_final_console_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _build_final_console_matrix(
    *,
    contract_fit_panel: Mapping[str, Any],
    signed_triplet_panel: Mapping[str, Any],
    lane_intelligence_panel: Mapping[str, Any],
    controls_panel: Mapping[str, Any],
    experimental_lane_acceptance_recorded: bool,
    blocked_by: Sequence[str],
) -> dict[str, Any]:
    blocked = list(blocked_by)
    if not contract_fit_panel.get("r262b_found"):
        blocked.append("missing_r262b")
    if not contract_fit_panel.get("risk_contract_valid"):
        blocked.append("risk_contract_invalid")
    if lane_intelligence_panel.get("operator_acceptance_required") and not experimental_lane_acceptance_recorded:
        blocked.append("experimental_lane_acceptance_required")
    return {
        "r262b_valid": contract_fit_panel.get("r262b_found") is True and contract_fit_panel.get("fits_contract") is True,
        "signed_triplet_available": signed_triplet_panel.get("signed_triplet_available") is True,
        "risk_contract_valid": contract_fit_panel.get("risk_contract_valid") is True,
        "lane_intelligence_loaded": bool(lane_intelligence_panel.get("execution_lane")),
        "experimental_lane_acceptance_required": lane_intelligence_panel.get("operator_acceptance_required") is True,
        "experimental_lane_acceptance_recorded": bool(experimental_lane_acceptance_recorded),
        "controls_armed": controls_panel.get("controls_armed") is True,
        "submit_allowed": False,
        "order_placed": False,
        "blocked_by": _dedupe(blocked),
    }


def _top_status(
    *,
    record_requested: bool,
    arm_requested: bool,
    review_confirmation_valid: bool,
    arming_confirmation_valid: bool,
    review_recorded: bool,
    controls_armed: bool,
    blocked_by: Sequence[str],
) -> str:
    if record_requested and not review_confirmation_valid:
        return TINY_LIVE_FINAL_CONSOLE_ARMING_REJECTED
    if arm_requested and not arming_confirmation_valid:
        return TINY_LIVE_FINAL_CONSOLE_ARMING_REJECTED
    if controls_armed:
        return TINY_LIVE_FINAL_CONSOLE_CONTROLS_ARMED
    if arm_requested and blocked_by:
        return TINY_LIVE_FINAL_CONSOLE_BLOCKED
    if review_recorded:
        return TINY_LIVE_FINAL_CONSOLE_REVIEW_RECORDED
    return TINY_LIVE_FINAL_CONSOLE_READY


def _safety(*, lane_controls_written: bool, experimental_lane_acceptance_recorded: bool) -> dict[str, Any]:
    return {
        **SAFETY_FALSE,
        "env_written": False,
        "env_mutated": False,
        "external_env_file_written": False,
        "config_written": bool(lane_controls_written),
        "risk_contract_config_written": False,
        "lane_controls_written": bool(lane_controls_written),
        "live_config_written": False,
        "final_console_only": True,
        "hmac_signature_created": False,
        "signed_request_written": False,
        "signed_order_request_created": False,
        "signed_trading_request_created": False,
        "submit_allowed": False,
        "submit_attempted": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "binance_order_endpoint_called": False,
        "binance_test_order_endpoint_called": False,
        "binance_account_endpoint_called": False,
        "binance_exchange_info_endpoint_called": False,
        "binance_mark_price_endpoint_called": False,
        "private_binance_endpoint_called": False,
        "signed_binance_endpoint_called": False,
        "network_allowed": False,
        "transfer_endpoint_called": False,
        "withdraw_endpoint_called": False,
        "kill_switch_disabled": False,
        "live_controls_armed_by_phase": bool(lane_controls_written),
        "secrets_read": False,
        "secrets_shown": False,
        "secrets_persisted": False,
        "secret_values_in_output": False,
        "global_live_flags_changed": False,
        "paper_live_separation_intact": True,
        "official_tiny_live_lane_changed": False,
        "experimental_lane_acceptance_recorded": bool(experimental_lane_acceptance_recorded),
    }


def _recommended_next_operator_move(packet: Mapping[str, Any], overall: str) -> str:
    step = packet.get("next_required_step")
    if step == "R264_ACTUAL_SUBMIT_CHECKPOINT":
        return "Proceed only to the R264 actual submit checkpoint; do not submit from R263."
    if step == "ARM_CONTROLS":
        return "Use the exact R263 controls arming phrase only if accepting the 8m short experimental lane."
    if step == "RERUN_R262B":
        return "Rerun R262B contract-fit triplet before using this console."
    if step == "WAIT_FOR_FRESH_CANDIDATE":
        return "Wait for a fresh eligible tiny-live candidate or switch lane in a later phase."
    return "Review the final console; actual submit remains forbidden."


def _recommended_next_engineering_move(packet: Mapping[str, Any], overall: str) -> str:
    if packet.get("next_required_step") == "R264_ACTUAL_SUBMIT_CHECKPOINT":
        return "Build/run R264 with R263 armed-state, R262B contract-fit, exact submit phrase, idempotency, and reconciliation checks."
    if packet.get("next_required_step") == "ARM_CONTROLS":
        return "Keep R264 blocked until R263 experimental-lane acceptance and controls arming are recorded."
    return "Keep R263 read-only except exact controls arming; do not create submit behavior here."


def _promotion_ready_lanes(snapshot: Mapping[str, Any]) -> list[str]:
    lanes: list[str] = []
    for row in snapshot.get("promotion_ready") or []:
        if not isinstance(row, Mapping):
            continue
        lane = row.get("strategy_key") or _lane_key_from_row(row)
        if lane:
            lanes.append(str(lane))
    for lane in PROMOTED_LANE_KEYS:
        if lane not in lanes:
            lanes.append(lane)
    return lanes


def _risk_contract_limits_valid(risk_contract: Mapping[str, Any]) -> bool:
    contract = risk_contract.get("contract") if isinstance(risk_contract.get("contract"), Mapping) else {}
    if not contract:
        return False
    return bool(
        contract.get("symbol") == "BTCUSDT"
        and contract.get("timeframe") == "8m"
        and contract.get("direction") == "short"
        and (_float_or_none(contract.get("tiny_live_margin_usdt") or contract.get("margin_budget_usdt")) or 0) <= 44.0
        and (_float_or_none(contract.get("max_loss_usdt")) or 0) <= 4.44
        and (_float_or_none(contract.get("max_notional_usdt") or contract.get("max_position_notional_usdt")) or 0) >= 440.0
        and (_float_or_none(contract.get("leverage")) or 0) <= 10.0
    )


def _lane_experimental_acceptance_recorded(lane_controls: Mapping[str, Any]) -> bool:
    lane = lane_controls.get("official_lane") if isinstance(lane_controls.get("official_lane"), Mapping) else {}
    return bool(
        lane.get("experimental_lane_acceptance_recorded") is True
        and lane.get("experimental_lane_acceptance_phase") == "R263"
    )


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=50, max_bytes=16_777_216)]


def _latest_file_record(path: Path) -> dict[str, Any]:
    records = _load_ndjson(path)
    return records[0] if records else {}


def _record_lane(record: Mapping[str, Any]) -> str:
    target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    return str(target.get("official_lane_key") or record.get("official_lane_key") or "")


def _arming_result(succeeded: bool, blocked_by: Sequence[str]) -> dict[str, Any]:
    return {
        "attempted": True,
        "succeeded": bool(succeeded),
        "lane_controls_written": False,
        "blocked_by": _dedupe(blocked_by),
        "before": {},
        "after": {},
    }


def _lane_key_from_row(row: Mapping[str, Any]) -> str:
    return normalize_lane_key(
        row.get("symbol"),
        row.get("timeframe"),
        row.get("direction"),
        row.get("entry_mode"),
    )


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key).split("|")
    padded = (parts + ["", "", "", ""])[:4]
    return padded[0], padded[1], padded[2], padded[3]


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
