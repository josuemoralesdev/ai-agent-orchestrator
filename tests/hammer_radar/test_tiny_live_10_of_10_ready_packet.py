from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_10_of_10_ready_packet import (
    CONFIRM_TINY_LIVE_10_OF_10_READY_PACKET_RECORDING_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_10_OF_10_BLOCKED_BY_FISHERMAN_STALE,
    TINY_LIVE_10_OF_10_BLOCKED_BY_RISK_CONTRACT,
    TINY_LIVE_10_OF_10_NOT_MET,
    TINY_LIVE_10_OF_10_READY_PACKET_RECORDED,
    TINY_LIVE_10_OF_10_READY_PACKET_REJECTED,
    build_capture_threshold_recheck,
    build_tiny_live_10_of_10_ready_packet,
    load_tiny_live_10_of_10_ready_packet_records,
)

NOW = datetime(2026, 6, 9, 3, 5, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_tiny_live_10_of_10_ready_packet(log_dir=log_dir, now=NOW)

    assert payload["packet_recorded"] is False
    assert payload["record_packet_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_tiny_live_10_of_10_ready_packet(
        log_dir=log_dir,
        record_packet=True,
        confirm_tiny_live_10_of_10_ready_packet="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_10_OF_10_READY_PACKET_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["packet_recorded"] is False
    assert load_tiny_live_10_of_10_ready_packet_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_packet_only(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    protected = {
        "paper_outcomes": log_dir / "paper_outcomes.ndjson",
        "strategy_performance": log_dir / "strategy_performance.ndjson",
        "strategy_promotion_status": log_dir / "strategy_promotion_status.ndjson",
    }
    before = {name: path.read_text(encoding="utf-8") for name, path in protected.items()}

    payload = build_tiny_live_10_of_10_ready_packet(
        log_dir=log_dir,
        record_packet=True,
        confirm_tiny_live_10_of_10_ready_packet=CONFIRM_TINY_LIVE_10_OF_10_READY_PACKET_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_tiny_live_10_of_10_ready_packet_records(log_dir=log_dir, limit=0)

    assert payload["status"] == TINY_LIVE_10_OF_10_READY_PACKET_RECORDED
    assert payload["packet_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "TINY_LIVE_10_OF_10_READY_PACKET"
    assert {name: path.read_text(encoding="utf-8") for name, path in protected.items()} == before
    assert records[0]["safety"]["risk_contract_config_written"] is False
    assert records[0]["safety"]["order_payload_created"] is False


def test_status_ready_when_official_capture_count_10_of_10_and_watcher_fresh(tmp_path: Path) -> None:
    payload = build_tiny_live_10_of_10_ready_packet(log_dir=_fixture_logs(tmp_path), now=NOW)

    assert payload["capture_threshold_recheck"]["fresh_capture_count"] == 10
    assert payload["capture_threshold_recheck"]["required_fresh_capture_count"] == 10
    assert payload["capture_threshold_recheck"]["threshold_met"] is True
    assert payload["capture_threshold_recheck"]["unique_capture_count"] == 10
    assert payload["capture_threshold_recheck"]["evidence_threshold_ready"] is True
    assert payload["fisherman_health_recheck"]["fisherman_ready"] is True
    assert payload["tiny_live_gate_matrix"]["evidence_ready"] is True
    assert payload["tiny_live_gate_matrix"]["fisherman_ready"] is True
    assert payload["tiny_live_gate_matrix"]["operator_review_ready"] is True
    assert payload["ready_packet_overall_status"] == TINY_LIVE_10_OF_10_BLOCKED_BY_RISK_CONTRACT


def test_status_not_ready_when_capture_count_below_10(tmp_path: Path) -> None:
    payload = build_tiny_live_10_of_10_ready_packet(log_dir=_fixture_logs(tmp_path, fresh_count=9), now=NOW)

    assert payload["capture_threshold_recheck"]["fresh_capture_count"] == 9
    assert payload["tiny_live_gate_matrix"]["evidence_ready"] is False
    assert payload["ready_packet_overall_status"] == TINY_LIVE_10_OF_10_NOT_MET


def test_status_blocked_when_watcher_stale(tmp_path: Path) -> None:
    payload = build_tiny_live_10_of_10_ready_packet(log_dir=_fixture_logs(tmp_path, watcher_stale=True), now=NOW)

    assert payload["fisherman_health_recheck"]["watcher_stale"] is True
    assert payload["tiny_live_gate_matrix"]["fisherman_ready"] is False
    assert payload["ready_packet_overall_status"] == TINY_LIVE_10_OF_10_BLOCKED_BY_FISHERMAN_STALE


def test_official_lane_key_cannot_change() -> None:
    recheck = build_capture_threshold_recheck(
        {
            "target_family": {"lane_key": "BTCUSDT|8m|long|ladder_close_50_618"},
            "capture_count": _capture_count(10),
            "threshold_status": "CAPTURE_THRESHOLD_MET",
        },
        official_lane_key=OFFICIAL,
    )

    assert recheck["official_lane_key"] == "BTCUSDT|8m|long|ladder_close_50_618"
    assert recheck["official_lane_unchanged"] is False
    assert recheck["evidence_threshold_ready"] is False


def test_old_r177_recommendation_is_reconciled_to_r228_modern_path(tmp_path: Path) -> None:
    payload = build_tiny_live_10_of_10_ready_packet(log_dir=_fixture_logs(tmp_path), now=NOW)
    recheck = payload["capture_threshold_recheck"]

    assert recheck["old_recommendation_reconciled"] == "RUN_R177_EVIDENCE_THRESHOLD_RECHECK"
    assert recheck["modern_path"] == "R228_TINY_LIVE_10_OF_10_READY_PACKET"


def test_evidence_ready_does_not_imply_live_or_order_readiness(tmp_path: Path) -> None:
    payload = build_tiny_live_10_of_10_ready_packet(log_dir=_fixture_logs(tmp_path), now=NOW)
    gates = payload["tiny_live_gate_matrix"]

    assert gates["evidence_ready"] is True
    assert gates["risk_contract_ready"] is False
    assert gates["live_authorization_ready"] is False
    assert gates["live_execution_ready"] is False
    assert gates["order_ready"] is False
    assert gates["live_ready_today"] is False
    assert payload["operator_ready_packet"]["operator_should_place_order"] is False
    assert payload["operator_ready_packet"]["operator_should_enable_live"] is False


def test_order_payload_never_created_and_no_mutations_or_promotions(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = _fixture_logs(tmp_path)
    before_env = dict(os.environ)
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_tiny_live_10_of_10_ready_packet(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert dict(os.environ) == before_env
    for key in (
        "env_written",
        "env_mutated",
        "config_written",
        "risk_contract_config_written",
        "lane_config_written",
        "fisherman_config_written",
        "scheduler_config_written",
        "ledger_rewritten",
        "destructive_write",
        "historical_ledger_rewritten",
        "paper_outcomes_appended",
        "strategy_performance_appended",
        "strategy_promotion_status_appended",
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
        "live_authorization_created",
        "live_execution_enabled",
        "global_live_flags_changed",
        "kill_switch_disabled",
        "lane_promoted",
        "official_tiny_live_lane_changed",
        "alternate_lane_promoted",
        "betrayal_live_authorized",
        "betrayal_promoted",
        "position_permission_created",
    ):
        assert payload["safety"][key] is False
    assert payload["safety"]["paper_live_separation_intact"] is True


def test_track_b_context_remains_passive(tmp_path: Path) -> None:
    payload = build_tiny_live_10_of_10_ready_packet(log_dir=_fixture_logs(tmp_path), now=NOW)
    track_b = payload["track_b_context"]

    assert track_b["track_b_structurally_complete_for_now"] is True
    assert track_b["waiting_for_data_not_architecture"] is True
    assert track_b["betrayal_live_authorized"] is False
    assert track_b["betrayal_promoted"] is False
    assert track_b["track_b_action_required_now"] is False


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-10-of-10-ready-packet",
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
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["packet_recorded"] is False
    assert "tiny-live-10-of-10-ready-packet" in help_result.stdout


def _fixture_logs(tmp_path: Path, *, fresh_count: int = 10, watcher_stale: bool = False) -> Path:
    log_dir = tmp_path / "logs"
    _append(log_dir / "capture_count_sync_8m_short.ndjson", _capture_sync_record(fresh_count, watcher_stale=watcher_stale))
    for signal_id in _capture_count(fresh_count)["unique_captured_signal_ids"]:
        _write_capture(log_dir, str(signal_id))
    _write_heartbeat(log_dir, watcher_stale=watcher_stale)
    _append(log_dir / "lane_outcome_enrichment.ndjson", _lane_outcome_record(fresh_count))
    _append(log_dir / "capture_priority_rebalance.ndjson", _capture_priority_record())
    _append(log_dir / "betrayal_ranking_feed_preview.ndjson", _track_b_record())
    _append(log_dir / "paper_outcomes.ndjson", {"signal_id": "ordinary-signal", "outcome": "win"})
    _append(log_dir / "strategy_performance.ndjson", {"lane_key": "ordinary", "sample_size": 30, "win_rate_pct": 60.0})
    _append(log_dir / "strategy_promotion_status.ndjson", {"lane_key": "ordinary", "promotion_allowed": False})
    return log_dir


def _write_capture(log_dir: Path, signal_id: str) -> None:
    _append(
        log_dir / "short_paper_evidence_capture.ndjson",
        {
            "event_type": "SHORT_PAPER_EVIDENCE_CAPTURE",
            "status": "SHORT_PAPER_EVIDENCE_CAPTURED",
            "capture_id": f"capture-{signal_id}",
            "captured_signal_id": signal_id,
            "captured_lane_key": OFFICIAL,
            "paper_evidence_captured": True,
            "target_lane": {
                "lane_key": OFFICIAL,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "mode": "paper",
            },
        },
    )


def _write_heartbeat(log_dir: Path, *, watcher_stale: bool) -> None:
    heartbeat_at = NOW - (timedelta(seconds=600) if watcher_stale else timedelta(seconds=7))
    _append(
        log_dir / "short_paper_evidence_capture_heartbeats.ndjson",
        {
            "event_type": "SHORT_PAPER_EVIDENCE_CAPTURE_HEARTBEAT",
            "capture_id": "capture-watch",
            "generated_at": heartbeat_at.isoformat(),
            "iteration": 99,
            "max_iterations": 1440,
            "sleep_seconds": 60,
            "status": "SHORT_PAPER_CAPTURE_ITERATION_COMPLETED",
            "target_lane": {
                "lane_key": OFFICIAL,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "mode": "paper",
            },
        },
    )


def _capture_sync_record(fresh: int, *, watcher_stale: bool = False) -> dict[str, object]:
    heartbeat_at = NOW - (timedelta(seconds=600) if watcher_stale else timedelta(seconds=7))
    return {
        "event_type": "CAPTURE_COUNT_SYNC_8M_SHORT",
        "status": "CAPTURE_COUNT_SYNC_RECORDED",
        "target_family": {
            "lane_key": OFFICIAL,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "current_mode": "paper",
        },
        "capture_count": _capture_count(fresh),
        "watcher_status": {
            "latest_heartbeat_found": True,
            "heartbeat_age_seconds": 600 if watcher_stale else 7,
            "stale_after_seconds": 180,
            "latest_heartbeat_status": "SHORT_PAPER_CAPTURE_ITERATION_COMPLETED",
            "latest_heartbeat_iteration": 99,
            "latest_heartbeat_generated_at": heartbeat_at.isoformat(),
            "watcher_likely_running": not watcher_stale,
            "watcher_stale": watcher_stale,
        },
        "threshold_status": "CAPTURE_THRESHOLD_MET" if fresh >= 10 else "CAPTURE_THRESHOLD_NOT_MET",
        "recommended_next_operator_move": "RUN_R177_EVIDENCE_THRESHOLD_RECHECK" if fresh >= 10 else "WAIT_FOR_10_OF_10",
    }


def _capture_count(fresh: int) -> dict[str, object]:
    ids = [f"BTCUSDT|8m|short|2026-06-09T03:{index:02d}:59.999000+00:00" for index in range(fresh)]
    ids.reverse()
    return {
        "fresh_capture_count": fresh,
        "required_fresh_capture_count": 10,
        "threshold_met": fresh >= 10,
        "unique_captured_signal_ids": ids,
        "latest_captured_signal_id": ids[0] if ids else None,
    }


def _lane_outcome_record(fresh: int) -> dict[str, object]:
    return {
        "event_type": "LANE_OUTCOME_ENRICHMENT",
        "target_scope": {"paper_only": True, "live_authorized": False, "official_tiny_live_lane": OFFICIAL},
        "enriched_lane_rows": [
            {
                "lane_key": OFFICIAL,
                "known_outcome_count": 292,
                "win_rate_pct": 72.95,
                "combined_watch_score": 61.04,
                "unique_capture_count": fresh,
                "enrichment_notes": ["combined_watch_score is watchlist-only"],
            }
        ],
    }


def _capture_priority_record() -> dict[str, object]:
    return {
        "event_type": "CAPTURE_PRIORITY_REBALANCE",
        "target_scope": {"paper_only": True, "live_authorized": False, "official_tiny_live_lane": OFFICIAL},
        "official_protected_path_summary": {
            "lane_key": OFFICIAL,
            "official_path_still_primary": True,
            "combined_watch_score": 61.04,
        },
    }


def _track_b_record() -> dict[str, object]:
    return {
        "event_type": "BETRAYAL_RANKING_FEED_PREVIEW",
        "target_scope": {"paper_only": True, "live_authorized": False, "official_tiny_live_lane": OFFICIAL},
        "ranking_overall_status": "BETRAYAL_TRACK_B_STRUCTURALLY_COMPLETE_WAITING_FOR_DATA",
        "track_b_structural_completion_report": {
            "structurally_complete_for_now": True,
            "waiting_for_data_not_architecture": True,
            "remaining_architecture_gaps": [],
            "remaining_data_gaps": ["true_inverse_outcomes_pending"],
        },
    }


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
