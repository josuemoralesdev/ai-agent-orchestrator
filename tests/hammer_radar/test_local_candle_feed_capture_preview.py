from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.local_candle_feed_capture_preview import (
    CONFIRM_LOCAL_CANDLE_FEED_PREVIEW_RECORDING_PHRASE,
    LEDGER_FILENAME,
    LOCAL_CANDLE_FEED_PREVIEW_RECORDED,
    LOCAL_CANDLE_FEED_PREVIEW_REJECTED,
    SYNTHETIC_SIGNAL_CONTEXT_ONLY,
    VALID_LOCAL_OHLC_FEED_AVAILABLE,
    build_local_candle_feed_capture_preview,
    discover_local_candle_like_sources,
    load_local_candle_feed_preview_records,
    normalize_valid_ohlc_records,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs" / "candles.ndjson")

    payload = build_local_candle_feed_capture_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_preview_requested"] is False
    assert payload["preview_recorded"] is False
    assert payload["preview_id"] is None
    assert payload["normalized_feed_preview"]["would_write_feed_now"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = build_local_candle_feed_capture_preview(
        log_dir=tmp_path / "logs",
        record_preview=True,
        confirm_local_candle_feed_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == LOCAL_CANDLE_FEED_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["preview_recorded"] is False
    assert load_local_candle_feed_preview_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_preview_only(tmp_path: Path) -> None:
    before_env = dict(os.environ)

    payload = build_local_candle_feed_capture_preview(
        log_dir=tmp_path / "logs",
        record_preview=True,
        confirm_local_candle_feed_preview=CONFIRM_LOCAL_CANDLE_FEED_PREVIEW_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_local_candle_feed_preview_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == LOCAL_CANDLE_FEED_PREVIEW_RECORDED
    assert payload["preview_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "LOCAL_CANDLE_FEED_CAPTURE_PREVIEW"
    assert records[0]["normalized_feed_preview"]["would_write_feed_now"] is False
    assert before_env == dict(os.environ)


def test_discovers_valid_local_ohlc_mocked_file(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs" / "candles.ndjson")

    discovery = discover_local_candle_like_sources(log_dir=tmp_path / "logs", symbol="BTCUSDT", timeframe="8m")
    payload = build_local_candle_feed_capture_preview(log_dir=tmp_path / "logs", now=NOW)

    assert str(tmp_path / "logs" / "candles.ndjson") in discovery["valid_ohlc_files"]
    assert payload["source_discovery"]["valid_ohlc_files"]
    assert payload["detector_feed_readiness"]["feed_readiness"] == VALID_LOCAL_OHLC_FEED_AVAILABLE


def test_discovers_existing_candle_archive_file_shape(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs" / "candle_archive" / "BTCUSDT_8m.ndjson")

    payload = build_local_candle_feed_capture_preview(log_dir=tmp_path / "logs", now=NOW)

    assert str(tmp_path / "logs" / "candle_archive" / "BTCUSDT_8m.ndjson") in payload["source_discovery"]["valid_ohlc_files"]
    assert payload["normalized_feed_preview"]["valid_candles_found"] == 3
    assert payload["normalized_feed_preview"]["candidate_output_path"] == "logs/hammer_radar_forward/candles_BTCUSDT_8m.ndjson"


def test_normalizes_valid_ohlc_records() -> None:
    normalized = normalize_valid_ohlc_records(_valid_candles())

    assert len(normalized) == 3
    assert normalized[0]["symbol"] == "BTCUSDT"
    assert normalized[0]["timeframe"] == "8m"
    assert normalized[0]["open_time"] == "2026-06-04T12:00:00+00:00"
    assert normalized[0]["source"] == "local_test_feed"


def test_rejects_signal_only_records(tmp_path: Path) -> None:
    _append_json(
        tmp_path / "logs" / "signals.ndjson",
        {
            "signal_id": "s1",
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "signal_close": 100.0,
        },
    )

    payload = build_local_candle_feed_capture_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["detector_feed_readiness"]["feed_readiness"] == SYNTHETIC_SIGNAL_CONTEXT_ONLY
    assert payload["normalized_feed_preview"]["valid_candles_found"] == 0
    assert payload["safety"]["fake_ohlc_created"] is False
    assert payload["source_discovery"]["invalid_or_synthetic_sources"][0]["reason"] == "synthetic_signal_context_not_valid_ohlc"


def test_rejects_malformed_candles(tmp_path: Path) -> None:
    _append_json(
        tmp_path / "logs" / "candles.ndjson",
        {"symbol": "BTCUSDT", "timeframe": "8m", "open_time": "t", "open": 100, "high": 101, "low": 99},
    )

    payload = build_local_candle_feed_capture_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["detector_feed_readiness"]["feed_readiness"] == "LOCAL_FEED_INVALID_SHAPE"
    assert payload["normalized_feed_preview"]["valid_candles_found"] == 0


def test_rejects_fake_synthetic_ohlc(tmp_path: Path) -> None:
    fake = _valid_candles()[0] | {"synthetic": True, "source": "synthetic_signal_builder"}
    _append_json(tmp_path / "logs" / "candles.ndjson", fake)

    payload = build_local_candle_feed_capture_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["normalized_feed_preview"]["valid_candles_found"] == 0
    assert payload["safety"]["fake_ohlc_created"] is False
    assert "missing_required_true_ohlc_shape" in {
        row["reason"] for row in payload["source_discovery"]["invalid_or_synthetic_sources"]
    }


def test_high_low_consistency_is_validated(tmp_path: Path) -> None:
    bad_high = _valid_candles()[0] | {"high": 99.0}
    bad_low = _valid_candles()[1] | {"low": 99.0}
    _append_json(tmp_path / "logs" / "candles.ndjson", bad_high)
    _append_json(tmp_path / "logs" / "candles.ndjson", bad_low)

    payload = build_local_candle_feed_capture_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["normalized_feed_preview"]["valid_candles_found"] == 0
    reasons = payload["source_discovery"]["invalid_or_synthetic_sources"][0]["invalid_reasons"]
    assert reasons["high_below_open_or_close"] == 1
    assert reasons["low_above_open_or_close"] == 1


def test_feed_readiness_is_valid_when_valid_candles_exist(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs" / "candles.ndjson")

    payload = build_local_candle_feed_capture_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["detector_feed_readiness"]["feed_readiness"] == VALID_LOCAL_OHLC_FEED_AVAILABLE
    assert payload["detector_feed_readiness"]["three_black_crows_ready_to_detect"] is True


def test_would_write_feed_now_false_and_no_env_config_mutation(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs" / "candles.ndjson")
    config_path = tmp_path / "lane_controls.json"
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_local_candle_feed_capture_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["normalized_feed_preview"]["would_write_feed_now"] is False
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["candle_feed_written"] is False
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")


def test_no_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_candles(tmp_path / "logs" / "candles.ndjson")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_local_candle_feed_capture_preview(log_dir=tmp_path / "logs", now=NOW)

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


def test_cli_exists(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs" / "candles.ndjson")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "local-candle-feed-preview",
            "--symbol",
            "BTCUSDT",
            "--timeframe",
            "8m",
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
    assert payload["target_context"]["consumer"] == "three_black_crows_detector"
    assert payload["detector_feed_readiness"]["feed_readiness"] == VALID_LOCAL_OHLC_FEED_AVAILABLE
    assert "local-candle-feed-preview" in help_result.stdout


def _valid_candles() -> list[dict]:
    return [
        {
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "open_time": "2026-06-04T12:00:00+00:00",
            "open": 100.0,
            "high": 100.5,
            "low": 97.8,
            "close": 98.0,
            "source": "local_test_feed",
        },
        {
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "open_time": "2026-06-04T12:08:00+00:00",
            "open": 98.7,
            "high": 99.0,
            "low": 96.2,
            "close": 96.8,
            "source": "local_test_feed",
        },
        {
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "open_time": "2026-06-04T12:16:00+00:00",
            "open": 97.1,
            "high": 97.5,
            "low": 94.6,
            "close": 95.2,
            "source": "local_test_feed",
            "volume": 12.3,
        },
    ]


def _write_candles(path: Path) -> None:
    for candle in _valid_candles():
        _append_json(path, candle)


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
