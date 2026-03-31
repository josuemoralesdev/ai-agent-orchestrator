"""Operator-layer data models for Hammer Radar."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(value)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _to_bool_dict(value: Any) -> dict[str, bool] | None:
    if value in (None, ""):
        return None
    if not isinstance(value, dict):
        return None
    return {str(key): _to_bool(item) for key, item in value.items()}


@dataclass(slots=True)
class SignalRecord:
    signal_id: str
    symbol: str
    timeframe: str
    direction: str
    timestamp: str
    hammer_strength: float
    hammer_high: float
    hammer_low: float
    fib_50: float
    fib_618: float
    fib_650: float
    fib_786: float
    invalidation: float
    bias_timeframe: str
    bias_direction: str
    bias_aligned: bool
    same_direction_streak: int
    opposite_direction_streak: int
    tradable: bool
    reject_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SignalRecord":
        return cls(
            signal_id=str(payload["signal_id"]),
            symbol=str(payload["symbol"]),
            timeframe=str(payload["timeframe"]),
            direction=str(payload["direction"]),
            timestamp=str(payload["timestamp"]),
            hammer_strength=float(payload["hammer_strength"]),
            hammer_high=float(payload["hammer_high"]),
            hammer_low=float(payload["hammer_low"]),
            fib_50=float(payload["fib_50"]),
            fib_618=float(payload["fib_618"]),
            fib_650=float(payload["fib_650"]),
            fib_786=float(payload["fib_786"]),
            invalidation=float(payload["invalidation"]),
            bias_timeframe=str(payload.get("bias_timeframe", "")),
            bias_direction=str(payload.get("bias_direction", "neutral")),
            bias_aligned=_to_bool(payload.get("bias_aligned")),
            same_direction_streak=_to_int(payload.get("same_direction_streak")),
            opposite_direction_streak=_to_int(payload.get("opposite_direction_streak")),
            tradable=_to_bool(payload.get("tradable")),
            reject_reason=payload.get("reject_reason"),
        )


@dataclass(slots=True)
class OutcomeRecord:
    signal_id: str
    symbol: str
    timeframe: str
    direction: str
    timestamp: str
    entry_price: float | None
    exit_price: float | None
    fill_status: str
    outcome: str
    mae_pct: float
    mfe_pct: float
    pnl_pct: float
    stop_hit: bool
    evaluated_at: str
    entry_mode: str = "fib_618"
    filled_size_fraction: float | None = None
    tranche_fills: dict[str, bool] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OutcomeRecord":
        return cls(
            signal_id=str(payload["signal_id"]),
            symbol=str(payload["symbol"]),
            timeframe=str(payload["timeframe"]),
            direction=str(payload["direction"]),
            timestamp=str(payload["timestamp"]),
            entry_price=_to_float(payload.get("entry_price")),
            exit_price=_to_float(payload.get("exit_price")),
            fill_status=str(payload["fill_status"]),
            outcome=str(payload["outcome"]),
            mae_pct=float(payload.get("mae_pct", 0.0)),
            mfe_pct=float(payload.get("mfe_pct", 0.0)),
            pnl_pct=float(payload.get("pnl_pct", 0.0)),
            stop_hit=_to_bool(payload.get("stop_hit")),
            evaluated_at=str(payload["evaluated_at"]),
            entry_mode=str(payload.get("entry_mode", "fib_618")),
            filled_size_fraction=_to_float(payload.get("filled_size_fraction")),
            tranche_fills=_to_bool_dict(payload.get("tranche_fills")),
        )
