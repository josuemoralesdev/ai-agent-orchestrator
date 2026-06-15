from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import tiny_live_jit_launch_packet as r264b
from src.app.hammer_radar.operator.approval_api import _operator_ui_html, app

OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"
NOW = datetime(2026, 6, 12, 14, 0, tzinfo=UTC)
API_KEY = "R264B_API_KEY_SHOULD_NOT_APPEAR"
API_SECRET = "R264B_API_SECRET_SHOULD_NOT_APPEAR"


def test_cli_preview_returns_json_and_does_not_mutate(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-jit-launch-packet",
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == r264b.TINY_LIVE_JIT_LAUNCH_PACKET_READY
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["run_jit_launch_prep_requested"] is False
    assert payload["jit_launch_packet_recorded"] is False
    assert payload["safety"]["order_placed"] is False
    assert not (log_dir / r264b.LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_without_child_steps(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: calls.append("r262b"))
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep="wrong",
        now=NOW,
    )
    assert calls == []
    assert payload["status"] == r264b.TINY_LIVE_JIT_LAUNCH_PACKET_REJECTED
    assert payload["jit_launch_overall_status"] == r264b.TINY_LIVE_JIT_REJECTED_BAD_CONFIRMATION
    assert payload["confirmation_valid"] is False
    assert payload["jit_launch_packet_recorded"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False


def test_exact_confirmation_orchestrates_r262b_r263_r264_and_records(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    _patch_current_candidate_only(monkeypatch)
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: calls.append("r262b") or _r262b_ok())
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: calls.append("r263") or _r263_ok())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: calls.append("r264") or _r264_ok())

    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        operator_id="local_operator",
        reason="test",
        now=NOW,
    )

    assert calls == ["r262b", "r263", "r264"]
    assert payload["status"] == r264b.TINY_LIVE_JIT_LAUNCH_PACKET_RECORDED
    assert payload["jit_launch_packet_recorded"] is True
    assert payload["jit_validation"]["valid"] is True
    assert payload["jit_go_no_go_packet"]["go_for_manual_live_submit_command"] is False
    assert payload["jit_go_no_go_packet"]["next_required_step"] == "FINAL_COMMAND_UNAVAILABLE_R267"
    assert payload["final_live_submit_command_packet"]["available"] is False
    assert (tmp_path / "logs" / r264b.LEDGER_FILENAME).exists()
    _assert_no_submit_safety(payload)


def test_successful_jit_packet_keeps_final_manual_command_unavailable(tmp_path: Path, monkeypatch) -> None:
    _patch_success(monkeypatch)
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        now=NOW,
    )
    command = payload["final_live_submit_command_packet"]
    assert command["available"] is False
    assert command["must_be_run_manually_by_operator"] is True
    assert command["do_not_run_from_codex"] is True
    assert command["command"] == ""
    assert "unlock_confirmation_exact" in command["unavailable_reason"]
    assert "I CONFIRM R271 QUALIFIED-LANE MANUAL UNLOCK PACKET ONLY" in command["unlock_confirmation_phrase"]
    assert r264b.LIVE_SUBMIT_CONFIRMATION_PHRASE in command["confirmation_phrase"]
    assert "80 USDT notional cap" in command["expected_orders"]["main"]


def test_4m_long_ticket_gets_buy_main_sell_reduce_only_expected_orders(tmp_path: Path, monkeypatch) -> None:
    _patch_success(monkeypatch, lane_key="BTCUSDT|4m|long|ladder_close_50_618")
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        confirm_final_manual_submit_unlock=r264b.R268_FINAL_MANUAL_SUBMIT_UNLOCK_CONFIRMATION_PHRASE,
        now=NOW,
    )
    command = payload["final_live_submit_command_packet"]
    assert payload["target_scope"]["official_lane_key"] == "BTCUSDT|4m|long|ladder_close_50_618"
    assert command["expected_orders"]["main"].startswith("BUY MARKET")
    assert command["expected_orders"]["stop"] == "SELL STOP_MARKET REDUCE_ONLY"
    assert command["expected_orders"]["take_profit"] == "SELL TAKE_PROFIT_MARKET REDUCE_ONLY"
    assert "BTCUSDT|8m|short|ladder_close_50_618" != command["packet_lane_key"]
    _assert_no_submit_safety(payload)


