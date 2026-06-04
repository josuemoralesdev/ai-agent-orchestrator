from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.signal_origin_lane_matrix import (
    CONFIRM_SIGNAL_ORIGIN_LANE_MATRIX_RECORDING_PHRASE,
    LEDGER_FILENAME,
    PAIR_NEEDS_DETECTOR,
    PAIR_READY_FOR_PAPER_TRACKING,
    PAIR_REFERENCE_ONLY,
    SIGNAL_ORIGIN_LANE_MATRIX_RECORDED,
    SIGNAL_ORIGIN_LANE_MATRIX_REJECTED,
    build_signal_origin_lane_matrix,
    load_signal_origin_lane_matrix_records,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
LANE_4M_LONG = "BTCUSDT|4m|long|ladder_close_50_618"
LANE_13M_LONG = "BTCUSDT|13m|long|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_matrix_inputs(tmp_path / "logs")

    payload = build_signal_origin_lane_matrix(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_matrix_requested"] is False
    assert payload["matrix_recorded"] is False
    assert payload["matrix_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_matrix_inputs(tmp_path / "logs")

    payload = build_signal_origin_lane_matrix(
        log_dir=tmp_path / "logs",
        record_matrix=True,
        confirm_signal_origin_lane_matrix="wrong",
        now=NOW,
    )

    assert payload["status"] == SIGNAL_ORIGIN_LANE_MATRIX_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["matrix_recorded"] is False
    assert load_signal_origin_lane_matrix_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_matrix_inputs(log_dir)
    before_env = dict(os.environ)

    payload = build_signal_origin_lane_matrix(
        log_dir=log_dir,
        record_matrix=True,
        confirm_signal_origin_lane_matrix=CONFIRM_SIGNAL_ORIGIN_LANE_MATRIX_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_signal_origin_lane_matrix_records(log_dir=log_dir, limit=0)

    assert payload["status"] == SIGNAL_ORIGIN_LANE_MATRIX_RECORDED
    assert payload["matrix_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "SIGNAL_ORIGIN_LANE_MATRIX"
    assert before_env == dict(os.environ)


def test_8m_short_hammer_can_become_current_best_pair_when_scores_lead(tmp_path: Path) -> None:
    _write_matrix_inputs(tmp_path / "logs")

    payload = build_signal_origin_lane_matrix(log_dir=tmp_path / "logs", now=NOW)

    assert payload["current_best_pair"]["lane_key"] == LANE_8M_SHORT
    assert payload["current_best_pair"]["signal_origin"] == "hammer_wick_reversal"
    row = _pair(payload, LANE_8M_SHORT, "hammer_wick_reversal")
    assert row["pair_readiness"] == PAIR_READY_FOR_PAPER_TRACKING
    assert row["pair_score"] > _pair(payload, LANE_4M_LONG, "hammer_wick_reversal")["pair_score"]


def test_three_black_crows_for_8m_short_is_detector_priority_not_ready_pair(tmp_path: Path) -> None:
    _write_matrix_inputs(tmp_path / "logs")

    payload = build_signal_origin_lane_matrix(log_dir=tmp_path / "logs", now=NOW)
    crows = _pair(payload, LANE_8M_SHORT, "three_black_crows")

    assert crows["pair_readiness"] == PAIR_NEEDS_DETECTOR
    assert crows["pair_score"] < _pair(payload, LANE_8M_SHORT, "hammer_wick_reversal")["pair_score"]
    priorities = {(row["lane_key"], row["signal_origin"]): row for row in payload["detector_priority_pairs"]}
    assert priorities[(LANE_8M_SHORT, "three_black_crows")]["priority"] == "HIGH"
    assert "detector missing" in priorities[(LANE_8M_SHORT, "three_black_crows")]["why"]


def test_registry_only_origins_are_penalized(tmp_path: Path) -> None:
    _write_matrix_inputs(tmp_path / "logs")

    payload = build_signal_origin_lane_matrix(log_dir=tmp_path / "logs", now=NOW)
    crows = _pair(payload, LANE_8M_SHORT, "three_black_crows")

    assert crows["origin_availability"] == "REGISTRY_ONLY"
    assert crows["pair_score"] <= 49
    assert "registry-only origins cannot be trade-ready" in " ".join(crows["blockers"])


def test_reference_only_tiny_live_lanes_cannot_become_new_paper_candidate_door(tmp_path: Path) -> None:
    _write_matrix_inputs(tmp_path / "logs", reference_lane_score=95, reference_hammer_count=200)

    payload = build_signal_origin_lane_matrix(log_dir=tmp_path / "logs", now=NOW)
    reference = _pair(payload, LANE_13M_LONG, "hammer_wick_reversal")

    assert reference["reference_only"] is True
    assert reference["pair_readiness"] == PAIR_REFERENCE_ONLY
    assert reference["pair_score"] <= 69
    assert payload["current_best_pair"]["lane_key"] != LANE_13M_LONG


def test_pair_score_includes_lane_and_origin_inputs(tmp_path: Path) -> None:
    _write_matrix_inputs(tmp_path / "logs", hammer_score=82)

    payload = build_signal_origin_lane_matrix(log_dir=tmp_path / "logs", now=NOW)
    row = _pair(payload, LANE_8M_SHORT, "hammer_wick_reversal")

    assert row["score_inputs"]["lane_score"] == 59
    assert row["score_inputs"]["origin_keter_score"] == 82
    assert row["score_inputs"]["tagged_density_score"] == 100
    assert row["score_inputs"]["threshold_progress_score"] == 30
    assert row["pair_score"] >= 50


def test_no_pair_is_live_authorized_and_nothing_promoted(tmp_path: Path) -> None:
    _write_matrix_inputs(tmp_path / "logs")

    payload = build_signal_origin_lane_matrix(log_dir=tmp_path / "logs", now=NOW)

    assert all(row["live_authorized"] is False for row in payload["lane_origin_matrix"])
    assert all(row["lane_promoted"] is False for row in payload["lane_origin_matrix"])
    assert all(row["signal_origin_promoted"] is False for row in payload["lane_origin_matrix"])
    assert payload["safety"]["lane_promoted"] is False
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["live_authorization_created"] is False


def test_no_env_config_mutation_no_binance_calls_and_no_order_live_transfer_withdraw(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = tmp_path / "logs"
    config_path = tmp_path / "lane_controls.json"
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    _write_matrix_inputs(log_dir)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_signal_origin_lane_matrix(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    safety = payload["safety"]
    for key, value in safety.items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_cli_exists(tmp_path: Path) -> None:
    _write_matrix_inputs(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "signal-origin-lane-matrix",
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
    assert "lane_origin_matrix" in payload
    assert "current_best_pair" in payload
    assert "signal-origin-lane-matrix" in help_result.stdout


def _write_matrix_inputs(
    log_dir: Path,
    *,
    hammer_score: int = 82,
    reference_lane_score: int = 56,
    reference_hammer_count: int = 20,
) -> None:
    _append_json(
        log_dir / "multi_lane_evidence_rankings.ndjson",
        {
            "event_type": "MULTI_LANE_EVIDENCE_RANKING",
            "status": "MULTI_LANE_EVIDENCE_RANKING_RECORDED",
            "ranked_lanes": [
                {
                    "lane_key": LANE_8M_SHORT,
                    "mode": "paper",
                    "fresh_capture_count": 3,
                    "fresh_threshold_required": 10,
                    "fresh_threshold_met": False,
                    "score": 59,
                    "reference_only": False,
                },
                {
                    "lane_key": LANE_4M_LONG,
                    "mode": "paper",
                    "fresh_capture_count": 2,
                    "fresh_threshold_required": 10,
                    "fresh_threshold_met": False,
                    "score": 48,
                    "reference_only": False,
                },
                {
                    "lane_key": LANE_13M_LONG,
                    "mode": "tiny_live_observed_reference",
                    "fresh_capture_count": 20,
                    "fresh_threshold_required": 10,
                    "fresh_threshold_met": True,
                    "score": reference_lane_score,
                    "reference_only": True,
                },
            ],
            "next_door_selection": {
                "selected_lane": LANE_8M_SHORT,
                "selection_type": "KEEP_8M_SHORT",
                "confidence": "MEDIUM",
            },
        },
    )
    _append_json(
        log_dir / "keter_signal_origin_scoring.ndjson",
        {
            "event_type": "KETER_SIGNAL_ORIGIN_SCORING",
            "status": "KETER_SIGNAL_ORIGIN_SCORING_RECORDED",
            "keter_origin_rankings": [
                {
                    "signal_origin": "hammer_wick_reversal",
                    "availability": "DETECTOR_AVAILABLE",
                    "keter_score": hammer_score,
                    "readiness": "ORIGIN_READY_FOR_PAPER_TRACKING",
                    "tagged_record_count": 114,
                    "live_authorized": False,
                    "paper_only": True,
                },
                {
                    "signal_origin": "three_black_crows",
                    "availability": "REGISTRY_ONLY",
                    "keter_score": 28,
                    "readiness": "ORIGIN_NEEDS_DETECTOR",
                    "tagged_record_count": 0,
                    "live_authorized": False,
                    "paper_only": True,
                },
                {
                    "signal_origin": "unknown_or_unclassified",
                    "availability": "UNKNOWN",
                    "keter_score": 10,
                    "readiness": "ORIGIN_UNKNOWN",
                    "tagged_record_count": 2,
                    "live_authorized": False,
                    "paper_only": True,
                },
            ],
            "by_lane_origin_scores": {
                LANE_8M_SHORT: [
                    {"signal_origin": "hammer_wick_reversal", "keter_score": hammer_score, "tagged_record_count": 114},
                    {"signal_origin": "unknown_or_unclassified", "keter_score": 10, "tagged_record_count": 2},
                ],
                LANE_4M_LONG: [
                    {"signal_origin": "hammer_wick_reversal", "keter_score": hammer_score, "tagged_record_count": 40},
                ],
                LANE_13M_LONG: [
                    {
                        "signal_origin": "hammer_wick_reversal",
                        "keter_score": hammer_score,
                        "tagged_record_count": reference_hammer_count,
                    },
                ],
            },
            "detector_priority_recommendations": [
                {
                    "signal_origin": "three_black_crows",
                    "priority": "HIGH",
                    "reason": "operator-prioritized bearish reversal pattern but registry-only until detector exists",
                }
            ],
        },
    )


def _pair(payload: dict, lane_key: str, signal_origin: str) -> dict:
    return next(
        row
        for row in payload["lane_origin_matrix"]
        if row["lane_key"] == lane_key and row["signal_origin"] == signal_origin
    )


def _append_json(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
