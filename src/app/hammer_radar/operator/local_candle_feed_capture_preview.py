"""R187 local candle feed capture preview.

This module audits local candle-like files only. It never calls Binance,
creates order payloads, mutates env/config, writes candle feeds, changes lane
modes, promotes origins/lanes, or authorizes live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, normalize_lane_key
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY
from src.app.hammer_radar.operator.three_black_crows_detector import (
    DEFAULT_LATEST_CANDLES,
    DEFAULT_SYMBOL,
    DEFAULT_TIMEFRAME,
    MAX_LATEST_CANDLES,
)

LOCAL_CANDLE_FEED_PREVIEW_READY = "LOCAL_CANDLE_FEED_PREVIEW_READY"
LOCAL_CANDLE_FEED_PREVIEW_REJECTED = "LOCAL_CANDLE_FEED_PREVIEW_REJECTED"
LOCAL_CANDLE_FEED_PREVIEW_RECORDED = "LOCAL_CANDLE_FEED_PREVIEW_RECORDED"
LOCAL_CANDLE_FEED_PREVIEW_BLOCKED = "LOCAL_CANDLE_FEED_PREVIEW_BLOCKED"
LOCAL_CANDLE_FEED_PREVIEW_ERROR = "LOCAL_CANDLE_FEED_PREVIEW_ERROR"

VALID_LOCAL_OHLC_FEED_AVAILABLE = "VALID_LOCAL_OHLC_FEED_AVAILABLE"
LOCAL_FEED_MISSING = "LOCAL_FEED_MISSING"
LOCAL_FEED_INVALID_SHAPE = "LOCAL_FEED_INVALID_SHAPE"
SYNTHETIC_SIGNAL_CONTEXT_ONLY = "SYNTHETIC_SIGNAL_CONTEXT_ONLY"
FUTURE_CAPTURE_PLAN_REQUIRED = "FUTURE_CAPTURE_PLAN_REQUIRED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "LOCAL_CANDLE_FEED_CAPTURE_PREVIEW"
LEDGER_FILENAME = "local_candle_feed_capture_previews.ndjson"
CONFIRM_LOCAL_CANDLE_FEED_PREVIEW_RECORDING_PHRASE = (
    "I CONFIRM LOCAL CANDLE FEED PREVIEW RECORDING ONLY; NO FEED WRITE; NO ORDER; NO BINANCE CALL."
)

SYNTHETIC_CONTEXT_FILENAMES = (
    "signals.ndjson",
    "multi_symbol_paper_scans.ndjson",
    "multi_lane_paper_harvester.ndjson",
)

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "candle_feed_written": False,
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
    "fake_ohlc_created": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/candles.ndjson",
    "logs/hammer_radar_forward/ohlc.ndjson",
    "logs/hammer_radar_forward/klines.ndjson",
    "logs/hammer_radar_forward/*candle*.ndjson",
    "logs/hammer_radar_forward/*ohlc*.ndjson",
    "logs/hammer_radar_forward/*kline*.ndjson",
    "logs/hammer_radar_forward/candle_archive/*.ndjson",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    "logs/hammer_radar_forward/multi_lane_paper_harvester.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_local_candle_feed_capture_preview(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    latest_candles: int = DEFAULT_LATEST_CANDLES,
    record_preview: bool = False,
    confirm_local_candle_feed_preview: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    normalized_timeframe = str(timeframe or DEFAULT_TIMEFRAME).strip()
    confirmation_valid = confirm_local_candle_feed_preview == CONFIRM_LOCAL_CANDLE_FEED_PREVIEW_RECORDING_PHRASE
    try:
        discovery = discover_local_candle_like_sources(
            log_dir=resolved_log_dir,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            latest_candles=latest_candles,
        )
        normalized = normalize_valid_ohlc_records(
            discovery["source_shapes"],
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            latest_candles=latest_candles,
        )
        rejection = reject_invalid_or_synthetic_candle_sources(discovery["source_shapes"])
        readiness = build_detector_feed_readiness(
            valid_candles=normalized,
            invalid_or_synthetic_sources=rejection,
            source_shapes=discovery["source_shapes"],
        )
        status = _status_for_readiness(readiness["feed_readiness"])
        if record_preview and not confirmation_valid:
            status = LOCAL_CANDLE_FEED_PREVIEW_REJECTED
        elif record_preview and confirmation_valid:
            status = LOCAL_CANDLE_FEED_PREVIEW_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "preview_recorded": False,
            "preview_id": None,
            "record_preview_requested": bool(record_preview),
            "confirmation_valid": bool(confirmation_valid),
            "target_context": _target_context(normalized_symbol, normalized_timeframe),
            "source_discovery": {
                "files_checked": discovery["files_checked"],
                "files_found": discovery["files_found"],
                "valid_ohlc_files": discovery["valid_ohlc_files"],
                "invalid_or_synthetic_sources": rejection,
            },
            "normalized_feed_preview": {
                "valid_candles_found": len(normalized),
                "latest_candle_time": _latest_candle_time(normalized),
                "sample_candle": normalized[-1] if normalized else None,
                "would_write_feed_now": False,
                "candidate_output_path": _candidate_output_path(normalized_symbol, normalized_timeframe),
            },
            "candidate_candle_feed_schema": build_candidate_candle_feed_schema(),
            "detector_feed_readiness": readiness,
            "future_candle_capture_plan": build_future_candle_capture_plan(
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
            ),
            "recommended_next_operator_move": _recommended_next_operator_move(readiness["feed_readiness"]),
            "recommended_next_engineering_move": _recommended_next_engineering_move(readiness["feed_readiness"]),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_preview and confirmation_valid:
            record = append_local_candle_feed_preview_record(payload, log_dir=resolved_log_dir)
            payload["preview_recorded"] = True
            payload["preview_id"] = record["preview_id"]
            payload["ledger_path"] = str(local_candle_feed_preview_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": LOCAL_CANDLE_FEED_PREVIEW_ERROR,
                "generated_at": generated_at.isoformat(),
                "preview_recorded": False,
                "preview_id": None,
                "record_preview_requested": bool(record_preview),
                "confirmation_valid": bool(confirmation_valid),
                "target_context": _target_context(normalized_symbol, normalized_timeframe),
                "source_discovery": {
                    "files_checked": [],
                    "files_found": [],
                    "valid_ohlc_files": [],
                    "invalid_or_synthetic_sources": [],
                },
                "normalized_feed_preview": {
                    "valid_candles_found": 0,
                    "latest_candle_time": None,
                    "sample_candle": None,
                    "would_write_feed_now": False,
                    "candidate_output_path": _candidate_output_path(normalized_symbol, normalized_timeframe),
                },
                "candidate_candle_feed_schema": build_candidate_candle_feed_schema(),
                "detector_feed_readiness": {
                    "three_black_crows_ready_to_detect": False,
                    "feed_readiness": UNKNOWN_NEEDS_MANUAL_REVIEW,
                    "blockers": [UNKNOWN_NEEDS_MANUAL_REVIEW],
                },
                "future_candle_capture_plan": build_future_candle_capture_plan(
                    symbol=normalized_symbol,
                    timeframe=normalized_timeframe,
                ),
                "recommended_next_operator_move": "PROVIDE_LOCAL_OHLC_FILE",
                "recommended_next_engineering_move": "Fix R187 local candle feed preview error and rerun without network.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def discover_local_candle_like_sources(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    latest_candles: int = DEFAULT_LATEST_CANDLES,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_paths = _candidate_source_files(resolved_log_dir, symbol, timeframe)
    source_shapes = [
        inspect_local_candle_source_shape(
            path,
            symbol=symbol,
            timeframe=timeframe,
            latest_candles=latest_candles,
            synthetic_context=path.name in SYNTHETIC_CONTEXT_FILENAMES,
        )
        for path in source_paths
    ]
    return {
        "files_checked": [str(path) for path in source_paths],
        "files_found": [shape["path"] for shape in source_shapes if shape["exists"]],
        "valid_ohlc_files": [shape["path"] for shape in source_shapes if shape["valid_ohlc_records"] > 0],
        "source_shapes": source_shapes,
    }


def inspect_local_candle_source_shape(
    path: str | Path,
    *,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    latest_candles: int = DEFAULT_LATEST_CANDLES,
    synthetic_context: bool | None = None,
) -> dict[str, Any]:
    resolved = Path(path)
    records = _read_records(resolved, latest_candles=latest_candles)
    valid = []
    invalid_reasons: Counter[str] = Counter()
    synthetic = bool(synthetic_context) or resolved.name in SYNTHETIC_CONTEXT_FILENAMES
    for record in records:
        candle, reason = _normalize_record_with_reason(
            record,
            symbol=symbol,
            timeframe=timeframe,
            source=resolved.name,
            reject_synthetic=synthetic,
        )
        if candle is None:
            invalid_reasons[reason] += 1
        else:
            valid.append(candle)
    return {
        "path": str(resolved),
        "exists": resolved.exists(),
        "records_checked": len(records),
        "valid_ohlc_records": len(valid),
        "invalid_records": sum(invalid_reasons.values()),
        "invalid_reasons": dict(sorted(invalid_reasons.items())),
        "synthetic_context": synthetic,
        "sample_valid_candle": valid[-1] if valid else None,
    }


def normalize_valid_ohlc_records(
    source_shapes: Sequence[Mapping[str, Any]] | Sequence[Mapping[str, Any] | Sequence[Any]],
    *,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    latest_candles: int = DEFAULT_LATEST_CANDLES,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    shapes_or_records = list(source_shapes)
    if shapes_or_records and isinstance(shapes_or_records[0], Mapping) and "path" in shapes_or_records[0]:
        for shape in shapes_or_records:
            if bool(shape.get("synthetic_context")):
                continue
            for record in _read_records(Path(str(shape.get("path") or "")), latest_candles=latest_candles):
                candle, _reason = _normalize_record_with_reason(
                    record,
                    symbol=symbol,
                    timeframe=timeframe,
                    source=Path(str(shape.get("path") or "")).name,
                )
                if candle is not None:
                    normalized.append(candle)
    else:
        for record in shapes_or_records:
            candle, _reason = _normalize_record_with_reason(record, symbol=symbol, timeframe=timeframe, source="provided")
            if candle is not None:
                normalized.append(candle)
    by_key = {(row["symbol"], row["timeframe"], row["open_time"]): row for row in normalized}
    ordered = sorted(by_key.values(), key=lambda row: str(row.get("open_time") or row.get("timestamp") or ""))
    limit = _bounded_int(latest_candles, 1, MAX_LATEST_CANDLES, DEFAULT_LATEST_CANDLES)
    return ordered[-limit:]


def reject_invalid_or_synthetic_candle_sources(source_shapes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rejected = []
    for shape in source_shapes:
        if bool(shape.get("synthetic_context")) and int(shape.get("records_checked") or 0) > 0:
            rejected.append(
                {
                    "path": shape.get("path"),
                    "reason": "synthetic_signal_context_not_valid_ohlc",
                    "records_checked": shape.get("records_checked", 0),
                    "valid_ohlc_records": 0,
                }
            )
        elif bool(shape.get("exists")) and int(shape.get("valid_ohlc_records") or 0) == 0:
            rejected.append(
                {
                    "path": shape.get("path"),
                    "reason": "missing_required_true_ohlc_shape",
                    "records_checked": shape.get("records_checked", 0),
                    "invalid_reasons": dict(shape.get("invalid_reasons") or {}),
                }
            )
    return rejected


def build_candidate_candle_feed_schema() -> dict[str, list[str]]:
    return {
        "required_fields": ["symbol", "timeframe", "open_time", "open", "high", "low", "close", "source"],
        "optional_fields": ["timestamp", "close_time", "volume", "generated_at"],
    }


def build_future_candle_capture_plan(*, symbol: str = DEFAULT_SYMBOL, timeframe: str = DEFAULT_TIMEFRAME) -> list[dict[str, Any]]:
    return [
        {
            "step": "keep_local_paper_harvesters_running",
            "operator_action": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
            "reason": "preserves signal context while local candles are sourced separately",
        },
        {
            "step": "provide_or_mount_local_ohlc_file",
            "target_shape": build_candidate_candle_feed_schema(),
            "example_path": _candidate_output_path(symbol, timeframe),
            "reason": "R188 can adapt local OHLC files without Binance or network calls",
        },
        {
            "step": "run_r188_local_candle_feed_adapter_no_network",
            "operator_action": "RUN_R188_LOCAL_CANDLE_FEED_ADAPTER_NO_NETWORK",
            "reason": "optional future adapter may write a normalized feed only after exact confirmation",
        },
    ]


def build_detector_feed_readiness(
    *,
    valid_candles: Sequence[Mapping[str, Any]],
    invalid_or_synthetic_sources: Sequence[Mapping[str, Any]],
    source_shapes: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    shapes = list(source_shapes or [])
    existing_non_synthetic = [
        shape for shape in shapes if bool(shape.get("exists")) and not bool(shape.get("synthetic_context"))
    ]
    synthetic_with_records = [
        shape for shape in shapes if bool(shape.get("synthetic_context")) and int(shape.get("records_checked") or 0) > 0
    ]
    blockers: list[str] = []
    if valid_candles:
        readiness = VALID_LOCAL_OHLC_FEED_AVAILABLE
    elif synthetic_with_records and not existing_non_synthetic:
        readiness = SYNTHETIC_SIGNAL_CONTEXT_ONLY
        blockers.append("synthetic_signal_context_not_valid_ohlc")
    elif existing_non_synthetic:
        readiness = LOCAL_FEED_INVALID_SHAPE
        blockers.append("local_candle_like_files_lack_valid_true_ohlc_shape")
    else:
        readiness = LOCAL_FEED_MISSING
        blockers.append("missing_local_ohlc_feed")
    if readiness != VALID_LOCAL_OHLC_FEED_AVAILABLE:
        blockers.append(FUTURE_CAPTURE_PLAN_REQUIRED)
    if invalid_or_synthetic_sources and valid_candles:
        blockers.append("invalid_or_synthetic_sources_excluded")
    return {
        "three_black_crows_ready_to_detect": bool(valid_candles),
        "feed_readiness": readiness,
        "blockers": blockers,
    }


def append_local_candle_feed_preview_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = local_candle_feed_preview_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "preview_id": str(record.get("preview_id") or f"r187_local_candle_feed_preview_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_preview_requested": bool(record.get("record_preview_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_context": dict(record.get("target_context") or {}),
            "source_discovery": dict(record.get("source_discovery") or {}),
            "normalized_feed_preview": dict(record.get("normalized_feed_preview") or {}),
            "candidate_candle_feed_schema": dict(record.get("candidate_candle_feed_schema") or {}),
            "detector_feed_readiness": dict(record.get("detector_feed_readiness") or {}),
            "future_candle_capture_plan": list(record.get("future_candle_capture_plan") or []),
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


def load_local_candle_feed_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = local_candle_feed_preview_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_local_candle_feed_previews(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    readiness_counts = Counter(
        str((record.get("detector_feed_readiness") or {}).get("feed_readiness") or "UNKNOWN")
        for record in records
    )
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "feed_readiness_counts": dict(sorted(readiness_counts.items())),
        "last_preview_id": latest.get("preview_id"),
        "last_feed_readiness": (latest.get("detector_feed_readiness") or {}).get("feed_readiness")
        if isinstance(latest, Mapping)
        else None,
        "safety": dict(SAFETY),
    }


def local_candle_feed_preview_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_local_candle_feed_capture_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _candidate_source_files(log_dir: Path, symbol: str, timeframe: str) -> list[Path]:
    lower_symbol = str(symbol or DEFAULT_SYMBOL).lower()
    upper_symbol = str(symbol or DEFAULT_SYMBOL).upper()
    direct = [
        log_dir / "candles.ndjson",
        log_dir / "ohlc.ndjson",
        log_dir / "klines.ndjson",
        log_dir / "market_candles.ndjson",
        log_dir / "price_candles.ndjson",
        log_dir / "paper_candles.ndjson",
        log_dir / f"{lower_symbol}_{timeframe}_candles.ndjson",
        log_dir / f"{upper_symbol}_{timeframe}_candles.ndjson",
        log_dir / f"candles_{lower_symbol}_{timeframe}.ndjson",
        log_dir / f"candles_{upper_symbol}_{timeframe}.ndjson",
        log_dir / "candle_archive" / f"{upper_symbol}_{timeframe}.ndjson",
    ]
    wildcard_patterns = ("*candle*.ndjson", "*ohlc*.ndjson", "*kline*.ndjson")
    wildcards: list[Path] = []
    for pattern in wildcard_patterns:
        wildcards.extend(sorted(log_dir.glob(pattern)))
    archive_dir = log_dir / "candle_archive"
    if archive_dir.exists():
        wildcards.extend(sorted(archive_dir.glob("*.ndjson")))
    synthetic = [log_dir / filename for filename in SYNTHETIC_CONTEXT_FILENAMES]
    seen: set[Path] = set()
    ordered = []
    for path in [*direct, *wildcards, *synthetic]:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def _read_records(path: Path, *, latest_candles: int) -> list[Any]:
    if not path.exists():
        return []
    limit = _bounded_int(latest_candles, 1, MAX_LATEST_CANDLES, DEFAULT_LATEST_CANDLES)
    return read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)


def _normalize_record_with_reason(
    raw: Mapping[str, Any] | Sequence[Any] | object,
    *,
    symbol: str,
    timeframe: str,
    source: str,
    reject_synthetic: bool = False,
) -> tuple[dict[str, Any] | None, str]:
    if reject_synthetic:
        return None, "synthetic_context_source"
    if not isinstance(raw, Mapping) and not isinstance(raw, (list, tuple)):
        return None, "not_mapping_or_sequence"
    if isinstance(raw, Mapping) and _is_synthetic_record(raw):
        return None, "synthetic_or_signal_only_record"
    if isinstance(raw, Mapping):
        if isinstance(raw.get("candles") or raw.get("ohlc") or raw.get("klines"), list):
            nested = raw.get("candles") or raw.get("ohlc") or raw.get("klines")
            for item in nested:
                candle, reason = _normalize_record_with_reason(item, symbol=symbol, timeframe=timeframe, source=source)
                if candle is not None:
                    return candle, "ok"
            return None, "nested_records_missing_valid_ohlc"
        raw_symbol = str(raw.get("symbol") or "").strip().upper()
        raw_timeframe = str(raw.get("timeframe") or raw.get("interval") or "").strip()
        open_time = _first_present(raw, "open_time", "timestamp", "time", "candle_time")
        close_time = _first_present(raw, "close_time")
        open_value = _first_present(raw, "open", "o")
        high_value = _first_present(raw, "high", "h")
        low_value = _first_present(raw, "low", "l")
        close_value = _first_present(raw, "close", "c")
        volume = _first_present(raw, "volume", "v")
        raw_source = str(raw.get("source") or source)
    else:
        if len(raw) < 5:
            return None, "sequence_too_short"
        open_time, open_value, high_value, low_value, close_value = raw[:5]
        close_time = raw[6] if len(raw) > 6 else None
        volume = raw[5] if len(raw) > 5 else None
        raw_symbol = symbol.upper()
        raw_timeframe = timeframe
        raw_source = source
    if raw_symbol != symbol.upper():
        return None, "symbol_mismatch_or_missing"
    if raw_timeframe != timeframe:
        return None, "timeframe_mismatch_or_missing"
    if open_time in (None, ""):
        return None, "missing_open_time_or_timestamp"
    values = [_to_float(value) for value in (open_value, high_value, low_value, close_value)]
    if any(value is None for value in values):
        return None, "missing_numeric_ohlc"
    open_float, high_float, low_float, close_float = [float(value) for value in values]
    if high_float < max(open_float, close_float):
        return None, "high_below_open_or_close"
    if low_float > min(open_float, close_float):
        return None, "low_above_open_or_close"
    if high_float < low_float:
        return None, "high_below_low"
    candle = {
        "symbol": raw_symbol,
        "timeframe": raw_timeframe,
        "open_time": str(open_time),
        "timestamp": str(open_time),
        "open": open_float,
        "high": high_float,
        "low": low_float,
        "close": close_float,
        "source": raw_source,
    }
    if close_time not in (None, ""):
        candle["close_time"] = str(close_time)
    volume_float = _to_float(volume)
    if volume_float is not None:
        candle["volume"] = volume_float
    return candle, "ok"


def _is_synthetic_record(raw: Mapping[str, Any]) -> bool:
    truthy_flags = (
        "not_valid_for_three_black_crows_detection",
        "synthetic",
        "fake_ohlc",
        "signal_only",
        "paper_signal_status",
        "watch_only",
    )
    if any(bool(raw.get(key)) for key in truthy_flags):
        return True
    source = str(raw.get("source") or "").lower()
    if "synthetic" in source or "signal" in source or "scanner" in source or "harvester" in source:
        return True
    identity_keys = {"signal_id", "candidate_id", "scan_id", "harvest_id"}
    return bool(identity_keys.intersection(raw.keys()))


def _first_present(raw: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounded_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _latest_candle_time(candles: Sequence[Mapping[str, Any]]) -> str | None:
    return max((str(row.get("open_time") or row.get("timestamp") or "") for row in candles), default=None)


def _candidate_output_path(symbol: str, timeframe: str) -> str:
    return f"logs/hammer_radar_forward/candles_{str(symbol).upper()}_{timeframe}.ndjson"


def _target_context(symbol: str, timeframe: str) -> dict[str, Any]:
    return {
        "symbol": str(symbol or DEFAULT_SYMBOL).upper(),
        "timeframe": str(timeframe or DEFAULT_TIMEFRAME),
        "primary_lane": normalize_lane_key(symbol, timeframe, "short", "ladder_close_50_618") or DEFAULT_TARGET_LANE_KEY,
        "consumer": "three_black_crows_detector",
    }


def _status_for_readiness(feed_readiness: str) -> str:
    if feed_readiness == VALID_LOCAL_OHLC_FEED_AVAILABLE:
        return LOCAL_CANDLE_FEED_PREVIEW_READY
    return LOCAL_CANDLE_FEED_PREVIEW_BLOCKED


def _recommended_next_operator_move(feed_readiness: str) -> str:
    if feed_readiness == VALID_LOCAL_OHLC_FEED_AVAILABLE:
        return "RUN_R188_LOCAL_CANDLE_FEED_ADAPTER_NO_NETWORK"
    if feed_readiness == SYNTHETIC_SIGNAL_CONTEXT_ONLY:
        return "KEEP_MULTI_LANE_HARVESTER_RUNNING"
    return "PROVIDE_LOCAL_OHLC_FILE"


def _recommended_next_engineering_move(feed_readiness: str) -> str:
    if feed_readiness == VALID_LOCAL_OHLC_FEED_AVAILABLE:
        return "Build R188 local-only adapter to consume this OHLC shape; keep feed writes confirmation-gated."
    if feed_readiness == SYNTHETIC_SIGNAL_CONTEXT_ONLY:
        return "Keep signal context separate and add a true local OHLC capture source before detector consumption."
    if feed_readiness == LOCAL_FEED_INVALID_SHAPE:
        return "Fix local candle files to include symbol, timeframe, open_time/timestamp, numeric open/high/low/close, and source."
    return "Provide or collect a local OHLC candle file without Binance/network calls."


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
