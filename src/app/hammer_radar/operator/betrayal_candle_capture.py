"""R81.3 safe local candle capture/backfill for betrayal replay.

This module writes only local candle archive records. It does not fetch market
data, place orders, read secrets, or change live readiness.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_candle_archive import (
    ARCHIVE_DIRNAME,
    EXECUTION_MODE as ARCHIVE_EXECUTION_MODE,
    TARGET_TIMEFRAMES,
    append_archive_candles,
    build_betrayal_candle_archive,
    build_betrayal_candle_archive_status,
    normalize_candle,
)

PHASE = "R81.3"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "SAFE_CANDLE_CAPTURE_BACKFILL_ONLY_NO_ORDER"
SOURCE_MODE_LOCAL_ONLY = "LOCAL_ONLY"
SOURCE = "betrayal_candle_capture"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R81.3 captures/backfills local candles only. No orders, no network, no Binance."


def capture_candles(
    candles: list[Mapping[str, Any]],
    *,
    source: str = SOURCE,
    write: bool = True,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized = [
        candle
        for candle in (normalize_candle({**dict(item), "source": source}, fallback_source=source) for item in candles)
        if candle is not None
    ]
    written = append_archive_candles(normalized, log_dir=resolved_log_dir) if write else 0
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "source_mode": SOURCE_MODE_LOCAL_ONLY,
            "archive_dir": str(resolved_log_dir / ARCHIVE_DIRNAME),
            "candles_received": len(candles),
            "candles_normalized": len(normalized),
            "candles_written": written,
            "write": bool(write),
            "notes": [NO_ORDER_NOTE],
            **_safety_fields(),
        }
    )


def capture_resampled_frames(
    resampled_frames: Mapping[str, Any],
    *,
    symbol: str = "BTCUSDT",
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    candles: list[dict[str, Any]] = []
    for timeframe, frame in resampled_frames.items():
        if frame is None or getattr(frame, "empty", True):
            continue
        for _index, row in frame.iterrows():
            timestamp = _format_timestamp(row.get("close_time", row.get("open_time")))
            if timestamp is None:
                continue
            candles.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open_time": timestamp,
                    "timestamp": timestamp,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": _float_or_none(row.get("volume")),
                    "source": "hammer_radar_resampled_runtime",
                }
            )
    return capture_candles(candles, source="hammer_radar_resampled_runtime", write=True, log_dir=log_dir)


def backfill_betrayal_candle_capture(
    *,
    dry_run: bool = True,
    write: bool = False,
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int = 0,
    since_hours: int | None = None,
    source_mode: str = SOURCE_MODE_LOCAL_ONLY,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    normalized_source_mode = str(source_mode or SOURCE_MODE_LOCAL_ONLY).upper()
    before = build_betrayal_candle_archive_status(symbol=symbol, timeframe=timeframe, log_dir=resolved_log_dir)
    if normalized_source_mode != SOURCE_MODE_LOCAL_ONLY:
        archive_payload = {
            "status": "OK",
            "discovered_sources": [],
            "candles_found": 0,
            "candles_written": 0,
            "duplicate_candles_skipped": 0,
            "notes": [f"unsupported source_mode {normalized_source_mode}; only LOCAL_ONLY is enabled"],
        }
    else:
        archive_payload = build_betrayal_candle_archive(
            dry_run=dry_run,
            write=write,
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            since_hours=since_hours,
            log_dir=resolved_log_dir,
        )
    after = build_betrayal_candle_archive_status(symbol=symbol, timeframe=timeframe, log_dir=resolved_log_dir)
    if dry_run or not write:
        after = dict(after)
        after["target_coverage"] = archive_payload.get("target_coverage", before.get("target_coverage"))
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "source_mode": normalized_source_mode,
            "generated_at": datetime.now(UTC).isoformat(),
            "log_dir": str(resolved_log_dir),
            "archive_dir": str(resolved_log_dir / ARCHIVE_DIRNAME),
            "dry_run": bool(dry_run),
            "write": bool(write),
            "persisted": bool(archive_payload.get("persisted")),
            "discovered_sources": archive_payload.get("discovered_sources", []),
            "candles_found": int(archive_payload.get("candles_found") or 0),
            "candles_writable": int(archive_payload.get("candles_found") or 0),
            "candles_written": int(archive_payload.get("candles_written") or 0),
            "duplicate_candles_skipped": int(archive_payload.get("duplicate_candles_skipped") or 0),
            "target_coverage_before": before.get("target_coverage", {}),
            "target_coverage_after": after.get("target_coverage", {}),
            "missing_coverage": archive_payload.get("missing_coverage", []),
            "source_policy": "LOCAL_ONLY_NO_NETWORK",
            "archive_execution_mode": ARCHIVE_EXECUTION_MODE,
            "notes": [
                NO_ORDER_NOTE,
                "Runtime capture hook writes resampled Hammer Radar candles when the radar loop runs.",
                "Backfill scans local candle-shaped NDJSON only and reports zero when no source files exist.",
            ],
            **_safety_fields(),
        }
    )


def build_betrayal_candle_capture_status(
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    archive = build_betrayal_candle_archive_status(symbol=symbol, timeframe=timeframe, log_dir=log_dir)
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "capture_hook_exists": True,
            "capture_hook": "src.app.hammer_radar.main.capture_resampled_frames",
            "source_mode": SOURCE_MODE_LOCAL_ONLY,
            "archive_dir": archive.get("archive_dir"),
            "available": archive.get("available", []),
            "target_coverage": archive.get("target_coverage", {}),
            "notes": [NO_ORDER_NOTE],
            **_safety_fields(),
        }
    )


def build_betrayal_candle_capture_text(
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int = 0,
    since_hours: int | None = None,
    write: bool = False,
    source_mode: str = SOURCE_MODE_LOCAL_ONLY,
    log_dir: str | Path | None = None,
) -> str:
    payload = backfill_betrayal_candle_capture(
        dry_run=not write,
        write=write,
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
        since_hours=since_hours,
        source_mode=source_mode,
        log_dir=log_dir,
    )
    before = payload.get("target_coverage_before") if isinstance(payload.get("target_coverage_before"), dict) else {}
    after = payload.get("target_coverage_after") if isinstance(payload.get("target_coverage_after"), dict) else {}
    lines = [
        f"R81.3 betrayal candle capture: {payload.get('status')}",
        str(payload.get("execution_mode")),
        f"dry_run: {str(payload.get('dry_run')).lower()} write: {str(payload.get('write')).lower()} persisted: {str(payload.get('persisted')).lower()}",
        f"source_mode: {payload.get('source_mode')}",
        "No order placed. real_order_placed=false execution_attempted=false network_allowed=false secrets_shown=false.",
        f"discovered_sources: {', '.join(payload.get('discovered_sources') or []) or 'none'}",
        f"candles_found: {payload.get('candles_found')}",
        f"candles_written: {payload.get('candles_written')}",
        f"duplicate_candles_skipped: {payload.get('duplicate_candles_skipped')}",
        "target_coverage_before_after:",
    ]
    for target in TARGET_TIMEFRAMES:
        before_row = before.get(target) if isinstance(before.get(target), dict) else {}
        after_row = after.get(target) if isinstance(after.get(target), dict) else {}
        lines.append(
            f"  {target}: before={before_row.get('covered_records', 0)}/{before_row.get('shadow_records', 0)} "
            f"after={after_row.get('covered_records', 0)}/{after_row.get('shadow_records', 0)} "
            f"candles_after={after_row.get('candles', 0)}"
        )
    lines.append(NO_ORDER_NOTE)
    return "\n".join(lines)


def _format_timestamp(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    try:
        return datetime.fromisoformat(str(value)).isoformat()
    except ValueError:
        return str(value)


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safety_fields() -> dict[str, Any]:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "order_payload_created": ORDER_PAYLOAD_CREATED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in (
            "live_execution_enabled",
            "allow_live_orders",
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "order_payload_created",
            "network_allowed",
            "secrets_shown",
        ):
            if key in sanitized:
                sanitized[key] = False
        if "global_kill_switch" in sanitized:
            sanitized["global_kill_switch"] = True
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
