from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.crow_outcome_keter_feedback import (
    CONFIRM_CROW_OUTCOME_KETER_FEEDBACK_RECORDING_PHRASE,
    CROW_OUTCOME_KETER_FEEDBACK_BLOCKED,
    CROW_OUTCOME_KETER_FEEDBACK_RECORDED,
    CROW_OUTCOME_KETER_FEEDBACK_REJECTED,
    CROW_OUTCOME_NEEDS_MORE_SAMPLES,
    LEDGER_FILENAME,
    build_crow_outcome_keter_feedback,
    build_crow_outcome_quality_dimensions,
    build_updated_crow_keter_projection,
    compute_crow_outcome_feedback_score,
    load_crow_outcome_keter_feedback_records,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
LANE = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_r194_inputs(tmp_path / "logs")

    payload = build_crow_outcome_keter_feedback(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_feedback_requested"] is False
    assert payload["feedback_recorded"] is False
    assert payload["feedback_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_r194_inputs(tmp_path / "logs")

    payload = build_crow_outcome_keter_feedback(
        log_dir=tmp_path / "logs",
        record_feedback=True,
        confirm_crow_outcome_keter_feedback="wrong",
        now=NOW,
    )

    assert payload["status"] == CROW_OUTCOME_KETER_FEEDBACK_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["feedback_recorded"] is False
    assert load_crow_outcome_keter_feedback_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_feedback_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_r194_inputs(log_dir)
    before_env = dict(os.environ)

    payload = build_crow_outcome_keter_feedback(
        log_dir=log_dir,
        record_feedback=True,
        confirm_crow_outcome_keter_feedback=CONFIRM_CROW_OUTCOME_KETER_FEEDBACK_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_crow_outcome_keter_feedback_records(log_dir=log_dir, limit=0)

    assert payload["status"] == CROW_OUTCOME_KETER_FEEDBACK_RECORDED
    assert payload["feedback_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "CROW_OUTCOME_KETER_FEEDBACK"
    assert records[0]["safety"]["config_written"] is False
    assert records[0]["safety"]["order_placed"] is False
    assert before_env == dict(os.environ)


def test_missing_outcome_mapping_blocks(tmp_path: Path) -> None:
    _write_r191_rescore(tmp_path / "logs")

    payload = build_crow_outcome_keter_feedback(
        log_dir=tmp_path / "logs",
        record_feedback=True,
        confirm_crow_outcome_keter_feedback=CONFIRM_CROW_OUTCOME_KETER_FEEDBACK_RECORDING_PHRASE,
        now=NOW,
    )

    assert payload["status"] == CROW_OUTCOME_KETER_FEEDBACK_BLOCKED
    assert payload["input_outcome_mapping"]["mapping_found"] is False
    assert payload["feedback_recorded"] is False


def test_favorable_short_outcome_increases_projected_score(tmp_path: Path) -> None:
    _write_r194_inputs(tmp_path / "logs")

    payload = build_crow_outcome_keter_feedback(log_dir=tmp_path / "logs", now=NOW)

    assert payload["input_outcome_mapping"]["mapped_count"] == 23
    assert payload["crow_outcome_feedback_score"]["outcome_score"] > 50
    assert payload["updated_crow_keter_projection"]["previous_keter_score"] == 56
    assert payload["updated_crow_keter_projection"]["projected_keter_score_after_outcome"] > 56
    assert payload["feedback_status"] == CROW_OUTCOME_NEEDS_MORE_SAMPLES


def test_high_failure_rate_creates_risk_warning(tmp_path: Path) -> None:
    _write_r194_inputs(tmp_path / "logs", failure_rate=91.0)

    payload = build_crow_outcome_keter_feedback(log_dir=tmp_path / "logs", now=NOW)

    assert payload["outcome_quality_dimensions"]["risk_warning"] == "HIGH_SIMPLE_FAILURE_RATE_REVIEW_REQUIRED"
    assert "failure rate" in payload["crow_outcome_feedback_score"]["why"]


def test_needs_more_samples_caps_confidence(tmp_path: Path) -> None:
    _write_r194_inputs(tmp_path / "logs", mapped_count=23, needs_more_samples=True)

    payload = build_crow_outcome_keter_feedback(log_dir=tmp_path / "logs", now=NOW)

    assert payload["outcome_quality_dimensions"]["sample_confidence"] == "LOW"
    assert payload["crow_outcome_feedback_score"]["confidence"] == "LOW"
    assert payload["updated_crow_keter_projection"]["projected_keter_score_after_outcome"] <= 69


def test_projected_score_does_not_write_scoring_config() -> None:
    feedback = compute_crow_outcome_feedback_score(
        input_mapping={
            "mapping_found": True,
            "mapped_count": 80,
            "supports_short_bias": True,
        },
        quality_dimensions={
            "favorable_close_rate_pct": 75.0,
            "simple_success_rate_pct": 80.0,
            "simple_failure_rate_pct": 20.0,
            "avg_close_return_pct": -0.2,
            "avg_mfe_downside_pct": 0.8,
            "avg_mae_upside_pct": 0.2,
            "sample_confidence": "HIGH",
        },
    )
    projection = build_updated_crow_keter_projection(previous_keter_score=56, outcome_feedback_score=feedback)

    assert projection["projected_keter_score_after_outcome"] > 56
    assert projection["write_scoring_now"] is False
    assert projection["paper_only"] is True


def test_live_authorized_false_signal_origin_and_lane_not_promoted(tmp_path: Path) -> None:
    _write_r194_inputs(tmp_path / "logs")

    payload = build_crow_outcome_keter_feedback(log_dir=tmp_path / "logs", now=NOW)

    projection = payload["updated_crow_keter_projection"]
    assert projection["live_authorized"] is False
    assert projection["signal_origin_promoted"] is False
    assert payload["safety"]["live_authorization_created"] is False
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False


def test_no_env_config_mutation(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = tmp_path / "lane_controls.json"
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    _write_r194_inputs(log_dir)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_crow_outcome_keter_feedback(log_dir=log_dir, now=NOW)

    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["scoring_config_written"] is False
    assert payload["safety"]["matrix_config_written"] is False


def test_no_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_r194_inputs(tmp_path / "logs")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_crow_outcome_keter_feedback(log_dir=tmp_path / "logs", now=NOW)

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
    _write_r194_inputs(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "crow-outcome-keter-feedback",
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
    assert "crow_outcome_feedback_score" in payload
    assert "crow-outcome-keter-feedback" in help_result.stdout


def test_quality_dimensions_extract_best_window_stats() -> None:
    input_mapping = {"mapping_found": True, "mapped_count": 30, "best_window": "10"}
    quality = build_crow_outcome_quality_dimensions(
        input_mapping=input_mapping,
        outcome_mapping={
            "aggregate_summary": {
                "best_window": "10",
                "window_stats": {
                    "10": {
                        "mapped_count": 30,
                        "favorable_close_rate_pct": 78.26,
                        "simple_success_rate_pct": 95.65,
                        "simple_failure_rate_pct": 12.0,
                        "avg_close_return_pct": -0.098776,
                        "avg_mfe_downside_pct": 0.744359,
                        "avg_mae_upside_pct": 0.51241,
                    }
                },
            }
        },
    )

    assert quality["best_window"] == "10"
    assert quality["sample_confidence"] == "MEDIUM"
    assert quality["avg_close_return_pct"] == -0.098776


def _write_r194_inputs(
    log_dir: Path,
    *,
    mapped_count: int = 23,
    failure_rate: float = 95.652174,
    needs_more_samples: bool = True,
) -> None:
    _write_r193_mapping(log_dir, mapped_count=mapped_count, failure_rate=failure_rate, needs_more_samples=needs_more_samples)
    _write_r191_rescore(log_dir)


def _write_r193_mapping(log_dir: Path, *, mapped_count: int, failure_rate: float, needs_more_samples: bool) -> None:
    _append_json(
        log_dir / "crow_outcome_mapping_preview.ndjson",
        {
            "event_type": "CROW_OUTCOME_MAPPING_PREVIEW",
            "mapping_id": "r193-mapping",
            "status": "CROW_OUTCOME_MAPPING_PREVIEW_RECORDED",
            "target_context": _target_context(),
            "input_summary": {"valid_detections_mapped": mapped_count},
            "aggregate_summary": {
                "mapped_count": mapped_count,
                "strict_mapped_count": 5,
                "loose_mapped_count": max(0, mapped_count - 5),
                "best_window": "10",
                "window_stats": {
                    "10": {
                        "mapped_count": mapped_count,
                        "favorable_close_rate_pct": 78.26087,
                        "simple_success_rate_pct": 95.652174,
                        "simple_failure_rate_pct": failure_rate,
                        "avg_close_return_pct": -0.098776,
                        "avg_mfe_downside_pct": 0.744359,
                        "avg_mae_upside_pct": 0.51241,
                    }
                },
            },
            "outcome_mapping_status": "OUTCOME_MAPPING_AVAILABLE",
            "interpretation": {
                "supports_short_bias": True,
                "paper_tracking_recommended": True,
                "needs_more_samples": needs_more_samples,
                "live_ready": False,
            },
            "safety": {"order_placed": False, "real_order_placed": False},
        },
    )


def _write_r191_rescore(log_dir: Path) -> None:
    _append_json(
        log_dir / "keter_rescore_after_three_black_crows.ndjson",
        {
            "event_type": "KETER_RESCORING_AFTER_THREE_BLACK_CROWS",
            "status": "KETER_RESCORING_AFTER_CROWS_RECORDED",
            "target_context": _target_context(),
            "three_black_crows_rescore": {
                "previous_keter_score": 0,
                "new_keter_score": 56,
                "readiness": "CROWS_READY_FOR_PAPER_TRACKING_REVIEW",
                "paper_only": True,
                "live_authorized": False,
                "signal_origin_promoted": False,
            },
            "comparison_to_hammer": {
                "hammer_keter_score": 82,
                "three_black_crows_keter_score": 56,
                "hammer_still_best_origin": True,
            },
            "safety": {"order_placed": False, "real_order_placed": False},
        },
    )


def _target_context() -> dict[str, object]:
    return {
        "signal_origin": "three_black_crows",
        "primary_lane": LANE,
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
    }


def _append_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
