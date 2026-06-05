from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.weekend_paper_fisherman_supervisor import (
    CONFIRM_WEEKEND_PAPER_FISHERMAN_SUPERVISOR_RECORDING_PHRASE,
    FISHERMAN_STALE,
    LEDGER_FILENAME,
    NO_SIGNAL_BUT_FISHERMAN_RUNNING,
    SIGNAL_CAPTURED_AND_FISHERMAN_EXITED,
    WEEKEND_PAPER_FISHERMAN_SUPERVISOR_RECORDED,
    WEEKEND_PAPER_FISHERMAN_SUPERVISOR_REJECTED,
    build_weekend_paper_fisherman_supervisor,
    load_weekend_paper_fisherman_supervisor_records,
)

NOW = datetime(2026, 6, 5, 18, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
LANE_222M_LONG = "BTCUSDT|222m|long|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_running_heartbeats(log_dir)

    payload = build_weekend_paper_fisherman_supervisor(log_dir=log_dir, now=NOW)

    assert payload["record_supervisor_requested"] is False
    assert payload["supervisor_recorded"] is False
    assert payload["supervisor_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = build_weekend_paper_fisherman_supervisor(
        log_dir=tmp_path / "logs",
        record_supervisor=True,
        confirm_weekend_fisherman_supervisor="wrong",
        now=NOW,
    )

    assert payload["status"] == WEEKEND_PAPER_FISHERMAN_SUPERVISOR_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["supervisor_recorded"] is False
    assert load_weekend_paper_fisherman_supervisor_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_supervisor_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    before_env = dict(os.environ)

    payload = build_weekend_paper_fisherman_supervisor(
        log_dir=log_dir,
        record_supervisor=True,
        confirm_weekend_fisherman_supervisor=CONFIRM_WEEKEND_PAPER_FISHERMAN_SUPERVISOR_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_weekend_paper_fisherman_supervisor_records(log_dir=log_dir, limit=0)

    assert payload["status"] == WEEKEND_PAPER_FISHERMAN_SUPERVISOR_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["supervisor_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "WEEKEND_PAPER_FISHERMAN_SUPERVISOR"
    assert before_env == dict(os.environ)


def test_detects_no_signal_but_fisherman_running(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_running_heartbeats(log_dir)

    payload = build_weekend_paper_fisherman_supervisor(log_dir=log_dir, now=NOW)

    assert payload["fisherman_health"]["fisherman_status"] == "FISHERMAN_RUNNING_RECENT"
    assert payload["no_signal_vs_no_fisherman"]["classification"] == NO_SIGNAL_BUT_FISHERMAN_RUNNING
    assert payload["weekend_policy"]["acceptable_no_signal_if_fisherman_running"] is True


def test_detects_fisherman_stale(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_full_heartbeat(log_dir, NOW - timedelta(minutes=10))
    _write_short_heartbeat(log_dir, NOW - timedelta(minutes=10))

    payload = build_weekend_paper_fisherman_supervisor(log_dir=log_dir, now=NOW)

    assert payload["fisherman_health"]["full_spectrum_watcher_stale"] is True
    assert payload["fisherman_health"]["short_capture_watcher_stale"] is True
    assert payload["fisherman_health"]["fisherman_status"] == FISHERMAN_STALE
    assert payload["no_signal_vs_no_fisherman"]["classification"] == FISHERMAN_STALE


def test_detects_fisherman_exited_after_capture(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_short_heartbeat(log_dir, NOW - timedelta(seconds=20))
    _write_full_heartbeat(
        log_dir,
        NOW - timedelta(seconds=20),
        status="FULL_SPECTRUM_HARVEST_EXITED",
        captured_lanes=[LANE_222M_LONG],
        total_captured=1,
    )
    _write_full_spectrum_record(log_dir, [("sig-222", LANE_222M_LONG)])

    payload = build_weekend_paper_fisherman_supervisor(log_dir=log_dir, now=NOW)

    assert payload["fisherman_health"]["fisherman_status"] == SIGNAL_CAPTURED_AND_FISHERMAN_EXITED
    assert payload["capture_watch_summary"]["harvester_exited_after_capture"] is True
    assert payload["no_signal_vs_no_fisherman"]["classification"] == "FISHERMAN_EXITED_AFTER_CAPTURE"


def test_detects_ledger_mismatch_warning(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_running_heartbeats(log_dir)
    _write_short_capture(log_dir, "sig-short")
    _write_full_spectrum_record(log_dir, [("sig-full", LANE_8M_SHORT)])

    payload = build_weekend_paper_fisherman_supervisor(log_dir=log_dir, now=NOW)

    assert payload["capture_watch_summary"]["ledger_mismatch_found"] is True
    assert payload["capture_watch_summary"]["ledger_path_warnings"]
    assert payload["fisherman_health"]["fisherman_status"] == "LEDGER_MISMATCH_REQUIRES_RECONCILIATION"


def test_includes_betrayal_222m_and_88m_context_and_not_live_ready(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_running_heartbeats(log_dir)
    _write_full_spectrum_record(log_dir, [("sig-222", LANE_222M_LONG)])

    payload = build_weekend_paper_fisherman_supervisor(log_dir=log_dir, now=NOW)
    summary = payload["betrayal_watch_summary"]

    assert summary["betrayal_context_included"] is True
    assert summary["primary_betrayal_candidate"] == "222m aggregate"
    assert summary["watchlist_betrayal_candidate"] == "88m aggregate"
    assert summary["latest_222m_capture_found"] is True
    assert summary["latest_222m_capture_lane"] == LANE_222M_LONG
    assert summary["betrayal_integrated_into_current_matrix"] is False
    assert summary["betrayal_live_ready"] is False
    assert "true inverse paper outcomes" in summary["required_before_betrayal_promotion"]


def test_safe_operator_commands_are_present(tmp_path: Path) -> None:
    payload = build_weekend_paper_fisherman_supervisor(log_dir=tmp_path / "logs", now=NOW)

    commands = payload["safe_weekend_operator_commands"]
    assert "tmux has-session -t r198-full-spectrum-harvest" in commands["tmux_status_check"]
    assert "tail -n 20" in commands["heartbeat_tail"]
    assert "full-spectrum-harvester-expansion" in commands["full_spectrum_harvester_restart_24h"]
    assert "--max-iterations 1440" in commands["full_spectrum_harvester_restart_24h"]
    assert "short-paper-evidence-capture-loop" in commands["short_capture_watcher_restart_24h"]
    assert "capture-count-sync-8m-short" in commands["capture_count_recheck"]
    assert "weekend-paper-fisherman-supervisor" in commands["weekend_supervisor_preview"]


def test_no_live_authorization_env_config_mutation_or_unsafe_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    before_env = dict(os.environ)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_weekend_paper_fisherman_supervisor(log_dir=tmp_path / "logs", now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key
    assert payload["weekend_policy"]["live_authorized"] is False


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "weekend-paper-fisherman-supervisor",
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
    assert "fisherman_health" in payload
    assert "weekend-paper-fisherman-supervisor" in help_result.stdout


def _write_running_heartbeats(log_dir: Path) -> None:
    _write_full_heartbeat(log_dir, NOW - timedelta(seconds=20))
    _write_short_heartbeat(log_dir, NOW - timedelta(seconds=20))


def _write_full_heartbeat(
    log_dir: Path,
    generated_at: datetime,
    *,
    status: str = "FULL_SPECTRUM_HARVEST_ITERATION_COMPLETED",
    captured_lanes: list[str] | None = None,
    total_captured: int = 0,
) -> None:
    _append_json(
        log_dir / "full_spectrum_harvester_heartbeats.ndjson",
        {
            "event_type": "FULL_SPECTRUM_HARVESTER_EXPANSION_HEARTBEAT",
            "generated_at": generated_at.isoformat(),
            "iteration": 4,
            "status": status,
            "captured_lanes": captured_lanes or [],
            "total_captured": total_captured,
            "safety": {"order_placed": False},
        },
    )


def _write_short_heartbeat(log_dir: Path, generated_at: datetime) -> None:
    _append_json(
        log_dir / "short_paper_evidence_capture_heartbeats.ndjson",
        {
            "event_type": "SHORT_PAPER_EVIDENCE_CAPTURE_HEARTBEAT",
            "generated_at": generated_at.isoformat(),
            "iteration": 4,
            "status": "SHORT_PAPER_CAPTURE_ITERATION_COMPLETED",
            "target_lane": {"lane_key": LANE_8M_SHORT},
            "paper_evidence_captured": False,
            "safety": {"order_placed": False},
        },
    )


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


def _write_full_spectrum_record(log_dir: Path, captures: list[tuple[str, str]]) -> None:
    _append_json(
        log_dir / "full_spectrum_harvester_expansion.ndjson",
        {
            "event_type": "FULL_SPECTRUM_HARVESTER_EXPANSION",
            "status": "FULL_SPECTRUM_HARVESTER_EXPANSION_CAPTURED",
            "generated_at": NOW.isoformat(),
            "harvest_id": "harvest-1",
            "capture_summary": {
                "captured_candidates": [
                    {
                        "signal_id": signal_id,
                        "candidate_id": signal_id,
                        "lane_key": lane_key,
                        "timestamp": NOW.isoformat(),
                    }
                    for signal_id, lane_key in captures
                ],
                "captured_lanes": sorted({lane_key for _signal_id, lane_key in captures}),
            },
            "safety": {"order_placed": False},
        },
    )


def _append_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
