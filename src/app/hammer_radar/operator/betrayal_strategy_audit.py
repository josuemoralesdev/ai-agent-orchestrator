"""R80 betrayal strategy audit for Hammer Radar.

This module ranks naive inverse strategy families from existing paper
performance rows. It is audit/reporting only: no orders, no network, no live
execution arming, and no signed payloads.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.strategy_performance import (
    build_live_eligibility_matrix,
)

PHASE = "R80"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "BETRAYAL_STRATEGY_AUDIT_ONLY_NO_ORDER"

BETRAYAL_PRIMARY_CANDIDATE = "BETRAYAL_PRIMARY_CANDIDATE"
BETRAYAL_WATCHLIST = "BETRAYAL_WATCHLIST"
BETRAYAL_REJECTED = "BETRAYAL_REJECTED"
NOT_BETRAYAL = "NOT_BETRAYAL"
NEEDS_TRUE_INVERSE_VALIDATION = "BETRAYAL_NEEDS_TRUE_INVERSE_VALIDATION"

DEFAULT_MIN_SAMPLE = 30
PRIMARY_MAX_ORIGINAL_WIN_RATE = 25.0
PRIMARY_MIN_BETRAYAL_WIN_RATE = 75.0
WATCHLIST_MAX_ORIGINAL_WIN_RATE = 40.0
WATCHLIST_MIN_BETRAYAL_WIN_RATE = 60.0

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "Naive inverse metrics are audit evidence only. True inverse paper outcomes must be tracked before live eligibility."


def build_betrayal_strategy_audit(
    *,
    log_dir: str | Path | None = None,
    min_sample: int = DEFAULT_MIN_SAMPLE,
) -> dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat()
    source = build_live_eligibility_matrix(log_dir=log_dir)
    rows = source.get("recommendations") if isinstance(source.get("recommendations"), list) else []
    audited_rows = [
        build_betrayal_strategy_row(row, min_sample=min_sample)
        for row in rows
        if _has_group_identity(row)
    ]
    audited_rows.sort(key=_sort_key)
    primary = [row for row in audited_rows if row["recommendation"] == BETRAYAL_PRIMARY_CANDIDATE]
    watchlist = [row for row in audited_rows if row["recommendation"] == BETRAYAL_WATCHLIST]
    rejected = [row for row in audited_rows if row["recommendation"] not in {BETRAYAL_PRIMARY_CANDIDATE, BETRAYAL_WATCHLIST}]
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at,
            "archive_log_dir": source.get("archive_log_dir"),
            "config": {
                "min_sample": int(min_sample),
                "primary": {
                    "sample_count_gte": int(min_sample),
                    "original_win_rate_lte": PRIMARY_MAX_ORIGINAL_WIN_RATE,
                    "original_avg_pnl_lt": 0.0,
                    "original_total_pnl_lt": 0.0,
                    "betrayal_win_rate_gte": PRIMARY_MIN_BETRAYAL_WIN_RATE,
                    "betrayal_total_pnl_gt": 0.0,
                },
                "watchlist": {
                    "sample_count_gte": int(min_sample),
                    "original_win_rate_lt": WATCHLIST_MAX_ORIGINAL_WIN_RATE,
                    "original_avg_pnl_lt": 0.0,
                    "original_total_pnl_lt": 0.0,
                    "betrayal_win_rate_gte": WATCHLIST_MIN_BETRAYAL_WIN_RATE,
                    "betrayal_total_pnl_gt": 0.0,
                },
                "formulas": {
                    "betrayal_win_rate_pct": "100 - original_win_rate_pct",
                    "betrayal_avg_pnl_pct": "-original_avg_pnl_pct",
                    "betrayal_total_pnl_pct": "-original_total_pnl_pct",
                },
            },
            "leaderboard": audited_rows,
            "primary_candidates": primary,
            "watchlist_candidates": watchlist,
            "rejected_candidates": rejected,
            "notes": [
                "R80 is paper/shadow/audit only.",
                NO_ORDER_NOTE,
                "This reinforces the normal strategy promotion system and does not replace 13m/44m long promotion review.",
                "Do not treat BETRAYAL_PRIMARY_CANDIDATE or BETRAYAL_WATCHLIST as live-ready.",
            ],
            **_safety_fields(),
        }
    )


def build_betrayal_strategy_row(row: Mapping[str, Any], *, min_sample: int = DEFAULT_MIN_SAMPLE) -> dict[str, Any]:
    sample_count = _int(row.get("sample_count"))
    original_win_rate = _float(row.get("win_rate_pct"))
    original_avg_pnl = _float(row.get("avg_pnl_pct"))
    original_total_pnl = _float(row.get("total_pnl_pct"))
    betrayal_win_rate = round(100.0 - original_win_rate, 2)
    betrayal_avg_pnl = round(-original_avg_pnl, 4)
    betrayal_total_pnl = round(-original_total_pnl, 4)
    original_direction = str(row.get("direction") or "")
    betrayal_direction = invert_direction(original_direction)
    blockers = _blockers(
        sample_count=sample_count,
        min_sample=min_sample,
        original_win_rate=original_win_rate,
        original_avg_pnl=original_avg_pnl,
        original_total_pnl=original_total_pnl,
        betrayal_win_rate=betrayal_win_rate,
        betrayal_total_pnl=betrayal_total_pnl,
    )
    recommendation = _recommendation(
        sample_count=sample_count,
        min_sample=min_sample,
        original_win_rate=original_win_rate,
        original_avg_pnl=original_avg_pnl,
        original_total_pnl=original_total_pnl,
        betrayal_win_rate=betrayal_win_rate,
        betrayal_total_pnl=betrayal_total_pnl,
    )
    return _sanitize(
        {
            "timeframe": row.get("timeframe"),
            "original_direction": original_direction or None,
            "betrayal_direction": betrayal_direction,
            "entry_mode": row.get("entry_mode"),
            "sample_count": sample_count,
            "original": {
                "wins": _int(row.get("wins")),
                "losses": _int(row.get("losses")),
                "win_rate_pct": original_win_rate,
                "avg_pnl_pct": original_avg_pnl,
                "total_pnl_pct": original_total_pnl,
                "best_pnl_pct": row.get("best_pnl_pct"),
                "worst_pnl_pct": row.get("worst_pnl_pct"),
                "max_losing_streak": row.get("max_losing_streak"),
                "source_recommendation": row.get("recommendation"),
            },
            "betrayal": {
                "wins": _int(row.get("losses")),
                "losses": _int(row.get("wins")),
                "win_rate_pct": betrayal_win_rate,
                "avg_pnl_pct": betrayal_avg_pnl,
                "total_pnl_pct": betrayal_total_pnl,
            },
            "confidence": _confidence(sample_count=sample_count, min_sample=min_sample, recommendation=recommendation),
            "recommendation": recommendation,
            "next_required_status": NEEDS_TRUE_INVERSE_VALIDATION
            if recommendation in {BETRAYAL_PRIMARY_CANDIDATE, BETRAYAL_WATCHLIST}
            else NOT_BETRAYAL,
            "blockers": blockers,
            "operator_note": _operator_note(recommendation),
            **_safety_fields(),
        }
    )


def invert_direction(direction: object) -> str | None:
    normalized = str(direction or "").strip().lower()
    if normalized == "long":
        return "short"
    if normalized == "short":
        return "long"
    return None


def format_betrayal_strategy_audit_text(payload: Mapping[str, Any]) -> str:
    primary = payload.get("primary_candidates") if isinstance(payload.get("primary_candidates"), list) else []
    watchlist = payload.get("watchlist_candidates") if isinstance(payload.get("watchlist_candidates"), list) else []
    rejected = payload.get("rejected_candidates") if isinstance(payload.get("rejected_candidates"), list) else []
    lines = [
        f"R80 betrayal strategy audit: {payload.get('status')}",
        "BETRAYAL_STRATEGY_AUDIT_ONLY_NO_ORDER",
        "No order placed. real_order_placed=false execution_attempted=false network_allowed=false secrets_shown=false.",
        f"primary_candidates: {len(primary)}",
    ]
    lines.extend(_format_rows(primary[:5]))
    lines.append(f"watchlist_candidates: {len(watchlist)}")
    lines.extend(_format_rows(watchlist[:5]))
    lines.append(f"rejected_candidates: {len(rejected)}")
    lines.append(NO_ORDER_NOTE)
    return "\n".join(lines)


def _format_rows(rows: list[Mapping[str, Any]]) -> list[str]:
    if not rows:
        return ["  none"]
    formatted = []
    for row in rows:
        betrayal = row.get("betrayal") if isinstance(row.get("betrayal"), dict) else {}
        original = row.get("original") if isinstance(row.get("original"), dict) else {}
        formatted.append(
            "  "
            f"{row.get('recommendation')} "
            f"{row.get('timeframe')} {row.get('original_direction')}->{row.get('betrayal_direction')} "
            f"{row.get('entry_mode')} samples={row.get('sample_count')} "
            f"orig_win={original.get('win_rate_pct')} betrayal_win={betrayal.get('win_rate_pct')} "
            f"betrayal_total={betrayal.get('total_pnl_pct')}"
        )
    return formatted


def _recommendation(
    *,
    sample_count: int,
    min_sample: int,
    original_win_rate: float,
    original_avg_pnl: float,
    original_total_pnl: float,
    betrayal_win_rate: float,
    betrayal_total_pnl: float,
) -> str:
    if (
        sample_count >= min_sample
        and original_win_rate <= PRIMARY_MAX_ORIGINAL_WIN_RATE
        and original_avg_pnl < 0.0
        and original_total_pnl < 0.0
        and betrayal_win_rate >= PRIMARY_MIN_BETRAYAL_WIN_RATE
        and betrayal_total_pnl > 0.0
    ):
        return BETRAYAL_PRIMARY_CANDIDATE
    if (
        sample_count >= min_sample
        and original_win_rate < WATCHLIST_MAX_ORIGINAL_WIN_RATE
        and original_avg_pnl < 0.0
        and original_total_pnl < 0.0
        and betrayal_win_rate >= WATCHLIST_MIN_BETRAYAL_WIN_RATE
        and betrayal_total_pnl > 0.0
    ):
        return BETRAYAL_WATCHLIST
    if sample_count < min_sample or original_avg_pnl > 0.0 or original_total_pnl > 0.0 or betrayal_total_pnl <= 0.0:
        return BETRAYAL_REJECTED
    return NOT_BETRAYAL


def _blockers(
    *,
    sample_count: int,
    min_sample: int,
    original_win_rate: float,
    original_avg_pnl: float,
    original_total_pnl: float,
    betrayal_win_rate: float,
    betrayal_total_pnl: float,
) -> list[str]:
    blockers: list[str] = []
    if sample_count < min_sample:
        blockers.append(f"sample_count below minimum {min_sample}")
    if original_total_pnl >= 0.0:
        blockers.append("original total pnl is not negative")
    if original_avg_pnl >= 0.0:
        blockers.append("original avg pnl is not negative")
    if original_win_rate >= WATCHLIST_MAX_ORIGINAL_WIN_RATE:
        blockers.append("original win rate is not weak enough for betrayal watchlist")
    if betrayal_win_rate < WATCHLIST_MIN_BETRAYAL_WIN_RATE:
        blockers.append("naive betrayal win rate is below watchlist threshold")
    if betrayal_total_pnl <= 0.0:
        blockers.append("naive betrayal total pnl is not positive")
    return blockers


def _confidence(*, sample_count: int, min_sample: int, recommendation: str) -> str:
    if sample_count < min_sample:
        return "LOW_SAMPLE"
    if recommendation == BETRAYAL_PRIMARY_CANDIDATE:
        return "PRIMARY_AUDIT_EVIDENCE"
    if recommendation == BETRAYAL_WATCHLIST:
        return "WATCHLIST_AUDIT_EVIDENCE"
    return "NOT_BETRAYAL"


def _operator_note(recommendation: str) -> str:
    if recommendation == BETRAYAL_PRIMARY_CANDIDATE:
        return "Primary betrayal audit candidate; track true inverse paper outcomes before any live eligibility discussion."
    if recommendation == BETRAYAL_WATCHLIST:
        return "Betrayal watchlist candidate; collect true inverse paper outcomes before promotion."
    return "Rejected for betrayal audit; keep normal strategy evaluation unchanged."


def _has_group_identity(row: Mapping[str, Any]) -> bool:
    return bool(row.get("timeframe") and row.get("direction") and row.get("entry_mode"))


def _sort_key(row: Mapping[str, Any]) -> tuple[int, float, int, str, str, str]:
    rank = {
        BETRAYAL_PRIMARY_CANDIDATE: 0,
        BETRAYAL_WATCHLIST: 1,
        BETRAYAL_REJECTED: 2,
        NOT_BETRAYAL: 3,
    }.get(str(row.get("recommendation")), 9)
    betrayal = row.get("betrayal") if isinstance(row.get("betrayal"), dict) else {}
    return (
        rank,
        -float(betrayal.get("total_pnl_pct") or 0.0),
        -int(row.get("sample_count") or 0),
        str(row.get("timeframe") or ""),
        str(row.get("original_direction") or ""),
        str(row.get("entry_mode") or ""),
    )


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
