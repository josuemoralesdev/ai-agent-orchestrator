"""R172 account-read env manual migration packet.

This module is no-write operator guidance only. It fingerprints the known
account-capable env source with hash previews and lengths, emits manual shell
commands for the operator to run, and optionally records the packet to an
append-only ledger after an exact confirmation phrase. It never mutates env or
config files, calls Binance, signs requests, or creates order payloads.
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
from src.app.hammer_radar.operator.env_role_adapter import (
    ACCOUNT_READ_KEY_VAR,
    ACCOUNT_READ_SECRET_VAR,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.funding_gate_key_role_sync import DEFAULT_BINANCE_LIVE_ENV_PATH
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE

ACCOUNT_READ_ENV_MIGRATION_PACKET_READY = "ACCOUNT_READ_ENV_MIGRATION_PACKET_READY"
ACCOUNT_READ_ENV_MIGRATION_PACKET_REJECTED = "ACCOUNT_READ_ENV_MIGRATION_PACKET_REJECTED"
ACCOUNT_READ_ENV_MIGRATION_PACKET_RECORDED = "ACCOUNT_READ_ENV_MIGRATION_PACKET_RECORDED"
ACCOUNT_READ_ENV_MIGRATION_PACKET_BLOCKED = "ACCOUNT_READ_ENV_MIGRATION_PACKET_BLOCKED"
ACCOUNT_READ_ENV_MIGRATION_PACKET_ERROR = "ACCOUNT_READ_ENV_MIGRATION_PACKET_ERROR"

EVENT_TYPE = "ACCOUNT_READ_ENV_MIGRATION_PACKET"
LEDGER_FILENAME = "account_read_env_migration_packets.ndjson"
CONFIRM_ACCOUNT_READ_ENV_MIGRATION_PACKET_RECORDING_PHRASE = (
    "I CONFIRM ACCOUNT READ ENV MIGRATION PACKET RECORDING ONLY; NO ENV WRITE; NO ORDER; NO BINANCE CALL."
)

RUNTIME_SAFETY_FLAGS_REQUIRED = {
    ENV_CONNECTOR_MODE: "read_only",
    ENV_LIVE_TRADING_ENABLED: "false",
    ENV_BINANCE_LIVE_ENABLED: "false",
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
    "protective_order_endpoint_called": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "full_api_key_shown": False,
    "full_api_secret_shown": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
}

SOURCE_SURFACES_USED = [
    "docs/hammer_radar/live_readiness/R168_FUNDING_GATE_RECHECK_AND_KEY_ROLE_SYNC.md",
    "docs/hammer_radar/live_readiness/R169_ENV_ROLE_SPLIT_PROPOSAL_NO_WRITE.md",
    "docs/hammer_radar/live_readiness/R171_ENV_ROLE_ADAPTER_IMPLEMENTATION_NO_ENV_WRITE.md",
    "src/app/hammer_radar/operator/env_role_adapter.py",
    "src/app/hammer_radar/operator/env_role_adapter_preview.py",
    "src/app/hammer_radar/operator/env_role_split_proposal.py",
    "src/app/hammer_radar/operator/funding_gate_key_role_sync.py",
    "src/app/hammer_radar/operator/funding_readonly_precheck.py",
    "src/app/hammer_radar/operator/readonly_balance_check.py",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_account_read_env_migration_packet(
    *,
    log_dir: str | Path | None = None,
    record_packet: bool = False,
    confirm_account_read_env_migration: str | None = None,
    account_capable_source_file: str | Path = DEFAULT_BINANCE_LIVE_ENV_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_account_read_env_migration == CONFIRM_ACCOUNT_READ_ENV_MIGRATION_PACKET_RECORDING_PHRASE
    try:
        inventory = build_account_read_source_inventory(account_capable_source_file=account_capable_source_file)
        blockers = build_migration_blockers(account_read_source_inventory=inventory)
        status = ACCOUNT_READ_ENV_MIGRATION_PACKET_READY if not blockers else ACCOUNT_READ_ENV_MIGRATION_PACKET_BLOCKED
        if record_packet and not confirmation_valid:
            status = ACCOUNT_READ_ENV_MIGRATION_PACKET_REJECTED
        elif record_packet and confirmation_valid:
            status = ACCOUNT_READ_ENV_MIGRATION_PACKET_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "packet_recorded": False,
            "packet_id": None,
            "record_packet_requested": bool(record_packet),
            "confirmation_valid": bool(confirmation_valid),
            "account_read_source_inventory": inventory,
            "manual_migration_steps": build_manual_migration_steps(account_capable_source_file=account_capable_source_file),
            "manual_source_commands": build_manual_source_commands(account_capable_source_file=account_capable_source_file),
            "post_migration_verification_commands": build_post_migration_verification_commands(),
            "runtime_safety_flags_required": dict(RUNTIME_SAFETY_FLAGS_REQUIRED),
            "expected_after_manual_migration": {
                "account_read_selected_pair_source": "role_specific",
                "legacy_fallback_used": False,
                "future_live_still_disabled": True,
                "funding_status_expected_now": "ACCOUNT_NOT_FUNDED unless account is funded",
            },
            "blockers": blockers,
            "recommended_next_operator_move": _recommended_next_operator_move(
                record_packet=record_packet,
                confirmation_valid=confirmation_valid,
                blockers=blockers,
            ),
            "recommended_next_engineering_move": "Run R173 after the operator manually sources HAMMER_ACCOUNT_READ_* variables; keep env/config unchanged in Codex.",
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_packet and confirmation_valid:
            record = append_account_read_env_migration_packet_record(payload, log_dir=resolved_log_dir)
            payload["packet_recorded"] = True
            payload["packet_id"] = record["packet_id"]
            payload["ledger_path"] = str(account_read_env_migration_packet_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": ACCOUNT_READ_ENV_MIGRATION_PACKET_ERROR,
                "generated_at": generated_at.isoformat(),
                "packet_recorded": False,
                "packet_id": None,
                "record_packet_requested": bool(record_packet),
                "confirmation_valid": bool(confirmation_valid),
                "account_read_source_inventory": _empty_source_inventory(account_capable_source_file),
                "manual_migration_steps": build_manual_migration_steps(account_capable_source_file=account_capable_source_file),
                "manual_source_commands": build_manual_source_commands(account_capable_source_file=account_capable_source_file),
                "post_migration_verification_commands": build_post_migration_verification_commands(),
                "runtime_safety_flags_required": dict(RUNTIME_SAFETY_FLAGS_REQUIRED),
                "expected_after_manual_migration": {
                    "account_read_selected_pair_source": "role_specific",
                    "legacy_fallback_used": False,
                    "future_live_still_disabled": True,
                    "funding_status_expected_now": "ACCOUNT_NOT_FUNDED unless account is funded",
                },
                "blockers": ["R172 account-read env migration packet build error must be fixed before recording"],
                "recommended_next_operator_move": "REVIEW_MANUAL_ACCOUNT_READ_ENV_MIGRATION",
                "recommended_next_engineering_move": "Fix R172 packet builder error; do not write env/config or call Binance.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_account_read_source_inventory(
    *,
    account_capable_source_file: str | Path = DEFAULT_BINANCE_LIVE_ENV_PATH,
) -> dict[str, Any]:
    path = Path(account_capable_source_file)
    values = _load_env_values(path)
    api_key = values.get(ENV_API_KEY) or ""
    api_secret = values.get(ENV_API_SECRET) or ""
    return {
        "account_capable_source_file": str(path),
        "source_file_present": path.exists() and path.is_file(),
        "source_key_hash_preview": _hash_preview(api_key),
        "source_secret_hash_preview": _hash_preview(api_secret),
        "source_key_length": len(api_key) if api_key else 0,
        "source_secret_length": len(api_secret) if api_secret else 0,
        "secrets_shown": False,
    }


def build_manual_migration_steps(
    *,
    account_capable_source_file: str | Path = DEFAULT_BINANCE_LIVE_ENV_PATH,
) -> list[dict[str, Any]]:
    source = str(Path(account_capable_source_file))
    return [
        {
            "step": 1,
            "action": "Review the hash/length-only account-read source inventory.",
            "source_file": source,
            "writes_env_file": False,
            "calls_binance": False,
        },
        {
            "step": 2,
            "action": f"Manually source {source} into the current operator shell.",
            "writes_env_file": False,
            "prints_secrets": False,
        },
        {
            "step": 3,
            "action": f"Export {ACCOUNT_READ_KEY_VAR} and {ACCOUNT_READ_SECRET_VAR} from the sourced legacy pair in that shell only.",
            "legacy_env_unchanged": True,
            "writes_env_file": False,
        },
        {
            "step": 4,
            "action": "Force read-only runtime flags and keep all live/order flags disabled with the global kill switch enabled.",
            "runtime_safety_flags_required": dict(RUNTIME_SAFETY_FLAGS_REQUIRED),
        },
        {
            "step": 5,
            "action": "Run R173 verification after manual migration; use the explicit read-only network balance check only if the operator approves it.",
            "default_network_use": False,
        },
    ]


def build_manual_source_commands(
    *,
    account_capable_source_file: str | Path = DEFAULT_BINANCE_LIVE_ENV_PATH,
) -> list[str]:
    source = str(Path(account_capable_source_file))
    return [
        "set -a",
        f"source {source}",
        f'export {ACCOUNT_READ_KEY_VAR}="$BINANCE_API_KEY"',
        f'export {ACCOUNT_READ_SECRET_VAR}="$BINANCE_API_SECRET"',
        "export BINANCE_CONNECTOR_MODE=read_only",
        "export BINANCE_LIVE_TRADING_ENABLED=false",
        "export HAMMER_BINANCE_LIVE_ENABLED=false",
        "export HAMMER_LIVE_EXECUTION_ENABLED=false",
        "export HAMMER_ALLOW_LIVE_ORDERS=false",
        "export HAMMER_GLOBAL_KILL_SWITCH=true",
        "set +a",
    ]


def build_post_migration_verification_commands() -> list[str]:
    base = "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward"
    return [
        f"{base} env-role-adapter-preview",
        f"{base} funding-readonly-precheck",
        f"{base} readonly-balance-check",
        f"{base} readonly-balance-check --allow-readonly-network-check",
    ]


def build_migration_blockers(*, account_read_source_inventory: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if account_read_source_inventory.get("source_file_present") is not True:
        blockers.append("account-capable source file is missing")
    if not account_read_source_inventory.get("source_key_hash_preview"):
        blockers.append("account-capable source file does not contain BINANCE_API_KEY")
    if not account_read_source_inventory.get("source_secret_hash_preview"):
        blockers.append("account-capable source file does not contain BINANCE_API_SECRET")
    return blockers


def append_account_read_env_migration_packet_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = account_read_env_migration_packet_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "packet_id": record.get("packet_id") or f"r172_account_read_env_migration_packet_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_packet_requested": bool(record.get("record_packet_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "account_read_source_inventory": dict(record.get("account_read_source_inventory") or {}),
            "manual_migration_steps": list(record.get("manual_migration_steps") or []),
            "manual_source_commands": list(record.get("manual_source_commands") or []),
            "post_migration_verification_commands": list(record.get("post_migration_verification_commands") or []),
            "runtime_safety_flags_required": dict(record.get("runtime_safety_flags_required") or {}),
            "expected_after_manual_migration": dict(record.get("expected_after_manual_migration") or {}),
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


def load_account_read_env_migration_packet_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = account_read_env_migration_packet_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_account_read_env_migration_packets(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_packet_id": latest.get("packet_id"),
        "last_source_file": (latest.get("account_read_source_inventory") or {}).get("account_capable_source_file")
        if isinstance(latest.get("account_read_source_inventory"), Mapping)
        else None,
        "safety": dict(SAFETY),
    }


def account_read_env_migration_packet_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_account_read_env_migration_packet_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _recommended_next_operator_move(*, record_packet: bool, confirmation_valid: bool, blockers: list[str]) -> str:
    if record_packet and not confirmation_valid:
        return "REVIEW_MANUAL_ACCOUNT_READ_ENV_MIGRATION"
    if blockers:
        return "REVIEW_MANUAL_ACCOUNT_READ_ENV_MIGRATION"
    if record_packet and confirmation_valid:
        return "RUN_MANUAL_SOURCE_COMMANDS"
    return "REVIEW_MANUAL_ACCOUNT_READ_ENV_MIGRATION"


def _do_not_run_yet() -> list[str]:
    return [
        "write env files automatically",
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set short lane tiny_live",
        "transfer",
        "withdraw",
    ]


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


def _empty_source_inventory(account_capable_source_file: str | Path) -> dict[str, Any]:
    return {
        "account_capable_source_file": str(Path(account_capable_source_file)),
        "source_file_present": False,
        "source_key_hash_preview": None,
        "source_secret_hash_preview": None,
        "source_key_length": 0,
        "source_secret_length": 0,
        "secrets_shown": False,
    }


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return {str(key): _sanitize(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, tuple):
        return [_sanitize(item) for item in payload]
    return payload
