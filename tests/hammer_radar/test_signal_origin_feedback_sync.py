from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.signal_origin_feedback_sync import (
    CONFIRM_SIGNAL_ORIGIN_FEEDBACK_SYNC_RECORDING_PHRASE,
    DETECTOR_EVIDENCE_AVAILABLE_REVIEW_REQUIRED,
    LEDGER_FILENAME,
    NO_DETECTION_RECORDS_FOUND,
    PAPER_TAGS_FOUND,
    READY_TO_RERUN_KETER_AND_MATRIX,
    SIGNAL_ORIGIN_FEEDBACK_SYNC_BLOCKED,
    SIGNAL_ORIGIN_FEEDBACK_SYNC_RECORDED,
    SIGNAL_ORIGIN_FEEDBACK_SYNC_REJECTED,
    build_signal_origin_feedback_sync_after_three_black_crows,
    load_signal_origin_feedback_sync_records,
)

NOW = datetime(2026, 6, 4, 12, 0, tzinfo=UTC)
LANE = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_r189_ledgers(tmp_path / "logs")

    payload = build_signal_origin_feedback_sync_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_feedback_requested"] is False
    assert payload["feedback_recorded"] is False
    assert payload["feedback_id"] is None
    assert payload["feedback_status"] == READY_TO_RERUN_KETER_AND_MATRIX
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_r189_ledgers(tmp_path / "logs")

    payload = build_signal_origin_feedback_sync_after_three_black_crows(
        log_dir=tmp_path / "logs",
        record_feedback=True,
        confirm_signal_origin_feedback_sync="wrong",
        now=NOW,
    )

    assert payload["status"] == SIGNAL_ORIGIN_FEEDBACK_SYNC_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["feedback_recorded"] is False
    assert load_signal_origin_feedback_sync_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_feedback_only(tmp_path: Path) -> None:
    _write_r189_ledgers(tmp_path / "logs")
    before_env = dict(os.environ)

    payload = build_signal_origin_feedback_sync_after_three_black_crows(
        log_dir=tmp_path / "logs",
        record_feedback=True,
        confirm_signal_origin_feedback_sync=CONFIRM_SIGNAL_ORIGIN_FEEDBACK_SYNC_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_signal_origin_feedback_sync_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == SIGNAL_ORIGIN_FEEDBACK_SYNC_RECORDED
    assert payload["feedback_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "SIGNAL_ORIGIN_FEEDBACK_SYNC"
    assert records[0]["registry_feedback"]["write_registry_now"] is False
    assert records[0]["keter_feedback"]["write_scoring_now"] is False
    assert records[0]["lane_matrix_feedback"]["write_matrix_now"] is False
    assert before_env == dict(os.environ)


def test_detection_records_found_produces_detector_evidence_available(tmp_path: Path) -> None:
    _write_r189_ledgers(tmp_path / "logs")

    payload = build_signal_origin_feedback_sync_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)
    summary = payload["three_black_crows_feedback_summary"]

    assert summary["detection_records_found"] == 3
    assert summary["strict_detections_found"] == 1
    assert summary["loose_detections_found"] == 2
    assert summary["latest_detection_at"] == "2026-06-04T07:19:59.999000+00:00"
    assert summary["local_detector_available"] is True
    assert DETECTOR_EVIDENCE_AVAILABLE_REVIEW_REQUIRED in payload["feedback_statuses"]


def test_paper_tags_found_are_counted(tmp_path: Path) -> None:
    _write_r189_ledgers(tmp_path / "logs")

    payload = build_signal_origin_feedback_sync_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)
    summary = payload["three_black_crows_feedback_summary"]

    assert summary["paper_tags_found"] == 3
    assert summary["latest_tag_at"] == "2026-06-04T07:19:59.999000+00:00"
    assert PAPER_TAGS_FOUND in payload["feedback_statuses"]


def test_missing_detections_blocks(tmp_path: Path) -> None:
    _write_tag(
        tmp_path / "logs" / "three_black_crows_paper_tags.ndjson",
        tag_id="tag-only",
        detected_at="2026-06-04T07:19:59.999000+00:00",
    )

    payload = build_signal_origin_feedback_sync_after_three_black_crows(
        log_dir=tmp_path / "logs",
        record_feedback=True,
        confirm_signal_origin_feedback_sync=CONFIRM_SIGNAL_ORIGIN_FEEDBACK_SYNC_RECORDING_PHRASE,
        now=NOW,
    )

    assert payload["status"] == SIGNAL_ORIGIN_FEEDBACK_SYNC_BLOCKED
    assert payload["feedback_status"] == NO_DETECTION_RECORDS_FOUND
    assert payload["feedback_recorded"] is False
    assert payload["blockers"] == [NO_DETECTION_RECORDS_FOUND]
    assert load_signal_origin_feedback_sync_records(log_dir=tmp_path / "logs", limit=0) == []


