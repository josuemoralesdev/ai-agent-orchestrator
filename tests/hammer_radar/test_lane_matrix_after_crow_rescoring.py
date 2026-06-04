from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.lane_matrix_after_crow_rescoring import (
    CONFIRM_LANE_MATRIX_AFTER_CROW_RESCORING_RECORDING_PHRASE,
    HAMMER_REMAINS_CURRENT_BEST_PAIR,
    LANE_MATRIX_AFTER_CROW_RESCORING_RECORDED,
    LANE_MATRIX_AFTER_CROW_RESCORING_REJECTED,
    LEDGER_FILENAME,
    PAIR_NEEDS_PAPER_OUTCOME_MAPPING,
    build_lane_matrix_after_crow_rescoring,
    load_lane_matrix_after_crow_rescoring_records,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
LANE = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_r192_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_rescoring(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_matrix_requested"] is False
    assert payload["matrix_recorded"] is False
    assert payload["matrix_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_r192_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_rescoring(
        log_dir=tmp_path / "logs",
        record_matrix=True,
        confirm_lane_matrix_after_crow_rescore="wrong",
        now=NOW,
    )

    assert payload["status"] == LANE_MATRIX_AFTER_CROW_RESCORING_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["matrix_recorded"] is False
    assert load_lane_matrix_after_crow_rescoring_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_matrix_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_r192_inputs(log_dir)
    before_env = dict(os.environ)

    payload = build_lane_matrix_after_crow_rescoring(
        log_dir=log_dir,
        record_matrix=True,
        confirm_lane_matrix_after_crow_rescore=CONFIRM_LANE_MATRIX_AFTER_CROW_RESCORING_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_lane_matrix_after_crow_rescoring_records(log_dir=log_dir, limit=0)

    assert payload["status"] == LANE_MATRIX_AFTER_CROW_RESCORING_RECORDED
    assert payload["matrix_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "LANE_MATRIX_AFTER_CROW_RESCORING"
    assert before_env == dict(os.environ)


def test_hammer_remains_best_when_hammer_score_is_higher(tmp_path: Path) -> None:
    _write_r192_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_rescoring(log_dir=tmp_path / "logs", now=NOW)

    assert payload["current_best_pair"]["lane_key"] == LANE
    assert payload["current_best_pair"]["signal_origin"] == "hammer_wick_reversal"
    assert payload["pair_comparison"]["hammer_wick_reversal"]["origin_keter_score"] == 82
    assert payload["pair_comparison"]["three_black_crows"]["origin_keter_score"] == 56
    assert payload["pair_comparison"]["hammer_wick_reversal"]["pair_score"] > payload["pair_comparison"]["three_black_crows"][
        "pair_score"
    ]
    assert payload["post_crow_matrix_status"] == HAMMER_REMAINS_CURRENT_BEST_PAIR


def test_crows_become_paper_tracking_candidate_after_r191_score(tmp_path: Path) -> None:
    _write_r192_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_rescoring(log_dir=tmp_path / "logs", now=NOW)
    crows = payload["pair_comparison"]["three_black_crows"]

    assert crows["pair_score"] >= 50
    assert crows["strict_detections_found"] == 5
    assert crows["loose_detections_found"] == 18
    assert crows["paper_tags_found"] == 23
    assert payload["recommendations"]["paper_track_three_black_crows"] is True


def test_crows_require_paper_outcome_mapping(tmp_path: Path) -> None:
    _write_r192_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_rescoring(log_dir=tmp_path / "logs", now=NOW)
    crows = payload["pair_comparison"]["three_black_crows"]

    assert crows["pair_readiness"] == PAIR_NEEDS_PAPER_OUTCOME_MAPPING
    assert crows["needs_paper_outcome_mapping"] is True
    assert payload["recommendations"]["map_crow_detections_to_paper_outcomes"] is True
    assert payload["recommended_next_operator_move"] == "RUN_R193_CROW_OUTCOME_MAPPING_PREVIEW"


def test_family_reuse_plan_includes_three_white_soldiers_and_engulfing_detectors(tmp_path: Path) -> None:
    _write_r192_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_rescoring(log_dir=tmp_path / "logs", now=NOW)
    origins = {row["next_origin"] for row in payload["candle_pattern_family_reuse_plan"]}

    assert "three_white_soldiers" in origins
    assert "bearish_engulfing" in origins
    assert "bullish_engulfing" in origins
    assert payload["recommendations"]["build_three_white_soldiers_detector_later"] is True
    assert payload["recommendations"]["build_engulfing_detectors_later"] is True


def test_no_live_authorization_no_origin_or_lane_promotion(tmp_path: Path) -> None:
    _write_r192_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_rescoring(log_dir=tmp_path / "logs", now=NOW)

    assert payload["recommendations"]["no_live_authorization"] is True
    assert payload["pair_comparison"]["hammer_wick_reversal"]["live_authorized"] is False
    assert payload["pair_comparison"]["three_black_crows"]["live_authorized"] is False
    assert payload["safety"]["live_authorization_created"] is False
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False


def test_no_env_config_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    config_path = tmp_path / "lane_controls.json"
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    _write_r192_inputs(log_dir)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_lane_matrix_after_crow_rescoring(log_dir=log_dir, now=NOW)

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
    _write_r192_inputs(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "lane-matrix-after-crow-rescoring",
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
    assert "pair_comparison" in payload
    assert "lane-matrix-after-crow-rescoring" in help_result.stdout


def _write_r192_inputs(log_dir: Path) -> None:
    _append_json(
        log_dir / "multi_lane_evidence_rankings.ndjson",
        {
            "event_type": "MULTI_LANE_EVIDENCE_RANKING",
            "status": "MULTI_LANE_EVIDENCE_RANKING_RECORDED",
            "ranked_lanes": [
                {
                    "lane_key": LANE,
                    "mode": "paper",
                    "fresh_capture_count": 10,
                    "fresh_threshold_required": 10,
                    "fresh_threshold_met": True,
                    "score": 72,
                    "reference_only": False,
                }
            ],
        },
    )
    _append_json(
        log_dir / "signal_origin_lane_matrix.ndjson",
        {
            "event_type": "SIGNAL_ORIGIN_LANE_MATRIX",
            "status": "SIGNAL_ORIGIN_LANE_MATRIX_RECORDED",
            "lane_origin_matrix": [
                {
                    "lane_key": LANE,
                    "signal_origin": "hammer_wick_reversal",
                    "lane_score": 72,
                    "origin_keter_score": 82,
                    "pair_score": 76,
                    "pair_readiness": "PAIR_READY_FOR_PAPER_TRACKING",
                    "fresh_capture_count": 10,
                    "required_fresh_capture_count": 10,
                    "threshold_met": True,
                    "tagged_record_count_for_lane": 114,
                    "paper_only": True,
                    "live_authorized": False,
                },
                {
                    "lane_key": LANE,
                    "signal_origin": "three_black_crows",
                    "lane_score": 72,
                    "origin_keter_score": 0,
                    "pair_score": 0,
                    "pair_readiness": "PAIR_NEEDS_DETECTOR",
                    "fresh_capture_count": 10,
                    "required_fresh_capture_count": 10,
                    "threshold_met": True,
                    "tagged_record_count_for_lane": 0,
                    "paper_only": True,
                    "live_authorized": False,
                },
            ],
            "current_best_pair": {
                "lane_key": LANE,
                "signal_origin": "hammer_wick_reversal",
                "pair_score": 76,
                "paper_only": True,
                "live_authorized": False,
            },
        },
    )
    _append_json(
        log_dir / "keter_rescore_after_three_black_crows.ndjson",
        {
            "event_type": "KETER_RESCORING_AFTER_THREE_BLACK_CROWS",
            "status": "KETER_RESCORING_AFTER_CROWS_RECORDED",
            "target_context": {
                "signal_origin": "three_black_crows",
                "primary_lane": LANE,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
            },
            "input_feedback": {
                "feedback_found": True,
                "detection_records_found": 23,
                "paper_tags_found": 23,
                "strict_detections_found": 5,
                "loose_detections_found": 18,
                "local_detector_available": True,
                "paper_only": True,
                "live_authorized": False,
                "signal_origin_promoted": False,
                "lane_promoted": False,
            },
            "three_black_crows_rescore": {
                "previous_keter_score": 0,
                "new_keter_score": 56,
                "readiness": "CROWS_READY_FOR_PAPER_TRACKING_REVIEW",
                "score_band": "paper tracking candidate",
                "paper_only": True,
                "live_authorized": False,
                "signal_origin_promoted": False,
            },
            "comparison_to_hammer": {
                "hammer_keter_score": 82,
                "three_black_crows_keter_score": 56,
                "hammer_still_best_origin": True,
            },
        },
    )


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
