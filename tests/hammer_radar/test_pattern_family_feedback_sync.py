from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.pattern_family_feedback_sync import (
    CONFIRM_PATTERN_FAMILY_FEEDBACK_SYNC_RECORDING_PHRASE,
    LEDGER_FILENAME,
    PATTERN_DETECTOR_EVIDENCE_AVAILABLE_REVIEW_REQUIRED,
    PATTERN_FAMILY_FEEDBACK_SYNC_RECORDED,
    PATTERN_FAMILY_FEEDBACK_SYNC_REJECTED,
    PATTERN_REGISTRY_ONLY_GAPS_REMAIN,
    READY_FOR_KETER_AND_MATRIX_REVIEW,
    READY_FOR_PATTERN_OUTCOME_MAPPING,
    build_pattern_family_feedback_sync,
    load_pattern_family_feedback_sync_records,
)

NOW = datetime(2026, 6, 5, 15, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")

    payload = build_pattern_family_feedback_sync(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_feedback_requested"] is False
    assert payload["feedback_recorded"] is False
    assert payload["feedback_id"] is None
    assert payload["feedback_status"] == READY_FOR_KETER_AND_MATRIX_REVIEW
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")

    payload = build_pattern_family_feedback_sync(
        log_dir=tmp_path / "logs",
        record_feedback=True,
        confirm_pattern_family_feedback_sync="wrong",
        now=NOW,
    )

    assert payload["status"] == PATTERN_FAMILY_FEEDBACK_SYNC_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["feedback_recorded"] is False
    assert load_pattern_family_feedback_sync_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_feedback_only(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")
    before_env = dict(os.environ)

    payload = build_pattern_family_feedback_sync(
        log_dir=tmp_path / "logs",
        record_feedback=True,
        confirm_pattern_family_feedback_sync=CONFIRM_PATTERN_FAMILY_FEEDBACK_SYNC_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_pattern_family_feedback_sync_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == PATTERN_FAMILY_FEEDBACK_SYNC_RECORDED
    assert payload["feedback_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "PATTERN_FAMILY_FEEDBACK_SYNC"
    assert records[0]["registry_feedback"]["write_registry_now"] is False
    assert records[0]["keter_feedback"]["write_scoring_now"] is False
    assert records[0]["lane_matrix_feedback"]["write_matrix_now"] is False
    assert before_env == dict(os.environ)


def test_reads_pattern_family_detector_summary(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")

    payload = build_pattern_family_feedback_sync(log_dir=tmp_path / "logs", now=NOW)
    summary = payload["pattern_family_detection_summary"]

    assert summary["three_white_soldiers"]["strict_detections_found"] == 7
    assert summary["bearish_engulfing"]["loose_detections_found"] == 178
    assert summary["bullish_engulfing"]["timeframes_with_detections"] == ["4m", "8m"]
    assert summary["exhaustion_wick"]["strict_detections_found"] == 831
    assert summary["three_white_soldiers"]["paper_only"] is True
    assert summary["three_white_soldiers"]["live_authorized"] is False


def test_detector_evidence_becomes_review_ready(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")

    payload = build_pattern_family_feedback_sync(log_dir=tmp_path / "logs", now=NOW)
    summary = payload["pattern_family_detection_summary"]

    for origin in ("three_white_soldiers", "bearish_engulfing", "bullish_engulfing", "exhaustion_wick"):
        assert summary[origin]["detector_available"] is True
    assert PATTERN_DETECTOR_EVIDENCE_AVAILABLE_REVIEW_REQUIRED in payload["feedback_statuses"]
    assert READY_FOR_PATTERN_OUTCOME_MAPPING in payload["feedback_statuses"]


def test_retest_origins_remain_registry_only_blocked(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")

    payload = build_pattern_family_feedback_sync(log_dir=tmp_path / "logs", now=NOW)
    summary = payload["pattern_family_detection_summary"]

    assert summary["breakdown_retest"]["detector_available"] is False
    assert summary["breakdown_retest"]["registry_only"] is True
    assert summary["breakout_retest"]["detector_available"] is False
    assert summary["breakout_retest"]["registry_only"] is True
    assert "breakdown_retest" in payload["keter_feedback"]["pattern_origins_blocked"]
    assert "breakout_retest" in payload["lane_matrix_feedback"]["origins_blocked_from_matrix"]
    assert PATTERN_REGISTRY_ONLY_GAPS_REMAIN in payload["feedback_statuses"]


def test_keter_and_lane_matrix_rerun_recommended_without_writes(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")

    payload = build_pattern_family_feedback_sync(log_dir=tmp_path / "logs", now=NOW)

    assert payload["keter_feedback"]["rerun_keter_scoring_recommended"] is True
    assert payload["keter_feedback"]["write_scoring_now"] is False
    assert payload["lane_matrix_feedback"]["rerun_lane_matrix_recommended"] is True
    assert payload["lane_matrix_feedback"]["write_matrix_now"] is False
    assert set(payload["keter_feedback"]["pattern_origins_ready_for_scoring"]) == {
        "three_white_soldiers",
        "bearish_engulfing",
        "bullish_engulfing",
        "exhaustion_wick",
    }


def test_registry_scoring_matrix_origin_lane_config_not_written_or_promoted(tmp_path: Path) -> None:
    _write_r197_record(tmp_path / "logs")

    payload = build_pattern_family_feedback_sync(log_dir=tmp_path / "logs", now=NOW)

    assert payload["registry_feedback"]["write_registry_now"] is False
    assert payload["registry_feedback"]["signal_origin_promoted"] is False
    assert payload["safety"]["registry_config_written"] is False
    assert payload["safety"]["scoring_config_written"] is False
    assert payload["safety"]["matrix_config_written"] is False
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False


def test_no_env_config_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_r197_record(tmp_path / "logs")
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
        payload = build_pattern_family_feedback_sync(log_dir=tmp_path / "logs", now=NOW)

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
    _write_r197_record(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "pattern-family-feedback-sync",
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
    assert payload["feedback_status"] == READY_FOR_KETER_AND_MATRIX_REVIEW
    assert "pattern-family-feedback-sync" in help_result.stdout


def _write_r197_record(log_dir: Path) -> None:
    _append_json(
        log_dir / "pattern_detector_family_expansion.ndjson",
        {
            "event_type": "PATTERN_DETECTOR_FAMILY_EXPANSION",
            "expansion_id": "r197-test",
            "status": "PATTERN_DETECTOR_FAMILY_EXPANSION_RECORDED",
            "generated_at": "2026-06-05T12:00:00+00:00",
            "record_expansion_requested": True,
            "confirmation_valid": True,
            "target_scope": {
                "symbol": "BTCUSDT",
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
                "three_white_soldiers": {
                    "strict_detections_found": 7,
                    "loose_detections_found": 27,
                    "timeframes_with_detections": ["13m", "4H", "4m", "8m"],
                    "paper_only": True,
                    "live_authorized": False,
                },
                "bearish_engulfing": {
                    "strict_detections_found": 53,
                    "loose_detections_found": 178,
                    "timeframes_with_detections": ["4m", "8m"],
                    "paper_only": True,
                    "live_authorized": False,
                },
                "bullish_engulfing": {
                    "strict_detections_found": 75,
                    "loose_detections_found": 189,
                    "timeframes_with_detections": ["4m", "8m"],
                    "paper_only": True,
                    "live_authorized": False,
                },
                "exhaustion_wick": {
                    "strict_detections_found": 831,
                    "loose_detections_found": 1602,
                    "timeframes_with_detections": ["4m", "8m"],
                    "paper_only": True,
                    "live_authorized": False,
                },
                "breakdown_retest": {
                    "detections_found": 0,
                    "detector_status": "REGISTRY_ONLY_PREVIEW",
                    "paper_only": True,
                    "live_authorized": False,
                },
                "breakout_retest": {
                    "detections_found": 0,
                    "detector_status": "REGISTRY_ONLY_PREVIEW",
                    "paper_only": True,
                    "live_authorized": False,
                },
            },
            "safety": {"order_placed": False, "real_order_placed": False},
        },
    )
    _append_json(
        log_dir / "wma_ma_anchor_layer_preview.ndjson",
        {
            "event_type": "WMA_MA_ANCHOR_LAYER_PREVIEW",
            "preview_id": "r199-test",
            "status": "WMA_MA_ANCHOR_LAYER_PREVIEW_RECORDED",
            "anchor_event_summary": {"events_by_timeframe": {"4m": 1000, "8m": 2000, "13m": 3000, "4H": 4000}},
            "safety": {"order_placed": False, "real_order_placed": False},
        },
    )


def _append_json(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
