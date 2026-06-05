"""R201 anchor outcome deepening.

Paper-only WMA/MA anchor outcome research. This module reuses R199 local
anchor calculation and candle loading, adds longer outcome windows, separates
sample quality, and overlays recorded signal-origin summaries without writing
config, calling Binance/network, creating payloads, or authorizing live.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir, load_signals
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.pattern_detector_family_expansion import (
    LEDGER_FILENAME as PATTERN_FAMILY_EXPANSION_LEDGER_FILENAME,
)
from src.app.hammer_radar.operator.pattern_family_feedback_sync import (
    LEDGER_FILENAME as PATTERN_FAMILY_FEEDBACK_LEDGER_FILENAME,
)
from src.app.hammer_radar.operator.three_black_crows_local_feed_detection import (
    LEDGER_FILENAME as THREE_BLACK_CROWS_LEDGER_FILENAME,
)
from src.app.hammer_radar.operator.wma_ma_anchor_layer_preview import (
    ANCHOR_TYPES,
    CUSTOM_WMA,
    DEFAULT_ANCHOR_PERIODS,
    DEFAULT_NEAR_TOUCH_THRESHOLD_PCT,
    DEFAULT_SYMBOL,
    DEFAULT_TIMEFRAMES,
    LEDGER_FILENAME as WMA_MA_ANCHOR_LAYER_PREVIEW_LEDGER_FILENAME,
    SMA200,
    WMA200,
    build_anchor_event_candidates as build_r199_anchor_event_candidates,
    compute_anchor_series,
    discover_anchor_candle_sources,
    load_anchor_candles,
    load_wma_ma_anchor_preview_records,
    map_anchor_event_outcomes,
)

ANCHOR_OUTCOME_DEEPENING_READY = "ANCHOR_OUTCOME_DEEPENING_READY"
ANCHOR_OUTCOME_DEEPENING_REJECTED = "ANCHOR_OUTCOME_DEEPENING_REJECTED"
ANCHOR_OUTCOME_DEEPENING_RECORDED = "ANCHOR_OUTCOME_DEEPENING_RECORDED"
ANCHOR_OUTCOME_DEEPENING_BLOCKED = "ANCHOR_OUTCOME_DEEPENING_BLOCKED"
ANCHOR_OUTCOME_DEEPENING_ERROR = "ANCHOR_OUTCOME_DEEPENING_ERROR"

ANCHOR_CANDIDATES_READY_FOR_PAPER_REVIEW = "ANCHOR_CANDIDATES_READY_FOR_PAPER_REVIEW"
ANCHOR_CANDIDATES_NEED_MORE_SAMPLES = "ANCHOR_CANDIDATES_NEED_MORE_SAMPLES"
ANCHOR_CONFLUENCE_AVAILABLE = "ANCHOR_CONFLUENCE_AVAILABLE"
ANCHOR_CONFLUENCE_NEEDS_DEEPER_MAPPING = "ANCHOR_CONFLUENCE_NEEDS_DEEPER_MAPPING"
ANCHOR_LAYER_NOT_LIVE_AUTHORIZED = "ANCHOR_LAYER_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "ANCHOR_OUTCOME_DEEPENING"
LEDGER_FILENAME = "anchor_outcome_deepening.ndjson"
CONFIRM_ANCHOR_OUTCOME_DEEPENING_RECORDING_PHRASE = (
    "I CONFIRM ANCHOR OUTCOME DEEPENING RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_OUTCOME_WINDOWS = (1, 3, 5, 10, 21, 34, 55)
SIGNAL_ORIGIN_CONFLUENCE_TARGETS = (
    "hammer_wick_reversal",
    "three_black_crows",
    "three_white_soldiers",
    "bearish_engulfing",
    "bullish_engulfing",
    "exhaustion_wick",
    "golden_pocket_rejection",
    "rsi_divergence_bearish",
    "rsi_divergence_bullish",
)

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
    "anchor_live_authorized": False,
    "anchor_position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "operator.wma_ma_anchor_layer_preview.compute_anchor_series",
    "operator.wma_ma_anchor_layer_preview.build_anchor_event_candidates",
    "operator.wma_ma_anchor_layer_preview.map_anchor_event_outcomes",
    "operator.local_candle_feed_adapter via R199 load_anchor_candles",
    "logs/hammer_radar_forward/signals.ndjson via operator.archive.load_signals",
    "logs/hammer_radar_forward/candle_archive/{symbol}_{timeframe}.ndjson",
    f"logs/hammer_radar_forward/{WMA_MA_ANCHOR_LAYER_PREVIEW_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{PATTERN_FAMILY_FEEDBACK_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{PATTERN_FAMILY_EXPANSION_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{THREE_BLACK_CROWS_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_anchor_outcome_deepening(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    record_deepening: bool = False,
    confirm_anchor_outcome_deepening: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    confirmation_valid = confirm_anchor_outcome_deepening == CONFIRM_ANCHOR_OUTCOME_DEEPENING_RECORDING_PHRASE
    try:
        latest_preview = load_latest_wma_ma_anchor_preview(log_dir=resolved_log_dir)
        target_scope = _target_scope_from_preview(latest_preview, normalized_symbol)
        candidates = load_anchor_event_candidates(
            log_dir=resolved_log_dir,
            symbol=normalized_symbol,
            timeframes=target_scope["timeframes"],
            periods=target_scope["anchor_periods"],
        )
        mapped_events = deepen_anchor_outcome_windows(
            candidates,
            log_dir=resolved_log_dir,
            symbol=normalized_symbol,
            windows=target_scope["outcome_windows"],
        )
        interaction_rankings = build_anchor_interaction_rankings(mapped_events)
        sample_quality = build_anchor_sample_quality_report(interaction_rankings)
        timeframe_rankings = build_anchor_timeframe_rankings(interaction_rankings)
        confluence = build_anchor_signal_origin_confluence(
            log_dir=resolved_log_dir,
            symbol=normalized_symbol,
            anchor_rankings=interaction_rankings,
        )
        confluence_rankings = build_anchor_confluence_rankings(confluence, interaction_rankings)
        risk_warnings = build_anchor_risk_warnings(interaction_rankings)
        next_actions = build_anchor_next_actions(
            sample_quality_report=sample_quality,
            confluence=confluence,
            risk_warnings=risk_warnings,
        )
        deepening_status = _deepening_status(sample_quality, confluence)
        status = _status_for_deepening(
            record_deepening=record_deepening,
            confirmation_valid=confirmation_valid,
            mapped_events=len(mapped_events),
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "deepening_recorded": False,
            "deepening_id": None,
            "record_deepening_requested": bool(record_deepening),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": target_scope,
            "anchor_sample_quality_report": sample_quality,
            "anchor_interaction_rankings": interaction_rankings,
            "anchor_timeframe_rankings": timeframe_rankings,
            "anchor_signal_origin_confluence": confluence,
            "anchor_confluence_rankings": confluence_rankings,
            "anchor_risk_warnings": risk_warnings,
            "anchor_next_actions": next_actions,
            "deepening_status": deepening_status,
            "recommended_next_operator_move": _recommended_next_operator_move(sample_quality, confluence),
            "recommended_next_engineering_move": _recommended_next_engineering_move(sample_quality, confluence),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "r199_anchor_source": latest_preview.get("anchor_source"),
        }
        if record_deepening and confirmation_valid and status != ANCHOR_OUTCOME_DEEPENING_BLOCKED:
            record = append_anchor_outcome_deepening_record(payload, log_dir=resolved_log_dir)
            payload["status"] = ANCHOR_OUTCOME_DEEPENING_RECORDED
            payload["deepening_recorded"] = True
            payload["deepening_id"] = record["deepening_id"]
            payload["ledger_path"] = str(anchor_outcome_deepening_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": ANCHOR_OUTCOME_DEEPENING_ERROR,
                "generated_at": generated_at.isoformat(),
                "deepening_recorded": False,
                "deepening_id": None,
                "record_deepening_requested": bool(record_deepening),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": _default_target_scope(normalized_symbol),
                "anchor_sample_quality_report": build_anchor_sample_quality_report([]),
                "anchor_interaction_rankings": [],
                "anchor_timeframe_rankings": [],
                "anchor_signal_origin_confluence": _empty_confluence("R201 deepening errored before overlay mapping."),
                "anchor_confluence_rankings": [],
                "anchor_risk_warnings": [f"{UNKNOWN_NEEDS_MANUAL_REVIEW}: {exc.__class__.__name__}"],
                "anchor_next_actions": build_anchor_next_actions(),
                "deepening_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R201 anchor outcome deepening error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_wma_ma_anchor_preview(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_wma_ma_anchor_preview_records(log_dir=log_dir, limit=100)
    if records:
        latest = dict(records[0])
        latest["anchor_source"] = "wma_ma_anchor_layer_preview_ledger"
        return latest
    return {"anchor_source": "missing"}


def load_anchor_event_candidates(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframes: Sequence[str] | None = None,
    periods: Sequence[int] | None = None,
) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    normalized_periods = _normalize_periods(periods)
    discovered = discover_anchor_candle_sources(
        log_dir=resolved_log_dir,
        symbol=normalized_symbol,
        requested_timeframes=timeframes,
        periods=normalized_periods,
    )
    events: list[dict[str, Any]] = []
    for timeframe in discovered["timeframes"]:
        candles = load_anchor_candles(log_dir=resolved_log_dir, symbol=normalized_symbol, timeframe=str(timeframe))
        anchor_series = compute_anchor_series(candles, periods=normalized_periods)
        events.extend(
            build_r199_anchor_event_candidates(
                candles,
                anchor_series,
                symbol=normalized_symbol,
                timeframe=str(timeframe),
                near_touch_threshold_pct=DEFAULT_NEAR_TOUCH_THRESHOLD_PCT,
            )
        )
    return _sanitize(events)


def deepen_anchor_outcome_windows(
    anchor_events: Sequence[Mapping[str, Any]],
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    windows: Sequence[int] = DEFAULT_OUTCOME_WINDOWS,
) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    timeframes = sorted({str(event.get("timeframe") or "") for event in anchor_events if event.get("timeframe")})
    candles_by_timeframe = {
        timeframe: load_anchor_candles(log_dir=resolved_log_dir, symbol=normalized_symbol, timeframe=timeframe)
        for timeframe in timeframes
    }
    return map_anchor_event_outcomes(
        anchor_events,
        candles_by_timeframe=candles_by_timeframe,
        windows=tuple(_normalize_windows(windows)),
    )


def build_anchor_sample_quality_report(rankings: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    confidence_counts = Counter(str(row.get("sample_confidence") or sample_confidence(row.get("mapped_events"))) for row in rankings)
    risk_warning_candidates = sum(1 for row in rankings if row.get("risk_warnings"))
    return {
        "total_candidates_reviewed": len(rankings),
        "high_confidence_candidates": int(confidence_counts.get("HIGH", 0)),
        "medium_confidence_candidates": int(confidence_counts.get("MEDIUM", 0)),
        "low_confidence_candidates": int(confidence_counts.get("LOW", 0)),
        "risk_warning_candidates": risk_warning_candidates,
    }


def build_anchor_interaction_rankings(
    mapped_events: Sequence[Mapping[str, Any]],
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for event in mapped_events:
        grouped[
            (
                str(event.get("timeframe") or ""),
                str(event.get("anchor_type") or ""),
                int(event.get("period") or 0),
                str(event.get("interaction") or ""),
                str(event.get("direction_bias") or "neutral"),
            )
        ].append(event)
    rankings = []
    for (timeframe, anchor_type, period, interaction, direction_bias), rows in grouped.items():
        stats = _best_window_stats(rows)
        warnings = _candidate_risk_warnings(stats)
        confidence = sample_confidence(stats["mapped_events"])
        rankings.append(
            {
                "rank": 0,
                "timeframe": timeframe,
                "anchor_type": anchor_type,
                "period": period,
                "interaction": interaction,
                "direction_bias": direction_bias,
                "mapped_events": stats["mapped_events"],
                "sample_confidence": confidence,
                "best_window": stats["best_window"],
                "success_rate_pct": stats["success_rate_pct"],
                "failure_rate_pct": stats["failure_rate_pct"],
                "avg_favorable_move_pct": stats["avg_favorable_move_pct"],
                "avg_adverse_move_pct": stats["avg_adverse_move_pct"],
                "score": _candidate_score(stats, confidence),
                "risk_warnings": warnings,
                "paper_only": True,
                "live_authorized": False,
            }
        )
    rankings.sort(key=lambda row: (float(row["score"]), int(row["mapped_events"])), reverse=True)
    for rank, row in enumerate(rankings[:limit], start=1):
        row["rank"] = rank
    return _sanitize(rankings[:limit])


def build_anchor_timeframe_rankings(rankings: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rankings:
        grouped[str(row.get("timeframe") or "")].append(row)
    output = []
    for timeframe, rows in grouped.items():
        best = max(rows, key=lambda row: float(row.get("score") or 0.0))
        warnings = sum(len(row.get("risk_warnings") or []) for row in rows)
        output.append(
            {
                "timeframe": timeframe,
                "candidate_count": len(rows),
                "best_anchor": _anchor_label(best),
                "best_score": _round(best.get("score")),
                "notes": _timeframe_notes(rows, warnings),
            }
        )
    output.sort(key=lambda row: (float(row["best_score"]), int(row["candidate_count"])), reverse=True)
    return _sanitize(output)


def build_anchor_signal_origin_confluence(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    anchor_rankings: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    origin_summaries = _load_signal_origin_summaries(resolved_log_dir, normalized_symbol)
    anchors_by_timeframe = _anchors_by_timeframe(anchor_rankings or [])
    top = []
    for origin, summary in origin_summaries.items():
        for timeframe in summary["timeframes"]:
            best_anchor = anchors_by_timeframe.get(timeframe)
            if not best_anchor:
                continue
            top.append(
                {
                    "signal_origin": origin,
                    "timeframe": timeframe,
                    "anchor_type": best_anchor.get("anchor_type"),
                    "period": best_anchor.get("period"),
                    "interaction": best_anchor.get("interaction"),
                    "confidence": _confluence_confidence(summary, best_anchor),
                    "why": _confluence_why(origin, summary, best_anchor),
                }
            )
    top.sort(key=lambda row: (_confidence_rank(str(row.get("confidence"))), str(row.get("signal_origin"))), reverse=True)
    resolution = "summary_level_only" if top else "none"
    return {
        "confluence_records_found": len(top),
        "confluence_resolution": resolution,
        "top_confluences": _sanitize(top[:20]),
        "notes": [
            "Confluence is preview-only and does not create live authorization.",
            "summary_level_only means timeframe/source overlap exists, but exact candle timestamps were not matched locally.",
        ],
    }


def build_anchor_confluence_rankings(
    confluence: Mapping[str, Any],
    anchor_rankings: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    score_by_anchor = {
        (
            str(row.get("timeframe") or ""),
            str(row.get("anchor_type") or ""),
            int(row.get("period") or 0),
            str(row.get("interaction") or ""),
        ): row
        for row in anchor_rankings
    }
    output = []
    for item in confluence.get("top_confluences") or []:
        if not isinstance(item, Mapping):
            continue
        key = (
            str(item.get("timeframe") or ""),
            str(item.get("anchor_type") or ""),
            int(item.get("period") or 0),
            str(item.get("interaction") or ""),
        )
        anchor = score_by_anchor.get(key, {})
        output.append(
            {
                "signal_origin": item.get("signal_origin"),
                "timeframe": item.get("timeframe"),
                "anchor_type": item.get("anchor_type"),
                "period": item.get("period"),
                "interaction": item.get("interaction"),
                "anchor_score": _round(anchor.get("score")),
                "sample_confidence": anchor.get("sample_confidence", "LOW"),
                "confluence_resolution": confluence.get("confluence_resolution", "none"),
                "paper_only": True,
                "live_authorized": False,
            }
        )
    output.sort(key=lambda row: (float(row["anchor_score"]), _confidence_rank(str(row["sample_confidence"]))), reverse=True)
    return _sanitize(output[:20])


def build_anchor_risk_warnings(rankings: Sequence[Mapping[str, Any]]) -> list[str]:
    warnings = []
    for row in rankings:
        label = _anchor_label(row)
        for warning in row.get("risk_warnings") or []:
            warnings.append(f"{label}: {warning}")
    if not warnings:
        warnings.append("No anchor candidate creates live permission; direction bias remains a paper-only hypothesis.")
    return warnings[:30]


def build_anchor_next_actions(
    *,
    sample_quality_report: Mapping[str, Any] | None = None,
    confluence: Mapping[str, Any] | None = None,
    risk_warnings: Sequence[str] | None = None,
) -> list[dict[str, str]]:
    quality = sample_quality_report or {}
    confluence_records = int((confluence or {}).get("confluence_records_found") or 0)
    high = int(quality.get("high_confidence_candidates") or 0)
    low = int(quality.get("low_confidence_candidates") or 0)
    actions = [
        {
            "priority": "HIGH" if low > high else "MEDIUM",
            "future_phase": "R202",
            "action": "Map detector-backed pattern-family outcomes before any Keter or matrix scoring proposal.",
            "why": "Pattern outcomes are needed to avoid overfitting anchor-only evidence.",
        },
        {
            "priority": "HIGH" if confluence_records else "MEDIUM",
            "future_phase": "R203",
            "action": "Build an anchor x signal-origin confluence matrix from paper-only local evidence.",
            "why": "R201 confluence is summary-level unless exact local timestamps can be mapped.",
        },
    ]
    if risk_warnings:
        actions.append(
            {
                "priority": "MEDIUM",
                "future_phase": "R203",
                "action": "Keep risk warnings attached to candidate rows in any future confluence matrix.",
                "why": "High success rates can still be traps when failures or adverse moves are large.",
            }
        )
    return actions


def append_anchor_outcome_deepening_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = anchor_outcome_deepening_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "deepening_id": str(record.get("deepening_id") or f"r201_anchor_outcome_deepening_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": ANCHOR_OUTCOME_DEEPENING_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_deepening_requested": bool(record.get("record_deepening_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "anchor_sample_quality_report": dict(record.get("anchor_sample_quality_report") or {}),
            "anchor_interaction_rankings": list(record.get("anchor_interaction_rankings") or []),
            "anchor_timeframe_rankings": list(record.get("anchor_timeframe_rankings") or []),
            "anchor_signal_origin_confluence": dict(record.get("anchor_signal_origin_confluence") or {}),
            "anchor_confluence_rankings": list(record.get("anchor_confluence_rankings") or []),
            "anchor_risk_warnings": list(record.get("anchor_risk_warnings") or []),
            "anchor_next_actions": list(record.get("anchor_next_actions") or []),
            "deepening_status": record.get("deepening_status"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
            "r199_anchor_source": record.get("r199_anchor_source"),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_anchor_outcome_deepening_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return _load_ndjson(anchor_outcome_deepening_records_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def summarize_anchor_outcome_deepening_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "deepening_status_counts": dict(sorted(Counter(str(record.get("deepening_status") or "UNKNOWN") for record in records).items())),
        "last_deepening_id": latest.get("deepening_id") if isinstance(latest, Mapping) else None,
        "last_sample_quality_report": dict(latest.get("anchor_sample_quality_report") or {}) if isinstance(latest, Mapping) else {},
        "safety": dict(SAFETY),
    }


def anchor_outcome_deepening_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_anchor_outcome_deepening_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def sample_confidence(mapped_events: object) -> str:
    mapped = _to_int(mapped_events)
    if mapped >= 100:
        return "HIGH"
    if mapped >= 30:
        return "MEDIUM"
    return "LOW"


def _target_scope_from_preview(latest_preview: Mapping[str, Any], symbol: str) -> dict[str, Any]:
    scope = latest_preview.get("target_scope") if isinstance(latest_preview.get("target_scope"), Mapping) else {}
    return {
        "symbol": symbol,
        "anchor_types": _normalize_anchor_types(scope.get("anchor_types")),
        "anchor_periods": _normalize_periods(scope.get("anchor_periods")),
        "timeframes": _normalize_timeframes(scope.get("timeframes")),
        "outcome_windows": list(DEFAULT_OUTCOME_WINDOWS),
        "paper_only": True,
        "live_authorized": False,
    }


def _default_target_scope(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "anchor_types": list(ANCHOR_TYPES),
        "anchor_periods": list(DEFAULT_ANCHOR_PERIODS),
        "timeframes": list(DEFAULT_TIMEFRAMES),
        "outcome_windows": list(DEFAULT_OUTCOME_WINDOWS),
        "paper_only": True,
        "live_authorized": False,
    }


def _best_window_stats(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for window in DEFAULT_OUTCOME_WINDOWS:
        rows = [
            dict(window_row)
            for event in events
            if isinstance((window_row := (event.get("windows") or {}).get(str(window))), Mapping)
        ]
        if not rows:
            continue
        stats = _window_stats(rows)
        stats["best_window"] = str(window)
        candidate_score = _raw_score(stats)
        if best is None or candidate_score > float(best["raw_score"]):
            best = {**stats, "raw_score": candidate_score}
    if best is None:
        return {
            "mapped_events": 0,
            "best_window": None,
            "success_rate_pct": 0.0,
            "failure_rate_pct": 0.0,
            "avg_favorable_move_pct": 0.0,
            "avg_adverse_move_pct": 0.0,
            "raw_score": 0.0,
        }
    return best


def _window_stats(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "mapped_events": len(rows),
        "success_rate_pct": _rate(rows, "simple_success"),
        "failure_rate_pct": _rate(rows, "simple_failure"),
        "avg_favorable_move_pct": _avg(rows, "mfe_favorable_pct"),
        "avg_adverse_move_pct": _avg(rows, "mae_adverse_pct"),
    }


def _candidate_score(stats: Mapping[str, Any], confidence: str) -> float:
    score = _raw_score(stats)
    if confidence == "LOW":
        score -= 30.0
    elif confidence == "MEDIUM":
        score -= 10.0
    favorable = _to_float(stats.get("avg_favorable_move_pct"))
    adverse = _to_float(stats.get("avg_adverse_move_pct"))
    if favorable is not None and adverse is not None and adverse > favorable * 1.5:
        score -= min(25.0, (adverse - favorable) * 10.0)
    return _round(score)


def _raw_score(stats: Mapping[str, Any]) -> float:
    mapped = _to_int(stats.get("mapped_events"))
    success = _to_float(stats.get("success_rate_pct")) or 0.0
    failure = _to_float(stats.get("failure_rate_pct")) or 0.0
    favorable = _to_float(stats.get("avg_favorable_move_pct")) or 0.0
    adverse = _to_float(stats.get("avg_adverse_move_pct")) or 0.0
    return (success - failure) + favorable - adverse + min(mapped, 200) * 0.05


def _candidate_risk_warnings(stats: Mapping[str, Any]) -> list[str]:
    warnings = []
    success = _to_float(stats.get("success_rate_pct")) or 0.0
    failure = _to_float(stats.get("failure_rate_pct")) or 0.0
    favorable = _to_float(stats.get("avg_favorable_move_pct")) or 0.0
    adverse = _to_float(stats.get("avg_adverse_move_pct")) or 0.0
    mapped = _to_int(stats.get("mapped_events"))
    if mapped < 30:
        warnings.append("LOW_SAMPLE_TRAP")
    if failure >= 70.0:
        warnings.append("VERY_HIGH_FAILURE_RATE")
    elif failure >= success:
        warnings.append("FAILURE_RATE_MEETS_OR_EXCEEDS_SUCCESS_RATE")
    if favorable > 0 and adverse > favorable * 1.5:
        warnings.append("ADVERSE_MOVE_EXCEEDS_FAVORABLE_MOVE_BY_LARGE_MARGIN")
    return warnings


def _load_signal_origin_summaries(log_dir: Path, symbol: str) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    _merge_pattern_feedback(summaries, _load_ndjson(log_dir / PATTERN_FAMILY_FEEDBACK_LEDGER_FILENAME, limit=20), symbol)
    _merge_pattern_expansion(summaries, _load_ndjson(log_dir / PATTERN_FAMILY_EXPANSION_LEDGER_FILENAME, limit=20), symbol)
    _merge_three_black_crows(summaries, _load_ndjson(log_dir / THREE_BLACK_CROWS_LEDGER_FILENAME, limit=20), symbol)
    _merge_signal_log_origins(summaries, log_dir, symbol)
    return {
        origin: summary
        for origin, summary in summaries.items()
        if origin in SIGNAL_ORIGIN_CONFLUENCE_TARGETS and summary["timeframes"]
    }


def _merge_pattern_feedback(summaries: dict[str, dict[str, Any]], records: Sequence[Mapping[str, Any]], symbol: str) -> None:
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        if str(target.get("symbol") or symbol).upper() != symbol:
            continue
        detection_summary = record.get("pattern_family_detection_summary")
        if not isinstance(detection_summary, Mapping):
            continue
        for origin, row in detection_summary.items():
            if isinstance(row, Mapping):
                _merge_origin_summary(
                    summaries,
                    str(origin),
                    timeframes=row.get("timeframes_with_detections") or [],
                    count=_to_int(row.get("strict_detections_found")) + _to_int(row.get("loose_detections_found")),
                    source="pattern_family_feedback_sync",
                )


def _merge_pattern_expansion(summaries: dict[str, dict[str, Any]], records: Sequence[Mapping[str, Any]], symbol: str) -> None:
    for record in records:
        target = record.get("target_scope") if isinstance(record.get("target_scope"), Mapping) else {}
        if str(target.get("symbol") or symbol).upper() != symbol:
            continue
        detector_results = record.get("detector_results")
        if not isinstance(detector_results, Mapping):
            continue
        for origin, row in detector_results.items():
            if isinstance(row, Mapping):
                _merge_origin_summary(
                    summaries,
                    str(origin),
                    timeframes=row.get("timeframes_with_detections") or [],
                    count=_to_int(row.get("strict_detections_found")) + _to_int(row.get("loose_detections_found")),
                    source="pattern_detector_family_expansion",
                )


def _merge_three_black_crows(summaries: dict[str, dict[str, Any]], records: Sequence[Mapping[str, Any]], symbol: str) -> None:
    for record in records:
        detections = record.get("detections")
        if not isinstance(detections, list):
            continue
        counts = Counter(
            str(row.get("timeframe") or "")
            for row in detections
            if isinstance(row, Mapping) and str(row.get("symbol") or symbol).upper() == symbol and row.get("timeframe")
        )
        _merge_origin_summary(
            summaries,
            "three_black_crows",
            timeframes=list(counts),
            count=sum(counts.values()),
            source="three_black_crows_local_detections",
        )


def _merge_signal_log_origins(summaries: dict[str, dict[str, Any]], log_dir: Path, symbol: str) -> None:
    counts: Counter[tuple[str, str]] = Counter()
    for signal in load_signals(log_dir):
        if str(signal.symbol).upper() != symbol:
            continue
        timeframe = str(signal.timeframe)
        if signal.tradable:
            counts[("hammer_wick_reversal", timeframe)] += 1
        if _to_float(getattr(signal, "fib_618", None)) is not None:
            counts[("golden_pocket_rejection", timeframe)] += 1
        if bool(getattr(signal, "divergence_confirmed", False)) and str(getattr(signal, "divergence_type", "") or "").lower() == "bearish":
            counts[("rsi_divergence_bearish", timeframe)] += 1
        if bool(getattr(signal, "divergence_confirmed", False)) and str(getattr(signal, "divergence_type", "") or "").lower() == "bullish":
            counts[("rsi_divergence_bullish", timeframe)] += 1
    grouped: dict[str, list[str]] = defaultdict(list)
    count_by_origin: Counter[str] = Counter()
    for (origin, timeframe), count in counts.items():
        grouped[origin].append(timeframe)
        count_by_origin[origin] += count
    for origin, timeframes in grouped.items():
        _merge_origin_summary(
            summaries,
            origin,
            timeframes=timeframes,
            count=count_by_origin[origin],
            source="signals_ndjson",
        )


def _merge_origin_summary(
    summaries: dict[str, dict[str, Any]],
    origin: str,
    *,
    timeframes: Sequence[Any],
    count: int,
    source: str,
) -> None:
    summary = summaries.setdefault(origin, {"timeframes": set(), "records": 0, "sources": set()})
    summary["timeframes"].update(str(timeframe) for timeframe in timeframes if str(timeframe))
    summary["records"] += max(count, 0)
    summary["sources"].add(source)


def _anchors_by_timeframe(anchor_rankings: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in anchor_rankings:
        grouped[str(row.get("timeframe") or "")].append(row)
    return {timeframe: max(rows, key=lambda row: float(row.get("score") or 0.0)) for timeframe, rows in grouped.items()}


def _confluence_confidence(summary: Mapping[str, Any], anchor: Mapping[str, Any]) -> str:
    anchor_conf = str(anchor.get("sample_confidence") or "LOW")
    records = _to_int(summary.get("records"))
    if anchor_conf == "HIGH" and records >= 100:
        return "HIGH"
    if anchor_conf in {"HIGH", "MEDIUM"} and records >= 25:
        return "MEDIUM"
    return "LOW"


def _confluence_why(origin: str, summary: Mapping[str, Any], anchor: Mapping[str, Any]) -> str:
    sources = ", ".join(sorted(str(source) for source in summary.get("sources") or []))
    return (
        f"{origin} has summary-level timeframe overlap with {_anchor_label(anchor)}; "
        f"records={_to_int(summary.get('records'))}; sources={sources or 'unknown'}."
    )


def _deepening_status(sample_quality: Mapping[str, Any], confluence: Mapping[str, Any]) -> str:
    if int(confluence.get("confluence_records_found") or 0) > 0:
        return ANCHOR_CONFLUENCE_AVAILABLE
    if int(sample_quality.get("high_confidence_candidates") or 0) > 0:
        return ANCHOR_CANDIDATES_READY_FOR_PAPER_REVIEW
    if int(sample_quality.get("total_candidates_reviewed") or 0) > 0:
        return ANCHOR_CANDIDATES_NEED_MORE_SAMPLES
    return ANCHOR_CONFLUENCE_NEEDS_DEEPER_MAPPING


def _status_for_deepening(*, record_deepening: bool, confirmation_valid: bool, mapped_events: int) -> str:
    if record_deepening and not confirmation_valid:
        return ANCHOR_OUTCOME_DEEPENING_REJECTED
    if mapped_events <= 0:
        return ANCHOR_OUTCOME_DEEPENING_BLOCKED
    if record_deepening and confirmation_valid:
        return ANCHOR_OUTCOME_DEEPENING_RECORDED
    return ANCHOR_OUTCOME_DEEPENING_READY


def _recommended_next_operator_move(sample_quality: Mapping[str, Any], confluence: Mapping[str, Any]) -> str:
    if int(confluence.get("confluence_records_found") or 0) > 0:
        return "RUN_R203_ANCHOR_SIGNAL_CONFLUENCE_MATRIX"
    if int(sample_quality.get("high_confidence_candidates") or 0) > 0:
        return "RUN_R202_PATTERN_OUTCOME_MAPPING_FAMILY"
    return "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING"


def _recommended_next_engineering_move(sample_quality: Mapping[str, Any], confluence: Mapping[str, Any]) -> str:
    if int(confluence.get("confluence_records_found") or 0) > 0:
        return "Build R203 anchor x signal-origin confluence matrix from R201/R202 paper-only evidence; keep config writes and live execution disabled."
    if int(sample_quality.get("high_confidence_candidates") or 0) > 0:
        return "Build R202 pattern-family outcome mapping before converting anchor candidates into scoring inputs."
    return "Keep harvesting local candles and rerun R201 after sample depth improves."


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


def _empty_confluence(note: str) -> dict[str, Any]:
    return {"confluence_records_found": 0, "confluence_resolution": "none", "top_confluences": [], "notes": [note]}


def _anchor_label(row: Mapping[str, Any]) -> str:
    return f"{row.get('timeframe')} {row.get('anchor_type')} period {row.get('period')} {row.get('interaction')}"


def _timeframe_notes(rows: Sequence[Mapping[str, Any]], warnings: int) -> list[str]:
    notes = [f"{len(rows)} ranked anchor candidates on timeframe."]
    if warnings:
        notes.append(f"{warnings} risk warnings require manual review.")
    if any(str(row.get("sample_confidence")) == "HIGH" for row in rows):
        notes.append("At least one high-sample candidate exists; still paper-only.")
    return notes


def _confidence_rank(value: str) -> int:
    return {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(value, 0)


def _normalize_anchor_types(anchor_types: object) -> list[str]:
    valid = {SMA200, WMA200, CUSTOM_WMA}
    if isinstance(anchor_types, Sequence) and not isinstance(anchor_types, str):
        parsed = [str(item) for item in anchor_types if str(item) in valid]
    else:
        parsed = list(ANCHOR_TYPES)
    return parsed or list(ANCHOR_TYPES)


def _normalize_timeframes(timeframes: object) -> list[str]:
    if isinstance(timeframes, Sequence) and not isinstance(timeframes, str):
        parsed = [str(item).strip() for item in timeframes if str(item).strip()]
    elif isinstance(timeframes, str):
        parsed = [part.strip() for part in timeframes.split(",") if part.strip()]
    else:
        parsed = list(DEFAULT_TIMEFRAMES)
    deduped = []
    for timeframe in parsed:
        if timeframe not in deduped:
            deduped.append(timeframe)
    return deduped or list(DEFAULT_TIMEFRAMES)


def _normalize_periods(periods: object) -> list[int]:
    raw = periods if isinstance(periods, Sequence) and not isinstance(periods, str) else DEFAULT_ANCHOR_PERIODS
    parsed = []
    for period in raw:
        value = _to_int(period)
        if value > 0 and value not in parsed:
            parsed.append(value)
    return parsed or list(DEFAULT_ANCHOR_PERIODS)


def _normalize_windows(windows: Sequence[int]) -> list[int]:
    parsed = []
    for window in windows:
        value = _to_int(window)
        if value > 0 and value not in parsed:
            parsed.append(value)
    return parsed or list(DEFAULT_OUTCOME_WINDOWS)


def _load_ndjson(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if limit <= 0:
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]


def _rate(rows: Sequence[Mapping[str, Any]], field: str) -> float:
    if not rows:
        return 0.0
    return _round(sum(1 for row in rows if row.get(field) is True) / len(rows) * 100.0)


def _avg(rows: Sequence[Mapping[str, Any]], field: str) -> float:
    values = [_to_float(row.get(field)) for row in rows]
    parsed = [float(value) for value in values if value is not None]
    if not parsed:
        return 0.0
    return _round(sum(parsed) / len(parsed))


def _round(value: object, digits: int = 6) -> float:
    numeric = _to_float(value)
    return round(numeric or 0.0, digits)


def _to_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, set):
        return sorted(_sanitize(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    return value
