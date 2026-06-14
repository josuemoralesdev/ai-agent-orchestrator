"""R261 tiny-live controls arming review surface.

This module builds a local operator review packet for tiny-live lane controls.
It may append R261 review/arming ledgers, and it may update only the official
lane row in lane_controls.json after the exact arming phrase. It never signs,
submits, calls Binance/network, writes risk contracts, or places orders.
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
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import (
    DEFAULT_OFFICIAL_TINY_LIVE_LANE,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, normalize_lane_key
from src.app.hammer_radar.operator.tiny_live_actual_submit_gate import (
    LANE_CONTROLS_PATH,
    RISK_CONTRACT_CONFIG_PATH,
    validate_tiny_live_risk_contract_still_within_bounds,
)

TINY_LIVE_CONTROLS_REVIEW_READY = "TINY_LIVE_CONTROLS_REVIEW_READY"
TINY_LIVE_CONTROLS_REVIEW_RECORDED = "TINY_LIVE_CONTROLS_REVIEW_RECORDED"
TINY_LIVE_CONTROLS_ARMING_RECORDED = "TINY_LIVE_CONTROLS_ARMING_RECORDED"
TINY_LIVE_CONTROLS_ARMING_REJECTED = "TINY_LIVE_CONTROLS_ARMING_REJECTED"
TINY_LIVE_CONTROLS_ARMING_BLOCKED = "TINY_LIVE_CONTROLS_ARMING_BLOCKED"
TINY_LIVE_CONTROLS_ARMING_ERROR = "TINY_LIVE_CONTROLS_ARMING_ERROR"

TINY_LIVE_CONTROLS_READY_FOR_REVIEW = "TINY_LIVE_CONTROLS_READY_FOR_REVIEW"
TINY_LIVE_CONTROLS_REVIEW_RECORDED_ARMING_REQUIRED = (
    "TINY_LIVE_CONTROLS_REVIEW_RECORDED_ARMING_REQUIRED"
)
TINY_LIVE_CONTROLS_ARMED_R262_FINAL_CONSOLE_REQUIRED = (
    "TINY_LIVE_CONTROLS_ARMED_R262_FINAL_CONSOLE_REQUIRED"
)
TINY_LIVE_CONTROLS_ARMING_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_CONTROLS_ARMING_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_CONTROLS_ARMING_BLOCKED_BY_RISK_CONTRACT = (
    "TINY_LIVE_CONTROLS_ARMING_BLOCKED_BY_RISK_CONTRACT"
)
TINY_LIVE_CONTROLS_ARMING_BLOCKED_BY_MISSING_R260 = (
    "TINY_LIVE_CONTROLS_ARMING_BLOCKED_BY_MISSING_R260"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE_REVIEW = "TINY_LIVE_CONTROLS_REVIEW"
EVENT_TYPE_ARMING = "TINY_LIVE_CONTROLS_ARMING"
LEDGER_FILENAME = "tiny_live_controls_arming.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R261_TINY_LIVE_CONTROLS_ARMING_UI_AND_API"
REVIEW_CONFIRMATION_PHRASE = (
    "I CONFIRM TINY LIVE CONTROLS REVIEW RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
)
ARMING_CONFIRMATION_PHRASE = (
    "I CONFIRM ARM TINY LIVE CONTROLS FOR BTCUSDT 8M SHORT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
)

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_fresh_cycle_one_shot.ndjson",
    "logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_controls_review(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    record_controls_review: bool = False,
    confirm_tiny_live_controls_review: str | None = None,
    arm_tiny_live_controls: bool = False,
    confirm_arm_tiny_live_controls: str | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    lane_path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    review_confirmation_valid = confirm_tiny_live_controls_review == REVIEW_CONFIRMATION_PHRASE
    arming_confirmation_valid = confirm_arm_tiny_live_controls == ARMING_CONFIRMATION_PHRASE
    confirmation_valid = bool(
        (record_controls_review and review_confirmation_valid)
        or (arm_tiny_live_controls and arming_confirmation_valid)
    )
    symbol, timeframe, direction, _entry_mode = _lane_parts(official_lane_key)

    try:
        latest_r260 = load_latest_tiny_live_fresh_cycle_one_shot(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r255 = load_latest_tiny_live_actual_submit_gate(
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
        input_summary = {
            "r260_one_shot_found": bool(latest_r260),
            "r260_one_shot_valid": _r260_valid(latest_r260),
            "r255_dry_preview_found": bool(latest_r255),
            "lane_controls_found": bool(lane_controls.get("found")),
            "risk_contract_found": bool(risk_contract.get("found")),
        }
        controls_state = summarize_tiny_live_controls_state(
            lane_controls=lane_controls,
            risk_contract=risk_contract,
        )
        risk_contract_state = summarize_tiny_live_risk_contract_state(
            risk_contract=risk_contract,
            latest_r255=latest_r255,
            risk_contract_config_path=risk_path,
            official_lane_key=official_lane_key,
        )
        freshness_state = summarize_tiny_live_freshness_state(
            latest_r260=latest_r260,
            latest_r255=latest_r255,
        )
        packet = build_tiny_live_controls_review_packet(
            input_summary=input_summary,
            controls_state=controls_state,
            risk_contract_state=risk_contract_state,
            freshness_state=freshness_state,
        )
        arming_plan = build_tiny_live_controls_arming_plan(
            controls_state=controls_state,
            risk_contract_state=risk_contract_state,
            input_summary=input_summary,
            arm_requested=arm_tiny_live_controls,
        )
        validation = validate_tiny_live_controls_arming_request(
            arm_tiny_live_controls=arm_tiny_live_controls,
            confirmation_valid=arming_confirmation_valid,
            input_summary=input_summary,
            risk_contract_state=risk_contract_state,
            official_lane_key=official_lane_key,
        )
        arming_result = {
            "attempted": bool(arm_tiny_live_controls),
            "succeeded": False,
            "blocked_by": list(validation.get("blocked_by") or []),
            "lane_controls_written": False,
            "before": {},
            "after": {},
        }
        controls_review_recorded = False
        controls_arming_recorded = False
        safety = _safety(lane_controls_written=False)

        if record_controls_review and review_confirmation_valid:
            controls_review_recorded = True
        if arm_tiny_live_controls and arming_confirmation_valid and validation["valid"]:
            arming_result = apply_tiny_live_controls_arming_request(
                lane_controls_path=lane_path,
                official_lane_key=official_lane_key,
                operator_id=operator_id,
                reason=reason,
                now=generated_at,
            )
            controls_arming_recorded = arming_result["succeeded"]
            safety = _safety(lane_controls_written=controls_arming_recorded)
            if controls_arming_recorded:
                lane_controls = load_tiny_live_lane_controls(
                    lane_controls_path=lane_path,
                    official_lane_key=official_lane_key,
                )
                controls_state = summarize_tiny_live_controls_state(
                    lane_controls=lane_controls,
                    risk_contract=risk_contract,
                    armed_by_this_phase=True,
                )
                packet = build_tiny_live_controls_review_packet(
                    input_summary=input_summary,
                    controls_state=controls_state,
                    risk_contract_state=risk_contract_state,
                    freshness_state=freshness_state,
                )

        matrix = _build_controls_arming_matrix(
            input_summary=input_summary,
            controls_state=controls_state,
            risk_contract_state=risk_contract_state,
            freshness_state=freshness_state,
            record_confirmed=review_confirmation_valid,
            review_recorded=controls_review_recorded,
            arming_recorded=controls_arming_recorded,
            blocked_by=arming_result["blocked_by"],
        )
        overall = classify_tiny_live_controls_arming_status(
            arm_requested=arm_tiny_live_controls,
            record_requested=record_controls_review,
            arming_confirmation_valid=arming_confirmation_valid,
            input_summary=input_summary,
            risk_contract_state=risk_contract_state,
            controls_arming_recorded=controls_arming_recorded,
            controls_review_recorded=controls_review_recorded,
        )
        status = classify_tiny_live_controls_review_status(
            record_requested=record_controls_review,
            arm_requested=arm_tiny_live_controls,
            review_confirmation_valid=review_confirmation_valid,
            arming_confirmation_valid=arming_confirmation_valid,
            controls_review_recorded=controls_review_recorded,
            controls_arming_recorded=controls_arming_recorded,
            blocked_by=arming_result["blocked_by"],
        )
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "record_controls_review_requested": bool(record_controls_review),
                "arm_tiny_live_controls_requested": bool(arm_tiny_live_controls),
                "confirmation_valid": bool(confirmation_valid),
                "controls_review_recorded": bool(controls_review_recorded),
                "controls_arming_recorded": bool(controls_arming_recorded),
                "operator_intent": {
                    "operator_id": str(operator_id or "local_operator"),
                    "reason": str(reason or ""),
                    "source_phase": "R261",
                },
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "controls_arming_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "controls_state": controls_state,
                "risk_contract_state": risk_contract_state,
                "freshness_state": freshness_state,
                "controls_review_packet": packet,
                "arming_plan": arming_plan,
                "arming_result": arming_result,
                "controls_arming_matrix": matrix,
                "controls_arming_overall_status": overall,
                "recommended_next_operator_move": _recommended_next_operator_move(packet, overall),
                "recommended_next_engineering_move": _recommended_next_engineering_move(packet, overall),
                "do_not_run_yet": [
                    "real submit from R261",
                    "real submit before R262 console",
                    "real submit while risk contract invalid",
                    "duplicate live submit",
                ],
                "safety": safety,
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if controls_review_recorded:
            append_tiny_live_controls_review_record(
                payload,
                log_dir=resolved_log_dir,
                confirm_tiny_live_controls_review=confirm_tiny_live_controls_review,
            )
        if controls_arming_recorded:
            append_tiny_live_controls_arming_record(
                payload,
                log_dir=resolved_log_dir,
                confirm_arm_tiny_live_controls=confirm_arm_tiny_live_controls,
            )
        return payload
    except Exception as exc:  # pragma: no cover - defensive JSON surface
        return _sanitize(
            {
                "status": TINY_LIVE_CONTROLS_ARMING_ERROR,
                "generated_at": generated_at.isoformat(),
                "record_controls_review_requested": bool(record_controls_review),
                "arm_tiny_live_controls_requested": bool(arm_tiny_live_controls),
                "confirmation_valid": False,
                "controls_review_recorded": False,
                "controls_arming_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "controls_arming_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "error": str(exc),
                "safety": _safety(lane_controls_written=False),
            }
        )


def load_latest_tiny_live_fresh_cycle_one_shot(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in _load_ndjson(Path(get_log_dir(log_dir, use_env=True)) / "tiny_live_fresh_cycle_one_shot.ndjson"):
        if _record_lane(record) == official_lane_key:
            return record
    return {}


def load_latest_tiny_live_actual_submit_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in _load_ndjson(Path(get_log_dir(log_dir, use_env=True)) / "tiny_live_actual_submit_gate.ndjson"):
        if _record_lane(record) == official_lane_key:
            return record
    return {}


def load_tiny_live_lane_controls(
    *,
    lane_controls_path: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    if not path.exists():
        return {"found": False, "path": str(path), "raw": {}, "official_lane": {}}
    raw = json.loads(path.read_text(encoding="utf-8"))
    lane = _matching_lane(raw, official_lane_key)
    return {
        "found": True,
        "path": str(path),
        "raw": raw,
        "official_lane": lane,
        "official_lane_found": bool(lane),
    }


def load_tiny_live_risk_contract(
    *,
    risk_contract_config_path: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    if not path.exists():
        return {"found": False, "path": str(path), "contract": {}}
    raw = json.loads(path.read_text(encoding="utf-8"))
    contract = _matching_contract(raw, official_lane_key)
    return {
        "found": True,
        "path": str(path),
        "raw": raw,
        "contract": contract,
        "official_contract_found": bool(contract),
    }


def summarize_tiny_live_controls_state(
    *,
    lane_controls: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    armed_by_this_phase: bool = False,
) -> dict[str, Any]:
    lane = lane_controls.get("official_lane") if isinstance(lane_controls.get("official_lane"), Mapping) else {}
    contract = risk_contract.get("contract") if isinstance(risk_contract.get("contract"), Mapping) else {}
    official_lane_allowed = str(lane.get("mode") or "").strip().lower() == "tiny_live"
    live_execution_enabled = contract.get("live_execution_enabled") is True
    return {
        "official_lane_allowed": bool(official_lane_allowed),
        "live_execution_enabled": bool(live_execution_enabled),
        "kill_switch_allows_tiny_live": bool(official_lane_allowed and live_execution_enabled),
        "manual_arming_required": not official_lane_allowed,
        "armed_by_this_phase": bool(armed_by_this_phase),
    }


def summarize_tiny_live_risk_contract_state(
    *,
    risk_contract: Mapping[str, Any],
    latest_r255: Mapping[str, Any] | None = None,
    risk_contract_config_path: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    contract = risk_contract.get("contract") if isinstance(risk_contract.get("contract"), Mapping) else {}
    submit_summary = (
        (latest_r255 or {}).get("risk_contract_submit_summary")
        if isinstance((latest_r255 or {}).get("risk_contract_submit_summary"), Mapping)
        else {}
    )
    validation = {}
    triplet = (latest_r255 or {}).get("actual_submit_dry_run_preview", {}).get("orders") if latest_r255 else {}
    if isinstance(triplet, Mapping):
        validation = validate_tiny_live_risk_contract_still_within_bounds(
            risk_contract_config_path=risk_contract_config_path,
            order_triplet={
                "main_order": triplet.get("main_order", {}),
                "stop_order": triplet.get("stop_order", {}),
                "take_profit_order": triplet.get("take_profit_order", {}),
            },
            official_lane_key=official_lane_key,
        )
    invalid_reasons: list[str] = []
    found = bool(risk_contract.get("found") and contract)
    if not found:
        invalid_reasons.append("risk_contract_missing")
    if found and contract.get("symbol") != "BTCUSDT":
        invalid_reasons.append("risk_contract_symbol_not_BTCUSDT")
    if found and contract.get("timeframe") != "8m":
        invalid_reasons.append("risk_contract_timeframe_not_8m")
    if found and contract.get("direction") != "short":
        invalid_reasons.append("risk_contract_direction_not_short")
    if found and (validation.get("within_tiny_live_contract") is False or submit_summary.get("within_tiny_live_contract") is False):
        invalid_reasons.append("risk_contract_invalid")
    valid = bool(found and not invalid_reasons)
    return {
        "risk_contract_found": found,
        "risk_contract_valid": valid,
        "risk_contract_invalid_reasons": _dedupe(invalid_reasons),
        "tiny_live_margin_budget_usdt": contract.get("tiny_live_margin_usdt")
        or contract.get("margin_budget_usdt"),
        "tiny_live_max_notional_usdt": contract.get("max_notional_usdt")
        or contract.get("max_position_notional_usdt"),
        "tiny_live_max_loss_usdt": contract.get("max_loss_usdt"),
        "leverage": contract.get("leverage"),
    }


def summarize_tiny_live_freshness_state(
    *, latest_r260: Mapping[str, Any], latest_r255: Mapping[str, Any]
) -> dict[str, Any]:
    validation = latest_r260.get("one_shot_output_validation") if isinstance(latest_r260.get("one_shot_output_validation"), Mapping) else {}
    freshness = latest_r255.get("signed_request_freshness") if isinstance(latest_r255.get("signed_request_freshness"), Mapping) else {}
    return {
        "fresh_cycle_valid": validation.get("valid") is True,
        "fresh_signed_request_available": validation.get("fresh_signed_request_available") is True,
        "signed_request_fresh_enough_for_dry_preview": (
            validation.get("signed_request_fresh_enough_for_dry_preview") is True
            or freshness.get("fresh_enough_for_real_submit") is True
        ),
        "dry_preview_recorded": bool(latest_r255.get("actual_submit_gate_record_id")),
    }


def build_tiny_live_controls_review_packet(
    *,
    input_summary: Mapping[str, Any],
    controls_state: Mapping[str, Any],
    risk_contract_state: Mapping[str, Any],
    freshness_state: Mapping[str, Any],
) -> dict[str, Any]:
    if not input_summary.get("r260_one_shot_found"):
        next_step = "RERUN_R260"
    elif not risk_contract_state.get("risk_contract_valid"):
        next_step = "FIX_RISK_CONTRACT"
    elif not controls_state.get("official_lane_allowed"):
        next_step = "ARM_CONTROLS"
    elif controls_state.get("official_lane_allowed"):
        next_step = "R262_FINAL_SUBMIT_CONSOLE"
    else:
        next_step = "WAIT"
    return {
        "submit_still_forbidden": True,
        "operator_should_submit_now": False,
        "operator_should_review_risk_contract": not risk_contract_state.get("risk_contract_valid"),
        "operator_should_arm_controls": next_step == "ARM_CONTROLS",
        "operator_should_open_r262_console_next": next_step == "R262_FINAL_SUBMIT_CONSOLE",
        "next_required_step": next_step,
    }


def build_tiny_live_controls_arming_plan(
    *,
    controls_state: Mapping[str, Any],
    risk_contract_state: Mapping[str, Any],
    input_summary: Mapping[str, Any],
    arm_requested: bool,
) -> dict[str, Any]:
    will_write = bool(
        arm_requested
        and input_summary.get("r260_one_shot_found")
        and risk_contract_state.get("risk_contract_valid")
        and not controls_state.get("official_lane_allowed")
    )
    return {
        "will_write_lane_controls": will_write,
        "will_change_official_lane_only": will_write,
        "will_enable_live_execution": False,
        "will_disable_kill_switch": False,
        "will_submit": False,
        "will_place_order": False,
    }


def validate_tiny_live_controls_arming_request(
    *,
    arm_tiny_live_controls: bool,
    confirmation_valid: bool,
    input_summary: Mapping[str, Any],
    risk_contract_state: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    blocked_by: list[str] = []
    if not arm_tiny_live_controls:
        return {"valid": False, "blocked_by": []}
    if not confirmation_valid:
        blocked_by.append("bad_confirmation")
    if official_lane_key != OFFICIAL_LANE_KEY:
        blocked_by.append("official_lane_change_forbidden")
    if not input_summary.get("r260_one_shot_found"):
        blocked_by.append("missing_r260")
    if not input_summary.get("r260_one_shot_valid"):
        blocked_by.append("r260_one_shot_invalid")
    if not risk_contract_state.get("risk_contract_valid"):
        blocked_by.append("risk_contract_invalid")
    return {"valid": not blocked_by, "blocked_by": _dedupe(blocked_by)}


def apply_tiny_live_controls_arming_request(
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
        return {
            "attempted": True,
            "succeeded": False,
            "blocked_by": ["lane_controls_schema_missing_lanes"],
            "lane_controls_written": False,
            "before": {},
            "after": {},
        }
    for lane in lanes:
        if isinstance(lane, dict) and _lane_key_from_row(lane) == official_lane_key:
            before = deepcopy(lane)
            lane["mode"] = "tiny_live"
            lane["tiny_live_armed_by_phase"] = "R261"
            lane["tiny_live_armed_at_utc"] = generated_at.isoformat()
            lane["tiny_live_armed_by_operator_id"] = str(operator_id or "local_operator")
            lane["tiny_live_arming_reason"] = str(reason or "")
            after = deepcopy(lane)
            path.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return {
                "attempted": True,
                "succeeded": True,
                "blocked_by": [],
                "lane_controls_written": True,
                "before": before,
                "after": after,
            }
    return {
        "attempted": True,
        "succeeded": False,
        "blocked_by": ["official_lane_missing"],
        "lane_controls_written": False,
        "before": {},
        "after": {},
    }


def append_tiny_live_controls_review_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_tiny_live_controls_review: str | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_controls_review != REVIEW_CONFIRMATION_PHRASE:
        raise ValueError("bad_tiny_live_controls_review_confirmation")
    return _append_record(
        record,
        log_dir=log_dir,
        event_type=EVENT_TYPE_REVIEW,
        record_id_key="controls_review_record_id",
        record_id_prefix="r261_controls_review",
    )


def append_tiny_live_controls_arming_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_arm_tiny_live_controls: str | None = None,
) -> dict[str, Any]:
    if confirm_arm_tiny_live_controls != ARMING_CONFIRMATION_PHRASE:
        raise ValueError("bad_tiny_live_controls_arming_confirmation")
    return _append_record(
        record,
        log_dir=log_dir,
        event_type=EVENT_TYPE_ARMING,
        record_id_key="controls_arming_record_id",
        record_id_prefix="r261_controls_arming",
    )


def load_tiny_live_controls_arming_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_controls_arming_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def classify_tiny_live_controls_review_status(
    *,
    record_requested: bool,
    arm_requested: bool,
    review_confirmation_valid: bool,
    arming_confirmation_valid: bool,
    controls_review_recorded: bool,
    controls_arming_recorded: bool,
    blocked_by: Sequence[str],
) -> str:
    if record_requested and not review_confirmation_valid:
        return TINY_LIVE_CONTROLS_ARMING_REJECTED
    if arm_requested and not arming_confirmation_valid:
        return TINY_LIVE_CONTROLS_ARMING_REJECTED
    if controls_arming_recorded:
        return TINY_LIVE_CONTROLS_ARMING_RECORDED
    if arm_requested and blocked_by:
        return TINY_LIVE_CONTROLS_ARMING_BLOCKED
    if controls_review_recorded:
        return TINY_LIVE_CONTROLS_REVIEW_RECORDED
    return TINY_LIVE_CONTROLS_REVIEW_READY


def classify_tiny_live_controls_arming_status(
    *,
    arm_requested: bool,
    record_requested: bool,
    arming_confirmation_valid: bool,
    input_summary: Mapping[str, Any],
    risk_contract_state: Mapping[str, Any],
    controls_arming_recorded: bool,
    controls_review_recorded: bool,
) -> str:
    if arm_requested and not arming_confirmation_valid:
        return TINY_LIVE_CONTROLS_ARMING_REJECTED_BAD_CONFIRMATION
    if not input_summary.get("r260_one_shot_found"):
        return TINY_LIVE_CONTROLS_ARMING_BLOCKED_BY_MISSING_R260
    if not risk_contract_state.get("risk_contract_valid"):
        return TINY_LIVE_CONTROLS_ARMING_BLOCKED_BY_RISK_CONTRACT
    if controls_arming_recorded:
        return TINY_LIVE_CONTROLS_ARMED_R262_FINAL_CONSOLE_REQUIRED
    if controls_review_recorded or record_requested:
        return TINY_LIVE_CONTROLS_REVIEW_RECORDED_ARMING_REQUIRED
    return TINY_LIVE_CONTROLS_READY_FOR_REVIEW


def format_tiny_live_controls_arming_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def tiny_live_controls_arming_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _append_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None,
    event_type: str,
    record_id_key: str,
    record_id_prefix: str,
) -> dict[str, Any]:
    path = tiny_live_controls_arming_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": event_type,
            record_id_key: record.get(record_id_key) or f"{record_id_prefix}_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "created_by_phase": CREATED_BY_PHASE,
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def _build_controls_arming_matrix(
    *,
    input_summary: Mapping[str, Any],
    controls_state: Mapping[str, Any],
    risk_contract_state: Mapping[str, Any],
    freshness_state: Mapping[str, Any],
    record_confirmed: bool,
    review_recorded: bool,
    arming_recorded: bool,
    blocked_by: Sequence[str],
) -> dict[str, Any]:
    return {
        "r260_available": input_summary.get("r260_one_shot_found") is True,
        "risk_contract_valid": risk_contract_state.get("risk_contract_valid") is True,
        "fresh_cycle_valid": freshness_state.get("fresh_cycle_valid") is True,
        "official_lane_allowed": controls_state.get("official_lane_allowed") is True,
        "live_execution_enabled": controls_state.get("live_execution_enabled") is True,
        "kill_switch_allows_tiny_live": controls_state.get("kill_switch_allows_tiny_live") is True,
        "record_confirmed": bool(record_confirmed),
        "review_recorded": bool(review_recorded),
        "arming_recorded": bool(arming_recorded),
        "submit_allowed": False,
        "order_placed": False,
        "blocked_by": _dedupe(list(blocked_by)),
    }


def _safety(*, lane_controls_written: bool) -> dict[str, Any]:
    return {
        **SAFETY_FALSE,
        "env_written": False,
        "env_mutated": False,
        "external_env_file_written": False,
        "config_written": bool(lane_controls_written),
        "risk_contract_config_written": False,
        "lane_controls_written": bool(lane_controls_written),
        "live_config_written": False,
        "controls_arming_only": True,
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
        "official_tiny_live_lane_armed": bool(lane_controls_written),
    }


def _recommended_next_operator_move(packet: Mapping[str, Any], overall: str) -> str:
    if overall == TINY_LIVE_CONTROLS_ARMED_R262_FINAL_CONSOLE_REQUIRED:
        return "Open R262 final submit console; do not submit from R261."
    step = packet.get("next_required_step")
    if step == "FIX_RISK_CONTRACT":
        return "Review and fix the tiny-live risk contract before arming controls."
    if step == "ARM_CONTROLS":
        return "Use the exact R261 arming confirmation only if operator intent is final."
    if step == "RERUN_R260":
        return "Rerun R260 fresh cycle before controls review."
    return "Review the R261 controls packet; submit remains forbidden."


def _recommended_next_engineering_move(packet: Mapping[str, Any], overall: str) -> str:
    if overall == TINY_LIVE_CONTROLS_ARMED_R262_FINAL_CONSOLE_REQUIRED:
        return "Build/run R262 final submit console; no auto-submit by default."
    if packet.get("next_required_step") == "FIX_RISK_CONTRACT":
        return "Resolve risk contract invalid visibility/fix path before R262."
    return "Keep R262 final submit console blocked until controls and risk contract are ready."


def _r260_valid(record: Mapping[str, Any]) -> bool:
    validation = record.get("one_shot_output_validation") if isinstance(record.get("one_shot_output_validation"), Mapping) else {}
    return bool(
        validation.get("valid") is True
        and validation.get("fresh_signed_request_available") is True
        and validation.get("signed_request_fresh_enough_for_dry_preview") is True
    )


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=50, max_bytes=16_777_216)]


def _record_lane(record: Mapping[str, Any]) -> str:
    target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    return str(target.get("official_lane_key") or record.get("official_lane_key") or "")


def _matching_lane(raw: Mapping[str, Any], official_lane_key: str) -> dict[str, Any]:
    for row in raw.get("lanes", []) if isinstance(raw.get("lanes"), list) else []:
        if isinstance(row, Mapping) and _lane_key_from_row(row) == official_lane_key:
            return dict(row)
    return {}


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
