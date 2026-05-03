"""Strategy performance audit and live-eligibility recommendations.

This module is audit/reporting only. It reads local Hammer Radar paper logs and
never enables live execution, places orders, reads secrets, or creates signed
order payloads.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from src.app.hammer_radar.operator.archive import get_log_dir, load_outcomes, load_signals
from src.app.hammer_radar.operator.notification_watcher import ALERTS_FILENAME
from src.app.hammer_radar.operator.operator_actions import OPERATOR_ACTIONS_FILENAME
from src.app.hammer_radar.operator.live_approval import LIVE_APPROVAL_REQUESTS_FILENAME
from src.app.hammer_radar.operator.positions import load_closed_positions

LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False
EXECUTION_ENABLED = False
NO_ORDER_PAYLOAD_CREATED = True
SECRETS_SHOWN = False

DEFAULT_MIN_SAMPLE = 30
DEFAULT_MIN_WIN_RATE = 45.0
DEFAULT_ALLOWED_TINY_LIVE_TIMEFRAMES = ("13m", "44m")
DEFAULT_PAPER_ONLY_TIMEFRAMES = ("4m", "8m", "88m")
DEFAULT_CONTEXT_ONLY_TIMEFRAMES = ("4H", "13H", "13D", "888m")
DEFAULT_BLOCKED_TIMEFRAMES = ("22m", "55m", "222m", "444m")
PREFERRED_ENTRY_MODE = "ladder_close_50_618"
BTC_SYMBOL = "BTCUSDT"

ELIGIBLE_FOR_FUTURE_TINY_LIVE = "ELIGIBLE_FOR_FUTURE_TINY_LIVE"
PAPER_ONLY = "PAPER_ONLY"
CONTEXT_ONLY = "CONTEXT_ONLY"
BLOCKED_FROM_LIVE = "BLOCKED_FROM_LIVE"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class StrategyAuditConfig:
    min_sample: int
    min_win_rate: float
    allowed_tiny_live_timeframes: tuple[str, ...]
    paper_only_timeframes: tuple[str, ...]
    context_only_timeframes: tuple[str, ...]
    blocked_timeframes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_sample": self.min_sample,
            "min_win_rate": self.min_win_rate,
            "allowed_tiny_live_timeframes": list(self.allowed_tiny_live_timeframes),
            "paper_only_timeframes": list(self.paper_only_timeframes),
            "context_only_timeframes": list(self.context_only_timeframes),
            "blocked_timeframes": list(self.blocked_timeframes),
            "preferred_entry_mode": PREFERRED_ENTRY_MODE,
            "btc_symbol": BTC_SYMBOL,
        }


def load_strategy_audit_config(env: dict[str, str] | None = None) -> StrategyAuditConfig:
    source = os.environ if env is None else env
    return StrategyAuditConfig(
        min_sample=_env_int(source.get("HAMMER_STRATEGY_AUDIT_MIN_SAMPLE"), default=DEFAULT_MIN_SAMPLE, minimum=1),
        min_win_rate=_env_float(
            source.get("HAMMER_STRATEGY_AUDIT_MIN_WIN_RATE"),
            default=DEFAULT_MIN_WIN_RATE,
            minimum=0.0,
        ),
        allowed_tiny_live_timeframes=_env_list(
            source.get("HAMMER_STRATEGY_AUDIT_ALLOWED_TINY_LIVE_TIMEFRAMES"),
            default=DEFAULT_ALLOWED_TINY_LIVE_TIMEFRAMES,
        ),
        paper_only_timeframes=_env_list(
            source.get("HAMMER_STRATEGY_AUDIT_PAPER_ONLY_TIMEFRAMES"),
            default=DEFAULT_PAPER_ONLY_TIMEFRAMES,
        ),
        context_only_timeframes=_env_list(
            source.get("HAMMER_STRATEGY_AUDIT_CONTEXT_ONLY_TIMEFRAMES"),
            default=DEFAULT_CONTEXT_ONLY_TIMEFRAMES,
        ),
        blocked_timeframes=_env_list(
            source.get("HAMMER_STRATEGY_AUDIT_BLOCKED_TIMEFRAMES"),
            default=DEFAULT_BLOCKED_TIMEFRAMES,
        ),
    )


def build_strategy_performance_summary(
    *,
    log_dir: str | Path | None = None,
    config: StrategyAuditConfig | None = None,
) -> dict[str, Any]:
    audit = _build_audit(log_dir=log_dir, config=config)
    return {
        **_safety_fields(),
        "generated_at": audit["generated_at"],
        "archive_log_dir": audit["archive_log_dir"],
        "config": audit["config"],
        "source_counts": audit["source_counts"],
        "overall": audit["overall"],
        "groups": audit["groups"],
        "recent_windows": audit["recent_windows"],
        "notes": [
            "R40 is audit/reporting only.",
            "Live eligibility is recommendation only, not execution permission.",
            "Future tiny-live still requires exact LIVE APPROVE <signal_id> and all safety gates.",
        ],
    }


def build_strategy_timeframe_summary(
    *,
    log_dir: str | Path | None = None,
    config: StrategyAuditConfig | None = None,
) -> dict[str, Any]:
    audit = _build_audit(log_dir=log_dir, config=config)
    return {
        **_safety_fields(),
        "generated_at": audit["generated_at"],
        "archive_log_dir": audit["archive_log_dir"],
        "config": audit["config"],
        "timeframes": audit["groups"]["timeframe"],
    }


def build_strategy_entry_mode_summary(
    *,
    log_dir: str | Path | None = None,
    config: StrategyAuditConfig | None = None,
) -> dict[str, Any]:
    audit = _build_audit(log_dir=log_dir, config=config)
    return {
        **_safety_fields(),
        "generated_at": audit["generated_at"],
        "archive_log_dir": audit["archive_log_dir"],
        "config": audit["config"],
        "entry_modes": audit["groups"]["entry_mode"],
    }


def build_live_eligibility_matrix(
    *,
    log_dir: str | Path | None = None,
    config: StrategyAuditConfig | None = None,
) -> dict[str, Any]:
    audit = _build_audit(log_dir=log_dir, config=config)
    recommendations = [
        _recommendation(row, config=load_strategy_audit_config() if config is None else config)
        for row in audit["groups"]["timeframe_direction_entry_mode"]
    ]
    recommendations.sort(
        key=lambda row: (
            _recommendation_rank(row["recommendation"]),
            str(row["timeframe"]),
            str(row["direction"]),
            str(row["entry_mode"]),
        )
    )
    return {
        **_safety_fields(),
        "generated_at": audit["generated_at"],
        "archive_log_dir": audit["archive_log_dir"],
        "config": audit["config"],
        "recommendations": recommendations,
        "eligible_recommendations": [
            row for row in recommendations if row["recommendation"] == ELIGIBLE_FOR_FUTURE_TINY_LIVE
        ],
        "notes": [
            "Recommendation only. Not permission to execute.",
            "No live orders. No signed order payloads.",
            "BTCUSDT long-only remains the future tiny-live recommendation boundary.",
        ],
    }


def _build_audit(*, log_dir: str | Path | None, config: StrategyAuditConfig | None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    audit_config = config or load_strategy_audit_config()
    generated_at = datetime.now(UTC)
    signals = load_signals(resolved_log_dir)
    raw_outcomes = load_outcomes(resolved_log_dir)
    outcomes = [outcome for outcome in raw_outcomes if outcome.fill_status in {"filled", "partial"}]
    positions = load_closed_positions(resolved_log_dir)
    rows = [_outcome_row(outcome) for outcome in outcomes]

    groups = {
        "timeframe": _group_metrics(rows, ("timeframe",), config=audit_config),
        "direction": _group_metrics(rows, ("direction",), config=audit_config),
        "entry_mode": _group_metrics(rows, ("entry_mode",), config=audit_config),
        "timeframe_direction": _group_metrics(rows, ("timeframe", "direction"), config=audit_config),
        "timeframe_entry_mode": _group_metrics(rows, ("timeframe", "entry_mode"), config=audit_config),
        "timeframe_direction_entry_mode": _group_metrics(
            rows,
            ("timeframe", "direction", "entry_mode"),
            config=audit_config,
        ),
    }
    recent_windows = {
        "last_24h": _window_summary(rows, generated_at=generated_at, hours=24, config=audit_config),
        "last_7d": _window_summary(rows, generated_at=generated_at, hours=24 * 7, config=audit_config),
    }
    return {
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "config": audit_config.to_dict(),
        "source_counts": {
            "signals": len(signals),
            "outcomes": len(raw_outcomes),
            "audited_filled_outcomes": len(outcomes),
            "positions": _count_ndjson(resolved_log_dir / "positions.ndjson"),
            "closed_positions": len(positions),
            "readiness_alerts": _count_ndjson(resolved_log_dir / ALERTS_FILENAME),
            "operator_actions": _count_ndjson(resolved_log_dir / OPERATOR_ACTIONS_FILENAME),
            "live_approval_requests": _count_ndjson(resolved_log_dir / LIVE_APPROVAL_REQUESTS_FILENAME),
        },
        "overall": _metrics_for_rows(rows, group={}, config=audit_config),
        "groups": groups,
        "recent_windows": recent_windows,
    }


def _group_metrics(
    rows: list[dict[str, Any]],
    keys: tuple[str, ...],
    *,
    config: StrategyAuditConfig,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[tuple(row.get(key) for key in keys)].append(row)
    result = []
    for key_values, bucket_rows in buckets.items():
        group = dict(zip(keys, key_values, strict=True))
        result.append(_metrics_for_rows(bucket_rows, group=group, config=config))
    return sorted(
        result,
        key=lambda row: (
            -int(row["sample_count"]),
            str(row.get("timeframe", "")),
            str(row.get("direction", "")),
            str(row.get("entry_mode", "")),
        ),
    )


def _metrics_for_rows(
    rows: list[dict[str, Any]],
    *,
    group: dict[str, Any],
    config: StrategyAuditConfig,
) -> dict[str, Any]:
    pnl_values = [float(row["pnl_pct"]) for row in rows]
    sample_count = len(pnl_values)
    wins = sum(1 for value in pnl_values if value > 0.0)
    losses = sum(1 for value in pnl_values if value <= 0.0)
    total = sum(pnl_values)
    return {
        **group,
        "sample_count": sample_count,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round((wins / sample_count) * 100.0, 2) if sample_count else 0.0,
        "avg_pnl_pct": round(total / sample_count, 4) if sample_count else 0.0,
        "total_pnl_pct": round(total, 4),
        "best_pnl_pct": round(max(pnl_values), 4) if pnl_values else None,
        "worst_pnl_pct": round(min(pnl_values), 4) if pnl_values else None,
        "max_losing_streak": _max_losing_streak(rows),
        "confidence": _confidence(sample_count, config=config),
    }


def _window_summary(
    rows: list[dict[str, Any]],
    *,
    generated_at: datetime,
    hours: int,
    config: StrategyAuditConfig,
) -> dict[str, Any]:
    window_start = generated_at - timedelta(hours=hours)
    window_rows = [
        row
        for row in rows
        if row["event_time"] is not None and window_start <= row["event_time"] <= generated_at
    ]
    return {
        "window_hours": hours,
        "window_start": window_start.isoformat(),
        "overall": _metrics_for_rows(window_rows, group={}, config=config),
        "timeframes": _group_metrics(window_rows, ("timeframe",), config=config),
    }


def _recommendation(row: dict[str, Any], *, config: StrategyAuditConfig) -> dict[str, Any]:
    timeframe = str(row.get("timeframe") or "")
    direction = str(row.get("direction") or "")
    entry_mode = str(row.get("entry_mode") or "")
    blockers: list[str] = []
    recommendation = PAPER_ONLY

    if direction == "short":
        recommendation = PAPER_ONLY
        blockers.append("shorts remain paper/operator visibility only")
    elif direction != "long":
        recommendation = BLOCKED_FROM_LIVE
        blockers.append(f"unsupported direction: {direction}")
    elif timeframe in config.context_only_timeframes:
        recommendation = CONTEXT_ONLY
        blockers.append("timeframe is context-only until explicitly promoted")
    elif timeframe in config.paper_only_timeframes:
        recommendation = PAPER_ONLY
        blockers.append("timeframe remains paper-only by default because of noise/context risk")
    elif timeframe in config.blocked_timeframes:
        recommendation = BLOCKED_FROM_LIVE
        blockers.append("timeframe is blocked from live by R40 audit defaults")
    elif int(row["sample_count"]) < config.min_sample:
        recommendation = INSUFFICIENT_DATA
        blockers.append(f"sample_count below minimum {config.min_sample}")
    elif timeframe not in config.allowed_tiny_live_timeframes:
        recommendation = PAPER_ONLY
        blockers.append("timeframe is not in allowed future tiny-live recommendation list")
    elif entry_mode != PREFERRED_ENTRY_MODE:
        recommendation = PAPER_ONLY
        blockers.append(f"entry_mode is not preferred {PREFERRED_ENTRY_MODE}")
    elif float(row["avg_pnl_pct"]) <= 0.0:
        recommendation = BLOCKED_FROM_LIVE
        blockers.append("avg_pnl_pct must be positive")
    elif float(row["total_pnl_pct"]) <= 0.0:
        recommendation = BLOCKED_FROM_LIVE
        blockers.append("total_pnl_pct must be positive")
    elif float(row["win_rate_pct"]) < config.min_win_rate:
        recommendation = BLOCKED_FROM_LIVE
        blockers.append(f"win_rate_pct below minimum {config.min_win_rate}")
    else:
        recommendation = ELIGIBLE_FOR_FUTURE_TINY_LIVE

    return {
        **row,
        "recommendation": recommendation,
        "preferred_entry_mode": PREFERRED_ENTRY_MODE,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "execution_enabled": EXECUTION_ENABLED,
        "no_order_payload_created": NO_ORDER_PAYLOAD_CREATED,
        "blockers": blockers,
        "operator_note": _operator_note(recommendation),
    }


def _outcome_row(outcome: Any) -> dict[str, Any]:
    return {
        "signal_id": outcome.signal_id,
        "symbol": outcome.symbol,
        "timeframe": outcome.timeframe,
        "direction": outcome.direction,
        "entry_mode": outcome.entry_mode,
        "pnl_pct": float(outcome.pnl_pct),
        "timestamp": outcome.timestamp,
        "evaluated_at": outcome.evaluated_at,
        "event_time": _parse_datetime(outcome.evaluated_at) or _parse_datetime(outcome.timestamp),
    }


def _max_losing_streak(rows: Iterable[dict[str, Any]]) -> int:
    ordered = sorted(rows, key=lambda row: row.get("event_time") or datetime.min.replace(tzinfo=UTC))
    max_streak = 0
    current = 0
    for row in ordered:
        if float(row["pnl_pct"]) <= 0.0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak


def _confidence(sample_count: int, *, config: StrategyAuditConfig) -> str:
    if sample_count < config.min_sample:
        return "LOW_SAMPLE"
    if sample_count < config.min_sample * 3:
        return "DEVELOPING"
    return "USABLE_SAMPLE"


def _operator_note(recommendation: str) -> str:
    if recommendation == ELIGIBLE_FOR_FUTURE_TINY_LIVE:
        return "Future tiny-live candidate class only; still requires exact LIVE APPROVE <signal_id> and all safety gates."
    if recommendation == CONTEXT_ONLY:
        return "Use as market context only until explicitly promoted."
    if recommendation == INSUFFICIENT_DATA:
        return "Collect more paper samples before considering live promotion."
    if recommendation == BLOCKED_FROM_LIVE:
        return "Do not promote to live under R40 audit rules."
    return "Continue paper/watch-only tracking."


def _recommendation_rank(value: str) -> int:
    order = {
        ELIGIBLE_FOR_FUTURE_TINY_LIVE: 0,
        PAPER_ONLY: 1,
        CONTEXT_ONLY: 2,
        INSUFFICIENT_DATA: 3,
        BLOCKED_FROM_LIVE: 4,
    }
    return order.get(value, 99)


def _safety_fields() -> dict[str, Any]:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "execution_enabled": EXECUTION_ENABLED,
        "no_order_payload_created": NO_ORDER_PAYLOAD_CREATED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _count_ndjson(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _env_int(value: str | None, *, default: int, minimum: int) -> int:
    try:
        parsed = int(value) if value not in (None, "") else default
    except ValueError:
        return default
    return max(parsed, minimum)


def _env_float(value: str | None, *, default: float, minimum: float) -> float:
    try:
        parsed = float(value) if value not in (None, "") else default
    except ValueError:
        return default
    return max(parsed, minimum)


def _env_list(value: str | None, *, default: tuple[str, ...]) -> tuple[str, ...]:
    if value in (None, ""):
        return default
    parsed = tuple(item.strip() for item in value.split(",") if item.strip())
    return parsed or default
