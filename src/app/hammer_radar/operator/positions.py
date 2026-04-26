"""Paper position storage and deterministic stop-only lifecycle handling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, TypeVar

from src.app.hammer_radar.operator.models import PaperPosition, PositionEvent, SignalRecord
from src.app.hammer_radar.operator.paths import DEFAULT_LOG_DIR, resolve_log_dir
from src.app.hammer_radar.operator.strategy_config import TIMEFRAME_MINUTES, load_strategy_config

LOG_DIR = DEFAULT_LOG_DIR
POSITIONS_PATH = LOG_DIR / "positions.ndjson"
POSITION_EVENTS_PATH = LOG_DIR / "position_events.ndjson"

DEFAULT_ENTRY_MODE = "fib_618"
DEFAULT_POSITION_SIZE_USD = 100.0

RecordT = TypeVar("RecordT", PaperPosition, PositionEvent)


def get_log_dir(log_dir: str | Path | None = None, *, use_env: bool = False) -> Path:
    if log_dir is None and not use_env:
        return LOG_DIR
    return resolve_log_dir(log_dir, default=LOG_DIR)


def get_positions_path(log_dir: str | Path | None = None) -> Path:
    if log_dir is None:
        resolved_log_dir = get_log_dir()
        if resolved_log_dir == LOG_DIR:
            return POSITIONS_PATH
        return resolved_log_dir / "positions.ndjson"
    return get_log_dir(log_dir) / "positions.ndjson"


def get_position_events_path(log_dir: str | Path | None = None) -> Path:
    if log_dir is None:
        resolved_log_dir = get_log_dir()
        if resolved_log_dir == LOG_DIR:
            return POSITION_EVENTS_PATH
        return resolved_log_dir / "position_events.ndjson"
    return get_log_dir(log_dir) / "position_events.ndjson"


def create_paper_position(
    signal: SignalRecord,
    *,
    entry_mode: str = DEFAULT_ENTRY_MODE,
    size_usd: float = DEFAULT_POSITION_SIZE_USD,
) -> PaperPosition | None:
    if not signal.tradable:
        return None

    existing = load_positions_by_signal_entry().get((signal.signal_id, entry_mode))
    if existing is not None:
        return None

    position = PaperPosition(
        position_id=_build_position_id(signal.signal_id, entry_mode),
        signal_id=signal.signal_id,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        direction=signal.direction,
        entry_mode=entry_mode,
        entry_price=float(signal.fib_618),
        size_usd=float(size_usd),
        stop_price=float(signal.invalidation),
        take_profit_price=_calculate_take_profit_price(signal),
        status="open",
        opened_at=signal.timestamp,
        opened_candle_timestamp=signal.timestamp,
    )
    append_position(position)
    append_position_event(
        PositionEvent(
            event_id=_build_event_id(position.position_id, "open", position.opened_at),
            position_id=position.position_id,
            signal_id=position.signal_id,
            event_type="open",
            timestamp=position.opened_at,
            payload={
                "entry_mode": position.entry_mode,
                "entry_price": position.entry_price,
                "size_usd": position.size_usd,
                "stop_price": position.stop_price,
                "take_profit_price": position.take_profit_price,
            },
        )
    )
    return position


def close_position(
    position: PaperPosition,
    *,
    exit_price: float,
    close_reason: str,
    closed_at: str,
) -> PaperPosition:
    closed_position = PaperPosition(
        position_id=position.position_id,
        signal_id=position.signal_id,
        symbol=position.symbol,
        timeframe=position.timeframe,
        direction=position.direction,
        entry_mode=position.entry_mode,
        entry_price=position.entry_price,
        size_usd=position.size_usd,
        stop_price=position.stop_price,
        take_profit_price=position.take_profit_price,
        status="closed",
        opened_at=position.opened_at,
        opened_candle_timestamp=position.opened_candle_timestamp,
        closed_at=closed_at,
        closed_candle_timestamp=closed_at,
        held_candles=position.held_candles,
        exit_price=float(exit_price),
        pnl_pct=_calculate_pnl_pct(position.direction, position.entry_price, float(exit_price)),
        pnl_usd=_calculate_pnl_usd(
            position.direction,
            position.entry_price,
            float(exit_price),
            position.size_usd,
        ),
        close_reason=close_reason,
    )
    append_position(closed_position)
    append_position_event(
        PositionEvent(
            event_id=_build_event_id(position.position_id, "close", closed_at),
            position_id=position.position_id,
            signal_id=position.signal_id,
            event_type="close",
            timestamp=closed_at,
            payload={
                "close_reason": close_reason,
                "exit_price": float(exit_price),
                "pnl_pct": closed_position.pnl_pct,
                "pnl_usd": closed_position.pnl_usd,
            },
        )
    )
    return closed_position


def close_paper_position(
    position: PaperPosition,
    *,
    exit_price: float,
    close_reason: str,
    closed_at: str,
) -> PaperPosition:
    return close_position(
        position,
        exit_price=exit_price,
        close_reason=close_reason,
        closed_at=closed_at,
    )


def load_positions_by_signal_entry(log_dir: str | Path | None = None) -> dict[tuple[str, str], PaperPosition]:
    return {
        (position.signal_id, position.entry_mode): position
        for position in load_positions(log_dir)
    }


def load_positions(log_dir: str | Path | None = None) -> list[PaperPosition]:
    positions_by_id: dict[str, PaperPosition] = {}
    for position in _load_records(get_positions_path(log_dir), PaperPosition.from_dict):
        positions_by_id[position.position_id] = position
    return list(positions_by_id.values())


def load_open_positions(log_dir: str | Path | None = None) -> list[PaperPosition]:
    return [position for position in load_positions(log_dir) if position.status == "open"]


def load_closed_positions(log_dir: str | Path | None = None) -> list[PaperPosition]:
    return [position for position in load_positions(log_dir) if position.status == "closed"]


def load_position_events(log_dir: str | Path | None = None) -> list[PositionEvent]:
    return _load_records(get_position_events_path(log_dir), PositionEvent.from_dict)


def append_position(position: PaperPosition) -> None:
    _append_record(POSITIONS_PATH, position.to_dict())


def append_position_event(event: PositionEvent) -> None:
    _append_record(POSITION_EVENTS_PATH, event.to_dict())


def evaluate_open_positions(
    open_positions: list[PaperPosition],
    latest_candles_by_timeframe: dict[str, dict[str, Any]],
) -> list[PaperPosition]:
    strategy_config = load_strategy_config()
    closed_positions: list[PaperPosition] = []

    for position in open_positions:
        candle = latest_candles_by_timeframe.get(position.timeframe)
        if candle is None:
            continue
        candle_timestamp = str(candle.get("timestamp", ""))
        if not candle_timestamp or candle_timestamp <= _signal_timestamp_from_id(position.signal_id):
            continue
        held_candles = _calculate_held_candles(position, candle_timestamp)
        position = _position_with_held_candles(position, held_candles)

        stop_hit = strategy_config.exit_on_stop and _is_stop_hit(position, candle)
        take_profit_hit = strategy_config.exit_on_take_profit and _is_take_profit_hit(position, candle)
        max_hold_hit = (
            strategy_config.exit_on_max_hold
            and strategy_config.max_hold_candles > 0
            and held_candles >= strategy_config.max_hold_candles
        )

        if stop_hit:
            closed_positions.append(
                close_position(
                    position,
                    exit_price=position.stop_price,
                    close_reason="stop",
                    closed_at=candle_timestamp,
                )
            )
            continue
        if take_profit_hit and position.take_profit_price is not None:
            closed_positions.append(
                close_position(
                    position,
                    exit_price=position.take_profit_price,
                    close_reason="take_profit",
                    closed_at=candle_timestamp,
                )
            )
            continue
        if max_hold_hit:
            closed_positions.append(
                close_position(
                    position,
                    exit_price=float(candle["close"]),
                    close_reason="max_hold",
                    closed_at=candle_timestamp,
                )
            )

    return closed_positions


def _append_record(path: Path, payload: dict[str, Any]) -> None:
    _ensure_log_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _load_records(path: Path, factory: Callable[[dict[str, Any]], RecordT]) -> list[RecordT]:
    if not path.exists():
        return []

    records: list[RecordT] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(factory(json.loads(line)))
    return records


def _ensure_log_dir(log_dir: Path = LOG_DIR) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)


def _build_position_id(signal_id: str, entry_mode: str) -> str:
    return f"{signal_id}|{entry_mode}"


def _build_event_id(position_id: str, event_type: str, timestamp: str) -> str:
    return f"{position_id}|{event_type}|{timestamp}"


def _signal_timestamp_from_id(signal_id: str) -> str:
    parts = signal_id.split("|", 3)
    if len(parts) == 4:
        return parts[3]
    return ""


def _calculate_take_profit_price(signal: SignalRecord) -> float | None:
    strategy_config = load_strategy_config()
    risk = abs(float(signal.fib_618) - float(signal.invalidation))
    if risk <= 0.0:
        return None
    if signal.direction == "short":
        return round(float(signal.fib_618) - (risk * strategy_config.take_profit_r_multiple), 4)
    return round(float(signal.fib_618) + (risk * strategy_config.take_profit_r_multiple), 4)


def _calculate_held_candles(position: PaperPosition, candle_timestamp: str) -> int:
    timeframe_minutes = TIMEFRAME_MINUTES.get(position.timeframe)
    opened_candle_timestamp = position.opened_candle_timestamp or position.opened_at
    if timeframe_minutes is None:
        return position.held_candles
    signal_time = _parse_timestamp(opened_candle_timestamp)
    candle_time = _parse_timestamp(candle_timestamp)
    if signal_time is None or candle_time is None or candle_time <= signal_time:
        return position.held_candles
    candle_gap = int((candle_time - signal_time).total_seconds() / (timeframe_minutes * 60.0))
    return max(position.held_candles, candle_gap)


def _position_with_held_candles(position: PaperPosition, held_candles: int) -> PaperPosition:
    if held_candles == position.held_candles:
        return position
    return PaperPosition(
        position_id=position.position_id,
        signal_id=position.signal_id,
        symbol=position.symbol,
        timeframe=position.timeframe,
        direction=position.direction,
        entry_mode=position.entry_mode,
        entry_price=position.entry_price,
        size_usd=position.size_usd,
        stop_price=position.stop_price,
        take_profit_price=position.take_profit_price,
        status=position.status,
        opened_at=position.opened_at,
        opened_candle_timestamp=position.opened_candle_timestamp,
        closed_at=position.closed_at,
        closed_candle_timestamp=position.closed_candle_timestamp,
        held_candles=held_candles,
        exit_price=position.exit_price,
        pnl_pct=position.pnl_pct,
        pnl_usd=position.pnl_usd,
        close_reason=position.close_reason,
    )


def _is_stop_hit(position: PaperPosition, candle: dict[str, Any]) -> bool:
    if position.direction == "short":
        return float(candle["high"]) >= position.stop_price
    return float(candle["low"]) <= position.stop_price


def _is_take_profit_hit(position: PaperPosition, candle: dict[str, Any]) -> bool:
    if position.take_profit_price is None:
        return False
    if position.direction == "short":
        return float(candle["low"]) <= position.take_profit_price
    return float(candle["high"]) >= position.take_profit_price


def _parse_timestamp(value: str) -> Any:
    from datetime import datetime

    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _calculate_pnl_pct(direction: str, entry_price: float, exit_price: float) -> float:
    if entry_price == 0:
        return 0.0
    if direction == "short":
        return round(((entry_price - exit_price) / entry_price) * 100.0, 4)
    return round(((exit_price - entry_price) / entry_price) * 100.0, 4)


def _calculate_pnl_usd(direction: str, entry_price: float, exit_price: float, size_usd: float) -> float:
    pnl_pct = _calculate_pnl_pct(direction, entry_price, exit_price)
    return round(size_usd * (pnl_pct / 100.0), 4)
