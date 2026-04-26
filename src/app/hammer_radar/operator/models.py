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


def _to_dict(value: Any) -> dict[str, Any] | None:
    if value in (None, ""):
        return None
    if not isinstance(value, dict):
        return None
    return dict(value)


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
    trend_direction: str | None = None
    trend_strength_score: float | None = None
    trend_lookback_candles: int | None = None
    ema_4h_20: float | None = None
    price_vs_ema_4h_pct: float | None = None
    signal_close: float | None = None
    rsi_length: int | None = None
    rsi_value: float | None = None
    rsi_state: str | None = None
    divergence_type: str | None = None
    divergence_confirmed: bool = False
    divergence_price_pivot_1: float | None = None
    divergence_price_pivot_2: float | None = None
    divergence_rsi_pivot_1: float | None = None
    divergence_rsi_pivot_2: float | None = None
    extreme_trigger: bool = False
    critical_trigger: bool = False
    micro_scalp_candidate: bool = False
    requires_human_approval: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "rsi_length",
            "rsi_value",
            "rsi_state",
            "divergence_type",
            "divergence_confirmed",
            "divergence_price_pivot_1",
            "divergence_price_pivot_2",
            "divergence_rsi_pivot_1",
            "divergence_rsi_pivot_2",
        ):
            payload.pop(key, None)
        payload["rsi"] = {
            "length": self.rsi_length,
            "value": self.rsi_value,
            "state": self.rsi_state,
        }
        payload["divergence"] = {
            "type": self.divergence_type,
            "confirmed": self.divergence_confirmed,
            "price_pivot_1": self.divergence_price_pivot_1,
            "price_pivot_2": self.divergence_price_pivot_2,
            "rsi_pivot_1": self.divergence_rsi_pivot_1,
            "rsi_pivot_2": self.divergence_rsi_pivot_2,
        }
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SignalRecord":
        rsi_payload = _to_dict(payload.get("rsi")) or {}
        divergence_payload = _to_dict(payload.get("divergence")) or {}
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
            trend_direction=payload.get("trend_direction"),
            trend_strength_score=_to_float(payload.get("trend_strength_score")),
            trend_lookback_candles=(
                None
                if payload.get("trend_lookback_candles") in (None, "")
                else int(payload["trend_lookback_candles"])
            ),
            ema_4h_20=_to_float(payload.get("ema_4h_20")),
            price_vs_ema_4h_pct=_to_float(payload.get("price_vs_ema_4h_pct")),
            signal_close=_to_float(payload.get("signal_close")),
            rsi_length=(
                None
                if rsi_payload.get("length", payload.get("rsi_length")) in (None, "")
                else int(rsi_payload.get("length", payload.get("rsi_length")))
            ),
            rsi_value=_to_float(rsi_payload.get("value", payload.get("rsi_value"))),
            rsi_state=(
                None
                if rsi_payload.get("state", payload.get("rsi_state")) in (None, "")
                else str(rsi_payload.get("state", payload.get("rsi_state")))
            ),
            divergence_type=(
                None
                if divergence_payload.get("type", payload.get("divergence_type")) in (None, "")
                else str(divergence_payload.get("type", payload.get("divergence_type")))
            ),
            divergence_confirmed=_to_bool(
                divergence_payload.get("confirmed", payload.get("divergence_confirmed"))
            ),
            divergence_price_pivot_1=_to_float(
                divergence_payload.get("price_pivot_1", payload.get("divergence_price_pivot_1"))
            ),
            divergence_price_pivot_2=_to_float(
                divergence_payload.get("price_pivot_2", payload.get("divergence_price_pivot_2"))
            ),
            divergence_rsi_pivot_1=_to_float(
                divergence_payload.get("rsi_pivot_1", payload.get("divergence_rsi_pivot_1"))
            ),
            divergence_rsi_pivot_2=_to_float(
                divergence_payload.get("rsi_pivot_2", payload.get("divergence_rsi_pivot_2"))
            ),
            extreme_trigger=_to_bool(payload.get("extreme_trigger")),
            critical_trigger=_to_bool(payload.get("critical_trigger")),
            micro_scalp_candidate=_to_bool(payload.get("micro_scalp_candidate")),
            requires_human_approval=_to_bool(payload.get("requires_human_approval")),
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


@dataclass(slots=True)
class PaperPosition:
    position_id: str
    signal_id: str
    symbol: str
    timeframe: str
    direction: str
    entry_mode: str
    entry_price: float
    size_usd: float
    stop_price: float
    status: str
    opened_at: str
    take_profit_price: float | None = None
    opened_candle_timestamp: str | None = None
    closed_at: str | None = None
    closed_candle_timestamp: str | None = None
    held_candles: int = 0
    exit_price: float | None = None
    pnl_pct: float | None = None
    pnl_usd: float | None = None
    close_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PaperPosition":
        return cls(
            position_id=str(payload["position_id"]),
            signal_id=str(payload["signal_id"]),
            symbol=str(payload["symbol"]),
            timeframe=str(payload["timeframe"]),
            direction=str(payload["direction"]),
            entry_mode=str(payload.get("entry_mode", "fib_618")),
            entry_price=float(payload["entry_price"]),
            size_usd=float(payload["size_usd"]),
            stop_price=float(payload["stop_price"]),
            take_profit_price=_to_float(payload.get("take_profit_price")),
            status=str(payload["status"]),
            opened_at=str(payload["opened_at"]),
            opened_candle_timestamp=payload.get("opened_candle_timestamp", payload.get("opened_at")),
            closed_at=payload.get("closed_at"),
            closed_candle_timestamp=payload.get("closed_candle_timestamp", payload.get("closed_at")),
            held_candles=_to_int(payload.get("held_candles")),
            exit_price=_to_float(payload.get("exit_price")),
            pnl_pct=_to_float(payload.get("pnl_pct")),
            pnl_usd=_to_float(payload.get("pnl_usd")),
            close_reason=payload.get("close_reason"),
        )


@dataclass(slots=True)
class PositionEvent:
    event_id: str
    position_id: str
    signal_id: str
    event_type: str
    timestamp: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PositionEvent":
        return cls(
            event_id=str(payload["event_id"]),
            position_id=str(payload["position_id"]),
            signal_id=str(payload["signal_id"]),
            event_type=str(payload["event_type"]),
            timestamp=str(payload["timestamp"]),
            payload=dict(payload.get("payload", {})),
        )