def test_mismatch_blocks_command_availability(tmp_path: Path, monkeypatch) -> None:
    _patch_success(monkeypatch, lane_key="BTCUSDT|4m|long|ladder_close_50_618")
    monkeypatch.setattr(
        r264b,
        "build_fresh_candidate_status",
        lambda **_: _fresh_candidate_ok(lane_key="BTCUSDT|8m|short|ladder_close_50_618"),
    )
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        confirm_final_manual_submit_unlock=r264b.R268_FINAL_MANUAL_SUBMIT_UNLOCK_CONFIRMATION_PHRASE,
        now=NOW,
    )
    blocked = payload["final_live_submit_command_packet"]["gate_validation"]["blocked_by"]
    assert payload["final_live_submit_command_packet"]["available"] is False
    assert "fresh_candidate_lane_matches_packet" in blocked
    assert "fresh_candidate_timeframe_matches_packet" in blocked
    _assert_no_submit_safety(payload)


def test_betrayal_or_inverse_origin_blocks_manual_unlock(tmp_path: Path, monkeypatch) -> None:
    _patch_success(
        monkeypatch,
        origin={
            **_standard_origin(),
            "signal_origin_family": "betrayal",
            "betrayal_mode_involved": True,
            "betrayal_inverse_involved": True,
            "candidate_origin_classification": "inverse-derived",
            "manual_unlock_allowed": False,
            "blocked_by": ["betrayal_first_tiny_live_not_explicitly_accepted"],
        },
    )
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        confirm_final_manual_submit_unlock=r264b.R268_FINAL_MANUAL_SUBMIT_UNLOCK_CONFIRMATION_PHRASE,
        now=NOW,
    )
    blocked = payload["final_live_submit_command_packet"]["gate_validation"]["blocked_by"]
    assert payload["final_live_submit_command_packet"]["available"] is False
    assert "betrayal_first_tiny_live_not_explicitly_accepted" in blocked
    assert "betrayal_not_involved" in blocked
    assert "betrayal_inverse_not_involved" in blocked
    _assert_no_submit_safety(payload)


def test_unknown_origin_blocks_manual_unlock(tmp_path: Path, monkeypatch) -> None:
    _patch_success(
        monkeypatch,
        origin={
            **_standard_origin(),
            "signal_origin_family": "unknown",
            "betrayal_mode_involved": "unknown",
            "betrayal_inverse_involved": "unknown",
            "candidate_origin_classification": "unknown",
            "manual_unlock_allowed": False,
            "blocked_by": ["needs_manual_origin_review"],
        },
    )
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        confirm_final_manual_submit_unlock=r264b.R268_FINAL_MANUAL_SUBMIT_UNLOCK_CONFIRMATION_PHRASE,
        now=NOW,
    )
    blocked = payload["final_live_submit_command_packet"]["gate_validation"]["blocked_by"]
    assert payload["final_live_submit_command_packet"]["available"] is False
    assert "needs_manual_origin_review" in blocked
    assert "signal_origin_allowed" in blocked
    _assert_no_submit_safety(payload)


def test_final_command_unavailable_without_exact_r268_unlock_confirmation(tmp_path: Path, monkeypatch) -> None:
    _patch_success(monkeypatch)
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        confirm_final_manual_submit_unlock="wrong",
        now=NOW,
    )
    command = payload["final_live_submit_command_packet"]
    assert command["available"] is False
    assert command["unlock_confirmation_valid"] is False
    assert "unlock_confirmation_exact" in command["gate_validation"]["blocked_by"]
    _assert_no_submit_safety(payload)


