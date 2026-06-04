from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.crow_outcome_mapping_preview import (
    CONFIRM_CROW_OUTCOME_MAPPING_PREVIEW_RECORDING_PHRASE,
    CROW_OUTCOME_MAPPING_PREVIEW_RECORDED,
    CROW_OUTCOME_MAPPING_PREVIEW_REJECTED,
    LEDGER_FILENAME,
    OUTCOME_MAPPING_NO_DETECTIONS,
    OUTCOME_MAPPING_NO_LOCAL_CANDLES,
    OUTCOME_MAPPING_PARTIAL_FUTURE_CANDLES_MISSING,
    build_crow_outcome_mapping_preview,
    build_crow_outcome_summary,
    compute_short_outcome_window,
    load_crow_outcome_mapping_preview_records,
    map_detection_to_future_candles,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
LANE = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_inputs(tmp_path / "logs")

    payload = build_crow_outcome_mapping_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_mapping_requested"] is False
    assert payload["mapping_recorded"] is False
    assert payload["mapping_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_inputs(tmp_path / "logs")

    payload = build_crow_outcome_mapping_preview(
        log_dir=tmp_path / "logs",
        record_mapping=True,
        confirm_crow_outcome_mapping="wrong",
        now=NOW,
    )

    assert payload["status"] == CROW_OUTCOME_MAPPING_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["mapping_recorded"] is False
    assert load_crow_outcome_mapping_preview_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_mapping_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_inputs(log_dir)
    before_env = dict(os.environ)

    payload = build_crow_outcome_mapping_preview(
        log_dir=log_dir,
        record_mapping=True,
        confirm_crow_outcome_mapping=CONFIRM_CROW_OUTCOME_MAPPING_PREVIEW_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_crow_outcome_mapping_preview_records(log_dir=log_dir, limit=0)

    assert payload["status"] == CROW_OUTCOME_MAPPING_PREVIEW_RECORDED
    assert payload["mapping_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "CROW_OUTCOME_MAPPING_PREVIEW"
    assert before_env == dict(os.environ)
    assert not (log_dir / "candles_BTCUSDT_8m.ndjson").exists()


def test_missing_detections_blocks(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs")

    payload = build_crow_outcome_mapping_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["outcome_mapping_status"] == OUTCOME_MAPPING_NO_DETECTIONS
    assert payload["input_summary"]["detections_loaded"] == 0
    assert payload["mapping_recorded"] is False


def test_missing_candles_blocks(tmp_path: Path) -> None:
    _write_detection_records(tmp_path / "logs")
    _write_paper_tags(tmp_path / "logs")

    payload = build_crow_outcome_mapping_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["outcome_mapping_status"] == OUTCOME_MAPPING_NO_LOCAL_CANDLES
    assert payload["input_summary"]["candles_loaded"] == 0
    assert payload["mapping_recorded"] is False


def test_maps_detection_to_future_candle_windows(tmp_path: Path) -> None:
    candles = _candles()
    detection = _detection("det_1", candles[0]["open_time"], "strict")

    mapped = map_detection_to_future_candles(detection, candles)
    windows = compute_short_outcome_window(
        entry_reference_price=mapped["entry_reference_price"],
        future_candles=mapped["future_candles"],
    )

    assert mapped["entry_reference_price"] == 100.0
    assert mapped["entry_reference_source"] == "detection_close"
    assert set(windows) == {"1", "3", "5", "10"}


def test_computes_short_favorable_close_mfe_and_mae_correctly() -> None:
    windows = compute_short_outcome_window(
        entry_reference_price=100.0,
        future_candles=[
            _candle(1, 100.0, 100.05, 99.8, 99.9),
            _candle(2, 99.9, 100.04, 99.7, 99.75),
            _candle(3, 99.75, 100.03, 99.6, 99.65),
        ],
        windows=(1, 3),
        success_threshold_pct=0.10,
        adverse_threshold_pct=0.10,
    )

    assert windows["1"]["close_return_pct"] == -0.1
    assert windows["1"]["mfe_downside_pct"] == 0.2
    assert windows["1"]["mae_upside_pct"] == 0.05
    assert windows["1"]["favorable_close"] is True
    assert windows["1"]["adverse_close"] is False
    assert windows["1"]["simple_success"] is True
    assert windows["1"]["simple_failure"] is False
    assert windows["3"]["mfe_downside_pct"] == 0.4


def test_handles_insufficient_future_candles(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_detection_records(log_dir)
    _write_paper_tags(log_dir)
    _write_candles(log_dir, future_count=1)

    payload = build_crow_outcome_mapping_preview(log_dir=log_dir, now=NOW)

    assert payload["outcome_mapping_status"] == OUTCOME_MAPPING_PARTIAL_FUTURE_CANDLES_MISSING
    assert set(payload["mapped_outcomes"][0]["windows"]) == {"1"}


def test_aggregate_summary_computes_rates() -> None:
    summary = build_crow_outcome_summary(
        [
            {"mode": "strict", "windows": {"1": {"favorable_close": True, "simple_success": True, "simple_failure": False, "close_return_pct": -0.1, "mfe_downside_pct": 0.2, "mae_upside_pct": 0.05}}},
            {"mode": "loose_preview", "windows": {"1": {"favorable_close": False, "simple_success": False, "simple_failure": True, "close_return_pct": 0.1, "mfe_downside_pct": 0.05, "mae_upside_pct": 0.2}}},
        ]
    )

    assert summary["mapped_count"] == 2
    assert summary["strict_mapped_count"] == 1
    assert summary["loose_mapped_count"] == 1
    assert summary["window_stats"]["1"]["favorable_close_rate_pct"] == 50.0
    assert summary["window_stats"]["1"]["simple_success_rate_pct"] == 50.0
    assert summary["window_stats"]["1"]["simple_failure_rate_pct"] == 50.0
    assert summary["window_stats"]["1"]["avg_close_return_pct"] == 0.0


def test_supports_short_bias_true_when_outcome_rates_are_favorable(tmp_path: Path) -> None:
    _write_inputs(tmp_path / "logs")

    payload = build_crow_outcome_mapping_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["aggregate_summary"]["mapped_count"] == 2
    assert payload["interpretation"]["supports_short_bias"] is True
    assert payload["interpretation"]["paper_tracking_recommended"] is True


def test_live_ready_false_always(tmp_path: Path) -> None:
    _write_inputs(tmp_path / "logs")

    payload = build_crow_outcome_mapping_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["interpretation"]["live_ready"] is False
    assert all(row["live_authorized"] is False for row in payload["mapped_outcomes"])


def test_no_env_config_mutation(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_inputs(log_dir)
    config_path = tmp_path / "lane_controls.json"
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_crow_outcome_mapping_preview(log_dir=log_dir, now=NOW)

    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["lane_config_written"] is False


def test_no_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_inputs(tmp_path / "logs")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_crow_outcome_mapping_preview(log_dir=tmp_path / "logs", now=NOW)

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
    _write_inputs(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "crow-outcome-mapping-preview",
            "--symbol",
            "BTCUSDT",
            "--timeframe",
            "8m",
            "--lane-key",
            LANE,
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
    assert payload["target_context"]["primary_lane"] == LANE
    assert "aggregate_summary" in payload
    assert "crow-outcome-mapping-preview" in help_result.stdout


def _write_inputs(log_dir: Path) -> None:
    _write_detection_records(log_dir)
    _write_paper_tags(log_dir)
    _write_candles(log_dir)


def _write_detection_records(log_dir: Path) -> None:
    stale = {
        "event_type": "THREE_BLACK_CROWS_LOCAL_DETECTION",
        "detection_id": "source_old",
        "recorded_at_utc": "2026-06-04T10:00:00+00:00",
        "target_context": {"primary_lane": LANE, "symbol": "BTCUSDT", "timeframe": "8m", "direction": "short", "signal_origin": "three_black_crows"},
        "detections": [_detection("old_det", "2026-06-04T11:00:00+00:00", "strict")],
    }
    latest = {
        "event_type": "THREE_BLACK_CROWS_LOCAL_DETECTION",
        "detection_id": "source_latest",
        "recorded_at_utc": "2026-06-04T12:00:00+00:00",
        "target_context": {"primary_lane": LANE, "symbol": "BTCUSDT", "timeframe": "8m", "direction": "short", "signal_origin": "three_black_crows"},
        "detections": [
            _detection("det_1", "2026-06-04T12:00:00+00:00", "strict"),
            _detection("det_2", "2026-06-04T12:08:00+00:00", "loose_preview"),
        ],
    }
    _append_json(log_dir / "three_black_crows_local_detections.ndjson", stale)
    _append_json(log_dir / "three_black_crows_local_detections.ndjson", latest)


def _write_paper_tags(log_dir: Path) -> None:
    for detection_id in ("det_1", "det_2"):
        _append_json(
            log_dir / "three_black_crows_paper_tags.ndjson",
            {
                "event_type": "THREE_BLACK_CROWS_PAPER_TAG",
                "tag_id": f"tag_{detection_id}",
                "detection_id": detection_id,
                "signal_origin": "three_black_crows",
                "lane_key": LANE,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "paper_only": True,
                "live_authorized": False,
            },
        )


def _write_candles(log_dir: Path, *, future_count: int = 12) -> None:
    path = log_dir / "candle_archive" / "BTCUSDT_8m.ndjson"
    for row in _candles(future_count=future_count):
        _append_json(path, row)


def _candles(*, future_count: int = 12) -> list[dict[str, object]]:
    rows = [_candle(0, 101.0, 102.0, 99.5, 100.0)]
    for index in range(1, future_count + 1):
        close = 100.0 - (index * 0.05)
        rows.append(_candle(index, 100.0, 100.05, 99.8 - (index * 0.05), close))
    return rows


def _detection(detection_id: str, detected_at: str, mode: str) -> dict[str, object]:
    return {
        "detection_id": detection_id,
        "signal_origin": "three_black_crows",
        "lane_key": LANE,
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "mode": mode,
        "confidence": "HIGH" if mode == "strict" else "LOW",
        "detected_at": detected_at,
        "paper_only": True,
        "live_authorized": False,
    }


def _candle(offset: int, open_price: float, high: float, low: float, close: float) -> dict[str, object]:
    ts = datetime(2026, 6, 4, 12, 0, tzinfo=UTC) + timedelta(minutes=8 * offset)
    return {
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "open_time": ts.isoformat(),
        "timestamp": ts.isoformat(),
        "source": "local_test_feed",
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1.0,
    }


def _append_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
