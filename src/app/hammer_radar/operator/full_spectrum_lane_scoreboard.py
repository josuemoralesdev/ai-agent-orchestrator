"""R231 full-spectrum lane scoreboard / tiny-live alternate audit.

This module reads local paper ledgers only. It never calls Binance/network,
mutates env/config/lane/risk state, creates order payloads, promotes lanes, or
authorizes live execution.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.capture_count_sync_8m_short import (
    DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    build_capture_count_sync_8m_short,
    load_capture_count_sync_records,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_harvester_expansion import (
    load_full_spectrum_harvester_records,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import (
    load_short_paper_evidence_capture_records,
)
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY, MIN_FRESH_CANDIDATES

FULL_SPECTRUM_LANE_SCOREBOARD_READY = "FULL_SPECTRUM_LANE_SCOREBOARD_READY"
FULL_SPECTRUM_LANE_SCOREBOARD_REJECTED = "FULL_SPECTRUM_LANE_SCOREBOARD_REJECTED"
FULL_SPECTRUM_LANE_SCOREBOARD_RECORDED = "FULL_SPECTRUM_LANE_SCOREBOARD_RECORDED"
FULL_SPECTRUM_LANE_SCOREBOARD_BLOCKED = "FULL_SPECTRUM_LANE_SCOREBOARD_BLOCKED"
FULL_SPECTRUM_LANE_SCOREBOARD_ERROR = "FULL_SPECTRUM_LANE_SCOREBOARD_ERROR"

LANE_SCOREBOARD_READY = "LANE_SCOREBOARD_READY"
OFFICIAL_TINY_LIVE_STILL_LEADING = "OFFICIAL_TINY_LIVE_STILL_LEADING"
ALTERNATE_CANDIDATES_FOUND = "ALTERNATE_CANDIDATES_FOUND"
LANE_SCOREBOARD_DATA_GAPS_REMAIN = "LANE_SCOREBOARD_DATA_GAPS_REMAIN"
TINY_LIVE_THRESHOLD_MET = "TINY_LIVE_THRESHOLD_MET"
TINY_LIVE_THRESHOLD_NOT_MET = "TINY_LIVE_THRESHOLD_NOT_MET"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

OFFICIAL_CANDIDATE = "OFFICIAL_CANDIDATE"
ALTERNATE_WATCHLIST = "ALTERNATE_WATCHLIST"
TOO_FEW_UNIQUE_CAPTURES = "TOO_FEW_UNIQUE_CAPTURES"
OUTCOME_DATA_MISSING = "OUTCOME_DATA_MISSING"
ENTRY_MODE_MISSING = "ENTRY_MODE_MISSING"
NOT_ELIGIBLE = "NOT_ELIGIBLE"

EVENT_TYPE = "FULL_SPECTRUM_LANE_SCOREBOARD"
LEDGER_FILENAME = "full_spectrum_lane_scoreboard.ndjson"
CONFIRM_FULL_SPECTRUM_LANE_SCOREBOARD_RECORDING_PHRASE = (
    "I CONFIRM FULL SPECTRUM LANE SCOREBOARD RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_THRESHOLD_REQUIRED_COUNT = MIN_FRESH_CANDIDATES
DEFAULT_OFFICIAL_TINY_LIVE_LANE = DEFAULT_TARGET_LANE_KEY

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
    "ledger_rewritten": False,
    "destructive_write": False,
    "historical_ledger_rewritten": False,
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
    "signal_origin_promoted": False,
    "lane_promoted": False,
    "official_tiny_live_lane_changed": False,
    "alternate_lane_promoted": False,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/full_spectrum_harvester_expansion.ndjson",
    "logs/hammer_radar_forward/multi_lane_paper_harvester.ndjson",
    "logs/hammer_radar_forward/short_paper_evidence_capture.ndjson",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    "logs/hammer_radar_forward/paper_outcomes.ndjson",
    "logs/hammer_radar_forward/outcomes.ndjson",
    "logs/hammer_radar_forward/strategy_performance.ndjson",
    "logs/hammer_radar_forward/strategy_promotion_status.ndjson",
    "logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_full_spectrum_lane_scoreboard(
    *,
    log_dir: str | Path | None = None,
    record_scoreboard: bool = False,
    confirm_full_spectrum_lane_scoreboard: str | None = None,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_full_spectrum_lane_scoreboard == CONFIRM_FULL_SPECTRUM_LANE_SCOREBOARD_RECORDING_PHRASE
    )
    try:
        full_spectrum_records = load_full_spectrum_capture_records(log_dir=resolved_log_dir, limit=0)
        short_capture_records = load_short_capture_records(log_dir=resolved_log_dir, limit=0)
        signal_flow_records = load_signal_flow_records(log_dir=resolved_log_dir, limit=0)
        paper_outcome_records = load_paper_outcome_records(log_dir=resolved_log_dir, limit=0)
        tiny_live_sync = load_tiny_live_capture_count_sync(log_dir=resolved_log_dir)

        signal_counts = build_lane_signal_counts(signal_flow_records)
        capture_counts = build_lane_capture_counts([*full_spectrum_records, *short_capture_records])
        outcome_counts = build_lane_outcome_counts(paper_outcome_records)
        rows = rank_lane_score_rows(
            build_lane_score_rows(
                signal_counts=signal_counts,
                capture_counts=capture_counts,
                outcome_counts=outcome_counts,
                official_tiny_live_lane=official_tiny_live_lane,
                threshold_required_count=threshold_required_count,
                stale_after_seconds=stale_after_seconds,
                now=generated_at,
            )
        )
        official_status = _official_tiny_live_lane_status(
            tiny_live_sync=tiny_live_sync,
            official_tiny_live_lane=official_tiny_live_lane,
            threshold_required_count=threshold_required_count,
        )
        alternate_report = build_tiny_live_alternate_candidate_report(
            rows,
            official_tiny_live_lane=official_tiny_live_lane,
        )
        gap_report = build_lane_scoreboard_gap_report(rows)
        recommendations = build_lane_scoreboard_recommendations(
            official_tiny_live_lane_status=official_status,
            alternate_candidate_report=alternate_report,
            gap_report=gap_report,
        )
        scoreboard_status = classify_full_spectrum_lane_scoreboard_status(
            rows,
            official_tiny_live_lane_status=official_status,
            alternate_candidate_report=alternate_report,
            gap_report=gap_report,
        )
        status = FULL_SPECTRUM_LANE_SCOREBOARD_READY
        if not rows:
            status = FULL_SPECTRUM_LANE_SCOREBOARD_BLOCKED
        if record_scoreboard and not confirmation_valid:
            status = FULL_SPECTRUM_LANE_SCOREBOARD_REJECTED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "scoreboard_recorded": False,
            "scoreboard_id": None,
            "record_scoreboard_requested": bool(record_scoreboard),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "paper_only": True,
                "live_authorized": False,
                "official_tiny_live_lane": official_tiny_live_lane,
            },
            "input_summary": {
                "full_spectrum_records_found": bool(full_spectrum_records),
                "short_capture_records_found": bool(short_capture_records),
                "signal_flow_records_found": bool(signal_flow_records),
                "paper_outcome_records_found": bool(paper_outcome_records),
                "tiny_live_capture_sync_found": bool(tiny_live_sync),
                "strategy_performance_records_found": bool(
                    _read_ndjson_records(resolved_log_dir / "strategy_performance.ndjson", limit=1)
                ),
                "strategy_promotion_status_records_found": bool(
                    _read_ndjson_records(resolved_log_dir / "strategy_promotion_status.ndjson", limit=1)
                ),
            },
            "official_tiny_live_lane_status": official_status,
            "lane_scoreboard_rows": rows,
            "tiny_live_alternate_candidate_report": alternate_report,
            "lane_scoreboard_gap_report": gap_report,
            "lane_scoreboard_recommendations": recommendations,
            "scoreboard_status": scoreboard_status,
            "recommended_next_operator_move": _recommended_next_operator_move(
                official_tiny_live_lane_status=official_status,
                alternate_candidate_report=alternate_report,
                gap_report=gap_report,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(
                alternate_candidate_report=alternate_report,
                gap_report=gap_report,
            ),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_scoreboard and confirmation_valid:
            record = append_full_spectrum_lane_scoreboard_record(payload, log_dir=resolved_log_dir)
            payload["status"] = FULL_SPECTRUM_LANE_SCOREBOARD_RECORDED
            payload["scoreboard_recorded"] = True
            payload["scoreboard_id"] = record["scoreboard_id"]
            payload["ledger_path"] = str(full_spectrum_lane_scoreboard_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": FULL_SPECTRUM_LANE_SCOREBOARD_ERROR,
                "generated_at": generated_at.isoformat(),
                "scoreboard_recorded": False,
                "scoreboard_id": None,
                "record_scoreboard_requested": bool(record_scoreboard),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "paper_only": True,
                    "live_authorized": False,
                    "official_tiny_live_lane": official_tiny_live_lane,
                },
                "input_summary": {
                    "full_spectrum_records_found": False,
                    "short_capture_records_found": False,
                    "signal_flow_records_found": False,
                    "paper_outcome_records_found": False,
                    "tiny_live_capture_sync_found": False,
                },
                "official_tiny_live_lane_status": _empty_official_status(
                    official_tiny_live_lane,
                    threshold_required_count=threshold_required_count,
                ),
                "lane_scoreboard_rows": [],
                "tiny_live_alternate_candidate_report": {
                    "official_lane_still_best": False,
                    "alternate_candidates_found": False,
                    "top_alternates": [],
                    "why": "Scoreboard build failed before alternate ranking.",
                },
                "lane_scoreboard_gap_report": _empty_gap_report(),
                "lane_scoreboard_recommendations": [],
                "scoreboard_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R231 scoreboard error before using lane rankings.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_full_spectrum_capture_records(*, log_dir: str | Path | None = None, limit: int = 0) -> list[dict[str, Any]]:
    records = load_full_spectrum_harvester_records(log_dir=log_dir, limit=limit)
    return extract_lane_events(records, source_family="full_spectrum_capture")


def load_short_capture_records(*, log_dir: str | Path | None = None, limit: int = 0) -> list[dict[str, Any]]:
    records = load_short_paper_evidence_capture_records(log_dir=log_dir, limit=limit)
    return extract_lane_events(records, source_family="short_capture")


def load_signal_flow_records(*, log_dir: str | Path | None = None, limit: int = 0) -> list[dict[str, Any]]:
    resolved = get_log_dir(log_dir, use_env=True)
    records = [
        *_read_ndjson_records(resolved / "signals.ndjson", limit=limit),
        *_read_ndjson_records(resolved / "multi_symbol_paper_scans.ndjson", limit=limit),
    ]
    return [_signal_flow_row(record) for record in records if _signal_flow_row(record).get("lane_key")]


def load_paper_outcome_records(*, log_dir: str | Path | None = None, limit: int = 0) -> list[dict[str, Any]]:
    resolved = get_log_dir(log_dir, use_env=True)
    records = [
        *_read_ndjson_records(resolved / "paper_outcomes.ndjson", limit=limit),
        *_read_ndjson_records(resolved / "outcomes.ndjson", limit=limit),
    ]
    return [_outcome_row(record) for record in records if _outcome_row(record).get("lane_key")]


def load_tiny_live_capture_count_sync(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_capture_count_sync_records(log_dir=log_dir, limit=1)
    if records:
        return records[0]
    return build_capture_count_sync_8m_short(log_dir=log_dir)


def normalize_lane_key(symbol: object, timeframe: object, direction: object, entry_mode: object | None = None) -> str:
    normalized_entry = str(entry_mode or "entry_unknown").strip().lower() or "entry_unknown"
    return "|".join(
        [
            str(symbol or "").strip().upper(),
            str(timeframe or "").strip().lower(),
            str(direction or "").strip().lower(),
            normalized_entry,
        ]
    )


def parse_signal_id_for_lane(signal_id: object) -> dict[str, Any]:
    parts = str(signal_id or "").split("|")
    symbol = parts[0] if len(parts) > 0 else ""
    timeframe = parts[1] if len(parts) > 1 else ""
    direction = parts[2] if len(parts) > 2 else ""
    entry_mode = parts[3] if len(parts) > 4 else "entry_unknown"
    timestamp = parts[-1] if len(parts) >= 4 else None
    return {
        "symbol": str(symbol).strip().upper(),
        "timeframe": str(timeframe).strip().lower(),
        "direction": str(direction).strip().lower(),
        "entry_mode": str(entry_mode or "entry_unknown").strip().lower(),
        "lane_key": normalize_lane_key(symbol, timeframe, direction, entry_mode),
        "timestamp": timestamp,
    }


def extract_lane_events(records: Sequence[Mapping[str, Any]], *, source_family: str = "capture") -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for record in records:
        direct = _capture_event_from_record(record, source_family=source_family)
        if direct:
            events.append(direct)
        for candidate in _iter_capture_candidates(record):
            event = _capture_event_from_record(candidate, source_family=source_family, parent=record)
            if event:
                events.append(event)
        if not direct and not list(_iter_capture_candidates(record)):
            for lane_key in _iter_captured_lane_keys(record):
                parsed = _lane_from_key(lane_key)
                if parsed["lane_key"]:
                    events.append(
                        {
                            **parsed,
                            "signal_id": None,
                            "captured_signal_id": None,
                            "capture_at": _first_present(record, "recorded_at_utc", "generated_at"),
                            "source_family": source_family,
                        }
                    )
    return [_sanitize(event) for event in events]


def build_lane_signal_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = defaultdict(lambda: {"signal_flow_count": 0, "latest_signal_at": None})
    for record in records:
        lane_key = str(record.get("lane_key") or "")
        if not lane_key:
            continue
        counts[lane_key]["signal_flow_count"] += 1
        counts[lane_key]["latest_signal_at"] = _latest_iso(counts[lane_key]["latest_signal_at"], record.get("signal_at"))
    return dict(counts)


def build_lane_capture_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"capture_event_count": 0, "unique_capture_count": 0, "latest_capture_at": None, "unique_signal_ids": []}
    )
    seen_by_lane: dict[str, set[str]] = defaultdict(set)
    for record in records:
        lane_key = str(record.get("lane_key") or "")
        if not lane_key:
            continue
        counts[lane_key]["capture_event_count"] += 1
        counts[lane_key]["latest_capture_at"] = _latest_iso(counts[lane_key]["latest_capture_at"], record.get("capture_at"))
        signal_id = str(record.get("captured_signal_id") or record.get("signal_id") or "").strip()
        if signal_id and signal_id not in seen_by_lane[lane_key]:
            seen_by_lane[lane_key].add(signal_id)
            counts[lane_key]["unique_signal_ids"].append(signal_id)
            counts[lane_key]["unique_capture_count"] = len(seen_by_lane[lane_key])
    return dict(counts)


def build_lane_outcome_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "paper_outcome_count": 0,
            "known_outcome_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "outcome_unknown_count": 0,
            "latest_outcome_at": None,
        }
    )
    for record in records:
        lane_key = str(record.get("lane_key") or "")
        if not lane_key:
            continue
        row = counts[lane_key]
        row["paper_outcome_count"] += 1
        row["latest_outcome_at"] = _latest_iso(row["latest_outcome_at"], record.get("outcome_at"))
        outcome = str(record.get("outcome") or "").strip().lower()
        if outcome == "win":
            row["known_outcome_count"] += 1
            row["win_count"] += 1
        elif outcome in {"loss", "lose", "lost"}:
            row["known_outcome_count"] += 1
            row["loss_count"] += 1
        else:
            row["outcome_unknown_count"] += 1
    return dict(counts)


def build_lane_score_rows(
    *,
    signal_counts: Mapping[str, Mapping[str, Any]],
    capture_counts: Mapping[str, Mapping[str, Any]],
    outcome_counts: Mapping[str, Mapping[str, Any]],
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
    threshold_required_count: int = DEFAULT_THRESHOLD_REQUIRED_COUNT,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    lanes = set(signal_counts) | set(capture_counts) | set(outcome_counts)
    rows = []
    generated_at = now or datetime.now(UTC)
    for lane_key in lanes:
        lane = _lane_from_key(lane_key)
        signals = dict(signal_counts.get(lane_key) or {})
        captures = dict(capture_counts.get(lane_key) or {})
        outcomes = dict(outcome_counts.get(lane_key) or {})
        known = int(outcomes.get("known_outcome_count") or 0)
        wins = int(outcomes.get("win_count") or 0)
        unique_captures = int(captures.get("unique_capture_count") or 0)
        row = {
            "rank": None,
            "lane_key": lane_key,
            "symbol": lane["symbol"],
            "timeframe": lane["timeframe"],
            "direction": lane["direction"],
            "entry_mode": lane["entry_mode"],
            "signal_flow_count": int(signals.get("signal_flow_count") or 0),
            "capture_event_count": int(captures.get("capture_event_count") or 0),
            "unique_capture_count": unique_captures,
            "latest_signal_at": signals.get("latest_signal_at"),
            "latest_capture_at": captures.get("latest_capture_at"),
            "latest_outcome_at": outcomes.get("latest_outcome_at"),
            "paper_outcome_count": int(outcomes.get("paper_outcome_count") or 0),
            "known_outcome_count": known,
            "win_count": wins,
            "loss_count": int(outcomes.get("loss_count") or 0),
            "win_rate_pct": round((wins / known) * 100, 2) if known > 0 else None,
            "outcome_unknown_count": int(outcomes.get("outcome_unknown_count") or 0),
            "threshold_required_count": int(threshold_required_count),
            "threshold_distance_remaining": max(0, int(threshold_required_count) - unique_captures),
            "freshness_status": _freshness_status(
                captures.get("latest_capture_at") or signals.get("latest_signal_at"),
                now=generated_at,
                stale_after_seconds=stale_after_seconds,
            ),
            "tiny_live_candidate_status": NOT_ELIGIBLE,
            "score_notes": [],
            "live_authorized": False,
            "promotion_allowed": False,
        }
        row["tiny_live_candidate_status"] = _candidate_status(row, official_tiny_live_lane=official_tiny_live_lane)
        row["score_notes"] = _score_notes(row)
        rows.append(row)
    return rows


def rank_lane_score_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ranked = [dict(row) for row in rows]
    ranked.sort(
        key=lambda row: (
            -int(row.get("unique_capture_count") or 0),
            _freshness_rank(str(row.get("freshness_status") or "")),
            -int(row.get("signal_flow_count") or 0),
            -int(row.get("paper_outcome_count") or 0),
            -(float(row.get("win_rate_pct")) if row.get("win_rate_pct") is not None else -1.0),
            str(row.get("lane_key") or ""),
        )
    )
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return _sanitize(ranked)


def build_tiny_live_alternate_candidate_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    official_tiny_live_lane: str = DEFAULT_OFFICIAL_TINY_LIVE_LANE,
) -> dict[str, Any]:
    official = next((row for row in rows if row.get("lane_key") == official_tiny_live_lane), None)
    official_rank = int(official.get("rank") or 999999) if official else None
    alternates = [
        _alternate_row(row)
        for row in rows
        if row.get("lane_key") != official_tiny_live_lane
        and row.get("entry_mode") != "entry_unknown"
        and int(row.get("unique_capture_count") or 0) >= int(row.get("threshold_required_count") or DEFAULT_THRESHOLD_REQUIRED_COUNT)
    ][:10]
    return {
        "official_lane_still_best": official_rank == 1,
        "alternate_candidates_found": bool(alternates),
        "top_alternates": alternates,
        "why": _alternate_why(official_rank=official_rank, alternates=alternates),
    }


def build_lane_scoreboard_gap_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    missing_entry = [row for row in rows if row.get("entry_mode") == "entry_unknown"]
    missing_outcomes = [row for row in rows if int(row.get("known_outcome_count") or 0) == 0]
    signal_no_capture = [
        row for row in rows if int(row.get("signal_flow_count") or 0) > 0 and int(row.get("unique_capture_count") or 0) == 0
    ]
    near_threshold = [
        {
            "lane_key": row.get("lane_key"),
            "unique_capture_count": row.get("unique_capture_count"),
            "threshold_distance_remaining": row.get("threshold_distance_remaining"),
        }
        for row in rows
        if 0 < int(row.get("threshold_distance_remaining") or 0) <= 3
    ][:20]
    return {
        "lanes_missing_entry_mode": len(missing_entry),
        "lanes_missing_entry_mode_keys": [row.get("lane_key") for row in missing_entry[:20]],
        "lanes_missing_outcomes": len(missing_outcomes),
        "lanes_with_signal_flow_but_no_unique_captures": len(signal_no_capture),
        "lanes_near_threshold": near_threshold,
        "hard_live_blockers": [
            "R231 is audit-only and cannot authorize live.",
            "No alternate lane can be promoted by scoreboard score.",
            "Funding must wait until the official protected path says otherwise.",
            "Risk contract readiness must wait until the official protected path says otherwise.",
        ],
    }


def build_lane_scoreboard_recommendations(
    *,
    official_tiny_live_lane_status: Mapping[str, Any],
    alternate_candidate_report: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations = [
        {
            "priority": "HIGH",
            "recommended_action": "KEEP_8M_SHORT_AS_OFFICIAL",
            "future_phase": "R228",
            "why": "R231 is an audit and keeps the official tiny-live lane unchanged.",
        }
    ]
    if official_tiny_live_lane_status.get("threshold_met"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RUN_R228_IF_10_OF_10",
                "future_phase": "R228",
                "why": "Official lane unique capture threshold is met in local sync evidence; still no live authorization.",
            }
        )
    if alternate_candidate_report.get("alternate_candidates_found"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "WATCH_ALTERNATE_LANE",
                "future_phase": "R232",
                "why": "At least one non-official lane crossed the unique capture threshold and needs outcome/blocker enrichment.",
            }
        )
    if int(gap_report.get("lanes_missing_outcomes") or 0) > 0:
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "RUN_OUTCOME_ENRICHMENT",
                "future_phase": "R232",
                "why": "Some lanes have capture or signal flow without known paper win/loss evidence.",
            }
        )
    return recommendations


def classify_full_spectrum_lane_scoreboard_status(
    rows: Sequence[Mapping[str, Any]],
    *,
    official_tiny_live_lane_status: Mapping[str, Any],
    alternate_candidate_report: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> str:
    if official_tiny_live_lane_status.get("threshold_met") is True:
        return TINY_LIVE_THRESHOLD_MET
    if alternate_candidate_report.get("alternate_candidates_found"):
        return ALTERNATE_CANDIDATES_FOUND
    if alternate_candidate_report.get("official_lane_still_best"):
        return OFFICIAL_TINY_LIVE_STILL_LEADING
    if int(gap_report.get("lanes_missing_outcomes") or 0) > 0 or int(gap_report.get("lanes_missing_entry_mode") or 0) > 0:
        return LANE_SCOREBOARD_DATA_GAPS_REMAIN
    if rows:
        return TINY_LIVE_THRESHOLD_NOT_MET
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_full_spectrum_lane_scoreboard_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = full_spectrum_lane_scoreboard_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "scoreboard_id": str(record.get("scoreboard_id") or f"r231_full_spectrum_lane_scoreboard_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "official_tiny_live_lane_status": dict(record.get("official_tiny_live_lane_status") or {}),
            "lane_scoreboard_rows": list(record.get("lane_scoreboard_rows") or []),
            "tiny_live_alternate_candidate_report": dict(record.get("tiny_live_alternate_candidate_report") or {}),
            "lane_scoreboard_gap_report": dict(record.get("lane_scoreboard_gap_report") or {}),
            "lane_scoreboard_recommendations": list(record.get("lane_scoreboard_recommendations") or []),
            "scoreboard_status": record.get("scoreboard_status"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_full_spectrum_lane_scoreboard_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return [_sanitize(record) for record in _read_ndjson_records(full_spectrum_lane_scoreboard_records_path(get_log_dir(log_dir, use_env=True)), limit=limit)]


def summarize_full_spectrum_lane_scoreboard_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "latest_scoreboard_id": latest.get("scoreboard_id") if latest else None,
        "latest_scoreboard_status": latest.get("scoreboard_status") if latest else None,
        "safety": dict(SAFETY),
    }


def full_spectrum_lane_scoreboard_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_full_spectrum_lane_scoreboard_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _official_tiny_live_lane_status(
    *,
    tiny_live_sync: Mapping[str, Any],
    official_tiny_live_lane: str,
    threshold_required_count: int,
) -> dict[str, Any]:
    capture = dict(tiny_live_sync.get("capture_count") or {})
    watcher = dict(tiny_live_sync.get("watcher_status") or {})
    count = int(capture.get("fresh_capture_count") or 0)
    required = int(capture.get("required_fresh_capture_count") or threshold_required_count)
    return {
        "lane_key": official_tiny_live_lane,
        "fresh_capture_count": count,
        "required_fresh_capture_count": required,
        "threshold_met": bool(capture.get("threshold_met")) or count >= required,
        "threshold_distance_remaining": max(0, required - count),
        "watcher_likely_running": bool(watcher.get("watcher_likely_running")),
        "watcher_stale": bool(watcher.get("watcher_stale")),
        "fisherman_status": "FISHERMAN_RUNNING_RECENT"
        if watcher.get("watcher_likely_running") and not watcher.get("watcher_stale")
        else "FISHERMAN_NEEDS_REVIEW",
        "ledger_mismatch_found": False,
        "funding_should_wait": True,
        "risk_contract_should_wait": True,
    }


def _empty_official_status(lane_key: str, *, threshold_required_count: int) -> dict[str, Any]:
    return {
        "lane_key": lane_key,
        "fresh_capture_count": 0,
        "required_fresh_capture_count": int(threshold_required_count),
        "threshold_met": False,
        "threshold_distance_remaining": int(threshold_required_count),
        "watcher_likely_running": False,
        "watcher_stale": False,
        "funding_should_wait": True,
        "risk_contract_should_wait": True,
    }


def _empty_gap_report() -> dict[str, Any]:
    return {
        "lanes_missing_entry_mode": 0,
        "lanes_missing_outcomes": 0,
        "lanes_with_signal_flow_but_no_unique_captures": 0,
        "lanes_near_threshold": [],
        "hard_live_blockers": [],
    }


def _capture_event_from_record(
    record: Mapping[str, Any],
    *,
    source_family: str,
    parent: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if source_family == "short_capture" and record.get("paper_evidence_captured") is not True:
        return None
    lane_key = str(record.get("captured_lane_key") or record.get("lane_key") or "")
    lane = record.get("target_lane")
    if not lane_key and isinstance(lane, Mapping):
        lane_key = str(lane.get("lane_key") or "")
    signal_id = str(record.get("captured_signal_id") or record.get("signal_id") or record.get("candidate_id") or "")
    parsed = _lane_from_key(lane_key) if lane_key else _lane_from_record_or_signal(record, signal_id)
    if not parsed["lane_key"]:
        return None
    parent_record = parent or record
    return {
        **parsed,
        "signal_id": signal_id or None,
        "captured_signal_id": signal_id or None,
        "capture_at": _first_present(record, "recorded_at_utc", "generated_at", "timestamp")
        or _first_present(parent_record, "recorded_at_utc", "generated_at"),
        "source_family": source_family,
    }


def _iter_capture_candidates(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidates: list[Mapping[str, Any]] = []
    for key in ("captured_candidates", "capturable_candidates"):
        value = record.get(key)
        if isinstance(value, list):
            candidates.extend([row for row in value if isinstance(row, Mapping)])
    summary = record.get("capture_summary")
    if isinstance(summary, Mapping):
        for key in ("captured_candidates", "capturable_candidates"):
            value = summary.get(key)
            if isinstance(value, list):
                candidates.extend([row for row in value if isinstance(row, Mapping)])
    for iteration in record.get("iteration_summaries") or []:
        if not isinstance(iteration, Mapping):
            continue
        summary = iteration.get("capture_summary")
        if isinstance(summary, Mapping):
            value = summary.get("captured_candidates")
            if isinstance(value, list):
                candidates.extend([row for row in value if isinstance(row, Mapping)])
    return candidates


def _iter_captured_lane_keys(record: Mapping[str, Any]) -> list[str]:
    keys: list[str] = []
    for value in (record.get("captured_lanes") or []):
        keys.append(str(value))
    summary = record.get("capture_summary")
    if isinstance(summary, Mapping):
        for value in summary.get("captured_lanes") or []:
            keys.append(str(value))
    return keys


def _signal_flow_row(record: Mapping[str, Any]) -> dict[str, Any]:
    signal_id = str(_first_present(record, "signal_id", "candidate_id", "id") or "")
    parsed = _lane_from_record_or_signal(record, signal_id)
    return {
        **parsed,
        "signal_id": signal_id or None,
        "signal_at": _first_present(record, "timestamp", "generated_at", "closed_at", "detected_at") or parsed.get("timestamp"),
    }


def _outcome_row(record: Mapping[str, Any]) -> dict[str, Any]:
    signal_id = str(_first_present(record, "signal_id", "candidate_id", "id") or "")
    parsed = _lane_from_record_or_signal(record, signal_id)
    return {
        **parsed,
        "signal_id": signal_id or None,
        "outcome": _first_present(record, "outcome", "result", "status"),
        "outcome_at": _first_present(record, "evaluated_at", "timestamp", "generated_at", "recorded_at_utc"),
    }


def _lane_from_record_or_signal(record: Mapping[str, Any], signal_id: str | None = None) -> dict[str, Any]:
    symbol = _first_present(record, "symbol", "base_symbol")
    timeframe = _first_present(record, "timeframe", "tf", "interval")
    direction = _normalize_direction(_first_present(record, "direction", "bias_direction", "side"))
    entry_mode = _first_present(record, "entry_mode", "mode")
    if symbol and timeframe and direction:
        return _lane_from_key(normalize_lane_key(symbol, timeframe, direction, entry_mode))
    if signal_id:
        return parse_signal_id_for_lane(signal_id)
    return _lane_from_key("")


def _lane_from_key(lane_key: object) -> dict[str, Any]:
    parts = str(lane_key or "").split("|")
    symbol = parts[0] if len(parts) > 0 else ""
    timeframe = parts[1] if len(parts) > 1 else ""
    direction = parts[2] if len(parts) > 2 else ""
    entry_mode = parts[3] if len(parts) > 3 and parts[3] else "entry_unknown"
    normalized = normalize_lane_key(symbol, timeframe, direction, entry_mode) if symbol and timeframe and direction else ""
    return {
        "lane_key": normalized,
        "symbol": str(symbol).strip().upper(),
        "timeframe": str(timeframe).strip().lower(),
        "direction": str(direction).strip().lower(),
        "entry_mode": str(entry_mode).strip().lower(),
    }


def _candidate_status(row: Mapping[str, Any], *, official_tiny_live_lane: str) -> str:
    if row.get("lane_key") == official_tiny_live_lane:
        return OFFICIAL_CANDIDATE
    if row.get("entry_mode") == "entry_unknown":
        return ENTRY_MODE_MISSING
    if int(row.get("unique_capture_count") or 0) < int(row.get("threshold_required_count") or DEFAULT_THRESHOLD_REQUIRED_COUNT):
        return TOO_FEW_UNIQUE_CAPTURES
    if int(row.get("known_outcome_count") or 0) <= 0:
        return OUTCOME_DATA_MISSING
    return ALTERNATE_WATCHLIST


def _score_notes(row: Mapping[str, Any]) -> list[str]:
    notes = []
    if int(row.get("signal_flow_count") or 0) > 0 and int(row.get("unique_capture_count") or 0) == 0:
        notes.append("signal flow is present but unique capture count is zero")
    if int(row.get("capture_event_count") or 0) > int(row.get("unique_capture_count") or 0):
        notes.append("capture event count is not used as unique capture count")
    if row.get("entry_mode") == "entry_unknown":
        notes.append("entry mode missing; not tiny-live eligible")
    if int(row.get("known_outcome_count") or 0) == 0:
        notes.append("known win/loss outcome data missing")
    notes.append("live_authorized=false")
    notes.append("promotion_allowed=false")
    return notes


def _alternate_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rank": row.get("rank"),
        "lane_key": row.get("lane_key"),
        "unique_capture_count": row.get("unique_capture_count"),
        "capture_event_count": row.get("capture_event_count"),
        "signal_flow_count": row.get("signal_flow_count"),
        "known_outcome_count": row.get("known_outcome_count"),
        "win_rate_pct": row.get("win_rate_pct"),
        "tiny_live_candidate_status": row.get("tiny_live_candidate_status"),
        "live_authorized": False,
        "promotion_allowed": False,
    }


def _alternate_why(*, official_rank: int | None, alternates: Sequence[Mapping[str, Any]]) -> str:
    if alternates and official_rank == 1:
        return "Official lane ranks first, but alternate lanes crossed the unique capture threshold for watchlist review only."
    if alternates:
        return "Non-official lanes crossed the unique capture threshold; R231 does not promote or authorize them."
    return "No non-official lane crossed the unique capture threshold with a known entry mode."


def _recommended_next_operator_move(
    *,
    official_tiny_live_lane_status: Mapping[str, Any],
    alternate_candidate_report: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> str:
    if official_tiny_live_lane_status.get("threshold_met"):
        return "RUN_R228_TINY_LIVE_10_OF_10_READY_PACKET"
    if alternate_candidate_report.get("alternate_candidates_found"):
        return "WATCH_ALTERNATE_LANES"
    if int(gap_report.get("lanes_missing_outcomes") or 0) > 0:
        return "RUN_R232_LANE_OUTCOME_ENRICHMENT"
    return "KEEP_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(
    *,
    alternate_candidate_report: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> str:
    if alternate_candidate_report.get("alternate_candidates_found") or int(gap_report.get("lanes_missing_outcomes") or 0) > 0:
        return "Build R232 lane outcome enrichment for top scoreboard lanes; no config writes, no live execution."
    return "Keep R231 scoreboard available while official 8m short continues collecting unique captures."


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
    ]


def _freshness_status(value: Any, *, now: datetime, stale_after_seconds: int) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return "unknown"
    return "fresh" if (now - parsed).total_seconds() <= int(stale_after_seconds) else "stale"


def _freshness_rank(status: str) -> int:
    return {"fresh": 0, "unknown": 1, "stale": 2}.get(status, 3)


def _latest_iso(current: Any, candidate: Any) -> str | None:
    current_dt = _parse_datetime(current)
    candidate_dt = _parse_datetime(candidate)
    if candidate_dt is None:
        return current if current else None
    if current_dt is None or candidate_dt > current_dt:
        return candidate_dt.isoformat()
    return current_dt.isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _normalize_direction(value: Any) -> str:
    direction = str(value or "").strip().lower()
    if direction in {"buy", "bull", "bullish"}:
        return "long"
    if direction in {"sell", "bear", "bearish"}:
        return "short"
    return direction


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _read_ndjson_records(path: Path, *, limit: int = 0) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if limit and limit > 0:
        return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=64_000_000)]
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(_sanitize(json.loads(line)))
    return records


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
