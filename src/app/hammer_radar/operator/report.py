"""Compact console formatting for Hammer Radar operator records."""

from __future__ import annotations

from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord


def format_signal_operator_line(signal: SignalRecord) -> str:
    status = "TRADE" if signal.tradable else f"SKIP:{signal.reject_reason}"
    bias_tag = "aligned" if signal.bias_aligned else signal.bias_direction
    trend_text = ""
    if signal.trend_direction:
        trend_band = _display_trend_strength_band(signal.trend_strength_score)
        trend_text = f" trend={signal.trend_direction}/{trend_band}" if trend_band else f" trend={signal.trend_direction}"
    ema_text = ""
    if signal.price_vs_ema_4h_pct is not None:
        ema_text = f" ema4h={_format_pct(signal.price_vs_ema_4h_pct, digits=2)}"
    return (
        f"OPERATOR SIGNAL [{signal.timeframe}] {signal.symbol} {signal.direction.upper()} "
        f"t={signal.timestamp} strength={signal.hammer_strength:.2f} "
        f"bias={signal.bias_timeframe}:{bias_tag} streaks={signal.same_direction_streak}/{signal.opposite_direction_streak} "
        f"entry={signal.fib_618:.2f} invalidation={signal.invalidation:.2f}{trend_text}{ema_text} {status}"
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
                    *(
                        [f"trend={row['trend_direction']}/{row['trend_strength_band']}"]
                        if row.get("trend_direction")
                        else []
                    ),
                    *(
                        [f"ema4h={row['price_vs_ema_4h_pct_band']}"]
                        if row.get("price_vs_ema_4h_pct_band")
                        else []
                    ),
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


def _display_trend_strength_band(score: float | None) -> str:
    if score is None:
        return ""
    magnitude = abs(float(score))
    if magnitude < 0.2:
        return "weak"
    if magnitude < 0.5:
        return "medium"
    return "strong"
