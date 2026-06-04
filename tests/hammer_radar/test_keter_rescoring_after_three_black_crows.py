from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.keter_rescoring_after_three_black_crows import (
    CONFIRM_KETER_RESCORING_AFTER_CROWS_RECORDING_PHRASE,
    CROWS_READY_FOR_PAPER_TRACKING_REVIEW,
    KETER_RESCORING_AFTER_CROWS_BLOCKED,
    KETER_RESCORING_AFTER_CROWS_RECORDED,
    KETER_RESCORING_AFTER_CROWS_REJECTED,
    LEDGER_FILENAME,
    build_keter_rescoring_after_three_black_crows,
    load_keter_rescore_after_three_black_crows_records,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
LANE = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_r191_inputs(tmp_path / "logs")

    payload = build_keter_rescoring_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_rescore_requested"] is False
    assert payload["rescore_recorded"] is False
    assert payload["rescore_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_r191_inputs(tmp_path / "logs")

    payload = build_keter_rescoring_after_three_black_crows(
        log_dir=tmp_path / "logs",
        record_rescore=True,
        confirm_keter_rescore_after_crows="wrong",
        now=NOW,
    )

    assert payload["status"] == KETER_RESCORING_AFTER_CROWS_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["rescore_recorded"] is False
    assert load_keter_rescore_after_three_black_crows_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_rescore_only(tmp_path: Path) -> None:
    _write_r191_inputs(tmp_path / "logs")
    before_env = dict(os.environ)

    payload = build_keter_rescoring_after_three_black_crows(
        log_dir=tmp_path / "logs",
        record_rescore=True,
        confirm_keter_rescore_after_crows=CONFIRM_KETER_RESCORING_AFTER_CROWS_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_keter_rescore_after_three_black_crows_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == KETER_RESCORING_AFTER_CROWS_RECORDED
    assert payload["rescore_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "KETER_RESCORING_AFTER_THREE_BLACK_CROWS"
    assert records[0]["safety"]["config_written"] is False
    assert records[0]["safety"]["order_placed"] is False
    assert before_env == dict(os.environ)


def test_missing_feedback_blocks(tmp_path: Path) -> None:
    _write_r189_ledgers(tmp_path / "logs")
    _write_hammer_feed(tmp_path / "logs")

    payload = build_keter_rescoring_after_three_black_crows(
        log_dir=tmp_path / "logs",
        record_rescore=True,
        confirm_keter_rescore_after_crows=CONFIRM_KETER_RESCORING_AFTER_CROWS_RECORDING_PHRASE,
        now=NOW,
    )

    assert payload["status"] == KETER_RESCORING_AFTER_CROWS_BLOCKED
    assert payload["input_feedback"]["feedback_found"] is False
    assert payload["rescore_recorded"] is False
    assert "R190_FEEDBACK_SYNC_MISSING" in payload["blockers"]


def test_detection_evidence_increases_detector_availability_score(tmp_path: Path) -> None:
    _write_r191_inputs(tmp_path / "logs")

    payload = build_keter_rescoring_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)
    dimensions = payload["three_black_crows_rescore"]["dimension_scores"]

    assert payload["three_black_crows_rescore"]["previous_keter_score"] == 0
    assert dimensions["detector_availability_score"] > 12
    assert payload["three_black_crows_rescore"]["new_keter_score"] > 0


def test_paper_tags_influence_tagged_data_score(tmp_path: Path) -> None:
    _write_r191_inputs(tmp_path / "logs", tag_count=23)

    payload = build_keter_rescoring_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)

    assert payload["input_feedback"]["paper_tags_found"] == 23
    assert payload["three_black_crows_rescore"]["dimension_scores"]["tagged_data_score"] > 0


def test_historical_outcome_score_remains_limited_without_mapping(tmp_path: Path) -> None:
    _write_r191_inputs(tmp_path / "logs")

    payload = build_keter_rescoring_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)

    assert payload["three_black_crows_rescore"]["dimension_scores"]["historical_outcome_score"] == 0
    assert payload["recommendations"]["need_paper_outcome_mapping"] is True


def test_crows_do_not_become_live_authorized_or_promoted(tmp_path: Path) -> None:
    _write_r191_inputs(tmp_path / "logs")

    payload = build_keter_rescoring_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)
    rescore = payload["three_black_crows_rescore"]

    assert rescore["readiness"] == CROWS_READY_FOR_PAPER_TRACKING_REVIEW
    assert rescore["paper_only"] is True
    assert rescore["live_authorized"] is False
    assert rescore["signal_origin_promoted"] is False
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False


