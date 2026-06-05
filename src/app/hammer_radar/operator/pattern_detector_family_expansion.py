"""R197 paper-only candle pattern detector family expansion.

This module reuses the R188 local candle feed adapter for local OHLC reads and
creates detector previews/tags for registry-only pattern origins. It does not
call Binance/network, mutate env/config, create payloads, promote lanes/origins,
or authorize live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.full_spectrum_harvester_expansion import DEFAULT_EXPANDED_TIMEFRAMES
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, normalize_lane_key
from src.app.hammer_radar.operator.local_candle_feed_adapter import (
    DEFAULT_LATEST_CANDLES,
    DETECTOR_READY_LOCAL_OHLC_AVAILABLE,
    LOCAL_OHLC_INVALID,
    LOCAL_OHLC_MISSING,
    MAX_LATEST_CANDLES,
    load_local_candle_feed,
    normalize_local_candle_feed,
    resolve_local_candle_feed_path,
    validate_normalized_candle_feed,
)

PATTERN_DETECTOR_FAMILY_EXPANSION_READY = "PATTERN_DETECTOR_FAMILY_EXPANSION_READY"
PATTERN_DETECTOR_FAMILY_EXPANSION_REJECTED = "PATTERN_DETECTOR_FAMILY_EXPANSION_REJECTED"
PATTERN_DETECTOR_FAMILY_EXPANSION_RECORDED = "PATTERN_DETECTOR_FAMILY_EXPANSION_RECORDED"
PATTERN_DETECTOR_FAMILY_EXPANSION_BLOCKED = "PATTERN_DETECTOR_FAMILY_EXPANSION_BLOCKED"
PATTERN_DETECTOR_FAMILY_EXPANSION_ERROR = "PATTERN_DETECTOR_FAMILY_EXPANSION_ERROR"

DETECTIONS_FOUND = "DETECTIONS_FOUND"
NO_DETECTIONS_FOUND = "NO_DETECTIONS_FOUND"
LOCAL_FEED_MISSING = "LOCAL_FEED_MISSING"
LOCAL_FEED_INVALID = "LOCAL_FEED_INVALID"
REGISTRY_ONLY_PREVIEW = "REGISTRY_ONLY_PREVIEW"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "PATTERN_DETECTOR_FAMILY_EXPANSION"
TAG_EVENT_TYPE = "PATTERN_FAMILY_PAPER_TAG_PREVIEW"
LEDGER_FILENAME = "pattern_detector_family_expansion.ndjson"
PAPER_TAG_LEDGER_FILENAME = "pattern_family_paper_tags.ndjson"
CONFIRM_PATTERN_FAMILY_EXPANSION_RECORDING_PHRASE = (
    "I CONFIRM PATTERN DETECTOR FAMILY EXPANSION RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_MODE = "both"
DEFAULT_PATTERNS = (
    "three_white_soldiers",
    "bearish_engulfing",
    "bullish_engulfing",
    "exhaustion_wick",
    "breakdown_retest",
    "breakout_retest",
)
DETECTOR_PATTERNS = ("three_white_soldiers", "bearish_engulfing", "bullish_engulfing", "exhaustion_wick")
REGISTRY_ONLY_PATTERNS = ("breakdown_retest", "breakout_retest")
PATTERN_DIRECTIONS = {
    "three_white_soldiers": ["long"],
    "bearish_engulfing": ["short"],
    "bullish_engulfing": ["long"],
    "exhaustion_wick": ["long", "short"],
    "breakdown_retest": ["short"],
    "breakout_retest": ["long"],
}
STRICT_BODY_RATIO_THRESHOLD = 0.5
LOOSE_BODY_RATIO_THRESHOLD = 0.35
STRICT_WICK_RATIO_THRESHOLD = 0.6
LOOSE_WICK_RATIO_THRESHOLD = 0.45
ENTRY_MODE = "ladder_close_50_618"

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
}

SOURCE_SURFACES_USED = [
    "operator.local_candle_feed_adapter.resolve_local_candle_feed_path",
    "operator.local_candle_feed_adapter.load_local_candle_feed",
    "operator.local_candle_feed_adapter.normalize_local_candle_feed",
    "operator.local_candle_feed_adapter.validate_normalized_candle_feed",
    "logs/hammer_radar_forward/candle_archive/{symbol}_{timeframe}.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{PAPER_TAG_LEDGER_FILENAME}",
]


def build_pattern_detector_family_expansion(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframes: Sequence[str] | str | None = None,
    mode: str = DEFAULT_MODE,
    latest_candles: int = DEFAULT_LATEST_CANDLES,
    record_expansion: bool = False,
    confirm_pattern_family_expansion: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    normalized_timeframes = _normalize_timeframes(timeframes)
    normalized_mode = _normalize_mode(mode)
    confirmation_valid = confirm_pattern_family_expansion == CONFIRM_PATTERN_FAMILY_EXPANSION_RECORDING_PHRASE
    try:
        registry = build_pattern_family_registry(mode=normalized_mode)
        detector_run = run_pattern_family_detectors_on_local_feeds(
            log_dir=resolved_log_dir,
            symbol=normalized_symbol,
            timeframes=normalized_timeframes,
            mode=normalized_mode,
            latest_candles=latest_candles,
        )
        detector_results = build_pattern_family_detection_summary(detector_run["by_pattern"])
        paper_tags = build_pattern_family_paper_tags(detector_run["detections"])
        status = classify_pattern_family_expansion_status(
            record_expansion=record_expansion,
            confirmation_valid=confirmation_valid,
            detector_results=detector_results,
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "expansion_recorded": False,
            "expansion_id": None,
            "record_expansion_requested": bool(record_expansion),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "symbol": normalized_symbol,
                "timeframes": normalized_timeframes,
                "patterns": list(DEFAULT_PATTERNS),
            },
            "pattern_family_registry": registry,
            "detector_results": detector_results,
            "local_feed_summary": detector_run["local_feed_summary"],
            "paper_tags": {
                "tags_created_preview": len(paper_tags),
                "record_tags_requested": False,
                "tag_ledger_path": f"logs/hammer_radar_forward/{PAPER_TAG_LEDGER_FILENAME}",
                "paper_only": True,
                "live_authorized": False,
            },
            "pattern_family_reuse_map": build_pattern_family_reuse_map(),
            "remaining_detector_gaps": _remaining_detector_gaps(detector_results),
            "recommended_next_operator_move": _recommended_next_operator_move(detector_results),
            "recommended_next_engineering_move": _recommended_next_engineering_move(detector_results),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_expansion and confirmation_valid:
            record = append_pattern_family_expansion_record(payload, log_dir=resolved_log_dir)
            payload["expansion_recorded"] = True
            payload["expansion_id"] = record["expansion_id"]
            payload["ledger_path"] = str(pattern_family_expansion_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": PATTERN_DETECTOR_FAMILY_EXPANSION_ERROR,
                "generated_at": generated_at.isoformat(),
                "expansion_recorded": False,
                "expansion_id": None,
                "record_expansion_requested": bool(record_expansion),
                "confirmation_valid": bool(confirmation_valid),
                "target_scope": {
                    "symbol": normalized_symbol,
                    "timeframes": normalized_timeframes,
                    "patterns": list(DEFAULT_PATTERNS),
                },
                "pattern_family_registry": build_pattern_family_registry(mode=normalized_mode),
                "detector_results": _empty_family_results(),
                "paper_tags": {
                    "tags_created_preview": 0,
                    "record_tags_requested": False,
                    "tag_ledger_path": f"logs/hammer_radar_forward/{PAPER_TAG_LEDGER_FILENAME}",
                    "paper_only": True,
                    "live_authorized": False,
                },
                "pattern_family_reuse_map": build_pattern_family_reuse_map(),
                "remaining_detector_gaps": list(DEFAULT_PATTERNS),
                "recommended_next_operator_move": "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R197 detector family preview error and rerun without network.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_pattern_family_registry(*, mode: str = DEFAULT_MODE) -> list[dict[str, Any]]:
    normalized_mode = _normalize_mode(mode)
    return [
        {
            "signal_origin": pattern,
            "direction_support": list(PATTERN_DIRECTIONS[pattern]),
            "detector_mode": normalized_mode if pattern in DETECTOR_PATTERNS else "registry_only",
            "paper_only": True,
            "live_authorized": False,
        }
        for pattern in DEFAULT_PATTERNS
    ]


def detect_three_white_soldiers_sequences(
    candles: Sequence[Mapping[str, Any]], *, symbol: str = DEFAULT_SYMBOL, timeframe: str = "8m", mode: str = DEFAULT_MODE
) -> list[dict[str, Any]]:
    normalized_mode = _normalize_mode(mode)
    threshold = STRICT_BODY_RATIO_THRESHOLD if normalized_mode == "strict" else LOOSE_BODY_RATIO_THRESHOLD
    rows = _sorted_candles(candles)
    detections: list[dict[str, Any]] = []
    for index in range(2, len(rows)):
        window = rows[index - 2 : index + 1]
        if not _is_consecutive_window(window, timeframe):
            continue
        if not all(_is_bullish(candle) for candle in window):
            continue
        if not (float(window[2]["close"]) > float(window[1]["close"]) > float(window[0]["close"])):
            continue
        ratios = [_body_ratio(candle) for candle in window]
        if any(ratio < threshold for ratio in ratios):
            continue
        if normalized_mode == "strict" and not _strict_three_white_soldier_opens_valid(window):
            continue
        detections.append(
            build_pattern_family_candidate(
                signal_origin="three_white_soldiers",
                direction="long",
                candles=window,
                symbol=symbol,
                timeframe=timeframe,
                mode=normalized_mode,
                confidence=_confidence(ratios, strict=normalized_mode == "strict"),
                why="three consecutive bullish candles with rising closes",
                metrics={"body_ratios": ratios},
            )
        )
    return detections


def detect_bearish_engulfing_sequences(
    candles: Sequence[Mapping[str, Any]], *, symbol: str = DEFAULT_SYMBOL, timeframe: str = "8m", mode: str = DEFAULT_MODE
) -> list[dict[str, Any]]:
    normalized_mode = _normalize_mode(mode)
    rows = _sorted_candles(candles)
    detections: list[dict[str, Any]] = []
    for index in range(1, len(rows)):
        previous, current = rows[index - 1], rows[index]
        if not _is_consecutive_window([previous, current], timeframe):
            continue
        if not (_is_bullish(previous) or _is_neutral(previous)) or not _is_bearish(current):
            continue
        prev_mid = (float(previous["open"]) + float(previous["close"])) / 2
        strict_match = float(current["close"]) < float(previous["open"]) and float(current["open"]) > float(previous["close"])
        loose_match = float(current["close"]) < prev_mid and _body_size(current) > _body_size(previous)
        if (normalized_mode == "strict" and not strict_match) or (normalized_mode != "strict" and not (strict_match or loose_match)):
            continue
        detections.append(
            build_pattern_family_candidate(
                signal_origin="bearish_engulfing",
                direction="short",
                candles=[previous, current],
                symbol=symbol,
                timeframe=timeframe,
                mode=normalized_mode,
                confidence=0.88 if strict_match else 0.68,
                why="bearish candle body engulfs prior bullish/neutral body",
                metrics={"strict_engulfing": strict_match, "body_dominance": _body_size(current) > _body_size(previous)},
            )
        )
    return detections


def detect_bullish_engulfing_sequences(
    candles: Sequence[Mapping[str, Any]], *, symbol: str = DEFAULT_SYMBOL, timeframe: str = "8m", mode: str = DEFAULT_MODE
) -> list[dict[str, Any]]:
    normalized_mode = _normalize_mode(mode)
    rows = _sorted_candles(candles)
    detections: list[dict[str, Any]] = []
    for index in range(1, len(rows)):
        previous, current = rows[index - 1], rows[index]
        if not _is_consecutive_window([previous, current], timeframe):
            continue
        if not (_is_bearish(previous) or _is_neutral(previous)) or not _is_bullish(current):
            continue
        prev_mid = (float(previous["open"]) + float(previous["close"])) / 2
        strict_match = float(current["close"]) > float(previous["open"]) and float(current["open"]) < float(previous["close"])
        loose_match = float(current["close"]) > prev_mid and _body_size(current) > _body_size(previous)
        if (normalized_mode == "strict" and not strict_match) or (normalized_mode != "strict" and not (strict_match or loose_match)):
            continue
        detections.append(
            build_pattern_family_candidate(
                signal_origin="bullish_engulfing",
                direction="long",
                candles=[previous, current],
                symbol=symbol,
                timeframe=timeframe,
                mode=normalized_mode,
                confidence=0.88 if strict_match else 0.68,
                why="bullish candle body engulfs prior bearish/neutral body",
                metrics={"strict_engulfing": strict_match, "body_dominance": _body_size(current) > _body_size(previous)},
            )
        )
    return detections


def detect_exhaustion_wick_sequences(
    candles: Sequence[Mapping[str, Any]], *, symbol: str = DEFAULT_SYMBOL, timeframe: str = "8m", mode: str = DEFAULT_MODE
) -> list[dict[str, Any]]:
    normalized_mode = _normalize_mode(mode)
    threshold = STRICT_WICK_RATIO_THRESHOLD if normalized_mode == "strict" else LOOSE_WICK_RATIO_THRESHOLD
    detections: list[dict[str, Any]] = []
    for candle in _sorted_candles(candles):
        midpoint = (float(candle["high"]) + float(candle["low"])) / 2
        lower_ratio = _lower_wick_ratio(candle)
        upper_ratio = _upper_wick_ratio(candle)
        if lower_ratio >= threshold and float(candle["close"]) > midpoint:
            detections.append(
                build_pattern_family_candidate(
                    signal_origin="exhaustion_wick",
                    direction="long",
                    candles=[candle],
                    symbol=symbol,
                    timeframe=timeframe,
                    mode=normalized_mode,
                    confidence=0.86 if normalized_mode == "strict" else 0.66,
                    why="lower wick exhaustion with close recovery above candle midpoint",
                    metrics={"lower_wick_ratio": lower_ratio, "upper_wick_ratio": upper_ratio},
                )
            )
        if upper_ratio >= threshold and float(candle["close"]) < midpoint:
            detections.append(
                build_pattern_family_candidate(
                    signal_origin="exhaustion_wick",
                    direction="short",
                    candles=[candle],
                    symbol=symbol,
                    timeframe=timeframe,
                    mode=normalized_mode,
                    confidence=0.86 if normalized_mode == "strict" else 0.66,
                    why="upper wick exhaustion with close rejection below candle midpoint",
                    metrics={"lower_wick_ratio": lower_ratio, "upper_wick_ratio": upper_ratio},
                )
            )
    return detections


def build_pattern_family_candidate(
    *,
    signal_origin: str,
    direction: str,
    candles: Sequence[Mapping[str, Any]],
    symbol: str,
    timeframe: str,
    mode: str,
    confidence: float,
    why: str,
    metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    lane_key = normalize_lane_key(symbol, timeframe, direction, ENTRY_MODE)
    return {
        "candidate_id": f"r197_{signal_origin}_{uuid4().hex}",
        "signal_origin": signal_origin,
        "lane_key": lane_key,
        "symbol": str(symbol or DEFAULT_SYMBOL).upper(),
        "timeframe": str(timeframe),
        "direction": direction,
        "mode": _normalize_mode(mode),
        "detected_at": _latest_candle_time(candles),
        "candle_times": [_candle_time(candle) for candle in candles],
        "confidence": round(float(confidence), 4),
        "paper_only": True,
        "live_authorized": False,
        "signal_origin_promoted": False,
        "lane_promoted": False,
        "why": why,
        "metrics": dict(metrics or {}),
    }


def run_pattern_family_detectors_on_local_feeds(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframes: Sequence[str] | str | None = None,
    mode: str = DEFAULT_MODE,
    latest_candles: int = DEFAULT_LATEST_CANDLES,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    normalized_timeframes = _normalize_timeframes(timeframes)
    normalized_mode = _normalize_mode(mode)
    detector_functions: dict[str, Callable[..., list[dict[str, Any]]]] = {
        "three_white_soldiers": detect_three_white_soldiers_sequences,
        "bearish_engulfing": detect_bearish_engulfing_sequences,
        "bullish_engulfing": detect_bullish_engulfing_sequences,
        "exhaustion_wick": detect_exhaustion_wick_sequences,
    }
    by_pattern = {pattern: [] for pattern in DEFAULT_PATTERNS}
    detections: list[dict[str, Any]] = []
    feed_rows: list[dict[str, Any]] = []
    for timeframe in normalized_timeframes:
        source_path = resolve_local_candle_feed_path(log_dir=resolved_log_dir, symbol=normalized_symbol, timeframe=timeframe)
        raw_records = load_local_candle_feed(source_path, latest_candles=_bounded_int(latest_candles, 1, MAX_LATEST_CANDLES, DEFAULT_LATEST_CANDLES))
        candles = normalize_local_candle_feed(
            raw_records,
            symbol=normalized_symbol,
            timeframe=timeframe,
            source=source_path.name,
            latest_candles=latest_candles,
        )
        validation = validate_normalized_candle_feed(
            source_path=source_path,
            normalized_candles=candles,
            symbol=normalized_symbol,
            timeframe=timeframe,
            latest_candles=latest_candles,
        )
        feed_ready = bool(validation.get("source_found")) and bool(validation.get("all_normalized_records_valid")) and bool(candles)
        feed_status = _feed_status(validation=validation, feed_ready=feed_ready)
        feed_rows.append(
            {
                "symbol": normalized_symbol,
                "timeframe": timeframe,
                "source_path": f"logs/hammer_radar_forward/candle_archive/{normalized_symbol}_{timeframe}.ndjson",
                "records_loaded": len(raw_records),
                "valid_records": int(validation.get("valid_records") or 0),
                "feed_ready": feed_ready,
                "adapter_readiness": feed_status,
            }
        )
        if not feed_ready:
            for pattern in DETECTOR_PATTERNS:
                by_pattern[pattern].append({"timeframe": timeframe, "feed_status": feed_status, "strict": [], "loose_preview": []})
            continue
        for pattern, detector in detector_functions.items():
            strict = detector(candles, symbol=normalized_symbol, timeframe=timeframe, mode="strict") if normalized_mode in {"strict", "both"} else []
            loose = detector(candles, symbol=normalized_symbol, timeframe=timeframe, mode="loose_preview") if normalized_mode in {"loose_preview", "both"} else []
            by_pattern[pattern].append({"timeframe": timeframe, "feed_status": feed_status, "strict": strict, "loose_preview": loose})
            detections.extend([*strict, *loose])
    for pattern in REGISTRY_ONLY_PATTERNS:
        by_pattern[pattern].append({"timeframe": None, "feed_status": REGISTRY_ONLY_PREVIEW, "strict": [], "loose_preview": []})
    return {
        "by_pattern": by_pattern,
        "detections": detections,
        "local_feed_summary": {
            "adapter_reused": True,
            "timeframes_checked": normalized_timeframes,
            "feeds_ready": sum(1 for row in feed_rows if row["feed_ready"]),
            "feeds_missing": sum(1 for row in feed_rows if row["adapter_readiness"] == LOCAL_FEED_MISSING),
            "feeds_invalid": sum(1 for row in feed_rows if row["adapter_readiness"] == LOCAL_FEED_INVALID),
            "feeds": feed_rows,
        },
    }


def build_pattern_family_detection_summary(by_pattern: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for pattern in DEFAULT_PATTERNS:
        if pattern in REGISTRY_ONLY_PATTERNS:
            result[pattern] = {
                "detector_status": REGISTRY_ONLY_PREVIEW,
                "detections_found": 0,
                "paper_only": True,
                "live_authorized": False,
            }
            continue
        rows = list(by_pattern.get(pattern) or [])
        strict_count = sum(len(row.get("strict") or []) for row in rows)
        loose_count = sum(len(row.get("loose_preview") or []) for row in rows)
        detection_timeframes = sorted(
            {str(row.get("timeframe")) for row in rows if (row.get("strict") or row.get("loose_preview"))}
        )
        statuses = [str(row.get("feed_status") or UNKNOWN_NEEDS_MANUAL_REVIEW) for row in rows]
        result[pattern] = {
            "detector_status": _detector_status(strict_count=strict_count, loose_count=loose_count, feed_statuses=statuses),
            "strict_detections_found": strict_count,
            "loose_detections_found": loose_count,
            "timeframes_with_detections": detection_timeframes,
            "timeframes_checked": [str(row.get("timeframe")) for row in rows if row.get("timeframe")],
            "paper_only": True,
            "live_authorized": False,
        }
    return result


def build_pattern_family_paper_tags(detections: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "tag_id": f"r197_pattern_family_tag_{uuid4().hex}",
            "event_type": TAG_EVENT_TYPE,
            "candidate_id": detection.get("candidate_id"),
            "signal_origin": detection.get("signal_origin"),
            "lane_key": detection.get("lane_key"),
            "symbol": detection.get("symbol"),
            "timeframe": detection.get("timeframe"),
            "direction": detection.get("direction"),
            "mode": detection.get("mode"),
            "detected_at": detection.get("detected_at"),
            "confidence": detection.get("confidence"),
            "paper_only": True,
            "live_authorized": False,
            "signal_origin_promoted": False,
            "lane_promoted": False,
        }
        for detection in detections
    ]


def build_pattern_family_reuse_map() -> dict[str, Any]:
    return {
        "three_black_crows": {
            "reused_for": ["three_white_soldiers"],
            "reuse_type": "mirror",
        },
        "local_candle_feed_adapter": {
            "reused_by": list(DETECTOR_PATTERNS),
            "reuse_type": "local_ohlc_loader_and_normalizer",
        },
        "paper_only_tagging_model": {
            "reused_by": list(DEFAULT_PATTERNS),
            "reuse_type": "preview_tags_no_live_authorization",
        },
    }


def classify_pattern_family_expansion_status(
    *,
    record_expansion: bool,
    confirmation_valid: bool,
    detector_results: Mapping[str, Mapping[str, Any]],
) -> str:
    if record_expansion and not confirmation_valid:
        return PATTERN_DETECTOR_FAMILY_EXPANSION_REJECTED
    if record_expansion and confirmation_valid:
        return PATTERN_DETECTOR_FAMILY_EXPANSION_RECORDED
    if all((row.get("detector_status") in {LOCAL_FEED_MISSING, LOCAL_FEED_INVALID, REGISTRY_ONLY_PREVIEW}) for row in detector_results.values()):
        return PATTERN_DETECTOR_FAMILY_EXPANSION_BLOCKED
    return PATTERN_DETECTOR_FAMILY_EXPANSION_READY


def append_pattern_family_expansion_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = pattern_family_expansion_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "expansion_id": str(record.get("expansion_id") or f"r197_pattern_detector_family_expansion_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_expansion_requested": bool(record.get("record_expansion_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "pattern_family_registry": list(record.get("pattern_family_registry") or []),
            "detector_results": dict(record.get("detector_results") or {}),
            "paper_tags": dict(record.get("paper_tags") or {}),
            "pattern_family_reuse_map": dict(record.get("pattern_family_reuse_map") or {}),
            "remaining_detector_gaps": list(record.get("remaining_detector_gaps") or []),
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


def load_pattern_family_expansion_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = pattern_family_expansion_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_pattern_family_expansion_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_expansion_id": latest.get("expansion_id") if isinstance(latest, Mapping) else None,
        "last_remaining_detector_gaps": list(latest.get("remaining_detector_gaps") or []) if isinstance(latest, Mapping) else [],
        "safety": dict(SAFETY),
    }


def pattern_family_expansion_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def pattern_family_paper_tag_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / PAPER_TAG_LEDGER_FILENAME


def format_pattern_detector_family_expansion_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _empty_family_results() -> dict[str, Any]:
    return {
        pattern: {
            "detector_status": REGISTRY_ONLY_PREVIEW if pattern in REGISTRY_ONLY_PATTERNS else UNKNOWN_NEEDS_MANUAL_REVIEW,
            "strict_detections_found": 0,
            "loose_detections_found": 0,
            "timeframes_with_detections": [],
            "paper_only": True,
            "live_authorized": False,
        }
        for pattern in DEFAULT_PATTERNS
    }


def _remaining_detector_gaps(detector_results: Mapping[str, Mapping[str, Any]]) -> list[str]:
    return [
        pattern
        for pattern, result in detector_results.items()
        if result.get("detector_status") in {REGISTRY_ONLY_PREVIEW, LOCAL_FEED_MISSING, LOCAL_FEED_INVALID, UNKNOWN_NEEDS_MANUAL_REVIEW}
    ]


def _recommended_next_operator_move(detector_results: Mapping[str, Mapping[str, Any]]) -> str:
    if any(row.get("detector_status") == DETECTIONS_FOUND for row in detector_results.values()):
        return "RUN_R200_PATTERN_FAMILY_FEEDBACK_SYNC"
    return "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING"


def _recommended_next_engineering_move(detector_results: Mapping[str, Mapping[str, Any]]) -> str:
    if detector_results.get("breakdown_retest", {}).get("detector_status") == REGISTRY_ONLY_PREVIEW:
        return "Design R200 feedback sync for paper-only pattern detections; keep retest origins registry-only until swing/retest structure exists."
    return "Run R200 paper-only feedback sync only after reviewing R197 detector output."


def _detector_status(*, strict_count: int, loose_count: int, feed_statuses: Sequence[str]) -> str:
    if strict_count or loose_count:
        return DETECTIONS_FOUND
    if feed_statuses and all(status == LOCAL_FEED_MISSING for status in feed_statuses):
        return LOCAL_FEED_MISSING
    if any(status == LOCAL_FEED_INVALID for status in feed_statuses):
        return LOCAL_FEED_INVALID
    if any(status == DETECTOR_READY_LOCAL_OHLC_AVAILABLE for status in feed_statuses):
        return NO_DETECTIONS_FOUND
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def _feed_status(*, validation: Mapping[str, Any], feed_ready: bool) -> str:
    if feed_ready:
        return DETECTOR_READY_LOCAL_OHLC_AVAILABLE
    if not bool(validation.get("source_found")):
        return LOCAL_FEED_MISSING
    if not bool(validation.get("all_normalized_records_valid")):
        return LOCAL_FEED_INVALID
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def _sorted_candles(candles: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(candle) for candle in candles if _valid_candle(candle)]
    rows.sort(key=lambda row: _candle_time(row))
    return rows


def _valid_candle(candle: Mapping[str, Any]) -> bool:
    return all(_to_float(candle.get(key)) is not None for key in ("open", "high", "low", "close"))


def _is_consecutive_window(candles: Sequence[Mapping[str, Any]], timeframe: str) -> bool:
    step = _timeframe_delta(timeframe)
    if step is None:
        return True
    parsed = [_parse_time(_candle_time(candle)) for candle in candles]
    if any(value is None for value in parsed):
        return True
    for prev, current in zip(parsed, parsed[1:]):
        if current - prev != step:
            return False
    return True


def _timeframe_delta(timeframe: str) -> timedelta | None:
    value = str(timeframe or "").strip()
    if not value:
        return None
    unit = value[-1]
    try:
        amount = int(value[:-1])
    except ValueError:
        return None
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "H":
        return timedelta(hours=amount)
    if unit == "D":
        return timedelta(days=amount)
    return None


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _strict_three_white_soldier_opens_valid(candles: Sequence[Mapping[str, Any]]) -> bool:
    for previous, current in zip(candles, candles[1:]):
        previous_low_body = min(float(previous["open"]), float(previous["close"]))
        previous_high_body = max(float(previous["open"]), float(previous["close"]))
        tolerance = abs(previous_high_body - previous_low_body) * 0.2
        current_open = float(current["open"])
        if not (previous_low_body - tolerance <= current_open <= previous_high_body + tolerance):
            return False
    return True


def _body_ratio(candle: Mapping[str, Any]) -> float:
    spread = float(candle["high"]) - float(candle["low"])
    if spread <= 0:
        return 0.0
    return abs(float(candle["close"]) - float(candle["open"])) / spread


def _body_size(candle: Mapping[str, Any]) -> float:
    return abs(float(candle["close"]) - float(candle["open"]))


def _upper_wick_ratio(candle: Mapping[str, Any]) -> float:
    spread = float(candle["high"]) - float(candle["low"])
    if spread <= 0:
        return 0.0
    return (float(candle["high"]) - max(float(candle["open"]), float(candle["close"]))) / spread


def _lower_wick_ratio(candle: Mapping[str, Any]) -> float:
    spread = float(candle["high"]) - float(candle["low"])
    if spread <= 0:
        return 0.0
    return (min(float(candle["open"]), float(candle["close"])) - float(candle["low"])) / spread


def _is_bullish(candle: Mapping[str, Any]) -> bool:
    return float(candle["close"]) > float(candle["open"])


def _is_bearish(candle: Mapping[str, Any]) -> bool:
    return float(candle["close"]) < float(candle["open"])


def _is_neutral(candle: Mapping[str, Any]) -> bool:
    return float(candle["close"]) == float(candle["open"])


def _confidence(ratios: Sequence[float], *, strict: bool) -> float:
    base = 0.75 if strict else 0.58
    return min(0.95, base + (sum(ratios) / max(1, len(ratios))) * 0.2)


def _latest_candle_time(candles: Sequence[Mapping[str, Any]]) -> str | None:
    return max((_candle_time(candle) for candle in candles), default=None)


def _candle_time(candle: Mapping[str, Any]) -> str:
    return str(candle.get("open_time") or candle.get("timestamp") or candle.get("close_time") or "")


def _normalize_mode(mode: str) -> str:
    value = str(mode or DEFAULT_MODE).strip()
    if value in {"strict", "loose_preview", "both"}:
        return value
    return DEFAULT_MODE


def _normalize_timeframes(timeframes: Sequence[str] | str | None) -> list[str]:
    if timeframes is None:
        raw = list(DEFAULT_EXPANDED_TIMEFRAMES)
    elif isinstance(timeframes, str):
        raw = [part.strip() for part in timeframes.split(",")]
    else:
        raw = [str(part).strip() for part in timeframes]
    result = []
    for timeframe in raw:
        if timeframe and timeframe not in result:
            result.append(timeframe)
    return result or list(DEFAULT_EXPANDED_TIMEFRAMES)


def _bounded_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
