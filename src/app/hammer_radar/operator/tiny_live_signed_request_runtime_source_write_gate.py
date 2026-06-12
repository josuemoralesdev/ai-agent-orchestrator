"""R251E tiny-live signed request runtime-source write gate.

This wrapper uses the R251D runtime credential source resolver and delegates
local signed request artifact creation to the existing R251 write gate. It does
not call Binance/network endpoints, submit, place orders, mutate persistent
env/config/lane controls, or persist secret values.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import (
    DEFAULT_OFFICIAL_TINY_LIVE_LANE,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_runtime_credential_source_drill import (
    BINANCE_API_KEY_ENV,
    BINANCE_API_SECRET_ENV,
    OVERRIDE_ENV_NAME,
    PRESENT_REDACTED,
    build_runtime_credential_source_summary,
    detect_external_env_file_credential_presence,
    detect_process_env_credential_presence,
    load_tiny_live_runtime_credential_source_drill_records,
    resolve_runtime_credential_source_path,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_write_gate import (
    CONFIRM_TINY_LIVE_SIGNED_REQUEST_WRITE_PHRASE,
    TINY_LIVE_SIGNED_REQUEST_WRITE_GATE_WRITTEN,
    build_tiny_live_signed_request_write_gate,
    load_tiny_live_signed_request_write_gate_records,
    validate_signed_request_artifact,
)

TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_READY = (
    "TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_READY"
)
TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_REJECTED = (
    "TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_REJECTED"
)
TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_WRITTEN = (
    "TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_WRITTEN"
)
TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_BLOCKED = (
    "TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_BLOCKED"
)
TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_ERROR = (
    "TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_ERROR"
)

TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_READY_FOR_CONFIRMATION = (
    "TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_READY_FOR_CONFIRMATION"
)
TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITTEN_SUBMIT_READINESS_REQUIRED = (
    "TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITTEN_SUBMIT_READINESS_REQUIRED"
)
TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_REJECTED_BAD_CONFIRMATION"
)
TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_BLOCKED_BY_CREDENTIAL_SOURCE = (
    "TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_BLOCKED_BY_CREDENTIAL_SOURCE"
)
TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_BLOCKED_BY_R251 = (
    "TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_BLOCKED_BY_R251"
)
TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_BLOCKED_BY_SECRET_VALIDATION = (
    "TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_BLOCKED_BY_SECRET_VALIDATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE"
LEDGER_FILENAME = "tiny_live_signed_request_runtime_source_write_gate.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R251E_TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE"
CONFIRM_TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_PHRASE = (
    "I CONFIRM TINY LIVE SIGNED REQUEST RUNTIME SOURCE WRITE GATE ONLY; "
    "WRITE LOCAL SIGNED REQUEST ARTIFACT ONLY; NO SUBMIT; NO ORDER; NO BINANCE CALL."
)

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/tiny_live_runtime_credential_source_drill.py",
    "src/app/hammer_radar/operator/tiny_live_signed_request_write_gate.py",
    "logs/hammer_radar_forward/tiny_live_runtime_credential_source_drill.ndjson",
    "logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson",
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
    "signed_request_runtime_source_write_gate_only": True,
    "hmac_signature_created": False,
    "signed_request_written": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
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
    "secret_values_in_output": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "official_tiny_live_lane_changed": False,
}


def build_tiny_live_signed_request_runtime_source_write_gate(
    *,
    log_dir: str | Path | None = None,
    write_signed_request_runtime_source: bool = False,
    confirm_tiny_live_signed_request_runtime_source_write: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_signed_request_runtime_source_write
        == CONFIRM_TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_PHRASE
    )
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    try:
        latest_r251d = load_latest_tiny_live_runtime_credential_source_drill(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        latest_r251 = load_latest_tiny_live_signed_request_write_gate(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
        )
        credential_context = validate_runtime_credential_source_ready()
        plan = build_r251e_signed_request_write_plan(
            credential_source_ready=credential_context["credential_source_ready"],
            write_requested=write_signed_request_runtime_source,
            confirmation_valid=confirmation_valid,
        )

        r251_result: dict[str, Any] = {}
        written = False
        secret_validation = _empty_secret_validation()
        artifact_summary = _artifact_summary({})
        post_write = build_r251e_post_write_verification(
            signed_request_written=False,
            r251_result={},
            log_dir=resolved_log_dir,
        )
        raw_api_key: str | None = None
        raw_api_secret: str | None = None

        if write_signed_request_runtime_source and not confirmation_valid:
            status = TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_REJECTED
            overall = TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_REJECTED_BAD_CONFIRMATION
        elif credential_context["credential_source_ready"] is not True:
            status = TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_BLOCKED
            overall = TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_BLOCKED_BY_CREDENTIAL_SOURCE
        elif write_signed_request_runtime_source and confirmation_valid:
            credentials = resolve_runtime_signing_credentials_for_confirmed_write(
                confirm_tiny_live_signed_request_runtime_source_write=(
                    confirm_tiny_live_signed_request_runtime_source_write
                )
            )
            raw_api_key = credentials.get("api_key") or ""
            raw_api_secret = credentials.get("api_secret") or ""
            if not raw_api_key or not raw_api_secret:
                status = TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_BLOCKED
                overall = TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_BLOCKED_BY_CREDENTIAL_SOURCE
            else:
                r251_result = invoke_r251_signed_request_artifact_write_with_runtime_source(
                    api_key=raw_api_key,
                    api_secret=raw_api_secret,
                    log_dir=resolved_log_dir,
                    now=generated_at,
                )
                written = r251_result.get("signed_request_written") is True
                r251_record = (
                    load_latest_tiny_live_signed_request_write_gate(
                        log_dir=resolved_log_dir,
                        official_lane_key=official_lane_key,
                    )
                    if written
                    else {}
                )
                signed_artifact = _r251_artifact(r251_result) or _r251_artifact(r251_record)
                artifact_summary = _artifact_summary(signed_artifact)
                artifact_validation = validate_r251e_signed_request_artifact(signed_artifact)
                secret_validation = validate_no_secret_values_in_artifact(
                    signed_artifact,
                    raw_api_key=raw_api_key,
                    raw_api_secret=raw_api_secret,
                    extra_payload=r251_result,
                )
                post_write = build_r251e_post_write_verification(
                    signed_request_written=written,
                    r251_result=r251_result,
                    signed_request_artifact=signed_artifact,
                    log_dir=resolved_log_dir,
                )
                if not written:
                    status = TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_BLOCKED
                    overall = TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_BLOCKED_BY_R251
                elif artifact_validation["valid"] is not True or secret_validation["valid"] is not True:
                    status = TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_BLOCKED
                    overall = (
                        TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_BLOCKED_BY_SECRET_VALIDATION
                    )
                    secret_validation = _merge_secret_validation_errors(
                        secret_validation,
                        artifact_validation.get("errors") or [],
                    )
                else:
                    status = TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_WRITTEN
                    overall = (
                        TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITTEN_SUBMIT_READINESS_REQUIRED
                    )
        else:
            status = TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_READY
            overall = TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_READY_FOR_CONFIRMATION

        blocked_by = _blocked_by(
            credential_context=credential_context,
            write_requested=write_signed_request_runtime_source,
            confirmation_valid=confirmation_valid,
            r251_result=r251_result,
            secret_validation=secret_validation,
            signed_request_written=written,
        )
        matrix = build_r251e_gate_matrix(
            runtime_credential_source_ready=credential_context["credential_source_ready"],
            r251_write_gate_available=True,
            write_confirmed=write_signed_request_runtime_source and confirmation_valid,
            signed_request_written=written,
            secret_validation_passed=secret_validation["valid"],
            blocked_by=blocked_by,
        )
        operator_packet = build_operator_r251e_packet(matrix)
        payload = _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "write_signed_request_runtime_source_requested": bool(
                    write_signed_request_runtime_source
                ),
                "confirmation_valid": bool(confirmation_valid),
                "signed_request_written": bool(written),
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "signed_request_runtime_source_write_gate_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "runtime_credential_source_context": credential_context,
                "signed_request_write_plan": plan,
                "signed_request_artifact_summary": artifact_summary,
                "secret_validation": secret_validation,
                "post_write_verification": post_write,
                "r251e_gate_matrix": matrix,
                "operator_r251e_packet": operator_packet,
                "recommended_next_operator_move": _recommended_next_operator_move(matrix),
                "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
                "r251e_overall_status": overall,
                "do_not_run_yet": _do_not_run_yet(),
                "safety": _safety(written),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
                "latest_r251d_runtime_source_drill_found": bool(latest_r251d),
                "latest_r251_signed_request_found": bool(latest_r251),
            }
        )

        output_validation = validate_no_secret_values_in_artifact(
            {},
            raw_api_key=raw_api_key,
            raw_api_secret=raw_api_secret,
            extra_payload=payload,
        )
        if output_validation["valid"] is not True:
            payload["status"] = TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_BLOCKED
            payload["r251e_overall_status"] = (
                TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_BLOCKED_BY_SECRET_VALIDATION
            )
            payload["secret_validation"] = output_validation
            payload["safety"]["secret_values_in_output"] = True

        if (
            write_signed_request_runtime_source
            and confirmation_valid
            and written
            and payload["secret_validation"]["valid"] is True
            and payload["safety"]["secret_values_in_output"] is False
        ):
            payload = append_tiny_live_signed_request_runtime_source_write_gate_record(
                payload,
                log_dir=resolved_log_dir,
                confirm_tiny_live_signed_request_runtime_source_write=(
                    confirm_tiny_live_signed_request_runtime_source_write
                ),
            )
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        matrix = build_r251e_gate_matrix(
            runtime_credential_source_ready=False,
            r251_write_gate_available=True,
            write_confirmed=False,
            signed_request_written=False,
            secret_validation_passed=False,
            blocked_by=["r251e_error"],
        )
        return _sanitize(
            {
                "status": TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_GATE_ERROR,
                "generated_at": generated_at.isoformat(),
                "write_signed_request_runtime_source_requested": bool(
                    write_signed_request_runtime_source
                ),
                "confirmation_valid": bool(confirmation_valid),
                "signed_request_written": False,
                "target_scope": {
                    "official_lane_key": official_lane_key,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": entry_mode,
                    "signed_request_runtime_source_write_gate_only": True,
                    "submit_allowed": False,
                    "order_placed": False,
                    "binance_call_allowed": False,
                    "network_allowed": False,
                },
                "runtime_credential_source_context": _empty_runtime_credential_context(),
                "signed_request_write_plan": build_r251e_signed_request_write_plan(
                    credential_source_ready=False,
                    write_requested=write_signed_request_runtime_source,
                    confirmation_valid=confirmation_valid,
                ),
                "signed_request_artifact_summary": _artifact_summary({}),
                "secret_validation": {
                    "valid": False,
                    "raw_api_key_found_in_artifacts": False,
                    "raw_api_secret_found_in_artifacts": False,
                    "secret_values_in_output": False,
                    "errors": ["r251e_error"],
                    "warnings": [],
                },
                "post_write_verification": build_r251e_post_write_verification(
                    signed_request_written=False,
                    r251_result={},
                    log_dir=resolved_log_dir,
                ),
                "r251e_gate_matrix": matrix,
                "operator_r251e_packet": build_operator_r251e_packet(matrix),
                "recommended_next_operator_move": "WAIT",
                "recommended_next_engineering_move": "Fix R251E runtime-source write gate error before submit readiness preview.",
                "r251e_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": _safety(False),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_tiny_live_runtime_credential_source_drill(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_runtime_credential_source_drill_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        if target.get("official_lane_key") == official_lane_key:
            return _sanitize(record)
    return {}


def load_latest_tiny_live_signed_request_write_gate(
    *, log_dir: str | Path | None = None, official_lane_key: str = OFFICIAL_LANE_KEY
) -> dict[str, Any]:
    records = load_tiny_live_signed_request_write_gate_records(log_dir=log_dir, limit=50)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        artifact = _r251_artifact(record)
        if (
            (target.get("official_lane_key") or artifact.get("official_lane_key"))
            == official_lane_key
            and record.get("signed_request_written") is True
        ):
            return _sanitize(record)
    return {}


def validate_runtime_credential_source_ready(
    *, env: Mapping[str, str] | None = None, repo_root: str | Path | None = None
) -> dict[str, Any]:
    process_presence = detect_process_env_credential_presence(env=env)
    external_source = detect_external_env_file_credential_presence(
        env=env,
        repo_root=repo_root,
    )
    summary = build_runtime_credential_source_summary(
        process_env_presence=process_presence,
        external_env_file_source=external_source,
    )
    source_type = summary.get("preferred_future_source") or "none"
    source_ready = summary.get("credentials_available_for_future_signing") is True
    external_path = (
        external_source.get("resolved_path")
        if source_type == "external_env_file"
        else None
    )
    api_key_present = (
        process_presence.get("api_key_present")
        if source_type == "process_env"
        else external_source.get("api_key_present")
    )
    api_secret_present = (
        process_presence.get("api_secret_present")
        if source_type == "process_env"
        else external_source.get("api_secret_present")
    )
    warnings = list(external_source.get("warnings") or [])
    errors = list(summary.get("remaining_blockers") or [])
    return {
        "credential_source_ready": bool(source_ready),
        "source_type": source_type if source_ready else "none",
        "external_file_path": external_path,
        "external_file_permission_ok": (
            external_source.get("permission_ok") if source_type == "external_env_file" else None
        ),
        "credentials_present": bool(source_ready),
        "api_key_hint": PRESENT_REDACTED if api_key_present is True and source_ready else None,
        "api_secret_hint": PRESENT_REDACTED if api_secret_present is True and source_ready else None,
        "secrets_shown": False,
        "secrets_persisted": False,
        "errors": _dedupe([str(error) for error in errors]),
        "warnings": _dedupe([str(warning) for warning in warnings]),
    }


def resolve_runtime_signing_credentials_for_confirmed_write(
    *,
    confirm_tiny_live_signed_request_runtime_source_write: str | None,
    env: Mapping[str, str] | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, str]:
    if (
        confirm_tiny_live_signed_request_runtime_source_write
        != CONFIRM_TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_PHRASE
    ):
        return {"api_key": "", "api_secret": "", "source_type": "none"}
    source_env = env if env is not None else os.environ
    context = validate_runtime_credential_source_ready(env=source_env, repo_root=repo_root)
    if context.get("source_type") == "process_env":
        return {
            "api_key": source_env.get(BINANCE_API_KEY_ENV, ""),
            "api_secret": source_env.get(BINANCE_API_SECRET_ENV, ""),
            "source_type": "process_env",
        }
    if context.get("source_type") == "external_env_file":
        values = _read_external_env_file_values(resolve_runtime_credential_source_path(source_env))
        return {
            "api_key": values.get(BINANCE_API_KEY_ENV, ""),
            "api_secret": values.get(BINANCE_API_SECRET_ENV, ""),
            "source_type": "external_env_file",
        }
    return {"api_key": "", "api_secret": "", "source_type": "none"}


def build_r251e_signed_request_write_plan(
    *, credential_source_ready: bool, write_requested: bool, confirmation_valid: bool
) -> dict[str, Any]:
    return {
        "would_write": bool(credential_source_ready and write_requested and confirmation_valid),
        "write_requires_confirmation": True,
        "uses_r251_write_gate": True,
        "uses_runtime_credential_source": True,
        "requires_credentials": True,
        "submit_allowed": False,
        "binance_call_allowed": False,
        "network_allowed": False,
    }


def invoke_r251_signed_request_artifact_write_with_runtime_source(
    *,
    api_key: str,
    api_secret: str,
    log_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    prior_key = os.environ.get(BINANCE_API_KEY_ENV)
    prior_secret = os.environ.get(BINANCE_API_SECRET_ENV)
    try:
        os.environ[BINANCE_API_KEY_ENV] = api_key
        os.environ[BINANCE_API_SECRET_ENV] = api_secret
        return build_tiny_live_signed_request_write_gate(
            log_dir=log_dir,
            write_signed_request=True,
            confirm_tiny_live_signed_request_write=CONFIRM_TINY_LIVE_SIGNED_REQUEST_WRITE_PHRASE,
            now=now,
        )
    finally:
        if prior_key is None:
            os.environ.pop(BINANCE_API_KEY_ENV, None)
        else:
            os.environ[BINANCE_API_KEY_ENV] = prior_key
        if prior_secret is None:
            os.environ.pop(BINANCE_API_SECRET_ENV, None)
        else:
            os.environ[BINANCE_API_SECRET_ENV] = prior_secret


def validate_r251e_signed_request_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    validation = validate_signed_request_artifact(artifact)
    errors = list(validation.get("errors") or [])
    signed_requests = artifact.get("signed_requests") if isinstance(artifact.get("signed_requests"), Mapping) else {}
    for key in ("main_order", "stop_order", "take_profit_order"):
        request = signed_requests.get(key) if isinstance(signed_requests.get(key), Mapping) else {}
        if not re.fullmatch(r"[0-9a-f]{64}", str(request.get("signature") or "")):
            errors.append(f"{key}_signature_not_64_hex")
    return {
        "valid": not errors,
        "errors": _dedupe([str(error) for error in errors]),
        "warnings": _dedupe([str(warning) for warning in validation.get("warnings") or []]),
    }


def validate_no_secret_values_in_artifact(
    artifact: Mapping[str, Any],
    *,
    raw_api_key: str | None = None,
    raw_api_secret: str | None = None,
    extra_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    text = json.dumps(
        {"artifact": artifact, "extra_payload": extra_payload or {}},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    raw_api_key_found = bool(raw_api_key and raw_api_key in text)
    raw_api_secret_found = bool(raw_api_secret and raw_api_secret in text)
    if raw_api_key_found:
        errors.append("raw_api_key_found_in_artifacts")
    if raw_api_secret_found:
        errors.append("raw_api_secret_found_in_artifacts")
    return {
        "valid": not errors,
        "raw_api_key_found_in_artifacts": raw_api_key_found,
        "raw_api_secret_found_in_artifacts": raw_api_secret_found,
        "secret_values_in_output": bool(errors),
        "errors": _dedupe(errors),
        "warnings": [],
    }


def build_r251e_post_write_verification(
    *,
    signed_request_written: bool,
    r251_result: Mapping[str, Any],
    signed_request_artifact: Mapping[str, Any] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    artifact = _r251_artifact(r251_result) or dict(signed_request_artifact or {})
    latest = load_latest_tiny_live_signed_request_write_gate(log_dir=log_dir) if signed_request_written else {}
    latest_artifact = _r251_artifact(latest)
    validation = validate_r251e_signed_request_artifact(latest_artifact)
    controls = latest_artifact.get("controls") if isinstance(latest_artifact.get("controls"), Mapping) else {}
    safety = latest_artifact.get("safety") if isinstance(latest_artifact.get("safety"), Mapping) else {}
    return {
        "signed_request_written": bool(signed_request_written),
        "matching_signed_request_found": bool(
            latest_artifact
            and artifact
            and latest_artifact.get("signed_request_artifact_id")
            == artifact.get("signed_request_artifact_id")
        ),
        "matching_signed_request_valid": validation["valid"] is True,
        "submit_allowed": controls.get("submit_allowed", False) is True,
        "order_placed": safety.get("order_placed", False) is True,
        "binance_call_allowed": controls.get("binance_call_allowed", False) is True,
        "network_allowed": controls.get("network_allowed", False) is True,
        "secrets_shown": safety.get("secrets_shown", False) is True,
        "secrets_persisted": safety.get("secrets_persisted", False) is True,
    }


def build_r251e_gate_matrix(
    *,
    runtime_credential_source_ready: bool,
    r251_write_gate_available: bool,
    write_confirmed: bool,
    signed_request_written: bool,
    secret_validation_passed: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers = list(blocked_by or [])
    if signed_request_written:
        blockers = ["submit_gate_required", "r252_submit_readiness_preview_required"]
    return {
        "runtime_credential_source_ready": bool(runtime_credential_source_ready),
        "r251_write_gate_available": bool(r251_write_gate_available),
        "write_confirmed": bool(write_confirmed),
        "signed_request_written": bool(signed_request_written),
        "secret_validation_passed": bool(secret_validation_passed),
        "submit_gate_required": True,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def build_operator_r251e_packet(r251e_gate_matrix: Mapping[str, Any]) -> dict[str, Any]:
    written = r251e_gate_matrix.get("signed_request_written") is True
    ready = r251e_gate_matrix.get("runtime_credential_source_ready") is True
    if written:
        action = "REVIEW_R251E_RESULT"
    elif ready:
        action = "CONFIRM_R251E_SIGNED_REQUEST_RUNTIME_SOURCE"
    elif r251e_gate_matrix.get("blocked_by"):
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


def classify_tiny_live_signed_request_runtime_source_write_gate_status(
    *,
    write_requested: bool,
    confirmation_valid: bool,
    credential_source_ready: bool,
    signed_request_written: bool,
    secret_validation_passed: bool,
) -> str:
    if write_requested and not confirmation_valid:
        return TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_REJECTED_BAD_CONFIRMATION
    if not credential_source_ready:
        return TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_BLOCKED_BY_CREDENTIAL_SOURCE
    if signed_request_written and not secret_validation_passed:
        return TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_BLOCKED_BY_SECRET_VALIDATION
    if signed_request_written:
        return TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITTEN_SUBMIT_READINESS_REQUIRED
    return TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_READY_FOR_CONFIRMATION


def append_tiny_live_signed_request_runtime_source_write_gate_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_tiny_live_signed_request_runtime_source_write: str | None = None,
) -> dict[str, Any]:
    if (
        confirm_tiny_live_signed_request_runtime_source_write
        != CONFIRM_TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_PHRASE
    ):
        raise ValueError("bad_tiny_live_signed_request_runtime_source_write_confirmation")
    if record.get("signed_request_written") is not True:
        raise ValueError("r251e_signed_request_not_written")
    secret_validation = record.get("secret_validation") if isinstance(record.get("secret_validation"), Mapping) else {}
    if secret_validation.get("valid") is not True:
        raise ValueError("r251e_secret_validation_failed")
    path = tiny_live_signed_request_runtime_source_write_gate_records_path(
        get_log_dir(log_dir, use_env=True)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "r251e_write_gate_record_id": record.get("r251e_write_gate_record_id")
            or f"r251e_signed_request_runtime_source_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_signed_request_runtime_source_write_gate_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_signed_request_runtime_source_write_gate_records_path(
        get_log_dir(log_dir, use_env=True)
    )
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_signed_request_runtime_source_write_gate_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    summary = (
        latest.get("signed_request_artifact_summary")
        if isinstance(latest.get("signed_request_artifact_summary"), Mapping)
        else {}
    )
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_signed_request_written": latest.get("signed_request_written") is True,
        "latest_signed_requests_count": summary.get("signed_requests_count"),
        "latest_overall_status": latest.get("r251e_overall_status"),
    }


def tiny_live_signed_request_runtime_source_write_gate_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_signed_request_runtime_source_write_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _read_external_env_file_values(path: str | Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {BINANCE_API_KEY_ENV, BINANCE_API_SECRET_ENV}:
            values[key] = _strip_env_value(value.strip())
    return values


def _strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _artifact_summary(artifact: Mapping[str, Any]) -> dict[str, Any]:
    signed_requests = artifact.get("signed_requests") if isinstance(artifact.get("signed_requests"), Mapping) else {}
    controls = artifact.get("controls") if isinstance(artifact.get("controls"), Mapping) else {}
    safety = artifact.get("safety") if isinstance(artifact.get("safety"), Mapping) else {}
    return {
        "signed_request_written": bool(artifact),
        "signed_requests_count": len(signed_requests),
        "main_order_signature_present": _has_signature(signed_requests, "main_order"),
        "stop_order_signature_present": _has_signature(signed_requests, "stop_order"),
        "take_profit_order_signature_present": _has_signature(signed_requests, "take_profit_order"),
        "submit_allowed": controls.get("submit_allowed", False) is True,
        "order_placed": safety.get("order_placed", False) is True,
        "binance_call_allowed": controls.get("binance_call_allowed", False) is True,
        "network_allowed": controls.get("network_allowed", False) is True,
    }


def _empty_secret_validation() -> dict[str, Any]:
    return {
        "valid": False,
        "raw_api_key_found_in_artifacts": False,
        "raw_api_secret_found_in_artifacts": False,
        "secret_values_in_output": False,
        "errors": [],
        "warnings": [],
    }


def _empty_runtime_credential_context() -> dict[str, Any]:
    return {
        "credential_source_ready": False,
        "source_type": "none",
        "external_file_path": None,
        "external_file_permission_ok": None,
        "credentials_present": False,
        "api_key_hint": None,
        "api_secret_hint": None,
        "secrets_shown": False,
        "secrets_persisted": False,
        "errors": ["runtime_credential_source_unavailable"],
        "warnings": [],
    }


def _merge_secret_validation_errors(
    secret_validation: Mapping[str, Any],
    errors: Sequence[str],
) -> dict[str, Any]:
    combined = dict(secret_validation)
    combined["valid"] = False
    combined["errors"] = _dedupe([*(secret_validation.get("errors") or []), *errors])
    combined["secret_values_in_output"] = bool(combined.get("errors"))
    return combined


def _has_signature(signed_requests: Mapping[str, Any], key: str) -> bool:
    request = signed_requests.get(key) if isinstance(signed_requests.get(key), Mapping) else {}
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(request.get("signature") or "")))


def _r251_artifact(record: Mapping[str, Any]) -> dict[str, Any]:
    artifact = record.get("signed_request_artifact")
    return _sanitize(dict(artifact)) if isinstance(artifact, Mapping) else {}


def _blocked_by(
    *,
    credential_context: Mapping[str, Any],
    write_requested: bool,
    confirmation_valid: bool,
    r251_result: Mapping[str, Any],
    secret_validation: Mapping[str, Any],
    signed_request_written: bool,
) -> list[str]:
    blockers: list[str] = []
    blockers.extend(str(error) for error in credential_context.get("errors") or [])
    if write_requested and not confirmation_valid:
        blockers.append("bad_confirmation")
    if credential_context.get("credential_source_ready") is not True:
        blockers.append("runtime_credential_source_not_ready")
    if write_requested and confirmation_valid and not signed_request_written:
        blockers.append("r251_signed_request_write_not_written")
        matrix = r251_result.get("signed_request_write_gate_matrix")
        if isinstance(matrix, Mapping):
            blockers.extend(str(item) for item in matrix.get("blocked_by") or [])
    blockers.extend(str(error) for error in secret_validation.get("errors") or [])
    return _dedupe(blockers)


def _recommended_next_operator_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("signed_request_written") is True:
        return "REVIEW_R251E_SIGNED_REQUEST_ARTIFACT"
    if matrix.get("runtime_credential_source_ready") is True:
        return "CONFIRM_R251E_SIGNED_REQUEST_RUNTIME_SOURCE"
    if matrix.get("blocked_by"):
        return "FIX_BLOCKER"
    return "WAIT"


def _recommended_next_engineering_move(matrix: Mapping[str, Any]) -> str:
    if matrix.get("signed_request_written") is True:
        return "Create R252 tiny-live submit readiness preview; consume the runtime-source signed request artifact, require future read-only mark-price refresh, and keep no Binance call/no submit/no order."
    if matrix.get("runtime_credential_source_ready") is True:
        return "Await exact R251E confirmation, then delegate to R251 for local signed request artifact writing only."
    return "Fix runtime credential source readiness before any signed request artifact write."


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
            "hmac_signature_created": bool(written),
            "signed_request_written": bool(written),
            "signed_order_request_created": bool(written),
            "signed_trading_request_created": bool(written),
        }
    )
    return safety


def _lane_parts(official_lane_key: str) -> tuple[str, str, str, str]:
    parts = official_lane_key.split("|")
    if len(parts) != 4:
        return "BTCUSDT", "8m", "short", "ladder_close_50_618"
    return parts[0], parts[1], parts[2], parts[3]


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
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
