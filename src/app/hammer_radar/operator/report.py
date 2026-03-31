"""Compact console formatting for Hammer Radar operator records."""

from __future__ import annotations

from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord


def format_signal_operator_line(signal: SignalRecord) -> str:
    status = "TRADE" if signal.tradable else f"SKIP:{signal.reject_reason}"
    bias_tag = "aligned" if signal.bias_aligned else signal.bias_direction
    return (
        f"OPERATOR SIGNAL [{signal.timeframe}] {signal.symbol} {signal.direction.upper()} "
        f"t={signal.timestamp} strength={signal.hammer_strength:.2f} "
        f"bias={signal.bias_timeframe}:{bias_tag} streaks={signal.same_direction_streak}/{signal.opposite_direction_streak} "
        f"entry={signal.fib_618:.2f} invalidation={signal.invalidation:.2f} {status}"
    )


def format_outcome_line(outcome: OutcomeRecord) -> str:
    entry_text = "na" if outcome.entry_price is None else f"{outcome.entry_price:.2f}"
    exit_text = "na" if outcome.exit_price is None else f"{outcome.exit_price:.2f}"
    size_text = (
        ""
        if outcome.filled_size_fraction is None
        else f" size={outcome.filled_size_fraction:.2f}"
    )
    return (
        f"OPERATOR OUTCOME [{outcome.timeframe}] {outcome.symbol} {outcome.direction.upper()} "
        f"signal={outcome.signal_id} entry={outcome.entry_mode}{size_text} fill={outcome.fill_status} outcome={outcome.outcome} "
        f"entry={entry_text} exit={exit_text} pnl={_format_pct(outcome.pnl_pct)} "
        f"mae={_format_pct(outcome.mae_pct)} mfe={_format_pct(outcome.mfe_pct)}"
    )


def format_stats_summary(summary_rows: list[dict], top_n: int = 10, label: str = "all_evaluated_signals") -> str:
    if not summary_rows:
        return f"OPERATOR STATS [{label}] no evaluated outcomes yet"

    lines = [f"OPERATOR STATS [{label}]"]
    for row in summary_rows[:top_n]:
        lines.append(
            " | ".join(
                [
                    f"{row['timeframe']} {row['direction'].upper()}",
                    f"bias={'Y' if row['bias_aligned'] else 'N'}",
                    f"strength={row['strength_band']}",
                    f"entry={row['entry_mode']}",
                    f"samples={row['samples']}",
                    f"fills={row['fills']} ({_format_pct(row['fill_rate'], digits=2)})",
                    f"wins={row['wins']}",
                    f"losses={row['losses']}",
                    f"stops={row['stops']}",
                    f"win_rate={_format_pct(row['win_rate_on_filled'], digits=2)}",
                    f"avg_pnl={_format_pct(row['avg_pnl_pct'])}",
                ]
            )
        )
    return "\n".join(lines)


def _format_pct(value: float, digits: int = 4) -> str:
    rounded = round(float(value), digits)
    if rounded == 0.0:
        rounded = 0.0
    return f"{rounded:.{digits}f}%"
