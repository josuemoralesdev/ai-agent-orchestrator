"""R251B tiny-live signing credential presence drill.

This diagnostic checks only whether the Binance signing credential environment
variables exist in the current process. It does not read credential values for
signing, create HMAC signatures, write signed request artifacts, call Binance,
mutate env/configs, or place orders.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
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

TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_READY = (
    "TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_READY"
)
TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_RECORDED = (
    "TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_RECORDED"
)
TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_REJECTED = (
    "TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_REJECTED"
)
TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_BLOCKED = (
    "TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_BLOCKED"
)
TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_ERROR = (
    "TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_ERROR"
)

TINY_LIVE_SIGNING_CREDENTIALS_PRESENT_R251_CAN_BE_RERUN = (
    "TINY_LIVE_SIGNING_CREDENTIALS_PRESENT_R251_CAN_BE_RERUN"
)
TINY_LIVE_SIGNING_CREDENTIALS_MISSING_SET_ENV_THEN_RERUN = (
    "TINY_LIVE_SIGNING_CREDENTIALS_MISSING_SET_ENV_THEN_RERUN"
)
TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_RECORDED_STATUS = (
    "TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_RECORDED"
)
TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_REJECTED_BAD_CONFIRMATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL"
LEDGER_FILENAME = "tiny_live_signing_credential_presence_drill.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R251B_TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL"
R251_GATE_MODULE_PATH = Path("src/app/hammer_radar/operator/tiny_live_signed_request_write_gate.py")
CONFIRM_TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_PHRASE = (
    "I CONFIRM TINY LIVE SIGNING CREDENTIAL PRESENCE DRILL RECORDING ONLY; "
    "NO SIGNING; NO ORDER; NO BINANCE CALL."
)
BINANCE_API_KEY_ENV = "BINANCE_API_KEY"
BINANCE_API_SECRET_ENV = "BINANCE_API_SECRET"
PRESENT_REDACTED = "<PRESENT_REDACTED>"

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/tiny_live_signed_request_write_gate.py",
    "logs/hammer_radar_forward/tiny_live_signed_request_write_gate.ndjson",
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
    "credential_presence_drill_only": True,
    "signing_attempted": False,
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


def build_tiny_live_signing_credential_presence_drill(
    *,
    log_dir: str | Path | None = None,
    record_signing_credential_presence_drill: bool = False,
    confirm_tiny_live_signing_credential_presence_drill: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_signing_credential_presence_drill
        == CONFIRM_TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_PHRASE
    )
    try:
        credential_presence = detect_signing_credential_presence_only()
        readiness_summary = build_credential_presence_readiness_summary(
            credential_presence=credential_presence
        )

        recorded = False
        if record_signing_credential_presence_drill and not confirmation_valid:
            status = TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_REJECTED
            overall = TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_REJECTED_BAD_CONFIRMATION
        else:
            status = classify_tiny_live_signing_credential_presence_drill_status(
                record_requested=record_signing_credential_presence_drill,
                confirmation_valid=confirmation_valid,
                recorded=False,
                blocked_by=[],
            )
            overall = (
                TINY_LIVE_SIGNING_CREDENTIALS_PRESENT_R251_CAN_BE_RERUN
                if credential_presence["credentials_present"]
                else TINY_LIVE_SIGNING_CREDENTIALS_MISSING_SET_ENV_THEN_RERUN
            )

        matrix = build_credential_presence_gate_matrix(
            credential_presence=credential_presence,
            record_confirmed=record_signing_credential_presence_drill and confirmation_valid,
            recorded=recorded,
        )
        operator_packet = build_operator_credential_presence_packet(
            credential_presence=credential_presence,
            recorded=recorded,
        )
        payload = _base_payload(
            status=status,
            generated_at=generated_at,
            record_requested=record_signing_credential_presence_drill,
            confirmation_valid=confirmation_valid,
            recorded=recorded,
            official_lane_key=official_lane_key,
            credential_presence=credential_presence,
            readiness_summary=readiness_summary,
            operator_packet=operator_packet,
            matrix=matrix,
            overall=overall,
        )

        validation = validate_no_secret_values_in_object(payload)
        if validation["valid"] is not True:
            payload["status"] = TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_BLOCKED
            payload["credential_presence_overall_status"] = UNKNOWN_NEEDS_MANUAL_REVIEW
            payload["credential_presence_gate_matrix"]["blocked_by"] = _dedupe(
                [*payload["credential_presence_gate_matrix"].get("blocked_by", []), *validation["errors"]]
            )
            payload["safety"]["secret_values_in_output"] = True

        if record_signing_credential_presence_drill and confirmation_valid and validation["valid"] is True:
            recorded_matrix = build_credential_presence_gate_matrix(
                credential_presence=credential_presence,
                record_confirmed=True,
                recorded=True,
            )
            payload["status"] = TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_RECORDED
            payload["credential_presence_overall_status"] = (
                TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_RECORDED_STATUS
            )
            payload["credential_presence_drill_recorded"] = True
            payload["credential_presence_gate_matrix"] = recorded_matrix
            payload["operator_credential_presence_packet"] = (
                build_operator_credential_presence_packet(
                    credential_presence=credential_presence,
                    recorded=True,
                )
            )
            payload["recommended_next_operator_move"] = _recommended_next_operator_move(
                recorded_matrix,
                credential_presence=credential_presence,
            )
            payload["recommended_next_engineering_move"] = _recommended_next_engineering_move(
                recorded_matrix,
                credential_presence=credential_presence,
            )
            recorded_payload = append_tiny_live_signing_credential_presence_drill_record(
                payload,
                log_dir=resolved_log_dir,
                confirm_tiny_live_signing_credential_presence_drill=(
                    confirm_tiny_live_signing_credential_presence_drill
                ),
            )
            return _sanitize(recorded_payload)

        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        credential_presence = _empty_credential_presence()
        matrix = build_credential_presence_gate_matrix(
            credential_presence=credential_presence,
            record_confirmed=False,
            recorded=False,
            blocked_by=["credential_presence_drill_error"],
        )
        return _sanitize(
            _base_payload(
                status=TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_ERROR,
                generated_at=generated_at,
                record_requested=record_signing_credential_presence_drill,
                confirmation_valid=confirmation_valid,
                recorded=False,
                official_lane_key=official_lane_key,
                credential_presence=credential_presence,
                readiness_summary=build_credential_presence_readiness_summary(
                    credential_presence=credential_presence
                ),
                operator_packet=build_operator_credential_presence_packet(
                    credential_presence=credential_presence,
                    recorded=False,
                ),
                matrix=matrix,
                overall=UNKNOWN_NEEDS_MANUAL_REVIEW,
                error=exc.__class__.__name__,
            )
        )


def detect_signing_credential_presence_only() -> dict[str, Any]:
    api_key_present = BINANCE_API_KEY_ENV in os.environ
    api_secret_present = BINANCE_API_SECRET_ENV in os.environ
    return {
        "api_key_env_name": BINANCE_API_KEY_ENV,
        "api_secret_env_name": BINANCE_API_SECRET_ENV,
        "api_key_present": api_key_present,
        "api_secret_present": api_secret_present,
        "credentials_present": bool(api_key_present and api_secret_present),
        "api_key_hint": PRESENT_REDACTED if api_key_present else None,
        "api_secret_hint": PRESENT_REDACTED if api_secret_present else None,
        "api_key_value_shown": False,
        "api_secret_value_shown": False,
        "secrets_read_for_signing": False,
        "secrets_persisted": False,
    }


def build_credential_presence_readiness_summary(
    *, credential_presence: Mapping[str, Any]
) -> dict[str, Any]:
    remaining_blockers: list[str] = []
    if credential_presence.get("api_key_present") is not True:
        remaining_blockers.append("missing_BINANCE_API_KEY")
    if credential_presence.get("api_secret_present") is not True:
        remaining_blockers.append("missing_BINANCE_API_SECRET")
    return {
        "r251_signed_request_write_gate_available": R251_GATE_MODULE_PATH.exists(),
        "can_rerun_r251_write_after_credentials": credential_presence.get("credentials_present") is True,
        "remaining_blockers": remaining_blockers,
    }


def validate_no_secret_values_in_object(
    payload: Mapping[str, Any] | Sequence[Any],
    *,
    forbidden_values: Iterable[str] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    for value in forbidden_values or ():
        if value and value in raw:
            errors.append("secret_value_found_in_output")
    if '"api_key_hint":"<' not in raw and "api_key_hint" in raw:
        if '"api_key_hint":null' not in raw:
            errors.append("api_key_hint_not_redacted")
    if '"api_secret_hint":"<' not in raw and "api_secret_hint" in raw:
        if '"api_secret_hint":null' not in raw:
            errors.append("api_secret_hint_not_redacted")
    return {"valid": not errors, "errors": _dedupe(errors), "warnings": []}


def build_operator_credential_presence_packet(
    *,
    credential_presence: Mapping[str, Any],
    recorded: bool = False,
) -> dict[str, Any]:
    credentials_present = credential_presence.get("credentials_present") is True
    if credentials_present:
        action = "RERUN_R251"
    elif recorded:
        action = "SET_SIGNING_CREDENTIALS_OUTSIDE_GIT"
    else:
        action = "SET_SIGNING_CREDENTIALS_OUTSIDE_GIT"
    return {
        "operator_should_set_credentials_outside_git": not credentials_present,
        "operator_should_rerun_r251_after_credentials_present": credentials_present,
        "operator_should_place_order": False,
        "operator_should_submit_now": False,
        "safe_manual_credential_guidance": [
            "Set credentials in the shell/session or service environment outside Git.",
            "Do not paste secrets into chat, commits, logs, or task files.",
            "After setting credentials, rerun the R251 signed request write gate exact confirmation.",
        ],
        "next_required_human_action": action,
    }


def build_credential_presence_gate_matrix(
    *,
    credential_presence: Mapping[str, Any],
    record_confirmed: bool,
    recorded: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    blockers = list(blocked_by or [])
    if credential_presence.get("api_key_present") is not True:
        blockers.append("missing_BINANCE_API_KEY")
    if credential_presence.get("api_secret_present") is not True:
        blockers.append("missing_BINANCE_API_SECRET")
    if recorded:
        blockers.append("rerun_r251_signed_request_write_gate_required")
    return {
        "api_key_present": credential_presence.get("api_key_present") is True,
        "api_secret_present": credential_presence.get("api_secret_present") is True,
        "credentials_present": credential_presence.get("credentials_present") is True,
        "record_confirmed": bool(record_confirmed),
        "recorded": bool(recorded),
        "signing_attempted": False,
        "signed_request_written": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def classify_tiny_live_signing_credential_presence_drill_status(
    *,
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
    blocked_by: Sequence[str] | None = None,
) -> str:
    if record_requested and not confirmation_valid:
        return TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_REJECTED
    if recorded:
        return TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_RECORDED
    if blocked_by:
        return TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_BLOCKED
    return TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_READY


def append_tiny_live_signing_credential_presence_drill_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_tiny_live_signing_credential_presence_drill: str | None = None,
) -> dict[str, Any]:
    if (
        confirm_tiny_live_signing_credential_presence_drill
        != CONFIRM_TINY_LIVE_SIGNING_CREDENTIAL_PRESENCE_DRILL_PHRASE
    ):
        raise ValueError("bad_tiny_live_signing_credential_presence_drill_confirmation")
    validation = validate_no_secret_values_in_object(record)
    if validation["valid"] is not True:
        raise ValueError("credential_presence_drill_secret_value_validation_failed")
    path = tiny_live_signing_credential_presence_drill_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "credential_presence_drill_record_id": record.get("credential_presence_drill_record_id")
            or f"r251b_credential_presence_drill_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "credential_presence_drill_recorded": True,
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_signing_credential_presence_drill_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_signing_credential_presence_drill_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_signing_credential_presence_drill_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    presence = (
        latest.get("credential_presence")
        if isinstance(latest.get("credential_presence"), Mapping)
        else {}
    )
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_credential_presence_drill_recorded": (
            latest.get("credential_presence_drill_recorded") is True
        ),
        "latest_api_key_present": presence.get("api_key_present"),
        "latest_api_secret_present": presence.get("api_secret_present"),
        "latest_credentials_present": presence.get("credentials_present"),
        "latest_overall_status": latest.get("credential_presence_overall_status"),
    }


def tiny_live_signing_credential_presence_drill_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_signing_credential_presence_drill_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _base_payload(
    *,
    status: str,
    generated_at: datetime,
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
    official_lane_key: str,
    credential_presence: Mapping[str, Any],
    readiness_summary: Mapping[str, Any],
    operator_packet: Mapping[str, Any],
    matrix: Mapping[str, Any],
    overall: str,
    error: str | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "generated_at": generated_at.isoformat(),
        "credential_presence_drill_recorded": bool(recorded),
        "record_credential_presence_drill_requested": bool(record_requested),
        "confirmation_valid": bool(confirmation_valid),
        "target_scope": {
            "official_lane_key": official_lane_key,
            "credential_presence_drill_only": True,
            "signing_attempted": False,
            "hmac_signature_created": False,
            "signed_request_written": False,
            "order_placed": False,
            "binance_call_allowed": False,
            "network_allowed": False,
        },
        "credential_presence": dict(credential_presence),
        "r251_readiness_summary": dict(readiness_summary),
        "operator_credential_presence_packet": dict(operator_packet),
        "credential_presence_gate_matrix": dict(matrix),
        "credential_presence_overall_status": overall,
        "recommended_next_operator_move": _recommended_next_operator_move(
            matrix,
            credential_presence=credential_presence,
        ),
        "recommended_next_engineering_move": _recommended_next_engineering_move(
            matrix,
            credential_presence=credential_presence,
        ),
        "do_not_run_yet": _do_not_run_yet(),
        "safety": dict(SAFETY),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }
    if error:
        payload["error"] = error
    return payload


def _recommended_next_operator_move(
    matrix: Mapping[str, Any],
    *,
    credential_presence: Mapping[str, Any],
) -> str:
    if credential_presence.get("credentials_present") is True:
        return "RERUN_R251_SIGNED_REQUEST_WRITE_GATE_WITH_EXACT_CONFIRMATION"
    if matrix.get("recorded") is True:
        return "SET_SIGNING_CREDENTIALS_OUTSIDE_GIT_THEN_RERUN_R251B"
    return "SET_SIGNING_CREDENTIALS_OUTSIDE_GIT_THEN_RERUN_R251B"


def _recommended_next_engineering_move(
    matrix: Mapping[str, Any],
    *,
    credential_presence: Mapping[str, Any],
) -> str:
    if credential_presence.get("credentials_present") is True:
        return "Rerun R251 signed request write gate after operator confirms credentials are present; keep Binance/network/order calls forbidden."
    if matrix.get("recorded") is True:
        return "Wait for operator to set BINANCE_API_KEY and BINANCE_API_SECRET outside Git, then rerun this presence drill."
    return "Record R251B presence-only audit after exact confirmation, then set credentials outside Git before rerunning R251."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "signed request write without credentials",
        "kill switch disable",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _empty_credential_presence() -> dict[str, Any]:
    return {
        "api_key_env_name": BINANCE_API_KEY_ENV,
        "api_secret_env_name": BINANCE_API_SECRET_ENV,
        "api_key_present": False,
        "api_secret_present": False,
        "credentials_present": False,
        "api_key_hint": None,
        "api_secret_hint": None,
        "api_key_value_shown": False,
        "api_secret_value_shown": False,
        "secrets_read_for_signing": False,
        "secrets_persisted": False,
    }


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
