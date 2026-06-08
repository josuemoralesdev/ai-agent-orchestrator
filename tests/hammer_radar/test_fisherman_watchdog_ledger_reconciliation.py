from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.fisherman_watchdog_ledger_reconciliation import (
    CAPTURE_COUNT_SYNC_LEDGER_FILENAME,
    CONFIRM_FISHERMAN_WATCHDOG_LEDGER_RECONCILIATION_PHRASE,
    FISHERMAN_ALIVE_NO_SIGNAL,
    FISHERMAN_STALE,
    FISHERMAN_WATCHDOG_RECONCILIATION_RECORDED,
    FISHERMAN_WATCHDOG_RECONCILIATION_REJECTED,
    LEDGER_FILENAME,
    build_fisherman_watchdog_ledger_reconciliation,
    build_reconciled_capture_count_snapshot,
    load_capture_count_sync_records,
    load_fisherman_reconciliation_records,
)
from src.app.hammer_radar.operator.weekend_paper_fisherman_supervisor import (
    build_weekend_paper_fisherman_supervisor,
)

NOW = datetime(2026, 6, 7, 22, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
LANE_4M_SHORT = "BTCUSDT|4m|short|ladder_close_50_618"
LANE_8M_LONG = "BTCUSDT|8m|long|ladder_close_50_618"


def test_preview_writes_no_ledger(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_running_heartbeats(log_dir)
    _write_short_capture(log_dir, "BTCUSDT|8m|short|2026-06-07T21:19:59.999000+00:00")

    payload = build_fisherman_watchdog_ledger_reconciliation(log_dir=log_dir, now=NOW)

    assert payload["record_reconciliation_requested"] is False
    assert payload["reconciliation_recorded"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()
    assert not (log_dir / CAPTURE_COUNT_SYNC_LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_and_writes_no_ledger(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_running_heartbeats(log_dir)
    _write_short_capture(log_dir, "sig-short-1")

    payload = build_fisherman_watchdog_ledger_reconciliation(
        log_dir=log_dir,
        record_reconciliation=True,
        confirm_fisherman_watchdog_ledger_reconciliation="wrong",
        now=NOW,
    )

    assert payload["status"] == FISHERMAN_WATCHDOG_RECONCILIATION_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["reconciliation_recorded"] is False
    assert load_fisherman_reconciliation_records(log_dir=log_dir, limit=0) == []
    assert load_capture_count_sync_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_appends_reconciliation_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_running_heartbeats(log_dir)
    _write_short_capture(log_dir, "sig-short-1")
    before_env = dict(os.environ)

    payload = build_fisherman_watchdog_ledger_reconciliation(
        log_dir=log_dir,
        record_reconciliation=True,
        confirm_fisherman_watchdog_ledger_reconciliation=CONFIRM_FISHERMAN_WATCHDOG_LEDGER_RECONCILIATION_PHRASE,
        now=NOW,
    )
    reconciliation_records = load_fisherman_reconciliation_records(log_dir=log_dir, limit=0)
    sync_records = load_capture_count_sync_records(log_dir=log_dir, limit=0)

    assert payload["status"] == FISHERMAN_WATCHDOG_RECONCILIATION_RECORDED
    assert payload["reconciliation_recorded"] is True
    assert len(reconciliation_records) == 1
    assert len(sync_records) == 1
    assert reconciliation_records[0]["event_type"] == "FISHERMAN_WATCHDOG_LEDGER_RECONCILIATION"
    assert sync_records[0]["event_type"] == "CAPTURE_COUNT_SYNC_8M_SHORT"
    assert payload["safety"]["capture_count_sync_appended"] is True
    assert payload["safety"]["reconciliation_audit_appended"] is True
    assert before_env == dict(os.environ)


def test_weekend_supervisor_trusts_matching_r208b_reconciliation(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_running_heartbeats(log_dir)
    _write_short_capture(log_dir, "sig-short-1")
    _write_short_capture(log_dir, "sig-short-2")
    _write_full_spectrum_record(log_dir, [("sig-short-2", LANE_8M_SHORT)])

    before = build_weekend_paper_fisherman_supervisor(log_dir=log_dir, now=NOW)
    assert before["capture_watch_summary"]["ledger_mismatch_found"] is True

    build_fisherman_watchdog_ledger_reconciliation(
        log_dir=log_dir,
        record_reconciliation=True,
        confirm_fisherman_watchdog_ledger_reconciliation=CONFIRM_FISHERMAN_WATCHDOG_LEDGER_RECONCILIATION_PHRASE,
        now=NOW,
    )
    after = build_weekend_paper_fisherman_supervisor(log_dir=log_dir, now=NOW)

    assert after["capture_watch_summary"]["ledger_mismatch_found"] is False
    assert after["fisherman_health"]["fisherman_status"] == "FISHERMAN_RUNNING_RECENT"


def test_missing_capture_count_sync_ledger_is_detected(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_running_heartbeats(log_dir)
    _write_short_capture(log_dir, "sig-short-1")

    payload = build_fisherman_watchdog_ledger_reconciliation(log_dir=log_dir, now=NOW)

    assert payload["input_summary"]["capture_count_sync_ledger_found"] is False
    assert payload["ledger_mismatch_report"]["ledger_mismatch_found"] is True
    assert "logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson" in payload["ledger_mismatch_report"]["missing_ledgers"]


def test_capture_count_can_be_rebuilt_from_local_evidence(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_running_heartbeats(log_dir)
    _write_short_capture(log_dir, "sig-short-1")
    _write_full_spectrum_record(log_dir, [("sig-short-2", LANE_8M_SHORT)])

    payload = build_fisherman_watchdog_ledger_reconciliation(log_dir=log_dir, now=NOW)

    assert payload["reconciled_capture_count"]["fresh_capture_count"] == 2
    assert payload["ledger_mismatch_report"]["reconciliation_possible_from_local_evidence"] is True
    assert payload["ledger_mismatch_report"]["reconciled_capture_count_would_write"] is True


def test_unique_8m_short_captures_are_counted_and_duplicates_ignored() -> None:
    count = build_reconciled_capture_count_snapshot(
        short_capture_records=[
            _short_capture_record("sig-short-1"),
            _short_capture_record("sig-short-2"),
            _short_capture_record("sig-short-1"),
        ],
        full_spectrum_capture_records=[
            _full_spectrum_record([("sig-short-2", LANE_8M_SHORT), ("sig-short-3", LANE_8M_SHORT)])
        ],
    )

    assert count["fresh_capture_count"] == 3
    assert count["unique_captured_signal_ids"] == ["sig-short-1", "sig-short-2", "sig-short-3"]


def test_non_8m_short_lanes_are_not_counted_toward_threshold() -> None:
    count = build_reconciled_capture_count_snapshot(
        short_capture_records=[_short_capture_record("sig-short-1")],
        full_spectrum_capture_records=[
            _full_spectrum_record(
                [
                    ("sig-4m", LANE_4M_SHORT),
                    ("sig-long", LANE_8M_LONG),
                    ("sig-8m-short", LANE_8M_SHORT),
                ]
            )
        ],
    )

    assert count["fresh_capture_count"] == 2
    assert count["unique_captured_signal_ids"] == ["sig-short-1", "sig-8m-short"]


def test_threshold_false_when_count_below_10(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_running_heartbeats(log_dir)
    for index in range(9):
        _write_short_capture(log_dir, f"sig-short-{index}")

    payload = build_fisherman_watchdog_ledger_reconciliation(log_dir=log_dir, now=NOW)

    assert payload["reconciled_capture_count"]["fresh_capture_count"] == 9
    assert payload["reconciled_capture_count"]["threshold_met"] is False


def test_threshold_true_only_when_count_at_least_10(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_running_heartbeats(log_dir)
    for index in range(10):
        _write_short_capture(log_dir, f"sig-short-{index}")

    payload = build_fisherman_watchdog_ledger_reconciliation(log_dir=log_dir, now=NOW)

    assert payload["reconciled_capture_count"]["fresh_capture_count"] == 10
    assert payload["reconciled_capture_count"]["threshold_met"] is True


def test_fisherman_alive_no_signal_classification_works(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_running_heartbeats(log_dir)
    _write_existing_sync(log_dir, [])

    payload = build_fisherman_watchdog_ledger_reconciliation(log_dir=log_dir, now=NOW)

    assert payload["no_signal_vs_no_fisherman"]["classification"] == FISHERMAN_ALIVE_NO_SIGNAL


def test_fisherman_stale_classification_works(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_full_heartbeat(log_dir, NOW - timedelta(minutes=10))
    _write_short_heartbeat(log_dir, NOW - timedelta(minutes=10))
    _write_existing_sync(log_dir, [])

    payload = build_fisherman_watchdog_ledger_reconciliation(log_dir=log_dir, now=NOW)

    assert payload["watcher_health"]["short_capture_watcher_stale"] is True
    assert payload["watcher_health"]["full_spectrum_watcher_stale"] is True
    assert payload["no_signal_vs_no_fisherman"]["classification"] == FISHERMAN_STALE


def test_safety_object_forbids_config_network_order_live(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    before_env = dict(os.environ)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_fisherman_watchdog_ledger_reconciliation(log_dir=tmp_path / "logs", now=NOW)

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


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "fisherman-watchdog-ledger-reconciliation",
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
    assert payload["target_scope"]["primary_lane"] == LANE_8M_SHORT
    assert "fisherman-watchdog-ledger-reconciliation" in help_result.stdout


def _write_running_heartbeats(log_dir: Path) -> None:
    _write_full_heartbeat(log_dir, NOW - timedelta(seconds=20))
    _write_short_heartbeat(log_dir, NOW - timedelta(seconds=20))


def _write_full_heartbeat(log_dir: Path, generated_at: datetime) -> None:
    _append_json(
        log_dir / "full_spectrum_harvester_heartbeats.ndjson",
        {
            "event_type": "FULL_SPECTRUM_HARVESTER_EXPANSION_HEARTBEAT",
            "generated_at": generated_at.isoformat(),
            "iteration": 7,
            "status": "FULL_SPECTRUM_HARVEST_ITERATION_COMPLETED",
            "safety": {"order_placed": False},
        },
    )


def _write_short_heartbeat(log_dir: Path, generated_at: datetime) -> None:
    _append_json(
        log_dir / "short_paper_evidence_capture_heartbeats.ndjson",
        {
            "event_type": "SHORT_PAPER_EVIDENCE_CAPTURE_HEARTBEAT",
            "generated_at": generated_at.isoformat(),
            "iteration": 9,
            "status": "SHORT_PAPER_CAPTURE_ITERATION_COMPLETED",
            "target_lane": {"lane_key": LANE_8M_SHORT},
            "safety": {"order_placed": False},
        },
    )


def _write_short_capture(log_dir: Path, signal_id: str) -> None:
    _append_json(log_dir / "short_paper_evidence_capture.ndjson", _short_capture_record(signal_id))


def _short_capture_record(signal_id: str) -> dict[str, object]:
    return {
        "event_type": "SHORT_PAPER_EVIDENCE_CAPTURE",
        "generated_at": NOW.isoformat(),
        "target_lane": {"lane_key": LANE_8M_SHORT},
        "paper_evidence_captured": True,
        "captured_signal_id": signal_id,
        "captured_lane_key": LANE_8M_SHORT,
        "safety": {"order_placed": False},
    }


def _write_full_spectrum_record(log_dir: Path, captures: list[tuple[str, str]]) -> None:
    _append_json(log_dir / "full_spectrum_harvester_expansion.ndjson", _full_spectrum_record(captures))


def _full_spectrum_record(captures: list[tuple[str, str]]) -> dict[str, object]:
    return {
        "event_type": "FULL_SPECTRUM_HARVESTER_EXPANSION",
        "status": "FULL_SPECTRUM_HARVESTER_EXPANSION_CAPTURED",
        "generated_at": NOW.isoformat(),
        "capture_summary": {
            "captured_candidates": [
                {"signal_id": signal_id, "candidate_id": signal_id, "lane_key": lane_key, "timestamp": NOW.isoformat()}
                for signal_id, lane_key in captures
            ],
            "captured_lanes": sorted({lane_key for _signal_id, lane_key in captures}),
        },
        "safety": {"order_placed": False},
    }


def _write_existing_sync(log_dir: Path, ids: list[str]) -> None:
    _append_json(
        log_dir / "capture_count_sync_8m_short.ndjson",
        {
            "event_type": "CAPTURE_COUNT_SYNC_8M_SHORT",
            "generated_at": NOW.isoformat(),
            "capture_count": {
                "fresh_capture_count": len(ids),
                "required_fresh_capture_count": 10,
                "threshold_met": len(ids) >= 10,
                "latest_captured_signal_id": ids[0] if ids else None,
                "unique_captured_signal_ids": ids,
            },
            "safety": {"order_placed": False},
        },
    )


def _append_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
