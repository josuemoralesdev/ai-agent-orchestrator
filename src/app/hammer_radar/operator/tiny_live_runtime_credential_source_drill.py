"""R251D tiny-live runtime credential source drill.

This diagnostic resolves whether Binance signing credentials are available
from the current process environment or from an operator-managed env file
outside the repository. It never signs, calls Binance/network endpoints,
submits, places orders, mutates env/configs, or writes credential values.
"""

from __future__ import annotations

import json
import os
import stat
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
from src.app.hammer_radar.operator.tiny_live_signing_credential_presence_drill import (
    BINANCE_API_KEY_ENV,
    BINANCE_API_SECRET_ENV,
    PRESENT_REDACTED,
)

TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_READY = (
    "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_READY"
)
TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_RECORDED = (
    "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_RECORDED"
)
TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_REJECTED = (
    "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_REJECTED"
)
TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_BLOCKED = (
    "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_BLOCKED"
)
TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_ERROR = (
    "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_ERROR"
)

TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_READY_FOR_R251C = (
    "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_READY_FOR_R251C"
)
TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_MISSING_CREATE_EXTERNAL_FILE = (
    "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_MISSING_CREATE_EXTERNAL_FILE"
)
TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_PRESENT_BUT_PERMISSION_WARNING = (
    "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_PRESENT_BUT_PERMISSION_WARNING"
)
TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_RECORDED = (
    "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_RECORDED"
)
TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_REJECTED_BAD_CONFIRMATION = (
    "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_REJECTED_BAD_CONFIRMATION"
)
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL"
LEDGER_FILENAME = "tiny_live_runtime_credential_source_drill.ndjson"
OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
CREATED_BY_PHASE = "R251D_TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL"
DEFAULT_EXTERNAL_ENV_FILE = Path("/home/josue/.config/hammer-radar/binance-signing.env")
OVERRIDE_ENV_NAME = "HAMMER_BINANCE_SIGNING_ENV_FILE"
CONFIRM_TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_PHRASE = (
    "I CONFIRM TINY LIVE RUNTIME CREDENTIAL SOURCE DRILL RECORDING ONLY; "
    "NO SIGNING; NO ORDER; NO BINANCE CALL."
)

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/tiny_live_signing_credential_presence_drill.py",
    "src/app/hammer_radar/operator/tiny_live_signed_request_with_credentials_drill.py",
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
    "runtime_credential_source_drill_only": True,
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