def test_old_r268_unlock_phrase_no_longer_unlocks(tmp_path: Path, monkeypatch) -> None:
    _patch_success(monkeypatch)
    old_phrase = (
        "I CONFIRM R268 TINY LIVE FINAL MANUAL SUBMIT UNLOCK PACKET ONLY; "
        "EXPOSE MANUAL COMMAND ONLY IF R262B R263 R264 IDEMPOTENCY FRESHNESS "
        "AND 80 USDT 10X CONTRACT GATES ARE CLEAN; CODEX MUST NOT SUBMIT; "
        "NO ORDER; NO BINANCE ORDER CALL."
    )
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        confirm_final_manual_submit_unlock=old_phrase,
        now=NOW,
    )
    command = payload["final_live_submit_command_packet"]
    assert command["available"] is False
    assert command["unlock_confirmation_valid"] is False
    assert "unlock_confirmation_exact" in command["gate_validation"]["blocked_by"]
    _assert_no_submit_safety(payload)


def test_final_command_unavailable_without_fresh_candidate(tmp_path: Path, monkeypatch) -> None:
    _patch_success(monkeypatch, fresh_candidate=False)
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        confirm_final_manual_submit_unlock=r264b.R268_FINAL_MANUAL_SUBMIT_UNLOCK_CONFIRMATION_PHRASE,
        now=NOW,
    )
    command = payload["final_live_submit_command_packet"]
    assert payload["fresh_candidate_status"]["fresh_candidate_available"] is False
    assert command["available"] is False
    assert "fresh_candidate_available" in command["gate_validation"]["blocked_by"]
    assert "no fresh ELIGIBLE_TINY_LIVE BTCUSDT candidate" in command["gate_validation"]["blocked_by"]
    _assert_no_submit_safety(payload)


def test_jit_prep_does_not_run_child_steps_without_current_candidate(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: calls.append("r262b") or _r262b_ok())
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: calls.append("r263") or _r263_ok())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: calls.append("r264") or _r264_ok())
    monkeypatch.setattr(
        r264b,
        "build_current_proposed_ticket_context",
        lambda **_: {
            **_current_ticket_context(),
            "selected": False,
            "lane_key": None,
            "blockers": ["no current BTCUSDT live-checklist candidate available"],
        },
    )
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        confirm_final_manual_submit_unlock=r264b.R271_FINAL_MANUAL_SUBMIT_UNLOCK_CONFIRMATION_PHRASE,
        now=NOW,
    )
    assert calls == []
    assert payload["status"] == r264b.TINY_LIVE_JIT_LAUNCH_PACKET_BLOCKED
    assert "no_current_qualified_fresh_candidate" in payload["jit_validation"]["blocked_by"]
    assert payload["final_live_submit_command_packet"]["available"] is False
    _assert_no_submit_safety(payload)


def test_final_command_available_only_manual_packet_when_all_gates_clean(tmp_path: Path, monkeypatch) -> None:
    _patch_success(monkeypatch)
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        confirm_final_manual_submit_unlock=r264b.R268_FINAL_MANUAL_SUBMIT_UNLOCK_CONFIRMATION_PHRASE,
        now=NOW,
    )
    command = payload["final_live_submit_command_packet"]
    assert command["available"] is True
    assert command["manual_only"] is True
    assert command["must_be_run_manually_by_operator"] is True
    assert command["do_not_run_from_codex"] is True
    assert command["submit_allowed_from_codex"] is False
    assert command["strategy_evidence"]["avg_pnl_pct"] == 0.1
    assert payload["jit_go_no_go_packet"]["go_for_manual_live_submit_command"] is True
    assert payload["jit_go_no_go_packet"]["operator_should_submit_now"] is False
    assert payload["target_scope"]["submit_allowed"] is False
    assert "--execute-actual-live-submit" in command["command"]
    assert "--allow-binance-order-endpoint" in command["command"]
    assert command["command"].count("/fapi/v1/order") == 0
    assert command["allowed_endpoint"] == "/fapi/v1/order"
    assert len(command["expected_orders"]) == 3
    _assert_no_submit_safety(payload)


