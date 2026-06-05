from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.anchor_outcome_deepening import (
    ANCHOR_OUTCOME_DEEPENING_RECORDED,
    ANCHOR_OUTCOME_DEEPENING_REJECTED,
    CONFIRM_ANCHOR_OUTCOME_DEEPENING_RECORDING_PHRASE,
    LEDGER_FILENAME,
    build_anchor_interaction_rankings,
    build_anchor_outcome_deepening,
    build_anchor_sample_quality_report,
    build_anchor_signal_origin_confluence,
    load_anchor_outcome_deepening_records,
)

NOW = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _anchor_candles(80))

    payload = build_anchor_outcome_deepening(log_dir=tmp_path / "logs", symbol="BTCUSDT", now=NOW)

    assert payload["record_deepening_requested"] is False
    assert payload["deepening_recorded"] is False
    assert payload["deepening_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _anchor_candles(80))

    payload = build_anchor_outcome_deepening(
        log_dir=tmp_path / "logs",
        record_deepening=True,
        confirm_anchor_outcome_deepening="wrong",
        now=NOW,
    )

    assert payload["status"] == ANCHOR_OUTCOME_DEEPENING_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["deepening_recorded"] is False
    assert load_anchor_outcome_deepening_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_deepening_only(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _anchor_candles(80))
    before_env = dict(os.environ)

    payload = build_anchor_outcome_deepening(
        log_dir=tmp_path / "logs",
        record_deepening=True,
        confirm_anchor_outcome_deepening=CONFIRM_ANCHOR_OUTCOME_DEEPENING_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_anchor_outcome_deepening_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == ANCHOR_OUTCOME_DEEPENING_RECORDED
    assert payload["deepening_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "ANCHOR_OUTCOME_DEEPENING"
    assert before_env == dict(os.environ)
    assert payload["safety"]["config_written"] is False


def test_sample_quality_classification_works() -> None:
    rankings = [
        {"mapped_events": 29, "sample_confidence": "LOW"},
        {"mapped_events": 30, "sample_confidence": "MEDIUM"},
        {"mapped_events": 100, "sample_confidence": "HIGH"},
    ]

    report = build_anchor_sample_quality_report(rankings)

    assert report["low_confidence_candidates"] == 1
    assert report["medium_confidence_candidates"] == 1
    assert report["high_confidence_candidates"] == 1


def test_high_failure_rate_produces_warning() -> None:
    ranking = build_anchor_interaction_rankings([_mapped_event(success=True, failure=True) for _ in range(35)])

    assert "VERY_HIGH_FAILURE_RATE" in ranking[0]["risk_warnings"]


def test_candidate_score_penalizes_low_sample_count() -> None:
    low = build_anchor_interaction_rankings([_mapped_event(success=True, failure=False) for _ in range(5)])[0]
    medium = build_anchor_interaction_rankings([_mapped_event(success=True, failure=False) for _ in range(35)])[0]

    assert low["sample_confidence"] == "LOW"
    assert medium["sample_confidence"] == "MEDIUM"
    assert medium["score"] > low["score"]


def test_candidate_score_penalizes_adverse_greater_than_favorable() -> None:
    favorable = build_anchor_interaction_rankings(
        [_mapped_event(success=True, failure=False, favorable=2.0, adverse=0.2) for _ in range(120)]
    )[0]
    adverse = build_anchor_interaction_rankings(
        [_mapped_event(success=True, failure=False, favorable=0.2, adverse=2.0) for _ in range(120)]
    )[0]

    assert "ADVERSE_MOVE_EXCEEDS_FAVORABLE_MOVE_BY_LARGE_MARGIN" in adverse["risk_warnings"]
    assert favorable["score"] > adverse["score"]


def test_confluence_summary_handles_summary_level_only_overlays(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "pattern_family_feedback_sync.ndjson").write_text(
        json.dumps(
            {
                "event_type": "PATTERN_FAMILY_FEEDBACK_SYNC",
                "target_scope": {"symbol": "BTCUSDT"},
                "pattern_family_detection_summary": {
                    "bullish_engulfing": {
                        "strict_detections_found": 40,
                        "loose_detections_found": 75,
                        "timeframes_with_detections": ["8m"],
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    confluence = build_anchor_signal_origin_confluence(
        log_dir=log_dir,
        symbol="BTCUSDT",
        anchor_rankings=[
            {
                "timeframe": "8m",
                "anchor_type": "custom_wma",
                "period": 89,
                "interaction": "rejection_up",
                "sample_confidence": "HIGH",
                "score": 12,
            }
        ],
    )

    assert confluence["confluence_records_found"] == 1
    assert confluence["confluence_resolution"] == "summary_level_only"
    assert confluence["top_confluences"][0]["signal_origin"] == "bullish_engulfing"


def test_no_live_authorization_or_anchor_position_permission(tmp_path: Path) -> None:
    _write_candles(tmp_path / "logs", "8m", _anchor_candles(80))

    payload = build_anchor_outcome_deepening(log_dir=tmp_path / "logs", now=NOW)

    assert payload["target_scope"]["live_authorized"] is False
    assert payload["target_scope"]["paper_only"] is True
    assert payload["safety"]["anchor_live_authorized"] is False
    assert payload["safety"]["anchor_position_permission_created"] is False
    assert all(row["live_authorized"] is False for row in payload["anchor_interaction_rankings"])


def test_no_env_config_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_candles(tmp_path / "logs", "8m", _anchor_candles(80))
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
        payload = build_anchor_outcome_deepening(log_dir=tmp_path / "logs", now=NOW)

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
    _write_candles(tmp_path / "logs", "8m", _anchor_candles(80))

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "anchor-outcome-deepening",
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
    assert payload["target_scope"]["outcome_windows"] == [1, 3, 5, 10, 21, 34, 55]
    assert payload["safety"]["anchor_live_authorized"] is False
    assert "anchor-outcome-deepening" in help_result.stdout


def _mapped_event(*, success: bool, failure: bool, favorable: float = 1.0, adverse: float = 0.1) -> dict:
    return {
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "anchor_type": "custom_wma",
        "period": 89,
        "interaction": "rejection_up",
        "direction_bias": "long",
        "windows": {
            "3": {
                "simple_success": success,
                "simple_failure": failure,
                "mfe_favorable_pct": favorable,
                "mae_adverse_pct": adverse,
            }
        },
    }


def _anchor_candles(count: int) -> list[dict]:
    candles = []
    for index in range(count):
        base = 100 + (index % 9) * 0.2
        close = base + (0.8 if index % 6 in {2, 3} else -0.8 if index % 6 in {4, 5} else 0.0)
        high = max(base, close) + 1.0
        low = min(base, close) - 1.0
        candles.append(_candle(index, base, high, low, close))
    return candles


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
