"""Small deterministic market-state helpers for Hammer Radar research context."""

from __future__ import annotations

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - depends on runtime environment
    pd = None


def compute_trend_direction(df, lookback: int = 3) -> str:
    closes = _extract_recent_closes(df, lookback=lookback)
    if closes is None:
        return "neutral"

    start_close = float(closes.iloc[0])
    end_close = float(closes.iloc[-1])
    if end_close > start_close:
        return "bullish"
    if end_close < start_close:
        return "bearish"
    return "neutral"


def compute_trend_strength_score(df, lookback: int = 3) -> float | None:
    closes = _extract_recent_closes(df, lookback=lookback)
    if closes is None:
        return None

    start_close = float(closes.iloc[0])
    if start_close == 0.0:
        return None
    end_close = float(closes.iloc[-1])
    return round(((end_close - start_close) / start_close) * 100.0, 4)


def compute_ema(series, span: int = 20):
    _require_pandas()
    return series.astype(float).ewm(span=span, adjust=False).mean()


def compute_price_vs_ema_pct(price: float | None, ema_value: float | None) -> float | None:
    if price is None or ema_value in (None, 0.0):
        return None
    return round(((float(price) - float(ema_value)) / float(ema_value)) * 100.0, 4)


def _extract_recent_closes(df, lookback: int):
    _require_pandas()
    if df is None or getattr(df, "empty", True):
        return None
    if "close" not in df.columns:
        raise ValueError("market-state helpers require a close column")

    required_rows = max(int(lookback), 1) + 1
    if len(df.index) < required_rows:
        return None
    return df["close"].astype(float).iloc[-required_rows:]


def _require_pandas() -> None:
    if pd is None:
        raise RuntimeError("pandas is required for Hammer Radar market-state helpers")
