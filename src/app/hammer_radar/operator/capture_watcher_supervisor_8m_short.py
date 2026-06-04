"""R179 paper-only capture watcher supervisor for BTCUSDT 8m short.

This module supervises local R157/R176 evidence collection state only. It
reads capture and heartbeat ledgers, can append a local supervisor record after
exact confirmation, and can optionally restart the paper watcher in tmux. It
never mutates env/config/lane/risk state, calls Binance, creates payloads,
places orders, transfers, withdraws, disables safety controls, or authorizes
live execution.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.capture_count_sync_8m_short import (
    DEFAULT_LATEST_CAPTURES,
    DEFAULT_LATEST_HEARTBEATS,
    DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    TMUX_SESSION,
    build_watcher_heartbeat_status,
    count_unique_fresh_captures,
    load_short_capture_heartbeats,
    load_short_capture_records,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import (
    CONFIRM_SHORT_PAPER_CAPTURE_PHRASE,
    HEARTBEAT_LEDGER_FILENAME as SHORT_CAPTURE_HEARTBEAT_LEDGER_FILENAME,
    LEDGER_FILENAME as SHORT_CAPTURE_LEDGER_FILENAME,
    SHORT_PAPER_CAPTURE_EXITED,
)
from src.app.hammer_radar.operator.short_strategy_packet import (
    DEFAULT_TARGET_LANE_KEY,
    MIN_FRESH_CANDIDATES,
    build_short_strategy_target_family,
)

CAPTURE_WATCHER_SUPERVISOR_READY = "CAPTURE_WATCHER_SUPERVISOR_READY"
CAPTURE_WATCHER_SUPERVISOR_REJECTED = "CAPTURE_WATCHER_SUPERVISOR_REJECTED"
CAPTURE_WATCHER_SUPERVISOR_RECORDED = "CAPTURE_WATCHER_SUPERVISOR_RECORDED"
CAPTURE_WATCHER_SUPERVISOR_BLOCKED = "CAPTURE_WATCHER_SUPERVISOR_BLOCKED"
CAPTURE_WATCHER_SUPERVISOR_LOOP_STARTED = "CAPTURE_WATCHER_SUPERVISOR_LOOP_STARTED"
CAPTURE_WATCHER_SUPERVISOR_LOOP_EXITED = "CAPTURE_WATCHER_SUPERVISOR_LOOP_EXITED"
CAPTURE_WATCHER_SUPERVISOR_ERROR = "CAPTURE_WATCHER_SUPERVISOR_ERROR"

THRESHOLD_MET_STOP_SUPERVISING = "THRESHOLD_MET_STOP_SUPERVISING"
WATCHER_RUNNING_KEEP_WAITING = "WATCHER_RUNNING_KEEP_WAITING"
WATCHER_EXITED_AFTER_CAPTURE_RESTART_RECOMMENDED = "WATCHER_EXITED_AFTER_CAPTURE_RESTART_RECOMMENDED"
WATCHER_STALE_RESTART_RECOMMENDED = "WATCHER_STALE_RESTART_RECOMMENDED"
WATCHER_NOT_FOUND_RESTART_RECOMMENDED = "WATCHER_NOT_FOUND_RESTART_RECOMMENDED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

KEEP_WATCHER_RUNNING = "KEEP_WATCHER_RUNNING"
RESTART_WATCHER_NOW = "RESTART_WATCHER_NOW"
RUN_SUPERVISOR_LOOP = "RUN_SUPERVISOR_LOOP"
RUN_R177_WHEN_10_CAPTURES = "RUN_R177_WHEN_10_CAPTURES"

EVENT_TYPE = "CAPTURE_WATCHER_SUPERVISOR_8M_SHORT"
LEDGER_FILENAME = "capture_watcher_supervisor_8m_short.ndjson"
CONFIRM_CAPTURE_WATCHER_SUPERVISOR_RECORDING_PHRASE = (
    "I CONFIRM CAPTURE WATCHER SUPERVISOR RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_MAX_SUPERVISOR_ITERATIONS = 60
DEFAULT_SLEEP_SECONDS = 60
DEFAULT_RESTART_WATCHER_MAX_ITERATIONS = 1440
DEFAULT_RESTART_WATCHER_SLEEP_SECONDS = 60
DEFAULT_RESTART_WATCHER_LATEST_SIGNALS = 500
DEFAULT_RESTART_WATCHER_LATEST_SCANS = 1000
DEFAULT_RESTART_WATCHER_ITERATION_TIMEOUT_SECONDS = 30
DEFAULT_RESTART_WATCHER_HEARTBEAT_EVERY = 1

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
    "src/app/hammer_radar/operator/capture_count_sync_8m_short.py",
    "src/app/hammer_radar/operator/short_paper_evidence_capture_loop.py",
    "src/app/hammer_radar/operator/short_strategy_packet.py",
    f"logs/hammer_radar_forward/{SHORT_CAPTURE_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_CAPTURE_HEARTBEAT_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_capture_watcher_supervisor_status(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_heartbeats: int = DEFAULT_LATEST_HEARTBEATS,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    record_supervisor: bool = False,
    confirm_capture_watcher_supervisor: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
    loop_requested: bool = False,
    max_supervisor_iterations: int = DEFAULT_MAX_SUPERVISOR_ITERATIONS,
    sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
    allow_paper_watcher_restart: bool = False,
    restart_attempted: bool = False,
    restart_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_capture_watcher_supervisor == CONFIRM_CAPTURE_WATCHER_SUPERVISOR_RECORDING_PHRASE
    try:
        target = build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)
        captures = load_short_capture_records(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            limit=latest_captures,
        )
        heartbeats = load_short_capture_heartbeats(
            log_dir=resolved_log_dir,
            lane_key=target["lane_key"],
            limit=latest_heartbeats,
        )
        capture_count = count_unique_fresh_captures(captures, required_count=MIN_FRESH_CANDIDATES)
        watcher_status = build_watcher_heartbeat_status(
            heartbeats,
            now=generated_at,
            stale_after_seconds=stale_after_seconds,
        )
        supervisor_decision = classify_capture_watcher_supervisor_status(
            capture_count=capture_count,
            watcher_status=watcher_status,
            latest_heartbeat=heartbeats[0] if heartbeats else None,
        )
        status = CAPTURE_WATCHER_SUPERVISOR_READY
        if supervisor_decision == UNKNOWN_NEEDS_MANUAL_REVIEW:
            status = CAPTURE_WATCHER_SUPERVISOR_BLOCKED
        if record_supervisor and not confirmation_valid:
            status = CAPTURE_WATCHER_SUPERVISOR_REJECTED
        elif record_supervisor and confirmation_valid:
            status = CAPTURE_WATCHER_SUPERVISOR_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "supervisor_recorded": False,
            "supervisor_id": None,
            "record_supervisor_requested": bool(record_supervisor),
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
            "supervisor_decision": supervisor_decision,
            "safe_restart_commands": {
                "tmux_session": TMUX_SESSION,
                "tmux_restart_command": build_safe_tmux_restart_command(lane_key=target["lane_key"]),
                "direct_command": build_safe_direct_restart_command(lane_key=target["lane_key"]),
            },
            "supervisor_loop": {
                "loop_requested": bool(loop_requested),
                "max_supervisor_iterations": max(1, int(max_supervisor_iterations)),
                "sleep_seconds": max(0, int(sleep_seconds)),
                "restart_attempted": bool(restart_attempted),
                "restart_allowed": bool(allow_paper_watcher_restart),
                "restart_result": dict(restart_result or {}),
            },
            "recommended_next_operator_move": _recommended_next_operator_move(supervisor_decision),
            "recommended_next_engineering_move": _recommended_next_engineering_move(supervisor_decision),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_supervisor and confirmation_valid:
            record = append_capture_watcher_supervisor_record(payload, log_dir=resolved_log_dir)
            payload["supervisor_recorded"] = True
            payload["supervisor_id"] = record["supervisor_id"]
            payload["ledger_path"] = str(capture_watcher_supervisor_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": CAPTURE_WATCHER_SUPERVISOR_ERROR,
                "generated_at": generated_at.isoformat(),
                "supervisor_recorded": False,
                "supervisor_id": None,
                "record_supervisor_requested": bool(record_supervisor),
                "confirmation_valid": bool(confirmation_valid),
                "target_family": _target_from_key(lane_key),
                "capture_count": _empty_capture_count(),
                "watcher_status": _empty_watcher_status(),
                "supervisor_decision": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "safe_restart_commands": {
                    "tmux_session": TMUX_SESSION,
                    "tmux_restart_command": build_safe_tmux_restart_command(lane_key=lane_key),
                    "direct_command": build_safe_direct_restart_command(lane_key=lane_key),
                },
                "supervisor_loop": {
                    "loop_requested": bool(loop_requested),
                    "max_supervisor_iterations": max(1, int(max_supervisor_iterations)),
                    "sleep_seconds": max(0, int(sleep_seconds)),
                    "restart_attempted": bool(restart_attempted),
                    "restart_allowed": bool(allow_paper_watcher_restart),
                    "restart_result": dict(restart_result or {}),
                },
                "recommended_next_operator_move": RESTART_WATCHER_NOW,
                "recommended_next_engineering_move": "Fix R179 supervisor preview error before restarting or recording.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_capture_watcher_supervisor_once(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_heartbeats: int = DEFAULT_LATEST_HEARTBEATS,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    record_supervisor: bool = False,
    confirm_capture_watcher_supervisor: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
    loop_requested: bool = False,
    max_supervisor_iterations: int = DEFAULT_MAX_SUPERVISOR_ITERATIONS,
    sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
    allow_paper_watcher_restart: bool = False,
    restart_fn: Callable[[str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    initial = build_capture_watcher_supervisor_status(
        log_dir=log_dir,
        lane_key=lane_key,
        latest_captures=latest_captures,
        latest_heartbeats=latest_heartbeats,
        stale_after_seconds=stale_after_seconds,
        record_supervisor=False,
        confirm_capture_watcher_supervisor=confirm_capture_watcher_supervisor,
        config_path=config_path,
        now=now,
        loop_requested=loop_requested,
        max_supervisor_iterations=max_supervisor_iterations,
        sleep_seconds=sleep_seconds,
        allow_paper_watcher_restart=allow_paper_watcher_restart,
    )
    restart_attempted = False
    restart_result: Mapping[str, Any] | None = None
    if allow_paper_watcher_restart and _decision_recommends_restart(str(initial.get("supervisor_decision"))):
        restart_attempted = True
        runner = restart_fn or _restart_tmux_paper_watcher
        restart_result = runner(build_safe_direct_restart_command(lane_key=lane_key))

    return build_capture_watcher_supervisor_status(
        log_dir=log_dir,
        lane_key=lane_key,
        latest_captures=latest_captures,
        latest_heartbeats=latest_heartbeats,
        stale_after_seconds=stale_after_seconds,
        record_supervisor=record_supervisor,
        confirm_capture_watcher_supervisor=confirm_capture_watcher_supervisor,
        config_path=config_path,
        now=now,
        loop_requested=loop_requested,
        max_supervisor_iterations=max_supervisor_iterations,
        sleep_seconds=sleep_seconds,
        allow_paper_watcher_restart=allow_paper_watcher_restart,
        restart_attempted=restart_attempted,
        restart_result=restart_result,
    )


def run_capture_watcher_supervisor_loop(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    latest_captures: int = DEFAULT_LATEST_CAPTURES,
    latest_heartbeats: int = DEFAULT_LATEST_HEARTBEATS,
    stale_after_seconds: int = DEFAULT_WATCHER_STALE_AFTER_SECONDS,
    record_supervisor: bool = False,
    confirm_capture_watcher_supervisor: str | None = None,
    config_path: str | Path | None = None,
    max_supervisor_iterations: int = DEFAULT_MAX_SUPERVISOR_ITERATIONS,
    sleep_seconds: int = DEFAULT_SLEEP_SECONDS,
    allow_paper_watcher_restart: bool = False,
    restart_fn: Callable[[str], Mapping[str, Any]] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    bounded_iterations = max(1, int(max_supervisor_iterations))
    bounded_sleep = max(0, int(sleep_seconds))
    sleeper = sleep_fn or time.sleep
    last_payload: dict[str, Any] | None = None

    for iteration in range(1, bounded_iterations + 1):
        last_payload = build_capture_watcher_supervisor_once(
            log_dir=log_dir,
            lane_key=lane_key,
            latest_captures=latest_captures,
            latest_heartbeats=latest_heartbeats,
            stale_after_seconds=stale_after_seconds,
            record_supervisor=record_supervisor,
            confirm_capture_watcher_supervisor=confirm_capture_watcher_supervisor,
            config_path=config_path,
            loop_requested=True,
            max_supervisor_iterations=bounded_iterations,
            sleep_seconds=bounded_sleep,
            allow_paper_watcher_restart=allow_paper_watcher_restart,
            restart_fn=restart_fn,
        )
        last_payload["loop_iteration"] = iteration
        if last_payload.get("supervisor_decision") == THRESHOLD_MET_STOP_SUPERVISING:
            break
        if iteration < bounded_iterations:
            sleeper(float(bounded_sleep))

    payload = dict(last_payload or {})
    payload["status"] = CAPTURE_WATCHER_SUPERVISOR_LOOP_EXITED
    payload.setdefault("supervisor_loop", {})
    payload["supervisor_loop"] = {
        **dict(payload.get("supervisor_loop") or {}),
        "loop_requested": True,
        "loop_status": CAPTURE_WATCHER_SUPERVISOR_LOOP_EXITED,
        "iterations_completed": int(payload.get("loop_iteration") or bounded_iterations),
    }
    return _sanitize(payload)


def build_safe_tmux_restart_command(*, lane_key: str = DEFAULT_TARGET_LANE_KEY) -> str:
    direct_command = build_safe_direct_restart_command(lane_key=lane_key)
    return (
        f"tmux kill-session -t {TMUX_SESSION} 2>/dev/null || true; "
        f"tmux new-session -d -s {TMUX_SESSION} '{direct_command}'"
    )


def build_safe_direct_restart_command(*, lane_key: str = DEFAULT_TARGET_LANE_KEY) -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward short-paper-evidence-capture-loop "
        f'--lane-key "{lane_key}" '
        f"--latest-signals {DEFAULT_RESTART_WATCHER_LATEST_SIGNALS} "
        f"--latest-scans {DEFAULT_RESTART_WATCHER_LATEST_SCANS} "
        f"--max-iterations {DEFAULT_RESTART_WATCHER_MAX_ITERATIONS} "
        f"--sleep-seconds {DEFAULT_RESTART_WATCHER_SLEEP_SECONDS} "
        f"--iteration-timeout-seconds {DEFAULT_RESTART_WATCHER_ITERATION_TIMEOUT_SECONDS} "
        f"--heartbeat-every {DEFAULT_RESTART_WATCHER_HEARTBEAT_EVERY} "
        "--run-capture-loop --record-capture "
        f'--confirm-short-paper-capture "{CONFIRM_SHORT_PAPER_CAPTURE_PHRASE}"'
    )


def classify_capture_watcher_supervisor_status(
    *,
    capture_count: Mapping[str, Any],
    watcher_status: Mapping[str, Any],
    latest_heartbeat: Mapping[str, Any] | None = None,
) -> str:
    if capture_count.get("threshold_met") is True:
        return THRESHOLD_MET_STOP_SUPERVISING
    if watcher_status.get("watcher_likely_running") is True:
        return WATCHER_RUNNING_KEEP_WAITING
    latest = latest_heartbeat or {}
    latest_status = str(watcher_status.get("latest_heartbeat_status") or latest.get("status") or "")
    if latest_status == SHORT_PAPER_CAPTURE_EXITED and (
        latest.get("paper_evidence_captured") is True
        or bool(latest.get("captured_signal_id"))
        or bool(capture_count.get("latest_captured_signal_id"))
    ):
        return WATCHER_EXITED_AFTER_CAPTURE_RESTART_RECOMMENDED
    if watcher_status.get("watcher_stale") is True:
        return WATCHER_STALE_RESTART_RECOMMENDED
    if watcher_status.get("latest_heartbeat_found") is False:
        return WATCHER_NOT_FOUND_RESTART_RECOMMENDED
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_capture_watcher_supervisor_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = capture_watcher_supervisor_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "supervisor_id": str(record.get("supervisor_id") or f"r179_capture_watcher_supervisor_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "target_family": dict(record.get("target_family") or {}),
            "capture_count": dict(record.get("capture_count") or {}),
            "watcher_status": dict(record.get("watcher_status") or {}),
            "supervisor_decision": record.get("supervisor_decision"),
            "safe_restart_commands": dict(record.get("safe_restart_commands") or {}),
            "supervisor_loop": dict(record.get("supervisor_loop") or {}),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_capture_watcher_supervisor_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = capture_watcher_supervisor_records_path(get_log_dir(log_dir, use_env=True))
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


def capture_watcher_supervisor_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_capture_watcher_supervisor_8m_short_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _restart_tmux_paper_watcher(direct_command: str) -> dict[str, Any]:
    subprocess.run(["tmux", "kill-session", "-t", TMUX_SESSION], check=False, capture_output=True, text=True)
    result = subprocess.run(
        ["tmux", "new-session", "-d", "-s", TMUX_SESSION, direct_command],
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "tmux_session": TMUX_SESSION,
        "returncode": result.returncode,
        "started": result.returncode == 0,
        "stderr_tail": (result.stderr or "")[-500:],
    }


def _decision_recommends_restart(decision: str) -> bool:
    return decision in {
        WATCHER_EXITED_AFTER_CAPTURE_RESTART_RECOMMENDED,
        WATCHER_STALE_RESTART_RECOMMENDED,
        WATCHER_NOT_FOUND_RESTART_RECOMMENDED,
    }


def _recommended_next_operator_move(decision: str) -> str:
    if decision == THRESHOLD_MET_STOP_SUPERVISING:
        return RUN_R177_WHEN_10_CAPTURES
    if decision == WATCHER_RUNNING_KEEP_WAITING:
        return KEEP_WATCHER_RUNNING
    if _decision_recommends_restart(decision):
        return RESTART_WATCHER_NOW
    return RUN_SUPERVISOR_LOOP


def _recommended_next_engineering_move(decision: str) -> str:
    if decision == THRESHOLD_MET_STOP_SUPERVISING:
        return "Stop supervising the watcher and run R177 evidence threshold recheck; do not enable live execution."
    if decision == WATCHER_RUNNING_KEEP_WAITING:
        return "Keep the R157 paper watcher running until unique fresh captures reach 10."
    if decision == WATCHER_EXITED_AFTER_CAPTURE_RESTART_RECOMMENDED:
        return "Restart the R157 paper watcher with the safe tmux command so capture collection can continue."
    if decision == WATCHER_STALE_RESTART_RECOMMENDED:
        return "Heartbeat is stale; restart the paper watcher and confirm new heartbeat records appear."
    if decision == WATCHER_NOT_FOUND_RESTART_RECOMMENDED:
        return "No watcher heartbeat was found; start the paper watcher with the safe tmux command."
    return "Review the latest capture and heartbeat ledgers before restarting or recording supervisor evidence."


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
