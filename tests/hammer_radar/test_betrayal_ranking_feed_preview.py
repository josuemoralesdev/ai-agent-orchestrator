import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_ranking_feed_preview import (
    BETRAYAL_RANKING_FEED_PREVIEW_RECORDED,
    BETRAYAL_RANKING_FEED_PREVIEW_REJECTED,
    BETRAYAL_TRACK_B_STRUCTURALLY_COMPLETE_WAITING_FOR_DATA,
    CONFIRM_BETRAYAL_RANKING_FEED_PREVIEW_RECORDING_PHRASE,
    RANKING_FEED_PREVIEW_READY,
    build_betrayal_ranking_feed_preview,
    load_betrayal_ranking_feed_preview_records,
    normalize_true_inverse_capture_row_for_ranking_preview,
)

NOW = datetime(2026, 6, 8, 22, 30, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_betrayal_ranking_feed_preview(log_dir=log_dir, now=NOW)

    assert payload["ranking_preview_recorded"] is False
    assert payload["record_ranking_preview_requested"] is False
    assert load_betrayal_ranking_feed_preview_records(log_dir=log_dir, limit=0) == []
    assert payload["target_scope"]["ranking_feed_preview_only"] is True
    assert payload["safety"]["ranking_feed_preview_ledger_only"] is True


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_betrayal_ranking_feed_preview(
        log_dir=log_dir,
        record_ranking_preview=True,
        confirm_betrayal_ranking_feed_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_RANKING_FEED_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["ranking_preview_recorded"] is False
    assert load_betrayal_ranking_feed_preview_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_ranking_preview_only(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    protected = {
        "paper_outcomes": log_dir / "paper_outcomes.ndjson",
        "strategy_performance": log_dir / "strategy_performance.ndjson",
        "strategy_promotion_status": log_dir / "strategy_promotion_status.ndjson",
    }
    before = {name: path.read_text(encoding="utf-8") for name, path in protected.items()}

    payload = build_betrayal_ranking_feed_preview(
        log_dir=log_dir,
        record_ranking_preview=True,
        confirm_betrayal_ranking_feed_preview=CONFIRM_BETRAYAL_RANKING_FEED_PREVIEW_RECORDING_PHRASE,
        now=NOW,
    )

    records = load_betrayal_ranking_feed_preview_records(log_dir=log_dir, limit=0)
    assert payload["status"] == BETRAYAL_RANKING_FEED_PREVIEW_RECORDED
    assert payload["ranking_preview_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_RANKING_FEED_PREVIEW"
    assert {name: path.read_text(encoding="utf-8") for name, path in protected.items()} == before
    assert records[0]["safety"]["normal_ranking_ledger_appended"] is False
    assert records[0]["safety"]["strategy_performance_appended"] is False
    assert records[0]["safety"]["strategy_promotion_status_appended"] is False


def test_ranking_preview_reads_r237_true_inverse_capture_rows(tmp_path: Path) -> None:
    payload = build_betrayal_ranking_feed_preview(log_dir=_fixture_logs(tmp_path), now=NOW)

    assert payload["input_summary"]["betrayal_true_inverse_capture_bridge_found"] is True
    assert payload["ranking_feed_summary"]["rows_reviewed"] == 4
    ready = [
        row for row in payload["ranking_feed_preview_rows"] if row["ranking_feed_status"] == RANKING_FEED_PREVIEW_READY
    ]
    assert [row["signal_id"] for row in ready] == ["signal-ready-1"]


def test_ranking_feed_preview_ready_requires_ranking_projection_ready() -> None:
    ready = normalize_true_inverse_capture_row_for_ranking_preview(
        _r237_ready_row(),
        schema_context={"registry_valid_entry_modes": ["ladder_close_50_618"]},
    )
    blocked = normalize_true_inverse_capture_row_for_ranking_preview(
        {**_r237_ready_row(), "ranking_projection_ready": False},
        schema_context={"registry_valid_entry_modes": ["ladder_close_50_618"]},
    )

    assert ready["ranking_feed_status"] == RANKING_FEED_PREVIEW_READY
    assert blocked["ranking_feed_status"] == "BLOCKED"
    assert "ranking_projection_not_ready" in blocked["blockers"]


def test_true_inverse_outcome_pending_blocks_ranking_evidence(tmp_path: Path) -> None:
    payload = build_betrayal_ranking_feed_preview(log_dir=_fixture_logs(tmp_path), now=NOW)
    ready = next(row for row in payload["ranking_feed_preview_rows"] if row["signal_id"] == "signal-ready-1")

    assert ready["true_inverse_outcome_found"] is False
    assert ready["true_inverse_outcome_pending"] is True
    assert ready["ranking_evidence_available"] is False
    assert "true_inverse_outcome_pending" in ready["blockers"]
    assert payload["ranking_feed_summary"]["waiting_for_true_inverse_outcome_rows"] == 4


def test_ranking_scores_win_rates_and_promotion_eligibility_are_not_fabricated(tmp_path: Path) -> None:
    payload = build_betrayal_ranking_feed_preview(log_dir=_fixture_logs(tmp_path), now=NOW)

    assert payload["ranking_feed_summary"]["ranking_evidence_available_rows"] == 0
    assert all(row["ranking_score"] is None for row in payload["ranking_feed_preview_rows"])
    assert all(row["win_rate_pct"] is None for row in payload["ranking_feed_preview_rows"])
    assert all(row["sample_size"] is None for row in payload["ranking_feed_preview_rows"])
    assert payload["promotion_gate_preview"]["can_promote_today"] is False
    assert payload["safety"]["ranking_scores_fabricated"] is False
    assert payload["safety"]["win_rates_fabricated"] is False
    assert payload["safety"]["promotion_eligibility_fabricated"] is False


def test_promotion_review_ready_and_live_ready_today_always_false(tmp_path: Path) -> None:
    payload = build_betrayal_ranking_feed_preview(log_dir=_fixture_logs(tmp_path), now=NOW)

    assert payload["ranking_feed_summary"]["promotion_review_ready_rows"] == 0
    assert payload["ranking_feed_summary"]["live_ready_today_rows"] == 0
    assert all(row["promotion_review_ready"] is False for row in payload["ranking_feed_preview_rows"])
    assert all(row["live_ready_today"] is False for row in payload["ranking_feed_preview_rows"])
    assert all(row["promotion_allowed"] is False for row in payload["ranking_feed_preview_rows"])
    assert all(row["live_authorized"] is False for row in payload["ranking_feed_preview_rows"])


def test_normal_ranking_and_promotion_ledgers_are_not_appended(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    before = {
        "paper_outcomes": (log_dir / "paper_outcomes.ndjson").read_text(encoding="utf-8"),
        "strategy_performance": (log_dir / "strategy_performance.ndjson").read_text(encoding="utf-8"),
        "strategy_promotion_status": (log_dir / "strategy_promotion_status.ndjson").read_text(encoding="utf-8"),
    }

    payload = build_betrayal_ranking_feed_preview(
        log_dir=log_dir,
        record_ranking_preview=True,
        confirm_betrayal_ranking_feed_preview=CONFIRM_BETRAYAL_RANKING_FEED_PREVIEW_RECORDING_PHRASE,
        now=NOW,
    )

    assert (log_dir / "paper_outcomes.ndjson").read_text(encoding="utf-8") == before["paper_outcomes"]
    assert (log_dir / "strategy_performance.ndjson").read_text(encoding="utf-8") == before["strategy_performance"]
    assert (log_dir / "strategy_promotion_status.ndjson").read_text(encoding="utf-8") == before["strategy_promotion_status"]
    assert payload["safety"]["normal_ranking_ledger_appended"] is False
    assert payload["safety"]["paper_outcomes_appended"] is False
    assert payload["safety"]["strategy_performance_appended"] is False
    assert payload["safety"]["strategy_promotion_status_appended"] is False


def test_official_tiny_live_lane_remains_unchanged_and_no_promotions(tmp_path: Path) -> None:
    payload = build_betrayal_ranking_feed_preview(log_dir=_fixture_logs(tmp_path), now=NOW)
    safety = payload["safety"]

    assert payload["target_scope"]["official_tiny_live_lane"] == OFFICIAL
    assert payload["target_scope"]["official_tiny_live_lane_changed"] is False
    assert payload["official_tiny_live_status"]["fresh_capture_count"] == 8
    assert payload["official_tiny_live_status"]["threshold_met"] is False
    assert safety["betrayal_promoted"] is False
    assert safety["signal_origin_promoted"] is False
    assert safety["lane_promoted"] is False
    assert safety["betrayal_live_authorized"] is False


def test_track_b_structural_completion_report_is_produced(tmp_path: Path) -> None:
    payload = build_betrayal_ranking_feed_preview(log_dir=_fixture_logs(tmp_path), now=NOW)
    report = payload["track_b_structural_completion_report"]

    assert report["same_flow_contract_ready"] is True
    assert report["paper_outcome_bridge_ready"] is True
    assert report["true_inverse_capture_bridge_ready"] is True
    assert report["ranking_feed_preview_ready"] is True
    assert report["structurally_complete_for_now"] is True
    assert report["waiting_for_data_not_architecture"] is True
    assert report["remaining_architecture_gaps"] == []
    assert "true_inverse_outcomes_pending" in report["remaining_data_gaps"]
    assert payload["ranking_overall_status"] == BETRAYAL_TRACK_B_STRUCTURALLY_COMPLETE_WAITING_FOR_DATA


def test_no_env_config_destructive_binance_network_or_order_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    before_env = dict(os.environ)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_betrayal_ranking_feed_preview(log_dir=_fixture_logs(tmp_path), now=NOW)

    assert dict(os.environ) == before_env
    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    for key in (
        "env_written",
        "env_mutated",
        "config_written",
        "registry_config_written",
        "scoring_config_written",
        "matrix_config_written",
        "risk_contract_config_written",
        "lane_config_written",
        "fisherman_config_written",
        "scheduler_config_written",
        "ledger_rewritten",
        "destructive_write",
        "historical_ledger_rewritten",
        "normalized_rows_appended",
        "paper_outcomes_appended",
        "true_inverse_outcomes_fabricated",
        "ranking_scores_fabricated",
        "win_rates_fabricated",
        "promotion_eligibility_fabricated",
        "normal_ranking_ledger_appended",
        "strategy_performance_appended",
        "strategy_promotion_status_appended",
        "network_allowed",
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
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "live_authorization_created",
        "global_live_flags_changed",
        "kill_switch_disabled",
        "signal_origin_promoted",
        "lane_promoted",
        "betrayal_promoted",
        "betrayal_live_authorized",
        "position_permission_created",
    ):
        assert payload["safety"][key] is False
    assert payload["safety"]["paper_live_separation_intact"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "betrayal-ranking-feed-preview",
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["target_scope"]["paper_only"] is True
    assert payload["ranking_preview_recorded"] is False
    assert payload["ranking_feed_summary"]["ranking_feed_preview_ready_rows"] == 1


def _fixture_logs(tmp_path: Path) -> Path:
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    _append(log_dir / "capture_count_sync_8m_short.ndjson", _capture_sync_record(8))
    _append(log_dir / "betrayal_signal_origin_integration_contract.ndjson", _r235_contract_record())
    _append(log_dir / "betrayal_paper_outcome_tracking_bridge.ndjson", _r236_bridge_record())
    _append(log_dir / "betrayal_true_inverse_outcome_capture_bridge.ndjson", _r237_capture_record())
    _append(log_dir / "paper_outcomes.ndjson", {"signal_id": "ordinary-signal", "outcome": "win"})
    _append(log_dir / "strategy_performance.ndjson", {"lane_key": "ordinary", "sample_size": 30, "win_rate_pct": 60.0})
    _append(log_dir / "strategy_promotion_status.ndjson", {"lane_key": "ordinary", "promotion_allowed": False})
    return log_dir


def _r237_ready_row() -> dict[str, object]:
    return {
        "schema_version": "betrayal_true_inverse_outcome_capture_bridge_v1",
        "capture_id": "capture-ready-1",
        "capture_status": "TRUE_INVERSE_CAPTURE_READY",
        "signal_origin_family": "betrayal",
        "signal_origin_type": "inverse",
        "signal_origin_variant": "betrayal_inverse",
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "original_direction": "long",
        "inverse_direction": "short",
        "entry_mode": "ladder_close_50_618",
        "lane_key": OFFICIAL,
        "signal_id": "signal-ready-1",
        "source_signal_id": "source-ready-1",
        "source_identity": "betrayal_source_emitter_v2|fixture",
        "paper_outcome_tracking_identity": "betrayal-outcome-ready-1",
        "outcome_window_spec": [1, 3, 5],
        "true_inverse_outcome_found": False,
        "result_pending": True,
        "ranking_projection_ready": True,
        "live_authorized": False,
        "promotion_allowed": False,
    }


def _r237_capture_record() -> dict[str, object]:
    rows = [
        _r237_ready_row(),
        {
            **_r237_ready_row(),
            "capture_id": "capture-entry-missing",
            "capture_status": "NEEDS_ENTRY_MODE",
            "signal_id": "signal-entry-missing",
            "source_signal_id": "source-entry-missing",
            "paper_outcome_tracking_identity": "betrayal-outcome-entry-missing",
            "entry_mode": "entry_unknown",
            "lane_key": "BTCUSDT|8m|short|entry_unknown",
            "ranking_projection_ready": False,
            "blockers": ["missing_entry_mode", "missing_lane_key"],
        },
        {
            **_r237_ready_row(),
            "capture_id": "capture-outcome-missing",
            "capture_status": "NEEDS_OUTCOME_IDENTITY",
            "signal_id": "signal-outcome-missing",
            "source_signal_id": "source-outcome-missing",
            "paper_outcome_tracking_identity": None,
            "ranking_projection_ready": False,
            "blockers": ["missing_outcome_identity"],
        },
        {
            **_r237_ready_row(),
            "capture_id": "capture-source-missing",
            "capture_status": "NEEDS_SOURCE_SIGNAL",
            "signal_id": None,
            "source_signal_id": None,
            "source_identity": "betrayal_source_emitter_v2|source-missing",
            "ranking_projection_ready": False,
            "blockers": ["missing_source_signal"],
        },
    ]
    return {
        "event_type": "BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE",
        "capture_bridge_record_id": "r237_fixture",
        "status": "BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_RECORDED",
        "target_scope": {
            "paper_only": True,
            "live_authorized": False,
            "official_tiny_live_lane": OFFICIAL,
            "official_tiny_live_lane_changed": False,
        },
        "official_tiny_live_status": {
            "lane_key": OFFICIAL,
            "fresh_capture_count": 8,
            "required_fresh_capture_count": 10,
            "threshold_met": False,
            "threshold_distance_remaining": 2,
            "recommended_action": "WAIT_FOR_10_OF_10",
        },
        "true_inverse_capture_preview_rows": rows,
        "capture_summary": {"rows_reviewed": 4, "ranking_projection_ready_rows": 1},
        "capture_overall_status": "BETRAYAL_TRUE_INVERSE_CAPTURE_NEEDS_ENTRY_MODE",
        "safety": {"paper_outcomes_appended": False, "config_written": False, "order_placed": False},
    }


def _r236_bridge_record() -> dict[str, object]:
    return {
        "event_type": "BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE",
        "bridge_record_id": "r236_fixture",
        "status": "BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_RECORDED",
        "target_scope": {"paper_only": True, "live_authorized": False, "official_tiny_live_lane": OFFICIAL},
        "official_tiny_live_status": {
            "lane_key": OFFICIAL,
            "fresh_capture_count": 8,
            "required_fresh_capture_count": 10,
            "threshold_met": False,
            "threshold_distance_remaining": 2,
            "recommended_action": "WAIT_FOR_10_OF_10",
        },
        "bridge_preview_rows": [{"signal_origin_family": "betrayal", "signal_id": "signal-ready-1"}],
        "bridge_summary": {"rows_reviewed": 1, "bridge_ready_rows": 1},
    }


def _r235_contract_record() -> dict[str, object]:
    return {
        "event_type": "BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT",
        "contract_id": "r235_fixture",
        "status": "BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_RECORDED",
        "target_scope": {"paper_only": True, "live_authorized": False, "official_tiny_live_lane": OFFICIAL},
        "same_flow_readiness_rows": [{"signal_origin_family": "betrayal", "signal_id": "signal-ready-1"}],
        "same_flow_summary": {"rows_reviewed": 1},
    }


def _capture_sync_record(fresh: int) -> dict[str, object]:
    return {
        "capture_count": {
            "fresh_capture_count": fresh,
            "required_fresh_capture_count": 10,
            "threshold_met": fresh >= 10,
        },
        "watcher_status": {"watcher_likely_running": True, "watcher_stale": False},
        "threshold_status": "CAPTURE_THRESHOLD_MET" if fresh >= 10 else "CAPTURE_THRESHOLD_NOT_MET",
    }


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
