"""Minimal hammer and shooting-star detector for Hammer Radar."""

from __future__ import annotations

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - depends on runtime environment
    pd = None


REQUIRED_COLUMNS = ("open", "high", "low", "close")
OUTPUT_COLUMNS = (
    "body",
    "range",
    "lower_wick",
    "upper_wick",
    "wick_body_ratio",
    "bullish_hammer",
    "bearish_hammer",
    "bullish_real_nice",
    "bearish_real_nice",
    "hammer_strength",
)


def annotate_hammers(df):
    """Return a copy of ``df`` with hammer metrics, flags, and a strength score."""
    _require_pandas()
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"annotate_hammers requires columns: {', '.join(REQUIRED_COLUMNS)}")

    result = df.copy()
    body = (result["close"] - result["open"]).abs()
    candle_range = (result["high"] - result["low"]).clip(lower=0.0)
    lower_wick = (result[["open", "close"]].min(axis=1) - result["low"]).clip(lower=0.0)
    upper_wick = (result["high"] - result[["open", "close"]].max(axis=1)).clip(lower=0.0)
    dominant_wick = lower_wick.where(lower_wick >= upper_wick, upper_wick)

    safe_body = body.mask(body <= 0.0)
    safe_range = candle_range.mask(candle_range <= 0.0)
    close_position = ((result["close"] - result["low"]) / safe_range).fillna(0.0)
    wick_body_ratio = (dominant_wick / safe_body).fillna(0.0)

    bullish_hammer = (
        (body > 0.0)
        & (lower_wick >= (2.0 * body))
        & (upper_wick <= body)
        & (close_position >= 0.6)
    )
    bearish_hammer = (
        (body > 0.0)
        & (upper_wick >= (2.0 * body))
        & (lower_wick <= body)
        & (close_position <= 0.4)
    )
    bullish_real_nice = bullish_hammer & (lower_wick >= (3.0 * body))
    bearish_real_nice = bearish_hammer & (upper_wick >= (3.0 * body))

    bullish_strength = _score_pattern(
        body=body,
        candle_range=candle_range,
        dominant_wick=lower_wick,
        opposite_wick=upper_wick,
        close_quality=((close_position - 0.5) / 0.5).clip(lower=0.0, upper=1.0),
        detected=bullish_hammer,
        real_nice=bullish_real_nice,
    )
    bearish_strength = _score_pattern(
        body=body,
        candle_range=candle_range,
        dominant_wick=upper_wick,
        opposite_wick=lower_wick,
        close_quality=((0.5 - close_position) / 0.5).clip(lower=0.0, upper=1.0),
        detected=bearish_hammer,
        real_nice=bearish_real_nice,
    )

    result["body"] = body.astype(float)
    result["range"] = candle_range.astype(float)
    result["lower_wick"] = lower_wick.astype(float)
    result["upper_wick"] = upper_wick.astype(float)
    result["wick_body_ratio"] = wick_body_ratio.astype(float)
    result["bullish_hammer"] = bullish_hammer.astype(bool)
    result["bearish_hammer"] = bearish_hammer.astype(bool)
    result["bullish_real_nice"] = bullish_real_nice.astype(bool)
    result["bearish_real_nice"] = bearish_real_nice.astype(bool)
    result["hammer_strength"] = (
        pd.concat([bullish_strength, bearish_strength], axis=1).max(axis=1).round(2).astype(float)
    )
    return result


def _score_pattern(body, candle_range, dominant_wick, opposite_wick, close_quality, detected, real_nice):
    """Build a bounded 0-100 score from wick/body ratio and basic candle quality."""
    safe_body = body.mask(body <= 0.0)
    safe_range = candle_range.mask(candle_range <= 0.0)

    wick_ratio_score = ((dominant_wick / safe_body).clip(lower=0.0, upper=4.0) / 4.0).fillna(0.0) * 55.0
    body_efficiency = (body / safe_range).clip(lower=0.0, upper=1.0).fillna(0.0)
    opposite_wick_penalty = ((opposite_wick / safe_body).clip(lower=0.0, upper=2.0) / 2.0).fillna(0.0)
    structure_score = ((1.0 - opposite_wick_penalty) * 25.0).clip(lower=0.0, upper=25.0)
    close_score = close_quality.fillna(0.0) * 15.0
    body_score = ((1.0 - body_efficiency) * 5.0).clip(lower=0.0, upper=5.0)
    base_score = wick_ratio_score + structure_score + close_score + body_score

    pattern_score = base_score.where(detected, 0.0)
    return (pattern_score + real_nice.astype(float) * 5.0).clip(lower=0.0, upper=100.0)


def _require_pandas() -> None:
    if pd is None:
        raise RuntimeError("pandas is required for annotate_hammers")
