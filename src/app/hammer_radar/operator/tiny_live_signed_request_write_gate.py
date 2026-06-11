"""R251 tiny-live signed request artifact write gate.

This gate can write local signed Binance Futures request artifacts after exact
confirmation and in-memory credential loading. It never calls Binance/network
endpoints, submits requests, places orders, mutates configs/env/lane controls,
or disables the kill switch.
"""

from __future__ import annotations

import hmac
import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_executable_payload_write_gate import (
    load_tiny_live_executable_payload_write_gate_records,
    validate_executable_payload_artifact,
)
from src.app.hammer_radar.operator.tiny_live_signature_gate_preview import (
    load_tiny_live_signature_gate_preview_records,
    validate_signature_gate_preview,
)

TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_READY = "TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_READY"
TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_REJECTED = "TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_REJECTED"
TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_WRITTEN = "TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_WRITTEN"
TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_BLOCKED = "TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_BLOCKED"
TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_ERROR = "TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_ERROR"

TINY_LIVE_SIGNED_REQUEST_WRITE_READY_FOR_CONFIRMATION = (
    "TINY_LIVE_SIGNED_REQUEST_WRITE_READY_FOR_CONFIRMATION"
)
TINY_LIVE_SIGNED_REQUEST_WRITTEN_SUBMIT_GATE_REQUIRED = (
    "TINY_LIVE_SIGNED_REQUEST_WRITTEN_SUBMIT_GATE_REQUIRED"
)
TINY_LIVE_SIGNED_REQUEST_WRITE_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_SIGNED_REQUEST_WRITE_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_R250 = "TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_R250"
TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_R249 = "TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_R249"
TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_MISSING_SIGNING_CREDENTIALS = (
    "TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_MISSING_SIGNING_CREDENTIALS"
)
TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_VALIDATION = (
    "TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_SIGNED_REQUEST_WRITE_GATE"
LEDGER_FILENAME = "tiny_live_signed_request_write_gate.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R251_TINY_LIVE_SIGNED_REQUEST_WRITE_GATE"
CONFIRM_TINY_LIVE_SIGNED_REQUEST_WRITE_PHRASE = (
    "I CONFIRM TINY LIVE SIGNED REQUEST WRITE GATE ONLY; "
    "WRITE LOCAL SIGNED REQUEST ARTIFACT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
)
BINANCE_API_KEY_ENV = "BINANCE_API_KEY"
BINANCE_API_SECRET_ENV = "BINANCE_API_SECRET"

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/tiny_live_signature_gate_preview.ndjson",
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
    "signed_request_write_gate_only": True,
    "signed_request_written": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "hmac_signature_created": False,
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
    "secrets_persisted": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
}


