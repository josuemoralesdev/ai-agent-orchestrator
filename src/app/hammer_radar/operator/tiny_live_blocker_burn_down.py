"""R175 tiny-live blocker burn-down for the BTCUSDT 8m short lane.

This module is audit-only. It composes existing local lane, evidence, funding,
and risk-contract surfaces into one compact blocker view. It never writes env
or config files, calls Binance, creates executable payloads, changes lane
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
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.funding_gate_role_specific_sync import (
    LEDGER_FILENAME as FUNDING_GATE_SYNC_LEDGER_FILENAME,
    load_funding_gate_role_specific_sync_records,
)
from src.app.hammer_radar.operator.funding_readonly_precheck import DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT
from src.app.hammer_radar.operator.fundless_short_tiny_live_readiness_rehearsal import RISK_CONTRACT_CONFIG_PATH
from src.app.hammer_radar.operator.lane_control import DEFAULT_CONFIG_PATH, SAFETY_FALSE
from src.app.hammer_radar.operator.readonly_balance_check import (
    ACCOUNT_FUNDED_READY_FOR_REVIEW,
    ACCOUNT_NOT_FUNDED,
    LEDGER_FILENAME as READONLY_BALANCE_LEDGER_FILENAME,
    load_readonly_balance_check_records,
)
from src.app.hammer_radar.operator.short_evidence_recheck_packet import (
    DEFAULT_LATEST_CAPTURES,
    PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW,
    summarize_short_fresh_evidence,
)
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import (
    LEDGER_FILENAME as SHORT_PAPER_CAPTURE_LEDGER_FILENAME,
    load_short_paper_evidence_capture_records,
)
from src.app.hammer_radar.operator.short_risk_contract_apply_review import (
    LEDGER_FILENAME as SHORT_RISK_CONTRACT_APPLY_REVIEW_LEDGER_FILENAME,
    load_short_risk_contract_apply_review_records,
)
from src.app.hammer_radar.operator.short_risk_contract_draft_preview import (
    LEDGER_FILENAME as SHORT_RISK_CONTRACT_DRAFT_LEDGER_FILENAME,
    TARGET_CANDIDATE_ID,
    build_existing_contract_summary,
    load_existing_tiny_live_risk_contracts,
)
from src.app.hammer_radar.operator.short_strategy_packet import (
    DEFAULT_TARGET_LANE_KEY,
    MIN_FRESH_CANDIDATES,
    build_short_strategy_target_family,
)

TINY_LIVE_BLOCKER_BURN_DOWN_READY = "TINY_LIVE_BLOCKER_BURN_DOWN_READY"
TINY_LIVE_BLOCKER_BURN_DOWN_REJECTED = "TINY_LIVE_BLOCKER_BURN_DOWN_REJECTED"
TINY_LIVE_BLOCKER_BURN_DOWN_RECORDED = "TINY_LIVE_BLOCKER_BURN_DOWN_RECORDED"
TINY_LIVE_BLOCKER_BURN_DOWN_BLOCKED = "TINY_LIVE_BLOCKER_BURN_DOWN_BLOCKED"
TINY_LIVE_BLOCKER_BURN_DOWN_ERROR = "TINY_LIVE_BLOCKER_BURN_DOWN_ERROR"

NOT_CLOSE_MULTIPLE_HARD_BLOCKERS = "NOT_CLOSE_MULTIPLE_HARD_BLOCKERS"
STRUCTURALLY_CLOSE_BUT_NEEDS_FUNDING_AND_EVIDENCE = "STRUCTURALLY_CLOSE_BUT_NEEDS_FUNDING_AND_EVIDENCE"
CLOSE_AFTER_FUNDING_AND_EVIDENCE = "CLOSE_AFTER_FUNDING_AND_EVIDENCE"
READY_FOR_OPERATOR_REVIEW_PACKET = "READY_FOR_OPERATOR_REVIEW_PACKET"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

KEEP_R157_RUNNING = "KEEP_R157_RUNNING"
FUND_ACCOUNT_LATER = "FUND_ACCOUNT_LATER"
RUN_R176_CAPTURE_COUNT_SYNC = "RUN_R176_CAPTURE_COUNT_SYNC"
WAIT_FOR_MORE_EVIDENCE = "WAIT_FOR_MORE_EVIDENCE"

EVENT_TYPE = "TINY_LIVE_BLOCKER_BURN_DOWN"
LEDGER_FILENAME = "tiny_live_blocker_burn_downs.ndjson"
CONFIRM_TINY_LIVE_BURN_DOWN_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE BLOCKER BURN DOWN RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_config_written": False,
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
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "src/app/hammer_radar/operator/funding_gate_role_specific_sync.py",
    "src/app/hammer_radar/operator/account_read_env_migration_verify.py",
    "src/app/hammer_radar/operator/account_read_env_migration_packet.py",
    "src/app/hammer_radar/operator/env_role_adapter.py",
    "src/app/hammer_radar/operator/readonly_balance_check.py",
    "src/app/hammer_radar/operator/short_evidence_recheck_packet.py",
    "src/app/hammer_radar/operator/short_paper_evidence_capture_loop.py",
    "src/app/hammer_radar/operator/short_strategy_packet.py",
    "src/app/hammer_radar/operator/fundless_short_dry_run_packet.py",
    "src/app/hammer_radar/operator/short_risk_contract_draft_preview.py",
    "src/app/hammer_radar/operator/short_risk_contract_apply_review.py",
    "src/app/hammer_radar/operator/lane_control.py",
    "src/app/hammer_radar/operator/inspect.py",
    f"logs/hammer_radar_forward/{SHORT_PAPER_CAPTURE_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{READONLY_BALANCE_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{ACCOUNT_READ_VERIFY_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{FUNDING_GATE_SYNC_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_RISK_CONTRACT_DRAFT_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_RISK_CONTRACT_APPLY_REVIEW_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_blocker_burn_down(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    record_burn_down: bool = False,
    confirm_tiny_live_burn_down: str | None = None,
    config_path: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_tiny_live_burn_down == CONFIRM_TINY_LIVE_BURN_DOWN_RECORDING_PHRASE
    try:
        target = build_target_lane_status_summary(lane_key=lane_key, config_path=config_path)
        funding = build_funding_blocker_summary(log_dir=resolved_log_dir)
        fresh_evidence = build_evidence_blocker_summary(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            latest_captures=latest_captures,
        )
        risk_contract = build_risk_contract_blocker_summary(
            log_dir=resolved_log_dir,
            target_family=target,
            risk_contract_config_path=risk_contract_config_path,
        )
        lane_mode = build_lane_mode_blocker_summary(target_family=target)
        protective_policy = build_protective_policy_blocker_summary(target_family=target)
        operator_approval = build_operator_approval_blocker_summary()
        live_flags = build_live_flag_blocker_summary()
        blockers = {
            "funding": funding,
            "fresh_evidence": fresh_evidence,
            "risk_contract": risk_contract,
            "lane_mode": lane_mode,
            "protective_policy": protective_policy,
            "operator_approval": operator_approval,
            "live_flags": live_flags,
        }
        distance = classify_tiny_live_distance(blockers=blockers)
        shortest_path = build_shortest_safe_path_summary(blockers=blockers)
        status = TINY_LIVE_BLOCKER_BURN_DOWN_READY
        if any(summary.get("status") == "blocked" for summary in blockers.values()):
            status = TINY_LIVE_BLOCKER_BURN_DOWN_BLOCKED
        if record_burn_down and not confirmation_valid:
            status = TINY_LIVE_BLOCKER_BURN_DOWN_REJECTED
        elif record_burn_down and confirmation_valid:
            status = TINY_LIVE_BLOCKER_BURN_DOWN_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "burn_down_recorded": False,
            "burn_down_id": None,
            "record_burn_down_requested": bool(record_burn_down),
            "confirmation_valid": bool(confirmation_valid),
            "target_family": target,
            "blockers": blockers,
            "cleared_items": _cleared_items(
                target_family=target,
                funding=funding,
                fresh_evidence=fresh_evidence,
                risk_contract=risk_contract,
            ),
            "tiny_live_distance": distance,
            "shortest_safe_path": shortest_path,
            "estimated_phase_distance": {
                "if_funding_and_captures_ready": "2-4 phases",
                "if_captures_missing": "depends on market, keep watcher running",
                "if_funding_missing": "blocked until funded",
            },
            "recommended_next_operator_move": _recommended_next_operator_move(
                funding=funding,
                fresh_evidence=fresh_evidence,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(
                funding=funding,
                fresh_evidence=fresh_evidence,
                risk_contract=risk_contract,
            ),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_burn_down and confirmation_valid:
            record = append_tiny_live_blocker_burn_down_record(payload, log_dir=resolved_log_dir)
            payload["burn_down_recorded"] = True
            payload["burn_down_id"] = record["burn_down_id"]
            payload["ledger_path"] = str(tiny_live_blocker_burn_down_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": TINY_LIVE_BLOCKER_BURN_DOWN_ERROR,
                "generated_at": generated_at.isoformat(),
                "burn_down_recorded": False,
                "burn_down_id": None,
                "record_burn_down_requested": bool(record_burn_down),
                "confirmation_valid": bool(confirmation_valid),
                "target_family": _target_from_key(lane_key),
                "blockers": _unknown_blockers(),
                "cleared_items": ["candidate door identified"],
                "tiny_live_distance": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "shortest_safe_path": build_shortest_safe_path_summary(blockers={}),
                "estimated_phase_distance": {
                    "if_funding_and_captures_ready": "2-4 phases",
                    "if_captures_missing": "depends on market, keep watcher running",
                    "if_funding_missing": "blocked until funded",
                },
                "recommended_next_operator_move": KEEP_R157_RUNNING,
                "recommended_next_engineering_move": "Fix R175 burn-down builder error before any future tiny-live review.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_target_lane_status_summary(
    *,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    target = build_short_strategy_target_family(lane_key=lane_key, config_path=config_path or DEFAULT_CONFIG_PATH)
    return {
        "lane_key": target.get("lane_key") or lane_key,
        "symbol": target.get("symbol") or _target_from_key(lane_key)["symbol"],
        "timeframe": target.get("timeframe") or _target_from_key(lane_key)["timeframe"],
        "direction": target.get("direction") or _target_from_key(lane_key)["direction"],
        "entry_mode": target.get("entry_mode") or _target_from_key(lane_key)["entry_mode"],
        "current_mode": target.get("current_mode") or "unknown",
    }


def build_evidence_blocker_summary(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
) -> dict[str, Any]:
    captures = [
        record
        for record in load_short_paper_evidence_capture_records(log_dir=log_dir, limit=max(1, int(latest_captures or 1)))
        if _record_lane_key(record) == lane_key
    ]
    fresh = summarize_short_fresh_evidence(captures, lane_key=lane_key)
    count = int(fresh.get("fresh_candidate_count") or 0)
    required = int(fresh.get("freshness_threshold_required") or MIN_FRESH_CANDIDATES)
    return {
        "status": "clear" if count >= required else "blocked",
        "current": f"{count} / {required} fresh captures",
        "required": ">= 10 fresh captures",
        "blocker_type": "market/evidence",
        "fresh_capture_count": count,
        "required_fresh_capture_count": required,
        "freshness_threshold_met": count >= required,
        "latest_captured_signal_id": fresh.get("latest_captured_signal_id"),
        "source_ledger": SHORT_PAPER_CAPTURE_LEDGER_FILENAME,
    }


def build_funding_blocker_summary(
    *,
    log_dir: str | Path | None = None,
    minimum_balance_usdt: float = DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT,
) -> dict[str, Any]:
    latest_sync = _latest_funding_sync(log_dir=log_dir)
    latest_balance = _latest_balance(log_dir=log_dir)
    balance_state = dict(latest_sync.get("latest_balance_state") or {})
    if not balance_state and latest_balance:
        balance_state = {
            "balance_readiness": latest_balance.get("balance_readiness") or (latest_balance.get("balance_check") or {}).get("funding_status"),
            "available_balance_usdt": (latest_balance.get("balance_check") or {}).get("available_balance_usdt"),
            "wallet_balance_usdt": (latest_balance.get("balance_check") or {}).get("wallet_balance_usdt"),
            "minimum_balance_required_estimate_usdt": (latest_balance.get("balance_check") or {}).get(
                "minimum_balance_required_estimate_usdt",
                minimum_balance_usdt,
            ),
        }
    readiness = str(balance_state.get("balance_readiness") or "UNKNOWN")
    available = _float_or_none(balance_state.get("available_balance_usdt"))
    required = _float_or_none(balance_state.get("minimum_balance_required_estimate_usdt")) or float(minimum_balance_usdt)
    if readiness == ACCOUNT_NOT_FUNDED:
        status = "blocked"
        current = f"{ACCOUNT_NOT_FUNDED} / {available if available is not None else 0.0:.1f} USDT"
    elif readiness == ACCOUNT_FUNDED_READY_FOR_REVIEW or (available is not None and available >= required):
        status = "clear"
        current = f"{readiness} / {available:.1f} USDT"
    elif readiness == "UNKNOWN":
        status = "unknown"
        current = "UNKNOWN / no latest funding sync"
    else:
        status = "blocked"
        current = f"{readiness} / {available if available is not None else 0.0:.1f} USDT"
    return {
        "status": status,
        "current": current,
        "required": ">= 44 USDT estimate or future risk contract amount",
        "blocker_type": "operator/funding",
        "funding_readiness": readiness,
        "available_balance_usdt": available,
        "minimum_balance_required_estimate_usdt": required,
        "source_ledgers": [FUNDING_GATE_SYNC_LEDGER_FILENAME, READONLY_BALANCE_LEDGER_FILENAME],
    }


def build_risk_contract_blocker_summary(
    *,
    log_dir: str | Path | None = None,
    target_family: Mapping[str, Any] | None = None,
    risk_contract_config_path: str | Path | None = None,
) -> dict[str, Any]:
    target = dict(target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY))
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    existing = load_existing_tiny_live_risk_contracts(config_path=risk_path)
    existing_summary = build_existing_contract_summary(existing, target_family=target, config_path=risk_path)
    latest_reviews = load_short_risk_contract_apply_review_records(log_dir=log_dir, limit=1)
    latest_review = latest_reviews[0] if latest_reviews else {}
    target_exists = bool(existing_summary.get("target_contract_exists"))
    enabled = bool((latest_review.get("existing_contract_state") or {}).get("target_contract_enabled_for_preflight"))
    if target_exists and enabled:
        status = "clear"
        current = "target risk contract applied/enabled"
    else:
        status = "blocked"
        current = "draft preview only / not applied"
    return {
        "status": status,
        "current": current,
        "required": "target risk contract applied in future safe phase",
        "blocker_type": "engineering/operator approval",
        "target_contract_exists": target_exists,
        "target_candidate_id": TARGET_CANDIDATE_ID,
        "latest_apply_review_readiness": latest_review.get("readiness"),
        "source_ledgers": [SHORT_RISK_CONTRACT_DRAFT_LEDGER_FILENAME, SHORT_RISK_CONTRACT_APPLY_REVIEW_LEDGER_FILENAME],
    }


def build_lane_mode_blocker_summary(*, target_family: Mapping[str, Any] | None = None) -> dict[str, Any]:
    target = dict(target_family or _target_from_key(DEFAULT_TARGET_LANE_KEY))
    current_mode = str(target.get("current_mode") or "unknown")
    return {
        "status": "clear" if current_mode == "tiny_live" else ("blocked" if current_mode == "paper" else "unknown"),
        "current": current_mode,
        "required": "future tiny_live mode only after approval",
        "blocker_type": "operator approval/config",
    }


def build_protective_policy_blocker_summary(*, target_family: Mapping[str, Any] | None = None) -> dict[str, Any]:
    _ = target_family
    return {
        "status": "blocked",
        "current": "short-specific policy reviewed but not live-applied",
        "required": "short stop/TP protective policy final review",
        "blocker_type": "engineering/risk",
    }


def build_operator_approval_blocker_summary() -> dict[str, Any]:
    return {
        "status": "blocked",
        "current": "not provided",
        "required": "explicit future approval phrase",
        "blocker_type": "operator",
    }


def build_live_flag_blocker_summary() -> dict[str, Any]:
    return {
        "status": "blocked",
        "current": "disabled/kill-switch-on",
        "required": "future authorized arming phase",
        "blocker_type": "operator/safety",
    }


def build_shortest_safe_path_summary(*, blockers: Mapping[str, Any] | None = None) -> list[str]:
    _ = blockers
    return [
        "continue R157 until fresh captures >= 10",
        "fund account later",
        "rerun R158/R174 sync",
        "apply risk contract in future safe config phase",
        "build tiny-live review packet",
        "operator approval",
        "arming phase",
    ]


def classify_tiny_live_distance(*, blockers: Mapping[str, Any] | None = None) -> str:
    summaries = {key: dict(value or {}) for key, value in (blockers or {}).items()}
    if not summaries:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    blocked = {key for key, value in summaries.items() if value.get("status") == "blocked"}
    unknown = {key for key, value in summaries.items() if value.get("status") == "unknown"}
    if unknown:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if not blocked:
        return READY_FOR_OPERATOR_REVIEW_PACKET
    hard = {"funding", "fresh_evidence", "risk_contract", "lane_mode", "operator_approval", "live_flags"}
    if len(blocked & hard) >= 4:
        return NOT_CLOSE_MULTIPLE_HARD_BLOCKERS
    if blocked <= {"funding", "fresh_evidence"}:
        return STRUCTURALLY_CLOSE_BUT_NEEDS_FUNDING_AND_EVIDENCE
    if "funding" not in blocked and "fresh_evidence" not in blocked:
        return CLOSE_AFTER_FUNDING_AND_EVIDENCE
    return NOT_CLOSE_MULTIPLE_HARD_BLOCKERS


def append_tiny_live_blocker_burn_down_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_blocker_burn_down_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "burn_down_id": record.get("burn_down_id") or f"r175_tiny_live_blocker_burn_down_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_burn_down_requested": bool(record.get("record_burn_down_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_family": dict(record.get("target_family") or {}),
            "blockers": dict(record.get("blockers") or {}),
            "cleared_items": list(record.get("cleared_items") or []),
            "tiny_live_distance": record.get("tiny_live_distance"),
            "shortest_safe_path": list(record.get("shortest_safe_path") or []),
            "estimated_phase_distance": dict(record.get("estimated_phase_distance") or {}),
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


def load_tiny_live_blocker_burn_down_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_blocker_burn_down_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_tiny_live_blocker_burn_downs(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    distance_counts = Counter(str(record.get("tiny_live_distance") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "tiny_live_distance_counts": dict(sorted(distance_counts.items())),
        "last_burn_down_id": latest.get("burn_down_id"),
        "last_tiny_live_distance": latest.get("tiny_live_distance"),
        "last_target_lane": (latest.get("target_family") or {}).get("lane_key") if isinstance(latest.get("target_family"), Mapping) else None,
        "safety": dict(SAFETY),
    }


def tiny_live_blocker_burn_down_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_blocker_burn_down_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _latest_funding_sync(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_funding_gate_role_specific_sync_records(log_dir=log_dir, limit=1)
    return dict(records[0]) if records else {}


def _latest_balance(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_readonly_balance_check_records(log_dir=log_dir, limit=1)
    return dict(records[0]) if records else {}


def _cleared_items(
    *,
    target_family: Mapping[str, Any],
    funding: Mapping[str, Any],
    fresh_evidence: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
) -> list[str]:
    _ = (fresh_evidence, risk_contract)
    items = [
        "candidate door identified",
        "short strategy packet exists",
        "fresh capture loop exists",
        "account-read role-specific env verified",
        "read-only balance path works",
        "funding truth known",
    ]
    if target_family.get("current_mode") == "paper":
        items.append("target lane remains paper")
    if funding.get("funding_readiness") == ACCOUNT_NOT_FUNDED:
        items.append("funding blocker classified as ACCOUNT_NOT_FUNDED")
    return items


def _recommended_next_operator_move(*, funding: Mapping[str, Any], fresh_evidence: Mapping[str, Any]) -> str:
    if int(fresh_evidence.get("fresh_capture_count") or 0) < int(fresh_evidence.get("required_fresh_capture_count") or MIN_FRESH_CANDIDATES):
        return KEEP_R157_RUNNING
    if funding.get("status") == "blocked":
        return FUND_ACCOUNT_LATER
    if fresh_evidence.get("status") == "clear":
        return RUN_R176_CAPTURE_COUNT_SYNC
    return WAIT_FOR_MORE_EVIDENCE


def _recommended_next_engineering_move(
    *,
    funding: Mapping[str, Any],
    fresh_evidence: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
) -> str:
    if fresh_evidence.get("status") == "blocked":
        return "Build R176 capture-count sync after more R157 records; keep config and Binance untouched."
    if funding.get("status") == "blocked":
        return "After funding, rerun R174 funding sync and keep short lane paper."
    if risk_contract.get("status") == "blocked":
        return "Prepare a future safe risk-contract config-apply phase; do not apply in R175."
    return "Build a future tiny-live review packet; R175 remains audit-only."


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


def _unknown_blockers() -> dict[str, dict[str, str]]:
    return {
        "funding": {"status": "unknown", "current": "unknown", "required": ">= 44 USDT estimate or future risk contract amount", "blocker_type": "operator/funding"},
        "fresh_evidence": {"status": "unknown", "current": "unknown", "required": ">= 10 fresh captures", "blocker_type": "market/evidence"},
        "risk_contract": {"status": "unknown", "current": "unknown", "required": "target risk contract applied in future safe phase", "blocker_type": "engineering/operator approval"},
        "lane_mode": {"status": "unknown", "current": "unknown", "required": "future tiny_live mode only after approval", "blocker_type": "operator approval/config"},
        "protective_policy": {"status": "unknown", "current": "unknown", "required": "short stop/TP protective policy final review", "blocker_type": "engineering/risk"},
        "operator_approval": build_operator_approval_blocker_summary(),
        "live_flags": build_live_flag_blocker_summary(),
    }


def _record_lane_key(record: Mapping[str, Any]) -> str:
    target = record.get("target_lane") if isinstance(record.get("target_lane"), Mapping) else record.get("target_family")
    if isinstance(target, Mapping) and target.get("lane_key"):
        return str(target.get("lane_key"))
    return str(record.get("captured_lane_key") or "")


def _target_from_key(lane_key: str, *, mode: str = "unknown") -> dict[str, str]:
    parts = (lane_key or DEFAULT_TARGET_LANE_KEY).split("|")
    padded = [*parts, "", "", "", ""]
    return {
        "lane_key": lane_key or DEFAULT_TARGET_LANE_KEY,
        "symbol": padded[0].upper(),
        "timeframe": padded[1].lower(),
        "direction": padded[2].lower(),
        "entry_mode": padded[3].lower(),
        "current_mode": mode,
    }


def _float_or_none(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
