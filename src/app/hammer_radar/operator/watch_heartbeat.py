"""Append-only watcher heartbeat helpers.

These helpers are diagnostic only. They write local NDJSON records and never
create order payloads, call Binance, sign requests, mutate env files, or enable
live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE

HEARTBEAT_EVENT_TYPE = "FRESH_CANDIDATE_PAPER_PROOF_WATCH_HEARTBEAT"
HEARTBEAT_LEDGER_FILENAME = "fresh_candidate_paper_proof_watch_heartbeats.ndjson"

WATCH_ITERATION_STARTED = "WATCH_ITERATION_STARTED"
WATCH_ITERATION_COMPLETED = "WATCH_ITERATION_COMPLETED"
WATCH_ITERATION_TIMEOUT = "WATCH_ITERATION_TIMEOUT"
WATCH_CAPTURED_PROOF = "WATCH_CAPTURED_PROOF"
WATCH_EXITED = "WATCH_EXITED"

WATCH_HEARTBEAT_SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
}


def build_watch_heartbeat_record(
    *,
    watch_id: str,
    iteration: int,
    max_iterations: int,
    sleep_seconds: int,
    status: str,
    elapsed_seconds: float = 0.0,
    lanes: list[Mapping[str, Any]] | None = None,
    candidates_checked: int = 0,
    fresh_normalized_count: int = 0,
    stale_normalized_count: int = 0,
    paper_proof_captured: bool = False,
    captured_lane_key: str | None = None,
    next_operator_move: str = "",
    safety: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at or datetime.now(UTC)
    return _sanitize(
        {
            "event_type": HEARTBEAT_EVENT_TYPE,
            "watch_id": watch_id,
            "generated_at": generated.isoformat(),
            "iteration": int(iteration),
            "max_iterations": int(max_iterations),
            "sleep_seconds": int(sleep_seconds),
            "status": status,
            "elapsed_seconds": round(float(elapsed_seconds), 6),
            "lanes": [dict(lane) for lane in lanes or []],
            "candidates_checked": int(candidates_checked),
            "fresh_normalized_count": int(fresh_normalized_count),
            "stale_normalized_count": int(stale_normalized_count),
            "paper_proof_captured": bool(paper_proof_captured),
            "captured_lane_key": captured_lane_key,
            "next_operator_move": next_operator_move,
            "safety": _heartbeat_safety(safety),
        }
    )


def append_watch_heartbeat(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
    heartbeat_ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    path = _heartbeat_path(log_dir=log_dir, heartbeat_ledger_path=heartbeat_ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(dict(record))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_recent_watch_heartbeats(
    *,
    log_dir: str | Path | None = None,
    heartbeat_ledger_path: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = _heartbeat_path(log_dir=log_dir, heartbeat_ledger_path=heartbeat_ledger_path)
    return load_recent_ndjson_records(path, limit=limit)


def summarize_watch_heartbeats(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    captured = [record for record in records if record.get("paper_proof_captured")]
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_watch_id": records[0].get("watch_id") if records else None,
        "last_status": records[0].get("status") if records else None,
        "paper_proof_captures_count": len(captured),
        "last_captured_lane_key": captured[0].get("captured_lane_key") if captured else None,
        "safety": dict(WATCH_HEARTBEAT_SAFETY),
    }


def load_recent_ndjson_records(path: str | Path, *, limit: int = 50, max_bytes: int = 2_097_152) -> list[dict[str, Any]]:
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=max_bytes)]


def watch_heartbeat_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / HEARTBEAT_LEDGER_FILENAME


def _heartbeat_path(
    *,
    log_dir: str | Path | None,
    heartbeat_ledger_path: str | Path | None,
) -> Path:
    if heartbeat_ledger_path is not None:
        return Path(heartbeat_ledger_path)
    return watch_heartbeat_path(get_log_dir(log_dir, use_env=True))


def _heartbeat_safety(safety: Mapping[str, Any] | None) -> dict[str, bool]:
    result = dict(WATCH_HEARTBEAT_SAFETY)
    for key, value in dict(safety or {}).items():
        if key == "paper_live_separation_intact":
            result[key] = bool(value)
        elif key in result:
            result[key] = bool(value)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
