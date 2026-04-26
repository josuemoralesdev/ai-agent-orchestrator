"""Pivot-based RSI divergence helpers."""

from __future__ import annotations

from dataclasses import dataclass

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - depends on runtime environment
    pd = None


@dataclass(frozen=True, slots=True)
class DivergenceMatch:
    kind: str
    confirmed: bool
    price_pivot_1: float
    price_pivot_2: float
    rsi_pivot_1: float
    rsi_pivot_2: float
    pivot_index_2: int

    def to_payload(self) -> dict[str, float | bool | str]:
        return {
            "type": self.kind,
            "confirmed": self.confirmed,
            "price_pivot_1": self.price_pivot_1,
            "price_pivot_2": self.price_pivot_2,
            "rsi_pivot_1": self.rsi_pivot_1,
            "rsi_pivot_2": self.rsi_pivot_2,
        }


def detect_rsi_divergence(
    df,
    rsi_series,
    *,
    preferred: str | None = None,
    left_span: int = 2,
    right_span: int = 2,
) -> dict[str, float | bool | str | None]:
    """Return the latest confirmed bullish or bearish RSI divergence payload."""
    _require_pandas()
    bullish = _detect_bullish_divergence(df, rsi_series, left_span=left_span, right_span=right_span)
    bearish = _detect_bearish_divergence(df, rsi_series, left_span=left_span, right_span=right_span)
    selected = _select_divergence(bullish, bearish, preferred=preferred)
    if selected is None:
        return {
            "type": None,
            "confirmed": False,
            "price_pivot_1": None,
            "price_pivot_2": None,
            "rsi_pivot_1": None,
            "rsi_pivot_2": None,
        }
    return selected.to_payload()


def _detect_bullish_divergence(df, rsi_series, *, left_span: int, right_span: int) -> DivergenceMatch | None:
    pivot_indices = _find_pivot_indices(df["low"], left_span=left_span, right_span=right_span, direction="low")
    return _build_divergence_match(df, rsi_series, pivot_indices, kind="bullish")


def _detect_bearish_divergence(df, rsi_series, *, left_span: int, right_span: int) -> DivergenceMatch | None:
    pivot_indices = _find_pivot_indices(df["high"], left_span=left_span, right_span=right_span, direction="high")
    return _build_divergence_match(df, rsi_series, pivot_indices, kind="bearish")


def _build_divergence_match(df, rsi_series, pivot_indices: list[int], *, kind: str) -> DivergenceMatch | None:
    if len(pivot_indices) < 2:
        return None

    rsi_values = pd.Series(rsi_series, copy=False).astype(float)
    for second_index in range(len(pivot_indices) - 1, 0, -1):
        pivot_1 = pivot_indices[second_index - 1]
        pivot_2 = pivot_indices[second_index]
        rsi_1 = rsi_values.iloc[pivot_1]
        rsi_2 = rsi_values.iloc[pivot_2]
        if pd.isna(rsi_1) or pd.isna(rsi_2):
            continue
        if kind == "bullish":
            price_1 = float(df["low"].iloc[pivot_1])
            price_2 = float(df["low"].iloc[pivot_2])
            if price_2 < price_1 and float(rsi_2) > float(rsi_1):
                return DivergenceMatch(
                    kind="bullish",
                    confirmed=True,
                    price_pivot_1=price_1,
                    price_pivot_2=price_2,
                    rsi_pivot_1=float(rsi_1),
                    rsi_pivot_2=float(rsi_2),
                    pivot_index_2=pivot_2,
                )
        else:
            price_1 = float(df["high"].iloc[pivot_1])
            price_2 = float(df["high"].iloc[pivot_2])
            if price_2 > price_1 and float(rsi_2) < float(rsi_1):
                return DivergenceMatch(
                    kind="bearish",
                    confirmed=True,
                    price_pivot_1=price_1,
                    price_pivot_2=price_2,
                    rsi_pivot_1=float(rsi_1),
                    rsi_pivot_2=float(rsi_2),
                    pivot_index_2=pivot_2,
                )
    return None


def _find_pivot_indices(series, *, left_span: int, right_span: int, direction: str) -> list[int]:
    values = pd.Series(series, copy=False).astype(float).tolist()
    pivot_indices: list[int] = []
    for index in range(left_span, len(values) - right_span):
        current = values[index]
        left_values = values[index - left_span:index]
        right_values = values[index + 1:index + 1 + right_span]
        if direction == "low":
            if current < min(left_values) and current <= min(right_values):
                pivot_indices.append(index)
        else:
            if current > max(left_values) and current >= max(right_values):
                pivot_indices.append(index)
    return pivot_indices


def _select_divergence(
    bullish: DivergenceMatch | None,
    bearish: DivergenceMatch | None,
    *,
    preferred: str | None,
) -> DivergenceMatch | None:
    matches = {match.kind: match for match in (bullish, bearish) if match is not None}
    if preferred in matches:
        return matches[preferred]
    if bullish is None:
        return bearish
    if bearish is None:
        return bullish
    return bullish if bullish.pivot_index_2 >= bearish.pivot_index_2 else bearish


def _require_pandas() -> None:
    if pd is None:
        raise RuntimeError("pandas is required for divergence detection")