def build_tiny_live_signed_request_write_gate(
    *,
    log_dir: str | Path | None = None,
    write_signed_request: bool = False,
    confirm_tiny_live_signed_request_write: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_tiny_live_signed_request_write == CONFIRM_TINY_LIVE_SIGNED_REQUEST_WRITE_PHRASE
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    try:
        latest_r250 = load_latest_tiny_live_signature_gate_preview(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r249 = load_latest_tiny_live_executable_payload_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        r250_validation = validate_r250_signature_preview_for_signed_write(latest_r250)
        r249_validation = validate_r249_executable_payload_for_signed_write(latest_r249)
        executable_payload = _r249_artifact(latest_r249)
        input_summary = _build_input_summary(
            latest_r250=latest_r250,
            r250_validation=r250_validation,
            latest_r249=latest_r249,
            r249_validation=r249_validation,
        )
        credential_presence = detect_signing_credentials_presence()
        unsigned_payloads = build_unsigned_order_request_payloads(executable_payload, now=generated_at)
        preview = build_signed_request_artifact_preview(
            input_summary=input_summary,
            credential_presence_preview=credential_presence,
            unsigned_request_payloads=unsigned_payloads,
        )
        blocked_by = _blocked_by(
            input_summary=input_summary,
            write_requested=write_signed_request,
            confirmation_valid=confirmation_valid,
            credential_presence=credential_presence,
        )

        artifact: dict[str, Any] = {}
        signed_validation = {"valid": False, "errors": ["signed_request_not_created"], "warnings": []}
        written = False
        if write_signed_request and not confirmation_valid:
            status = TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_REJECTED
            overall = TINY_LIVE_SIGNED_REQUEST_WRITE_REJECTED_BAD_CONFIRMATION
        elif write_signed_request and confirmation_valid and not _credentials_present(credential_presence):
            status = TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_BLOCKED
            overall = TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_MISSING_SIGNING_CREDENTIALS
        elif input_summary.get("r250_signature_preview_valid") is not True:
            status = TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_BLOCKED
            overall = TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_R250
        elif input_summary.get("r249_executable_payload_valid") is not True:
            status = TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_BLOCKED
            overall = TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_R249
        elif write_signed_request and confirmation_valid:
            credentials = load_signing_credentials_for_confirmed_write(
                confirm_tiny_live_signed_request_write=confirm_tiny_live_signed_request_write
            )
            artifact = build_signed_request_artifact(
                unsigned_request_payloads=unsigned_payloads,
                api_key=credentials["api_key"],
                api_secret=credentials["api_secret"],
                official_lane_key=official_lane_key,
                now=generated_at,
            )
            signed_validation = validate_signed_request_artifact(
                artifact,
                raw_api_key=credentials["api_key"],
                raw_api_secret=credentials["api_secret"],
            )
            write_result = write_signed_request_artifact_if_confirmed(
                signed_request_artifact=artifact,
                confirm_tiny_live_signed_request_write=confirm_tiny_live_signed_request_write,
                raw_api_key=credentials["api_key"],
                raw_api_secret=credentials["api_secret"],
                log_dir=resolved_log_dir,
            )
            written = write_result.get("written") is True
            status = TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_WRITTEN if written else TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_BLOCKED
            overall = (
                TINY_LIVE_SIGNED_REQUEST_WRITTEN_SUBMIT_GATE_REQUIRED
                if written
                else TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_VALIDATION
            )
        elif blocked_by:
            status = TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_BLOCKED
            overall = classify_tiny_live_signed_request_write_gate_status(
                input_summary=input_summary,
                signed_request_validation=signed_validation,
                write_requested=write_signed_request,
                rejected_bad_confirmation=False,
                credentials_present=_credentials_present(credential_presence),
                signed_request_written=False,
            )
        else:
            status = TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_READY
            overall = TINY_LIVE_SIGNED_REQUEST_WRITE_READY_FOR_CONFIRMATION

        if not artifact and not written:
            signed_validation = {
                "valid": bool(input_summary.get("r250_signature_preview_valid") and input_summary.get("r249_executable_payload_valid")),
                "errors": [],
                "warnings": ["preview_only_no_signed_artifact_created"],
            }

        post_write = build_post_write_signed_request_verification(
            signed_request_artifact=artifact,
            signed_request_written=written,
            log_dir=resolved_log_dir,
        )
        matrix = build_signed_request_write_gate_matrix(
            input_summary=input_summary,
            credentials_present=_credentials_present(credential_presence),
            write_confirmed=bool(write_signed_request and confirmation_valid),
            signed_request_written=written,
            signed_request_valid=signed_validation.get("valid") is True,
            blocked_by=blocked_by,
        )
        operator_packet = build_operator_signed_request_write_packet(matrix)
        safety = _safety(written)
        return _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "write_signed_request_requested": bool(write_signed_request),
                "confirmation_valid": bool(confirmation_valid),
                "signed_request_written": bool(written),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "signed_request_write_gate_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "input_summary": input_summary,
                "credential_presence_preview": credential_presence,
                "unsigned_request_payloads": unsigned_payloads,
                "signed_request_artifact_preview": preview,
                "signed_request_validation": signed_validation,
                "post_write_verification": post_write,
                "signed_request_write_gate_matrix": matrix,
                "operator_signed_request_write_packet": operator_packet,
                "recommended_next_operator_move": _recommended_next_operator_move(matrix),
                "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
                "signed_request_write_overall_status": overall,
                "do_not_run_yet": _do_not_run_yet(),
                "safety": safety,
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = build_signed_request_write_gate_matrix(
            input_summary=_empty_input_summary(),
            credentials_present=False,
            write_confirmed=False,
            signed_request_written=False,
            signed_request_valid=False,
            blocked_by=["signed_request_write_gate_error"],
        )
        return _sanitize(
            {
                "status": TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "write_signed_request_requested": bool(write_signed_request),
                "confirmation_valid": bool(confirmation_valid),
                "signed_request_written": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "signed_request_write_gate_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "input_summary": _empty_input_summary(),
                "credential_presence_preview": _empty_credential_presence_preview(),
                "unsigned_request_payloads": {},
                "signed_request_artifact_preview": _empty_signed_request_artifact_preview(),
                "signed_request_validation": {"valid": False, "errors": ["signed_request_write_gate_error"], "warnings": []},
                "post_write_verification": _empty_post_write_verification(),
                "signed_request_write_gate_matrix": matrix,
                "operator_signed_request_write_packet": build_operator_signed_request_write_packet(matrix),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R251 signed request write gate error before any submit-readiness preview.",
                "signed_request_write_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": _safety(False),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_signature_gate_preview(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_signature_gate_preview_records(log_dir=log_dir, limit=50)
    for record in records:
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("signature_gate_preview_recorded") is True
            and validate_r250_signature_preview_for_signed_write(record).get("valid") is True
        ):
            return _sanitize(record)
    return {}


def load_latest_tiny_live_executable_payload_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_executable_payload_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        artifact = _r249_artifact(record)
        if (
            _record_matches_lane(record, official_lane_key)
            and record.get("executable_payload_written") is True
            and validate_r249_executable_payload_for_signed_write(record).get("valid") is True
            and artifact.get("controls", {}).get("signed") is False
        ):
            return _sanitize(record)
    return {}


def validate_r250_signature_preview_for_signed_write(record: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not record:
        errors.append("r250_signature_preview_missing")
        return {"valid": False, "errors": errors, "warnings": warnings}
    if record.get("signature_gate_preview_recorded") is not True:
        errors.append("r250_signature_preview_not_recorded")
    if record.get("signature_gate_preview_overall_status") not in {
        "TINY_LIVE_SIGNATURE_GATE_PREVIEW_RECORDED_SIGNED_WRITE_REQUIRED",
        "TINY_LIVE_SIGNATURE_GATE_PREVIEW_READY_FOR_FUTURE_WRITE_GATE",
    }:
        errors.append("r250_signature_preview_status_invalid")
    input_summary = record.get("input_summary") if isinstance(record.get("input_summary"), Mapping) else {}
    executable_summary = record.get("executable_payload_summary") if isinstance(record.get("executable_payload_summary"), Mapping) else {}
    templates = (
        record.get("unsigned_request_templates_preview")
        if isinstance(record.get("unsigned_request_templates_preview"), Mapping)
        else {}
    )
    requirements = (
        record.get("signature_requirements_preview")
        if isinstance(record.get("signature_requirements_preview"), Mapping)
        else {}
    )
    validation = validate_signature_gate_preview(
        input_summary=input_summary,
        executable_payload_summary=executable_summary,
        unsigned_request_templates_preview=templates,
        signature_requirements_preview=requirements,
    )
    errors.extend(str(error) for error in validation.get("errors") or [])
    warnings.extend(str(warning) for warning in validation.get("warnings") or [])
    target = _target_from_record(record)
    if target.get("official_lane_key") != OFFICIAL_LANE_KEY:
        errors.append("r250_official_lane_key_invalid")
    safety = record.get("safety") if isinstance(record.get("safety"), Mapping) else {}
    for key in ("api_key_loaded", "api_secret_loaded", "secrets_read", "secrets_shown", "hmac_signature_created", "signed_request_written"):
        if safety.get(key) is not False:
            errors.append(f"r250_safety_{key}_must_remain_false")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def validate_r249_executable_payload_for_signed_write(record: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    artifact = _r249_artifact(record)
    if not record:
        errors.append("r249_executable_payload_missing")
        return {"valid": False, "errors": errors, "warnings": warnings}
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
    for key in ("signed_order_request_created", "signed_trading_request_created", "submit_allowed", "order_placed", "binance_order_endpoint_called", "network_allowed"):
        if safety.get(key) is not False:
            errors.append(f"r249_safety_{key}_must_remain_false")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def build_unsigned_order_request_payloads(executable_payload: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    timestamp_ms = int((now or datetime.now(UTC)).timestamp() * 1000)
    main = executable_payload.get("main_order") if isinstance(executable_payload.get("main_order"), Mapping) else {}
    stop = executable_payload.get("stop_order") if isinstance(executable_payload.get("stop_order"), Mapping) else {}
    take_profit = executable_payload.get("take_profit_order") if isinstance(executable_payload.get("take_profit_order"), Mapping) else {}
    quantity = _format_decimal(main.get("quantity") or stop.get("quantity") or take_profit.get("quantity"))
    return {
        "main_order": _unsigned_request(
            {
                "symbol": main.get("symbol") or "BTCUSDT",
                "side": main.get("side"),
                "type": main.get("type"),
                "quantity": quantity,
                "timestamp": str(timestamp_ms),
            }
        ),
        "stop_order": _unsigned_request(
            {
                "symbol": stop.get("symbol") or "BTCUSDT",
                "side": stop.get("side"),
                "type": stop.get("type"),
                "quantity": quantity,
                "stopPrice": _format_decimal(stop.get("stopPrice")),
                "reduceOnly": _format_bool(stop.get("reduceOnly")),
                "workingType": stop.get("workingType") or "MARK_PRICE",
                "timestamp": str(timestamp_ms),
            }
        ),
        "take_profit_order": _unsigned_request(
            {
                "symbol": take_profit.get("symbol") or "BTCUSDT",
                "side": take_profit.get("side"),
                "type": take_profit.get("type"),
                "quantity": quantity,
                "stopPrice": _format_decimal(take_profit.get("stopPrice")),
                "reduceOnly": _format_bool(take_profit.get("reduceOnly")),
                "workingType": take_profit.get("workingType") or "MARK_PRICE",
                "timestamp": str(timestamp_ms),
            }
        ),
    }


def build_canonical_query_string(params: Mapping[str, Any]) -> str:
    clean = [(str(key), str(value)) for key, value in params.items() if value not in (None, "")]
    return urlencode(clean, doseq=False, safe="")


def redact_api_key_hint(api_key: str | None) -> str:
    if not api_key:
        return "<REDACTED_MISSING>"
    if len(api_key) >= 12:
        return f"{api_key[:4]}...{api_key[-4:]}"
    return "<REDACTED_PRESENT>"


def detect_signing_credentials_presence() -> dict[str, Any]:
    return {
        "api_key_present": BINANCE_API_KEY_ENV in os.environ,
        "api_secret_present": BINANCE_API_SECRET_ENV in os.environ,
        "api_key_loaded": False,
        "api_secret_loaded": False,
        "secrets_read": False,
        "secrets_shown": False,
    }


def load_signing_credentials_for_confirmed_write(*, confirm_tiny_live_signed_request_write: str | None) -> dict[str, str]:
    if confirm_tiny_live_signed_request_write != CONFIRM_TINY_LIVE_SIGNED_REQUEST_WRITE_PHRASE:
        return {"api_key": "", "api_secret": ""}
    return {
        "api_key": os.environ.get(BINANCE_API_KEY_ENV, ""),
        "api_secret": os.environ.get(BINANCE_API_SECRET_ENV, ""),
    }


def sign_query_string_hmac_sha256(query_string: str, api_secret: str) -> str:
    return hmac.new(api_secret.encode("utf-8"), query_string.encode("utf-8"), sha256).hexdigest()


def build_signed_request_artifact_preview(
    *,
    input_summary: Mapping[str, Any],
    credential_presence_preview: Mapping[str, Any],
    unsigned_request_payloads: Mapping[str, Any],
) -> dict[str, Any]:
    would_write = (
        input_summary.get("r250_signature_preview_valid") is True
        and input_summary.get("r249_executable_payload_valid") is True
        and bool(unsigned_request_payloads)
    )
    return {
        "would_write": bool(would_write),
        "write_requires_confirmation": True,
        "requires_credentials": True,
        "credentials_present": _credentials_present(credential_presence_preview),
        "signed": False,
        "submit_allowed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
    }


def build_signed_request_artifact(
    *,
    unsigned_request_payloads: Mapping[str, Any],
    api_key: str,
    api_secret: str,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    signed_requests: dict[str, Any] = {}
    for order_key in ("main_order", "stop_order", "take_profit_order"):
        request = unsigned_request_payloads.get(order_key) if isinstance(unsigned_request_payloads.get(order_key), Mapping) else {}
        query_string = str(request.get("query_string_without_signature") or "")
        signed_requests[order_key] = {
            "method": "POST",
            "endpoint": "/fapi/v1/order",
            "query_string_without_signature": query_string,
            "signature": sign_query_string_hmac_sha256(query_string, api_secret),
            "signed": True,
            "submit_allowed": False,
            "network_allowed": False,
        }
    return {
        "signed_request_artifact_id": f"r251_signed_request_{symbol}_{timeframe}_{direction}_{entry_mode}_{uuid4().hex}",
        "artifact_only": True,
        "created_by_phase": CREATED_BY_PHASE,
        "created_at": generated_at.isoformat(),
        "official_lane_key": official_lane_key,
        "exchange": "binance_futures",
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "credential_context": {
            "api_key_present": bool(api_key),
            "api_secret_present": bool(api_secret),
            "api_key_hint": redact_api_key_hint(api_key),
            "api_secret_persisted": False,
            "secrets_printed": False,
            "secrets_persisted": False,
        },
        "signed_requests": signed_requests,
        "controls": {
            "signed_request_written": True,
            "submit_allowed": False,
            "binance_call_allowed": False,
            "network_allowed": False,
            "requires_submit_gate": True,
            "requires_future_readonly_mark_price_refresh_before_submit": True,
            "requires_operator_final_submit_confirmation": True,
            "kill_switch_required": True,
        },
        "safety": {
            "hmac_signature_created": True,
            "signed_order_request_created": True,
            "signed_trading_request_created": True,
            "submit_allowed": False,
            "order_placed": False,
            "binance_order_endpoint_called": False,
            "network_allowed": False,
            "secrets_shown": False,
            "secrets_persisted": False,
        },
    }


def validate_signed_request_artifact(
    artifact: Mapping[str, Any],
    *,
    raw_api_key: str | None = None,
    raw_api_secret: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    expected = {
        "official_lane_key": OFFICIAL_LANE_KEY,
        "exchange": "binance_futures",
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "entry_mode": "ladder_close_50_618",
        "artifact_only": True,
        "created_by_phase": CREATED_BY_PHASE,
    }
    for key, value in expected.items():
        if artifact.get(key) != value:
            errors.append(f"{key}_invalid")
    signed_requests = artifact.get("signed_requests") if isinstance(artifact.get("signed_requests"), Mapping) else {}
    if set(signed_requests) != {"main_order", "stop_order", "take_profit_order"}:
        errors.append("signed_requests_keys_invalid")
    artifact_text = json.dumps(artifact, sort_keys=True, separators=(",", ":"))
    if raw_api_secret and raw_api_secret in artifact_text:
        errors.append("raw_api_secret_persisted")
    if raw_api_key and raw_api_key in artifact_text:
        errors.append("raw_api_key_persisted")
    for order_key in ("main_order", "stop_order", "take_profit_order"):
        request = signed_requests.get(order_key) if isinstance(signed_requests.get(order_key), Mapping) else {}
        query = str(request.get("query_string_without_signature") or "")
        if request.get("method") != "POST":
            errors.append(f"{order_key}_method_invalid")
        if request.get("endpoint") != "/fapi/v1/order":
            errors.append(f"{order_key}_endpoint_invalid")
        if request.get("signed") is not True:
            errors.append(f"{order_key}_signed_invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", str(request.get("signature") or "")):
            errors.append(f"{order_key}_signature_invalid")
        if "signature=" in query:
            errors.append(f"{order_key}_query_contains_signature")
        if raw_api_secret and raw_api_secret in query:
            errors.append(f"{order_key}_query_contains_api_secret")
        if raw_api_key and raw_api_key in query:
            errors.append(f"{order_key}_query_contains_api_key")
        for key in ("submit_allowed", "network_allowed"):
            if request.get(key) is not False:
                errors.append(f"{order_key}_{key}_invalid")
    credential_context = (
        artifact.get("credential_context") if isinstance(artifact.get("credential_context"), Mapping) else {}
    )
    if credential_context.get("api_secret_persisted") is not False:
        errors.append("credential_context_api_secret_persisted_invalid")
    if credential_context.get("secrets_printed") is not False:
        errors.append("credential_context_secrets_printed_invalid")
    if credential_context.get("secrets_persisted") is not False:
        errors.append("credential_context_secrets_persisted_invalid")
    controls = artifact.get("controls") if isinstance(artifact.get("controls"), Mapping) else {}
    safety = artifact.get("safety") if isinstance(artifact.get("safety"), Mapping) else {}
    for key in ("submit_allowed", "binance_call_allowed", "network_allowed"):
        if controls.get(key) is not False:
            errors.append(f"controls_{key}_invalid")
    for key in ("requires_submit_gate", "requires_future_readonly_mark_price_refresh_before_submit", "requires_operator_final_submit_confirmation", "kill_switch_required"):
        if controls.get(key) is not True:
            errors.append(f"controls_{key}_invalid")
    if controls.get("signed_request_written") is not True:
        errors.append("controls_signed_request_written_invalid")
    for key in ("submit_allowed", "order_placed", "binance_order_endpoint_called", "network_allowed", "secrets_shown", "secrets_persisted"):
        if safety.get(key) is not False:
            errors.append(f"safety_{key}_invalid")
    for key in ("hmac_signature_created", "signed_order_request_created", "signed_trading_request_created"):
        if safety.get(key) is not True:
            errors.append(f"safety_{key}_invalid")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": _dedupe(warnings)}


def write_signed_request_artifact_if_confirmed(
    *,
    signed_request_artifact: Mapping[str, Any],
    confirm_tiny_live_signed_request_write: str | None,
    raw_api_key: str | None = None,
    raw_api_secret: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    if confirm_tiny_live_signed_request_write != CONFIRM_TINY_LIVE_SIGNED_REQUEST_WRITE_PHRASE:
        return {"written": False, "reason": "bad_confirmation"}
    validation = validate_signed_request_artifact(
        signed_request_artifact,
        raw_api_key=raw_api_key,
        raw_api_secret=raw_api_secret,
    )
    if validation["valid"] is not True:
        return {"written": False, "reason": "validation_failed", "validation": validation}
    record = append_tiny_live_signed_request_write_gate_record(
        {
            "status": TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_WRITTEN,
            "generated_at": signed_request_artifact.get("created_at"),
            "signed_request_written": True,
            "write_signed_request_requested": True,
            "confirmation_valid": True,
            "target_scope": _target_scope(str(signed_request_artifact.get("official_lane_key") or OFFICIAL_LANE_KEY)),
            "signed_request_artifact": dict(signed_request_artifact),
            "signed_request_validation": validation,
            "post_write_verification": {
                "signed_request_written": True,
                "matching_signed_request_found": True,
                "matching_signed_request_valid": True,
                "submit_allowed": False,
                "order_placed": False,
                "binance_call_allowed": False,
                "network_allowed": False,
                "secrets_shown": False,
                "secrets_persisted": False,
            },
            "safety": _safety(True),
        },
        log_dir=log_dir,
    )
    return {"written": True, "record": record}


def build_post_write_signed_request_verification(
    *,
    signed_request_artifact: Mapping[str, Any],
    signed_request_written: bool,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_tiny_live_signed_request_write_gate_records(log_dir=log_dir, limit=50) if signed_request_written else []
    matching = _matching_signed_request_record(records, signed_request_artifact)
    artifact = matching.get("signed_request_artifact") if isinstance(matching.get("signed_request_artifact"), Mapping) else {}
    validation = validate_signed_request_artifact(artifact)
    controls = artifact.get("controls") if isinstance(artifact.get("controls"), Mapping) else {}
    safety = artifact.get("safety") if isinstance(artifact.get("safety"), Mapping) else {}
    return {
        "signed_request_written": bool(signed_request_written),
        "matching_signed_request_found": bool(matching),
        "matching_signed_request_valid": bool(matching and validation["valid"]),
        "submit_allowed": controls.get("submit_allowed", False) is True,
        "order_placed": safety.get("order_placed", False) is True,
        "binance_call_allowed": controls.get("binance_call_allowed", False) is True,
        "network_allowed": controls.get("network_allowed", False) is True,
        "secrets_shown": safety.get("secrets_shown", False) is True,
        "secrets_persisted": safety.get("secrets_persisted", False) is True,
    }


def build_signed_request_write_gate_matrix(
    *,
    input_summary: Mapping[str, Any],
    credentials_present: bool,
    write_confirmed: bool,
    signed_request_written: bool,
    signed_request_valid: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers = list(blocked_by or [])
    if not input_summary.get("r250_signature_preview_valid"):
        blockers.append("r250_signature_preview_not_ready")
    if not input_summary.get("r249_executable_payload_valid"):
        blockers.append("r249_executable_payload_not_ready")
    if not credentials_present:
        blockers.append("missing_signing_credentials")
    if not write_confirmed:
        blockers.append("exact_signed_request_write_confirmation_required")
    if not signed_request_valid:
        blockers.append("signed_request_not_valid")
    if signed_request_written:
        blockers = [
            "submit_gate_required",
            "future_readonly_mark_price_refresh_required_before_submit",
            "kill_switch_still_required",
        ]
    return {
        "r250_signature_preview_ready": input_summary.get("r250_signature_preview_valid") is True,
        "r249_executable_payload_ready": input_summary.get("r249_executable_payload_valid") is True,
        "credentials_present": bool(credentials_present),
        "write_confirmed": bool(write_confirmed),
        "signed_request_written": bool(signed_request_written),
        "signed_request_valid": bool(signed_request_valid),
        "submit_gate_required": True,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_signed_request_write_packet(signed_request_write_gate_matrix: Mapping[str, Any]) -> dict[str, Any]:
    written = signed_request_write_gate_matrix.get("signed_request_written") is True
    ready = (
        signed_request_write_gate_matrix.get("r250_signature_preview_ready") is True
        and signed_request_write_gate_matrix.get("r249_executable_payload_ready") is True
        and signed_request_write_gate_matrix.get("credentials_present") is True
    )
    if written:
        action = "REVIEW_R251_RESULT"
    elif ready:
        action = "CONFIRM_R251_SIGNED_REQUEST_WRITE"
    elif signed_request_write_gate_matrix.get("blocked_by"):
        action = "FIX_BLOCKER"
    else:
        action = "WAIT"
    return {
        "operator_should_review_signed_request_artifact": bool(ready or written),
        "operator_should_submit_now": False,
        "operator_should_place_order": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not submit",
            "do not call Binance from this phase",
        ],
    }


def classify_tiny_live_signed_request_write_gate_status(
    *,
    input_summary: Mapping[str, Any],
    signed_request_validation: Mapping[str, Any],
    write_requested: bool = False,
    rejected_bad_confirmation: bool = False,
    credentials_present: bool = False,
    signed_request_written: bool = False,
) -> str:
    if rejected_bad_confirmation:
        return TINY_LIVE_SIGNED_REQUEST_WRITE_REJECTED_BAD_CONFIRMATION
    if signed_request_written:
        return TINY_LIVE_SIGNED_REQUEST_WRITTEN_SUBMIT_GATE_REQUIRED
    if not input_summary.get("r250_signature_preview_found") or not input_summary.get("r250_signature_preview_valid"):
        return TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_R250
    if not input_summary.get("r249_executable_payload_found") or not input_summary.get("r249_executable_payload_valid"):
        return TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_R249
    if write_requested and not credentials_present:
        return TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_MISSING_SIGNING_CREDENTIALS
    if signed_request_validation.get("valid") is not True:
        return TINY_LIVE_SIGNED_REQUEST_WRITE_BLOCKED_BY_VALIDATION
    return TINY_LIVE_SIGNED_REQUEST_WRITE_READY_FOR_CONFIRMATION


def append_tiny_live_signed_request_write_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_signed_request_write_gate_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "signed_request_write_gate_record_id": record.get("signed_request_write_gate_record_id")
            or f"r251_signed_request_write_gate_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "signed_request_written": record.get("signed_request_written") is True,
            "safety": dict(record.get("safety") or _safety(record.get("signed_request_written") is True)),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_signed_request_write_gate_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_signed_request_write_gate_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_signed_request_write_gate_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    artifact = latest.get("signed_request_artifact") if isinstance(latest.get("signed_request_artifact"), Mapping) else {}
    signed_requests = artifact.get("signed_requests") if isinstance(artifact.get("signed_requests"), Mapping) else {}
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_signed_request_written": latest.get("signed_request_written") is True,
        "latest_signed_request_artifact_id": artifact.get("signed_request_artifact_id"),
        "latest_signed_request_count": len(signed_requests),
    }


def tiny_live_signed_request_write_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_signed_request_write_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_input_summary(
    *,
    latest_r250: Mapping[str, Any],
    r250_validation: Mapping[str, Any],
    latest_r249: Mapping[str, Any],
    r249_validation: Mapping[str, Any],
) -> dict[str, Any]:
    artifact = _r249_artifact(latest_r249)
    controls = artifact.get("controls") if isinstance(artifact.get("controls"), Mapping) else {}
    safety = artifact.get("safety") if isinstance(artifact.get("safety"), Mapping) else {}
    return {
        "r250_signature_preview_found": bool(latest_r250),
        "r250_signature_preview_valid": r250_validation.get("valid") is True,
        "r249_executable_payload_found": bool(latest_r249),
        "r249_executable_payload_valid": r249_validation.get("valid") is True,
        "r249_payload_signed": controls.get("signed", False) is True,
        "r249_submit_allowed": controls.get("submit_allowed", False) is True,
        "r249_order_placed": safety.get("order_placed", False) is True,
    }


def _empty_input_summary() -> dict[str, Any]:
    return {
        "r250_signature_preview_found": False,
        "r250_signature_preview_valid": False,
        "r249_executable_payload_found": False,
        "r249_executable_payload_valid": False,
        "r249_payload_signed": False,
        "r249_submit_allowed": False,
        "r249_order_placed": False,
    }


def _empty_credential_presence_preview() -> dict[str, Any]:
    return {
        "api_key_present": False,
        "api_secret_present": False,
        "api_key_loaded": False,
        "api_secret_loaded": False,
        "secrets_read": False,
        "secrets_shown": False,
    }


def _empty_signed_request_artifact_preview() -> dict[str, Any]:
    return {
        "would_write": False,
        "write_requires_confirmation": True,
        "requires_credentials": True,
        "signed": False,
        "submit_allowed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
    }


def _empty_post_write_verification() -> dict[str, Any]:
    return {
        "signed_request_written": False,
        "matching_signed_request_found": False,
        "matching_signed_request_valid": False,
        "submit_allowed": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
        "secrets_shown": False,
        "secrets_persisted": False,
    }


def _blocked_by(
    *,
    input_summary: Mapping[str, Any],
    write_requested: bool,
    confirmation_valid: bool,
    credential_presence: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not input_summary.get("r250_signature_preview_found"):
        blockers.append("r250_signature_preview_missing")
    elif not input_summary.get("r250_signature_preview_valid"):
        blockers.append("r250_signature_preview_not_ready")
    if not input_summary.get("r249_executable_payload_found"):
        blockers.append("r249_executable_payload_missing")
    elif not input_summary.get("r249_executable_payload_valid"):
        blockers.append("r249_executable_payload_not_ready")
    if write_requested and not confirmation_valid:
        blockers.append("bad_confirmation")
    if write_requested and confirmation_valid and not _credentials_present(credential_presence):
        blockers.append("missing_signing_credentials")
    return _dedupe(blockers)


def _unsigned_request(query_params: Mapping[str, Any]) -> dict[str, Any]:
    params = {key: value for key, value in query_params.items() if value not in (None, "")}
    return {
        "method": "POST",
        "endpoint": "/fapi/v1/order",
        "requires_signature": True,
        "signed": False,
        "submit_allowed": False,
        "network_allowed": False,
        "query_params": params,
        "query_string_without_signature": build_canonical_query_string(params),
    }


def _matching_signed_request_record(records: Sequence[Mapping[str, Any]], signed_request_artifact: Mapping[str, Any]) -> dict[str, Any]:
    expected_id = signed_request_artifact.get("signed_request_artifact_id")
    for record in records:
        artifact = record.get("signed_request_artifact") if isinstance(record.get("signed_request_artifact"), Mapping) else {}
        if artifact.get("signed_request_artifact_id") == expected_id and record.get("signed_request_written") is True:
            return _sanitize(record)
    return {}


def _r249_artifact(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = record.get("executable_payload_artifact")
    return _sanitize(dict(artifact)) if isinstance(artifact, Mapping) else {}


def _target_scope(official_lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    return {
        "official_lane_key": official_lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "signed_request_write_gate_only": True,
        "submit_allowed": False,
        "order_placed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
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


def _credentials_present(credential_presence: Mapping[str, Any]) -> bool:
    return credential_presence.get("api_key_present") is True and credential_presence.get("api_secret_present") is True


def _recommended_next_operator_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("signed_request_written") is True:
        return "REVIEW_R251_RESULT"
    if (
        matrix.get("r250_signature_preview_ready") is True
        and matrix.get("r249_executable_payload_ready") is True
        and matrix.get("credentials_present") is True
    ):
        return "CONFIRM_R251_SIGNED_REQUEST_WRITE"
    if matrix.get("blocked_by"):
        return "FIX_BLOCKER"
    return "WAIT"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("signed_request_written") is True:
        return "Create R252 tiny-live submit readiness preview; require read-only mark-price refresh and keep no Binance call/no submit/no order."
    if matrix.get("r250_signature_preview_ready") is True and matrix.get("r249_executable_payload_ready") is True:
        return "Await exact R251 confirmation and signing credentials before local signed request artifact write."
    return "Fix R250/R249 readiness before any signed request artifact write."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "kill switch disable",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _safety(written: bool) -> dict[str, Any]:
    safety = dict(SAFETY)
    safety.update(
        {
            "signed_request_written": bool(written),
            "signed_order_request_created": bool(written),
            "signed_trading_request_created": bool(written),
            "hmac_signature_created": bool(written),
        }
    )
    return safety


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
            if lowered == "api_key_hint":
                sanitized[str(key)] = item
            elif "secret" in lowered and item not in (False, True, None):
                sanitized[str(key)] = "<REDACTED>"
            elif lowered in {"api_key", "apikey"} and item not in (False, True, None):
                sanitized[str(key)] = "<REDACTED>"
            else:
                sanitized[str(key)] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
