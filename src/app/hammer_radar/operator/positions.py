"""Paper position storage and deterministic stop-only lifecycle handling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, TypeVar

from src.app.hammer_radar.operator.models import PaperPosition, PositionEvent, SignalRecord

ROOT_DIR = Path(__file__).resolve().parents[4]
LOG_DIR = ROOT_DIR / "logs" / "hammer_radar"
POSITIONS_PATH = LOG_DIR / "positions.ndjson"
POSITION_EVENTS_PATH = LOG_DIR / "position_events.ndjson"

DEFAULT_ENTRY_MODE = "fib_618"
DEFAULT_POSITION_SIZE_USD = 100.0

RecordT = TypeVar("RecordT", PaperPosition, PositionEvent)


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
        status="open",
        opened_at=signal.timestamp,
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
        status="closed",
        opened_at=position.opened_at,
        closed_at=closed_at,
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


def load_positions_by_signal_entry() -> dict[tuple[str, str], PaperPosition]:
    return {
        (position.signal_id, position.entry_mode): position
        for position in load_positions()
    }


def load_positions() -> list[PaperPosition]:
    positions_by_id: dict[str, PaperPosition] = {}
    for position in _load_records(POSITIONS_PATH, PaperPosition.from_dict):
        positions_by_id[position.position_id] = position
    return list(positions_by_id.values())


def load_open_positions() -> list[PaperPosition]:
    return [position for position in load_positions() if position.status == "open"]


def load_closed_positions() -> list[PaperPosition]:
    return [position for position in load_positions() if position.status == "closed"]


def load_position_events() -> list[PositionEvent]:
    return _load_records(POSITION_EVENTS_PATH, PositionEvent.from_dict)


def append_position(position: PaperPosition) -> None:
    _append_record(POSITIONS_PATH, position.to_dict())


def append_position_event(event: PositionEvent) -> None:
    _append_record(POSITION_EVENTS_PATH, event.to_dict())


def evaluate_open_positions(
    open_positions: list[PaperPosition],
    latest_candles_by_timeframe: dict[str, dict[str, Any]],
) -> list[PaperPosition]:
    closed_positions: list[PaperPosition] = []

    for position in open_positions:
        candle = latest_candles_by_timeframe.get(position.timeframe)
        if candle is None:
            continue
        candle_timestamp = str(candle.get("timestamp", ""))
        if not candle_timestamp or candle_timestamp <= _signal_timestamp_from_id(position.signal_id):
            continue

        if position.direction == "long" and float(candle["low"]) <= position.stop_price:
            closed_positions.append(
                close_position(
                    position,
                    exit_price=position.stop_price,
                    close_reason="stop",
                    closed_at=candle_timestamp,
                )
            )
        elif position.direction == "short" and float(candle["high"]) >= position.stop_price:
            closed_positions.append(
                close_position(
                    position,
                    exit_price=position.stop_price,
                    close_reason="stop",
                    closed_at=candle_timestamp,
                )
            )

    return closed_positions


def _append_record(path: Path, payload: dict[str, Any]) -> None:
    _ensure_log_dir()
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


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _build_position_id(signal_id: str, entry_mode: str) -> str:
    return f"{signal_id}|{entry_mode}"


def _build_event_id(position_id: str, event_type: str, timestamp: str) -> str:
    return f"{position_id}|{event_type}|{timestamp}"


def _signal_timestamp_from_id(signal_id: str) -> str:
    parts = signal_id.split("|", 3)
    if len(parts) == 4:
        return parts[3]
    return ""


def _calculate_pnl_pct(direction: str, entry_price: float, exit_price: float) -> float:
    if entry_price == 0:
        return 0.0
    if direction == "short":
        return round(((entry_price - exit_price) / entry_price) * 100.0, 4)
    return round(((exit_price - entry_price) / entry_price) * 100.0, 4)


def _calculate_pnl_usd(direction: str, entry_price: float, exit_price: float, size_usd: float) -> float:
    pnl_pct = _calculate_pnl_pct(direction, entry_price, exit_price)
    return round(size_usd * (pnl_pct / 100.0), 4)
