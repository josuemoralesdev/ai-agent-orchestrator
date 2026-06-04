"""R185 Three Black Crows detector preview.

This module reads local candle/OHLC ledgers only. It never calls Binance,
creates order payloads, mutates env/config, changes lane modes, promotes
origins/lanes, or authorizes live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, normalize_lane_key
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY

THREE_BLACK_CROWS_DETECTOR_READY = "THREE_BLACK_CROWS_DETECTOR_READY"
THREE_BLACK_CROWS_DETECTOR_REJECTED = "THREE_BLACK_CROWS_DETECTOR_REJECTED"
THREE_BLACK_CROWS_DETECTOR_RECORDED = "THREE_BLACK_CROWS_DETECTOR_RECORDED"
THREE_BLACK_CROWS_DETECTOR_BLOCKED = "THREE_BLACK_CROWS_DETECTOR_BLOCKED"
THREE_BLACK_CROWS_DETECTOR_ERROR = "THREE_BLACK_CROWS_DETECTOR_ERROR"

DETECTIONS_FOUND = "DETECTIONS_FOUND"
NO_DETECTIONS_FOUND = "NO_DETECTIONS_FOUND"
MISSING_OHLC_FEED = "MISSING_OHLC_FEED"
INSUFFICIENT_CANDLES = "INSUFFICIENT_CANDLES"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "THREE_BLACK_CROWS_DETECTOR"
LEDGER_FILENAME = "three_black_crows_detector.ndjson"
SIGNAL_ORIGIN = "three_black_crows"
DETECTOR_VERSION = "r185_preview"
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_TIMEFRAME = "8m"
DEFAULT_DIRECTION = "short"
DEFAULT_LATEST_CANDLES = 500
MAX_LATEST_CANDLES = 5000
STRICT_BODY_RATIO_THRESHOLD = 0.5
LOOSE_BODY_RATIO_THRESHOLD = 0.35
CONFIRM_THREE_BLACK_CROWS_DETECTOR_RECORDING_PHRASE = (
    "I CONFIRM THREE BLACK CROWS DETECTOR RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
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
    "live_authorization_created": False,
    "signal_origin_promoted": False,
    "lane_promoted": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/candles.ndjson",
    "logs/hammer_radar_forward/ohlc.ndjson",
    "logs/hammer_radar_forward/klines.ndjson",
    "logs/hammer_radar_forward/btcusdt_8m_candles.ndjson",
    "logs/hammer_radar_forward/BTCUSDT_8m_candles.ndjson",
    "operator.short_strategy_packet.DEFAULT_TARGET_LANE_KEY",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_three_black_crows_detector_preview(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    mode: str = "strict",
    latest_candles: int = DEFAULT_LATEST_CANDLES,
    record_detector: bool = False,
    confirm_three_black_crows_detector: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_symbol = str(symbol or DEFAULT_SYMBOL).strip().upper()
    normalized_timeframe = str(timeframe or DEFAULT_TIMEFRAME).strip()
    normalized_mode = _normalize_mode(mode)
    confirmation_valid = confirm_three_black_crows_detector == CONFIRM_THREE_BLACK_CROWS_DETECTOR_RECORDING_PHRASE
    try:
        source_files = _candidate_source_files(resolved_log_dir, normalized_symbol, normalized_timeframe)
        existing_files = [path for path in source_files if path.exists()]
        raw_records = _load_candle_records(existing_files, latest_candles=latest_candles)
        candles = normalize_candle_records(raw_records, symbol=normalized_symbol, timeframe=normalized_timeframe)
        detections = detect_three_black_crows_sequences(
            candles,
            symbol=normalized_symbol,
            timeframe=normalized_timeframe,
            mode=normalized_mode,
        )
        data_availability = {
            "ohlc_feed_found": bool(existing_files),
            "source_files_checked": [str(path) for path in source_files],
            "records_checked": len(candles),
            "blockers": _data_blockers(existing_files=existing_files, candles=candles),
        }
        detector_status = classify_three_black_crows_detector_status(
            ohlc_feed_found=bool(existing_files),
            records_checked=len(candles),
            detections=detections,
        )
        status = _preview_status(detector_status)
        if record_detector and not confirmation_valid:
            status = THREE_BLACK_CROWS_DETECTOR_REJECTED
        elif record_detector and confirmation_valid:
            status = THREE_BLACK_CROWS_DETECTOR_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "detector_recorded": False,
            "detector_id": None,
            "record_detector_requested": bool(record_detector),
            "confirmation_valid": bool(confirmation_valid),
            "detector": {
                "signal_origin": SIGNAL_ORIGIN,
                "detector_version": DETECTOR_VERSION,
                "mode": normalized_mode,
                "paper_only": True,
                "live_authorized": False,
            },
            "target_context": {
                "primary_lane": DEFAULT_TARGET_LANE_KEY,
                "symbol": normalized_symbol,
                "direction": DEFAULT_DIRECTION,
                "timeframes_checked": [normalized_timeframe],
            },
            "data_availability": data_availability,
            "detections": detections,
            "lane_summary": build_three_black_crows_lane_summary(
                detections=detections,
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
                data_availability=data_availability,
            ),
            "detector_status": detector_status,
            "recommended_next_operator_move": _recommended_next_operator_move(detector_status),
            "recommended_next_engineering_move": _recommended_next_engineering_move(detector_status),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_detector and confirmation_valid:
            record = append_three_black_crows_detector_record(payload, log_dir=resolved_log_dir)
            payload["detector_recorded"] = True
            payload["detector_id"] = record["detector_id"]
            payload["ledger_path"] = str(three_black_crows_detector_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": THREE_BLACK_CROWS_DETECTOR_ERROR,
                "generated_at": generated_at.isoformat(),
                "detector_recorded": False,
                "detector_id": None,
                "record_detector_requested": bool(record_detector),
                "confirmation_valid": bool(confirmation_valid),
                "detector": {
                    "signal_origin": SIGNAL_ORIGIN,
                    "detector_version": DETECTOR_VERSION,
                    "mode": normalized_mode,
                    "paper_only": True,
                    "live_authorized": False,
                },
                "target_context": {
                    "primary_lane": DEFAULT_TARGET_LANE_KEY,
                    "symbol": normalized_symbol,
                    "direction": DEFAULT_DIRECTION,
                    "timeframes_checked": [normalized_timeframe],
                },
                "data_availability": {
                    "ohlc_feed_found": False,
                    "source_files_checked": [],
                    "records_checked": 0,
                    "blockers": [UNKNOWN_NEEDS_MANUAL_REVIEW],
                },
                "detections": [],
                "lane_summary": {},
                "detector_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R185 detector preview error and rerun locally.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def detect_three_black_crows_sequences(
    candles: Sequence[Mapping[str, Any]],
    *,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    mode: str = "strict",
) -> list[dict[str, Any]]:
    normalized_mode = _normalize_mode(mode)
    threshold = STRICT_BODY_RATIO_THRESHOLD if normalized_mode == "strict" else LOOSE_BODY_RATIO_THRESHOLD
    rows = [dict(candle) for candle in candles]
    rows.sort(key=lambda row: str(row.get("timestamp") or ""))
    detections: list[dict[str, Any]] = []
    for index in range(2, len(rows)):
        window = rows[index - 2 : index + 1]
        if not _is_consecutive_window(window, timeframe):
            continue
        if not all(_is_bearish(candle) for candle in window):
            continue
        if not (float(window[2]["close"]) < float(window[1]["close"]) < float(window[0]["close"])):
            continue
        ratios = [_body_ratio(candle) for candle in window]
        if any(ratio < threshold for ratio in ratios):
            continue
        if normalized_mode == "strict" and not _strict_opens_valid(window):
            continue
        detections.append(
            build_three_black_crows_candidate(
                candles=window,
                symbol=symbol,
                timeframe=timeframe,
                mode=normalized_mode,
                body_ratios=ratios,
            )
        )
    return detections


def normalize_candle_records(
    records: Sequence[Mapping[str, Any] | Sequence[Any]],
    *,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in _flatten_records(records):
        candle = _normalize_candle(raw, symbol=symbol, timeframe=timeframe)
        if candle is not None:
            normalized.append(candle)
    normalized.sort(key=lambda row: str(row.get("timestamp") or ""))
    return normalized


def build_three_black_crows_candidate(
    *,
    candles: Sequence[Mapping[str, Any]],
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    mode: str = "strict",
    body_ratios: Sequence[float] | None = None,
) -> dict[str, Any]:
    ratios = list(body_ratios or [_body_ratio(candle) for candle in candles])
    detected_at = str(candles[-1].get("timestamp") or datetime.now(UTC).isoformat())
    confidence = "HIGH" if mode == "strict" and min(ratios or [0.0]) >= 0.6 else ("MEDIUM" if mode == "strict" else "LOW")
    return {
        "symbol": str(symbol or DEFAULT_SYMBOL).upper(),
        "timeframe": str(timeframe or DEFAULT_TIMEFRAME),
        "direction": DEFAULT_DIRECTION,
        "signal_origin": SIGNAL_ORIGIN,
        "detected_at": detected_at,
        "candle_times": [str(candle.get("timestamp") or "") for candle in candles],
        "confidence": confidence,
        "mode": _normalize_mode(mode),
        "paper_only": True,
        "live_authorized": False,
        "why": (
            "Three consecutive bearish candles with lower closes and "
            f"body ratios >= {min(ratios or [0.0]):.2f}; detector_version={DETECTOR_VERSION}."
        ),
    }


def build_three_black_crows_lane_summary(
    *,
    detections: Sequence[Mapping[str, Any]],
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str = DEFAULT_TIMEFRAME,
    data_availability: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    lane_key = normalize_lane_key(
        str(symbol or DEFAULT_SYMBOL).upper(),
        str(timeframe or DEFAULT_TIMEFRAME),
        DEFAULT_DIRECTION,
        "ladder_close_50_618",
    )
    latest_detection_at = max((str(row.get("detected_at") or "") for row in detections), default=None)
    blockers = list((data_availability or {}).get("blockers") or [])
    if not detections and not blockers:
        blockers.append("no_three_black_crows_detection")
    return {
        lane_key: {
            "detections_found": len(detections),
            "latest_detection_at": latest_detection_at,
            "ready_for_paper_tracking": bool(detections),
            "blockers": [] if detections else blockers,
        }
    }


def classify_three_black_crows_detector_status(
    *,
    ohlc_feed_found: bool,
    records_checked: int,
    detections: Sequence[Mapping[str, Any]],
) -> str:
    if not ohlc_feed_found:
        return MISSING_OHLC_FEED
    if records_checked < 3:
        return INSUFFICIENT_CANDLES
    if detections:
        return DETECTIONS_FOUND
    return NO_DETECTIONS_FOUND


def append_three_black_crows_detector_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = three_black_crows_detector_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "detector_id": str(record.get("detector_id") or f"r185_three_black_crows_detector_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_detector_requested": bool(record.get("record_detector_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "detector": dict(record.get("detector") or {}),
            "target_context": dict(record.get("target_context") or {}),
            "data_availability": dict(record.get("data_availability") or {}),
            "detections": list(record.get("detections") or []),
            "lane_summary": dict(record.get("lane_summary") or {}),
            "detector_status": record.get("detector_status"),
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


def load_three_black_crows_detector_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = three_black_crows_detector_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_three_black_crows_detector_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_detector_id": latest.get("detector_id"),
        "last_detector_status": latest.get("detector_status"),
        "last_detection_count": len(latest.get("detections") or []) if isinstance(latest, Mapping) else 0,
        "safety": dict(SAFETY),
    }


def three_black_crows_detector_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_three_black_crows_detector_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _candidate_source_files(log_dir: Path, symbol: str, timeframe: str) -> list[Path]:
    lower_symbol = symbol.lower()
    upper_symbol = symbol.upper()
    return [
        log_dir / "candles.ndjson",
        log_dir / "ohlc.ndjson",
        log_dir / "klines.ndjson",
        log_dir / f"{lower_symbol}_{timeframe}_candles.ndjson",
        log_dir / f"{upper_symbol}_{timeframe}_candles.ndjson",
        log_dir / f"candles_{lower_symbol}_{timeframe}.ndjson",
        log_dir / f"candles_{upper_symbol}_{timeframe}.ndjson",
    ]


def _load_candle_records(paths: Sequence[Path], *, latest_candles: int) -> list[dict[str, Any]]:
    limit = _bounded_int(latest_candles, 3, MAX_LATEST_CANDLES, DEFAULT_LATEST_CANDLES)
    records: list[dict[str, Any]] = []
    for path in paths:
        records.extend(read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000))
    return records[-limit:]


def _flatten_records(records: Sequence[Mapping[str, Any] | Sequence[Any]]) -> list[Mapping[str, Any] | Sequence[Any]]:
    flattened: list[Mapping[str, Any] | Sequence[Any]] = []
    for record in records:
        if isinstance(record, Mapping):
            nested = record.get("candles") or record.get("ohlc") or record.get("klines")
            if isinstance(nested, list):
                flattened.extend(item for item in nested if isinstance(item, (Mapping, list, tuple)))
                continue
        flattened.append(record)
    return flattened


def _normalize_candle(raw: Mapping[str, Any] | Sequence[Any], *, symbol: str, timeframe: str) -> dict[str, Any] | None:
    if isinstance(raw, Mapping):
        raw_symbol = str(raw.get("symbol") or symbol).strip().upper()
        raw_timeframe = str(raw.get("timeframe") or raw.get("interval") or timeframe).strip()
        if raw_symbol != symbol.upper() or raw_timeframe != timeframe:
            return None
        open_value = _first_present(raw, "open", "o")
        high_value = _first_present(raw, "high", "h")
        low_value = _first_present(raw, "low", "l")
        close_value = _first_present(raw, "close", "c")
        timestamp = _first_present(raw, "timestamp", "close_time", "open_time", "time", "candle_time", "created_at")
    elif isinstance(raw, (list, tuple)) and len(raw) >= 5:
        timestamp, open_value, high_value, low_value, close_value = raw[:5]
        raw_symbol = symbol.upper()
        raw_timeframe = timeframe
    else:
        return None
    values = [_to_float(value) for value in (open_value, high_value, low_value, close_value)]
    if any(value is None for value in values):
        return None
    open_float, high_float, low_float, close_float = [float(value) for value in values]
    if high_float < low_float or high_float <= 0 or low_float < 0:
        return None
    return {
        "symbol": raw_symbol,
        "timeframe": raw_timeframe,
        "timestamp": _normalize_timestamp(timestamp),
        "open": open_float,
        "high": high_float,
        "low": low_float,
        "close": close_float,
    }


def _first_present(raw: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


def _is_bearish(candle: Mapping[str, Any]) -> bool:
    return float(candle.get("close") or 0.0) < float(candle.get("open") or 0.0)


def _body_ratio(candle: Mapping[str, Any]) -> float:
    high = float(candle.get("high") or 0.0)
    low = float(candle.get("low") or 0.0)
    candle_range = high - low
    if candle_range <= 0:
        return 0.0
    return abs(float(candle.get("close") or 0.0) - float(candle.get("open") or 0.0)) / candle_range


def _strict_opens_valid(window: Sequence[Mapping[str, Any]]) -> bool:
    for previous, current in ((window[0], window[1]), (window[1], window[2])):
        previous_body_low = min(float(previous["open"]), float(previous["close"]))
        previous_body_high = max(float(previous["open"]), float(previous["close"]))
        tolerance = max(abs(float(previous["open"]) - float(previous["close"])) * 0.10, 0.0)
        current_open = float(current["open"])
        if current_open < previous_body_low - tolerance or current_open > previous_body_high + tolerance:
            return False
    return True


def _is_consecutive_window(window: Sequence[Mapping[str, Any]], timeframe: str) -> bool:
    expected_delta = _timeframe_delta(timeframe)
    if expected_delta is None:
        return True
    parsed = [_parse_datetime(candle.get("timestamp")) for candle in window]
    if any(item is None for item in parsed):
        return True
    return parsed[1] - parsed[0] == expected_delta and parsed[2] - parsed[1] == expected_delta


def _timeframe_delta(timeframe: str) -> timedelta | None:
    value = str(timeframe or "").strip().lower()
    try:
        if value.endswith("m"):
            return timedelta(minutes=int(value[:-1]))
        if value.endswith("h"):
            return timedelta(hours=int(value[:-1]))
        if value.endswith("d"):
            return timedelta(days=int(value[:-1]))
    except ValueError:
        return None
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        number = int(text)
        if number > 10_000_000_000:
            return datetime.fromtimestamp(number / 1000, tz=UTC)
        return datetime.fromtimestamp(number, tz=UTC)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _normalize_timestamp(value: Any) -> str:
    parsed = _parse_datetime(value)
    if parsed is not None:
        return parsed.isoformat()
    return str(value or "")


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _data_blockers(*, existing_files: Sequence[Path], candles: Sequence[Mapping[str, Any]]) -> list[str]:
    if not existing_files:
        return ["missing_ohlc_feed"]
    if len(candles) < 3:
        return ["insufficient_candles"]
    return []


def _preview_status(detector_status: str) -> str:
    if detector_status in {MISSING_OHLC_FEED, INSUFFICIENT_CANDLES, UNKNOWN_NEEDS_MANUAL_REVIEW}:
        return THREE_BLACK_CROWS_DETECTOR_BLOCKED
    return THREE_BLACK_CROWS_DETECTOR_READY


def _recommended_next_operator_move(detector_status: str) -> str:
    if detector_status == DETECTIONS_FOUND:
        return "RUN_R184_AFTER_DETECTIONS"
    if detector_status == MISSING_OHLC_FEED:
        return "RUN_R186_THREE_BLACK_CROWS_FEED_INTEGRATION"
    return "KEEP_MULTI_LANE_HARVESTER_RUNNING"


def _recommended_next_engineering_move(detector_status: str) -> str:
    if detector_status == DETECTIONS_FOUND:
        return "Wire R185 detections into R186 feed tagging while staying paper-only."
    if detector_status == MISSING_OHLC_FEED:
        return "Run R186 to integrate a local OHLC candle feed before expecting detections."
    if detector_status == INSUFFICIENT_CANDLES:
        return "Collect at least three consecutive OHLC candles for the target symbol/timeframe."
    return "Keep the detector preview available and rerun after fresh local candle data arrives."


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


def _normalize_mode(mode: str) -> str:
    return "loose_preview" if str(mode or "").strip() == "loose_preview" else "strict"


def _bounded_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


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
