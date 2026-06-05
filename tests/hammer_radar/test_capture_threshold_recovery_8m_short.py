from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.capture_threshold_recovery_8m_short import (
    CAPTURE_LEDGER_MISMATCH,
    CAPTURE_THRESHOLD_MET,
    CAPTURE_THRESHOLD_NOT_MET,
    CAPTURE_THRESHOLD_RECOVERY_RECORDED,
    CAPTURE_THRESHOLD_RECOVERY_REJECTED,
    CONFIRM_CAPTURE_THRESHOLD_RECOVERY_RECORDING_PHRASE,
    HARVESTER_RUNNING_RECENT_HEARTBEAT,
    HARVESTER_STALE,
    LEDGER_FILENAME,
    build_capture_threshold_recovery_8m_short,
    load_capture_threshold_recovery_records,
)

NOW = datetime(2026, 6, 5, 18, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
LANE_4M_LONG = "BTCUSDT|4m|long|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_matching_capture_set(log_dir, count=3)

    payload = build_capture_threshold_recovery_8m_short(log_dir=log_dir, config_path=_write_config(tmp_path / "lane_controls.json"), now=NOW)

    assert payload["record_recovery_requested"] is False
    assert payload["recovery_recorded"] is False
    assert payload["recovery_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = build_capture_threshold_recovery_8m_short(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_recovery=True,
        confirm_capture_threshold_recovery="wrong",
        now=NOW,
    )

    assert payload["status"] == CAPTURE_THRESHOLD_RECOVERY_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["recovery_recorded"] is False
    assert load_capture_threshold_recovery_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_recovery_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_capture_threshold_recovery_8m_short(
        log_dir=log_dir,
        config_path=config_path,
        record_recovery=True,
        confirm_capture_threshold_recovery=CONFIRM_CAPTURE_THRESHOLD_RECOVERY_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_capture_threshold_recovery_records(log_dir=log_dir, limit=0)

    assert payload["status"] == CAPTURE_THRESHOLD_RECOVERY_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["recovery_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "CAPTURE_THRESHOLD_RECOVERY_8M_SHORT"
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")


def test_detects_stale_full_spectrum_heartbeat(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_heartbeat(log_dir, NOW - timedelta(minutes=10))

    payload = build_capture_threshold_recovery_8m_short(log_dir=log_dir, config_path=_write_config(tmp_path / "lane_controls.json"), now=NOW)

    runtime = payload["harvester_runtime_status"]
    assert runtime["full_spectrum_heartbeat_found"] is True
    assert runtime["full_spectrum_watcher_stale"] is True
    assert runtime["watcher_status"] == HARVESTER_STALE


def test_detects_recent_full_spectrum_heartbeat(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_matching_capture_set(log_dir, count=1)
    _write_heartbeat(log_dir, NOW - timedelta(seconds=20))

    payload = build_capture_threshold_recovery_8m_short(log_dir=log_dir, config_path=_write_config(tmp_path / "lane_controls.json"), now=NOW)

    assert payload["harvester_runtime_status"]["full_spectrum_watcher_likely_running"] is True
    assert payload["harvester_runtime_status"]["watcher_status"] == HARVESTER_RUNNING_RECENT_HEARTBEAT


def test_recomputes_8m_short_capture_count(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_matching_capture_set(log_dir, count=3)

    payload = build_capture_threshold_recovery_8m_short(log_dir=log_dir, config_path=_write_config(tmp_path / "lane_controls.json"), now=NOW)

    count = payload["capture_count_recompute"]
    assert count["fresh_capture_count"] == 3
    assert count["required_fresh_capture_count"] == 10
    assert count["unique_captured_signal_ids"] == ["sig-2", "sig-1", "sig-0"]
    assert count["latest_captured_signal_id"] == "sig-2"


def test_reports_threshold_not_met_when_below_10(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_matching_capture_set(log_dir, count=3)

    payload = build_capture_threshold_recovery_8m_short(log_dir=log_dir, config_path=_write_config(tmp_path / "lane_controls.json"), now=NOW)

    assert payload["capture_count_recompute"]["threshold_met"] is False
    assert payload["threshold_status"] == CAPTURE_THRESHOLD_NOT_MET


def test_reports_threshold_met_when_at_least_10(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_matching_capture_set(log_dir, count=10)

    payload = build_capture_threshold_recovery_8m_short(log_dir=log_dir, config_path=_write_config(tmp_path / "lane_controls.json"), now=NOW)

    assert payload["capture_count_recompute"]["fresh_capture_count"] == 10
    assert payload["capture_count_recompute"]["threshold_met"] is True
    assert payload["threshold_status"] == CAPTURE_THRESHOLD_MET


def test_detects_capture_count_mismatch(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_short_capture(log_dir, "sig-short-only")
    _write_full_spectrum_record(log_dir, ["sig-harvester-only"])
    _write_count_sync(log_dir, ["sig-short-only"])

    payload = build_capture_threshold_recovery_8m_short(log_dir=log_dir, config_path=_write_config(tmp_path / "lane_controls.json"), now=NOW)

    mismatch = payload["capture_count_mismatch_report"]
    assert mismatch["mismatch_found"] is True
    assert "sig-harvester-only" in mismatch["harvester_captures_not_counted"]
    assert payload["threshold_status"] == CAPTURE_LEDGER_MISMATCH


def test_safe_operator_commands_are_present(tmp_path: Path) -> None:
    payload = build_capture_threshold_recovery_8m_short(log_dir=tmp_path / "logs", config_path=_write_config(tmp_path / "lane_controls.json"), now=NOW)

    commands = payload["safe_operator_commands"]
    assert "tmux has-session -t r198-full-spectrum-harvest" in commands["tmux_status_check"]
    assert "full-spectrum-harvester-expansion" in commands["full_spectrum_harvester_restart"]
    assert "capture-count-sync-8m-short" in commands["capture_count_recheck"]
    assert commands["heartbeat_tail"].endswith("full_spectrum_harvester_heartbeats.ndjson")


def test_no_live_authorization_env_config_mutation_or_unsafe_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_capture_threshold_recovery_8m_short(log_dir=log_dir, config_path=config_path, now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "capture-threshold-recovery-8m-short",
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
    assert "capture_count_recompute" in payload
    assert "capture-threshold-recovery-8m-short" in help_result.stdout


def _write_matching_capture_set(log_dir: Path, *, count: int) -> None:
    ids = [f"sig-{index}" for index in range(count)]
    for signal_id in ids:
        _write_short_capture(log_dir, signal_id)
    _write_full_spectrum_record(log_dir, ids)
    _write_count_sync(log_dir, ids)
    _write_heartbeat(log_dir, NOW - timedelta(seconds=20))


def _write_short_capture(log_dir: Path, signal_id: str) -> None:
    _append_json(
        log_dir / "short_paper_evidence_capture.ndjson",
        {
            "event_type": "SHORT_PAPER_EVIDENCE_CAPTURE",
            "generated_at": NOW.isoformat(),
            "target_lane": {"lane_key": LANE_8M_SHORT},
            "paper_evidence_captured": True,
            "captured_signal_id": signal_id,
            "captured_lane_key": LANE_8M_SHORT,
            "safety": {"order_placed": False},
        },
    )


def _write_full_spectrum_record(log_dir: Path, signal_ids: list[str]) -> None:
    _append_json(
        log_dir / "full_spectrum_harvester_expansion.ndjson",
        {
            "event_type": "FULL_SPECTRUM_HARVESTER_EXPANSION",
            "status": "FULL_SPECTRUM_HARVESTER_EXPANSION_CAPTURED",
            "generated_at": NOW.isoformat(),
            "harvest_id": "harvest-1",
            "scope": {"configured_paper_lanes": [_lane("8m", "short"), _lane("4m", "long")], "discovered_unconfigured_paper_lanes": [], "tiny_live_reference_lanes": []},
            "capture_summary": {
                "captured_candidates": [
                    {
                        "signal_id": signal_id,
                        "candidate_id": signal_id,
                        "lane_key": LANE_8M_SHORT,
                        "timestamp": NOW.isoformat(),
                    }
                    for signal_id in signal_ids
                ],
                "captured_lanes": [LANE_8M_SHORT] if signal_ids else [],
                "stale_by_lane": {LANE_4M_LONG: 1},
            },
            "safety": {"order_placed": False},
        },
    )


def _write_count_sync(log_dir: Path, signal_ids: list[str]) -> None:
    _append_json(
        log_dir / "capture_count_sync_8m_short.ndjson",
        {
            "event_type": "CAPTURE_COUNT_SYNC_8M_SHORT",
            "generated_at": NOW.isoformat(),
            "capture_count": {
                "fresh_capture_count": len(signal_ids),
                "required_fresh_capture_count": 10,
                "threshold_met": len(signal_ids) >= 10,
                "unique_captured_signal_ids": signal_ids,
                "latest_captured_signal_id": signal_ids[0] if signal_ids else None,
            },
            "safety": {"order_placed": False},
        },
    )


def _write_heartbeat(log_dir: Path, generated_at: datetime) -> None:
    _append_json(
        log_dir / "full_spectrum_harvester_heartbeats.ndjson",
        {
            "event_type": "FULL_SPECTRUM_HARVESTER_EXPANSION_HEARTBEAT",
            "generated_at": generated_at.isoformat(),
            "iteration": 2,
            "status": "FULL_SPECTRUM_HARVEST_ITERATION_COMPLETED",
            "safety": {"order_placed": False},
        },
    )


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "default_mode": "disabled",
                "lanes": [_lane("8m", "short"), _lane("4m", "long")],
            }
        ),
        encoding="utf-8",
    )
    return path


def _lane(timeframe: str, direction: str) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": "ladder_close_50_618",
        "mode": "paper",
        "freshness_seconds": 120,
    }


def _append_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
