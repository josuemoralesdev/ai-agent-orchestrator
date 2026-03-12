"""Minimal hammer signal extraction for Hammer Radar."""

from __future__ import annotations

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - depends on runtime environment
    pd = None


REQUIRED_COLUMNS = ("high", "low", "bullish_hammer", "bearish_hammer", "hammer_strength")


def extract_signal(df, symbol: str, timeframe: str = "1m"):
    """Return a signal dictionary for the latest hammer candle or ``None``."""
    _require_pandas()
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"extract_signal requires columns: {', '.join(REQUIRED_COLUMNS)}")
    if df.empty:
        return None

    latest = df.iloc[-1]
    is_bullish = bool(latest["bullish_hammer"])
    is_bearish = bool(latest["bearish_hammer"])
    if not is_bullish and not is_bearish:
        return None

    hammer_high = float(latest["high"])
    hammer_low = float(latest["low"])
    fib_levels = _compute_fibonacci_levels(hammer_high=hammer_high, hammer_low=hammer_low, bullish=is_bullish)

    return {
        "symbol": symbol,
        "timestamp": _extract_timestamp(latest),
        "timeframe": timeframe,
        "direction": "long" if is_bullish else "short",
        "hammer_strength": float(latest["hammer_strength"]),
        "hammer_high": hammer_high,
        "hammer_low": hammer_low,
        "fib_50": fib_levels["fib_50"],
        "fib_618": fib_levels["fib_618"],
        "fib_650": fib_levels["fib_650"],
        "fib_786": fib_levels["fib_786"],
    }


def _compute_fibonacci_levels(hammer_high: float, hammer_low: float, bullish: bool) -> dict[str, float]:
    """Compute retracement levels from the hammer range."""
    price_range = max(hammer_high - hammer_low, 0.0)
    if bullish:
        return {
            "fib_50": hammer_high - (price_range * 0.5),
            "fib_618": hammer_high - (price_range * 0.618),
            "fib_650": hammer_high - (price_range * 0.65),
            "fib_786": hammer_high - (price_range * 0.786),
        }
    return {
        "fib_50": hammer_low + (price_range * 0.5),
        "fib_618": hammer_low + (price_range * 0.618),
        "fib_650": hammer_low + (price_range * 0.65),
        "fib_786": hammer_low + (price_range * 0.786),
    }


def _extract_timestamp(row) -> str | None:
    """Prefer candle timestamps when present and return an ISO string."""
    for column in ("close_time", "open_time", "timestamp"):
        if column not in row.index:
            continue
        value = row[column]
        if pd.isna(value):
            continue
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
    return None


def _require_pandas() -> None:
    if pd is None:
        raise RuntimeError("pandas is required for extract_signal")