def build_tiny_live_runtime_credential_source_drill(
    *,
    log_dir: str | Path | None = None,
    record_runtime_credential_source_drill: bool = False,
    confirm_tiny_live_runtime_credential_source_drill: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_tiny_live_runtime_credential_source_drill
        == CONFIRM_TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_PHRASE
    )
    try:
        process_presence = detect_process_env_credential_presence()
        external_source = detect_external_env_file_credential_presence()
        summary = build_runtime_credential_source_summary(
            process_env_presence=process_presence,
            external_env_file_source=external_source,
        )

        if record_runtime_credential_source_drill and not confirmation_valid:
            status = TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_REJECTED
            overall = TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_REJECTED_BAD_CONFIRMATION
        else:
            status = classify_tiny_live_runtime_credential_source_drill_status(
                record_requested=record_runtime_credential_source_drill,
                confirmation_valid=confirmation_valid,
                recorded=False,
                blocked_by=summary.get("remaining_blockers") or [],
            )
            overall = _overall_status(summary, external_source)

        matrix = build_runtime_credential_source_gate_matrix(
            process_env_presence=process_presence,
            external_env_file_source=external_source,
            record_confirmed=record_runtime_credential_source_drill and confirmation_valid,
            recorded=False,
        )
        operator_packet = build_operator_runtime_credential_source_packet(
            runtime_credential_source_summary=summary,
            external_env_file_source=external_source,
        )
        payload = _base_payload(
            status=status,
            generated_at=generated_at,
            record_requested=record_runtime_credential_source_drill,
            confirmation_valid=confirmation_valid,
            recorded=False,
            official_lane_key=official_lane_key,
            process_env_presence=process_presence,
            external_env_file_source=external_source,
            summary=summary,
            operator_packet=operator_packet,
            matrix=matrix,
            overall=overall,
        )
        validation = validate_no_secret_values_in_object(
            payload,
            forbidden_values=_current_forbidden_values(external_source),
        )
        if validation["valid"] is not True:
            payload["status"] = TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_BLOCKED
            payload["runtime_credential_source_overall_status"] = UNKNOWN_NEEDS_MANUAL_REVIEW
            payload["runtime_credential_source_gate_matrix"]["blocked_by"] = _dedupe(
                [
                    *payload["runtime_credential_source_gate_matrix"].get("blocked_by", []),
                    *validation["errors"],
                ]
            )
            payload["safety"]["secret_values_in_output"] = True

        if (
            record_runtime_credential_source_drill
            and confirmation_valid
            and validation["valid"] is True
        ):
            recorded_matrix = build_runtime_credential_source_gate_matrix(
                process_env_presence=process_presence,
                external_env_file_source=external_source,
                record_confirmed=True,
                recorded=True,
            )
            payload["status"] = TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_RECORDED
            payload["runtime_credential_source_drill_recorded"] = True
            payload["runtime_credential_source_gate_matrix"] = recorded_matrix
            payload["runtime_credential_source_overall_status"] = (
                TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_RECORDED
            )
            payload["operator_runtime_credential_source_packet"] = (
                build_operator_runtime_credential_source_packet(
                    runtime_credential_source_summary=summary,
                    external_env_file_source=external_source,
                )
            )
            payload["recommended_next_operator_move"] = _recommended_next_operator_move(
                summary,
                external_source,
            )
            payload["recommended_next_engineering_move"] = _recommended_next_engineering_move(
                summary
            )
            return _sanitize(
                append_tiny_live_runtime_credential_source_drill_record(
                    payload,
                    log_dir=resolved_log_dir,
                    confirm_tiny_live_runtime_credential_source_drill=(
                        confirm_tiny_live_runtime_credential_source_drill
                    ),
                    forbidden_values=_current_forbidden_values(external_source),
                )
            )

        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        process_presence = _empty_process_env_presence()
        external_source = _empty_external_env_file_source()
        summary = build_runtime_credential_source_summary(
            process_env_presence=process_presence,
            external_env_file_source=external_source,
        )
        matrix = build_runtime_credential_source_gate_matrix(
            process_env_presence=process_presence,
            external_env_file_source=external_source,
            record_confirmed=False,
            recorded=False,
            blocked_by=["runtime_credential_source_drill_error"],
        )
        return _sanitize(
            _base_payload(
                status=TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_ERROR,
                generated_at=generated_at,
                record_requested=record_runtime_credential_source_drill,
                confirmation_valid=confirmation_valid,
                recorded=False,
                official_lane_key=official_lane_key,
                process_env_presence=process_presence,
                external_env_file_source=external_source,
                summary=summary,
                operator_packet=build_operator_runtime_credential_source_packet(
                    runtime_credential_source_summary=summary,
                    external_env_file_source=external_source,
                ),
                matrix=matrix,
                overall=UNKNOWN_NEEDS_MANUAL_REVIEW,
                error=exc.__class__.__name__,
            )
        )


def get_repo_root(start: str | Path | None = None) -> Path:
    current = Path(start or __file__).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return Path.cwd().resolve()


def resolve_runtime_credential_source_path(
    env: Mapping[str, str] | None = None,
) -> Path:
    source_env = env if env is not None else os.environ
    override = source_env.get(OVERRIDE_ENV_NAME)
    return Path(override) if override else DEFAULT_EXTERNAL_ENV_FILE


