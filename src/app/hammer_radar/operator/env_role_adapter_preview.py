"""R170 no-write Binance env role adapter preview.

This module previews the R169 role-specific Binance env selection order without
mutating env/config files and without calling Binance. It emits only presence,
lengths, and hash previews for candidate key/secret pairs.
"""

from __future__ import annotations

import hashlib
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
    ENV_BINANCE_LIVE_ENABLED,
    ENV_GLOBAL_KILL_SWITCH,
    ENV_LIVE_EXECUTION_ENABLED,
)
from src.app.hammer_radar.operator.binance_readonly import (
    ENV_API_KEY,
    ENV_API_SECRET,
    ENV_CONNECTOR_MODE,
    ENV_LIVE_TRADING_ENABLED,
)
from src.app.hammer_radar.operator.env_role_split_proposal import (
    ACCOUNT_READ_KEY_VAR,
    ACCOUNT_READ_SECRET_VAR,
    LIVE_KEY_VAR,
    LIVE_SECRET_VAR,
    MARKET_KEY_VAR,
    MARKET_SECRET_VAR,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE

ENV_ROLE_ADAPTER_PREVIEW_READY = "ENV_ROLE_ADAPTER_PREVIEW_READY"
ENV_ROLE_ADAPTER_PREVIEW_REJECTED = "ENV_ROLE_ADAPTER_PREVIEW_REJECTED"
ENV_ROLE_ADAPTER_PREVIEW_RECORDED = "ENV_ROLE_ADAPTER_PREVIEW_RECORDED"
ENV_ROLE_ADAPTER_PREVIEW_BLOCKED = "ENV_ROLE_ADAPTER_PREVIEW_BLOCKED"
ENV_ROLE_ADAPTER_PREVIEW_ERROR = "ENV_ROLE_ADAPTER_PREVIEW_ERROR"

ROLE_MARKET_DATA = "market_data"
ROLE_ACCOUNT_READ = "account_read"
ROLE_FUTURE_LIVE = "future_live"
ROLES = (ROLE_MARKET_DATA, ROLE_ACCOUNT_READ, ROLE_FUTURE_LIVE)

EVENT_TYPE = "ENV_ROLE_ADAPTER_PREVIEW"
LEDGER_FILENAME = "env_role_adapter_previews.ndjson"
CONFIRM_ENV_ROLE_ADAPTER_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM ENV ROLE ADAPTER PREVIEW RECORDING ONLY; NO ENV WRITE; NO ORDER; NO BINANCE CALL."
)

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
    "docs/hammer_radar/live_readiness/R169_ENV_ROLE_SPLIT_PROPOSAL_NO_WRITE.md",
    "src/app/hammer_radar/operator/env_role_split_proposal.py",
    "src/app/hammer_radar/operator/funding_gate_key_role_sync.py",
    "src/app/hammer_radar/operator/funding_readonly_precheck.py",
    "src/app/hammer_radar/operator/readonly_balance_check.py",
    "src/app/hammer_radar/operator/inspect.py",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_env_role_adapter_preview(
    *,
    log_dir: str | Path | None = None,
    record_preview: bool = False,
    confirm_env_role_adapter_preview: str | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_env_role_adapter_preview == CONFIRM_ENV_ROLE_ADAPTER_PREVIEW_RECORDING_PHRASE
    source = os.environ if env is None else env
    try:
        matrix = build_role_resolution_matrix(env=source)
        runtime_flags = build_runtime_safety_flags(env=source)
        risks = detect_legacy_fallback_risks(role_resolution_matrix=matrix, runtime_safety_flags=runtime_flags)
        migration_plan = build_adapter_migration_plan(role_resolution_matrix=matrix, legacy_fallback_risks=risks)
        status = ENV_ROLE_ADAPTER_PREVIEW_READY
        if record_preview and not confirmation_valid:
            status = ENV_ROLE_ADAPTER_PREVIEW_REJECTED
        elif record_preview and confirmation_valid:
            status = ENV_ROLE_ADAPTER_PREVIEW_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "preview_recorded": False,
            "preview_id": None,
            "record_preview_requested": bool(record_preview),
            "confirmation_valid": bool(confirmation_valid),
            "role_resolution_matrix": matrix,
            "runtime_safety_flags": runtime_flags,
            "legacy_fallback_risks": risks,
            "adapter_migration_plan": migration_plan,
            "recommended_next_operator_move": _recommended_next_operator_move(
                record_preview=record_preview,
                confirmation_valid=confirmation_valid,
                legacy_fallback_risks=risks,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(matrix),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_preview and confirmation_valid:
            record = append_env_role_adapter_preview_record(payload, log_dir=resolved_log_dir)
            payload["preview_recorded"] = True
            payload["preview_id"] = record["preview_id"]
            payload["ledger_path"] = str(env_role_adapter_preview_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": ENV_ROLE_ADAPTER_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "preview_recorded": False,
                "preview_id": None,
                "record_preview_requested": bool(record_preview),
                "confirmation_valid": bool(confirmation_valid),
                "role_resolution_matrix": {role: _missing_resolution(role) for role in ROLES},
                "runtime_safety_flags": build_runtime_safety_flags(env=source),
                "legacy_fallback_risks": ["R170 env role adapter preview build error must be fixed before recording"],
                "adapter_migration_plan": build_adapter_migration_plan(role_resolution_matrix={}, legacy_fallback_risks=[]),
                "recommended_next_operator_move": "KEEP_ENV_UNCHANGED",
                "recommended_next_engineering_move": "Fix R170 env role adapter preview builder error before implementation wiring.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_role_specific_env_schema() -> dict[str, Any]:
    return {
        ROLE_MARKET_DATA: {
            "role_specific_pair": [MARKET_KEY_VAR, MARKET_SECRET_VAR],
            "legacy_fallback_pair": [ENV_API_KEY, ENV_API_SECRET],
            "fallback_allowed": True,
            "legacy_fallback_marked_ambiguous": True,
            "may_place_orders": False,
        },
        ROLE_ACCOUNT_READ: {
            "role_specific_pair": [ACCOUNT_READ_KEY_VAR, ACCOUNT_READ_SECRET_VAR],
            "legacy_fallback_pair": [ENV_API_KEY, ENV_API_SECRET],
            "fallback_allowed": True,
            "legacy_fallback_marked_ambiguous": True,
            "required_runtime_flags": {
                ENV_CONNECTOR_MODE: "read_only",
                ENV_LIVE_TRADING_ENABLED: "false",
                ENV_BINANCE_LIVE_ENABLED: "false",
                ENV_LIVE_EXECUTION_ENABLED: "false",
                ENV_ALLOW_LIVE_ORDERS: "false",
                ENV_GLOBAL_KILL_SWITCH: "true",
            },
            "may_place_orders": False,
        },
        ROLE_FUTURE_LIVE: {
            "role_specific_pair": [LIVE_KEY_VAR, LIVE_SECRET_VAR],
            "legacy_fallback_pair": [],
            "fallback_allowed": False,
            "future_live_disabled": True,
            "may_place_orders": False,
        },
        "secrets_shown": False,
    }


def resolve_env_role_preview(role: str, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    schema = build_role_specific_env_schema()
    if role not in ROLES:
        raise ValueError(f"unsupported env role: {role}")
    role_schema = dict(schema[role])
    role_pair = list(role_schema["role_specific_pair"])
    legacy_pair = list(role_schema.get("legacy_fallback_pair") or [])
    role_specific = _pair_summary(source, role_pair, "role_specific")
    legacy = _pair_summary(source, legacy_pair, "legacy_fallback") if legacy_pair else _empty_pair_summary("legacy_fallback")

    selected_source = "missing"
    selected = _empty_pair_summary("missing")
    legacy_fallback_used = False
    legacy_ambiguous = False
    if _pair_complete(role_specific):
        selected_source = "role_specific"
        selected = role_specific
    elif role != ROLE_FUTURE_LIVE and _pair_absent(role_specific) and _pair_complete(legacy):
        selected_source = "legacy_fallback"
        selected = legacy
        legacy_fallback_used = True
        legacy_ambiguous = True

    partial_pair_detected = _pair_partial(role_specific) or (role != ROLE_FUTURE_LIVE and _pair_partial(legacy))
    resolution = {
        "role": role,
        "selected_pair_source": selected_source,
        "api_key_variable": selected.get("api_key_variable"),
        "api_secret_variable": selected.get("api_secret_variable"),
        "api_key_present": bool(selected.get("api_key_present")),
        "api_secret_present": bool(selected.get("api_secret_present")),
        "api_key_length": int(selected.get("api_key_length") or 0),
        "api_secret_length": int(selected.get("api_secret_length") or 0),
        "api_key_hash_preview": selected.get("api_key_hash_preview"),
        "api_secret_hash_preview": selected.get("api_secret_hash_preview"),
        "role_specific_pair_present": _pair_complete(role_specific),
        "role_specific_pair_partial": _pair_partial(role_specific),
        "legacy_pair_present": _pair_complete(legacy),
        "legacy_pair_partial": _pair_partial(legacy),
        "partial_pair_detected": partial_pair_detected,
        "legacy_fallback_used": legacy_fallback_used,
        "legacy_ambiguous": legacy_ambiguous,
        "full_api_key_shown": False,
        "full_api_secret_shown": False,
        "secrets_shown": False,
    }
    if role == ROLE_ACCOUNT_READ:
        runtime = build_runtime_safety_flags(env=source)
        resolution["account_read_runtime_required"] = {
            ENV_CONNECTOR_MODE: "read_only",
            ENV_LIVE_TRADING_ENABLED: "false",
            ENV_BINANCE_LIVE_ENABLED: "false",
            ENV_LIVE_EXECUTION_ENABLED: "false",
            ENV_ALLOW_LIVE_ORDERS: "false",
            ENV_GLOBAL_KILL_SWITCH: "true",
        }
        resolution["account_read_runtime_safe"] = _account_read_runtime_safe(runtime)
    if role == ROLE_FUTURE_LIVE:
        legacy_present = bool(_env_value(source, ENV_API_KEY)) and bool(_env_value(source, ENV_API_SECRET))
        resolution["future_live_disabled"] = True
        resolution["legacy_fallback_allowed"] = False
        resolution["legacy_pair_present_ignored"] = legacy_present
    return resolution


def build_role_resolution_matrix(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    return {role: resolve_env_role_preview(role, env=source) for role in ROLES}


def build_runtime_safety_flags(*, env: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    return {
        ENV_CONNECTOR_MODE: _env_value(source, ENV_CONNECTOR_MODE) or "n/a",
        ENV_LIVE_TRADING_ENABLED: _env_value(source, ENV_LIVE_TRADING_ENABLED) or "n/a",
        ENV_BINANCE_LIVE_ENABLED: _env_value(source, ENV_BINANCE_LIVE_ENABLED) or "n/a",
        ENV_LIVE_EXECUTION_ENABLED: _env_value(source, ENV_LIVE_EXECUTION_ENABLED) or "n/a",
        ENV_ALLOW_LIVE_ORDERS: _env_value(source, ENV_ALLOW_LIVE_ORDERS) or "n/a",
        ENV_GLOBAL_KILL_SWITCH: _env_value(source, ENV_GLOBAL_KILL_SWITCH) or "n/a",
    }


def detect_legacy_fallback_risks(
    *,
    role_resolution_matrix: Mapping[str, Any],
    runtime_safety_flags: Mapping[str, str] | None = None,
) -> list[str]:
    risks: list[str] = []
    market = role_resolution_matrix.get(ROLE_MARKET_DATA) or {}
    account = role_resolution_matrix.get(ROLE_ACCOUNT_READ) or {}
    future_live = role_resolution_matrix.get(ROLE_FUTURE_LIVE) or {}
    for role in (ROLE_MARKET_DATA, ROLE_ACCOUNT_READ):
        resolution = role_resolution_matrix.get(role) or {}
        if resolution.get("legacy_fallback_used"):
            risks.append(f"{role} uses legacy BINANCE_API_KEY/BINANCE_API_SECRET fallback; role source remains ambiguous")
        if resolution.get("partial_pair_detected"):
            risks.append(f"{role} has a partial key/secret pair; do not migrate or wire until pair is complete")
    if market.get("legacy_fallback_used") and account.get("legacy_fallback_used"):
        risks.append("market_data and account_read both fall back to the same legacy pair; intended key role cannot be proven")
    if future_live.get("legacy_pair_present_ignored"):
        risks.append("future_live ignores legacy BINANCE_API_KEY/BINANCE_API_SECRET by design")
    if future_live.get("partial_pair_detected"):
        risks.append("future_live role-specific pair is partial; keep future live disabled")
    flags = runtime_safety_flags or {}
    if flags and not _account_read_runtime_safe(flags):
        risks.append("account_read runtime flags are not in the required read-only/live-disabled/kill-switch-on state")
    return _dedupe(risks)


def build_adapter_migration_plan(
    *,
    role_resolution_matrix: Mapping[str, Any],
    legacy_fallback_risks: list[str],
) -> list[dict[str, Any]]:
    return [
        {
            "step": 1,
            "action": "review_adapter_preview",
            "write_env": False,
            "description": "Review selected pair sources, hash previews, lengths, partial pairs, and legacy fallback risks.",
        },
        {
            "step": 2,
            "action": "keep_env_unchanged",
            "write_env": False,
            "description": "Do not write .env or role env files during R170.",
        },
        {
            "step": 3,
            "action": "fill_role_specific_pairs_manually_later",
            "write_env": "future_operator_phase_only",
            "description": "In a later approved phase, copy complete key/secret pairs into the R169 role-specific variables.",
        },
        {
            "step": 4,
            "action": "run_r171_adapter_implementation_no_env_write",
            "write_env": False,
            "description": "Wire account-read preview helpers into read-only balance and funding precheck code without env writes or test Binance calls.",
        },
        {
            "step": 5,
            "action": "preserve_future_live_disabled",
            "write_env": False,
            "description": "Keep future_live disabled and prevent legacy fallback for any live role until an explicit future live phase.",
        },
        {
            "step": 6,
            "action": "resolve_legacy_fallback_risks",
            "write_env": False,
            "description": "Treat legacy fallback warnings as migration guidance, not execution approval.",
            "risk_count": len(legacy_fallback_risks),
            "roles_using_legacy_fallback": [
                role
                for role, resolution in role_resolution_matrix.items()
                if isinstance(resolution, Mapping) and resolution.get("legacy_fallback_used")
            ],
        },
    ]


def append_env_role_adapter_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = env_role_adapter_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "preview_id": record.get("preview_id") or f"r170_env_role_adapter_preview_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_preview_requested": bool(record.get("record_preview_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "role_resolution_matrix": dict(record.get("role_resolution_matrix") or {}),
            "runtime_safety_flags": dict(record.get("runtime_safety_flags") or {}),
            "legacy_fallback_risks": list(record.get("legacy_fallback_risks") or []),
            "adapter_migration_plan": list(record.get("adapter_migration_plan") or []),
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


def load_env_role_adapter_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = env_role_adapter_preview_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_env_role_adapter_previews(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    latest_matrix = latest.get("role_resolution_matrix") if isinstance(latest.get("role_resolution_matrix"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_preview_id": latest.get("preview_id"),
        "last_recommended_next_operator_move": latest.get("recommended_next_operator_move"),
        "last_roles_using_legacy_fallback": [
            role
            for role, resolution in latest_matrix.items()
            if isinstance(resolution, Mapping) and resolution.get("legacy_fallback_used")
        ],
        "safety": dict(SAFETY),
    }


def env_role_adapter_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_env_role_adapter_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _pair_summary(source: Mapping[str, str], pair: list[str], pair_source: str) -> dict[str, Any]:
    if len(pair) != 2:
        return _empty_pair_summary(pair_source)
    key_var, secret_var = pair
    key_value = _env_value(source, key_var)
    secret_value = _env_value(source, secret_var)
    return {
        "pair_source": pair_source,
        "api_key_variable": key_var,
        "api_secret_variable": secret_var,
        "api_key_present": bool(key_value),
        "api_secret_present": bool(secret_value),
        "api_key_length": len(key_value) if key_value else 0,
        "api_secret_length": len(secret_value) if secret_value else 0,
        "api_key_hash_preview": _hash_preview(key_value),
        "api_secret_hash_preview": _hash_preview(secret_value),
        "full_api_key_shown": False,
        "full_api_secret_shown": False,
        "secrets_shown": False,
    }


def _empty_pair_summary(pair_source: str) -> dict[str, Any]:
    return {
        "pair_source": pair_source,
        "api_key_variable": None,
        "api_secret_variable": None,
        "api_key_present": False,
        "api_secret_present": False,
        "api_key_length": 0,
        "api_secret_length": 0,
        "api_key_hash_preview": None,
        "api_secret_hash_preview": None,
        "full_api_key_shown": False,
        "full_api_secret_shown": False,
        "secrets_shown": False,
    }


def _missing_resolution(role: str) -> dict[str, Any]:
    return {
        "role": role,
        "selected_pair_source": "missing",
        "api_key_present": False,
        "api_secret_present": False,
        "api_key_hash_preview": None,
        "api_secret_hash_preview": None,
        "legacy_fallback_used": False,
        "secrets_shown": False,
    }


def _pair_complete(pair_summary: Mapping[str, Any]) -> bool:
    return bool(pair_summary.get("api_key_present")) and bool(pair_summary.get("api_secret_present"))


def _pair_absent(pair_summary: Mapping[str, Any]) -> bool:
    return not pair_summary.get("api_key_present") and not pair_summary.get("api_secret_present")


def _pair_partial(pair_summary: Mapping[str, Any]) -> bool:
    return bool(pair_summary.get("api_key_present")) != bool(pair_summary.get("api_secret_present"))


def _env_value(source: Mapping[str, str], key: str) -> str:
    value = source.get(key)
    return "" if value is None else str(value).strip()


def _hash_preview(value: str) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _account_read_runtime_safe(runtime_flags: Mapping[str, str]) -> bool:
    return (
        str(runtime_flags.get(ENV_CONNECTOR_MODE) or "").lower() == "read_only"
        and str(runtime_flags.get(ENV_LIVE_TRADING_ENABLED) or "").lower() == "false"
        and str(runtime_flags.get(ENV_BINANCE_LIVE_ENABLED) or "").lower() == "false"
        and str(runtime_flags.get(ENV_LIVE_EXECUTION_ENABLED) or "").lower() == "false"
        and str(runtime_flags.get(ENV_ALLOW_LIVE_ORDERS) or "").lower() == "false"
        and str(runtime_flags.get(ENV_GLOBAL_KILL_SWITCH) or "").lower() == "true"
    )


def _recommended_next_operator_move(
    *,
    record_preview: bool,
    confirmation_valid: bool,
    legacy_fallback_risks: list[str],
) -> str:
    if record_preview and not confirmation_valid:
        return "KEEP_ENV_UNCHANGED"
    if legacy_fallback_risks:
        return "REVIEW_ADAPTER_PREVIEW"
    return "RUN_R171_ENV_ROLE_ADAPTER_IMPLEMENTATION_NO_WRITE"


def _recommended_next_engineering_move(role_resolution_matrix: Mapping[str, Any]) -> str:
    account = role_resolution_matrix.get(ROLE_ACCOUNT_READ)
    if isinstance(account, Mapping) and account.get("account_read_runtime_safe") is False:
        return "Keep R171 blocked until account-read runtime flags are read_only, live-disabled, and kill-switch-on."
    return "Build R171 code-level adapter wiring for read-only balance and funding precheck without env writes or Binance calls in tests."


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


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return {str(key): _sanitize(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, tuple):
        return [_sanitize(item) for item in payload]
    return payload
