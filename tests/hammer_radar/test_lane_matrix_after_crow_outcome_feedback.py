from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.lane_matrix_after_crow_outcome_feedback import (
    CONFIRM_LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_RECORDING_PHRASE,
    CROWS_CLOSE_GAP_BUT_NEED_MORE_SAMPLES,
    LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_RECORDED,
    LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_REJECTED,
    LEDGER_FILENAME,
    NOT_CLOSE_FUNDING_AND_EVIDENCE_BLOCKED,
    build_lane_matrix_after_crow_outcome_feedback,
    load_lane_matrix_after_crow_outcome_feedback_records,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
LANE = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_r195_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_outcome_feedback(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_matrix_requested"] is False
    assert payload["matrix_recorded"] is False
    assert payload["matrix_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_r195_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_outcome_feedback(
        log_dir=tmp_path / "logs",
        record_matrix=True,
        confirm_lane_matrix_after_crow_outcome="wrong",
        now=NOW,
    )

    assert payload["status"] == LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["matrix_recorded"] is False
    assert load_lane_matrix_after_crow_outcome_feedback_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_matrix_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_r195_inputs(log_dir)
    before_env = dict(os.environ)

    payload = build_lane_matrix_after_crow_outcome_feedback(
        log_dir=log_dir,
        record_matrix=True,
        confirm_lane_matrix_after_crow_outcome=CONFIRM_LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_lane_matrix_after_crow_outcome_feedback_records(log_dir=log_dir, limit=0)

    assert payload["status"] == LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_RECORDED
    assert payload["matrix_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK"
    assert before_env == dict(os.environ)


def test_hammer_remains_best_when_score_stays_above_crow(tmp_path: Path) -> None:
    _write_r195_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_outcome_feedback(log_dir=tmp_path / "logs", now=NOW)

    assert payload["current_best_pair"]["lane_key"] == LANE
    assert payload["current_best_pair"]["signal_origin"] == "hammer_wick_reversal"
    assert payload["current_best_pair"]["pair_score"] == 72
    assert payload["post_outcome_pair_comparison"]["three_black_crows"]["current_pair_score"] < 72
    assert payload["recommendations"]["keep_hammer_as_current_best_pair"] is True


def test_crow_closes_gap_after_outcome_feedback(tmp_path: Path) -> None:
    _write_r195_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_outcome_feedback(log_dir=tmp_path / "logs", now=NOW)
    crows = payload["post_outcome_pair_comparison"]["three_black_crows"]

    assert crows["previous_pair_score"] == 51
    assert crows["projected_keter_score_after_outcome"] == 69
    assert crows["outcome_score"] == 100
    assert crows["best_window"] == "10"
    assert crows["mapped_count"] == 23
    assert crows["needs_more_samples"] is True
    assert crows["current_pair_score"] > crows["previous_pair_score"]
    assert payload["post_outcome_matrix_status"] == CROWS_CLOSE_GAP_BUT_NEED_MORE_SAMPLES


def test_tiny_live_distance_reports_funding_and_evidence_blocked(tmp_path: Path) -> None:
    _write_r195_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_outcome_feedback(log_dir=tmp_path / "logs", now=NOW)
    distance = payload["tiny_live_distance_after_outcome_feedback"]

    assert distance["distance"] == NOT_CLOSE_FUNDING_AND_EVIDENCE_BLOCKED
    assert distance["funding_status"] == "ACCOUNT_NOT_FUNDED"
    assert distance["available_balance_usdt"] == 0.0
    assert distance["fresh_capture_count"] == 3
    assert distance["required_fresh_capture_count"] == 10
    assert distance["risk_contract_applied"] is False
    assert distance["lane_mode"] == "paper"
    assert distance["operator_approval"] is False
    assert distance["live_flags_armed"] is False


def test_remaining_blockers_include_required_items(tmp_path: Path) -> None:
    _write_r195_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_outcome_feedback(log_dir=tmp_path / "logs", now=NOW)

    assert payload["remaining_tiny_live_blockers"] == [
        "funding",
        "fresh captures 10/10",
        "risk contract",
        "lane mode",
        "operator approval",
        "live flags",
    ]


def test_no_live_authorization_no_origin_or_lane_promotion(tmp_path: Path) -> None:
    _write_r195_inputs(tmp_path / "logs")

    payload = build_lane_matrix_after_crow_outcome_feedback(log_dir=tmp_path / "logs", now=NOW)

    assert payload["recommendations"]["continue_crow_paper_tracking"] is True
    assert payload["recommendations"]["no_live_authorization"] is True
    assert payload["post_outcome_pair_comparison"]["hammer_wick_reversal"]["live_authorized"] is False
    assert payload["post_outcome_pair_comparison"]["three_black_crows"]["live_authorized"] is False
    assert payload["safety"]["live_authorization_created"] is False
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False


def test_no_env_config_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    config_path = tmp_path / "lane_controls.json"
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    _write_r195_inputs(log_dir)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_lane_matrix_after_crow_outcome_feedback(log_dir=log_dir, now=NOW)

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
    _write_r195_inputs(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "lane-matrix-after-crow-outcome-feedback",
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
    assert "post_outcome_pair_comparison" in payload
    assert "lane-matrix-after-crow-outcome-feedback" in help_result.stdout


def _write_r195_inputs(log_dir: Path) -> None:
    _append_json(
        log_dir / "lane_matrix_after_crow_rescoring.ndjson",
        {
            "event_type": "LANE_MATRIX_AFTER_CROW_RESCORING",
            "status": "LANE_MATRIX_AFTER_CROW_RESCORING_RECORDED",
            "target_context": {
                "primary_lane": LANE,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
            },
            "pair_comparison": {
                "hammer_wick_reversal": {
                    "lane_key": LANE,
                    "signal_origin": "hammer_wick_reversal",
                    "lane_score": 63,
                    "origin_keter_score": 82,
                    "pair_score": 72,
                    "pair_readiness": "PAIR_READY_FOR_PAPER_TRACKING",
                    "fresh_capture_count": 3,
                    "required_fresh_capture_count": 10,
                    "threshold_met": False,
                    "tagged_record_count_for_lane": 116,
                    "paper_only": True,
                    "live_authorized": False,
                },
                "three_black_crows": {
                    "lane_key": LANE,
                    "signal_origin": "three_black_crows",
                    "lane_score": 63,
                    "origin_keter_score": 56,
                    "pair_score": 51,
                    "pair_readiness": "PAIR_NEEDS_PAPER_OUTCOME_MAPPING",
                    "fresh_capture_count": 3,
                    "required_fresh_capture_count": 10,
                    "threshold_met": False,
                    "tagged_record_count_for_lane": 23,
                    "strict_detections_found": 5,
                    "loose_detections_found": 18,
                    "paper_tags_found": 23,
                    "detection_records_found": 23,
                    "needs_paper_outcome_mapping": True,
                    "paper_only": True,
                    "live_authorized": False,
                    "blockers": [
                        "no live authorization in R184",
                        "fresh capture count below threshold",
                        "paper outcome mapping required before promotion review",
                    ],
                },
            },
            "current_best_pair": {
                "lane_key": LANE,
                "signal_origin": "hammer_wick_reversal",
                "pair_score": 72,
                "paper_only": True,
                "live_authorized": False,
            },
            "post_crow_matrix_status": "HAMMER_REMAINS_CURRENT_BEST_PAIR",
        },
    )
    _append_json(
        log_dir / "crow_outcome_keter_feedback.ndjson",
        {
            "event_type": "CROW_OUTCOME_KETER_FEEDBACK",
            "status": "CROW_OUTCOME_KETER_FEEDBACK_RECORDED",
            "target_context": {
                "signal_origin": "three_black_crows",
                "primary_lane": LANE,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
            },
            "input_outcome_mapping": {
                "mapping_found": True,
                "mapped_count": 23,
                "best_window": "10",
                "supports_short_bias": True,
                "paper_tracking_recommended": True,
                "needs_more_samples": True,
                "live_ready": False,
            },
            "crow_outcome_feedback_score": {
                "outcome_score": 100,
                "confidence": "LOW",
            },
            "updated_crow_keter_projection": {
                "previous_keter_score": 56,
                "projected_keter_score_after_outcome": 69,
                "projected_readiness": "CROW_OUTCOME_NEEDS_MORE_SAMPLES",
                "paper_only": True,
                "live_authorized": False,
                "signal_origin_promoted": False,
            },
            "comparison_to_hammer": {
                "hammer_keter_score": 82,
                "projected_crow_keter_score": 69,
                "hammer_still_best_origin": True,
            },
        },
    )
    _append_json(
        log_dir / "funding_gate_role_specific_sync.ndjson",
        {
            "event_type": "FUNDING_GATE_ROLE_SPECIFIC_SYNC",
            "status": "FUNDING_GATE_ROLE_SPECIFIC_SYNC_BLOCKED",
            "latest_balance_state": {
                "record_found": True,
                "balance_readiness": "ACCOUNT_NOT_FUNDED",
                "available_balance_usdt": 0.0,
                "funding_ready": False,
            },
            "funding_gate": {
                "funding_sync_status": "FUNDING_SYNC_ACCOUNT_NOT_FUNDED",
                "funding_ready": False,
                "safe_to_arm_live": False,
            },
        },
    )


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
