from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.pattern_lane_matrix_review import (
    CONFIRM_PATTERN_LANE_MATRIX_REVIEW_RECORDING_PHRASE,
    LEDGER_FILENAME,
    PATTERN_LANE_MATRIX_REVIEW_RECORDED,
    PATTERN_LANE_MATRIX_REVIEW_REJECTED,
    PATTERN_PAIR_MIXED_BIAS_REVIEW_REQUIRED,
    PATTERN_PAIR_NEEDS_MORE_FRESH_FLOW,
    PATTERN_PAIR_READY_FOR_PAPER_TRACKING,
    PATTERN_PAIR_REGISTRY_ONLY_BLOCKED,
    build_pattern_lane_matrix_review,
    load_pattern_lane_matrix_review_records,
    score_pattern_lane_pair,
)

NOW = datetime(2026, 6, 5, 21, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
LANE_8M_LONG = "BTCUSDT|8m|long|ladder_close_50_618"
LANE_22M_SHORT = "BTCUSDT|22m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _write_r205_inputs(tmp_path / "logs")

    payload = build_pattern_lane_matrix_review(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["record_matrix_requested"] is False
    assert payload["matrix_recorded"] is False
    assert payload["matrix_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    _write_r205_inputs(tmp_path / "logs")

    payload = build_pattern_lane_matrix_review(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_matrix=True,
        confirm_pattern_lane_matrix="wrong",
        now=NOW,
    )

    assert payload["status"] == PATTERN_LANE_MATRIX_REVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["matrix_recorded"] is False
    assert load_pattern_lane_matrix_review_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_matrix_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    _write_r205_inputs(log_dir)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_pattern_lane_matrix_review(
        log_dir=log_dir,
        config_path=config_path,
        record_matrix=True,
        confirm_pattern_lane_matrix=CONFIRM_PATTERN_LANE_MATRIX_REVIEW_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_pattern_lane_matrix_review_records(log_dir=log_dir, limit=0)

    assert payload["status"] == PATTERN_LANE_MATRIX_REVIEW_RECORDED
    assert payload["matrix_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "PATTERN_LANE_MATRIX_REVIEW"
    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")


def test_directional_pattern_alignment(tmp_path: Path) -> None:
    _write_r205_inputs(tmp_path / "logs")
    payload = build_pattern_lane_matrix_review(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    rows = {(row["lane_key"], row["signal_origin"]): row for row in payload["pattern_lane_pair_matrix"]}

    assert rows[(LANE_8M_SHORT, "bearish_engulfing")]["pair_readiness"] == PATTERN_PAIR_READY_FOR_PAPER_TRACKING
    assert rows[(LANE_8M_LONG, "bullish_engulfing")]["pair_score"] > rows[(LANE_8M_SHORT, "bullish_engulfing")]["pair_score"]
    assert rows[(LANE_8M_LONG, "three_white_soldiers")]["pair_score"] > rows[(LANE_8M_SHORT, "three_white_soldiers")]["pair_score"]


def test_registry_only_retest_origins_are_blocked() -> None:
    row = score_pattern_lane_pair(
        lane=_lane(LANE_8M_SHORT, configured=True),
        signal_origin="breakdown_retest",
        pattern_card={"signal_origin": "breakdown_retest", "keter_score": 0, "mapped_count": 0},
        lane_reference={},
        outcome_mapping={},
    )

    assert row["pair_readiness"] == PATTERN_PAIR_REGISTRY_ONLY_BLOCKED
    assert row["live_authorized"] is False
    assert row["signal_origin_promoted"] is False


def test_stale_only_flow_creates_penalty() -> None:
    fresh = score_pattern_lane_pair(
        lane={**_lane(LANE_8M_SHORT, configured=True), "fresh_flow_status": "fresh"},
        signal_origin="bearish_engulfing",
        pattern_card=_card("bearish_engulfing", 74, mapped_count=120),
        lane_reference={},
        outcome_mapping={},
    )
    stale = score_pattern_lane_pair(
        lane={**_lane("BTCUSDT|13m|short|ladder_close_50_618", configured=True), "fresh_flow_status": "stale_only"},
        signal_origin="bearish_engulfing",
        pattern_card=_card("bearish_engulfing", 74, mapped_count=120),
        lane_reference={},
        outcome_mapping={},
    )

    assert stale["pair_score"] < fresh["pair_score"]
    assert stale["pair_readiness"] == PATTERN_PAIR_NEEDS_MORE_FRESH_FLOW
    assert "stale_only_flow" in stale["risk_warnings"]


def test_discovered_unconfigured_lane_creates_caution() -> None:
    discovered = score_pattern_lane_pair(
        lane=_lane(LANE_22M_SHORT, configured=False),
        signal_origin="bearish_engulfing",
        pattern_card=_card("bearish_engulfing", 74, mapped_count=120),
        lane_reference={},
        outcome_mapping={},
    )

    assert discovered["configured_lane"] is False
    assert discovered["lane_mode"] == "paper_discovered_unconfigured"
    assert "discovered_unconfigured_lane_caution" in discovered["risk_warnings"]


def test_no_live_authorization_no_promotions_or_mutations(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config_path = _write_config(tmp_path / "lane_controls.json")
    _write_r205_inputs(log_dir)
    before_env = dict(os.environ)
    before_config = config_path.read_text(encoding="utf-8")

    payload = build_pattern_lane_matrix_review(log_dir=log_dir, config_path=config_path, now=NOW)

    assert before_env == dict(os.environ)
    assert before_config == config_path.read_text(encoding="utf-8")
    assert all(row["live_authorized"] is False for row in payload["pattern_lane_pair_matrix"])
    assert all(row["signal_origin_promoted"] is False for row in payload["pattern_lane_pair_matrix"])
    assert all(row["lane_promoted"] is False for row in payload["pattern_lane_pair_matrix"])
    for key in (
        "env_written",
        "env_mutated",
        "config_written",
        "registry_config_written",
        "scoring_config_written",
        "matrix_config_written",
        "risk_contract_config_written",
        "lane_config_written",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "order_payload_created",
        "executable_payload_created",
        "signed_order_request_created",
        "signed_trading_request_created",
        "signed_readonly_request_created",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "network_allowed",
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "secrets_shown",
        "global_live_flags_changed",
        "kill_switch_disabled",
        "live_authorization_created",
        "signal_origin_promoted",
        "lane_promoted",
        "pattern_family_live_authorized",
        "anchor_live_authorized",
    ):
        assert payload["safety"][key] is False, key
    assert payload["safety"]["paper_live_separation_intact"] is True


def test_no_binance_network_order_live_transfer_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    _write_r205_inputs(tmp_path / "logs")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_pattern_lane_matrix_review(
            log_dir=tmp_path / "logs",
            config_path=_write_config(tmp_path / "lane_controls.json"),
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert payload["safety"]["network_allowed"] is False
    assert payload["safety"]["order_placed"] is False
    assert payload["safety"]["transfer_endpoint_called"] is False
    assert payload["safety"]["withdraw_endpoint_called"] is False


def test_exhaustion_wick_mixed_bias_review_required() -> None:
    row = score_pattern_lane_pair(
        lane={**_lane(LANE_8M_SHORT, configured=True), "fresh_flow_status": "fresh"},
        signal_origin="exhaustion_wick",
        pattern_card=_card("exhaustion_wick", 53, mapped_count=70, mixed=True),
        lane_reference={},
        outcome_mapping={},
    )

    assert row["pair_readiness"] == PATTERN_PAIR_MIXED_BIAS_REVIEW_REQUIRED


def test_cli_exists(tmp_path: Path) -> None:
    _write_r205_inputs(tmp_path / "logs")

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "pattern-lane-matrix-review",
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
    assert "pattern_lane_pair_matrix" in payload
    assert "pattern-lane-matrix-review" in help_result.stdout


def _write_r205_inputs(log_dir: Path) -> None:
    _append_json(log_dir / "pattern_keter_rescoring_family.ndjson", _r204_record())
    _append_json(log_dir / "pattern_outcome_mapping_family.ndjson", _r202_record())
    _append_json(log_dir / "lane_matrix_after_crow_outcome_feedback.ndjson", _r195_record())


def _r204_record() -> dict:
    return {
        "event_type": "PATTERN_KETER_RESCORING_FAMILY",
        "status": "PATTERN_KETER_RESCORING_FAMILY_RECORDED",
        "pattern_origin_scorecards": {
            "bearish_engulfing": _card("bearish_engulfing", 74, mapped_count=120),
            "exhaustion_wick": _card("exhaustion_wick", 53, mapped_count=70, mixed=True),
            "bullish_engulfing": _card("bullish_engulfing", 49, mapped_count=80),
            "three_white_soldiers": _card("three_white_soldiers", 40, mapped_count=90),
            "breakdown_retest": _card("breakdown_retest", 0, mapped_count=0),
            "breakout_retest": _card("breakout_retest", 0, mapped_count=0),
        },
        "reference_comparison": {
            "hammer_wick_reversal_keter_score": 82,
            "three_black_crows_projected_score": 69,
        },
    }


def _r195_record() -> dict:
    return {
        "event_type": "LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK",
        "status": "LANE_MATRIX_AFTER_CROW_OUTCOME_FEEDBACK_RECORDED",
        "post_outcome_pair_comparison": {
            "hammer_wick_reversal": {
                "lane_key": LANE_8M_SHORT,
                "signal_origin": "hammer_wick_reversal",
                "lane_score": 63,
                "origin_keter_score": 82,
                "pair_score": 72,
                "fresh_capture_count": 3,
                "mapped_count": 116,
                "paper_only": True,
                "live_authorized": False,
            },
            "three_black_crows": {
                "lane_key": LANE_8M_SHORT,
                "signal_origin": "three_black_crows",
                "lane_score": 63,
                "origin_keter_score": 69,
                "projected_keter_score_after_outcome": 69,
                "pair_score": 66,
                "fresh_capture_count": 3,
                "mapped_count": 23,
                "paper_only": True,
                "live_authorized": False,
            },
        },
    }


def _r202_record() -> dict:
    return {
        "event_type": "PATTERN_OUTCOME_MAPPING_FAMILY",
        "origin_outcome_summary": {
            "bearish_engulfing": {"mapped_count": 120},
            "bullish_engulfing": {"mapped_count": 80},
            "three_white_soldiers": {"mapped_count": 90},
            "exhaustion_wick": {"mapped_count": 70},
        },
    }


def _card(origin: str, score: int, *, mapped_count: int, mixed: bool = False) -> dict:
    return {
        "signal_origin": origin,
        "keter_score": score,
        "readiness": "PATTERN_MIXED_BIAS_REVIEW_REQUIRED" if mixed else "PATTERN_READY_FOR_PAPER_MATRIX_REVIEW",
        "mapped_count": mapped_count,
        "supports_directional_bias": not mixed,
        "risk_warnings": ["mixed_directional_bias_review_required"] if mixed else [],
        "paper_only": True,
        "live_authorized": False,
        "signal_origin_promoted": False,
        "lane_promoted": False,
    }


def _lane(lane_key: str, *, configured: bool) -> dict:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    return {
        "lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "lane_mode": "paper" if configured else "paper_discovered_unconfigured",
        "configured_lane": configured,
        "lane_score": 63 if configured else 42,
    }


def _write_config(path: Path) -> Path:
    payload = {
        "schema_version": "1.0",
        "default_mode": "disabled",
        "lanes": [
            {
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "mode": "paper",
            },
            {
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "long",
                "entry_mode": "ladder_close_50_618",
                "mode": "paper",
            },
        ],
    }
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
