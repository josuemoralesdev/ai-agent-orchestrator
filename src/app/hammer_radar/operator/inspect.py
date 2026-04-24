"""Local CLI inspection views for Hammer Radar NDJSON state."""

from __future__ import annotations

import argparse

from src.app.hammer_radar.operator.archive import load_outcomes, load_signals
from src.app.hammer_radar.operator.positions import (
    load_closed_positions,
    load_open_positions,
    load_position_events,
    load_positions,
)


def build_summary_text() -> str:
    signals = load_signals()
    outcomes = load_outcomes()
    positions = load_positions()
    open_positions = [position for position in positions if position.status == "open"]
    closed_positions = [position for position in positions if position.status == "closed"]
    events = load_position_events()
    closed_pnl_usd = round(sum(position.pnl_usd or 0.0 for position in closed_positions), 4)
    closed_pnl_pct = round(sum(position.pnl_pct or 0.0 for position in closed_positions), 4)
    last_signal_timestamp = signals[-1].timestamp if signals else "n/a"
    last_position_event_timestamp = events[-1].timestamp if events else "n/a"

    lines = [
        "HAMMER RADAR SUMMARY",
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


def build_signals_text(limit: int) -> str:
    signals = load_signals()
    rows = [
        (
            signal.timestamp,
            f"{signal.signal_id} | {signal.symbol} | {signal.timeframe} | {signal.direction.upper()} | "
            f"tradable={'Y' if signal.tradable else 'N'} | entry={signal.fib_618:.2f} | stop={signal.invalidation:.2f}"
        )
        for signal in signals
    ]
    return _format_rows("HAMMER RADAR SIGNALS", rows, limit=limit)


def build_outcomes_text(limit: int) -> str:
    outcomes = load_outcomes()
    rows = [
        (
            outcome.evaluated_at,
            f"{outcome.signal_id} | {outcome.timeframe} | {outcome.direction.upper()} | entry={outcome.entry_mode} | "
            f"fill={outcome.fill_status} | outcome={outcome.outcome} | pnl={outcome.pnl_pct:.4f}%"
        )
        for outcome in outcomes
    ]
    return _format_rows("HAMMER RADAR OUTCOMES", rows, limit=limit)


def build_positions_text(status: str) -> str:
    if status == "open":
        positions = load_open_positions()
    elif status == "closed":
        positions = load_closed_positions()
    else:
        positions = load_positions()

    rows: list[tuple[str, str]] = []
    for position in positions:
        line = (
            f"{position.position_id} | {position.symbol} | {position.timeframe} | {position.direction.upper()} | "
            f"{position.entry_mode} | entry={position.entry_price:.2f} | stop={position.stop_price:.2f} | "
            f"size={position.size_usd:.2f} | status={position.status}"
        )
        if position.status == "closed":
            pnl_usd = 0.0 if position.pnl_usd is None else position.pnl_usd
            close_reason = position.close_reason or "n/a"
            line += f" | pnl_usd={pnl_usd:.2f} | close_reason={close_reason}"
        rows.append((position.closed_at or position.opened_at, line))

    return _format_rows(f"HAMMER RADAR POSITIONS [{status}]", rows, limit=None)


def build_events_text(limit: int) -> str:
    events = load_position_events()
    rows = [
        (
            event.timestamp,
            f"{event.timestamp} | {event.event_type} | position={event.position_id} | signal={event.signal_id} | payload={event.payload}"
        )
        for event in events
    ]
    return _format_rows("HAMMER RADAR EVENTS", rows, limit=limit)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "summary":
        print(build_summary_text())
    elif args.command == "signals":
        print(build_signals_text(limit=args.limit))
    elif args.command == "outcomes":
        print(build_outcomes_text(limit=args.limit))
    elif args.command == "positions":
        print(build_positions_text(status=args.status))
    elif args.command == "events":
        print(build_events_text(limit=args.limit))
    else:
        parser.error(f"unsupported command: {args.command}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.inspect")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("summary")

    signals_parser = subparsers.add_parser("signals")
    signals_parser.add_argument("--limit", type=int, default=10)

    outcomes_parser = subparsers.add_parser("outcomes")
    outcomes_parser.add_argument("--limit", type=int, default=10)

    positions_parser = subparsers.add_parser("positions")
    positions_parser.add_argument("--status", choices=("open", "closed", "all"), default="all")

    events_parser = subparsers.add_parser("events")
    events_parser.add_argument("--limit", type=int, default=20)

    return parser


def _format_rows(title: str, rows: list[tuple[str, str]], *, limit: int | None) -> str:
    if not rows:
        return f"{title}\nno records"

    ordered_lines = [line for _sort_key, line in reversed(rows)]
    if limit is not None:
        ordered_lines = ordered_lines[: max(limit, 0)]
    return "\n".join([title, *ordered_lines])


if __name__ == "__main__":
    raise SystemExit(main())
