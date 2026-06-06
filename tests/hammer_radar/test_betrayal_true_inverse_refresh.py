from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_true_inverse_refresh import (
    BETRAYAL_TRUE_INVERSE_REFRESH_RECORDED,
    BETRAYAL_TRUE_INVERSE_REFRESH_REJECTED,
    CONFIRM_BETRAYAL_TRUE_INVERSE_REFRESH_RECORDING_PHRASE,
    LEDGER_FILENAME,
    TRUE_INVERSE_TIMESTAMP_ALIGNMENT_BLOCKED,
    build_betrayal_true_inverse_refresh,
    load_betrayal_true_inverse_refresh_records,
)

NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
LANE_222M_LONG = "BTCUSDT|222m|long|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_local_evidence(log_dir)

    payload = build_betrayal_true_inverse_refresh(log_dir=log_dir, now=NOW)

    assert payload["record_refresh_requested"] is False
    assert payload["refresh_recorded"] is False
    assert payload["refresh_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = build_betrayal_true_inverse_refresh(
        log_dir=tmp_path / "logs",
        record_refresh=True,
        confirm_betrayal_true_inverse_refresh="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_TRUE_INVERSE_REFRESH_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["refresh_recorded"] is False
    assert load_betrayal_true_inverse_refresh_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_refresh_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_local_evidence(log_dir)
    before_env = dict(os.environ)

    payload = build_betrayal_true_inverse_refresh(
        log_dir=log_dir,
        record_refresh=True,
        confirm_betrayal_true_inverse_refresh=CONFIRM_BETRAYAL_TRUE_INVERSE_REFRESH_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_betrayal_true_inverse_refresh_records(log_dir=log_dir, limit=0)

    assert payload["status"] == BETRAYAL_TRUE_INVERSE_REFRESH_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["refresh_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_TRUE_INVERSE_REFRESH"
    assert before_env == dict(os.environ)


def test_includes_222m_primary_and_88m_watchlist(tmp_path: Path) -> None:
    payload = build_betrayal_true_inverse_refresh(log_dir=tmp_path / "logs", now=NOW)
    summary = payload["candidate_true_inverse_summary"]

    assert payload["betrayal_scope"]["primary_candidate"] == "222m aggregate"
    assert "88m aggregate" in payload["betrayal_scope"]["watchlist_candidates"]
    assert summary["222m"]["label"] == "BETRAYAL_PRIMARY_CANDIDATE"
    assert summary["222m"]["naive_inverse_win_rate_pct"] == 87.5
    assert summary["88m"]["label"] == "BETRAYAL_WATCHLIST"
    assert summary["88m"]["naive_inverse_win_rate_pct"] == 63.33


def test_loads_shadow_and_candle_availability_summary(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_local_evidence(log_dir)

    payload = build_betrayal_true_inverse_refresh(log_dir=log_dir, now=NOW)
    input_summary = payload["input_summary"]

    assert input_summary["shadow_outcomes_found"] is True
    assert input_summary["shadow_outcome_count"] == 2
    assert input_summary["local_candles_loaded"]["222m"] == 1
    assert input_summary["local_candles_loaded"]["88m"] == 1


def test_links_latest_222m_capture_without_counting_as_validated_sample(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_local_evidence(log_dir)

    payload = build_betrayal_true_inverse_refresh(log_dir=log_dir, now=NOW)
    capture = payload["capture_seed_validation_summary"]

    assert capture["latest_222m_capture_lane"] == LANE_222M_LONG
    assert capture["capture_matches_222m"] is True
    assert capture["capture_can_seed_true_inverse_tracking"] is True
    assert capture["capture_counted_as_validated_sample"] is False


def test_does_not_treat_naive_inverse_as_validated_edge(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_local_evidence(log_dir)

    payload = build_betrayal_true_inverse_refresh(log_dir=log_dir, now=NOW)

    assert payload["candidate_true_inverse_summary"]["222m"]["naive_inverse_win_rate_pct"] == 87.5
    assert payload["candidate_true_inverse_summary"]["222m"]["naive_inverse_counted_as_validated_edge"] is False
    assert payload["capture_seed_validation_summary"]["capture_counted_as_validated_sample"] is False


def test_blocks_validation_when_timestamp_candle_or_schema_missing(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_local_evidence(log_dir)

    payload = build_betrayal_true_inverse_refresh(log_dir=log_dir, now=NOW)
    summary_88m = payload["candidate_true_inverse_summary"]["88m"]

    assert summary_88m["resolved_true_inverse_samples"] == 0
    assert summary_88m["validation_status"] == TRUE_INVERSE_TIMESTAMP_ALIGNMENT_BLOCKED
    assert "88m:missing_signal_timestamp" in summary_88m["blockers"]
    assert "88m:missing_signal_timestamp" in payload["validation_gap_report"]["missing_shadow_schema"]


def test_keeps_betrayal_not_live_ready_and_not_promoted(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_local_evidence(log_dir)

    payload = build_betrayal_true_inverse_refresh(log_dir=log_dir, now=NOW)

    assert payload["betrayal_scope"]["live_authorized"] is False
    for row in payload["candidate_true_inverse_summary"].values():
        assert row["live_ready"] is False
        assert row["promotion_allowed"] is False
    assert payload["safety"]["betrayal_live_authorized"] is False
    assert payload["safety"]["betrayal_promoted"] is False


def test_no_env_config_destructive_network_binance_or_live_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    before_env = dict(os.environ)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_betrayal_true_inverse_refresh(log_dir=tmp_path / "logs", now=NOW)

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
            "betrayal-true-inverse-refresh",
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
    assert "candidate_true_inverse_summary" in payload
    assert "betrayal-true-inverse-refresh" in help_result.stdout


def _write_local_evidence(log_dir: Path) -> None:
    _append_json(
        log_dir / "betrayal_shadow_outcomes.ndjson",
        {
            "shadow_outcome_id": "shadow_222m_win",
            "symbol": "BTCUSDT",
            "timeframe": "222m",
            "signal_timestamp": "2026-06-06T12:00:00+00:00",
            "original_signal_id": "BTCUSDT|222m|short|2026-06-06T12:00:00+00:00",
            "original_direction": "short",
            "shadow_direction": "long",
            "shadow_entry": 100.0,
            "shadow_stop": 90.0,
            "shadow_take_profit": 110.0,
            "shadow_status": "SHADOW_NO_DATA",
        },
    )
    _append_json(
        log_dir / "betrayal_shadow_outcomes.ndjson",
        {
            "shadow_outcome_id": "shadow_88m_missing_timestamp",
            "symbol": "BTCUSDT",
            "timeframe": "88m",
            "signal_timestamp": "",
            "original_signal_id": "BTCUSDT|88m|long|2026-06-06T12:00:00+00:00",
            "original_direction": "long",
            "shadow_direction": "short",
            "shadow_entry": 100.0,
            "shadow_stop": 105.0,
            "shadow_take_profit": 95.0,
            "shadow_status": "SHADOW_NO_DATA",
        },
    )
    _append_json(
        log_dir / "candle_archive" / "BTCUSDT_222m.ndjson",
        {
            "symbol": "BTCUSDT",
            "timeframe": "222m",
            "timestamp": "2026-06-06T13:00:00+00:00",
            "open_time": "2026-06-06T13:00:00+00:00",
            "open": 100.0,
            "high": 111.0,
            "low": 99.0,
            "close": 110.0,
        },
    )
    _append_json(
        log_dir / "candle_archive" / "BTCUSDT_88m.ndjson",
        {
            "symbol": "BTCUSDT",
            "timeframe": "88m",
            "timestamp": "2026-06-06T13:00:00+00:00",
            "open_time": "2026-06-06T13:00:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 94.0,
            "close": 96.0,
        },
    )
    _append_json(
        log_dir / "full_spectrum_harvester_heartbeats.ndjson",
        {
            "event_type": "FULL_SPECTRUM_HARVESTER_EXPANSION_HEARTBEAT",
            "generated_at": NOW.isoformat(),
            "captured_lanes": [LANE_222M_LONG],
        },
    )


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
