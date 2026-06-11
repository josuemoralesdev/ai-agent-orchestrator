"""R250 tiny-live signature gate preview.

This preview consumes the latest R249 executable payload artifact and reports
the unsigned Binance Futures order request templates that a later signed write
gate would need. It never reads secrets, creates signatures, writes signed
requests, calls Binance/network endpoints, submits, places orders, mutates
configs/env/lane controls, or disables the kill switch.
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
from src.app.hammer_radar.operator.tiny_live_executable_payload_write_gate import (
    load_tiny_live_executable_payload_write_gate_records,
    validate_executable_payload_artifact,
)

TINY_LIVE_SIGNATURE_GATE_PREVIEW_READY = "TINY_LIVE_SIGNATURE_GATE_PREVIEW_READY"
TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDED = "TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDED"
TINY_LIVE_SIGNATURE_GATE_PREVIEW_REJECTED = "TINY_LIVE_SIGNATURE_GATE_PREVIEW_REJECTED"
TINY_LIVE_SIGNATURE_GATE_PREVIEW_BLOCKED = "TINY_LIVE_SIGNATURE_GATE_PREVIEW_BLOCKED"
TINY_LIVE_SIGNATURE_GATE_PREVIEW_ERROR = "TINY_LIVE_SIGNATURE_GATE_PREVIEW_ERROR"

TINY_LIVE_SIGNATURE_GATE_PREVIEW_READY_FOR_FUTURE_WRITE_GATE = (
    "TINY_LIVE_SIGNATURE_GATE_PREVIEW_READY_FOR_FUTURE_WRITE_GATE"
)
TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDED_SIGNED_WRITE_REQUIRED = (
    "TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDED_SIGNED_WRITE_REQUIRED"
)
TINY_LIVE_SIGNATURE_GATE_PREVIEW_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_SIGNATURE_GATE_PREVIEW_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_SIGNATURE_GATE_PREVIEW_BLOCKED_BY_R249 = "TINY_LIVE_SIGNATURE_GATE_PREVIEW_BLOCKED_BY_R249"
TINY_LIVE_SIGNATURE_GATE_PREVIEW_BLOCKED_BY_VALIDATION = (
    "TINY_LIVE_SIGNATURE_GATE_PREVIEW_BLOCKED_BY_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_SIGNATURE_GATE_PREVIEW"
LEDGER_FILENAME = "tiny_live_signature_gate_preview.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R250_TINY_LIVE_SIGNATURE_GATE_PREVIEW"
FUTURE_GATE_REQUIRED = "R251_TINY_LIVE_SIGNED_REQUEST_WRITE_GATE"
CONFIRM_TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE SIGNATURE GATE PREVIEW RECORDING ONLY; "
    "NO SIGNED REQUEST; NO ORDER; NO BINANCE CALL."
)

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_executable_payload_write_gate.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "signature_gate_preview_only": True,
    "executable_payload_written": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_request_written": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "hmac_signature_created": False,
    "api_key_loaded": False,
    "api_secret_loaded": False,
    "secrets_read": False,
    "secrets_shown": False,
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
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
}


def build_tiny_live_signature_gate_preview(
    *,
    log_dir: str | Path | None = None,
    record_signature_gate_preview: bool = False,
    confirm_tiny_live_signature_gate_preview: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_signature_gate_preview
        == CONFIRM_TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDING_PHRASE
    )
    symbol, timeframe, direction, _ = _lane_parts(official_lane_key)
    try:
        latest_r249 = load_latest_tiny_live_executable_payload_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        executable_payload = _r249_artifact(latest_r249)
        input_summary = _build_input_summary(latest_r249=latest_r249, executable_payload=executable_payload)
        executable_summary = _build_executable_payload_summary(executable_payload)
        templates = build_unsigned_binance_request_templates_preview(executable_payload)
        requirements = build_signature_requirements_preview()
        validation = validate_signature_gate_preview(
            input_summary=input_summary,
            executable_payload_summary=executable_summary,
            unsigned_request_templates_preview=templates,
            signature_requirements_preview=requirements,
        )
        blocked_by = _blocked_by(input_summary=input_summary, validation=validation)

        recorded = False
        if record_signature_gate_preview and not confirmation_valid:
            status = TINY_LIVE_SIGNATURE_GATE_PREVIEW_REJECTED
            overall = TINY_LIVE_SIGNATURE_GATE_PREVIEW_REJECTED_BAD_CONFIRMATION
        elif blocked_by:
            status = TINY_LIVE_SIGNATURE_GATE_PREVIEW_BLOCKED
            overall = classify_tiny_live_signature_gate_preview_status(
                input_summary=input_summary,
                signature_gate_validation=validation,
                rejected_bad_confirmation=False,
                recorded=False,
            )
        elif record_signature_gate_preview and confirmation_valid:
            recorded = True
            status = TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDED
            overall = TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDED_SIGNED_WRITE_REQUIRED
        else:
            status = TINY_LIVE_SIGNATURE_GATE_PREVIEW_READY
            overall = TINY_LIVE_SIGNATURE_GATE_PREVIEW_READY_FOR_FUTURE_WRITE_GATE

        matrix = build_signature_gate_preview_matrix(
            input_summary=input_summary,
            unsigned_templates_ready=templates.get("preview_only") is True,
            signature_requirements_ready=requirements.get("future_gate_required") == FUTURE_GATE_REQUIRED,
            signature_gate_validation=validation,
            record_confirmed=bool(record_signature_gate_preview and confirmation_valid),
            recorded=recorded,
            blocked_by=blocked_by,
        )
        operator_packet = build_operator_signature_gate_preview_packet(matrix)
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "signature_gate_preview_recorded": recorded,
                "record_signature_gate_preview_requested": bool(record_signature_gate_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "signature_gate_preview_only": True,
                    "signed_order_request_created": False,
                    "signed_request_written": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "executable_payload_summary": executable_summary,
                "unsigned_request_templates_preview": templates,
                "signature_requirements_preview": requirements,
                "signature_gate_validation": validation,
                "signature_gate_preview_matrix": matrix,
                "operator_signature_gate_preview_packet": operator_packet,
                "recommended_next_operator_move": _recommended_next_operator_move(matrix),
                "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
                "signature_gate_preview_overall_status": overall,
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
        if recorded:
            append_tiny_live_signature_gate_preview_record(payload, log_dir=resolved_log_dir)
        return payload
    except Exception as exc:  # pragma: no cover - defensive operator surface
        input_summary = _empty_input_summary()
        validation = {
            "valid": False,
            "errors": ["signature_gate_preview_error"],
            "warnings": [],
        }
        matrix = build_signature_gate_preview_matrix(
            input_summary=input_summary,
            unsigned_templates_ready=False,
            signature_requirements_ready=False,
            signature_gate_validation=validation,
            record_confirmed=False,
            recorded=False,
            blocked_by=["signature_gate_preview_error"],
        )
        return _sanitize(
            {
                "status": TINY_LIVE_SIGNATURE_GATE_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "signature_gate_preview_recorded": False,
                "record_signature_gate_preview_requested": bool(record_signature_gate_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "signature_gate_preview_only": True,
                    "signed_order_request_created": False,
                    "signed_request_written": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "executable_payload_summary": _empty_executable_payload_summary(),
                "unsigned_request_templates_preview": build_unsigned_binance_request_templates_preview({}),
                "signature_requirements_preview": build_signature_requirements_preview(),
                "signature_gate_validation": validation,
                "signature_gate_preview_matrix": matrix,
                "operator_signature_gate_preview_packet": build_operator_signature_gate_preview_packet(matrix),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R250 signature gate preview error before any signed request write gate.",
                "signature_gate_preview_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_executable_payload_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_executable_payload_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        artifact = _r249_artifact(record)
        controls = artifact.get("controls") if isinstance(artifact.get("controls"), Mapping) else {}
        safety = artifact.get("safety") if isinstance(artifact.get("safety"), Mapping) else {}
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("executable_payload_written") is True
            and validate_executable_payload_artifact(artifact).get("valid") is True
            and controls.get("signed") is False
            and controls.get("submit_allowed") is False
            and controls.get("binance_call_allowed") is False
            and controls.get("network_allowed") is False
            and safety.get("signed_order_request_created") is False
            and safety.get("order_placed") is False
        ):
            return _sanitize(record)
    return {}


def validate_r249_executable_payload_for_signature_preview(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = _r249_artifact(record)
    errors: list[str] = []
    warnings: list[str] = []
    if not record:
        errors.append("r249_executable_payload_missing")
    if record.get("executable_payload_written") is not True:
        errors.append("r249_executable_payload_not_written")
    validation = validate_executable_payload_artifact(artifact)
    errors.extend(str(error) for error in validation.get("errors") or [])
    warnings.extend(str(warning) for warning in validation.get("warnings") or [])
    controls = artifact.get("controls") if isinstance(artifact.get("controls"), Mapping) else {}
    safety = artifact.get("safety") if isinstance(artifact.get("safety"), Mapping) else {}
    for key in ("signed", "submit_allowed", "binance_call_allowed", "network_allowed"):
        if controls.get(key) is not False:
            errors.append(f"r249_controls_{key}_must_remain_false")
    if safety.get("signed_order_request_created") is not False:
        errors.append("r249_signed_order_request_created_must_remain_false")
    if safety.get("order_placed") is not False:
        errors.append("r249_order_placed_must_remain_false")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def build_unsigned_binance_request_templates_preview(executable_payload: Mapping[str, Any]) -> dict[str, Any]:
    main = executable_payload.get("main_order") if isinstance(executable_payload.get("main_order"), Mapping) else {}
    stop = executable_payload.get("stop_order") if isinstance(executable_payload.get("stop_order"), Mapping) else {}
    take_profit = (
        executable_payload.get("take_profit_order")
        if isinstance(executable_payload.get("take_profit_order"), Mapping)
        else {}
    )
    quantity = _format_decimal(main.get("quantity") or stop.get("quantity") or take_profit.get("quantity"))
    return {
        "preview_only": True,
        "signed": False,
        "submit_allowed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "main_order_template": _order_template(
            {
                "symbol": main.get("symbol") or "BTCUSDT",
                "side": main.get("side"),
                "type": main.get("type"),
                "quantity": quantity,
            }
        ),
        "stop_order_template": _order_template(
            {
                "symbol": stop.get("symbol") or "BTCUSDT",
                "side": stop.get("side"),
                "type": stop.get("type"),
                "quantity": quantity,
                "stopPrice": _format_decimal(stop.get("stopPrice")),
                "reduceOnly": _format_bool(stop.get("reduceOnly")),
                "workingType": stop.get("workingType") or "MARK_PRICE",
            }
        ),
        "take_profit_order_template": _order_template(
            {
                "symbol": take_profit.get("symbol") or "BTCUSDT",
                "side": take_profit.get("side"),
                "type": take_profit.get("type"),
                "quantity": quantity,
                "stopPrice": _format_decimal(take_profit.get("stopPrice")),
                "reduceOnly": _format_bool(take_profit.get("reduceOnly")),
                "workingType": take_profit.get("workingType") or "MARK_PRICE",
            }
        ),
    }


def build_signature_requirements_preview() -> dict[str, Any]:
    return {
        "requires_api_key_later": True,
        "requires_api_secret_later": True,
        "api_key_loaded": False,
        "api_secret_loaded": False,
        "secrets_read": False,
        "secrets_shown": False,
        "hmac_signature_created": False,
        "signed_request_written": False,
        "future_gate_required": FUTURE_GATE_REQUIRED,
    }


def validate_signature_gate_preview(
    *,
    input_summary: Mapping[str, Any],
    executable_payload_summary: Mapping[str, Any],
    unsigned_request_templates_preview: Mapping[str, Any],
    signature_requirements_preview: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if input_summary.get("r249_executable_payload_valid") is not True:
        errors.append("r249_executable_payload_not_ready")
    if input_summary.get("r249_payload_signed") is not False:
        errors.append("r249_payload_signed_must_be_false")
    if input_summary.get("r249_submit_allowed") is not False:
        errors.append("r249_submit_allowed_must_be_false")
    if input_summary.get("r249_order_placed") is not False:
        errors.append("r249_order_placed_must_be_false")
    expected_summary = {
        "main_order_side": "SELL",
        "main_order_type": "MARKET",
        "quantity": 0.007,
        "stop_order_side": "BUY",
        "stop_order_type": "STOP_MARKET",
        "stop_price": 62844.6,
        "take_profit_order_side": "BUY",
        "take_profit_order_type": "TAKE_PROFIT_MARKET",
        "take_profit_price": 60941.7,
    }
    for key, expected in expected_summary.items():
        if executable_payload_summary.get(key) != expected:
            errors.append(f"executable_payload_summary_{key}_invalid")
    if unsigned_request_templates_preview.get("preview_only") is not True:
        errors.append("unsigned_templates_preview_only_invalid")
    for key in ("signed", "submit_allowed", "binance_call_allowed", "network_allowed"):
        if unsigned_request_templates_preview.get(key) is not False:
            errors.append(f"unsigned_templates_{key}_invalid")
    for template_key in ("main_order_template", "stop_order_template", "take_profit_order_template"):
        template = unsigned_request_templates_preview.get(template_key)
        template = template if isinstance(template, Mapping) else {}
        params = template.get("query_params_preview") if isinstance(template.get("query_params_preview"), Mapping) else {}
        if template.get("endpoint") != "/fapi/v1/order":
            errors.append(f"{template_key}_endpoint_invalid")
        if template.get("requires_signature") is not True or template.get("signed") is not False:
            errors.append(f"{template_key}_signature_flags_invalid")
        if params.get("timestamp") != "<FUTURE_TIMESTAMP>":
            errors.append(f"{template_key}_timestamp_placeholder_invalid")
        if params.get("signature") != "<NOT_CREATED>":
            errors.append(f"{template_key}_signature_placeholder_invalid")
    for key in (
        "api_key_loaded",
        "api_secret_loaded",
        "secrets_read",
        "secrets_shown",
        "hmac_signature_created",
        "signed_request_written",
    ):
        if signature_requirements_preview.get(key) is not False:
            errors.append(f"signature_requirements_{key}_invalid")
    if signature_requirements_preview.get("future_gate_required") != FUTURE_GATE_REQUIRED:
        errors.append("future_gate_required_invalid")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def build_signature_gate_preview_matrix(
    *,
    input_summary: Mapping[str, Any],
    unsigned_templates_ready: bool,
    signature_requirements_ready: bool,
    signature_gate_validation: Mapping[str, Any],
    record_confirmed: bool,
    recorded: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers = list(blocked_by or [])
    if not input_summary.get("r249_executable_payload_valid"):
        blockers.append("r249_executable_payload_not_ready")
    if not unsigned_templates_ready:
        blockers.append("unsigned_templates_not_ready")
    if not signature_requirements_ready:
        blockers.append("signature_requirements_not_ready")
    if signature_gate_validation.get("valid") is not True:
        blockers.append("signature_gate_validation_failed")
    if recorded:
        blockers = ["signed_write_gate_required", "submit_gate_required", "future_readonly_mark_price_refresh_required_before_submit"]
    return {
        "r249_executable_payload_ready": input_summary.get("r249_executable_payload_valid") is True,
        "unsigned_templates_ready": bool(unsigned_templates_ready),
        "signature_requirements_ready": bool(signature_requirements_ready),
        "signature_gate_preview_ready": signature_gate_validation.get("valid") is True,
        "record_confirmed": bool(record_confirmed),
        "recorded": bool(recorded),
        "signed_order_request_created": False,
        "signed_request_written": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_signature_gate_preview_packet(signature_gate_preview_matrix: Mapping[str, Any]) -> dict[str, Any]:
    ready = signature_gate_preview_matrix.get("signature_gate_preview_ready") is True
    recorded = signature_gate_preview_matrix.get("recorded") is True
    if ready or recorded:
        action = "REVIEW_R250_SIGNATURE_PREVIEW"
    elif signature_gate_preview_matrix.get("blocked_by"):
        action = "FIX_BLOCKER"
    else:
        action = "WAIT"
    return {
        "operator_should_review_signature_preview": bool(ready or recorded),
        "operator_should_create_signed_request_now": False,
        "operator_should_submit_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not sign request",
            "do not call Binance from this phase",
        ],
    }


def classify_tiny_live_signature_gate_preview_status(
    *,
    input_summary: Mapping[str, Any],
    signature_gate_validation: Mapping[str, Any],
    rejected_bad_confirmation: bool = False,
    recorded: bool = False,
) -> str:
    if rejected_bad_confirmation:
        return TINY_LIVE_SIGNATURE_GATE_PREVIEW_REJECTED_BAD_CONFIRMATION
    if recorded:
        return TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDED_SIGNED_WRITE_REQUIRED
    if not input_summary.get("r249_executable_payload_found"):
        return TINY_LIVE_SIGNATURE_GATE_PREVIEW_BLOCKED_BY_R249
    if signature_gate_validation.get("valid") is not True:
        return TINY_LIVE_SIGNATURE_GATE_PREVIEW_BLOCKED_BY_VALIDATION
    return TINY_LIVE_SIGNATURE_GATE_PREVIEW_READY_FOR_FUTURE_WRITE_GATE


def append_tiny_live_signature_gate_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_signature_gate_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "signature_gate_preview_record_id": record.get("signature_gate_preview_record_id")
            or f"r250_signature_gate_preview_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "signature_gate_preview_recorded": True,
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_signature_gate_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_signature_gate_preview_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_signature_gate_preview_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    summary = latest.get("executable_payload_summary") if isinstance(latest.get("executable_payload_summary"), Mapping) else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_signature_gate_preview_recorded": latest.get("signature_gate_preview_recorded") is True,
        "latest_quantity": summary.get("quantity"),
        "latest_future_gate_required": (
            (latest.get("signature_requirements_preview") or {}).get("future_gate_required")
            if isinstance(latest.get("signature_requirements_preview"), Mapping)
            else None
        ),
    }


def tiny_live_signature_gate_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_signature_gate_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(*, latest_r249: Mapping[str, Any], executable_payload: Mapping[str, Any]) -> dict[str, Any]:
    validation = validate_r249_executable_payload_for_signature_preview(latest_r249)
    controls = executable_payload.get("controls") if isinstance(executable_payload.get("controls"), Mapping) else {}
    safety = executable_payload.get("safety") if isinstance(executable_payload.get("safety"), Mapping) else {}
    return {
        "r249_executable_payload_found": bool(latest_r249),
        "r249_executable_payload_valid": validation["valid"],
        "r249_payload_signed": controls.get("signed", False) is True,
        "r249_submit_allowed": controls.get("submit_allowed", False) is True,
        "r249_order_placed": safety.get("order_placed", False) is True,
    }


def _build_executable_payload_summary(executable_payload: Mapping[str, Any]) -> dict[str, Any]:
    main = executable_payload.get("main_order") if isinstance(executable_payload.get("main_order"), Mapping) else {}
    stop = executable_payload.get("stop_order") if isinstance(executable_payload.get("stop_order"), Mapping) else {}
    take_profit = (
        executable_payload.get("take_profit_order")
        if isinstance(executable_payload.get("take_profit_order"), Mapping)
        else {}
    )
    return {
        "main_order_side": main.get("side"),
        "main_order_type": main.get("type"),
        "quantity": _number(main.get("quantity")),
        "stop_order_side": stop.get("side"),
        "stop_order_type": stop.get("type"),
        "stop_price": _number(stop.get("stopPrice")),
        "take_profit_order_side": take_profit.get("side"),
        "take_profit_order_type": take_profit.get("type"),
        "take_profit_price": _number(take_profit.get("stopPrice")),
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r249_executable_payload_found": False,
        "r249_executable_payload_valid": False,
        "r249_payload_signed": False,
        "r249_submit_allowed": False,
        "r249_order_placed": False,
    }


def _empty_executable_payload_summary() -> dict[str, Any]:
    return {
        "main_order_side": None,
        "main_order_type": None,
        "quantity": None,
        "stop_order_side": None,
        "stop_order_type": None,
        "stop_price": None,
        "take_profit_order_side": None,
        "take_profit_order_type": None,
        "take_profit_price": None,
    }


def _blocked_by(*, input_summary: Mapping[str, Any], validation: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not input_summary.get("r249_executable_payload_found"):
        blockers.append("r249_executable_payload_missing")
    elif not input_summary.get("r249_executable_payload_valid"):
        blockers.append("r249_executable_payload_not_ready")
    if validation.get("valid") is not True:
        blockers.extend(str(item) for item in validation.get("errors") or ["signature_gate_validation_failed"])
    return _dedupe(blockers)


def _r249_artifact(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = record.get("executable_payload_artifact")
    return _sanitize(dict(artifact)) if isinstance(artifact, Mapping) else {}


def _order_template(query_params: Mapping[str, Any]) -> dict[str, Any]:
    params = {key: value for key, value in query_params.items() if value not in (None, "")}
    params["timestamp"] = "<FUTURE_TIMESTAMP>"
    params["signature"] = "<NOT_CREATED>"
    return {
        "method": "POST",
        "endpoint": "/fapi/v1/order",
        "requires_signature": True,
        "signed": False,
        "query_params_preview": params,
    }


def _target_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
    artifact = _r249_artifact(record)
    return {
        "official_lane_key": target.get("official_lane_key") or artifact.get("official_lane_key"),
        "symbol": target.get("symbol") or artifact.get("symbol"),
        "timeframe": target.get("timeframe") or artifact.get("timeframe"),
        "direction": target.get("direction") or artifact.get("direction"),
        "entry_mode": target.get("entry_mode") or artifact.get("entry_mode"),
    }


def _record_matches_lane(record: Mapping[str, Any], official_lane_key: str) -> bool:
    return _target_from_record(record).get("official_lane_key") == official_lane_key


def _lane_parts(official_lane_key: str) -> tuple[str, str, str, str]:
    parts = official_lane_key.split("|")
    if len(parts) != 4:
        return "BTCUSDT", "8m", "short", "ladder_close_50_618"
    return parts[0], parts[1], parts[2], parts[3]


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number.is_integer():
        return int(number)
    return number


def _format_decimal(value: Any) -> str:
    number = _number(value)
    if number is None:
        return ""
    return f"{float(number):.10f}".rstrip("0").rstrip(".")


def _format_bool(value: Any) -> str:
    return "true" if value is True else "false"


def _recommended_next_operator_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("signature_gate_preview_ready") is True:
        return "REVIEW_R250_SIGNATURE_PREVIEW"
    if matrix.get("blocked_by"):
        return "FIX_BLOCKER"
    return "WAIT"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("recorded") is True:
        return "Create R251 signed request write gate task; keep Binance submit and order placement forbidden."
    if matrix.get("signature_gate_preview_ready") is True:
        return "Record R250 signature gate preview only after exact confirmation, then prepare R251."
    return "Fix R249 executable payload readiness before any signature preview recording."


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


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("secret", "api_key")) and item not in (False, True, None):
                sanitized[str(key)] = "<REDACTED>"
            elif lowered == "signature" and item not in (False, True, None, "<NOT_CREATED>"):
                sanitized[str(key)] = "<REDACTED>"
            else:
                sanitized[str(key)] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
