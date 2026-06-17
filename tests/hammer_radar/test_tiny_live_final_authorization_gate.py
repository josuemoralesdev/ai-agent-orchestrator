from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.tiny_live_final_authorization_gate import (
    FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED,
    FINAL_TINY_LIVE_AUTHORIZATION_READY_FOR_OPERATOR_FINAL_SUBMIT,
    FINAL_TINY_LIVE_AUTHORIZATION_WAITING_FOR_REAL_CANDIDATE,
    build_tiny_live_final_authorization_gate,
)

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
LANE = "BTCUSDT|44m|long|ladder_close_50_618"
NEAR_MISS = "BTCUSDT|13m|long|ladder_close_50_618"
PAPER_ONLY = "BTCUSDT|8m|short|ladder_close_50_618"
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_no_candidate_waits_without_final_command(tmp_path: Path) -> None:
    payload = _build(tmp_path, r298_packet=_r298_wait(), candidate_watch_packet=_watch_wait())

    assert payload["status"] == FINAL_TINY_LIVE_AUTHORIZATION_WAITING_FOR_REAL_CANDIDATE
    assert payload["current_real_candidate_exists"] is False
    assert payload["blockers"] == []
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True
    assert payload["final_manual_submit_command"] is None
    assert payload["final_manual_submit_packet"] is None
    _assert_no_execution(payload)


def test_matching_candidate_all_gates_green_ready(tmp_path: Path) -> None:
    payload = _build(tmp_path)

    assert payload["status"] == FINAL_TINY_LIVE_AUTHORIZATION_READY_FOR_OPERATOR_FINAL_SUBMIT
    assert payload["current_real_candidate_exists"] is True
    assert payload["candidate_matches_requested_lane"] is True
    assert payload["final_command_available"] is True
    assert payload["submit_allowed"] is True
    assert payload["real_order_forbidden"] is False
    assert payload["executable_payload_created"] is True
    assert payload["order_payload_created"] is True
    assert "MANUAL_OPERATOR_ONLY" in payload["final_manual_submit_command"]
    assert "ONE_SHOT_TINY_LIVE" in payload["final_manual_submit_command"]
    assert "EXACT_LANE_ONLY" in payload["final_manual_submit_command"]
    assert "NO_CROSS_LANE_BORROWING" in payload["final_manual_submit_command"]
    packet = payload["final_manual_submit_packet"]
    assert packet["lane_key"] == LANE
    assert packet["signal_id"] == "sig-303"
    assert packet["notional_cap_usdt"] == 80.0
    assert packet["leverage"] == 10
    assert packet["margin_budget_usdt"] == 8.0
    assert packet["max_loss_usdt"] == 4.44
    assert packet["submit_allowed"] is True
    assert packet["real_order_forbidden"] is False
    _assert_no_execution(payload)


def test_mismatched_candidate_lane_blocks(tmp_path: Path) -> None:
    payload = _build(tmp_path, r298_packet=_r298_ready(lane="BTCUSDT|55m|long|ladder_close_50_618", matches=False))

    assert payload["status"] == FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED
    assert "real_candidate_lane_mismatch" in payload["blockers"]
    _assert_no_final_command(payload)


def test_near_miss_lane_blocks(tmp_path: Path) -> None:
    payload = _build(tmp_path, lane_key=NEAR_MISS)

    assert payload["status"] == FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED
    assert payload["lane_is_near_miss"] is True
    assert "requested_lane_is_near_miss" in payload["blockers"]
    _assert_no_final_command(payload)


def test_paper_only_lane_blocks(tmp_path: Path) -> None:
    payload = _build(tmp_path, lane_key=PAPER_ONLY)

    assert payload["status"] == FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED
    assert payload["lane_is_paper_only"] is True
    assert "requested_lane_is_paper_only" in payload["blockers"]
    _assert_no_final_command(payload)


def test_not_armed_blocks(tmp_path: Path) -> None:
    payload = _build(tmp_path, r302_packet={**_r302(), "exact_lane_auto_armed": False})

    assert payload["status"] == FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED
    assert "exact_lane_not_armed" in payload["blockers"]
    _assert_no_final_command(payload)


def test_stale_timer_blocks(tmp_path: Path) -> None:
    payload = _build(tmp_path, r302_packet={**_r302(), "recent_tick_seen": False, "recent_tick_count": 0})

    assert payload["status"] == FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED
    assert "timer_recent_tick_missing" in payload["blockers"]
    _assert_no_final_command(payload)


