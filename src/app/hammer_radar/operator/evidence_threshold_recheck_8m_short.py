"""R177 evidence threshold recheck for BTCUSDT 8m short.

This module composes existing local audit surfaces only. It reads R157/R176
capture evidence, rechecks R158 short evidence, reads R174 funding context,
reviews R162 risk-contract context, and can append one local R177 record after
exact confirmation. It never mutates env/config, calls Binance, creates
payloads, changes lane mode, disables safety locks, or authorizes execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.capture_count_sync_8m_short import (
    DEFAULT_LATEST_CAPTURES,
    DEFAULT_LATEST_HEARTBEATS,
    DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    LEDGER_FILENAME as CAPTURE_COUNT_SYNC_LEDGER_FILENAME,
    build_watcher_heartbeat_status,
    count_unique_fresh_captures,
    load_capture_count_sync_records,
    load_short_capture_heartbeats,
    load_short_capture_records,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.funding_gate_role_specific_sync import (
    ACCOUNT_NOT_FUNDED,
    build_funding_gate_role_specific_sync,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_evidence_recheck_packet import (
    DEFAULT_LATEST_BETRAYAL_RECHECK,
    DEFAULT_LATEST_OUTCOMES,
    DEFAULT_LATEST_SIGNALS,
    LEDGER_FILENAME as SHORT_EVIDENCE_RECHECK_LEDGER_FILENAME,
    PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW,
    build_short_evidence_recheck_packet,
    load_short_evidence_recheck_records,
)
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import LEDGER_FILENAME as SHORT_CAPTURE_LEDGER_FILENAME
from src.app.hammer_radar.operator.short_risk_contract_apply_review import (
    LEDGER_FILENAME as SHORT_RISK_CONTRACT_APPLY_REVIEW_LEDGER_FILENAME,
    build_short_risk_contract_apply_review,
    load_short_risk_contract_apply_review_records,
)
from src.app.hammer_radar.operator.short_strategy_packet import (
    DEFAULT_TARGET_LANE_KEY,
    MIN_FRESH_CANDIDATES,
    build_short_strategy_target_family,
)

EVIDENCE_THRESHOLD_RECHECK_READY = "EVIDENCE_THRESHOLD_RECHECK_READY"
EVIDENCE_THRESHOLD_RECHECK_REJECTED = "EVIDENCE_THRESHOLD_RECHECK_REJECTED"
EVIDENCE_THRESHOLD_RECHECK_RECORDED = "EVIDENCE_THRESHOLD_RECHECK_RECORDED"
EVIDENCE_THRESHOLD_RECHECK_BLOCKED = "EVIDENCE_THRESHOLD_RECHECK_BLOCKED"
EVIDENCE_THRESHOLD_RECHECK_ERROR = "EVIDENCE_THRESHOLD_RECHECK_ERROR"

EVIDENCE_THRESHOLD_NOT_MET = "EVIDENCE_THRESHOLD_NOT_MET"
EVIDENCE_THRESHOLD_MET_FUNDING_BLOCKED = "EVIDENCE_THRESHOLD_MET_FUNDING_BLOCKED"
EVIDENCE_THRESHOLD_MET_RISK_CONTRACT_BLOCKED = "EVIDENCE_THRESHOLD_MET_RISK_CONTRACT_BLOCKED"
EVIDENCE_THRESHOLD_MET_READY_FOR_REVIEW_PACKET = "EVIDENCE_THRESHOLD_MET_READY_FOR_REVIEW_PACKET"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

KEEP_WATCHER_RUNNING = "KEEP_WATCHER_RUNNING"
START_WATCHER_NOW = "START_WATCHER_NOW"
RUN_R158_AFTER_10_CAPTURES = "RUN_R158_AFTER_10_CAPTURES"
FUND_ACCOUNT_LATER = "FUND_ACCOUNT_LATER"
RUN_R178_RISK_CONTRACT_APPLY_PACKET_IF_READY = "RUN_R178_RISK_CONTRACT_APPLY_PACKET_IF_READY"

EVENT_TYPE = "EVIDENCE_THRESHOLD_RECHECK_8M_SHORT"
LEDGER_FILENAME = "evidence_threshold_recheck_8m_short.ndjson"
CONFIRM_EVIDENCE_THRESHOLD_RECHECK_RECORDING_PHRASE = (
    "I CONFIRM EVIDENCE THRESHOLD RECHECK RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
}

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/capture_count_sync_8m_short.py",
    "src/app/hammer_radar/operator/short_evidence_recheck_packet.py",
    "src/app/hammer_radar/operator/funding_gate_role_specific_sync.py",
    "src/app/hammer_radar/operator/short_risk_contract_apply_review.py",
    "src/app/hammer_radar/operator/short_strategy_packet.py",
    f"logs/hammer_radar_forward/{SHORT_CAPTURE_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{CAPTURE_COUNT_SYNC_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_EVIDENCE_RECHECK_LEDGER_FILENAME}",
    "logs/hammer_radar_forward/funding_gate_role_specific_sync.ndjson",
    f"logs/hammer_radar_forward/{SHORT_RISK_CONTRACT_APPLY_REVIEW_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_evidence_threshold_recheck_8m_short(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_heartbeats: int = DEFAULT_LATEST_HEARTBEATS,
    latest_outcomes: int = DEFAULT_LATEST_OUTCOMES,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_betrayal: int = DEFAULT_LATEST_BETRAYAL_RECHECK,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    record_recheck: bool = False,
    confirm_evidence_threshold_recheck: str | None = None,
    config_path: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_evidence_threshold_recheck == CONFIRM_EVIDENCE_THRESHOLD_RECHECK_RECORDING_PHRASE
    try:
        target = build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)
        capture_threshold_state = build_capture_threshold_state(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            latest_captures=latest_captures,
            latest_heartbeats=latest_heartbeats,
            stale_after_seconds=stale_after_seconds,
            now=generated_at,
        )
        short_evidence_state = build_short_evidence_readiness_state(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            latest_captures=latest_captures,
            latest_outcomes=latest_outcomes,
            latest_signals=latest_signals,
            latest_betrayal=latest_betrayal,
            config_path=config_path,
            now=generated_at,
        )
        funding_context = build_funding_context_state(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            config_path=config_path,
            now=generated_at,
        )
        risk_contract_context = build_risk_contract_context_state(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            latest_captures=latest_captures,
            config_path=config_path,
            risk_contract_config_path=risk_contract_config_path,
            now=generated_at,
        )
        readiness = classify_evidence_threshold_readiness(
            capture_threshold_state=capture_threshold_state,
            short_evidence_state=short_evidence_state,
            funding_context=funding_context,
            risk_contract_context=risk_contract_context,
        )
        blockers = _build_blockers(
            capture_threshold_state=capture_threshold_state,
            short_evidence_state=short_evidence_state,
            funding_context=funding_context,
            risk_contract_context=risk_contract_context,
            readiness=readiness,
        )
        next_path = build_next_safe_path_after_threshold(
            readiness=readiness,
            capture_threshold_state=capture_threshold_state,
            short_evidence_state=short_evidence_state,
            funding_context=funding_context,
            risk_contract_context=risk_contract_context,
        )
        status = EVIDENCE_THRESHOLD_RECHECK_READY if readiness == EVIDENCE_THRESHOLD_MET_READY_FOR_REVIEW_PACKET else EVIDENCE_THRESHOLD_RECHECK_BLOCKED
        if record_recheck and not confirmation_valid:
            status = EVIDENCE_THRESHOLD_RECHECK_REJECTED
        elif record_recheck and confirmation_valid:
            status = EVIDENCE_THRESHOLD_RECHECK_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "recheck_recorded": False,
            "recheck_id": None,
            "record_recheck_requested": bool(record_recheck),
            "confirmation_valid": bool(confirmation_valid),
            "target_family": {
                "lane_key": target.get("lane_key"),
                "symbol": target.get("symbol"),
                "timeframe": target.get("timeframe"),
                "direction": target.get("direction"),
                "entry_mode": target.get("entry_mode"),
                "current_mode": target.get("current_mode"),
            },
            "capture_threshold_state": capture_threshold_state,
            "short_evidence_state": short_evidence_state,
            "funding_context": funding_context,
            "risk_contract_context": risk_contract_context,
            "readiness": readiness,
            "blockers": blockers,
            "next_safe_path": next_path,
            "recommended_next_operator_move": _recommended_next_operator_move(
                readiness=readiness,
                capture_threshold_state=capture_threshold_state,
                short_evidence_state=short_evidence_state,
                funding_context=funding_context,
                risk_contract_context=risk_contract_context,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(readiness),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_recheck and confirmation_valid:
            record = append_evidence_threshold_recheck_record(payload, log_dir=resolved_log_dir)
            payload["recheck_recorded"] = True
            payload["recheck_id"] = record["recheck_id"]
            payload["ledger_path"] = str(evidence_threshold_recheck_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": EVIDENCE_THRESHOLD_RECHECK_ERROR,
                "generated_at": generated_at.isoformat(),
                "recheck_recorded": False,
                "recheck_id": None,
                "record_recheck_requested": bool(record_recheck),
                "confirmation_valid": bool(confirmation_valid),
                "target_family": _target_from_key(lane_key),
                "capture_threshold_state": _empty_capture_threshold_state(),
                "short_evidence_state": _empty_short_evidence_state(),
                "funding_context": _empty_funding_context(),
                "risk_contract_context": _empty_risk_contract_context(),
                "readiness": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "blockers": ["R177 evidence threshold recheck build error must be fixed before any next phase"],
                "next_safe_path": ["fix R177 build error", "rerun preview only", "do not mutate config or call Binance"],
                "recommended_next_operator_move": START_WATCHER_NOW,
                "recommended_next_engineering_move": "Fix R177 builder error and rerun the preview; do not record until preview is sane.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_capture_threshold_state(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_heartbeats: int = DEFAULT_LATEST_HEARTBEATS,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    captures = load_short_capture_records(log_dir=log_dir, lane_key=lane_key, limit=latest_captures)
    heartbeats = load_short_capture_heartbeats(log_dir=log_dir, lane_key=lane_key, limit=latest_heartbeats)
    count = count_unique_fresh_captures(captures, required_count=MIN_FRESH_CANDIDATES)
    watcher = build_watcher_heartbeat_status(heartbeats, now=generated_at, stale_after_seconds=stale_after_seconds)
    return _sanitize(
        {
            **count,
            "watcher_likely_running": bool(watcher.get("watcher_likely_running")),
            "watcher_stale": bool(watcher.get("watcher_stale")),
            "latest_heartbeat_found": bool(watcher.get("latest_heartbeat_found")),
            "latest_heartbeat_status": watcher.get("latest_heartbeat_status"),
            "heartbeat_age_seconds": watcher.get("heartbeat_age_seconds"),
            "source_capture_sync": _latest_capture_count_sync(log_dir=log_dir, lane_key=lane_key),
        }
    )


def build_short_evidence_readiness_state(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_outcomes: int = DEFAULT_LATEST_OUTCOMES,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_betrayal: int = DEFAULT_LATEST_BETRAYAL_RECHECK,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    packet = build_short_evidence_recheck_packet(
        log_dir=log_dir,
        lane_key=lane_key,
        latest_captures=latest_captures,
        latest_outcomes=latest_outcomes,
        latest_signals=latest_signals,
        latest_betrayal=latest_betrayal,
        record_packet=False,
        config_path=config_path,
        now=now,
    )
    historical = dict(packet.get("historical_evidence") or {})
    promotion = dict(packet.get("promotion_readiness") or {})
    latest_record = _latest_short_evidence_recheck(log_dir=log_dir, lane_key=lane_key)
    latest_status = promotion.get("readiness") or latest_record.get("latest_recheck_status") or "UNKNOWN"
    ready = latest_status == PROMOTION_PACKET_READY_FOR_OPERATOR_REVIEW and promotion.get("ready_for_operator_review") is True
    return _sanitize(
        {
            "historical_win_rate_pct": historical.get("win_rate_pct"),
            "avg_pnl_pct": historical.get("avg_pnl_pct"),
            "paper_outcome_count": historical.get("paper_outcome_count"),
            "latest_recheck_status": latest_status,
            "evidence_ready_for_review": bool(ready),
            "latest_recorded_recheck_status": latest_record.get("latest_recheck_status"),
            "source_packet_status": packet.get("status"),
        }
    )


def build_funding_context_state(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    sync = build_funding_gate_role_specific_sync(
        log_dir=log_dir,
        lane_key=lane_key,
        record_sync=False,
        config_path=config_path,
        now=now,
    )
    balance = dict(sync.get("latest_balance_state") or {})
    gate = dict(sync.get("funding_gate") or {})
    status = balance.get("balance_readiness") or gate.get("funding_sync_status") or "UNKNOWN"
    available = balance.get("available_balance_usdt")
    if available is None and status == ACCOUNT_NOT_FUNDED:
        available = 0.0
    return _sanitize(
        {
            "funding_status": status or "UNKNOWN",
            "available_balance_usdt": available,
            "funding_ready": bool(gate.get("funding_ready") and balance.get("funding_ready")),
            "funding_sync_status": gate.get("funding_sync_status"),
            "source_sync_status": sync.get("status"),
        }
    )


def build_risk_contract_context_state(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
    config_path: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    review = build_short_risk_contract_apply_review(
        log_dir=log_dir,
        lane_key=lane_key,
        latest_captures=latest_captures,
        record_review=False,
        config_path=config_path,
        risk_contract_config_path=risk_contract_config_path,
        now=now,
    )
    existing = dict(review.get("existing_contract_state") or {})
    latest_record = _latest_risk_contract_apply_review(log_dir=log_dir, lane_key=lane_key)
    applied = bool(existing.get("target_contract_exists") and existing.get("target_contract_enabled_for_preflight"))
    return _sanitize(
        {
            "target_contract_exists": bool(existing.get("target_contract_exists")),
            "risk_contract_applied": applied,
            "latest_apply_review_readiness": latest_record.get("latest_apply_review_readiness"),
            "current_apply_review_readiness": review.get("readiness"),
            "source_review_status": review.get("status"),
        }
    )


def classify_evidence_threshold_readiness(
    *,
    capture_threshold_state: Mapping[str, Any],
    short_evidence_state: Mapping[str, Any],
    funding_context: Mapping[str, Any],
    risk_contract_context: Mapping[str, Any],
) -> str:
    if capture_threshold_state.get("threshold_met") is not True:
        return EVIDENCE_THRESHOLD_NOT_MET
    if short_evidence_state.get("evidence_ready_for_review") is not True:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if funding_context.get("funding_ready") is not True:
        return EVIDENCE_THRESHOLD_MET_FUNDING_BLOCKED
    if risk_contract_context.get("risk_contract_applied") is not True:
        return EVIDENCE_THRESHOLD_MET_RISK_CONTRACT_BLOCKED
    return EVIDENCE_THRESHOLD_MET_READY_FOR_REVIEW_PACKET


def build_next_safe_path_after_threshold(
    *,
    readiness: str,
    capture_threshold_state: Mapping[str, Any],
    short_evidence_state: Mapping[str, Any],
    funding_context: Mapping[str, Any],
    risk_contract_context: Mapping[str, Any],
) -> list[str]:
    if capture_threshold_state.get("watcher_stale") is True or capture_threshold_state.get("watcher_likely_running") is not True:
        return ["start or refresh the R157/R176 paper capture watcher", "rerun R177 preview", "record R177 only after exact confirmation"]
    if readiness == EVIDENCE_THRESHOLD_NOT_MET:
        required = capture_threshold_state.get("required_fresh_capture_count")
        current = capture_threshold_state.get("fresh_capture_count")
        return [f"keep watcher running until fresh captures reach {required}", f"current unique fresh captures: {current}", "rerun R177 when threshold is met"]
    if short_evidence_state.get("evidence_ready_for_review") is not True:
        return ["run R158 short evidence recheck after 10 captures", "inspect promotion readiness", "keep lane mode paper"]
    if funding_context.get("funding_ready") is not True:
        return ["fund account later through operator process", "rerun read-only balance/funding sync", "keep live execution disabled"]
    if risk_contract_context.get("risk_contract_applied") is not True:
        return ["run R178 risk-contract apply packet if evidence ready", "preview only by default", "do not write risk contract config in R177"]
    return ["build future tiny-live review packet", "require operator approval", "keep kill switch and live flags protected"]


def append_evidence_threshold_recheck_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = evidence_threshold_recheck_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "recheck_id": record.get("recheck_id") or f"r177_evidence_threshold_recheck_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_recheck_requested": bool(record.get("record_recheck_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_family": dict(record.get("target_family") or {}),
            "capture_threshold_state": dict(record.get("capture_threshold_state") or {}),
            "short_evidence_state": dict(record.get("short_evidence_state") or {}),
            "funding_context": dict(record.get("funding_context") or {}),
            "risk_contract_context": dict(record.get("risk_contract_context") or {}),
            "readiness": record.get("readiness"),
            "blockers": list(record.get("blockers") or []),
            "next_safe_path": list(record.get("next_safe_path") or []),
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


def load_evidence_threshold_recheck_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = evidence_threshold_recheck_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_evidence_threshold_rechecks(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    readiness_counts = Counter(str(record.get("readiness") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "readiness_counts": dict(sorted(readiness_counts.items())),
        "last_recheck_id": latest.get("recheck_id"),
        "last_target_lane": (latest.get("target_family") or {}).get("lane_key")
        if isinstance(latest.get("target_family"), Mapping)
        else None,
        "safety": dict(SAFETY),
    }


def evidence_threshold_recheck_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_evidence_threshold_recheck_8m_short_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_blockers(
    *,
    capture_threshold_state: Mapping[str, Any],
    short_evidence_state: Mapping[str, Any],
    funding_context: Mapping[str, Any],
    risk_contract_context: Mapping[str, Any],
    readiness: str,
) -> list[str]:
    blockers: list[str] = []
    if capture_threshold_state.get("watcher_stale") is True:
        blockers.append("R157/R176 watcher heartbeat is stale")
    if capture_threshold_state.get("watcher_likely_running") is not True:
        blockers.append("R157/R176 watcher is not likely running")
    if capture_threshold_state.get("threshold_met") is not True:
        blockers.append("fresh capture threshold below 10")
    if short_evidence_state.get("evidence_ready_for_review") is not True:
        blockers.append("R158 short evidence is not ready for operator review")
    if funding_context.get("funding_ready") is not True:
        blockers.append(f"funding gate blocked: {funding_context.get('funding_status') or 'UNKNOWN'}")
    if risk_contract_context.get("risk_contract_applied") is not True:
        blockers.append("target 8m short risk contract is not applied")
    blockers.extend(
        [
            "lane remains paper",
            "global kill switch must remain enabled",
            "live execution remains disabled",
            "operator approval is not granted by R177",
        ]
    )
    if readiness == UNKNOWN_NEEDS_MANUAL_REVIEW:
        blockers.append("manual review needed after threshold because evidence readiness is not ready")
    return _dedupe(blockers)


def _recommended_next_operator_move(
    *,
    readiness: str,
    capture_threshold_state: Mapping[str, Any],
    short_evidence_state: Mapping[str, Any],
    funding_context: Mapping[str, Any],
    risk_contract_context: Mapping[str, Any],
) -> str:
    if capture_threshold_state.get("watcher_stale") is True or capture_threshold_state.get("watcher_likely_running") is not True:
        return START_WATCHER_NOW
    if readiness == EVIDENCE_THRESHOLD_NOT_MET:
        return KEEP_WATCHER_RUNNING
    if short_evidence_state.get("evidence_ready_for_review") is not True:
        return RUN_R158_AFTER_10_CAPTURES
    if funding_context.get("funding_ready") is not True:
        return FUND_ACCOUNT_LATER
    if risk_contract_context.get("risk_contract_applied") is not True:
        return RUN_R178_RISK_CONTRACT_APPLY_PACKET_IF_READY
    return RUN_R178_RISK_CONTRACT_APPLY_PACKET_IF_READY


def _recommended_next_engineering_move(readiness: str) -> str:
    if readiness == EVIDENCE_THRESHOLD_NOT_MET:
        return "Keep R176 capture count sync and R157 watcher active; rerun R177 after 10 unique fresh captures."
    if readiness == EVIDENCE_THRESHOLD_MET_FUNDING_BLOCKED:
        return "Keep tiny-live blocked and rerun funding sync only after operator-funded read-only evidence exists."
    if readiness == EVIDENCE_THRESHOLD_MET_RISK_CONTRACT_BLOCKED:
        return "Create R178 risk-contract apply packet as preview-only; no config write or lane-mode change."
    if readiness == EVIDENCE_THRESHOLD_MET_READY_FOR_REVIEW_PACKET:
        return "Build the next review packet path only; live execution and lane promotion remain separate future phases."
    return "Run R158 evidence recheck and inspect missing evidence fields before any future packet."


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


def _latest_capture_count_sync(*, log_dir: str | Path | None, lane_key: str) -> dict[str, Any]:
    for record in load_capture_count_sync_records(log_dir=log_dir, limit=10):
        target = record.get("target_family") if isinstance(record.get("target_family"), Mapping) else {}
        if target.get("lane_key") == lane_key:
            return {
                "sync_id": record.get("sync_id"),
                "threshold_status": record.get("threshold_status"),
                "tiny_live_evidence_threshold_met": bool(record.get("tiny_live_evidence_threshold_met")),
            }
    return {"sync_id": None, "threshold_status": None, "tiny_live_evidence_threshold_met": False}


def _latest_short_evidence_recheck(*, log_dir: str | Path | None, lane_key: str) -> dict[str, Any]:
    for record in load_short_evidence_recheck_records(log_dir=log_dir, limit=10):
        target = record.get("target_family") if isinstance(record.get("target_family"), Mapping) else {}
        if target.get("lane_key") == lane_key:
            promotion = record.get("promotion_readiness") if isinstance(record.get("promotion_readiness"), Mapping) else {}
            return {
                "packet_id": record.get("packet_id"),
                "latest_recheck_status": promotion.get("readiness"),
            }
    return {"packet_id": None, "latest_recheck_status": None}


def _latest_risk_contract_apply_review(*, log_dir: str | Path | None, lane_key: str) -> dict[str, Any]:
    for record in load_short_risk_contract_apply_review_records(log_dir=log_dir, limit=10):
        target = record.get("target_family") if isinstance(record.get("target_family"), Mapping) else {}
        if target.get("lane_key") == lane_key:
            return {
                "review_id": record.get("review_id"),
                "latest_apply_review_readiness": record.get("readiness"),
            }
    return {"review_id": None, "latest_apply_review_readiness": None}


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


def _empty_capture_threshold_state() -> dict[str, Any]:
    return {
        "fresh_capture_count": 0,
        "required_fresh_capture_count": int(MIN_FRESH_CANDIDATES),
        "threshold_met": False,
        "unique_captured_signal_ids": [],
        "latest_captured_signal_id": None,
        "watcher_likely_running": False,
        "watcher_stale": False,
    }


def _empty_short_evidence_state() -> dict[str, Any]:
    return {
        "historical_win_rate_pct": None,
        "avg_pnl_pct": None,
        "paper_outcome_count": None,
        "latest_recheck_status": "UNKNOWN",
        "evidence_ready_for_review": False,
    }


def _empty_funding_context() -> dict[str, Any]:
    return {
        "funding_status": "UNKNOWN",
        "available_balance_usdt": None,
        "funding_ready": False,
    }


def _empty_risk_contract_context() -> dict[str, Any]:
    return {
        "target_contract_exists": False,
        "risk_contract_applied": False,
        "latest_apply_review_readiness": None,
    }


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
