from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_risk_contract_preview import (
    CONFIRM_TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDING_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_RISK_CONTRACT_PREVIEW_READY,
    TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDED,
    TINY_LIVE_RISK_CONTRACT_PREVIEW_REJECTED,
    TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_EVIDENCE_GAP,
    TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_FISHERMAN_STALE,
    TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_R228_PACKET,
    TINY_LIVE_RISK_PREVIEW_READY_CONFIG_WRITE_REQUIRED_LATER,
    build_tiny_live_risk_contract_preview,
    load_tiny_live_risk_contract_preview_records,
)

NOW = datetime(2026, 6, 9, 4, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_tiny_live_risk_contract_preview(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_RISK_CONTRACT_PREVIEW_READY
    assert payload["risk_preview_recorded"] is False
    assert payload["record_risk_preview_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)

    payload = build_tiny_live_risk_contract_preview(
        log_dir=log_dir,
        record_risk_preview=True,
        confirm_tiny_live_risk_contract_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_RISK_CONTRACT_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["risk_preview_recorded"] is False
    assert load_tiny_live_risk_contract_preview_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_risk_preview_only(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    lane_path = _write_lane_controls(tmp_path / "lane_controls.json")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    payload = build_tiny_live_risk_contract_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        record_risk_preview=True,
        confirm_tiny_live_risk_contract_preview=CONFIRM_TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_tiny_live_risk_contract_preview_records(log_dir=log_dir, limit=0)

    assert payload["status"] == TINY_LIVE_RISK_CONTRACT_PREVIEW_RECORDED
    assert payload["risk_preview_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "TINY_LIVE_RISK_CONTRACT_PREVIEW"
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert records[0]["safety"]["risk_contract_config_written"] is False
    assert records[0]["safety"]["order_payload_created"] is False


def test_preview_requires_r228_packet(tmp_path: Path) -> None:
    payload = build_tiny_live_risk_contract_preview(log_dir=tmp_path / "logs", now=NOW)

    assert payload["input_summary"]["r228_packet_found"] is False
    assert payload["risk_gate_matrix"]["risk_contract_preview_ready"] is False
    assert payload["risk_preview_overall_status"] == TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_R228_PACKET


def test_preview_requires_r228_evidence_ready(tmp_path: Path) -> None:
    payload = build_tiny_live_risk_contract_preview(log_dir=_fixture_logs(tmp_path, evidence_ready=False), now=NOW)

    assert payload["input_summary"]["r228_evidence_ready"] is False
    assert payload["risk_gate_matrix"]["risk_contract_preview_ready"] is False
    assert payload["risk_preview_overall_status"] == TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_EVIDENCE_GAP


def test_preview_requires_r228_fisherman_ready(tmp_path: Path) -> None:
    payload = build_tiny_live_risk_contract_preview(log_dir=_fixture_logs(tmp_path, fisherman_ready=False), now=NOW)

    assert payload["input_summary"]["r228_fisherman_ready"] is False
    assert payload["risk_gate_matrix"]["risk_contract_preview_ready"] is False
    assert payload["risk_preview_overall_status"] == TINY_LIVE_RISK_PREVIEW_BLOCKED_BY_FISHERMAN_STALE


def test_preview_keeps_dangerous_gates_false(tmp_path: Path) -> None:
    payload = build_tiny_live_risk_contract_preview(log_dir=_fixture_logs(tmp_path), now=NOW)
    gates = payload["risk_gate_matrix"]

    assert gates["evidence_ready"] is True
    assert gates["fisherman_ready"] is True
    assert gates["operator_review_ready"] is True
    assert gates["risk_contract_preview_ready"] is True
    assert gates["risk_contract_config_written"] is False
    assert gates["risk_contract_approved"] is False
    assert gates["live_authorization_ready"] is False
    assert gates["live_execution_ready"] is False
    assert gates["order_ready"] is False
    assert gates["live_ready_today"] is False


def test_preview_does_not_create_order_payload_or_write_configs(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    lane_path = _write_lane_controls(tmp_path / "lane_controls.json")
    before_env = dict(os.environ)
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as build_signed_live_order_request,
    ):
        payload = build_tiny_live_risk_contract_preview(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    build_signed_live_order_request.assert_not_called()
    assert dict(os.environ) == before_env
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
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
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "secrets_shown",
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
    assert payload["safety"]["risk_contract_preview_only"] is True


def test_preview_keeps_official_lane_unchanged(tmp_path: Path) -> None:
    payload = build_tiny_live_risk_contract_preview(log_dir=_fixture_logs(tmp_path), now=NOW)

    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["r228_packet_summary"]["official_lane_unchanged"] is True
    assert payload["risk_contract_preview"]["official_lane_key"] == OFFICIAL


def test_conservative_defaults_are_preview_only_and_not_approved(tmp_path: Path) -> None:
    payload = build_tiny_live_risk_contract_preview(log_dir=_fixture_logs(tmp_path), now=NOW)
    preview = payload["risk_contract_preview"]

    assert preview["capital_mode"] == "tiny_live_preview"
    assert preview["proposed_tiny_live_margin_usdt"] == 44
    assert preview["proposed_leverage"] == 1
    assert preview["proposed_max_notional_usdt"] == 44
    assert preview["proposed_max_loss_usdt"] <= preview["proposed_tiny_live_margin_usdt"]
    assert preview["preview_only"] is True
    assert preview["approval_status"] == "NOT_APPROVED_PREVIEW_ONLY"
    assert preview["order_payload_forbidden_now"] is True
    assert preview["binance_call_forbidden_now"] is True


def test_operator_packet_says_review_only(tmp_path: Path) -> None:
    payload = build_tiny_live_risk_contract_preview(log_dir=_fixture_logs(tmp_path), now=NOW)
    packet = payload["operator_review_packet"]

    assert packet["operator_should_review_risk_preview"] is True
    assert packet["operator_should_write_config"] is False
    assert packet["operator_should_enable_live"] is False
    assert packet["operator_should_place_order"] is False
    assert packet["next_required_human_action"] == "REVIEW_R229_RISK_PREVIEW"
    assert "do not write risk config from this preview" in packet["explicit_non_actions"]
    assert payload["risk_preview_overall_status"] == TINY_LIVE_RISK_PREVIEW_READY_CONFIG_WRITE_REQUIRED_LATER


def test_existing_risk_contract_context_is_read_only(tmp_path: Path) -> None:
    risk_path = _write_matching_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    before = risk_path.read_text(encoding="utf-8")

    payload = build_tiny_live_risk_contract_preview(
        log_dir=_fixture_logs(tmp_path),
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    context = payload["existing_contract_context"]
    assert context["context_found"] is True
    assert context["matching_contract_found"] is True
    assert context["matching_contract_summary"]["symbol"] == "BTCUSDT"
    assert context["config_mutated"] is False
    assert risk_path.read_text(encoding="utf-8") == before
    assert payload["risk_gate_matrix"]["risk_contract_config_written"] is False


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-risk-contract-preview",
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
    assert payload["risk_preview_recorded"] is False
    assert "tiny-live-risk-contract-preview" in help_result.stdout


def _fixture_logs(
    tmp_path: Path,
    *,
    evidence_ready: bool = True,
    fisherman_ready: bool = True,
) -> Path:
    log_dir = tmp_path / "logs"
    _append(
        log_dir / "tiny_live_10_of_10_ready_packet.ndjson",
        _r228_packet_record(evidence_ready=evidence_ready, fisherman_ready=fisherman_ready),
    )
    _append(log_dir / "paper_outcomes.ndjson", {"signal_id": "ordinary-signal", "outcome": "win"})
    _append(log_dir / "strategy_performance.ndjson", {"lane_key": "ordinary", "sample_size": 30, "win_rate_pct": 60.0})
    _append(log_dir / "strategy_promotion_status.ndjson", {"lane_key": "ordinary", "promotion_allowed": False})
    return log_dir


def _r228_packet_record(*, evidence_ready: bool, fisherman_ready: bool) -> dict[str, object]:
    operator_review_ready = evidence_ready and fisherman_ready
    fresh = 10 if evidence_ready else 9
    return {
        "event_type": "TINY_LIVE_10_OF_10_READY_PACKET",
        "status": "TINY_LIVE_10_OF_10_READY_PACKET_READY" if operator_review_ready else "TINY_LIVE_10_OF_10_READY_PACKET_BLOCKED",
        "packet_record_id": "r228_tiny_live_10_of_10_packet_fixture",
        "generated_at": NOW.isoformat(),
        "target_scope": {
            "official_lane_key": OFFICIAL,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "paper_only": True,
            "live_authorized": False,
        },
        "capture_threshold_recheck": {
            "fresh_capture_count": fresh,
            "required_fresh_capture_count": 10,
            "threshold_met": evidence_ready,
            "threshold_status": "CAPTURE_THRESHOLD_MET" if evidence_ready else "CAPTURE_THRESHOLD_NOT_MET",
            "official_lane_key": OFFICIAL,
            "official_lane_unchanged": True,
            "evidence_threshold_ready": evidence_ready,
        },
        "fisherman_health_recheck": {
            "latest_heartbeat_found": fisherman_ready,
            "watcher_likely_running": fisherman_ready,
            "watcher_stale": not fisherman_ready,
            "fisherman_ready": fisherman_ready,
        },
        "tiny_live_gate_matrix": {
            "evidence_ready": evidence_ready,
            "fisherman_ready": fisherman_ready,
            "operator_review_ready": operator_review_ready,
            "risk_contract_ready": False,
            "live_authorization_ready": False,
            "live_execution_ready": False,
            "order_ready": False,
            "live_ready_today": False,
            "blocked_by": ["risk_contract_missing", "live_authorization_absent", "live_execution_disabled", "order_payload_forbidden"],
        },
        "ready_packet_overall_status": "TINY_LIVE_10_OF_10_BLOCKED_BY_RISK_CONTRACT",
        "recommended_next_operator_move": "REVIEW_R228_PACKET",
        "recommended_next_engineering_move": "Create R229 tiny-live risk contract preview from this packet; preview only, no config writes or orders.",
    }


def _write_risk_contract_config(path: Path) -> Path:
    payload = {
        "funding_config": {"max_margin_usdt": 44.0, "max_loss_usdt": 4.44},
        "risk_contracts": [
            {
                "candidate_id": "normal|BTCUSDT|13m|long|ladder_close_50_618",
                "symbol": "BTCUSDT",
                "timeframe": "13m",
                "direction": "long",
                "entry_mode": "ladder_close_50_618",
                "enabled_for_preflight": True,
                "max_margin_usdt": 44.0,
                "max_position_notional_usdt": 44.0,
                "leverage": 1,
                "max_loss_usdt": 4.44,
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _write_matching_risk_contract_config(path: Path) -> Path:
    payload = {
        "funding_config": {"max_margin_usdt": 44.0, "max_loss_usdt": 4.44},
        "risk_contracts": [
            {
                "candidate_id": "normal|BTCUSDT|8m|short|ladder_close_50_618",
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "enabled_for_preflight": False,
                "approval_status": "NOT_APPROVED_PREVIEW_ONLY",
                "max_margin_usdt": 44.0,
                "max_position_notional_usdt": 44.0,
                "leverage": 1,
                "max_loss_usdt": 4.44,
                "protective_stop_required": True,
                "take_profit_required": True,
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _write_lane_controls(path: Path) -> Path:
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
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _append(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