def test_readiness_blockers(tmp_path: Path) -> None:
    cases = [
        ("leverage_margin_ready", False, "leverage_margin_not_ready"),
        ("wallet_ready", False, "wallet_not_ready"),
        ("no_conflicting_position", False, "open_position_conflict"),
        ("idempotency_clean", False, "idempotency_not_clean"),
        ("exact_lane_risk_contract_found", False, "exact_lane_risk_contract_missing"),
        ("exact_lane_risk_contract_valid", False, "exact_lane_risk_contract_invalid"),
        ("protective_triplet_preview_available", False, "protective_triplet_preview_missing"),
        ("protective_triplet_preview_valid", False, "protective_triplet_preview_invalid"),
    ]
    for key, value, blocker in cases:
        payload = _build(tmp_path, pre_activation_packet={**_pre_activation_ready(), key: value})
        assert payload["status"] == FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED
        assert blocker in payload["blockers"]
        _assert_no_final_command(payload)


def test_prior_live_submit_blocks(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        pre_activation_packet={**_pre_activation_ready(), "no_prior_live_submit": False},
    )

    assert payload["status"] == FINAL_TINY_LIVE_AUTHORIZATION_BLOCKED
    assert "prior_live_submit_found" in payload["blockers"]
    _assert_no_final_command(payload)


def test_invalid_risk_contract_limits_block(tmp_path: Path) -> None:
    payload = _build(
        tmp_path,
        pre_activation_packet={
            **_pre_activation_ready(),
            "risk_contract_notional_cap_usdt": 81.0,
            "risk_contract_leverage": 5.0,
            "risk_contract_margin_budget_usdt": 7.0,
        },
    )

    assert "risk_contract_notional_cap_not_80" in payload["blockers"]
    assert "risk_contract_leverage_not_10" in payload["blockers"]
    assert "risk_contract_margin_budget_not_8" in payload["blockers"]
    _assert_no_final_command(payload)


def test_fake_or_test_candidate_rejected(tmp_path: Path) -> None:
    fake = _build(tmp_path, r298_packet={**_r298_ready(), "fake_candidate_used": True})
    test = _build(tmp_path, r298_packet={**_r298_ready(), "test_only": True})

    assert "fake_candidate_rejected" in fake["blockers"]
    assert "test_candidate_rejected" in test["blockers"]
    _assert_no_final_command(fake)
    _assert_no_final_command(test)


def test_record_appends_only_r303_ledger(tmp_path: Path) -> None:
    payload = _build(tmp_path, record_final_authorization_gate=True)

    assert payload["final_authorization_gate_recorded"] is True
    assert (tmp_path / "tiny_live_final_authorization_gate.ndjson").exists()
    assert not (tmp_path / "tiny_live_armed_dry_run_timer_observation_certificate.ndjson").exists()
    _assert_no_execution(payload)


