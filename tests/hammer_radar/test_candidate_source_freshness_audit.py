from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

from src.app.hammer_radar.operator.candidate_source_freshness_audit import (
    CANDIDATE_SOURCE_AUDIT_READY,
    CANDIDATE_SOURCE_AUDIT_RECORDED,
    CANDIDATE_SOURCE_AUDIT_REJECTED,
    CONFIRM_CANDIDATE_SOURCE_AUDIT_RECORDING_PHRASE,
    LEDGER_FILENAME,
    NO_TARGET_LANE_SIGNALS_DURING_WINDOW,
    PAPER_CAPTURE_BLOCKED_AFTER_ELIGIBLE_SIGNAL,
    SOURCE_FEED_STALE_OR_STOPPED,
    TARGET_LANE_SIGNALS_ALL_STALE,
    TARGET_TIMEFRAME_PRESENT_BUT_WRONG_DIRECTION,
    WATCH_SCAN_WINDOW_TOO_NARROW,
    WATCHER_HEALTHY_MARKET_QUIET,
    build_candidate_source_freshness_audit,
    load_candidate_source_freshness_audit_records,
)

LANE_13M = "BTCUSDT|13m|long|ladder_close_50_618"
LANE_44M = "BTCUSDT|44m|long|ladder_close_50_618"
NOW = datetime(2026, 5, 30, 12, 10, tzinfo=UTC)
STARTED = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)
ENDED = datetime(2026, 5, 30, 12, 9, tzinfo=UTC)


