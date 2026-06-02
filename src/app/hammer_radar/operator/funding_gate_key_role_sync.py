"""R168 funding gate recheck and key role sync.

This module is diagnostic/audit only. It reads local env files for safe
fingerprints, consumes the R164 read-only balance ledger, and may append a
funding/key-role sync record after exact confirmation. It never calls Binance,
creates order payloads, mutates env/config, or enables live execution.
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
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.readonly_balance_check import (
    ACCOUNT_NOT_FUNDED,
    LEDGER_FILENAME as READONLY_BALANCE_LEDGER_FILENAME,
    load_readonly_balance_check_records,
)
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY, build_short_strategy_target_family

FUNDING_GATE_KEY_ROLE_SYNC_READY = "FUNDING_GATE_KEY_ROLE_SYNC_READY"
FUNDING_GATE_KEY_ROLE_SYNC_REJECTED = "FUNDING_GATE_KEY_ROLE_SYNC_REJECTED"
FUNDING_GATE_KEY_ROLE_SYNC_RECORDED = "FUNDING_GATE_KEY_ROLE_SYNC_RECORDED"
FUNDING_GATE_KEY_ROLE_SYNC_BLOCKED = "FUNDING_GATE_KEY_ROLE_SYNC_BLOCKED"
FUNDING_GATE_KEY_ROLE_SYNC_ERROR = "FUNDING_GATE_KEY_ROLE_SYNC_ERROR"

EVENT_TYPE = "FUNDING_GATE_KEY_ROLE_SYNC"
LEDGER_FILENAME = "funding_gate_key_role_sync.ndjson"
CONFIRM_FUNDING_KEY_ROLE_SYNC_RECORDING_PHRASE = (
    "I CONFIRM FUNDING GATE KEY ROLE SYNC RECORDING ONLY; NO ENV WRITE; NO ORDER; NO BINANCE TRADING CALL."
)

DEFAULT_REPO_ENV_PATH = ".env"
DEFAULT_BINANCE_READONLY_ENV_PATH = "/home/josue/.config/hammer-radar/binance-readonly.env"
DEFAULT_BINANCE_LIVE_ENV_PATH = "/home/josue/.config/hammer-radar/binance-live.env"

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "signed_request_created_scope": "none",
    "signed_trading_request_created": False,
    "signed_order_request_created": False,
    "signed_readonly_request_created": False,
    "network_allowed": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "signature_shown": False,
    "signed_url_shown": False,
    "env_mutated": False,
    "env_written": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_config_written": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{READONLY_BALANCE_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
    "repo .env fingerprint only",
    "binance-readonly.env fingerprint only",
    "binance-live.env fingerprint only",
    "operator.short_strategy_packet.build_short_strategy_target_family",
]


def build_funding_gate_key_role_sync(
    *,
    log_dir: str | Path | None = None,
    record_sync: bool = False,
    confirm_funding_key_role_sync: str | None = None,
    repo_env_path: str | Path = DEFAULT_REPO_ENV_PATH,
    readonly_env_path: str | Path = DEFAULT_BINANCE_READONLY_ENV_PATH,
    live_env_path: str | Path = DEFAULT_BINANCE_LIVE_ENV_PATH,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_funding_key_role_sync == CONFIRM_FUNDING_KEY_ROLE_SYNC_RECORDING_PHRASE
    try:
        target_family = build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)
        latest_balance_result = load_latest_readonly_balance_result(log_dir=resolved_log_dir)
        key_role_summary = build_key_role_hash_summary(
            repo_env_path=repo_env_path,
            readonly_env_path=readonly_env_path,
            live_env_path=live_env_path,
        )
        funding_gate = build_funding_gate_sync_summary(latest_balance_result=latest_balance_result)
        guidance = build_operator_env_role_guidance()
        blockers = _build_blockers(target_family=target_family, latest_balance_result=latest_balance_result)
        status = FUNDING_GATE_KEY_ROLE_SYNC_READY if not blockers else FUNDING_GATE_KEY_ROLE_SYNC_BLOCKED
        if record_sync and not confirmation_valid:
            status = FUNDING_GATE_KEY_ROLE_SYNC_REJECTED
        elif record_sync and confirmation_valid:
            status = FUNDING_GATE_KEY_ROLE_SYNC_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "sync_recorded": False,
            "sync_id": None,
            "record_sync_requested": bool(record_sync),
            "confirmation_valid": bool(confirmation_valid),
            "target_family": target_family,
            "latest_balance_result": latest_balance_result,
            "key_role_summary": key_role_summary,
            "funding_gate": funding_gate,
            "operator_env_role_guidance": guidance,
            "blockers": blockers,
            "safe_operator_commands": _safe_operator_commands(),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_sync and confirmation_valid:
            record = append_funding_gate_key_role_sync_record(payload, log_dir=resolved_log_dir)
            payload["sync_recorded"] = True
            payload["sync_id"] = record["sync_id"]
            payload["ledger_path"] = str(funding_gate_key_role_sync_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": FUNDING_GATE_KEY_ROLE_SYNC_ERROR,
                "generated_at": generated_at.isoformat(),
                "sync_recorded": False,
                "sync_id": None,
                "record_sync_requested": bool(record_sync),
                "confirmation_valid": bool(confirmation_valid),
                "target_family": _target_from_key(lane_key),
                "latest_balance_result": _empty_latest_balance_result(),
                "key_role_summary": _empty_key_role_summary(),
                "funding_gate": {"funding_ready": False, "funding_status": "UNKNOWN_NO_BALANCE_RECORD"},
                "operator_env_role_guidance": build_operator_env_role_guidance(),
                "blockers": ["R168 sync build error must be fixed before recording funding/key-role state"],
                "safe_operator_commands": _safe_operator_commands(),
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_key_role_hash_summary(
    *,
    repo_env_path: str | Path = DEFAULT_REPO_ENV_PATH,
    readonly_env_path: str | Path = DEFAULT_BINANCE_READONLY_ENV_PATH,
    live_env_path: str | Path = DEFAULT_BINANCE_LIVE_ENV_PATH,
) -> dict[str, Any]:
    roles = {
        "repo_env": _env_file_hash_summary(repo_env_path, role="repo_default_env"),
        "binance_readonly_env": _env_file_hash_summary(readonly_env_path, role="market_or_readonly_key"),
        "binance_live_env": _env_file_hash_summary(live_env_path, role="account_read_key_when_forced_read_only"),
    }
    mismatch = detect_key_secret_pair_mismatch(roles)
    return {
        **roles,
        "mismatched_pair_detected": bool(mismatch["mismatched_pair_detected"]),
        "mismatch_evidence": mismatch["mismatch_evidence"],
        "comparison_method": "sha256_preview_and_value_length_only",
        "secrets_shown": False,
    }


def detect_key_secret_pair_mismatch(hash_summaries: Mapping[str, Any]) -> dict[str, Any]:
    summaries = {
        str(name): dict(summary)
        for name, summary in hash_summaries.items()
        if isinstance(summary, Mapping)
    }
    key_matches = _matching_roles(summaries, "api_key_hash_preview", "api_key_length")
    secret_matches = _matching_roles(summaries, "api_secret_hash_preview", "api_secret_length")
    evidence: list[str] = []
    for role in summaries:
        key_peers = set(key_matches.get(role, []))
        secret_peers = set(secret_matches.get(role, []))
        if key_peers and secret_peers and key_peers != secret_peers:
            evidence.append(f"{role} API key matches {sorted(key_peers)} but secret matches {sorted(secret_peers)}")
        if key_peers and not secret_peers:
            evidence.append(f"{role} API key matches another env file but API secret does not")
        if secret_peers and not key_peers:
            evidence.append(f"{role} API secret matches another env file but API key does not")
    return {
        "mismatched_pair_detected": bool(evidence),
        "mismatch_evidence": _dedupe(evidence),
        "secrets_shown": False,
    }


def load_latest_readonly_balance_result(*, log_dir: str | Path | None = None, limit: int = 50) -> dict[str, Any]:
    records = load_readonly_balance_check_records(log_dir=log_dir, limit=limit)
    if not records:
        return _empty_latest_balance_result()
    latest = records[0]
    balance = dict(latest.get("balance_check") or {})
    funding_status = str(balance.get("funding_status") or latest.get("balance_readiness") or "UNKNOWN")
    return _sanitize(
        {
            "record_found": True,
            "source_ledger": READONLY_BALANCE_LEDGER_FILENAME,
            "balance_check_id": latest.get("balance_check_id"),
            "status": latest.get("status"),
            "recorded_at_utc": latest.get("recorded_at_utc"),
            "generated_at": latest.get("generated_at"),
            "balance_readiness": latest.get("balance_readiness") or funding_status,
            "funding_status": funding_status,
            "funding_ready": bool(balance.get("funding_ready")),
            "available_balance_usdt": _float_or_none(balance.get("available_balance_usdt")),
            "wallet_balance_usdt": _float_or_none(balance.get("wallet_balance_usdt")),
            "asset": balance.get("asset") or "USDT",
            "network_check_attempted": bool(balance.get("network_check_attempted")),
            "balance_check_attempted": bool(balance.get("balance_check_attempted")),
            "signed_readonly_request_created": bool(balance.get("signed_readonly_request_created")),
            "signed_trading_request_created": bool((latest.get("safety") or {}).get("signed_trading_request_created")),
            "secrets_shown": False,
        }
    )


def build_funding_gate_sync_summary(*, latest_balance_result: Mapping[str, Any]) -> dict[str, Any]:
    funding_status = str(latest_balance_result.get("funding_status") or latest_balance_result.get("balance_readiness") or "UNKNOWN")
    return {
        "funding_ready": funding_status != ACCOUNT_NOT_FUNDED and bool(latest_balance_result.get("funding_ready")),
        "funding_status": funding_status,
        "balance_readiness": latest_balance_result.get("balance_readiness") or funding_status,
        "account_not_funded_recorded": funding_status == ACCOUNT_NOT_FUNDED,
        "source_ledger": READONLY_BALANCE_LEDGER_FILENAME,
        "safe_to_arm_live": False,
    }


def build_operator_env_role_guidance() -> dict[str, Any]:
    return {
        "use_account_capable_key_only_for_balance_checks": True,
        "force_read_only_runtime_flags": {
            "BINANCE_CONNECTOR_MODE": "read_only",
            "BINANCE_LIVE_TRADING_ENABLED": "false",
            "HAMMER_LIVE_EXECUTION_ENABLED": "false",
            "HAMMER_ALLOW_LIVE_ORDERS": "false",
            "HAMMER_GLOBAL_KILL_SWITCH": "true",
        },
        "keep_live_flags_false": True,
        "do_not_edit_env_automatically": True,
        "do_not_mix_market_key_with_account_read_secret": True,
        "account_capable_key_role": "read-only Futures account balance checks only when runtime flags force read-only mode",
        "market_key_role": "market data/read-only status only; do not use for account-balance readiness if Binance rejects account reads",
        "secrets_shown": False,
    }


def append_funding_gate_key_role_sync_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = funding_gate_key_role_sync_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "sync_id": record.get("sync_id") or f"r168_funding_gate_key_role_sync_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_sync_requested": bool(record.get("record_sync_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_family": dict(record.get("target_family") or {}),
            "latest_balance_result": dict(record.get("latest_balance_result") or {}),
            "key_role_summary": dict(record.get("key_role_summary") or {}),
            "funding_gate": dict(record.get("funding_gate") or {}),
            "operator_env_role_guidance": dict(record.get("operator_env_role_guidance") or {}),
            "blockers": list(record.get("blockers") or []),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_funding_gate_key_role_sync_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = funding_gate_key_role_sync_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_funding_gate_key_role_sync_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_sync_id": latest.get("sync_id"),
        "last_funding_status": (latest.get("funding_gate") or {}).get("funding_status") if isinstance(latest.get("funding_gate"), Mapping) else None,
        "safety": dict(SAFETY),
    }


def funding_gate_key_role_sync_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_funding_gate_key_role_sync_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _env_file_hash_summary(path: str | Path, *, role: str) -> dict[str, Any]:
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


def _matching_roles(summaries: Mapping[str, Mapping[str, Any]], hash_key: str, length_key: str) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}
    items = list(summaries.items())
    for left_name, left in items:
        left_hash = left.get(hash_key)
        left_length = left.get(length_key)
        if not left_hash or not left_length:
            continue
        for right_name, right in items:
            if right_name == left_name:
                continue
            if left_hash == right.get(hash_key) and left_length == right.get(length_key):
                matches.setdefault(left_name, []).append(right_name)
    return {name: sorted(peers) for name, peers in matches.items()}


def _build_blockers(*, target_family: Mapping[str, Any], latest_balance_result: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if target_family.get("lane_key") != DEFAULT_TARGET_LANE_KEY:
        blockers.append("target family differs from BTCUSDT 8m short ladder_close_50_618")
    if latest_balance_result.get("record_found") is not True:
        blockers.append("no R164 read-only balance record found")
    if latest_balance_result.get("funding_status") != ACCOUNT_NOT_FUNDED:
        blockers.append(f"latest funding status is {latest_balance_result.get('funding_status') or 'UNKNOWN'}, expected ACCOUNT_NOT_FUNDED")
    return blockers


def _safe_operator_commands() -> list[str]:
    return [
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward funding-gate-key-role-sync"
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward funding-gate-key-role-sync --record-sync "
            f'--confirm-funding-key-role-sync "{CONFIRM_FUNDING_KEY_ROLE_SYNC_RECORDING_PHRASE}"'
        ),
    ]


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set short lane tiny_live",
        "write risk contract config",
        "transfer",
        "withdraw",
    ]


def _empty_latest_balance_result() -> dict[str, Any]:
    return {
        "record_found": False,
        "source_ledger": READONLY_BALANCE_LEDGER_FILENAME,
        "balance_check_id": None,
        "status": "MISSING",
        "recorded_at_utc": None,
        "generated_at": None,
        "balance_readiness": "UNKNOWN_NO_BALANCE_RECORD",
        "funding_status": "UNKNOWN_NO_BALANCE_RECORD",
        "funding_ready": False,
        "available_balance_usdt": None,
        "wallet_balance_usdt": None,
        "asset": "USDT",
        "network_check_attempted": False,
        "balance_check_attempted": False,
        "signed_readonly_request_created": False,
        "signed_trading_request_created": False,
        "secrets_shown": False,
    }


def _empty_key_role_summary() -> dict[str, Any]:
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
        "secrets_shown": False,
    }
    return {
        "repo_env": dict(empty),
        "binance_readonly_env": dict(empty),
        "binance_live_env": dict(empty),
        "mismatched_pair_detected": False,
        "mismatch_evidence": [],
        "comparison_method": "sha256_preview_and_value_length_only",
        "secrets_shown": False,
    }


def _target_from_key(lane_key: str) -> dict[str, Any]:
    parts = str(lane_key).split("|")
    return {
        "lane_key": lane_key,
        "symbol": parts[0] if len(parts) > 0 else "UNKNOWN",
        "timeframe": parts[1] if len(parts) > 1 else "unknown",
        "direction": parts[2] if len(parts) > 2 else "unknown",
        "entry_mode": parts[3] if len(parts) > 3 else "unknown",
        "current_mode": "unknown",
    }


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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
