"""Local CLI inspection views for Hammer Radar NDJSON state."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.app.hammer_radar.operator.archive import get_log_dir, load_outcomes, load_signals
from src.app.hammer_radar.operator.models import OutcomeRecord, PaperPosition, SignalRecord
from src.app.hammer_radar.operator.positions import (
    load_closed_positions,
    load_open_positions,
    load_position_events,
    load_positions,
)

DAILY_EXECUTION_TIMEFRAMES = {"4m", "8m", "13m", "22m"}
HIGH_TIMEFRAMES = {"444m", "888m"}
LIVE_DECISION_ELIGIBLE = "ELIGIBLE_TINY_LIVE"
LIVE_DECISION_PAPER_ONLY = "PAPER_ONLY"
LIVE_DECISION_FORBIDDEN = "FORBIDDEN"
BETRAYAL_STRONG = "STRONG_BETRAYAL_WATCH"
BETRAYAL_WATCH = "BETRAYAL_WATCH"
BETRAYAL_WEAK = "WEAK_BETRAYAL_CONTEXT"
BETRAYAL_IGNORE = "IGNORE"


def build_summary_text(log_dir: str | Path | None = None) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    signals = load_signals(resolved_log_dir)
    outcomes = load_outcomes(resolved_log_dir)
    positions = load_positions(resolved_log_dir)
    open_positions = [position for position in positions if position.status == "open"]
    closed_positions = [position for position in positions if position.status == "closed"]
    events = load_position_events(resolved_log_dir)
    closed_pnl_usd = round(sum(position.pnl_usd or 0.0 for position in closed_positions), 4)
    closed_pnl_pct = round(sum(position.pnl_pct or 0.0 for position in closed_positions), 4)
    last_signal_timestamp = signals[-1].timestamp if signals else "n/a"
    last_position_event_timestamp = events[-1].timestamp if events else "n/a"

    lines = [
        "HAMMER RADAR SUMMARY",
        f"archive_log_dir: {resolved_log_dir}",
        f"total_signals: {len(signals)}",
        f"tradable_signals: {sum(1 for signal in signals if signal.tradable)}",
        f"total_outcomes: {len(outcomes)}",
        f"total_paper_positions: {len(positions)}",
        f"open_paper_positions: {len(open_positions)}",
        f"closed_paper_positions: {len(closed_positions)}",
        f"total_closed_pnl_usd: {closed_pnl_usd:.4f}",
        f"total_closed_pnl_pct: {closed_pnl_pct:.4f}%",
        f"last_signal_timestamp: {last_signal_timestamp}",
        f"last_position_event_timestamp: {last_position_event_timestamp}",
    ]
    return "\n".join(lines)


def build_signals_text(limit: int, log_dir: str | Path | None = None) -> str:
    signals = load_signals(get_log_dir(log_dir, use_env=True))
    rows = [
        (
            signal.timestamp,
            f"{signal.signal_id} | {signal.symbol} | {signal.timeframe} | {signal.direction.upper()} | "
            f"tradable={'Y' if signal.tradable else 'N'} | entry={signal.fib_618:.2f} | stop={signal.invalidation:.2f}"
            f"{_format_r9_metadata(signal)}"
        )
        for signal in signals
    ]
    return _format_rows("HAMMER RADAR SIGNALS", rows, limit=limit)


def build_outcomes_text(limit: int, log_dir: str | Path | None = None) -> str:
    outcomes = load_outcomes(get_log_dir(log_dir, use_env=True))
    rows = [
        (
            outcome.evaluated_at,
            f"{outcome.signal_id} | {outcome.timeframe} | {outcome.direction.upper()} | entry={outcome.entry_mode} | "
            f"fill={outcome.fill_status} | outcome={outcome.outcome} | pnl={outcome.pnl_pct:.4f}%"
        )
        for outcome in outcomes
    ]
    return _format_rows("HAMMER RADAR OUTCOMES", rows, limit=limit)


def build_positions_text(status: str, log_dir: str | Path | None = None) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    if status == "open":
        positions = load_open_positions(resolved_log_dir)
    elif status == "closed":
        positions = load_closed_positions(resolved_log_dir)
    else:
        positions = load_positions(resolved_log_dir)

    rows: list[tuple[str, str]] = []
    for position in positions:
        line = (
            f"{position.position_id} | {position.symbol} | {position.timeframe} | {position.direction.upper()} | "
            f"{position.entry_mode} | entry={position.entry_price:.2f} | stop={position.stop_price:.2f} | "
            f"size={position.size_usd:.2f} | status={position.status}"
        )
        if position.take_profit_price is not None:
            line += f" | tp={position.take_profit_price:.2f}"
        if position.status == "closed":
            pnl_usd = 0.0 if position.pnl_usd is None else position.pnl_usd
            close_reason = position.close_reason or "n/a"
            line += f" | pnl_usd={pnl_usd:.2f} | close_reason={close_reason}"
        rows.append((position.closed_at or position.opened_at, line))

    return _format_rows(f"HAMMER RADAR POSITIONS [{status}]", rows, limit=None)


def build_events_text(limit: int, log_dir: str | Path | None = None) -> str:
    events = load_position_events(get_log_dir(log_dir, use_env=True))
    rows = [
        (
            event.timestamp,
            f"{event.timestamp} | {event.event_type} | position={event.position_id} | signal={event.signal_id} | payload={event.payload}"
        )
        for event in events
    ]
    return _format_rows("HAMMER RADAR EVENTS", rows, limit=limit)


def build_r9_coverage_text(log_dir: str | Path | None = None) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    signals = load_signals(resolved_log_dir)
    total = len(signals)
    with_rsi = sum(1 for signal in signals if signal.rsi_value is not None or signal.rsi_state is not None)
    with_divergence = sum(
        1
        for signal in signals
        if signal.divergence_type is not None or signal.divergence_confirmed
    )
    with_triggers = sum(
        1
        for signal in signals
        if signal.extreme_trigger
        or signal.critical_trigger
        or signal.micro_scalp_candidate
        or signal.requires_human_approval
    )
    with_any_r9 = sum(1 for signal in signals if _has_any_r9_metadata(signal))
    missing_r9 = total - with_any_r9
    coverage_pct = (with_any_r9 / total) * 100.0 if total else 0.0
    last_signal_timestamp = signals[-1].timestamp if signals else "n/a"

    lines = [
        "HAMMER RADAR R9 COVERAGE",
        f"archive_log_dir: {resolved_log_dir}",
        f"total_signals: {total}",
        f"signals_with_rsi: {with_rsi}",
        f"signals_with_divergence: {with_divergence}",
        f"signals_with_trigger_fields: {with_triggers}",
        f"signals_missing_r9_metadata: {missing_r9}",
        f"r9_metadata_coverage_pct: {coverage_pct:.2f}%",
        f"last_signal_timestamp: {last_signal_timestamp}",
    ]
    return "\n".join(lines)


def build_daily_report_text(
    *,
    limit: int = 10,
    since_hours: int = 24,
    tradable_only: bool = False,
    symbol: str | None = None,
    log_dir: str | Path | None = None,
) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC)
    signals = _filter_symbol(load_signals(resolved_log_dir), symbol)
    outcomes = _filter_symbol(load_outcomes(resolved_log_dir), symbol)
    positions = _filter_symbol(load_positions(resolved_log_dir), symbol)
    open_positions = [position for position in positions if position.status == "open"]
    closed_positions = [position for position in positions if position.status == "closed"]
    signal_window_start = generated_at - timedelta(hours=max(since_hours, 0))
    window_signals = [
        signal
        for signal in signals
        if _timestamp_in_window(signal.timestamp, signal_window_start, generated_at)
    ]
    window_outcomes = [
        outcome
        for outcome in outcomes
        if _timestamp_in_window(outcome.evaluated_at, signal_window_start, generated_at)
        or _timestamp_in_window(outcome.timestamp, signal_window_start, generated_at)
    ]
    if tradable_only:
        window_signals = [signal for signal in window_signals if signal.tradable]

    latest_signal = signals[-1] if signals else None
    closed_pnl_usd = round(sum(position.pnl_usd or 0.0 for position in closed_positions), 4)
    closed_pnl_pct = round(sum(position.pnl_pct or 0.0 for position in closed_positions), 4)
    symbols = sorted({record.symbol for record in [*signals, *outcomes, *positions]})
    r9_coverage = _r9_coverage(signals)
    recent_bias = latest_signal.bias_direction if latest_signal is not None else "n/a"
    performance = _performance_summary(outcomes)
    positions_by_signal = _positions_by_signal(closed_positions)
    ranked = [
        _rank_candidate(signal, positions_by_signal.get(signal.signal_id, []))
        for signal in window_signals
    ]
    ranked.sort(key=lambda candidate: (candidate.score, candidate.signal.timestamp), reverse=True)
    ranked = ranked[: max(limit, 0)]

    lines = [
        "HAMMER RADAR DAILY TRADE CANDIDATE REPORT",
        "",
        "1. HEADER",
        f"archive_log_dir: {resolved_log_dir}",
        f"generated_at: {generated_at.isoformat()}",
        f"symbols: {', '.join(symbols) if symbols else (symbol or 'n/a')}",
        f"signal_window: last_{max(since_hours, 0)}h ({signal_window_start.isoformat()} to {generated_at.isoformat()})",
        f"total_signals_in_window: {len(window_signals)}",
        f"tradable_signals_in_window: {sum(1 for signal in window_signals if signal.tradable)}",
        f"total_outcomes_in_window: {len(window_outcomes)}",
        f"open_paper_positions: {len(open_positions)}",
        f"closed_paper_positions: {len(closed_positions)}",
        f"total_closed_paper_pnl_pct: {closed_pnl_pct:.4f}%",
        f"total_closed_paper_pnl_usd: {closed_pnl_usd:.4f}",
        "",
        "2. MARKET/STRATEGY SUMMARY",
        f"latest_signal_timestamp: {latest_signal.timestamp if latest_signal else 'n/a'}",
        f"latest_signal_direction_timeframe: {_latest_signal_direction_timeframe(latest_signal)}",
        f"recent_bias_direction: {recent_bias}",
        f"r9_metadata_coverage_pct: {r9_coverage:.2f}%",
        f"total_candidates_with_rsi: {sum(1 for signal in window_signals if signal.rsi_value is not None or signal.rsi_state is not None)}",
        f"total_candidates_with_confirmed_divergence: {sum(1 for signal in window_signals if signal.divergence_confirmed)}",
        f"total_candidates_with_extreme_or_critical_triggers: {sum(1 for signal in window_signals if signal.extreme_trigger or signal.critical_trigger)}",
        "",
        "3. PERFORMANCE SUMMARY",
        f"fill_rate: {performance['fill_rate']:.2f}%",
        f"win_rate_on_filled: {performance['win_rate_on_filled']:.2f}%",
        f"avg_pnl_pct: {performance['avg_pnl_pct']:.4f}%",
        f"avg_mae_pct: {performance['avg_mae_pct']:.4f}%",
        f"avg_mfe_pct: {performance['avg_mfe_pct']:.4f}%",
        f"best_by_rsi_state: {_best_grouping(signals, outcomes, 'rsi_state')}",
        f"best_by_divergence: {_best_grouping(signals, outcomes, 'divergence')}",
        f"best_by_timeframe: {_best_grouping(signals, outcomes, 'timeframe')}",
        f"best_by_entry_mode: {_best_outcome_grouping(outcomes, 'entry_mode')}",
        "",
        "4. CANDIDATE RANKING",
    ]
    if ranked:
        for index, candidate in enumerate(ranked, start=1):
            lines.extend(_format_candidate_lines(index, candidate))
    else:
        lines.append("no candidates in window")

    lines.extend(
        [
            "",
            "5. SAFETY/RISK OUTPUT",
            "This is paper/operator guidance only.",
            "No live order was placed.",
            "Suggested max live mode remains disabled.",
            "If human chooses manual live trade, require: isolated margin; predefined stop; predefined max daily loss; screenshot/log of entry; post-trade review.",
        ]
    )
    return "\n".join(lines)


def build_live_checklist_text(
    *,
    limit: int = 10,
    since_hours: int = 24,
    min_score: int = 90,
    symbol: str | None = None,
    allow_short: bool = False,
    allow_oversold: bool = False,
    allow_trigger_flags: bool = False,
    max_risk_usd: float = 5.0,
    max_leverage: float = 3.0,
    max_position_usd: float = 44.0,
    fresh_minutes: int = 30,
    allow_expired: bool = False,
    latest_only: bool = False,
    log_dir: str | Path | None = None,
) -> str:
    snapshot = build_live_candidate_snapshot(
        limit=limit,
        since_hours=since_hours,
        min_score=min_score,
        symbol=symbol,
        allow_short=allow_short,
        allow_oversold=allow_oversold,
        allow_trigger_flags=allow_trigger_flags,
        max_risk_usd=max_risk_usd,
        max_leverage=max_leverage,
        max_position_usd=max_position_usd,
        fresh_minutes=fresh_minutes,
        allow_expired=allow_expired,
        latest_only=latest_only,
        log_dir=log_dir,
    )
    resolved_log_dir = snapshot["archive_log_dir"]
    generated_at = snapshot["generated_at"]
    signal_window_start = snapshot["signal_window_start"]
    window_signals = snapshot["window_signals"]
    signals = snapshot["signals"]
    outcomes = snapshot["outcomes"]
    performance = snapshot["performance"]
    checks = snapshot["checks"]
    decisions = [check.decision for check in checks]
    current_eligible_count = sum(
        1
        for check in checks
        if check.decision == LIVE_DECISION_ELIGIBLE and check.freshness_status == "fresh"
    )
    expired_eligible_count = sum(
        1
        for check in checks
        if (
            check.decision == LIVE_DECISION_ELIGIBLE
            and check.freshness_status == "expired"
        )
        or "freshness gate" in check.reason
    )
    freshest_candidate = _freshest_signal(window_signals)
    freshest_age_minutes = _candidate_age_minutes(freshest_candidate, generated_at) if freshest_candidate else None

    lines = [
        "HAMMER RADAR MANUAL TINY-LIVE CHECKLIST",
        "CURRENT ACTION SUMMARY",
        f"current_eligible_count: {current_eligible_count}",
        f"expired_eligible_count: {expired_eligible_count}",
        f"paper_only_count: {decisions.count(LIVE_DECISION_PAPER_ONLY)}",
        f"forbidden_count: {decisions.count(LIVE_DECISION_FORBIDDEN)}",
        f"freshest_candidate_timestamp: {freshest_candidate.timestamp if freshest_candidate else 'n/a'}",
        f"freshest_candidate_age_minutes: {_format_optional_float(freshest_age_minutes)}",
        "",
        "1. HEADER",
        f"archive_log_dir: {resolved_log_dir}",
        f"generated_at: {generated_at.isoformat()}",
        f"symbol: {symbol or 'all'}",
        f"signal_window: last_{max(since_hours, 0)}h ({signal_window_start.isoformat()} to {generated_at.isoformat()})",
        f"min_score: {min_score}",
        f"max_risk_usd: {float(max_risk_usd):.2f}",
        f"max_leverage: {float(max_leverage):.2f}",
        f"max_position_usd: {float(max_position_usd):.2f}",
        f"fresh_minutes: {max(fresh_minutes, 0)}",
        f"allow_short: {allow_short}",
        f"allow_oversold: {allow_oversold}",
        f"allow_expired: {allow_expired}",
        f"latest_only: {latest_only}",
        f"allow_trigger_flags: {allow_trigger_flags}",
        "live_execution_enabled: false",
        "",
        "2. CURRENT EVIDENCE SUMMARY",
        f"total_signals_in_window: {len(window_signals)}",
        f"tradable_signals_in_window: {sum(1 for signal in window_signals if signal.tradable)}",
        f"r9_metadata_coverage_pct: {_r9_coverage(signals):.2f}%",
        f"win_rate_on_filled: {performance['win_rate_on_filled']:.2f}%",
        f"avg_pnl_pct: {performance['avg_pnl_pct']:.4f}%",
        f"best_rsi_state: {_best_grouping(signals, outcomes, 'rsi_state')}",
        f"best_divergence_bucket: {_best_grouping(signals, outcomes, 'divergence')}",
        f"best_timeframe: {_best_grouping(signals, outcomes, 'timeframe')}",
        f"best_entry_mode: {_best_outcome_grouping(outcomes, 'entry_mode')}",
        "",
        "3. LIVE ELIGIBILITY SUMMARY",
        f"eligible_tiny_live_count: {decisions.count(LIVE_DECISION_ELIGIBLE)}",
        f"paper_only_count: {decisions.count(LIVE_DECISION_PAPER_ONLY)}",
        f"forbidden_count: {decisions.count(LIVE_DECISION_FORBIDDEN)}",
        "",
        "4. CANDIDATE CHECKLIST",
    ]
    if checks:
        for index, check in enumerate(checks, start=1):
            lines.extend(_format_live_check_lines(index, check))
    else:
        lines.append("no candidates in window")

    lines.extend(
        [
            "",
            "5. SAFETY OUTPUT",
            "No live order was placed.",
            "This is a manual checklist only.",
            "Live exchange execution remains disabled.",
            "If manually trading, use isolated margin and predefined stop.",
            "This is not financial advice.",
        ]
    )
    return "\n".join(lines)


def build_live_candidate_snapshot(
    *,
    limit: int = 10,
    since_hours: int = 24,
    min_score: int = 90,
    symbol: str | None = None,
    allow_short: bool = False,
    allow_oversold: bool = False,
    allow_trigger_flags: bool = False,
    max_risk_usd: float = 5.0,
    max_leverage: float = 3.0,
    max_position_usd: float = 44.0,
    fresh_minutes: int = 30,
    allow_expired: bool = False,
    latest_only: bool = False,
    log_dir: str | Path | None = None,
) -> dict:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC)
    signals = _filter_symbol(load_signals(resolved_log_dir), symbol)
    outcomes = _filter_symbol(load_outcomes(resolved_log_dir), symbol)
    positions = _filter_symbol(load_positions(resolved_log_dir), symbol)
    closed_positions = [position for position in positions if position.status == "closed"]
    positions_by_signal = _positions_by_signal(closed_positions)
    signal_window_start = generated_at - timedelta(hours=max(since_hours, 0))
    window_signals = [
        signal
        for signal in signals
        if _timestamp_in_window(signal.timestamp, signal_window_start, generated_at)
    ]
    if latest_only:
        window_signals = sorted(window_signals, key=lambda signal: signal.timestamp, reverse=True)[:5]
    ranked = [
        _rank_candidate(signal, positions_by_signal.get(signal.signal_id, []))
        for signal in window_signals
    ]
    ranked.sort(key=lambda candidate: (candidate.score, candidate.signal.timestamp), reverse=True)
    if not latest_only:
        ranked = ranked[: max(limit, 0)]
    checks = [
        _build_live_check(
            candidate,
            generated_at=generated_at,
            min_score=min_score,
            allow_short=allow_short,
            allow_oversold=allow_oversold,
            allow_trigger_flags=allow_trigger_flags,
            allow_expired=allow_expired,
            max_risk_usd=max_risk_usd,
            max_leverage=max_leverage,
            max_position_usd=max_position_usd,
            fresh_minutes=fresh_minutes,
        )
        for candidate in ranked
    ]
    return {
        "archive_log_dir": resolved_log_dir,
        "generated_at": generated_at,
        "signal_window_start": signal_window_start,
        "window_signals": window_signals,
        "signals": signals,
        "outcomes": outcomes,
        "checks": checks,
        "performance": _performance_summary(outcomes),
    }


def build_betrayal_report_text(
    *,
    limit: int = 20,
    since_hours: int = 24,
    symbol: str | None = None,
    min_betrayal_score: int = 50,
    latest_only: bool = False,
    log_dir: str | Path | None = None,
) -> str:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC)
    signals = _filter_symbol(load_signals(resolved_log_dir), symbol)
    outcomes = _filter_symbol(load_outcomes(resolved_log_dir), symbol)
    signal_window_start = generated_at - timedelta(hours=max(since_hours, 0))
    window_signals = [
        signal
        for signal in signals
        if _timestamp_in_window(signal.timestamp, signal_window_start, generated_at)
    ]
    if latest_only:
        window_signals = sorted(window_signals, key=lambda signal: signal.timestamp, reverse=True)[:5]

    outcome_by_signal = _outcomes_by_signal(outcomes)
    candidates = [
        _build_betrayal_candidate(signal, generated_at=generated_at, outcomes=outcome_by_signal.get(signal.signal_id, []))
        for signal in window_signals
    ]
    candidates = [candidate for candidate in candidates if candidate.score >= min_betrayal_score]
    candidates.sort(key=lambda candidate: (candidate.score, candidate.signal.timestamp), reverse=True)
    if not latest_only:
        candidates = candidates[: max(limit, 0)]

    scores = [candidate.score for candidate in candidates]
    fresh_count = sum(1 for candidate in candidates if candidate.age_minutes is not None and candidate.age_minutes <= 30)

    lines = [
        "HAMMER RADAR BETRAYAL SHADOW REPORT",
        "",
        "1. HEADER",
        f"archive_log_dir: {resolved_log_dir}",
        f"generated_at: {generated_at.isoformat()}",
        f"signal_window: last_{max(since_hours, 0)}h ({signal_window_start.isoformat()} to {generated_at.isoformat()})",
        f"symbol: {symbol or 'all'}",
        f"total_signals_in_window: {len(window_signals)}",
        f"total_betrayal_candidates: {len(candidates)}",
        "live_execution_enabled: false",
        "betrayal_mode: shadow_only",
        "",
        "2. BETRAYAL SUMMARY",
        f"long_signal_betrayal_count: {sum(1 for candidate in candidates if candidate.signal.direction == 'long')}",
        f"short_signal_betrayal_count: {sum(1 for candidate in candidates if candidate.signal.direction == 'short')}",
        f"avg_betrayal_score: {_average(scores):.2f}",
        f"highest_betrayal_score: {max(scores) if scores else 0}",
        f"fresh_within_30m_count: {fresh_count}",
        "",
        "3. BETRAYAL CANDIDATES",
    ]
    if candidates:
        for index, candidate in enumerate(candidates, start=1):
            lines.extend(_format_betrayal_candidate_lines(index, candidate))
    else:
        lines.append("no betrayal candidates")

    lines.extend(
        [
            "",
            "4. SHADOW OUTCOME EVALUATION",
            "Opposite-direction outcomes are not available unless separately archived; this report does not fabricate shadow outcomes.",
            "",
            "5. SAFETY OUTPUT",
            "Betrayal mode is shadow-only.",
            "No live order was placed.",
            "This report does not affect live-checklist eligibility.",
            "Betrayal candidates require separate forward evidence before trading.",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "summary":
        print(build_summary_text(log_dir=args.log_dir))
    elif args.command == "signals":
        print(build_signals_text(limit=args.limit, log_dir=args.log_dir))
    elif args.command == "outcomes":
        print(build_outcomes_text(limit=args.limit, log_dir=args.log_dir))
    elif args.command == "positions":
        print(build_positions_text(status=args.status, log_dir=args.log_dir))
    elif args.command == "events":
        print(build_events_text(limit=args.limit, log_dir=args.log_dir))
    elif args.command == "r9-coverage":
        print(build_r9_coverage_text(log_dir=args.log_dir))
    elif args.command == "daily-report":
        print(
            build_daily_report_text(
                limit=args.limit,
                since_hours=args.since_hours,
                tradable_only=args.tradable_only,
                symbol=args.symbol,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "live-checklist":
        print(
            build_live_checklist_text(
                limit=args.limit,
                since_hours=args.since_hours,
                min_score=args.min_score,
                symbol=args.symbol,
                allow_short=args.allow_short,
                allow_oversold=args.allow_oversold,
                allow_trigger_flags=args.allow_trigger_flags,
                max_risk_usd=args.max_risk_usd,
                max_leverage=args.max_leverage,
                max_position_usd=args.max_position_usd,
                fresh_minutes=args.fresh_minutes,
                allow_expired=args.allow_expired,
                latest_only=args.latest_only,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "betrayal-report":
        print(
            build_betrayal_report_text(
                limit=args.limit,
                since_hours=args.since_hours,
                symbol=args.symbol,
                min_betrayal_score=args.min_betrayal_score,
                latest_only=args.latest_only,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "betrayal-shadow-track":
        from src.app.hammer_radar.operator.betrayal_shadow_outcomes import build_betrayal_shadow_track_text

        print(
            build_betrayal_shadow_track_text(
                latest_only=args.latest_only,
                limit=args.limit,
                since_hours=args.since_hours,
                symbol=args.symbol,
                min_betrayal_score=args.min_betrayal_score,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "betrayal-shadow-outcomes":
        from src.app.hammer_radar.operator.betrayal_shadow_outcomes import build_betrayal_shadow_outcomes_text

        print(
            build_betrayal_shadow_outcomes_text(
                limit=args.limit,
                symbol=args.symbol,
                status=args.status,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "betrayal-shadow-resolve":
        from src.app.hammer_radar.operator.betrayal_shadow_resolver import build_betrayal_shadow_resolve_text

        print(
            build_betrayal_shadow_resolve_text(
                limit=args.limit,
                symbol=args.symbol,
                timeframe=args.timeframe,
                since_hours=args.since_hours,
                write=args.write,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "betrayal-candle-archive":
        from src.app.hammer_radar.operator.betrayal_candle_archive import build_betrayal_candle_archive_text

        print(
            build_betrayal_candle_archive_text(
                symbol=args.symbol,
                timeframe=args.timeframe,
                limit=args.limit,
                since_hours=args.since_hours,
                write=args.write,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "betrayal-candle-capture":
        from src.app.hammer_radar.operator.betrayal_candle_capture import build_betrayal_candle_capture_text

        print(
            build_betrayal_candle_capture_text(
                symbol=args.symbol,
                timeframe=args.timeframe,
                limit=args.limit,
                since_hours=args.since_hours,
                write=args.write,
                source_mode=args.source_mode,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "betrayal-strategy-audit":
        from src.app.hammer_radar.operator.betrayal_strategy_audit import (
            build_betrayal_strategy_audit,
            format_betrayal_strategy_audit_text,
        )

        print(
            format_betrayal_strategy_audit_text(
                build_betrayal_strategy_audit(log_dir=args.log_dir)
            )
        )
    elif args.command == "betrayal-inverse-validation":
        from src.app.hammer_radar.operator.betrayal_inverse_validation import (
            build_betrayal_inverse_validation,
            format_betrayal_inverse_validation_text,
        )

        print(
            format_betrayal_inverse_validation_text(
                build_betrayal_inverse_validation(log_dir=args.log_dir)
            )
        )
    elif args.command == "markov-regime-gate":
        from src.app.hammer_radar.operator.markov_regime_gate import (
            build_markov_regime_gate,
            format_markov_regime_gate_text,
        )

        print(
            format_markov_regime_gate_text(
                build_markov_regime_gate(
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    limit=args.limit,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "miro-fish-quality-gate":
        from src.app.hammer_radar.operator.miro_fish_quality_gate import (
            build_miro_fish_quality_gate,
            format_miro_fish_quality_gate_text,
        )

        print(
            format_miro_fish_quality_gate_text(
                build_miro_fish_quality_gate(
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    family=args.family,
                    limit=args.limit,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "live-arming-preflight":
        from src.app.hammer_radar.operator.live_arming_preflight import (
            build_live_arming_preflight,
            format_live_arming_preflight_text,
        )

        print(
            format_live_arming_preflight_text(
                build_live_arming_preflight(
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "tiny-live-risk-contract":
        from src.app.hammer_radar.operator.tiny_live_risk_contract import (
            build_tiny_live_risk_contract_payload,
            format_tiny_live_risk_contract_text,
        )

        print(
            format_tiny_live_risk_contract_text(
                build_tiny_live_risk_contract_payload(candidate_id=args.candidate_id)
            )
        )
    elif args.command == "tiny-live-ticket":
        from src.app.hammer_radar.operator.tiny_live_ticket_builder import (
            build_tiny_live_ticket,
            format_tiny_live_ticket_text,
        )

        print(
            format_tiny_live_ticket_text(
                build_tiny_live_ticket(
                    candidate_id=args.candidate_id,
                    approval_phrase=args.approval_phrase,
                    operator_note=args.operator_note,
                    dry_run=not args.write,
                    write=args.write,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "live-env-checklist":
        from src.app.hammer_radar.operator.live_env_arming_checklist import (
            build_live_env_arming_checklist,
            format_live_env_arming_checklist_text,
        )

        print(
            format_live_env_arming_checklist_text(
                build_live_env_arming_checklist(
                    candidate_id=args.candidate_id,
                    manual_funding_phrase=args.manual_funding_phrase,
                    live_env_review_phrase=args.live_env_review_phrase,
                    max_loss_ack_phrase=args.max_loss_ack_phrase,
                    exact_candidate_ack_phrase=args.exact_candidate_ack_phrase,
                    operator_note=args.operator_note,
                    dry_run=not args.write,
                    write=args.write,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "live-env-boundary-review":
        from src.app.hammer_radar.operator.live_env_boundary_review import (
            build_live_env_boundary_review,
            format_live_env_boundary_review_text,
        )

        print(
            format_live_env_boundary_review_text(
                build_live_env_boundary_review(
                    candidate_id=args.candidate_id,
                    dry_run=not args.write,
                    write=args.write,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "final-review-packet":
        from src.app.hammer_radar.operator.final_human_review_packet import (
            build_final_human_review_packet,
            format_final_human_review_packet_text,
        )

        print(
            format_final_human_review_packet_text(
                build_final_human_review_packet(
                    candidate_id=args.candidate_id,
                    final_approval_phrase=args.final_approval_phrase,
                    operator_note=args.operator_note,
                    dry_run=not args.write,
                    write=args.write,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "human-confirmations":
        from src.app.hammer_radar.operator.human_confirmation_records import (
            build_human_confirmation_records,
            format_human_confirmation_records_text,
        )

        print(
            format_human_confirmation_records_text(
                build_human_confirmation_records(
                    candidate_id=args.candidate_id,
                    r85_approval_phrase=args.r85_approval_phrase,
                    r86_manual_funding_phrase=args.r86_manual_funding_phrase,
                    r86_live_env_review_phrase=args.r86_live_env_review_phrase,
                    r86_max_loss_ack_phrase=args.r86_max_loss_ack_phrase,
                    r86_exact_candidate_ack_phrase=args.r86_exact_candidate_ack_phrase,
                    r88_final_approval_phrase=args.r88_final_approval_phrase,
                    operator_note=args.operator_note,
                    dry_run=not args.write,
                    write=args.write,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "readiness-snapshot":
        from src.app.hammer_radar.operator.review_record_aggregator import (
            build_review_record_arming_snapshot,
            format_review_record_arming_snapshot_text,
        )

        print(
            format_review_record_arming_snapshot_text(
                build_review_record_arming_snapshot(
                    candidate_id=args.candidate_id,
                    dry_run=not args.write,
                    write=args.write,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "final-live-preflight":
        from src.app.hammer_radar.operator.final_live_preflight import (
            build_final_live_preflight,
            format_final_live_preflight_text,
        )

        print(
            format_final_live_preflight_text(
                build_final_live_preflight(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "tiny-live-armed-dry-run":
        from src.app.hammer_radar.operator.tiny_live_armed_dry_run import (
            build_tiny_live_armed_dry_run,
            format_tiny_live_armed_dry_run_text,
        )

        print(
            format_tiny_live_armed_dry_run_text(
                build_tiny_live_armed_dry_run(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                    record=not args.no_record,
                )
            )
        )
    elif args.command == "one-tiny-live-order-protocol":
        from src.app.hammer_radar.operator.one_tiny_live_order_protocol import (
            build_one_tiny_live_order_protocol_check,
            format_one_tiny_live_order_protocol_check_text,
        )

        print(
            format_one_tiny_live_order_protocol_check_text(
                build_one_tiny_live_order_protocol_check(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                    record=not args.no_record,
                )
            )
        )
    elif args.command == "first-live-activation-gate":
        from src.app.hammer_radar.operator.first_live_activation_gate import (
            build_first_live_activation_gate,
            format_first_live_activation_gate_text,
        )

        print(
            format_first_live_activation_gate_text(
                build_first_live_activation_gate(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                    record=not args.no_record,
                )
            )
        )
    elif args.command == "first-live-burn-down":
        from src.app.hammer_radar.operator.first_live_burn_down import (
            build_first_live_burn_down,
            format_first_live_burn_down_text,
        )

        print(
            format_first_live_burn_down_text(
                build_first_live_burn_down(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                    record=not args.no_record,
                )
            )
        )
    elif args.command == "first-live-prerequisite-clearing":
        from src.app.hammer_radar.operator.first_live_prerequisite_clearing import (
            build_first_live_prerequisite_clearing,
            format_first_live_prerequisite_clearing_text,
        )

        print(
            format_first_live_prerequisite_clearing_text(
                build_first_live_prerequisite_clearing(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                    record=not args.no_record,
                )
            )
        )
    elif args.command == "record-first-live-evidence":
        from src.app.hammer_radar.operator.first_live_operator_evidence import (
            format_first_live_operator_evidence_text,
            record_first_live_operator_evidence,
        )

        print(
            format_first_live_operator_evidence_text(
                record_first_live_operator_evidence(
                    evidence_type=args.evidence_type,
                    candidate_id=args.candidate_id,
                    risk_contract_hash=args.risk_contract_hash,
                    packet_hash=args.packet_hash,
                    note=args.note,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "first-live-evidence-status":
        from src.app.hammer_radar.operator.first_live_operator_evidence import (
            build_first_live_evidence_status,
            format_first_live_operator_evidence_text,
        )

        print(
            format_first_live_operator_evidence_text(
                build_first_live_evidence_status(log_dir=args.log_dir)
            )
        )
    elif args.command == "first-live-prerequisite-recheck-after-evidence":
        from src.app.hammer_radar.operator.first_live_prerequisite_recheck_after_evidence import (
            build_first_live_prerequisite_recheck_after_evidence,
            format_first_live_prerequisite_recheck_after_evidence_text,
        )

        print(
            format_first_live_prerequisite_recheck_after_evidence_text(
                build_first_live_prerequisite_recheck_after_evidence(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                    record=not args.no_record,
                )
            )
        )
    elif args.command == "first-live-evidence-guided-actions":
        from src.app.hammer_radar.operator.first_live_evidence_guided_actions import (
            build_first_live_evidence_guided_actions,
            format_first_live_evidence_guided_actions_text,
        )

        print(
            format_first_live_evidence_guided_actions_text(
                build_first_live_evidence_guided_actions(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                    record=not args.no_record,
                )
            )
        )
    elif args.command == "first-live-evidence-runbook":
        from src.app.hammer_radar.operator.first_live_evidence_runbook import (
            build_first_live_evidence_runbook,
            format_first_live_evidence_runbook_text,
        )

        print(
            format_first_live_evidence_runbook_text(
                build_first_live_evidence_runbook(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                    record=not args.no_record,
                )
            )
        )
    elif args.command == "first-live-evidence-assisted-run":
        from src.app.hammer_radar.operator.first_live_evidence_assisted_run import (
            build_first_live_evidence_assisted_run,
            format_first_live_evidence_assisted_run_text,
        )

        print(
            format_first_live_evidence_assisted_run_text(
                build_first_live_evidence_assisted_run(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                    group=args.group,
                    all_groups=args.all_groups,
                    execute_evidence=args.execute_evidence,
                    confirm_evidence_only=args.confirm_evidence_only,
                )
            )
        )
    elif args.command == "first-live-post-evidence-gate-recheck":
        from src.app.hammer_radar.operator.first_live_post_evidence_gate_recheck import (
            build_first_live_post_evidence_gate_recheck,
            format_first_live_post_evidence_gate_recheck_text,
        )

        print(
            format_first_live_post_evidence_gate_recheck_text(
                build_first_live_post_evidence_gate_recheck(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                    record=not args.no_record,
                )
            )
        )
    elif args.command == "first-live-activation-final-review":
        from src.app.hammer_radar.operator.first_live_activation_gate_final_review import (
            build_first_live_activation_final_review,
            format_first_live_activation_final_review_text,
        )

        print(
            format_first_live_activation_final_review_text(
                build_first_live_activation_final_review(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                    record=not args.no_record,
                )
            )
        )
    elif args.command == "first-live-blocker-clearing-workbench":
        from src.app.hammer_radar.operator.first_live_blocker_clearing_workbench import (
            build_first_live_blocker_clearing_workbench,
            format_first_live_blocker_clearing_workbench_text,
        )

        print(
            format_first_live_blocker_clearing_workbench_text(
                build_first_live_blocker_clearing_workbench(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                    record=not args.no_record,
                )
            )
        )
    elif args.command == "first-live-targeted-clearing-pack":
        from src.app.hammer_radar.operator.first_live_targeted_clearing_pack import (
            build_first_live_targeted_clearing_pack,
            format_first_live_targeted_clearing_pack_text,
        )

        print(
            format_first_live_targeted_clearing_pack_text(
                build_first_live_targeted_clearing_pack(
                    candidate_id=args.candidate_id,
                    log_dir=args.log_dir,
                    lane=args.lane,
                    all_evidence_lanes=args.all_evidence_lanes,
                    authorization_check=args.authorization_check,
                    record=not args.no_record,
                )
            )
        )
    elif args.command == "source-warning-review":
        from src.app.hammer_radar.operator.source_warning_review import (
            build_source_warning_review,
            format_source_warning_review_text,
        )

        print(
            format_source_warning_review_text(
                build_source_warning_review(
                    candidate_id=args.candidate_id,
                    dry_run=not args.write,
                    write=args.write,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "source-chain-repair":
        from src.app.hammer_radar.operator.source_chain_repair import (
            build_source_chain_repair,
            format_source_chain_repair_text,
        )

        print(
            format_source_chain_repair_text(
                build_source_chain_repair(
                    candidate_id=args.candidate_id,
                    dry_run=not args.write,
                    write=args.write,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "candidate-revalidation-watch":
        from src.app.hammer_radar.operator.candidate_revalidation_watch import (
            build_candidate_revalidation_watch,
            format_candidate_revalidation_watch_text,
        )

        print(
            format_candidate_revalidation_watch_text(
                build_candidate_revalidation_watch(
                    candidate_id=args.candidate_id,
                    dry_run=not args.write,
                    write=args.write,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "dual-lane-candidate-watch":
        from src.app.hammer_radar.operator.dual_lane_candidate_watch import (
            build_dual_lane_candidate_watch,
            format_dual_lane_candidate_watch_text,
        )

        print(
            format_dual_lane_candidate_watch_text(
                build_dual_lane_candidate_watch(
                    candidate_id=args.candidate_id,
                    dry_run=not args.write,
                    write=args.write,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "lane-control-status":
        from src.app.hammer_radar.operator.lane_control import (
            build_lane_control_status,
            format_lane_control_status_json,
        )

        print(
            format_lane_control_status_json(
                build_lane_control_status(
                    log_dir=args.log_dir,
                    deep_global_gate_review=args.deep_global_gate_review,
                )
            )
        )
    elif args.command == "lane-control-cockpit-state":
        from src.app.hammer_radar.operator.lane_control_cockpit import (
            build_lane_control_cockpit_state,
            format_lane_control_cockpit_state_json,
        )

        print(
            format_lane_control_cockpit_state_json(
                build_lane_control_cockpit_state(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                )
            )
        )
    elif args.command == "fresh-signal-router-status":
        from src.app.hammer_radar.operator.fresh_signal_router import (
            build_fresh_signal_router_status,
            format_fresh_signal_router_status_json,
        )

        print(
            format_fresh_signal_router_status_json(
                build_fresh_signal_router_status(
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "lane-control-command":
        from src.app.hammer_radar.operator.lane_command_interface import (
            apply_lane_command,
            format_lane_command_result_json,
        )

        print(
            format_lane_command_result_json(
                apply_lane_command(
                    action=args.action,
                    lane_key=args.lane_key,
                    mode=args.mode,
                    apply=args.apply,
                    confirm_lane_change=args.confirm_lane_change,
                    request_tiny_live=args.request_tiny_live,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "autonomous-paper-lane-execution":
        from src.app.hammer_radar.operator.autonomous_paper_lane_execution import (
            build_autonomous_paper_lane_execution_status,
            format_autonomous_paper_lane_execution_status_json,
        )

        print(
            format_autonomous_paper_lane_execution_status_json(
                build_autonomous_paper_lane_execution_status(
                    log_dir=args.log_dir,
                    execute_paper=args.execute_paper,
                    lane_key=args.lane_key,
                    all_lanes=args.all_lanes,
                    confirm_paper_only=args.confirm_paper_only,
                )
            )
        )
    elif args.command == "first-tiny-live-lane-execution-gate":
        from src.app.hammer_radar.operator.first_tiny_live_lane_execution_gate import (
            build_first_tiny_live_lane_execution_gate,
            format_first_tiny_live_lane_execution_gate_json,
        )

        print(
            format_first_tiny_live_lane_execution_gate_json(
                build_first_tiny_live_lane_execution_gate(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    candidate_id=args.candidate_id,
                    confirm_review_only=args.confirm_review_only,
                )
            )
        )
    elif args.command == "lane-autonomy-control-loop":
        from src.app.hammer_radar.operator.lane_autonomy_control_loop import (
            build_lane_autonomy_control_loop_status,
            format_lane_autonomy_control_loop_status_json,
        )

        print(
            format_lane_autonomy_control_loop_status_json(
                build_lane_autonomy_control_loop_status(
                    log_dir=args.log_dir,
                    record_decision=args.record_decision,
                    lane_key=args.lane_key,
                    all_lanes=args.all_lanes,
                    confirm_decision_record=args.confirm_decision_record,
                )
            )
        )
    elif args.command == "lane-autonomy-scheduler":
        from src.app.hammer_radar.operator.lane_autonomy_scheduler import (
            format_lane_autonomy_scheduler_status_json,
            run_lane_autonomy_scheduler_once,
        )

        print(
            format_lane_autonomy_scheduler_status_json(
                run_lane_autonomy_scheduler_once(
                    log_dir=args.log_dir,
                    record_tick=args.record_tick,
                    record_decisions=args.record_decisions,
                    lane_key=args.lane_key,
                    all_lanes=args.all_lanes,
                    confirm_scheduler_record=args.confirm_scheduler_record,
                )
            )
        )
    elif args.command == "autonomous-paper-lane-executor-integration":
        from src.app.hammer_radar.operator.autonomous_paper_lane_executor_integration import (
            format_autonomous_paper_lane_executor_integration_status_json,
            run_autonomous_paper_lane_executor_once,
        )

        print(
            format_autonomous_paper_lane_executor_integration_status_json(
                run_autonomous_paper_lane_executor_once(
                    log_dir=args.log_dir,
                    record_paper=args.record_paper,
                    record_scheduler_tick=args.record_scheduler_tick,
                    record_decisions=args.record_decisions,
                    lane_key=args.lane_key,
                    all_lanes=args.all_lanes,
                    confirm_paper_integration=args.confirm_paper_integration,
                )
            )
        )
    elif args.command == "first-tiny-live-autonomous-lane-authorization":
        from src.app.hammer_radar.operator.first_tiny_live_autonomous_lane_authorization import (
            build_first_tiny_live_autonomous_lane_authorization,
            format_first_tiny_live_autonomous_lane_authorization_json,
        )

        print(
            format_first_tiny_live_autonomous_lane_authorization_json(
                build_first_tiny_live_autonomous_lane_authorization(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_authorization=args.record_authorization,
                    request_lane_mode_tiny_live=args.request_lane_mode_tiny_live,
                    apply_lane_mode_change=args.apply_lane_mode_change,
                    confirm_tiny_live_authorization=args.confirm_tiny_live_authorization,
                )
            )
        )
    elif args.command == "live-lane-kill-switch-rehearsal":
        from src.app.hammer_radar.operator.live_lane_kill_switch_rehearsal import (
            build_live_lane_kill_switch_rehearsal_cli_payload,
            format_live_lane_kill_switch_rehearsal_json,
        )

        print(
            format_live_lane_kill_switch_rehearsal_json(
                build_live_lane_kill_switch_rehearsal_cli_payload(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_rehearsal=args.record_rehearsal,
                    confirm_rehearsal_record=args.confirm_rehearsal_record,
                )
            )
        )
    elif args.command == "live-adapter-boundary-final-review":
        from src.app.hammer_radar.operator.live_adapter_boundary_final_review import (
            build_live_adapter_boundary_final_review_cli_payload,
            format_live_adapter_boundary_final_review_json,
        )

        print(
            format_live_adapter_boundary_final_review_json(
                build_live_adapter_boundary_final_review_cli_payload(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_review=args.record_review,
                    confirm_boundary_review=args.confirm_boundary_review,
                )
            )
        )
    elif args.command == "first-tiny-live-order-payload-dry-authorization":
        from src.app.hammer_radar.operator.first_tiny_live_order_payload_dry_authorization import (
            build_first_tiny_live_order_payload_dry_authorization,
            format_first_tiny_live_order_payload_dry_authorization_json,
        )

        print(
            format_first_tiny_live_order_payload_dry_authorization_json(
                build_first_tiny_live_order_payload_dry_authorization(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_dry_authorization=args.record_dry_authorization,
                    confirm_dry_authorization=args.confirm_dry_authorization,
                )
            )
        )
    elif args.command == "live-adapter-execution-rehearsal":
        from src.app.hammer_radar.operator.live_adapter_execution_rehearsal import (
            build_live_adapter_execution_rehearsal,
            format_live_adapter_execution_rehearsal_json,
        )

        print(
            format_live_adapter_execution_rehearsal_json(
                build_live_adapter_execution_rehearsal(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_rehearsal=args.record_rehearsal,
                    confirm_adapter_rehearsal=args.confirm_adapter_rehearsal,
                )
            )
        )
    elif args.command == "protective-order-dry-policy-review":
        from src.app.hammer_radar.operator.protective_order_dry_policy_review import (
            build_protective_order_dry_policy_review,
            format_protective_order_dry_policy_review_json,
        )

        print(
            format_protective_order_dry_policy_review_json(
                build_protective_order_dry_policy_review(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_review=args.record_review,
                    confirm_protective_review=args.confirm_protective_review,
                )
            )
        )
    elif args.command == "protective-payload-dry-preview-boundary":
        from src.app.hammer_radar.operator.protective_payload_dry_preview_boundary import (
            build_protective_payload_dry_preview_boundary,
            format_protective_payload_dry_preview_boundary_json,
        )

        print(
            format_protective_payload_dry_preview_boundary_json(
                build_protective_payload_dry_preview_boundary(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_preview=args.record_preview,
                    confirm_protective_preview=args.confirm_protective_preview,
                )
            )
        )
    elif args.command == "autonomous-lane-live-ready-burn-down":
        from src.app.hammer_radar.operator.autonomous_lane_live_ready_burn_down import (
            build_autonomous_lane_live_ready_burn_down_cli_payload,
            format_autonomous_lane_live_ready_burn_down_json,
        )

        print(
            format_autonomous_lane_live_ready_burn_down_json(
                build_autonomous_lane_live_ready_burn_down_cli_payload(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_burn_down=args.record_burn_down,
                    confirm_burn_down=args.confirm_burn_down,
                )
            )
        )
    elif args.command == "burn-down-command-pack-sanity":
        from src.app.hammer_radar.operator.burn_down_command_pack_sanity import (
            build_burn_down_command_pack_sanity,
            format_burn_down_command_pack_sanity_json,
        )

        print(
            format_burn_down_command_pack_sanity_json(
                build_burn_down_command_pack_sanity(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                )
            )
        )
    elif args.command == "live-ready-blocker-clearing-operator-pack":
        from src.app.hammer_radar.operator.live_ready_blocker_clearing_operator_pack import (
            build_live_ready_blocker_clearing_operator_pack,
            format_live_ready_blocker_clearing_operator_pack_json,
        )

        print(
            format_live_ready_blocker_clearing_operator_pack_json(
                build_live_ready_blocker_clearing_operator_pack(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_pack=args.record_pack,
                    confirm_operator_pack=args.confirm_operator_pack,
                )
            )
        )
    elif args.command == "operator-executes-safe-clearing-pack":
        from src.app.hammer_radar.operator.operator_executes_safe_clearing_pack import (
            build_operator_executes_safe_clearing_pack,
            format_operator_executes_safe_clearing_pack_json,
        )

        print(
            format_operator_executes_safe_clearing_pack_json(
                build_operator_executes_safe_clearing_pack(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    execute_safe_clearing=args.execute_safe_clearing,
                    confirm_safe_clearing=args.confirm_safe_clearing,
                )
            )
        )
    elif args.command == "post-clearing-live-ready-recheck":
        from src.app.hammer_radar.operator.post_clearing_live_ready_recheck import (
            build_post_clearing_live_ready_recheck,
            format_post_clearing_live_ready_recheck_json,
        )

        print(
            format_post_clearing_live_ready_recheck_json(
                build_post_clearing_live_ready_recheck(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_recheck=args.record_recheck,
                    confirm_post_clearing_recheck=args.confirm_post_clearing_recheck,
                )
            )
        )
    elif args.command == "fresh-candidate-paper-proof-capture-loop":
        from src.app.hammer_radar.operator.fresh_candidate_paper_proof_capture_loop import (
            format_fresh_candidate_paper_proof_capture_loop_json,
            run_fresh_candidate_paper_proof_capture_loop,
        )

        print(
            format_fresh_candidate_paper_proof_capture_loop_json(
                run_fresh_candidate_paper_proof_capture_loop(
                    log_dir=args.log_dir,
                    lane_keys=args.lane_key,
                    lane_keys_csv=args.lane_keys,
                    watch_all_recommended_lanes=args.watch_all_recommended_lanes,
                    max_iterations=args.max_iterations,
                    sleep_seconds=args.sleep_seconds,
                    latest_signals=args.latest_signals,
                    latest_scans=args.latest_scans,
                    iteration_timeout_seconds=args.iteration_timeout_seconds,
                    heartbeat_every=args.heartbeat_every,
                    heartbeat_ledger_path=args.heartbeat_ledger_path,
                    run_watch_loop=args.run_watch_loop,
                    record_watch=args.record_watch,
                    confirm_watch_loop=args.confirm_watch_loop,
                    progress_fn=(lambda line: print(line, file=sys.stderr, flush=True)) if args.run_watch_loop else None,
                )
            )
        )
    elif args.command == "tiny-live-lane-unlock-contract":
        from src.app.hammer_radar.operator.tiny_live_lane_unlock_contract import (
            build_lane_unlock_contract,
            format_tiny_live_lane_unlock_contract_json,
        )

        print(
            format_tiny_live_lane_unlock_contract_json(
                build_lane_unlock_contract(
                    log_dir=args.log_dir,
                    lane_keys=args.lane_key,
                    lane_keys_csv=args.lane_keys,
                    unlock_all_recommended_lanes=args.unlock_all_recommended_lanes,
                    record_unlock_contract=args.record_unlock_contract,
                    confirm_unlock_contract=args.confirm_unlock_contract,
                    apply_lane_mode_if_safe=args.apply_lane_mode_if_safe,
                    status_only=args.status_only,
                )
            )
        )
    elif args.command == "signal-to-watcher-eligibility-trace":
        from src.app.hammer_radar.operator.signal_to_watcher_eligibility_trace import (
            build_signal_to_watcher_eligibility_trace,
            format_signal_to_watcher_eligibility_trace_json,
        )

        print(
            format_signal_to_watcher_eligibility_trace_json(
                build_signal_to_watcher_eligibility_trace(
                    log_dir=args.log_dir,
                    lane_keys=args.lane_key,
                    lane_keys_csv=args.lane_keys,
                    trace_all_unlocked_lanes=args.trace_all_unlocked_lanes,
                    latest_signals=args.latest_signals,
                    latest_scans=args.latest_scans,
                    signal_id=args.signal_id,
                    record_trace=args.record_trace,
                    confirm_trace=args.confirm_trace,
                )
            )
        )
    elif args.command == "entry-mode-derivation-bridge":
        from src.app.hammer_radar.operator.entry_mode_derivation_bridge import (
            build_entry_mode_derivation_bridge_status,
            format_entry_mode_derivation_bridge_json,
        )

        print(
            format_entry_mode_derivation_bridge_json(
                build_entry_mode_derivation_bridge_status(
                    log_dir=args.log_dir,
                    lane_keys=args.lane_key,
                    lane_keys_csv=args.lane_keys,
                    trace_all_unlocked_lanes=args.trace_all_unlocked_lanes,
                    latest_signals=args.latest_signals,
                    record_bridge=args.record_bridge,
                    confirm_bridge=args.confirm_bridge,
                )
            )
        )
    elif args.command == "post-bridge-watcher-proof-capture-recheck":
        from src.app.hammer_radar.operator.post_bridge_watcher_proof_capture_recheck import (
            build_post_bridge_watcher_proof_capture_recheck,
            format_post_bridge_watcher_proof_capture_recheck_json,
        )

        print(
            format_post_bridge_watcher_proof_capture_recheck_json(
                build_post_bridge_watcher_proof_capture_recheck(
                    log_dir=args.log_dir,
                    lane_keys=args.lane_key,
                    lane_keys_csv=args.lane_keys,
                    trace_all_unlocked_lanes=args.trace_all_unlocked_lanes,
                    latest_signals=args.latest_signals,
                    record_recheck=args.record_recheck,
                    confirm_post_bridge_recheck=args.confirm_post_bridge_recheck,
                )
            )
        )
    elif args.command == "apply-tiny-live-lane-mode-recheck":
        from src.app.hammer_radar.operator.apply_tiny_live_lane_mode_recheck import (
            build_tiny_live_lane_mode_recheck_status,
            format_tiny_live_lane_mode_recheck_json,
        )

        print(
            format_tiny_live_lane_mode_recheck_json(
                build_tiny_live_lane_mode_recheck_status(
                    log_dir=args.log_dir,
                    lane_keys=args.lane_key,
                    lane_keys_csv=args.lane_keys,
                    all_target_lanes=args.all_target_lanes,
                    record_recheck=args.record_recheck,
                    confirm_recheck=args.confirm_recheck,
                    include_apply_commands=args.include_apply_commands,
                    include_post_apply_recheck_commands=args.include_post_apply_recheck_commands,
                )
            )
        )
    elif args.command == "post-tiny-live-mode-fresh-proof-watch":
        from src.app.hammer_radar.operator.post_tiny_live_mode_fresh_proof_watch import (
            build_post_tiny_live_mode_fresh_proof_watch_preview,
            format_post_tiny_live_mode_fresh_proof_watch_json,
        )

        print(
            format_post_tiny_live_mode_fresh_proof_watch_json(
                build_post_tiny_live_mode_fresh_proof_watch_preview(
                    log_dir=args.log_dir,
                    lane_keys=args.lane_key,
                    lane_keys_csv=args.lane_keys,
                    all_target_lanes=args.all_target_lanes,
                    include_watch_command=args.include_watch_command,
                    record_watch_prep=args.record_watch_prep,
                    confirm_watch_prep=args.confirm_watch_prep,
                )
            )
        )
    elif args.command == "candidate-source-freshness-audit":
        from src.app.hammer_radar.operator.candidate_source_freshness_audit import (
            build_candidate_source_freshness_audit,
            format_candidate_source_freshness_audit_json,
        )

        print(
            format_candidate_source_freshness_audit_json(
                build_candidate_source_freshness_audit(
                    log_dir=args.log_dir,
                    latest_signals=args.latest_signals,
                    latest_scans=args.latest_scans,
                    watch_id=args.watch_id,
                    record_audit=args.record_audit,
                    confirm_audit=args.confirm_audit,
                )
            )
        )
    elif args.command == "paper-opportunity-expansion":
        from src.app.hammer_radar.operator.paper_opportunity_expansion import (
            build_paper_opportunity_expansion_preview,
            format_paper_opportunity_expansion_json,
        )

        print(
            format_paper_opportunity_expansion_json(
                build_paper_opportunity_expansion_preview(
                    log_dir=args.log_dir,
                    latest_signals=args.latest_signals,
                    latest_scans=args.latest_scans,
                    include_default_expansion=args.include_default_expansion,
                    apply=args.apply,
                    confirm_paper_expansion=args.confirm_paper_expansion,
                    record_expansion=args.record_expansion,
                )
            )
        )
    elif args.command == "expanded-paper-watch":
        from src.app.hammer_radar.operator.expanded_paper_watch import (
            build_expanded_paper_watch_preview,
            format_expanded_paper_watch_json,
        )

        print(
            format_expanded_paper_watch_json(
                build_expanded_paper_watch_preview(
                    log_dir=args.log_dir,
                    latest_signals=args.latest_signals,
                    latest_scans=args.latest_scans,
                    all_paper_lanes=args.all_paper_lanes,
                    include_tiny_live_targets_as_observed=args.include_tiny_live_targets_as_observed,
                    record_watch=args.record_watch,
                    confirm_expanded_paper_watch=args.confirm_expanded_paper_watch,
                )
            )
        )
    elif args.command == "multi-lane-paper-harvester":
        from src.app.hammer_radar.operator.multi_lane_paper_capture_harvester import (
            format_multi_lane_paper_harvester_json,
            run_multi_lane_paper_harvester_loop,
        )

        print(
            format_multi_lane_paper_harvester_json(
                run_multi_lane_paper_harvester_loop(
                    log_dir=args.log_dir,
                    latest_signals=args.latest_signals,
                    latest_scans=args.latest_scans,
                    max_iterations=args.max_iterations,
                    sleep_seconds=args.sleep_seconds,
                    iteration_timeout_seconds=args.iteration_timeout_seconds,
                    heartbeat_every=args.heartbeat_every,
                    max_captures_per_iteration=args.max_captures_per_iteration,
                    run_harvester_loop=args.run_harvester_loop,
                    record_harvest=args.record_harvest,
                    confirm_multi_lane_harvest=args.confirm_multi_lane_harvest,
                    progress_fn=(lambda line: print(line, file=sys.stderr, flush=True)) if args.run_harvester_loop else None,
                )
            )
        )
    elif args.command == "full-spectrum-harvester-expansion":
        from src.app.hammer_radar.operator.full_spectrum_harvester_expansion import (
            format_full_spectrum_harvester_expansion_json,
            run_full_spectrum_harvester_loop,
        )

        print(
            format_full_spectrum_harvester_expansion_json(
                run_full_spectrum_harvester_loop(
                    log_dir=args.log_dir,
                    latest_signals=args.latest_signals,
                    latest_scans=args.latest_scans,
                    max_iterations=args.max_iterations,
                    sleep_seconds=args.sleep_seconds,
                    iteration_timeout_seconds=args.iteration_timeout_seconds,
                    heartbeat_every=args.heartbeat_every,
                    max_captures_per_iteration=args.max_captures_per_iteration,
                    run_harvester_loop=args.run_harvester_loop,
                    record_harvest=args.record_harvest,
                    confirm_full_spectrum_harvest=args.confirm_full_spectrum_harvest,
                    progress_fn=(lambda line: print(line, file=sys.stderr, flush=True)) if args.run_harvester_loop else None,
                )
            )
        )
    elif args.command == "multi-lane-evidence-ranking":
        from src.app.hammer_radar.operator.multi_lane_evidence_ranking import (
            build_multi_lane_evidence_ranking,
            format_multi_lane_evidence_ranking_json,
        )

        print(
            format_multi_lane_evidence_ranking_json(
                build_multi_lane_evidence_ranking(
                    log_dir=args.log_dir,
                    record_ranking=args.record_ranking,
                    confirm_multi_lane_ranking=args.confirm_multi_lane_ranking,
                )
            )
        )
    elif args.command == "signal-origin-registry":
        from src.app.hammer_radar.operator.signal_origin_registry import (
            build_signal_origin_registry_preview,
            format_signal_origin_registry_json,
        )

        print(
            format_signal_origin_registry_json(
                build_signal_origin_registry_preview(
                    log_dir=args.log_dir,
                    latest_signals=args.latest_signals,
                    latest_harvest_records=args.latest_harvest_records,
                    record_registry=args.record_registry,
                    confirm_signal_origin_registry=args.confirm_signal_origin_registry,
                )
            )
        )
    elif args.command == "keter-signal-origin-scoring":
        from src.app.hammer_radar.operator.keter_signal_origin_scoring import (
            build_keter_signal_origin_scoring,
            format_keter_signal_origin_scoring_json,
        )

        print(
            format_keter_signal_origin_scoring_json(
                build_keter_signal_origin_scoring(
                    log_dir=args.log_dir,
                    latest_registry_records=args.latest_registry_records,
                    latest_ranking_records=args.latest_ranking_records,
                    record_scoring=args.record_scoring,
                    confirm_keter_origin_scoring=args.confirm_keter_origin_scoring,
                )
            )
        )
    elif args.command == "signal-origin-lane-matrix":
        from src.app.hammer_radar.operator.signal_origin_lane_matrix import (
            build_signal_origin_lane_matrix,
            format_signal_origin_lane_matrix_json,
        )

        print(
            format_signal_origin_lane_matrix_json(
                build_signal_origin_lane_matrix(
                    log_dir=args.log_dir,
                    latest_ranking_records=args.latest_ranking_records,
                    latest_scoring_records=args.latest_scoring_records,
                    record_matrix=args.record_matrix,
                    confirm_signal_origin_lane_matrix=args.confirm_signal_origin_lane_matrix,
                )
            )
        )
    elif args.command == "three-black-crows-detector":
        from src.app.hammer_radar.operator.three_black_crows_detector import (
            build_three_black_crows_detector_preview,
            format_three_black_crows_detector_json,
        )

        print(
            format_three_black_crows_detector_json(
                build_three_black_crows_detector_preview(
                    log_dir=args.log_dir,
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    mode=args.mode,
                    latest_candles=args.latest_candles,
                    record_detector=args.record_detector,
                    confirm_three_black_crows_detector=args.confirm_three_black_crows_detector,
                )
            )
        )
    elif args.command == "three-black-crows-feed-integration":
        from src.app.hammer_radar.operator.three_black_crows_feed_integration import (
            build_three_black_crows_feed_integration,
            format_three_black_crows_feed_integration_json,
        )

        print(
            format_three_black_crows_feed_integration_json(
                build_three_black_crows_feed_integration(
                    log_dir=args.log_dir,
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    mode=args.mode,
                    latest_candles=args.latest_candles,
                    record_integration=args.record_integration,
                    confirm_three_black_crows_feed_integration=args.confirm_three_black_crows_feed_integration,
                )
            )
        )
    elif args.command == "local-candle-feed-preview":
        from src.app.hammer_radar.operator.local_candle_feed_capture_preview import (
            build_local_candle_feed_capture_preview,
            format_local_candle_feed_capture_preview_json,
        )

        print(
            format_local_candle_feed_capture_preview_json(
                build_local_candle_feed_capture_preview(
                    log_dir=args.log_dir,
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    latest_candles=args.latest_candles,
                    record_preview=args.record_preview,
                    confirm_local_candle_feed_preview=args.confirm_local_candle_feed_preview,
                )
            )
        )
    elif args.command == "local-candle-feed-adapter":
        from src.app.hammer_radar.operator.local_candle_feed_adapter import (
            build_local_candle_feed_adapter_preview,
            format_local_candle_feed_adapter_json,
        )

        print(
            format_local_candle_feed_adapter_json(
                build_local_candle_feed_adapter_preview(
                    log_dir=args.log_dir,
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    latest_candles=args.latest_candles,
                    record_adapter=args.record_adapter,
                    confirm_local_candle_feed_adapter=args.confirm_local_candle_feed_adapter,
                    write_normalized_feed=args.write_normalized_feed,
                    confirm_normalized_candle_feed_write=args.confirm_normalized_candle_feed_write,
                )
            )
        )
    elif args.command == "three-black-crows-local-detection":
        from src.app.hammer_radar.operator.three_black_crows_local_feed_detection import (
            build_three_black_crows_local_feed_detection,
            format_three_black_crows_local_feed_detection_json,
        )

        print(
            format_three_black_crows_local_feed_detection_json(
                build_three_black_crows_local_feed_detection(
                    log_dir=args.log_dir,
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    latest_candles=args.latest_candles,
                    mode=args.mode,
                    record_detection=args.record_detection,
                    confirm_three_black_crows_local_detection=args.confirm_three_black_crows_local_detection,
                )
            )
        )
    elif args.command == "pattern-detector-family-expansion":
        from src.app.hammer_radar.operator.pattern_detector_family_expansion import (
            build_pattern_detector_family_expansion,
            format_pattern_detector_family_expansion_json,
        )

        print(
            format_pattern_detector_family_expansion_json(
                build_pattern_detector_family_expansion(
                    log_dir=args.log_dir,
                    symbol=args.symbol,
                    timeframes=args.timeframes,
                    mode=args.mode,
                    latest_candles=args.latest_candles,
                    record_expansion=args.record_expansion,
                    confirm_pattern_family_expansion=args.confirm_pattern_family_expansion,
                )
            )
        )
    elif args.command == "wma-ma-anchor-layer-preview":
        from src.app.hammer_radar.operator.wma_ma_anchor_layer_preview import (
            build_wma_ma_anchor_layer_preview,
            format_wma_ma_anchor_layer_preview_json,
        )

        print(
            format_wma_ma_anchor_layer_preview_json(
                build_wma_ma_anchor_layer_preview(
                    log_dir=args.log_dir,
                    symbol=args.symbol,
                    timeframes=args.timeframes,
                    periods=args.periods,
                    near_touch_threshold_pct=args.near_touch_threshold_pct,
                    success_threshold_pct=args.success_threshold_pct,
                    adverse_threshold_pct=args.adverse_threshold_pct,
                    record_preview=args.record_preview,
                    confirm_wma_ma_anchor_preview=args.confirm_wma_ma_anchor_preview,
                )
            )
        )
    elif args.command == "signal-origin-feedback-sync":
        from src.app.hammer_radar.operator.signal_origin_feedback_sync import (
            build_signal_origin_feedback_sync_after_three_black_crows,
            format_signal_origin_feedback_sync_json,
        )

        print(
            format_signal_origin_feedback_sync_json(
                build_signal_origin_feedback_sync_after_three_black_crows(
                    log_dir=args.log_dir,
                    signal_origin=args.signal_origin,
                    lane_key=args.lane_key,
                    record_feedback=args.record_feedback,
                    confirm_signal_origin_feedback_sync=args.confirm_signal_origin_feedback_sync,
                )
            )
        )
    elif args.command == "pattern-family-feedback-sync":
        from src.app.hammer_radar.operator.pattern_family_feedback_sync import (
            build_pattern_family_feedback_sync,
            format_pattern_family_feedback_sync_json,
        )

        print(
            format_pattern_family_feedback_sync_json(
                build_pattern_family_feedback_sync(
                    log_dir=args.log_dir,
                    record_feedback=args.record_feedback,
                    confirm_pattern_family_feedback_sync=args.confirm_pattern_family_feedback_sync,
                )
            )
        )
    elif args.command == "anchor-outcome-deepening":
        from src.app.hammer_radar.operator.anchor_outcome_deepening import (
            build_anchor_outcome_deepening,
            format_anchor_outcome_deepening_json,
        )

        print(
            format_anchor_outcome_deepening_json(
                build_anchor_outcome_deepening(
                    log_dir=args.log_dir,
                    symbol=args.symbol,
                    record_deepening=args.record_deepening,
                    confirm_anchor_outcome_deepening=args.confirm_anchor_outcome_deepening,
                )
            )
        )
    elif args.command == "keter-rescore-after-three-black-crows":
        from src.app.hammer_radar.operator.keter_rescoring_after_three_black_crows import (
            build_keter_rescoring_after_three_black_crows,
            format_keter_rescore_after_three_black_crows_json,
        )

        print(
            format_keter_rescore_after_three_black_crows_json(
                build_keter_rescoring_after_three_black_crows(
                    log_dir=args.log_dir,
                    record_rescore=args.record_rescore,
                    confirm_keter_rescore_after_crows=args.confirm_keter_rescore_after_crows,
                )
            )
        )
    elif args.command == "lane-matrix-after-crow-rescoring":
        from src.app.hammer_radar.operator.lane_matrix_after_crow_rescoring import (
            build_lane_matrix_after_crow_rescoring,
            format_lane_matrix_after_crow_rescoring_json,
        )

        print(
            format_lane_matrix_after_crow_rescoring_json(
                build_lane_matrix_after_crow_rescoring(
                    log_dir=args.log_dir,
                    record_matrix=args.record_matrix,
                    confirm_lane_matrix_after_crow_rescore=args.confirm_lane_matrix_after_crow_rescore,
                )
            )
        )
    elif args.command == "crow-outcome-mapping-preview":
        from src.app.hammer_radar.operator.crow_outcome_mapping_preview import (
            build_crow_outcome_mapping_preview,
            format_crow_outcome_mapping_preview_json,
        )

        print(
            format_crow_outcome_mapping_preview_json(
                build_crow_outcome_mapping_preview(
                    log_dir=args.log_dir,
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    lane_key=args.lane_key,
                    success_threshold_pct=args.success_threshold_pct,
                    adverse_threshold_pct=args.adverse_threshold_pct,
                    record_mapping=args.record_mapping,
                    confirm_crow_outcome_mapping=args.confirm_crow_outcome_mapping,
                )
            )
        )
    elif args.command == "pattern-outcome-mapping-family":
        from src.app.hammer_radar.operator.pattern_outcome_mapping_family import (
            build_pattern_outcome_mapping_family,
            format_pattern_outcome_mapping_family_json,
        )

        print(
            format_pattern_outcome_mapping_family_json(
                build_pattern_outcome_mapping_family(
                    log_dir=args.log_dir,
                    symbol=args.symbol,
                    success_threshold_pct=args.success_threshold_pct,
                    adverse_threshold_pct=args.adverse_threshold_pct,
                    record_mapping=args.record_mapping,
                    confirm_pattern_outcome_family=args.confirm_pattern_outcome_family,
                )
            )
        )
    elif args.command == "crow-outcome-keter-feedback":
        from src.app.hammer_radar.operator.crow_outcome_keter_feedback import (
            build_crow_outcome_keter_feedback,
            format_crow_outcome_keter_feedback_json,
        )

        print(
            format_crow_outcome_keter_feedback_json(
                build_crow_outcome_keter_feedback(
                    log_dir=args.log_dir,
                    record_feedback=args.record_feedback,
                    confirm_crow_outcome_keter_feedback=args.confirm_crow_outcome_keter_feedback,
                )
            )
        )
    elif args.command == "pattern-keter-rescoring-family":
        from src.app.hammer_radar.operator.pattern_keter_rescoring_family import (
            build_pattern_keter_rescoring_family,
            format_pattern_keter_rescoring_family_json,
        )

        print(
            format_pattern_keter_rescoring_family_json(
                build_pattern_keter_rescoring_family(
                    log_dir=args.log_dir,
                    record_rescore=args.record_rescore,
                    confirm_pattern_keter_family=args.confirm_pattern_keter_family,
                )
            )
        )
    elif args.command == "pattern-lane-matrix-review":
        from src.app.hammer_radar.operator.pattern_lane_matrix_review import (
            build_pattern_lane_matrix_review,
            format_pattern_lane_matrix_review_json,
        )

        print(
            format_pattern_lane_matrix_review_json(
                build_pattern_lane_matrix_review(
                    log_dir=args.log_dir,
                    record_matrix=args.record_matrix,
                    confirm_pattern_lane_matrix=args.confirm_pattern_lane_matrix,
                )
            )
        )
    elif args.command == "anchor-signal-confluence-matrix":
        from src.app.hammer_radar.operator.anchor_signal_confluence_matrix import (
            build_anchor_signal_confluence_matrix,
            format_anchor_signal_confluence_matrix_json,
        )

        print(
            format_anchor_signal_confluence_matrix_json(
                build_anchor_signal_confluence_matrix(
                    log_dir=args.log_dir,
                    record_matrix=args.record_matrix,
                    confirm_anchor_signal_confluence=args.confirm_anchor_signal_confluence,
                )
            )
        )
    elif args.command == "strategy-evidence-registry":
        from src.app.hammer_radar.operator.strategy_evidence_registry import (
            build_strategy_evidence_registry,
            format_strategy_evidence_registry_json,
        )

        print(
            format_strategy_evidence_registry_json(
                build_strategy_evidence_registry(
                    log_dir=args.log_dir,
                    record_registry=args.record_registry,
                    confirm_strategy_evidence_registry=args.confirm_strategy_evidence_registry,
                )
            )
        )
    elif args.command == "lane-matrix-after-crow-outcome-feedback":
        from src.app.hammer_radar.operator.lane_matrix_after_crow_outcome_feedback import (
            build_lane_matrix_after_crow_outcome_feedback,
            format_lane_matrix_after_crow_outcome_feedback_json,
        )

        print(
            format_lane_matrix_after_crow_outcome_feedback_json(
                build_lane_matrix_after_crow_outcome_feedback(
                    log_dir=args.log_dir,
                    record_matrix=args.record_matrix,
                    confirm_lane_matrix_after_crow_outcome=args.confirm_lane_matrix_after_crow_outcome,
                )
            )
        )
    elif args.command == "full-spectrum-paper-coverage-audit":
        from src.app.hammer_radar.operator.full_spectrum_paper_coverage_audit import (
            build_full_spectrum_paper_coverage_audit,
            format_full_spectrum_paper_coverage_audit_json,
        )

        print(
            format_full_spectrum_paper_coverage_audit_json(
                build_full_spectrum_paper_coverage_audit(
                    log_dir=args.log_dir,
                    record_audit=args.record_audit,
                    confirm_full_spectrum_paper_audit=args.confirm_full_spectrum_paper_audit,
                )
            )
        )
    elif args.command == "promotion-candidate-audit":
        from src.app.hammer_radar.operator.promotion_candidate_audit import (
            build_promotion_candidate_audit,
            format_promotion_candidate_audit_json,
        )

        print(
            format_promotion_candidate_audit_json(
                build_promotion_candidate_audit(
                    log_dir=args.log_dir,
                    latest_outcomes=args.latest_outcomes,
                    latest_signals=args.latest_signals,
                    latest_watch_records=args.latest_watch_records,
                    include_paper_lanes=args.include_paper_lanes,
                    include_tiny_live_incumbents=args.include_tiny_live_incumbents,
                    record_audit=args.record_audit,
                    confirm_promotion_audit=args.confirm_promotion_audit,
                )
            )
        )
    elif args.command == "full-spectrum-betrayal-short-review":
        from src.app.hammer_radar.operator.full_spectrum_betrayal_short_review import (
            build_full_spectrum_betrayal_short_review,
            format_full_spectrum_betrayal_review_json,
        )

        print(
            format_full_spectrum_betrayal_review_json(
                build_full_spectrum_betrayal_short_review(
                    log_dir=args.log_dir,
                    latest_outcomes=args.latest_outcomes,
                    latest_signals=args.latest_signals,
                    latest_betrayal=args.latest_betrayal,
                    latest_watch_records=args.latest_watch_records,
                    include_paper_lanes=args.include_paper_lanes,
                    include_tiny_live_incumbents=args.include_tiny_live_incumbents,
                    include_betrayal_inverse=args.include_betrayal_inverse,
                    record_review=args.record_review,
                    confirm_full_spectrum_review=args.confirm_full_spectrum_review,
                )
            )
        )
    elif args.command == "short-strategy-packet":
        from src.app.hammer_radar.operator.short_strategy_packet import (
            build_short_strategy_packet,
            format_short_strategy_packet_json,
        )

        print(
            format_short_strategy_packet_json(
                build_short_strategy_packet(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    latest_outcomes=args.latest_outcomes,
                    latest_signals=args.latest_signals,
                    latest_betrayal=args.latest_betrayal,
                    latest_watch_records=args.latest_watch_records,
                    record_packet=args.record_packet,
                    confirm_short_strategy_packet=args.confirm_short_strategy_packet,
                )
            )
        )
    elif args.command == "short-paper-evidence-capture-loop":
        from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import (
            format_short_paper_evidence_capture_json,
            run_short_paper_evidence_capture_loop,
        )

        print(
            format_short_paper_evidence_capture_json(
                run_short_paper_evidence_capture_loop(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    latest_signals=args.latest_signals,
                    latest_scans=args.latest_scans,
                    max_iterations=args.max_iterations,
                    sleep_seconds=args.sleep_seconds,
                    iteration_timeout_seconds=args.iteration_timeout_seconds,
                    heartbeat_every=args.heartbeat_every,
                    run_capture_loop=args.run_capture_loop,
                    record_capture=args.record_capture,
                    confirm_short_paper_capture=args.confirm_short_paper_capture,
                    progress_fn=(lambda line: print(line, file=sys.stderr, flush=True)) if args.run_capture_loop else None,
                )
            )
        )
    elif args.command == "short-evidence-recheck-packet":
        from src.app.hammer_radar.operator.short_evidence_recheck_packet import (
            build_short_evidence_recheck_packet,
            format_short_evidence_recheck_packet_json,
        )

        print(
            format_short_evidence_recheck_packet_json(
                build_short_evidence_recheck_packet(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    latest_captures=args.latest_captures,
                    latest_outcomes=args.latest_outcomes,
                    latest_signals=args.latest_signals,
                    latest_betrayal=args.latest_betrayal,
                    record_packet=args.record_packet,
                    confirm_short_evidence_recheck=args.confirm_short_evidence_recheck,
                )
            )
        )
    elif args.command == "fundless-short-tiny-live-readiness-rehearsal":
        from src.app.hammer_radar.operator.fundless_short_tiny_live_readiness_rehearsal import (
            build_fundless_short_tiny_live_readiness_rehearsal,
            format_fundless_readiness_rehearsal_json,
        )

        print(
            format_fundless_readiness_rehearsal_json(
                build_fundless_short_tiny_live_readiness_rehearsal(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    latest_captures=args.latest_captures,
                    latest_outcomes=args.latest_outcomes,
                    latest_signals=args.latest_signals,
                    record_rehearsal=args.record_rehearsal,
                    confirm_fundless_short_rehearsal=args.confirm_fundless_short_rehearsal,
                )
            )
        )
    elif args.command == "fundless-short-dry-run-packet":
        from src.app.hammer_radar.operator.fundless_short_dry_run_packet import (
            build_fundless_short_dry_run_packet,
            format_fundless_short_dry_run_packet_json,
        )

        print(
            format_fundless_short_dry_run_packet_json(
                build_fundless_short_dry_run_packet(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    latest_captures=args.latest_captures,
                    latest_outcomes=args.latest_outcomes,
                    latest_signals=args.latest_signals,
                    record_packet=args.record_packet,
                    confirm_fundless_short_dry_run=args.confirm_fundless_short_dry_run,
                )
            )
        )
    elif args.command == "short-risk-contract-draft-preview":
        from src.app.hammer_radar.operator.short_risk_contract_draft_preview import (
            build_short_risk_contract_draft_preview,
            format_short_risk_contract_draft_preview_json,
        )

        print(
            format_short_risk_contract_draft_preview_json(
                build_short_risk_contract_draft_preview(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_draft=args.record_draft,
                    confirm_short_risk_contract_draft=args.confirm_short_risk_contract_draft,
                )
            )
        )
    elif args.command == "short-risk-contract-apply-review":
        from src.app.hammer_radar.operator.short_risk_contract_apply_review import (
            build_short_risk_contract_apply_review,
            format_short_risk_contract_apply_review_json,
        )

        print(
            format_short_risk_contract_apply_review_json(
                build_short_risk_contract_apply_review(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    latest_captures=args.latest_captures,
                    latest_drafts=args.latest_drafts,
                    record_review=args.record_review,
                    confirm_short_risk_contract_apply_review=args.confirm_short_risk_contract_apply_review,
                )
            )
        )
    elif args.command == "funding-readonly-precheck":
        from src.app.hammer_radar.operator.funding_readonly_precheck import (
            build_funding_readonly_precheck,
            format_funding_readonly_precheck_json,
        )

        print(
            format_funding_readonly_precheck_json(
                build_funding_readonly_precheck(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    minimum_balance_usdt=args.minimum_balance_usdt,
                    allow_readonly_network_check=args.allow_readonly_network_check,
                    record_precheck=args.record_precheck,
                    confirm_funding_readonly_precheck=args.confirm_funding_readonly_precheck,
                )
            )
        )
    elif args.command == "readonly-balance-check":
        from src.app.hammer_radar.operator.readonly_balance_check import (
            build_readonly_balance_check,
            format_readonly_balance_check_json,
        )

        print(
            format_readonly_balance_check_json(
                build_readonly_balance_check(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    minimum_balance_usdt=args.minimum_balance_usdt,
                    allow_readonly_network_check=args.allow_readonly_network_check,
                    recv_window_ms=args.recv_window_ms,
                    record_balance_check=args.record_balance_check,
                    confirm_readonly_balance_check=args.confirm_readonly_balance_check,
                )
            )
        )
    elif args.command == "readonly-balance-failure-recheck":
        from src.app.hammer_radar.operator.readonly_balance_failure_classifier import (
            build_readonly_balance_failure_recheck,
            format_readonly_balance_failure_recheck_json,
        )

        print(
            format_readonly_balance_failure_recheck_json(
                build_readonly_balance_failure_recheck(
                    log_dir=args.log_dir,
                    latest_balance_checks=args.latest_balance_checks,
                    record_recheck=args.record_recheck,
                    confirm_readonly_balance_failure_recheck=args.confirm_readonly_balance_failure_recheck,
                )
            )
        )
    elif args.command == "funding-gate-key-role-sync":
        from src.app.hammer_radar.operator.funding_gate_key_role_sync import (
            build_funding_gate_key_role_sync,
            format_funding_gate_key_role_sync_json,
        )

        print(
            format_funding_gate_key_role_sync_json(
                build_funding_gate_key_role_sync(
                    log_dir=args.log_dir,
                    record_sync=args.record_sync,
                    confirm_funding_key_role_sync=args.confirm_funding_key_role_sync,
                )
            )
        )
    elif args.command == "funding-gate-role-specific-sync":
        from src.app.hammer_radar.operator.funding_gate_role_specific_sync import (
            build_funding_gate_role_specific_sync,
            format_funding_gate_role_specific_sync_json,
        )

        print(
            format_funding_gate_role_specific_sync_json(
                build_funding_gate_role_specific_sync(
                    log_dir=args.log_dir,
                    record_sync=args.record_sync,
                    confirm_funding_role_specific_sync=args.confirm_funding_role_specific_sync,
                )
            )
        )
    elif args.command == "tiny-live-blocker-burn-down":
        from src.app.hammer_radar.operator.tiny_live_blocker_burn_down import (
            build_tiny_live_blocker_burn_down,
            format_tiny_live_blocker_burn_down_json,
        )

        print(
            format_tiny_live_blocker_burn_down_json(
                build_tiny_live_blocker_burn_down(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_burn_down=args.record_burn_down,
                    confirm_tiny_live_burn_down=args.confirm_tiny_live_burn_down,
                )
            )
        )
    elif args.command == "capture-count-sync-8m-short":
        from src.app.hammer_radar.operator.capture_count_sync_8m_short import (
            build_capture_count_sync_8m_short,
            format_capture_count_sync_8m_short_json,
        )

        print(
            format_capture_count_sync_8m_short_json(
                build_capture_count_sync_8m_short(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_sync=args.record_sync,
                    confirm_capture_count_sync=args.confirm_capture_count_sync,
                )
            )
        )
    elif args.command == "tiny-live-readiness-gap-recheck":
        from src.app.hammer_radar.operator.tiny_live_readiness_gap_recheck import (
            build_tiny_live_readiness_gap_recheck,
            format_tiny_live_readiness_gap_recheck_json,
        )

        print(
            format_tiny_live_readiness_gap_recheck_json(
                build_tiny_live_readiness_gap_recheck(
                    log_dir=args.log_dir,
                    record_recheck=args.record_recheck,
                    confirm_tiny_live_gap_recheck=args.confirm_tiny_live_gap_recheck,
                )
            )
        )
    elif args.command == "capture-threshold-recovery-8m-short":
        from src.app.hammer_radar.operator.capture_threshold_recovery_8m_short import (
            build_capture_threshold_recovery_8m_short,
            format_capture_threshold_recovery_8m_short_json,
        )

        print(
            format_capture_threshold_recovery_8m_short_json(
                build_capture_threshold_recovery_8m_short(
                    log_dir=args.log_dir,
                    record_recovery=args.record_recovery,
                    confirm_capture_threshold_recovery=args.confirm_capture_threshold_recovery,
                )
            )
        )
    elif args.command == "evidence-threshold-recheck-8m-short":
        from src.app.hammer_radar.operator.evidence_threshold_recheck_8m_short import (
            build_evidence_threshold_recheck_8m_short,
            format_evidence_threshold_recheck_8m_short_json,
        )

        print(
            format_evidence_threshold_recheck_8m_short_json(
                build_evidence_threshold_recheck_8m_short(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_recheck=args.record_recheck,
                    confirm_evidence_threshold_recheck=args.confirm_evidence_threshold_recheck,
                )
            )
        )
    elif args.command == "capture-watcher-supervisor-8m-short":
        from src.app.hammer_radar.operator.capture_watcher_supervisor_8m_short import (
            build_capture_watcher_supervisor_once,
            format_capture_watcher_supervisor_8m_short_json,
            run_capture_watcher_supervisor_loop,
        )

        builder = run_capture_watcher_supervisor_loop if args.run_supervisor_loop else build_capture_watcher_supervisor_once
        print(
            format_capture_watcher_supervisor_8m_short_json(
                builder(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_supervisor=args.record_supervisor,
                    confirm_capture_watcher_supervisor=args.confirm_capture_watcher_supervisor,
                    max_supervisor_iterations=args.max_supervisor_iterations,
                    sleep_seconds=args.sleep_seconds,
                    allow_paper_watcher_restart=args.allow_paper_watcher_restart,
                    **({"sleep_fn": (lambda _seconds: None)} if args.run_supervisor_loop and args.sleep_seconds == 0 else {}),
                )
            )
        )
    elif args.command == "weekend-paper-fisherman-supervisor":
        from src.app.hammer_radar.operator.weekend_paper_fisherman_supervisor import (
            build_weekend_paper_fisherman_supervisor,
            format_weekend_paper_fisherman_supervisor_json,
        )

        print(
            format_weekend_paper_fisherman_supervisor_json(
                build_weekend_paper_fisherman_supervisor(
                    log_dir=args.log_dir,
                    record_supervisor=args.record_supervisor,
                    confirm_weekend_fisherman_supervisor=args.confirm_weekend_fisherman_supervisor,
                )
            )
        )
    elif args.command == "betrayal-integration-recheck":
        from src.app.hammer_radar.operator.betrayal_integration_recheck import (
            build_betrayal_integration_recheck,
            format_betrayal_integration_recheck_json,
        )

        print(
            format_betrayal_integration_recheck_json(
                build_betrayal_integration_recheck(
                    log_dir=args.log_dir,
                    record_recheck=args.record_recheck,
                    confirm_betrayal_integration_recheck=args.confirm_betrayal_integration_recheck,
                )
            )
        )
    elif args.command == "betrayal-true-inverse-refresh":
        from src.app.hammer_radar.operator.betrayal_true_inverse_refresh import (
            build_betrayal_true_inverse_refresh,
            format_betrayal_true_inverse_refresh_json,
        )

        print(
            format_betrayal_true_inverse_refresh_json(
                build_betrayal_true_inverse_refresh(
                    log_dir=args.log_dir,
                    record_refresh=args.record_refresh,
                    confirm_betrayal_true_inverse_refresh=args.confirm_betrayal_true_inverse_refresh,
                )
            )
        )
    elif args.command == "betrayal-paper-matrix-context":
        from src.app.hammer_radar.operator.betrayal_paper_matrix_context import (
            build_betrayal_paper_matrix_context,
            format_betrayal_paper_matrix_context_json,
        )

        print(
            format_betrayal_paper_matrix_context_json(
                build_betrayal_paper_matrix_context(
                    log_dir=args.log_dir,
                    record_matrix=args.record_matrix,
                    confirm_betrayal_paper_matrix_context=args.confirm_betrayal_paper_matrix_context,
                )
            )
        )
    elif args.command == "betrayal-event-tracker":
        from src.app.hammer_radar.operator.betrayal_event_tracker import (
            build_betrayal_event_tracker,
            format_betrayal_event_tracker_json,
        )

        print(
            format_betrayal_event_tracker_json(
                build_betrayal_event_tracker(
                    log_dir=args.log_dir,
                    record_tracker=args.record_tracker,
                    confirm_betrayal_event_tracker=args.confirm_betrayal_event_tracker,
                )
            )
        )
    elif args.command == "betrayal-regime-miro-recheck":
        from src.app.hammer_radar.operator.betrayal_regime_miro_recheck import (
            build_betrayal_regime_miro_recheck,
            format_betrayal_regime_miro_recheck_json,
        )

        print(
            format_betrayal_regime_miro_recheck_json(
                build_betrayal_regime_miro_recheck(
                    log_dir=args.log_dir,
                    record_recheck=args.record_recheck,
                    confirm_betrayal_regime_miro_recheck=args.confirm_betrayal_regime_miro_recheck,
                )
            )
        )
    elif args.command == "betrayal-direction-split-resolver":
        from src.app.hammer_radar.operator.betrayal_direction_split_resolver import (
            build_betrayal_direction_split_resolver,
            format_betrayal_direction_split_resolver_json,
        )

        print(
            format_betrayal_direction_split_resolver_json(
                build_betrayal_direction_split_resolver(
                    log_dir=args.log_dir,
                    record_resolver=args.record_resolver,
                    confirm_betrayal_direction_split_resolver=args.confirm_betrayal_direction_split_resolver,
                )
            )
        )
    elif args.command == "betrayal-source-emitter-refresh":
        from src.app.hammer_radar.operator.betrayal_source_emitter_refresh import (
            build_betrayal_source_emitter_refresh,
            format_betrayal_source_emitter_refresh_json,
        )

        print(
            format_betrayal_source_emitter_refresh_json(
                build_betrayal_source_emitter_refresh(
                    log_dir=args.log_dir,
                    record_refresh=args.record_refresh,
                    confirm_betrayal_source_emitter_refresh=args.confirm_betrayal_source_emitter_refresh,
                )
            )
        )
    elif args.command == "betrayal-aggregate-decomposition":
        from src.app.hammer_radar.operator.betrayal_aggregate_decomposition import (
            build_betrayal_aggregate_decomposition,
            format_betrayal_aggregate_decomposition_json,
        )

        print(
            format_betrayal_aggregate_decomposition_json(
                build_betrayal_aggregate_decomposition(
                    log_dir=args.log_dir,
                    record_decomposition=args.record_decomposition,
                    confirm_betrayal_aggregate_decomposition=args.confirm_betrayal_aggregate_decomposition,
                )
            )
        )
    elif args.command == "registry-wiring-betrayal-source-family":
        from src.app.hammer_radar.operator.registry_wiring_betrayal_source_family import (
            build_registry_wiring_betrayal_source_family,
            format_registry_wiring_betrayal_source_family_json,
        )

        print(
            format_registry_wiring_betrayal_source_family_json(
                build_registry_wiring_betrayal_source_family(
                    log_dir=args.log_dir,
                    record_wiring=args.record_wiring,
                    confirm_registry_wiring_betrayal_source_family=(
                        args.confirm_registry_wiring_betrayal_source_family
                    ),
                )
            )
        )
    elif args.command == "betrayal-registry-consumer-refactor":
        from src.app.hammer_radar.operator.betrayal_registry_consumer_refactor import (
            build_betrayal_registry_consumer_refactor,
            format_betrayal_registry_consumer_refactor_json,
        )

        print(
            format_betrayal_registry_consumer_refactor_json(
                build_betrayal_registry_consumer_refactor(
                    log_dir=args.log_dir,
                    record_refactor=args.record_refactor,
                    confirm_betrayal_registry_consumer_refactor=(
                        args.confirm_betrayal_registry_consumer_refactor
                    ),
                )
            )
        )
    elif args.command == "betrayal-source-identity-normalizer":
        from src.app.hammer_radar.operator.betrayal_source_identity_normalizer import (
            build_betrayal_source_identity_normalizer,
            format_betrayal_source_identity_normalizer_json,
        )

        print(
            format_betrayal_source_identity_normalizer_json(
                build_betrayal_source_identity_normalizer(
                    log_dir=args.log_dir,
                    record_normalizer=args.record_normalizer,
                    confirm_betrayal_source_identity_normalizer=(
                        args.confirm_betrayal_source_identity_normalizer
                    ),
                )
            )
        )
    elif args.command == "betrayal-source-identity-evidence-collector":
        from src.app.hammer_radar.operator.betrayal_source_identity_evidence_collector import (
            build_betrayal_source_identity_evidence_collector,
            format_betrayal_source_identity_evidence_collector_json,
        )

        print(
            format_betrayal_source_identity_evidence_collector_json(
                build_betrayal_source_identity_evidence_collector(
                    log_dir=args.log_dir,
                    record_collector=args.record_collector,
                    confirm_betrayal_source_identity_evidence_collector=(
                        args.confirm_betrayal_source_identity_evidence_collector
                    ),
                )
            )
        )
    elif args.command == "betrayal-entry-mode-evidence-wiring":
        from src.app.hammer_radar.operator.betrayal_entry_mode_evidence_wiring import (
            build_betrayal_entry_mode_evidence_wiring,
            format_betrayal_entry_mode_evidence_wiring_json,
        )

        print(
            format_betrayal_entry_mode_evidence_wiring_json(
                build_betrayal_entry_mode_evidence_wiring(
                    log_dir=args.log_dir,
                    record_wiring=args.record_wiring,
                    confirm_betrayal_entry_mode_evidence_wiring=(
                        args.confirm_betrayal_entry_mode_evidence_wiring
                    ),
                )
            )
        )
    elif args.command == "risk-contract-apply-packet-8m-short":
        from src.app.hammer_radar.operator.risk_contract_apply_packet_8m_short import (
            build_risk_contract_apply_packet_8m_short,
            format_risk_contract_apply_packet_8m_short_json,
        )

        print(
            format_risk_contract_apply_packet_8m_short_json(
                build_risk_contract_apply_packet_8m_short(
                    log_dir=args.log_dir,
                    lane_key=args.lane_key,
                    record_packet=args.record_packet,
                    confirm_risk_contract_apply_packet=args.confirm_risk_contract_apply_packet,
                )
            )
        )
    elif args.command == "env-role-split-proposal":
        from src.app.hammer_radar.operator.env_role_split_proposal import (
            build_env_role_split_proposal,
            format_env_role_split_proposal_json,
        )

        print(
            format_env_role_split_proposal_json(
                build_env_role_split_proposal(
                    log_dir=args.log_dir,
                    record_proposal=args.record_proposal,
                    confirm_env_role_split_proposal=args.confirm_env_role_split_proposal,
                )
            )
        )
    elif args.command == "env-role-adapter-preview":
        from src.app.hammer_radar.operator.env_role_adapter_preview import (
            build_env_role_adapter_preview,
            format_env_role_adapter_preview_json,
        )

        print(
            format_env_role_adapter_preview_json(
                build_env_role_adapter_preview(
                    log_dir=args.log_dir,
                    record_preview=args.record_preview,
                    confirm_env_role_adapter_preview=args.confirm_env_role_adapter_preview,
                )
            )
        )
    elif args.command == "account-read-env-migration-packet":
        from src.app.hammer_radar.operator.account_read_env_migration_packet import (
            build_account_read_env_migration_packet,
            format_account_read_env_migration_packet_json,
        )

        print(
            format_account_read_env_migration_packet_json(
                build_account_read_env_migration_packet(
                    log_dir=args.log_dir,
                    record_packet=args.record_packet,
                    confirm_account_read_env_migration=args.confirm_account_read_env_migration,
                )
            )
        )
    elif args.command == "account-read-env-migration-verify":
        from src.app.hammer_radar.operator.account_read_env_migration_verify import (
            build_account_read_env_migration_verify,
            format_account_read_env_migration_verify_json,
        )

        print(
            format_account_read_env_migration_verify_json(
                build_account_read_env_migration_verify(
                    log_dir=args.log_dir,
                    record_verify=args.record_verify,
                    confirm_account_read_env_migration_verify=args.confirm_account_read_env_migration_verify,
                )
            )
        )
    elif args.command == "betrayal-true-paper-scaffold":
        from src.app.hammer_radar.operator.betrayal_true_paper_tracking import (
            build_betrayal_true_paper_scaffold,
            format_betrayal_true_paper_scaffold_text,
        )

        print(
            format_betrayal_true_paper_scaffold_text(
                build_betrayal_true_paper_scaffold(
                    symbol=args.symbol,
                    max_candidates=args.max_candidates,
                    dry_run=not args.write,
                    write=args.write,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "betrayal-paper-outcomes":
        from src.app.hammer_radar.operator.betrayal_paper_outcome_ledger import (
            build_betrayal_paper_outcome_status,
            format_betrayal_paper_outcome_status_text,
            record_betrayal_paper_outcome,
        )

        if args.write:
            outcome = None
            if args.outcome_json:
                with Path(args.outcome_json).open("r", encoding="utf-8") as handle:
                    outcome = json.load(handle)
            result = record_betrayal_paper_outcome(
                outcome=outcome,
                dry_run=False,
                write=True,
                log_dir=args.log_dir,
            )
            print(format_betrayal_paper_outcome_status_text(build_betrayal_paper_outcome_status(log_dir=args.log_dir)))
            print(f"record_status: {result.get('record_status')} outcome_written: {result.get('outcome_written')}")
            if result.get("validation_errors"):
                print(f"validation_errors: {result.get('validation_errors')}")
        else:
            print(
                format_betrayal_paper_outcome_status_text(
                    build_betrayal_paper_outcome_status(
                        signal_id=args.signal_id,
                        recent=args.recent,
                        log_dir=args.log_dir,
                    )
                )
            )
    elif args.command == "betrayal-paper-signal-detector":
        from src.app.hammer_radar.operator.betrayal_paper_signal_detector import (
            format_betrayal_paper_signal_detector_text,
            run_betrayal_paper_signal_detector,
        )

        print(
            format_betrayal_paper_signal_detector_text(
                run_betrayal_paper_signal_detector(
                    dry_run=not args.write,
                    write=args.write,
                    max_signals=args.max_signals,
                    identity_filter=args.identity_filter,
                    allow_open_tracking=args.allow_open_tracking,
                    allow_closed_outcomes=args.allow_closed_outcomes,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "betrayal-detector-source-wiring":
        from src.app.hammer_radar.operator.betrayal_detector_source_wiring import (
            build_betrayal_detector_source_wiring,
            format_betrayal_detector_source_wiring_text,
        )

        print(
            format_betrayal_detector_source_wiring_text(
                build_betrayal_detector_source_wiring(
                    symbol=args.symbol,
                    timeframe=args.timeframe,
                    dry_run=not args.write,
                    write=args.write,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "betrayal-source-signal-emitter":
        from src.app.hammer_radar.operator.betrayal_source_signal_emitter import (
            format_betrayal_source_signal_emitter_text,
            run_betrayal_source_signal_emitter,
        )

        print(
            format_betrayal_source_signal_emitter_text(
                run_betrayal_source_signal_emitter(
                    dry_run=not args.write,
                    write=args.write,
                    max_signals=args.max_signals,
                    identity_filter=args.identity_filter,
                    allow_historical_replay=args.allow_historical_replay,
                    allow_fresh_current=args.allow_fresh_current,
                    log_dir=args.log_dir,
                )
            )
        )
    elif args.command == "decisions":
        from src.app.hammer_radar.operator.approval_api import build_decisions_text

        print(build_decisions_text(limit=args.limit, signal_id=args.signal_id, log_dir=args.log_dir))
    elif args.command == "log-manual-outcome":
        from src.app.hammer_radar.operator.manual_outcomes import append_manual_outcome

        record = append_manual_outcome(
            signal_id=args.signal_id,
            result=args.result,
            entry_price=args.entry_price,
            exit_price=args.exit_price,
            position_usd=args.position_usd,
            leverage=args.leverage,
            pnl_usd=args.pnl_usd,
            pnl_pct=args.pnl_pct,
            notes=args.notes,
            log_dir=args.log_dir,
        )
        print("HAMMER RADAR MANUAL OUTCOME LOGGED")
        print(f"outcome_id: {record['outcome_id']}")
        print(f"signal_id: {record['signal_id']}")
        print(f"result: {record['result']}")
        print("live_execution_enabled: false")
        print("order_placed: false")
    elif args.command == "manual-outcomes":
        from src.app.hammer_radar.operator.manual_outcomes import build_manual_outcomes_text

        print(build_manual_outcomes_text(limit=args.limit, signal_id=args.signal_id, log_dir=args.log_dir))
    elif args.command == "readiness":
        from src.app.hammer_radar.operator.readiness import build_readiness_text

        print(build_readiness_text(log_dir=args.log_dir))
    elif args.command == "trade-ticket":
        from src.app.hammer_radar.operator.trade_ticket import build_trade_ticket_text

        print(build_trade_ticket_text(log_dir=args.log_dir))
    elif args.command == "trade-tickets":
        from src.app.hammer_radar.operator.trade_ticket import build_trade_tickets_text

        print(build_trade_tickets_text(limit=args.limit, ticket_id=args.ticket_id, log_dir=args.log_dir))
    elif args.command == "execute-paper-ticket":
        from src.app.hammer_radar.operator.paper_execution import build_execute_paper_ticket_text

        print(
            build_execute_paper_ticket_text(
                ticket_id=args.ticket_id,
                operator=args.operator,
                notes=args.notes,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "paper-executions":
        from src.app.hammer_radar.operator.paper_execution import build_paper_executions_text

        print(
            build_paper_executions_text(
                limit=args.limit,
                signal_id=args.signal_id,
                status=args.status,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "exchange-dry-run":
        from src.app.hammer_radar.operator.exchange_dry_run import build_exchange_dry_run_text

        print(
            build_exchange_dry_run_text(
                signal_id=args.signal_id,
                allow_short=args.allow_short,
                max_position_usd=args.max_position_usd,
                max_leverage=args.max_leverage,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "live-safety":
        from src.app.hammer_radar.operator.live_safety import build_live_safety_text

        print(build_live_safety_text(log_dir=args.log_dir))
    elif args.command == "live-connector-submit":
        from src.app.hammer_radar.operator.live_connector_stub import build_live_connector_submit_text

        print(
            build_live_connector_submit_text(
                ticket_id=args.ticket_id,
                operator=args.operator,
                notes=args.notes,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "live-attempts":
        from src.app.hammer_radar.operator.live_connector_stub import build_live_attempts_text

        print(
            build_live_attempts_text(
                limit=args.limit,
                signal_id=args.signal_id,
                ticket_id=args.ticket_id,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "binance-readonly-status":
        from src.app.hammer_radar.operator.binance_readonly import build_binance_readonly_status_text

        print(build_binance_readonly_status_text())
    elif args.command == "notification-status":
        from src.app.hammer_radar.operator.notification_watcher import build_notification_status_text

        print(build_notification_status_text(log_dir=args.log_dir))
    elif args.command == "notification-check":
        from src.app.hammer_radar.operator.notification_watcher import build_notification_check_text

        print(build_notification_check_text(send=args.send, channel=args.channel, log_dir=args.log_dir))
    elif args.command == "readiness-alerts":
        from src.app.hammer_radar.operator.notification_watcher import build_readiness_alerts_text

        print(build_readiness_alerts_text(limit=args.limit, log_dir=args.log_dir))
    elif args.command == "watchlist":
        from src.app.hammer_radar.operator.alt_watchlist import build_watchlist_text

        print(build_watchlist_text(category=args.category, limit=args.limit, log_dir=args.log_dir))
    elif args.command == "watchlist-summary":
        from src.app.hammer_radar.operator.alt_watchlist import build_watchlist_summary_text

        print(build_watchlist_summary_text(log_dir=args.log_dir))
    elif args.command == "multi-symbol-scan":
        from src.app.hammer_radar.operator.multi_symbol_scanner import build_multi_symbol_scan_text

        print(
            build_multi_symbol_scan_text(
                symbol=args.symbol,
                category=args.category,
                limit=args.limit,
                write=args.write,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "multi-symbol-scans":
        from src.app.hammer_radar.operator.multi_symbol_scanner import build_multi_symbol_scans_text

        print(
            build_multi_symbol_scans_text(
                limit=args.limit,
                symbol=args.symbol,
                category=args.category,
                status=args.status,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "multi-symbol-summary":
        from src.app.hammer_radar.operator.multi_symbol_scanner import build_multi_symbol_summary_text

        print(build_multi_symbol_summary_text(log_dir=args.log_dir))
    elif args.command == "market-intelligence-summary":
        from src.app.hammer_radar.operator.market_intelligence import build_market_intelligence_summary_text

        print(
            build_market_intelligence_summary_text(
                use_network=args.use_network,
                write=args.write,
                limit=args.limit,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "market-intelligence-rankings":
        from src.app.hammer_radar.operator.market_intelligence import build_market_rankings_text

        print(
            build_market_rankings_text(
                use_network=args.use_network,
                category=args.category,
                limit=args.limit,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "ethbtc-rotation":
        from src.app.hammer_radar.operator.market_intelligence import build_ethbtc_rotation_text

        print(build_ethbtc_rotation_text(use_network=args.use_network, log_dir=args.log_dir))
    elif args.command == "market-intelligence-snapshots":
        from src.app.hammer_radar.operator.market_intelligence import build_market_snapshots_text

        print(build_market_snapshots_text(limit=args.limit, log_dir=args.log_dir))
    elif args.command == "eth-paper-candidate":
        from src.app.hammer_radar.operator.eth_paper_candidates import build_eth_paper_candidate_text

        print(build_eth_paper_candidate_text(use_network=args.use_network, write=args.write, log_dir=args.log_dir))
    elif args.command == "eth-paper-candidates":
        from src.app.hammer_radar.operator.eth_paper_candidates import build_eth_candidates_text

        print(build_eth_candidates_text(limit=args.limit, status=args.status, log_dir=args.log_dir))
    elif args.command == "eth-paper-summary":
        from src.app.hammer_radar.operator.eth_paper_candidates import build_eth_paper_summary_text

        print(build_eth_paper_summary_text(log_dir=args.log_dir))
    elif args.command == "eth-paper-outcome":
        from src.app.hammer_radar.operator.eth_paper_outcomes import build_eth_paper_outcome_text

        print(build_eth_paper_outcome_text(candidate_id=args.candidate_id, write=args.write, log_dir=args.log_dir))
    elif args.command == "eth-paper-outcomes":
        from src.app.hammer_radar.operator.eth_paper_outcomes import build_eth_paper_outcomes_text

        print(
            build_eth_paper_outcomes_text(
                limit=args.limit,
                status=args.status,
                candidate_id=args.candidate_id,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "eth-paper-outcome-summary":
        from src.app.hammer_radar.operator.eth_paper_outcomes import build_eth_paper_outcome_summary_text

        print(build_eth_paper_outcome_summary_text(log_dir=args.log_dir))
    elif args.command == "paper-refresh-status":
        from src.app.hammer_radar.operator.paper_refresh_scheduler import build_refresh_status_text

        print(build_refresh_status_text(log_dir=args.log_dir))
    elif args.command == "paper-refresh-run":
        from src.app.hammer_radar.operator.paper_refresh_scheduler import build_refresh_run_text

        print(
            build_refresh_run_text(
                tasks=args.tasks,
                use_network=args.use_network,
                write_outputs=not args.no_write,
                send_notifications=args.send_notifications,
                log_dir=args.log_dir,
            )
        )
    elif args.command == "paper-refresh-runs":
        from src.app.hammer_radar.operator.paper_refresh_scheduler import build_refresh_runs_text

        print(build_refresh_runs_text(limit=args.limit, log_dir=args.log_dir))
    else:
        parser.error(f"unsupported command: {args.command}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.inspect")
    parser.add_argument("--log-dir", default=None, help="Read Hammer Radar NDJSON files from this directory.")
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--log-dir",
        default=argparse.SUPPRESS,
        help="Read Hammer Radar NDJSON files from this directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("summary", parents=[parent])

    signals_parser = subparsers.add_parser("signals", parents=[parent])
    signals_parser.add_argument("--limit", type=int, default=10)

    outcomes_parser = subparsers.add_parser("outcomes", parents=[parent])
    outcomes_parser.add_argument("--limit", type=int, default=10)

    positions_parser = subparsers.add_parser("positions", parents=[parent])
    positions_parser.add_argument("--status", choices=("open", "closed", "all"), default="all")

    events_parser = subparsers.add_parser("events", parents=[parent])
    events_parser.add_argument("--limit", type=int, default=20)

    subparsers.add_parser("r9-coverage", parents=[parent])

    daily_parser = subparsers.add_parser("daily-report", parents=[parent])
    daily_parser.add_argument("--limit", type=int, default=10)
    daily_parser.add_argument("--since-hours", type=int, default=24)
    daily_parser.add_argument("--tradable-only", action="store_true")
    daily_parser.add_argument("--symbol", default=None)

    live_parser = subparsers.add_parser("live-checklist", parents=[parent])
    live_parser.add_argument("--limit", type=int, default=10)
    live_parser.add_argument("--since-hours", type=int, default=24)
    live_parser.add_argument("--min-score", type=int, default=90)
    live_parser.add_argument("--symbol", default=None)
    live_parser.add_argument("--allow-short", action="store_true")
    live_parser.add_argument("--allow-oversold", action="store_true")
    live_parser.add_argument("--allow-trigger-flags", action="store_true")
    live_parser.add_argument("--max-risk-usd", type=float, default=5.0)
    live_parser.add_argument("--max-leverage", type=float, default=3.0)
    live_parser.add_argument("--max-position-usd", type=float, default=44.0)
    live_parser.add_argument("--fresh-minutes", type=int, default=30)
    live_parser.add_argument("--allow-expired", action="store_true")
    live_parser.add_argument("--latest-only", action="store_true")

    betrayal_parser = subparsers.add_parser("betrayal-report", parents=[parent])
    betrayal_parser.add_argument("--limit", type=int, default=20)
    betrayal_parser.add_argument("--since-hours", type=int, default=24)
    betrayal_parser.add_argument("--symbol", default=None)
    betrayal_parser.add_argument("--min-betrayal-score", type=int, default=50)
    betrayal_parser.add_argument("--latest-only", action="store_true")

    betrayal_shadow_track_parser = subparsers.add_parser("betrayal-shadow-track", parents=[parent])
    betrayal_shadow_track_parser.add_argument("--latest-only", action="store_true")
    betrayal_shadow_track_parser.add_argument("--limit", type=int, default=20)
    betrayal_shadow_track_parser.add_argument("--since-hours", type=int, default=24)
    betrayal_shadow_track_parser.add_argument("--symbol", default=None)
    betrayal_shadow_track_parser.add_argument("--min-betrayal-score", type=int, default=50)

    betrayal_shadow_outcomes_parser = subparsers.add_parser("betrayal-shadow-outcomes", parents=[parent])
    betrayal_shadow_outcomes_parser.add_argument("--limit", type=int, default=50)
    betrayal_shadow_outcomes_parser.add_argument("--symbol", default=None)
    betrayal_shadow_outcomes_parser.add_argument("--status", default=None)

    betrayal_shadow_resolve_parser = subparsers.add_parser("betrayal-shadow-resolve", parents=[parent])
    betrayal_shadow_resolve_parser.add_argument("--limit", type=int, default=0)
    betrayal_shadow_resolve_parser.add_argument("--symbol", default=None)
    betrayal_shadow_resolve_parser.add_argument("--timeframe", default=None)
    betrayal_shadow_resolve_parser.add_argument("--since-hours", type=int, default=None)
    betrayal_shadow_resolve_parser.add_argument("--write", action="store_true")

    betrayal_candle_archive_parser = subparsers.add_parser("betrayal-candle-archive", parents=[parent])
    betrayal_candle_archive_parser.add_argument("--symbol", default=None)
    betrayal_candle_archive_parser.add_argument("--timeframe", default=None)
    betrayal_candle_archive_parser.add_argument("--limit", type=int, default=0)
    betrayal_candle_archive_parser.add_argument("--since-hours", type=int, default=None)
    betrayal_candle_archive_parser.add_argument("--write", action="store_true")

    betrayal_candle_capture_parser = subparsers.add_parser("betrayal-candle-capture", parents=[parent])
    betrayal_candle_capture_parser.add_argument("--symbol", default=None)
    betrayal_candle_capture_parser.add_argument("--timeframe", default=None)
    betrayal_candle_capture_parser.add_argument("--limit", type=int, default=0)
    betrayal_candle_capture_parser.add_argument("--since-hours", type=int, default=None)
    betrayal_candle_capture_parser.add_argument("--write", action="store_true")
    betrayal_candle_capture_parser.add_argument("--source-mode", default="LOCAL_ONLY")

    subparsers.add_parser("betrayal-strategy-audit", parents=[parent])
    subparsers.add_parser("betrayal-inverse-validation", parents=[parent])

    markov_regime_gate_parser = subparsers.add_parser("markov-regime-gate", parents=[parent])
    markov_regime_gate_parser.add_argument("--symbol", default="BTCUSDT")
    markov_regime_gate_parser.add_argument("--timeframe", default=None)
    markov_regime_gate_parser.add_argument("--limit", type=int, default=120)

    miro_fish_quality_gate_parser = subparsers.add_parser("miro-fish-quality-gate", parents=[parent])
    miro_fish_quality_gate_parser.add_argument("--symbol", default="BTCUSDT")
    miro_fish_quality_gate_parser.add_argument("--timeframe", default=None)
    miro_fish_quality_gate_parser.add_argument("--family", default=None)
    miro_fish_quality_gate_parser.add_argument("--limit", type=int, default=120)

    live_arming_preflight_parser = subparsers.add_parser("live-arming-preflight", parents=[parent])
    live_arming_preflight_parser.add_argument("--symbol", default="BTCUSDT")
    live_arming_preflight_parser.add_argument("--timeframe", default=None)
    live_arming_preflight_parser.add_argument("--candidate-id", default=None)

    tiny_live_risk_contract_parser = subparsers.add_parser("tiny-live-risk-contract", parents=[parent])
    tiny_live_risk_contract_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )

    tiny_live_ticket_parser = subparsers.add_parser("tiny-live-ticket", parents=[parent])
    tiny_live_ticket_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    tiny_live_ticket_parser.add_argument("--write", action="store_true")
    tiny_live_ticket_parser.add_argument("--approval-phrase", default=None)
    tiny_live_ticket_parser.add_argument("--operator-note", default=None)

    live_env_checklist_parser = subparsers.add_parser("live-env-checklist", parents=[parent])
    live_env_checklist_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    live_env_checklist_parser.add_argument("--write", action="store_true")
    live_env_checklist_parser.add_argument("--manual-funding-phrase", default=None)
    live_env_checklist_parser.add_argument("--live-env-review-phrase", default=None)
    live_env_checklist_parser.add_argument("--max-loss-ack-phrase", default=None)
    live_env_checklist_parser.add_argument("--exact-candidate-ack-phrase", default=None)
    live_env_checklist_parser.add_argument("--operator-note", default=None)

    live_env_boundary_review_parser = subparsers.add_parser("live-env-boundary-review", parents=[parent])
    live_env_boundary_review_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    live_env_boundary_review_parser.add_argument("--write", action="store_true")

    final_review_packet_parser = subparsers.add_parser("final-review-packet", parents=[parent])
    final_review_packet_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    final_review_packet_parser.add_argument("--write", action="store_true")
    final_review_packet_parser.add_argument("--final-approval-phrase", default=None)
    final_review_packet_parser.add_argument("--operator-note", default=None)

    human_confirmations_parser = subparsers.add_parser("human-confirmations", parents=[parent])
    human_confirmations_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    human_confirmations_parser.add_argument("--write", action="store_true")
    human_confirmations_parser.add_argument("--r85-approval-phrase", default=None)
    human_confirmations_parser.add_argument("--r86-manual-funding-phrase", default=None)
    human_confirmations_parser.add_argument("--r86-live-env-review-phrase", default=None)
    human_confirmations_parser.add_argument("--r86-max-loss-ack-phrase", default=None)
    human_confirmations_parser.add_argument("--r86-exact-candidate-ack-phrase", default=None)
    human_confirmations_parser.add_argument("--r88-final-approval-phrase", default=None)
    human_confirmations_parser.add_argument("--operator-note", default=None)

    readiness_snapshot_parser = subparsers.add_parser("readiness-snapshot", parents=[parent])
    readiness_snapshot_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    readiness_snapshot_parser.add_argument("--write", action="store_true")

    final_live_preflight_parser = subparsers.add_parser("final-live-preflight", parents=[parent])
    final_live_preflight_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )

    tiny_live_armed_dry_run_parser = subparsers.add_parser("tiny-live-armed-dry-run", parents=[parent])
    tiny_live_armed_dry_run_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    tiny_live_armed_dry_run_parser.add_argument("--no-record", action="store_true")

    one_tiny_live_order_protocol_parser = subparsers.add_parser("one-tiny-live-order-protocol", parents=[parent])
    one_tiny_live_order_protocol_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    one_tiny_live_order_protocol_parser.add_argument("--no-record", action="store_true")

    first_live_activation_gate_parser = subparsers.add_parser("first-live-activation-gate", parents=[parent])
    first_live_activation_gate_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    first_live_activation_gate_parser.add_argument("--no-record", action="store_true")

    first_live_burn_down_parser = subparsers.add_parser("first-live-burn-down", parents=[parent])
    first_live_burn_down_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    first_live_burn_down_parser.add_argument("--no-record", action="store_true")

    first_live_prerequisite_clearing_parser = subparsers.add_parser("first-live-prerequisite-clearing", parents=[parent])
    first_live_prerequisite_clearing_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    first_live_prerequisite_clearing_parser.add_argument("--no-record", action="store_true")

    first_live_evidence_parser = subparsers.add_parser("record-first-live-evidence", parents=[parent])
    first_live_evidence_parser.add_argument("--evidence-type", default=None)
    first_live_evidence_parser.add_argument("--candidate-id", default=None)
    first_live_evidence_parser.add_argument("--risk-contract-hash", default=None)
    first_live_evidence_parser.add_argument("--packet-hash", default=None)
    first_live_evidence_parser.add_argument("--note", default=None)

    subparsers.add_parser("first-live-evidence-status", parents=[parent])

    first_live_recheck_parser = subparsers.add_parser("first-live-prerequisite-recheck-after-evidence", parents=[parent])
    first_live_recheck_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    first_live_recheck_parser.add_argument("--no-record", action="store_true")

    first_live_guided_actions_parser = subparsers.add_parser("first-live-evidence-guided-actions", parents=[parent])
    first_live_guided_actions_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    first_live_guided_actions_parser.add_argument("--no-record", action="store_true")

    first_live_evidence_runbook_parser = subparsers.add_parser("first-live-evidence-runbook", parents=[parent])
    first_live_evidence_runbook_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    first_live_evidence_runbook_parser.add_argument("--no-record", action="store_true")

    first_live_evidence_assisted_run_parser = subparsers.add_parser("first-live-evidence-assisted-run", parents=[parent])
    first_live_evidence_assisted_run_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    first_live_evidence_assisted_run_parser.add_argument("--group", default=None)
    first_live_evidence_assisted_run_parser.add_argument("--all-groups", action="store_true")
    first_live_evidence_assisted_run_parser.add_argument("--execute-evidence", action="store_true")
    first_live_evidence_assisted_run_parser.add_argument("--confirm-evidence-only", default=None)

    first_live_post_evidence_recheck_parser = subparsers.add_parser("first-live-post-evidence-gate-recheck", parents=[parent])
    first_live_post_evidence_recheck_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    first_live_post_evidence_recheck_parser.add_argument("--no-record", action="store_true")

    first_live_activation_final_review_parser = subparsers.add_parser("first-live-activation-final-review", parents=[parent])
    first_live_activation_final_review_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    first_live_activation_final_review_parser.add_argument("--no-record", action="store_true")

    first_live_blocker_clearing_workbench_parser = subparsers.add_parser("first-live-blocker-clearing-workbench", parents=[parent])
    first_live_blocker_clearing_workbench_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    first_live_blocker_clearing_workbench_parser.add_argument("--no-record", action="store_true")

    first_live_targeted_clearing_pack_parser = subparsers.add_parser("first-live-targeted-clearing-pack", parents=[parent])
    first_live_targeted_clearing_pack_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    first_live_targeted_clearing_pack_parser.add_argument("--lane", default=None)
    first_live_targeted_clearing_pack_parser.add_argument("--all-evidence-lanes", action="store_true")
    first_live_targeted_clearing_pack_parser.add_argument("--authorization-check", action="store_true")
    first_live_targeted_clearing_pack_parser.add_argument("--no-record", action="store_true")

    source_warning_review_parser = subparsers.add_parser("source-warning-review", parents=[parent])
    source_warning_review_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    source_warning_review_parser.add_argument("--write", action="store_true")

    source_chain_repair_parser = subparsers.add_parser("source-chain-repair", parents=[parent])
    source_chain_repair_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    source_chain_repair_parser.add_argument("--write", action="store_true")

    candidate_revalidation_watch_parser = subparsers.add_parser("candidate-revalidation-watch", parents=[parent])
    candidate_revalidation_watch_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    candidate_revalidation_watch_parser.add_argument("--write", action="store_true")

    dual_lane_candidate_watch_parser = subparsers.add_parser("dual-lane-candidate-watch", parents=[parent])
    dual_lane_candidate_watch_parser.add_argument(
        "--candidate-id",
        default="normal|BTCUSDT|13m|long|ladder_close_50_618",
    )
    dual_lane_candidate_watch_parser.add_argument("--write", action="store_true")

    lane_control_status_parser = subparsers.add_parser("lane-control-status", parents=[parent])
    lane_control_status_parser.add_argument("--deep-global-gate-review", action="store_true")
    lane_control_cockpit_parser = subparsers.add_parser("lane-control-cockpit-state", parents=[parent])
    lane_control_cockpit_parser.add_argument("--lane-key", default="BTCUSDT|13m|long|ladder_close_50_618")
    subparsers.add_parser("fresh-signal-router-status", parents=[parent])
    lane_control_command_parser = subparsers.add_parser("lane-control-command", parents=[parent])
    lane_control_command_parser.add_argument("--action", required=True)
    lane_control_command_parser.add_argument("--lane-key", default=None)
    lane_control_command_parser.add_argument("--mode", default=None)
    lane_control_command_parser.add_argument("--apply", action="store_true")
    lane_control_command_parser.add_argument("--confirm-lane-change", default=None)
    lane_control_command_parser.add_argument("--request-tiny-live", action="store_true")

    autonomous_paper_lane_execution_parser = subparsers.add_parser("autonomous-paper-lane-execution", parents=[parent])
    autonomous_paper_lane_execution_parser.add_argument("--execute-paper", action="store_true")
    autonomous_paper_lane_execution_parser.add_argument("--lane-key", default=None)
    autonomous_paper_lane_execution_parser.add_argument("--all-lanes", action="store_true")
    autonomous_paper_lane_execution_parser.add_argument("--confirm-paper-only", default=None)

    first_tiny_live_lane_execution_gate_parser = subparsers.add_parser("first-tiny-live-lane-execution-gate", parents=[parent])
    first_tiny_live_lane_execution_gate_parser.add_argument("--lane-key", default=None)
    first_tiny_live_lane_execution_gate_parser.add_argument("--candidate-id", default=None)
    first_tiny_live_lane_execution_gate_parser.add_argument("--confirm-review-only", default=None)

    lane_autonomy_control_loop_parser = subparsers.add_parser("lane-autonomy-control-loop", parents=[parent])
    lane_autonomy_control_loop_parser.add_argument("--record-decision", action="store_true")
    lane_autonomy_control_loop_parser.add_argument("--lane-key", default=None)
    lane_autonomy_control_loop_parser.add_argument("--all-lanes", action="store_true")
    lane_autonomy_control_loop_parser.add_argument("--confirm-decision-record", default=None)

    lane_autonomy_scheduler_parser = subparsers.add_parser("lane-autonomy-scheduler", parents=[parent])
    lane_autonomy_scheduler_parser.add_argument("--once", action="store_true")
    lane_autonomy_scheduler_parser.add_argument("--record-tick", action="store_true")
    lane_autonomy_scheduler_parser.add_argument("--record-decisions", action="store_true")
    lane_autonomy_scheduler_parser.add_argument("--lane-key", default=None)
    lane_autonomy_scheduler_parser.add_argument("--all-lanes", action="store_true")
    lane_autonomy_scheduler_parser.add_argument("--confirm-scheduler-record", default=None)

    autonomous_paper_lane_executor_integration_parser = subparsers.add_parser(
        "autonomous-paper-lane-executor-integration",
        parents=[parent],
    )
    autonomous_paper_lane_executor_integration_parser.add_argument("--record-paper", action="store_true")
    autonomous_paper_lane_executor_integration_parser.add_argument("--record-scheduler-tick", action="store_true")
    autonomous_paper_lane_executor_integration_parser.add_argument("--record-decisions", action="store_true")
    autonomous_paper_lane_executor_integration_parser.add_argument("--lane-key", default=None)
    autonomous_paper_lane_executor_integration_parser.add_argument("--all-lanes", action="store_true")
    autonomous_paper_lane_executor_integration_parser.add_argument("--confirm-paper-integration", default=None)

    first_tiny_live_autonomous_lane_authorization_parser = subparsers.add_parser(
        "first-tiny-live-autonomous-lane-authorization",
        parents=[parent],
    )
    first_tiny_live_autonomous_lane_authorization_parser.add_argument("--lane-key", required=True)
    first_tiny_live_autonomous_lane_authorization_parser.add_argument("--record-authorization", action="store_true")
    first_tiny_live_autonomous_lane_authorization_parser.add_argument("--request-lane-mode-tiny-live", action="store_true")
    first_tiny_live_autonomous_lane_authorization_parser.add_argument("--apply-lane-mode-change", action="store_true")
    first_tiny_live_autonomous_lane_authorization_parser.add_argument("--confirm-tiny-live-authorization", default=None)

    live_lane_kill_switch_rehearsal_parser = subparsers.add_parser("live-lane-kill-switch-rehearsal", parents=[parent])
    live_lane_kill_switch_rehearsal_parser.add_argument("--lane-key", default="BTCUSDT|13m|long|ladder_close_50_618")
    live_lane_kill_switch_rehearsal_parser.add_argument("--record-rehearsal", action="store_true")
    live_lane_kill_switch_rehearsal_parser.add_argument("--confirm-rehearsal-record", default=None)

    live_adapter_boundary_review_parser = subparsers.add_parser("live-adapter-boundary-final-review", parents=[parent])
    live_adapter_boundary_review_parser.add_argument("--lane-key", default="BTCUSDT|13m|long|ladder_close_50_618")
    live_adapter_boundary_review_parser.add_argument("--record-review", action="store_true")
    live_adapter_boundary_review_parser.add_argument("--confirm-boundary-review", default=None)

    first_tiny_live_order_payload_dry_authorization_parser = subparsers.add_parser(
        "first-tiny-live-order-payload-dry-authorization",
        parents=[parent],
    )
    first_tiny_live_order_payload_dry_authorization_parser.add_argument(
        "--lane-key",
        default="BTCUSDT|13m|long|ladder_close_50_618",
    )
    first_tiny_live_order_payload_dry_authorization_parser.add_argument(
        "--record-dry-authorization",
        action="store_true",
    )
    first_tiny_live_order_payload_dry_authorization_parser.add_argument("--confirm-dry-authorization", default=None)

    live_adapter_execution_rehearsal_parser = subparsers.add_parser(
        "live-adapter-execution-rehearsal",
        parents=[parent],
    )
    live_adapter_execution_rehearsal_parser.add_argument(
        "--lane-key",
        default="BTCUSDT|13m|long|ladder_close_50_618",
    )
    live_adapter_execution_rehearsal_parser.add_argument("--record-rehearsal", action="store_true")
    live_adapter_execution_rehearsal_parser.add_argument("--confirm-adapter-rehearsal", default=None)

    protective_order_dry_policy_review_parser = subparsers.add_parser(
        "protective-order-dry-policy-review",
        parents=[parent],
    )
    protective_order_dry_policy_review_parser.add_argument(
        "--lane-key",
        default="BTCUSDT|13m|long|ladder_close_50_618",
    )
    protective_order_dry_policy_review_parser.add_argument("--record-review", action="store_true")
    protective_order_dry_policy_review_parser.add_argument("--confirm-protective-review", default=None)

    protective_payload_dry_preview_boundary_parser = subparsers.add_parser(
        "protective-payload-dry-preview-boundary",
        parents=[parent],
    )
    protective_payload_dry_preview_boundary_parser.add_argument(
        "--lane-key",
        default="BTCUSDT|13m|long|ladder_close_50_618",
    )
    protective_payload_dry_preview_boundary_parser.add_argument("--record-preview", action="store_true")
    protective_payload_dry_preview_boundary_parser.add_argument("--confirm-protective-preview", default=None)

    autonomous_lane_live_ready_burn_down_parser = subparsers.add_parser(
        "autonomous-lane-live-ready-burn-down",
        parents=[parent],
    )
    autonomous_lane_live_ready_burn_down_parser.add_argument(
        "--lane-key",
        default="BTCUSDT|13m|long|ladder_close_50_618",
    )
    autonomous_lane_live_ready_burn_down_parser.add_argument("--record-burn-down", action="store_true")
    autonomous_lane_live_ready_burn_down_parser.add_argument("--confirm-burn-down", default=None)

    burn_down_command_pack_sanity_parser = subparsers.add_parser(
        "burn-down-command-pack-sanity",
        parents=[parent],
    )
    burn_down_command_pack_sanity_parser.add_argument(
        "--lane-key",
        default="BTCUSDT|13m|long|ladder_close_50_618",
    )

    live_ready_blocker_clearing_operator_pack_parser = subparsers.add_parser(
        "live-ready-blocker-clearing-operator-pack",
        parents=[parent],
    )
    live_ready_blocker_clearing_operator_pack_parser.add_argument(
        "--lane-key",
        default="BTCUSDT|13m|long|ladder_close_50_618",
    )
    live_ready_blocker_clearing_operator_pack_parser.add_argument("--record-pack", action="store_true")
    live_ready_blocker_clearing_operator_pack_parser.add_argument("--confirm-operator-pack", default=None)

    operator_executes_safe_clearing_pack_parser = subparsers.add_parser(
        "operator-executes-safe-clearing-pack",
        parents=[parent],
    )
    operator_executes_safe_clearing_pack_parser.add_argument(
        "--lane-key",
        default="BTCUSDT|13m|long|ladder_close_50_618",
    )
    operator_executes_safe_clearing_pack_parser.add_argument("--execute-safe-clearing", action="store_true")
    operator_executes_safe_clearing_pack_parser.add_argument("--confirm-safe-clearing", default=None)

    post_clearing_live_ready_recheck_parser = subparsers.add_parser(
        "post-clearing-live-ready-recheck",
        parents=[parent],
    )
    post_clearing_live_ready_recheck_parser.add_argument(
        "--lane-key",
        default="BTCUSDT|13m|long|ladder_close_50_618",
    )
    post_clearing_live_ready_recheck_parser.add_argument("--record-recheck", action="store_true")
    post_clearing_live_ready_recheck_parser.add_argument("--confirm-post-clearing-recheck", default=None)

    fresh_candidate_watch_parser = subparsers.add_parser(
        "fresh-candidate-paper-proof-capture-loop",
        parents=[parent],
    )
    fresh_candidate_watch_parser.add_argument("--lane-key", action="append", default=None)
    fresh_candidate_watch_parser.add_argument("--lane-keys", default=None)
    fresh_candidate_watch_parser.add_argument("--watch-all-recommended-lanes", action="store_true")
    fresh_candidate_watch_parser.add_argument("--max-iterations", type=int, default=5)
    fresh_candidate_watch_parser.add_argument("--sleep-seconds", type=int, default=60)
    fresh_candidate_watch_parser.add_argument("--latest-signals", type=int, default=250)
    fresh_candidate_watch_parser.add_argument("--latest-scans", type=int, default=500)
    fresh_candidate_watch_parser.add_argument("--iteration-timeout-seconds", type=int, default=30)
    fresh_candidate_watch_parser.add_argument("--heartbeat-every", type=int, default=1)
    fresh_candidate_watch_parser.add_argument("--heartbeat-ledger-path", default=None)
    fresh_candidate_watch_parser.add_argument("--run-watch-loop", action="store_true")
    fresh_candidate_watch_parser.add_argument("--record-watch", action="store_true")
    fresh_candidate_watch_parser.add_argument("--confirm-watch-loop", default=None)

    tiny_live_lane_unlock_parser = subparsers.add_parser(
        "tiny-live-lane-unlock-contract",
        parents=[parent],
    )
    tiny_live_lane_unlock_parser.add_argument("--lane-key", action="append", default=None)
    tiny_live_lane_unlock_parser.add_argument("--lane-keys", default=None)
    tiny_live_lane_unlock_parser.add_argument("--unlock-all-recommended-lanes", action="store_true")
    tiny_live_lane_unlock_parser.add_argument("--record-unlock-contract", action="store_true")
    tiny_live_lane_unlock_parser.add_argument("--confirm-unlock-contract", default=None)
    tiny_live_lane_unlock_parser.add_argument("--apply-lane-mode-if-safe", action="store_true")
    tiny_live_lane_unlock_parser.add_argument("--status-only", action="store_true")

    signal_to_watcher_trace_parser = subparsers.add_parser(
        "signal-to-watcher-eligibility-trace",
        parents=[parent],
    )
    signal_to_watcher_trace_parser.add_argument("--lane-key", action="append", default=None)
    signal_to_watcher_trace_parser.add_argument("--lane-keys", default=None)
    signal_to_watcher_trace_parser.add_argument("--trace-all-unlocked-lanes", action="store_true")
    signal_to_watcher_trace_parser.add_argument("--latest-signals", type=int, default=100)
    signal_to_watcher_trace_parser.add_argument("--latest-scans", type=int, default=200)
    signal_to_watcher_trace_parser.add_argument("--signal-id", default=None)
    signal_to_watcher_trace_parser.add_argument("--record-trace", action="store_true")
    signal_to_watcher_trace_parser.add_argument("--confirm-trace", default=None)

    entry_mode_derivation_bridge_parser = subparsers.add_parser(
        "entry-mode-derivation-bridge",
        parents=[parent],
    )
    entry_mode_derivation_bridge_parser.add_argument("--lane-key", action="append", default=None)
    entry_mode_derivation_bridge_parser.add_argument("--lane-keys", default=None)
    entry_mode_derivation_bridge_parser.add_argument("--trace-all-unlocked-lanes", action="store_true")
    entry_mode_derivation_bridge_parser.add_argument("--latest-signals", type=int, default=100)
    entry_mode_derivation_bridge_parser.add_argument("--record-bridge", action="store_true")
    entry_mode_derivation_bridge_parser.add_argument("--confirm-bridge", default=None)

    post_bridge_recheck_parser = subparsers.add_parser(
        "post-bridge-watcher-proof-capture-recheck",
        parents=[parent],
    )
    post_bridge_recheck_parser.add_argument("--lane-key", action="append", default=None)
    post_bridge_recheck_parser.add_argument("--lane-keys", default=None)
    post_bridge_recheck_parser.add_argument("--trace-all-unlocked-lanes", action="store_true")
    post_bridge_recheck_parser.add_argument("--latest-signals", type=int, default=100)
    post_bridge_recheck_parser.add_argument("--record-recheck", action="store_true")
    post_bridge_recheck_parser.add_argument("--confirm-post-bridge-recheck", default=None)

    apply_tiny_live_lane_mode_recheck_parser = subparsers.add_parser(
        "apply-tiny-live-lane-mode-recheck",
        parents=[parent],
    )
    apply_tiny_live_lane_mode_recheck_parser.add_argument("--lane-key", action="append", default=None)
    apply_tiny_live_lane_mode_recheck_parser.add_argument("--lane-keys", default=None)
    apply_tiny_live_lane_mode_recheck_parser.add_argument("--all-target-lanes", action="store_true")
    apply_tiny_live_lane_mode_recheck_parser.add_argument("--record-recheck", action="store_true")
    apply_tiny_live_lane_mode_recheck_parser.add_argument("--confirm-recheck", default=None)
    apply_tiny_live_lane_mode_recheck_parser.add_argument("--include-apply-commands", action="store_true")
    apply_tiny_live_lane_mode_recheck_parser.add_argument("--include-post-apply-recheck-commands", action="store_true")

    post_tiny_live_mode_watch_parser = subparsers.add_parser(
        "post-tiny-live-mode-fresh-proof-watch",
        parents=[parent],
    )
    post_tiny_live_mode_watch_parser.add_argument("--lane-key", action="append", default=None)
    post_tiny_live_mode_watch_parser.add_argument("--lane-keys", default=None)
    post_tiny_live_mode_watch_parser.add_argument("--all-target-lanes", action="store_true")
    post_tiny_live_mode_watch_parser.add_argument("--include-watch-command", action="store_true")
    post_tiny_live_mode_watch_parser.add_argument("--record-watch-prep", action="store_true")
    post_tiny_live_mode_watch_parser.add_argument("--confirm-watch-prep", default=None)

    candidate_source_audit_parser = subparsers.add_parser(
        "candidate-source-freshness-audit",
        parents=[parent],
    )
    candidate_source_audit_parser.add_argument("--latest-signals", type=int, default=1000)
    candidate_source_audit_parser.add_argument("--latest-scans", type=int, default=2000)
    candidate_source_audit_parser.add_argument("--watch-id", default=None)
    candidate_source_audit_parser.add_argument("--record-audit", action="store_true")
    candidate_source_audit_parser.add_argument("--confirm-audit", default=None)

    paper_opportunity_expansion_parser = subparsers.add_parser(
        "paper-opportunity-expansion",
        parents=[parent],
    )
    paper_opportunity_expansion_parser.add_argument("--latest-signals", type=int, default=1000)
    paper_opportunity_expansion_parser.add_argument("--latest-scans", type=int, default=2000)
    paper_opportunity_expansion_parser.add_argument("--include-default-expansion", action="store_true")
    paper_opportunity_expansion_parser.add_argument("--apply", action="store_true")
    paper_opportunity_expansion_parser.add_argument("--confirm-paper-expansion", default=None)
    paper_opportunity_expansion_parser.add_argument("--record-expansion", action="store_true")

    expanded_paper_watch_parser = subparsers.add_parser(
        "expanded-paper-watch",
        parents=[parent],
    )
    expanded_paper_watch_parser.add_argument("--latest-signals", type=int, default=1000)
    expanded_paper_watch_parser.add_argument("--latest-scans", type=int, default=2000)
    expanded_paper_watch_parser.add_argument("--all-paper-lanes", action="store_true")
    expanded_paper_watch_parser.add_argument("--include-tiny-live-targets-as-observed", action="store_true")
    expanded_paper_watch_parser.add_argument("--record-watch", action="store_true")
    expanded_paper_watch_parser.add_argument("--confirm-expanded-paper-watch", default=None)

    multi_lane_harvester_parser = subparsers.add_parser(
        "multi-lane-paper-harvester",
        parents=[parent],
    )
    multi_lane_harvester_parser.add_argument("--latest-signals", type=int, default=1000)
    multi_lane_harvester_parser.add_argument("--latest-scans", type=int, default=2000)
    multi_lane_harvester_parser.add_argument("--max-iterations", type=int, default=60)
    multi_lane_harvester_parser.add_argument("--sleep-seconds", type=int, default=60)
    multi_lane_harvester_parser.add_argument("--iteration-timeout-seconds", type=int, default=30)
    multi_lane_harvester_parser.add_argument("--heartbeat-every", type=int, default=1)
    multi_lane_harvester_parser.add_argument("--max-captures-per-iteration", type=int, default=10)
    multi_lane_harvester_parser.add_argument("--run-harvester-loop", action="store_true")
    multi_lane_harvester_parser.add_argument("--record-harvest", action="store_true")
    multi_lane_harvester_parser.add_argument("--confirm-multi-lane-harvest", default=None)

    full_spectrum_harvester_parser = subparsers.add_parser(
        "full-spectrum-harvester-expansion",
        parents=[parent],
    )
    full_spectrum_harvester_parser.add_argument("--latest-signals", type=int, default=3000)
    full_spectrum_harvester_parser.add_argument("--latest-scans", type=int, default=5000)
    full_spectrum_harvester_parser.add_argument("--max-iterations", type=int, default=60)
    full_spectrum_harvester_parser.add_argument("--sleep-seconds", type=int, default=60)
    full_spectrum_harvester_parser.add_argument("--iteration-timeout-seconds", type=int, default=30)
    full_spectrum_harvester_parser.add_argument("--heartbeat-every", type=int, default=1)
    full_spectrum_harvester_parser.add_argument("--max-captures-per-iteration", type=int, default=50)
    full_spectrum_harvester_parser.add_argument("--run-harvester-loop", action="store_true")
    full_spectrum_harvester_parser.add_argument("--record-harvest", action="store_true")
    full_spectrum_harvester_parser.add_argument("--confirm-full-spectrum-harvest", default=None)

    multi_lane_evidence_ranking_parser = subparsers.add_parser(
        "multi-lane-evidence-ranking",
        parents=[parent],
    )
    multi_lane_evidence_ranking_parser.add_argument("--record-ranking", action="store_true")
    multi_lane_evidence_ranking_parser.add_argument("--confirm-multi-lane-ranking", default=None)

    signal_origin_registry_parser = subparsers.add_parser(
        "signal-origin-registry",
        parents=[parent],
    )
    signal_origin_registry_parser.add_argument("--latest-signals", type=int, default=1000)
    signal_origin_registry_parser.add_argument("--latest-harvest-records", type=int, default=500)
    signal_origin_registry_parser.add_argument("--record-registry", action="store_true")
    signal_origin_registry_parser.add_argument("--confirm-signal-origin-registry", default=None)

    keter_signal_origin_scoring_parser = subparsers.add_parser(
        "keter-signal-origin-scoring",
        parents=[parent],
    )
    keter_signal_origin_scoring_parser.add_argument("--latest-registry-records", type=int, default=100)
    keter_signal_origin_scoring_parser.add_argument("--latest-ranking-records", type=int, default=100)
    keter_signal_origin_scoring_parser.add_argument("--record-scoring", action="store_true")
    keter_signal_origin_scoring_parser.add_argument("--confirm-keter-origin-scoring", default=None)

    signal_origin_lane_matrix_parser = subparsers.add_parser(
        "signal-origin-lane-matrix",
        parents=[parent],
    )
    signal_origin_lane_matrix_parser.add_argument("--latest-ranking-records", type=int, default=100)
    signal_origin_lane_matrix_parser.add_argument("--latest-scoring-records", type=int, default=100)
    signal_origin_lane_matrix_parser.add_argument("--record-matrix", action="store_true")
    signal_origin_lane_matrix_parser.add_argument("--confirm-signal-origin-lane-matrix", default=None)

    three_black_crows_detector_parser = subparsers.add_parser(
        "three-black-crows-detector",
        parents=[parent],
    )
    three_black_crows_detector_parser.add_argument("--symbol", default="BTCUSDT")
    three_black_crows_detector_parser.add_argument("--timeframe", default="8m")
    three_black_crows_detector_parser.add_argument("--mode", choices=["strict", "loose_preview"], default="strict")
    three_black_crows_detector_parser.add_argument("--latest-candles", type=int, default=500)
    three_black_crows_detector_parser.add_argument("--record-detector", action="store_true")
    three_black_crows_detector_parser.add_argument("--confirm-three-black-crows-detector", default=None)

    three_black_crows_feed_integration_parser = subparsers.add_parser(
        "three-black-crows-feed-integration",
        parents=[parent],
    )
    three_black_crows_feed_integration_parser.add_argument("--symbol", default="BTCUSDT")
    three_black_crows_feed_integration_parser.add_argument("--timeframe", default="8m")
    three_black_crows_feed_integration_parser.add_argument("--mode", choices=["strict", "loose_preview"], default="strict")
    three_black_crows_feed_integration_parser.add_argument("--latest-candles", type=int, default=500)
    three_black_crows_feed_integration_parser.add_argument("--record-integration", action="store_true")
    three_black_crows_feed_integration_parser.add_argument("--confirm-three-black-crows-feed-integration", default=None)

    local_candle_feed_preview_parser = subparsers.add_parser(
        "local-candle-feed-preview",
        parents=[parent],
    )
    local_candle_feed_preview_parser.add_argument("--symbol", default="BTCUSDT")
    local_candle_feed_preview_parser.add_argument("--timeframe", default="8m")
    local_candle_feed_preview_parser.add_argument("--latest-candles", type=int, default=500)
    local_candle_feed_preview_parser.add_argument("--record-preview", action="store_true")
    local_candle_feed_preview_parser.add_argument("--confirm-local-candle-feed-preview", default=None)

    local_candle_feed_adapter_parser = subparsers.add_parser(
        "local-candle-feed-adapter",
        parents=[parent],
    )
    local_candle_feed_adapter_parser.add_argument("--symbol", default="BTCUSDT")
    local_candle_feed_adapter_parser.add_argument("--timeframe", default="8m")
    local_candle_feed_adapter_parser.add_argument("--latest-candles", type=int, default=500)
    local_candle_feed_adapter_parser.add_argument("--record-adapter", action="store_true")
    local_candle_feed_adapter_parser.add_argument("--confirm-local-candle-feed-adapter", default=None)
    local_candle_feed_adapter_parser.add_argument("--write-normalized-feed", action="store_true")
    local_candle_feed_adapter_parser.add_argument("--confirm-normalized-candle-feed-write", default=None)

    three_black_crows_local_detection_parser = subparsers.add_parser(
        "three-black-crows-local-detection",
        parents=[parent],
    )
    three_black_crows_local_detection_parser.add_argument("--symbol", default="BTCUSDT")
    three_black_crows_local_detection_parser.add_argument("--timeframe", default="8m")
    three_black_crows_local_detection_parser.add_argument("--latest-candles", type=int, default=500)
    three_black_crows_local_detection_parser.add_argument(
        "--mode",
        choices=["strict", "loose_preview", "both"],
        default="both",
    )
    three_black_crows_local_detection_parser.add_argument("--record-detection", action="store_true")
    three_black_crows_local_detection_parser.add_argument(
        "--confirm-three-black-crows-local-detection",
        default=None,
    )

    pattern_detector_family_expansion_parser = subparsers.add_parser(
        "pattern-detector-family-expansion",
        parents=[parent],
    )
    pattern_detector_family_expansion_parser.add_argument("--symbol", default="BTCUSDT")
    pattern_detector_family_expansion_parser.add_argument(
        "--timeframes",
        default="4m,8m,13m,22m,44m,55m,88m,222m,444m,666m,888m,4H,13H,13D",
    )
    pattern_detector_family_expansion_parser.add_argument(
        "--mode",
        choices=["strict", "loose_preview", "both"],
        default="both",
    )
    pattern_detector_family_expansion_parser.add_argument("--latest-candles", type=int, default=500)
    pattern_detector_family_expansion_parser.add_argument("--record-expansion", action="store_true")
    pattern_detector_family_expansion_parser.add_argument("--confirm-pattern-family-expansion", default=None)

    wma_ma_anchor_layer_preview_parser = subparsers.add_parser(
        "wma-ma-anchor-layer-preview",
        parents=[parent],
    )
    wma_ma_anchor_layer_preview_parser.add_argument("--symbol", default="BTCUSDT")
    wma_ma_anchor_layer_preview_parser.add_argument("--timeframes", default=None)
    wma_ma_anchor_layer_preview_parser.add_argument("--periods", default=None)
    wma_ma_anchor_layer_preview_parser.add_argument("--near-touch-threshold-pct", type=float, default=0.15)
    wma_ma_anchor_layer_preview_parser.add_argument("--success-threshold-pct", type=float, default=0.10)
    wma_ma_anchor_layer_preview_parser.add_argument("--adverse-threshold-pct", type=float, default=0.10)
    wma_ma_anchor_layer_preview_parser.add_argument("--record-preview", action="store_true")
    wma_ma_anchor_layer_preview_parser.add_argument("--confirm-wma-ma-anchor-preview", default=None)

    signal_origin_feedback_sync_parser = subparsers.add_parser(
        "signal-origin-feedback-sync",
        parents=[parent],
    )
    signal_origin_feedback_sync_parser.add_argument("--signal-origin", default="three_black_crows")
    signal_origin_feedback_sync_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    signal_origin_feedback_sync_parser.add_argument("--record-feedback", action="store_true")
    signal_origin_feedback_sync_parser.add_argument("--confirm-signal-origin-feedback-sync", default=None)

    pattern_family_feedback_sync_parser = subparsers.add_parser(
        "pattern-family-feedback-sync",
        parents=[parent],
    )
    pattern_family_feedback_sync_parser.add_argument("--record-feedback", action="store_true")
    pattern_family_feedback_sync_parser.add_argument("--confirm-pattern-family-feedback-sync", default=None)

    anchor_outcome_deepening_parser = subparsers.add_parser(
        "anchor-outcome-deepening",
        parents=[parent],
    )
    anchor_outcome_deepening_parser.add_argument("--symbol", default="BTCUSDT")
    anchor_outcome_deepening_parser.add_argument("--record-deepening", action="store_true")
    anchor_outcome_deepening_parser.add_argument("--confirm-anchor-outcome-deepening", default=None)

    keter_rescore_after_three_black_crows_parser = subparsers.add_parser(
        "keter-rescore-after-three-black-crows",
        parents=[parent],
    )
    keter_rescore_after_three_black_crows_parser.add_argument("--record-rescore", action="store_true")
    keter_rescore_after_three_black_crows_parser.add_argument("--confirm-keter-rescore-after-crows", default=None)

    lane_matrix_after_crow_rescoring_parser = subparsers.add_parser(
        "lane-matrix-after-crow-rescoring",
        parents=[parent],
    )
    lane_matrix_after_crow_rescoring_parser.add_argument("--record-matrix", action="store_true")
    lane_matrix_after_crow_rescoring_parser.add_argument("--confirm-lane-matrix-after-crow-rescore", default=None)

    crow_outcome_mapping_parser = subparsers.add_parser(
        "crow-outcome-mapping-preview",
        parents=[parent],
    )
    crow_outcome_mapping_parser.add_argument("--symbol", default="BTCUSDT")
    crow_outcome_mapping_parser.add_argument("--timeframe", default="8m")
    crow_outcome_mapping_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    crow_outcome_mapping_parser.add_argument("--success-threshold-pct", type=float, default=0.10)
    crow_outcome_mapping_parser.add_argument("--adverse-threshold-pct", type=float, default=0.10)
    crow_outcome_mapping_parser.add_argument("--record-mapping", action="store_true")
    crow_outcome_mapping_parser.add_argument("--confirm-crow-outcome-mapping", default=None)

    pattern_outcome_mapping_family_parser = subparsers.add_parser(
        "pattern-outcome-mapping-family",
        parents=[parent],
    )
    pattern_outcome_mapping_family_parser.add_argument("--symbol", default="BTCUSDT")
    pattern_outcome_mapping_family_parser.add_argument("--success-threshold-pct", type=float, default=0.10)
    pattern_outcome_mapping_family_parser.add_argument("--adverse-threshold-pct", type=float, default=0.10)
    pattern_outcome_mapping_family_parser.add_argument("--record-mapping", action="store_true")
    pattern_outcome_mapping_family_parser.add_argument("--confirm-pattern-outcome-family", default=None)

    crow_outcome_keter_feedback_parser = subparsers.add_parser(
        "crow-outcome-keter-feedback",
        parents=[parent],
    )
    crow_outcome_keter_feedback_parser.add_argument("--record-feedback", action="store_true")
    crow_outcome_keter_feedback_parser.add_argument("--confirm-crow-outcome-keter-feedback", default=None)

    pattern_keter_rescoring_family_parser = subparsers.add_parser(
        "pattern-keter-rescoring-family",
        parents=[parent],
    )
    pattern_keter_rescoring_family_parser.add_argument("--record-rescore", action="store_true")
    pattern_keter_rescoring_family_parser.add_argument("--confirm-pattern-keter-family", default=None)

    pattern_lane_matrix_review_parser = subparsers.add_parser(
        "pattern-lane-matrix-review",
        parents=[parent],
    )
    pattern_lane_matrix_review_parser.add_argument("--record-matrix", action="store_true")
    pattern_lane_matrix_review_parser.add_argument("--confirm-pattern-lane-matrix", default=None)

    anchor_signal_confluence_matrix_parser = subparsers.add_parser(
        "anchor-signal-confluence-matrix",
        parents=[parent],
    )
    anchor_signal_confluence_matrix_parser.add_argument("--record-matrix", action="store_true")
    anchor_signal_confluence_matrix_parser.add_argument("--confirm-anchor-signal-confluence", default=None)

    strategy_evidence_registry_parser = subparsers.add_parser(
        "strategy-evidence-registry",
        parents=[parent],
    )
    strategy_evidence_registry_parser.add_argument("--record-registry", action="store_true")
    strategy_evidence_registry_parser.add_argument("--confirm-strategy-evidence-registry", default=None)

    lane_matrix_after_crow_outcome_feedback_parser = subparsers.add_parser(
        "lane-matrix-after-crow-outcome-feedback",
        parents=[parent],
    )
    lane_matrix_after_crow_outcome_feedback_parser.add_argument("--record-matrix", action="store_true")
    lane_matrix_after_crow_outcome_feedback_parser.add_argument(
        "--confirm-lane-matrix-after-crow-outcome",
        default=None,
    )

    full_spectrum_paper_coverage_audit_parser = subparsers.add_parser(
        "full-spectrum-paper-coverage-audit",
        parents=[parent],
    )
    full_spectrum_paper_coverage_audit_parser.add_argument("--record-audit", action="store_true")
    full_spectrum_paper_coverage_audit_parser.add_argument("--confirm-full-spectrum-paper-audit", default=None)

    promotion_candidate_audit_parser = subparsers.add_parser(
        "promotion-candidate-audit",
        parents=[parent],
    )
    promotion_candidate_audit_parser.add_argument("--latest-outcomes", type=int, default=5000)
    promotion_candidate_audit_parser.add_argument("--latest-signals", type=int, default=2000)
    promotion_candidate_audit_parser.add_argument("--latest-watch-records", type=int, default=200)
    promotion_candidate_audit_parser.add_argument("--include-paper-lanes", action="store_true")
    promotion_candidate_audit_parser.add_argument("--include-tiny-live-incumbents", action="store_true")
    promotion_candidate_audit_parser.add_argument("--record-audit", action="store_true")
    promotion_candidate_audit_parser.add_argument("--confirm-promotion-audit", default=None)

    full_spectrum_review_parser = subparsers.add_parser(
        "full-spectrum-betrayal-short-review",
        parents=[parent],
    )
    full_spectrum_review_parser.add_argument("--latest-outcomes", type=int, default=10000)
    full_spectrum_review_parser.add_argument("--latest-signals", type=int, default=3000)
    full_spectrum_review_parser.add_argument("--latest-betrayal", type=int, default=5000)
    full_spectrum_review_parser.add_argument("--latest-watch-records", type=int, default=500)
    full_spectrum_review_parser.add_argument("--include-paper-lanes", action="store_true")
    full_spectrum_review_parser.add_argument("--include-tiny-live-incumbents", action="store_true")
    full_spectrum_review_parser.add_argument("--include-betrayal-inverse", action="store_true")
    full_spectrum_review_parser.add_argument("--record-review", action="store_true")
    full_spectrum_review_parser.add_argument("--confirm-full-spectrum-review", default=None)

    short_strategy_packet_parser = subparsers.add_parser(
        "short-strategy-packet",
        parents=[parent],
    )
    short_strategy_packet_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    short_strategy_packet_parser.add_argument("--latest-outcomes", type=int, default=10000)
    short_strategy_packet_parser.add_argument("--latest-signals", type=int, default=3000)
    short_strategy_packet_parser.add_argument("--latest-betrayal", type=int, default=5000)
    short_strategy_packet_parser.add_argument("--latest-watch-records", type=int, default=500)
    short_strategy_packet_parser.add_argument("--record-packet", action="store_true")
    short_strategy_packet_parser.add_argument("--confirm-short-strategy-packet", default=None)

    short_paper_capture_parser = subparsers.add_parser(
        "short-paper-evidence-capture-loop",
        parents=[parent],
    )
    short_paper_capture_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    short_paper_capture_parser.add_argument("--latest-signals", type=int, default=500)
    short_paper_capture_parser.add_argument("--latest-scans", type=int, default=1000)
    short_paper_capture_parser.add_argument("--max-iterations", type=int, default=60)
    short_paper_capture_parser.add_argument("--sleep-seconds", type=int, default=60)
    short_paper_capture_parser.add_argument("--iteration-timeout-seconds", type=int, default=30)
    short_paper_capture_parser.add_argument("--heartbeat-every", type=int, default=1)
    short_paper_capture_parser.add_argument("--run-capture-loop", action="store_true")
    short_paper_capture_parser.add_argument("--record-capture", action="store_true")
    short_paper_capture_parser.add_argument("--confirm-short-paper-capture", default=None)

    short_evidence_recheck_parser = subparsers.add_parser(
        "short-evidence-recheck-packet",
        parents=[parent],
    )
    short_evidence_recheck_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    short_evidence_recheck_parser.add_argument("--latest-captures", type=int, default=200)
    short_evidence_recheck_parser.add_argument("--latest-outcomes", type=int, default=10000)
    short_evidence_recheck_parser.add_argument("--latest-signals", type=int, default=3000)
    short_evidence_recheck_parser.add_argument("--latest-betrayal", type=int, default=5000)
    short_evidence_recheck_parser.add_argument("--record-packet", action="store_true")
    short_evidence_recheck_parser.add_argument("--confirm-short-evidence-recheck", default=None)

    fundless_short_rehearsal_parser = subparsers.add_parser(
        "fundless-short-tiny-live-readiness-rehearsal",
        parents=[parent],
    )
    fundless_short_rehearsal_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    fundless_short_rehearsal_parser.add_argument("--latest-captures", type=int, default=200)
    fundless_short_rehearsal_parser.add_argument("--latest-outcomes", type=int, default=10000)
    fundless_short_rehearsal_parser.add_argument("--latest-signals", type=int, default=3000)
    fundless_short_rehearsal_parser.add_argument("--record-rehearsal", action="store_true")
    fundless_short_rehearsal_parser.add_argument("--confirm-fundless-short-rehearsal", default=None)

    fundless_short_dry_run_packet_parser = subparsers.add_parser(
        "fundless-short-dry-run-packet",
        parents=[parent],
    )
    fundless_short_dry_run_packet_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    fundless_short_dry_run_packet_parser.add_argument("--latest-captures", type=int, default=200)
    fundless_short_dry_run_packet_parser.add_argument("--latest-outcomes", type=int, default=10000)
    fundless_short_dry_run_packet_parser.add_argument("--latest-signals", type=int, default=3000)
    fundless_short_dry_run_packet_parser.add_argument("--record-packet", action="store_true")
    fundless_short_dry_run_packet_parser.add_argument("--confirm-fundless-short-dry-run", default=None)

    short_risk_contract_draft_preview_parser = subparsers.add_parser(
        "short-risk-contract-draft-preview",
        parents=[parent],
    )
    short_risk_contract_draft_preview_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    short_risk_contract_draft_preview_parser.add_argument("--record-draft", action="store_true")
    short_risk_contract_draft_preview_parser.add_argument("--confirm-short-risk-contract-draft", default=None)

    short_risk_contract_apply_review_parser = subparsers.add_parser(
        "short-risk-contract-apply-review",
        parents=[parent],
    )
    short_risk_contract_apply_review_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    short_risk_contract_apply_review_parser.add_argument("--latest-captures", type=int, default=200)
    short_risk_contract_apply_review_parser.add_argument("--latest-drafts", type=int, default=50)
    short_risk_contract_apply_review_parser.add_argument("--record-review", action="store_true")
    short_risk_contract_apply_review_parser.add_argument("--confirm-short-risk-contract-apply-review", default=None)

    funding_readonly_precheck_parser = subparsers.add_parser(
        "funding-readonly-precheck",
        parents=[parent],
    )
    funding_readonly_precheck_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    funding_readonly_precheck_parser.add_argument("--minimum-balance-usdt", type=float, default=44.0)
    funding_readonly_precheck_parser.add_argument("--allow-readonly-network-check", action="store_true")
    funding_readonly_precheck_parser.add_argument("--record-precheck", action="store_true")
    funding_readonly_precheck_parser.add_argument("--confirm-funding-readonly-precheck", default=None)

    readonly_balance_check_parser = subparsers.add_parser(
        "readonly-balance-check",
        parents=[parent],
    )
    readonly_balance_check_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    readonly_balance_check_parser.add_argument("--minimum-balance-usdt", type=float, default=44.0)
    readonly_balance_check_parser.add_argument("--allow-readonly-network-check", action="store_true")
    readonly_balance_check_parser.add_argument("--recv-window-ms", type=int, default=5000)
    readonly_balance_check_parser.add_argument("--record-balance-check", action="store_true")
    readonly_balance_check_parser.add_argument("--confirm-readonly-balance-check", default=None)

    readonly_balance_failure_recheck_parser = subparsers.add_parser(
        "readonly-balance-failure-recheck",
        parents=[parent],
    )
    readonly_balance_failure_recheck_parser.add_argument("--latest-balance-checks", type=int, default=50)
    readonly_balance_failure_recheck_parser.add_argument("--record-recheck", action="store_true")
    readonly_balance_failure_recheck_parser.add_argument("--confirm-readonly-balance-failure-recheck", default=None)

    funding_gate_key_role_sync_parser = subparsers.add_parser(
        "funding-gate-key-role-sync",
        parents=[parent],
    )
    funding_gate_key_role_sync_parser.add_argument("--record-sync", action="store_true")
    funding_gate_key_role_sync_parser.add_argument("--confirm-funding-key-role-sync", default=None)

    funding_gate_role_specific_sync_parser = subparsers.add_parser(
        "funding-gate-role-specific-sync",
        parents=[parent],
    )
    funding_gate_role_specific_sync_parser.add_argument("--record-sync", action="store_true")
    funding_gate_role_specific_sync_parser.add_argument("--confirm-funding-role-specific-sync", default=None)

    tiny_live_blocker_burn_down_parser = subparsers.add_parser(
        "tiny-live-blocker-burn-down",
        parents=[parent],
    )
    tiny_live_blocker_burn_down_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    tiny_live_blocker_burn_down_parser.add_argument("--record-burn-down", action="store_true")
    tiny_live_blocker_burn_down_parser.add_argument("--confirm-tiny-live-burn-down", default=None)

    capture_count_sync_parser = subparsers.add_parser(
        "capture-count-sync-8m-short",
        parents=[parent],
    )
    capture_count_sync_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    capture_count_sync_parser.add_argument("--record-sync", action="store_true")
    capture_count_sync_parser.add_argument("--confirm-capture-count-sync", default=None)

    tiny_live_readiness_gap_recheck_parser = subparsers.add_parser(
        "tiny-live-readiness-gap-recheck",
        parents=[parent],
    )
    tiny_live_readiness_gap_recheck_parser.add_argument("--record-recheck", action="store_true")
    tiny_live_readiness_gap_recheck_parser.add_argument("--confirm-tiny-live-gap-recheck", default=None)

    capture_threshold_recovery_parser = subparsers.add_parser(
        "capture-threshold-recovery-8m-short",
        parents=[parent],
    )
    capture_threshold_recovery_parser.add_argument("--record-recovery", action="store_true")
    capture_threshold_recovery_parser.add_argument("--confirm-capture-threshold-recovery", default=None)

    evidence_threshold_recheck_parser = subparsers.add_parser(
        "evidence-threshold-recheck-8m-short",
        parents=[parent],
    )
    evidence_threshold_recheck_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    evidence_threshold_recheck_parser.add_argument("--record-recheck", action="store_true")
    evidence_threshold_recheck_parser.add_argument("--confirm-evidence-threshold-recheck", default=None)

    capture_watcher_supervisor_parser = subparsers.add_parser(
        "capture-watcher-supervisor-8m-short",
        parents=[parent],
    )
    capture_watcher_supervisor_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    capture_watcher_supervisor_parser.add_argument("--record-supervisor", action="store_true")
    capture_watcher_supervisor_parser.add_argument("--confirm-capture-watcher-supervisor", default=None)
    capture_watcher_supervisor_parser.add_argument("--run-supervisor-loop", action="store_true")
    capture_watcher_supervisor_parser.add_argument("--max-supervisor-iterations", type=int, default=60)
    capture_watcher_supervisor_parser.add_argument("--sleep-seconds", type=int, default=60)
    capture_watcher_supervisor_parser.add_argument("--allow-paper-watcher-restart", action="store_true")

    weekend_paper_fisherman_supervisor_parser = subparsers.add_parser(
        "weekend-paper-fisherman-supervisor",
        parents=[parent],
    )
    weekend_paper_fisherman_supervisor_parser.add_argument("--record-supervisor", action="store_true")
    weekend_paper_fisherman_supervisor_parser.add_argument("--confirm-weekend-fisherman-supervisor", default=None)

    betrayal_integration_recheck_parser = subparsers.add_parser(
        "betrayal-integration-recheck",
        parents=[parent],
    )
    betrayal_integration_recheck_parser.add_argument("--record-recheck", action="store_true")
    betrayal_integration_recheck_parser.add_argument("--confirm-betrayal-integration-recheck", default=None)

    betrayal_true_inverse_refresh_parser = subparsers.add_parser(
        "betrayal-true-inverse-refresh",
        parents=[parent],
    )
    betrayal_true_inverse_refresh_parser.add_argument("--record-refresh", action="store_true")
    betrayal_true_inverse_refresh_parser.add_argument("--confirm-betrayal-true-inverse-refresh", default=None)

    betrayal_paper_matrix_context_parser = subparsers.add_parser(
        "betrayal-paper-matrix-context",
        parents=[parent],
    )
    betrayal_paper_matrix_context_parser.add_argument("--record-matrix", action="store_true")
    betrayal_paper_matrix_context_parser.add_argument("--confirm-betrayal-paper-matrix-context", default=None)

    betrayal_event_tracker_parser = subparsers.add_parser(
        "betrayal-event-tracker",
        parents=[parent],
    )
    betrayal_event_tracker_parser.add_argument("--record-tracker", action="store_true")
    betrayal_event_tracker_parser.add_argument("--confirm-betrayal-event-tracker", default=None)

    betrayal_regime_miro_recheck_parser = subparsers.add_parser(
        "betrayal-regime-miro-recheck",
        parents=[parent],
    )
    betrayal_regime_miro_recheck_parser.add_argument("--record-recheck", action="store_true")
    betrayal_regime_miro_recheck_parser.add_argument("--confirm-betrayal-regime-miro-recheck", default=None)

    betrayal_direction_split_resolver_parser = subparsers.add_parser(
        "betrayal-direction-split-resolver",
        parents=[parent],
    )
    betrayal_direction_split_resolver_parser.add_argument("--record-resolver", action="store_true")
    betrayal_direction_split_resolver_parser.add_argument("--confirm-betrayal-direction-split-resolver", default=None)

    betrayal_source_emitter_refresh_parser = subparsers.add_parser(
        "betrayal-source-emitter-refresh",
        parents=[parent],
    )
    betrayal_source_emitter_refresh_parser.add_argument("--record-refresh", action="store_true")
    betrayal_source_emitter_refresh_parser.add_argument("--confirm-betrayal-source-emitter-refresh", default=None)

    betrayal_aggregate_decomposition_parser = subparsers.add_parser(
        "betrayal-aggregate-decomposition",
        parents=[parent],
    )
    betrayal_aggregate_decomposition_parser.add_argument("--record-decomposition", action="store_true")
    betrayal_aggregate_decomposition_parser.add_argument("--confirm-betrayal-aggregate-decomposition", default=None)

    registry_wiring_betrayal_parser = subparsers.add_parser(
        "registry-wiring-betrayal-source-family",
        parents=[parent],
    )
    registry_wiring_betrayal_parser.add_argument("--record-wiring", action="store_true")
    registry_wiring_betrayal_parser.add_argument(
        "--confirm-registry-wiring-betrayal-source-family",
        default=None,
    )

    betrayal_registry_consumer_refactor_parser = subparsers.add_parser(
        "betrayal-registry-consumer-refactor",
        parents=[parent],
    )
    betrayal_registry_consumer_refactor_parser.add_argument("--record-refactor", action="store_true")
    betrayal_registry_consumer_refactor_parser.add_argument(
        "--confirm-betrayal-registry-consumer-refactor",
        default=None,
    )

    betrayal_source_identity_normalizer_parser = subparsers.add_parser(
        "betrayal-source-identity-normalizer",
        parents=[parent],
    )
    betrayal_source_identity_normalizer_parser.add_argument("--record-normalizer", action="store_true")
    betrayal_source_identity_normalizer_parser.add_argument(
        "--confirm-betrayal-source-identity-normalizer",
        default=None,
    )

    betrayal_source_identity_evidence_collector_parser = subparsers.add_parser(
        "betrayal-source-identity-evidence-collector",
        parents=[parent],
    )
    betrayal_source_identity_evidence_collector_parser.add_argument("--record-collector", action="store_true")
    betrayal_source_identity_evidence_collector_parser.add_argument(
        "--confirm-betrayal-source-identity-evidence-collector",
        default=None,
    )

    betrayal_entry_mode_evidence_wiring_parser = subparsers.add_parser(
        "betrayal-entry-mode-evidence-wiring",
        parents=[parent],
    )
    betrayal_entry_mode_evidence_wiring_parser.add_argument("--record-wiring", action="store_true")
    betrayal_entry_mode_evidence_wiring_parser.add_argument(
        "--confirm-betrayal-entry-mode-evidence-wiring",
        default=None,
    )

    risk_contract_apply_packet_parser = subparsers.add_parser(
        "risk-contract-apply-packet-8m-short",
        parents=[parent],
    )
    risk_contract_apply_packet_parser.add_argument("--lane-key", default="BTCUSDT|8m|short|ladder_close_50_618")
    risk_contract_apply_packet_parser.add_argument("--record-packet", action="store_true")
    risk_contract_apply_packet_parser.add_argument("--confirm-risk-contract-apply-packet", default=None)

    env_role_split_proposal_parser = subparsers.add_parser(
        "env-role-split-proposal",
        parents=[parent],
    )
    env_role_split_proposal_parser.add_argument("--record-proposal", action="store_true")
    env_role_split_proposal_parser.add_argument("--confirm-env-role-split-proposal", default=None)

    env_role_adapter_preview_parser = subparsers.add_parser(
        "env-role-adapter-preview",
        parents=[parent],
    )
    env_role_adapter_preview_parser.add_argument("--record-preview", action="store_true")
    env_role_adapter_preview_parser.add_argument("--confirm-env-role-adapter-preview", default=None)

    account_read_env_migration_packet_parser = subparsers.add_parser(
        "account-read-env-migration-packet",
        parents=[parent],
    )
    account_read_env_migration_packet_parser.add_argument("--record-packet", action="store_true")
    account_read_env_migration_packet_parser.add_argument("--confirm-account-read-env-migration", default=None)

    account_read_env_migration_verify_parser = subparsers.add_parser(
        "account-read-env-migration-verify",
        parents=[parent],
    )
    account_read_env_migration_verify_parser.add_argument("--record-verify", action="store_true")
    account_read_env_migration_verify_parser.add_argument("--confirm-account-read-env-migration-verify", default=None)

    betrayal_true_paper_scaffold_parser = subparsers.add_parser("betrayal-true-paper-scaffold", parents=[parent])
    betrayal_true_paper_scaffold_parser.add_argument("--symbol", default="BTCUSDT")
    betrayal_true_paper_scaffold_parser.add_argument("--max-candidates", type=int, default=20)
    betrayal_true_paper_scaffold_parser.add_argument("--write", action="store_true")

    betrayal_paper_outcomes_parser = subparsers.add_parser("betrayal-paper-outcomes", parents=[parent])
    betrayal_paper_outcomes_parser.add_argument("--signal-id", default=None)
    betrayal_paper_outcomes_parser.add_argument("--recent", type=int, default=20)
    betrayal_paper_outcomes_parser.add_argument("--write", action="store_true")
    betrayal_paper_outcomes_parser.add_argument("--outcome-json", default=None)

    betrayal_paper_signal_detector_parser = subparsers.add_parser("betrayal-paper-signal-detector", parents=[parent])
    betrayal_paper_signal_detector_parser.add_argument("--max-signals", type=int, default=20)
    betrayal_paper_signal_detector_parser.add_argument("--identity-filter", default=None)
    betrayal_paper_signal_detector_parser.add_argument("--write", action="store_true")
    betrayal_paper_signal_detector_parser.add_argument("--allow-open-tracking", action=argparse.BooleanOptionalAction, default=True)
    betrayal_paper_signal_detector_parser.add_argument("--allow-closed-outcomes", action=argparse.BooleanOptionalAction, default=True)

    betrayal_detector_source_wiring_parser = subparsers.add_parser("betrayal-detector-source-wiring", parents=[parent])
    betrayal_detector_source_wiring_parser.add_argument("--symbol", default="BTCUSDT")
    betrayal_detector_source_wiring_parser.add_argument("--timeframe", default="222m")
    betrayal_detector_source_wiring_parser.add_argument("--write", action="store_true")

    betrayal_source_signal_emitter_parser = subparsers.add_parser("betrayal-source-signal-emitter", parents=[parent])
    betrayal_source_signal_emitter_parser.add_argument("--max-signals", type=int, default=20)
    betrayal_source_signal_emitter_parser.add_argument("--identity-filter", default=None)
    betrayal_source_signal_emitter_parser.add_argument("--write", action="store_true")
    betrayal_source_signal_emitter_parser.add_argument("--allow-historical-replay", action=argparse.BooleanOptionalAction, default=True)
    betrayal_source_signal_emitter_parser.add_argument("--allow-fresh-current", action=argparse.BooleanOptionalAction, default=False)

    decisions_parser = subparsers.add_parser("decisions", parents=[parent])
    decisions_parser.add_argument("--limit", type=int, default=50)
    decisions_parser.add_argument("--signal-id", default=None)

    log_manual_outcome_parser = subparsers.add_parser("log-manual-outcome", parents=[parent])
    log_manual_outcome_parser.add_argument("--signal-id", required=True)
    log_manual_outcome_parser.add_argument("--result", choices=("win", "loss", "breakeven", "skipped"), required=True)
    log_manual_outcome_parser.add_argument("--entry-price", type=float, default=None)
    log_manual_outcome_parser.add_argument("--exit-price", type=float, default=None)
    log_manual_outcome_parser.add_argument("--position-usd", type=float, default=None)
    log_manual_outcome_parser.add_argument("--leverage", type=float, default=None)
    log_manual_outcome_parser.add_argument("--pnl-usd", type=float, default=None)
    log_manual_outcome_parser.add_argument("--pnl-pct", type=float, default=None)
    log_manual_outcome_parser.add_argument("--notes", default="")

    manual_outcomes_parser = subparsers.add_parser("manual-outcomes", parents=[parent])
    manual_outcomes_parser.add_argument("--limit", type=int, default=50)
    manual_outcomes_parser.add_argument("--signal-id", default=None)

    subparsers.add_parser("readiness", parents=[parent])

    subparsers.add_parser("trade-ticket", parents=[parent])

    trade_tickets_parser = subparsers.add_parser("trade-tickets", parents=[parent])
    trade_tickets_parser.add_argument("--limit", type=int, default=50)
    trade_tickets_parser.add_argument("--ticket-id", default=None)

    execute_paper_parser = subparsers.add_parser("execute-paper-ticket", parents=[parent])
    execute_paper_parser.add_argument("--ticket-id", required=True)
    execute_paper_parser.add_argument("--operator", default="josue")
    execute_paper_parser.add_argument("--notes", default="")

    paper_executions_parser = subparsers.add_parser("paper-executions", parents=[parent])
    paper_executions_parser.add_argument("--limit", type=int, default=50)
    paper_executions_parser.add_argument("--signal-id", default=None)
    paper_executions_parser.add_argument("--status", default=None)

    exchange_dry_run_parser = subparsers.add_parser("exchange-dry-run", parents=[parent])
    exchange_dry_run_parser.add_argument("--allow-short", action="store_true")
    exchange_dry_run_parser.add_argument("--signal-id", default=None)
    exchange_dry_run_parser.add_argument("--max-position-usd", type=float, default=44.0)
    exchange_dry_run_parser.add_argument("--max-leverage", type=float, default=3.0)

    subparsers.add_parser("live-safety", parents=[parent])

    live_connector_submit_parser = subparsers.add_parser("live-connector-submit", parents=[parent])
    live_connector_submit_parser.add_argument("--ticket-id", required=True)
    live_connector_submit_parser.add_argument("--operator", default="josue")
    live_connector_submit_parser.add_argument("--notes", default="")

    live_attempts_parser = subparsers.add_parser("live-attempts", parents=[parent])
    live_attempts_parser.add_argument("--limit", type=int, default=50)
    live_attempts_parser.add_argument("--signal-id", default=None)
    live_attempts_parser.add_argument("--ticket-id", default=None)

    subparsers.add_parser("binance-readonly-status", parents=[parent])

    subparsers.add_parser("notification-status", parents=[parent])

    notification_check_parser = subparsers.add_parser("notification-check", parents=[parent])
    notification_check_parser.add_argument("--send", action="store_true")
    notification_check_parser.add_argument("--channel", choices=("telegram", "none"), default="none")

    readiness_alerts_parser = subparsers.add_parser("readiness-alerts", parents=[parent])
    readiness_alerts_parser.add_argument("--limit", type=int, default=50)

    watchlist_parser = subparsers.add_parser("watchlist", parents=[parent])
    watchlist_parser.add_argument(
        "--category",
        choices=("CORE_LIVE", "CORE_WATCH", "RELATIVE_STRENGTH", "LIQUID_MAJOR", "HIGH_BETA"),
        default=None,
    )
    watchlist_parser.add_argument("--limit", type=int, default=50)

    subparsers.add_parser("watchlist-summary", parents=[parent])

    multi_scan_parser = subparsers.add_parser("multi-symbol-scan", parents=[parent])
    multi_scan_parser.add_argument("--symbol", default=None)
    multi_scan_parser.add_argument(
        "--category",
        choices=("CORE_LIVE", "CORE_WATCH", "RELATIVE_STRENGTH", "LIQUID_MAJOR", "HIGH_BETA"),
        default=None,
    )
    multi_scan_parser.add_argument("--limit", type=int, default=50)
    multi_scan_parser.add_argument("--write", action="store_true")

    multi_scans_parser = subparsers.add_parser("multi-symbol-scans", parents=[parent])
    multi_scans_parser.add_argument("--limit", type=int, default=50)
    multi_scans_parser.add_argument("--symbol", default=None)
    multi_scans_parser.add_argument(
        "--category",
        choices=("CORE_LIVE", "CORE_WATCH", "RELATIVE_STRENGTH", "LIQUID_MAJOR", "HIGH_BETA"),
        default=None,
    )
    multi_scans_parser.add_argument("--status", default=None)

    subparsers.add_parser("multi-symbol-summary", parents=[parent])

    market_summary_parser = subparsers.add_parser("market-intelligence-summary", parents=[parent])
    market_summary_parser.add_argument("--use-network", action="store_true")
    market_summary_parser.add_argument("--write", action="store_true")
    market_summary_parser.add_argument("--limit", type=int, default=20)

    market_rankings_parser = subparsers.add_parser("market-intelligence-rankings", parents=[parent])
    market_rankings_parser.add_argument("--use-network", action="store_true")
    market_rankings_parser.add_argument(
        "--category",
        choices=("CORE_LIVE", "CORE_WATCH", "RELATIVE_STRENGTH", "LIQUID_MAJOR", "HIGH_BETA"),
        default=None,
    )
    market_rankings_parser.add_argument("--limit", type=int, default=20)

    ethbtc_rotation_parser = subparsers.add_parser("ethbtc-rotation", parents=[parent])
    ethbtc_rotation_parser.add_argument("--use-network", action="store_true")

    market_snapshots_parser = subparsers.add_parser("market-intelligence-snapshots", parents=[parent])
    market_snapshots_parser.add_argument("--limit", type=int, default=50)

    eth_candidate_parser = subparsers.add_parser("eth-paper-candidate", parents=[parent])
    eth_candidate_parser.add_argument("--use-network", action="store_true")
    eth_candidate_parser.add_argument("--write", action="store_true")

    eth_candidates_parser = subparsers.add_parser("eth-paper-candidates", parents=[parent])
    eth_candidates_parser.add_argument("--limit", type=int, default=50)
    eth_candidates_parser.add_argument("--status", default=None)

    subparsers.add_parser("eth-paper-summary", parents=[parent])

    eth_outcome_parser = subparsers.add_parser("eth-paper-outcome", parents=[parent])
    eth_outcome_parser.add_argument("--candidate-id", default=None)
    eth_outcome_parser.add_argument("--write", action="store_true")

    eth_outcomes_parser = subparsers.add_parser("eth-paper-outcomes", parents=[parent])
    eth_outcomes_parser.add_argument("--limit", type=int, default=50)
    eth_outcomes_parser.add_argument("--status", default=None)
    eth_outcomes_parser.add_argument("--candidate-id", default=None)

    subparsers.add_parser("eth-paper-outcome-summary", parents=[parent])

    subparsers.add_parser("paper-refresh-status", parents=[parent])

    paper_refresh_run_parser = subparsers.add_parser("paper-refresh-run", parents=[parent])
    paper_refresh_run_parser.add_argument("--tasks", default=None)
    paper_refresh_run_parser.add_argument("--use-network", action="store_true")
    paper_refresh_run_parser.add_argument("--no-write", action="store_true")
    paper_refresh_run_parser.add_argument("--send-notifications", action="store_true")

    paper_refresh_runs_parser = subparsers.add_parser("paper-refresh-runs", parents=[parent])
    paper_refresh_runs_parser.add_argument("--limit", type=int, default=50)

    return parser


@dataclass(frozen=True)
class RankedCandidate:
    signal: SignalRecord
    score: int
    tier: str
    note: str


@dataclass(frozen=True)
class LiveCandidateCheck:
    candidate: RankedCandidate
    decision: str
    reason: str
    entry: float | None
    stop: float | None
    take_profit: float | None
    age_minutes: float | None
    fresh_minutes: int
    freshness_status: str
    risk_distance_pct: float | None
    theoretical_max_position_usd: float | None
    capped_max_position_usd: float | None
    max_position_cap_usd: float
    max_leverage: float
    suggested_leverage: float


@dataclass(frozen=True)
class BetrayalCandidate:
    signal: SignalRecord
    score: int
    tier: str
    shadow_direction: str
    age_minutes: float | None
    reasons: list[str]
    original_outcome_summary: str


def _has_any_r9_metadata(signal: object) -> bool:
    return any(
        [
            getattr(signal, "rsi_value", None) is not None,
            getattr(signal, "rsi_state", None) is not None,
            getattr(signal, "divergence_type", None) is not None,
            bool(getattr(signal, "divergence_confirmed", False)),
            bool(getattr(signal, "extreme_trigger", False)),
            bool(getattr(signal, "critical_trigger", False)),
            bool(getattr(signal, "micro_scalp_candidate", False)),
            bool(getattr(signal, "requires_human_approval", False)),
        ]
    )


def _format_r9_metadata(signal: object) -> str:
    rsi_value = getattr(signal, "rsi_value", None)
    rsi_text = "missing" if rsi_value is None else f"{float(rsi_value):.2f}"
    rsi_state = getattr(signal, "rsi_state", None) or "missing"
    divergence_type = getattr(signal, "divergence_type", None) or "missing"
    divergence_confirmed = "Y" if getattr(signal, "divergence_confirmed", False) else "N"
    extreme_trigger = "Y" if getattr(signal, "extreme_trigger", False) else "N"
    critical_trigger = "Y" if getattr(signal, "critical_trigger", False) else "N"
    micro_scalp_candidate = "Y" if getattr(signal, "micro_scalp_candidate", False) else "N"
    requires_human_approval = "Y" if getattr(signal, "requires_human_approval", False) else "N"
    return (
        f" | rsi={rsi_text} | rsi_state={rsi_state} | div={divergence_type}"
        f" | div_confirmed={divergence_confirmed} | extreme={extreme_trigger}"
        f" | critical={critical_trigger} | micro_scalp={micro_scalp_candidate}"
        f" | human_approval={requires_human_approval}"
    )


def _format_rows(title: str, rows: list[tuple[str, str]], *, limit: int | None) -> str:
    if not rows:
        return f"{title}\nno records"

    ordered_lines = [line for _sort_key, line in reversed(rows)]
    if limit is not None:
        ordered_lines = ordered_lines[: max(limit, 0)]
    return "\n".join([title, *ordered_lines])


def _filter_symbol(records: list, symbol: str | None) -> list:
    if symbol is None:
        return records
    return [record for record in records if getattr(record, "symbol", None) == symbol]


def _timestamp_in_window(timestamp: str, start: datetime, end: datetime) -> bool:
    parsed = _parse_timestamp(timestamp)
    if parsed is None:
        return True
    return start <= parsed <= end


def _parse_timestamp(timestamp: str | None) -> datetime | None:
    if not timestamp:
        return None
    try:
        normalized = timestamp.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _r9_coverage(signals: list[SignalRecord]) -> float:
    if not signals:
        return 0.0
    return (sum(1 for signal in signals if _has_any_r9_metadata(signal)) / len(signals)) * 100.0


def _latest_signal_direction_timeframe(signal: SignalRecord | None) -> str:
    if signal is None:
        return "n/a"
    return f"{signal.direction}/{signal.timeframe}"


def _performance_summary(outcomes: list[OutcomeRecord]) -> dict[str, float]:
    total = len(outcomes)
    filled = [outcome for outcome in outcomes if _is_filled_outcome(outcome)]
    winners = [outcome for outcome in filled if outcome.pnl_pct > 0.0]
    return {
        "fill_rate": (len(filled) / total) * 100.0 if total else 0.0,
        "win_rate_on_filled": (len(winners) / len(filled)) * 100.0 if filled else 0.0,
        "avg_pnl_pct": _average([outcome.pnl_pct for outcome in filled]),
        "avg_mae_pct": _average([outcome.mae_pct for outcome in filled]),
        "avg_mfe_pct": _average([outcome.mfe_pct for outcome in filled]),
    }


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _is_filled_outcome(outcome: OutcomeRecord) -> bool:
    return outcome.fill_status in {"filled", "partial"}


def _best_grouping(signals: list[SignalRecord], outcomes: list[OutcomeRecord], group_key: str) -> str:
    signal_by_id = {signal.signal_id: signal for signal in signals}
    grouped: dict[str, list[OutcomeRecord]] = defaultdict(list)
    for outcome in outcomes:
        signal = signal_by_id.get(outcome.signal_id)
        if signal is None or not _is_filled_outcome(outcome):
            continue
        grouped[_signal_group_value(signal, group_key)].append(outcome)
    return _format_best_outcome_group(grouped)


def _best_outcome_grouping(outcomes: list[OutcomeRecord], group_key: str) -> str:
    grouped: dict[str, list[OutcomeRecord]] = defaultdict(list)
    for outcome in outcomes:
        if not _is_filled_outcome(outcome):
            continue
        grouped[str(getattr(outcome, group_key, "missing") or "missing")].append(outcome)
    return _format_best_outcome_group(grouped)


def _signal_group_value(signal: SignalRecord, group_key: str) -> str:
    if group_key == "rsi_state":
        return signal.rsi_state or "missing"
    if group_key == "divergence":
        divergence_type = signal.divergence_type or "none"
        confirmed = "Y" if signal.divergence_confirmed else "N"
        return f"{divergence_type}|confirmed={confirmed}"
    if group_key == "timeframe":
        return signal.timeframe
    return "missing"


def _format_best_outcome_group(grouped: dict[str, list[OutcomeRecord]]) -> str:
    if not grouped:
        return "n/a"
    rows = []
    for key, group_outcomes in grouped.items():
        avg_pnl = _average([outcome.pnl_pct for outcome in group_outcomes])
        rows.append((avg_pnl, key, len(group_outcomes)))
    avg_pnl, key, count = sorted(rows, reverse=True)[0]
    return f"{key} avg_pnl={avg_pnl:.4f}% samples={count}"


def _positions_by_signal(closed_positions: list[PaperPosition]) -> dict[str, list[PaperPosition]]:
    grouped: dict[str, list[PaperPosition]] = defaultdict(list)
    for position in closed_positions:
        grouped[position.signal_id].append(position)
    return dict(grouped)


def _rank_candidate(signal: SignalRecord, closed_positions: list[PaperPosition]) -> RankedCandidate:
    score = 0
    reasons: list[str] = []

    if signal.tradable:
        score += 40
        reasons.append("tradable")
    else:
        score -= 25
    if signal.reject_reason:
        score -= 15
    if signal.divergence_confirmed and signal.divergence_type == "bullish" and signal.direction == "long":
        score += 20
        reasons.append("bullish divergence confirmed")
    elif signal.divergence_confirmed and signal.divergence_type == "bearish" and signal.direction == "short":
        score += 20
        reasons.append("bearish divergence confirmed")
    elif not signal.divergence_confirmed:
        score -= 10
    if signal.rsi_state == "neutral":
        score += 5
        reasons.append("neutral RSI")
    if signal.rsi_state == "oversold" and signal.direction == "long":
        if signal.divergence_confirmed:
            score += 5
        else:
            score -= 15
    if signal.rsi_state == "overbought" and signal.direction == "short":
        if signal.divergence_confirmed:
            score += 5
        else:
            score -= 15
    if signal.bias_aligned:
        score += 15
        reasons.append("bias aligned")
    else:
        score -= 20
    if signal.hammer_strength >= 85:
        score += 10
    if signal.hammer_strength >= 95:
        score += 10
    if signal.timeframe in DAILY_EXECUTION_TIMEFRAMES:
        score += 5
    if signal.timeframe in HIGH_TIMEFRAMES:
        score -= 10
    if any(position.close_reason == "take_profit" for position in closed_positions):
        score += 10

    tier = _score_tier(score)
    note = _operator_note(signal, reasons)
    return RankedCandidate(signal=signal, score=score, tier=tier, note=note)


def _score_tier(score: int) -> str:
    if score >= 80:
        return "ACTIONABLE_PAPER_CANDIDATE"
    if score >= 60:
        return "WATCHLIST"
    if score >= 40:
        return "CONTEXT_ONLY"
    return "IGNORE"


def _operator_note(signal: SignalRecord, reasons: list[str]) -> str:
    if not signal.tradable and signal.reject_reason:
        return f"Watch only: rejected by {signal.reject_reason}."
    if signal.rsi_state == "oversold" and not signal.divergence_confirmed:
        return "Avoid for now: oversold bucket has weak forward performance without confirmation."
    if signal.bias_aligned is False:
        return "Watch only: strong hammer but rejected by bias."
    if signal.tradable and signal.divergence_confirmed:
        reason_text = ", ".join(reasons) if reasons else "confirmed setup"
        return f"Possible {signal.direction} candidate: {reason_text}."
    return "Context only: wait for stronger confirmation."


def _format_candidate_lines(index: int, candidate: RankedCandidate) -> list[str]:
    signal = candidate.signal
    take_profit = _calculate_report_take_profit(signal)
    return [
        f"rank: {index}",
        f"tier: {candidate.tier}",
        f"score: {candidate.score}",
        f"signal_id: {signal.signal_id}",
        f"timestamp: {signal.timestamp}",
        f"symbol: {signal.symbol}",
        f"timeframe: {signal.timeframe}",
        f"direction: {signal.direction}",
        f"tradable: {signal.tradable}",
        f"reject_reason: {signal.reject_reason or 'n/a'}",
        f"entry: {signal.fib_618:.4f}",
        f"stop/invalidation: {signal.invalidation:.4f}",
        f"take_profit: {_format_optional_float(take_profit)}",
        f"rsi: {_format_optional_float(signal.rsi_value)} state={signal.rsi_state or 'missing'}",
        f"divergence: type={signal.divergence_type or 'missing'} confirmed={signal.divergence_confirmed}",
        f"trigger_flags: extreme={signal.extreme_trigger} critical={signal.critical_trigger} micro_scalp={signal.micro_scalp_candidate} human_approval={signal.requires_human_approval}",
        f"bias: direction={signal.bias_direction} aligned={signal.bias_aligned}",
        f"hammer_strength: {signal.hammer_strength:.2f}",
        f"suggested_operator_note: {candidate.note}",
        "",
    ]


def _build_live_check(
    candidate: RankedCandidate,
    *,
    generated_at: datetime,
    min_score: int,
    allow_short: bool,
    allow_oversold: bool,
    allow_trigger_flags: bool,
    allow_expired: bool,
    max_risk_usd: float,
    max_leverage: float,
    max_position_usd: float,
    fresh_minutes: int,
) -> LiveCandidateCheck:
    signal = candidate.signal
    entry = _positive_float_or_none(signal.fib_618)
    stop = _positive_float_or_none(signal.invalidation)
    take_profit = _calculate_report_take_profit(signal)
    age_minutes = _candidate_age_minutes(signal, generated_at)
    fresh_gate_minutes = max(fresh_minutes, 0)
    freshness_status = _freshness_status(age_minutes, fresh_gate_minutes)
    risk_distance_pct = _risk_distance_pct(entry, stop)
    theoretical_max_position_usd = (
        max_risk_usd / (risk_distance_pct / 100.0)
        if risk_distance_pct is not None and risk_distance_pct > 0.0
        else None
    )
    capped_max_position_usd = (
        min(theoretical_max_position_usd, float(max_position_usd))
        if theoretical_max_position_usd is not None
        else None
    )

    decision, reason = _live_decision_reason(
        candidate,
        entry=entry,
        stop=stop,
        take_profit=take_profit,
        freshness_status=freshness_status,
        risk_distance_pct=risk_distance_pct,
        min_score=min_score,
        allow_short=allow_short,
        allow_oversold=allow_oversold,
        allow_trigger_flags=allow_trigger_flags,
        allow_expired=allow_expired,
    )
    suggested_leverage = _suggested_leverage(candidate.score, decision=decision, max_leverage=max_leverage)
    return LiveCandidateCheck(
        candidate=candidate,
        decision=decision,
        reason=reason,
        entry=entry,
        stop=stop,
        take_profit=take_profit,
        age_minutes=age_minutes,
        fresh_minutes=fresh_gate_minutes,
        freshness_status=freshness_status,
        risk_distance_pct=risk_distance_pct,
        theoretical_max_position_usd=theoretical_max_position_usd,
        capped_max_position_usd=capped_max_position_usd,
        max_position_cap_usd=float(max_position_usd),
        max_leverage=max_leverage,
        suggested_leverage=suggested_leverage,
    )


def _live_decision_reason(
    candidate: RankedCandidate,
    *,
    entry: float | None,
    stop: float | None,
    take_profit: float | None,
    freshness_status: str,
    risk_distance_pct: float | None,
    min_score: int,
    allow_short: bool,
    allow_oversold: bool,
    allow_trigger_flags: bool,
    allow_expired: bool,
) -> tuple[str, str]:
    signal = candidate.signal
    if not signal.tradable:
        return LIVE_DECISION_FORBIDDEN, "not tradable"
    if signal.reject_reason:
        return LIVE_DECISION_FORBIDDEN, f"reject_reason present: {signal.reject_reason}"
    if not signal.bias_aligned:
        return LIVE_DECISION_FORBIDDEN, "bias not aligned"
    if not _has_any_r9_metadata(signal):
        return LIVE_DECISION_FORBIDDEN, "missing R9 metadata"
    if entry is None:
        return LIVE_DECISION_FORBIDDEN, "missing entry"
    if stop is None:
        return LIVE_DECISION_FORBIDDEN, "missing stop/invalidation"
    if risk_distance_pct is None or risk_distance_pct <= 0.0:
        return LIVE_DECISION_FORBIDDEN, "no clear invalidation risk distance"
    if take_profit is None:
        return LIVE_DECISION_FORBIDDEN, "missing take_profit"
    if candidate.tier != "ACTIONABLE_PAPER_CANDIDATE":
        return LIVE_DECISION_PAPER_ONLY, f"candidate tier is {candidate.tier}"
    if candidate.score < min_score:
        return LIVE_DECISION_PAPER_ONLY, f"score below min_score {min_score}"
    if signal.direction == "short" and not allow_short:
        return LIVE_DECISION_PAPER_ONLY, "short candidate requires --allow-short"
    if signal.direction != "long" and signal.direction != "short":
        return LIVE_DECISION_FORBIDDEN, f"unsupported direction: {signal.direction}"
    if signal.rsi_state == "oversold":
        if not allow_oversold:
            return LIVE_DECISION_PAPER_ONLY, "oversold candidate requires --allow-oversold"
        if not (signal.direction == "long" and signal.divergence_type == "bullish" and signal.divergence_confirmed):
            return LIVE_DECISION_PAPER_ONLY, "oversold candidate lacks confirmed bullish divergence"
    elif signal.rsi_state != "neutral":
        return LIVE_DECISION_PAPER_ONLY, f"RSI state {signal.rsi_state or 'missing'} is not neutral"
    if (
        signal.extreme_trigger
        or signal.critical_trigger
        or signal.micro_scalp_candidate
        or signal.requires_human_approval
    ) and not allow_trigger_flags:
        return LIVE_DECISION_PAPER_ONLY, "trigger flags require explicit override"
    if freshness_status == "expired" and not allow_expired:
        return LIVE_DECISION_PAPER_ONLY, "candidate expired by freshness gate"
    return LIVE_DECISION_ELIGIBLE, "passes conservative manual tiny-live checklist"


def _format_live_check_lines(index: int, check: LiveCandidateCheck) -> list[str]:
    signal = check.candidate.signal
    return [
        f"rank: {index}",
        f"decision: {check.decision}",
        f"reason: {check.reason}",
        f"signal_id: {signal.signal_id}",
        f"score: {check.candidate.score}",
        f"tier: {check.candidate.tier}",
        f"direction/timeframe: {signal.direction}/{signal.timeframe}",
        f"age_minutes: {_format_optional_float(check.age_minutes)}",
        f"fresh_gate_minutes: {check.fresh_minutes}",
        f"freshness_status: {check.freshness_status}",
        f"entry: {_format_optional_float(check.entry)}",
        f"stop: {_format_optional_float(check.stop)}",
        f"take_profit: {_format_optional_float(check.take_profit)}",
        f"estimated_risk_distance_pct: {_format_optional_float(check.risk_distance_pct)}%",
        f"theoretical_max_position_size_usd: {_format_optional_float(check.theoretical_max_position_usd)}",
        f"capped_max_position_size_usd: {_format_optional_float(check.capped_max_position_usd)}",
        f"suggested_max_position_size_usd: {_format_optional_float(check.capped_max_position_usd)}",
        f"max_position_cap_usd: {check.max_position_cap_usd:.2f}",
        f"suggested_max_leverage_cap: {check.max_leverage:.2f}",
        f"suggested_leverage: {check.suggested_leverage:.2f}",
        "required_manual_checklist: isolated margin; set stop before or immediately after entry; set take profit; confirm max daily loss not breached; screenshot entry; write reason before entry; review after exit",
        "",
    ]


def _build_betrayal_candidate(
    signal: SignalRecord,
    *,
    generated_at: datetime,
    outcomes: list[OutcomeRecord],
) -> BetrayalCandidate:
    score = 0
    reasons: list[str] = []
    opposite_direction = _opposite_direction(signal.direction)

    if not signal.bias_aligned:
        score += 25
        reasons.append("bias_aligned=false")
    if signal.direction == "long" and signal.bias_direction == "bearish":
        score += 20
        reasons.append("long signal against bearish bias")
    if signal.direction == "short" and signal.bias_direction == "bullish":
        score += 20
        reasons.append("short signal against bullish bias")
    if _trend_opposes_signal(signal):
        score += 15
        reasons.append(f"trend_direction opposes signal: {signal.trend_direction}")
    if signal.divergence_type is None or not signal.divergence_confirmed:
        score += 15
        reasons.append("divergence missing or not confirmed")
    if signal.rsi_value is None and signal.rsi_state is None:
        score += 5
        reasons.append("RSI missing")
    if signal.hammer_strength < 85:
        score += 10
        reasons.append("hammer_strength below 85")
    if signal.reject_reason:
        score += 10
        reasons.append(f"reject_reason present: {signal.reject_reason}")
    if signal.reject_reason == "strength_below_minimum":
        score += 10
        reasons.append("reject_reason is strength_below_minimum")
    if not signal.tradable:
        score += 10
        reasons.append("signal was not tradable")

    if signal.tradable:
        score -= 20
    if signal.bias_aligned:
        score -= 15
    if _divergence_confirms_signal(signal):
        score -= 10
    if signal.hammer_strength >= 95:
        score -= 10

    clamped_score = max(0, min(100, score))
    if not reasons:
        reasons.append("original signal is strong and aligned")

    return BetrayalCandidate(
        signal=signal,
        score=clamped_score,
        tier=_betrayal_tier(clamped_score),
        shadow_direction=opposite_direction,
        age_minutes=_candidate_age_minutes(signal, generated_at),
        reasons=reasons,
        original_outcome_summary=_format_original_outcome_summary(outcomes),
    )


def _betrayal_tier(score: int) -> str:
    if score >= 80:
        return BETRAYAL_STRONG
    if score >= 60:
        return BETRAYAL_WATCH
    if score >= 40:
        return BETRAYAL_WEAK
    return BETRAYAL_IGNORE


def _opposite_direction(direction: str) -> str:
    if direction == "long":
        return "short"
    if direction == "short":
        return "long"
    return "unknown"


def _trend_opposes_signal(signal: SignalRecord) -> bool:
    return (
        (signal.direction == "long" and signal.trend_direction == "bearish")
        or (signal.direction == "short" and signal.trend_direction == "bullish")
    )


def _divergence_confirms_signal(signal: SignalRecord) -> bool:
    return (
        (signal.direction == "long" and signal.divergence_type == "bullish" and signal.divergence_confirmed)
        or (signal.direction == "short" and signal.divergence_type == "bearish" and signal.divergence_confirmed)
    )


def _outcomes_by_signal(outcomes: list[OutcomeRecord]) -> dict[str, list[OutcomeRecord]]:
    grouped: dict[str, list[OutcomeRecord]] = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome.signal_id].append(outcome)
    return dict(grouped)


def _format_original_outcome_summary(outcomes: list[OutcomeRecord]) -> str:
    if not outcomes:
        return "original outcome not available; opposite outcome not available yet"
    filled = [outcome for outcome in outcomes if _is_filled_outcome(outcome)]
    wins = [outcome for outcome in filled if outcome.pnl_pct > 0.0]
    return (
        f"original samples={len(outcomes)} fills={len(filled)} wins={len(wins)} "
        f"avg_pnl={_average([outcome.pnl_pct for outcome in filled]):.4f}%; "
        "opposite outcome not available yet"
    )


def _format_betrayal_candidate_lines(index: int, candidate: BetrayalCandidate) -> list[str]:
    signal = candidate.signal
    take_profit = _calculate_report_take_profit(signal)
    return [
        f"rank: {index}",
        f"betrayal_tier: {candidate.tier}",
        f"betrayal_score: {candidate.score}",
        f"signal_id: {signal.signal_id}",
        f"timestamp: {signal.timestamp}",
        f"age_minutes: {_format_optional_float(candidate.age_minutes)}",
        f"original_direction/timeframe: {signal.direction}/{signal.timeframe}",
        f"shadow_direction: {candidate.shadow_direction}",
        f"tradable_original_signal: {'yes' if signal.tradable else 'no'}",
        f"reject_reason: {signal.reject_reason or 'n/a'}",
        f"bias: direction={signal.bias_direction} aligned={signal.bias_aligned}",
        f"trend_direction: {signal.trend_direction or 'missing'}",
        f"rsi: {_format_optional_float(signal.rsi_value)} state={signal.rsi_state or 'missing'}",
        f"divergence: type={signal.divergence_type or 'missing'} confirmed={signal.divergence_confirmed}",
        f"hammer_strength: {signal.hammer_strength:.2f}",
        f"entry: {signal.fib_618:.4f}",
        f"stop/invalidation: {signal.invalidation:.4f}",
        f"take_profit: {_format_optional_float(take_profit)}",
        f"betrayal_reasons: {', '.join(candidate.reasons)}",
        f"shadow_outcome_evaluation: {candidate.original_outcome_summary}",
        f"operator_note: {_betrayal_operator_note(candidate)}",
        "",
    ]


def _betrayal_operator_note(candidate: BetrayalCandidate) -> str:
    signal = candidate.signal
    if candidate.tier == BETRAYAL_IGNORE:
        return "Ignore: original signal is strong and aligned."
    if candidate.shadow_direction == "short":
        return f"Shadow short watch: {', '.join(candidate.reasons[:3])}."
    if candidate.shadow_direction == "long":
        return f"Shadow long watch: {', '.join(candidate.reasons[:3])}."
    return "Shadow watch: contradiction detected, but direction is unknown."


def _calculate_report_take_profit(signal: SignalRecord) -> float | None:
    entry = _positive_float_or_none(signal.fib_618)
    stop = _positive_float_or_none(signal.invalidation)
    if entry is None or stop is None:
        return None
    risk = abs(entry - stop)
    if risk <= 0.0:
        return None
    if signal.direction == "short":
        return round(entry - risk, 4)
    return round(entry + risk, 4)


def _positive_float_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    if value <= 0.0:
        return None
    return value


def _risk_distance_pct(entry: float | None, stop: float | None) -> float | None:
    if entry is None or stop is None or entry <= 0.0:
        return None
    risk_distance_pct = abs(entry - stop) / entry * 100.0
    if risk_distance_pct <= 0.0:
        return None
    return risk_distance_pct


def _freshest_signal(signals: list[SignalRecord]) -> SignalRecord | None:
    if not signals:
        return None
    return max(signals, key=lambda signal: signal.timestamp)


def _candidate_age_minutes(signal: SignalRecord | None, generated_at: datetime) -> float | None:
    if signal is None:
        return None
    timestamp = _parse_timestamp(signal.timestamp)
    if timestamp is None:
        return None
    age_seconds = (generated_at - timestamp).total_seconds()
    return max(age_seconds / 60.0, 0.0)


def _freshness_status(age_minutes: float | None, fresh_minutes: int) -> str:
    if age_minutes is None:
        return "expired"
    return "fresh" if age_minutes <= fresh_minutes else "expired"


def _suggested_leverage(score: int, *, decision: str, max_leverage: float) -> float:
    if decision != LIVE_DECISION_ELIGIBLE:
        return 0.0
    leverage_cap = max(float(max_leverage), 0.0)
    if score >= 120:
        return min(5.0, leverage_cap)
    if score >= 100:
        return min(3.0, leverage_cap)
    return min(2.0, leverage_cap)


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


if __name__ == "__main__":
    raise SystemExit(main())