def test_final_command_unavailable_when_strategy_avg_pnl_not_positive(tmp_path: Path, monkeypatch) -> None:
    _patch_success(monkeypatch)
    monkeypatch.setattr(
        r264b,
        "build_fresh_candidate_status",
        lambda **_: {
            **_fresh_candidate_ok(),
            "strategy_qualification": {
                **_strategy_qualification(),
                "avg_pnl_pct": 0.0,
                "strategy_qualified": False,
                "blocked_by": ["strategy_lane_avg_pnl_pct_not_positive"],
            },
            "strategy_qualified": False,
            "blocked_by": ["strategy_lane_avg_pnl_pct_not_positive"],
        },
    )
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        confirm_final_manual_submit_unlock=r264b.R271_FINAL_MANUAL_SUBMIT_UNLOCK_CONFIRMATION_PHRASE,
        now=NOW,
    )
    command = payload["final_live_submit_command_packet"]
    assert command["available"] is False
    assert "strategy_lane_qualified" in command["gate_validation"]["blocked_by"]
    assert "strategy_avg_pnl_positive" in command["gate_validation"]["blocked_by"]
    assert "strategy_lane_avg_pnl_pct_not_positive" in command["gate_validation"]["blocked_by"]
    _assert_no_submit_safety(payload)


def test_near_miss_strategy_cannot_unlock_final_manual_command(tmp_path: Path, monkeypatch) -> None:
    _patch_success(monkeypatch)
    near_miss = {
        **_strategy_qualification(),
        "strategy_qualified": False,
        "qualification_status": "BLOCKED",
        "win_rate_pct": 54.99,
        "live_qualification_class": "NEAR_MISS_INCUBATOR",
        "watch_category": "NEAR_MISS_INCUBATOR",
        "near_miss_incubator": True,
        "manual_live_unlock_allowed": False,
        "blocked_by": ["strategy_near_miss_not_live_eligible"],
    }
    monkeypatch.setattr(
        r264b,
        "build_fresh_candidate_status",
        lambda **_: {
            **_fresh_candidate_ok(),
            "strategy_qualification": near_miss,
            "strategy_qualified": False,
            "strategy_win_rate_pct": 54.99,
            "blocked_by": ["strategy_near_miss_not_live_eligible"],
        },
    )
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        confirm_final_manual_submit_unlock=r264b.R271_FINAL_MANUAL_SUBMIT_UNLOCK_CONFIRMATION_PHRASE,
        now=NOW,
    )
    command = payload["final_live_submit_command_packet"]
    blocked = command["gate_validation"]["blocked_by"]
    assert command["available"] is False
    assert "strategy_live_qualified" in blocked
    assert "strategy_near_miss_not_live_eligible" in blocked
    assert command["strategy_evidence"]["near_miss_incubator"] is True
    _assert_no_submit_safety(payload)


def test_no_binance_order_private_or_account_calls_and_no_actual_submit(tmp_path: Path, monkeypatch) -> None:
    _patch_success(monkeypatch)
    with patch("urllib.request.urlopen") as urlopen:
        payload = r264b.build_tiny_live_jit_launch_packet(
            log_dir=tmp_path / "logs",
            run_jit_launch_prep=True,
            record_jit_launch_packet=True,
            confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
            now=NOW,
        )
    urlopen.assert_not_called()
    _assert_no_submit_safety(payload)
    assert payload["jit_validation"]["no_live_submit_performed"] is True


def test_stale_signed_triplet_after_r262b_blocks(tmp_path: Path, monkeypatch) -> None:
    _patch_current_candidate_only(monkeypatch)
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: _r262b_ok())
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: _r263_ok())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: _r264_ok(signed_triplet_fresh=False))
    payload = _run_exact(tmp_path)
    assert payload["status"] == r264b.TINY_LIVE_JIT_LAUNCH_PACKET_BLOCKED
    assert payload["jit_validation"]["signed_triplet_fresh"] is False
    assert payload["final_live_submit_command_packet"]["available"] is False


