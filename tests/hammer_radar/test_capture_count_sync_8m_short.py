from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.capture_count_sync_8m_short import (
    CAPTURE_COUNT_SYNC_RECORDED,
    CAPTURE_COUNT_SYNC_REJECTED,
    CAPTURE_THRESHOLD_MET,
    CAPTURE_THRESHOLD_NOT_MET,
    CAPTURE_WATCHER_STALE,
    CONFIRM_CAPTURE_COUNT_SYNC_RECORDING_PHRASE,
    LEDGER_FILENAME,
    build_capture_count_sync_8m_short,
    build_watcher_heartbeat_status,
    classify_capture_threshold_status,
    count_unique_fresh_captures,
    load_capture_count_sync_records,
)

NOW = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_capture(log_dir, "fresh-short-1")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))

    payload = build_capture_count_sync_8m_short(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["sync_recorded"] is False
    assert payload["record_sync_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_capture(log_dir, "fresh-short-1")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))

    payload = build_capture_count_sync_8m_short(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_sync=True,
        confirm_capture_count_sync="wrong",
        now=NOW,
    )

    assert payload["status"] == CAPTURE_COUNT_SYNC_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["sync_recorded"] is False
    assert load_capture_count_sync_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    _write_capture(log_dir, "fresh-short-1")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_capture_count_sync_8m_short(
        log_dir=log_dir,
        config_path=config_path,
        record_sync=True,
        confirm_capture_count_sync=CONFIRM_CAPTURE_COUNT_SYNC_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_capture_count_sync_records(log_dir=log_dir, limit=0)

    assert payload["status"] == CAPTURE_COUNT_SYNC_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["sync_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "CAPTURE_COUNT_SYNC_8M_SHORT"
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")


def test_counts_unique_fresh_captures() -> None:
    payload = count_unique_fresh_captures(
        [
            {"paper_evidence_captured": True, "captured_signal_id": "fresh-short-2"},
            {"paper_evidence_captured": True, "captured_signal_id": "fresh-short-1"},
            {"paper_evidence_captured": True, "captured_signal_id": "fresh-short-1"},
            {"paper_evidence_captured": False, "captured_signal_id": "ignored"},
        ],
        required_count=10,
    )

    assert payload["fresh_capture_count"] == 2
    assert payload["unique_captured_signal_ids"] == ["fresh-short-2", "fresh-short-1"]
    assert payload["latest_captured_signal_id"] == "fresh-short-2"


def test_threshold_false_below_10(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    for index in range(9):
        _write_capture(log_dir, f"fresh-short-{index}")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))

    payload = build_capture_count_sync_8m_short(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["capture_count"]["fresh_capture_count"] == 9
    assert payload["capture_count"]["threshold_met"] is False
    assert payload["threshold_status"] == CAPTURE_THRESHOLD_NOT_MET


def test_threshold_true_at_10_or_more(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    for index in range(10):
        _write_capture(log_dir, f"fresh-short-{index}")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))

    payload = build_capture_count_sync_8m_short(
        log_dir=log_dir,
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["capture_count"]["fresh_capture_count"] == 10
    assert payload["capture_count"]["threshold_met"] is True
    assert payload["threshold_status"] == CAPTURE_THRESHOLD_MET
    assert payload["r158_should_be_rerun"] is True


def test_watcher_status_detects_recent_heartbeat() -> None:
    status = build_watcher_heartbeat_status(
        [
            {
                "generated_at": (NOW - timedelta(seconds=30)).isoformat(),
                "status": "SHORT_PAPER_CAPTURE_ITERATION_COMPLETED",
                "iteration": 4,
                "sleep_seconds": 60,
            }
        ],
        now=NOW,
    )

    assert status["latest_heartbeat_found"] is True
    assert status["latest_heartbeat_iteration"] == 4
    assert status["watcher_likely_running"] is True
    assert status["watcher_stale"] is False


def test_watcher_status_detects_stale_heartbeat() -> None:
    status = build_watcher_heartbeat_status(
        [
            {
                "generated_at": (NOW - timedelta(seconds=600)).isoformat(),
                "status": "SHORT_PAPER_CAPTURE_ITERATION_COMPLETED",
                "iteration": 4,
                "sleep_seconds": 60,
            }
        ],
        now=NOW,
    )

    assert status["latest_heartbeat_found"] is True
    assert status["watcher_likely_running"] is False
    assert status["watcher_stale"] is True
    assert classify_capture_threshold_status(
        capture_count={"threshold_met": False},
        watcher_status=status,
    ) == CAPTURE_WATCHER_STALE


def test_safe_tmux_watcher_command_included(tmp_path: Path) -> None:
    payload = build_capture_count_sync_8m_short(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    commands = payload["safe_watcher_commands"]

    assert commands["tmux_session"] == "r176-8m-short-capture"
    assert "tmux new-session -d -s r176-8m-short-capture" in commands["start_24h_command"]
    assert "short-paper-evidence-capture-loop" in commands["start_24h_command"]
    assert "--max-iterations 1440" in commands["start_24h_command"]
    assert "tmux has-session -t r176-8m-short-capture" in commands["check_command"]


def test_no_env_config_mutation_no_binance_calls(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    _write_capture(log_dir, "fresh-short-1")
    _write_heartbeat(log_dir, NOW - timedelta(seconds=30))
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_capture_count_sync_8m_short(log_dir=log_dir, config_path=config_path, now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False


def test_no_order_live_transfer_withdraw_or_signed_actions(tmp_path: Path) -> None:
    payload = build_capture_count_sync_8m_short(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    safety = payload["safety"]

    assert safety["order_placed"] is False
    assert safety["real_order_placed"] is False
    assert safety["execution_attempted"] is False
    assert safety["order_payload_created"] is False
    assert safety["executable_payload_created"] is False
    assert safety["signed_order_request_created"] is False
    assert safety["signed_trading_request_created"] is False
    assert safety["signed_readonly_request_created"] is False
    assert safety["binance_test_order_endpoint_called"] is False
    assert safety["transfer_endpoint_called"] is False
    assert safety["withdraw_endpoint_called"] is False
    assert safety["secrets_shown"] is False
    assert safety["global_live_flags_changed"] is False
    assert safety["kill_switch_disabled"] is False
    assert safety["paper_live_separation_intact"] is True


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "capture-count-sync-8m-short",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    help_result = subprocess.run(
        [".venv/bin/python", "-m", "src.app.hammer_radar.operator.inspect", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["target_family"]["lane_key"] == LANE_8M_SHORT
    assert "capture-count-sync-8m-short" in help_result.stdout


def _write_capture(log_dir: Path, signal_id: str) -> None:
    _append(
        log_dir / "short_paper_evidence_capture.ndjson",
        {
            "event_type": "SHORT_PAPER_EVIDENCE_CAPTURE",
            "status": "SHORT_PAPER_EVIDENCE_CAPTURED",
            "capture_id": f"capture-{signal_id}",
            "captured_signal_id": signal_id,
            "captured_lane_key": LANE_8M_SHORT,
            "paper_evidence_captured": True,
            "target_lane": {
                "lane_key": LANE_8M_SHORT,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "mode": "paper",
            },
        },
    )


def _write_heartbeat(log_dir: Path, generated_at: datetime, *, status: str = "SHORT_PAPER_CAPTURE_ITERATION_COMPLETED") -> None:
    _append(
        log_dir / "short_paper_evidence_capture_heartbeats.ndjson",
        {
            "event_type": "SHORT_PAPER_EVIDENCE_CAPTURE_HEARTBEAT",
            "capture_id": "capture-watch",
            "generated_at": generated_at.isoformat(),
            "iteration": 4,
            "max_iterations": 1440,
            "sleep_seconds": 60,
            "status": status,
            "target_lane": {
                "lane_key": LANE_8M_SHORT,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "mode": "paper",
            },
        },
    )


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "default_mode": "disabled",
                "lanes": [
                    {
                        "symbol": "BTCUSDT",
                        "timeframe": "8m",
                        "direction": "short",
                        "entry_mode": "ladder_close_50_618",
                        "mode": "paper",
                        "max_daily_trades": 1,
                        "max_daily_loss_pct": 0.15,
                        "freshness_seconds": 60,
                        "cooldown_after_loss_minutes": 120,
                        "require_protective_orders": True,
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
