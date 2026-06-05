"""R203 anchor x signal-origin confluence matrix.

Paper-only audit that composes R201 anchor outcome deepening, R205 pattern lane
matrix review, R204 pattern Keter rescoring, and R192/R195 lane references.
It never calls Binance/network, creates payloads, mutates env/config, promotes
origins/lanes, creates position permission, or authorizes live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.anchor_outcome_deepening import (
    load_anchor_outcome_deepening_records,
)
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, normalize_lane_key
from src.app.hammer_radar.operator.lane_matrix_after_crow_outcome_feedback import (
    DEFAULT_HAMMER_KETER_SCORE,
    DEFAULT_PROJECTED_CROW_KETER_SCORE,
    load_lane_matrix_after_crow_outcome_feedback_records,
)
from src.app.hammer_radar.operator.lane_matrix_after_crow_rescoring import (
    load_lane_matrix_after_crow_rescoring_records,
)
from src.app.hammer_radar.operator.pattern_detector_family_expansion import DEFAULT_SYMBOL
from src.app.hammer_radar.operator.pattern_keter_rescoring_family import (
    load_pattern_keter_rescoring_family_records,
)
from src.app.hammer_radar.operator.pattern_lane_matrix_review import (
    load_pattern_lane_matrix_review_records,
)
from src.app.hammer_radar.operator.short_strategy_packet import TARGET_ENTRY_MODE

ANCHOR_SIGNAL_CONFLUENCE_MATRIX_READY = "ANCHOR_SIGNAL_CONFLUENCE_MATRIX_READY"
ANCHOR_SIGNAL_CONFLUENCE_MATRIX_REJECTED = "ANCHOR_SIGNAL_CONFLUENCE_MATRIX_REJECTED"
ANCHOR_SIGNAL_CONFLUENCE_MATRIX_RECORDED = "ANCHOR_SIGNAL_CONFLUENCE_MATRIX_RECORDED"
ANCHOR_SIGNAL_CONFLUENCE_MATRIX_BLOCKED = "ANCHOR_SIGNAL_CONFLUENCE_MATRIX_BLOCKED"
ANCHOR_SIGNAL_CONFLUENCE_MATRIX_ERROR = "ANCHOR_SIGNAL_CONFLUENCE_MATRIX_ERROR"

SUMMARY_LEVEL_CONFLUENCE_AVAILABLE = "SUMMARY_LEVEL_CONFLUENCE_AVAILABLE"
EVENT_LEVEL_CONFLUENCE_AVAILABLE = "EVENT_LEVEL_CONFLUENCE_AVAILABLE"
EVENT_LEVEL_CONFLUENCE_NOT_AVAILABLE = "EVENT_LEVEL_CONFLUENCE_NOT_AVAILABLE"
CONFLUENCE_NEEDS_TIMESTAMP_MAPPING = "CONFLUENCE_NEEDS_TIMESTAMP_MAPPING"
CONFLUENCE_NOT_LIVE_AUTHORIZED = "CONFLUENCE_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "ANCHOR_SIGNAL_CONFLUENCE_MATRIX"
LEDGER_FILENAME = "anchor_signal_confluence_matrix.ndjson"
CONFIRM_ANCHOR_SIGNAL_CONFLUENCE_MATRIX_RECORDING_PHRASE = (
    "I CONFIRM ANCHOR SIGNAL CONFLUENCE MATRIX RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

PRIMARY_SIGNAL_ORIGINS = ("hammer_wick_reversal", "bearish_engulfing", "three_black_crows")
SECONDARY_SIGNAL_ORIGINS = (
    "exhaustion_wick",
    "bullish_engulfing",
    "three_white_soldiers",
    "golden_pocket_rejection",
    "rsi_divergence_bearish",
    "rsi_divergence_bullish",
)
BLOCKED_SIGNAL_ORIGINS = ("breakdown_retest", "breakout_retest")
TARGET_SIGNAL_ORIGINS = (*PRIMARY_SIGNAL_ORIGINS, *SECONDARY_SIGNAL_ORIGINS)
TARGET_ANCHOR_TYPES = ("SMA200", "WMA200", "custom_wma")
TARGET_ANCHOR_PERIODS = (13, 21, 34, 55, 89, 144, 200, 233, 377, 610, 888)
TARGET_TIMEFRAMES = ("4m", "8m", "13m", "22m", "44m", "55m", "88m", "222m", "444m", "666m", "888m", "4H", "13H", "13D")

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
    "pattern_family_live_authorized": False,
    "anchor_live_authorized": False,
    "confluence_live_authorized": False,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/anchor_outcome_deepening.ndjson",
    "logs/hammer_radar_forward/pattern_lane_matrix_review.ndjson",
    "logs/hammer_radar_forward/pattern_keter_rescoring_family.ndjson",
    "logs/hammer_radar_forward/lane_matrix_after_crow_outcome_feedback.ndjson",
    "logs/hammer_radar_forward/lane_matrix_after_crow_rescoring.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_anchor_signal_confluence_matrix(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    record_matrix: bool = False,
    confirm_anchor_signal_confluence: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    confirmation_valid = confirm_anchor_signal_confluence == CONFIRM_ANCHOR_SIGNAL_CONFLUENCE_MATRIX_RECORDING_PHRASE
    try:
        anchor_deepening = load_latest_anchor_outcome_deepening(log_dir=resolved_log_dir)
        lane_matrix = load_latest_pattern_lane_matrix_review(log_dir=resolved_log_dir)
        keter = load_latest_pattern_keter_rescoring(log_dir=resolved_log_dir)
        references = load_latest_crow_hammer_lane_references(log_dir=resolved_log_dir)
        signal_inputs = build_signal_origin_confluence_inputs(
            pattern_lane_matrix=lane_matrix,
            pattern_keter=keter,
            crow_hammer_lane_references=references,
            symbol=normalized_symbol,
        )
        anchor_inputs = build_anchor_confluence_inputs(anchor_deepening=anchor_deepening)
        event_preview = attempt_event_level_confluence_preview(anchor_inputs=anchor_inputs, signal_inputs=signal_inputs)
        rows = build_anchor_signal_confluence_rows(
            anchor_inputs=anchor_inputs,
            signal_inputs=signal_inputs,
            event_level_matches=event_preview,
        )
        rankings = build_anchor_signal_confluence_rankings(rows)
        quality = build_confluence_evidence_quality_report(rows)
        next_actions = build_confluence_next_actions(rows=rows, quality_report=quality)
        confluence_status = classify_anchor_signal_confluence_status(rows=rows, quality_report=quality)
        status = _status_for_matrix(
            record_matrix=record_matrix,
            confirmation_valid=confirmation_valid,
            has_inputs=bool(anchor_inputs) and bool(signal_inputs),
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "matrix_recorded": False,
            "matrix_id": None,
            "record_matrix_requested": bool(record_matrix),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "symbol": normalized_symbol,
                "signal_origins": list(TARGET_SIGNAL_ORIGINS),
                "blocked_signal_origins": list(BLOCKED_SIGNAL_ORIGINS),
                "anchor_types": list(TARGET_ANCHOR_TYPES),
                "anchor_periods": list(TARGET_ANCHOR_PERIODS),
                "timeframes": list(TARGET_TIMEFRAMES),
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "anchor_deepening_found": bool(anchor_deepening),
                "pattern_lane_matrix_found": bool(lane_matrix),
                "pattern_keter_found": bool(keter),
                "crow_hammer_lane_references_found": bool(references),
                "anchor_candidates_loaded": len(anchor_inputs),
                "signal_origin_candidates_loaded": len(signal_inputs),
                "event_level_matches_found": len(event_preview),
                "summary_level_matches_found": sum(1 for row in rows if row.get("confluence_resolution") == "summary_level"),
            },
            "confluence_evidence_quality_report": quality,
            "anchor_signal_confluence_rows": rows,
            "anchor_signal_confluence_rankings": rankings,
            "best_confluence_candidates": rankings[:10],
            "confluence_next_actions": next_actions,
            "confluence_status": confluence_status,
            "recommended_next_operator_move": _recommended_next_operator_move(confluence_status),
            "recommended_next_engineering_move": _recommended_next_engineering_move(confluence_status, quality),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "anchor_deepening_source": anchor_deepening.get("deepening_id") or anchor_deepening.get("deepening_source"),
            "pattern_lane_matrix_source": lane_matrix.get("matrix_id") or lane_matrix.get("matrix_source"),
            "pattern_keter_source": keter.get("rescore_id") or keter.get("rescore_source"),
        }
        if record_matrix and confirmation_valid and rows:
            record = append_anchor_signal_confluence_matrix_record(payload, log_dir=resolved_log_dir)
            payload["status"] = ANCHOR_SIGNAL_CONFLUENCE_MATRIX_RECORDED
            payload["matrix_recorded"] = True
            payload["matrix_id"] = record["matrix_id"]
            payload["ledger_path"] = str(anchor_signal_confluence_matrix_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": ANCHOR_SIGNAL_CONFLUENCE_MATRIX_ERROR,
                "generated_at": generated_at.isoformat(),
                "matrix_recorded": False,
                "matrix_id": None,
                "record_matrix_requested": bool(record_matrix),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _default_target_scope(normalized_symbol),
                "input_summary": {
                    "anchor_deepening_found": False,
                    "pattern_lane_matrix_found": False,
                    "pattern_keter_found": False,
                    "crow_hammer_lane_references_found": False,
                    "anchor_candidates_loaded": 0,
                    "signal_origin_candidates_loaded": 0,
                    "event_level_matches_found": 0,
                    "summary_level_matches_found": 0,
                },
                "confluence_evidence_quality_report": build_confluence_evidence_quality_report([]),
                "anchor_signal_confluence_rows": [],
                "anchor_signal_confluence_rankings": [],
                "best_confluence_candidates": [],
                "confluence_next_actions": build_confluence_next_actions(),
                "confluence_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R203 confluence matrix build error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_anchor_outcome_deepening(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    for record in load_anchor_outcome_deepening_records(log_dir=log_dir, limit=100):
        if isinstance(record.get("anchor_interaction_rankings"), list):
            latest = dict(record)
            latest["deepening_source"] = "anchor_outcome_deepening_ledger"
            return latest
    return {}


def load_latest_pattern_lane_matrix_review(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    for record in load_pattern_lane_matrix_review_records(log_dir=log_dir, limit=100):
        if isinstance(record.get("pattern_lane_pair_matrix"), list):
            latest = dict(record)
            latest["matrix_source"] = "pattern_lane_matrix_review_ledger"
            return latest
    return {}


def load_latest_pattern_keter_rescoring(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    for record in load_pattern_keter_rescoring_family_records(log_dir=log_dir, limit=100):
        if isinstance(record.get("pattern_origin_scorecards"), Mapping):
            latest = dict(record)
            latest["rescore_source"] = "pattern_keter_rescoring_family_ledger"
            return latest
    return {}


def load_latest_crow_hammer_lane_references(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    r195 = load_lane_matrix_after_crow_outcome_feedback_records(log_dir=log_dir, limit=100)
    for record in r195:
        comparison = record.get("post_outcome_pair_comparison")
        if isinstance(comparison, Mapping):
            latest = dict(record)
            latest["reference_source"] = "lane_matrix_after_crow_outcome_feedback_ledger"
            return latest
    r192 = load_lane_matrix_after_crow_rescoring_records(log_dir=log_dir, limit=100)
    for record in r192:
        if isinstance(record.get("lane_pair_comparison"), Mapping) or isinstance(record.get("pair_comparison"), Mapping):
            latest = dict(record)
            latest["reference_source"] = "lane_matrix_after_crow_rescoring_ledger"
            return latest
    return {}


def build_signal_origin_confluence_inputs(
    *,
    pattern_lane_matrix: Mapping[str, Any],
    pattern_keter: Mapping[str, Any],
    crow_hammer_lane_references: Mapping[str, Any] | None = None,
    symbol: str = DEFAULT_SYMBOL,
) -> list[dict[str, Any]]:
    cards = pattern_keter.get("pattern_origin_scorecards") if isinstance(pattern_keter.get("pattern_origin_scorecards"), Mapping) else {}
    reference = pattern_keter.get("reference_comparison") if isinstance(pattern_keter.get("reference_comparison"), Mapping) else {}
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in pattern_lane_matrix.get("pattern_lane_pair_matrix") or []:
        if not isinstance(row, Mapping):
            continue
        origin = str(row.get("signal_origin") or "")
        if origin not in (*TARGET_SIGNAL_ORIGINS, *BLOCKED_SIGNAL_ORIGINS):
            continue
        lane_key = str(row.get("lane_key") or "")
        if not lane_key:
            lane_key = normalize_lane_key(symbol, row.get("timeframe") or "unknown", row.get("direction") or "short", TARGET_ENTRY_MODE)
        key = (lane_key, origin)
        if key in seen:
            continue
        seen.add(key)
        rows.append(_signal_input_from_lane_row(row=row, card=cards.get(origin) if isinstance(cards, Mapping) else {}, reference=reference))
    for origin, card in (cards or {}).items():
        if origin not in TARGET_SIGNAL_ORIGINS and origin not in BLOCKED_SIGNAL_ORIGINS:
            continue
        if any(row["signal_origin"] == origin for row in rows):
            continue
        direction = _origin_direction_bias(str(origin))
        rows.append(
            {
                "lane_key": normalize_lane_key(symbol, "8m", direction, TARGET_ENTRY_MODE),
                "signal_origin": origin,
                "timeframe": "8m",
                "direction_bias": direction,
                "signal_score": _origin_score_from_card(str(origin), card, reference),
                "pair_score": _origin_score_from_card(str(origin), card, reference),
                "lane_score": 0,
                "configured_lane": False,
                "fresh_flow_status": "unknown",
                "pair_readiness": card.get("readiness") if isinstance(card, Mapping) else "UNKNOWN_NEEDS_MANUAL_REVIEW",
                "risk_warnings": list(card.get("risk_warnings") or []) if isinstance(card, Mapping) else [],
                "blocked": origin in BLOCKED_SIGNAL_ORIGINS,
                "event_timestamps": _extract_event_timestamps(card),
            }
        )
    for origin in BLOCKED_SIGNAL_ORIGINS:
        if any(row["signal_origin"] == origin for row in rows):
            continue
        rows.append(
            {
                "lane_key": normalize_lane_key(symbol, "8m", "short", TARGET_ENTRY_MODE),
                "signal_origin": origin,
                "timeframe": "8m",
                "direction_bias": "short",
                "signal_score": 0,
                "pair_score": 0,
                "lane_score": 0,
                "configured_lane": False,
                "fresh_flow_status": "unknown",
                "pair_readiness": "PATTERN_PAIR_REGISTRY_ONLY_BLOCKED",
                "risk_warnings": ["registry_only_until_retest_structure"],
                "blocked": True,
                "event_timestamps": [],
            }
        )
    return _sanitize(rows)


def build_anchor_confluence_inputs(*, anchor_deepening: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in anchor_deepening.get("anchor_interaction_rankings") or []:
        if not isinstance(row, Mapping):
            continue
        anchor_type = str(row.get("anchor_type") or "")
        period = _to_int(row.get("period"))
        timeframe = str(row.get("timeframe") or "")
        if anchor_type not in TARGET_ANCHOR_TYPES or period not in TARGET_ANCHOR_PERIODS:
            continue
        rows.append(
            {
                "timeframe": timeframe,
                "timeframe_key": _timeframe_key(timeframe),
                "anchor_type": anchor_type,
                "anchor_period": period,
                "anchor_interaction": str(row.get("interaction") or "unknown"),
                "direction_bias": str(row.get("direction_bias") or _anchor_direction_bias(row.get("interaction"))),
                "anchor_score": _to_float(row.get("score")),
                "sample_confidence": str(row.get("sample_confidence") or "LOW").upper(),
                "risk_warnings": list(row.get("risk_warnings") or []),
                "mapped_events": _to_int(row.get("mapped_events")),
                "event_timestamps": _extract_event_timestamps(row),
            }
        )
    return _sanitize(rows)


def match_summary_level_confluence(
    *,
    anchor_input: Mapping[str, Any],
    signal_input: Mapping[str, Any],
) -> dict[str, Any] | None:
    if _timeframe_key(anchor_input.get("timeframe")) != _timeframe_key(signal_input.get("timeframe")):
        return None
    if signal_input.get("blocked"):
        return {
            "confluence_resolution": "none",
            "why": "Blocked registry-only origin is kept blocked; no useful confluence is granted.",
        }
    return {
        "confluence_resolution": "summary_level",
        "why": (
            f"{signal_input.get('signal_origin')} overlaps {anchor_input.get('timeframe')} "
            f"{anchor_input.get('anchor_type')} period {anchor_input.get('anchor_period')} "
            f"{anchor_input.get('anchor_interaction')} at timeframe/source level only."
        ),
    }


def attempt_event_level_confluence_preview(
    *,
    anchor_inputs: Sequence[Mapping[str, Any]],
    signal_inputs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    matches = []
    for anchor in anchor_inputs:
        anchor_timestamps = set(anchor.get("event_timestamps") or [])
        if not anchor_timestamps:
            continue
        for signal in signal_inputs:
            if signal.get("blocked"):
                continue
            if _timeframe_key(anchor.get("timeframe")) != _timeframe_key(signal.get("timeframe")):
                continue
            overlap = sorted(anchor_timestamps.intersection(set(signal.get("event_timestamps") or [])))
            if overlap:
                matches.append(
                    {
                        "timeframe": anchor.get("timeframe"),
                        "signal_origin": signal.get("signal_origin"),
                        "anchor_type": anchor.get("anchor_type"),
                        "anchor_period": anchor.get("anchor_period"),
                        "anchor_interaction": anchor.get("anchor_interaction"),
                        "matched_timestamps": overlap[:10],
                        "match_count": len(overlap),
                    }
                )
    return _sanitize(matches)


def score_anchor_signal_confluence_row(
    *,
    signal_origin_score: float,
    anchor_score: float,
    lane_score: float,
    sample_confidence: str,
    confluence_resolution: str,
    direction_alignment: bool,
    risk_warnings: Sequence[str] | None = None,
    configured_lane: bool = False,
    fresh_flow: str = "unknown",
    blocked_origin: bool = False,
) -> int:
    confidence_score = {"HIGH": 100, "MEDIUM": 65, "LOW": 30}.get(str(sample_confidence).upper(), 20)
    resolution_score = {"event_level": 100, "summary_level": 60, "none": 0}.get(str(confluence_resolution), 0)
    alignment_score = 100 if direction_alignment else 25
    base = (
        (min(max(signal_origin_score, 0), 100) * 0.30)
        + (min(max(anchor_score * 4, 0), 100) * 0.25)
        + (min(max(lane_score, 0), 100) * 0.20)
        + (((confidence_score * 0.65) + (resolution_score * 0.35)) * 0.15)
        + (alignment_score * 0.10)
    )
    warnings = [str(warning) for warning in (risk_warnings or [])]
    penalty = 0
    if confluence_resolution == "summary_level":
        penalty += 8
    elif confluence_resolution == "none":
        penalty += 25
    if not direction_alignment:
        penalty += 12
    if fresh_flow == "stale_only":
        penalty += 8
    elif fresh_flow == "unknown":
        penalty += 4
    if not configured_lane:
        penalty += 5
    penalty += min(24, len(warnings) * 4)
    if any("VERY_HIGH_FAILURE_RATE" in warning or "failure_rate" in warning for warning in warnings):
        penalty += 8
    if any("adverse" in warning.lower() for warning in warnings):
        penalty += 6
    if blocked_origin:
        penalty += 60
    return int(round(max(0, min(100, base - penalty))))


def build_anchor_signal_confluence_rows(
    *,
    anchor_inputs: Sequence[Mapping[str, Any]],
    signal_inputs: Sequence[Mapping[str, Any]],
    event_level_matches: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    event_keys = {
        (
            _timeframe_key(match.get("timeframe")),
            str(match.get("signal_origin")),
            str(match.get("anchor_type")),
            _to_int(match.get("anchor_period")),
            str(match.get("anchor_interaction")),
        )
        for match in (event_level_matches or [])
    }
    rows = []
    for signal in signal_inputs:
        for anchor in anchor_inputs:
            summary = match_summary_level_confluence(anchor_input=anchor, signal_input=signal)
            if not summary:
                continue
            key = (
                _timeframe_key(anchor.get("timeframe")),
                str(signal.get("signal_origin")),
                str(anchor.get("anchor_type")),
                _to_int(anchor.get("anchor_period")),
                str(anchor.get("anchor_interaction")),
            )
            resolution = "event_level" if key in event_keys else summary["confluence_resolution"]
            direction_alignment = str(signal.get("direction_bias")) == str(anchor.get("direction_bias"))
            risk_warnings = list(dict.fromkeys([*(signal.get("risk_warnings") or []), *(anchor.get("risk_warnings") or [])]))
            score = score_anchor_signal_confluence_row(
                signal_origin_score=_to_float(signal.get("pair_score") or signal.get("signal_score")),
                anchor_score=_to_float(anchor.get("anchor_score")),
                lane_score=_to_float(signal.get("lane_score")),
                sample_confidence=str(anchor.get("sample_confidence") or "LOW"),
                confluence_resolution=resolution,
                direction_alignment=direction_alignment,
                risk_warnings=risk_warnings,
                configured_lane=bool(signal.get("configured_lane")),
                fresh_flow=str(signal.get("fresh_flow_status") or "unknown"),
                blocked_origin=bool(signal.get("blocked")),
            )
            why = _row_why(signal=signal, anchor=anchor, resolution=resolution, direction_alignment=direction_alignment)
            rows.append(
                {
                    "lane_key": signal.get("lane_key"),
                    "signal_origin": signal.get("signal_origin"),
                    "timeframe": anchor.get("timeframe"),
                    "direction_bias": signal.get("direction_bias"),
                    "anchor_type": anchor.get("anchor_type"),
                    "anchor_period": anchor.get("anchor_period"),
                    "anchor_interaction": anchor.get("anchor_interaction"),
                    "signal_score": _to_number(signal.get("pair_score") or signal.get("signal_score")),
                    "anchor_score": _round(_to_float(anchor.get("anchor_score"))),
                    "lane_score": _to_number(signal.get("lane_score")),
                    "confluence_score": score,
                    "confluence_resolution": resolution,
                    "sample_confidence": anchor.get("sample_confidence"),
                    "risk_warnings": risk_warnings,
                    "pair_readiness": signal.get("pair_readiness"),
                    "fresh_flow_status": signal.get("fresh_flow_status"),
                    "configured_lane": bool(signal.get("configured_lane")),
                    "direction_alignment": direction_alignment,
                    "paper_only": True,
                    "live_authorized": False,
                    "signal_origin_promoted": False,
                    "lane_promoted": False,
                    "confluence_live_authorized": False,
                    "position_permission_created": False,
                    "why": why,
                }
            )
    rows.sort(key=lambda row: (-_to_float(row.get("confluence_score")), row.get("signal_origin") or "", row.get("lane_key") or ""))
    return _sanitize(rows)


def build_anchor_signal_confluence_rankings(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rankings = []
    for rank, row in enumerate(
        sorted(rows, key=lambda item: (-_to_float(item.get("confluence_score")), str(item.get("signal_origin")))),
        start=1,
    ):
        action = "TRACK_PAPER"
        if row.get("confluence_resolution") == "summary_level":
            action = "DEEPEN_EVENT_MATCHING"
        if row.get("fresh_flow_status") in {"stale_only", "unknown"} and _to_float(row.get("confluence_score")) < 65:
            action = "COLLECT_MORE_FLOW"
        if row.get("pair_readiness") and "MIXED_BIAS" in str(row.get("pair_readiness")):
            action = "KEEP_REVIEW_ONLY"
        if row.get("confluence_resolution") == "none" or "registry_only" in " ".join(row.get("risk_warnings") or []):
            action = "KEEP_BLOCKED"
        rankings.append(
            {
                "rank": rank,
                "lane_key": row.get("lane_key"),
                "signal_origin": row.get("signal_origin"),
                "anchor_type": row.get("anchor_type"),
                "anchor_period": row.get("anchor_period"),
                "anchor_interaction": row.get("anchor_interaction"),
                "confluence_score": row.get("confluence_score"),
                "confluence_resolution": row.get("confluence_resolution"),
                "recommended_action": action,
                "why": row.get("why"),
            }
        )
    return _sanitize(rankings)


def build_confluence_evidence_quality_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "event_level_rows": sum(1 for row in rows if row.get("confluence_resolution") == "event_level"),
        "summary_level_rows": sum(1 for row in rows if row.get("confluence_resolution") == "summary_level"),
        "none_rows": sum(1 for row in rows if row.get("confluence_resolution") == "none"),
        "low_confidence_rows": sum(1 for row in rows if row.get("sample_confidence") == "LOW"),
        "risk_warning_rows": sum(1 for row in rows if row.get("risk_warnings")),
        "blocked_rows": sum(1 for row in rows if row.get("confluence_resolution") == "none" or "registry_only" in " ".join(row.get("risk_warnings") or [])),
        "paper_only_rows": sum(1 for row in rows if row.get("paper_only") is True),
        "live_authorized_rows": sum(1 for row in rows if row.get("live_authorized") is True),
        "summary_level_is_weaker_evidence": True,
    }


def build_confluence_next_actions(
    *,
    rows: Sequence[Mapping[str, Any]] | None = None,
    quality_report: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    quality = quality_report or build_confluence_evidence_quality_report(rows or [])
    actions = [
        {
            "priority": "HIGH",
            "future_phase": "R207",
            "action": "Build exact timestamp/candle-level matcher between anchor events and signal-origin detections.",
            "why": "Current confluence is summary-level unless exact event timestamps overlap.",
        },
        {
            "priority": "MEDIUM",
            "future_phase": "R206",
            "action": "Recheck tiny-live readiness gaps without using confluence as live authorization.",
            "why": "R203 improves paper evidence only; live blockers and kill-switch policy remain separate.",
        },
    ]
    if _to_int(quality.get("risk_warning_rows")):
        actions.append(
            {
                "priority": "MEDIUM",
                "future_phase": "R207",
                "action": "Carry risk warnings into event-level confluence matching and reject high-failure traps.",
                "why": "Anchor and pattern warnings materially reduce score quality.",
            }
        )
    return actions


def classify_anchor_signal_confluence_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    quality_report: Mapping[str, Any],
) -> str:
    if not rows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if _to_int(quality_report.get("event_level_rows")) > 0:
        return EVENT_LEVEL_CONFLUENCE_AVAILABLE
    if _to_int(quality_report.get("summary_level_rows")) > 0:
        return SUMMARY_LEVEL_CONFLUENCE_AVAILABLE
    return EVENT_LEVEL_CONFLUENCE_NOT_AVAILABLE


def append_anchor_signal_confluence_matrix_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = anchor_signal_confluence_matrix_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "matrix_id": str(record.get("matrix_id") or f"r203_anchor_signal_confluence_matrix_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": ANCHOR_SIGNAL_CONFLUENCE_MATRIX_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_matrix_requested": bool(record.get("record_matrix_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "confluence_evidence_quality_report": dict(record.get("confluence_evidence_quality_report") or {}),
            "anchor_signal_confluence_rows": list(record.get("anchor_signal_confluence_rows") or []),
            "anchor_signal_confluence_rankings": list(record.get("anchor_signal_confluence_rankings") or []),
            "best_confluence_candidates": list(record.get("best_confluence_candidates") or []),
            "confluence_next_actions": list(record.get("confluence_next_actions") or []),
            "confluence_status": record.get("confluence_status"),
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


def load_anchor_signal_confluence_matrix_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = anchor_signal_confluence_matrix_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_anchor_signal_confluence_matrix_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    top = (latest.get("anchor_signal_confluence_rankings") or [{}])[0] if isinstance(latest, Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "confluence_status_counts": dict(sorted(Counter(str(record.get("confluence_status") or "UNKNOWN") for record in records).items())),
        "last_matrix_id": latest.get("matrix_id") if isinstance(latest, Mapping) else None,
        "last_top_lane": top.get("lane_key") if isinstance(top, Mapping) else None,
        "last_top_origin": top.get("signal_origin") if isinstance(top, Mapping) else None,
        "safety": dict(SAFETY),
    }


def anchor_signal_confluence_matrix_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_anchor_signal_confluence_matrix_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _signal_input_from_lane_row(*, row: Mapping[str, Any], card: Any, reference: Mapping[str, Any]) -> dict[str, Any]:
    lane_key = str(row.get("lane_key") or "")
    parts = lane_key.split("|")
    timeframe = str(row.get("timeframe") or (parts[1] if len(parts) > 1 else ""))
    direction = str(row.get("direction") or (parts[2] if len(parts) > 2 else _origin_direction_bias(str(row.get("signal_origin")))))
    origin = str(row.get("signal_origin") or "")
    return {
        "lane_key": lane_key,
        "signal_origin": origin,
        "timeframe": timeframe,
        "direction_bias": direction,
        "signal_score": _origin_score_from_card(origin, card, reference),
        "pair_score": _to_float(row.get("pair_score") or row.get("origin_keter_score") or _origin_score_from_card(origin, card, reference)),
        "lane_score": _to_float(row.get("lane_score")),
        "configured_lane": bool(row.get("configured_lane")),
        "fresh_flow_status": str(row.get("fresh_flow_status") or "unknown"),
        "pair_readiness": row.get("pair_readiness"),
        "risk_warnings": list(row.get("risk_warnings") or []),
        "blocked": origin in BLOCKED_SIGNAL_ORIGINS or "REGISTRY_ONLY_BLOCKED" in str(row.get("pair_readiness")),
        "event_timestamps": _extract_event_timestamps(row),
    }


def _origin_score_from_card(origin: str, card: Any, reference: Mapping[str, Any]) -> float:
    if isinstance(card, Mapping) and card.get("keter_score") is not None:
        return _to_float(card.get("keter_score"))
    if origin == "hammer_wick_reversal":
        return _to_float(reference.get("hammer_wick_reversal_keter_score") or DEFAULT_HAMMER_KETER_SCORE)
    if origin == "three_black_crows":
        return _to_float(reference.get("three_black_crows_projected_score") or DEFAULT_PROJECTED_CROW_KETER_SCORE)
    return 0.0


def _origin_direction_bias(origin: str) -> str:
    if origin in {"bullish_engulfing", "three_white_soldiers", "rsi_divergence_bullish"}:
        return "long"
    return "short"


def _anchor_direction_bias(interaction: Any) -> str:
    value = str(interaction or "").lower()
    if "up" in value or "reclaim" in value:
        return "long"
    if "down" in value or "loss" in value:
        return "short"
    return "unknown"


def _row_why(*, signal: Mapping[str, Any], anchor: Mapping[str, Any], resolution: str, direction_alignment: bool) -> str:
    evidence = "exact event-level" if resolution == "event_level" else "summary-level"
    alignment = "aligns" if direction_alignment else "does not align"
    return (
        f"{signal.get('lane_key')} + {signal.get('signal_origin')} has {evidence} overlap with "
        f"{anchor.get('timeframe')} {anchor.get('anchor_type')} period {anchor.get('anchor_period')} "
        f"{anchor.get('anchor_interaction')}; signal direction {alignment} with anchor bias. "
        "Paper-only evidence; no live permission is created."
    )


def _status_for_matrix(*, record_matrix: bool, confirmation_valid: bool, has_inputs: bool) -> str:
    if not has_inputs:
        return ANCHOR_SIGNAL_CONFLUENCE_MATRIX_BLOCKED
    if record_matrix and not confirmation_valid:
        return ANCHOR_SIGNAL_CONFLUENCE_MATRIX_REJECTED
    if record_matrix and confirmation_valid:
        return ANCHOR_SIGNAL_CONFLUENCE_MATRIX_RECORDED
    return ANCHOR_SIGNAL_CONFLUENCE_MATRIX_READY


def _recommended_next_operator_move(confluence_status: str) -> str:
    if confluence_status == SUMMARY_LEVEL_CONFLUENCE_AVAILABLE:
        return "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING"
    if confluence_status == EVENT_LEVEL_CONFLUENCE_AVAILABLE:
        return "RUN_R206_TINY_LIVE_READINESS_GAP_RECHECK"
    return "RUN_R207_EVENT_LEVEL_CONFLUENCE_MATCHER"


def _recommended_next_engineering_move(confluence_status: str, quality: Mapping[str, Any]) -> str:
    if confluence_status == SUMMARY_LEVEL_CONFLUENCE_AVAILABLE:
        return "Build R207 event-level confluence matcher; keep R203 scores paper-only and weaker until timestamps match."
    if _to_int(quality.get("event_level_rows")):
        return "Review event-level rows in paper only; do not translate confluence into live authorization."
    return "Refresh R201/R205/R204 inputs and rerun R203 preview only."


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


def _default_target_scope(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "signal_origins": list(TARGET_SIGNAL_ORIGINS),
        "blocked_signal_origins": list(BLOCKED_SIGNAL_ORIGINS),
        "anchor_types": list(TARGET_ANCHOR_TYPES),
        "anchor_periods": list(TARGET_ANCHOR_PERIODS),
        "timeframes": list(TARGET_TIMEFRAMES),
        "paper_only": True,
        "live_authorized": False,
    }


def _extract_event_timestamps(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    timestamps: list[str] = []
    for key in ("event_timestamp", "timestamp", "open_time", "close_time", "detected_at"):
        if value.get(key):
            timestamps.append(str(value.get(key)))
    for key in ("event_timestamps", "matched_timestamps", "timestamps"):
        items = value.get(key)
        if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
            timestamps.extend(str(item) for item in items if item)
    return list(dict.fromkeys(timestamps))


def _timeframe_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_number(value: Any) -> int | float:
    number = _to_float(value)
    if number.is_integer():
        return int(number)
    return _round(number)


def _round(value: float) -> float:
    return round(value, 6)


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