def test_final_command_unavailable_if_notional_exceeds_80(tmp_path: Path, monkeypatch) -> None:
    _patch_current_candidate_only(monkeypatch)
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: _r262b_ok(candidate_notional=81.0))
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: _r263_ok())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: _r264_ok(candidate_notional=81.0))
    payload = r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        confirm_final_manual_submit_unlock=r264b.R268_FINAL_MANUAL_SUBMIT_UNLOCK_CONFIRMATION_PHRASE,
        now=NOW,
    )
    assert payload["jit_validation"]["candidate_notional_within_cap"] is False
    assert "candidate_notional_exceeds_80" in payload["jit_validation"]["blocked_by"]
    assert payload["final_live_submit_command_packet"]["available"] is False


def test_failed_r263_arming_blocks(tmp_path: Path, monkeypatch) -> None:
    _patch_current_candidate_only(monkeypatch)
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: _r262b_ok())
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: _r263_blocked())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: _r264_ok())
    payload = _run_exact(tmp_path)
    assert payload["jit_launch_overall_status"] == r264b.TINY_LIVE_JIT_BLOCKED_BY_R263_ARMING
    assert payload["jit_step_results"]["r264_dry_preview"]["attempted"] is False


def test_failed_r264_dry_preview_blocks(tmp_path: Path, monkeypatch) -> None:
    _patch_current_candidate_only(monkeypatch)
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: _r262b_ok())
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: _r263_ok())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: _r264_blocked())
    payload = _run_exact(tmp_path)
    assert payload["jit_launch_overall_status"] == r264b.TINY_LIVE_JIT_BLOCKED_BY_R264_DRY_PREVIEW
    assert payload["jit_validation"]["r264_dry_preview_valid"] is False


def test_risk_contract_mismatch_blocks_final_command(tmp_path: Path, monkeypatch) -> None:
    _patch_current_candidate_only(monkeypatch)
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: _r262b_ok())
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: _r263_ok())
    monkeypatch.setattr(
        r264b,
        "run_r264_dry_preview_step",
        lambda **_: {
            **_r264_ok(),
            "succeeded": False,
            "pre_submit_valid": False,
            "risk_contract_valid": False,
            "blocked_by": ["risk_contract_config_invalid", "risk_contract_notional_cap_exceeds_44"],
            "risk_contract_interpretation": {
                "valid": False,
                "tiny_live_contract_mode": "margin_budget_cap",
                "higher_notional_interpretation_rejected": True,
                "blocked_by": ["risk_contract_notional_cap_exceeds_44"],
            },
        },
    )
    payload = _run_exact(tmp_path)
    assert payload["jit_launch_overall_status"] == r264b.TINY_LIVE_JIT_BLOCKED_BY_R264_DRY_PREVIEW
    assert payload["jit_validation"]["risk_contract_valid"] is False
    assert payload["final_live_submit_command_packet"]["available"] is False
    assert payload["jit_go_no_go_packet"]["go_for_manual_live_submit_command"] is False


def test_idempotency_dirty_blocks(tmp_path: Path, monkeypatch) -> None:
    _patch_current_candidate_only(monkeypatch)
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: _r262b_ok())
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: _r263_ok())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: _r264_ok(idempotency_clean=False))
    payload = _run_exact(tmp_path)
    assert payload["jit_launch_overall_status"] == r264b.TINY_LIVE_JIT_BLOCKED_BY_IDEMPOTENCY
    assert payload["jit_go_no_go_packet"]["next_required_step"] == "WAIT"


def test_secrets_not_in_output(tmp_path: Path, monkeypatch) -> None:
    _patch_current_candidate_only(monkeypatch)
    monkeypatch.setenv("BINANCE_API_KEY", API_KEY)
    monkeypatch.setenv("BINANCE_API_SECRET", API_SECRET)
    monkeypatch.setattr(
        r264b,
        "run_r262b_contract_fit_refresh_step",
        lambda **_: {
            **_r262b_ok(),
            "signed_request": {
                "headers": {"X-MBX-APIKEY": API_KEY},
                "query_string": f"symbol=BTCUSDT&signature={API_SECRET}",
                "signature": API_SECRET,
            },
        },
    )
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: _r263_ok())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: _r264_ok())
    payload = _run_exact(tmp_path)
    _assert_no_secrets(payload)


