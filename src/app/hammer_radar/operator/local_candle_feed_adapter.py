"""R188 local candle feed adapter.

This module adapts local OHLC archive files for detector consumers only. It
does not call Binance or any network, mutate env/config, create order payloads,
change lane modes, promote origins/lanes, or authorize live execution.
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
from src.app.hammer_radar.operator.local_candle_feed_capture_preview import (
    build_candidate_candle_feed_schema,
    inspect_local_candle_source_shape,
    normalize_valid_ohlc_records,
)
from src.app.hammer_radar.operator.three_black_crows_detector import (
    DEFAULT_DIRECTION,
    DEFAULT_LATEST_CANDLES,
    DEFAULT_SYMBOL,
    DEFAULT_TIMEFRAME,
    MAX_LATEST_CANDLES,
    NO_DETECTIONS_FOUND,
    SIGNAL_ORIGIN,
    UNKNOWN_NEEDS_MANUAL_REVIEW,
    classify_three_black_crows_detector_status,
    detect_three_black_crows_sequences,
)

LOCAL_CANDLE_FEED_ADAPTER_READY = "LOCAL_CANDLE_FEED_ADAPTER_READY"
LOCAL_CANDLE_FEED_ADAPTER_REJECTED = "LOCAL_CANDLE_FEED_ADAPTER_REJECTED"
LOCAL_CANDLE_FEED_ADAPTER_RECORDED = "LOCAL_CANDLE_FEED_ADAPTER_RECORDED"
LOCAL_CANDLE_FEED_ADAPTER_WRITTEN = "LOCAL_CANDLE_FEED_ADAPTER_WRITTEN"
LOCAL_CANDLE_FEED_ADAPTER_BLOCKED = "LOCAL_CANDLE_FEED_ADAPTER_BLOCKED"
LOCAL_CANDLE_FEED_ADAPTER_ERROR = "LOCAL_CANDLE_FEED_ADAPTER_ERROR"

DETECTOR_READY_LOCAL_OHLC_AVAILABLE = "DETECTOR_READY_LOCAL_OHLC_AVAILABLE"
LOCAL_OHLC_MISSING = "LOCAL_OHLC_MISSING"
LOCAL_OHLC_INVALID = "LOCAL_OHLC_INVALID"
NORMALIZED_FEED_READY = "NORMALIZED_FEED_READY"
NORMALIZED_FEED_WRITE_BLOCKED_BY_DEFAULT = "NORMALIZED_FEED_WRITE_BLOCKED_BY_DEFAULT"
UNKNOWN_NEEDS_MANUAL_REVIEW_STATUS = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "LOCAL_CANDLE_FEED_ADAPTER"
LEDGER_FILENAME = "local_candle_feed_adapter.ndjson"
CONFIRM_LOCAL_CANDLE_FEED_ADAPTER_RECORDING_PHRASE = (
    "I CONFIRM LOCAL CANDLE FEED ADAPTER RECORDING ONLY; NO FEED WRITE; NO ORDER; NO BINANCE CALL."
)
CONFIRM_NORMALIZED_LOCAL_CANDLE_FEED_WRITE_PHRASE = (
    "I CONFIRM NORMALIZED LOCAL CANDLE FEED WRITE ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "candle_feed_written": False,
    "fake_ohlc_created": False,
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
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/candle_archive/BTCUSDT_8m.ndjson",
    "operator.local_candle_feed_capture_preview.inspect_local_candle_source_shape",
    "operator.local_candle_feed_capture_preview.normalize_valid_ohlc_records",
    "operator.three_black_crows_detector.detect_three_black_crows_sequences",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_local_candle_feed_adapter_preview(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    latest_candles: int = DEFAULT_LATEST_CANDLES,
    record_adapter: bool = False,
    confirm_local_candle_feed_adapter: str | None = None,
    write_normalized_feed: bool = False,
    confirm_normalized_candle_feed_write: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    normalized_timeframe = str(timeframe or DEFAULT_TIMEFRAME).strip()
    record_confirmation_valid = confirm_local_candle_feed_adapter == CONFIRM_LOCAL_CANDLE_FEED_ADAPTER_RECORDING_PHRASE
    write_confirmation_valid = (
        confirm_normalized_candle_feed_write == CONFIRM_NORMALIZED_LOCAL_CANDLE_FEED_WRITE_PHRASE
    )
    try:
        source_path = resolve_local_candle_feed_path(
            log_dir=resolved_log_dir,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
        )
        raw_records = load_local_candle_feed(source_path, latest_candles=latest_candles)
        normalized = normalize_local_candle_feed(
            raw_records,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            source=source_path.name,
            latest_candles=latest_candles,
        )
        validation = validate_normalized_candle_feed(
            source_path=source_path,
            normalized_candles=normalized,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            latest_candles=latest_candles,
        )
        detector_ready = build_detector_ready_candle_feed(validation=validation, normalized_candles=normalized)
        detector_result = run_three_black_crows_on_local_feed(
            normalized,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            ohlc_feed_found=bool(validation["source_found"]),
        )
        output_path = _normalized_output_path(resolved_log_dir, normalized_symbol, normalized_timeframe)
        write_result = write_normalized_candle_feed_if_confirmed(
            normalized,
            output_path=output_path,
            write_normalized_feed=write_normalized_feed,
            confirmation_valid=write_confirmation_valid,
        )
        status = _status_for_adapter(
            detector_ready=detector_ready,
            record_adapter=record_adapter,
            record_confirmation_valid=record_confirmation_valid,
            write_normalized_feed=write_normalized_feed,
            write_confirmation_valid=write_confirmation_valid,
            normalized_feed_written=bool(write_result["written"]),
        )
        safety = dict(SAFETY)
        safety["candle_feed_written"] = bool(write_result["written"])
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "adapter_recorded": False,
            "adapter_id": None,
            "record_adapter_requested": bool(record_adapter),
            "confirmation_valid": bool(record_confirmation_valid),
            "write_normalized_feed_requested": bool(write_normalized_feed),
            "write_confirmation_valid": bool(write_confirmation_valid),
            "normalized_feed_written": bool(write_result["written"]),
            "target_context": _target_context(normalized_symbol, normalized_timeframe),
            "source_feed": {
                "path": _display_archive_path(normalized_symbol, normalized_timeframe),
                "source_found": bool(validation["source_found"]),
                "records_loaded": len(raw_records),
                "valid_records": int(validation["valid_records"]),
                "invalid_records": int(validation["invalid_records"]),
                "invalid_reasons": dict(validation.get("invalid_reasons") or {}),
            },
            "normalized_feed": {
                "normalized_records": len(normalized),
                "latest_candle_time": _latest_candle_time(normalized),
                "sample_candle": normalized[-1] if normalized else None,
                "output_path": _display_output_path(normalized_symbol, normalized_timeframe),
                "would_write_by_default": False,
                "written": bool(write_result["written"]),
                "normalized_feed_written": bool(write_result["written"]),
                "write_blocker": write_result.get("blocker"),
            },
            "detector_ready_feed": detector_ready,
            "three_black_crows_detector_result": detector_result,
            "candidate_candle_feed_schema": build_candidate_candle_feed_schema(),
            "recommended_next_operator_move": _recommended_next_operator_move(detector_ready, detector_result),
            "recommended_next_engineering_move": _recommended_next_engineering_move(detector_ready, detector_result),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_adapter and record_confirmation_valid:
            record = append_local_candle_feed_adapter_record(payload, log_dir=resolved_log_dir)
            payload["adapter_recorded"] = True
            payload["adapter_id"] = record["adapter_id"]
            payload["ledger_path"] = str(local_candle_feed_adapter_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": LOCAL_CANDLE_FEED_ADAPTER_ERROR,
                "generated_at": generated_at.isoformat(),
                "adapter_recorded": False,
                "adapter_id": None,
                "record_adapter_requested": bool(record_adapter),
                "confirmation_valid": bool(record_confirmation_valid),
                "write_normalized_feed_requested": bool(write_normalized_feed),
                "write_confirmation_valid": bool(write_confirmation_valid),
                "normalized_feed_written": False,
                "target_context": _target_context(normalized_symbol, normalized_timeframe),
                "source_feed": {
                    "path": _display_archive_path(normalized_symbol, normalized_timeframe),
                    "source_found": False,
                    "records_loaded": 0,
                    "valid_records": 0,
                    "invalid_records": 0,
                },
                "normalized_feed": {
                    "normalized_records": 0,
                    "latest_candle_time": None,
                    "sample_candle": None,
                    "output_path": _display_output_path(normalized_symbol, normalized_timeframe),
                    "would_write_by_default": False,
                    "written": False,
                    "normalized_feed_written": False,
                },
                "detector_ready_feed": {
                    "ready": False,
                    "adapter_readiness": UNKNOWN_NEEDS_MANUAL_REVIEW_STATUS,
                    "blockers": [UNKNOWN_NEEDS_MANUAL_REVIEW_STATUS],
                },
                "three_black_crows_detector_result": _empty_detector_result(UNKNOWN_NEEDS_MANUAL_REVIEW),
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R188 local candle feed adapter error and rerun without network.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def resolve_local_candle_feed_path(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> Path:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    return resolved_log_dir / "candle_archive" / f"{str(symbol or DEFAULT_SYMBOL).upper()}_{timeframe}.ndjson"


def load_local_candle_feed(path: str | Path, *, latest_candles: int = DEFAULT_LATEST_CANDLES) -> list[Any]:
    resolved = Path(path)
    if not resolved.exists():
        return []
    limit = _bounded_int(latest_candles, 1, MAX_LATEST_CANDLES, DEFAULT_LATEST_CANDLES)
    return read_recent_ndjson_records(resolved, limit=limit, max_bytes=32_000_000)


def normalize_local_candle_feed(
    records: Sequence[Mapping[str, Any] | Sequence[Any]],
    *,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    source: str = "local_candle_feed_adapter",
    latest_candles: int = DEFAULT_LATEST_CANDLES,
) -> list[dict[str, Any]]:
    stamped = []
    for record in records:
        if isinstance(record, Mapping):
            raw = dict(record)
            raw.setdefault("source", source)
            stamped.append(raw)
        else:
            stamped.append(record)
    return normalize_valid_ohlc_records(
        stamped,
        symbol=str(symbol or DEFAULT_SYMBOL).upper(),
        timeframe=str(timeframe or DEFAULT_TIMEFRAME),
        latest_candles=latest_candles,
    )


def validate_normalized_candle_feed(
    *,
    source_path: str | Path,
    normalized_candles: Sequence[Mapping[str, Any]],
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    latest_candles: int = DEFAULT_LATEST_CANDLES,
) -> dict[str, Any]:
    shape = inspect_local_candle_source_shape(
        source_path,
        symbol=str(symbol or DEFAULT_SYMBOL).upper(),
        timeframe=str(timeframe or DEFAULT_TIMEFRAME),
        latest_candles=latest_candles,
    )
    invalid_reasons = dict(shape.get("invalid_reasons") or {})
    shape_valid = int(shape.get("valid_ohlc_records") or 0)
    return {
        "source_found": bool(shape.get("exists")),
        "records_checked": int(shape.get("records_checked") or 0),
        "valid_records": min(shape_valid, len(normalized_candles)) if normalized_candles else 0,
        "invalid_records": int(shape.get("invalid_records") or 0),
        "invalid_reasons": invalid_reasons,
        "all_normalized_records_valid": all(_is_valid_normalized_candle(row, symbol=symbol, timeframe=timeframe) for row in normalized_candles),
    }


def build_detector_ready_candle_feed(
    *,
    validation: Mapping[str, Any],
    normalized_candles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    blockers: list[str] = []
    if not bool(validation.get("source_found")):
        return {"ready": False, "adapter_readiness": LOCAL_OHLC_MISSING, "blockers": ["missing_local_ohlc_feed"]}
    if not normalized_candles or not bool(validation.get("all_normalized_records_valid")):
        return {"ready": False, "adapter_readiness": LOCAL_OHLC_INVALID, "blockers": ["local_ohlc_invalid"]}
    if int(validation.get("invalid_records") or 0) > 0:
        blockers.append("invalid_records_excluded")
    return {
        "ready": True,
        "adapter_readiness": DETECTOR_READY_LOCAL_OHLC_AVAILABLE,
        "blockers": blockers,
    }


def run_three_black_crows_on_local_feed(
    candles: Sequence[Mapping[str, Any]],
    *,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    ohlc_feed_found: bool = True,
) -> dict[str, Any]:
    strict = (
        detect_three_black_crows_sequences(candles, symbol=symbol, timeframe=timeframe, mode="strict")
        if ohlc_feed_found and len(candles) >= 3
        else []
    )
    loose = (
        detect_three_black_crows_sequences(candles, symbol=symbol, timeframe=timeframe, mode="loose_preview")
        if ohlc_feed_found and len(candles) >= 3
        else []
    )
    detector_status = classify_three_black_crows_detector_status(
        ohlc_feed_found=ohlc_feed_found,
        records_checked=len(candles),
        detections=strict or loose,
    )
    latest_detection_at = max(
        (str(row.get("detected_at") or "") for row in [*strict, *loose]),
        default=None,
    )
    return {
        "detector_status": detector_status,
        "strict_detections_found": len(strict),
        "loose_detections_found": len(loose),
        "latest_detection_at": latest_detection_at,
        "paper_only": True,
        "live_authorized": False,
    }


def write_normalized_candle_feed_if_confirmed(
    candles: Sequence[Mapping[str, Any]],
    *,
    output_path: str | Path,
    write_normalized_feed: bool = False,
    confirmation_valid: bool = False,
) -> dict[str, Any]:
    if not write_normalized_feed:
        return {"written": False, "blocker": NORMALIZED_FEED_WRITE_BLOCKED_BY_DEFAULT}
    if not confirmation_valid:
        return {"written": False, "blocker": "normalized_feed_write_confirmation_invalid"}
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for candle in candles:
            handle.write(json.dumps(_sanitize(candle), sort_keys=True, separators=(",", ":")) + "\n")
    return {"written": True, "blocker": None, "path": str(path)}


def build_local_candle_feed_adapter_summary(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    return summarize_local_candle_feed_adapters(load_local_candle_feed_adapter_records(log_dir=log_dir, limit=limit))


def append_local_candle_feed_adapter_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = local_candle_feed_adapter_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "adapter_id": str(record.get("adapter_id") or f"r188_local_candle_feed_adapter_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_adapter_requested": bool(record.get("record_adapter_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "write_normalized_feed_requested": bool(record.get("write_normalized_feed_requested")),
            "normalized_feed_written": bool(record.get("normalized_feed_written")),
            "target_context": dict(record.get("target_context") or {}),
            "source_feed": dict(record.get("source_feed") or {}),
            "normalized_feed": dict(record.get("normalized_feed") or {}),
            "detector_ready_feed": dict(record.get("detector_ready_feed") or {}),
            "three_black_crows_detector_result": dict(record.get("three_black_crows_detector_result") or {}),
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


def load_local_candle_feed_adapter_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = local_candle_feed_adapter_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_local_candle_feed_adapters(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    readiness_counts = Counter(
        str((record.get("detector_ready_feed") or {}).get("adapter_readiness") or "UNKNOWN")
        for record in records
    )
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "adapter_readiness_counts": dict(sorted(readiness_counts.items())),
        "last_adapter_id": latest.get("adapter_id") if isinstance(latest, Mapping) else None,
        "last_adapter_readiness": (latest.get("detector_ready_feed") or {}).get("adapter_readiness")
        if isinstance(latest, Mapping)
        else None,
        "safety": dict(SAFETY),
    }


def local_candle_feed_adapter_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_local_candle_feed_adapter_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _status_for_adapter(
    *,
    detector_ready: Mapping[str, Any],
    record_adapter: bool,
    record_confirmation_valid: bool,
    write_normalized_feed: bool,
    write_confirmation_valid: bool,
    normalized_feed_written: bool,
) -> str:
    if record_adapter and not record_confirmation_valid:
        return LOCAL_CANDLE_FEED_ADAPTER_REJECTED
    if write_normalized_feed and not write_confirmation_valid:
        return LOCAL_CANDLE_FEED_ADAPTER_REJECTED
    if normalized_feed_written:
        return LOCAL_CANDLE_FEED_ADAPTER_WRITTEN
    if record_adapter and record_confirmation_valid:
        return LOCAL_CANDLE_FEED_ADAPTER_RECORDED
    if not bool(detector_ready.get("ready")):
        return LOCAL_CANDLE_FEED_ADAPTER_BLOCKED
    return LOCAL_CANDLE_FEED_ADAPTER_READY


def _target_context(symbol: str, timeframe: str) -> dict[str, Any]:
    return {
        "symbol": str(symbol or DEFAULT_SYMBOL).upper(),
        "timeframe": str(timeframe or DEFAULT_TIMEFRAME),
        "primary_lane": normalize_lane_key(symbol, timeframe, DEFAULT_DIRECTION, "ladder_close_50_618"),
        "consumer": "three_black_crows_detector",
        "signal_origin": SIGNAL_ORIGIN,
    }


def _normalized_output_path(log_dir: Path, symbol: str, timeframe: str) -> Path:
    return log_dir / f"candles_{str(symbol or DEFAULT_SYMBOL).upper()}_{timeframe}.ndjson"


def _display_archive_path(symbol: str, timeframe: str) -> str:
    return f"logs/hammer_radar_forward/candle_archive/{str(symbol or DEFAULT_SYMBOL).upper()}_{timeframe}.ndjson"


def _display_output_path(symbol: str, timeframe: str) -> str:
    return f"logs/hammer_radar_forward/candles_{str(symbol or DEFAULT_SYMBOL).upper()}_{timeframe}.ndjson"


def _latest_candle_time(candles: Sequence[Mapping[str, Any]]) -> str | None:
    if not candles:
        return None
    return max(str(row.get("open_time") or row.get("timestamp") or "") for row in candles) or None


def _is_valid_normalized_candle(
    candle: Mapping[str, Any],
    *,
    symbol: str,
    timeframe: str,
) -> bool:
    if str(candle.get("symbol") or "").upper() != str(symbol or DEFAULT_SYMBOL).upper():
        return False
    if str(candle.get("timeframe") or "") != str(timeframe or DEFAULT_TIMEFRAME):
        return False
    if not (candle.get("open_time") or candle.get("timestamp")):
        return False
    if not candle.get("source"):
        return False
    values = [_to_float(candle.get(key)) for key in ("open", "high", "low", "close")]
    if any(value is None for value in values):
        return False
    open_value, high_value, low_value, close_value = [float(value) for value in values]
    if high_value < max(open_value, close_value):
        return False
    if low_value > min(open_value, close_value):
        return False
    return high_value >= low_value


def _recommended_next_operator_move(
    detector_ready: Mapping[str, Any],
    detector_result: Mapping[str, Any],
) -> str:
    if bool(detector_ready.get("ready")):
        return "RUN_R189_THREE_BLACK_CROWS_DETECTION_ON_LOCAL_FEED"
    if detector_result.get("detector_status") == NO_DETECTIONS_FOUND:
        return "KEEP_MULTI_LANE_HARVESTER_RUNNING"
    return "RUN_R186_AFTER_NORMALIZED_FEED"


def _recommended_next_engineering_move(
    detector_ready: Mapping[str, Any],
    detector_result: Mapping[str, Any],
) -> str:
    if bool(detector_ready.get("ready")):
        return "Build R189 paper-only Three Black Crows local-feed detection/tagging on top of the R188 adapter output."
    if detector_result.get("detector_status") == UNKNOWN_NEEDS_MANUAL_REVIEW:
        return "Review local archive candle shape before detector integration; do not synthesize OHLC."
    return "Keep using the R187/R188 local-only candle path and rerun once valid local OHLC is present."


def _empty_detector_result(detector_status: str) -> dict[str, Any]:
    return {
        "detector_status": detector_status,
        "strict_detections_found": 0,
        "loose_detections_found": 0,
        "latest_detection_at": None,
        "paper_only": True,
        "live_authorized": False,
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
    ]


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
