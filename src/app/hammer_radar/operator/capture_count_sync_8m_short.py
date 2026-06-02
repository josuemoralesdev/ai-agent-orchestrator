"""R176 capture count sync and watcher guard for BTCUSDT 8m short.

This module reads only local R157 capture and heartbeat ledgers, can append a
local sync record after exact confirmation, and never mutates env/config,
calls Binance, creates payloads, changes lane mode, or authorizes execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import (
    HEARTBEAT_LEDGER_FILENAME as SHORT_CAPTURE_HEARTBEAT_LEDGER_FILENAME,
    LEDGER_FILENAME as SHORT_CAPTURE_LEDGER_FILENAME,
    SHORT_PAPER_CAPTURE_EXITED,
    SHORT_PAPER_CAPTURE_PERFORMANCE_GUARD,
    load_short_paper_evidence_capture_records,
    short_paper_capture_heartbeats_path,
)
from src.app.hammer_radar.operator.short_strategy_packet import (
    DEFAULT_TARGET_LANE_KEY,
    MIN_FRESH_CANDIDATES,
    build_short_strategy_target_family,
)

CAPTURE_COUNT_SYNC_READY = "CAPTURE_COUNT_SYNC_READY"
CAPTURE_COUNT_SYNC_REJECTED = "CAPTURE_COUNT_SYNC_REJECTED"
CAPTURE_COUNT_SYNC_RECORDED = "CAPTURE_COUNT_SYNC_RECORDED"
CAPTURE_COUNT_SYNC_BLOCKED = "CAPTURE_COUNT_SYNC_BLOCKED"
CAPTURE_COUNT_SYNC_ERROR = "CAPTURE_COUNT_SYNC_ERROR"

CAPTURE_THRESHOLD_NOT_MET = "CAPTURE_THRESHOLD_NOT_MET"
CAPTURE_THRESHOLD_MET = "CAPTURE_THRESHOLD_MET"
CAPTURE_WATCHER_INACTIVE = "CAPTURE_WATCHER_INACTIVE"
CAPTURE_WATCHER_STALE = "CAPTURE_WATCHER_STALE"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

KEEP_WATCHER_RUNNING = "KEEP_WATCHER_RUNNING"
START_WATCHER_NOW = "START_WATCHER_NOW"
RUN_R158_AFTER_MORE_CAPTURES = "RUN_R158_AFTER_MORE_CAPTURES"
RUN_R177_EVIDENCE_THRESHOLD_RECHECK = "RUN_R177_EVIDENCE_THRESHOLD_RECHECK"

EVENT_TYPE = "CAPTURE_COUNT_SYNC_8M_SHORT"
LEDGER_FILENAME = "capture_count_sync_8m_short.ndjson"
CONFIRM_CAPTURE_COUNT_SYNC_RECORDING_PHRASE = (
    "I CONFIRM CAPTURE COUNT SYNC RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_CAPTURES = 1000
DEFAULT_LATEST_HEARTBEATS = 1000
DEFAULT_WATCHER_STALE_AFTER_SECONDS = 180
TMUX_SESSION = "r176-8m-short-capture"

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_config_written": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
}

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/short_paper_evidence_capture_loop.py",
    "src/app/hammer_radar/operator/short_evidence_recheck_packet.py",
    "src/app/hammer_radar/operator/tiny_live_blocker_burn_down.py",
    f"logs/hammer_radar_forward/{SHORT_CAPTURE_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_CAPTURE_HEARTBEAT_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_capture_count_sync_8m_short(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_heartbeats: int = DEFAULT_LATEST_HEARTBEATS,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    record_sync: bool = False,
    confirm_capture_count_sync: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_capture_count_sync == CONFIRM_CAPTURE_COUNT_SYNC_RECORDING_PHRASE
    try:
        target = build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)
        captures = load_short_capture_records(log_dir=resolved_log_dir, lane_key=target["lane_key"], limit=latest_captures)
        heartbeats = load_short_capture_heartbeats(log_dir=resolved_log_dir, lane_key=target["lane_key"], limit=latest_heartbeats)
        capture_count = count_unique_fresh_captures(captures, required_count=MIN_FRESH_CANDIDATES)
        watcher_status = build_watcher_heartbeat_status(
            heartbeats,
            now=generated_at,
            stale_after_seconds=stale_after_seconds,
        )
        threshold_status = classify_capture_threshold_status(
            capture_count=capture_count,
            watcher_status=watcher_status,
        )
        status = CAPTURE_COUNT_SYNC_READY
        if threshold_status in {CAPTURE_WATCHER_INACTIVE, CAPTURE_WATCHER_STALE, CAPTURE_THRESHOLD_NOT_MET}:
            status = CAPTURE_COUNT_SYNC_BLOCKED
        if record_sync and not confirmation_valid:
            status = CAPTURE_COUNT_SYNC_REJECTED
        elif record_sync and confirmation_valid:
            status = CAPTURE_COUNT_SYNC_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "sync_recorded": False,
            "sync_id": None,
            "record_sync_requested": bool(record_sync),
            "confirmation_valid": bool(confirmation_valid),
            "target_family": {
                "lane_key": target.get("lane_key"),
                "symbol": target.get("symbol"),
                "timeframe": target.get("timeframe"),
                "direction": target.get("direction"),
                "entry_mode": target.get("entry_mode"),
                "current_mode": target.get("current_mode"),
            },
            "capture_count": capture_count,
            "watcher_status": watcher_status,
            "safe_watcher_commands": build_safe_watcher_restart_commands(),
            "threshold_status": threshold_status,
            "capture_stale_or_inactive": threshold_status in {CAPTURE_WATCHER_INACTIVE, CAPTURE_WATCHER_STALE},
            "r158_should_be_rerun": threshold_status == CAPTURE_THRESHOLD_MET,
            "tiny_live_evidence_threshold_met": bool(capture_count["threshold_met"]),
            "recommended_next_operator_move": _recommended_next_operator_move(threshold_status, capture_count),
            "recommended_next_engineering_move": _recommended_next_engineering_move(threshold_status, capture_count),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_sync and confirmation_valid:
            record = append_capture_count_sync_record(payload, log_dir=resolved_log_dir)
            payload["sync_recorded"] = True
            payload["sync_id"] = record["sync_id"]
            payload["ledger_path"] = str(capture_count_sync_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": CAPTURE_COUNT_SYNC_ERROR,
                "generated_at": generated_at.isoformat(),
                "sync_recorded": False,
                "sync_id": None,
                "record_sync_requested": bool(record_sync),
                "confirmation_valid": bool(confirmation_valid),
                "target_family": _target_from_key(lane_key),
                "capture_count": _empty_capture_count(),
                "watcher_status": _empty_watcher_status(),
                "safe_watcher_commands": build_safe_watcher_restart_commands(),
                "threshold_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "capture_stale_or_inactive": True,
                "r158_should_be_rerun": False,
                "tiny_live_evidence_threshold_met": False,
                "recommended_next_operator_move": START_WATCHER_NOW,
                "recommended_next_engineering_move": "Fix R176 capture count sync error before any R158/R177 evidence recheck.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_short_capture_records(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    limit: int = DEFAULT_LATEST_CAPTURES,
) -> list[dict[str, Any]]:
    records = load_short_paper_evidence_capture_records(log_dir=log_dir, limit=max(0, int(limit)))
    return [_sanitize(record) for record in records if _record_lane_key(record) == lane_key]


def load_short_capture_heartbeats(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    limit: int = DEFAULT_LATEST_HEARTBEATS,
) -> list[dict[str, Any]]:
    path = short_paper_capture_heartbeats_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records = read_recent_ndjson_records(path, limit=max(0, int(limit)), max_bytes=16_777_216)
    return [_sanitize(record) for record in records if _record_lane_key(record) == lane_key]


def count_unique_fresh_captures(
    records: list[Mapping[str, Any]],
    *,
    required_count: int = MIN_FRESH_CANDIDATES,
) -> dict[str, Any]:
    ids: list[str] = []
    for record in records:
        if record.get("paper_evidence_captured") is not True:
            continue
        signal_id = str(record.get("captured_signal_id") or "").strip()
        if signal_id and signal_id not in ids:
            ids.append(signal_id)
    latest_signal_id = ids[0] if ids else None
    return {
        "fresh_capture_count": len(ids),
        "required_fresh_capture_count": int(required_count),
        "threshold_met": len(ids) >= int(required_count),
        "unique_captured_signal_ids": ids,
        "latest_captured_signal_id": latest_signal_id,
    }


def build_watcher_heartbeat_status(
    heartbeats: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    latest = heartbeats[0] if heartbeats else {}
    latest_at = _parse_datetime(latest.get("generated_at")) if latest else None
    age = (generated_at - latest_at).total_seconds() if latest_at is not None else None
    stale_limit = max(int(stale_after_seconds), int(latest.get("sleep_seconds") or 0) * 3)
    if stale_limit <= 0:
        stale_limit = DEFAULT_WATCHER_STALE_AFTER_SECONDS
    status = str(latest.get("status") or "") if latest else None
    terminal = status in {SHORT_PAPER_CAPTURE_EXITED, SHORT_PAPER_CAPTURE_PERFORMANCE_GUARD}
    stale = age is None or age > stale_limit
    likely_running = bool(latest) and not stale and not terminal
    return _sanitize(
        {
            "latest_heartbeat_found": bool(latest),
            "latest_heartbeat_status": status,
            "latest_heartbeat_iteration": latest.get("iteration") if latest else None,
            "heartbeat_age_seconds": round(age, 6) if age is not None else None,
            "stale_after_seconds": stale_limit,
            "latest_capture_id": latest.get("capture_id") if latest else None,
            "watcher_likely_running": likely_running,
            "watcher_stale": bool(latest) and stale,
        }
    )


def build_safe_watcher_restart_commands() -> dict[str, str]:
    phrase = (
        "I CONFIRM SHORT PAPER EVIDENCE CAPTURE ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
    )
    start_command = (
        f"tmux new-session -d -s {TMUX_SESSION} "
        "'PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward short-paper-evidence-capture-loop "
        "--lane-key \"BTCUSDT|8m|short|ladder_close_50_618\" "
        "--latest-signals 500 --latest-scans 1000 --max-iterations 1440 --sleep-seconds 60 "
        "--iteration-timeout-seconds 30 --heartbeat-every 1 --run-capture-loop --record-capture "
        f"--confirm-short-paper-capture \"{phrase}\"'"
    )
    return {
        "tmux_session": TMUX_SESSION,
        "start_24h_command": start_command,
        "check_command": f"tmux has-session -t {TMUX_SESSION} && tmux capture-pane -pt {TMUX_SESSION} -S -20",
    }


def classify_capture_threshold_status(
    *,
    capture_count: Mapping[str, Any],
    watcher_status: Mapping[str, Any],
) -> str:
    if capture_count.get("threshold_met") is True:
        return CAPTURE_THRESHOLD_MET
    if not watcher_status.get("latest_heartbeat_found") or not watcher_status.get("watcher_likely_running"):
        if watcher_status.get("watcher_stale"):
            return CAPTURE_WATCHER_STALE
        return CAPTURE_WATCHER_INACTIVE
    if watcher_status.get("watcher_stale"):
        return CAPTURE_WATCHER_STALE
    return CAPTURE_THRESHOLD_NOT_MET


def append_capture_count_sync_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = capture_count_sync_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "sync_id": str(record.get("sync_id") or f"r176_capture_count_sync_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "target_family": dict(record.get("target_family") or {}),
            "capture_count": dict(record.get("capture_count") or {}),
            "watcher_status": dict(record.get("watcher_status") or {}),
            "threshold_status": record.get("threshold_status"),
            "r158_should_be_rerun": bool(record.get("r158_should_be_rerun")),
            "tiny_live_evidence_threshold_met": bool(record.get("tiny_live_evidence_threshold_met")),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_capture_count_sync_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = capture_count_sync_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def capture_count_sync_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_capture_count_sync_8m_short_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _recommended_next_operator_move(threshold_status: str, capture_count: Mapping[str, Any]) -> str:
    if threshold_status == CAPTURE_THRESHOLD_MET:
        return RUN_R177_EVIDENCE_THRESHOLD_RECHECK
    if threshold_status in {CAPTURE_WATCHER_INACTIVE, CAPTURE_WATCHER_STALE}:
        return START_WATCHER_NOW
    if int(capture_count.get("fresh_capture_count") or 0) > 0:
        return RUN_R158_AFTER_MORE_CAPTURES
    return KEEP_WATCHER_RUNNING


def _recommended_next_engineering_move(threshold_status: str, capture_count: Mapping[str, Any]) -> str:
    count = int(capture_count.get("fresh_capture_count") or 0)
    required = int(capture_count.get("required_fresh_capture_count") or MIN_FRESH_CANDIDATES)
    if threshold_status == CAPTURE_THRESHOLD_MET:
        return "Create/run R177 to rerun R158 evidence readiness and decide if risk-contract apply review can proceed; no live execution."
    if threshold_status == CAPTURE_WATCHER_STALE:
        return "Heartbeat is stale; restart the R157/R176 tmux watcher, then rerun this sync after new heartbeats arrive."
    if threshold_status == CAPTURE_WATCHER_INACTIVE:
        return "No active watcher heartbeat is visible; start the safe tmux watcher and keep collecting paper-only captures."
    return f"Keep watcher running until fresh captures reach {required}; current unique count is {count}."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set short lane tiny_live",
        "write risk contract config",
        "transfer",
        "withdraw",
    ]


def _record_lane_key(record: Mapping[str, Any]) -> str:
    lane = record.get("target_lane")
    if isinstance(lane, Mapping) and lane.get("lane_key"):
        return str(lane.get("lane_key"))
    return str(record.get("captured_lane_key") or "")


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _target_from_key(lane_key: str) -> dict[str, Any]:
    parts = str(lane_key or "").split("|")
    return {
        "lane_key": lane_key,
        "symbol": parts[0] if len(parts) > 0 else "",
        "timeframe": parts[1] if len(parts) > 1 else "",
        "direction": parts[2] if len(parts) > 2 else "",
        "entry_mode": parts[3] if len(parts) > 3 else "",
        "current_mode": "unknown",
    }


def _empty_capture_count() -> dict[str, Any]:
    return {
        "fresh_capture_count": 0,
        "required_fresh_capture_count": int(MIN_FRESH_CANDIDATES),
        "threshold_met": False,
        "unique_captured_signal_ids": [],
        "latest_captured_signal_id": None,
    }


def _empty_watcher_status() -> dict[str, Any]:
    return {
        "latest_heartbeat_found": False,
        "latest_heartbeat_status": None,
        "latest_heartbeat_iteration": None,
        "heartbeat_age_seconds": None,
        "watcher_likely_running": False,
        "watcher_stale": False,
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
