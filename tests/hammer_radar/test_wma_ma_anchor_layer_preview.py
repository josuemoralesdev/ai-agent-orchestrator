from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.wma_ma_anchor_layer_preview import (
    CONFIRM_WMA_MA_ANCHOR_PREVIEW_RECORDING_PHRASE,
    INSUFFICIENT_CANDLES_FOR_ANCHOR,
    LEDGER_FILENAME,
    WMA_MA_ANCHOR_LAYER_PREVIEW_RECORDED,
    WMA_MA_ANCHOR_LAYER_PREVIEW_REJECTED,
    build_anchor_candidate_ranking,
    build_anchor_event_candidates,
    build_anchor_signal_origin_overlay,
    build_wma_ma_anchor_layer_preview,
    classify_anchor_interaction,
    compute_anchor_series,
    compute_sma,
    compute_wma,
    load_wma_ma_anchor_preview_records,
    map_anchor_event_outcomes,
)

NOW = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _anchor_candles())

    payload = build_wma_ma_anchor_layer_preview(log_dir=tmp_path / "logs", timeframes=["8m"], periods=[3], now=NOW)

    assert payload["record_preview_requested"] is False
    assert payload["preview_recorded"] is False
    assert payload["preview_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _anchor_candles())

    payload = build_wma_ma_anchor_layer_preview(
        log_dir=tmp_path / "logs",
        timeframes=["8m"],
        periods=[3],
        record_preview=True,
        confirm_wma_ma_anchor_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == WMA_MA_ANCHOR_LAYER_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["preview_recorded"] is False
    assert load_wma_ma_anchor_preview_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_preview_only(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _anchor_candles())
    before_env = dict(os.environ)

    payload = build_wma_ma_anchor_layer_preview(
        log_dir=tmp_path / "logs",
        timeframes=["8m"],
        periods=[3],
        record_preview=True,
        confirm_wma_ma_anchor_preview=CONFIRM_WMA_MA_ANCHOR_PREVIEW_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_wma_ma_anchor_preview_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == WMA_MA_ANCHOR_LAYER_PREVIEW_RECORDED
    assert payload["preview_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "WMA_MA_ANCHOR_LAYER_PREVIEW"
    assert before_env == dict(os.environ)
    assert not (tmp_path / "logs" / "candles_BTCUSDT_8m.ndjson").exists()


def test_sma_and_wma_calculation_work() -> None:
    assert compute_sma([1, 2, 3, 4], 3) == 3.0
    assert compute_wma([1, 2, 3, 4], 3) == 3.333333
    assert compute_sma([1, 2], 3) is None
    assert compute_wma([1, 2], 3) is None


def test_insufficient_candles_are_blocked(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _anchor_candles()[:2])

    payload = build_wma_ma_anchor_layer_preview(log_dir=tmp_path / "logs", timeframes=["8m"], periods=[3], now=NOW)

    assert payload["anchor_status"] == INSUFFICIENT_CANDLES_FOR_ANCHOR
    assert payload["anchor_event_summary"]["total_anchor_events"] == 0
    assert payload["preview_recorded"] is False


def test_touch_near_touch_cross_and_rejection_classifications_work() -> None:
    previous = _candle(0, 99.0, 99.5, 98.8, 99.0)
    current_up = _candle(1, 99.0, 101.0, 98.9, 100.1)
    up = classify_anchor_interaction(current_up, anchor=100.0, previous_candle=previous, previous_anchor=100.0)

    assert up["touch"] is True
    assert up["near_touch"] is True
    assert up["cross_up"] is True
    assert up["rejection_up"] is True
    assert up["reclaim"] is True

    previous = _candle(0, 101.0, 101.5, 100.8, 101.0)
    current_down = _candle(1, 101.0, 100.2, 98.9, 99.9)
    down = classify_anchor_interaction(current_down, anchor=100.0, previous_candle=previous, previous_anchor=100.0)

    assert down["touch"] is True
    assert down["near_touch"] is True
    assert down["cross_down"] is True
    assert down["rejection_down"] is True
    assert down["loss"] is True


def test_outcome_mapping_works_for_long_and_short_hypotheses() -> None:
    events = [
        {"symbol": "BTCUSDT", "timeframe": "8m", "anchor_type": "custom_wma", "period": 3, "interaction": "cross_up", "direction_bias": "long", "candle_index": 0, "close": 100.0},
        {"symbol": "BTCUSDT", "timeframe": "8m", "anchor_type": "custom_wma", "period": 3, "interaction": "cross_down", "direction_bias": "short", "candle_index": 1, "close": 101.0},
    ]
    candles = [_candle(0, 100, 100, 100, 100), _candle(1, 101, 101.5, 100.8, 101), _candle(2, 101, 102, 99, 99)]

    mapped = map_anchor_event_outcomes(events, candles_by_timeframe={"8m": candles}, windows=(1,), success_threshold_pct=0.1, adverse_threshold_pct=0.1)

    assert len(mapped) == 2
    assert mapped[0]["windows"]["1"]["simple_success"] is True
    assert mapped[1]["windows"]["1"]["simple_success"] is True
    assert all(row["live_authorized"] is False for row in mapped)


def test_anchor_rankings_are_paper_only_and_live_authorized_false() -> None:
    mapped = [
        {
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "anchor_type": "custom_wma",
            "period": 3,
            "interaction": "cross_up",
            "direction_bias": "long",
            "windows": {"1": {"simple_success": True, "simple_failure": False, "mfe_favorable_pct": 1.0, "mae_adverse_pct": 0.1}},
        }
    ]

    ranking = build_anchor_candidate_ranking(mapped)

    assert ranking[0]["paper_only"] is True
    assert ranking[0]["live_authorized"] is False


def test_anchor_layer_does_not_create_position_permission(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _anchor_candles())

    payload = build_wma_ma_anchor_layer_preview(log_dir=tmp_path / "logs", timeframes=["8m"], periods=[3], now=NOW)

    assert payload["safety"]["anchor_position_permission_created"] is False
    assert all(row["live_authorized"] is False for row in payload["anchor_candidate_ranking"])


def test_signal_origin_overlay_is_preview_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "pattern_detector_family_expansion.ndjson").write_text(
        json.dumps(
            {
                "event_type": "PATTERN_DETECTOR_FAMILY_EXPANSION",
                "status": "PATTERN_DETECTOR_FAMILY_EXPANSION_RECORDED",
                "target_scope": {"symbol": "BTCUSDT", "timeframes": ["8m"]},
                "pattern_family_registry": [{"signal_origin": "bullish_engulfing"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    overlay = build_anchor_signal_origin_overlay(
        log_dir=log_dir,
        timeframes=["8m"],
        anchor_events=[{"timeframe": "8m"}],
    )

    assert overlay["overlap_records_found"] == 1
    assert overlay["top_overlaps"][0]["preview_only"] is True
    assert overlay["top_overlaps"][0]["live_authorized"] is False
    assert overlay["top_overlaps"][0]["signal_origin_promoted"] is False


def test_no_env_config_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_candles(tmp_path / "logs", "8m", _anchor_candles())
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
        payload = build_wma_ma_anchor_layer_preview(log_dir=tmp_path / "logs", timeframes=["8m"], periods=[3], now=NOW)

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


def test_build_anchor_events_uses_anchor_series() -> None:
    candles = _anchor_candles()
    series = compute_anchor_series(candles, periods=[3])

    events = build_anchor_event_candidates(candles, series, timeframe="8m")

    assert events
    assert all(event["paper_only"] is True and event["live_authorized"] is False for event in events)


def test_cli_exists(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _anchor_candles())

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "wma-ma-anchor-layer-preview",
            "--symbol",
            "BTCUSDT",
            "--timeframes",
            "8m",
            "--periods",
            "3",
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
    assert payload["target_scope"]["anchor_types"] == ["SMA200", "WMA200", "custom_wma"]
    assert payload["safety"]["anchor_live_authorized"] is False
    assert "wma-ma-anchor-layer-preview" in help_result.stdout


def _anchor_candles() -> list[dict]:
    return [
        _candle(0, 100, 101, 99, 100),
        _candle(1, 100, 101, 99, 99),
        _candle(2, 99, 100.1, 98.8, 99.5),
        _candle(3, 99.5, 101, 99, 100.4),
        _candle(4, 100.4, 101.2, 100.0, 100.8),
        _candle(5, 100.8, 101.0, 98.5, 99.4),
        _candle(6, 99.4, 100.5, 98.8, 100.2),
    ]


def _candle(index: int, open_: float, high: float, low: float, close: float) -> dict:
    opened = datetime(2026, 6, 5, 12, 0, tzinfo=UTC) + timedelta(minutes=8 * index)
    return {
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "open_time": opened.isoformat(),
        "timestamp": opened.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1,
    }


def _write_candles(log_dir: Path, timeframe: str, candles: list[dict]) -> None:
    archive = log_dir / "candle_archive"
    archive.mkdir(parents=True, exist_ok=True)
    with (archive / f"BTCUSDT_{timeframe}.ndjson").open("w", encoding="utf-8") as handle:
        for candle in candles:
            row = dict(candle)
            row["timeframe"] = timeframe
            handle.write(json.dumps(row) + "\n")