def test_recommends_lane_matrix_rerun_and_compares_to_hammer(tmp_path: Path) -> None:
    _write_r191_inputs(tmp_path / "logs")

    payload = build_keter_rescoring_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)

    assert payload["recommendations"]["rerun_lane_matrix"] is True
    assert payload["recommendations"]["paper_track_three_black_crows"] is True
    assert payload["recommended_next_operator_move"] == "RUN_R192_LANE_MATRIX_AFTER_CROW_RESCORING"
    assert payload["comparison_to_hammer"]["hammer_keter_score"] > 0
    assert payload["comparison_to_hammer"]["hammer_still_best_origin"] is True


def test_no_env_config_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_r191_inputs(tmp_path / "logs")
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
        payload = build_keter_rescoring_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)

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
    _write_r191_inputs(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "keter-rescore-after-three-black-crows",
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
    assert "keter-rescore-after-three-black-crows" in help_result.stdout


def _write_r191_inputs(log_dir: Path, *, detection_count: int = 23, tag_count: int = 23) -> None:
    _write_r189_ledgers(log_dir, detection_count=detection_count, tag_count=tag_count)
    _write_r190_feedback(log_dir, detection_count=detection_count, tag_count=tag_count)
    _write_hammer_feed(log_dir)


def _write_r190_feedback(log_dir: Path, *, detection_count: int, tag_count: int) -> None:
    _append_json(
        log_dir / "signal_origin_feedback_sync.ndjson",
        {
            "event_type": "SIGNAL_ORIGIN_FEEDBACK_SYNC",
            "feedback_id": "r190-feedback",
            "status": "SIGNAL_ORIGIN_FEEDBACK_SYNC_RECORDED",
            "feedback_status": "READY_TO_RERUN_KETER_AND_MATRIX",
            "target_context": _target_context(),
            "three_black_crows_feedback_summary": {
                "detection_records_found": detection_count,
                "paper_tags_found": tag_count,
                "strict_detections_found": 5,
                "loose_detections_found": detection_count - 5,
                "latest_detection_at": "2026-06-04T07:19:59.999000+00:00",
                "local_detector_available": True,
                "paper_only": True,
                "live_authorized": False,
                "signal_origin_promoted": False,
                "lane_promoted": False,
            },
            "registry_feedback": {
                "previous_availability": "REGISTRY_ONLY",
                "recommended_future_availability": "DETECTOR_AVAILABLE_AFTER_REVIEW",
                "write_registry_now": False,
                "signal_origin_promoted": False,
            },
            "safety": {"order_placed": False, "real_order_placed": False},
        },
    )


def _write_r189_ledgers(log_dir: Path, *, detection_count: int = 23, tag_count: int = 23) -> None:
    detections = []
    for index in range(detection_count):
        detection_id = f"detection-{index}"
        mode = "strict" if index < 5 else "loose_preview"
        detections.append(_detection(detection_id, mode))
        if index < tag_count:
            _append_json(
                log_dir / "three_black_crows_paper_tags.ndjson",
                {
                    "tag_id": f"tag-{index}",
                    "detection_id": detection_id,
                    "signal_origin": "three_black_crows",
                    "lane_key": LANE,
                    "symbol": "BTCUSDT",
                    "timeframe": "8m",
                    "direction": "short",
                    "mode": mode,
                    "detected_at": "2026-06-04T07:19:59.999000+00:00",
                    "paper_only": True,
                    "live_authorized": False,
                },
            )
    _append_json(
        log_dir / "three_black_crows_local_detections.ndjson",
        {
            "event_type": "THREE_BLACK_CROWS_LOCAL_DETECTION",
            "detection_id": "r189-record",
            "target_context": _target_context(),
            "detections": detections,
            "detector_result": {
                "strict_detections_found": 5,
                "loose_detections_found": max(0, detection_count - 5),
                "latest_detection_at": "2026-06-04T07:19:59.999000+00:00",
                "paper_only": True,
                "live_authorized": False,
            },
            "safety": {"order_placed": False, "real_order_placed": False},
        },
    )


def _write_hammer_feed(log_dir: Path) -> None:
    for index in range(6):
        _append_json(
            log_dir / "signals.ndjson",
            {
                "signal_id": f"hammer-{index}",
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "hammer_strength": 90,
                "freshness": "fresh",
            },
        )
    _append_json(
        log_dir / "multi_lane_evidence_rankings.ndjson",
        {"ranked_lanes": [{"lane_key": LANE, "score": 72}]},
    )


def _target_context() -> dict:
    return {
        "signal_origin": "three_black_crows",
        "primary_lane": LANE,
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
    }


def _detection(detection_id: str, mode: str) -> dict:
    return {
        "detection_id": detection_id,
        "signal_origin": "three_black_crows",
        "lane_key": LANE,
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "mode": mode,
        "detected_at": "2026-06-04T07:19:59.999000+00:00",
        "paper_only": True,
        "live_authorized": False,
    }


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
