"""R247 tiny-live executable payload readiness preview.

This preview consumes the refreshed R246 non-executable payload artifact and
reports what is still required before a future executable payload write gate.
It never creates executable payloads, signs requests, calls Binance/network,
places orders, or mutates configs/env/lane controls.
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
from src.app.hammer_radar.operator.tiny_live_10_of_10_ready_packet import (
    load_tiny_live_10_of_10_ready_packet_records,
)
from src.app.hammer_radar.operator.tiny_live_lane_arm_write_gate import (
    load_tiny_live_lane_arm_write_gate_records,
    validate_lane_arm_object,
)
from src.app.hammer_radar.operator.tiny_live_order_payload_refresh_preview import (
    load_latest_tiny_live_binance_readonly_precision_mark_price_gate as _load_latest_r242,
    load_latest_tiny_live_leverage_notional_risk_contract_write_gate as _load_latest_r244,
    load_latest_tiny_live_order_preflight_write_gate as _load_latest_r238,
    load_tiny_live_order_payload_refresh_preview_records,
    validate_refreshed_payload_preview,
)
from src.app.hammer_radar.operator.tiny_live_order_payload_refresh_write_gate import (
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_WRITTEN,
    TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITTEN_EXECUTABLE_PREVIEW_REQUIRED,
    load_tiny_live_order_payload_refresh_write_gate_records,
    validate_refreshed_non_executable_payload_artifact,
)
from src.app.hammer_radar.operator.tiny_live_order_preflight_write_gate import (
    load_tiny_live_order_preflight_write_gate_records,
    validate_order_preflight_object,
)

TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_READY = "TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_READY"
TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_REJECTED = "TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_REJECTED"
TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_RECORDED = "TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_RECORDED"
TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED = "TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED"
TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_ERROR = "TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_ERROR"

TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED_BY_STOP_TP_LEVELS = (
    "TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED_BY_STOP_TP_LEVELS"
)
TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_READY_FOR_FUTURE_WRITE_GATE = (
    "TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_READY_FOR_FUTURE_WRITE_GATE"
)
TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED_BY_R246 = "TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED_BY_R246"
TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED_BY_VALIDATION = (
    "TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED_BY_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW"
LEDGER_FILENAME = "tiny_live_executable_payload_preview.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R247_TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW"
CONFIRM_TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE EXECUTABLE PAYLOAD PREVIEW RECORDING ONLY; "
    "NO EXECUTABLE PAYLOAD; NO SIGNATURE; NO ORDER; NO BINANCE CALL."
)
FUTURE_R248_CONFIRMATION_PHRASE_SUGGESTION = (
    "I CONFIRM TINY LIVE EXECUTABLE PAYLOAD WRITE GATE ONLY; "
    "WRITE EXECUTABLE PAYLOAD ARTIFACT ONLY; NO SIGNATURE; NO ORDER; NO BINANCE CALL."
)

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "order_payload_written": False,
    "order_payload_created": False,
    "executable_payload_written": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "submit_allowed": False,
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
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
    "executable_payload_preview_only": True,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_order_payload_refresh_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_order_payload_refresh_preview.ndjson",
    "logs/hammer_radar_forward/tiny_live_leverage_notional_risk_contract_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_binance_readonly_precision_mark_price_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_order_preflight_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_lane_arm_write_gate.ndjson",
    "logs/hammer_radar_forward/tiny_live_10_of_10_ready_packet.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_executable_payload_preview(
    *,
    log_dir: str | Path | None = None,
    record_executable_payload_preview: bool = False,
    confirm_tiny_live_executable_payload_preview: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_executable_payload_preview
        == CONFIRM_TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_RECORDING_PHRASE
    )
    symbol, _, direction, _ = _lane_parts(official_lane_key)
    try:
        latest_r246 = load_latest_tiny_live_order_payload_refresh_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r245 = load_latest_tiny_live_order_payload_refresh_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r244 = load_latest_tiny_live_leverage_notional_risk_contract_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r242 = load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r238 = load_latest_tiny_live_order_preflight_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r236 = load_latest_tiny_live_lane_arm_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r228 = _load_latest_tiny_live_10_of_10_ready_packet(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        input_summary = _build_input_summary(
            latest_r246=latest_r246,
            latest_r245=latest_r245,
            latest_r244=latest_r244,
            latest_r242=latest_r242,
            latest_r238=latest_r238,
            latest_r236=latest_r236,
            latest_r228=latest_r228,
        )
        base_payload = _base_payload(latest_r246)
        base_summary = _base_non_executable_payload_summary(base_payload)
        candidates = discover_local_stop_take_profit_candidates(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        readiness = build_executable_payload_readiness_preview(
            base_payload=base_payload,
            latest_r246=latest_r246,
            latest_r242=latest_r242,
            stop_take_profit_candidates=candidates,
            official_lane_key=official_lane_key,
            now=generated_at,
        )
        validation = validate_executable_payload_preview(readiness, input_summary=input_summary)
        matrix = build_executable_payload_preview_gate_matrix(
            input_summary=input_summary,
            base_payload_summary=base_summary,
            stop_take_profit_candidate_summary=candidates,
            validation=validation,
        )
        operator_packet = build_operator_executable_payload_preview_packet(matrix)
        overall = classify_tiny_live_executable_payload_preview_status(
            input_summary=input_summary,
            executable_payload_preview_validation=validation,
            executable_payload_preview_gate_matrix=matrix,
        )

        recorded = False
        status = TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_READY if validation["valid"] else TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED
        if matrix.get("executable_payload_preview_ready") is not True:
            status = TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED
        if record_executable_payload_preview and not confirmation_valid:
            status = TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_REJECTED
            overall = TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED_BY_VALIDATION
        elif record_executable_payload_preview and confirmation_valid:
            append_tiny_live_executable_payload_preview_record(
                {
                    "status": TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_RECORDED,
                    "generated_at": generated_at.isoformat(),
                    "executable_payload_preview_recorded": True,
                    "record_executable_payload_preview_requested": True,
                    "confirmation_valid": True,
                    "target_scope": _target_scope(official_lane_key),
                    "input_summary": input_summary,
                    "base_non_executable_payload_summary": base_summary,
                    "stop_take_profit_candidate_summary": candidates,
                    "executable_payload_readiness_preview": readiness,
                    "executable_payload_preview_validation": validation,
                    "executable_payload_preview_gate_matrix": matrix,
                    "operator_executable_payload_preview_packet": operator_packet,
                    "recommended_next_operator_move": _recommended_next_operator_move(matrix),
                    "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
                    "executable_payload_preview_overall_status": overall,
                    "future_r248_confirmation_phrase_suggestion": FUTURE_R248_CONFIRMATION_PHRASE_SUGGESTION,
                    "do_not_run_yet": _do_not_run_yet(),
                    "safety": dict(SAFETY),
                    "source_surfaces_used": list(SOURCE_SURFACES_USED),
                },
                log_dir=resolved_log_dir,
            )
            recorded = True
            status = TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_RECORDED

        return _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "executable_payload_preview_recorded": recorded,
                "record_executable_payload_preview_requested": bool(record_executable_payload_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(official_lane_key),
                "input_summary": input_summary,
                "base_non_executable_payload_summary": base_summary,
                "stop_take_profit_candidate_summary": candidates,
                "executable_payload_readiness_preview": readiness,
                "executable_payload_preview_validation": validation,
                "executable_payload_preview_gate_matrix": matrix,
                "operator_executable_payload_preview_packet": operator_packet,
                "recommended_next_operator_move": _recommended_next_operator_move(matrix),
                "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
                "executable_payload_preview_overall_status": overall,
                "future_r248_confirmation_phrase_suggestion": FUTURE_R248_CONFIRMATION_PHRASE_SUGGESTION,
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = build_executable_payload_preview_gate_matrix(
            input_summary=_empty_input_summary(),
            base_payload_summary=_empty_base_non_executable_payload_summary(),
            stop_take_profit_candidate_summary=_empty_stop_take_profit_candidate_summary(),
            validation={"valid": False, "errors": ["executable_payload_preview_error"], "warnings": []},
        )
        return _sanitize(
            {
                "status": TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "executable_payload_preview_recorded": False,
                "record_executable_payload_preview_requested": bool(record_executable_payload_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(official_lane_key),
                "input_summary": _empty_input_summary(),
                "base_non_executable_payload_summary": _empty_base_non_executable_payload_summary(),
                "stop_take_profit_candidate_summary": _empty_stop_take_profit_candidate_summary(),
                "executable_payload_readiness_preview": _empty_readiness_preview(official_lane_key),
                "executable_payload_preview_validation": {
                    "valid": False,
                    "errors": ["executable_payload_preview_error"],
                    "warnings": [],
                },
                "executable_payload_preview_gate_matrix": matrix,
                "operator_executable_payload_preview_packet": build_operator_executable_payload_preview_packet(matrix),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R247 executable payload preview error before any future write gate.",
                "executable_payload_preview_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "future_r248_confirmation_phrase_suggestion": FUTURE_R248_CONFIRMATION_PHRASE_SUGGESTION,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_order_payload_refresh_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_order_payload_refresh_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        artifact = _base_payload(record)
        validation = validate_refreshed_non_executable_payload_artifact(artifact) if artifact else {"valid": False}
        if (
            str(target.get("official_lane_key") or artifact.get("official_lane_key") or "") == official_lane_key
            and record.get("status") == TINY_LIVE_ORDER_PAYLOAD_REFRESH_WRITE_GATE_WRITTEN
            and record.get("payload_refresh_written") is True
            and validation.get("valid") is True
        ):
            return _sanitize({**record, "r246_payload_refresh_found": True})
    return {}


def load_latest_tiny_live_order_payload_refresh_preview(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_order_payload_refresh_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        preview = (
            record.get("refreshed_non_executable_payload_preview")
            if isinstance(record.get("refreshed_non_executable_payload_preview"), Mapping)
            else {}
        )
        validation = validate_refreshed_payload_preview(preview)
        if (
            str(target.get("official_lane_key") or preview.get("official_lane_key") or "") == official_lane_key
            and record.get("payload_refresh_preview_recorded") is True
            and validation.get("valid") is True
        ):
            return _sanitize({**record, "r245_refresh_preview_found": True})
    return {}


def load_latest_tiny_live_leverage_notional_risk_contract_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_r244(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_binance_readonly_precision_mark_price_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    return _load_latest_r242(log_dir=log_dir, official_lane_key=official_lane_key)


def load_latest_tiny_live_order_preflight_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_order_preflight_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        preflight = record.get("order_preflight") if isinstance(record.get("order_preflight"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or preflight.get("official_lane_key") or "") == official_lane_key
            and record.get("order_preflight_written") is True
            and validate_order_preflight_object(preflight).get("valid") is True
        ):
            return _sanitize({**record, "r238_order_preflight_found": True})
    return {}


def load_latest_tiny_live_lane_arm_write_gate(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_lane_arm_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        lane_arm = record.get("lane_arm") if isinstance(record.get("lane_arm"), Mapping) else {}
        if (
            str(target.get("official_lane_key") or lane_arm.get("official_lane_key") or "") == official_lane_key
            and record.get("lane_arm_written") is True
            and validate_lane_arm_object(lane_arm).get("valid") is True
        ):
            return _sanitize({**record, "r236_lane_arm_found": True})
    return {}


def build_executable_payload_readiness_preview(
    *,
    base_payload: Mapping[str, Any],
    latest_r246: Mapping[str, Any],
    latest_r242: Mapping[str, Any],
    stop_take_profit_candidates: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, _, _, _ = _lane_parts(official_lane_key)
    precision = _price_precision_requirements(latest_r242)
    stop_price = stop_take_profit_candidates.get("stop_price")
    take_profit_price = stop_take_profit_candidates.get("take_profit_price")
    missing = [
        key
        for key, present in (
            ("final_stop_price", stop_price is not None),
            ("final_take_profit_price", take_profit_price is not None),
            ("operator_executable_payload_confirmation", False),
            ("signature_gate", False),
            ("submit_gate", False),
        )
        if not present
    ]
    return {
        "executable_payload_preview_id": f"r247_executable_payload_preview_{uuid4().hex}",
        "created_by_phase": CREATED_BY_PHASE,
        "created_at": generated_at.isoformat(),
        "preview_only": True,
        "artifact_written": False,
        "executable_payload_created": False,
        "signed": False,
        "submit_allowed": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "official_lane_key": official_lane_key,
        "source_r246_order_payload_id": base_payload.get("order_payload_id"),
        "source_r246_gate_record_id": latest_r246.get("gate_record_id"),
        "base_payload": {
            "symbol": base_payload.get("symbol") or symbol,
            "side": base_payload.get("side"),
            "quantity": base_payload.get("quantity"),
            "order_type": base_payload.get("order_type"),
            "leverage": base_payload.get("leverage"),
            "margin_budget_usdt": base_payload.get("margin_budget_usdt"),
            "notional_after_rounding": base_payload.get("notional_after_rounding"),
        },
        "would_be_executable_payload_shape_later": {
            "symbol": base_payload.get("symbol") or symbol,
            "side": base_payload.get("side"),
            "type": "MARKET",
            "quantity": base_payload.get("quantity"),
            "reduceOnly": False,
            "positionSide": base_payload.get("position_side"),
            "timeInForce": None,
            "newClientOrderId": None,
            "executable": False,
            "signed": False,
            "submit_allowed": False,
        },
        "required_protective_orders_later": {
            "stop_market": {
                "required": True,
                "side": "BUY",
                "reduce_only": True,
                "stop_price": stop_price,
                "ready": stop_price is not None,
                "blocked_by": [] if stop_price is not None else ["final_stop_price_missing"],
            },
            "take_profit_market": {
                "required": True,
                "side": "BUY",
                "reduce_only": True,
                "take_profit_price": take_profit_price,
                "ready": take_profit_price is not None,
                "blocked_by": [] if take_profit_price is not None else ["final_take_profit_price_missing"],
            },
        },
        "price_precision_requirements": precision,
        "executable_conversion_requirements": build_executable_conversion_requirements(
            stop_price_found=stop_price is not None,
            take_profit_price_found=take_profit_price is not None,
        ),
        "missing_before_executable_payload": missing,
    }


def build_executable_conversion_requirements(
    *,
    stop_price_found: bool = False,
    take_profit_price_found: bool = False,
) -> dict[str, Any]:
    return {
        "requires_final_stop_price": True,
        "requires_final_take_profit_price": True,
        "requires_operator_executable_payload_confirmation": True,
        "requires_signature_gate_later": True,
        "requires_submit_gate_later": True,
        "requires_price_precision_rounding": True,
        "requires_r248_guarded_write_gate": True,
        "stop_price_ready": bool(stop_price_found),
        "take_profit_price_ready": bool(take_profit_price_found),
        "executable_payload_creation_allowed_now": False,
        "signed_request_creation_allowed_now": False,
        "order_submission_allowed_now": False,
    }


def discover_local_stop_take_profit_candidates(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    candidates: list[dict[str, Any]] = []
    for path in _candidate_stop_take_paths(resolved_log_dir):
        for record in _read_candidate_records(path):
            if not _record_matches_lane(record, official_lane_key):
                continue
            stop_price = _first_number(record, ("final_stop_price", "stop_price"))
            take_profit_price = _first_number(record, ("final_take_profit_price", "take_profit_price", "tp_price"))
            if stop_price is not None or take_profit_price is not None:
                candidates.append(
                    {
                        "source": str(path),
                        "record_id": record.get("record_id") or record.get("ticket_id") or record.get("event_id"),
                        "stop_price": stop_price,
                        "take_profit_price": take_profit_price,
                    }
                )
    latest = candidates[-1] if candidates else {}
    stop_price = latest.get("stop_price")
    take_profit_price = latest.get("take_profit_price")
    blocked_by: list[str] = []
    if stop_price is None:
        blocked_by.append("final_stop_price_missing")
    if take_profit_price is None:
        blocked_by.append("final_take_profit_price_missing")
    return {
        "stop_price_found": stop_price is not None,
        "take_profit_price_found": take_profit_price is not None,
        "stop_price": stop_price,
        "take_profit_price": take_profit_price,
        "source": latest.get("source"),
        "candidate_count": len(candidates),
        "blocked_by": blocked_by,
    }


def validate_executable_payload_preview(
    executable_payload_preview: Mapping[str, Any],
    *,
    input_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    input_summary = input_summary or {}
    base = executable_payload_preview.get("base_payload") if isinstance(executable_payload_preview.get("base_payload"), Mapping) else {}
    shape = (
        executable_payload_preview.get("would_be_executable_payload_shape_later")
        if isinstance(executable_payload_preview.get("would_be_executable_payload_shape_later"), Mapping)
        else {}
    )
    if input_summary and input_summary.get("r246_payload_refresh_valid") is not True:
        errors.append("r246_payload_refresh_not_ready")
    for key in ("preview_only",):
        if executable_payload_preview.get(key) is not True:
            errors.append(f"{key}_invalid")
    for key in (
        "artifact_written",
        "executable_payload_created",
        "signed",
        "submit_allowed",
        "order_placed",
        "binance_call_allowed",
        "network_allowed",
    ):
        if executable_payload_preview.get(key) is not False:
            errors.append(f"{key}_invalid")
    if executable_payload_preview.get("official_lane_key") != OFFICIAL_LANE_KEY:
        errors.append("official_lane_key_invalid")
    if base.get("symbol") != "BTCUSDT" or base.get("side") != "SELL":
        errors.append("base_payload_symbol_side_invalid")
    if base.get("quantity") != 0.007:
        errors.append("base_payload_quantity_invalid")
    notional = base.get("notional_after_rounding")
    if notional is None or abs(float(notional) - 435.4721) > 0.0001:
        errors.append("base_payload_notional_after_rounding_invalid")
    if shape.get("type") != "MARKET" or shape.get("executable") is not False:
        errors.append("would_be_executable_payload_shape_invalid")
    missing = set(executable_payload_preview.get("missing_before_executable_payload") or [])
    if "final_stop_price" in missing:
        warnings.append("final_stop_price_missing")
    if "final_take_profit_price" in missing:
        warnings.append("final_take_profit_price_missing")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def build_executable_payload_preview_gate_matrix(
    *,
    input_summary: Mapping[str, Any],
    base_payload_summary: Mapping[str, Any],
    stop_take_profit_candidate_summary: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if input_summary.get("r246_payload_refresh_valid") is not True:
        blockers.append("r246_payload_refresh_not_ready")
    if base_payload_summary.get("quantity") != 0.007:
        blockers.append("quantity_not_ready")
    if not base_payload_summary.get("notional_meets_min_notional"):
        blockers.append("notional_not_ready")
    if stop_take_profit_candidate_summary.get("stop_price_found") is not True:
        blockers.append("final_stop_price_missing")
    if stop_take_profit_candidate_summary.get("take_profit_price_found") is not True:
        blockers.append("final_take_profit_price_missing")
    if validation.get("valid") is not True:
        blockers.extend(str(error) for error in validation.get("errors") or ["executable_payload_preview_invalid"])
    blockers = _dedupe(blockers)
    return {
        "r246_payload_refresh_ready": input_summary.get("r246_payload_refresh_valid") is True,
        "quantity_ready": base_payload_summary.get("quantity") == 0.007,
        "notional_ready": base_payload_summary.get("notional_meets_min_notional") is True,
        "stop_price_ready": stop_take_profit_candidate_summary.get("stop_price_found") is True,
        "take_profit_price_ready": stop_take_profit_candidate_summary.get("take_profit_price_found") is True,
        "price_precision_ready": input_summary.get("r242_readonly_valid") is True,
        "executable_payload_preview_ready": validation.get("valid") is True and not blockers,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": blockers,
    }


def build_operator_executable_payload_preview_packet(
    executable_payload_preview_gate_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    blocked = bool(executable_payload_preview_gate_matrix.get("blocked_by"))
    action = "REVIEW_R247_EXECUTABLE_PAYLOAD_PREVIEW"
    if "final_stop_price_missing" in executable_payload_preview_gate_matrix.get("blocked_by", []):
        action = "PROVIDE_STOP_TP_SOURCE"
    if not executable_payload_preview_gate_matrix.get("r246_payload_refresh_ready"):
        action = "WAIT"
    return {
        "operator_should_review_executable_payload_preview": True,
        "operator_should_create_executable_payload_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action if blocked else "REVIEW_R247_EXECUTABLE_PAYLOAD_PREVIEW",
        "explicit_non_actions": [
            "do not place order",
            "do not create executable payload",
            "do not sign request",
            "do not call Binance from this phase",
        ],
    }


def classify_tiny_live_executable_payload_preview_status(
    *,
    input_summary: Mapping[str, Any],
    executable_payload_preview_validation: Mapping[str, Any],
    executable_payload_preview_gate_matrix: Mapping[str, Any],
) -> str:
    blockers = set(executable_payload_preview_gate_matrix.get("blocked_by") or [])
    if input_summary.get("r246_payload_refresh_valid") is not True:
        return TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED_BY_R246
    if executable_payload_preview_validation.get("valid") is not True:
        return TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED_BY_VALIDATION
    if {"final_stop_price_missing", "final_take_profit_price_missing"} & blockers:
        return TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_BLOCKED_BY_STOP_TP_LEVELS
    if executable_payload_preview_gate_matrix.get("executable_payload_preview_ready") is True:
        return TINY_LIVE_EXECUTABLE_PAYLOAD_PREVIEW_READY_FOR_FUTURE_WRITE_GATE
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_tiny_live_executable_payload_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_executable_payload_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "executable_payload_preview_record_id": (
                record.get("executable_payload_preview_record_id") or f"r247_executable_payload_preview_{uuid4().hex}"
            ),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "executable_payload_preview_recorded": record.get("executable_payload_preview_recorded") is True,
            "record_executable_payload_preview_requested": (
                record.get("record_executable_payload_preview_requested") is True
            ),
            "confirmation_valid": record.get("confirmation_valid") is True,
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "base_non_executable_payload_summary": dict(record.get("base_non_executable_payload_summary") or {}),
            "stop_take_profit_candidate_summary": dict(record.get("stop_take_profit_candidate_summary") or {}),
            "executable_payload_readiness_preview": dict(record.get("executable_payload_readiness_preview") or {}),
            "executable_payload_preview_validation": dict(record.get("executable_payload_preview_validation") or {}),
            "executable_payload_preview_gate_matrix": dict(record.get("executable_payload_preview_gate_matrix") or {}),
            "operator_executable_payload_preview_packet": dict(record.get("operator_executable_payload_preview_packet") or {}),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "executable_payload_preview_overall_status": record.get("executable_payload_preview_overall_status"),
            "future_r248_confirmation_phrase_suggestion": record.get("future_r248_confirmation_phrase_suggestion"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_executable_payload_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_executable_payload_preview_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_executable_payload_preview_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    base = (
        latest.get("base_non_executable_payload_summary")
        if isinstance(latest.get("base_non_executable_payload_summary"), Mapping)
        else {}
    )
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_preview_recorded": latest.get("executable_payload_preview_recorded") is True,
        "latest_overall_status": latest.get("executable_payload_preview_overall_status"),
        "latest_quantity": base.get("quantity"),
        "latest_notional_after_rounding": base.get("notional_after_rounding"),
    }


def tiny_live_executable_payload_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_executable_payload_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r246: Mapping[str, Any],
    latest_r245: Mapping[str, Any],
    latest_r244: Mapping[str, Any],
    latest_r242: Mapping[str, Any],
    latest_r238: Mapping[str, Any],
    latest_r236: Mapping[str, Any],
    latest_r228: Mapping[str, Any],
) -> dict[str, Any]:
    r246_payload = _base_payload(latest_r246)
    r246_validation = validate_refreshed_non_executable_payload_artifact(r246_payload) if r246_payload else {"valid": False}
    readonly = latest_r242.get("binance_readonly_result") if isinstance(latest_r242.get("binance_readonly_result"), Mapping) else {}
    precision = readonly.get("precision_snapshot") if isinstance(readonly.get("precision_snapshot"), Mapping) else {}
    mark = readonly.get("mark_price_snapshot") if isinstance(readonly.get("mark_price_snapshot"), Mapping) else {}
    preflight = latest_r238.get("order_preflight") if isinstance(latest_r238.get("order_preflight"), Mapping) else {}
    lane_arm = latest_r236.get("lane_arm") if isinstance(latest_r236.get("lane_arm"), Mapping) else {}
    r228_matrix = latest_r228.get("tiny_live_gate_matrix") if isinstance(latest_r228.get("tiny_live_gate_matrix"), Mapping) else {}
    return {
        "r246_payload_refresh_found": bool(latest_r246),
        "r246_payload_refresh_valid": r246_validation.get("valid") is True,
        "r245_refresh_preview_found": bool(latest_r245),
        "r244_adjusted_contract_found": bool(latest_r244),
        "r242_readonly_found": bool(latest_r242),
        "r242_readonly_valid": (
            latest_r242.get("readonly_fetch_performed") is True
            and precision.get("found") is True
            and mark.get("found") is True
        ),
        "r238_order_preflight_found": bool(latest_r238),
        "r238_order_preflight_valid": validate_order_preflight_object(preflight).get("valid") is True if preflight else False,
        "r236_lane_arm_found": bool(latest_r236),
        "r236_lane_arm_valid": validate_lane_arm_object(lane_arm).get("valid") is True if lane_arm else False,
        "r228_evidence_ready": r228_matrix.get("evidence_ready") is True,
    }


def _base_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("refreshed_payload_artifact", "order_payload"):
        value = record.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _base_non_executable_payload_summary(base_payload: Mapping[str, Any]) -> dict[str, Any]:
    notional = base_payload.get("notional_after_rounding")
    min_notional = 50.0
    return {
        "quantity": base_payload.get("quantity"),
        "notional_after_rounding": notional,
        "min_notional": min_notional,
        "notional_meets_min_notional": _number(notional) is not None and float(notional) >= min_notional,
        "side": base_payload.get("side"),
        "executable": base_payload.get("executable"),
        "signed": base_payload.get("signed"),
        "submit_allowed": base_payload.get("submit_allowed"),
    }


def _price_precision_requirements(latest_r242: Mapping[str, Any]) -> dict[str, Any]:
    readonly = latest_r242.get("binance_readonly_result") if isinstance(latest_r242.get("binance_readonly_result"), Mapping) else {}
    precision = readonly.get("precision_snapshot") if isinstance(readonly.get("precision_snapshot"), Mapping) else {}
    return {
        "tick_size": _number(precision.get("tick_size")),
        "price_precision": precision.get("price_precision"),
        "requires_stop_price_rounding": True,
        "requires_take_profit_price_rounding": True,
    }


def _load_latest_tiny_live_10_of_10_ready_packet(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_tiny_live_10_of_10_ready_packet_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        matrix = record.get("tiny_live_gate_matrix") if isinstance(record.get("tiny_live_gate_matrix"), Mapping) else {}
        if str(target.get("official_lane_key") or "") == official_lane_key and matrix.get("evidence_ready") is True:
            return _sanitize(record)
    return {}


def _candidate_stop_take_paths(log_dir: Path) -> list[Path]:
    if not log_dir.exists():
        return []
    names = ("stop", "take", "ticket", "approval")
    return sorted(path for path in log_dir.glob("*.ndjson") if any(name in path.name for name in names))


def _read_candidate_records(path: Path) -> list[dict[str, Any]]:
    try:
        return [dict(record) for record in read_recent_ndjson_records(path, limit=100, max_bytes=4_194_304)]
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []


def _record_matches_lane(record: Mapping[str, Any], official_lane_key: str) -> bool:
    if str(record.get("official_lane_key") or "") == official_lane_key:
        return True
    target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    if str(target.get("official_lane_key") or "") == official_lane_key:
        return True
    payload = record.get("payload") if isinstance(record.get("payload"), Mapping) else {}
    return str(payload.get("official_lane_key") or "") == official_lane_key


def _first_number(record: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    stack: list[Any] = [record]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            for key in keys:
                number = _number(item.get(key))
                if number is not None:
                    return number
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return None


def _target_scope(official_lane_key: str) -> dict[str, Any]:
    symbol, _, direction, _ = _lane_parts(official_lane_key)
    return {
        "official_lane_key": official_lane_key,
        "symbol": symbol,
        "direction": direction,
        "executable_payload_preview_only": True,
        "executable_payload_created": False,
        "signed_order_request_created": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
    }


def _recommended_next_operator_move(matrix: Mapping[str, Any]) -> str:
    if "final_stop_price_missing" in matrix.get("blocked_by", []) or "final_take_profit_price_missing" in matrix.get("blocked_by", []):
        return "PROVIDE_STOP_TP_SOURCE"
    if matrix.get("r246_payload_refresh_ready") is True:
        return "REVIEW_R247_EXECUTABLE_PAYLOAD_PREVIEW"
    return "WAIT"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if "final_stop_price_missing" in matrix.get("blocked_by", []) or "final_take_profit_price_missing" in matrix.get("blocked_by", []):
        return "Create R248 guarded stop/take-profit source gate before any executable payload write gate."
    if matrix.get("executable_payload_preview_ready") is True:
        return "Create R248 guarded executable payload write gate only after exact operator confirmation; no signature, no order, no Binance call."
    return "Fix R247 input or validation blockers before any future executable payload write gate."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "signed order request",
        "signed trading request",
        "kill switch disable",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r246_payload_refresh_found": False,
        "r246_payload_refresh_valid": False,
        "r245_refresh_preview_found": False,
        "r244_adjusted_contract_found": False,
        "r242_readonly_found": False,
        "r242_readonly_valid": False,
        "r238_order_preflight_found": False,
        "r238_order_preflight_valid": False,
        "r236_lane_arm_found": False,
        "r236_lane_arm_valid": False,
        "r228_evidence_ready": False,
    }


def _empty_base_non_executable_payload_summary() -> dict[str, Any]:
    return {
        "quantity": None,
        "notional_after_rounding": None,
        "min_notional": 50.0,
        "notional_meets_min_notional": False,
        "side": None,
        "executable": None,
        "signed": None,
        "submit_allowed": None,
    }


def _empty_stop_take_profit_candidate_summary() -> dict[str, Any]:
    return {
        "stop_price_found": False,
        "take_profit_price_found": False,
        "stop_price": None,
        "take_profit_price": None,
        "source": None,
        "candidate_count": 0,
        "blocked_by": ["final_stop_price_missing", "final_take_profit_price_missing"],
    }


def _empty_readiness_preview(official_lane_key: str) -> dict[str, Any]:
    return {
        "executable_payload_preview_id": None,
        "preview_only": True,
        "artifact_written": False,
        "executable_payload_created": False,
        "signed": False,
        "submit_allowed": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "official_lane_key": official_lane_key,
        "source_r246_order_payload_id": None,
        "base_payload": {},
        "would_be_executable_payload_shape_later": {},
        "required_protective_orders_later": {},
        "price_precision_requirements": {},
        "missing_before_executable_payload": [
            "final_stop_price",
            "final_take_profit_price",
            "operator_executable_payload_confirmation",
            "signature_gate",
            "submit_gate",
        ],
    }


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key).split("|")
    if len(parts) != 4:
        return ("BTCUSDT", "8m", "short", "ladder_close_50_618")
    return parts[0], parts[1], parts[2], parts[3]


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
