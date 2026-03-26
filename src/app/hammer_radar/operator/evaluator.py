"""Outcome evaluation for Hammer Radar operator signals."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord


def evaluate_signal_on_next_candle(signal: SignalRecord, next_candle: dict[str, Any]) -> OutcomeRecord | None:
    """Evaluate a 13m signal using the immediately following closed candle."""
    if signal.timeframe != "13m":
        return None

    entry_price = float(signal.fib_618)
    high_price = float(next_candle["high"])
    low_price = float(next_candle["low"])
    close_price = float(next_candle["close"])

    if signal.direction == "long":
        filled = low_price <= entry_price
        stop_hit = low_price < signal.invalidation
        mae_pct = _pct_move(entry_price, min(low_price, entry_price), direction="long", favorable=False)
        mfe_pct = _pct_move(entry_price, max(high_price, entry_price), direction="long", favorable=True)
        exit_price = signal.invalidation if stop_hit and filled else close_price if filled else None
        pnl_pct = _signed_pnl_pct(entry_price, exit_price, direction="long") if exit_price is not None else 0.0
    else:
        filled = high_price >= entry_price
        stop_hit = high_price > signal.invalidation
        mae_pct = _pct_move(entry_price, max(high_price, entry_price), direction="short", favorable=False)
        mfe_pct = _pct_move(entry_price, min(low_price, entry_price), direction="short", favorable=True)
        exit_price = signal.invalidation if stop_hit and filled else close_price if filled else None
        pnl_pct = _signed_pnl_pct(entry_price, exit_price, direction="short") if exit_price is not None else 0.0

    fill_status = "filled" if filled else "no_fill"
    if not filled:
        outcome = "no_trade"
    elif stop_hit:
        outcome = "stopped"
    elif pnl_pct > 0:
        outcome = "win"
    elif pnl_pct < 0:
        outcome = "loss"
    else:
        outcome = "flat"

    return OutcomeRecord(
        signal_id=signal.signal_id,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        direction=signal.direction,
        timestamp=str(next_candle["timestamp"]),
        entry_price=entry_price,
        exit_price=exit_price,
        fill_status=fill_status,
        outcome=outcome,
        mae_pct=round(mae_pct, 4),
        mfe_pct=round(mfe_pct, 4),
        pnl_pct=round(pnl_pct, 4),
        stop_hit=bool(stop_hit and filled),
        evaluated_at=datetime.now(timezone.utc).isoformat(),
    )


def _signed_pnl_pct(entry_price: float, exit_price: float, direction: str) -> float:
    if entry_price == 0.0:
        return 0.0
    if direction == "long":
        return ((exit_price - entry_price) / entry_price) * 100.0
    return ((entry_price - exit_price) / entry_price) * 100.0


def _pct_move(entry_price: float, probe_price: float, direction: str, favorable: bool) -> float:
    if entry_price == 0.0:
        return 0.0
    if direction == "long":
        delta = probe_price - entry_price
    else:
        delta = entry_price - probe_price
    if favorable:
        return max(delta, 0.0) / entry_price * 100.0
    return max(-delta, 0.0) / entry_price * 100.0
