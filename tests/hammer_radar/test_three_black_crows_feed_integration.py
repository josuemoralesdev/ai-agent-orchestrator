from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.three_black_crows_feed_integration import (
    CONFIRM_THREE_BLACK_CROWS_FEED_INTEGRATION_RECORDING_PHRASE,
    DETECTIONS_TAGGED,
    LEDGER_FILENAME,
    LOCAL_OHLC_FEED_FOUND,
    LOCAL_OHLC_FEED_MISSING,
    PAPER_TAG_LEDGER_FILENAME,
    SYNTHETIC_SIGNAL_FEED_AVAILABLE,
    THREE_BLACK_CROWS_FEED_INTEGRATION_BLOCKED,
    THREE_BLACK_CROWS_FEED_INTEGRATION_READY,
    THREE_BLACK_CROWS_FEED_INTEGRATION_RECORDED,
    THREE_BLACK_CROWS_FEED_INTEGRATION_REJECTED,
    build_synthetic_candle_candidates_from_signal_logs_if_safe,
    build_three_black_crows_feed_integration,
    discover_local_candle_feeds,
    load_three_black_crows_feed_integration_records,
    run_three_black_crows_detector_on_feed,
    tag_three_black_crows_paper_candidates,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_three_black_crows_feed_integration(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_integration_requested"] is False
    assert payload["integration_recorded"] is False
    assert payload["integration_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()
    assert not (tmp_path / "logs" / PAPER_TAG_LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = build_three_black_crows_feed_integration(
        log_dir=tmp_path / "logs",
        record_integration=True,
        confirm_three_black_crows_feed_integration="wrong",
        now=NOW,
    )

    assert payload["status"] == THREE_BLACK_CROWS_FEED_INTEGRATION_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["integration_recorded"] is False
    assert load_three_black_crows_feed_integration_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_integration_only_without_config_mutation(tmp_path: Path) -> None:
    before_env = dict(os.environ)

    payload = build_three_black_crows_feed_integration(
        log_dir=tmp_path / "logs",
        record_integration=True,
        confirm_three_black_crows_feed_integration=CONFIRM_THREE_BLACK_CROWS_FEED_INTEGRATION_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_three_black_crows_feed_integration_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == THREE_BLACK_CROWS_FEED_INTEGRATION_RECORDED
    assert payload["integration_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "THREE_BLACK_CROWS_FEED_INTEGRATION"
    assert before_env == dict(os.environ)
    assert not (tmp_path / "logs" / PAPER_TAG_LEDGER_FILENAME).exists()


def test_discovers_local_ohlc_feed_when_mocked_file_exists(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    discovery = discover_local_candle_feeds(log_dir=tmp_path / "logs", symbol="BTCUSDT", timeframe="8m")
    payload = build_three_black_crows_feed_integration(log_dir=tmp_path / "logs", now=NOW)

    assert discovery["local_ohlc_feed_found"] is True
    assert str(tmp_path / "logs" / "candles.ndjson") in discovery["source_files_used"]
    assert payload["feed_discovery"]["local_ohlc_feed_found"] is True
    assert payload["feed_status"] in {LOCAL_OHLC_FEED_FOUND, DETECTIONS_TAGGED}


def test_blocks_when_no_ohlc_feed_exists(tmp_path: Path) -> None:
    payload = build_three_black_crows_feed_integration(log_dir=tmp_path / "logs", now=NOW)

    assert payload["status"] == THREE_BLACK_CROWS_FEED_INTEGRATION_BLOCKED
    assert payload["feed_status"] == LOCAL_OHLC_FEED_MISSING
    assert payload["detector_result"]["detector_status"] == "MISSING_OHLC_FEED"
    assert payload["paper_tags"]["tags_created"] == 0


def test_does_not_fake_ohlc_from_signal_logs(tmp_path: Path) -> None:
    _append_json(
        tmp_path / "logs" / "signals.ndjson",
        {
            "signal_id": "s1",
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "open": 100,
            "high": 101,
            "low": 95,
            "close": 96,
        },
    )

    contexts = build_synthetic_candle_candidates_from_signal_logs_if_safe(log_dir=tmp_path / "logs")
    payload = build_three_black_crows_feed_integration(log_dir=tmp_path / "logs", now=NOW)

    assert contexts
    assert all(context["not_valid_for_three_black_crows_detection"] is True for context in contexts)
    assert payload["feed_status"] == SYNTHETIC_SIGNAL_FEED_AVAILABLE
    assert payload["detector_result"]["detector_status"] == "MISSING_OHLC_FEED"
    assert payload["detector_result"]["detections_found"] == 0


def test_detector_runs_on_real_mocked_ohlc_feed() -> None:
    detector = run_three_black_crows_detector_on_feed(_valid_candles(), ohlc_feed_found=True)

    assert detector["detector_status"] == "DETECTIONS_FOUND"
    assert detector["detections_found"] == 1
    assert detector["paper_only"] is True
    assert detector["live_authorized"] is False


def test_tags_three_black_crows_paper_candidates_when_detections_exist(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_three_black_crows_feed_integration(log_dir=tmp_path / "logs", now=NOW)

    assert payload["status"] == THREE_BLACK_CROWS_FEED_INTEGRATION_READY
    assert payload["feed_status"] == DETECTIONS_TAGGED
    assert payload["detector_result"]["detections_found"] == 1
    assert payload["paper_tags"]["tags_created"] == 1
    tag = payload["paper_tags"]["tags"][0]
    assert tag["signal_origin"] == "three_black_crows"
    assert tag["lane_key"] == "BTCUSDT|8m|short|ladder_close_50_618"


def test_paper_tags_are_paper_only_and_not_live_authorized() -> None:
    detector = run_three_black_crows_detector_on_feed(_valid_candles(), ohlc_feed_found=True)
    tags = tag_three_black_crows_paper_candidates(detector["detections"])

    assert tags
    assert all(tag["paper_only"] is True for tag in tags)
    assert all(tag["live_authorized"] is False for tag in tags)


def test_no_signal_origin_promoted_no_lane_promoted_and_no_env_config_mutation(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")
    config_path = tmp_path / "lane_controls.json"
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_three_black_crows_feed_integration(log_dir=tmp_path / "logs", now=NOW)

    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["config_written"] is False
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")


def test_no_binance_calls_and_no_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_candles(tmp_path / "logs")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_three_black_crows_feed_integration(log_dir=tmp_path / "logs", now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    safety = payload["safety"]
    for key, value in safety.items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_correct_confirmation_records_paper_tag_ledger_when_detections_exist(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_three_black_crows_feed_integration(
        log_dir=tmp_path / "logs",
        record_integration=True,
        confirm_three_black_crows_feed_integration=CONFIRM_THREE_BLACK_CROWS_FEED_INTEGRATION_RECORDING_PHRASE,
        now=NOW,
    )

    assert payload["integration_recorded"] is True
    assert payload["paper_tags"]["tags_created"] == 1
    assert payload["paper_tags"]["tags_recorded"] == 1
    assert (tmp_path / "logs" / LEDGER_FILENAME).exists()
    assert (tmp_path / "logs" / PAPER_TAG_LEDGER_FILENAME).exists()


def test_cli_exists(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "three-black-crows-feed-integration",
            "--symbol",
            "BTCUSDT",
            "--timeframe",
            "8m",
            "--mode",
            "strict",
            "--latest-candles",
            "500",
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
    assert payload["target_context"]["signal_origin"] == "three_black_crows"
    assert payload["feed_status"] == DETECTIONS_TAGGED
    assert "three-black-crows-feed-integration" in help_result.stdout


def _valid_candles() -> list[dict]:
    return [
        {
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "timestamp": "2026-06-04T12:00:00+00:00",
            "open": 100.0,
            "high": 100.5,
            "low": 97.8,
            "close": 98.0,
        },
        {
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "timestamp": "2026-06-04T12:08:00+00:00",
            "open": 98.7,
            "high": 99.0,
            "low": 96.2,
            "close": 96.8,
        },
        {
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "timestamp": "2026-06-04T12:16:00+00:00",
            "open": 97.1,
            "high": 97.5,
            "low": 94.6,
            "close": 95.2,
        },
    ]


def _write_candles(log_dir: Path) -> None:
    for candle in _valid_candles():
        _append_json(log_dir / "candles.ndjson", candle)


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
