from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.pattern_outcome_mapping_family import (
    CONFIRM_PATTERN_OUTCOME_MAPPING_FAMILY_RECORDING_PHRASE,
    LEDGER_FILENAME,
    PATTERN_OUTCOME_MAPPING_FAMILY_RECORDED,
    PATTERN_OUTCOME_MAPPING_FAMILY_REJECTED,
    build_pattern_family_aggregate_summary,
    build_pattern_outcome_mapping_family,
    compute_pattern_outcome_window,
    load_pattern_outcome_mapping_family_records,
    map_pattern_detection_to_future_candles,
)

NOW = datetime(2026, 6, 5, 18, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")
    _write_candles(tmp_path / "logs", _bullish_engulfing_sequence())

    payload = build_pattern_outcome_mapping_family(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_mapping_requested"] is False
    assert payload["mapping_recorded"] is False
    assert payload["mapping_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")
    _write_candles(tmp_path / "logs", _bullish_engulfing_sequence())

    payload = build_pattern_outcome_mapping_family(
        log_dir=tmp_path / "logs",
        record_mapping=True,
        confirm_pattern_outcome_family="wrong",
        now=NOW,
    )

    assert payload["status"] == PATTERN_OUTCOME_MAPPING_FAMILY_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["mapping_recorded"] is False
    assert load_pattern_outcome_mapping_family_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_mapping_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_r197_record(log_dir)
    _write_candles(log_dir, _bullish_engulfing_sequence())
    before_env = dict(os.environ)

    payload = build_pattern_outcome_mapping_family(
        log_dir=log_dir,
        record_mapping=True,
        confirm_pattern_outcome_family=CONFIRM_PATTERN_OUTCOME_MAPPING_FAMILY_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_pattern_outcome_mapping_family_records(log_dir=log_dir, limit=0)

    assert payload["status"] == PATTERN_OUTCOME_MAPPING_FAMILY_RECORDED
    assert payload["mapping_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "PATTERN_OUTCOME_MAPPING_FAMILY"
    assert before_env == dict(os.environ)
    assert not (log_dir / "candles_BTCUSDT_8m.ndjson").exists()


def test_maps_bullish_pattern_as_long_outcome(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")
    _write_candles(tmp_path / "logs", _bullish_engulfing_sequence())

    payload = build_pattern_outcome_mapping_family(log_dir=tmp_path / "logs", now=NOW)
    summary = payload["origin_outcome_summary"]["bullish_engulfing"]

    assert payload["input_summary"]["detections_loaded_by_origin"]["bullish_engulfing"] > 0
    assert summary["mapped_count"] > 0
    assert summary["supports_directional_bias"] is True
    ranking = next(row for row in payload["pattern_outcome_rankings"] if row["signal_origin"] == "bullish_engulfing")
    assert ranking["direction_bias"] == "long"
    assert ranking["paper_only"] is True
    assert ranking["live_authorized"] is False


def test_maps_bearish_pattern_as_short_outcome(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")
    _write_candles(tmp_path / "logs", _bearish_engulfing_sequence())

    payload = build_pattern_outcome_mapping_family(log_dir=tmp_path / "logs", now=NOW)
    ranking = next(row for row in payload["pattern_outcome_rankings"] if row["signal_origin"] == "bearish_engulfing")

    assert payload["origin_outcome_summary"]["bearish_engulfing"]["mapped_count"] > 0
    assert ranking["direction_bias"] == "short"
    assert ranking["favorable_close_rate_pct"] > 0


def test_exhaustion_wick_respects_direction_when_available(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")
    _write_candles(tmp_path / "logs", _upper_exhaustion_wick_sequence())

    payload = build_pattern_outcome_mapping_family(log_dir=tmp_path / "logs", now=NOW)
    rankings = [row for row in payload["pattern_outcome_rankings"] if row["signal_origin"] == "exhaustion_wick"]

    assert rankings
    assert {row["direction_bias"] for row in rankings} == {"short"}


def test_registry_only_retest_origins_remain_blocked(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")
    _write_candles(tmp_path / "logs", _bullish_engulfing_sequence())

    payload = build_pattern_outcome_mapping_family(log_dir=tmp_path / "logs", now=NOW)

    assert payload["origin_outcome_summary"]["breakdown_retest"]["mapped_count"] == 0
    assert payload["origin_outcome_summary"]["breakdown_retest"]["blocked_reason"] == "registry_only_until_retest_structure"
    assert payload["origin_outcome_summary"]["breakout_retest"]["mapped_count"] == 0
    assert payload["aggregate_summary"]["registry_only_blocked"] == ["breakdown_retest", "breakout_retest"]


def test_computes_favorable_close_correctly_for_long_and_short() -> None:
    long_windows = compute_pattern_outcome_window(
        entry_reference_price=100.0,
        future_candles=[_candle(1, 100.0, 101.0, 99.9, 100.5)],
        direction="long",
        windows=(1,),
    )
    short_windows = compute_pattern_outcome_window(
        entry_reference_price=100.0,
        future_candles=[_candle(1, 100.0, 100.1, 99.0, 99.5)],
        direction="short",
        windows=(1,),
    )

    assert long_windows["1"]["close_return_pct"] == 0.5
    assert long_windows["1"]["favorable_close"] is True
    assert short_windows["1"]["close_return_pct"] == -0.5
    assert short_windows["1"]["favorable_close"] is True


def test_computes_mfe_and_mae_correctly() -> None:
    long_windows = compute_pattern_outcome_window(
        entry_reference_price=100.0,
        future_candles=[
            _candle(1, 100.0, 100.5, 99.8, 100.2),
            _candle(2, 100.2, 101.0, 99.7, 100.8),
        ],
        direction="long",
        windows=(2,),
    )
    short_windows = compute_pattern_outcome_window(
        entry_reference_price=100.0,
        future_candles=[
            _candle(1, 100.0, 100.2, 99.5, 99.8),
            _candle(2, 99.8, 100.3, 99.0, 99.2),
        ],
        direction="short",
        windows=(2,),
    )

    assert long_windows["2"]["mfe_favorable_pct"] == 1.0
    assert long_windows["2"]["mae_adverse_pct"] == 0.3
    assert short_windows["2"]["mfe_favorable_pct"] == 1.0
    assert short_windows["2"]["mae_adverse_pct"] == 0.3


def test_map_detection_to_future_candles_uses_detection_close() -> None:
    candles = [_candle(index, 100 + index, 101 + index, 99 + index, 100 + index) for index in range(4)]
    detection = {"detected_at": candles[1]["open_time"]}

    mapped = map_pattern_detection_to_future_candles(detection, candles, windows=(1, 2))

    assert mapped["entry_reference_price"] == 101
    assert mapped["entry_reference_source"] == "detection_close"
    assert len(mapped["future_candles"]) == 2


def test_aggregate_summary_separates_positive_mixed_and_sample_limited_origins() -> None:
    aggregate = build_pattern_family_aggregate_summary(
        {
            "three_white_soldiers": {"mapped_count": 40, "supports_directional_bias": True, "needs_more_samples": False},
            "bearish_engulfing": {"mapped_count": 40, "supports_directional_bias": False, "needs_more_samples": False},
            "bullish_engulfing": {"mapped_count": 4, "supports_directional_bias": True, "needs_more_samples": True},
            "exhaustion_wick": {"mapped_count": 0, "supports_directional_bias": None, "needs_more_samples": True},
            "breakdown_retest": {"mapped_count": 0},
            "breakout_retest": {"mapped_count": 0},
        }
    )

    assert aggregate["origins_with_positive_bias"] == ["three_white_soldiers", "bullish_engulfing"]
    assert aggregate["origins_with_mixed_bias"] == ["bearish_engulfing"]
    assert aggregate["origins_needing_more_samples"] == ["bullish_engulfing", "exhaustion_wick"]


def test_rankings_are_paper_only_and_live_authorized_false(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")
    _write_candles(tmp_path / "logs", _bullish_engulfing_sequence())

    payload = build_pattern_outcome_mapping_family(log_dir=tmp_path / "logs", now=NOW)

    assert payload["pattern_outcome_rankings"]
    assert all(row["paper_only"] is True for row in payload["pattern_outcome_rankings"])
    assert all(row["live_authorized"] is False for row in payload["pattern_outcome_rankings"])


def test_no_env_config_mutation(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_r197_record(log_dir)
    _write_candles(log_dir, _bullish_engulfing_sequence())
    config_path = tmp_path / "lane_controls.json"
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_pattern_outcome_mapping_family(log_dir=log_dir, now=NOW)

    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["lane_config_written"] is False


def test_no_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_r197_record(tmp_path / "logs")
    _write_candles(tmp_path / "logs", _bullish_engulfing_sequence())
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_pattern_outcome_mapping_family(log_dir=tmp_path / "logs", now=NOW)

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
    _write_r197_record(tmp_path / "logs")
    _write_candles(tmp_path / "logs", _bullish_engulfing_sequence())

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "pattern-outcome-mapping-family",
            "--symbol",
            "BTCUSDT",
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
    assert payload["target_scope"]["signal_origins"]
    assert payload["target_scope"]["live_authorized"] is False
    assert "pattern-outcome-mapping-family" in help_result.stdout


def _write_r197_record(log_dir: Path) -> None:
    _append_json(
        log_dir / "pattern_detector_family_expansion.ndjson",
        {
            "event_type": "PATTERN_DETECTOR_FAMILY_EXPANSION",
            "expansion_id": "r197-test",
            "status": "PATTERN_DETECTOR_FAMILY_EXPANSION_RECORDED",
            "generated_at": "2026-06-05T12:00:00+00:00",
            "target_scope": {
                "symbol": "BTCUSDT",
                "timeframes": ["8m"],
                "patterns": [
                    "three_white_soldiers",
                    "bearish_engulfing",
                    "bullish_engulfing",
                    "exhaustion_wick",
                    "breakdown_retest",
                    "breakout_retest",
                ],
            },
            "detector_results": {
                "bullish_engulfing": {"strict_detections_found": 1, "loose_detections_found": 1, "paper_only": True, "live_authorized": False},
                "bearish_engulfing": {"strict_detections_found": 1, "loose_detections_found": 1, "paper_only": True, "live_authorized": False},
                "exhaustion_wick": {"strict_detections_found": 1, "loose_detections_found": 1, "paper_only": True, "live_authorized": False},
                "three_white_soldiers": {"strict_detections_found": 0, "loose_detections_found": 0, "paper_only": True, "live_authorized": False},
            },
            "safety": {"order_placed": False, "real_order_placed": False, "execution_attempted": False},
        },
    )


def _bullish_engulfing_sequence() -> list[dict]:
    candles = [
        _candle(0, 102.0, 102.2, 99.5, 100.0),
        _candle(1, 99.0, 103.5, 98.5, 103.0),
    ]
    candles.extend(_future_candles(start_index=2, start_price=103.0, step=0.3))
    return candles


def _bearish_engulfing_sequence() -> list[dict]:
    candles = [
        _candle(0, 100.0, 102.5, 99.8, 102.0),
        _candle(1, 103.0, 103.5, 98.5, 99.0),
    ]
    candles.extend(_future_candles(start_index=2, start_price=99.0, step=-0.3))
    return candles


def _upper_exhaustion_wick_sequence() -> list[dict]:
    candles = [_candle(0, 100.0, 110.0, 99.0, 99.5)]
    candles.extend(_future_candles(start_index=1, start_price=99.5, step=-0.25))
    return candles


def _future_candles(*, start_index: int, start_price: float, step: float, count: int = 60) -> list[dict]:
    candles: list[dict] = []
    price = start_price
    for offset in range(count):
        index = start_index + offset
        next_price = price + step
        high = max(price, next_price) + 0.2
        low = min(price, next_price) - 0.2
        candles.append(_candle(index, price, high, low, next_price))
        price = next_price
    return candles


def _candle(index: int, open_value: float, high: float, low: float, close: float) -> dict:
    timestamp = (NOW + timedelta(minutes=8 * index)).isoformat()
    return {
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "timestamp": timestamp,
        "open_time": timestamp,
        "open": open_value,
        "high": high,
        "low": low,
        "close": close,
        "source": "local_test_feed",
    }


def _write_candles(log_dir: Path, candles: list[dict]) -> None:
    path = log_dir / "candle_archive" / "BTCUSDT_8m.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for candle in candles:
            handle.write(json.dumps(candle, sort_keys=True) + "\n")


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
