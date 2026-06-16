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
from src.app.hammer_radar.operator.binance_account_read_env_contract import (
    build_binance_account_read_env_discovery,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, normalize_lane_key
from src.app.hammer_radar.operator.readiness import build_readiness_payload
from src.app.hammer_radar.operator.strategy_promotion_watcher import build_strategy_promotion_status
from src.app.hammer_radar.operator.tiny_live_autonomous_armed_dry_run import (
    DRY_RUN_ARMING_CONFIRMATION_PHRASE,
    DRY_RUN_DISARM_CONFIRMATION_PHRASE,
    build_autonomous_dry_run_arming_status,
    build_tiny_live_autonomous_armed_dry_run,
    load_latest_autonomous_real_candidate_record,
    load_latest_autonomous_rehearsal_record,
)
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
from src.app.hammer_radar.operator.tiny_live_binance_readonly_precision_mark_price_gate import (
    build_exchange_minimum_tiny_live_decision_packet,
    load_tiny_live_binance_readonly_precision_mark_price_records,
)
from src.app.hammer_radar.operator.tiny_live_binance_autonomous_readiness_binding import (
    build_tiny_live_binance_autonomous_readiness_binding,
)
from src.app.hammer_radar.operator.tiny_live_leverage_margin_readiness import (
    build_post_manual_leverage_margin_alignment_verification,
    build_tiny_live_leverage_margin_readiness,
    load_latest_post_manual_leverage_margin_verification,
    load_latest_tiny_live_leverage_margin_readiness,
)
from src.app.hammer_radar.operator.tiny_live_one_shot_pre_activation_gate import (
    build_tiny_live_one_shot_pre_activation_gate,
)
from src.app.hammer_radar.operator.tiny_live_fresh_trigger_watch import (
    build_latest_or_not_checked_fresh_trigger_watch,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_loop import (
    build_latest_or_not_checked_autonomous_trigger_loop,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler import (
    build_latest_or_idle_autonomous_trigger_scheduler,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_validation import (
    build_tiny_live_risk_contract_validation_summary,
)
from src.app.hammer_radar.operator.trade_ticket import build_trade_ticket
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import LIVE_QUALIFIED, NEAR_MISS_INCUBATOR

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
    "logs/hammer_radar_forward/tiny_live_binance_readonly_precision_mark_price_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_binance_autonomous_readiness_binding.ndjson",
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
        latest_r264_dry_preview = load_latest_r264_dry_preview_summary(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        fresh_candidate_status = build_final_console_fresh_candidate_status(
            log_dir=resolved_log_dir,
            risk_contract_config_path=risk_path,
            official_lane_key=official_lane_key,
        )
        current_lane_key = fresh_candidate_status.get("lane_key")
        current_ticket_exists = bool(
            fresh_candidate_status.get("trade_ticket_status") == "PROPOSED"
            and current_lane_key
        )
        current_expected_orders = (
            expected_orders_for_direction(str(fresh_candidate_status.get("direction") or ""))
            if current_ticket_exists
            else None
        )
        latest_jit_launch_packet = load_latest_jit_launch_packet_summary(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_jit_launch_packet = suppress_final_command_for_unqualified_candidate(
            latest_jit_launch_packet=latest_jit_launch_packet,
            fresh_candidate_status=fresh_candidate_status,
        )
        exchange_minimum_decision_packet = build_final_console_exchange_minimum_decision_packet(
            log_dir=resolved_log_dir,
            risk_contract=risk_contract,
            official_lane_key=official_lane_key,
        )
        autonomous_armed_dry_run_panel = build_autonomous_armed_dry_run_panel(
            log_dir=resolved_log_dir,
        )
        binance_autonomous_readiness_panel = build_binance_autonomous_readiness_panel(
            log_dir=resolved_log_dir,
        )
        leverage_margin_readiness_panel = build_leverage_margin_readiness_panel(
            log_dir=resolved_log_dir,
        )
        post_manual_leverage_margin_verification_panel = (
            build_post_manual_leverage_margin_verification_panel(log_dir=resolved_log_dir)
        )
        one_shot_pre_activation_gate_panel = build_one_shot_pre_activation_gate_panel(
            log_dir=resolved_log_dir,
            risk_contract_config_path=risk_path,
        )
        fresh_trigger_watch_panel = build_fresh_trigger_watch_panel(
            log_dir=resolved_log_dir,
            risk_contract_config_path=risk_path,
        )
        autonomous_trigger_loop_panel = build_autonomous_trigger_loop_panel(
            log_dir=resolved_log_dir,
        )
        autonomous_trigger_scheduler_panel = build_autonomous_trigger_scheduler_panel(
            log_dir=resolved_log_dir,
        )
        lane_context = load_lane_fisherman_context(
            lane_controls=lane_controls,
            promotion_snapshot=promotion_snapshot,
            readiness_snapshot=readiness_snapshot,
            official_lane_key=official_lane_key,
        )

        risk_interpretation = summarize_final_console_risk_interpretation(
            latest_r262b=latest_r262b,
            risk_contract=risk_contract,
            fresh_candidate_status=fresh_candidate_status,
        )
        contract_fit_risk_interpretation = summarize_contract_fit_risk_interpretation(
            latest_r262b=latest_r262b,
            risk_contract=risk_contract,
        )
        contract_fit_panel = summarize_contract_fit_panel(
            latest_r262b,
            risk_interpretation=contract_fit_risk_interpretation,
        )
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
            exchange_minimum_decision_packet=exchange_minimum_decision_packet,
            no_current_ticket=not current_ticket_exists,
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
            exchange_minimum_decision_packet=exchange_minimum_decision_packet,
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
                    "historical_official_lane_key": official_lane_key,
                    "official_lane_key": official_lane_key,
                    "current_proposed_ticket_lane_key": fresh_candidate_status.get("lane_key"),
                    "current_proposed_ticket_selected": current_ticket_exists,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "final_console_only": True,
                    "submit_allowed": False,
                    "final_command_available": False,
                    "order_placed": False,
                    "real_order_placed": False,
                    "submit_attempted": False,
                    "binance_order_endpoint_called": False,
                },
                "contract_fit_panel": contract_fit_panel,
                "risk_contract_interpretation": risk_interpretation,
                "signed_triplet_panel": signed_triplet_panel,
                "controls_panel": controls_panel,
                "latest_r264_dry_preview": latest_r264_dry_preview,
                "previous_r264_preview": latest_r264_dry_preview,
                "fresh_candidate_status": fresh_candidate_status,
                "current_proposed_ticket_lane": {
                    "lane_key": fresh_candidate_status.get("lane_key"),
                    "symbol": fresh_candidate_status.get("symbol"),
                    "timeframe": fresh_candidate_status.get("timeframe"),
                    "direction": fresh_candidate_status.get("direction"),
                    "entry_mode": fresh_candidate_status.get("entry_mode"),
                    "signal_id": fresh_candidate_status.get("signal_id"),
                    "matches_console_lane": current_lane_key == official_lane_key if current_ticket_exists else False,
                    "no_current_ticket": not current_ticket_exists,
                    "historical_official_lane_key": official_lane_key,
                },
                "lane_specific_expected_orders": current_expected_orders,
                "signal_origin_status": fresh_candidate_status.get("signal_origin_status"),
                "latest_jit_launch_packet": latest_jit_launch_packet,
                "lane_intelligence_panel": lane_intelligence_panel,
                "autonomous_armed_dry_run_panel": autonomous_armed_dry_run_panel,
                "binance_autonomous_readiness_panel": binance_autonomous_readiness_panel,
                "leverage_margin_readiness_panel": leverage_margin_readiness_panel,
                "post_manual_leverage_margin_verification_panel": (
                    post_manual_leverage_margin_verification_panel
                ),
                "one_shot_pre_activation_gate_panel": one_shot_pre_activation_gate_panel,
                "fresh_trigger_watch_panel": fresh_trigger_watch_panel,
                "autonomous_trigger_loop_panel": autonomous_trigger_loop_panel,
                "autonomous_trigger_scheduler_panel": autonomous_trigger_scheduler_panel,
                "exchange_minimum_decision_packet": exchange_minimum_decision_packet,
                "promotion_readiness_panel": promotion_readiness_panel,
                "qualified_candidate_watch": promotion_readiness_panel.get("qualified_candidate_watch")
                if isinstance(promotion_readiness_panel.get("qualified_candidate_watch"), Mapping)
                else {},
                "operator_choice_panel": operator_choice_panel,
                "controls_arming_result": controls_arming_result,
                "final_console_go_no_go_packet": go_no_go,
                "final_console_matrix": matrix,
                "operator_access": build_final_console_operator_access(),
                "trade_ticket_status": fresh_candidate_status.get("trade_ticket_status") or "BLOCKED",
                "fresh_candidate_available": fresh_candidate_status.get("fresh_candidate_available") is True,
                "final_live_submit_command_packet": latest_jit_launch_packet.get(
                    "final_live_submit_command_packet"
                )
                if isinstance(latest_jit_launch_packet.get("final_live_submit_command_packet"), Mapping)
                else {
                    "available": False,
                    "must_be_run_manually_by_operator": True,
                    "do_not_run_from_codex": True,
                    "command": "",
                    "unavailable_reason": "no_r268_jit_unlock_packet_recorded",
                },
                "final_command_available": latest_jit_launch_packet.get("final_command_available") is True,
                "submit_allowed": False,
                "submit_attempted": False,
                "order_placed": False,
                "real_order_placed": False,
                "real_order_forbidden": True,
                "binance_order_endpoint_called": False,
                "binance_test_order_endpoint_called": False,
                "secrets_shown": False,
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


def build_autonomous_armed_dry_run_panel(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    packet = build_tiny_live_autonomous_armed_dry_run(log_dir=log_dir)
    arming_status = build_autonomous_dry_run_arming_status(log_dir=log_dir)
    latest_rehearsal = load_latest_autonomous_rehearsal_record(log_dir=log_dir)
    latest_real_candidate = load_latest_autonomous_real_candidate_record(log_dir=log_dir)
    arming = packet.get("arming_state") if isinstance(packet.get("arming_state"), Mapping) else {}
    candidate = packet.get("selected_candidate") if isinstance(packet.get("selected_candidate"), Mapping) else {}
    status = str(packet.get("status") or "AUTO_DRY_RUN_WAIT")
    blockers = [str(item) for item in packet.get("blockers") or []]
    if status == "AUTO_DRY_RUN_WAIT":
        next_required_step = "WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE"
    elif "BLOCKED_BY_GLOBAL_ARMING" in blockers or "BLOCKED_BY_LANE_ARMING" in blockers:
        next_required_step = "BLOCKED_BY_ARMING"
    elif status == "AUTO_DRY_RUN_READY":
        next_required_step = "REVIEW_AUTONOMOUS_DRY_RUN_PACKET_REAL_ORDER_FORBIDDEN"
    else:
        next_required_step = packet.get("next_required_step") or "CLEAR_BLOCKERS_OR_WAIT"
    return {
        "dry_run_arming_control_supported": True,
        "dry_run_arming_status": arming_status,
        "armed_lane_key": arming.get("armed_lane_key"),
        "allowed_lane_keys": list(arming.get("allowed_lane_keys") or []),
        "any_lane_auto_armed": arming.get("any_lane_auto_armed") is True,
        "dry_run_only": True,
        "global_auto_live_enabled": arming.get("global_auto_live_enabled") is True,
        "current_lane_auto_armed": bool(candidate.get("lane_key") and candidate.get("lane_key") in set(arming.get("lane_auto_live_enabled_keys") or [])),
        "auto_execute_mode": arming.get("auto_execute_mode") or "dry_run_only",
        "selected_candidate_lane": candidate.get("lane_key"),
        "auto_dry_run_status": status,
        "rehearsal_supported": True,
        "real_candidate_binding_supported": packet.get("real_candidate_binding_supported") is True,
        "real_candidate_binding_status": status,
        "current_candidate_watch_status": packet.get("candidate_watch_status"),
        "real_candidate_lane": candidate.get("source_lane_key") or candidate.get("lane_key"),
        "real_candidate_signal_id": candidate.get("source_signal_id") or candidate.get("signal_id"),
        "real_candidate_dry_run_go_no_go": (
            packet.get("dry_run_go_no_go", {}).get("real_candidate_dry_run_go_no_go")
            if isinstance(packet.get("dry_run_go_no_go"), Mapping)
            else status
        ),
        "real_candidate_blockers": blockers,
        "latest_real_candidate_dry_run_record": _latest_real_candidate_record_summary(latest_real_candidate),
        "latest_rehearsal_status": latest_rehearsal.get("status") if latest_rehearsal else None,
        "latest_rehearsal_lane": (
            (latest_rehearsal.get("selected_candidate") or {}).get("lane_key")
            if isinstance((latest_rehearsal or {}).get("selected_candidate"), Mapping)
            else None
        ),
        "latest_rehearsal_order_triplet": latest_rehearsal.get("simulated_order_triplet") if latest_rehearsal else None,
        "next_required_step": next_required_step,
        "disarm_next_command": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward tiny-live-autonomous-dry-run-disarm-lane "
            "--operator-id local_operator --reason \"return autonomous dry-run arming to OFF\" "
            f"--confirm-dry-run-autonomous-disarm \"{DRY_RUN_DISARM_CONFIRMATION_PHRASE}\""
        ),
        "arm_next_command_templates": [
            (
                "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
                "--log-dir logs/hammer_radar_forward tiny-live-autonomous-dry-run-arm-lane "
                f"--lane-key \"{lane_key}\" --operator-id local_operator "
                "--reason \"dry-run arming only; no submit; no real order; no Binance endpoint.\" "
                f"--confirm-dry-run-autonomous-arming \"{DRY_RUN_ARMING_CONFIRMATION_PHRASE}\""
            )
            for lane_key in arming_status.get("live_qualified_lane_keys") or []
        ],
        "blockers": blockers,
        "real_order_still_forbidden": True,
        "real_order_forbidden": True,
        "submit_allowed": False,
        "final_command_available": False,
        "safety": packet.get("safety") if isinstance(packet.get("safety"), Mapping) else {},
    }


def build_binance_autonomous_readiness_panel(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    binding = build_tiny_live_binance_autonomous_readiness_binding(log_dir=log_dir)
    discovery = build_binance_account_read_env_discovery(include_systemd=False)
    selected = discovery.get("selected_env_contract") if isinstance(discovery.get("selected_env_contract"), Mapping) else {}
    matrix = (
        binding.get("autonomous_one_shot_readiness_matrix")
        if isinstance(binding.get("autonomous_one_shot_readiness_matrix"), Mapping)
        else {}
    )
    return {
        "binding_supported": binding.get("binding_supported") is True,
        "latest_status": binding.get("status"),
        "account_read_env_discovery_status": discovery.get("status"),
        "selected_account_read_env_names": {
            "selected_api_key_env_name": selected.get("selected_api_key_env_name"),
            "selected_api_secret_env_name": selected.get("selected_api_secret_env_name"),
            "selected_mode_env_name": selected.get("selected_mode_env_name"),
            "selected_enabled_env_name": selected.get("selected_enabled_env_name"),
            "selected_env_values_redacted": True,
        },
        "selected_env_source": selected.get("selected_env_source"),
        "account_read_alias_candidates_present": [
            {
                "source": candidate.get("source"),
                "api_key_env_name": candidate.get("api_key_env_name"),
                "api_secret_env_name": candidate.get("api_secret_env_name"),
                "api_key_present": candidate.get("api_key_present") is True,
                "api_secret_present": candidate.get("api_secret_present") is True,
            }
            for candidate in discovery.get("discovered_alias_candidates") or []
            if isinstance(candidate, Mapping)
            and (candidate.get("api_key_present") is True or candidate.get("api_secret_present") is True)
        ],
        "runtime_env_source_summary": discovery.get("runtime_env_sources"),
        "cli_runtime_env_loader_supported": discovery.get("cli_runtime_env_loader_supported") is True,
        "safe_cli_env_loader_command": discovery.get("safe_cli_env_loader_command"),
        "allowed_env_file_paths": list(discovery.get("allowed_env_file_paths") or []),
        "loaded_env_file_status": discovery.get("loaded_env_file_status"),
        "loaded_env_names": list(discovery.get("loaded_env_names") or []),
        "loaded_secret_names_redacted": True,
        "env_file_values_printed": False,
        "account_read_env_ready": discovery.get("status") == "ACCOUNT_READ_ENV_READY",
        "binance_readiness_ready": matrix.get("binance_readiness_ready") is True,
        "exchange_minimum_ready": matrix.get("exchange_minimum_ready") is True,
        "account_position_readiness_status": binding.get("account_position_readiness_status"),
        "account_balance_checked": binding.get("account_balance_checked") is True,
        "position_risk_checked": binding.get("position_risk_checked") is True,
        "wallet_supports_minimum_tiny": binding.get("wallet_supports_minimum_tiny") is True,
        "wallet_supports_configured_margin_budget": (
            binding.get("wallet_supports_configured_margin_budget") is True
        ),
        "open_position_conflict": binding.get("open_position_conflict"),
        "btcusdt_position_summary": {
            "position_amt": binding.get("btcusdt_position_amt"),
            "position_side": binding.get("btcusdt_position_side"),
            "position_notional": binding.get("btcusdt_position_notional"),
        },
        "leverage_checked": binding.get("leverage_checked") is True,
        "margin_mode_checked": binding.get("margin_mode_checked") is True,
        "private_readonly_supported": True,
        "wallet_ready": matrix.get("wallet_ready") is True,
        "position_conflict_status": (
            "NO_CONFLICT"
            if matrix.get("no_conflicting_position") is True
            else "NOT_VERIFIED_OR_CONFLICT"
        ),
        "configured_cap": binding.get("configured_notional_cap_usdt"),
        "configured_leverage": binding.get("configured_leverage"),
        "configured_margin_budget": binding.get("configured_margin_budget_usdt"),
        "readiness_blockers": list(binding.get("readiness_blockers") or []),
        "safe_next_readonly_commands": list(binding.get("safe_next_readonly_commands") or []),
        "private_readonly_safe_next_command": next(
            (
                command
                for command in binding.get("safe_next_readonly_commands") or []
                if "--fetch-binance-readonly-account-position" in str(command)
            ),
            None,
        ),
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def build_leverage_margin_readiness_panel(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    packet = load_latest_tiny_live_leverage_margin_readiness(log_dir=log_dir)
    if not packet:
        packet = build_tiny_live_leverage_margin_readiness(log_dir=log_dir)
    return {
        "status": packet.get("status"),
        "mismatch_classification": packet.get("mismatch_classification"),
        "current_leverage": packet.get("current_leverage"),
        "current_margin_mode": packet.get("current_margin_mode"),
        "configured_leverage": packet.get("configured_leverage"),
        "configured_margin_mode": packet.get("configured_margin_mode"),
        "zero_position": packet.get("zero_position"),
        "manual_only_adjustment_required": packet.get("manual_only_adjustment_required"),
        "mutation_required": packet.get("mutation_required"),
        "mutation_performed": False,
        "leverage_change_called": False,
        "margin_change_called": False,
        "live_submit_blocked_by_leverage_margin": packet.get("live_submit_blocked_by_leverage_margin"),
        "readiness_blockers": list(packet.get("readiness_blockers") or []),
        "safe_next_cli_command": packet.get("safe_next_cli_command"),
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "safety": packet.get("safety") if isinstance(packet.get("safety"), Mapping) else {},
    }


def build_post_manual_leverage_margin_verification_panel(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    packet = load_latest_post_manual_leverage_margin_verification(log_dir=log_dir)
    if not packet:
        packet = build_post_manual_leverage_margin_alignment_verification(log_dir=log_dir)
    return {
        "status": packet.get("status"),
        "operator_reported_manual_adjustment": packet.get("operator_reported_manual_adjustment") is True,
        "expected_leverage": packet.get("expected_leverage"),
        "expected_margin_mode": packet.get("expected_margin_mode"),
        "current_leverage": packet.get("current_leverage"),
        "current_margin_mode": packet.get("current_margin_mode"),
        "leverage_matches_expectation": packet.get("leverage_matches_expectation"),
        "margin_mode_matches_expectation": packet.get("margin_mode_matches_expectation"),
        "zero_position": packet.get("zero_position"),
        "open_position_conflict": packet.get("open_position_conflict"),
        "wallet_supports_configured_margin_budget": packet.get(
            "wallet_supports_configured_margin_budget"
        ),
        "post_manual_alignment_verified": packet.get("post_manual_alignment_verified") is True,
        "leverage_margin_ready": packet.get("leverage_margin_ready") is True,
        "leverage_margin_blocks_one_shot": packet.get("leverage_margin_blocks_one_shot") is True,
        "readiness_blockers": list(packet.get("readiness_blockers") or []),
        "recommended_operator_move": packet.get("recommended_operator_move"),
        "safe_next_cli_command": packet.get("safe_next_cli_command"),
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "safety": packet.get("safety") if isinstance(packet.get("safety"), Mapping) else {},
    }


def build_one_shot_pre_activation_gate_panel(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
) -> dict[str, Any]:
    packet = build_tiny_live_one_shot_pre_activation_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_contract_config_path,
    )
    panel = packet.get("one_shot_pre_activation_gate_panel")
    if isinstance(panel, Mapping):
        return dict(panel)
    return {
        "status": packet.get("status"),
        "current_candidate_status": packet.get("candidate_watch_status"),
        "binance_readiness_summary": {},
        "leverage_margin_verified_summary": {},
        "live_qualified_lane_list": [],
        "approved_lane_match": packet.get("approved_lane_match"),
        "exact_risk_contract_status": {},
        "protective_preview_status": {},
        "idempotency_status": {},
        "next_required_step": packet.get("next_required_step"),
        "safe_next_cli_command": packet.get("safe_next_cli_command"),
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def build_fresh_trigger_watch_panel(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
) -> dict[str, Any]:
    packet = build_latest_or_not_checked_fresh_trigger_watch(
        log_dir=log_dir,
    )
    panel = packet.get("fresh_trigger_watch_panel")
    if isinstance(panel, Mapping):
        return dict(panel)
    return {
        "status": packet.get("status"),
        "current_candidate_summary": {
            "lane_key": packet.get("current_candidate_lane_key"),
            "signal_id": packet.get("current_candidate_signal_id"),
            "timeframe": packet.get("current_candidate_timeframe"),
            "direction": packet.get("current_candidate_direction"),
            "entry_mode": packet.get("current_candidate_entry_mode"),
            "age_minutes": packet.get("current_candidate_age_minutes"),
        },
        "approved_lane_match": packet.get("approved_lane_match"),
        "pre_activation_status": packet.get("pre_activation_status"),
        "risk_contract_status": {
            "found": packet.get("exact_lane_risk_contract_found"),
            "valid": packet.get("exact_lane_risk_contract_valid"),
        },
        "dry_run_arming_status": packet.get("autonomous_dry_run_status"),
        "telegram_payload_prepared": bool(packet.get("telegram_compatible_payload")),
        "telegram_send_enabled": False,
        "next_required_step": packet.get("next_required_step"),
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def build_autonomous_trigger_loop_panel(
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    packet = build_latest_or_not_checked_autonomous_trigger_loop(log_dir=log_dir)
    panel = packet.get("autonomous_trigger_loop_panel")
    if isinstance(panel, Mapping):
        panel = dict(panel)
    else:
        panel = {
            "operator_role": packet.get("operator_role"),
            "machine_role": packet.get("machine_role"),
            "per_signal_operator_approval_required": False,
            "alert_is_visibility_only": True,
            "status": packet.get("status"),
            "candidate_summary": {
                "lane_key": packet.get("current_candidate_lane_key"),
                "signal_id": packet.get("current_candidate_signal_id"),
            },
            "arming_status": {
                "global_auto_live_enabled": packet.get("global_auto_live_enabled") is True,
                "exact_lane_auto_armed": packet.get("exact_lane_auto_armed") is True,
                "dry_run_only": True,
            },
            "autonomous_dry_run_lifecycle_status": (
                "recorded" if packet.get("autonomous_dry_run_execution_recorded") is True else "not_recorded"
            ),
            "next_required_step": packet.get("next_required_step"),
            "blockers": list(packet.get("blockers") or []),
        }
    panel.update(
        {
            "operator_role": panel.get("operator_role")
            or "arms_disarms_tunes_risk_not_per_signal_approval",
            "machine_role": panel.get("machine_role")
            or "auto_triggers_when_armed_and_all_gates_open",
            "per_signal_operator_approval_required": False,
            "alert_is_visibility_only": True,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )
    return panel


def build_autonomous_trigger_scheduler_panel(
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    packet = build_latest_or_idle_autonomous_trigger_scheduler(log_dir=log_dir)
    panel = packet.get("autonomous_trigger_scheduler_panel")
    if isinstance(panel, Mapping):
        panel = dict(panel)
    else:
        panel = {
            "scheduler_supported": True,
            "status": packet.get("status"),
            "latest_scheduler_status": packet.get("status"),
            "latest_trigger_loop_status": packet.get("trigger_loop_status"),
            "iterations_summary": {
                "iterations_requested": packet.get("iterations_requested"),
                "iterations_completed": packet.get("iterations_completed"),
                "statuses_seen": list(packet.get("statuses_seen") or []),
                "latest_status": packet.get("latest_status") or packet.get("status"),
                "latest_trigger_loop_status": packet.get("latest_trigger_loop_status")
                or packet.get("trigger_loop_status"),
                "latest_candidate_lane_key": packet.get("latest_candidate_lane_key")
                or packet.get("current_candidate_lane_key"),
                "any_dry_run_execution_recorded": (
                    packet.get("any_dry_run_execution_recorded") is True
                    or packet.get("autonomous_dry_run_execution_recorded") is True
                ),
                "any_unsafe_flag_detected": packet.get("any_unsafe_flag_detected") is True,
                "stopped_reason": packet.get("stopped_reason"),
            },
        }
    panel.update(
        {
            "scheduler_supported": True,
            "latest_scheduler_status": panel.get("latest_scheduler_status") or panel.get("status"),
            "latest_trigger_loop_status": panel.get("latest_trigger_loop_status"),
            "operator_role": "arms_disarms_tunes_risk_not_per_signal_approval",
            "machine_role": "auto_triggers_when_armed_and_all_gates_open",
            "per_signal_operator_approval_required": False,
            "next_scheduler_command": panel.get("next_scheduler_command")
            or (
                "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
                "--log-dir logs/hammer_radar_forward tiny-live-autonomous-trigger-scheduler-once "
                "--record-autonomous-trigger-scheduler --operator-id local_operator "
                "--reason \"R288 autonomous trigger scheduler dry-run loop; no submit.\""
            ),
            "proposed_safe_loop_command": panel.get("proposed_safe_loop_command")
            or (
                "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
                "--log-dir logs/hammer_radar_forward tiny-live-autonomous-trigger-scheduler-loop "
                "--max-iterations 2 --sleep-seconds 0 --record-autonomous-trigger-scheduler "
                "--operator-id local_operator --reason \"R288 bounded dry-run scheduler validation; no submit.\""
            ),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )
    return panel


def _latest_real_candidate_record_summary(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    candidate = record.get("selected_candidate") if isinstance(record.get("selected_candidate"), Mapping) else {}
    triplet = record.get("simulated_order_triplet") if isinstance(record.get("simulated_order_triplet"), Mapping) else None
    return {
        "record_id": record.get("record_id"),
        "status": record.get("status"),
        "recorded_at": record.get("recorded_at"),
        "lane_key": candidate.get("source_lane_key") or candidate.get("lane_key"),
        "signal_id": candidate.get("source_signal_id") or candidate.get("signal_id"),
        "real_market_signal": record.get("real_market_signal") is True,
        "fixture_candidate": record.get("fixture_candidate") is True,
        "simulated_order_triplet": triplet,
        "final_command_available": False,
        "real_order_forbidden": True,
        "submit_allowed": False,
    }


def load_latest_r264_dry_preview_summary(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    record = _latest_file_record(Path(get_log_dir(log_dir, use_env=True)) / "tiny_live_actual_submit_reconciliation.ndjson")
    if not record or _record_lane(record) != official_lane_key:
        return {"found": False, "valid": False, "blocked_by": ["r264_dry_preview_missing"]}
    pre = record.get("pre_submit_validation") if isinstance(record.get("pre_submit_validation"), Mapping) else {}
    return {
        "found": True,
        "valid": pre.get("valid") is True,
        "status": record.get("status"),
        "overall_status": record.get("actual_submit_overall_status"),
        "risk_contract_valid": pre.get("risk_contract_valid") is True,
        "blocked_by": list(pre.get("blocked_by") or []),
        "actual_submit_preview_recorded": record.get("actual_submit_preview_recorded") is True,
        "order_placed": False,
        "binance_order_endpoint_called": False,
    }


def load_latest_jit_launch_packet_summary(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    record = _latest_file_record(Path(get_log_dir(log_dir, use_env=True)) / "tiny_live_jit_launch_packet.ndjson")
    if not record or _record_lane(record) != official_lane_key:
        return {
            "found": False,
            "valid": False,
            "final_command_available": False,
            "blocked_by": ["r268_jit_unlock_packet_missing"],
            "order_placed": False,
            "binance_order_endpoint_called": False,
        }
    validation = record.get("jit_validation") if isinstance(record.get("jit_validation"), Mapping) else {}
    command = (
        record.get("final_live_submit_command_packet")
        if isinstance(record.get("final_live_submit_command_packet"), Mapping)
        else {}
    )
    gate = command.get("gate_validation") if isinstance(command.get("gate_validation"), Mapping) else {}
    return {
        "found": True,
        "valid": validation.get("valid") is True,
        "status": record.get("status"),
        "overall_status": record.get("jit_launch_overall_status"),
        "final_command_available": command.get("available") is True,
        "final_live_submit_command_packet": command,
        "unlock_confirmation_valid": command.get("unlock_confirmation_valid") is True,
        "manual_only": command.get("manual_only") is True,
        "do_not_run_from_codex": command.get("do_not_run_from_codex") is True,
        "blocked_by": list(gate.get("blocked_by") or validation.get("blocked_by") or []),
        "r262b_valid": validation.get("r262b_valid") is True,
        "r263_armed": validation.get("r263_armed") is True,
        "r264_dry_preview_valid": validation.get("r264_dry_preview_valid") is True,
        "signed_triplet_fresh": validation.get("signed_triplet_fresh") is True,
        "idempotency_clean": validation.get("idempotency_clean") is True,
        "candidate_qty": validation.get("candidate_qty"),
        "candidate_notional_usdt": validation.get("candidate_notional_usdt"),
        "order_placed": False,
        "binance_order_endpoint_called": False,
    }


def suppress_final_command_for_unqualified_candidate(
    *,
    latest_jit_launch_packet: Mapping[str, Any],
    fresh_candidate_status: Mapping[str, Any],
) -> dict[str, Any]:
    packet = _sanitize(dict(latest_jit_launch_packet))
    strategy = (
        fresh_candidate_status.get("strategy_qualification")
        if isinstance(fresh_candidate_status.get("strategy_qualification"), Mapping)
        else {}
    )
    live_class = str(strategy.get("live_qualification_class") or strategy.get("watch_category") or "")
    current_ticket_exists = bool(
        fresh_candidate_status.get("trade_ticket_status") == "PROPOSED"
        and fresh_candidate_status.get("lane_key")
    )
    if (
        current_ticket_exists
        and live_class in {"", LIVE_QUALIFIED}
        and fresh_candidate_status.get("fresh_candidate_available") is True
    ):
        return packet
    blocked_by = _dedupe(
        [
            "no_current_ticket" if not current_ticket_exists else "strategy_near_miss_not_live_eligible",
            *[str(item) for item in packet.get("blocked_by") or []],
            *[str(item) for item in fresh_candidate_status.get("blocked_by") or []],
        ]
    )
    command = packet.get("final_live_submit_command_packet")
    if not isinstance(command, Mapping):
        command = {}
    gate = command.get("gate_validation") if isinstance(command.get("gate_validation"), Mapping) else {}
    packet["valid"] = False
    packet["final_command_available"] = False
    packet["blocked_by"] = blocked_by
    suppressed_command = {
        **dict(command),
        "available": False,
        "command": "",
        "unavailable_reason": "; ".join(blocked_by),
        "gate_validation": {
            **dict(gate),
            "valid": False,
            "blocked_by": _dedupe([*[str(item) for item in gate.get("blocked_by") or []], *blocked_by]),
        },
    }
    if not current_ticket_exists:
        suppressed_command["confirmation_phrase"] = ""
        suppressed_command["expected_orders"] = None
        suppressed_command["packet_lane_key"] = None
        suppressed_command["historical_official_lane_key"] = command.get("packet_lane_key")
    packet["final_live_submit_command_packet"] = suppressed_command
    return packet


def build_final_console_fresh_candidate_status(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    try:
        ticket = build_trade_ticket(
            latest_only=True,
            allow_short=direction == "short",
            max_risk_usd=5.0,
            fresh_minutes=30,
            log_dir=log_dir,
            risk_contract_config_path=risk_contract_config_path,
            use_active_tiny_live_contract=True,
        )
    except Exception as exc:  # pragma: no cover - defensive console boundary
        return {
            "fresh_candidate_available": False,
            "trade_ticket_status": "ERROR",
            "blocked_by": [f"trade_ticket_error_{exc.__class__.__name__}"],
            "symbol": symbol,
            "order_placed": False,
            "real_order_placed": False,
            "submit_attempted": False,
            "binance_order_endpoint_called": False,
            "secrets_shown": False,
        }
    blockers = list(ticket.get("blockers") or [])
    if ticket.get("ticket_status") != "PROPOSED":
        blockers.append("fresh_trade_ticket_not_proposed")
    if ticket.get("symbol") != symbol:
        blockers.append("fresh_candidate_symbol_mismatch")
    if direction and ticket.get("direction") != direction:
        blockers.append("fresh_candidate_direction_mismatch")
    if timeframe and ticket.get("timeframe") != timeframe:
        blockers.append("fresh_candidate_timeframe_mismatch")
    if entry_mode and ticket.get("entry_mode") not in {None, "", entry_mode}:
        blockers.append("fresh_candidate_entry_mode_mismatch")
    suggested_position = _float_or_none(ticket.get("suggested_position_usd"))
    suggested_leverage = _float_or_none(ticket.get("suggested_leverage"))
    if _float_or_none(ticket.get("max_position_usd")) != 80.0:
        blockers.append("trade_ticket_max_position_not_80")
    if suggested_position is None or suggested_position <= 0:
        blockers.append("trade_ticket_suggested_position_missing")
    elif suggested_position > 80.0:
        blockers.append("trade_ticket_suggested_position_exceeds_80")
    if suggested_leverage != 10.0:
        blockers.append("trade_ticket_suggested_leverage_not_10")
    origin = ticket.get("signal_origin") if isinstance(ticket.get("signal_origin"), Mapping) else {}
    if origin.get("manual_unlock_allowed") is not True:
        blockers.extend(str(item) for item in origin.get("blocked_by") or ["needs_manual_origin_review"])
    return _sanitize(
        {
            "fresh_candidate_available": not blockers,
            "trade_ticket_status": ticket.get("ticket_status"),
            "ticket_id": ticket.get("ticket_id"),
            "signal_id": ticket.get("signal_id"),
            "symbol": ticket.get("symbol") or symbol,
            "timeframe": ticket.get("timeframe"),
            "direction": ticket.get("direction"),
            "entry_mode": ticket.get("entry_mode"),
            "lane_key": ticket.get("lane_key"),
            "expected_lane_key": official_lane_key,
            "readiness_status": ticket.get("readiness_status"),
            "allowed_now": ticket.get("allowed_now") is True,
            "max_position_usd": _float_or_none(ticket.get("max_position_usd")),
            "suggested_position_usd": suggested_position,
            "suggested_leverage": suggested_leverage,
            "active_contract_mode": ticket.get("active_contract_mode"),
            "active_contract_max_notional_usdt": ticket.get("active_contract_max_notional_usdt"),
            "active_contract_leverage": ticket.get("active_contract_leverage"),
            "active_contract_margin_budget_usdt": ticket.get("active_contract_margin_budget_usdt"),
            "machine_reason": ticket.get("machine_reason"),
            "signal_origin_status": origin,
            "strategy_qualification": ticket.get("strategy_qualification")
            if isinstance(ticket.get("strategy_qualification"), Mapping)
            else {},
            "strategy_qualified": ticket.get("strategy_qualified") is True,
            "strategy_win_rate_pct": ticket.get("strategy_win_rate_pct"),
            "strategy_sample_count": ticket.get("strategy_sample_count"),
            "strategy_avg_pnl_pct": ticket.get("strategy_avg_pnl_pct"),
            "strategy_min_sample": ticket.get("strategy_min_sample"),
            "exact_risk_contract_status": ticket.get("exact_risk_contract_status")
            if isinstance(ticket.get("exact_risk_contract_status"), Mapping)
            else {},
            "exact_risk_contract_found": ticket.get("exact_risk_contract_found") is True,
            "exact_risk_contract_valid": ticket.get("exact_risk_contract_valid") is True,
            "signal_origin_family": origin.get("signal_origin_family"),
            "betrayal_mode_involved": origin.get("betrayal_mode_involved"),
            "betrayal_inverse_involved": origin.get("betrayal_inverse_involved"),
            "promotion_family": origin.get("promotion_family"),
            "promotion_status": origin.get("promotion_status"),
            "candidate_origin_classification": origin.get("candidate_origin_classification"),
            "blocked_by": _dedupe(blockers),
            "order_placed": False,
            "real_order_placed": False,
            "submit_attempted": False,
            "binance_order_endpoint_called": False,
            "secrets_shown": False,
        }
    )


def load_latest_binance_readonly_exchange_minimum_record(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_binance_readonly_precision_mark_price_records(log_dir=log_dir, limit=50):
        if _record_lane(record) == official_lane_key and record.get("readonly_fetch_performed") is True:
            return record
    return {}


def build_final_console_exchange_minimum_decision_packet(
    *,
    log_dir: str | Path | None = None,
    risk_contract: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    contract = risk_contract.get("contract") if isinstance(risk_contract.get("contract"), Mapping) else risk_contract
    configured_cap = (
        _float_or_none(contract.get("max_position_notional_usdt"))
        or _float_or_none(contract.get("max_notional_usdt"))
        or 44.0
    )
    record = load_latest_binance_readonly_exchange_minimum_record(
        log_dir=log_dir,
        official_lane_key=official_lane_key,
    )
    readonly = record.get("binance_readonly_result") if isinstance(record.get("binance_readonly_result"), Mapping) else {}
    precision = readonly.get("precision_snapshot") if isinstance(readonly.get("precision_snapshot"), Mapping) else {}
    mark = readonly.get("mark_price_snapshot") if isinstance(readonly.get("mark_price_snapshot"), Mapping) else {}
    if precision.get("found") is True and mark.get("found") is True:
        return build_exchange_minimum_tiny_live_decision_packet(
            configured_cap_usdt=configured_cap,
            precision_snapshot=precision,
            mark_price_snapshot=mark,
            operator_reported_wallet_usdt=126,
        )
    return {
        "status": "EXCHANGE_MINIMUM_TINY_LIVE_DECISION_PACKET_BLOCKED",
        "symbol": _lane_parts(official_lane_key)[0] or "BTCUSDT",
        "configured_proper_tiny_cap_usdt": configured_cap,
        "configured_cap_possible": False,
        "configured_cap_clears_exchange_minimum": False,
        "configured_cap_blocked_by": ["exchange_minimum_readonly_snapshot_missing"],
        "block_reason": "exchange_minimum_readonly_snapshot_missing",
        "min_quantity": None,
        "step_size": None,
        "min_notional": None,
        "mark_price": None,
        "minimum_valid_quantity_after_rounding": None,
        "minimum_valid_notional_after_rounding": None,
        "wallet_funded_amount_usdt": 126.0,
        "wallet_funded_amount_source": "operator_reported_phase_context_no_account_check",
        "account_balance_checked": False,
        "wallet_supports_exchange_minimum_tiny": None,
        "recommended_operator_decision": "RUN_R242_READONLY_EXCHANGE_MINIMUM_CHECK",
        "recommended_cap_usdt": None,
        "recommended_cap_applied": False,
        "recommended_cap_warning": "No cap recommendation is available until public exchange-info and mark-price are recorded.",
        "safe_next_command": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward tiny-live-binance-readonly-precision-mark-price-gate "
            "--fetch-binance-readonly --confirm-tiny-live-binance-readonly-fetch "
            "\"I CONFIRM BINANCE READONLY PRECISION MARK PRICE CHECK ONLY; NO ORDER; NO SIGNATURE; NO PRIVATE ENDPOINT.\""
        ),
        "go_no_go": "NO-GO",
        "final_command_available": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "binance_order_endpoint_called": False,
        "binance_test_order_endpoint_called": False,
        "secrets_shown": False,
    }


def load_lane_fisherman_context(
    *,
    lane_controls: Mapping[str, Any],
    promotion_snapshot: Mapping[str, Any],
    readiness_snapshot: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    lane = lane_controls.get("official_lane") if isinstance(lane_controls.get("official_lane"), Mapping) else {}
    mode = str(lane.get("mode") or "").lower()
    legacy_promoted = _promotion_ready_lanes(promotion_snapshot)
    live_qualified = _live_qualified_lanes(promotion_snapshot)
    near_miss = _near_miss_lanes(promotion_snapshot)
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
    promotion_status = "live_qualified" if official_lane_key in live_qualified else "not_live_qualified"
    live_class = (
        LIVE_QUALIFIED
        if official_lane_key in live_qualified
        else NEAR_MISS_INCUBATOR
        if official_lane_key in near_miss
        else "PAPER_ONLY"
    )
    direction_status = "live_qualified" if promotion_status == "live_qualified" else (
        "experimental_short" if direction == "short" else "unknown"
    )
    return {
        "execution_lane": official_lane_key,
        "lane_control_mode": mode or "unknown",
        "execution_lane_timeframe_status": timeframe_status,
        "execution_lane_promotion_status": promotion_status,
        "live_qualification_class": live_class,
        "execution_lane_direction_status": direction_status,
        "live_qualified_lanes": live_qualified,
        "historical_legacy_promoted_lanes": legacy_promoted,
        "near_miss_incubator_lanes": near_miss,
        "readiness_status": readiness_snapshot.get("readiness_status") or "UNKNOWN",
        "fisherman_warning": promotion_status != "live_qualified" or timeframe_status != "allowed_tiny_live",
        "operator_acceptance_required": promotion_status != "live_qualified",
    }


def summarize_final_console_risk_interpretation(
    *,
    latest_r262b: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    fresh_candidate_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    fresh_candidate_status = fresh_candidate_status or {}
    if fresh_candidate_status.get("trade_ticket_status") != "PROPOSED":
        return {
            "valid": False,
            "active_context": "no_current_proposed_ticket",
            "no_current_proposed_ticket": True,
            "blocked_by": ["no_current_proposed_ticket"],
            "previous_r264_preview_available": bool(latest_r262b),
            "order_placed": False,
            "real_order_placed": False,
            "submit_attempted": False,
            "binance_order_endpoint_called": False,
            "secrets_shown": False,
        }
    max_notional = _float_or_none(
        fresh_candidate_status.get("active_contract_max_notional_usdt")
        or fresh_candidate_status.get("max_position_usd")
    )
    leverage = _float_or_none(fresh_candidate_status.get("active_contract_leverage"))
    candidate_notional = _float_or_none(fresh_candidate_status.get("suggested_position_usd"))
    if max_notional is not None or leverage is not None or candidate_notional is not None:
        blocked = []
        if max_notional != 80.0:
            blocked.append("max_position_notional_not_80")
        if leverage != 10.0:
            blocked.append("leverage_not_10")
        if candidate_notional is None:
            blocked.append("candidate_notional_missing")
        elif candidate_notional > 80.0:
            blocked.append("candidate_notional_exceeds_80")
        return {
            "valid": not blocked,
            "active_context": "current_proposed_ticket",
            "lane_key": fresh_candidate_status.get("lane_key"),
            "symbol": fresh_candidate_status.get("symbol"),
            "timeframe": fresh_candidate_status.get("timeframe"),
            "direction": fresh_candidate_status.get("direction"),
            "tiny_live_contract_mode": fresh_candidate_status.get("active_contract_mode"),
            "max_position_notional_usdt": max_notional,
            "max_notional_usdt": max_notional,
            "leverage": leverage,
            "candidate_notional_usdt": candidate_notional,
            "candidate_qty": None,
            "derived_margin_budget_usdt": fresh_candidate_status.get("active_contract_margin_budget_usdt"),
            "blocked_by": blocked,
            "previous_r264_preview_available": bool(latest_r262b),
            "order_placed": False,
            "real_order_placed": False,
            "submit_attempted": False,
            "binance_order_endpoint_called": False,
            "secrets_shown": False,
        }
    existing = latest_r262b.get("risk_contract_interpretation")
    if isinstance(existing, Mapping) and existing:
        return _sanitize(dict(existing))
    sizing = latest_r262b.get("contract_fit_sizing_plan") if isinstance(latest_r262b.get("contract_fit_sizing_plan"), Mapping) else {}
    return build_tiny_live_risk_contract_validation_summary(
        risk_contract=risk_contract,
        candidate_qty=sizing.get("candidate_qty"),
        candidate_notional_usdt=sizing.get("candidate_notional_usdt"),
        candidate_estimated_loss_usdt=sizing.get("candidate_estimated_loss_usdt"),
        require_live_execution_enabled=False,
    )


def summarize_contract_fit_risk_interpretation(
    *, latest_r262b: Mapping[str, Any], risk_contract: Mapping[str, Any]
) -> dict[str, Any]:
    existing = latest_r262b.get("risk_contract_interpretation")
    if isinstance(existing, Mapping) and existing:
        return _sanitize(dict(existing))
    sizing = latest_r262b.get("contract_fit_sizing_plan") if isinstance(latest_r262b.get("contract_fit_sizing_plan"), Mapping) else {}
    return build_tiny_live_risk_contract_validation_summary(
        risk_contract=risk_contract,
        candidate_qty=sizing.get("candidate_qty"),
        candidate_notional_usdt=sizing.get("candidate_notional_usdt"),
        candidate_estimated_loss_usdt=sizing.get("candidate_estimated_loss_usdt"),
        require_live_execution_enabled=False,
    )


def summarize_contract_fit_panel(
    latest_r262b: Mapping[str, Any], *, risk_interpretation: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    model = latest_r262b.get("percentage_contract_model") if isinstance(latest_r262b.get("percentage_contract_model"), Mapping) else {}
    resolved = model.get("resolved_values") if isinstance(model.get("resolved_values"), Mapping) else {}
    intervention = latest_r262b.get("operator_intervention_model") if isinstance(latest_r262b.get("operator_intervention_model"), Mapping) else {}
    sizing = latest_r262b.get("contract_fit_sizing_plan") if isinstance(latest_r262b.get("contract_fit_sizing_plan"), Mapping) else {}
    validation = latest_r262b.get("output_validation") if isinstance(latest_r262b.get("output_validation"), Mapping) else {}
    r262b_found = bool(latest_r262b)
    risk_valid = (
        (risk_interpretation or {}).get("valid") is True
        and (
            validation.get("risk_contract_valid_after") is True
            or latest_r262b.get("contract_fit_matrix", {}).get("risk_contract_valid") is True
        )
    )
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
        "risk_contract_interpretation_valid": (risk_interpretation or {}).get("valid") is True,
        "risk_contract_blockers": list((risk_interpretation or {}).get("blocked_by") or []),
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
    shared_risk = build_tiny_live_risk_contract_validation_summary(
        risk_contract=risk_contract,
        require_live_execution_enabled=False,
    )
    controls_armed = state.get("official_lane_allowed") is True
    return {
        "official_lane_allowed": controls_armed,
        "live_execution_enabled": state.get("live_execution_enabled") is True,
        "kill_switch_allows_tiny_live": state.get("kill_switch_allows_tiny_live") is True,
        "controls_armed": controls_armed,
        "controls_arming_required": not controls_armed,
        "latest_controls_record_found": bool(latest_controls),
        "risk_contract_valid": shared_risk.get("valid") is True,
        "legacy_risk_contract_valid": risk_state.get("risk_contract_valid") is True or _risk_contract_limits_valid(risk_contract),
        "risk_contract_blockers": list(shared_risk.get("blocked_by") or []),
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
    if lane_context.get("execution_lane_promotion_status") != "live_qualified":
        warnings.append("execution lane is not current live-qualified")
    if lane_context.get("live_qualification_class") != LIVE_QUALIFIED:
        warnings.append("strategy_near_miss_not_live_eligible")
    if lane_context.get("execution_lane_direction_status") == "experimental_short":
        warnings.append("8m short is a manual experimental lane, not fisherman-promoted")
    if readiness_snapshot.get("readiness_status") == "NOT_READY":
        warnings.append("readiness is NOT_READY")
    return {
        "execution_lane": lane_context.get("execution_lane"),
        "execution_lane_timeframe_status": lane_context.get("execution_lane_timeframe_status") or "unknown",
        "execution_lane_promotion_status": lane_context.get("execution_lane_promotion_status") or "unknown",
        "live_qualification_class": lane_context.get("live_qualification_class") or "PAPER_ONLY",
        "execution_lane_direction_status": lane_context.get("execution_lane_direction_status") or "unknown",
        "live_qualified_lanes": _live_qualified_lanes(promotion_snapshot),
        "historical_legacy_promoted_lanes": _promotion_ready_lanes(promotion_snapshot),
        "promoted_lanes": [],
        "promoted_lanes_field_status": "deprecated_use_live_qualified_lanes_or_historical_legacy_promoted_lanes",
        "near_miss_incubator_lanes": _near_miss_lanes(promotion_snapshot),
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
        "promotion_ready_field_status": "legacy_historical_not_current_live_qualified",
        "live_qualified_lanes": list(promotion_snapshot.get("live_qualified_lanes") or []),
        "near_miss_incubator_lanes": list(promotion_snapshot.get("near_miss_incubator_lanes") or []),
        "qualified_candidate_watch": promotion_snapshot.get("qualified_candidate_watch")
        if isinstance(promotion_snapshot.get("qualified_candidate_watch"), Mapping)
        else {},
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
    if lane_intelligence_panel.get("live_qualification_class") != LIVE_QUALIFIED:
        blocked_by.append("strategy_near_miss_not_live_eligible")
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
    exchange_minimum_decision_packet: Mapping[str, Any] | None = None,
    no_current_ticket: bool = False,
) -> dict[str, Any]:
    r262b_valid = contract_fit_panel.get("r262b_found") and contract_fit_panel.get("risk_contract_valid") and contract_fit_panel.get("fits_contract")
    exchange_packet = exchange_minimum_decision_packet or {}
    exchange_minimum_blocks = exchange_packet.get("configured_cap_possible") is not True
    strategy_blocks = lane_intelligence_panel.get("live_qualification_class") != LIVE_QUALIFIED
    if no_current_ticket:
        next_step = "WAIT_FOR_LIVE_QUALIFIED_FRESH_CANDIDATE"
    elif exchange_minimum_blocks:
        next_step = "DECIDE_EXCHANGE_MINIMUM_TINY_LIVE_CONTRACT"
    elif strategy_blocks:
        next_step = "WAIT_FOR_LIVE_QUALIFIED_FRESH_CANDIDATE"
    elif not r262b_valid:
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
            not exchange_minimum_blocks
            and not strategy_blocks
            and r262b_valid
            and signed_triplet_panel.get("signed_triplet_available")
            and controls_panel.get("controls_armed")
        ),
        "go_for_controls_arming": bool(
            not exchange_minimum_blocks and not strategy_blocks and r262b_valid and not controls_panel.get("controls_armed")
        ),
        "operator_should_submit_now": False,
        "next_required_step": next_step,
        "exchange_minimum_blocks_submit": bool(exchange_minimum_blocks),
        "exchange_minimum_block_reason": exchange_packet.get("block_reason"),
        "strategy_blocks_submit": bool(strategy_blocks),
        "strategy_block_reason": "no_current_ticket" if no_current_ticket else "strategy_near_miss_not_live_eligible" if strategy_blocks else "",
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


def build_final_console_operator_access() -> dict[str, Any]:
    return {
        "same_desktop_url": "http://127.0.0.1:8015/operator/tiny-live/final-console",
        "ssh_tunnel_command": "ssh -N -L 8015:127.0.0.1:8015 masonshift-node",
        "remote_browser_url_after_tunnel": "http://127.0.0.1:8015/operator/tiny-live/final-console",
        "public_exposure_allowed": False,
        "keep_approval_api_localhost_only": True,
    }


def render_tiny_live_final_console_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tiny Live Final Console</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, Arial, sans-serif; background: #0a0c0f; color: #f3f6fb; }
    body { margin: 0; background: #0a0c0f; }
    header { padding: 18px 22px; border-bottom: 1px solid #2b3038; background: #10141a; }
    h1 { margin: 0; font-size: 26px; letter-spacing: 0; }
    main { padding: 14px; display: grid; gap: 12px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
    .panel { border: 1px solid #313843; border-radius: 8px; background: #121720; padding: 14px; }
    .danger { border-color: #8b1e2d; }
    .safe { border-color: #23794f; }
    .label { color: #97a3b6; font-size: 11px; text-transform: uppercase; font-weight: 800; }
    .value { font-weight: 850; overflow-wrap: anywhere; }
    .bad { color: #ff6673; }
    .ok { color: #3ddb8d; }
    .warn { color: #f7c65a; }
    .row { display: grid; grid-template-columns: minmax(110px, .7fr) minmax(0, 1.3fr); gap: 8px; padding: 6px 0; border-bottom: 1px solid #242a33; }
    button { min-height: 36px; border: 1px solid #3a4350; border-radius: 7px; background: #1a202b; color: #f3f6fb; font-weight: 850; cursor: pointer; }
    pre { white-space: pre-wrap; word-break: break-word; max-height: 360px; overflow: auto; background: #080a0d; border: 1px solid #242a33; border-radius: 7px; padding: 10px; }
  </style>
</head>
<body>
  <header>
    <h1>Tiny Live Final Console</h1>
      <div class="label">Read only · no live submit button · localhost/private tunnel only</div>
      <div class="label">R267: 80 USDT max notional, 10x visible leverage, derived margin about 8 USDT, no live submit command.</div>
      <div class="label">proper_tiny_live_below_exchange_minimum remains the blocker when the configured notional cap is smaller than the BTCUSDT minimum valid order.</div>
  </header>
  <main>
    <section id="summary" class="panel danger"></section>
    <section class="grid">
      <div id="risk" class="panel"></div>
      <div id="exchange" class="panel danger"></div>
      <div id="candidate" class="panel"></div>
      <div id="lanes" class="panel"></div>
      <div id="safety" class="panel"></div>
    </section>
    <section class="panel">
      <div class="label">Safe Diagnostic Commands</div>
      <button onclick="copyText('curl -s http://127.0.0.1:8015/tiny-live/final-console | jq .')">Copy JSON curl</button>
      <button id="copyExchangeCommand">Copy exchange-minimum check</button>
      <button onclick="copyText('ssh -N -L 8015:127.0.0.1:8015 masonshift-node')">Copy SSH tunnel</button>
      <pre id="access"></pre>
    </section>
    <section class="panel">
      <div class="label">Raw State</div>
      <pre id="raw">loading</pre>
    </section>
  </main>
  <script>
    function esc(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
    function row(label, value, cls='') { return `<div class="row"><div class="label">${esc(label)}</div><div class="value ${cls}">${esc(value)}</div></div>`; }
    function yn(value) { return value === true ? 'true' : 'false'; }
    function copyText(text) { navigator.clipboard.writeText(text || ''); }
    async function loadState() {
      const response = await fetch('/tiny-live/final-console');
      const data = await response.json();
      const readiness = data.promotion_readiness_panel || {};
      const lane = data.lane_intelligence_panel || {};
      const risk = data.risk_contract_interpretation || {};
      const r262b = data.contract_fit_panel || {};
      const r264 = data.latest_r264_dry_preview || {};
      const fresh = data.fresh_candidate_status || {};
      const jit = data.latest_jit_launch_packet || {};
      const command = data.final_live_submit_command_packet || {};
      const exchange = data.exchange_minimum_decision_packet || {};
      const go = data.final_console_go_no_go_packet || {};
      const blockers = [...(fresh.blocked_by || []), ...(risk.blocked_by || []), ...(readiness.readiness_blockers || []), ...(lane.warnings || [])];
      if (exchange.block_reason) blockers.unshift(exchange.block_reason);
      if (command.unavailable_reason) blockers.unshift(command.unavailable_reason);
      document.getElementById('copyExchangeCommand').onclick = () => copyText(exchange.safe_next_command || 'curl -s http://127.0.0.1:8015/tiny-live/final-console | jq .exchange_minimum_decision_packet');
      document.getElementById('summary').innerHTML = [
        row('go/no-go', go.go_for_actual_submit_now ? 'GO' : 'NO-GO', go.go_for_actual_submit_now ? 'ok' : 'bad'),
        row('readiness status', lane.readiness_status || 'UNKNOWN', lane.readiness_status === 'READY' ? 'ok' : 'bad'),
        row('trade-ticket status', data.trade_ticket_status || 'not loaded in read-only console'),
        row('fresh candidate', yn(data.fresh_candidate_available), data.fresh_candidate_available ? 'ok' : 'bad'),
        row('latest candidate age', readiness.latest_candidate_age_minutes ?? 'n/a'),
        row('final command available', yn(data.final_command_available), data.final_command_available ? 'ok' : 'bad'),
        row('blockers', blockers.length ? blockers.join('; ') : 'none', blockers.length ? 'bad' : 'ok')
      ].join('');
      document.getElementById('risk').innerHTML = [
        row('contract mode', risk.tiny_live_contract_mode),
        row('contract note', risk.forty_four_usdt_meaning),
        row('max notional', risk.max_position_notional_usdt),
        row('configured notional', risk.configured_max_position_notional_usdt),
        row('margin budget', risk.margin_budget_usdt),
        row('derived margin', risk.derived_margin_budget_usdt),
        row('leverage', risk.leverage),
        row('estimated loss', risk.candidate_estimated_loss_usdt),
        row('stop-distance loss', risk.stop_distance_loss_usdt),
        row('valid', yn(risk.valid), risk.valid ? 'ok' : 'bad')
      ].join('');
      document.getElementById('exchange').innerHTML = [
        row('exchange minimum reason', exchange.block_reason || 'none', exchange.block_reason ? 'bad' : 'ok'),
        row('configured cap', exchange.configured_proper_tiny_cap_usdt),
        row('min quantity', exchange.min_quantity),
        row('step size', exchange.step_size),
        row('min notional', exchange.min_notional),
        row('mark price', exchange.mark_price),
        row('minimum valid quantity', exchange.minimum_valid_quantity_after_rounding),
        row('exchange minimum notional', exchange.minimum_valid_notional_after_rounding),
        row('configured cap clears minimum', yn(exchange.configured_cap_clears_exchange_minimum), exchange.configured_cap_clears_exchange_minimum ? 'ok' : 'bad'),
        row('wallet funded context', exchange.wallet_funded_amount_usdt ?? 'unknown/not checked'),
        row('126 USDT enough', exchange.wallet_supports_exchange_minimum_tiny ?? 'unknown/not checked', exchange.wallet_supports_exchange_minimum_tiny === true ? 'ok' : 'warn'),
        row('recommended decision', exchange.recommended_operator_decision),
        row('recommended cap', exchange.recommended_cap_usdt ?? 'none'),
        row('cap applied', yn(exchange.recommended_cap_applied), exchange.recommended_cap_applied ? 'bad' : 'ok')
      ].join('');
      document.getElementById('candidate').innerHTML = [
        row('R262B found', yn(r262b.r262b_found)),
        row('R262B valid', yn(r262b.risk_contract_valid), r262b.risk_contract_valid ? 'ok' : 'bad'),
        row('R263 armed', yn(data.final_console_controls_armed || (data.controls_panel || {}).controls_armed)),
        row('R264 dry preview valid', yn(r264.valid), r264.valid ? 'ok' : 'bad'),
        row('R271 unlock packet found', yn(jit.found), jit.found ? 'ok' : 'bad'),
        row('fresh ticket signal', fresh.signal_id || 'n/a'),
        row('fresh ticket status', fresh.trade_ticket_status || 'BLOCKED', fresh.trade_ticket_status === 'PROPOSED' ? 'ok' : 'bad'),
        row('fresh ticket notional cap', fresh.max_position_usd ?? 'n/a'),
        row('fresh ticket suggested position', fresh.suggested_position_usd ?? 'n/a'),
        row('fresh ticket leverage', fresh.suggested_leverage ?? 'n/a'),
        row('manual command available', yn(command.available), command.available ? 'ok' : 'bad'),
        row('unlock phrase exact', yn(command.unlock_confirmation_valid), command.unlock_confirmation_valid ? 'ok' : 'bad'),
        row('signed triplet fresh', yn(jit.signed_triplet_fresh), jit.signed_triplet_fresh ? 'ok' : 'bad'),
        row('candidate qty', r262b.candidate_qty),
        row('candidate notional', r262b.candidate_notional_usdt)
      ].join('');
      document.getElementById('lanes').innerHTML = [
        row('selected lane', lane.execution_lane),
        row('promoted lanes', (lane.promoted_lanes || []).join('; ') || 'none'),
        row('timeframe status', lane.execution_lane_timeframe_status),
        row('promotion status', lane.execution_lane_promotion_status),
        row('fresh eligible count', lane.fresh_eligible_count)
      ].join('');
      document.getElementById('safety').innerHTML = [
        row('order placed', yn(data.order_placed), 'ok'),
        row('real order placed', yn(data.real_order_placed), 'ok'),
        row('submit attempted', yn(data.submit_attempted), 'ok'),
        row('Binance order endpoint called', yn(data.binance_order_endpoint_called), 'ok'),
        row('Binance test order endpoint called', yn(data.binance_test_order_endpoint_called), 'ok'),
        row('secrets shown', yn(data.secrets_shown), 'ok'),
        row('submit allowed', yn((data.final_console_matrix || {}).submit_allowed), 'ok')
      ].join('');
      document.getElementById('access').textContent = JSON.stringify(data.operator_access || {}, null, 2);
      document.getElementById('raw').textContent = JSON.stringify(data, null, 2);
    }
    loadState();
    setInterval(loadState, 10000);
  </script>
</body>
</html>"""


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
    exchange_minimum_decision_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blocked = list(blocked_by)
    exchange_packet = exchange_minimum_decision_packet or {}
    if exchange_packet.get("configured_cap_possible") is not True:
        blocked.append(str(exchange_packet.get("block_reason") or "exchange_minimum_decision_missing"))
    if not contract_fit_panel.get("r262b_found"):
        blocked.append("missing_r262b")
    if not contract_fit_panel.get("risk_contract_valid"):
        blocked.append("risk_contract_invalid")
    if lane_intelligence_panel.get("operator_acceptance_required") and not experimental_lane_acceptance_recorded:
        blocked.append("experimental_lane_acceptance_required")
    if lane_intelligence_panel.get("live_qualification_class") != LIVE_QUALIFIED:
        blocked.append("strategy_near_miss_not_live_eligible")
    return {
        "r262b_valid": contract_fit_panel.get("r262b_found") is True and contract_fit_panel.get("fits_contract") is True,
        "signed_triplet_available": signed_triplet_panel.get("signed_triplet_available") is True,
        "risk_contract_valid": contract_fit_panel.get("risk_contract_valid") is True,
        "lane_intelligence_loaded": bool(lane_intelligence_panel.get("execution_lane")),
        "experimental_lane_acceptance_required": lane_intelligence_panel.get("operator_acceptance_required") is True,
        "experimental_lane_acceptance_recorded": bool(experimental_lane_acceptance_recorded),
        "live_qualification_class": lane_intelligence_panel.get("live_qualification_class") or "PAPER_ONLY",
        "controls_armed": controls_panel.get("controls_armed") is True,
        "exchange_minimum_cap_possible": exchange_packet.get("configured_cap_possible") is True,
        "exchange_minimum_block_reason": exchange_packet.get("block_reason"),
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
    if step == "DECIDE_EXCHANGE_MINIMUM_TINY_LIVE_CONTRACT":
        return "Review the exchange-minimum decision packet; keep NO-GO until an operator-approved cap decision is applied in a later safe phase."
    if step == "R264_ACTUAL_SUBMIT_CHECKPOINT":
        return "Proceed only to the R264 actual submit checkpoint; do not submit from R263."
    if step == "WAIT_FOR_LIVE_QUALIFIED_FRESH_CANDIDATE":
        return "WAIT_FOR_LIVE_QUALIFIED_FRESH_CANDIDATE: wait for a fresh LIVE_QUALIFIED candidate; near-miss lanes remain incubator/watchlist only."
    if step == "ARM_CONTROLS":
        return "Use the exact R263 controls arming phrase only if accepting the 8m short experimental lane."
    if step == "RERUN_R262B":
        return "Rerun R262B contract-fit triplet before using this console."
    if step == "WAIT_FOR_FRESH_CANDIDATE":
        return "Wait for a fresh eligible tiny-live candidate or switch lane in a later phase."
    return "Review the final console; actual submit remains forbidden."


def _recommended_next_engineering_move(packet: Mapping[str, Any], overall: str) -> str:
    if packet.get("next_required_step") == "DECIDE_EXCHANGE_MINIMUM_TINY_LIVE_CONTRACT":
        return "Keep final submit unavailable; add only an explicit operator decision/write phase if the exchange-minimum cap is accepted."
    if packet.get("next_required_step") == "R264_ACTUAL_SUBMIT_CHECKPOINT":
        return "Build/run R264 with R263 armed-state, R262B contract-fit, exact submit phrase, idempotency, and reconciliation checks."
    if packet.get("next_required_step") == "WAIT_FOR_LIVE_QUALIFIED_FRESH_CANDIDATE":
        return "Keep final command unavailable; route near-miss lanes to Strategy Lab paper work."
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


def _live_qualified_lanes(snapshot: Mapping[str, Any]) -> list[str]:
    lanes: list[str] = []
    for key in ("live_qualified_lanes",):
        for row in snapshot.get(key) or []:
            if not isinstance(row, Mapping):
                continue
            lane = row.get("strategy_key") or _lane_key_from_row(row)
            if lane:
                lanes.append(str(lane))
    watch = snapshot.get("qualified_candidate_watch")
    if isinstance(watch, Mapping):
        for row in watch.get("live_qualified_lanes") or []:
            if not isinstance(row, Mapping):
                continue
            lane = row.get("strategy_key") or _lane_key_from_row(row)
            if lane:
                lanes.append(str(lane))
    return _dedupe(lanes)


def _near_miss_lanes(snapshot: Mapping[str, Any]) -> list[str]:
    lanes: list[str] = []
    for key in ("near_miss_incubator_lanes",):
        for row in snapshot.get(key) or []:
            if not isinstance(row, Mapping):
                continue
            lane = row.get("strategy_key") or _lane_key_from_row(row)
            if lane:
                lanes.append(str(lane))
    watch = snapshot.get("qualified_candidate_watch")
    if isinstance(watch, Mapping):
        for row in watch.get("near_miss_incubator_lanes") or []:
            if not isinstance(row, Mapping):
                continue
            lane = row.get("strategy_key") or _lane_key_from_row(row)
            if lane:
                lanes.append(str(lane))
    return _dedupe(lanes)


def _risk_contract_limits_valid(risk_contract: Mapping[str, Any]) -> bool:
    contract = risk_contract.get("contract") if isinstance(risk_contract.get("contract"), Mapping) else {}
    if not contract:
        return False
    return bool(
        contract.get("symbol") == "BTCUSDT"
        and contract.get("timeframe") == "8m"
        and contract.get("direction") == "short"
        and contract.get("tiny_live_contract_mode") == "explicit_notional_cap_with_leverage"
        and (_float_or_none(contract.get("tiny_live_margin_usdt") or contract.get("margin_budget_usdt")) or 0) <= 8.0
        and (_float_or_none(contract.get("max_loss_usdt")) or 0) <= 4.44
        and (_float_or_none(contract.get("max_notional_usdt") or contract.get("max_position_notional_usdt")) or 0) <= 80.0
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


def expected_orders_for_direction(direction: str) -> dict[str, str]:
    if str(direction or "").lower() == "long":
        main_side = "BUY"
        exit_side = "SELL"
    else:
        main_side = "SELL"
        exit_side = "BUY"
    return {
        "main": f"{main_side} MARKET quantity must remain within 80 USDT notional cap",
        "stop": f"{exit_side} STOP_MARKET REDUCE_ONLY",
        "take_profit": f"{exit_side} TAKE_PROFIT_MARKET REDUCE_ONLY",
    }


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
