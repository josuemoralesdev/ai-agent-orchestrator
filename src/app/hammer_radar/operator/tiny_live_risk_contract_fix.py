"""R262A tiny-live risk-contract diagnostic and controls recheck.

This module diagnoses the official tiny-live risk contract and reuses the R261
controls arming surface. It never submits, signs, regenerates requests, calls
Binance/network, reads secrets, or places orders.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_actual_submit_gate import RISK_CONTRACT_CONFIG_PATH
from src.app.hammer_radar.operator.tiny_live_controls_arming import (
    ARMING_CONFIRMATION_PHRASE,
    LANE_CONTROLS_PATH,
    build_tiny_live_controls_review,
    load_tiny_live_lane_controls,
    load_tiny_live_risk_contract,
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
LEDGER_FILENAME = "tiny_live_risk_contract_fix.ndjson"
CREATED_BY_PHASE = "R262A_TINY_LIVE_RISK_CONTRACT_FIX_CONTROLS_RECHECK"
EVENT_TYPE = "TINY_LIVE_RISK_CONTRACT_FIX"

DIAGNOSTIC_CONFIRMATION_PHRASE = (
    "I CONFIRM TINY LIVE RISK CONTRACT DIAGNOSTIC RECORDING ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
)
FIX_CONFIRMATION_PHRASE = (
    "I CONFIRM TINY LIVE RISK CONTRACT FIX FOR BTCUSDT 8M SHORT ONLY; "
    "KEEP RISK LIMITS SAME OR STRICTER; NO SUBMIT; NO ORDER; NO BINANCE CALL."
)

TINY_LIVE_RISK_CONTRACT_FIX_READY = "TINY_LIVE_RISK_CONTRACT_FIX_READY"
TINY_LIVE_RISK_CONTRACT_DIAGNOSTIC_RECORDED = "TINY_LIVE_RISK_CONTRACT_DIAGNOSTIC_RECORDED"
TINY_LIVE_RISK_CONTRACT_FIX_APPLIED = "TINY_LIVE_RISK_CONTRACT_FIX_APPLIED"
TINY_LIVE_RISK_CONTRACT_FIX_AND_CONTROLS_ARMING_RECORDED = (
    "TINY_LIVE_RISK_CONTRACT_FIX_AND_CONTROLS_ARMING_RECORDED"
)
TINY_LIVE_RISK_CONTRACT_FIX_REJECTED = "TINY_LIVE_RISK_CONTRACT_FIX_REJECTED"
TINY_LIVE_RISK_CONTRACT_FIX_BLOCKED = "TINY_LIVE_RISK_CONTRACT_FIX_BLOCKED"
TINY_LIVE_RISK_CONTRACT_FIX_ERROR = "TINY_LIVE_RISK_CONTRACT_FIX_ERROR"

TINY_LIVE_RISK_CONTRACT_FIX_READY_FOR_DIAGNOSTIC = "TINY_LIVE_RISK_CONTRACT_FIX_READY_FOR_DIAGNOSTIC"
TINY_LIVE_RISK_CONTRACT_FIX_READY_TO_APPLY = "TINY_LIVE_RISK_CONTRACT_FIX_READY_TO_APPLY"
TINY_LIVE_RISK_CONTRACT_VALID_CONTROLS_ARMING_REQUIRED = (
    "TINY_LIVE_RISK_CONTRACT_VALID_CONTROLS_ARMING_REQUIRED"
)
TINY_LIVE_RISK_CONTRACT_VALID_CONTROLS_ARMED_R262_CONSOLE_REQUIRED = (
    "TINY_LIVE_RISK_CONTRACT_VALID_CONTROLS_ARMED_R262_CONSOLE_REQUIRED"
)
TINY_LIVE_RISK_CONTRACT_FIX_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_RISK_CONTRACT_FIX_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_RISK_CONTRACT_FIX_BLOCKED_UNSAFE_LIMIT_CHANGE = (
    "TINY_LIVE_RISK_CONTRACT_FIX_BLOCKED_UNSAFE_LIMIT_CHANGE"
)
TINY_LIVE_RISK_CONTRACT_FIX_BLOCKED_UNKNOWN_SCHEMA = "TINY_LIVE_RISK_CONTRACT_FIX_BLOCKED_UNKNOWN_SCHEMA"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/tiny_live_controls_arming.py",
    "src/app/hammer_radar/operator/tiny_live_actual_submit_gate.py",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    "logs/hammer_radar_forward/tiny_live_fresh_cycle_one_shot.ndjson",
    "logs/hammer_radar_forward/tiny_live_actual_submit_gate.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_risk_contract_diagnostic(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    record_risk_contract_diagnostic: bool = False,
    confirm_risk_contract_diagnostic: str | None = None,
    apply_risk_contract_fix: bool = False,
    confirm_risk_contract_fix: str | None = None,
    arm_controls_after_fix: bool = False,
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
    diagnostic_confirmation_valid = confirm_risk_contract_diagnostic == DIAGNOSTIC_CONFIRMATION_PHRASE
    fix_confirmation_valid = confirm_risk_contract_fix == FIX_CONFIRMATION_PHRASE
    arming_confirmation_valid = confirm_arm_tiny_live_controls == ARMING_CONFIRMATION_PHRASE
    confirmation_valid = bool(
        (record_risk_contract_diagnostic and diagnostic_confirmation_valid)
        or (apply_risk_contract_fix and fix_confirmation_valid)
        or (arm_controls_after_fix and arming_confirmation_valid)
    )
    symbol, timeframe, direction, _entry_mode = _lane_parts(official_lane_key)
    try:
        contract = load_tiny_live_risk_contract_for_official_lane(
            risk_contract_config_path=risk_path,
            official_lane_key=official_lane_key,
        )
        lane_controls = load_tiny_live_lane_controls(lane_controls_path=lane_path, official_lane_key=official_lane_key)
        before_review = build_tiny_live_controls_review(
            log_dir=resolved_log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            official_lane_key=official_lane_key,
        )
        diagnostic = classify_tiny_live_risk_contract_invalid_reason(
            contract=contract,
            controls_review=before_review,
        )
        fix_plan = build_tiny_live_risk_contract_fix_plan(
            contract=contract,
            diagnostic=diagnostic,
        )
        safety_validation = validate_tiny_live_risk_contract_fix_safety(
            contract=contract,
            fix_plan=fix_plan,
        )
        fix_result = apply_tiny_live_risk_contract_fix_if_needed(
            apply_requested=apply_risk_contract_fix,
            confirmation_valid=fix_confirmation_valid,
            fix_plan=fix_plan,
            safety_validation=safety_validation,
        )
        controls_recheck = rerun_tiny_live_controls_review_after_fix(
            log_dir=resolved_log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            official_lane_key=official_lane_key,
            attempted=bool(apply_risk_contract_fix or diagnostic["risk_contract_valid_before"]),
        )
        fix_result["risk_contract_valid_after"] = controls_recheck["risk_contract_valid"]
        fix_result["invalid_reasons_after"] = list(controls_recheck.get("risk_contract_invalid_reasons") or [])
        controls_arming = rerun_tiny_live_controls_arming_after_fix(
            log_dir=resolved_log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            official_lane_key=official_lane_key,
            arm_controls_after_fix=arm_controls_after_fix,
            confirm_arm_tiny_live_controls=confirm_arm_tiny_live_controls,
            operator_id=operator_id,
            reason=reason,
        )
        matrix = _build_matrix(
            before_review=before_review,
            controls_recheck=controls_recheck,
            controls_arming=controls_arming,
            fix_plan=fix_plan,
            safety_validation=safety_validation,
        )
        overall = classify_tiny_live_risk_contract_fix_status(
            record_requested=record_risk_contract_diagnostic,
            apply_requested=apply_risk_contract_fix,
            arm_requested=arm_controls_after_fix,
            diagnostic_confirmation_valid=diagnostic_confirmation_valid,
            fix_confirmation_valid=fix_confirmation_valid,
            fix_result=fix_result,
            controls_recheck=controls_recheck,
            controls_arming=controls_arming,
            matrix=matrix,
        )
        status = _status_for(
            record_requested=record_risk_contract_diagnostic,
            apply_requested=apply_risk_contract_fix,
            arm_requested=arm_controls_after_fix,
            diagnostic_confirmation_valid=diagnostic_confirmation_valid,
            fix_confirmation_valid=fix_confirmation_valid,
            diagnostic_recorded=False,
            fix_result=fix_result,
            controls_arming=controls_arming,
            matrix=matrix,
        )
        diagnostic_recorded = bool(record_risk_contract_diagnostic and diagnostic_confirmation_valid)
        if diagnostic_recorded:
            status = TINY_LIVE_RISK_CONTRACT_DIAGNOSTIC_RECORDED
        if fix_result["succeeded"]:
            status = TINY_LIVE_RISK_CONTRACT_FIX_APPLIED
        if controls_arming["succeeded"]:
            status = TINY_LIVE_RISK_CONTRACT_FIX_AND_CONTROLS_ARMING_RECORDED
        safety = _safety(
            risk_contract_config_written=bool(fix_result.get("risk_contract_config_written")),
            lane_controls_written=bool(controls_arming.get("lane_controls_written")),
        )
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "record_risk_contract_diagnostic_requested": bool(record_risk_contract_diagnostic),
                "apply_risk_contract_fix_requested": bool(apply_risk_contract_fix),
                "arm_controls_after_fix_requested": bool(arm_controls_after_fix),
                "confirmation_valid": bool(confirmation_valid),
                "risk_contract_diagnostic_recorded": diagnostic_recorded,
                "risk_contract_fix_applied": bool(fix_result["succeeded"]),
                "controls_arming_recorded": bool(controls_arming["succeeded"]),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "risk_contract_fix_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "input_summary": {
                    "risk_contract_found": bool(contract.get("risk_contract_found")),
                    "lane_controls_found": bool(lane_controls.get("found")),
                    "r261_controls_review_found": bool(before_review),
                    "r260_one_shot_found": bool(before_review.get("input_summary", {}).get("r260_one_shot_found")),
                    "r260_one_shot_valid": bool(before_review.get("input_summary", {}).get("r260_one_shot_valid")),
                },
                "risk_contract_before": contract.get("contract") or {},
                "risk_contract_diagnostic": diagnostic,
                "risk_contract_fix_plan": fix_plan,
                "risk_contract_fix_result": fix_result,
                "controls_recheck_after_fix": controls_recheck,
                "controls_arming_after_fix": controls_arming,
                "risk_contract_fix_matrix": matrix,
                "risk_contract_fix_overall_status": overall,
                "recommended_next_operator_move": _recommended_operator_move(overall, controls_recheck, matrix),
                "recommended_next_engineering_move": _recommended_engineering_move(overall, diagnostic, matrix),
                "do_not_run_yet": [
                    "real submit from R262A",
                    "real submit before R262 console",
                    "real submit if risk contract remains invalid",
                    "duplicate live submit",
                ],
                "safety": safety,
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if diagnostic_recorded or apply_risk_contract_fix or controls_arming["attempted"]:
            record = append_tiny_live_risk_contract_fix_record(payload, log_dir=resolved_log_dir)
            payload["risk_contract_fix_record_id"] = record["risk_contract_fix_record_id"]
            payload["ledger_path"] = str(tiny_live_risk_contract_fix_records_path(resolved_log_dir))
        return payload
    except Exception as exc:  # pragma: no cover - defensive operator JSON surface
        return _sanitize(
            {
                "status": TINY_LIVE_RISK_CONTRACT_FIX_ERROR,
                "generated_at": generated_at.isoformat(),
                "record_risk_contract_diagnostic_requested": bool(record_risk_contract_diagnostic),
                "apply_risk_contract_fix_requested": bool(apply_risk_contract_fix),
                "arm_controls_after_fix_requested": bool(arm_controls_after_fix),
                "confirmation_valid": False,
                "risk_contract_diagnostic_recorded": False,
                "risk_contract_fix_applied": False,
                "controls_arming_recorded": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "risk_contract_fix_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "error": str(exc),
                "safety": _safety(risk_contract_config_written=False, lane_controls_written=False),
            }
        )


def load_tiny_live_risk_contract_for_official_lane(
    *,
    risk_contract_config_path: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    loaded = load_tiny_live_risk_contract(
        risk_contract_config_path=risk_contract_config_path,
        official_lane_key=official_lane_key,
    )
    contract = loaded.get("contract") if isinstance(loaded.get("contract"), Mapping) else {}
    return {
        "risk_contract_found": bool(loaded.get("found") and contract),
        "path": loaded.get("path"),
        "contract": dict(contract),
        "raw_schema_keys": sorted(list((loaded.get("raw") or {}).keys())) if isinstance(loaded.get("raw"), Mapping) else [],
    }


def inspect_tiny_live_risk_contract_schema(contract: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "official_lane_key",
        "symbol",
        "timeframe",
        "direction",
        "entry_mode",
        "margin_budget_usdt",
        "max_notional_usdt",
        "max_loss_usdt",
        "leverage",
        "protective_stop_required",
        "take_profit_required",
    }
    keys = set(contract.keys())
    missing = sorted(expected - keys)
    return {
        "known_schema": not missing,
        "missing_fields": missing,
        "present_fields": sorted(keys),
        "schema_version": contract.get("contract_version"),
    }


def inspect_tiny_live_risk_contract_validator() -> dict[str, Any]:
    return {
        "validator": "validate_tiny_live_risk_contract_still_within_bounds",
        "uses_order_triplet_entry_reference_price": True,
        "uses_r260_fresh_mark_fallback_for_legacy_r255": True,
        "max_loss_cap_usdt": 4.44,
        "max_notional_cap_usdt": 440,
        "does_not_call_network": True,
    }


def classify_tiny_live_risk_contract_invalid_reason(
    *,
    contract: Mapping[str, Any],
    controls_review: Mapping[str, Any],
) -> dict[str, Any]:
    risk_state = controls_review.get("risk_contract_state") if isinstance(controls_review.get("risk_contract_state"), Mapping) else {}
    validation = risk_state.get("validation_summary") if isinstance(risk_state.get("validation_summary"), Mapping) else {}
    invalid_reasons = list(risk_state.get("risk_contract_invalid_reasons") or [])
    schema = inspect_tiny_live_risk_contract_schema(contract.get("contract") if isinstance(contract.get("contract"), Mapping) else {})
    blocked_by = [str(item) for item in validation.get("blocked_by") or []]
    config_issue = any(reason.endswith("_not_8m") or reason.endswith("_not_short") for reason in invalid_reasons)
    risk_math_issue = any(item in blocked_by for item in ("estimated_loss_exceeds_max_loss", "notional_exceeds_max_notional_buffer"))
    validator_issue = "missing_entry_reference_price" in blocked_by
    schema_issue = bool(schema["missing_fields"])
    strictness_issue = bool(risk_math_issue)
    if risk_state.get("risk_contract_valid") is True:
        root = "already_valid"
    elif risk_math_issue:
        root = "unsafe_limits"
    elif validator_issue:
        root = "validator_bug"
    elif schema_issue:
        root = "schema_mismatch"
    elif config_issue:
        root = "config_missing_field"
    else:
        root = "unknown"
    return {
        "risk_contract_valid_before": risk_state.get("risk_contract_valid") is True,
        "invalid_reasons_before": invalid_reasons,
        "schema_issue": schema_issue,
        "validator_issue": validator_issue,
        "config_issue": config_issue,
        "risk_math_issue": risk_math_issue,
        "strictness_issue": strictness_issue,
        "root_cause": root,
        "schema": schema,
        "validator": inspect_tiny_live_risk_contract_validator(),
        "validator_blocked_by": blocked_by,
        "validation_summary": dict(validation),
    }


def build_tiny_live_risk_contract_fix_plan(
    *,
    contract: Mapping[str, Any],
    diagnostic: Mapping[str, Any],
) -> dict[str, Any]:
    blocked_by: list[str] = []
    root = diagnostic.get("root_cause")
    if root == "unsafe_limits":
        blocked_by.append("unsafe_limit_change_required_or_current_triplet_exceeds_contract")
    if root in {"schema_mismatch", "unknown"}:
        blocked_by.append("manual_schema_review_required")
    return {
        "fix_required": root not in {"already_valid", "unsafe_limits"},
        "will_change_config": False,
        "will_change_validator": root == "validator_bug",
        "will_keep_limits_same_or_stricter": True,
        "risk_limit_changes": {},
        "blocked_by": _dedupe(blocked_by),
    }


def validate_tiny_live_risk_contract_fix_safety(
    *,
    contract: Mapping[str, Any],
    fix_plan: Mapping[str, Any],
) -> dict[str, Any]:
    row = contract.get("contract") if isinstance(contract.get("contract"), Mapping) else {}
    blocked_by: list[str] = []
    if _number(row.get("margin_budget_usdt") or row.get("tiny_live_margin_usdt") or row.get("max_margin_usdt")) and (
        _number(row.get("margin_budget_usdt") or row.get("tiny_live_margin_usdt") or row.get("max_margin_usdt")) > 44
    ):
        blocked_by.append("margin_budget_above_44")
    if _number(row.get("leverage")) and _number(row.get("leverage")) > 10:
        blocked_by.append("leverage_above_10")
    if _number(row.get("max_notional_usdt") or row.get("max_position_notional_usdt")) and (
        _number(row.get("max_notional_usdt") or row.get("max_position_notional_usdt")) > 440
    ):
        blocked_by.append("max_notional_above_440")
    if _number(row.get("max_loss_usdt")) and _number(row.get("max_loss_usdt")) > 4.44:
        blocked_by.append("max_loss_above_4_44")
    blocked_by.extend(str(item) for item in fix_plan.get("blocked_by") or [])
    return {
        "safe_to_apply": not blocked_by,
        "limits_same_or_stricter": not blocked_by,
        "blocked_by": _dedupe(blocked_by),
    }


def apply_tiny_live_risk_contract_fix_if_needed(
    *,
    apply_requested: bool,
    confirmation_valid: bool,
    fix_plan: Mapping[str, Any],
    safety_validation: Mapping[str, Any],
) -> dict[str, Any]:
    blocked_by = list(safety_validation.get("blocked_by") or [])
    if apply_requested and not confirmation_valid:
        blocked_by.append("bad_confirmation")
    attempted = bool(apply_requested)
    succeeded = bool(attempted and confirmation_valid and safety_validation.get("safe_to_apply") and not fix_plan.get("will_change_config"))
    return {
        "attempted": attempted,
        "succeeded": succeeded,
        "risk_contract_valid_after": False,
        "invalid_reasons_after": [],
        "files_changed": [
            "src/app/hammer_radar/operator/tiny_live_actual_submit_gate.py",
            "src/app/hammer_radar/operator/tiny_live_controls_arming.py",
        ]
        if succeeded and fix_plan.get("will_change_validator")
        else [],
        "risk_contract_config_written": False,
        "blocked_by": _dedupe(blocked_by),
    }


def rerun_tiny_live_controls_review_after_fix(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    attempted: bool = True,
) -> dict[str, Any]:
    review = build_tiny_live_controls_review(
        log_dir=log_dir,
        risk_contract_config_path=risk_contract_config_path,
        lane_controls_path=lane_controls_path,
        official_lane_key=official_lane_key,
    )
    risk = review.get("risk_contract_state") if isinstance(review.get("risk_contract_state"), Mapping) else {}
    fresh = review.get("freshness_state") if isinstance(review.get("freshness_state"), Mapping) else {}
    packet = review.get("controls_review_packet") if isinstance(review.get("controls_review_packet"), Mapping) else {}
    return {
        "attempted": bool(attempted),
        "risk_contract_valid": risk.get("risk_contract_valid") is True,
        "fresh_cycle_valid": fresh.get("fresh_cycle_valid") is True,
        "operator_should_arm_controls": packet.get("operator_should_arm_controls") is True,
        "next_required_step": packet.get("next_required_step") or "WAIT",
        "risk_contract_invalid_reasons": list(risk.get("risk_contract_invalid_reasons") or []),
        "risk_contract_validation_summary": risk.get("validation_summary") or {},
    }


def rerun_tiny_live_controls_arming_after_fix(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    arm_controls_after_fix: bool = False,
    confirm_arm_tiny_live_controls: str | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
) -> dict[str, Any]:
    if not arm_controls_after_fix:
        return _empty_arming_result(attempted=False)
    result = build_tiny_live_controls_review(
        log_dir=log_dir,
        risk_contract_config_path=risk_contract_config_path,
        lane_controls_path=lane_controls_path,
        arm_tiny_live_controls=True,
        confirm_arm_tiny_live_controls=confirm_arm_tiny_live_controls,
        operator_id=operator_id,
        reason=reason,
        official_lane_key=official_lane_key,
    )
    arming = result.get("arming_result") if isinstance(result.get("arming_result"), Mapping) else {}
    controls = result.get("controls_state") if isinstance(result.get("controls_state"), Mapping) else {}
    return {
        "attempted": True,
        "succeeded": result.get("controls_arming_recorded") is True,
        "lane_controls_written": arming.get("lane_controls_written") is True,
        "official_lane_allowed": controls.get("official_lane_allowed") is True,
        "live_execution_enabled": controls.get("live_execution_enabled") is True,
        "kill_switch_allows_tiny_live": controls.get("kill_switch_allows_tiny_live") is True,
        "blocked_by": list(arming.get("blocked_by") or []),
    }


def append_tiny_live_risk_contract_fix_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_risk_contract_fix_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "risk_contract_fix_record_id": record.get("risk_contract_fix_record_id")
            or f"r262a_risk_contract_fix_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "created_by_phase": CREATED_BY_PHASE,
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_risk_contract_fix_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_risk_contract_fix_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def classify_tiny_live_risk_contract_fix_status(
    *,
    record_requested: bool,
    apply_requested: bool,
    arm_requested: bool,
    diagnostic_confirmation_valid: bool,
    fix_confirmation_valid: bool,
    fix_result: Mapping[str, Any],
    controls_recheck: Mapping[str, Any],
    controls_arming: Mapping[str, Any],
    matrix: Mapping[str, Any],
) -> str:
    if record_requested and not diagnostic_confirmation_valid:
        return TINY_LIVE_RISK_CONTRACT_FIX_REJECTED_BAD_CONFIRMATION
    if apply_requested and not fix_confirmation_valid:
        return TINY_LIVE_RISK_CONTRACT_FIX_REJECTED_BAD_CONFIRMATION
    if not matrix.get("limits_same_or_stricter"):
        return TINY_LIVE_RISK_CONTRACT_FIX_BLOCKED_UNSAFE_LIMIT_CHANGE
    if matrix.get("blocked_by"):
        return TINY_LIVE_RISK_CONTRACT_FIX_BLOCKED_UNSAFE_LIMIT_CHANGE
    if controls_arming.get("succeeded"):
        return TINY_LIVE_RISK_CONTRACT_VALID_CONTROLS_ARMED_R262_CONSOLE_REQUIRED
    if controls_recheck.get("risk_contract_valid"):
        return TINY_LIVE_RISK_CONTRACT_VALID_CONTROLS_ARMING_REQUIRED
    if apply_requested or fix_result.get("succeeded"):
        return TINY_LIVE_RISK_CONTRACT_FIX_READY_TO_APPLY
    return TINY_LIVE_RISK_CONTRACT_FIX_READY_FOR_DIAGNOSTIC


def format_tiny_live_risk_contract_fix_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def tiny_live_risk_contract_fix_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _build_matrix(
    *,
    before_review: Mapping[str, Any],
    controls_recheck: Mapping[str, Any],
    controls_arming: Mapping[str, Any],
    fix_plan: Mapping[str, Any],
    safety_validation: Mapping[str, Any],
) -> dict[str, Any]:
    before_risk = before_review.get("risk_contract_state") if isinstance(before_review.get("risk_contract_state"), Mapping) else {}
    blocked_by = list(fix_plan.get("blocked_by") or []) + list(safety_validation.get("blocked_by") or [])
    return {
        "r260_available": before_review.get("input_summary", {}).get("r260_one_shot_found") is True,
        "risk_contract_valid_before": before_risk.get("risk_contract_valid") is True,
        "risk_contract_valid_after": controls_recheck.get("risk_contract_valid") is True,
        "limits_same_or_stricter": safety_validation.get("limits_same_or_stricter") is True,
        "controls_rechecked": controls_recheck.get("attempted") is True,
        "controls_armed": controls_arming.get("succeeded") is True,
        "submit_allowed": False,
        "order_placed": False,
        "blocked_by": _dedupe(blocked_by),
    }


def _status_for(
    *,
    record_requested: bool,
    apply_requested: bool,
    arm_requested: bool,
    diagnostic_confirmation_valid: bool,
    fix_confirmation_valid: bool,
    diagnostic_recorded: bool,
    fix_result: Mapping[str, Any],
    controls_arming: Mapping[str, Any],
    matrix: Mapping[str, Any],
) -> str:
    if record_requested and not diagnostic_confirmation_valid:
        return TINY_LIVE_RISK_CONTRACT_FIX_REJECTED
    if apply_requested and not fix_confirmation_valid:
        return TINY_LIVE_RISK_CONTRACT_FIX_REJECTED
    if controls_arming.get("succeeded"):
        return TINY_LIVE_RISK_CONTRACT_FIX_AND_CONTROLS_ARMING_RECORDED
    if fix_result.get("succeeded"):
        return TINY_LIVE_RISK_CONTRACT_FIX_APPLIED
    if diagnostic_recorded:
        return TINY_LIVE_RISK_CONTRACT_DIAGNOSTIC_RECORDED
    if (apply_requested or arm_requested) and matrix.get("blocked_by"):
        return TINY_LIVE_RISK_CONTRACT_FIX_BLOCKED
    return TINY_LIVE_RISK_CONTRACT_FIX_READY


def _empty_arming_result(*, attempted: bool) -> dict[str, Any]:
    return {
        "attempted": attempted,
        "succeeded": False,
        "lane_controls_written": False,
        "official_lane_allowed": False,
        "live_execution_enabled": False,
        "kill_switch_allows_tiny_live": False,
        "blocked_by": [],
    }


def _recommended_operator_move(
    overall: str,
    controls_recheck: Mapping[str, Any],
    matrix: Mapping[str, Any],
) -> str:
    if overall == TINY_LIVE_RISK_CONTRACT_VALID_CONTROLS_ARMED_R262_CONSOLE_REQUIRED:
        return "Open R262 final submit console; do not submit from R262A."
    if controls_recheck.get("next_required_step") == "ARM_CONTROLS":
        return "Arm tiny-live controls only with the exact R261/R262A arming phrase."
    if matrix.get("blocked_by"):
        return "Do not arm controls; current triplet or schema remains outside the risk contract."
    return "Record the R262A diagnostic before any further submit-console work."


def _recommended_engineering_move(
    overall: str,
    diagnostic: Mapping[str, Any],
    matrix: Mapping[str, Any],
) -> str:
    if overall == TINY_LIVE_RISK_CONTRACT_VALID_CONTROLS_ARMED_R262_CONSOLE_REQUIRED:
        return "Update/run R262 final submit console with no auto-submit by default."
    if diagnostic.get("risk_math_issue"):
        return "Refresh/rebuild the future signed triplet in a later authorized phase; R262A must not regenerate."
    if matrix.get("risk_contract_valid_after"):
        return "Proceed to controls arming review; keep real submit blocked."
    return "Keep R262 blocked until risk contract validation is clean."


def _safety(*, risk_contract_config_written: bool, lane_controls_written: bool) -> dict[str, Any]:
    return {
        **SAFETY_FALSE,
        "env_written": False,
        "env_mutated": False,
        "external_env_file_written": False,
        "config_written": bool(risk_contract_config_written or lane_controls_written),
        "risk_contract_config_written": bool(risk_contract_config_written),
        "lane_controls_written": bool(lane_controls_written),
        "live_config_written": False,
        "risk_contract_fix_only": True,
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


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key).split("|")
    padded = (parts + ["", "", "", ""])[:4]
    return padded[0], padded[1], padded[2], padded[3]


def _number(value: Any) -> float | None:
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
    if isinstance(value, dict):
        sanitized = {str(key): _sanitize(item) for key, item in value.items()}
        for key in (
            "env_written",
            "env_mutated",
            "external_env_file_written",
            "risk_contract_config_written",
            "hmac_signature_created",
            "signed_request_written",
            "signed_order_request_created",
            "signed_trading_request_created",
            "submit_allowed",
            "submit_attempted",
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "binance_order_endpoint_called",
            "binance_test_order_endpoint_called",
            "binance_account_endpoint_called",
            "binance_exchange_info_endpoint_called",
            "binance_mark_price_endpoint_called",
            "private_binance_endpoint_called",
            "signed_binance_endpoint_called",
            "network_allowed",
            "transfer_endpoint_called",
            "withdraw_endpoint_called",
            "kill_switch_disabled",
            "secrets_read",
            "secrets_shown",
            "secrets_persisted",
            "secret_values_in_output",
            "global_live_flags_changed",
            "official_tiny_live_lane_changed",
        ):
            if key in sanitized:
                sanitized[key] = False
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
