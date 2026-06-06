from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_integration_recheck import (
    BETRAYAL_INTEGRATION_RECHECK_RECORDED,
    BETRAYAL_INTEGRATION_RECHECK_REJECTED,
    CONFIRM_BETRAYAL_INTEGRATION_RECHECK_RECORDING_PHRASE,
    LEDGER_FILENAME,
    build_betrayal_integration_recheck,
    load_betrayal_integration_recheck_records,
)

NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
LANE_222M_LONG = "BTCUSDT|222m|long|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_integration_recheck(log_dir=log_dir, now=NOW)

    assert payload["record_recheck_requested"] is False
    assert payload["recheck_recorded"] is False
    assert payload["recheck_id"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    payload = build_betrayal_integration_recheck(
        log_dir=tmp_path / "logs",
        record_recheck=True,
        confirm_betrayal_integration_recheck="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_INTEGRATION_RECHECK_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["recheck_recorded"] is False
    assert load_betrayal_integration_recheck_records(log_dir=tmp_path / "logs", limit=0) == []


def test_correct_confirmation_records_recheck_only(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)
    before_env = dict(os.environ)

    payload = build_betrayal_integration_recheck(
        log_dir=log_dir,
        record_recheck=True,
        confirm_betrayal_integration_recheck=CONFIRM_BETRAYAL_INTEGRATION_RECHECK_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_betrayal_integration_recheck_records(log_dir=log_dir, limit=0)

    assert payload["status"] == BETRAYAL_INTEGRATION_RECHECK_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["recheck_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_INTEGRATION_RECHECK"
    assert before_env == dict(os.environ)


def test_includes_222m_primary_and_88m_watchlist_context(tmp_path: Path) -> None:
    payload = build_betrayal_integration_recheck(log_dir=tmp_path / "logs", now=NOW)
    summary = payload["betrayal_candidate_summary"]

    assert payload["betrayal_scope"]["primary_candidate"] == "222m aggregate"
    assert "88m aggregate" in payload["betrayal_scope"]["watchlist_candidates"]
    assert summary["222m"]["label"] == "BETRAYAL_PRIMARY_CANDIDATE"
    assert summary["222m"]["original_sample_count"] == 48
    assert summary["222m"]["original_win_rate_pct"] == 12.5
    assert summary["222m"]["naive_inverse_win_rate_pct"] == 87.5
    assert summary["88m"]["label"] == "BETRAYAL_WATCHLIST"
    assert summary["88m"]["original_sample_count"] == 90
    assert summary["88m"]["original_win_rate_pct"] == 36.67
    assert summary["88m"]["naive_inverse_win_rate_pct"] == 63.33


def test_marks_true_inverse_required_and_betrayal_not_live_ready(tmp_path: Path) -> None:
    payload = build_betrayal_integration_recheck(log_dir=tmp_path / "logs", now=NOW)

    assert payload["betrayal_candidate_summary"]["222m"]["true_inverse_validation_required"] is True
    assert payload["betrayal_candidate_summary"]["88m"]["true_inverse_validation_required"] is True
    assert payload["betrayal_candidate_summary"]["222m"]["live_ready"] is False
    assert payload["betrayal_candidate_summary"]["88m"]["live_ready"] is False
    assert payload["true_inverse_validation_summary"]["validation_required_before_promotion"] is True
    assert payload["true_inverse_validation_summary"]["naive_inverse_is_validated_edge"] is False
    assert payload["betrayal_scope"]["live_authorized"] is False


def test_detects_latest_222m_capture_linkage_but_not_validated_sample(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_full_spectrum_222m_capture(log_dir)

    payload = build_betrayal_integration_recheck(log_dir=log_dir, now=NOW)
    linkage = payload["betrayal_capture_linkage"]

    assert linkage["latest_222m_capture_found"] is True
    assert linkage["latest_222m_capture_lane"] == LANE_222M_LONG
    assert linkage["capture_matches_primary_candidate_timeframe"] is True
    assert linkage["capture_direction_context"] == "long"
    assert linkage["can_use_capture_as_true_inverse_sample_now"] is False
    assert "true inverse outcome" in linkage["why"]


def test_reports_missing_current_matrix_integration(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_integration_recheck(log_dir=log_dir, now=NOW)
    gap = payload["current_stack_gap_report"]

    assert gap["included_in_weekend_supervisor"] is True
    assert gap["included_in_pattern_lane_matrix"] is False
    assert gap["included_in_anchor_confluence_matrix"] is False
    assert gap["included_in_tiny_live_readiness"] is False
    assert gap["matrix_integration_missing"] is True
    assert "not an explicit betrayal-aware row" in gap["reason_if_missing"]


def test_no_live_authorization_promotion_env_config_network_or_orders(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    before_env = dict(os.environ)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_betrayal_integration_recheck(log_dir=tmp_path / "logs", now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert before_env == dict(os.environ)
    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key
    assert payload["safety"]["betrayal_live_authorized"] is False
    assert payload["safety"]["betrayal_promoted"] is False


def test_recommendations_keep_audit_only_and_refresh_true_inverse(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    _write_stack(log_dir)

    payload = build_betrayal_integration_recheck(log_dir=log_dir, now=NOW)
    actions = {row["recommended_action"] for row in payload["betrayal_integration_recommendations"]}

    assert "KEEP_AUDIT_ONLY" in actions
    assert "BUILD_TRUE_INVERSE_EVENT_MATCHER" in actions
    assert "ADD_PAPER_MATRIX_CONTEXT" in actions
    assert payload["recommended_next_operator_move"] == "RUN_R210_BETRAYAL_TRUE_INVERSE_REFRESH"
    assert "live-connector-submit" in payload["do_not_run_yet"]


def test_cli_exists(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "betrayal-integration-recheck",
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
    assert "betrayal_candidate_summary" in payload
    assert "betrayal-integration-recheck" in help_result.stdout


def _write_stack(log_dir: Path) -> None:
    _write_weekend_summary(log_dir)
    _write_full_spectrum_222m_capture(log_dir)
    _append_json(
        log_dir / "pattern_lane_matrix_review.ndjson",
        {"generated_at": NOW.isoformat(), "pattern_lane_pair_matrix": [{"signal_origin": "hammer_wick_reversal"}]},
    )
    _append_json(
        log_dir / "anchor_signal_confluence_matrix.ndjson",
        {"generated_at": NOW.isoformat(), "anchor_signal_confluence_rows": [{"signal_origin": "hammer_wick_reversal"}]},
    )
    _append_json(
        log_dir / "tiny_live_readiness_gap_recheck.ndjson",
        {"generated_at": NOW.isoformat(), "candidate_context": {"primary_signal_origin": "hammer_wick_reversal"}},
    )


def _write_weekend_summary(log_dir: Path) -> None:
    _append_json(
        log_dir / "weekend_paper_fisherman_supervisor.ndjson",
        {
            "generated_at": NOW.isoformat(),
            "betrayal_watch_summary": {
                "betrayal_context_included": True,
                "betrayal_integrated_into_current_matrix": False,
                "latest_222m_capture_found": True,
                "latest_222m_capture_lane": LANE_222M_LONG,
                "latest_222m_capture_at": NOW.isoformat(),
                "betrayal_live_ready": False,
                "true_inverse_validation_required": True,
            },
        },
    )


def _write_full_spectrum_222m_capture(log_dir: Path) -> None:
    _append_json(
        log_dir / "full_spectrum_harvester_heartbeats.ndjson",
        {
            "event_type": "FULL_SPECTRUM_HARVESTER_EXPANSION_HEARTBEAT",
            "generated_at": NOW.isoformat(),
            "captured_lanes": [LANE_222M_LONG],
            "status": "FULL_SPECTRUM_HARVEST_EXITED",
            "total_captured": 1,
        },
    )


def _append_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
