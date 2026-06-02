"""R174 funding gate sync after role-specific account-read verification.

This module is audit/sync only. It consumes local R173 account-read migration
verification records and R164/R167 read-only balance records, then optionally
appends a funding-gate sync record after an exact recording-only confirmation.
It never calls Binance, writes env/config, creates payloads, changes lane
modes, or authorizes live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.account_read_env_migration_verify import (
    LEDGER_FILENAME as ACCOUNT_READ_VERIFY_LEDGER_FILENAME,
    load_account_read_env_migration_verify_records,
)
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.env_role_adapter import (
    SELECTED_LEGACY_FALLBACK,
    SELECTED_MISSING,
    SELECTED_ROLE_SPECIFIC,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.funding_readonly_precheck import DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.readonly_balance_check import (
    ACCOUNT_FUNDED_BELOW_MINIMUM,
    ACCOUNT_FUNDED_READY_FOR_REVIEW,
    ACCOUNT_NOT_FUNDED,
    LEDGER_FILENAME as READONLY_BALANCE_LEDGER_FILENAME,
    load_readonly_balance_check_records,
)
from src.app.hammer_radar.operator.short_evidence_recheck_packet import (
    LEDGER_FILENAME as SHORT_EVIDENCE_RECHECK_LEDGER_FILENAME,
    PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW,
)
from src.app.hammer_radar.operator.short_risk_contract_apply_review import (
    LEDGER_FILENAME as SHORT_RISK_CONTRACT_APPLY_REVIEW_LEDGER_FILENAME,
)
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY, build_short_strategy_target_family

FUNDING_GATE_ROLE_SPECIFIC_SYNC_READY = "FUNDING_GATE_ROLE_SPECIFIC_SYNC_READY"
FUNDING_GATE_ROLE_SPECIFIC_SYNC_REJECTED = "FUNDING_GATE_ROLE_SPECIFIC_SYNC_REJECTED"
FUNDING_GATE_ROLE_SPECIFIC_SYNC_RECORDED = "FUNDING_GATE_ROLE_SPECIFIC_SYNC_RECORDED"
FUNDING_GATE_ROLE_SPECIFIC_SYNC_BLOCKED = "FUNDING_GATE_ROLE_SPECIFIC_SYNC_BLOCKED"
FUNDING_GATE_ROLE_SPECIFIC_SYNC_ERROR = "FUNDING_GATE_ROLE_SPECIFIC_SYNC_ERROR"

FUNDING_SYNC_ACCOUNT_NOT_FUNDED = "FUNDING_SYNC_ACCOUNT_NOT_FUNDED"
FUNDING_SYNC_BELOW_MINIMUM = "FUNDING_SYNC_BELOW_MINIMUM"
FUNDING_SYNC_READY_FOR_REVIEW = "FUNDING_SYNC_READY_FOR_REVIEW"
FUNDING_SYNC_NO_BALANCE_RECORD = "FUNDING_SYNC_NO_BALANCE_RECORD"
FUNDING_SYNC_ACCOUNT_READ_ROLE_NOT_VERIFIED = "FUNDING_SYNC_ACCOUNT_READ_ROLE_NOT_VERIFIED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

FUND_ACCOUNT_LATER = "FUND_ACCOUNT_LATER"
KEEP_R157_RUNNING = "KEEP_R157_RUNNING"
RUN_R158_AFTER_MORE_CAPTURES = "RUN_R158_AFTER_MORE_CAPTURES"
RUN_R175_TINY_LIVE_BLOCKER_BURN_DOWN = "RUN_R175_TINY_LIVE_BLOCKER_BURN_DOWN"

EVENT_TYPE = "FUNDING_GATE_ROLE_SPECIFIC_SYNC"
LEDGER_FILENAME = "funding_gate_role_specific_sync.ndjson"
CONFIRM_FUNDING_ROLE_SPECIFIC_SYNC_RECORDING_PHRASE = (
    "I CONFIRM FUNDING GATE ROLE-SPECIFIC SYNC RECORDING ONLY; NO ENV WRITE; NO ORDER; NO BINANCE CALL."
)

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
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
    "src/app/hammer_radar/operator/account_read_env_migration_verify.py",
    "src/app/hammer_radar/operator/readonly_balance_check.py",
    "src/app/hammer_radar/operator/funding_readonly_precheck.py",
    "src/app/hammer_radar/operator/funding_gate_key_role_sync.py",
    "src/app/hammer_radar/operator/short_evidence_recheck_packet.py",
    "src/app/hammer_radar/operator/short_risk_contract_apply_review.py",
    "src/app/hammer_radar/operator/short_strategy_packet.py",
    f"logs/hammer_radar_forward/{ACCOUNT_READ_VERIFY_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{READONLY_BALANCE_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_EVIDENCE_RECHECK_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_RISK_CONTRACT_APPLY_REVIEW_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_funding_gate_role_specific_sync(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    minimum_balance_usdt: float = DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT,
    record_sync: bool = False,
    confirm_funding_role_specific_sync: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_funding_role_specific_sync == CONFIRM_FUNDING_ROLE_SPECIFIC_SYNC_RECORDING_PHRASE
    try:
        target = build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)
        latest_verify = load_latest_account_read_migration_verify(log_dir=resolved_log_dir)
        latest_balance = load_latest_readonly_balance_record(
            log_dir=resolved_log_dir,
            minimum_balance_usdt=minimum_balance_usdt,
        )
        account_read_role_state = build_account_read_role_state(latest_verify=latest_verify)
        latest_balance_state = build_latest_balance_state(
            latest_balance=latest_balance,
            minimum_balance_usdt=minimum_balance_usdt,
        )
        funding_gate = build_funding_gate_state(
            account_read_role_state=account_read_role_state,
            latest_balance_state=latest_balance_state,
        )
        tiny_live_blockers = build_tiny_live_blocker_summary(
            log_dir=resolved_log_dir,
            target_family=target,
            funding_gate=funding_gate,
        )
        next_actions = build_next_readiness_actions(
            funding_gate=funding_gate,
            tiny_live_blocker_summary=tiny_live_blockers,
        )
        blockers = _build_blockers(
            target_family=target,
            account_read_role_state=account_read_role_state,
            latest_balance_state=latest_balance_state,
        )
        status = FUNDING_GATE_ROLE_SPECIFIC_SYNC_READY if not blockers else FUNDING_GATE_ROLE_SPECIFIC_SYNC_BLOCKED
        if record_sync and not confirmation_valid:
            status = FUNDING_GATE_ROLE_SPECIFIC_SYNC_REJECTED
        elif record_sync and confirmation_valid:
            status = FUNDING_GATE_ROLE_SPECIFIC_SYNC_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "sync_recorded": False,
            "sync_id": None,
            "record_sync_requested": bool(record_sync),
            "confirmation_valid": bool(confirmation_valid),
            "target_family": target,
            "account_read_role_state": account_read_role_state,
            "latest_balance_state": latest_balance_state,
            "funding_gate": funding_gate,
            "tiny_live_blocker_summary": tiny_live_blockers,
            "recommended_next_operator_move": next_actions["recommended_next_operator_move"],
            "recommended_next_engineering_move": next_actions["recommended_next_engineering_move"],
            "do_not_run_yet": _do_not_run_yet(),
            "blockers": blockers,
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_sync and confirmation_valid:
            record = append_funding_gate_role_specific_sync_record(payload, log_dir=resolved_log_dir)
            payload["sync_recorded"] = True
            payload["sync_id"] = record["sync_id"]
            payload["ledger_path"] = str(funding_gate_role_specific_sync_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": FUNDING_GATE_ROLE_SPECIFIC_SYNC_ERROR,
                "generated_at": generated_at.isoformat(),
                "sync_recorded": False,
                "sync_id": None,
                "record_sync_requested": bool(record_sync),
                "confirmation_valid": bool(confirmation_valid),
                "target_family": _target_from_key(lane_key),
                "account_read_role_state": _empty_account_read_role_state(),
                "latest_balance_state": _empty_latest_balance_state(minimum_balance_usdt=minimum_balance_usdt),
                "funding_gate": _empty_funding_gate(),
                "tiny_live_blocker_summary": _empty_tiny_live_blocker_summary(),
                "recommended_next_operator_move": KEEP_R157_RUNNING,
                "recommended_next_engineering_move": "Fix R174 sync builder error before any funding or tiny-live review.",
                "do_not_run_yet": _do_not_run_yet(),
                "blockers": ["R174 funding gate role-specific sync build error must be fixed before recording"],
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_account_read_migration_verify(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_account_read_env_migration_verify_records(log_dir=log_dir, limit=1)
    if not records:
        return {"record_found": False, "source_ledger": ACCOUNT_READ_VERIFY_LEDGER_FILENAME}
    latest = dict(records[0])
    latest["record_found"] = True
    latest["source_ledger"] = ACCOUNT_READ_VERIFY_LEDGER_FILENAME
    return _sanitize(latest)


def load_latest_readonly_balance_record(
    *,
    log_dir: str | Path | None = None,
    minimum_balance_usdt: float = DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT,
) -> dict[str, Any]:
    records = load_readonly_balance_check_records(log_dir=log_dir, limit=1)
    if not records:
        return _empty_latest_balance_state(minimum_balance_usdt=minimum_balance_usdt)
    latest = dict(records[0])
    latest["record_found"] = True
    latest["source_ledger"] = READONLY_BALANCE_LEDGER_FILENAME
    return _sanitize(latest)


def build_account_read_role_state(*, latest_verify: Mapping[str, Any]) -> dict[str, Any]:
    if latest_verify.get("record_found") is not True:
        return _empty_account_read_role_state()
    role = dict(latest_verify.get("account_read_role_verification") or {})
    runtime = dict(latest_verify.get("runtime_safety_verification") or {})
    future_live = dict(latest_verify.get("future_live_isolation") or {})
    selected = str(role.get("selected_pair_source") or SELECTED_MISSING)
    return {
        "selected_pair_source": selected,
        "role_specific_pair_present": bool(role.get("role_specific_pair_present")),
        "legacy_fallback_used": bool(role.get("legacy_fallback_used")),
        "runtime_safety_passed": bool(runtime.get("passed")),
        "future_live_disabled": bool(future_live.get("future_live_disabled")) and bool(future_live.get("passed", True)),
        "secrets_shown": False,
    }


def build_latest_balance_state(
    *,
    latest_balance: Mapping[str, Any],
    minimum_balance_usdt: float = DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT,
) -> dict[str, Any]:
    if latest_balance.get("record_found") is not True:
        return _empty_latest_balance_state(minimum_balance_usdt=minimum_balance_usdt)
    balance = dict(latest_balance.get("balance_check") or {})
    readiness = str(latest_balance.get("balance_readiness") or balance.get("funding_status") or "UNKNOWN")
    if readiness not in {ACCOUNT_NOT_FUNDED, ACCOUNT_FUNDED_BELOW_MINIMUM, ACCOUNT_FUNDED_READY_FOR_REVIEW}:
        readiness = "UNKNOWN"
    return {
        "record_found": True,
        "balance_readiness": readiness,
        "available_balance_usdt": _float_or_none(balance.get("available_balance_usdt")),
        "wallet_balance_usdt": _float_or_none(balance.get("wallet_balance_usdt")),
        "minimum_balance_required_estimate_usdt": _minimum_value(minimum_balance_usdt),
        "funding_ready": readiness == ACCOUNT_FUNDED_READY_FOR_REVIEW and bool(balance.get("funding_ready")),
        "source_ledger": READONLY_BALANCE_LEDGER_FILENAME,
    }


def build_funding_gate_state(
    *,
    account_read_role_state: Mapping[str, Any],
    latest_balance_state: Mapping[str, Any],
) -> dict[str, Any]:
    role_verified = _role_verified(account_read_role_state)
    if not role_verified:
        return {
            "funding_sync_status": FUNDING_SYNC_ACCOUNT_READ_ROLE_NOT_VERIFIED,
            "funding_ready": False,
            "funding_blocker": "role_not_verified",
            "safe_to_arm_live": False,
        }
    if latest_balance_state.get("record_found") is not True:
        return {
            "funding_sync_status": FUNDING_SYNC_NO_BALANCE_RECORD,
            "funding_ready": False,
            "funding_blocker": "missing_balance_record",
            "safe_to_arm_live": False,
        }
    readiness = latest_balance_state.get("balance_readiness")
    if readiness == ACCOUNT_NOT_FUNDED:
        return {
            "funding_sync_status": FUNDING_SYNC_ACCOUNT_NOT_FUNDED,
            "funding_ready": False,
            "funding_blocker": "account_not_funded",
            "safe_to_arm_live": False,
        }
    if readiness == ACCOUNT_FUNDED_BELOW_MINIMUM:
        return {
            "funding_sync_status": FUNDING_SYNC_BELOW_MINIMUM,
            "funding_ready": False,
            "funding_blocker": "below_minimum",
            "safe_to_arm_live": False,
        }
    if readiness == ACCOUNT_FUNDED_READY_FOR_REVIEW:
        return {
            "funding_sync_status": FUNDING_SYNC_READY_FOR_REVIEW,
            "funding_ready": bool(latest_balance_state.get("funding_ready")),
            "funding_blocker": None,
            "safe_to_arm_live": False,
        }
    return {
        "funding_sync_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
        "funding_ready": False,
        "funding_blocker": "missing_balance_record",
        "safe_to_arm_live": False,
    }


def build_tiny_live_blocker_summary(
    *,
    log_dir: str | Path | None = None,
    target_family: Mapping[str, Any],
    funding_gate: Mapping[str, Any],
) -> dict[str, bool]:
    return {
        "funding_blocked": funding_gate.get("funding_ready") is not True,
        "fresh_evidence_blocked": _fresh_evidence_blocked(log_dir=log_dir),
        "risk_contract_blocked": True,
        "lane_mode_blocked": target_family.get("current_mode") != "tiny_live",
        "operator_approval_blocked": True,
        "global_live_flags_blocked": True,
    }


def build_next_readiness_actions(
    *,
    funding_gate: Mapping[str, Any],
    tiny_live_blocker_summary: Mapping[str, Any],
) -> dict[str, str]:
    sync_status = funding_gate.get("funding_sync_status")
    if sync_status in {FUNDING_SYNC_ACCOUNT_READ_ROLE_NOT_VERIFIED, FUNDING_SYNC_NO_BALANCE_RECORD}:
        operator = KEEP_R157_RUNNING
    elif sync_status in {FUNDING_SYNC_ACCOUNT_NOT_FUNDED, FUNDING_SYNC_BELOW_MINIMUM}:
        operator = FUND_ACCOUNT_LATER
    elif tiny_live_blocker_summary.get("fresh_evidence_blocked") is True:
        operator = RUN_R158_AFTER_MORE_CAPTURES
    elif sync_status == FUNDING_SYNC_READY_FOR_REVIEW:
        operator = RUN_R175_TINY_LIVE_BLOCKER_BURN_DOWN
    else:
        operator = KEEP_R157_RUNNING
    return {
        "recommended_next_operator_move": operator,
        "recommended_next_engineering_move": _recommended_next_engineering_move(
            funding_gate=funding_gate,
            tiny_live_blocker_summary=tiny_live_blocker_summary,
        ),
    }


def append_funding_gate_role_specific_sync_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = funding_gate_role_specific_sync_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "sync_id": record.get("sync_id") or f"r174_funding_gate_role_specific_sync_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_sync_requested": bool(record.get("record_sync_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_family": dict(record.get("target_family") or {}),
            "account_read_role_state": dict(record.get("account_read_role_state") or {}),
            "latest_balance_state": dict(record.get("latest_balance_state") or {}),
            "funding_gate": dict(record.get("funding_gate") or {}),
            "tiny_live_blocker_summary": dict(record.get("tiny_live_blocker_summary") or {}),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "blockers": list(record.get("blockers") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_funding_gate_role_specific_sync_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = funding_gate_role_specific_sync_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_funding_gate_role_specific_syncs(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    funding_counts = Counter(
        str((record.get("funding_gate") or {}).get("funding_sync_status") or "UNKNOWN")
        for record in records
        if isinstance(record.get("funding_gate"), Mapping)
    )
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "funding_sync_status_counts": dict(sorted(funding_counts.items())),
        "last_sync_id": latest.get("sync_id"),
        "last_funding_sync_status": (latest.get("funding_gate") or {}).get("funding_sync_status")
        if isinstance(latest.get("funding_gate"), Mapping)
        else None,
        "safety": dict(SAFETY),
    }


def funding_gate_role_specific_sync_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_funding_gate_role_specific_sync_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _role_verified(account_read_role_state: Mapping[str, Any]) -> bool:
    return (
        account_read_role_state.get("selected_pair_source") == SELECTED_ROLE_SPECIFIC
        and account_read_role_state.get("role_specific_pair_present") is True
        and account_read_role_state.get("legacy_fallback_used") is False
        and account_read_role_state.get("runtime_safety_passed") is True
        and account_read_role_state.get("future_live_disabled") is True
    )


def _fresh_evidence_blocked(*, log_dir: str | Path | None = None) -> bool:
    path = Path(get_log_dir(log_dir, use_env=True)) / SHORT_EVIDENCE_RECHECK_LEDGER_FILENAME
    records = read_recent_ndjson_records(path, limit=1, max_bytes=32_000_000) if path.exists() else []
    if not records:
        return True
    latest = records[0]
    promotion = latest.get("promotion_readiness") or {}
    return promotion.get("readiness") != PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW


def _build_blockers(
    *,
    target_family: Mapping[str, Any],
    account_read_role_state: Mapping[str, Any],
    latest_balance_state: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if target_family.get("lane_key") != DEFAULT_TARGET_LANE_KEY:
        blockers.append("target family differs from BTCUSDT 8m short ladder_close_50_618")
    if target_family.get("current_mode") != "paper":
        blockers.append("target lane must remain paper for R174 sync")
    if not _role_verified(account_read_role_state):
        selected = account_read_role_state.get("selected_pair_source") or SELECTED_MISSING
        if selected == SELECTED_LEGACY_FALLBACK:
            blockers.append("latest R173 account-read verification used legacy fallback")
        elif selected == SELECTED_MISSING:
            blockers.append("no verified role-specific R173 account-read migration record found")
        else:
            blockers.append("latest R173 account-read verification is not role-specific/safe")
    if latest_balance_state.get("record_found") is not True:
        blockers.append("no latest read-only balance record found")
    return _dedupe(blockers)


def _recommended_next_engineering_move(
    *,
    funding_gate: Mapping[str, Any],
    tiny_live_blocker_summary: Mapping[str, Any],
) -> str:
    sync_status = funding_gate.get("funding_sync_status")
    if sync_status == FUNDING_SYNC_ACCOUNT_READ_ROLE_NOT_VERIFIED:
        return "Rerun R173 after sourcing HAMMER_ACCOUNT_READ_* role-specific credentials; do not write env files."
    if sync_status == FUNDING_SYNC_NO_BALANCE_RECORD:
        return "Have the operator run the explicit read-only balance check; R174 must not call Binance by default."
    if sync_status == FUNDING_SYNC_ACCOUNT_NOT_FUNDED:
        return "Keep tiny-live blocked; wait for funding, keep R157 paper capture running, then run R175 blocker burn-down."
    if sync_status == FUNDING_SYNC_BELOW_MINIMUM:
        return "Keep tiny-live blocked; funding is below the 44 USDT estimate and needs operator review after funding."
    if tiny_live_blocker_summary.get("fresh_evidence_blocked") is True:
        return "Run R158 after more fresh captures before any R175 tiny-live blocker burn-down review."
    return "Run R175 tiny-live blocker burn-down; do not arm live flags, lane mode, or risk-contract config."


def _do_not_run_yet() -> list[str]:
    return [
        "write env files",
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set short lane tiny_live",
        "write risk contract config",
        "transfer",
        "withdraw",
    ]


def _empty_account_read_role_state() -> dict[str, Any]:
    return {
        "selected_pair_source": SELECTED_MISSING,
        "role_specific_pair_present": False,
        "legacy_fallback_used": False,
        "runtime_safety_passed": False,
        "future_live_disabled": False,
        "secrets_shown": False,
    }


def _empty_latest_balance_state(*, minimum_balance_usdt: float) -> dict[str, Any]:
    return {
        "record_found": False,
        "balance_readiness": "UNKNOWN",
        "available_balance_usdt": None,
        "wallet_balance_usdt": None,
        "minimum_balance_required_estimate_usdt": _minimum_value(minimum_balance_usdt),
        "funding_ready": False,
        "source_ledger": READONLY_BALANCE_LEDGER_FILENAME,
    }


def _empty_funding_gate() -> dict[str, Any]:
    return {
        "funding_sync_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
        "funding_ready": False,
        "funding_blocker": "missing_balance_record",
        "safe_to_arm_live": False,
    }


def _empty_tiny_live_blocker_summary() -> dict[str, bool]:
    return {
        "funding_blocked": True,
        "fresh_evidence_blocked": True,
        "risk_contract_blocked": True,
        "lane_mode_blocked": True,
        "operator_approval_blocked": True,
        "global_live_flags_blocked": True,
    }


def _target_from_key(lane_key: str) -> dict[str, Any]:
    parts = str(lane_key or DEFAULT_TARGET_LANE_KEY).split("|")
    while len(parts) < 4:
        parts.append("")
    return {
        "lane_key": "|".join(parts[:4]),
        "symbol": parts[0] or "BTCUSDT",
        "timeframe": parts[1] or "8m",
        "direction": parts[2] or "short",
        "entry_mode": parts[3] or "ladder_close_50_618",
        "current_mode": "unknown",
    }


def _minimum_value(value: float) -> float | int:
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


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
