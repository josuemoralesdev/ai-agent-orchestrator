"""Append-only NDJSON storage for Hammer Radar operator records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, TypeVar

from src.app.hammer_radar.operator.models import OutcomeRecord, SignalRecord
from src.app.hammer_radar.operator.paths import DEFAULT_LOG_DIR, resolve_log_dir

LOG_DIR = DEFAULT_LOG_DIR
SIGNALS_PATH = LOG_DIR / "signals.ndjson"
OUTCOMES_PATH = LOG_DIR / "outcomes.ndjson"

RecordT = TypeVar("RecordT", SignalRecord, OutcomeRecord)


def get_log_dir(log_dir: str | Path | None = None, *, use_env: bool = False) -> Path:
    if log_dir is None and not use_env:
        return LOG_DIR
    return resolve_log_dir(log_dir, default=LOG_DIR)


def get_signals_path(log_dir: str | Path | None = None) -> Path:
    if log_dir is None:
        resolved_log_dir = get_log_dir()
        if resolved_log_dir == LOG_DIR:
            return SIGNALS_PATH
        return resolved_log_dir / "signals.ndjson"
    return get_log_dir(log_dir) / "signals.ndjson"


def get_outcomes_path(log_dir: str | Path | None = None) -> Path:
    if log_dir is None:
        resolved_log_dir = get_log_dir()
        if resolved_log_dir == LOG_DIR:
            return OUTCOMES_PATH
        return resolved_log_dir / "outcomes.ndjson"
    return get_log_dir(log_dir) / "outcomes.ndjson"


def append_signal(record: SignalRecord, log_dir: str | Path | None = None) -> None:
    _append_record(get_signals_path(log_dir), record.to_dict())


def append_outcome(record: OutcomeRecord, log_dir: str | Path | None = None) -> None:
    _append_record(get_outcomes_path(log_dir), record.to_dict())


def load_signals(log_dir: str | Path | None = None) -> list[SignalRecord]:
    return _load_records(get_signals_path(log_dir), SignalRecord.from_dict)


def load_outcomes(log_dir: str | Path | None = None) -> list[OutcomeRecord]:
    return _load_records(get_outcomes_path(log_dir), OutcomeRecord.from_dict)


def load_evaluated_signal_ids(log_dir: str | Path | None = None) -> set[str]:
    return {record.signal_id for record in load_outcomes(log_dir)}


def load_evaluated_outcome_keys(log_dir: str | Path | None = None) -> set[tuple[str, str]]:
    return {(record.signal_id, record.entry_mode) for record in load_outcomes(log_dir)}


def _append_record(path: Path, payload: dict) -> None:
    _ensure_log_dir(path.parent)
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


def _ensure_log_dir(log_dir: Path = LOG_DIR) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
