"""R81.2 local candle archive and replay bridge for betrayal validation.

The bridge normalizes local candle-shaped NDJSON records into a deterministic
archive that the betrayal shadow resolver can replay. It never fetches market
data and never touches live execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_shadow_outcomes import load_betrayal_shadow_outcomes

PHASE = "R81.2"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "BETRAYAL_CANDLE_ARCHIVE_REPLAY_BRIDGE_ONLY_NO_ORDER"
ARCHIVE_DIRNAME = "candle_archive"
SOURCE = "betrayal_candle_archive_bridge"

LOCAL_CANDLE_FILENAMES = (
    "candles.ndjson",
    "market_candles.ndjson",
    "price_candles.ndjson",
    "paper_candles.ndjson",
)
TARGET_TIMEFRAMES = ("222m", "88m", "55m")

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R81.2 builds local replay candle archives only. No orders, no network, no Binance."


def build_betrayal_candle_archive(
    *,
    dry_run: bool = True,
    write: bool = False,
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int = 0,
    since_hours: int | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC)
    discovered = discover_local_candles(
        log_dir=resolved_log_dir,
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
        since_hours=since_hours,
        generated_at=generated_at,
    )
    existing = load_archive_candles(log_dir=resolved_log_dir, symbol=symbol, timeframe=timeframe)
    existing_keys = {_candle_key(candle) for candle in existing}
    new_candles = [candle for candle in discovered["candles"] if _candle_key(candle) not in existing_keys]
    duplicate_count = len(discovered["candles"]) - len(new_candles)
    persisted = False
    written_count = 0
    if new_candles and write and not dry_run:
        written_count = append_archive_candles(new_candles, log_dir=resolved_log_dir)
        persisted = True
    archive_candles = load_archive_candles(log_dir=resolved_log_dir, symbol=symbol, timeframe=timeframe)
    effective_candles = [*archive_candles, *new_candles] if dry_run or not write else archive_candles
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at.isoformat(),
            "log_dir": str(resolved_log_dir),
            "archive_dir": str(_archive_dir(resolved_log_dir)),
            "dry_run": bool(dry_run),
            "write": bool(write),
            "persisted": persisted,
            "discovered_sources": discovered["discovered_sources"],
            "files_scanned": discovered["files_scanned"],
            "candles_found": len(discovered["candles"]),
            "candles_written": written_count,
            "duplicate_candles_skipped": duplicate_count,
            "target_coverage": _target_coverage(effective_candles, log_dir=resolved_log_dir),
            "missing_coverage": _missing_coverage(effective_candles, log_dir=resolved_log_dir),
            "notes": [
                NO_ORDER_NOTE,
                "dry_run=true or write=false does not persist archive candles.",
                "Only dry_run=false and write=true appends deduped local candles to candle_archive/*.ndjson.",
                "The bridge refuses to synthesize OHLC candles from non-candle logs.",
            ],
            **_safety_fields(),
        }
    )


def build_betrayal_candle_archive_status(
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    candles = load_archive_candles(log_dir=resolved_log_dir, symbol=symbol, timeframe=timeframe)
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "log_dir": str(resolved_log_dir),
            "archive_dir": str(_archive_dir(resolved_log_dir)),
            "available": _available_summary(candles),
            "target_coverage": _target_coverage(candles, log_dir=resolved_log_dir),
            "notes": [NO_ORDER_NOTE],
            **_safety_fields(),
        }
    )


def build_betrayal_candle_archive_text(
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int = 0,
    since_hours: int | None = None,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> str:
    payload = build_betrayal_candle_archive(
        dry_run=not write,
        write=write,
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
        since_hours=since_hours,
        log_dir=log_dir,
    )
    coverage = payload.get("target_coverage") if isinstance(payload.get("target_coverage"), dict) else {}
    lines = [
        f"R81.2 betrayal candle archive: {payload.get('status')}",
        str(payload.get("execution_mode")),
        f"dry_run: {str(payload.get('dry_run')).lower()} write: {str(payload.get('write')).lower()} persisted: {str(payload.get('persisted')).lower()}",
        "No order placed. real_order_placed=false execution_attempted=false network_allowed=false secrets_shown=false.",
        f"discovered_sources: {', '.join(payload.get('discovered_sources') or []) or 'none'}",
        f"files_scanned: {payload.get('files_scanned')}",
        f"candles_found: {payload.get('candles_found')}",
        f"candles_written: {payload.get('candles_written')}",
        f"duplicate_candles_skipped: {payload.get('duplicate_candles_skipped')}",
        "target_coverage:",
    ]
    for target in TARGET_TIMEFRAMES:
        item = coverage.get(target) if isinstance(coverage.get(target), dict) else {}
        lines.append(
            f"  {target}: shadow_records={item.get('shadow_records', 0)} "
            f"covered_records={item.get('covered_records', 0)} candles={item.get('candles', 0)}"
        )
    lines.append(NO_ORDER_NOTE)
    return "\n".join(lines)


def discover_local_candles(
    *,
    log_dir: str | Path | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int = 0,
    since_hours: int | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = generated_at or datetime.now(UTC)
    window_start = generated_at - timedelta(hours=max(since_hours, 0)) if since_hours is not None else None
    candles: list[dict[str, Any]] = []
    discovered_sources: set[str] = set()
    files_scanned = 0
    for path in _candidate_source_files(resolved_log_dir):
        files_scanned += 1
        file_candles = []
        for payload in _read_jsonl(path):
            normalized = normalize_candle(payload, fallback_source=path.name)
            if normalized is None:
                continue
            if symbol and normalized["symbol"].upper() != symbol.upper():
                continue
            if timeframe and normalized["timeframe"] != timeframe:
                continue
            if window_start is not None:
                timestamp = _parse_timestamp(normalized["open_time"])
                if timestamp is None or timestamp < window_start:
                    continue
            file_candles.append(normalized)
            discovered_sources.add(path.name)
        candles.extend(file_candles)
    candles = _dedupe_candles(candles)
    if limit > 0:
        candles = candles[:limit]
    return {
        "candles": candles,
        "discovered_sources": sorted(discovered_sources),
        "files_scanned": files_scanned,
    }


def normalize_candle(payload: Mapping[str, Any], *, fallback_source: str) -> dict[str, Any] | None:
    timestamp = payload.get("open_time") or payload.get("timestamp") or payload.get("close_time")
    symbol = payload.get("symbol")
    timeframe = payload.get("timeframe")
    high = _float_or_none(payload.get("high"))
    low = _float_or_none(payload.get("low"))
    close = _float_or_none(payload.get("close"))
    open_price = _float_or_none(payload.get("open"))
    if timestamp in (None, "") or symbol in (None, "") or timeframe in (None, "") or high is None or low is None:
        return None
    if close is None:
        close = open_price if open_price is not None else high
    if open_price is None:
        open_price = close
    return {
        "symbol": str(symbol).upper(),
        "timeframe": str(timeframe),
        "open_time": str(timestamp),
        "timestamp": str(timestamp),
        "open": round(float(open_price), 8),
        "high": round(float(high), 8),
        "low": round(float(low), 8),
        "close": round(float(close), 8),
        "volume": _float_or_none(payload.get("volume")),
        "source": str(payload.get("source") or fallback_source),
        "archived_at": datetime.now(UTC).isoformat(),
    }


def load_replay_candles(
    *,
    symbol: str,
    timeframe: str,
    start_timestamp: str,
    end_timestamp: str | None = None,
    max_lookahead: int = 0,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    candles = load_archive_candles(log_dir=log_dir, symbol=symbol, timeframe=timeframe)
    start = _parse_timestamp(start_timestamp)
    end = _parse_timestamp(end_timestamp or "") if end_timestamp else None
    replay = []
    for candle in candles:
        timestamp = _parse_timestamp(str(candle.get("open_time") or candle.get("timestamp") or ""))
        if timestamp is None or start is None or timestamp <= start:
            continue
        if end is not None and timestamp > end:
            continue
        replay.append(candle)
    if max_lookahead > 0:
        replay = replay[:max_lookahead]
    return replay


def load_archive_candles(
    *,
    log_dir: str | Path | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    archive_dir = _archive_dir(resolved_log_dir)
    if not archive_dir.exists():
        return []
    candles: list[dict[str, Any]] = []
    for path in sorted(archive_dir.glob("*.ndjson")):
        for payload in _read_jsonl(path):
            normalized = normalize_candle(payload, fallback_source=path.name)
            if normalized is None:
                continue
            if symbol and normalized["symbol"].upper() != symbol.upper():
                continue
            if timeframe and normalized["timeframe"] != timeframe:
                continue
            candles.append(normalized)
    return _dedupe_candles(candles)


def append_archive_candles(candles: list[dict[str, Any]], *, log_dir: Path) -> int:
    archive_dir = _archive_dir(log_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for candle in candles:
        grouped.setdefault((candle["symbol"], candle["timeframe"]), []).append(candle)
    written = 0
    for (symbol, timeframe), group in grouped.items():
        path = archive_dir / _archive_filename(symbol, timeframe)
        existing = []
        if path.exists():
            existing = [item for item in (normalize_candle(row, fallback_source=path.name) for row in _read_jsonl(path)) if item]
        by_key = {_candle_key(candle): candle for candle in existing}
        for candle in group:
            key = _candle_key(candle)
            if key in by_key:
                continue
            by_key[key] = candle
            written += 1
        ordered = sorted(by_key.values(), key=lambda item: str(item["open_time"]))
        with path.open("w", encoding="utf-8") as handle:
            for candle in ordered:
                handle.write(json.dumps(candle, sort_keys=True) + "\n")
    return written


def _candidate_source_files(log_dir: Path) -> list[Path]:
    files = [log_dir / filename for filename in LOCAL_CANDLE_FILENAMES if (log_dir / filename).exists()]
    archive_dir = _archive_dir(log_dir)
    if archive_dir.exists():
        files.extend(sorted(archive_dir.glob("*.ndjson")))
    return files


def _target_coverage(candles: list[dict[str, Any]], *, log_dir: Path) -> dict[str, dict[str, Any]]:
    shadow_records = load_betrayal_shadow_outcomes(log_dir=log_dir, newest_first=False)
    return {target: _coverage_for_timeframe(candles, shadow_records, target) for target in TARGET_TIMEFRAMES}


def _coverage_for_timeframe(
    candles: list[dict[str, Any]],
    shadow_records: list[dict[str, Any]],
    timeframe: str,
) -> dict[str, Any]:
    target_records = [record for record in shadow_records if record.get("timeframe") == timeframe]
    target_candles = [candle for candle in candles if candle.get("timeframe") == timeframe]
    covered = 0
    for record in target_records:
        signal_time = _parse_timestamp(str(record.get("signal_timestamp") or ""))
        if signal_time is None:
            continue
        if any(
            candle.get("symbol") == record.get("symbol")
            and (_parse_timestamp(str(candle.get("open_time") or "")) or datetime.min.replace(tzinfo=UTC)) > signal_time
            for candle in target_candles
        ):
            covered += 1
    return {
        "shadow_records": len(target_records),
        "covered_records": covered,
        "candles": len(target_candles),
    }


def _missing_coverage(candles: list[dict[str, Any]], *, log_dir: Path) -> list[str]:
    coverage = _target_coverage(candles, log_dir=log_dir)
    return [target for target, row in coverage.items() if row["shadow_records"] > 0 and row["covered_records"] == 0]


def _available_summary(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for candle in candles:
        grouped.setdefault((str(candle["symbol"]), str(candle["timeframe"])), []).append(candle)
    rows = []
    for (symbol, timeframe), group in grouped.items():
        timestamps = sorted(str(candle["open_time"]) for candle in group)
        rows.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "candle_count": len(group),
                "earliest_timestamp": timestamps[0] if timestamps else None,
                "latest_timestamp": timestamps[-1] if timestamps else None,
            }
        )
    return sorted(rows, key=lambda row: (row["symbol"], row["timeframe"]))


def _dedupe_candles(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {_candle_key(candle): candle for candle in candles}
    return sorted(by_key.values(), key=lambda candle: (candle["symbol"], candle["timeframe"], str(candle["open_time"])))


def _candle_key(candle: Mapping[str, Any]) -> tuple[str, str, str]:
    return str(candle.get("symbol") or ""), str(candle.get("timeframe") or ""), str(candle.get("open_time") or candle.get("timestamp") or "")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _archive_dir(log_dir: Path) -> Path:
    return log_dir / ARCHIVE_DIRNAME


def _archive_filename(symbol: str, timeframe: str) -> str:
    safe_symbol = symbol.upper().replace("/", "_")
    safe_timeframe = timeframe.replace("/", "_")
    return f"{safe_symbol}_{safe_timeframe}.ndjson"


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


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
