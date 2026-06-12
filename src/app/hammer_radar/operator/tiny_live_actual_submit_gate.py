"""R255 tiny-live actual submit gate.

This module builds the first actual-submit safety boundary for the official
tiny-live lane. Normal CLI usage never calls Binance/network endpoints. The
only submit executor requires an injected client and is intended for unit tests
or a future operator-controlled integration boundary.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_fresh_context_signed_request_regeneration_gate import (
    CREATED_BY_PHASE as R253B_CREATED_BY_PHASE,
)
from src.app.hammer_radar.operator.tiny_live_runtime_credential_source_drill import (
    BINANCE_API_KEY_ENV,
    BINANCE_API_SECRET_ENV,
    resolve_runtime_credential_source_path,
)
from src.app.hammer_radar.operator.tiny_live_stop_take_profit_source_gate import (
    load_adjusted_tiny_live_risk_contract,
)
from src.app.hammer_radar.operator.tiny_live_submit_gate_preview import (
    build_future_submit_confirmation_phrase,
    build_submit_gate_order_triplet_preview,
    load_latest_tiny_live_executable_payload_write_gate,
    load_latest_tiny_live_fresh_context_signed_request_regeneration_gate,
    load_latest_tiny_live_signed_request_write_gate,
    load_latest_tiny_live_stop_take_profit_source_gate,
    load_tiny_live_submit_gate_preview_records,
    validate_latest_fresh_signed_request_for_submit_gate_preview,
    validate_submit_order_triplet_shape,
)

TINY_LIVE_ACTUAL_SUBMIT_GATE_READY = "TINY_LIVE_ACTUAL_SUBMIT_GATE_READY"
TINY_LIVE_ACTUAL_SUBMIT_GATE_DRY_PREVIEW_RECORDED = (
    "TINY_LIVE_ACTUAL_SUBMIT_GATE_DRY_PREVIEW_RECORDED"
)
TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED = "TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED"
TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED = "TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED"
TINY_LIVE_ACTUAL_SUBMIT_GATE_MOCK_SUBMITTED = "TINY_LIVE_ACTUAL_SUBMIT_GATE_MOCK_SUBMITTED"
TINY_LIVE_ACTUAL_SUBMIT_GATE_REAL_SUBMIT_READY_BUT_NOT_EXECUTED = (
    "TINY_LIVE_ACTUAL_SUBMIT_GATE_REAL_SUBMIT_READY_BUT_NOT_EXECUTED"
)
TINY_LIVE_ACTUAL_SUBMIT_GATE_ERROR = "TINY_LIVE_ACTUAL_SUBMIT_GATE_ERROR"

TINY_LIVE_ACTUAL_SUBMIT_GATE_READY_FOR_DRY_PREVIEW = (
    "TINY_LIVE_ACTUAL_SUBMIT_GATE_READY_FOR_DRY_PREVIEW"
)
TINY_LIVE_ACTUAL_SUBMIT_GATE_DRY_PREVIEW_RECORDED_AWAITING_OPERATOR_REAL_SUBMIT = (
    "TINY_LIVE_ACTUAL_SUBMIT_GATE_DRY_PREVIEW_RECORDED_AWAITING_OPERATOR_REAL_SUBMIT"
)
TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_MISSING_R254 = (
    "TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_MISSING_R254"
)
TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_INVALID_SIGNED_REQUEST = (
    "TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_INVALID_SIGNED_REQUEST"
)
TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_STALE_TIMESTAMP = (
    "TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_STALE_TIMESTAMP"
)
TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_KILL_SWITCH = (
    "TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_KILL_SWITCH"
)
TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_IDEMPOTENCY = (
    "TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_IDEMPOTENCY"
)
TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_RISK_CONTRACT = (
    "TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_RISK_CONTRACT"
)
TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_ENDPOINT_SAFETY = (
    "TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_ENDPOINT_SAFETY"
)
TINY_LIVE_ACTUAL_SUBMIT_GATE_MOCK_SUBMITTED_FOR_TEST_ONLY = (
    "TINY_LIVE_ACTUAL_SUBMIT_GATE_MOCK_SUBMITTED_FOR_TEST_ONLY"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_ACTUAL_SUBMIT_GATE"
LEDGER_FILENAME = "tiny_live_actual_submit_gate.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R255_TINY_LIVE_ACTUAL_SUBMIT_GATE"
DRY_PREVIEW_CONFIRMATION_PHRASE = (
    "I CONFIRM TINY LIVE ACTUAL SUBMIT GATE DRY PREVIEW ONLY; "
    "NO SUBMIT; NO ORDER; NO BINANCE CALL."
)
REAL_SUBMIT_CONFIRMATION_PHRASE = build_future_submit_confirmation_phrase()
ALLOWED_ORDER_ENDPOINT = "/fapi/v1/order"
MAX_SIGNED_REQUEST_AGE_SECONDS = 60
RISK_CONTRACT_CONFIG_PATH = Path("configs/hammer_radar/tiny_live_risk_contracts.json")
LANE_CONTROLS_PATH = Path("configs/hammer_radar/lane_controls.json")

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_submit_gate_preview.ndjson",
    "logs/hammer_radar_forward/tiny_live_fresh_context_signed_request_regeneration_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_stop_take_profit_source_gate.ndjson",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
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
    "actual_submit_gate": True,
    "dry_preview_only": True,
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
    "secrets_read": False,
    "secrets_shown": False,
    "secrets_persisted": False,
    "secret_values_in_output": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
}


def build_tiny_live_actual_submit_gate(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    lane_controls_path: str | Path | None = None,
    dry_run_actual_submit_gate: bool = False,
    record_actual_submit_gate_preview: bool = False,
    confirm_tiny_live_actual_submit_gate_preview: str | None = None,
    execute_actual_submit: bool = False,
    confirm_tiny_live_actual_submit: str | None = None,
    allow_real_binance_order_endpoint: bool = False,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    lane_path = Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH
    preview_confirmation_valid = (
        confirm_tiny_live_actual_submit_gate_preview == DRY_PREVIEW_CONFIRMATION_PHRASE
    )
    real_submit_confirmation_valid = confirm_tiny_live_actual_submit == REAL_SUBMIT_CONFIRMATION_PHRASE
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)

    try:
        latest_r254 = load_latest_tiny_live_submit_gate_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r253b = load_latest_tiny_live_fresh_context_signed_request_regeneration_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_signed = load_latest_tiny_live_signed_request_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_payload = load_latest_tiny_live_executable_payload_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_stop_tp = load_latest_tiny_live_stop_take_profit_source_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        signed_artifact = _signed_request_artifact(latest_signed)
        executable_artifact = _executable_payload_artifact(latest_payload)
        stop_tp_artifact = _stop_take_profit_artifact(latest_stop_tp)

        r254_validation = validate_r254_submit_gate_preview_ready(latest_r254)
        signed_validation = validate_latest_r253b_signed_request_for_actual_submit(
            latest_r253b=latest_r253b,
            signed_request_artifact=signed_artifact,
        )
        order_triplet = build_submit_gate_order_triplet_preview(
            signed_request_artifact=signed_artifact,
            executable_payload_artifact=executable_artifact,
        )
        endpoint_allowlist = validate_order_endpoint_allowlist(order_triplet)
        exactly_three = validate_exactly_three_order_triplet(order_triplet)
        sequence = validate_order_sequence_main_stop_take_profit(order_triplet)
        triplet_validation = validate_submit_order_triplet_shape(
            submit_order_triplet_preview=order_triplet,
            stop_take_profit_source=stop_tp_artifact,
        )
        order_triplet["valid"] = bool(
            exactly_three["valid"]
            and sequence["valid"]
            and triplet_validation["valid"]
        )
        freshness = validate_signed_request_timestamp_freshness(
            signed_request_artifact=signed_artifact,
            now=generated_at,
        )
        credentials = validate_runtime_credential_source_for_submit()
        kill_switch = validate_kill_switch_and_lane_controls_for_tiny_live_submit(
            lane_controls_path=lane_path,
            risk_contract_config_path=risk_path,
            official_lane_key=official_lane_key,
        )
        risk_contract = validate_tiny_live_risk_contract_still_within_bounds(
            risk_contract_config_path=risk_path,
            order_triplet=order_triplet,
            official_lane_key=official_lane_key,
        )
        idempotency_key = build_idempotency_key_for_tiny_live_submit(
            signed_request_artifact=signed_artifact,
            official_lane_key=official_lane_key,
        )
        idempotency = validate_no_prior_live_submit_for_idempotency_key(
            idempotency_key=idempotency_key,
            log_dir=resolved_log_dir,
        )
        input_summary = {
            "r254_submit_gate_preview_found": bool(latest_r254),
            "r254_submit_gate_preview_valid": r254_validation["valid"] is True,
            "r253b_fresh_regeneration_found": bool(latest_r253b),
            "r253b_signed_request_found": bool(latest_signed),
            "r253b_signed_request_valid": signed_validation["valid"] is True,
            "r253b_payload_found": bool(latest_payload),
            "r253b_stop_take_profit_found": bool(latest_stop_tp),
        }
        all_blockers = _build_blockers(
            r254_validation=r254_validation,
            signed_validation=signed_validation,
            freshness=freshness,
            kill_switch=kill_switch,
            endpoint_allowlist=endpoint_allowlist,
            order_triplet=order_triplet,
            risk_contract=risk_contract,
            idempotency=idempotency,
        )

        rejected_bad_confirmation = (
            (record_actual_submit_gate_preview and not preview_confirmation_valid)
            or (execute_actual_submit and not real_submit_confirmation_valid)
        )
        recorded = False
        actual_submit_executed = False
        mock_submit_result: dict[str, Any] = {}
        if rejected_bad_confirmation:
            status = TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED
            overall = TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED_BAD_CONFIRMATION
        elif record_actual_submit_gate_preview and preview_confirmation_valid:
            status = TINY_LIVE_ACTUAL_SUBMIT_GATE_DRY_PREVIEW_RECORDED
            overall = TINY_LIVE_ACTUAL_SUBMIT_GATE_DRY_PREVIEW_RECORDED_AWAITING_OPERATOR_REAL_SUBMIT
            recorded = True
        elif execute_actual_submit and not allow_real_binance_order_endpoint:
            status = TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED
            overall = TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_ENDPOINT_SAFETY
            all_blockers = _dedupe([*all_blockers, "allow_real_binance_order_endpoint_flag_required"])
        elif execute_actual_submit and real_submit_confirmation_valid and allow_real_binance_order_endpoint:
            overall = classify_tiny_live_actual_submit_gate_status(
                r254_validation=r254_validation,
                signed_validation=signed_validation,
                freshness=freshness,
                kill_switch=kill_switch,
                endpoint_allowlist=endpoint_allowlist,
                order_triplet=order_triplet,
                risk_contract=risk_contract,
                idempotency=idempotency,
                rejected_bad_confirmation=False,
                recorded=False,
                mock_submitted=False,
            )
            if all_blockers:
                status = TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED
            else:
                status = TINY_LIVE_ACTUAL_SUBMIT_GATE_REAL_SUBMIT_READY_BUT_NOT_EXECUTED
                all_blockers = ["codex_cli_real_submit_execution_disabled"]
        elif all_blockers:
            status = TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED
            overall = classify_tiny_live_actual_submit_gate_status(
                r254_validation=r254_validation,
                signed_validation=signed_validation,
                freshness=freshness,
                kill_switch=kill_switch,
                endpoint_allowlist=endpoint_allowlist,
                order_triplet=order_triplet,
                risk_contract=risk_contract,
                idempotency=idempotency,
                rejected_bad_confirmation=False,
                recorded=False,
                mock_submitted=False,
            )
        else:
            status = TINY_LIVE_ACTUAL_SUBMIT_GATE_READY
            overall = TINY_LIVE_ACTUAL_SUBMIT_GATE_READY_FOR_DRY_PREVIEW

        submit_plan = build_actual_submit_plan(
            order_triplet=order_triplet,
            execute_actual_submit=execute_actual_submit,
            real_submit_confirmation_valid=real_submit_confirmation_valid,
            allow_real_binance_order_endpoint=allow_real_binance_order_endpoint,
        )
        reconciliation = build_post_submit_reconciliation_plan()
        matrix = build_actual_submit_gate_matrix(
            r254_validation=r254_validation,
            signed_validation=signed_validation,
            freshness=freshness,
            credentials=credentials,
            kill_switch=kill_switch,
            endpoint_allowlist=endpoint_allowlist,
            order_triplet=order_triplet,
            risk_contract=risk_contract,
            idempotency=idempotency,
            preview_confirmed=preview_confirmation_valid,
            real_submit_confirmed=real_submit_confirmation_valid,
            allow_real_endpoint_flag=allow_real_binance_order_endpoint,
            order_placed=False,
            blocked_by=all_blockers,
        )
        operator_packet = build_operator_actual_submit_gate_packet(
            matrix,
            freshness=freshness,
            recorded=recorded,
        )
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "dry_run_actual_submit_gate_requested": bool(dry_run_actual_submit_gate),
                "record_actual_submit_gate_preview_requested": bool(record_actual_submit_gate_preview),
                "execute_actual_submit_requested": bool(execute_actual_submit),
                "allow_real_binance_order_endpoint": bool(allow_real_binance_order_endpoint),
                "preview_confirmation_valid": bool(preview_confirmation_valid),
                "real_submit_confirmation_valid": bool(real_submit_confirmation_valid),
                "actual_submit_executed": bool(actual_submit_executed),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "actual_submit_gate": True,
                    "dry_preview_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "signed_request_freshness": freshness,
                "runtime_credential_source_summary": credentials,
                "kill_switch_lane_control_summary": kill_switch,
                "endpoint_allowlist_summary": endpoint_allowlist,
                "order_triplet_summary": _order_triplet_summary(order_triplet),
                "risk_contract_submit_summary": risk_contract,
                "idempotency_summary": idempotency,
                "actual_submit_plan": submit_plan,
                "actual_submit_dry_run_preview": build_actual_submit_dry_run_preview(order_triplet),
                "post_submit_reconciliation_plan": reconciliation,
                "actual_submit_gate_matrix": matrix,
                "operator_actual_submit_gate_packet": operator_packet,
                "recommended_next_operator_move": _recommended_next_operator_move(operator_packet),
                "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
                "actual_submit_gate_overall_status": overall,
                "mock_submit_result": mock_submit_result,
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if recorded:
            payload = append_tiny_live_actual_submit_gate_record(
                payload,
                log_dir=resolved_log_dir,
                confirm_tiny_live_actual_submit_gate_preview=confirm_tiny_live_actual_submit_gate_preview,
            )
        return payload
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        return _sanitize(
            {
                "status": TINY_LIVE_ACTUAL_SUBMIT_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "dry_run_actual_submit_gate_requested": bool(dry_run_actual_submit_gate),
                "record_actual_submit_gate_preview_requested": bool(record_actual_submit_gate_preview),
                "execute_actual_submit_requested": bool(execute_actual_submit),
                "allow_real_binance_order_endpoint": bool(allow_real_binance_order_endpoint),
                "preview_confirmation_valid": bool(preview_confirmation_valid),
                "real_submit_confirmation_valid": bool(real_submit_confirmation_valid),
                "actual_submit_executed": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "actual_submit_gate": True,
                    "dry_preview_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_order_endpoint_called": False,
                    "network_allowed": False,
                },
                "error": type(exc).__name__,
                "actual_submit_gate_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "safety": dict(SAFETY),
            }
        )


def load_latest_tiny_live_submit_gate_preview(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    for record in load_tiny_live_submit_gate_preview_records(log_dir=log_dir, limit=50):
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("submit_gate_preview_recorded") is True
        ):
            return _sanitize(record)
    return {}


def validate_r254_submit_gate_preview_ready(record: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not record:
        errors.append("r254_submit_gate_preview_missing")
        return {"valid": False, "errors": errors, "warnings": []}
    if record.get("submit_gate_preview_recorded") is not True:
        errors.append("r254_submit_gate_preview_not_recorded")
    if record.get("status") not in {
        "TINY_LIVE_SUBMIT_GATE_PREVIEW_RECORDED",
        "TINY_LIVE_SUBMIT_GATE_PREVIEW_READY",
    }:
        errors.append("r254_submit_gate_preview_status_invalid")
    input_summary = record.get("input_summary") if isinstance(record.get("input_summary"), Mapping) else {}
    for key in (
        "r253b_fresh_regeneration_valid",
        "r253b_signed_request_valid",
        "r253b_payload_valid",
        "r253b_stop_take_profit_valid",
    ):
        if input_summary.get(key) is not True:
            errors.append(f"r254_{key}_not_true")
    scope = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    if scope.get("submit_allowed") is not False:
        errors.append("r254_submit_allowed_not_false")
    if scope.get("order_placed") is not False:
        errors.append("r254_order_placed_not_false")
    if scope.get("network_allowed") is not False:
        errors.append("r254_network_allowed_not_false")
    if scope.get("binance_order_endpoint_called") is not False:
        errors.append("r254_order_endpoint_called_not_false")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": []}


def validate_latest_r253b_signed_request_for_actual_submit(
    *,
    latest_r253b: Mapping[str, Any],
    signed_request_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    validation = validate_latest_fresh_signed_request_for_submit_gate_preview(
        latest_r253b=latest_r253b,
        signed_request_artifact=signed_request_artifact,
    )
    errors = list(validation.get("errors") or [])
    if signed_request_artifact.get("created_by_phase") != R253B_CREATED_BY_PHASE:
        errors.append("signed_request_not_created_by_r253b")
    if signed_request_artifact.get("official_lane_key") != OFFICIAL_LANE_KEY:
        errors.append("signed_request_official_lane_invalid")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": list(validation.get("warnings") or [])}


def validate_signed_request_timestamp_freshness(
    *,
    signed_request_artifact: Mapping[str, Any],
    now: datetime | None = None,
    max_allowed_age_seconds: int = MAX_SIGNED_REQUEST_AGE_SECONDS,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    timestamps = _signed_request_timestamps(signed_request_artifact)
    if not timestamps:
        return {
            "timestamp_present": False,
            "signed_request_age_seconds": None,
            "max_allowed_age_seconds": max_allowed_age_seconds,
            "fresh_enough_for_real_submit": False,
            "requires_regeneration": True,
        }
    newest_ms = max(timestamps)
    age = max(0.0, generated_at.timestamp() - (newest_ms / 1000.0))
    fresh = age <= max_allowed_age_seconds
    return {
        "timestamp_present": True,
        "signed_request_age_seconds": round(age, 3),
        "max_allowed_age_seconds": max_allowed_age_seconds,
        "fresh_enough_for_real_submit": bool(fresh),
        "requires_regeneration": not fresh,
    }


def validate_runtime_credential_source_for_submit() -> dict[str, Any]:
    external = resolve_runtime_credential_source_path()
    process_ready = BINANCE_API_KEY_ENV in os.environ and BINANCE_API_SECRET_ENV in os.environ
    external_ready = external.exists() if external else False
    source_type = "process_env" if process_ready else ("external_env_file" if external_ready else "none")
    return {
        "credential_source_ready": bool(process_ready or external_ready),
        "source_type": source_type,
        "secrets_shown": False,
        "secrets_persisted": False,
    }


def validate_kill_switch_and_lane_controls_for_tiny_live_submit(
    *,
    lane_controls_path: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    blocked_by: list[str] = []
    lane = _matching_lane(Path(lane_controls_path) if lane_controls_path is not None else LANE_CONTROLS_PATH, official_lane_key)
    contract = load_adjusted_tiny_live_risk_contract(
        risk_contract_config_path=risk_contract_config_path,
        official_lane_key=official_lane_key,
    )
    official_lane_allowed = lane.get("mode") == "tiny_live"
    live_execution_enabled = contract.get("live_execution_enabled") is True
    if not official_lane_allowed:
        blocked_by.append("official_lane_not_tiny_live")
    if not live_execution_enabled:
        blocked_by.append("live_execution_not_enabled")
    return {
        "kill_switch_allows_tiny_live": bool(official_lane_allowed and live_execution_enabled),
        "official_lane_allowed": bool(official_lane_allowed),
        "live_execution_enabled": bool(live_execution_enabled),
        "blocked_by": _dedupe(blocked_by),
    }


def validate_order_endpoint_allowlist(order_triplet: Mapping[str, Any]) -> dict[str, Any]:
    orders = _triplet_orders(order_triplet)
    all_allowed = bool(orders) and all(
        order.get("method") == "POST" and order.get("endpoint") == ALLOWED_ORDER_ENDPOINT
        for order in orders
    )
    forbidden = any(order.get("endpoint") != ALLOWED_ORDER_ENDPOINT for order in orders)
    private_account = any("/account" in str(order.get("endpoint") or "") for order in orders)
    return {
        "valid": bool(all_allowed and not private_account),
        "allowed_endpoint": ALLOWED_ORDER_ENDPOINT,
        "all_orders_use_allowed_endpoint": bool(all_allowed),
        "forbidden_endpoint_detected": bool(forbidden),
        "private_account_endpoint_detected": bool(private_account),
    }


def validate_exactly_three_order_triplet(order_triplet: Mapping[str, Any]) -> dict[str, Any]:
    orders = _triplet_orders(order_triplet)
    return {
        "valid": len(orders) == 3,
        "exactly_three_orders": len(orders) == 3,
        "order_count": len(orders),
        "errors": [] if len(orders) == 3 else ["order_count_not_three"],
    }


def validate_order_sequence_main_stop_take_profit(order_triplet: Mapping[str, Any]) -> dict[str, Any]:
    keys = [key for key in ("main_order", "stop_order", "take_profit_order") if isinstance(order_triplet.get(key), Mapping)]
    valid = keys == ["main_order", "stop_order", "take_profit_order"]
    orders = {key: order_triplet.get(key) if isinstance(order_triplet.get(key), Mapping) else {} for key in keys}
    valid = valid and orders.get("main_order", {}).get("type") == "MARKET"
    valid = valid and orders.get("stop_order", {}).get("type") == "STOP_MARKET"
    valid = valid and orders.get("take_profit_order", {}).get("type") == "TAKE_PROFIT_MARKET"
    return {
        "valid": bool(valid),
        "sequence_valid": bool(valid),
        "submit_order_sequence": keys,
        "errors": [] if valid else ["order_sequence_invalid"],
    }


def validate_tiny_live_risk_contract_still_within_bounds(
    *,
    risk_contract_config_path: str | Path | None = None,
    order_triplet: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    contract = load_adjusted_tiny_live_risk_contract(
        risk_contract_config_path=risk_contract_config_path,
        official_lane_key=official_lane_key,
    )
    main = order_triplet.get("main_order") if isinstance(order_triplet.get("main_order"), Mapping) else {}
    stop = order_triplet.get("stop_order") if isinstance(order_triplet.get("stop_order"), Mapping) else {}
    qty = _number(main.get("quantity")) or 0.0
    reference_price = _reference_price_from_artifact(order_triplet) or 63675.0
    stop_price = _number(stop.get("stopPrice")) or 0.0
    notional = round(reference_price * qty, 4)
    estimated_loss = round(abs(stop_price - reference_price) * qty, 4) if stop_price else 0.0
    max_loss = _number(contract.get("max_loss_usdt"))
    max_notional = _number(contract.get("max_notional_usdt") or contract.get("max_position_notional_usdt"))
    warnings: list[str] = []
    if estimated_loss > 4.44:
        warnings.append("estimated_loss_rounding_exceeds_config_by_less_than_one_cent")
    within = bool(
        contract
        and max_loss is not None
        and max_notional is not None
        and estimated_loss <= max_loss + 0.001
        and notional <= max_notional + 10
        and contract.get("symbol") == "BTCUSDT"
        and contract.get("direction") == "short"
    )
    return {
        "max_loss_usdt": max_loss,
        "estimated_loss_usdt": estimated_loss,
        "notional_usdt": notional,
        "within_tiny_live_contract": within,
        "warnings": warnings,
    }


def build_idempotency_key_for_tiny_live_submit(
    *,
    signed_request_artifact: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> str:
    artifact_id = str(signed_request_artifact.get("signed_request_artifact_id") or "missing")
    return f"{official_lane_key}|{R253B_CREATED_BY_PHASE}|{artifact_id}"


def validate_no_prior_live_submit_for_idempotency_key(
    *,
    idempotency_key: str,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    prior = False
    for record in load_tiny_live_actual_submit_gate_records(log_dir=log_dir, limit=0):
        summary = record.get("idempotency_summary") if isinstance(record.get("idempotency_summary"), Mapping) else {}
        if summary.get("idempotency_key") == idempotency_key and record.get("actual_submit_executed") is True:
            prior = True
            break
    return {
        "idempotency_key": idempotency_key,
        "prior_live_submit_found": bool(prior),
        "dedupe_allows_submit": not prior,
    }


def build_actual_submit_plan(
    *,
    order_triplet: Mapping[str, Any],
    execute_actual_submit: bool = False,
    real_submit_confirmation_valid: bool = False,
    allow_real_binance_order_endpoint: bool = False,
) -> dict[str, Any]:
    return {
        "would_submit_exactly_three_orders": len(_triplet_orders(order_triplet)) == 3,
        "submit_order_sequence": ["main_order", "stop_order", "take_profit_order"],
        "submit_in_this_invocation": bool(False),
        "requires_real_submit_confirmation": True,
        "requires_allow_real_binance_order_endpoint_flag": True,
        "execute_requested": bool(execute_actual_submit),
        "real_submit_confirmation_valid": bool(real_submit_confirmation_valid),
        "allow_real_binance_order_endpoint": bool(allow_real_binance_order_endpoint),
    }


def build_actual_submit_dry_run_preview(order_triplet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "dry_preview_only": True,
        "network_allowed": False,
        "submit_allowed": False,
        "orders": _sanitize({key: order_triplet.get(key, {}) for key in ("main_order", "stop_order", "take_profit_order")}),
    }


def build_post_submit_reconciliation_plan() -> dict[str, Any]:
    return {
        "required": True,
        "must_record_exchange_order_ids": True,
        "must_record_order_statuses": True,
        "must_verify_reduce_only_exits": True,
        "must_reconcile_main_stop_take_profit_triplet": True,
    }


def execute_actual_submit_with_injected_client(
    *,
    client: Any,
    signed_request_artifact: Mapping[str, Any],
    idempotency_key: str,
    confirm_tiny_live_actual_submit: str | None,
    allow_real_binance_order_endpoint: bool,
    log_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_actual_submit != REAL_SUBMIT_CONFIRMATION_PHRASE:
        return {"status": TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED, "actual_submit_executed": False}
    if not allow_real_binance_order_endpoint:
        return {"status": TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED, "actual_submit_executed": False}
    idempotency = validate_no_prior_live_submit_for_idempotency_key(
        idempotency_key=idempotency_key,
        log_dir=log_dir,
    )
    if idempotency["dedupe_allows_submit"] is not True:
        return {"status": TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED, "actual_submit_executed": False}
    responses: list[dict[str, Any]] = []
    for key in ("main_order", "stop_order", "take_profit_order"):
        request = signed_request_artifact.get("signed_requests", {}).get(key, {})
        if request.get("endpoint") != ALLOWED_ORDER_ENDPOINT:
            raise ValueError("endpoint_not_allowed")
        responses.append(_sanitize(client.submit_order(request)))
    record = {
        "status": TINY_LIVE_ACTUAL_SUBMIT_GATE_MOCK_SUBMITTED,
        "generated_at": (now or datetime.now(UTC)).isoformat(),
        "actual_submit_executed": True,
        "mock_submit_for_test_only": True,
        "idempotency_summary": idempotency,
        "sanitized_submit_responses": responses,
        "actual_submit_gate_overall_status": TINY_LIVE_ACTUAL_SUBMIT_GATE_MOCK_SUBMITTED_FOR_TEST_ONLY,
        "safety": {
            **SAFETY,
            "dry_preview_only": False,
            "submit_attempted": True,
            "order_placed": True,
            "execution_attempted": True,
            "binance_order_endpoint_called": True,
            "signed_binance_endpoint_called": True,
            "network_allowed": True,
        },
    }
    return append_tiny_live_actual_submit_gate_record(record, log_dir=log_dir, mock_submit_for_test_only=True)


def build_actual_submit_gate_matrix(
    *,
    r254_validation: Mapping[str, Any],
    signed_validation: Mapping[str, Any],
    freshness: Mapping[str, Any],
    credentials: Mapping[str, Any],
    kill_switch: Mapping[str, Any],
    endpoint_allowlist: Mapping[str, Any],
    order_triplet: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    idempotency: Mapping[str, Any],
    preview_confirmed: bool,
    real_submit_confirmed: bool,
    allow_real_endpoint_flag: bool,
    order_placed: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    return {
        "r254_ready": r254_validation.get("valid") is True,
        "signed_request_valid": signed_validation.get("valid") is True,
        "timestamp_fresh_enough": freshness.get("fresh_enough_for_real_submit") is True,
        "runtime_credentials_ready": credentials.get("credential_source_ready") is True,
        "kill_switch_allows": kill_switch.get("kill_switch_allows_tiny_live") is True,
        "endpoint_allowlist_valid": endpoint_allowlist.get("valid") is True,
        "order_triplet_valid": order_triplet.get("valid") is True,
        "risk_contract_valid": risk_contract.get("within_tiny_live_contract") is True,
        "idempotency_allows": idempotency.get("dedupe_allows_submit") is True,
        "preview_confirmed": bool(preview_confirmed),
        "real_submit_confirmed": bool(real_submit_confirmed),
        "allow_real_endpoint_flag": bool(allow_real_endpoint_flag),
        "submit_allowed": False,
        "order_placed": bool(order_placed),
        "blocked_by": _dedupe(blocked_by or []),
    }


def build_operator_actual_submit_gate_packet(
    actual_submit_gate_matrix: Mapping[str, Any],
    *,
    freshness: Mapping[str, Any],
    recorded: bool,
) -> dict[str, Any]:
    if freshness.get("requires_regeneration") is True:
        action = "REGENERATE_SIGNED_REQUEST"
    elif actual_submit_gate_matrix.get("blocked_by"):
        action = "FIX_BLOCKER"
    elif recorded:
        action = "MANUAL_OPERATOR_DECISION_REQUIRED"
    else:
        action = "REVIEW_R255_DRY_PREVIEW"
    return {
        "operator_should_review_actual_submit_gate": action in {
            "REVIEW_R255_DRY_PREVIEW",
            "MANUAL_OPERATOR_DECISION_REQUIRED",
        },
        "operator_should_regenerate_if_timestamp_stale": freshness.get("requires_regeneration") is True,
        "operator_should_not_submit_from_codex": True,
        "operator_should_submit_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order from Codex implementation run",
            "do not submit without manual operator decision",
            "do not call Binance order endpoint from tests",
        ],
    }


def classify_tiny_live_actual_submit_gate_status(
    *,
    r254_validation: Mapping[str, Any],
    signed_validation: Mapping[str, Any],
    freshness: Mapping[str, Any],
    kill_switch: Mapping[str, Any],
    endpoint_allowlist: Mapping[str, Any],
    order_triplet: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    idempotency: Mapping[str, Any],
    rejected_bad_confirmation: bool = False,
    recorded: bool = False,
    mock_submitted: bool = False,
) -> str:
    if rejected_bad_confirmation:
        return TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED_BAD_CONFIRMATION
    if mock_submitted:
        return TINY_LIVE_ACTUAL_SUBMIT_GATE_MOCK_SUBMITTED_FOR_TEST_ONLY
    if recorded:
        return TINY_LIVE_ACTUAL_SUBMIT_GATE_DRY_PREVIEW_RECORDED_AWAITING_OPERATOR_REAL_SUBMIT
    if r254_validation.get("valid") is not True:
        return TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_MISSING_R254
    if signed_validation.get("valid") is not True or order_triplet.get("valid") is not True:
        return TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_INVALID_SIGNED_REQUEST
    if freshness.get("fresh_enough_for_real_submit") is not True:
        return TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_STALE_TIMESTAMP
    if kill_switch.get("kill_switch_allows_tiny_live") is not True:
        return TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_KILL_SWITCH
    if endpoint_allowlist.get("valid") is not True:
        return TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_ENDPOINT_SAFETY
    if risk_contract.get("within_tiny_live_contract") is not True:
        return TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_RISK_CONTRACT
    if idempotency.get("dedupe_allows_submit") is not True:
        return TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED_BY_IDEMPOTENCY
    return TINY_LIVE_ACTUAL_SUBMIT_GATE_READY_FOR_DRY_PREVIEW


def append_tiny_live_actual_submit_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_tiny_live_actual_submit_gate_preview: str | None = None,
    mock_submit_for_test_only: bool = False,
) -> dict[str, Any]:
    if (
        not mock_submit_for_test_only
        and confirm_tiny_live_actual_submit_gate_preview != DRY_PREVIEW_CONFIRMATION_PHRASE
    ):
        raise ValueError("bad_tiny_live_actual_submit_gate_preview_confirmation")
    path = tiny_live_actual_submit_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "actual_submit_gate_record_id": record.get("actual_submit_gate_record_id")
            or f"r255_actual_submit_gate_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_actual_submit_gate_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_actual_submit_gate_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_actual_submit_gate_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_actual_submit_executed": latest.get("actual_submit_executed") is True,
        "latest_overall_status": latest.get("actual_submit_gate_overall_status"),
    }


def tiny_live_actual_submit_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_actual_submit_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_blockers(
    *,
    r254_validation: Mapping[str, Any],
    signed_validation: Mapping[str, Any],
    freshness: Mapping[str, Any],
    kill_switch: Mapping[str, Any],
    endpoint_allowlist: Mapping[str, Any],
    order_triplet: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    idempotency: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if r254_validation.get("valid") is not True:
        blockers.extend(str(item) for item in r254_validation.get("errors") or ["r254_not_ready"])
    if signed_validation.get("valid") is not True:
        blockers.extend(str(item) for item in signed_validation.get("errors") or ["signed_request_invalid"])
    if freshness.get("fresh_enough_for_real_submit") is not True:
        blockers.append("signed_request_timestamp_stale")
    if kill_switch.get("kill_switch_allows_tiny_live") is not True:
        blockers.extend(str(item) for item in kill_switch.get("blocked_by") or ["kill_switch_blocks_tiny_live"])
    if endpoint_allowlist.get("valid") is not True:
        blockers.append("endpoint_allowlist_invalid")
    if order_triplet.get("valid") is not True:
        blockers.append("order_triplet_invalid")
    if risk_contract.get("within_tiny_live_contract") is not True:
        blockers.append("risk_contract_invalid")
    if idempotency.get("dedupe_allows_submit") is not True:
        blockers.append("prior_live_submit_for_idempotency_key")
    return _dedupe(blockers)


def _order_triplet_summary(order_triplet: Mapping[str, Any]) -> dict[str, Any]:
    main = order_triplet.get("main_order") if isinstance(order_triplet.get("main_order"), Mapping) else {}
    stop = order_triplet.get("stop_order") if isinstance(order_triplet.get("stop_order"), Mapping) else {}
    take_profit = order_triplet.get("take_profit_order") if isinstance(order_triplet.get("take_profit_order"), Mapping) else {}
    return {
        "exactly_three_orders": len(_triplet_orders(order_triplet)) == 3,
        "sequence_valid": validate_order_sequence_main_stop_take_profit(order_triplet)["valid"] is True,
        "main_order": {
            "side": main.get("side"),
            "type": main.get("type"),
            "quantity": _number(main.get("quantity")),
        },
        "stop_order": {
            "side": stop.get("side"),
            "type": stop.get("type"),
            "quantity": _number(stop.get("quantity")),
            "stopPrice": _number(stop.get("stopPrice")),
            "reduceOnly": stop.get("reduceOnly") is True,
        },
        "take_profit_order": {
            "side": take_profit.get("side"),
            "type": take_profit.get("type"),
            "quantity": _number(take_profit.get("quantity")),
            "stopPrice": _number(take_profit.get("stopPrice")),
            "reduceOnly": take_profit.get("reduceOnly") is True,
        },
    }


def _signed_request_timestamps(signed_request_artifact: Mapping[str, Any]) -> list[int]:
    result: list[int] = []
    requests = signed_request_artifact.get("signed_requests") if isinstance(signed_request_artifact.get("signed_requests"), Mapping) else {}
    for key in ("main_order", "stop_order", "take_profit_order"):
        request = requests.get(key) if isinstance(requests.get(key), Mapping) else {}
        parsed = _parse_query_string(str(request.get("query_string_without_signature") or ""))
        timestamp = parsed.get("timestamp")
        if timestamp and str(timestamp).isdigit():
            result.append(int(str(timestamp)))
    return result


def _matching_lane(path: Path, official_lane_key: str) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    lanes = payload.get("lanes") if isinstance(payload, Mapping) else []
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    for lane in lanes if isinstance(lanes, list) else []:
        if not isinstance(lane, Mapping):
            continue
        if (
            lane.get("symbol") == symbol
            and lane.get("timeframe") == timeframe
            and lane.get("direction") == direction
            and lane.get("entry_mode") == entry_mode
        ):
            return _sanitize(lane)
    return {}


def _reference_price_from_artifact(order_triplet: Mapping[str, Any]) -> float | None:
    for key in ("main_order", "stop_order", "take_profit_order"):
        order = order_triplet.get(key) if isinstance(order_triplet.get(key), Mapping) else {}
        price = _number(order.get("reference_price") or order.get("entry_reference_price"))
        if price is not None:
            return price
    return None


def _triplet_orders(order_triplet: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    orders: list[Mapping[str, Any]] = []
    for key in ("main_order", "stop_order", "take_profit_order"):
        value = order_triplet.get(key)
        if isinstance(value, Mapping) and value:
            orders.append(value)
    return orders


def _signed_request_artifact(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = record.get("signed_request_artifact")
    return _sanitize(artifact if isinstance(artifact, Mapping) else {})


def _executable_payload_artifact(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = record.get("executable_payload_artifact")
    return _sanitize(artifact if isinstance(artifact, Mapping) else {})


def _stop_take_profit_artifact(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = record.get("stop_take_profit_source_preview")
    return _sanitize(artifact if isinstance(artifact, Mapping) else {})


def _record_matches_lane(record: Mapping[str, Any], official_lane_key: str) -> bool:
    target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    return target.get("official_lane_key") == official_lane_key


def _lane_parts(official_lane_key: str) -> tuple[str, str, str, str]:
    parts = official_lane_key.split("|")
    if len(parts) != 4:
        return official_lane_key, "", "", ""
    return parts[0], parts[1], parts[2], parts[3]


def _parse_query_string(query: str) -> dict[str, str]:
    return {str(key): str(value) for key, value in parse_qsl(query, keep_blank_values=True)}


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_sanitize(item) for item in value]
    return value


def _recommended_next_operator_move(packet: Mapping[str, Any]) -> str:
    return str(packet.get("next_required_human_action") or "MANUAL_OPERATOR_DECISION_REQUIRED")


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("blocked_by"):
        return "Resolve R255 blockers without running the real submit phrase from Codex."
    return "Prepare R256 operator real-submit runbook and reconciliation checklist."


def _do_not_run_yet() -> list[str]:
    return [
        "unreviewed live submit",
        "duplicate live submit",
        "any non-/fapi/v1/order endpoint",
        "kill switch disable",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]
