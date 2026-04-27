"""Local CLI inspection views for Hammer Radar NDJSON state."""

from __future__ import annotations

import argparse
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
    log_dir: str | Path | None = None,
) -> str:
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
    performance = _performance_summary(outcomes)
    ranked = [
        _rank_candidate(signal, positions_by_signal.get(signal.signal_id, []))
        for signal in window_signals
    ]
    ranked.sort(key=lambda candidate: (candidate.score, candidate.signal.timestamp), reverse=True)
    ranked = ranked[: max(limit, 0)]
    checks = [
        _build_live_check(
            candidate,
            min_score=min_score,
            allow_short=allow_short,
            allow_oversold=allow_oversold,
            allow_trigger_flags=allow_trigger_flags,
            max_risk_usd=max_risk_usd,
            max_leverage=max_leverage,
        )
        for candidate in ranked
    ]
    decisions = [check.decision for check in checks]

    lines = [
        "HAMMER RADAR MANUAL TINY-LIVE CHECKLIST",
        "",
        "1. HEADER",
        f"archive_log_dir: {resolved_log_dir}",
        f"generated_at: {generated_at.isoformat()}",
        f"symbol: {symbol or 'all'}",
        f"signal_window: last_{max(since_hours, 0)}h ({signal_window_start.isoformat()} to {generated_at.isoformat()})",
        f"min_score: {min_score}",
        f"max_risk_usd: {float(max_risk_usd):.2f}",
        f"max_leverage: {float(max_leverage):.2f}",
        f"allow_short: {allow_short}",
        f"allow_oversold: {allow_oversold}",
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
                log_dir=args.log_dir,
            )
        )
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
    risk_distance_pct: float | None
    max_position_usd: float | None
    max_leverage: float


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
    min_score: int,
    allow_short: bool,
    allow_oversold: bool,
    allow_trigger_flags: bool,
    max_risk_usd: float,
    max_leverage: float,
) -> LiveCandidateCheck:
    signal = candidate.signal
    entry = _positive_float_or_none(signal.fib_618)
    stop = _positive_float_or_none(signal.invalidation)
    take_profit = _calculate_report_take_profit(signal)
    risk_distance_pct = _risk_distance_pct(entry, stop)
    max_position_usd = (
        max_risk_usd / (risk_distance_pct / 100.0)
        if risk_distance_pct is not None and risk_distance_pct > 0.0
        else None
    )

    decision, reason = _live_decision_reason(
        candidate,
        entry=entry,
        stop=stop,
        take_profit=take_profit,
        risk_distance_pct=risk_distance_pct,
        min_score=min_score,
        allow_short=allow_short,
        allow_oversold=allow_oversold,
        allow_trigger_flags=allow_trigger_flags,
    )
    return LiveCandidateCheck(
        candidate=candidate,
        decision=decision,
        reason=reason,
        entry=entry,
        stop=stop,
        take_profit=take_profit,
        risk_distance_pct=risk_distance_pct,
        max_position_usd=max_position_usd,
        max_leverage=max_leverage,
    )


def _live_decision_reason(
    candidate: RankedCandidate,
    *,
    entry: float | None,
    stop: float | None,
    take_profit: float | None,
    risk_distance_pct: float | None,
    min_score: int,
    allow_short: bool,
    allow_oversold: bool,
    allow_trigger_flags: bool,
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
        f"entry: {_format_optional_float(check.entry)}",
        f"stop: {_format_optional_float(check.stop)}",
        f"take_profit: {_format_optional_float(check.take_profit)}",
        f"estimated_risk_distance_pct: {_format_optional_float(check.risk_distance_pct)}%",
        f"suggested_max_position_size_usd: {_format_optional_float(check.max_position_usd)}",
        f"suggested_max_leverage_cap: {check.max_leverage:.2f}",
        "required_manual_checklist: isolated margin; set stop before or immediately after entry; set take profit; confirm max daily loss not breached; screenshot entry; write reason before entry; review after exit",
        "",
    ]


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


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


if __name__ == "__main__":
    raise SystemExit(main())
