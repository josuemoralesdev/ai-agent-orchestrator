"""R228 tiny-live 10-of-10 ready packet.

This module composes local paper-only evidence into an operator review packet.
It never calls Binance/network, creates order payloads, mutates env/config, arms
lanes, promotes strategies, or authorizes live execution.
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
from src.app.hammer_radar.operator.betrayal_ranking_feed_preview import (
    BETRAYAL_TRACK_B_STRUCTURALLY_COMPLETE_WAITING_FOR_DATA,
    build_betrayal_ranking_feed_preview,
    load_betrayal_ranking_feed_preview_records,
)
from src.app.hammer_radar.operator.capture_count_sync_8m_short import (
    CAPTURE_THRESHOLD_MET,
    DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    RUN_R177_EVIDENCE_THRESHOLD_RECHECK,
    build_capture_count_sync_8m_short,
    load_capture_count_sync_records,
)
from src.app.hammer_radar.operator.capture_priority_rebalance import (
    build_capture_priority_rebalance,
    load_capture_priority_rebalance_records,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_lane_scoreboard import DEFAULT_OFFICIAL_TINY_LIVE_LANE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.lane_outcome_enrichment import (
    build_lane_outcome_enrichment,
    load_lane_outcome_enrichment_records,
)

TINY_LIVE_10_OF_10_READY_PACKET_READY = "TINY_LIVE_10_OF_10_READY_PACKET_READY"
TINY_LIVE_10_OF_10_READY_PACKET_REJECTED = "TINY_LIVE_10_OF_10_READY_PACKET_REJECTED"
TINY_LIVE_10_OF_10_READY_PACKET_RECORDED = "TINY_LIVE_10_OF_10_READY_PACKET_RECORDED"
TINY_LIVE_10_OF_10_READY_PACKET_BLOCKED = "TINY_LIVE_10_OF_10_READY_PACKET_BLOCKED"
TINY_LIVE_10_OF_10_READY_PACKET_ERROR = "TINY_LIVE_10_OF_10_READY_PACKET_ERROR"

TINY_LIVE_10_OF_10_EVIDENCE_READY_OPERATOR_REVIEW_REQUIRED = (
    "TINY_LIVE_10_OF_10_EVIDENCE_READY_OPERATOR_REVIEW_REQUIRED"
)
TINY_LIVE_10_OF_10_BLOCKED_BY_RISK_CONTRACT = "TINY_LIVE_10_OF_10_BLOCKED_BY_RISK_CONTRACT"
TINY_LIVE_10_OF_10_BLOCKED_BY_LIVE_AUTHORIZATION = "TINY_LIVE_10_OF_10_BLOCKED_BY_LIVE_AUTHORIZATION"
TINY_LIVE_10_OF_10_BLOCKED_BY_FISHERMAN_STALE = "TINY_LIVE_10_OF_10_BLOCKED_BY_FISHERMAN_STALE"
TINY_LIVE_10_OF_10_BLOCKED_BY_EVIDENCE_GAP = "TINY_LIVE_10_OF_10_BLOCKED_BY_EVIDENCE_GAP"
TINY_LIVE_10_OF_10_NOT_MET = "TINY_LIVE_10_OF_10_NOT_MET"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_10_OF_10_READY_PACKET"
LEDGER_FILENAME = "tiny_live_10_of_10_ready_packet.ndjson"
CONFIRM_TINY_LIVE_10_OF_10_READY_PACKET_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE 10 OF 10 READY PACKET RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

OFFICIAL_LANE_KEY = DEFAULT_OFFICIAL_TINY_LIVE_LANE
MODERN_PATH = "R228_TINY_LIVE_10_OF_10_READY_PACKET"
RISK_CONTRACT_CONFIG_PATH = Path("configs/hammer_radar/tiny_live_risk_contracts.json")

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "registry_config_written": False,
    "scoring_config_written": False,
    "matrix_config_written": False,
    "risk_contract_config_written": False,
    "lane_config_written": False,
    "fisherman_config_written": False,
    "scheduler_config_written": False,
    "ledger_rewritten": False,
    "destructive_write": False,
    "historical_ledger_rewritten": False,
    "normalized_rows_appended": False,
    "paper_outcome_ledger_rewritten": False,
    "paper_outcomes_appended": False,
    "strategy_performance_appended": False,
    "strategy_promotion_status_appended": False,
    "ranking_scores_fabricated": False,
    "win_rates_fabricated": False,
    "promotion_eligibility_fabricated": False,
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
    "network_allowed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
    "live_authorization_created": False,
    "live_execution_enabled": False,
    "signal_origin_promoted": False,
    "lane_promoted": False,
    "official_tiny_live_lane_changed": False,
    "alternate_lane_promoted": False,
    "betrayal_live_authorized": False,
    "betrayal_promoted": False,
    "tiny_live_ready_packet_only": True,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/capture_count_sync_8m_short.py",
    "src/app/hammer_radar/operator/fisherman_watchdog_ledger_reconciliation.py",
    "src/app/hammer_radar/operator/lane_outcome_enrichment.py",
    "src/app/hammer_radar/operator/capture_priority_rebalance.py",
    "src/app/hammer_radar/operator/betrayal_ranking_feed_preview.py",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson",
    "logs/hammer_radar_forward/lane_outcome_enrichment.ndjson",
    "logs/hammer_radar_forward/capture_priority_rebalance.ndjson",
    "logs/hammer_radar_forward/betrayal_ranking_feed_preview.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_10_of_10_ready_packet(
    *,
    log_dir: str | Path | None = None,
    record_packet: bool = False,
    confirm_tiny_live_10_of_10_ready_packet: str | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    risk_contract_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_tiny_live_10_of_10_ready_packet == CONFIRM_TINY_LIVE_10_OF_10_READY_PACKET_RECORDING_PHRASE
    try:
        capture_sync = load_latest_capture_count_sync_8m_short(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
            stale_after_seconds=stale_after_seconds,
            now=generated_at,
        )
        fisherman = load_latest_fisherman_health_context(
            log_dir=resolved_log_dir,
            official_lane_key=official_lane_key,
            stale_after_seconds=stale_after_seconds,
            now=generated_at,
            capture_sync=capture_sync,
        )
        lane_outcome = load_latest_lane_outcome_context(log_dir=resolved_log_dir, official_lane_key=official_lane_key)
        capture_priority = load_latest_capture_priority_context(log_dir=resolved_log_dir, official_lane_key=official_lane_key)
        track_b = load_latest_track_b_structural_context(log_dir=resolved_log_dir, official_lane_key=official_lane_key)

        capture_recheck = build_capture_threshold_recheck(capture_sync, official_lane_key=official_lane_key)
        fisherman_recheck = build_fisherman_health_recheck(fisherman)
        evidence_recheck = build_evidence_quality_recheck(
            lane_outcome_context=lane_outcome,
            capture_priority_context=capture_priority,
            official_lane_key=official_lane_key,
        )
        track_b_context = _build_track_b_context(track_b)
        risk_contract_ready = _approved_risk_contract_exists(
            official_lane_key=official_lane_key,
            risk_contract_config_path=risk_contract_config_path,
        )
        gate_matrix = build_tiny_live_gate_matrix(
            capture_threshold_recheck=capture_recheck,
            fisherman_health_recheck=fisherman_recheck,
            risk_contract_ready=risk_contract_ready,
        )
        operator_packet = build_operator_ready_packet(gate_matrix)
        recommendations = build_tiny_live_10_of_10_recommendations(
            gate_matrix=gate_matrix,
            evidence_quality_recheck=evidence_recheck,
            track_b_context=track_b_context,
        )
        overall = classify_tiny_live_10_of_10_packet_status(gate_matrix)
        status = TINY_LIVE_10_OF_10_READY_PACKET_READY if gate_matrix.get("operator_review_ready") else TINY_LIVE_10_OF_10_READY_PACKET_BLOCKED
        if record_packet and not confirmation_valid:
            status = TINY_LIVE_10_OF_10_READY_PACKET_REJECTED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "packet_recorded": False,
            "packet_record_id": None,
            "record_packet_requested": bool(record_packet),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": _target_scope(official_lane_key),
            "capture_threshold_recheck": capture_recheck,
            "fisherman_health_recheck": fisherman_recheck,
            "evidence_quality_recheck": evidence_recheck,
            "track_b_context": track_b_context,
            "tiny_live_gate_matrix": gate_matrix,
            "operator_ready_packet": operator_packet,
            "recommended_next_operator_move": recommendations["recommended_next_operator_move"],
            "recommended_next_engineering_move": recommendations["recommended_next_engineering_move"],
            "ready_packet_overall_status": overall,
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_packet and confirmation_valid:
            record = append_tiny_live_10_of_10_ready_packet_record(payload, log_dir=resolved_log_dir)
            payload["status"] = TINY_LIVE_10_OF_10_READY_PACKET_RECORDED
            payload["packet_recorded"] = True
            payload["packet_record_id"] = record["packet_record_id"]
            payload["ledger_path"] = str(tiny_live_10_of_10_ready_packet_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": TINY_LIVE_10_OF_10_READY_PACKET_ERROR,
                "generated_at": generated_at.isoformat(),
                "packet_recorded": False,
                "packet_record_id": None,
                "record_packet_requested": bool(record_packet),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _target_scope(official_lane_key),
                "capture_threshold_recheck": _empty_capture_recheck(),
                "fisherman_health_recheck": _empty_fisherman_recheck(),
                "evidence_quality_recheck": _empty_evidence_quality(),
                "track_b_context": _empty_track_b_context(),
                "tiny_live_gate_matrix": build_tiny_live_gate_matrix(
                    capture_threshold_recheck=_empty_capture_recheck(),
                    fisherman_health_recheck=_empty_fisherman_recheck(),
                    risk_contract_ready=False,
                ),
                "operator_ready_packet": build_operator_ready_packet(
                    build_tiny_live_gate_matrix(
                        capture_threshold_recheck=_empty_capture_recheck(),
                        fisherman_health_recheck=_empty_fisherman_recheck(),
                        risk_contract_ready=False,
                    )
                ),
                "recommended_next_operator_move": "RECHECK_EVIDENCE",
                "recommended_next_engineering_move": "Fix R228 packet error before any R229 risk-contract preview.",
                "ready_packet_overall_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_capture_count_sync_8m_short(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = build_capture_count_sync_8m_short(
        log_dir=log_dir,
        lane_key=official_lane_key,
        stale_after_seconds=stale_after_seconds,
        now=now,
    )
    records = load_capture_count_sync_records(log_dir=log_dir, limit=50)
    latest_record: dict[str, Any] = {}
    for record in records:
        target = record.get("target_family") if isinstance(record.get("target_family"), Mapping) else {}
        if str(target.get("lane_key") or official_lane_key) == official_lane_key:
            latest_record = dict(record)
            break
    return _sanitize(
        {
            **current,
            "capture_sync_found": bool(latest_record),
            "source_built_from_local_ledgers": True,
            "latest_recorded_capture_sync": latest_record,
        }
    )


def load_latest_fisherman_health_context(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    now: datetime | None = None,
    capture_sync: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    sync = capture_sync or load_latest_capture_count_sync_8m_short(
        log_dir=log_dir,
        official_lane_key=official_lane_key,
        stale_after_seconds=stale_after_seconds,
        now=now,
    )
    return _sanitize(sync.get("watcher_status") if isinstance(sync.get("watcher_status"), Mapping) else {})


def load_latest_lane_outcome_context(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_lane_outcome_enrichment_records(log_dir=log_dir, limit=20)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        if str(target.get("official_tiny_live_lane") or official_lane_key) == official_lane_key:
            return _sanitize({**record, "context_found": True})
    context = build_lane_outcome_enrichment(log_dir=log_dir, official_tiny_live_lane=official_lane_key)
    return _sanitize({**context, "context_found": False, "source_built_from_local_ledgers": True})


def load_latest_capture_priority_context(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_capture_priority_rebalance_records(log_dir=log_dir, limit=20)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        if str(target.get("official_tiny_live_lane") or official_lane_key) == official_lane_key:
            return _sanitize({**record, "context_found": True})
    context = build_capture_priority_rebalance(log_dir=log_dir, official_tiny_live_lane=official_lane_key)
    return _sanitize({**context, "context_found": False, "source_built_from_local_ledgers": True})


def load_latest_track_b_structural_context(
    *,
    log_dir: str | Path | None = None,
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    records = load_betrayal_ranking_feed_preview_records(log_dir=log_dir, limit=20)
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        if str(target.get("official_tiny_live_lane") or official_lane_key) == official_lane_key:
            return _sanitize({**record, "context_found": True})
    context = build_betrayal_ranking_feed_preview(log_dir=log_dir, official_tiny_live_lane=official_lane_key)
    return _sanitize({**context, "context_found": False, "source_built_from_local_ledgers": True})


def normalize_official_capture_signal_ids(capture_count: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    raw_ids = capture_count.get("unique_captured_signal_ids") or capture_count.get("captured_signal_ids") or []
    for value in raw_ids if isinstance(raw_ids, list) else []:
        signal_id = str(value or "").strip()
        if signal_id and signal_id not in ids:
            ids.append(signal_id)
    latest = str(capture_count.get("latest_captured_signal_id") or "").strip()
    if latest and latest not in ids:
        ids.insert(0, latest)
    return ids


def build_capture_threshold_recheck(capture_sync: Mapping[str, Any], *, official_lane_key: str = OFFICIAL_LANE_KEY) -> dict[str, Any]:
    target = capture_sync.get("target_family") if isinstance(capture_sync.get("target_family"), Mapping) else {}
    capture_count = capture_sync.get("capture_count") if isinstance(capture_sync.get("capture_count"), Mapping) else {}
    ids = normalize_official_capture_signal_ids(capture_count)
    latest_signal_id = str(capture_count.get("latest_captured_signal_id") or (ids[0] if ids else "")).strip() or None
    latest_timestamp = _signal_timestamp(latest_signal_id)
    required = int(capture_count.get("required_fresh_capture_count") or 10)
    fresh = int(capture_count.get("fresh_capture_count") or len(ids))
    threshold_met = capture_count.get("threshold_met") is True
    threshold_status = str(capture_sync.get("threshold_status") or "")
    official_lane_matches = str(target.get("lane_key") or official_lane_key) == official_lane_key
    ready = all(
        [
            official_lane_matches,
            fresh >= 10,
            required == 10,
            threshold_met,
            threshold_status == CAPTURE_THRESHOLD_MET,
            len(ids) >= 10,
            bool(latest_signal_id),
            bool(latest_timestamp),
        ]
    )
    return _sanitize(
        {
            "fresh_capture_count": fresh,
            "required_fresh_capture_count": required,
            "threshold_met": threshold_met,
            "threshold_status": threshold_status or None,
            "unique_capture_count": len(ids),
            "latest_captured_signal_id": latest_signal_id,
            "latest_capture_timestamp": latest_timestamp,
            "captured_signal_ids": ids,
            "official_lane_key": str(target.get("lane_key") or official_lane_key),
            "official_lane_unchanged": official_lane_matches,
            "evidence_threshold_ready": ready,
            "old_recommendation_reconciled": RUN_R177_EVIDENCE_THRESHOLD_RECHECK,
            "modern_path": MODERN_PATH,
        }
    )


def build_fisherman_health_recheck(fisherman_health_context: Mapping[str, Any]) -> dict[str, Any]:
    latest_found = fisherman_health_context.get("latest_heartbeat_found") is True
    likely_running = fisherman_health_context.get("watcher_likely_running") is True
    stale = fisherman_health_context.get("watcher_stale") is True
    return _sanitize(
        {
            "latest_heartbeat_found": latest_found,
            "heartbeat_age_seconds": fisherman_health_context.get("heartbeat_age_seconds"),
            "stale_after_seconds": fisherman_health_context.get("stale_after_seconds"),
            "watcher_likely_running": likely_running,
            "watcher_stale": stale,
            "latest_heartbeat_status": fisherman_health_context.get("latest_heartbeat_status"),
            "fisherman_ready": latest_found and likely_running and not stale,
        }
    )


def build_evidence_quality_recheck(
    *,
    lane_outcome_context: Mapping[str, Any],
    capture_priority_context: Mapping[str, Any],
    official_lane_key: str = OFFICIAL_LANE_KEY,
) -> dict[str, Any]:
    outcome_row = _find_lane_row(lane_outcome_context.get("enriched_lane_rows"), official_lane_key)
    priority_summary = capture_priority_context.get("official_protected_path_summary")
    if not isinstance(priority_summary, Mapping):
        priority_summary = {}
    known = _number_or_none(outcome_row.get("known_outcome_count") if outcome_row else None)
    win_rate = _number_or_none(outcome_row.get("win_rate_pct") if outcome_row else None)
    score = _number_or_none(outcome_row.get("combined_watch_score") if outcome_row else priority_summary.get("combined_watch_score"))
    notes = []
    if outcome_row:
        notes.extend(str(item) for item in outcome_row.get("enrichment_notes") or [])
    if not outcome_row:
        notes.append("official_lane_outcome_row_missing")
    if not priority_summary:
        notes.append("capture_priority_official_summary_missing")
    context_found = bool(outcome_row)
    priority_found = bool(priority_summary) or bool(capture_priority_context.get("context_found"))
    if context_found and priority_found and known is not None and win_rate is not None:
        quality = "READY"
    elif context_found or priority_found:
        quality = "PARTIAL"
    else:
        quality = "MISSING"
    return _sanitize(
        {
            "lane_outcome_context_found": context_found,
            "capture_priority_context_found": priority_found,
            "known_outcome_count": known,
            "win_rate_pct": win_rate,
            "combined_watch_score": score,
            "quality_status": quality,
            "notes": notes,
        }
    )


def build_tiny_live_gate_matrix(
    *,
    capture_threshold_recheck: Mapping[str, Any],
    fisherman_health_recheck: Mapping[str, Any],
    risk_contract_ready: bool = False,
) -> dict[str, Any]:
    evidence_ready = capture_threshold_recheck.get("evidence_threshold_ready") is True
    fisherman_ready = fisherman_health_recheck.get("fisherman_ready") is True
    operator_review_ready = evidence_ready and fisherman_ready
    blocked_by: list[str] = []
    if not evidence_ready:
        blocked_by.append("evidence_threshold_not_ready")
    if not fisherman_ready:
        blocked_by.append("fisherman_not_ready")
    if not risk_contract_ready:
        blocked_by.append("risk_contract_missing")
    blocked_by.extend(["live_authorization_absent", "live_execution_disabled", "order_payload_forbidden"])
    return {
        "evidence_ready": evidence_ready,
        "fisherman_ready": fisherman_ready,
        "operator_review_ready": operator_review_ready,
        "risk_contract_ready": bool(risk_contract_ready),
        "live_authorization_ready": False,
        "live_execution_ready": False,
        "order_ready": False,
        "live_ready_today": False,
        "blocked_by": blocked_by,
    }


def build_operator_ready_packet(tiny_live_gate_matrix: Mapping[str, Any]) -> dict[str, Any]:
    review_ready = tiny_live_gate_matrix.get("operator_review_ready") is True
    if review_ready:
        action = "REVIEW_R228_PACKET"
    elif "fisherman_not_ready" in (tiny_live_gate_matrix.get("blocked_by") or []):
        action = "FIX_FISHERMAN"
    elif "evidence_threshold_not_ready" in (tiny_live_gate_matrix.get("blocked_by") or []):
        action = "RECHECK_EVIDENCE"
    else:
        action = "WAIT"
    return {
        "packet_ready_for_operator_review": review_ready,
        "operator_should_review": review_ready,
        "operator_should_place_order": False,
        "operator_should_enable_live": False,
        "next_required_human_action": action,
        "explicit_non_actions": [
            "do not place order",
            "do not enable live",
            "do not disable kill switch",
            "do not fund based on this packet alone",
        ],
    }


def build_tiny_live_10_of_10_recommendations(
    *,
    gate_matrix: Mapping[str, Any],
    evidence_quality_recheck: Mapping[str, Any],
    track_b_context: Mapping[str, Any],
) -> dict[str, str]:
    if not gate_matrix.get("evidence_ready"):
        operator = "RECHECK_EVIDENCE"
        engineering = "Rerun R176/R208B local capture sync until official 10-of-10 evidence is visible."
    elif not gate_matrix.get("fisherman_ready"):
        operator = "FIX_FISHERMAN"
        engineering = "Restore the paper fisherman heartbeat and rerun R228; no live actions."
    elif gate_matrix.get("operator_review_ready"):
        operator = "REVIEW_R228_PACKET"
        engineering = "Create R229 tiny-live risk contract preview from this packet; preview only, no config writes or orders."
    else:
        operator = "WAIT"
        engineering = "Wait for local evidence to settle, then rerun R228."
    if evidence_quality_recheck.get("quality_status") in {"MISSING", "UNKNOWN"}:
        engineering = "Refresh R232/R233 quality context locally, then rerun R228 before any R229 preview."
    if track_b_context.get("track_b_action_required_now") is True:
        engineering = "Do not promote Track B; rerun R238/R239 status only after true inverse data arrives."
    return {
        "recommended_next_operator_move": operator,
        "recommended_next_engineering_move": engineering,
    }


def classify_tiny_live_10_of_10_packet_status(tiny_live_gate_matrix: Mapping[str, Any]) -> str:
    if not tiny_live_gate_matrix.get("evidence_ready"):
        return TINY_LIVE_10_OF_10_NOT_MET
    if not tiny_live_gate_matrix.get("fisherman_ready"):
        return TINY_LIVE_10_OF_10_BLOCKED_BY_FISHERMAN_STALE
    if not tiny_live_gate_matrix.get("risk_contract_ready"):
        return TINY_LIVE_10_OF_10_BLOCKED_BY_RISK_CONTRACT
    if not tiny_live_gate_matrix.get("live_authorization_ready"):
        return TINY_LIVE_10_OF_10_BLOCKED_BY_LIVE_AUTHORIZATION
    return TINY_LIVE_10_OF_10_EVIDENCE_READY_OPERATOR_REVIEW_REQUIRED


def append_tiny_live_10_of_10_ready_packet_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_10_of_10_ready_packet_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "packet_record_id": record.get("packet_record_id") or f"r228_tiny_live_10_of_10_packet_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "target_scope": dict(record.get("target_scope") or {}),
            "capture_threshold_recheck": dict(record.get("capture_threshold_recheck") or {}),
            "fisherman_health_recheck": dict(record.get("fisherman_health_recheck") or {}),
            "evidence_quality_recheck": dict(record.get("evidence_quality_recheck") or {}),
            "track_b_context": dict(record.get("track_b_context") or {}),
            "tiny_live_gate_matrix": dict(record.get("tiny_live_gate_matrix") or {}),
            "operator_ready_packet": dict(record.get("operator_ready_packet") or {}),
            "ready_packet_overall_status": record.get("ready_packet_overall_status"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_10_of_10_ready_packet_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_10_of_10_ready_packet_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_10_of_10_ready_packet_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_reviewed": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "latest_packet_record_id": latest.get("packet_record_id"),
        "latest_ready_packet_overall_status": latest.get("ready_packet_overall_status"),
    }


def tiny_live_10_of_10_ready_packet_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_10_of_10_ready_packet_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _build_track_b_context(track_b: Mapping[str, Any]) -> dict[str, Any]:
    report = track_b.get("track_b_structural_completion_report")
    if not isinstance(report, Mapping):
        report = {}
    overall = str(track_b.get("ranking_overall_status") or "")
    structurally_complete = report.get("structurally_complete_for_now") is True or (
        overall == BETRAYAL_TRACK_B_STRUCTURALLY_COMPLETE_WAITING_FOR_DATA
    )
    waiting = report.get("waiting_for_data_not_architecture") is True or structurally_complete
    return {
        "track_b_structurally_complete_for_now": structurally_complete,
        "waiting_for_data_not_architecture": waiting,
        "betrayal_live_authorized": False,
        "betrayal_promoted": False,
        "track_b_action_required_now": False,
    }


def _approved_risk_contract_exists(
    *,
    official_lane_key: str,
    risk_contract_config_path: str | Path | None,
) -> bool:
    path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    contracts = payload.get("risk_contracts") if isinstance(payload, Mapping) else []
    symbol, timeframe, direction, entry_mode = _lane_parts(official_lane_key)
    for contract in contracts if isinstance(contracts, list) else []:
        if not isinstance(contract, Mapping):
            continue
        same_lane = (
            str(contract.get("symbol") or "") == symbol
            and str(contract.get("timeframe") or "") == timeframe
            and str(contract.get("direction") or "") == direction
            and str(contract.get("entry_mode") or "") == entry_mode
        )
        approved = contract.get("approved") is True or str(contract.get("approval_status") or "") == "APPROVED"
        if same_lane and approved:
            return True
    return False


def _find_lane_row(rows: Any, lane_key: str) -> dict[str, Any]:
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, Mapping) and str(row.get("lane_key") or "") == lane_key:
            return dict(row)
    return {}


def _target_scope(lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "paper_only": True,
        "live_authorized": False,
        "tiny_live_ready_packet_only": True,
    }


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key or "").split("|")
    return (
        parts[0] if len(parts) > 0 else "",
        parts[1] if len(parts) > 1 else "",
        parts[2] if len(parts) > 2 else "",
        parts[3] if len(parts) > 3 else "",
    )


def _signal_timestamp(signal_id: str | None) -> str | None:
    if not signal_id:
        return None
    parts = str(signal_id).split("|")
    if len(parts) < 4:
        return None
    candidate = parts[3]
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat()
    except ValueError:
        return None


def _number_or_none(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _empty_capture_recheck() -> dict[str, Any]:
    return {
        "fresh_capture_count": 0,
        "required_fresh_capture_count": 10,
        "threshold_met": False,
        "threshold_status": None,
        "unique_capture_count": 0,
        "latest_captured_signal_id": None,
        "latest_capture_timestamp": None,
        "captured_signal_ids": [],
        "official_lane_key": OFFICIAL_LANE_KEY,
        "official_lane_unchanged": True,
        "evidence_threshold_ready": False,
        "old_recommendation_reconciled": RUN_R177_EVIDENCE_THRESHOLD_RECHECK,
        "modern_path": MODERN_PATH,
    }


def _empty_fisherman_recheck() -> dict[str, Any]:
    return {
        "latest_heartbeat_found": False,
        "heartbeat_age_seconds": None,
        "stale_after_seconds": DEFAULT_WATCHER_STALE_AFTER_SECONDS,
        "watcher_likely_running": False,
        "watcher_stale": False,
        "latest_heartbeat_status": None,
        "fisherman_ready": False,
    }


def _empty_evidence_quality() -> dict[str, Any]:
    return {
        "lane_outcome_context_found": False,
        "capture_priority_context_found": False,
        "known_outcome_count": None,
        "win_rate_pct": None,
        "combined_watch_score": None,
        "quality_status": "UNKNOWN",
        "notes": [],
    }


def _empty_track_b_context() -> dict[str, Any]:
    return {
        "track_b_structurally_complete_for_now": False,
        "waiting_for_data_not_architecture": False,
        "betrayal_live_authorized": False,
        "betrayal_promoted": False,
        "track_b_action_required_now": False,
    }


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set any lane tiny_live",
        "write risk contract config",
        "transfer",
        "withdraw",
        "betrayal live promotion",
    ]


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
