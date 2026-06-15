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
    assert command["unavailable_reason"].startswith("R267 keeps final live submit command unavailable")
    assert r264b.LIVE_SUBMIT_CONFIRMATION_PHRASE in command["confirmation_phrase"]
    assert "80 USDT notional cap" in command["expected_orders"]["main"]


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
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: _r262b_ok())
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: _r263_ok())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: _r264_ok(signed_triplet_fresh=False))
    payload = _run_exact(tmp_path)
    assert payload["status"] == r264b.TINY_LIVE_JIT_LAUNCH_PACKET_BLOCKED
    assert payload["jit_validation"]["signed_triplet_fresh"] is False
    assert payload["final_live_submit_command_packet"]["available"] is False


def test_failed_r263_arming_blocks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: _r262b_ok())
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: _r263_blocked())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: _r264_ok())
    payload = _run_exact(tmp_path)
    assert payload["jit_launch_overall_status"] == r264b.TINY_LIVE_JIT_BLOCKED_BY_R263_ARMING
    assert payload["jit_step_results"]["r264_dry_preview"]["attempted"] is False


def test_failed_r264_dry_preview_blocks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: _r262b_ok())
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: _r263_ok())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: _r264_blocked())
    payload = _run_exact(tmp_path)
    assert payload["jit_launch_overall_status"] == r264b.TINY_LIVE_JIT_BLOCKED_BY_R264_DRY_PREVIEW
    assert payload["jit_validation"]["r264_dry_preview_valid"] is False


def test_risk_contract_mismatch_blocks_final_command(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: _r262b_ok())
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: _r263_ok())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: _r264_ok(idempotency_clean=False))
    payload = _run_exact(tmp_path)
    assert payload["jit_launch_overall_status"] == r264b.TINY_LIVE_JIT_BLOCKED_BY_IDEMPOTENCY
    assert payload["jit_go_no_go_packet"]["next_required_step"] == "WAIT"


def test_secrets_not_in_output(tmp_path: Path, monkeypatch) -> None:
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


def _patch_success(monkeypatch) -> None:
    monkeypatch.setattr(r264b, "run_r262b_contract_fit_refresh_step", lambda **_: _r262b_ok())
    monkeypatch.setattr(r264b, "run_r263_runtime_arming_step", lambda **_: _r263_ok())
    monkeypatch.setattr(r264b, "run_r264_dry_preview_step", lambda **_: _r264_ok())


def _r262b_ok() -> dict:
    return {
        "attempted": True,
        "succeeded": True,
        "risk_contract_valid": True,
        "signed_triplet_fresh": True,
        "candidate_qty": 0.006,
        "candidate_notional_usdt": 64.0,
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


def _r264_ok(*, signed_triplet_fresh: bool = True, idempotency_clean: bool = True) -> dict:
    return {
        "attempted": True,
        "succeeded": signed_triplet_fresh and idempotency_clean,
        "actual_submit_preview_recorded": True,
        "pre_submit_valid": signed_triplet_fresh and idempotency_clean,
        "idempotency_clean": idempotency_clean,
        "blocked_by": [] if signed_triplet_fresh and idempotency_clean else ["signed_triplet_stale" if not signed_triplet_fresh else "prior_live_submit_exists"],
        "exact_three_orders": True,
        "main_order_valid": True,
        "stop_order_valid": True,
        "take_profit_order_valid": True,
        "reduce_only_exits": True,
        "signed_triplet_fresh": signed_triplet_fresh,
        "risk_contract_valid": True,
        "controls_armed": True,
        "experimental_lane_acceptance_recorded": True,
        "prior_live_submit_found": not idempotency_clean,
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
