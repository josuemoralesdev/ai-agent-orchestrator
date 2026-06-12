"""R252 tiny-live submit readiness preview.

This module composes existing local R251E/R251/R249/R248/R242 artifacts into a
submit-readiness preview. It never calls Binance/network endpoints, signs
requests, creates new signed requests, submits, places orders, or mutates
env/config/lane controls.
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
from src.app.hammer_radar.operator.tiny_live_binance_readonly_precision_mark_price_gate import (
    load_tiny_live_binance_readonly_precision_mark_price_records,
)
from src.app.hammer_radar.operator.tiny_live_executable_payload_write_gate import (
    load_tiny_live_executable_payload_write_gate_records,
    validate_executable_payload_artifact,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_runtime_source_write_gate import (
    load_tiny_live_signed_request_runtime_source_write_gate_records,
    validate_r251e_signed_request_artifact,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_write_gate import (
    load_tiny_live_signed_request_write_gate_records,
    validate_signed_request_artifact,
)
from src.app.hammer_radar.operator.tiny_live_stop_take_profit_source_gate import (
    load_tiny_live_stop_take_profit_source_gate_records,
    validate_short_stop_take_profit_levels,
)

TINY_LIVE_SUBMIT_READINESS_PREVIEW_READY = "TINY_LIVE_SUBMIT_READINESS_PREVIEW_READY"
TINY_LIVE_SUBMIT_READINESS_PREVIEW_RECORDED = "TINY_LIVE_SUBMIT_READINESS_PREVIEW_RECORDED"
TINY_LIVE_SUBMIT_READINESS_PREVIEW_REJECTED = "TINY_LIVE_SUBMIT_READINESS_PREVIEW_REJECTED"
TINY_LIVE_SUBMIT_READINESS_PREVIEW_BLOCKED = "TINY_LIVE_SUBMIT_READINESS_PREVIEW_BLOCKED"
TINY_LIVE_SUBMIT_READINESS_PREVIEW_ERROR = "TINY_LIVE_SUBMIT_READINESS_PREVIEW_ERROR"

TINY_LIVE_SUBMIT_READINESS_READY_FOR_FINAL_READONLY_REFRESH = (
    "TINY_LIVE_SUBMIT_READINESS_READY_FOR_FINAL_READONLY_REFRESH"
)
TINY_LIVE_SUBMIT_READINESS_RECORDED_FINAL_READONLY_REFRESH_REQUIRED = (
    "TINY_LIVE_SUBMIT_READINESS_RECORDED_FINAL_READONLY_REFRESH_REQUIRED"
)
TINY_LIVE_SUBMIT_READINESS_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_SUBMIT_READINESS_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_SUBMIT_READINESS_BLOCKED_BY_MISSING_SIGNED_REQUEST = (
    "TINY_LIVE_SUBMIT_READINESS_BLOCKED_BY_MISSING_SIGNED_REQUEST"
)
TINY_LIVE_SUBMIT_READINESS_BLOCKED_BY_INVALID_SIGNED_REQUEST = (
    "TINY_LIVE_SUBMIT_READINESS_BLOCKED_BY_INVALID_SIGNED_REQUEST"
)
TINY_LIVE_SUBMIT_READINESS_BLOCKED_BY_SUBMIT_CONTROL = (
    "TINY_LIVE_SUBMIT_READINESS_BLOCKED_BY_SUBMIT_CONTROL"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_SUBMIT_READINESS_PREVIEW"
LEDGER_FILENAME = "tiny_live_submit_readiness_preview.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R252_TINY_LIVE_SUBMIT_READINESS_PREVIEW"
CONFIRM_TINY_LIVE_SUBMIT_READINESS_PREVIEW_PHRASE = (
    "I CONFIRM TINY LIVE SUBMIT READINESS PREVIEW RECORDING ONLY; "
    "NO SUBMIT; NO ORDER; NO BINANCE CALL."
)
FUTURE_READONLY_PHASE = "R253_TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE"

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_signed_request_runtime_source_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_binance_readonly_precision_mark_price_gate.ndjson",
]

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "external_env_file_written": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "submit_readiness_preview_only": True,
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
    "network_allowed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "kill_switch_disabled": False,
    "secrets_shown": False,
    "secrets_persisted": False,
    "secret_values_in_output": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
}


def build_tiny_live_submit_readiness_preview(
    *,
    log_dir: str | Path | None = None,
    record_submit_readiness_preview: bool = False,
    confirm_tiny_live_submit_readiness_preview: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_submit_readiness_preview
        == CONFIRM_TINY_LIVE_SUBMIT_READINESS_PREVIEW_PHRASE
    )
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)

    try:
        latest_r251e = load_latest_tiny_live_signed_request_runtime_source_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r251 = load_latest_tiny_live_signed_request_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r249 = load_latest_tiny_live_executable_payload_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r248 = load_latest_tiny_live_stop_take_profit_source_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r242 = load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )

        r251_artifact = _signed_request_artifact(latest_r251)
        r249_artifact = _executable_payload_artifact(latest_r249)
        r251e_validation = validate_runtime_source_signed_request_artifact_for_submit_preview(
            latest_r251e,
            signed_request_artifact=r251_artifact,
        )
        r251_validation = validate_signed_request_artifact(r251_artifact)
        submit_controls = validate_signed_request_submit_controls(r251_artifact)
        r249_validation = validate_executable_payload_artifact(r249_artifact)
        r248_validation = _validate_r248_record(latest_r248)
        r242_validation = _validate_r242_record(latest_r242)

        input_summary = _build_input_summary(
            latest_r251e=latest_r251e,
            r251e_validation=r251e_validation,
            latest_r251=latest_r251,
            r251_validation=r251_validation,
            latest_r249=latest_r249,
            r249_validation=r249_validation,
            latest_r248=latest_r248,
            r248_validation=r248_validation,
            latest_r242=latest_r242,
            r242_validation=r242_validation,
        )
        signed_summary = build_submit_readiness_signed_request_summary(r251_artifact)
        risk_summary = _build_risk_context_summary(r249_artifact, latest_r248)
        refresh_requirement = build_final_readonly_refresh_requirement()
        blocker_summary = build_submit_blocker_summary(
            input_summary=input_summary,
            signed_request_submit_summary=signed_summary,
            submit_controls_validation=submit_controls,
        )
        matrix = build_submit_readiness_preview_matrix(
            input_summary=input_summary,
            submit_controls_validation=submit_controls,
            record_confirmed=record_submit_readiness_preview and confirmation_valid,
            recorded=False,
            blocked_by=blocker_summary["blocked_by"],
        )

        if record_submit_readiness_preview and not confirmation_valid:
            status = TINY_LIVE_SUBMIT_READINESS_PREVIEW_REJECTED
            overall = TINY_LIVE_SUBMIT_READINESS_REJECTED_BAD_CONFIRMATION
        elif blocker_summary["hard_blocked"]:
            status = TINY_LIVE_SUBMIT_READINESS_PREVIEW_BLOCKED
            overall = classify_tiny_live_submit_readiness_preview_status(
                input_summary=input_summary,
                submit_controls_validation=submit_controls,
                record_requested=record_submit_readiness_preview,
                confirmation_valid=confirmation_valid,
                recorded=False,
            )
        elif record_submit_readiness_preview and confirmation_valid:
            status = TINY_LIVE_SUBMIT_READINESS_PREVIEW_RECORDED
            overall = TINY_LIVE_SUBMIT_READINESS_RECORDED_FINAL_READONLY_REFRESH_REQUIRED
            matrix = build_submit_readiness_preview_matrix(
                input_summary=input_summary,
                submit_controls_validation=submit_controls,
                record_confirmed=True,
                recorded=True,
                blocked_by=blocker_summary["blocked_by"],
            )
        else:
            status = TINY_LIVE_SUBMIT_READINESS_PREVIEW_READY
            overall = TINY_LIVE_SUBMIT_READINESS_READY_FOR_FINAL_READONLY_REFRESH

        operator_packet = build_operator_submit_readiness_preview_packet(matrix)
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "submit_readiness_preview_recorded": matrix["recorded"] is True,
                "record_submit_readiness_preview_requested": bool(record_submit_readiness_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "submit_readiness_preview_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "signed_request_submit_summary": signed_summary,
                "risk_context_summary": risk_summary,
                "final_readonly_refresh_requirement": refresh_requirement,
                "submit_blocker_summary": blocker_summary,
                "submit_readiness_preview_matrix": matrix,
                "operator_submit_readiness_preview_packet": operator_packet,
                "recommended_next_operator_move": _recommended_next_operator_move(matrix),
                "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
                "submit_readiness_overall_status": overall,
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if matrix["recorded"] is True:
            payload = append_tiny_live_submit_readiness_preview_record(
                payload,
                log_dir=resolved_log_dir,
                confirm_tiny_live_submit_readiness_preview=(
                    confirm_tiny_live_submit_readiness_preview
                ),
            )
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        matrix = build_submit_readiness_preview_matrix(
            input_summary=_empty_input_summary(),
            submit_controls_validation={"valid": False, "errors": ["submit_readiness_preview_error"]},
            record_confirmed=False,
            recorded=False,
            blocked_by=["submit_readiness_preview_error"],
        )
        return _sanitize(
            {
                "status": TINY_LIVE_SUBMIT_READINESS_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "submit_readiness_preview_recorded": False,
                "record_submit_readiness_preview_requested": bool(record_submit_readiness_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "submit_readiness_preview_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "input_summary": _empty_input_summary(),
                "signed_request_submit_summary": build_submit_readiness_signed_request_summary({}),
                "risk_context_summary": _empty_risk_context_summary(),
                "final_readonly_refresh_requirement": build_final_readonly_refresh_requirement(),
                "submit_blocker_summary": {
                    "submit_ready_now": False,
                    "blocked_by": ["submit_readiness_preview_error"],
                    "hard_blocked": True,
                },
                "submit_readiness_preview_matrix": matrix,
                "operator_submit_readiness_preview_packet": build_operator_submit_readiness_preview_packet(matrix),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R252 submit readiness preview error before any R253 refresh.",
                "submit_readiness_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_signed_request_runtime_source_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_signed_request_runtime_source_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        if (
            target.get("official_lane_key") == official_lane_key
            and record.get("signed_request_written") is True
            and record.get("secret_validation", {}).get("valid") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_signed_request_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_signed_request_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        artifact = _signed_request_artifact(record)
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("signed_request_written") is True
            and validate_signed_request_artifact(artifact).get("valid") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_executable_payload_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_executable_payload_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        artifact = _executable_payload_artifact(record)
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("executable_payload_written") is True
            and validate_executable_payload_artifact(artifact).get("valid") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_stop_take_profit_source_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_stop_take_profit_source_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        if _record_matches_lane(record, official_lane_key) and _validate_r248_record(record).get("valid") is True:
            return _sanitize(record)
    return {}


def load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_binance_readonly_precision_mark_price_records(log_dir=log_dir, limit=50)
    for record in records:
        if _record_matches_lane(record, official_lane_key) and _validate_r242_record(record).get("valid") is True:
            return _sanitize(record)
    return {}


def validate_runtime_source_signed_request_artifact_for_submit_preview(
    record: Mapping[str, Any],
    *,
    signed_request_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not record:
        errors.append("r251e_runtime_signed_request_missing")
    if record.get("signed_request_written") is not True:
        errors.append("r251e_signed_request_not_written")
    if record.get("secret_validation", {}).get("valid") is not True:
        errors.append("r251e_secret_validation_not_valid")
    if record.get("post_write_verification", {}).get("matching_signed_request_valid") is not True:
        errors.append("r251e_post_write_matching_signed_request_not_valid")
    validation = validate_r251e_signed_request_artifact(signed_request_artifact)
    errors.extend(str(item) for item in validation.get("errors") or [])
    warnings.extend(str(item) for item in validation.get("warnings") or [])
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def validate_signed_request_submit_controls(artifact: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    controls = artifact.get("controls") if isinstance(artifact.get("controls"), Mapping) else {}
    safety = artifact.get("safety") if isinstance(artifact.get("safety"), Mapping) else {}
    signed_requests = artifact.get("signed_requests") if isinstance(artifact.get("signed_requests"), Mapping) else {}
    for key in ("submit_allowed", "binance_call_allowed", "network_allowed"):
        if controls.get(key) is not False:
            errors.append(f"controls_{key}_must_remain_false")
    for key in ("submit_allowed", "order_placed", "binance_order_endpoint_called", "network_allowed"):
        if safety.get(key) is not False:
            errors.append(f"safety_{key}_must_remain_false")
    for order_key in ("main_order", "stop_order", "take_profit_order"):
        request = signed_requests.get(order_key) if isinstance(signed_requests.get(order_key), Mapping) else {}
        if request.get("submit_allowed") is not False:
            errors.append(f"{order_key}_submit_allowed_must_remain_false")
        if request.get("network_allowed") is not False:
            errors.append(f"{order_key}_network_allowed_must_remain_false")
        if request.get("endpoint") != "/fapi/v1/order":
            errors.append(f"{order_key}_endpoint_invalid")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": []}


def build_submit_readiness_signed_request_summary(artifact: Mapping[str, Any]) -> dict[str, Any]:
    signed_requests = artifact.get("signed_requests") if isinstance(artifact.get("signed_requests"), Mapping) else {}
    controls = artifact.get("controls") if isinstance(artifact.get("controls"), Mapping) else {}
    safety = artifact.get("safety") if isinstance(artifact.get("safety"), Mapping) else {}
    return {
        "signed_requests_count": len(signed_requests),
        "main_order_signed": signed_requests.get("main_order", {}).get("signed") is True,
        "stop_order_signed": signed_requests.get("stop_order", {}).get("signed") is True,
        "take_profit_order_signed": signed_requests.get("take_profit_order", {}).get("signed") is True,
        "main_order_endpoint": signed_requests.get("main_order", {}).get("endpoint"),
        "stop_order_endpoint": signed_requests.get("stop_order", {}).get("endpoint"),
        "take_profit_order_endpoint": signed_requests.get("take_profit_order", {}).get("endpoint"),
        "submit_allowed": controls.get("submit_allowed", False) is True,
        "network_allowed": controls.get("network_allowed", False) is True,
        "binance_call_allowed": controls.get("binance_call_allowed", False) is True,
        "order_placed": safety.get("order_placed", False) is True,
    }


def build_final_readonly_refresh_requirement() -> dict[str, Any]:
    return {
        "required_before_submit": True,
        "reason": "signed request and stop/take-profit source depend on older R242 reference mark price",
        "future_phase": FUTURE_READONLY_PHASE,
        "must_refresh": [
            "mark_price",
            "exchange_info_precision",
            "min_notional",
            "quantity_step_validation",
            "stop_take_profit_direction_validation",
            "notional_after_rounding",
        ],
        "binance_order_endpoint_allowed": False,
        "submit_allowed": False,
    }


def build_submit_blocker_summary(
    *,
    input_summary: Mapping[str, Any],
    signed_request_submit_summary: Mapping[str, Any],
    submit_controls_validation: Mapping[str, Any],
) -> dict[str, Any]:
    blocked_by: list[str] = [
        "final_readonly_mark_price_refresh_required",
        "operator_submit_confirmation_required_later",
        "submit_gate_required",
    ]
    hard_blocked = False
    if not input_summary.get("r251e_runtime_signed_request_found"):
        blocked_by.append("r251e_runtime_signed_request_missing")
        hard_blocked = True
    if not input_summary.get("r251e_runtime_signed_request_valid"):
        blocked_by.append("r251e_runtime_signed_request_invalid")
        hard_blocked = True
    if not input_summary.get("r251_signed_request_found"):
        blocked_by.append("r251_signed_request_missing")
        hard_blocked = True
    if not input_summary.get("r251_signed_request_valid"):
        blocked_by.append("r251_signed_request_invalid")
        hard_blocked = True
    for key in (
        "r249_executable_payload_valid",
        "r248_stop_take_profit_source_valid",
        "r242_readonly_reference_valid",
    ):
        if not input_summary.get(key):
            blocked_by.append(key.replace("_valid", "_not_ready"))
            hard_blocked = True
    if submit_controls_validation.get("valid") is not True:
        blocked_by.extend(str(item) for item in submit_controls_validation.get("errors") or [])
        hard_blocked = True
    if any(
        signed_request_submit_summary.get(key) is True
        for key in ("submit_allowed", "network_allowed", "binance_call_allowed", "order_placed")
    ):
        blocked_by.append("signed_request_submit_controls_not_safe")
        hard_blocked = True
    return {
        "submit_ready_now": False,
        "blocked_by": _dedupe(blocked_by),
        "hard_blocked": hard_blocked,
    }


def build_submit_readiness_preview_matrix(
    *,
    input_summary: Mapping[str, Any],
    submit_controls_validation: Mapping[str, Any],
    record_confirmed: bool,
    recorded: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    controls_safe = submit_controls_validation.get("valid") is True
    signed_valid = (
        input_summary.get("r251e_runtime_signed_request_valid") is True
        and input_summary.get("r251_signed_request_valid") is True
    )
    return {
        "runtime_source_signed_request_ready": input_summary.get("r251e_runtime_signed_request_valid") is True,
        "signed_request_valid": signed_valid,
        "submit_controls_safe": controls_safe,
        "final_readonly_refresh_required": True,
        "submit_allowed": False,
        "order_ready": False,
        "live_ready_today": False,
        "record_confirmed": bool(record_confirmed),
        "recorded": bool(recorded),
        "blocked_by": _dedupe(blocked_by or []),
    }


def build_operator_submit_readiness_preview_packet(
    submit_readiness_preview_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    if submit_readiness_preview_matrix.get("recorded") is True:
        action = "RUN_R253_FINAL_READONLY_REFRESH"
    elif submit_readiness_preview_matrix.get("runtime_source_signed_request_ready") is True and submit_readiness_preview_matrix.get("signed_request_valid") is True:
        action = "REVIEW_R252_SUBMIT_READINESS"
    elif submit_readiness_preview_matrix.get("blocked_by"):
        action = "FIX_BLOCKER"
    else:
        action = "WAIT"
    return {
        "operator_should_review_submit_readiness": action in {
            "REVIEW_R252_SUBMIT_READINESS",
            "RUN_R253_FINAL_READONLY_REFRESH",
        },
        "operator_should_run_final_readonly_refresh_next": action == "RUN_R253_FINAL_READONLY_REFRESH",
        "operator_should_submit_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not submit",
            "do not call Binance order endpoint from this phase",
        ],
    }


def classify_tiny_live_submit_readiness_preview_status(
    *,
    input_summary: Mapping[str, Any],
    submit_controls_validation: Mapping[str, Any],
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
) -> str:
    if record_requested and not confirmation_valid:
        return TINY_LIVE_SUBMIT_READINESS_REJECTED_BAD_CONFIRMATION
    if recorded:
        return TINY_LIVE_SUBMIT_READINESS_RECORDED_FINAL_READONLY_REFRESH_REQUIRED
    if not input_summary.get("r251e_runtime_signed_request_found") or not input_summary.get("r251_signed_request_found"):
        return TINY_LIVE_SUBMIT_READINESS_BLOCKED_BY_MISSING_SIGNED_REQUEST
    if not input_summary.get("r251e_runtime_signed_request_valid") or not input_summary.get("r251_signed_request_valid"):
        return TINY_LIVE_SUBMIT_READINESS_BLOCKED_BY_INVALID_SIGNED_REQUEST
    if submit_controls_validation.get("valid") is not True:
        return TINY_LIVE_SUBMIT_READINESS_BLOCKED_BY_SUBMIT_CONTROL
    if (
        input_summary.get("r249_executable_payload_valid") is True
        and input_summary.get("r248_stop_take_profit_source_valid") is True
        and input_summary.get("r242_readonly_reference_valid") is True
    ):
        return TINY_LIVE_SUBMIT_READINESS_READY_FOR_FINAL_READONLY_REFRESH
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_tiny_live_submit_readiness_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_tiny_live_submit_readiness_preview: str | None = None,
) -> dict[str, Any]:
    if (
        confirm_tiny_live_submit_readiness_preview
        != CONFIRM_TINY_LIVE_SUBMIT_READINESS_PREVIEW_PHRASE
    ):
        raise ValueError("bad_tiny_live_submit_readiness_preview_confirmation")
    path = tiny_live_submit_readiness_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "submit_readiness_preview_record_id": record.get("submit_readiness_preview_record_id")
            or f"r252_submit_readiness_preview_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "submit_readiness_preview_recorded": True,
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_submit_readiness_preview_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_submit_readiness_preview_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_submit_readiness_preview_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_recorded": latest.get("submit_readiness_preview_recorded") is True,
        "latest_overall_status": latest.get("submit_readiness_overall_status"),
        "latest_next_required_human_action": latest.get("operator_submit_readiness_preview_packet", {}).get("next_required_human_action"),
    }


def tiny_live_submit_readiness_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_submit_readiness_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r251e: Mapping[str, Any],
    r251e_validation: Mapping[str, Any],
    latest_r251: Mapping[str, Any],
    r251_validation: Mapping[str, Any],
    latest_r249: Mapping[str, Any],
    r249_validation: Mapping[str, Any],
    latest_r248: Mapping[str, Any],
    r248_validation: Mapping[str, Any],
    latest_r242: Mapping[str, Any],
    r242_validation: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "r251e_runtime_signed_request_found": bool(latest_r251e),
        "r251e_runtime_signed_request_valid": r251e_validation.get("valid") is True,
        "r251_signed_request_found": bool(latest_r251),
        "r251_signed_request_valid": r251_validation.get("valid") is True,
        "r249_executable_payload_found": bool(latest_r249),
        "r249_executable_payload_valid": r249_validation.get("valid") is True,
        "r248_stop_take_profit_source_found": bool(latest_r248),
        "r248_stop_take_profit_source_valid": r248_validation.get("valid") is True,
        "r242_readonly_reference_found": bool(latest_r242),
        "r242_readonly_reference_valid": r242_validation.get("valid") is True,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r251e_runtime_signed_request_found": False,
        "r251e_runtime_signed_request_valid": False,
        "r251_signed_request_found": False,
        "r251_signed_request_valid": False,
        "r249_executable_payload_found": False,
        "r249_executable_payload_valid": False,
        "r248_stop_take_profit_source_found": False,
        "r248_stop_take_profit_source_valid": False,
        "r242_readonly_reference_found": False,
        "r242_readonly_reference_valid": False,
    }


def _build_risk_context_summary(
    executable_payload_artifact: Mapping[str, Any],
    r248_record: Mapping[str, Any],
) -> dict[str, Any]:
    main = executable_payload_artifact.get("main_order") if isinstance(executable_payload_artifact.get("main_order"), Mapping) else {}
    stop = executable_payload_artifact.get("stop_order") if isinstance(executable_payload_artifact.get("stop_order"), Mapping) else {}
    take_profit = (
        executable_payload_artifact.get("take_profit_order")
        if isinstance(executable_payload_artifact.get("take_profit_order"), Mapping)
        else {}
    )
    risk = executable_payload_artifact.get("risk") if isinstance(executable_payload_artifact.get("risk"), Mapping) else {}
    source = _r248_source(r248_record)
    return _sanitize(
        {
            "symbol": executable_payload_artifact.get("symbol") or source.get("symbol"),
            "side": main.get("side"),
            "quantity": _number(main.get("quantity") or source.get("quantity")),
            "reference_price": _number(executable_payload_artifact.get("reference_price") or source.get("reference_price")),
            "stop_price": _number(stop.get("stopPrice") or source.get("stop_price")),
            "take_profit_price": _number(take_profit.get("stopPrice") or source.get("take_profit_price")),
            "estimated_loss_at_stop_usdt": _round_number(_number(risk.get("estimated_loss_at_stop_usdt") or source.get("estimated_loss_at_stop_usdt")), 4),
            "estimated_reward_at_take_profit_usdt": _round_number(_number(risk.get("estimated_reward_at_take_profit_usdt") or source.get("estimated_reward_at_take_profit_usdt")), 4),
            "risk_reward_ratio": _round_number(_number(risk.get("risk_reward_ratio") or source.get("risk_reward_ratio")), 4),
            "max_loss_usdt": _number(risk.get("max_loss_usdt") or source.get("max_loss_usdt")),
        }
    )


def _empty_risk_context_summary() -> dict[str, Any]:
    return {
        "symbol": None,
        "side": None,
        "quantity": None,
        "reference_price": None,
        "stop_price": None,
        "take_profit_price": None,
        "estimated_loss_at_stop_usdt": None,
        "estimated_reward_at_take_profit_usdt": None,
        "risk_reward_ratio": None,
        "max_loss_usdt": None,
    }


def _validate_r248_record(record: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not record:
        return {"valid": False, "errors": ["r248_stop_take_profit_source_missing"], "warnings": []}
    source = _r248_source(record)
    selected = {
        "entry_reference_price": source.get("reference_price"),
        "rounded_stop_price": source.get("stop_price"),
        "rounded_take_profit_price": source.get("take_profit_price"),
        "source_valid": True,
        "blocked_by": [],
    }
    direction = validate_short_stop_take_profit_levels(selected)
    errors.extend(str(item) for item in direction.get("errors") or [])
    warnings.extend(str(item) for item in direction.get("warnings") or [])
    if _number(source.get("quantity")) is None:
        errors.append("r248_quantity_missing")
    if source.get("requires_future_readonly_mark_price_refresh_before_submit") is not True:
        warnings.append("r248_future_readonly_refresh_flag_missing")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def _validate_r242_record(record: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not record:
        return {"valid": False, "errors": ["r242_readonly_reference_missing"], "warnings": []}
    result = record.get("binance_readonly_result") if isinstance(record.get("binance_readonly_result"), Mapping) else {}
    precision = result.get("precision_snapshot") if isinstance(result.get("precision_snapshot"), Mapping) else {}
    mark = result.get("mark_price_snapshot") if isinstance(result.get("mark_price_snapshot"), Mapping) else {}
    if record.get("readonly_fetch_performed") is not True:
        errors.append("r242_readonly_fetch_not_performed")
    if precision.get("found") is not True:
        errors.append("r242_precision_missing")
    if mark.get("found") is not True:
        errors.append("r242_mark_price_missing")
    if result.get("order_endpoint_called") is not False:
        errors.append("r242_order_endpoint_called")
    if result.get("account_endpoint_called") is not False:
        errors.append("r242_account_endpoint_called")
    if result.get("signed_request_created") is not False:
        errors.append("r242_signed_request_created")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": []}


def _signed_request_artifact(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = record.get("signed_request_artifact")
    return _sanitize(dict(artifact)) if isinstance(artifact, Mapping) else {}


def _executable_payload_artifact(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = record.get("executable_payload_artifact")
    return _sanitize(dict(artifact)) if isinstance(artifact, Mapping) else {}


def _r248_source(record: Mapping[str, Any]) -> dict[str, Any]:
    source = record.get("stop_take_profit_source") if isinstance(record.get("stop_take_profit_source"), Mapping) else {}
    selected = record.get("selected_stop_take_profit_source") if isinstance(record.get("selected_stop_take_profit_source"), Mapping) else {}
    risk = record.get("risk_reward_validation") if isinstance(record.get("risk_reward_validation"), Mapping) else {}
    return _sanitize(
        {
            "symbol": source.get("symbol") or "BTCUSDT",
            "reference_price": source.get("reference_price") or selected.get("entry_reference_price"),
            "stop_price": source.get("stop_price") or source.get("final_stop_price") or selected.get("rounded_stop_price"),
            "take_profit_price": source.get("take_profit_price") or source.get("final_take_profit_price") or selected.get("rounded_take_profit_price"),
            "quantity": source.get("quantity") or risk.get("quantity_preview"),
            "estimated_loss_at_stop_usdt": source.get("estimated_loss_at_stop_usdt") or risk.get("loss_usdt_preview"),
            "estimated_reward_at_take_profit_usdt": source.get("estimated_reward_at_take_profit_usdt") or risk.get("reward_usdt_preview"),
            "risk_reward_ratio": source.get("risk_reward_ratio") or risk.get("risk_reward_ratio_preview"),
            "max_loss_usdt": source.get("max_loss_usdt") or risk.get("max_loss_usdt"),
            "requires_future_readonly_mark_price_refresh_before_submit": source.get("requires_future_readonly_mark_price_refresh_before_submit"),
        }
    )


def _record_matches_lane(record: Mapping[str, Any], official_lane_key: str) -> bool:
    target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    if target.get("official_lane_key") is not None:
        return str(target.get("official_lane_key")) == official_lane_key
    for key in ("signed_request_artifact", "executable_payload_artifact", "stop_take_profit_source"):
        value = record.get(key)
        if isinstance(value, Mapping) and value.get("official_lane_key") is not None:
            return str(value.get("official_lane_key")) == official_lane_key
    return True


def _recommended_next_operator_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("recorded") is True:
        return "RUN_R253_FINAL_READONLY_REFRESH"
    if matrix.get("runtime_source_signed_request_ready") is True and matrix.get("signed_request_valid") is True:
        return "REVIEW_R252_SUBMIT_READINESS"
    if matrix.get("blocked_by"):
        return "FIX_BLOCKER"
    return "WAIT"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("recorded") is True:
        return "Implement R253 final public read-only mark-price/precision refresh gate; compare fresh context to signed artifact before any submit gate."
    if matrix.get("runtime_source_signed_request_ready") is True and matrix.get("signed_request_valid") is True:
        return "Record R252 preview if operator wants the readonly R253 handoff artifact; do not submit from R252."
    return "Repair missing or invalid R251E/R251/R249/R248/R242 local artifacts before R253."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "kill switch disable",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _lane_parts(official_lane_key: str) -> tuple[str, str, str, str]:
    parts = official_lane_key.split("|")
    if len(parts) != 4:
        return "BTCUSDT", "8m", "short", "ladder_close_50_618"
    return parts[0], parts[1], parts[2], parts[3]


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_number(value: float | None, places: int) -> float | None:
    return round(value, places) if value is not None else None


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values))


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
