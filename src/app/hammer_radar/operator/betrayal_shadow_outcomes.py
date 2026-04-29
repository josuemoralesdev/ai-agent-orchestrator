"""Shadow-only betrayal outcome tracking for Hammer Radar.

This module records hypothetical opposite-direction trades for betrayal
candidate signals. It never places orders and does not affect live readiness.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from src.app.hammer_radar.operator.archive import get_log_dir, load_outcomes, load_signals
from src.app.hammer_radar.operator.inspect import (
    _build_betrayal_candidate,
    _filter_symbol,
    _outcomes_by_signal,
    _timestamp_in_window,
)
from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord

OUTCOMES_FILENAME = "betrayal_shadow_outcomes.ndjson"
SOURCE = "betrayal_shadow_tracker"
LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False
SHADOW_ONLY = True

SHADOW_OPEN = "SHADOW_OPEN"
SHADOW_WIN = "SHADOW_WIN"
SHADOW_LOSS = "SHADOW_LOSS"
SHADOW_BREAKEVEN = "SHADOW_BREAKEVEN"
SHADOW_NO_DATA = "SHADOW_NO_DATA"
SHADOW_UNRESOLVED = "SHADOW_UNRESOLVED"
RESOLVED_STATUSES = {SHADOW_WIN, SHADOW_LOSS, SHADOW_BREAKEVEN}


def track_betrayal_shadow_outcomes(
    *,
    latest_only: bool = False,
    limit: int = 20,
    since_hours: int = 24,
    symbol: str | None = None,
    min_betrayal_score: int = 50,
    log_dir: str | Path | None = None,
) -> dict:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC)
    candidates = find_betrayal_shadow_candidates(
        latest_only=latest_only,
        limit=limit,
        since_hours=since_hours,
        symbol=symbol,
        min_betrayal_score=min_betrayal_score,
        log_dir=resolved_log_dir,
        generated_at=generated_at,
    )
    existing = load_betrayal_shadow_outcomes(log_dir=resolved_log_dir, newest_first=False)
    by_key = {
        _dedupe_key(record.get("original_signal_id"), record.get("shadow_direction")): record
        for record in existing
    }
    outcomes_by_signal = _outcomes_by_signal(load_outcomes(resolved_log_dir))
    created = 0
    updated = 0

    for candidate in candidates:
        record = build_shadow_outcome_record(
            candidate.signal,
            betrayal_score=candidate.score,
            betrayal_tier=candidate.tier,
            betrayal_reasons=candidate.reasons,
            shadow_direction=candidate.shadow_direction,
            original_outcomes=outcomes_by_signal.get(candidate.signal.signal_id, []),
            created_at=generated_at,
        )
        key = _dedupe_key(record["original_signal_id"], record["shadow_direction"])
        previous = by_key.get(key)
        if previous is None:
            by_key[key] = record
            created += 1
        else:
            merged = dict(previous)
            merged.update(record)
            merged["shadow_outcome_id"] = previous.get("shadow_outcome_id") or record["shadow_outcome_id"]
            merged["created_at"] = previous.get("created_at") or record["created_at"]
            if previous.get("shadow_status") in RESOLVED_STATUSES:
                merged["shadow_status"] = previous.get("shadow_status")
                merged["shadow_pnl_pct"] = previous.get("shadow_pnl_pct")
                merged["shadow_pnl_usd"] = previous.get("shadow_pnl_usd")
                merged["comparison"] = previous.get("comparison", record["comparison"])
            by_key[key] = merged
            updated += 1

    records = list(by_key.values())
    records.sort(key=lambda record: str(record.get("created_at", "")))
    _write_records(records, log_dir=resolved_log_dir)
    recent_records = _filter_records(list(reversed(records)), symbol=symbol, status=None)
    if limit > 0:
        recent_records = recent_records[:limit]
    return {
        "archive_log_dir": str(resolved_log_dir),
        "source": SOURCE,
        "created": created,
        "updated": updated,
        "candidate_count": len(candidates),
        "records": recent_records,
        "summary": summarize_betrayal_shadow_outcomes(records),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "shadow_only": SHADOW_ONLY,
    }


def find_betrayal_shadow_candidates(
    *,
    latest_only: bool = False,
    limit: int = 20,
    since_hours: int = 24,
    symbol: str | None = None,
    min_betrayal_score: int = 50,
    log_dir: str | Path | None = None,
    generated_at: datetime | None = None,
) -> list:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    now = generated_at or datetime.now(UTC)
    signals = _filter_symbol(load_signals(resolved_log_dir), symbol)
    outcomes = _filter_symbol(load_outcomes(resolved_log_dir), symbol)
    window_start = now - timedelta(hours=max(since_hours, 0))
    window_signals = [
        signal
        for signal in signals
        if _timestamp_in_window(signal.timestamp, window_start, now)
    ]
    if latest_only:
        window_signals = sorted(window_signals, key=lambda signal: signal.timestamp, reverse=True)[:5]

    outcomes_by_signal = _outcomes_by_signal(outcomes)
    candidates = [
        _build_betrayal_candidate(
            signal,
            generated_at=now,
            outcomes=outcomes_by_signal.get(signal.signal_id, []),
        )
        for signal in window_signals
    ]
    candidates = [candidate for candidate in candidates if candidate.score >= min_betrayal_score]
    candidates.sort(key=lambda candidate: (candidate.score, candidate.signal.timestamp), reverse=True)
    if not latest_only:
        candidates = candidates[: max(limit, 0)]
    return candidates


def build_shadow_outcome_record(
    signal: SignalRecord,
    *,
    betrayal_score: int,
    betrayal_tier: str,
    betrayal_reasons: list[str],
    shadow_direction: str,
    original_outcomes: list[OutcomeRecord] | None = None,
    created_at: datetime | None = None,
) -> dict:
    created = created_at or datetime.now(UTC)
    levels = build_symmetric_shadow_levels(signal, shadow_direction=shadow_direction)
    status = SHADOW_NO_DATA if levels["shadow_entry"] is not None else SHADOW_UNRESOLVED
    return {
        "shadow_outcome_id": _shadow_outcome_id(signal.signal_id, shadow_direction),
        "created_at": created.isoformat(),
        "source": SOURCE,
        "original_signal_id": signal.signal_id,
        "original_direction": signal.direction,
        "shadow_direction": shadow_direction,
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "signal_timestamp": signal.timestamp,
        "betrayal_score": betrayal_score,
        "betrayal_tier": betrayal_tier,
        "betrayal_reasons": list(betrayal_reasons),
        "original_tradable": signal.tradable,
        "original_reject_reason": signal.reject_reason,
        "original_entry": _round_price(signal.fib_618),
        "original_stop": _round_price(signal.invalidation),
        "original_take_profit": levels["original_take_profit"],
        "shadow_entry": levels["shadow_entry"],
        "shadow_stop": levels["shadow_stop"],
        "shadow_take_profit": levels["shadow_take_profit"],
        "shadow_status": status,
        "shadow_pnl_pct": None,
        "shadow_pnl_usd": None,
        "original_outcome_summary": _original_outcome_summary(original_outcomes or []),
        "comparison": {
            "shadow_better": False,
            "original_better": False,
            "inconclusive": True,
        },
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "shadow_only": SHADOW_ONLY,
    }


def build_symmetric_shadow_levels(signal: SignalRecord, *, shadow_direction: str) -> dict[str, float | None]:
    entry = _positive_float_or_none(signal.fib_618)
    stop = _positive_float_or_none(signal.invalidation)
    if entry is None or stop is None:
        return {
            "original_take_profit": None,
            "shadow_entry": entry,
            "shadow_stop": None,
            "shadow_take_profit": None,
        }
    risk_distance = abs(entry - stop)
    if risk_distance <= 0.0:
        return {
            "original_take_profit": None,
            "shadow_entry": _round_price(entry),
            "shadow_stop": None,
            "shadow_take_profit": None,
        }
    if signal.direction == "short":
        original_take_profit = entry - risk_distance
    else:
        original_take_profit = entry + risk_distance
    if shadow_direction == "long":
        shadow_stop = entry - risk_distance
        shadow_take_profit = entry + risk_distance
    elif shadow_direction == "short":
        shadow_stop = entry + risk_distance
        shadow_take_profit = entry - risk_distance
    else:
        shadow_stop = None
        shadow_take_profit = None
    return {
        "original_take_profit": _round_price(original_take_profit),
        "shadow_entry": _round_price(entry),
        "shadow_stop": _round_price(shadow_stop),
        "shadow_take_profit": _round_price(shadow_take_profit),
    }


def load_betrayal_shadow_outcomes(
    *,
    limit: int = 0,
    status: str | None = None,
    symbol: str | None = None,
    log_dir: str | Path | None = None,
    newest_first: bool = True,
) -> list[dict]:
    path = _outcomes_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    if newest_first:
        records = list(reversed(records))
    records = _filter_records(records, status=status, symbol=symbol)
    if limit > 0:
        return records[:limit]
    return records


def build_betrayal_shadow_outcomes_payload(
    *,
    limit: int = 50,
    status: str | None = None,
    symbol: str | None = None,
    log_dir: str | Path | None = None,
) -> dict:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    all_records = load_betrayal_shadow_outcomes(log_dir=resolved_log_dir, newest_first=False)
    records = load_betrayal_shadow_outcomes(
        limit=limit,
        status=status,
        symbol=symbol,
        log_dir=resolved_log_dir,
        newest_first=True,
    )
    return {
        "archive_log_dir": str(resolved_log_dir),
        "records": records,
        "summary": summarize_betrayal_shadow_outcomes(_filter_records(all_records, status=status, symbol=symbol)),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "shadow_only": SHADOW_ONLY,
    }


def summarize_betrayal_shadow_outcomes(records: list[dict]) -> dict:
    wins = [record for record in records if record.get("shadow_status") == SHADOW_WIN]
    losses = [record for record in records if record.get("shadow_status") == SHADOW_LOSS]
    breakeven = [record for record in records if record.get("shadow_status") == SHADOW_BREAKEVEN]
    unresolved = [
        record
        for record in records
        if record.get("shadow_status") in {SHADOW_OPEN, SHADOW_NO_DATA, SHADOW_UNRESOLVED}
    ]
    resolved = [*wins, *losses, *breakeven]
    pnl_values = [
        float(record["shadow_pnl_pct"])
        for record in records
        if record.get("shadow_pnl_pct") is not None
    ]
    return {
        "total_records": len(records),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "unresolved_no_data": len(unresolved),
        "win_rate": round((len(wins) / len(resolved)) * 100.0, 4) if resolved else None,
        "avg_shadow_pnl_pct": round(sum(pnl_values) / len(pnl_values), 4) if pnl_values else None,
        "best_timeframe": _best_timeframe(records),
        "enough_resolved_samples": len(resolved) >= 5,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "shadow_only": SHADOW_ONLY,
    }


def build_betrayal_shadow_track_text(
    *,
    latest_only: bool = False,
    limit: int = 20,
    since_hours: int = 24,
    symbol: str | None = None,
    min_betrayal_score: int = 50,
    log_dir: str | Path | None = None,
) -> str:
    payload = track_betrayal_shadow_outcomes(
        latest_only=latest_only,
        limit=limit,
        since_hours=since_hours,
        symbol=symbol,
        min_betrayal_score=min_betrayal_score,
        log_dir=log_dir,
    )
    summary = payload["summary"]
    lines = [
        "HAMMER RADAR BETRAYAL SHADOW TRACKER",
        f"archive_log_dir: {payload['archive_log_dir']}",
        f"source: {SOURCE}",
        f"candidate_count: {payload['candidate_count']}",
        f"created: {payload['created']}",
        f"updated: {payload['updated']}",
        "live_execution_enabled: false",
        "order_placed: false",
        "shadow_only: true",
        f"total_records: {summary['total_records']}",
        f"wins: {summary['wins']}",
        f"losses: {summary['losses']}",
        f"unresolved_no_data: {summary['unresolved_no_data']}",
    ]
    for record in payload["records"]:
        lines.append(
            f"{record.get('created_at')} | signal={record.get('original_signal_id')} | "
            f"{record.get('original_direction')} -> {record.get('shadow_direction')} | "
            f"score={record.get('betrayal_score')} | status={record.get('shadow_status')} | "
            f"comparison={_comparison_label(record.get('comparison'))}"
        )
    return "\n".join(lines)


def build_betrayal_shadow_outcomes_text(
    *,
    limit: int = 50,
    status: str | None = None,
    symbol: str | None = None,
    log_dir: str | Path | None = None,
) -> str:
    payload = build_betrayal_shadow_outcomes_payload(
        limit=limit,
        status=status,
        symbol=symbol,
        log_dir=log_dir,
    )
    summary = payload["summary"]
    lines = [
        "HAMMER RADAR BETRAYAL SHADOW OUTCOMES",
        f"archive_log_dir: {payload['archive_log_dir']}",
        "shadow_only: true",
        "live_execution_enabled: false",
        "order_placed: false",
        f"total_records: {summary['total_records']}",
        f"wins: {summary['wins']}",
        f"losses: {summary['losses']}",
        f"breakeven: {summary['breakeven']}",
        f"unresolved_no_data: {summary['unresolved_no_data']}",
        f"win_rate: {_format_optional(summary['win_rate'])}",
        f"avg_shadow_pnl_pct: {_format_optional(summary['avg_shadow_pnl_pct'])}",
        f"best_timeframe: {summary['best_timeframe'] or 'n/a'}",
    ]
    if not payload["records"]:
        lines.append("no betrayal shadow outcome records")
        return "\n".join(lines)
    for record in payload["records"]:
        lines.append(
            f"{record.get('created_at')} | signal={record.get('original_signal_id')} | "
            f"{record.get('symbol')} {record.get('timeframe')} | "
            f"{record.get('original_direction')} -> {record.get('shadow_direction')} | "
            f"score={record.get('betrayal_score')}/{record.get('betrayal_tier')} | "
            f"status={record.get('shadow_status')} | pnl={_format_optional(record.get('shadow_pnl_pct'))} | "
            f"comparison={_comparison_label(record.get('comparison'))}"
        )
    return "\n".join(lines)


def _write_records(records: list[dict], *, log_dir: Path) -> None:
    path = _outcomes_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _outcomes_path(log_dir: Path) -> Path:
    return log_dir / OUTCOMES_FILENAME


def _filter_records(records: list[dict], *, status: str | None = None, symbol: str | None = None) -> list[dict]:
    filtered = records
    if status:
        filtered = [record for record in filtered if record.get("shadow_status") == status]
    if symbol:
        normalized_symbol = symbol.upper()
        filtered = [record for record in filtered if str(record.get("symbol", "")).upper() == normalized_symbol]
    return filtered


def _original_outcome_summary(outcomes: list[OutcomeRecord]) -> dict | None:
    if not outcomes:
        return None
    pnl_values = [outcome.pnl_pct for outcome in outcomes]
    return {
        "samples": len(outcomes),
        "filled": sum(1 for outcome in outcomes if outcome.fill_status == "filled"),
        "wins": sum(1 for outcome in outcomes if outcome.pnl_pct > 0.0),
        "losses": sum(1 for outcome in outcomes if outcome.pnl_pct < 0.0),
        "avg_pnl_pct": round(sum(pnl_values) / len(pnl_values), 4) if pnl_values else None,
        "latest_outcome": outcomes[-1].outcome,
    }


def _best_timeframe(records: list[dict]) -> str | None:
    resolved = [record for record in records if record.get("shadow_status") in RESOLVED_STATUSES]
    if len(resolved) < 5:
        return None
    grouped: dict[str, list[dict]] = {}
    for record in resolved:
        grouped.setdefault(str(record.get("timeframe", "unknown")), []).append(record)
    ranked = sorted(
        grouped.items(),
        key=lambda item: (
            sum(1 for record in item[1] if record.get("shadow_status") == SHADOW_WIN) / len(item[1]),
            len(item[1]),
        ),
        reverse=True,
    )
    return ranked[0][0] if ranked else None


def _shadow_outcome_id(signal_id: str, shadow_direction: str) -> str:
    return uuid5(NAMESPACE_URL, f"hammer-radar-betrayal-shadow:{signal_id}:{shadow_direction}").hex


def _dedupe_key(signal_id: object, shadow_direction: object) -> tuple[str, str]:
    return str(signal_id), str(shadow_direction)


def _positive_float_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    if value <= 0.0:
        return None
    return value


def _round_price(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _comparison_label(comparison: object) -> str:
    if not isinstance(comparison, dict):
        return "inconclusive"
    if comparison.get("shadow_better"):
        return "shadow_better"
    if comparison.get("original_better"):
        return "original_better"
    return "inconclusive"


def _format_optional(value: object) -> str:
    if value is None:
        return "n/a"
    return str(value)