def test_api_endpoint_returns_json() -> None:
    client = TestClient(app)
    response = client.get("/tiny-live/jit-launch-packet")
    assert response.status_code == 200
    body = response.json()
    assert body["target_scope"]["official_lane_key"] == OFFICIAL
    assert "jit_validation" in body


def test_ui_card_has_no_auto_submit_button() -> None:
    html = _operator_ui_html()
    section = html.split('<section id="tinyLiveJitLaunchPacket"', 1)[1].split("</section>", 1)[0]
    assert "no submit from this screen" in section
    assert "Run JIT Prep Only" in section
    assert "Execute Exact Live Submit" not in section
    assert "auto-submit" not in section.lower()


def _run_exact(tmp_path: Path) -> dict:
    return r264b.build_tiny_live_jit_launch_packet(
        log_dir=tmp_path / "logs",
        run_jit_launch_prep=True,
        record_jit_launch_packet=True,
        confirm_jit_launch_prep=r264b.JIT_LAUNCH_PREP_CONFIRMATION_PHRASE,
        now=NOW,
    )


def _patch_success(
    monkeypatch,
    *,
    fresh_candidate: bool = True,
    lane_key: str = OFFICIAL,
    origin: dict | None = None,
) -> None:
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: _r262b_ok())
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: _r263_ok())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: _r264_ok())
    monkeypatch.setattr(
        r264b,
        "build_current_proposed_ticket_context",
        lambda **_: _current_ticket_context(lane_key=lane_key, origin=origin or _standard_origin(lane_key=lane_key)),
    )
    monkeypatch.setattr(
        r264b,
        "build_fresh_candidate_status",
        lambda **_: _fresh_candidate_ok(lane_key=lane_key, origin=origin or _standard_origin(lane_key=lane_key))
        if fresh_candidate
        else _fresh_candidate_blocked(),
    )


def _patch_current_candidate_only(monkeypatch, *, lane_key: str = OFFICIAL, origin: dict | None = None) -> None:
    monkeypatch.setattr(
        r264b,
        "build_current_proposed_ticket_context",
        lambda **_: _current_ticket_context(lane_key=lane_key, origin=origin or _standard_origin(lane_key=lane_key)),
    )
    monkeypatch.setattr(
        r264b,
        "build_fresh_candidate_status",
        lambda **_: _fresh_candidate_ok(lane_key=lane_key, origin=origin or _standard_origin(lane_key=lane_key)),
    )


def _r262b_ok(*, candidate_notional: float = 64.0) -> dict:
    return {
        "attempted": True,
        "succeeded": True,
        "risk_contract_valid": True,
        "signed_triplet_fresh": True,
        "candidate_qty": 0.006,
        "candidate_notional_usdt": candidate_notional,
        "exchange_minimum_cleared": True,
        "risk_contract_interpretation": _risk_interpretation(candidate_notional=candidate_notional),
        "blocked_by": [],
        "safety": {
            "risk_contract_config_written": True,
            "hmac_signature_created": True,
            "signed_request_written": True,
            "signed_order_request_created": True,
            "signed_trading_request_created": True,
            "binance_exchange_info_endpoint_called": True,
            "binance_mark_price_endpoint_called": True,
            "network_allowed": True,
        },
    }


def _r263_ok() -> dict:
    return {
        "attempted": True,
        "succeeded": True,
        "controls_armed": True,
        "experimental_lane_acceptance_recorded": True,
        "lane_controls_written": True,
        "blocked_by": [],
    }


def _r263_blocked() -> dict:
    return {
        "attempted": True,
        "succeeded": False,
        "controls_armed": False,
        "experimental_lane_acceptance_recorded": False,
        "lane_controls_written": False,
        "blocked_by": ["contract_fit_invalid"],
    }