def test_registry_feedback_does_not_write_config_or_promote(tmp_path: Path) -> None:
    _write_r189_ledgers(tmp_path / "logs")

    payload = build_signal_origin_feedback_sync_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)
    registry_feedback = payload["registry_feedback"]

    assert registry_feedback["previous_availability"] == "REGISTRY_ONLY"
    assert registry_feedback["recommended_future_availability"] == "DETECTOR_AVAILABLE_AFTER_REVIEW"
    assert registry_feedback["write_registry_now"] is False
    assert registry_feedback["requires_review"] is True
    assert registry_feedback["signal_origin_promoted"] is False
    assert payload["safety"]["registry_config_written"] is False
    assert payload["safety"]["signal_origin_promoted"] is False


def test_signal_origin_and_lane_are_not_promoted(tmp_path: Path) -> None:
    _write_r189_ledgers(tmp_path / "logs")

    payload = build_signal_origin_feedback_sync_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)

    assert payload["three_black_crows_feedback_summary"]["live_authorized"] is False
    assert payload["three_black_crows_feedback_summary"]["signal_origin_promoted"] is False
    assert payload["three_black_crows_feedback_summary"]["lane_promoted"] is False
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False


def test_recommends_rerun_keter_and_matrix(tmp_path: Path) -> None:
    _write_r189_ledgers(tmp_path / "logs")

    payload = build_signal_origin_feedback_sync_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)

    assert payload["keter_feedback"]["rerun_keter_scoring_recommended"] is True
    assert payload["lane_matrix_feedback"]["rerun_lane_matrix_recommended"] is True
    assert payload["recommended_next_operator_move"] == "RUN_R191_KETER_RESCORING_AFTER_THREE_BLACK_CROWS"


def test_no_env_config_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_r189_ledgers(tmp_path / "logs")
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
        payload = build_signal_origin_feedback_sync_after_three_black_crows(log_dir=tmp_path / "logs", now=NOW)

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
    _write_r189_ledgers(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "signal-origin-feedback-sync",
            "--signal-origin",
            "three_black_crows",
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
    assert payload["target_context"]["signal_origin"] == "three_black_crows"
    assert payload["target_context"]["primary_lane"] == LANE
    assert "signal-origin-feedback-sync" in help_result.stdout


def _write_r189_ledgers(log_dir: Path) -> None:
    detection_path = log_dir / "three_black_crows_local_detections.ndjson"
    tag_path = log_dir / "three_black_crows_paper_tags.ndjson"
    _append_json(
        detection_path,
        {
            "event_type": "THREE_BLACK_CROWS_LOCAL_DETECTION",
            "detection_id": "r189-record-1",
            "target_context": {
                "signal_origin": "three_black_crows",
                "primary_lane": LANE,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
            },
            "detections": [
                _detection("strict-1", "strict", "2026-06-04T07:03:59.999000+00:00"),
                _detection("loose-1", "loose_preview", "2026-06-04T07:11:59.999000+00:00"),
                _detection("loose-2", "loose_preview", "2026-06-04T07:19:59.999000+00:00"),
            ],
            "detector_result": {
                "strict_detections_found": 1,
                "loose_detections_found": 2,
                "latest_detection_at": "2026-06-04T07:19:59.999000+00:00",
                "paper_only": True,
                "live_authorized": False,
            },
            "safety": {"order_placed": False, "real_order_placed": False},
        },
    )
    _write_tag(tag_path, tag_id="tag-1", detection_id="strict-1", mode="strict", detected_at="2026-06-04T07:03:59.999000+00:00")
    _write_tag(tag_path, tag_id="tag-2", detection_id="loose-1", detected_at="2026-06-04T07:11:59.999000+00:00")
    _write_tag(tag_path, tag_id="tag-3", detection_id="loose-2", detected_at="2026-06-04T07:19:59.999000+00:00")


def _detection(detection_id: str, mode: str, detected_at: str) -> dict:
    return {
        "detection_id": detection_id,
        "signal_origin": "three_black_crows",
        "lane_key": LANE,
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "mode": mode,
        "detected_at": detected_at,
        "paper_only": True,
        "live_authorized": False,
        "signal_origin_promoted": False,
        "lane_promoted": False,
    }


def _write_tag(
    path: Path,
    *,
    tag_id: str,
    detected_at: str,
    detection_id: str | None = None,
    mode: str = "loose_preview",
) -> None:
    _append_json(
        path,
        {
            "event_type": "THREE_BLACK_CROWS_PAPER_TAG",
            "tag_id": tag_id,
            "detection_id": detection_id or tag_id,
            "signal_origin": "three_black_crows",
            "lane_key": LANE,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "mode": mode,
            "detected_at": detected_at,
            "paper_only": True,
            "live_authorized": False,
            "signal_origin_promoted": False,
            "lane_promoted": False,
        },
    )


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
