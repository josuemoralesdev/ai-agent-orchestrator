import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_true_inverse_outcome_capture_bridge import (
    BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_RECORDED,
    BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_REJECTED,
    CONFIRM_BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_RECORDING_PHRASE,
    TRUE_INVERSE_CAPTURE_READY,
    build_betrayal_true_inverse_outcome_capture_bridge,
    infer_inverse_direction,
    load_betrayal_true_inverse_outcome_capture_bridge_records,
    normalize_betrayal_bridge_row_for_true_inverse_capture,
)

NOW = datetime(2026, 6, 8, 22, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_betrayal_true_inverse_outcome_capture_bridge(log_dir=log_dir, now=NOW)

    assert payload["capture_bridge_recorded"] is False
    assert payload["record_capture_bridge_requested"] is False
    assert load_betrayal_true_inverse_outcome_capture_bridge_records(log_dir=log_dir, limit=0) == []
    assert payload["target_scope"]["true_inverse_capture_preview_only"] is True
    assert payload["safety"]["capture_bridge_preview_ledger_only"] is True


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_betrayal_true_inverse_outcome_capture_bridge(
        log_dir=log_dir,
        record_capture_bridge=True,
        confirm_betrayal_true_inverse_outcome_capture_bridge="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["capture_bridge_recorded"] is False
    assert load_betrayal_true_inverse_outcome_capture_bridge_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_capture_bridge_preview_only(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    protected_paths = {
        "lane_controls": tmp_path / "configs" / "hammer_radar" / "lane_controls.json",
        "risk_contracts": tmp_path / "configs" / "hammer_radar" / "tiny_live_risk_contracts.json",
        "paper_outcomes": log_dir / "paper_outcomes.ndjson",
    }
    for path in protected_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    before = {name: path.read_text(encoding="utf-8") for name, path in protected_paths.items()}

    payload = build_betrayal_true_inverse_outcome_capture_bridge(
        log_dir=log_dir,
        record_capture_bridge=True,
        confirm_betrayal_true_inverse_outcome_capture_bridge=(
            CONFIRM_BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_RECORDING_PHRASE
        ),
        now=NOW,
    )

    records = load_betrayal_true_inverse_outcome_capture_bridge_records(log_dir=log_dir, limit=0)
    assert payload["status"] == BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_RECORDED
    assert payload["capture_bridge_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE"
    assert {name: path.read_text(encoding="utf-8") for name, path in protected_paths.items()} == before
    assert records[0]["safety"]["paper_outcomes_appended"] is False
    assert records[0]["safety"]["config_written"] is False
    assert records[0]["safety"]["order_placed"] is False


def test_capture_bridge_reads_r236_bridge_ready_rows(tmp_path: Path) -> None:
    payload = build_betrayal_true_inverse_outcome_capture_bridge(log_dir=_fixture_logs(tmp_path), now=NOW)

    assert payload["input_summary"]["betrayal_outcome_bridge_found"] is True
    assert payload["capture_summary"]["rows_reviewed"] == 3
    ready_rows = [
        row for row in payload["true_inverse_capture_preview_rows"] if row["capture_status"] == TRUE_INVERSE_CAPTURE_READY
    ]
    assert [row["signal_id"] for row in ready_rows] == ["signal-ready-1"]


def test_true_inverse_direction_is_correctly_inferred() -> None:
    assert infer_inverse_direction("long") == "short"
    assert infer_inverse_direction("short") == "long"
    assert infer_inverse_direction("unknown") is None

    row = normalize_betrayal_bridge_row_for_true_inverse_capture(
        _r236_ready_row(),
        schema_context={"registry_valid_entry_modes": ["ladder_close_50_618"], "outcome_window_convention": [1, 3, 5]},
    )
    assert row["original_direction"] == "long"
    assert row["inverse_direction"] == "short"


def test_true_inverse_capture_ready_requires_bridge_ready_and_paper_outcome_identity() -> None:
    context = {"registry_valid_entry_modes": ["ladder_close_50_618"], "outcome_window_convention": [1, 3, 5]}
    no_bridge = normalize_betrayal_bridge_row_for_true_inverse_capture(
        {**_r236_ready_row(), "bridge_status": "NEEDS_ENTRY_MODE"},
        schema_context=context,
    )
    no_identity = normalize_betrayal_bridge_row_for_true_inverse_capture(
        {**_r236_ready_row(), "paper_outcome_tracking_identity": None},
        schema_context=context,
    )

    assert normalize_betrayal_bridge_row_for_true_inverse_capture(_r236_ready_row(), schema_context=context)[
        "capture_status"
    ] == TRUE_INVERSE_CAPTURE_READY
    assert no_bridge["capture_status"] != TRUE_INVERSE_CAPTURE_READY
    assert "bridge_not_ready" in no_bridge["blockers"]
    assert no_identity["capture_status"] == "NEEDS_OUTCOME_IDENTITY"
    assert "missing_outcome_identity" in no_identity["blockers"]


def test_ranking_projection_does_not_imply_promotion(tmp_path: Path) -> None:
    payload = build_betrayal_true_inverse_outcome_capture_bridge(log_dir=_fixture_logs(tmp_path), now=NOW)
    ready = next(row for row in payload["true_inverse_capture_preview_rows"] if row["capture_status"] == TRUE_INVERSE_CAPTURE_READY)

    assert ready["ranking_projection_ready"] is True
    assert payload["ranking_projection"]["can_feed_ranking_after_outcomes"] is True
    assert payload["ranking_projection"]["promotion_path_blocked"] is True
    assert ready["promotion_allowed"] is False
    assert ready["live_authorized"] is False


def test_promotion_review_ready_and_live_ready_today_always_false(tmp_path: Path) -> None:
    payload = build_betrayal_true_inverse_outcome_capture_bridge(log_dir=_fixture_logs(tmp_path), now=NOW)

    assert payload["capture_summary"]["promotion_review_ready_rows"] == 0
    assert payload["capture_summary"]["live_ready_today_rows"] == 0
    assert all(row["promotion_review_ready"] is False for row in payload["true_inverse_capture_preview_rows"])
    assert all(row["live_ready_today"] is False for row in payload["true_inverse_capture_preview_rows"])


def test_true_inverse_outcomes_are_not_fabricated(tmp_path: Path) -> None:
    payload = build_betrayal_true_inverse_outcome_capture_bridge(log_dir=_fixture_logs(tmp_path), now=NOW)

    assert payload["input_summary"]["betrayal_true_paper_outcomes_found"] is False
    assert payload["capture_summary"]["true_inverse_outcome_found_rows"] == 0
    assert all(row["true_inverse_outcome_found"] is False for row in payload["true_inverse_capture_preview_rows"])
    assert payload["safety"]["true_inverse_outcomes_fabricated"] is False


def test_existing_true_inverse_outcome_is_detected_without_fabrication(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    _append(
        log_dir / "betrayal_true_paper_outcomes.ndjson",
        {
            "paper_outcome_tracking_identity": "betrayal-outcome-ready-1",
            "signal_id": "signal-ready-1",
            "outcome_status": "resolved",
        },
    )

    payload = build_betrayal_true_inverse_outcome_capture_bridge(log_dir=log_dir, now=NOW)

    assert payload["input_summary"]["betrayal_true_paper_outcomes_found"] is True
    assert payload["capture_summary"]["true_inverse_outcome_found_rows"] == 1
    found = next(row for row in payload["true_inverse_capture_preview_rows"] if row["signal_id"] == "signal-ready-1")
    assert found["true_inverse_outcome_found"] is True
    assert found["result_pending"] is False
    assert payload["safety"]["true_inverse_outcomes_fabricated"] is False


def test_paper_outcomes_not_rewritten_or_appended(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    paper_outcomes = log_dir / "paper_outcomes.ndjson"
    before = paper_outcomes.read_text(encoding="utf-8")

    payload = build_betrayal_true_inverse_outcome_capture_bridge(
        log_dir=log_dir,
        record_capture_bridge=True,
        confirm_betrayal_true_inverse_outcome_capture_bridge=(
            CONFIRM_BETRAYAL_TRUE_INVERSE_OUTCOME_CAPTURE_BRIDGE_RECORDING_PHRASE
        ),
        now=NOW,
    )

    assert paper_outcomes.read_text(encoding="utf-8") == before
    assert payload["safety"]["paper_outcome_ledger_rewritten"] is False
    assert payload["safety"]["paper_outcomes_appended"] is False
    assert payload["safety"]["historical_ledger_rewritten"] is False


def test_live_ready_official_lane_unchanged_and_no_promotions(tmp_path: Path) -> None:
    payload = build_betrayal_true_inverse_outcome_capture_bridge(log_dir=_fixture_logs(tmp_path), now=NOW)
    safety = payload["safety"]

    assert payload["target_scope"]["official_tiny_live_lane"] == OFFICIAL
    assert payload["target_scope"]["official_tiny_live_lane_changed"] is False
    assert payload["official_tiny_live_status"]["fresh_capture_count"] == 8
    assert payload["official_tiny_live_status"]["threshold_met"] is False
    assert safety["betrayal_promoted"] is False
    assert safety["signal_origin_promoted"] is False
    assert safety["lane_promoted"] is False
    assert safety["betrayal_live_authorized"] is False


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
        payload = build_betrayal_true_inverse_outcome_capture_bridge(log_dir=_fixture_logs(tmp_path), now=NOW)

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
        "normalized_rows_appended",
        "paper_outcomes_appended",
        "true_inverse_outcomes_fabricated",
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
            "betrayal-true-inverse-outcome-capture-bridge",
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["target_scope"]["paper_only"] is True
    assert payload["capture_bridge_recorded"] is False
    assert payload["capture_summary"]["true_inverse_capture_ready_rows"] == 1


def _fixture_logs(tmp_path: Path) -> Path:
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    _append(log_dir / "capture_count_sync_8m_short.ndjson", _capture_sync_record(8))
    _append(log_dir / "betrayal_gate_ready_lane_packet.ndjson", _gate_packet_record())
    _append(log_dir / "betrayal_signal_origin_integration_contract.ndjson", _r235_contract_record())
    _append(log_dir / "betrayal_paper_outcome_tracking_bridge.ndjson", _r236_bridge_record())
    _append(log_dir / "paper_outcomes.ndjson", {"signal_id": "ordinary-signal", "outcome": "win"})
    _append(log_dir / "outcomes.ndjson", {"signal_id": "ordinary-signal", "outcome": "win"})
    return log_dir


def _r236_ready_row() -> dict[str, object]:
    return {
        "schema_version": "betrayal_paper_outcome_bridge_preview_v1",
        "bridge_id": "bridge-ready-1",
        "bridge_status": "BRIDGE_READY",
        "signal_origin_family": "betrayal",
        "signal_origin_type": "inverse",
        "signal_origin_variant": "betrayal_inverse",
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "entry_mode": "ladder_close_50_618",
        "lane_key": OFFICIAL,
        "signal_id": "signal-ready-1",
        "source_signal_id": "source-ready-1",
        "source_identity": "betrayal_source_emitter_v2|fixture",
        "paper_outcome_tracking_identity": "betrayal-outcome-ready-1",
        "outcome_window_spec": [1, 3, 5],
        "paper_signal_ready": True,
        "paper_outcome_ready": True,
        "outcome_tracking_ready": True,
        "ranking_feed_ready": True,
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
    }


def _r236_bridge_record() -> dict[str, object]:
    rows = [
        _r236_ready_row(),
        {
            **_r236_ready_row(),
            "bridge_id": "bridge-entry-missing",
            "bridge_status": "NEEDS_ENTRY_MODE",
            "signal_id": "signal-entry-missing",
            "source_signal_id": "source-entry-missing",
            "source_identity": "betrayal_source_emitter_v2|entry-missing",
            "paper_outcome_tracking_identity": "betrayal-outcome-entry-missing",
            "entry_mode": "entry_unknown",
            "lane_key": "BTCUSDT|8m|short|entry_unknown",
            "paper_signal_ready": False,
            "paper_outcome_ready": False,
            "outcome_tracking_ready": False,
            "ranking_feed_ready": False,
            "blockers": ["missing_entry_mode", "missing_lane_key"],
        },
        {
            **_r236_ready_row(),
            "bridge_id": "bridge-outcome-missing",
            "bridge_status": "NEEDS_OUTCOME_IDENTITY",
            "signal_id": "signal-outcome-missing",
            "source_signal_id": "source-outcome-missing",
            "source_identity": "betrayal_source_emitter_v2|outcome-missing",
            "paper_outcome_tracking_identity": None,
            "paper_outcome_ready": False,
            "outcome_tracking_ready": False,
            "ranking_feed_ready": False,
            "blockers": ["missing_outcome_identity"],
        },
    ]
    return {
        "event_type": "BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE",
        "bridge_record_id": "r236_fixture",
        "status": "BETRAYAL_PAPER_OUTCOME_TRACKING_BRIDGE_RECORDED",
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
        "bridge_preview_rows": rows,
        "bridge_summary": {"rows_reviewed": 3, "bridge_ready_rows": 1},
        "bridge_overall_status": "BETRAYAL_OUTCOME_BRIDGE_NEEDS_ENTRY_MODE",
        "safety": {"paper_outcomes_appended": False, "config_written": False, "order_placed": False},
    }


def _r235_contract_record() -> dict[str, object]:
    return {
        "event_type": "BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT",
        "contract_id": "r235_fixture",
        "status": "BETRAYAL_SIGNAL_ORIGIN_INTEGRATION_CONTRACT_RECORDED",
        "target_scope": {"paper_only": True, "live_authorized": False, "official_tiny_live_lane": OFFICIAL},
        "same_flow_readiness_rows": [
            {
                "signal_origin_family": "betrayal",
                "signal_id": "signal-ready-1",
                "paper_signal_ready": True,
                "paper_outcome_ready": True,
            }
        ],
        "same_flow_summary": {"rows_reviewed": 1},
        "integration_status": "BETRAYAL_SAME_FLOW_NEEDS_ENTRY_MODE",
        "safety": {"config_written": False, "order_placed": False},
    }


def _gate_packet_record() -> dict[str, object]:
    return {
        "event_type": "BETRAYAL_GATE_READY_LANE_PACKET",
        "packet_id": "r234_fixture",
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
        "betrayal_candidate_lane_registry": [{"candidate": "fixture inverse", "lane_key": OFFICIAL}],
        "recommended_next_operator_move": "WAIT_FOR_10_OF_10",
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
