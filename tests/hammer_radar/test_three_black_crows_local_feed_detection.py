from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.three_black_crows_local_feed_detection import (
    CONFIRM_THREE_BLACK_CROWS_LOCAL_DETECTION_RECORDING_PHRASE,
    LEDGER_FILENAME,
    LOOSE_DETECTIONS_FOUND,
    PAPER_TAG_LEDGER_FILENAME,
    STRICT_AND_LOOSE_DETECTIONS_FOUND,
    THREE_BLACK_CROWS_LOCAL_DETECTION_RECORDED,
    THREE_BLACK_CROWS_LOCAL_DETECTION_REJECTED,
    build_three_black_crows_local_feed_detection,
    load_three_black_crows_local_detection_records,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_three_black_crows_local_feed_detection(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_detection_requested"] is False
    assert payload["detection_recorded"] is False
    assert payload["detection_id"] is None
    assert payload["paper_tags"]["tags_created"] == 0
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()
    assert not (tmp_path / "logs" / PAPER_TAG_LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_three_black_crows_local_feed_detection(
        log_dir=tmp_path / "logs",
        record_detection=True,
        confirm_three_black_crows_local_detection="wrong",
        now=NOW,
    )

    assert payload["status"] == THREE_BLACK_CROWS_LOCAL_DETECTION_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["detection_recorded"] is False
    assert load_three_black_crows_local_detection_records(log_dir=tmp_path / "logs", limit=0) == []
    assert not (tmp_path / "logs" / PAPER_TAG_LEDGER_FILENAME).exists()


def test_correct_confirmation_records_detections_and_tags_only(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")
    before_env = dict(os.environ)

    payload = build_three_black_crows_local_feed_detection(
        log_dir=tmp_path / "logs",
        record_detection=True,
        confirm_three_black_crows_local_detection=CONFIRM_THREE_BLACK_CROWS_LOCAL_DETECTION_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_three_black_crows_local_detection_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == THREE_BLACK_CROWS_LOCAL_DETECTION_RECORDED
    assert payload["detection_recorded"] is True
    assert payload["paper_tags"]["tags_created"] == len(payload["detections"])
    assert len(records) == 1
    assert records[0]["event_type"] == "THREE_BLACK_CROWS_LOCAL_DETECTION"
    assert (tmp_path / "logs" / LEDGER_FILENAME).exists()
    assert (tmp_path / "logs" / PAPER_TAG_LEDGER_FILENAME).exists()
    assert not (tmp_path / "logs" / "candles_BTCUSDT_8m.ndjson").exists()
    assert before_env == dict(os.environ)


def test_uses_local_candle_adapter(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    with patch(
        "src.app.hammer_radar.operator.three_black_crows_local_feed_detection.load_local_candle_feed",
        wraps=__import__(
            "src.app.hammer_radar.operator.local_candle_feed_adapter",
            fromlist=["load_local_candle_feed"],
        ).load_local_candle_feed,
    ) as loader:
        payload = build_three_black_crows_local_feed_detection(log_dir=tmp_path / "logs", now=NOW)

    loader.assert_called_once()
    assert payload["local_feed"]["source_path"] == "logs/hammer_radar_forward/candle_archive/BTCUSDT_8m.ndjson"
    assert payload["local_feed"]["feed_ready"] is True


def test_strict_detections_produce_paper_only_records(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_three_black_crows_local_feed_detection(log_dir=tmp_path / "logs", mode="strict", now=NOW)

    assert payload["detector_result"]["strict_detections_found"] == 1
    assert payload["detector_result"]["loose_detections_found"] == 0
    assert payload["detections"]
    assert all(row["mode"] == "strict" for row in payload["detections"])
    assert all(row["paper_only"] is True for row in payload["detections"])
    assert all(row["live_authorized"] is False for row in payload["detections"])


def test_loose_detections_produce_paper_only_records(tmp_path: Path) -> None:
    _write_loose_only_candles(tmp_path / "logs")

    payload = build_three_black_crows_local_feed_detection(log_dir=tmp_path / "logs", mode="loose_preview", now=NOW)

    assert payload["detector_result"]["detection_status"] == LOOSE_DETECTIONS_FOUND
    assert payload["detector_result"]["loose_detections_found"] == 1
    assert payload["detections"][0]["mode"] == "loose_preview"
    assert payload["detections"][0]["paper_only"] is True
    assert payload["detections"][0]["live_authorized"] is False


def test_mode_both_includes_strict_and_loose_counts(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_three_black_crows_local_feed_detection(log_dir=tmp_path / "logs", mode="both", now=NOW)

    assert payload["detector_result"]["detection_status"] == STRICT_AND_LOOSE_DETECTIONS_FOUND
    assert payload["detector_result"]["strict_detections_found"] == 1
    assert payload["detector_result"]["loose_detections_found"] >= 1
    assert {row["mode"] for row in payload["detections"]} == {"strict", "loose_preview"}


def test_paper_tags_created_only_on_valid_confirmation(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    preview = build_three_black_crows_local_feed_detection(log_dir=tmp_path / "logs", now=NOW)
    rejected = build_three_black_crows_local_feed_detection(
        log_dir=tmp_path / "logs",
        record_detection=True,
        confirm_three_black_crows_local_detection="wrong",
        now=NOW,
    )
    recorded = build_three_black_crows_local_feed_detection(
        log_dir=tmp_path / "logs",
        record_detection=True,
        confirm_three_black_crows_local_detection=CONFIRM_THREE_BLACK_CROWS_LOCAL_DETECTION_RECORDING_PHRASE,
        now=NOW,
    )

    assert preview["paper_tags"]["tags_created"] == 0
    assert rejected["paper_tags"]["tags_created"] == 0
    assert recorded["paper_tags"]["tags_created"] == len(recorded["detections"])


def test_live_ready_origin_and_promotion_flags_stay_false(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_three_black_crows_local_feed_detection(log_dir=tmp_path / "logs", now=NOW)
    lane = payload["lane_detection_summary"]["BTCUSDT|8m|short|ladder_close_50_618"]
    feedback = payload["origin_feedback"]

    assert payload["detector_result"]["live_authorized"] is False
    assert lane["ready_for_live"] is False
    assert feedback["recommended_future_registry_status"] == "DETECTOR_AVAILABLE_AFTER_REVIEW"
    assert feedback["still_paper_only"] is True
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False


def test_no_env_config_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_candles(tmp_path / "logs")
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
        payload = build_three_black_crows_local_feed_detection(log_dir=tmp_path / "logs", now=NOW)

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
    _write_candles(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "three-black-crows-local-detection",
            "--symbol",
            "BTCUSDT",
            "--timeframe",
            "8m",
            "--latest-candles",
            "500",
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
    assert payload["target_context"]["signal_origin"] == "three_black_crows"
    assert payload["local_feed"]["feed_ready"] is True
    assert "three-black-crows-local-detection" in help_result.stdout


def _valid_candles() -> list[dict]:
    return [
        {
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "timestamp": "2026-06-04T12:00:00+00:00",
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
            "timestamp": "2026-06-04T12:08:00+00:00",
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
            "timestamp": "2026-06-04T12:16:00+00:00",
            "open_time": "2026-06-04T12:16:00+00:00",
            "open": 97.1,
            "high": 97.5,
            "low": 94.6,
            "close": 95.2,
            "source": "local_test_feed",
        },
    ]


def _loose_only_candles() -> list[dict]:
    candles = _valid_candles()
    candles[1].update({"open": 101.5, "high": 101.8, "low": 96.2, "close": 97.2})
    return candles


def _write_candles(log_dir: Path) -> None:
    for candle in _valid_candles():
        _append_json(log_dir / "candle_archive" / "BTCUSDT_8m.ndjson", candle)


def _write_loose_only_candles(log_dir: Path) -> None:
    for candle in _loose_only_candles():
        _append_json(log_dir / "candle_archive" / "BTCUSDT_8m.ndjson", candle)


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
