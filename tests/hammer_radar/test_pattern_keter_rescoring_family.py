from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.pattern_keter_rescoring_family import (
    CONFIRM_PATTERN_KETER_RESCORING_FAMILY_RECORDING_PHRASE,
    LEDGER_FILENAME,
    PATTERN_KETER_RESCORING_FAMILY_RECORDED,
    PATTERN_KETER_RESCORING_FAMILY_REJECTED,
    PATTERN_REGISTRY_ONLY_BLOCKED,
    build_pattern_keter_rescoring_family,
    load_pattern_keter_rescoring_family_records,
    score_pattern_origin,
)

NOW = datetime(2026, 6, 5, 19, 0, tzinfo=UTC)


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_r204_inputs(tmp_path / "logs")

    payload = build_pattern_keter_rescoring_family(log_dir=tmp_path / "logs", now=NOW)

    assert payload["record_rescore_requested"] is False
    assert payload["rescore_recorded"] is False
    assert payload["rescore_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_r204_inputs(tmp_path / "logs")

    payload = build_pattern_keter_rescoring_family(
        log_dir=tmp_path / "logs",
        record_rescore=True,
        confirm_pattern_keter_family="wrong",
        now=NOW,
    )

    assert payload["status"] == PATTERN_KETER_RESCORING_FAMILY_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["rescore_recorded"] is False
    assert load_pattern_keter_rescoring_family_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_rescore_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_r204_inputs(log_dir)
    before_env = dict(os.environ)

    payload = build_pattern_keter_rescoring_family(
        log_dir=log_dir,
        record_rescore=True,
        confirm_pattern_keter_family=CONFIRM_PATTERN_KETER_RESCORING_FAMILY_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_pattern_keter_rescoring_family_records(log_dir=log_dir, limit=0)

    assert payload["status"] == PATTERN_KETER_RESCORING_FAMILY_RECORDED
    assert payload["rescore_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "PATTERN_KETER_RESCORING_FAMILY"
    assert records[0]["safety"]["config_written"] is False
    assert records[0]["safety"]["order_placed"] is False
    assert before_env == dict(os.environ)


def test_positive_directional_bias_increases_score() -> None:
    positive = score_pattern_origin(
        signal_origin="bearish_engulfing",
        outcome_summary=_origin_summary(mapped_count=120, supports=True),
        detector_summary=_detector_summary(total=160),
        anchor_recommendations=[{"signal_origin": "bearish_engulfing", "priority": "HIGH"}],
    )
    mixed = score_pattern_origin(
        signal_origin="bearish_engulfing",
        outcome_summary=_origin_summary(mapped_count=120, supports=False),
        detector_summary=_detector_summary(total=160),
        anchor_recommendations=[{"signal_origin": "bearish_engulfing", "priority": "HIGH"}],
    )

    assert positive["keter_score"] > mixed["keter_score"]
    assert positive["readiness"] == "PATTERN_READY_FOR_PAPER_MATRIX_REVIEW"


def test_mixed_bias_creates_penalty() -> None:
    card = score_pattern_origin(
        signal_origin="bullish_engulfing",
        outcome_summary=_origin_summary(mapped_count=120, supports=False),
        detector_summary=_detector_summary(total=160),
    )

    assert card["readiness"] == "PATTERN_MIXED_BIAS_REVIEW_REQUIRED"
    assert card["dimension_scores"]["mixed_bias_penalty"] > 0
    assert "mixed_directional_bias_review_required" in card["risk_warnings"]


def test_high_failure_adverse_risk_creates_penalty() -> None:
    card = score_pattern_origin(
        signal_origin="exhaustion_wick",
        outcome_summary=_origin_summary(
            mapped_count=200,
            supports=True,
            success_rate=35.0,
            failure_rate=86.0,
            favorable_move=0.2,
            adverse_move=0.9,
        ),
        detector_summary=_detector_summary(total=300),
    )

    assert card["dimension_scores"]["failure_rate_penalty"] > 0
    assert card["dimension_scores"]["adverse_risk_penalty"] > 0
    assert "failure_rate_exceeds_success_rate" in card["risk_warnings"]
    assert "average_adverse_exceeds_average_favorable" in card["risk_warnings"]


def test_registry_only_retest_origins_remain_blocked(tmp_path: Path) -> None:
    _write_r204_inputs(tmp_path / "logs")

    payload = build_pattern_keter_rescoring_family(log_dir=tmp_path / "logs", now=NOW)

    for origin in ("breakdown_retest", "breakout_retest"):
        card = payload["pattern_origin_scorecards"][origin]
        assert card["keter_score"] == 0
        assert card["readiness"] == PATTERN_REGISTRY_ONLY_BLOCKED
        assert card["blocked_reason"] == "registry_only_until_retest_structure"


def test_no_pattern_becomes_live_authorized_or_promoted(tmp_path: Path) -> None:
    _write_r204_inputs(tmp_path / "logs")

    payload = build_pattern_keter_rescoring_family(log_dir=tmp_path / "logs", now=NOW)

    assert all(card["live_authorized"] is False for card in payload["pattern_origin_scorecards"].values())
    assert all(card["signal_origin_promoted"] is False for card in payload["pattern_origin_scorecards"].values())
    assert all(card["lane_promoted"] is False for card in payload["pattern_origin_scorecards"].values())
    assert payload["safety"]["pattern_family_live_authorized"] is False
    assert payload["safety"]["signal_origin_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False


def test_reference_comparison_and_recommendations_exist(tmp_path: Path) -> None:
    _write_r204_inputs(tmp_path / "logs")

    payload = build_pattern_keter_rescoring_family(log_dir=tmp_path / "logs", now=NOW)

    assert payload["reference_comparison"]["hammer_wick_reversal_keter_score"] == 82
    assert payload["reference_comparison"]["three_black_crows_projected_score"] == 69
    assert payload["reference_comparison"]["top_pattern_origin"]
    assert payload["lane_matrix_recommendations"]
    assert payload["anchor_confluence_recommendations"]


def test_no_env_config_mutation(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = tmp_path / "lane_controls.json"
    config_path.write_text('{"lanes":[]}\n', encoding="utf-8")
    _write_r204_inputs(log_dir)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_pattern_keter_rescoring_family(log_dir=log_dir, now=NOW)

    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert payload["safety"]["env_written"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["registry_config_written"] is False
    assert payload["safety"]["scoring_config_written"] is False
    assert payload["safety"]["matrix_config_written"] is False
    assert payload["safety"]["lane_config_written"] is False


def test_no_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_r204_inputs(tmp_path / "logs")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_pattern_keter_rescoring_family(log_dir=tmp_path / "logs", now=NOW)

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
    _write_r204_inputs(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "pattern-keter-rescoring-family",
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
    assert "pattern_origin_scorecards" in payload
    assert "pattern-keter-rescoring-family" in help_result.stdout


def _write_r204_inputs(log_dir: Path) -> None:
    _append_json(log_dir / "pattern_outcome_mapping_family.ndjson", _r202_record())
    _append_json(log_dir / "pattern_family_feedback_sync.ndjson", _r200_record())
    _append_json(
        log_dir / "crow_outcome_keter_feedback.ndjson",
        {
            "event_type": "CROW_OUTCOME_KETER_FEEDBACK",
            "updated_crow_keter_projection": {"projected_keter_score_after_outcome": 69},
            "comparison_to_hammer": {"hammer_keter_score": 82},
        },
    )


def _r202_record() -> dict:
    return {
        "event_type": "PATTERN_OUTCOME_MAPPING_FAMILY",
        "status": "PATTERN_OUTCOME_MAPPING_FAMILY_RECORDED",
        "aggregate_summary": {
            "total_mapped_count": 360,
            "origins_with_positive_bias": ["bearish_engulfing"],
            "origins_with_mixed_bias": ["three_white_soldiers", "bullish_engulfing", "exhaustion_wick"],
            "registry_only_blocked": ["breakdown_retest", "breakout_retest"],
        },
        "origin_outcome_summary": {
            "three_white_soldiers": _origin_summary(mapped_count=90, supports=False),
            "bearish_engulfing": _origin_summary(mapped_count=120, supports=True),
            "bullish_engulfing": _origin_summary(mapped_count=80, supports=False),
            "exhaustion_wick": _origin_summary(mapped_count=70, supports=False, failure_rate=78.0),
            "breakdown_retest": {"mapped_count": 0, "blocked_reason": "registry_only_until_retest_structure"},
            "breakout_retest": {"mapped_count": 0, "blocked_reason": "registry_only_until_retest_structure"},
        },
        "pattern_outcome_rankings": [
            {
                "signal_origin": "bearish_engulfing",
                "risk_warnings": [],
                "paper_only": True,
                "live_authorized": False,
            },
            {
                "signal_origin": "exhaustion_wick",
                "risk_warnings": ["failure_rate_exceeds_success_rate"],
                "paper_only": True,
                "live_authorized": False,
            },
        ],
    }


def _r200_record() -> dict:
    return {
        "event_type": "PATTERN_FAMILY_FEEDBACK_SYNC",
        "pattern_family_detection_summary": {
            "three_white_soldiers": _detector_summary(total=60, timeframes=["4m", "8m", "13m"]),
            "bearish_engulfing": _detector_summary(total=180, timeframes=["4m", "8m", "13m", "4H"]),
            "bullish_engulfing": _detector_summary(total=130, timeframes=["4m", "8m", "13m"]),
            "exhaustion_wick": _detector_summary(total=300, timeframes=["4m", "8m", "13m", "22m", "4H"]),
            "breakdown_retest": {"detector_available": False, "registry_only": True, "paper_only": True, "live_authorized": False},
            "breakout_retest": {"detector_available": False, "registry_only": True, "paper_only": True, "live_authorized": False},
        },
        "anchor_overlay_recommendations": [
            {"signal_origin": "bearish_engulfing", "priority": "HIGH"},
            {"signal_origin": "exhaustion_wick", "priority": "HIGH"},
            {"signal_origin": "bullish_engulfing", "priority": "MEDIUM"},
            {"signal_origin": "three_white_soldiers", "priority": "MEDIUM"},
        ],
    }


def _origin_summary(
    *,
    mapped_count: int,
    supports: bool,
    favorable_rate: float = 70.0,
    success_rate: float = 72.0,
    failure_rate: float = 30.0,
    favorable_move: float = 0.8,
    adverse_move: float = 0.25,
) -> dict:
    return {
        "mapped_count": mapped_count,
        "best_window": "10",
        "supports_directional_bias": supports,
        "window_stats": {
            "10": {
                "mapped_count": mapped_count,
                "favorable_close_rate_pct": favorable_rate,
                "simple_success_rate_pct": success_rate,
                "simple_failure_rate_pct": failure_rate,
                "avg_favorable_move_pct": favorable_move,
                "avg_adverse_move_pct": adverse_move,
            }
        },
        "paper_only": True,
        "live_authorized": False,
    }


def _detector_summary(*, total: int, timeframes: list[str] | None = None) -> dict:
    strict = max(1, total // 4)
    return {
        "strict_detections_found": strict,
        "loose_detections_found": max(0, total - strict),
        "timeframes_with_detections": timeframes or ["4m", "8m"],
        "detector_available": total > 0,
        "paper_only": True,
        "live_authorized": False,
    }


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
