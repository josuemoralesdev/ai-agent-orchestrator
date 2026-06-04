from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.three_black_crows_detector import (
    CONFIRM_THREE_BLACK_CROWS_DETECTOR_RECORDING_PHRASE,
    DETECTIONS_FOUND,
    LEDGER_FILENAME,
    MISSING_OHLC_FEED,
    THREE_BLACK_CROWS_DETECTOR_BLOCKED,
    THREE_BLACK_CROWS_DETECTOR_RECORDED,
    THREE_BLACK_CROWS_DETECTOR_REJECTED,
    build_three_black_crows_detector_preview,
    detect_three_black_crows_sequences,
    load_three_black_crows_detector_records,
    normalize_candle_records,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_three_black_crows_detector_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_detector_requested"] is False
    assert payload["detector_recorded"] is False
    assert payload["detector_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_three_black_crows_detector_preview(
        log_dir=tmp_path / "logs",
        record_detector=True,
        confirm_three_black_crows_detector="wrong",
        now=NOW,
    )

    assert payload["status"] == THREE_BLACK_CROWS_DETECTOR_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["detector_recorded"] is False
    assert load_three_black_crows_detector_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")
    before_env = dict(os.environ)

    payload = build_three_black_crows_detector_preview(
        log_dir=tmp_path / "logs",
        record_detector=True,
        confirm_three_black_crows_detector=CONFIRM_THREE_BLACK_CROWS_DETECTOR_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_three_black_crows_detector_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == THREE_BLACK_CROWS_DETECTOR_RECORDED
    assert payload["detector_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "THREE_BLACK_CROWS_DETECTOR"
    assert before_env == dict(os.environ)


def test_strict_detects_valid_three_bearish_lower_close_sequence() -> None:
    candles = normalize_candle_records(_valid_candles())

    detections = detect_three_black_crows_sequences(candles, mode="strict")

    assert len(detections) == 1
    detection = detections[0]
    assert detection["signal_origin"] == "three_black_crows"
    assert detection["direction"] == "short"
    assert detection["paper_only"] is True
    assert detection["live_authorized"] is False
    assert detection["mode"] == "strict"


def test_strict_rejects_non_consecutive_or_non_bearish_candles() -> None:
    non_consecutive = _valid_candles()
    non_consecutive[1]["timestamp"] = "2026-06-04T12:16:00+00:00"
    assert detect_three_black_crows_sequences(normalize_candle_records(non_consecutive), mode="strict") == []

    non_bearish = _valid_candles()
    non_bearish[1]["close"] = 99.5
    assert detect_three_black_crows_sequences(normalize_candle_records(non_bearish), mode="strict") == []


def test_strict_rejects_weak_body_ratio() -> None:
    candles = _valid_candles()
    candles[1].update({"open": 98.2, "close": 97.9, "high": 99.8, "low": 97.8})

    assert detect_three_black_crows_sequences(normalize_candle_records(candles), mode="strict") == []


def test_loose_preview_allows_lower_body_ratio() -> None:
    candles = _valid_candles()
    candles[1].update({"open": 98.9, "close": 97.9, "high": 99.8, "low": 97.2})

    assert detect_three_black_crows_sequences(normalize_candle_records(candles), mode="strict") == []
    detections = detect_three_black_crows_sequences(normalize_candle_records(candles), mode="loose_preview")
    assert len(detections) == 1
    assert detections[0]["mode"] == "loose_preview"


def test_missing_ohlc_feed_blocks_without_fake_detections(tmp_path: Path) -> None:
    payload = build_three_black_crows_detector_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["status"] == THREE_BLACK_CROWS_DETECTOR_BLOCKED
    assert payload["detector_status"] == MISSING_OHLC_FEED
    assert payload["data_availability"]["ohlc_feed_found"] is False
    assert payload["data_availability"]["blockers"] == ["missing_ohlc_feed"]
    assert payload["detections"] == []
    assert payload["recommended_next_operator_move"] == "RUN_R186_THREE_BLACK_CROWS_FEED_INTEGRATION"


def test_preview_output_origin_lane_and_safety_flags(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_three_black_crows_detector_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["detector_status"] == DETECTIONS_FOUND
    assert payload["detector"]["signal_origin"] == "three_black_crows"
    assert payload["detector"]["paper_only"] is True
    assert payload["detector"]["live_authorized"] is False
    assert payload["target_context"]["primary_lane"] == "BTCUSDT|8m|short|ladder_close_50_618"
    lane = payload["lane_summary"]["BTCUSDT|8m|short|ladder_close_50_618"]
    assert lane["detections_found"] == 1
    assert lane["ready_for_paper_tracking"] is True
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False


def test_no_env_config_mutation_no_binance_calls_and_no_order_live_transfer_withdraw(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    _write_candles(log_dir)
    config_path = tmp_path / "lane_controls.json"
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_three_black_crows_detector_preview(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    safety = payload["safety"]
    for key, value in safety.items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_cli_exists(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "three-black-crows-detector",
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
    assert payload["detector"]["signal_origin"] == "three_black_crows"
    assert payload["detector_status"] == DETECTIONS_FOUND
    assert "three-black-crows-detector" in help_result.stdout


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
