"""Outcome evaluation for Hammer Radar operator signals."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord

DEFAULT_ENTRY_MODES = ("fib_618", "fib_650", "market_close", "ladder_22_44_22")
LADDER_22_44_22_WEIGHTS = (
    ("fib_50", 0.22),
    ("fib_618", 0.44),
    ("fib_650", 0.22),
)


def evaluate_signal_on_next_candle(
    signal: SignalRecord,
    next_candle: dict[str, Any],
    signal_candle: dict[str, Any] | None = None,
    entry_mode: str = "fib_618",
) -> OutcomeRecord | None:
    """Evaluate a 13m signal using the immediately following closed candle."""
    if signal.timeframe != "13m":
        return None
    if entry_mode == "ladder_22_44_22":
        return _evaluate_ladder_22_44_22(signal, next_candle)

    entry_price = _resolve_entry_price(signal, signal_candle=signal_candle, entry_mode=entry_mode)
    if entry_price is None:
        return None
    filled = _is_price_filled(signal.direction, next_candle, entry_price) if entry_mode != "market_close" else True
    return _build_outcome_record(
        signal,
        next_candle=next_candle,
        entry_price=entry_price,
        filled=filled,
        fill_status="filled" if filled else "no_fill",
        entry_mode=entry_mode,
    )


def evaluate_signal_all_entry_modes(
    signal: SignalRecord,
    next_candle: dict[str, Any],
    signal_candle: dict[str, Any] | None = None,
    entry_modes: list[str] | tuple[str, ...] | None = None,
) -> list[OutcomeRecord]:
    modes = tuple(entry_modes or DEFAULT_ENTRY_MODES)
    outcomes: list[OutcomeRecord] = []
    for entry_mode in modes:
        outcome = evaluate_signal_on_next_candle(
            signal,
            next_candle,
            signal_candle=signal_candle,
            entry_mode=entry_mode,
        )
        if outcome is not None:
            outcomes.append(outcome)
    return outcomes


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


def _evaluate_ladder_22_44_22(signal: SignalRecord, next_candle: dict[str, Any]) -> OutcomeRecord:
    tranche_prices = {level: float(getattr(signal, level)) for level, _weight in LADDER_22_44_22_WEIGHTS}
    tranche_fills = {
        level: _is_price_filled(signal.direction, next_candle, price)
        for level, price in tranche_prices.items()
    }
    filled_weights = [
        weight
        for level, weight in LADDER_22_44_22_WEIGHTS
        if tranche_fills[level]
    ]
    total_filled_weight = sum(filled_weights)

    if total_filled_weight == 0.0:
        return _build_outcome_record(
            signal,
            next_candle=next_candle,
            entry_price=None,
            filled=False,
            fill_status="no_fill",
            entry_mode="ladder_22_44_22",
            tranche_fills=tranche_fills,
            filled_size_fraction=None,
        )

    effective_entry = sum(
        tranche_prices[level] * weight
        for level, weight in LADDER_22_44_22_WEIGHTS
        if tranche_fills[level]
    ) / total_filled_weight
    fill_status = "filled" if len(filled_weights) == len(LADDER_22_44_22_WEIGHTS) else "partial"
    return _build_outcome_record(
        signal,
        next_candle=next_candle,
        entry_price=effective_entry,
        filled=True,
        fill_status=fill_status,
        entry_mode="ladder_22_44_22",
        tranche_fills=tranche_fills,
        filled_size_fraction=round(total_filled_weight, 2),
    )


def _resolve_entry_price(
    signal: SignalRecord,
    signal_candle: dict[str, Any] | None,
    entry_mode: str,
) -> float | None:
    if entry_mode == "fib_618":
        return float(signal.fib_618)
    if entry_mode == "fib_650":
        return float(signal.fib_650)
    if entry_mode == "market_close":
        if signal_candle is None or "close" not in signal_candle:
            return None
        return float(signal_candle["close"])
    raise ValueError(f"unsupported entry_mode: {entry_mode}")


def _is_price_filled(direction: str, candle: dict[str, Any], price: float) -> bool:
    if direction == "long":
        return float(candle["low"]) <= price
    return float(candle["high"]) >= price


def _is_stop_hit(signal: SignalRecord, next_candle: dict[str, Any]) -> bool:
    if signal.direction == "long":
        return float(next_candle["low"]) < signal.invalidation
    return float(next_candle["high"]) > signal.invalidation


def _build_outcome_record(
    signal: SignalRecord,
    next_candle: dict[str, Any],
    entry_price: float | None,
    filled: bool,
    fill_status: str,
    entry_mode: str,
    tranche_fills: dict[str, bool] | None = None,
    filled_size_fraction: float | None = None,
) -> OutcomeRecord:
    stop_hit = _is_stop_hit(signal, next_candle) if filled else False
    close_price = float(next_candle["close"])

    if not filled or entry_price is None:
        exit_price = None
        mae_pct = 0.0
        mfe_pct = 0.0
        pnl_pct = 0.0
        outcome = "no_trade"
    else:
        exit_price = signal.invalidation if stop_hit else close_price
        mae_pct = _adverse_excursion_pct(signal.direction, entry_price, next_candle)
        mfe_pct = _favorable_excursion_pct(signal.direction, entry_price, next_candle)
        pnl_pct = _signed_pnl_pct(entry_price, exit_price, direction=signal.direction)
        if stop_hit:
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
        stop_hit=stop_hit,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        entry_mode=entry_mode,
        filled_size_fraction=filled_size_fraction,
        tranche_fills=tranche_fills,
    )


def _adverse_excursion_pct(direction: str, entry_price: float, next_candle: dict[str, Any]) -> float:
    if direction == "long":
        probe_price = min(float(next_candle["low"]), entry_price)
        return _pct_move(entry_price, probe_price, direction=direction, favorable=False)
    probe_price = max(float(next_candle["high"]), entry_price)
    return _pct_move(entry_price, probe_price, direction=direction, favorable=False)


def _favorable_excursion_pct(direction: str, entry_price: float, next_candle: dict[str, Any]) -> float:
    if direction == "long":
        probe_price = max(float(next_candle["high"]), entry_price)
        return _pct_move(entry_price, probe_price, direction=direction, favorable=True)
    probe_price = min(float(next_candle["low"]), entry_price)
    return _pct_move(entry_price, probe_price, direction=direction, favorable=True)
