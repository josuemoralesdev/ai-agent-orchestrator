from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.anchor_signal_confluence_matrix import (
    ANCHOR_SIGNAL_CONFLUENCE_MATRIX_RECORDED,
    ANCHOR_SIGNAL_CONFLUENCE_MATRIX_REJECTED,
    CONFIRM_ANCHOR_SIGNAL_CONFLUENCE_MATRIX_RECORDING_PHRASE,
    LEDGER_FILENAME,
    build_anchor_signal_confluence_matrix,
    load_anchor_signal_confluence_matrix_records,
    score_anchor_signal_confluence_row,
)

NOW = datetime(2026, 6, 5, 22, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
LANE_8M_LONG = "BTCUSDT|8m|long|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_r203_inputs(tmp_path / "logs")

    payload = build_anchor_signal_confluence_matrix(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_matrix_requested"] is False
    assert payload["matrix_recorded"] is False
    assert payload["matrix_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_r203_inputs(tmp_path / "logs")

    payload = build_anchor_signal_confluence_matrix(
        log_dir=tmp_path / "logs",
        record_matrix=True,
        confirm_anchor_signal_confluence="wrong",
        now=NOW,
    )

    assert payload["status"] == ANCHOR_SIGNAL_CONFLUENCE_MATRIX_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["matrix_recorded"] is False
    assert load_anchor_signal_confluence_matrix_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_matrix_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_r203_inputs(log_dir)
    before_env = dict(os.environ)

    payload = build_anchor_signal_confluence_matrix(
        log_dir=log_dir,
        record_matrix=True,
        confirm_anchor_signal_confluence=CONFIRM_ANCHOR_SIGNAL_CONFLUENCE_MATRIX_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_anchor_signal_confluence_matrix_records(log_dir=log_dir, limit=0)

    assert payload["status"] == ANCHOR_SIGNAL_CONFLUENCE_MATRIX_RECORDED
    assert payload["matrix_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "ANCHOR_SIGNAL_CONFLUENCE_MATRIX"
    assert before_env == dict(os.environ)


def test_summary_level_confluence_is_penalized_versus_event_level() -> None:
    event_level = score_anchor_signal_confluence_row(
        signal_origin_score=82,
        anchor_score=22,
        lane_score=63,
        sample_confidence="HIGH",
        confluence_resolution="event_level",
        direction_alignment=True,
        configured_lane=True,
        fresh_flow="fresh",
    )
    summary_level = score_anchor_signal_confluence_row(
        signal_origin_score=82,
        anchor_score=22,
        lane_score=63,
        sample_confidence="HIGH",
        confluence_resolution="summary_level",
        direction_alignment=True,
        configured_lane=True,
        fresh_flow="fresh",
    )

    assert summary_level < event_level


def test_risk_stale_direction_and_blocked_penalties_reduce_score() -> None:
    clean = score_anchor_signal_confluence_row(
        signal_origin_score=82,
        anchor_score=22,
        lane_score=63,
        sample_confidence="HIGH",
        confluence_resolution="event_level",
        direction_alignment=True,
        configured_lane=True,
        fresh_flow="fresh",
    )
    risky = score_anchor_signal_confluence_row(
        signal_origin_score=82,
        anchor_score=22,
        lane_score=63,
        sample_confidence="HIGH",
        confluence_resolution="event_level",
        direction_alignment=True,
        risk_warnings=["VERY_HIGH_FAILURE_RATE", "average_adverse_exceeds_average_favorable"],
        configured_lane=True,
        fresh_flow="fresh",
    )
    stale = score_anchor_signal_confluence_row(
        signal_origin_score=82,
        anchor_score=22,
        lane_score=63,
        sample_confidence="HIGH",
        confluence_resolution="event_level",
        direction_alignment=True,
        configured_lane=True,
        fresh_flow="stale_only",
    )
    mismatch = score_anchor_signal_confluence_row(
        signal_origin_score=82,
        anchor_score=22,
        lane_score=63,
        sample_confidence="HIGH",
        confluence_resolution="event_level",
        direction_alignment=False,
        configured_lane=True,
        fresh_flow="fresh",
    )
    blocked = score_anchor_signal_confluence_row(
        signal_origin_score=82,
        anchor_score=22,
        lane_score=63,
        sample_confidence="HIGH",
        confluence_resolution="event_level",
        direction_alignment=True,
        configured_lane=True,
        fresh_flow="fresh",
        blocked_origin=True,
    )

    assert risky < clean
    assert stale < clean
    assert mismatch < clean
    assert blocked < clean


def test_blocked_origins_are_marked_blocked(tmp_path: Path) -> None:
    _write_r203_inputs(tmp_path / "logs")

    payload = build_anchor_signal_confluence_matrix(log_dir=tmp_path / "logs", now=NOW)
    blocked = [row for row in payload["anchor_signal_confluence_rows"] if row["signal_origin"] == "breakdown_retest"]

    assert blocked
    assert all(row["confluence_resolution"] == "none" for row in blocked)
    assert all(row["live_authorized"] is False for row in blocked)


def test_no_live_authorization_or_mutations(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_r203_inputs(log_dir)
    before_env = dict(os.environ)

    payload = build_anchor_signal_confluence_matrix(log_dir=log_dir, now=NOW)

    assert before_env == dict(os.environ)
    assert payload["target_scope"]["paper_only"] is True
    assert payload["target_scope"]["live_authorized"] is False
    assert all(row["live_authorized"] is False for row in payload["anchor_signal_confluence_rows"])
    assert all(row["confluence_live_authorized"] is False for row in payload["anchor_signal_confluence_rows"])
    assert all(row["position_permission_created"] is False for row in payload["anchor_signal_confluence_rows"])
    assert all(row["signal_origin_promoted"] is False for row in payload["anchor_signal_confluence_rows"])
    assert all(row["lane_promoted"] is False for row in payload["anchor_signal_confluence_rows"])
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_no_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_r203_inputs(tmp_path / "logs")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_anchor_signal_confluence_matrix(log_dir=tmp_path / "logs", now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert payload["safety"]["network_allowed"] is False
    assert payload["safety"]["order_placed"] is False
    assert payload["safety"]["transfer_endpoint_called"] is False
    assert payload["safety"]["withdraw_endpoint_called"] is False


def test_cli_exists(tmp_path: Path) -> None:
    _write_r203_inputs(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "anchor-signal-confluence-matrix",
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
    assert "anchor_signal_confluence_rows" in payload
    assert "anchor-signal-confluence-matrix" in help_result.stdout


def _write_r203_inputs(log_dir: Path) -> None:
    _append_json(log_dir / "anchor_outcome_deepening.ndjson", _r201_record())
    _append_json(log_dir / "pattern_lane_matrix_review.ndjson", _r205_record())
    _append_json(log_dir / "pattern_keter_rescoring_family.ndjson", _r204_record())
    _append_json(log_dir / "lane_matrix_after_crow_outcome_feedback.ndjson", _r195_record())


def _r201_record() -> dict:
    return {
        "event_type": "ANCHOR_OUTCOME_DEEPENING",
        "status": "ANCHOR_OUTCOME_DEEPENING_RECORDED",
        "anchor_interaction_rankings": [
            _anchor("8m", "custom_wma", 21, "cross_down", "short", 21.9, []),
            _anchor("8m", "custom_wma", 89, "rejection_down", "short", 21.8, []),
            _anchor("8m", "custom_wma", 34, "rejection_up", "long", 14.0, []),
            _anchor("4m", "custom_wma", 144, "rejection_down", "short", 22.0, ["VERY_HIGH_FAILURE_RATE"]),
        ],
    }


def _r205_record() -> dict:
    return {
        "event_type": "PATTERN_LANE_MATRIX_REVIEW",
        "status": "PATTERN_LANE_MATRIX_REVIEW_RECORDED",
        "pattern_lane_pair_matrix": [
            _lane_pair(LANE_8M_SHORT, "hammer_wick_reversal", "8m", "short", 84, 63, []),
            _lane_pair(LANE_8M_SHORT, "bearish_engulfing", "8m", "short", 82, 63, ["failure_rate_exceeds_success_rate"]),
            _lane_pair(LANE_8M_SHORT, "three_black_crows", "8m", "short", 68, 63, []),
            _lane_pair(LANE_8M_LONG, "bullish_engulfing", "8m", "long", 55, 55, ["mixed_bias_review_required"]),
            _lane_pair("BTCUSDT|13m|short|ladder_close_50_618", "bullish_engulfing", "13m", "short", 7, 55, ["stale_only_flow"], fresh="stale_only"),
        ],
    }


def _r204_record() -> dict:
    return {
        "event_type": "PATTERN_KETER_RESCORING_FAMILY",
        "status": "PATTERN_KETER_RESCORING_FAMILY_RECORDED",
        "pattern_origin_scorecards": {
            "bearish_engulfing": {"keter_score": 74, "risk_warnings": ["failure_rate_exceeds_success_rate"]},
            "bullish_engulfing": {"keter_score": 49, "risk_warnings": ["mixed_directional_bias_review_required"]},
            "breakdown_retest": {"keter_score": 0, "risk_warnings": ["registry_only_until_retest_structure"]},
            "breakout_retest": {"keter_score": 0, "risk_warnings": ["registry_only_until_retest_structure"]},
        },
        "reference_comparison": {
            "hammer_wick_reversal_keter_score": 82,
            "three_black_crows_projected_score": 69,
        },
    }


def _r195_record() -> dict:
    return {
        "event_type": "LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK",
        "post_outcome_pair_comparison": {
            "hammer_wick_reversal": {"pair_score": 72},
            "three_black_crows": {"pair_score": 66},
        },
    }


def _anchor(timeframe: str, anchor_type: str, period: int, interaction: str, direction: str, score: float, warnings: list[str]) -> dict:
    return {
        "timeframe": timeframe,
        "anchor_type": anchor_type,
        "period": period,
        "interaction": interaction,
        "direction_bias": direction,
        "score": score,
        "mapped_events": 120,
        "sample_confidence": "HIGH",
        "risk_warnings": warnings,
        "paper_only": True,
        "live_authorized": False,
    }


def _lane_pair(
    lane_key: str,
    origin: str,
    timeframe: str,
    direction: str,
    pair_score: int,
    lane_score: int,
    warnings: list[str],
    *,
    fresh: str = "fresh",
) -> dict:
    return {
        "lane_key": lane_key,
        "signal_origin": origin,
        "timeframe": timeframe,
        "direction": direction,
        "pair_score": pair_score,
        "lane_score": lane_score,
        "configured_lane": True,
        "fresh_flow_status": fresh,
        "pair_readiness": "PATTERN_PAIR_READY_FOR_PAPER_TRACKING",
        "risk_warnings": warnings,
        "paper_only": True,
        "live_authorized": False,
    }


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
