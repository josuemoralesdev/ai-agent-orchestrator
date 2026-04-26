"""RSI utilities for Hammer Radar signal enrichment."""

from __future__ import annotations

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - depends on runtime environment
    pd = None


DEFAULT_RSI_LENGTH = 14


def calculate_rsi(close_series, length: int = DEFAULT_RSI_LENGTH):
    """Return a Wilder RSI series clipped to the canonical 0-100 range."""
    _require_pandas()
    if length <= 0:
        raise ValueError("length must be greater than zero")

    close = pd.Series(close_series, copy=False).astype(float)
    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    avg_gain = gains.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = losses.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    relative_strength = avg_gain / avg_loss.replace(0.0, pd.NA)
    rsi = 100 - (100 / (1 + relative_strength))
    rsi = rsi.where(avg_loss != 0.0, 100.0)
    rsi = rsi.where(avg_gain != 0.0, 0.0)
    return rsi.clip(lower=0.0, upper=100.0)


def classify_rsi_state(value: float | None) -> str:
    """Map RSI values to the requested state bands."""
    if value is None:
        return "neutral"
    if value <= 5:
        return "anomaly_oversold"
    if value <= 8:
        return "critical_oversold"
    if value <= 10:
        return "extreme_oversold"
    if value <= 20:
        return "oversold"
    if value >= 95:
        return "anomaly_overbought"
    if value >= 92:
        return "critical_overbought"
    if value >= 90:
        return "extreme_overbought"
    if value >= 80:
        return "overbought"
    return "neutral"


def build_rsi_payload(value: float | None, length: int = DEFAULT_RSI_LENGTH) -> dict[str, float | int | str | None]:
    return {
        "length": int(length),
        "value": None if value is None else float(value),
        "state": classify_rsi_state(value),
    }


def build_trigger_metadata(rsi_value: float | None, timeframe: str) -> dict[str, bool]:
    extreme_trigger = bool(rsi_value is not None and (rsi_value <= 10 or rsi_value >= 90))
    critical_trigger = bool(rsi_value is not None and (rsi_value <= 8 or rsi_value >= 92))
    micro_scalp_candidate = bool(
        critical_trigger and timeframe == "4m" and rsi_value is not None and (rsi_value <= 8 or rsi_value >= 92)
    )
    requires_human_approval = critical_trigger or micro_scalp_candidate
    return {
        "extreme_trigger": extreme_trigger,
        "critical_trigger": critical_trigger,
        "micro_scalp_candidate": micro_scalp_candidate,
        "requires_human_approval": requires_human_approval,
    }


def _require_pandas() -> None:
    if pd is None:
        raise RuntimeError("pandas is required for RSI calculations")
