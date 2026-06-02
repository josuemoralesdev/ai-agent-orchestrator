"""R169 no-write Binance env role split proposal.

This module is diagnostic/audit only. It fingerprints current local env-role
surfaces with hash previews and lengths, proposes future role-specific variable
names, and may append a proposal record after exact confirmation. It never calls
Binance, mutates env/config files, creates order payloads, or enables live
execution.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.binance_readonly import ENV_API_KEY, ENV_API_SECRET
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.funding_gate_key_role_sync import (
    DEFAULT_BINANCE_LIVE_ENV_PATH,
    DEFAULT_BINANCE_READONLY_ENV_PATH,
    DEFAULT_REPO_ENV_PATH,
    detect_key_secret_pair_mismatch,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE

ENV_ROLE_SPLIT_PROPOSAL_READY = "ENV_ROLE_SPLIT_PROPOSAL_READY"
ENV_ROLE_SPLIT_PROPOSAL_REJECTED = "ENV_ROLE_SPLIT_PROPOSAL_REJECTED"
ENV_ROLE_SPLIT_PROPOSAL_RECORDED = "ENV_ROLE_SPLIT_PROPOSAL_RECORDED"
ENV_ROLE_SPLIT_PROPOSAL_BLOCKED = "ENV_ROLE_SPLIT_PROPOSAL_BLOCKED"
ENV_ROLE_SPLIT_PROPOSAL_ERROR = "ENV_ROLE_SPLIT_PROPOSAL_ERROR"

EVENT_TYPE = "ENV_ROLE_SPLIT_PROPOSAL"
LEDGER_FILENAME = "env_role_split_proposals.ndjson"
CONFIRM_ENV_ROLE_SPLIT_PROPOSAL_RECORDING_PHRASE = (
    "I CONFIRM ENV ROLE SPLIT PROPOSAL RECORDING ONLY; NO ENV WRITE; NO ORDER; NO BINANCE CALL."
)

MARKET_KEY_VAR = "HAMMER_MARKET_BINANCE_API_KEY"
MARKET_SECRET_VAR = "HAMMER_MARKET_BINANCE_API_SECRET"
ACCOUNT_READ_KEY_VAR = "HAMMER_ACCOUNT_READ_BINANCE_API_KEY"
ACCOUNT_READ_SECRET_VAR = "HAMMER_ACCOUNT_READ_BINANCE_API_SECRET"
LIVE_KEY_VAR = "HAMMER_LIVE_BINANCE_API_KEY"
LIVE_SECRET_VAR = "HAMMER_LIVE_BINANCE_API_SECRET"

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
    "protective_order_endpoint_called": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "signature_shown": False,
    "signed_url_shown": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
}

SOURCE_SURFACES_USED = [
    "codex_tasks/phases/R169_ENV_ROLE_SPLIT_PROPOSAL_NO_WRITE.txt",
    "docs/hammer_radar/live_readiness/PHASE_INDEX.md",
    "docs/hammer_radar/live_readiness/R168_FUNDING_GATE_RECHECK_AND_KEY_ROLE_SYNC.md",
    "src/app/hammer_radar/operator/funding_gate_key_role_sync.py",
    "repo .env fingerprint only",
    "binance-readonly.env fingerprint only",
    "binance-live.env fingerprint only",
]


def build_env_role_split_proposal(
    *,
    log_dir: str | Path | None = None,
    record_proposal: bool = False,
    confirm_env_role_split_proposal: str | None = None,
    repo_env_path: str | Path = DEFAULT_REPO_ENV_PATH,
    readonly_env_path: str | Path = DEFAULT_BINANCE_READONLY_ENV_PATH,
    live_env_path: str | Path = DEFAULT_BINANCE_LIVE_ENV_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_env_role_split_proposal == CONFIRM_ENV_ROLE_SPLIT_PROPOSAL_RECORDING_PHRASE
    try:
        inventory = build_current_env_role_inventory(
            repo_env_path=repo_env_path,
            readonly_env_path=readonly_env_path,
            live_env_path=live_env_path,
        )
        schema = build_proposed_env_role_schema()
        compatibility_plan = build_backward_compatibility_plan()
        migration_steps = build_operator_migration_steps()
        blockers = build_env_role_blockers(current_env_inventory=inventory)
        status = ENV_ROLE_SPLIT_PROPOSAL_READY
        if record_proposal and not confirmation_valid:
            status = ENV_ROLE_SPLIT_PROPOSAL_REJECTED
        elif record_proposal and confirmation_valid:
            status = ENV_ROLE_SPLIT_PROPOSAL_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "proposal_recorded": False,
            "proposal_id": None,
            "record_proposal_requested": bool(record_proposal),
            "confirmation_valid": bool(confirmation_valid),
            "current_env_inventory": inventory,
            "proposed_env_role_schema": schema,
            "backward_compatibility_plan": compatibility_plan,
            "operator_migration_steps": migration_steps,
            "blockers": blockers,
            "recommended_next_operator_move": _recommended_next_operator_move(
                record_proposal=record_proposal,
                confirmation_valid=confirmation_valid,
                blockers=blockers,
            ),
            "recommended_next_engineering_move": "Create R170 env-role adapter preview that prefers role-specific variables without writing env files.",
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_proposal and confirmation_valid:
            record = append_env_role_split_proposal_record(payload, log_dir=resolved_log_dir)
            payload["proposal_recorded"] = True
            payload["proposal_id"] = record["proposal_id"]
            payload["ledger_path"] = str(env_role_split_proposal_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": ENV_ROLE_SPLIT_PROPOSAL_ERROR,
                "generated_at": generated_at.isoformat(),
                "proposal_recorded": False,
                "proposal_id": None,
                "record_proposal_requested": bool(record_proposal),
                "confirmation_valid": bool(confirmation_valid),
                "current_env_inventory": _empty_current_env_inventory(),
                "proposed_env_role_schema": build_proposed_env_role_schema(),
                "backward_compatibility_plan": build_backward_compatibility_plan(),
                "operator_migration_steps": build_operator_migration_steps(),
                "blockers": ["R169 env role split proposal build error must be fixed before recording"],
                "recommended_next_operator_move": "KEEP_CURRENT_ENV_UNCHANGED",
                "recommended_next_engineering_move": "Fix env role split proposal builder error before R170 adapter preview.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_current_env_role_inventory(
    *,
    repo_env_path: str | Path = DEFAULT_REPO_ENV_PATH,
    readonly_env_path: str | Path = DEFAULT_BINANCE_READONLY_ENV_PATH,
    live_env_path: str | Path = DEFAULT_BINANCE_LIVE_ENV_PATH,
) -> dict[str, Any]:
    roles = {
        "repo_env": _env_file_inventory(repo_env_path, role="legacy_ambiguous_repo_env"),
        "binance_readonly_env": _env_file_inventory(readonly_env_path, role="market_or_readonly_status_key"),
        "binance_live_env": _env_file_inventory(live_env_path, role="account_read_key_when_runtime_forces_read_only"),
    }
    mismatch = detect_key_secret_pair_mismatch(roles)
    return {
        **roles,
        "mismatched_pair_detected": bool(mismatch["mismatched_pair_detected"]),
        "mismatch_evidence": list(mismatch["mismatch_evidence"]),
        "comparison_method": "sha256_preview_and_value_length_only",
        "current_ambiguity_detected": _legacy_ambiguity_detected(roles),
        "secrets_shown": False,
    }


def build_proposed_env_role_schema() -> dict[str, Any]:
    return {
        "market_data_role": {
            "api_key_variable": MARKET_KEY_VAR,
            "api_secret_variable": MARKET_SECRET_VAR,
            "intended_use": "market data, exchange status, and public/read-only market surfaces",
            "may_call_account_balance": False,
            "may_place_orders": False,
            "may_be_used_for_future_live_trading": False,
            "preferred_file": "/home/josue/.config/hammer-radar/binance-market.env",
        },
        "account_read_role": {
            "api_key_variable": ACCOUNT_READ_KEY_VAR,
            "api_secret_variable": ACCOUNT_READ_SECRET_VAR,
            "intended_use": "Futures account balance/readiness checks only when runtime flags force read-only mode",
            "may_call_account_balance": True,
            "may_place_orders": False,
            "may_be_used_for_future_live_trading": False,
            "preferred_file": "/home/josue/.config/hammer-radar/binance-account-read.env",
            "required_connector_mode": "read_only",
        },
        "future_live_role": {
            "api_key_variable": LIVE_KEY_VAR,
            "api_secret_variable": LIVE_SECRET_VAR,
            "intended_use": "reserved for explicitly approved future live/trading phase only",
            "may_call_account_balance": False,
            "may_place_orders": False,
            "may_be_used_for_future_live_trading": "future_phase_only_after_explicit_approval",
            "preferred_file": "/home/josue/.config/hammer-radar/binance-live.env",
            "default_state": "disabled",
        },
        "runtime_safety_flags": {
            "BINANCE_CONNECTOR_MODE": "read_only",
            "BINANCE_LIVE_TRADING_ENABLED": "false",
            "HAMMER_BINANCE_LIVE_ENABLED": "false",
            "HAMMER_LIVE_EXECUTION_ENABLED": "false",
            "HAMMER_ALLOW_LIVE_ORDERS": "false",
            "HAMMER_GLOBAL_KILL_SWITCH": "true",
        },
        "secrets_shown": False,
    }


def build_backward_compatibility_plan() -> dict[str, Any]:
    return {
        "legacy_variables": [ENV_API_KEY, ENV_API_SECRET],
        "short_term_support": True,
        "market_data_preference_order": [
            [MARKET_KEY_VAR, MARKET_SECRET_VAR],
            [ENV_API_KEY, ENV_API_SECRET],
        ],
        "account_read_preference_order": [
            [ACCOUNT_READ_KEY_VAR, ACCOUNT_READ_SECRET_VAR],
            [ENV_API_KEY, ENV_API_SECRET],
        ],
        "future_live_preference_order": [
            [LIVE_KEY_VAR, LIVE_SECRET_VAR],
        ],
        "legacy_pair_allowed_only_when_role_specific_pair_absent": True,
        "legacy_pair_must_match_as_key_secret_pair": True,
        "future_live_variables_must_remain_unused_until_future_live_phase": True,
        "r170_preview_should_validate_pair_source_consistency": True,
        "secrets_shown": False,
    }


def build_operator_migration_steps() -> list[dict[str, Any]]:
    return [
        {
            "step": 1,
            "action": "review_current_inventory",
            "write_env": False,
            "description": "Review hash/length-only inventory and confirm which local file maps to market, account-read, and reserved live roles.",
        },
        {
            "step": 2,
            "action": "keep_current_env_unchanged",
            "write_env": False,
            "description": "Do not edit .env or role env files during R169; leave mixed legacy state untouched until an approved migration phase.",
        },
        {
            "step": 3,
            "action": "approve_r170_adapter_preview",
            "write_env": False,
            "description": "Run an R170 code-level preview that selects role-specific variables when present and reports fallback to legacy variables.",
        },
        {
            "step": 4,
            "action": "future_manual_env_migration",
            "write_env": "future_phase_only",
            "description": "Only after explicit future approval, copy complete key/secret pairs into role-specific variables without mixing pair sources.",
        },
        {
            "step": 5,
            "action": "verify_read_only_runtime_flags",
            "write_env": False,
            "description": "Keep read-only connector mode, live flags false, and global kill switch true for account-read checks.",
        },
    ]


def build_env_role_blockers(*, current_env_inventory: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if current_env_inventory.get("mismatched_pair_detected"):
        blockers.append("legacy BINANCE_API_KEY/BINANCE_API_SECRET role ambiguity or mismatched pair evidence detected")
    repo_env = current_env_inventory.get("repo_env")
    if isinstance(repo_env, Mapping) and repo_env.get("api_key_present") and repo_env.get("api_secret_present"):
        blockers.append("repo .env still uses ambiguous BINANCE_API_KEY/BINANCE_API_SECRET names")
    blockers.append("no approved env-write migration phase exists yet")
    return _dedupe(blockers)


def append_env_role_split_proposal_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = env_role_split_proposal_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "proposal_id": record.get("proposal_id") or f"r169_env_role_split_proposal_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_proposal_requested": bool(record.get("record_proposal_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "current_env_inventory": dict(record.get("current_env_inventory") or {}),
            "proposed_env_role_schema": dict(record.get("proposed_env_role_schema") or {}),
            "backward_compatibility_plan": dict(record.get("backward_compatibility_plan") or {}),
            "operator_migration_steps": list(record.get("operator_migration_steps") or []),
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


def load_env_role_split_proposal_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = env_role_split_proposal_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_env_role_split_proposals(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_proposal_id": latest.get("proposal_id"),
        "last_recommended_next_operator_move": latest.get("recommended_next_operator_move"),
        "safety": dict(SAFETY),
    }


def env_role_split_proposal_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_env_role_split_proposal_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _env_file_inventory(path: str | Path, *, role: str) -> dict[str, Any]:
    resolved = Path(path)
    values = _load_env_values(resolved)
    api_key = values.get(ENV_API_KEY) or ""
    api_secret = values.get(ENV_API_SECRET) or ""
    return {
        "path": str(resolved),
        "role": role,
        "file_present": resolved.exists(),
        "api_key_present": bool(api_key),
        "api_secret_present": bool(api_secret),
        "api_key_length": len(api_key) if api_key else 0,
        "api_secret_length": len(api_secret) if api_secret else 0,
        "api_key_hash_preview": _hash_preview(api_key),
        "api_secret_hash_preview": _hash_preview(api_secret),
        "legacy_variable_names_present": [name for name in (ENV_API_KEY, ENV_API_SECRET) if values.get(name)],
        "full_api_key_shown": False,
        "full_api_secret_shown": False,
        "secrets_shown": False,
    }


def _load_env_values(path: Path) -> dict[str, str]:
    if not path.exists() or not path.is_file():
        return {}
    values: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in {ENV_API_KEY, ENV_API_SECRET}:
                values[key] = value
    return values


def _hash_preview(value: str) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _legacy_ambiguity_detected(roles: Mapping[str, Mapping[str, Any]]) -> bool:
    present_roles = [
        name
        for name, summary in roles.items()
        if isinstance(summary, Mapping) and (summary.get("api_key_present") or summary.get("api_secret_present"))
    ]
    return len(present_roles) > 1


def _recommended_next_operator_move(
    *,
    record_proposal: bool,
    confirmation_valid: bool,
    blockers: list[str],
) -> str:
    if record_proposal and not confirmation_valid:
        return "KEEP_CURRENT_ENV_UNCHANGED"
    if blockers:
        return "REVIEW_ENV_ROLE_SPLIT"
    return "RUN_R170_ENV_ROLE_ADAPTER_PREVIEW"


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


def _empty_current_env_inventory() -> dict[str, Any]:
    empty = {
        "path": None,
        "role": "unknown",
        "file_present": False,
        "api_key_present": False,
        "api_secret_present": False,
        "api_key_length": 0,
        "api_secret_length": 0,
        "api_key_hash_preview": None,
        "api_secret_hash_preview": None,
        "legacy_variable_names_present": [],
        "full_api_key_shown": False,
        "full_api_secret_shown": False,
        "secrets_shown": False,
    }
    return {
        "repo_env": dict(empty),
        "binance_readonly_env": dict(empty),
        "binance_live_env": dict(empty),
        "mismatched_pair_detected": False,
        "mismatch_evidence": [],
        "comparison_method": "sha256_preview_and_value_length_only",
        "current_ambiguity_detected": False,
        "secrets_shown": False,
    }


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