def parse_external_env_file_presence_only(path: str | Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    api_key_present = False
    api_secret_present = False
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return _external_parse_result(False, False, ["external_env_file_not_utf8"], [])
    except OSError as exc:
        return _external_parse_result(False, False, [f"external_env_file_read_error_{exc.__class__.__name__}"], [])

    for index, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            warnings.append(f"line_{index}_uses_export_prefix")
            line = line[len("export ") :].strip()
        if "=" not in line:
            errors.append(f"line_{index}_missing_equals")
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_env_value(value.strip())
        if not key:
            errors.append(f"line_{index}_empty_key")
            continue
        if key in {BINANCE_API_KEY_ENV, BINANCE_API_SECRET_ENV} and not value:
            errors.append(f"{key}_empty")
        if key == BINANCE_API_KEY_ENV and value:
            api_key_present = True
        elif key == BINANCE_API_SECRET_ENV and value:
            api_secret_present = True
    return _external_parse_result(api_key_present, api_secret_present, errors, warnings)


def detect_process_env_credential_presence(
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    source_env = env if env is not None else os.environ
    api_key_present = BINANCE_API_KEY_ENV in source_env and bool(source_env.get(BINANCE_API_KEY_ENV))
    api_secret_present = (
        BINANCE_API_SECRET_ENV in source_env and bool(source_env.get(BINANCE_API_SECRET_ENV))
    )
    return {
        "api_key_present": api_key_present,
        "api_secret_present": api_secret_present,
        "credentials_present": bool(api_key_present and api_secret_present),
        "api_key_hint": PRESENT_REDACTED if api_key_present else None,
        "api_secret_hint": PRESENT_REDACTED if api_secret_present else None,
        "secrets_shown": False,
        "secrets_persisted": False,
    }


def detect_external_env_file_credential_presence(
    *,
    env: Mapping[str, str] | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    resolved_path = resolve_runtime_credential_source_path(env)
    path_validation = validate_external_env_file_path(resolved_path, repo_root=repo_root)
    permission_validation = validate_external_env_file_permissions(resolved_path)
    errors = [
        *path_validation.get("errors", []),
        *permission_validation.get("errors", []),
    ]
    warnings = [
        *path_validation.get("warnings", []),
        *permission_validation.get("warnings", []),
    ]
    parsed = _external_parse_result(False, False, [], [])
    if path_validation.get("file_exists") is True and path_validation.get("is_regular_file") is True:
        parsed = parse_external_env_file_presence_only(resolved_path)
        errors.extend(parsed.get("errors") or [])
        warnings.extend(parsed.get("warnings") or [])

    return {
        "default_path": str(DEFAULT_EXTERNAL_ENV_FILE),
        "override_env_name": OVERRIDE_ENV_NAME,
        "resolved_path": str(resolved_path),
        "path_is_absolute": path_validation.get("path_is_absolute") is True,
        "path_inside_repo": path_validation.get("path_inside_repo") is True,
        "file_exists": path_validation.get("file_exists") is True,
        "is_regular_file": path_validation.get("is_regular_file") is True,
        "file_mode": permission_validation.get("file_mode"),
        "permission_ok": permission_validation.get("permission_ok") is True,
        "owner_is_current_user": permission_validation.get("owner_is_current_user"),
        "api_key_present": parsed.get("api_key_present") is True,
        "api_secret_present": parsed.get("api_secret_present") is True,
        "credentials_present": parsed.get("credentials_present") is True,
        "api_key_hint": PRESENT_REDACTED if parsed.get("api_key_present") is True else None,
        "api_secret_hint": PRESENT_REDACTED if parsed.get("api_secret_present") is True else None,
        "secrets_shown": False,
        "secrets_persisted": False,
        "errors": _dedupe([str(error) for error in errors]),
        "warnings": _dedupe([str(warning) for warning in warnings]),
    }


def validate_external_env_file_path(
    path: str | Path,
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    candidate = Path(path)
    path_is_absolute = candidate.is_absolute()
    errors: list[str] = []
    warnings: list[str] = []
    if not path_is_absolute:
        errors.append("external_env_file_path_not_absolute")
    resolved = candidate.resolve(strict=False)
    root = Path(repo_root).resolve() if repo_root is not None else get_repo_root()
    path_inside_repo = _is_relative_to(resolved, root)
    if path_inside_repo:
        errors.append("external_env_file_path_inside_repo")
    file_exists = candidate.exists()
    if not file_exists:
        errors.append("external_env_file_missing")
    is_regular_file = candidate.is_file() if file_exists else False
    if file_exists and not is_regular_file:
        errors.append("external_env_file_not_regular_file")
    return {
        "path_is_absolute": path_is_absolute,
        "path_inside_repo": path_inside_repo,
        "file_exists": file_exists,
        "is_regular_file": is_regular_file,
        "errors": errors,
        "warnings": warnings,
    }


def validate_external_env_file_permissions(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.exists():
        return {
            "file_mode": None,
            "permission_ok": False,
            "owner_is_current_user": None,
            "errors": [],
            "warnings": [],
        }
    try:
        info = candidate.stat()
    except OSError as exc:
        return {
            "file_mode": None,
            "permission_ok": False,
            "owner_is_current_user": None,
            "errors": [f"external_env_file_stat_error_{exc.__class__.__name__}"],
            "warnings": [],
        }
    mode = stat.S_IMODE(info.st_mode)
    mode_text = f"{mode:04o}"
    warnings: list[str] = []
    errors: list[str] = []
    permission_ok = (mode & 0o077) == 0
    if not permission_ok:
        warnings.append("external_env_file_group_or_world_accessible")
    owner_is_current_user: bool | None
    try:
        owner_is_current_user = info.st_uid == os.getuid()
    except AttributeError:
        owner_is_current_user = None
    if owner_is_current_user is False:
        warnings.append("external_env_file_owner_not_current_user")
    return {
        "file_mode": mode_text,
        "permission_ok": bool(permission_ok),
        "owner_is_current_user": owner_is_current_user,
        "errors": errors,
        "warnings": warnings,
    }


def build_runtime_credential_source_summary(
    *,
    process_env_presence: Mapping[str, Any],
    external_env_file_source: Mapping[str, Any],
) -> dict[str, Any]:
    external_ready = bool(
        external_env_file_source.get("credentials_present") is True
        and external_env_file_source.get("permission_ok") is True
        and external_env_file_source.get("path_is_absolute") is True
        and external_env_file_source.get("path_inside_repo") is False
        and external_env_file_source.get("file_exists") is True
        and external_env_file_source.get("is_regular_file") is True
        and not external_env_file_source.get("errors")
    )
    process_ready = process_env_presence.get("credentials_present") is True
    remaining_blockers: list[str] = []
    if not process_ready and not external_ready:
        remaining_blockers.append("no_runtime_credential_source_ready")
    if external_env_file_source.get("file_exists") is False:
        remaining_blockers.append("external_env_file_missing")
    if external_env_file_source.get("path_inside_repo") is True:
        remaining_blockers.append("external_env_file_path_inside_repo")
    if (
        external_env_file_source.get("file_exists") is True
        and external_env_file_source.get("credentials_present") is not True
    ):
        remaining_blockers.append("external_env_file_missing_required_keys")
    if (
        external_env_file_source.get("file_exists") is True
        and external_env_file_source.get("permission_ok") is not True
    ):
        remaining_blockers.append("external_env_file_permissions_too_open")
    for error in external_env_file_source.get("errors") or []:
        remaining_blockers.append(str(error))
    preferred = "none"
    if process_ready:
        preferred = "process_env"
    elif external_ready:
        preferred = "external_env_file"
    return {
        "credentials_available_from_process_env": process_ready,
        "credentials_available_from_external_file": external_ready,
        "credentials_available_for_future_signing": bool(process_ready or external_ready),
        "preferred_future_source": preferred,
        "remaining_blockers": _dedupe(remaining_blockers),
    }


def validate_no_secret_values_in_object(
    payload: Mapping[str, Any] | Sequence[Any],
    *,
    forbidden_values: Iterable[str] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    raw = json.dumps(_strip_internal_fields(payload), sort_keys=True, separators=(",", ":"), default=str)
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


def build_operator_runtime_credential_source_packet(
    *,
    runtime_credential_source_summary: Mapping[str, Any],
    external_env_file_source: Mapping[str, Any],
) -> dict[str, Any]:
    summary = runtime_credential_source_summary
    create_file = external_env_file_source.get("file_exists") is not True
    fix_permissions = bool(
        external_env_file_source.get("file_exists") is True
        and external_env_file_source.get("permission_ok") is not True
    )
    ready = summary.get("credentials_available_for_future_signing") is True
    if create_file:
        action = "CREATE_EXTERNAL_CREDENTIAL_FILE"
    elif fix_permissions:
        action = "FIX_PERMISSIONS"
    elif ready:
        action = "RERUN_R251C"
    else:
        action = "WAIT"
    return {
        "operator_should_create_external_env_file": create_file,
        "operator_should_fix_file_permissions": fix_permissions,
        "operator_should_rerun_r251c_after_source_ready": ready,
        "operator_should_place_order": False,
        "operator_should_submit_now": False,
        "safe_manual_setup_guidance": [
            "Create /home/josue/.config/hammer-radar/binance-signing.env outside the repo.",
            "Set mode 600 on the file.",
            "Never commit, paste, screenshot, or log the credential values.",
            "Rerun this drill and then R251C.",
        ],
        "next_required_human_action": action,
    }


def build_runtime_credential_source_gate_matrix(
    *,
    process_env_presence: Mapping[str, Any],
    external_env_file_source: Mapping[str, Any],
    record_confirmed: bool,
    recorded: bool,
    blocked_by: Sequence[str] | None = None,
) -> dict[str, Any]:
    summary = build_runtime_credential_source_summary(
        process_env_presence=process_env_presence,
        external_env_file_source=external_env_file_source,
    )
    blockers = list(blocked_by or [])
    blockers.extend(summary.get("remaining_blockers") or [])
    if recorded:
        blockers.append("rerun_r251c_after_runtime_source_ready")
    return {
        "process_env_credentials_present": process_env_presence.get("credentials_present") is True,
        "external_env_file_credentials_present": (
            external_env_file_source.get("credentials_present") is True
        ),
        "external_env_file_permission_ok": external_env_file_source.get("permission_ok") is True,
        "credentials_available_for_future_signing": (
            summary.get("credentials_available_for_future_signing") is True
        ),
        "record_confirmed": bool(record_confirmed),
        "recorded": bool(recorded),
        "signing_attempted": False,
        "signed_request_written": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": _dedupe(blockers),
    }


def classify_tiny_live_runtime_credential_source_drill_status(
    *,
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
    blocked_by: Sequence[str] | None = None,
) -> str:
    if record_requested and not confirmation_valid:
        return TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_REJECTED
    if recorded:
        return TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_RECORDED
    if blocked_by:
        return TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_BLOCKED
    return TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_READY


def append_tiny_live_runtime_credential_source_drill_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    confirm_tiny_live_runtime_credential_source_drill: str | None = None,
    forbidden_values: Iterable[str] | None = None,
) -> dict[str, Any]:
    if (
        confirm_tiny_live_runtime_credential_source_drill
        != CONFIRM_TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_DRILL_PHRASE
    ):
        raise ValueError("bad_tiny_live_runtime_credential_source_drill_confirmation")
    validation = validate_no_secret_values_in_object(record, forbidden_values=forbidden_values)
    if validation["valid"] is not True:
        raise ValueError("runtime_credential_source_drill_secret_value_validation_failed")
    path = tiny_live_runtime_credential_source_drill_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "runtime_credential_source_drill_record_id": record.get(
                "runtime_credential_source_drill_record_id"
            )
            or f"r251d_runtime_credential_source_drill_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            **dict(record),
            "runtime_credential_source_drill_recorded": True,
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_runtime_credential_source_drill_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_runtime_credential_source_drill_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_runtime_credential_source_drill_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    latest = records[0] if records else {}
    summary = (
        latest.get("runtime_credential_source_summary")
        if isinstance(latest.get("runtime_credential_source_summary"), Mapping)
        else {}
    )
    return {
        "record_count": len(records),
        "latest_status": latest.get("status"),
        "latest_runtime_credential_source_drill_recorded": (
            latest.get("runtime_credential_source_drill_recorded") is True
        ),
        "latest_credentials_available_for_future_signing": (
            summary.get("credentials_available_for_future_signing") is True
        ),
        "latest_preferred_future_source": summary.get("preferred_future_source"),
        "latest_overall_status": latest.get("runtime_credential_source_overall_status"),
    }


def tiny_live_runtime_credential_source_drill_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_runtime_credential_source_drill_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _base_payload(
    *,
    status: str,
    generated_at: datetime,
    record_requested: bool,
    confirmation_valid: bool,
    recorded: bool,
    official_lane_key: str,
    process_env_presence: Mapping[str, Any],
    external_env_file_source: Mapping[str, Any],
    summary: Mapping[str, Any],
    operator_packet: Mapping[str, Any],
    matrix: Mapping[str, Any],
    overall: str,
    error: str | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "generated_at": generated_at.isoformat(),
        "runtime_credential_source_drill_recorded": bool(recorded),
        "record_runtime_credential_source_drill_requested": bool(record_requested),
        "confirmation_valid": bool(confirmation_valid),
        "target_scope": {
            "official_lane_key": official_lane_key,
            "runtime_credential_source_drill_only": True,
            "signing_attempted": False,
            "hmac_signature_created": False,
            "signed_request_written": False,
            "order_placed": False,
            "binance_call_allowed": False,
            "network_allowed": False,
        },
        "process_env_presence": dict(process_env_presence),
        "external_env_file_source": dict(external_env_file_source),
        "runtime_credential_source_summary": dict(summary),
        "operator_runtime_credential_source_packet": dict(operator_packet),
        "runtime_credential_source_gate_matrix": dict(matrix),
        "runtime_credential_source_overall_status": overall,
        "recommended_next_operator_move": _recommended_next_operator_move(
            summary,
            external_env_file_source,
        ),
        "recommended_next_engineering_move": _recommended_next_engineering_move(summary),
        "do_not_run_yet": _do_not_run_yet(),
        "safety": dict(SAFETY),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }
    if error:
        payload["error"] = error
    return payload


def _overall_status(summary: Mapping[str, Any], external_source: Mapping[str, Any]) -> str:
    if (
        external_source.get("file_exists") is True
        and external_source.get("credentials_present") is True
        and external_source.get("permission_ok") is not True
    ):
        return TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_PRESENT_BUT_PERMISSION_WARNING
    if summary.get("credentials_available_for_future_signing") is True:
        return TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_READY_FOR_R251C
    if external_source.get("file_exists") is False:
        return TINY_LIVE_RUNTIME_CREDENTIAL_SOURCE_MISSING_CREATE_EXTERNAL_FILE
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def _recommended_next_operator_move(
    summary: Mapping[str, Any],
    external_source: Mapping[str, Any],
) -> str:
    if external_source.get("file_exists") is not True:
        return "CREATE_EXTERNAL_CREDENTIAL_FILE"
    if external_source.get("permission_ok") is not True and external_source.get("file_exists") is True:
        return "FIX_EXTERNAL_CREDENTIAL_FILE_PERMISSIONS"
    if summary.get("credentials_available_for_future_signing") is True:
        return "RERUN_R251C"
    return "WAIT"


def _recommended_next_engineering_move(summary: Mapping[str, Any]) -> str:
    if summary.get("credentials_available_for_future_signing") is True:
        return "Wire R251C/R252 to consume the runtime credential source resolver without printing or persisting secrets."
    return "Keep R252 submit readiness preview blocked until a runtime credential source is ready; no Binance call, no submit, no order."


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


def _current_forbidden_values(external_source: Mapping[str, Any]) -> list[str]:
    values = [
        os.environ.get(BINANCE_API_KEY_ENV),
        os.environ.get(BINANCE_API_SECRET_ENV),
    ]
    return [str(value) for value in values if value]


def _external_parse_result(
    api_key_present: bool,
    api_secret_present: bool,
    errors: Sequence[str],
    warnings: Sequence[str],
) -> dict[str, Any]:
    return {
        "api_key_present": bool(api_key_present),
        "api_secret_present": bool(api_secret_present),
        "credentials_present": bool(api_key_present and api_secret_present),
        "errors": _dedupe([str(error) for error in errors]),
        "warnings": _dedupe([str(warning) for warning in warnings]),
    }


def _strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _empty_process_env_presence() -> dict[str, Any]:
    return {
        "api_key_present": False,
        "api_secret_present": False,
        "credentials_present": False,
        "api_key_hint": None,
        "api_secret_hint": None,
        "secrets_shown": False,
        "secrets_persisted": False,
    }


def _empty_external_env_file_source() -> dict[str, Any]:
    return {
        "default_path": str(DEFAULT_EXTERNAL_ENV_FILE),
        "override_env_name": OVERRIDE_ENV_NAME,
        "resolved_path": str(DEFAULT_EXTERNAL_ENV_FILE),
        "path_is_absolute": True,
        "path_inside_repo": False,
        "file_exists": False,
        "is_regular_file": False,
        "file_mode": None,
        "permission_ok": False,
        "owner_is_current_user": None,
        "api_key_present": False,
        "api_secret_present": False,
        "credentials_present": False,
        "api_key_hint": None,
        "api_secret_hint": None,
        "secrets_shown": False,
        "secrets_persisted": False,
        "errors": ["external_env_file_missing"],
        "warnings": [],
    }


def _strip_internal_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_internal_fields(item)
            for key, item in value.items()
            if str(key) != "_secret_values_for_validation"
        }
    if isinstance(value, list):
        return [_strip_internal_fields(item) for item in value]
    return value


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if str(key) != "_secret_values_for_validation"
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
