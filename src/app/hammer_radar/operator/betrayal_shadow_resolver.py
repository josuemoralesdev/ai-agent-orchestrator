"""R81.1 local betrayal shadow outcome resolver.

The resolver turns unresolved betrayal shadow records into resolved paper-only
shadow outcomes when local archived candle data is available. It never fetches
market data, places orders, or changes live readiness.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_candle_archive import load_archive_candles
from src.app.hammer_radar.operator.betrayal_shadow_outcomes import (
    OUTCOMES_FILENAME,
    RESOLVED_STATUSES,
    SHADOW_LOSS,
    SHADOW_NO_DATA,
    SHADOW_OPEN,
    SHADOW_UNRESOLVED,
    SHADOW_WIN,
    load_betrayal_shadow_outcomes,
)
from src.app.hammer_radar.operator.strategy_config import TIMEFRAME_MINUTES

PHASE = "R81.1"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "BETRAYAL_SHADOW_OUTCOME_RESOLVER_ONLY_NO_ORDER"
RESOLUTIONS_FILENAME = "betrayal_shadow_resolutions.ndjson"
SOURCE = "betrayal_shadow_outcome_resolver"

CANDLE_FILENAMES = (
    "candles.ndjson",
    "market_candles.ndjson",
    "price_candles.ndjson",
    "paper_candles.ndjson",
)
UNRESOLVED_STATUSES = {SHADOW_OPEN, SHADOW_NO_DATA, SHADOW_UNRESOLVED}
EVALUATION_WINDOW_MULTIPLIER = 3
MIN_EVALUATION_WINDOW_MINUTES = 60
TEMPORAL_ALIGNMENT_OK = "TEMPORAL_ALIGNMENT_OK"
TEMPORAL_ALIGNMENT_INVALID = "TEMPORAL_ALIGNMENT_INVALID"
TEMPORAL_ALIGNMENT_MISSING_DATA = "TEMPORAL_ALIGNMENT_MISSING_DATA"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R81.1 resolves local paper shadow outcomes only. No orders, no network, no Binance."


def resolve_betrayal_shadow_outcomes(
    *,
    limit: int = 0,
    symbol: str | None = None,
    timeframe: str | None = None,
    dry_run: bool = True,
    write: bool = False,
    since_hours: int | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC)
    source_records = _candidate_records(
        load_betrayal_shadow_outcomes(log_dir=resolved_log_dir, newest_first=False),
        symbol=symbol,
        timeframe=timeframe,
        since_hours=since_hours,
        generated_at=generated_at,
    )
    if limit > 0:
        source_records = source_records[:limit]
    existing_resolutions = annotate_resolution_records(
        load_betrayal_shadow_resolutions(log_dir=resolved_log_dir, newest_first=False)
    )
    existing_valid_ids = {
        str(record.get("shadow_outcome_id"))
        for record in existing_resolutions
        if record.get("temporal_alignment_ok") is True
    }
    invalid_resolution_records = sum(
        1 for record in existing_resolutions if record.get("temporal_alignment_ok") is False
    )
    candles = load_local_candles(log_dir=resolved_log_dir)

    resolution_records: list[dict[str, Any]] = []
    blockers: list[str] = []
    already_resolved = 0
    still_open = 0
    no_data = 0
    unresolved = 0

    for record in source_records:
        if str(record.get("shadow_status")) in RESOLVED_STATUSES or str(record.get("shadow_outcome_id")) in existing_valid_ids:
            already_resolved += 1
            continue
        result = resolve_shadow_record(record, candles=candles, generated_at=generated_at)
        status = str(result.get("shadow_status"))
        if status in RESOLVED_STATUSES:
            resolution_records.append(result)
        elif status == SHADOW_OPEN:
            still_open += 1
        elif status == SHADOW_NO_DATA:
            no_data += 1
        else:
            unresolved += 1
        blockers.extend(str(item) for item in result.get("resolution_blockers", []) if item)

    persisted = False
    if resolution_records and write and not dry_run:
        append_betrayal_shadow_resolutions(resolution_records, log_dir=resolved_log_dir)
        persisted = True

    combined_records = merge_shadow_records_with_resolutions(
        load_betrayal_shadow_outcomes(log_dir=resolved_log_dir, newest_first=False),
        load_betrayal_shadow_resolutions(log_dir=resolved_log_dir, newest_first=False),
    )
    if dry_run or not write:
        combined_records = merge_shadow_records_with_resolutions(
            combined_records,
            resolution_records,
        )
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at.isoformat(),
            "log_dir": str(resolved_log_dir),
            "dry_run": bool(dry_run),
            "write": bool(write),
            "persisted": persisted,
            "resolution_output_file": str(_resolutions_path(resolved_log_dir)),
            "scanned_records": len(source_records),
            "already_resolved_records": already_resolved,
            "newly_resolved_records": len(resolution_records),
            "still_open_records": still_open,
            "no_data_records": no_data,
            "unresolved_records": unresolved,
            "invalid_resolution_records": invalid_resolution_records,
            "resolution_summary": _resolution_summary(combined_records),
            "timeframe_summary": _group_summary(combined_records, ("timeframe",)),
            "direction_entry_mode_summary": _group_summary(
                combined_records,
                ("timeframe", "original_direction", "shadow_direction"),
            ),
            "target_summary": {
                "222m": _target_summary(combined_records, "222m"),
                "88m": _target_summary(combined_records, "88m"),
                "55m": _target_summary(combined_records, "55m"),
            },
            "records": resolution_records,
            "blockers": sorted(set(blockers)),
            "notes": [
                NO_ORDER_NOTE,
                "dry_run=true or write=false does not persist resolver output.",
                "Only dry_run=false and write=true appends resolved records to betrayal_shadow_resolutions.ndjson.",
                "If stop and take-profit hit in the same candle, loss is selected first for conservative safety.",
            ],
            **_safety_fields(),
        }
    )


def resolve_shadow_record(
    record: Mapping[str, Any],
    *,
    candles: list[dict[str, Any]],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(UTC)
    blockers = _record_blockers(record)
    candidate_candles = _candidate_symbol_timeframe_candles(record, candles)
    matching_candles = _matching_candles(record, candles)
    if not matching_candles:
        if candidate_candles:
            blockers.append("no_temporally_aligned_candles")
        else:
            blockers.append("no local candle data found for symbol/timeframe")
        return _unresolved_result(record, status=SHADOW_NO_DATA, blockers=blockers, generated_at=generated_at)
    if blockers:
        return _unresolved_result(record, status=SHADOW_UNRESOLVED, blockers=blockers, generated_at=generated_at)

    entry = float(record["shadow_entry"])
    stop = float(record["shadow_stop"])
    take_profit = float(record["shadow_take_profit"])
    direction = str(record.get("shadow_direction") or "")
    for candle in matching_candles:
        stop_hit = _stop_hit(direction=direction, stop=stop, candle=candle)
        take_profit_hit = _take_profit_hit(direction=direction, take_profit=take_profit, candle=candle)
        candle_timestamp = str(candle.get("timestamp") or candle.get("open_time") or candle.get("close_time") or "")
        # Conservative tie behavior matches existing paper position semantics:
        # when a candle can hit both levels, stop/loss wins because intrabar order is unknowable.
        if stop_hit:
            return _resolved_result(
                record,
                status=SHADOW_LOSS,
                exit_price=stop,
                close_reason="stop",
                candle_timestamp=candle_timestamp,
                alignment=is_candle_temporally_valid_for_shadow_record(record, candle),
                generated_at=generated_at,
            )
        if take_profit_hit:
            return _resolved_result(
                record,
                status=SHADOW_WIN,
                exit_price=take_profit,
                close_reason="take_profit",
                candle_timestamp=candle_timestamp,
                alignment=is_candle_temporally_valid_for_shadow_record(record, candle),
                generated_at=generated_at,
            )
    return _unresolved_result(
        record,
        status=SHADOW_OPEN,
        blockers=["local candles exist but neither stop nor take_profit was hit"],
        generated_at=generated_at,
    )


def build_betrayal_shadow_resolutions_payload(
    *,
    limit: int = 50,
    symbol: str | None = None,
    timeframe: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = load_betrayal_shadow_resolutions(log_dir=resolved_log_dir, newest_first=True)
    records = annotate_resolution_records(records)
    records = _filter_plain_records(records, symbol=symbol, timeframe=timeframe)
    if limit > 0:
        records = records[:limit]
    all_records = _filter_plain_records(
        annotate_resolution_records(load_betrayal_shadow_resolutions(log_dir=resolved_log_dir, newest_first=False)),
        symbol=symbol,
        timeframe=timeframe,
    )
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "log_dir": str(resolved_log_dir),
            "resolution_output_file": str(_resolutions_path(resolved_log_dir)),
            "records": records,
            "summary": _resolution_summary(all_records),
            **_safety_fields(),
        }
    )


def build_betrayal_shadow_resolve_text(
    *,
    limit: int = 0,
    symbol: str | None = None,
    timeframe: str | None = None,
    since_hours: int | None = None,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> str:
    payload = resolve_betrayal_shadow_outcomes(
        limit=limit,
        symbol=symbol,
        timeframe=timeframe,
        since_hours=since_hours,
        dry_run=not write,
        write=write,
        log_dir=log_dir,
    )
    target_summary = payload.get("target_summary") if isinstance(payload.get("target_summary"), dict) else {}
    lines = [
        f"R81.1 betrayal shadow resolver: {payload.get('status')}",
        str(payload.get("execution_mode")),
        f"dry_run: {str(payload.get('dry_run')).lower()} write: {str(payload.get('write')).lower()} persisted: {str(payload.get('persisted')).lower()}",
        "No order placed. real_order_placed=false execution_attempted=false network_allowed=false secrets_shown=false.",
        f"scanned_records: {payload.get('scanned_records')}",
        f"newly_resolved_records: {payload.get('newly_resolved_records')}",
        f"already_resolved_records: {payload.get('already_resolved_records')}",
        f"no_data_records: {payload.get('no_data_records')}",
        f"still_open_records: {payload.get('still_open_records')}",
        f"unresolved_records: {payload.get('unresolved_records')}",
        f"invalid_resolution_records: {payload.get('invalid_resolution_records', 0)}",
        "target_summary:",
    ]
    for target in ("222m", "88m", "55m"):
        summary = target_summary.get(target) if isinstance(target_summary.get(target), dict) else {}
        lines.append(
            f"  {target}: resolved={summary.get('resolved_records', 0)} "
            f"wins={summary.get('wins', 0)} losses={summary.get('losses', 0)} "
            f"no_data={summary.get('no_data_records', 0)} unresolved={summary.get('unresolved_records', 0)}"
        )
    lines.append(NO_ORDER_NOTE)
    return "\n".join(lines)


def load_betrayal_shadow_resolutions(
    *,
    log_dir: str | Path | None = None,
    newest_first: bool = True,
) -> list[dict[str, Any]]:
    path = _resolutions_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    if newest_first:
        records = list(reversed(records))
    return records


def append_betrayal_shadow_resolutions(records: list[dict[str, Any]], *, log_dir: Path) -> None:
    if not records:
        return
    path = _resolutions_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def merge_shadow_records_with_resolutions(
    shadow_records: list[dict[str, Any]],
    resolution_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {str(record.get("shadow_outcome_id")): dict(record) for record in shadow_records}
    for resolution in annotate_resolution_records(resolution_records):
        if resolution.get("temporal_alignment_ok") is False:
            continue
        shadow_id = str(resolution.get("shadow_outcome_id"))
        merged = dict(by_id.get(shadow_id, {}))
        merged.update(resolution)
        by_id[shadow_id] = merged
    return list(by_id.values())


def load_resolved_betrayal_shadow_records(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    return merge_shadow_records_with_resolutions(
        load_betrayal_shadow_outcomes(log_dir=resolved_log_dir, newest_first=False),
        load_betrayal_shadow_resolutions(log_dir=resolved_log_dir, newest_first=False),
    )


def load_betrayal_shadow_resolution_quality_summary(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = annotate_resolution_records(load_betrayal_shadow_resolutions(log_dir=log_dir, newest_first=False))
    return {
        "persisted_resolution_records": len(records),
        "temporally_valid_resolved_records": sum(
            1
            for record in records
            if record.get("shadow_status") in RESOLVED_STATUSES and record.get("temporal_alignment_ok") is True
        ),
        "temporally_invalid_resolved_records": sum(
            1
            for record in records
            if record.get("shadow_status") in RESOLVED_STATUSES and record.get("temporal_alignment_ok") is False
        ),
        "invalid_resolution_records": sum(
            1
            for record in records
            if record.get("shadow_status") in RESOLVED_STATUSES and record.get("temporal_alignment_ok") is False
        ),
    }


def annotate_resolution_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated = []
    for record in records:
        payload = dict(record)
        if payload.get("shadow_status") in RESOLVED_STATUSES or payload.get("resolved_candle_timestamp"):
            alignment = validate_resolution_temporal_alignment(payload)
            payload.update(alignment)
            if alignment["ok"] is False:
                blockers = list(payload.get("resolution_blockers") or [])
                blockers.extend(alignment["blockers"])
                payload["resolution_blockers"] = sorted(set(blockers))
            payload["temporal_alignment_ok"] = alignment["ok"]
            payload["temporal_alignment_status"] = alignment["status"]
        annotated.append(payload)
    return annotated


def load_local_candles(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    candles: list[dict[str, Any]] = load_archive_candles(log_dir=resolved_log_dir)
    for filename in CANDLE_FILENAMES:
        path = resolved_log_dir / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                candle = json.loads(line)
                if _valid_candle(candle):
                    candles.append(candle)
    candles.sort(key=lambda candle: str(candle.get("timestamp") or candle.get("open_time") or candle.get("close_time") or ""))
    return candles


def is_candle_temporally_valid_for_shadow_record(
    record: Mapping[str, Any],
    candle: Mapping[str, Any],
) -> dict[str, Any]:
    window = _evaluation_window(record)
    candle_time = _parse_timestamp(_candle_timestamp(candle))
    blockers = []
    if window["start"] is None or window["end"] is None:
        blockers.append("missing_signal_timestamp")
    if candle_time is None:
        blockers.append("missing_candle_timestamp")
    if str(candle.get("symbol") or record.get("symbol") or "") != str(record.get("symbol") or ""):
        blockers.append("candle_symbol_mismatch")
    if str(candle.get("timeframe") or record.get("timeframe") or "") != str(record.get("timeframe") or ""):
        blockers.append("candle_timeframe_mismatch")
    if candle_time is not None and window["start"] is not None and candle_time < window["start"]:
        blockers.append("candle_before_signal_timestamp")
    if candle_time is not None and window["end"] is not None and candle_time > window["end"]:
        blockers.append("candle_after_evaluation_window")
    if blockers:
        return {
            "ok": False,
            "status": TEMPORAL_ALIGNMENT_INVALID,
            "blockers": blockers,
            "evaluation_window_start": _format_dt(window["start"]),
            "evaluation_window_end": _format_dt(window["end"]),
        }
    return {
        "ok": True,
        "status": TEMPORAL_ALIGNMENT_OK,
        "blockers": [],
        "evaluation_window_start": _format_dt(window["start"]),
        "evaluation_window_end": _format_dt(window["end"]),
    }


def validate_resolution_temporal_alignment(record: Mapping[str, Any]) -> dict[str, Any]:
    window = _evaluation_window(record)
    resolved_time = _parse_timestamp(str(record.get("resolved_candle_timestamp") or ""))
    blockers = []
    if window["start"] is None or window["end"] is None:
        blockers.append("missing_signal_timestamp")
    if resolved_time is None:
        blockers.append("missing_resolved_candle_timestamp")
    if resolved_time is not None and window["start"] is not None and resolved_time < window["start"]:
        blockers.append("resolved_candle_before_signal_timestamp")
    if resolved_time is not None and window["end"] is not None and resolved_time > window["end"]:
        blockers.append("resolved_candle_after_evaluation_window")
    if blockers:
        return {
            "ok": False,
            "status": TEMPORAL_ALIGNMENT_INVALID,
            "blockers": blockers,
            "evaluation_window_start": _format_dt(window["start"]),
            "evaluation_window_end": _format_dt(window["end"]),
        }
    return {
        "ok": True,
        "status": TEMPORAL_ALIGNMENT_OK,
        "blockers": [],
        "evaluation_window_start": _format_dt(window["start"]),
        "evaluation_window_end": _format_dt(window["end"]),
    }


def _candidate_records(
    records: list[dict[str, Any]],
    *,
    symbol: str | None,
    timeframe: str | None,
    since_hours: int | None,
    generated_at: datetime,
) -> list[dict[str, Any]]:
    filtered = _filter_plain_records(records, symbol=symbol, timeframe=timeframe)
    if since_hours is not None:
        window_start = generated_at - timedelta(hours=max(since_hours, 0))
        filtered = [
            record
            for record in filtered
            if (timestamp := _parse_timestamp(str(record.get("signal_timestamp") or ""))) is not None
            and timestamp >= window_start
        ]
    return filtered


def _filter_plain_records(
    records: list[dict[str, Any]],
    *,
    symbol: str | None,
    timeframe: str | None,
) -> list[dict[str, Any]]:
    filtered = records
    if symbol:
        normalized_symbol = symbol.upper()
        filtered = [record for record in filtered if str(record.get("symbol", "")).upper() == normalized_symbol]
    if timeframe:
        filtered = [record for record in filtered if str(record.get("timeframe", "")) == timeframe]
    return filtered


def _candidate_symbol_timeframe_candles(record: Mapping[str, Any], candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    symbol = str(record.get("symbol") or "")
    timeframe = str(record.get("timeframe") or "")
    return [
        candle
        for candle in candles
        if str(candle.get("symbol") or symbol) == symbol and str(candle.get("timeframe") or timeframe) == timeframe
    ]


def _matching_candles(record: Mapping[str, Any], candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matched = [
        candle
        for candle in _candidate_symbol_timeframe_candles(record, candles)
        if is_candle_temporally_valid_for_shadow_record(record, candle)["ok"] is True
    ]
    matched.sort(key=lambda candle: _candle_timestamp(candle))
    return matched


def _record_blockers(record: Mapping[str, Any]) -> list[str]:
    blockers = []
    for key in ("shadow_direction", "shadow_entry", "shadow_stop", "shadow_take_profit", "signal_timestamp"):
        if record.get(key) in (None, ""):
            blockers.append(f"missing {key}")
    return blockers


def _unresolved_result(
    record: Mapping[str, Any],
    *,
    status: str,
    blockers: list[str],
    generated_at: datetime,
) -> dict[str, Any]:
    payload = dict(record)
    window = _evaluation_window(record)
    payload.update(
        {
            "resolver_phase": PHASE,
            "resolver_source": SOURCE,
            "resolved_at": None,
            "resolution_status": status,
            "shadow_status": status,
            "evaluation_window_start": _format_dt(window["start"]),
            "evaluation_window_end": _format_dt(window["end"]),
            "temporal_alignment_ok": False,
            "temporal_alignment_status": TEMPORAL_ALIGNMENT_MISSING_DATA,
            "resolution_blockers": blockers,
            **_safety_fields(),
        }
    )
    return _sanitize(payload)


def _resolved_result(
    record: Mapping[str, Any],
    *,
    status: str,
    exit_price: float,
    close_reason: str,
    candle_timestamp: str,
    alignment: Mapping[str, Any],
    generated_at: datetime,
) -> dict[str, Any]:
    direction = str(record.get("shadow_direction") or "")
    entry = float(record.get("shadow_entry") or 0.0)
    pnl_pct = _calculate_pnl_pct(direction=direction, entry_price=entry, exit_price=exit_price)
    payload = dict(record)
    payload.update(
        {
            "resolver_phase": PHASE,
            "resolver_source": SOURCE,
            "resolved_at": generated_at.isoformat(),
            "resolution_status": status,
            "resolved_candle_timestamp": candle_timestamp,
            "evaluation_window_start": alignment.get("evaluation_window_start"),
            "evaluation_window_end": alignment.get("evaluation_window_end"),
            "temporal_alignment_ok": alignment.get("ok") is True,
            "temporal_alignment_status": alignment.get("status"),
            "shadow_status": status,
            "shadow_exit_price": round(float(exit_price), 4),
            "shadow_close_reason": close_reason,
            "shadow_pnl_pct": pnl_pct,
            "true_inverse_pnl_pct": pnl_pct,
            "comparison": {
                "shadow_better": status == SHADOW_WIN,
                "original_better": status == SHADOW_LOSS,
                "inconclusive": False,
            },
            "resolution_blockers": list(alignment.get("blockers") or []),
            **_safety_fields(),
        }
    )
    return _sanitize(payload)


def _resolution_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for record in records if record.get("shadow_status") == SHADOW_WIN)
    losses = sum(1 for record in records if record.get("shadow_status") == SHADOW_LOSS)
    resolved = sum(1 for record in records if record.get("shadow_status") in RESOLVED_STATUSES)
    invalid = sum(
        1
        for record in records
        if record.get("shadow_status") in RESOLVED_STATUSES and record.get("temporal_alignment_ok") is False
    )
    no_data = sum(1 for record in records if record.get("shadow_status") == SHADOW_NO_DATA)
    unresolved = sum(1 for record in records if record.get("shadow_status") in {SHADOW_OPEN, SHADOW_UNRESOLVED})
    return {
        "total_records": len(records),
        "resolved_records": resolved,
        "temporally_valid_resolved_records": sum(
            1 for record in records if record.get("shadow_status") in RESOLVED_STATUSES and record.get("temporal_alignment_ok") is not False
        ),
        "temporally_invalid_resolved_records": invalid,
        "invalid_resolution_records": invalid,
        "wins": wins,
        "losses": losses,
        "no_data_records": no_data,
        "unresolved_records": unresolved,
        "win_rate_pct": round((wins / resolved) * 100.0, 2) if resolved else None,
    }


def _group_summary(records: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(tuple(record.get(key) for key in keys), []).append(record)
    rows = []
    for values, group_records in groups.items():
        row = dict(zip(keys, values, strict=True))
        row.update(_resolution_summary(group_records))
        rows.append(row)
    return sorted(rows, key=lambda row: (-int(row["resolved_records"]), str(row.get("timeframe") or "")))


def _target_summary(records: list[dict[str, Any]], timeframe: str) -> dict[str, Any]:
    return _resolution_summary([record for record in records if record.get("timeframe") == timeframe])


def _stop_hit(*, direction: str, stop: float, candle: Mapping[str, Any]) -> bool:
    if direction == "short":
        return float(candle["high"]) >= stop
    return float(candle["low"]) <= stop


def _take_profit_hit(*, direction: str, take_profit: float, candle: Mapping[str, Any]) -> bool:
    if direction == "short":
        return float(candle["low"]) <= take_profit
    return float(candle["high"]) >= take_profit


def _calculate_pnl_pct(*, direction: str, entry_price: float, exit_price: float) -> float:
    if entry_price == 0:
        return 0.0
    if direction == "short":
        return round(((entry_price - exit_price) / entry_price) * 100.0, 4)
    return round(((exit_price - entry_price) / entry_price) * 100.0, 4)


def _valid_candle(candle: Mapping[str, Any]) -> bool:
    return all(candle.get(key) is not None for key in ("high", "low")) and bool(
        candle.get("timestamp") or candle.get("open_time") or candle.get("close_time")
    )


def _evaluation_window(record: Mapping[str, Any]) -> dict[str, datetime | None]:
    signal_time = _parse_timestamp(str(record.get("signal_timestamp") or ""))
    if signal_time is None:
        return {"start": None, "end": None}
    timeframe_minutes = _timeframe_minutes(str(record.get("timeframe") or ""))
    window_minutes = max(timeframe_minutes * EVALUATION_WINDOW_MULTIPLIER, MIN_EVALUATION_WINDOW_MINUTES)
    return {"start": signal_time, "end": signal_time + timedelta(minutes=window_minutes)}


def _timeframe_minutes(timeframe: str) -> int:
    if timeframe in TIMEFRAME_MINUTES:
        return int(TIMEFRAME_MINUTES[timeframe])
    normalized = timeframe.strip()
    if normalized.endswith("m"):
        try:
            return int(normalized[:-1])
        except ValueError:
            return MIN_EVALUATION_WINDOW_MINUTES
    if normalized.endswith("H"):
        try:
            return int(normalized[:-1]) * 60
        except ValueError:
            return MIN_EVALUATION_WINDOW_MINUTES
    return MIN_EVALUATION_WINDOW_MINUTES


def _candle_timestamp(candle: Mapping[str, Any]) -> str:
    return str(candle.get("timestamp") or candle.get("open_time") or candle.get("close_time") or "")


def _format_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _resolutions_path(log_dir: Path) -> Path:
    return log_dir / RESOLUTIONS_FILENAME


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