def test_preview_writes_no_audit(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_completed_watch(log_dir)
    _write_signal(log_dir, _signal("ETHUSDT", "13m", "long", ENDED))
    _write_source(log_dir, "paper_refresh_runs.ndjson", ENDED)

    payload = build_candidate_source_freshness_audit(log_dir=log_dir, now=NOW)

    assert payload["status"] == CANDIDATE_SOURCE_AUDIT_READY
    assert payload["audit_recorded"] is False
    assert payload["audit_id"] is None
    assert payload["record_audit_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_completed_watch(log_dir)

    payload = build_candidate_source_freshness_audit(
        log_dir=log_dir,
        record_audit=True,
        confirm_audit="wrong",
        now=NOW,
    )

    assert payload["status"] == CANDIDATE_SOURCE_AUDIT_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["audit_recorded"] is False
    assert load_candidate_source_freshness_audit_records(log_dir=log_dir, limit=0) == []


def test_exact_confirmation_records_audit_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_completed_watch(log_dir)
    _write_source(log_dir, "paper_refresh_runs.ndjson", ENDED)

    payload = build_candidate_source_freshness_audit(
        log_dir=log_dir,
        record_audit=True,
        confirm_audit=CONFIRM_CANDIDATE_SOURCE_AUDIT_RECORDING_PHRASE,
        now=NOW,
    )

    records = load_candidate_source_freshness_audit_records(log_dir=log_dir, limit=0)
    assert payload["status"] == CANDIDATE_SOURCE_AUDIT_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["audit_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "CANDIDATE_SOURCE_FRESHNESS_AUDIT"
    assert records[0]["safety"]["order_placed"] is False
    assert records[0]["safety"]["real_order_placed"] is False
    assert records[0]["safety"]["execution_attempted"] is False


def test_source_stale_classification(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_completed_watch(log_dir)

    payload = build_candidate_source_freshness_audit(log_dir=log_dir, now=NOW)

    assert payload["starvation_classification"] == SOURCE_FEED_STALE_OR_STOPPED
    assert payload["source_freshness"]["source_appears_live"] is False


def test_all_target_signals_stale_classification(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_completed_watch(log_dir)
    _write_signal(log_dir, _signal("BTCUSDT", "13m", "long", STARTED + timedelta(minutes=1)))
    _write_source(log_dir, "paper_refresh_runs.ndjson", ENDED)

    payload = build_candidate_source_freshness_audit(log_dir=log_dir, now=NOW)

    assert payload["starvation_classification"] == TARGET_LANE_SIGNALS_ALL_STALE
    assert payload["candidate_distribution"]["target_lane_stale_count"] == 1
    assert payload["candidate_distribution"]["target_lane_fresh_count"] == 0


def test_no_target_lane_signals_classification(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_completed_watch(log_dir, iterations=10, max_iterations=720)
    _write_signal(log_dir, _signal("ETHUSDT", "13m", "long", ENDED))
    _write_source(log_dir, "paper_refresh_runs.ndjson", ENDED)

    payload = build_candidate_source_freshness_audit(log_dir=log_dir, now=NOW)

    assert payload["starvation_classification"] == NO_TARGET_LANE_SIGNALS_DURING_WINDOW
    assert payload["candidate_distribution"]["target_lane_exact_or_normalized_count"] == 0


def test_wrong_direction_dominates_classification(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_completed_watch(log_dir)
    _write_signal(log_dir, _signal("BTCUSDT", "13m", "short", ENDED))
    _write_source(log_dir, "paper_refresh_runs.ndjson", ENDED)

    payload = build_candidate_source_freshness_audit(log_dir=log_dir, now=NOW)

    assert payload["starvation_classification"] == TARGET_TIMEFRAME_PRESENT_BUT_WRONG_DIRECTION
    assert payload["candidate_distribution"]["short_candidate_count"] == 1
    assert "R152 short-lane paper-only" in payload["recommended_next_engineering_move"]


def test_watcher_healthy_market_quiet_classification(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_completed_watch(log_dir)
    _write_signal(log_dir, _signal("ETHUSDT", "13m", "long", ENDED))
    _write_source(log_dir, "paper_refresh_runs.ndjson", ENDED)

    payload = build_candidate_source_freshness_audit(log_dir=log_dir, now=NOW)

    assert payload["starvation_classification"] == WATCHER_HEALTHY_MARKET_QUIET
    assert payload["watcher_health"]["last_heartbeat_status"] == "WATCH_EXITED"
    assert payload["recommended_next_operator_move"] == "WAIT_FOR_FRESH_CANDIDATE"


def test_scan_window_too_narrow_classification_if_detectable(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_completed_watch(log_dir, latest_signals=1)
    _write_signal(log_dir, _signal("BTCUSDT", "13m", "long", ENDED))
    _write_signal(log_dir, _signal("ETHUSDT", "13m", "long", ENDED))
    _write_source(log_dir, "paper_refresh_runs.ndjson", ENDED)

    payload = build_candidate_source_freshness_audit(log_dir=log_dir, latest_signals=10, now=NOW)

    assert payload["starvation_classification"] == WATCH_SCAN_WINDOW_TOO_NARROW
    assert payload["candidate_distribution"]["target_lane_count_inside_watch_latest_signals"] == 0
    assert payload["candidate_distribution"]["target_lane_count_outside_watch_latest_signals"] == 1


def test_paper_capture_blocked_after_eligible_signal_classification(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_completed_watch(log_dir)
    _write_source(log_dir, "paper_refresh_runs.ndjson", ENDED)
    with patch(
        "src.app.hammer_radar.operator.candidate_source_freshness_audit.load_recent_signal_source_summary",
        return_value={
            "latest_timestamp": ENDED.isoformat(),
            "mtime": ENDED.isoformat(),
            "window_records_checked": 1,
            "candidate_distribution": {
                "latest_signals_checked": 1,
                "target_lane_exact_or_normalized_count": 1,
                "target_lane_fresh_count": 1,
                "target_lane_stale_count": 0,
                "target_timeframe_wrong_direction_count": 0,
                "short_candidate_count": 0,
                "wrong_timeframe_count": 0,
                "entry_mode_or_lane_key_mismatch_count": 0,
                "paper_capture_eligible_seen_count": 1,
                "target_lane_count_inside_watch_latest_signals": 1,
                "target_lane_count_outside_watch_latest_signals": 0,
            },
            "safety": _safe(),
        },
    ):
        payload = build_candidate_source_freshness_audit(log_dir=log_dir, now=NOW)

    assert payload["starvation_classification"] == PAPER_CAPTURE_BLOCKED_AFTER_ELIGIBLE_SIGNAL
    assert payload["recommended_next_operator_move"] == "STOP_AND_FIX_PAPER_CAPTURE_BLOCKER"


def test_safety_flags_all_false_except_separation(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_completed_watch(log_dir)
    payload = build_candidate_source_freshness_audit(log_dir=log_dir, now=NOW)

    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_no_binance_order_payload_network_env_or_config_mutation(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    _write_completed_watch(log_dir)
    before_env = dict(os.environ)
    with (
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "protective_preview") as protective_preview,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "submit_protective_test") as submit_protective_test,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
        patch.object(binance_futures_connector, "build_signed_test_order_request") as build_signed_test_order_request,
        patch.object(binance_futures_connector, "build_signed_protective_order_requests") as build_signed_protective_order_requests,
    ):
        payload = build_candidate_source_freshness_audit(log_dir=log_dir, now=NOW)

    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    protective_preview.assert_not_called()
    submit_test_order.assert_not_called()
    submit_protective_test.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    build_signed_test_order_request.assert_not_called()
    build_signed_protective_order_requests.assert_not_called()
    assert before_env == dict(os.environ)
    assert payload["safety"]["network_allowed"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["global_live_flags_changed"] is False


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "candidate-source-freshness-audit",
            "--latest-signals",
            "10",
            "--latest-scans",
            "20",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={"PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] in {CANDIDATE_SOURCE_AUDIT_READY, "CANDIDATE_SOURCE_AUDIT_ERROR"}
    assert "candidate-source-freshness-audit" in subprocess.run(
        [".venv/bin/python", "-m", "src.app.hammer_radar.operator.inspect", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        env={"PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    ).stdout


def _write_completed_watch(
    log_dir: Path,
    *,
    iterations: int = 720,
    max_iterations: int = 720,
    latest_signals: int = 250,
) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    watch_id = "watch-r151"
    watch_record = {
        "event_type": "FRESH_CANDIDATE_PAPER_PROOF_CAPTURE_LOOP",
        "watch_id": watch_id,
        "recorded_at_utc": ENDED.isoformat(),
        "status": "FRESH_CANDIDATE_WATCH_TIMEOUT",
        "watched_lanes": [{"lane_key": LANE_13M}, {"lane_key": LANE_44M}],
        "max_iterations": max_iterations,
        "iterations_completed": iterations,
        "paper_proof_captured": False,
        "captured_lane_key": None,
        "bounded_scan_limits": {"latest_signals": latest_signals, "latest_scans": 500},
        "iteration_summaries": [
            {
                "iteration": 1,
                "started_at": STARTED.isoformat(),
                "completed_at": (STARTED + timedelta(seconds=1)).isoformat(),
                "elapsed_seconds": 1.0,
            }
        ],
        "safety": _safe(),
    }
    _append(log_dir / "fresh_candidate_paper_proof_capture_loop.ndjson", watch_record)
    _append(
        log_dir / "fresh_candidate_paper_proof_watch_heartbeats.ndjson",
        {
            "event_type": "FRESH_CANDIDATE_PAPER_PROOF_WATCH_HEARTBEAT",
            "watch_id": watch_id,
            "generated_at": STARTED.isoformat(),
            "iteration": 1,
            "max_iterations": max_iterations,
            "sleep_seconds": 60,
            "status": "WATCH_ITERATION_COMPLETED",
            "elapsed_seconds": 1.0,
            "paper_proof_captured": False,
            "captured_lane_key": None,
            "safety": _safe(),
        },
    )
    _append(
        log_dir / "fresh_candidate_paper_proof_watch_heartbeats.ndjson",
        {
            "event_type": "FRESH_CANDIDATE_PAPER_PROOF_WATCH_HEARTBEAT",
            "watch_id": watch_id,
            "generated_at": ENDED.isoformat(),
            "iteration": iterations,
            "max_iterations": max_iterations,
            "sleep_seconds": 60,
            "status": "WATCH_EXITED",
            "elapsed_seconds": 0.0,
            "paper_proof_captured": False,
            "captured_lane_key": None,
            "safety": _safe(),
        },
    )


def _write_signal(log_dir: Path, row: dict[str, Any]) -> None:
    _append(log_dir / "signals.ndjson", row)


def _write_source(log_dir: Path, filename: str, timestamp: datetime) -> None:
    _append(log_dir / filename, {"generated_at": timestamp.isoformat(), "status": "ok"})


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _signal(symbol: str, timeframe: str, direction: str, timestamp: datetime) -> dict[str, Any]:
    return {
        "signal_id": f"{symbol}|{timeframe}|{direction}|{timestamp.isoformat()}",
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "generated_at": timestamp.isoformat(),
    }


def _safe() -> dict[str, bool]:
    return {
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "order_payload_created": False,
        "executable_payload_created": False,
        "protective_payload_created": False,
        "signed_request_created": False,
        "network_allowed": False,
        "binance_order_endpoint_called": False,
        "binance_test_order_endpoint_called": False,
        "protective_order_endpoint_called": False,
        "secrets_shown": False,
        "paper_live_separation_intact": True,
        "env_mutated": False,
        "config_written": False,
        "global_live_flags_changed": False,
    }