def _r264_ok(
    *,
    signed_triplet_fresh: bool = True,
    idempotency_clean: bool = True,
    candidate_notional: float = 64.0,
) -> dict:
    return {
        "attempted": True,
        "succeeded": signed_triplet_fresh and idempotency_clean,
        "actual_submit_preview_recorded": True,
        "pre_submit_valid": signed_triplet_fresh and idempotency_clean,
        "idempotency_clean": idempotency_clean,
        "blocked_by": [] if signed_triplet_fresh and idempotency_clean else ["signed_triplet_stale" if not signed_triplet_fresh else "prior_live_submit_exists"],
        "candidate_qty": 0.006,
        "candidate_notional_usdt": candidate_notional,
        "exchange_minimum_cleared": True,
        "exact_three_orders": True,
        "main_order_valid": True,
        "stop_order_valid": True,
        "take_profit_order_valid": True,
        "reduce_only_exits": True,
        "signed_triplet_fresh": signed_triplet_fresh,
        "risk_contract_valid": True,
        "risk_contract_interpretation": _risk_interpretation(candidate_notional=candidate_notional),
        "controls_armed": True,
        "experimental_lane_acceptance_recorded": True,
        "prior_live_submit_found": not idempotency_clean,
    }


def _risk_interpretation(*, candidate_notional: float = 64.0) -> dict:
    return {
        "valid": candidate_notional <= 80.0,
        "tiny_live_contract_mode": "explicit_notional_cap_with_leverage",
        "max_position_notional_usdt": 80.0,
        "configured_max_position_notional_usdt": 80.0,
        "leverage": 10.0,
        "derived_margin_budget_usdt": 8.0,
        "candidate_qty": 0.006,
        "candidate_notional_usdt": candidate_notional,
        "clears_exchange_minimum": True,
        "blocked_by": [] if candidate_notional <= 80.0 else ["candidate_notional_exceeds_position_notional_cap"],
    }


def _fresh_candidate_ok(
    *,
    lane_key: str = OFFICIAL,
    origin: dict | None = None,
) -> dict:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    origin = origin or _standard_origin(lane_key=lane_key)
    return {
        "fresh_candidate_available": True,
        "trade_ticket_status": "PROPOSED",
        "ticket_id": "tt_r269",
        "signal_id": "fresh|r269",
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "lane_key": lane_key,
        "expected_lane_key": lane_key,
        "readiness_status": "READY",
        "allowed_now": True,
        "max_position_usd": 80.0,
        "suggested_position_usd": 80.0,
        "suggested_leverage": 10.0,
        "active_contract_mode": "explicit_notional_cap_with_leverage",
        "active_contract_max_notional_usdt": 80.0,
        "active_contract_leverage": 10.0,
        "active_contract_margin_budget_usdt": 8.0,
        "signal_origin_status": origin,
        "strategy_qualification": _strategy_qualification(lane_key=lane_key),
        "strategy_qualified": True,
        "strategy_win_rate_pct": 62.0,
        "strategy_sample_count": 40,
        "strategy_min_sample": 30,
        "exact_risk_contract_status": _exact_risk_contract_status(lane_key=lane_key),
        "exact_risk_contract_found": True,
        "exact_risk_contract_valid": True,
        "signal_origin_family": origin["signal_origin_family"],
        "betrayal_mode_involved": origin["betrayal_mode_involved"],
        "betrayal_inverse_involved": origin["betrayal_inverse_involved"],
        "promotion_family": origin["promotion_family"],
        "promotion_status": origin["promotion_status"],
        "candidate_origin_classification": origin["candidate_origin_classification"],
        "blocked_by": [],
        "order_placed": False,
        "real_order_placed": False,
        "submit_attempted": False,
        "binance_order_endpoint_called": False,
        "secrets_shown": False,
    }


