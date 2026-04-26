"""Local CLI inspection views for Hammer Radar NDJSON state."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.app.hammer_radar.operator.archive import get_log_dir, load_outcomes, load_signals
from src.app.hammer_radar.operator.positions import (
    load_closed_positions,
    load_open_positions,
    load_position_events,
    load_positions,
)


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

    return parser


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


if __name__ == "__main__":
    raise SystemExit(main())
