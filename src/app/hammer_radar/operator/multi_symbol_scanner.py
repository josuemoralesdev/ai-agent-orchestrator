"""Multi-symbol paper/watch scanner for Hammer Radar.

R31 archives paper/watch observations only. It does not place orders, create
live tickets, or change BTCUSDT-only live readiness.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.alt_watchlist import (
    BTC_RELATIVE_STRENGTH,
    build_watchlist,
    build_watchlist_summary,
)
from src.app.hammer_radar.operator.archive import get_log_dir, load_signals
from src.app.hammer_radar.operator.models import SignalRecord

LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False
SCANS_FILENAME = "multi_symbol_paper_scans.ndjson"
SOURCE = "multi_symbol_paper_scanner"
ROTATION_CONTEXT = "ETHBTC tracks ETH strength vs BTC / alt-cycle rotation."


@dataclass(frozen=True)
class ScannerConfig:
    category: str | None = None
    symbol: str | None = None
    limit: int = 50


def scan_symbol(watch_record: dict[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    created_at = datetime.now(UTC).isoformat()
    signals = [signal for signal in load_signals(resolved_log_dir) if signal.symbol == watch_record["symbol"]]
    latest = max(signals, key=lambda signal: signal.timestamp, default=None)
    recent_signal_count = len(signals)
    recent_tradable_count = sum(1 for signal in signals if signal.tradable)
    score = _paper_score(watch_record, recent_signal_count=recent_signal_count, recent_tradable_count=recent_tradable_count)
    paper_signal_status = _paper_signal_status(
        watch_record,
        latest=latest,
        recent_signal_count=recent_signal_count,
        recent_tradable_count=recent_tradable_count,
    )
    scan_status = _scan_status(watch_record, recent_signal_count=recent_signal_count)
    direction = latest.direction if latest is not None else ("neutral" if watch_record["symbol"] == "ETHBTC" else "unknown")
    return {
        "scan_id": _scan_id(symbol=watch_record["symbol"], created_at=created_at),
        "created_at": created_at,
        "source": SOURCE,
        "symbol": watch_record["symbol"],
        "category": watch_record["category"],
        "pair_type": watch_record["pair_type"],
        "current_phase_permission": watch_record["current_phase_permission"],
        "live_eligible_symbol": bool(watch_record["live_eligible_symbol"]),
        "paper_watch_enabled": bool(watch_record["paper_watch_enabled"]),
        "watch_only": bool(watch_record["watch_only"]),
        "scan_status": scan_status,
        "paper_signal_status": paper_signal_status,
        "direction": direction,
        "timeframe": latest.timeframe if latest is not None else None,
        "score": score,
        "tier": _tier(score),
        "reason": _reason(watch_record, paper_signal_status=paper_signal_status),
        "recent_signal_count": recent_signal_count,
        "recent_tradable_count": recent_tradable_count,
        "latest_signal_timestamp": latest.timestamp if latest is not None else None,
        "latest_direction": latest.direction if latest is not None else None,
        "latest_score": watch_record.get("latest_score"),
        "rotation_context": ROTATION_CONTEXT if watch_record["symbol"] == "ETHBTC" else None,
        "rank_reason": _rank_reason(watch_record, recent_signal_count=recent_signal_count, recent_tradable_count=recent_tradable_count),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
    }


def scan_watchlist(
    *,
    symbol: str | None = None,
    category: str | None = None,
    limit: int = 50,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    watchlist = build_watchlist(category=category, limit=0, log_dir=resolved_log_dir)["symbols"]
    if symbol is not None:
        watchlist = [record for record in watchlist if record["symbol"] == symbol]
    records = [scan_symbol(record, log_dir=resolved_log_dir) for record in watchlist]
    records.sort(key=lambda record: (-int(record["score"]), record["symbol"]))
    if limit > 0:
        records = records[:limit]
    for rank, record in enumerate(records, start=1):
        record["rank"] = rank
    if write:
        append_scan_records(records, log_dir=resolved_log_dir)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "btc_live_only": True,
        "write": bool(write),
        "scanned_symbols": len(records),
        "records": records,
        "summary": _records_summary(records),
    }


def append_scan_records(records: list[dict[str, Any]], *, log_dir: str | Path | None = None) -> None:
    path = _scans_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_scan_records(
    *,
    limit: int = 50,
    symbol: str | None = None,
    category: str | None = None,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = _scans_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if symbol is not None and record.get("symbol") != symbol:
                continue
            if category is not None and record.get("category") != category:
                continue
            if status is not None and record.get("paper_signal_status") != status and record.get("scan_status") != status:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def build_multi_symbol_scans_payload(
    *,
    limit: int = 50,
    symbol: str | None = None,
    category: str | None = None,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_scan_records(limit=limit, symbol=symbol, category=category, status=status, log_dir=log_dir)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "btc_live_only": True,
        "archived_records": len(load_scan_records(limit=0, log_dir=log_dir)),
        "records": records,
        "summary": _records_summary(records),
    }


def build_multi_symbol_summary(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    watch_summary = build_watchlist_summary(log_dir=log_dir)
    preview = scan_watchlist(limit=0, write=False, log_dir=log_dir)
    archived = load_scan_records(limit=0, log_dir=log_dir)
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "total_watchlist_symbols": watch_summary["total_symbols"],
        "scanned_symbols": preview["scanned_symbols"],
        "archived_records": len(archived),
        "live_eligible_symbols": watch_summary["live_eligible_symbols"],
        "paper_watch_symbols": watch_summary["paper_watch_symbols"],
        "relative_strength_symbols": watch_summary["relative_strength_symbols"],
        "key_rotation_pair": "ETHBTC",
        "next_promotion_candidate": "ETHUSDT",
        "btc_live_only": True,
        "top_ranked_symbols": preview["records"][:5],
        "warning": "multi-symbol scanner is paper/watch-only",
    }


def build_multi_symbol_scan_text(
    *,
    symbol: str | None = None,
    category: str | None = None,
    limit: int = 50,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> str:
    payload = scan_watchlist(symbol=symbol, category=category, limit=limit, write=write, log_dir=log_dir)
    lines = [
        "HAMMER RADAR MULTI-SYMBOL PAPER SCAN",
        "live_execution_enabled: false",
        "order_placed: false",
        f"btc_live_only: {str(payload['btc_live_only']).lower()}",
        f"write: {str(payload['write']).lower()}",
        f"scanned_symbols: {payload['scanned_symbols']}",
    ]
    for record in payload["records"]:
        lines.append(
            f"{record['rank']}. {record['symbol']} | status={record['paper_signal_status']} | "
            f"scan_status={record['scan_status']} | score={record['score']} | tier={record['tier']} | "
            f"direction={record['direction']} | live_eligible_symbol={str(record['live_eligible_symbol']).lower()}"
        )
    return "\n".join(lines)


def build_multi_symbol_scans_text(
    *,
    limit: int = 50,
    symbol: str | None = None,
    category: str | None = None,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> str:
    payload = build_multi_symbol_scans_payload(
        limit=limit,
        symbol=symbol,
        category=category,
        status=status,
        log_dir=log_dir,
    )
    lines = [
        "HAMMER RADAR MULTI-SYMBOL PAPER SCANS",
        "live_execution_enabled: false",
        "order_placed: false",
        f"archived_records: {payload['archived_records']}",
    ]
    if not payload["records"]:
        return "\n".join([*lines, "no multi-symbol scan records"])
    for record in payload["records"]:
        lines.append(
            f"{record.get('created_at')} | {record.get('scan_id')} | {record.get('symbol')} | "
            f"{record.get('paper_signal_status')} | score={record.get('score')} | "
            f"live_eligible_symbol={str(record.get('live_eligible_symbol')).lower()}"
        )
    return "\n".join(lines)


def build_multi_symbol_summary_text(*, log_dir: str | Path | None = None) -> str:
    summary = build_multi_symbol_summary(log_dir=log_dir)
    top = ", ".join(record["symbol"] for record in summary["top_ranked_symbols"])
    return "\n".join(
        [
            "HAMMER RADAR MULTI-SYMBOL PAPER SUMMARY",
            "live_execution_enabled: false",
            "order_placed: false",
            f"total_watchlist_symbols: {summary['total_watchlist_symbols']}",
            f"scanned_symbols: {summary['scanned_symbols']}",
            f"archived_records: {summary['archived_records']}",
            f"live_eligible_symbols: {', '.join(summary['live_eligible_symbols'])}",
            f"relative_strength_symbols: {', '.join(summary['relative_strength_symbols'])}",
            f"key_rotation_pair: {summary['key_rotation_pair']}",
            f"next_promotion_candidate: {summary['next_promotion_candidate']}",
            f"btc_live_only: {str(summary['btc_live_only']).lower()}",
            f"top_ranked_symbols: {top}",
            f"warning: {summary['warning']}",
        ]
    )


def _paper_score(watch_record: dict[str, Any], *, recent_signal_count: int, recent_tradable_count: int) -> int:
    score = int(watch_record.get("watch_score") or 0)
    if recent_signal_count > 0:
        score += 10
    if recent_tradable_count > 0:
        score += 5
    if watch_record["symbol"] == "ETHBTC":
        score += 5
    return max(0, min(100, score))


def _paper_signal_status(
    watch_record: dict[str, Any],
    *,
    latest: SignalRecord | None,
    recent_signal_count: int,
    recent_tradable_count: int,
) -> str:
    if latest is not None and recent_tradable_count > 0:
        return "PAPER_CANDIDATE"
    if latest is not None or watch_record["symbol"] == "ETHBTC":
        return "WATCH_ONLY_CONTEXT"
    if recent_signal_count == 0:
        return "INSUFFICIENT_DATA"
    return "NO_SIGNAL"


def _scan_status(watch_record: dict[str, Any], *, recent_signal_count: int) -> str:
    if watch_record["current_phase_permission"] == "WATCH_ONLY_UNKNOWN_RULES":
        return "UNKNOWN_RULES"
    if recent_signal_count > 0:
        return "SCANNED"
    if watch_record["watch_only"]:
        return "WATCH_ONLY"
    return "SCANNED"


def _reason(watch_record: dict[str, Any], *, paper_signal_status: str) -> str:
    if watch_record["symbol"] == "ETHBTC":
        return ROTATION_CONTEXT
    if paper_signal_status == "PAPER_CANDIDATE":
        return "Archived signal exists; paper/watch candidate only. No live ticket is created."
    if paper_signal_status == "WATCH_ONLY_CONTEXT":
        return "Archived context exists; scanner remains paper/watch-only."
    return "No archived signal data for this symbol yet; scanner remains paper/watch-only."


def _rank_reason(watch_record: dict[str, Any], *, recent_signal_count: int, recent_tradable_count: int) -> str:
    reasons = [f"base_watch_score={watch_record.get('watch_score')}"]
    if recent_signal_count > 0:
        reasons.append("recent_signal_count_bonus=10")
    if recent_tradable_count > 0:
        reasons.append("recent_tradable_count_bonus=5")
    if watch_record["symbol"] == "ETHBTC":
        reasons.append("ethbtc_rotation_bonus=5")
    return "; ".join(reasons)


def _tier(score: int) -> str:
    if score >= 90:
        return "HIGH_PRIORITY_WATCH"
    if score >= 70:
        return "LIQUID_WATCH"
    return "BETA_WATCH"


def _records_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_records": len(records),
        "paper_candidates": sum(1 for record in records if record.get("paper_signal_status") == "PAPER_CANDIDATE"),
        "watch_only_context": sum(1 for record in records if record.get("paper_signal_status") == "WATCH_ONLY_CONTEXT"),
        "insufficient_data": sum(1 for record in records if record.get("paper_signal_status") == "INSUFFICIENT_DATA"),
        "live_eligible_symbols": [record["symbol"] for record in records if record.get("live_eligible_symbol") is True],
    }


def _scan_id(*, symbol: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{SOURCE}|{symbol}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"mss_{digest}"


def _scans_path(log_dir: Path) -> Path:
    return log_dir / SCANS_FILENAME
