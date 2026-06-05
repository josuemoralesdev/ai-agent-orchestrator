from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.pattern_detector_family_expansion import (
    CONFIRM_PATTERN_FAMILY_EXPANSION_RECORDING_PHRASE,
    DETECTIONS_FOUND,
    LEDGER_FILENAME,
    LOCAL_FEED_MISSING,
    PATTERN_DETECTOR_FAMILY_EXPANSION_RECORDED,
    PATTERN_DETECTOR_FAMILY_EXPANSION_REJECTED,
    REGISTRY_ONLY_PREVIEW,
    build_pattern_detector_family_expansion,
    detect_bearish_engulfing_sequences,
    detect_bullish_engulfing_sequences,
    detect_exhaustion_wick_sequences,
    detect_three_white_soldiers_sequences,
    load_pattern_family_expansion_records,
)

NOW = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _family_candles())

    payload = build_pattern_detector_family_expansion(
        log_dir=tmp_path / "logs",
        timeframes=["8m"],
        now=NOW,
    )

    assert payload["record_expansion_requested"] is False
    assert payload["expansion_recorded"] is False
    assert payload["expansion_id"] is None
    assert payload["paper_tags"]["record_tags_requested"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()
    assert not (tmp_path / "logs" / "pattern_family_paper_tags.ndjson").exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _family_candles())

    payload = build_pattern_detector_family_expansion(
        log_dir=tmp_path / "logs",
        timeframes=["8m"],
        record_expansion=True,
        confirm_pattern_family_expansion="wrong",
        now=NOW,
    )

    assert payload["status"] == PATTERN_DETECTOR_FAMILY_EXPANSION_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["expansion_recorded"] is False
    assert load_pattern_family_expansion_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_expansion_only(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _family_candles())
    before_env = dict(os.environ)

    payload = build_pattern_detector_family_expansion(
        log_dir=tmp_path / "logs",
        timeframes=["8m"],
        record_expansion=True,
        confirm_pattern_family_expansion=CONFIRM_PATTERN_FAMILY_EXPANSION_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_pattern_family_expansion_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == PATTERN_DETECTOR_FAMILY_EXPANSION_RECORDED
    assert payload["expansion_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "PATTERN_DETECTOR_FAMILY_EXPANSION"
    assert not (tmp_path / "logs" / "pattern_family_paper_tags.ndjson").exists()
    assert before_env == dict(os.environ)


def test_three_white_soldiers_detects_valid_bullish_3_candle_sequence() -> None:
    detections = detect_three_white_soldiers_sequences(_three_white_soldiers_candles(), mode="strict")

    assert len(detections) == 1
    assert detections[0]["signal_origin"] == "three_white_soldiers"
    assert detections[0]["direction"] == "long"
    assert detections[0]["paper_only"] is True
    assert detections[0]["live_authorized"] is False


def test_bearish_engulfing_detects_valid_bearish_engulfing() -> None:
    detections = detect_bearish_engulfing_sequences(_bearish_engulfing_candles(), mode="strict")

    assert len(detections) == 1
    assert detections[0]["signal_origin"] == "bearish_engulfing"
    assert detections[0]["direction"] == "short"
    assert detections[0]["live_authorized"] is False


def test_bullish_engulfing_detects_valid_bullish_engulfing() -> None:
    detections = detect_bullish_engulfing_sequences(_bullish_engulfing_candles(), mode="strict")

    assert len(detections) == 1
    assert detections[0]["signal_origin"] == "bullish_engulfing"
    assert detections[0]["direction"] == "long"
    assert detections[0]["live_authorized"] is False


def test_exhaustion_wick_detects_upper_and_lower_wick_exhaustion() -> None:
    detections = detect_exhaustion_wick_sequences(_exhaustion_wick_candles(), mode="strict")

    assert {row["direction"] for row in detections} == {"long", "short"}
    assert all(row["signal_origin"] == "exhaustion_wick" for row in detections)
    assert all(row["paper_only"] is True and row["live_authorized"] is False for row in detections)


def test_retest_patterns_stay_registry_only_if_no_detector_data_exists(tmp_path: Path) -> None:
    payload = build_pattern_detector_family_expansion(log_dir=tmp_path / "logs", timeframes=["8m"], now=NOW)

    assert payload["detector_results"]["breakdown_retest"]["detector_status"] == REGISTRY_ONLY_PREVIEW
    assert payload["detector_results"]["breakdown_retest"]["detections_found"] == 0
    assert payload["detector_results"]["breakout_retest"]["detector_status"] == REGISTRY_ONLY_PREVIEW
    assert payload["detector_results"]["breakout_retest"]["detections_found"] == 0
    assert payload["detector_results"]["three_white_soldiers"]["detector_status"] == LOCAL_FEED_MISSING


def test_local_candle_feed_adapter_is_reused(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _family_candles())

    with patch(
        "src.app.hammer_radar.operator.pattern_detector_family_expansion.load_local_candle_feed",
        wraps=__import__(
            "src.app.hammer_radar.operator.local_candle_feed_adapter",
            fromlist=["load_local_candle_feed"],
        ).load_local_candle_feed,
    ) as loader:
        payload = build_pattern_detector_family_expansion(log_dir=tmp_path / "logs", timeframes=["8m"], now=NOW)

    loader.assert_called_once()
    assert payload["local_feed_summary"]["adapter_reused"] is True
    assert payload["pattern_family_reuse_map"]["local_candle_feed_adapter"]["reused_by"]


def test_all_detections_are_paper_only_and_live_authorized_false(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _family_candles())

    payload = build_pattern_detector_family_expansion(log_dir=tmp_path / "logs", timeframes=["8m"], now=NOW)

    assert payload["detector_results"]["three_white_soldiers"]["detector_status"] == DETECTIONS_FOUND
    assert payload["paper_tags"]["tags_created_preview"] > 0
    assert all(row["paper_only"] is True for row in payload["pattern_family_registry"])
    assert all(row["live_authorized"] is False for row in payload["pattern_family_registry"])
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False


def test_no_env_config_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_candles(tmp_path / "logs", "8m", _family_candles())
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
        payload = build_pattern_detector_family_expansion(log_dir=tmp_path / "logs", timeframes=["8m"], now=NOW)

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
    _write_candles(tmp_path / "logs", "8m", _family_candles())

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "pattern-detector-family-expansion",
            "--symbol",
            "BTCUSDT",
            "--timeframes",
            "8m",
            "--mode",
            "both",
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
    assert payload["target_scope"]["patterns"]
    assert payload["pattern_family_registry"][0]["paper_only"] is True
    assert "pattern-detector-family-expansion" in help_result.stdout


def _three_white_soldiers_candles() -> list[dict]:
    return [
        _candle("2026-06-05T12:00:00+00:00", 100, 104, 99.8, 103, "8m"),
        _candle("2026-06-05T12:08:00+00:00", 102, 106, 101.8, 105, "8m"),
        _candle("2026-06-05T12:16:00+00:00", 104, 109, 103.9, 108, "8m"),
    ]


def _bearish_engulfing_candles() -> list[dict]:
    return [
        _candle("2026-06-05T12:00:00+00:00", 100, 102.5, 99.8, 102, "8m"),
        _candle("2026-06-05T12:08:00+00:00", 103, 103.5, 98.5, 99, "8m"),
    ]


def _bullish_engulfing_candles() -> list[dict]:
    return [
        _candle("2026-06-05T12:00:00+00:00", 102, 102.2, 99.5, 100, "8m"),
        _candle("2026-06-05T12:08:00+00:00", 99, 103.5, 98.5, 103, "8m"),
    ]


def _exhaustion_wick_candles() -> list[dict]:
    return [
        _candle("2026-06-05T12:00:00+00:00", 100, 101, 90, 100.8, "8m"),
        _candle("2026-06-05T12:08:00+00:00", 100, 110, 99, 99.5, "8m"),
    ]


def _family_candles() -> list[dict]:
    return [
        *_three_white_soldiers_candles(),
        *_bearish_engulfing_candles(),
        *_bullish_engulfing_candles(),
        *_exhaustion_wick_candles(),
    ]


def _candle(timestamp: str, open_value: float, high: float, low: float, close: float, timeframe: str) -> dict:
    return {
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "timestamp": timestamp,
        "open_time": timestamp,
        "open": open_value,
        "high": high,
        "low": low,
        "close": close,
        "source": "local_test_feed",
    }


def _write_candles(log_dir: Path, timeframe: str, candles: list[dict]) -> None:
    path = log_dir / "candle_archive" / f"BTCUSDT_{timeframe}.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for candle in candles:
            handle.write(json.dumps(candle, sort_keys=True) + "\n")
