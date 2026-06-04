from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.local_candle_feed_adapter import (
    CONFIRM_LOCAL_CANDLE_FEED_ADAPTER_RECORDING_PHRASE,
    CONFIRM_NORMALIZED_LOCAL_CANDLE_FEED_WRITE_PHRASE,
    DETECTOR_READY_LOCAL_OHLC_AVAILABLE,
    LEDGER_FILENAME,
    LOCAL_CANDLE_FEED_ADAPTER_RECORDED,
    LOCAL_CANDLE_FEED_ADAPTER_REJECTED,
    LOCAL_CANDLE_FEED_ADAPTER_WRITTEN,
    build_detector_ready_candle_feed,
    build_local_candle_feed_adapter_preview,
    load_local_candle_feed_adapter_records,
    normalize_local_candle_feed,
    resolve_local_candle_feed_path,
    run_three_black_crows_on_local_feed,
    validate_normalized_candle_feed,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_local_candle_feed_adapter_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_adapter_requested"] is False
    assert payload["adapter_recorded"] is False
    assert payload["adapter_id"] is None
    assert payload["write_normalized_feed_requested"] is False
    assert payload["normalized_feed_written"] is False
    assert payload["normalized_feed"]["written"] is False
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_local_candle_feed_adapter_preview(
        log_dir=tmp_path / "logs",
        record_adapter=True,
        confirm_local_candle_feed_adapter="wrong",
        now=NOW,
    )

    assert payload["status"] == LOCAL_CANDLE_FEED_ADAPTER_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["adapter_recorded"] is False
    assert load_local_candle_feed_adapter_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_adapter_only(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")
    before_env = dict(os.environ)

    payload = build_local_candle_feed_adapter_preview(
        log_dir=tmp_path / "logs",
        record_adapter=True,
        confirm_local_candle_feed_adapter=CONFIRM_LOCAL_CANDLE_FEED_ADAPTER_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_local_candle_feed_adapter_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == LOCAL_CANDLE_FEED_ADAPTER_RECORDED
    assert payload["adapter_recorded"] is True
    assert payload["normalized_feed_written"] is False
    assert len(records) == 1
    assert records[0]["event_type"] == "LOCAL_CANDLE_FEED_ADAPTER"
    assert records[0]["normalized_feed"]["written"] is False
    assert before_env == dict(os.environ)
    assert not (tmp_path / "logs" / "candles_BTCUSDT_8m.ndjson").exists()


def test_valid_local_source_is_normalized(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    source_path = resolve_local_candle_feed_path(log_dir=tmp_path / "logs", symbol="BTCUSDT", timeframe="8m")
    normalized = normalize_local_candle_feed(_valid_candles(), symbol="BTCUSDT", timeframe="8m")
    payload = build_local_candle_feed_adapter_preview(log_dir=tmp_path / "logs", now=NOW)

    assert source_path == tmp_path / "logs" / "candle_archive" / "BTCUSDT_8m.ndjson"
    assert len(normalized) == 3
    assert normalized[0]["source"] == "local_test_feed"
    assert payload["source_feed"]["source_found"] is True
    assert payload["source_feed"]["valid_records"] == 3
    assert payload["normalized_feed"]["normalized_records"] == 3
    assert payload["normalized_feed"]["latest_candle_time"] == "2026-06-04T12:16:00+00:00"


def test_invalid_candles_are_rejected(tmp_path: Path) -> None:
    _append_json(
        tmp_path / "logs" / "candle_archive" / "BTCUSDT_8m.ndjson",
        {"symbol": "BTCUSDT", "timeframe": "8m", "open_time": "t", "open": 100, "high": 99, "low": 98, "close": 98},
    )

    payload = build_local_candle_feed_adapter_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["source_feed"]["valid_records"] == 0
    assert payload["source_feed"]["invalid_records"] == 1
    assert payload["detector_ready_feed"]["adapter_readiness"] == "LOCAL_OHLC_INVALID"


def test_default_does_not_write_normalized_feed(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_local_candle_feed_adapter_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["normalized_feed"]["would_write_by_default"] is False
    assert payload["normalized_feed"]["written"] is False
    assert payload["safety"]["candle_feed_written"] is False
    assert not (tmp_path / "logs" / "candles_BTCUSDT_8m.ndjson").exists()


def test_write_normalized_feed_requires_exact_write_confirmation(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_local_candle_feed_adapter_preview(
        log_dir=tmp_path / "logs",
        write_normalized_feed=True,
        confirm_normalized_candle_feed_write=CONFIRM_NORMALIZED_LOCAL_CANDLE_FEED_WRITE_PHRASE,
        now=NOW,
    )

    assert payload["status"] == LOCAL_CANDLE_FEED_ADAPTER_WRITTEN
    assert payload["write_confirmation_valid"] is True
    assert payload["normalized_feed_written"] is True
    assert payload["safety"]["candle_feed_written"] is True
    output_path = tmp_path / "logs" / "candles_BTCUSDT_8m.ndjson"
    assert output_path.exists()
    assert len(output_path.read_text(encoding="utf-8").splitlines()) == 3


def test_wrong_write_confirmation_does_not_write(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_local_candle_feed_adapter_preview(
        log_dir=tmp_path / "logs",
        write_normalized_feed=True,
        confirm_normalized_candle_feed_write="wrong",
        now=NOW,
    )

    assert payload["status"] == LOCAL_CANDLE_FEED_ADAPTER_REJECTED
    assert payload["write_confirmation_valid"] is False
    assert payload["normalized_feed_written"] is False
    assert not (tmp_path / "logs" / "candles_BTCUSDT_8m.ndjson").exists()


def test_detector_ready_when_valid_local_ohlc_exists(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")
    source_path = resolve_local_candle_feed_path(log_dir=tmp_path / "logs")
    normalized = normalize_local_candle_feed(_valid_candles())
    validation = validate_normalized_candle_feed(source_path=source_path, normalized_candles=normalized)
    ready = build_detector_ready_candle_feed(validation=validation, normalized_candles=normalized)

    assert ready["ready"] is True
    assert ready["adapter_readiness"] == DETECTOR_READY_LOCAL_OHLC_AVAILABLE


def test_strict_and_loose_detector_result_included(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_local_candle_feed_adapter_preview(log_dir=tmp_path / "logs", now=NOW)
    detector = run_three_black_crows_on_local_feed(normalize_local_candle_feed(_valid_candles()))

    assert payload["three_black_crows_detector_result"]["detector_status"] == "DETECTIONS_FOUND"
    assert payload["three_black_crows_detector_result"]["strict_detections_found"] == 1
    assert payload["three_black_crows_detector_result"]["loose_detections_found"] == 1
    assert detector["paper_only"] is True
    assert detector["live_authorized"] is False


def test_fake_ohlc_false_no_env_or_config_mutation(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")
    config_path = tmp_path / "lane_controls.json"
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_local_candle_feed_adapter_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["safety"]["fake_ohlc_created"] is False
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["env_mutated"] is False
    assert payload["safety"]["config_written"] is False
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")


def test_no_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_candles(tmp_path / "logs")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_local_candle_feed_adapter_preview(log_dir=tmp_path / "logs", now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    for key, value in payload["safety"].items():
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
            "local-candle-feed-adapter",
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
    assert payload["detector_ready_feed"]["ready"] is True
    assert "local-candle-feed-adapter" in help_result.stdout


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
            "open": 97.4,
            "high": 97.9,
            "low": 94.8,
            "close": 95.2,
            "source": "local_test_feed",
        },
    ]


def _write_candles(log_dir: Path) -> None:
    path = log_dir / "candle_archive" / "BTCUSDT_8m.ndjson"
    for candle in _valid_candles():
        _append_json(path, candle)


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
