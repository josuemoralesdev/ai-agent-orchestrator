"""R173 account-read env migration verification.

This module verifies the no-write R172 manual env migration outcome. It reads
only process env and local ledgers, never calls Binance by default, and records
only an append-only verification event after the exact confirmation phrase.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.binance_live_status import (
    ENV_ALLOW_LIVE_ORDERS,
    ENV_GLOBAL_KILL_SWITCH,
    ENV_LIVE_EXECUTION_ENABLED,
)
from src.app.hammer_radar.operator.binance_readonly import (
    ENV_CONNECTOR_MODE,
    ENV_LIVE_TRADING_ENABLED,
)
from src.app.hammer_radar.operator.env_role_adapter import (
    ACCOUNT_READ_RUNTIME_REQUIRED,
    ROLE_FUTURE_LIVE,
    SELECTED_LEGACY_FALLBACK,
    SELECTED_MISSING,
    SELECTED_ROLE_SPECIFIC,
    build_runtime_safety_flags as build_adapter_runtime_safety_flags,
    resolve_account_read_env_pair,
    resolve_future_live_env_pair,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.readonly_balance_check import LEDGER_FILENAME as READONLY_BALANCE_LEDGER_FILENAME

ACCOUNT_READ_ENV_MIGRATION_VERIFY_READY = "ACCOUNT_READ_ENV_MIGRATION_VERIFY_READY"
ACCOUNT_READ_ENV_MIGRATION_VERIFY_REJECTED = "ACCOUNT_READ_ENV_MIGRATION_VERIFY_REJECTED"
ACCOUNT_READ_ENV_MIGRATION_VERIFY_RECORDED = "ACCOUNT_READ_ENV_MIGRATION_VERIFY_RECORDED"
ACCOUNT_READ_ENV_MIGRATION_VERIFY_BLOCKED = "ACCOUNT_READ_ENV_MIGRATION_VERIFY_BLOCKED"
ACCOUNT_READ_ENV_MIGRATION_VERIFY_ERROR = "ACCOUNT_READ_ENV_MIGRATION_VERIFY_ERROR"

EVENT_TYPE = "ACCOUNT_READ_ENV_MIGRATION_VERIFY"
LEDGER_FILENAME = "account_read_env_migration_verifications.ndjson"
CONFIRM_ACCOUNT_READ_ENV_MIGRATION_VERIFY_RECORDING_PHRASE = (
    "I CONFIRM ACCOUNT READ ENV MIGRATION VERIFY RECORDING ONLY; NO ENV WRITE; NO ORDER; NO BINANCE CALL."
)

RUNTIME_SAFETY_FLAGS_REQUIRED = {
    ENV_CONNECTOR_MODE: "read_only",
    ENV_LIVE_TRADING_ENABLED: "false",
    ENV_LIVE_EXECUTION_ENABLED: "false",
    ENV_ALLOW_LIVE_ORDERS: "false",
    ENV_GLOBAL_KILL_SWITCH: "true",
}

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "full_api_key_shown": False,
    "full_api_secret_shown": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
}

SOURCE_SURFACES_USED = [
    "docs/hammer_radar/live_readiness/R172_ACCOUNT_READ_ENV_MANUAL_MIGRATION_PACKET_NO_WRITE.md",
    "src/app/hammer_radar/operator/env_role_adapter.py",
    "src/app/hammer_radar/operator/env_role_adapter_preview.py",
    "src/app/hammer_radar/operator/account_read_env_migration_packet.py",
    "src/app/hammer_radar/operator/readonly_balance_check.py",
    "src/app/hammer_radar/operator/funding_readonly_precheck.py",
    f"logs/hammer_radar_forward/{READONLY_BALANCE_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_account_read_env_migration_verify(
    *,
    log_dir: str | Path | None = None,
    record_verify: bool = False,
    confirm_account_read_env_migration_verify: str | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_account_read_env_migration_verify == CONFIRM_ACCOUNT_READ_ENV_MIGRATION_VERIFY_RECORDING_PHRASE
    )
    source = os.environ if env is None else env
    try:
        account_read = build_account_read_role_verification(env=source)
        runtime = build_runtime_safety_verification(env=source)
        future_live = build_future_live_isolation_verification(env=source)
        no_write = build_no_write_verification()
        funding_context = _build_funding_gate_context(log_dir=resolved_log_dir)
        blockers = _verification_blockers(account_read=account_read, runtime=runtime, future_live=future_live)
        status = ACCOUNT_READ_ENV_MIGRATION_VERIFY_READY if not blockers else ACCOUNT_READ_ENV_MIGRATION_VERIFY_BLOCKED
        if record_verify and not confirmation_valid:
            status = ACCOUNT_READ_ENV_MIGRATION_VERIFY_REJECTED
        elif record_verify and confirmation_valid:
            status = ACCOUNT_READ_ENV_MIGRATION_VERIFY_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "verify_recorded": False,
            "verify_id": None,
            "record_verify_requested": bool(record_verify),
            "confirmation_valid": bool(confirmation_valid),
            "account_read_role_verification": account_read,
            "runtime_safety_verification": runtime,
            "future_live_isolation": future_live,
            "no_write_verification": no_write,
            "funding_gate_context": funding_context,
            "blockers": blockers,
            "recommended_next_operator_move": _recommended_next_operator_move(
                account_read=account_read,
                runtime=runtime,
                future_live=future_live,
                funding_context=funding_context,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(
                account_read=account_read,
                runtime=runtime,
                future_live=future_live,
            ),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_verify and confirmation_valid:
            record = append_account_read_env_migration_verify_record(payload, log_dir=resolved_log_dir)
            payload["verify_recorded"] = True
            payload["verify_id"] = record["verify_id"]
            payload["ledger_path"] = str(account_read_env_migration_verify_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": ACCOUNT_READ_ENV_MIGRATION_VERIFY_ERROR,
                "generated_at": generated_at.isoformat(),
                "verify_recorded": False,
                "verify_id": None,
                "record_verify_requested": bool(record_verify),
                "confirmation_valid": bool(confirmation_valid),
                "account_read_role_verification": _empty_account_read_role_verification(),
                "runtime_safety_verification": build_runtime_safety_verification(env=source),
                "future_live_isolation": build_future_live_isolation_verification(env=source),
                "no_write_verification": build_no_write_verification(),
                "funding_gate_context": {"latest_funding_status": "UNKNOWN", "funding_ready": False},
                "blockers": ["R173 account-read env migration verification build error must be fixed before recording"],
                "recommended_next_operator_move": "FIX_ACCOUNT_READ_ENV_ROLE",
                "recommended_next_engineering_move": "Fix R173 verifier error; do not write env/config or call Binance.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_account_read_role_verification(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    resolution = resolve_account_read_env_pair(env=source)
    selected = str(resolution.get("selected_pair_source") or SELECTED_MISSING)
    legacy_fallback_used = bool(resolution.get("legacy_fallback_used"))
    passed = (
        selected == SELECTED_ROLE_SPECIFIC
        and bool(resolution.get("role_specific_pair_present"))
        and legacy_fallback_used is False
    )
    return {
        "selected_pair_source": selected,
        "role_specific_pair_present": bool(resolution.get("role_specific_pair_present")),
        "legacy_fallback_used": legacy_fallback_used,
        "api_key_hash_preview": resolution.get("api_key_hash_preview"),
        "api_secret_hash_preview": resolution.get("api_secret_hash_preview"),
        "warnings": list(resolution.get("warnings") or []),
        "secrets_shown": False,
        "passed": bool(passed),
    }


def build_runtime_safety_verification(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    flags = build_adapter_runtime_safety_flags(env=source)
    payload = {
        name: str(flags.get(name) or "n/a")
        for name in (
            ENV_CONNECTOR_MODE,
            ENV_LIVE_TRADING_ENABLED,
            ENV_LIVE_EXECUTION_ENABLED,
            ENV_ALLOW_LIVE_ORDERS,
            ENV_GLOBAL_KILL_SWITCH,
        )
    }
    failed = [name for name, required in RUNTIME_SAFETY_FLAGS_REQUIRED.items() if payload.get(name).lower() != required]
    payload["passed"] = not failed and _account_read_adapter_runtime_required_matches()
    payload["failed_flags"] = failed
    return payload


def build_future_live_isolation_verification(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    resolution = resolve_future_live_env_pair(env=source)
    future_live_disabled = bool(resolution.get("future_live_disabled"))
    legacy_fallback_used = bool(resolution.get("legacy_fallback_used"))
    return {
        "future_live_disabled": future_live_disabled,
        "selected_pair_source": str(resolution.get("selected_pair_source") or SELECTED_MISSING),
        "legacy_fallback_used_for_future_live": legacy_fallback_used,
        "legacy_fallback_allowed": bool(resolution.get("legacy_fallback_allowed")),
        "role": resolution.get("role") or ROLE_FUTURE_LIVE,
        "passed": future_live_disabled and legacy_fallback_used is False,
    }


def build_no_write_verification() -> dict[str, bool]:
    return {
        "env_written": False,
        "env_mutated": False,
        "config_written": False,
    }


def append_account_read_env_migration_verify_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = account_read_env_migration_verify_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "verify_id": record.get("verify_id") or f"r173_account_read_env_migration_verify_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_verify_requested": bool(record.get("record_verify_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "account_read_role_verification": dict(record.get("account_read_role_verification") or {}),
            "runtime_safety_verification": dict(record.get("runtime_safety_verification") or {}),
            "future_live_isolation": dict(record.get("future_live_isolation") or {}),
            "no_write_verification": dict(record.get("no_write_verification") or {}),
            "funding_gate_context": dict(record.get("funding_gate_context") or {}),
            "blockers": list(record.get("blockers") or []),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_account_read_env_migration_verify_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = account_read_env_migration_verify_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]


def summarize_account_read_env_migration_verifications(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    latest_role = latest.get("account_read_role_verification") or {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_verify_id": latest.get("verify_id"),
        "last_selected_pair_source": latest_role.get("selected_pair_source") if isinstance(latest_role, Mapping) else None,
        "safety": dict(SAFETY),
    }


def account_read_env_migration_verify_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_account_read_env_migration_verify_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_funding_gate_context(*, log_dir: Path) -> dict[str, Any]:
    path = Path(log_dir) / READONLY_BALANCE_LEDGER_FILENAME
    latest = read_recent_ndjson_records(path, limit=1, max_bytes=32_000_000)
    record = latest[0] if latest else {}
    balance_check = record.get("balance_check") or {}
    readiness = str(record.get("balance_readiness") or balance_check.get("funding_status") or "UNKNOWN")
    if readiness != "ACCOUNT_NOT_FUNDED":
        readiness = "UNKNOWN"
    return {
        "latest_funding_status": readiness,
        "funding_ready": False,
    }


def _verification_blockers(
    *,
    account_read: Mapping[str, Any],
    runtime: Mapping[str, Any],
    future_live: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if account_read.get("passed") is not True:
        selected = account_read.get("selected_pair_source") or SELECTED_MISSING
        if selected == SELECTED_LEGACY_FALLBACK:
            blockers.append("account_read is still using legacy fallback; source HAMMER_ACCOUNT_READ_* in the current shell")
        elif selected == SELECTED_MISSING:
            blockers.append("account_read role-specific key/secret pair is missing")
        else:
            blockers.append("account_read role verification failed")
    if runtime.get("passed") is not True:
        failed = ", ".join(str(item) for item in runtime.get("failed_flags") or [])
        blockers.append(f"runtime safety flags are not forced read-only/live-disabled/kill-switch-on: {failed or 'unknown'}")
    if future_live.get("passed") is not True:
        blockers.append("future_live isolation failed; legacy fallback must remain disabled")
    return blockers


def _recommended_next_operator_move(
    *,
    account_read: Mapping[str, Any],
    runtime: Mapping[str, Any],
    future_live: Mapping[str, Any],
    funding_context: Mapping[str, Any],
) -> str:
    if account_read.get("passed") is not True or runtime.get("passed") is not True or future_live.get("passed") is not True:
        return "FIX_ACCOUNT_READ_ENV_ROLE"
    if funding_context.get("latest_funding_status") == "ACCOUNT_NOT_FUNDED":
        return "RUN_R174_FUNDING_EVIDENCE_SYNC"
    return "RUN_READONLY_BALANCE_CHECK_WITH_ROLE_SPECIFIC_ACCOUNT_READ"


def _recommended_next_engineering_move(
    *,
    account_read: Mapping[str, Any],
    runtime: Mapping[str, Any],
    future_live: Mapping[str, Any],
) -> str:
    if account_read.get("passed") is not True:
        return "Do not change code or env files; have the operator source HAMMER_ACCOUNT_READ_* in the current shell and rerun R173."
    if runtime.get("passed") is not True:
        return "Do not change lane/live config; have the operator force read-only runtime flags and rerun R173."
    if future_live.get("passed") is not True:
        return "Keep future-live disabled and fix the env-role adapter isolation before any funding sync."
    return "Proceed to R174 funding evidence sync only after an explicit operator-run read-only balance result exists."


def _do_not_run_yet() -> list[str]:
    return [
        "write env files",
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set short lane tiny_live",
        "transfer",
        "withdraw",
    ]


def _empty_account_read_role_verification() -> dict[str, Any]:
    return {
        "selected_pair_source": SELECTED_MISSING,
        "role_specific_pair_present": False,
        "legacy_fallback_used": False,
        "api_key_hash_preview": None,
        "api_secret_hash_preview": None,
        "secrets_shown": False,
        "passed": False,
    }


def _account_read_adapter_runtime_required_matches() -> bool:
    return all(ACCOUNT_READ_RUNTIME_REQUIRED.get(name) == value for name, value in RUNTIME_SAFETY_FLAGS_REQUIRED.items())


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return {str(key): _sanitize(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, tuple):
        return [_sanitize(item) for item in payload]
    return payload