def _current_ticket_context(*, lane_key: str = OFFICIAL, origin: dict | None = None) -> dict:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    return {
        "selected": True,
        "ticket_status": "PROPOSED",
        "ticket_id": "tt_r269",
        "signal_id": "fresh|r269",
        "lane_key": lane_key,
        "actual_ticket_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "blockers": [],
        "signal_origin_status": origin or _standard_origin(lane_key=lane_key),
        "strategy_qualification": _strategy_qualification(lane_key=lane_key),
        "exact_risk_contract_status": _exact_risk_contract_status(lane_key=lane_key),
        "order_placed": False,
        "real_order_placed": False,
        "submit_attempted": False,
        "binance_order_endpoint_called": False,
        "secrets_shown": False,
    }


def _standard_origin(*, lane_key: str = OFFICIAL) -> dict:
    return {
        "signal_id": "fresh|r269",
        "lane_key": lane_key,
        "signal_origin_family": "standard",
        "betrayal_mode_involved": False,
        "betrayal_inverse_involved": False,
        "promotion_family": "standard",
        "promotion_status": "promotion_ready",
        "candidate_origin_classification": "standard checklist",
        "manual_unlock_allowed": True,
        "blocked_by": [],
        "source_record_found": True,
    }


def _strategy_qualification(*, lane_key: str = OFFICIAL) -> dict:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    return {
        "lane_key": lane_key,
        "strategy_qualified": True,
        "qualification_status": "QUALIFIED",
        "win_rate_pct": 62.0,
        "sample_count": 40,
        "avg_pnl_pct": 0.1,
        "live_qualification_class": "LIVE_QUALIFIED",
        "watch_category": "LIVE_QUALIFIED",
        "near_miss_incubator": False,
        "manual_live_unlock_allowed": True,
        "min_sample": 30,
        "min_win_rate_pct": 55.0,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "blocked_by": [],
    }


def _exact_risk_contract_status(*, lane_key: str = OFFICIAL) -> dict:
    return {
        "lane_key": lane_key,
        "exact_contract_found": True,
        "risk_contract_valid": True,
        "blocked_by": [],
        "no_cross_lane_borrowing": True,
    }


def _fresh_candidate_blocked() -> dict:
    return {
        **_fresh_candidate_ok(),
        "fresh_candidate_available": False,
        "trade_ticket_status": "BLOCKED",
        "ticket_id": None,
        "signal_id": None,
        "suggested_position_usd": None,
        "suggested_leverage": None,
        "blocked_by": [
            "no fresh ELIGIBLE_TINY_LIVE BTCUSDT candidate",
            "fresh_trade_ticket_not_proposed",
        ],
    }


def _r264_blocked() -> dict:
    return {
        "attempted": True,
        "succeeded": False,
        "actual_submit_preview_recorded": False,
        "pre_submit_valid": False,
        "idempotency_clean": True,
        "blocked_by": ["order_count_not_three"],
        "exact_three_orders": False,
        "main_order_valid": True,
        "stop_order_valid": True,
        "take_profit_order_valid": False,
        "reduce_only_exits": True,
        "signed_triplet_fresh": True,
        "risk_contract_valid": True,
        "controls_armed": True,
    }


def _assert_no_submit_safety(payload: dict) -> None:
    safety = payload["safety"]
    for key in (
        "submit_allowed",
        "submit_attempted",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "binance_account_endpoint_called",
        "private_binance_endpoint_called",
        "signed_binance_endpoint_called",
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "kill_switch_disabled",
        "secrets_read",
        "secrets_shown",
        "secrets_persisted",
        "secret_values_in_output",
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert safety[key] is False
    assert safety["jit_launch_packet_only"] is True
    assert safety["paper_live_separation_intact"] is True


def _assert_no_secrets(payload: dict) -> None:
    raw = json.dumps(payload, sort_keys=True)
    assert API_KEY not in raw
    assert API_SECRET not in raw
    assert "BINANCE_API_KEY" not in raw
    assert "BINANCE_API_SECRET" not in raw
    for value in os.environ.values():
        if value in {API_KEY, API_SECRET}:
            assert value not in raw
