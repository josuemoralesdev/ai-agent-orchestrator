"""Append-only NDJSON storage for Hammer Radar operator records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, TypeVar

from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord

ROOT_DIR = Path(__file__).resolve().parents[4]
LOG_DIR = ROOT_DIR / "logs" / "hammer_radar"
SIGNALS_PATH = LOG_DIR / "signals.ndjson"
OUTCOMES_PATH = LOG_DIR / "outcomes.ndjson"

RecordT = TypeVar("RecordT", SignalRecord, OutcomeRecord)


def append_signal(record: SignalRecord) -> None:
    _append_record(SIGNALS_PATH, record.to_dict())


def append_outcome(record: OutcomeRecord) -> None:
    _append_record(OUTCOMES_PATH, record.to_dict())


def load_signals() -> list[SignalRecord]:
    return _load_records(SIGNALS_PATH, SignalRecord.from_dict)


def load_outcomes() -> list[OutcomeRecord]:
    return _load_records(OUTCOMES_PATH, OutcomeRecord.from_dict)


def load_evaluated_signal_ids() -> set[str]:
    return {record.signal_id for record in load_outcomes()}


def _append_record(path: Path, payload: dict) -> None:
    _ensure_log_dir()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _load_records(path: Path, factory: Callable[[dict], RecordT]) -> list[RecordT]:
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
