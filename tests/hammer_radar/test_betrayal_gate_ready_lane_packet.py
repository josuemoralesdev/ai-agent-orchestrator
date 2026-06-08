import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.betrayal_gate_ready_lane_packet import (
    BETRAYAL_GATE_READY_LANE_PACKET_RECORDED,
    BETRAYAL_GATE_READY_LANE_PACKET_REJECTED,
    CONFIRM_BETRAYAL_GATE_READY_LANE_PACKET_RECORDING_PHRASE,
    build_betrayal_gate_ready_lane_packet,
    load_betrayal_gate_ready_lane_packet_records,
)

NOW = datetime(2026, 6, 8, 19, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_betrayal_gate_ready_lane_packet(log_dir=log_dir, now=NOW)

    assert payload["packet_recorded"] is False
    assert payload["record_packet_requested"] is False
    assert load_betrayal_gate_ready_lane_packet_records(log_dir=log_dir, limit=0) == []
    assert payload["target_scope"]["paper_only"] is True
    assert payload["target_scope"]["betrayal_shadow_active"] is True


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_betrayal_gate_ready_lane_packet(
        log_dir=log_dir,
        record_packet=True,
        confirm_betrayal_gate_ready_lane_packet="wrong",
        now=NOW,
    )

    assert payload["status"] == BETRAYAL_GATE_READY_LANE_PACKET_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["packet_recorded"] is False
    assert load_betrayal_gate_ready_lane_packet_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_packet_only(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    protected_paths = {
        "lane_controls": log_dir.parent / "configs" / "hammer_radar" / "lane_controls.json",
        "risk_contracts": log_dir.parent / "configs" / "hammer_radar" / "tiny_live_risk_contracts.json",
        "paper_outcomes": log_dir / "paper_outcomes.ndjson",
    }
    for path in protected_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    before = {name: path.read_text(encoding="utf-8") for name, path in protected_paths.items()}

    payload = build_betrayal_gate_ready_lane_packet(
        log_dir=log_dir,
        record_packet=True,
        confirm_betrayal_gate_ready_lane_packet=CONFIRM_BETRAYAL_GATE_READY_LANE_PACKET_RECORDING_PHRASE,
        now=NOW,
    )

    records = load_betrayal_gate_ready_lane_packet_records(log_dir=log_dir, limit=0)
    assert payload["status"] == BETRAYAL_GATE_READY_LANE_PACKET_RECORDED
    assert payload["packet_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "BETRAYAL_GATE_READY_LANE_PACKET"
    assert {name: path.read_text(encoding="utf-8") for name, path in protected_paths.items()} == before
    assert records[0]["safety"]["config_written"] is False
    assert records[0]["safety"]["paper_outcome_ledger_rewritten"] is False
    assert records[0]["safety"]["order_placed"] is False


def test_betrayal_context_is_active_not_closed_and_packet_is_produced(tmp_path: Path) -> None:
    payload = build_betrayal_gate_ready_lane_packet(log_dir=_fixture_logs(tmp_path), now=NOW)

    assert payload["target_scope"]["betrayal_shadow_active"] is True
    assert payload["target_scope"]["betrayal_gate_prepared"] is True
    assert payload["gate_packet_status"] != "CLOSED_FOR_NOW"
    assert payload["betrayal_candidate_lane_registry"]
    assert payload["betrayal_activation_gate_checklist"]["all_requirements_known"] is True
    assert payload["betrayal_activation_gate_checklist"]["live_ready_today"] is False


def test_gate_ready_does_not_imply_live_readiness_or_promotion(tmp_path: Path) -> None:
    payload = build_betrayal_gate_ready_lane_packet(log_dir=_fixture_logs(tmp_path), now=NOW)

    assert payload["betrayal_auto_open_readiness_packet"]["can_auto_open_today"] is False
    assert payload["betrayal_auto_open_readiness_packet"]["can_wait_at_gate"] is True
    assert payload["target_scope"]["live_authorized"] is False
    assert payload["safety"]["betrayal_live_authorized"] is False
    assert payload["safety"]["betrayal_promoted"] is False
    assert payload["safety"]["lane_promoted"] is False


def test_official_tiny_live_lane_remains_unchanged_and_r228_only_at_10_of_10(tmp_path: Path) -> None:
    payload = build_betrayal_gate_ready_lane_packet(log_dir=_fixture_logs(tmp_path), now=NOW)

    assert payload["target_scope"]["official_tiny_live_lane"] == OFFICIAL
    assert payload["target_scope"]["official_tiny_live_lane_changed"] is False
    assert payload["official_tiny_live_status"]["fresh_capture_count"] == 8
    assert payload["official_tiny_live_status"]["threshold_met"] is False
    assert payload["official_tiny_live_status"]["recommended_action"] == "WAIT_FOR_10_OF_10"
    assert payload["recommended_next_operator_move"] == "WAIT_FOR_10_OF_10"

    log_dir = _fixture_logs(tmp_path / "met")
    _append(
        log_dir / "capture_count_sync_8m_short.ndjson",
        {
            "capture_count": {"fresh_capture_count": 10, "required_fresh_capture_count": 10, "threshold_met": True},
            "watcher_status": {"watcher_likely_running": True, "watcher_stale": False},
        },
    )
    _append(
        log_dir / "capture_priority_rebalance.ndjson",
        {
            **_capture_priority_record(),
            "official_protected_path_summary": {
                "lane_key": OFFICIAL,
                "fresh_capture_count": 10,
                "required_fresh_capture_count": 10,
                "threshold_met": True,
                "threshold_distance_remaining": 0,
                "recommended_action": "KEEP_AS_OFFICIAL_AND_WAIT_FOR_10_OF_10",
            },
        },
    )
    ready = build_betrayal_gate_ready_lane_packet(log_dir=log_dir, now=NOW)
    assert ready["official_tiny_live_status"]["recommended_action"] == "RUN_R228_IF_10_OF_10"
    assert ready["recommended_next_operator_move"] == "RUN_R228_TINY_LIVE_10_OF_10_READY_PACKET"


def test_222m_and_88m_betrayal_context_are_preserved_when_present(tmp_path: Path) -> None:
    payload = build_betrayal_gate_ready_lane_packet(log_dir=_fixture_logs(tmp_path), now=NOW)
    lanes = {row["lane_key"]: row for row in payload["betrayal_candidate_lane_registry"]}

    assert "BTCUSDT|222m|long|ladder_close_50_618" in lanes
    assert "BTCUSDT|88m|inverse|entry_unknown" in lanes
    assert lanes["BTCUSDT|222m|long|ladder_close_50_618"]["win_rate_pct"] == 87.5
    assert lanes["BTCUSDT|88m|inverse|entry_unknown"]["win_rate_pct"] == 63.33


def test_missing_entry_mode_and_lane_key_remain_blockers(tmp_path: Path) -> None:
    payload = build_betrayal_gate_ready_lane_packet(log_dir=_fixture_logs(tmp_path), now=NOW)
    rows = payload["betrayal_candidate_lane_registry"]

    assert any(row["gate_preparation_status"] == "NEEDS_ENTRY_MODE" for row in rows)
    assert any(row["entry_mode"] == "entry_unknown" for row in rows)
    assert "entry_mode_missing" in payload["betrayal_auto_open_readiness_packet"]["blocked_by"]


def test_no_fisherman_scheduler_env_config_or_destructive_mutation(tmp_path: Path) -> None:
    before_env = dict(os.environ)
    payload = build_betrayal_gate_ready_lane_packet(log_dir=_fixture_logs(tmp_path), now=NOW)
    safety = payload["safety"]

    assert dict(os.environ) == before_env
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
        "paper_outcome_ledger_rewritten",
    ):
        assert safety[key] is False


def test_no_binance_network_order_live_transfer_or_withdraw_actions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = _fixture_logs(tmp_path)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_betrayal_gate_ready_lane_packet(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    for key in (
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
            "betrayal-gate-ready-lane-packet",
        ],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["target_scope"]["paper_only"] is True
    assert payload["packet_recorded"] is False


def _fixture_logs(tmp_path: Path) -> Path:
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    _append(log_dir / "capture_count_sync_8m_short.ndjson", _capture_sync_record(8))
    _append(log_dir / "capture_priority_rebalance.ndjson", _capture_priority_record())
    _append(
        log_dir / "betrayal_upstream_emitter_entry_mode_contract.ndjson",
        {
            "contract_id": "r230_fixture",
            "future_emitter_contract_readiness_report": {
                "surfaces_inspected": 5,
                "surfaces_future_contract_ready": 1,
                "surfaces_partially_ready": 4,
            },
            "upstream_contract_gap_report": {"resolver_ready_preview_rows": 0},
            "safety": {"config_written": False, "order_placed": False},
        },
    )
    _append(
        log_dir / "betrayal_entry_mode_source_propagation.ndjson",
        {
            "propagation_id": "r229_fixture",
            "entry_mode_propagated_rows_preview": [
                {
                    "candidate": "222m aggregate",
                    "symbol": "BTCUSDT",
                    "timeframe": "222m",
                    "emitted_direction": "short",
                    "entry_mode": None,
                    "lane_key_preview": None,
                    "source_identity": "betrayal_source_emitter_v2|fixture",
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                }
            ],
            "source_propagation_gap_report": {"missing_entry_mode_rows": 1, "missing_lane_key_rows": 1},
        },
    )
    _append(
        log_dir / "betrayal_direction_completion.ndjson",
        {
            "completion_id": "r227_fixture",
            "direction_completed_rows_preview": [
                {
                    "candidate": "222m aggregate",
                    "symbol": "BTCUSDT",
                    "timeframe": "222m",
                    "entry_mode": "ladder_close_50_618",
                    "inverse_direction": "long",
                    "emitted_direction": "long",
                    "lane_key_preview": "BTCUSDT|222m|long|ladder_close_50_618",
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                }
            ],
        },
    )
    _append(
        log_dir / "weekend_paper_fisherman_supervisor.ndjson",
        {
            "betrayal_watch_summary": {
                "betrayal_context_included": True,
                "latest_222m_capture_lane": "BTCUSDT|222m|long|ladder_close_50_618",
                "primary_betrayal_candidate": "222m aggregate",
                "primary_betrayal_naive_inverse_win_rate_pct": 87.5,
                "watchlist_betrayal_candidate": "88m aggregate",
                "watchlist_betrayal_naive_inverse_win_rate_pct": 63.33,
            },
            "fisherman_health": {"fisherman_status": "FISHERMAN_RUNNING_RECENT"},
        },
    )
    _append(
        log_dir / "betrayal_shadow_outcomes.ndjson",
        {
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "shadow_direction": "long",
            "betrayal_tier": "STRONG_BETRAYAL_WATCH",
            "shadow_only": True,
            "order_placed": False,
            "original_signal_id": "BTCUSDT|8m|short|2026-06-08T18:31:59.999000+00:00",
        },
    )
    return log_dir


def _capture_priority_record() -> dict[str, object]:
    return {
        "rebalance_id": "r233_fixture",
        "target_scope": {
            "paper_only": True,
            "live_authorized": False,
            "official_tiny_live_lane": OFFICIAL,
            "official_tiny_live_lane_changed": False,
            "betrayal_shadow_preserved": True,
        },
        "official_protected_path_summary": {
            "lane_key": OFFICIAL,
            "fresh_capture_count": 8,
            "required_fresh_capture_count": 10,
            "threshold_met": False,
            "threshold_distance_remaining": 2,
            "recommended_action": "KEEP_AS_OFFICIAL_AND_WAIT_FOR_10_OF_10",
        },
        "betrayal_shadow_context": {
            "preserved": True,
            "status": "CONTEXT_ONLY",
            "candidate_lanes": [
                {
                    "candidate": "222m aggregate",
                    "symbol": "BTCUSDT",
                    "timeframe": "222m",
                    "direction": "long",
                    "entry_mode": "ladder_close_50_618",
                    "lane_key": "BTCUSDT|222m|long|ladder_close_50_618",
                    "source": "weekend_supervisor",
                    "win_rate_pct": 87.5,
                },
                {
                    "candidate": "88m aggregate",
                    "symbol": "BTCUSDT",
                    "timeframe": "88m",
                    "direction": "inverse",
                    "entry_mode": "entry_unknown",
                    "lane_key": "BTCUSDT|88m|inverse|entry_unknown",
                    "source": "weekend_supervisor",
                    "win_rate_pct": 63.33,
                },
            ],
        },
        "safety": {"config_written": False, "order_placed": False},
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