def test_api_status_never_records_and_never_executes(monkeypatch, tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import approval_api

    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    monkeypatch.setattr(
        approval_api,
        "build_status_tiny_live_final_authorization_gate",
        lambda **kwargs: _build(tmp_path, r298_packet=_r298_wait(), candidate_watch_packet=_watch_wait()),
    )
    response = TestClient(app).get("/tiny-live/final-authorization-gate/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_type"] == "TINY_LIVE_FINAL_AUTHORIZATION_GATE"
    assert payload["final_authorization_gate_recorded"] is False
    assert not (tmp_path / "tiny_live_final_authorization_gate.ndjson").exists()
    _assert_no_execution(payload)


def test_final_console_includes_r303_panel(monkeypatch, tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    monkeypatch.setattr(
        final_console,
        "build_status_tiny_live_final_authorization_gate",
        lambda **kwargs: _build(tmp_path, r298_packet=_r298_wait(), candidate_watch_packet=_watch_wait()),
    )
    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)
    panel = payload["final_tiny_live_authorization_gate_panel"]

    assert panel["status"] == FINAL_TINY_LIVE_AUTHORIZATION_WAITING_FOR_REAL_CANDIDATE
    assert panel["requested_lane_key"] == LANE
    assert panel["final_command_available"] is False
    assert panel["manual_disarm_command"]


def test_cli_help_has_no_submit_or_order_flags() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "tiny-live-final-authorization-gate",
            "--help",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--record-final-authorization-gate" in result.stdout
    assert "--submit" not in result.stdout
    assert "--execute" not in result.stdout
    assert "--allow-binance-order" not in result.stdout
    assert "simulate" not in result.stdout.lower()


def test_print_only_script_outputs_plan_without_dangerous_execution(tmp_path: Path) -> None:
    script = REPO_ROOT / "scripts/hammer_print_r303_final_tiny_live_authorization_gate_plan.sh"
    before = sorted(tmp_path.iterdir())
    result = subprocess.run(["bash", str(script)], cwd=REPO_ROOT, check=True, capture_output=True, text=True)

    assert "R303 PRINT ONLY" in result.stdout
    assert "tiny-live-final-authorization-gate" in result.stdout
    assert "sudo" in result.stdout
    assert "systemctl" in result.stdout
    assert sorted(tmp_path.iterdir()) == before


def _build(
    tmp_path: Path,
    *,
    lane_key: str = LANE,
    r302_packet: dict | None = None,
    r298_packet: dict | None = None,
    pre_activation_packet: dict | None = None,
    candidate_watch_packet: dict | None = None,
    record_final_authorization_gate: bool = False,
) -> dict:
    return build_tiny_live_final_authorization_gate(
        log_dir=tmp_path,
        lane_key=lane_key,
        operator_id="local_operator",
        reason="R303 test; no submit; no order.",
        r302_packet=r302_packet or _r302(),
        r301_packet=_r301(),
        r300_packet=_r300(),
        r299_packet=_r299(),
        r298_packet=r298_packet or _r298_ready(),
        pre_activation_packet=pre_activation_packet or _pre_activation_ready(),
        candidate_watch_packet=candidate_watch_packet or _watch_ready(),
        record_final_authorization_gate=record_final_authorization_gate,
        now=NOW,
    )


def _r302() -> dict:
    return {
        "status": "ARMED_DRY_RUN_TIMER_OBSERVATION_TRIGGER_READY_CERTIFIED",
        "exact_lane_auto_armed": True,
        "any_lane_auto_armed": True,
        "armed_lane_key": LANE,
        "global_auto_live_enabled": True,
        "timer_health_status": "TIMER_HEALTH_ACTIVE",
        "timer_active": True,
        "recent_tick_seen": True,
        "recent_tick_count": 2,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _r301() -> dict:
    return {"status": "MANUAL_OPERATOR_DRY_RUN_ARMING_POST_ARM_CERTIFIED"}


def _r300() -> dict:
    return {"status": "OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_ARMED_CERTIFIED"}


def _r299() -> dict:
    return {"status": "REAL_CANDIDATE_TIMER_OBSERVATION_TRIGGER_CERTIFIED"}


def _r298_ready(*, lane: str = LANE, matches: bool = True) -> dict:
    return {
        "status": "REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED",
        "current_real_candidate_exists": True,
        "current_real_candidate_lane_key": lane,
        "current_real_candidate_signal_id": "sig-303",
        "candidate_matches_requested_lane": matches,
        "current_real_candidate_freshness_status": "fresh",
        "current_real_candidate_live_qualification_class": "LIVE_QUALIFIED",
        "candidate_entry": 50000.0,
        "candidate_stop": 49750.0,
        "candidate_take_profit": 50500.0,
        "candidate_age_minutes": 2.0,
        "fake_candidate_used": False,
        "test_only": False,
    }


def _r298_wait() -> dict:
    return {
        "status": "REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT",
        "current_real_candidate_exists": False,
        "current_real_candidate_lane_key": None,
        "current_real_candidate_signal_id": None,
        "candidate_matches_requested_lane": False,
        "fake_candidate_used": False,
        "test_only": False,
    }


def _pre_activation_ready() -> dict:
    return {
        "status": "ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER",
        "binance_readiness_ready": True,
        "leverage_margin_ready": True,
        "post_manual_leverage_margin_verified": True,
        "wallet_ready": True,
        "wallet_supports_configured_margin_budget": True,
        "no_conflicting_position": True,
        "idempotency_clean": True,
        "no_prior_live_submit": True,
        "exact_lane_risk_contract_found": True,
        "exact_lane_risk_contract_valid": True,
        "risk_contract_notional_cap_usdt": 80.0,
        "risk_contract_margin_budget_usdt": 8.0,
        "risk_contract_leverage": 10.0,
        "protective_triplet_preview_available": True,
        "protective_triplet_preview_valid": True,
    }


def _watch_ready() -> dict:
    return {
        "status": "FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW",
        "current_candidate_entry": 50000.0,
        "current_candidate_stop": 49750.0,
        "current_candidate_take_profit": 50500.0,
        "current_candidate_age_minutes": 2.0,
    }


def _watch_wait() -> dict:
    return {"status": "FRESH_TRIGGER_WAIT"}


def _assert_no_final_command(payload: dict) -> None:
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True
    assert payload["final_manual_submit_command"] is None
    assert payload["final_manual_submit_packet"] is None
    _assert_no_execution(payload)


def _assert_no_execution(payload: dict) -> None:
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["secrets_shown"] is False
