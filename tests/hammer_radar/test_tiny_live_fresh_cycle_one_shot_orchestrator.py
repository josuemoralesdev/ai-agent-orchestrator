from __future__ import annotations

import hmac
import json
import subprocess
import urllib.request
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator import tiny_live_fresh_cycle_one_shot_orchestrator as r260

OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"
SECRET_SENTINEL = "R260_SECRET_SHOULD_NOT_APPEAR"


def test_cli_exists_and_returns_json(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path),
            "tiny-live-fresh-cycle-one-shot",
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == r260.TINY_LIVE_FRESH_CYCLE_ONE_SHOT_READY
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["run_fresh_cycle_one_shot_requested"] is False
    assert payload["fresh_cycle_one_shot_recorded"] is False
    assert payload["one_shot_step_plan"]["will_call_public_readonly_binance"] is False
    assert payload["one_shot_step_plan"]["will_sign_locally"] is False
    _assert_preview_step_results(payload)
    _assert_safe(payload, r253=False, r253b=False)
    _assert_no_secret_values(payload)


def test_preview_does_not_network_sign_submit_or_order(tmp_path: Path) -> None:
    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(hmac, "new") as hmac_new,
    ):
        payload = r260.build_tiny_live_fresh_cycle_one_shot_orchestrator(log_dir=tmp_path)

    urlopen.assert_not_called()
    hmac_new.assert_not_called()
    assert payload["confirmation_valid"] is False
    assert payload["fresh_cycle_one_shot_recorded"] is False
    assert not (tmp_path / r260.LEDGER_FILENAME).exists()
    _assert_preview_step_results(payload)
    _assert_safe(payload, r253=False, r253b=False)


def test_wrong_confirmation_rejects_and_does_not_run_steps(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(r260, "run_or_preview_r253_readonly_refresh_step", lambda **_: calls.append("r253"))

    payload = r260.build_tiny_live_fresh_cycle_one_shot_orchestrator(
        log_dir=tmp_path,
        run_fresh_cycle_one_shot=True,
        record_fresh_cycle_one_shot=True,
        confirm_tiny_live_fresh_cycle_one_shot="wrong",
    )

    assert calls == []
    assert payload["status"] == r260.TINY_LIVE_FRESH_CYCLE_ONE_SHOT_REJECTED
    assert payload["fresh_cycle_one_shot_overall_status"] == (
        r260.TINY_LIVE_FRESH_CYCLE_ONE_SHOT_REJECTED_BAD_CONFIRMATION
    )
    assert payload["confirmation_valid"] is False
    assert payload["fresh_cycle_one_shot_recorded"] is False
    assert not (tmp_path / r260.LEDGER_FILENAME).exists()
    _assert_safe(payload, r253=False, r253b=False)


def test_exact_confirmation_can_orchestrate_with_monkeypatched_steps(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    _patch_successful_steps(monkeypatch, calls)

    payload = r260.build_tiny_live_fresh_cycle_one_shot_orchestrator(
        log_dir=tmp_path,
        run_fresh_cycle_one_shot=True,
        record_fresh_cycle_one_shot=True,
        confirm_tiny_live_fresh_cycle_one_shot=r260.CONFIRM_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_PHRASE,
    )

    assert calls == ["r253", "r253b", "r254", "r255", "r258"]
    assert payload["status"] == r260.TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["fresh_cycle_one_shot_recorded"] is True
    assert payload["one_shot_output_validation"]["valid"] is True
    assert payload["one_shot_go_no_go_packet"] == {
        "go_for_manual_submit_now": False,
        "go_for_live_control_review": True,
        "go_for_r260_to_r261_ui": True,
        "next_required_step": "LIVE_CONTROL_REVIEW",
        "operator_should_submit_now": False,
        "operator_should_arm_live_controls_manually": True,
    }
    assert payload["one_shot_operator_packet"]["operator_should_not_submit_from_r260"] is True
    assert payload["one_shot_checkpoint_matrix"]["r258_recheck_succeeded"] is True
    assert payload["fresh_cycle_one_shot_overall_status"] == (
        r260.TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED_READY_FOR_LIVE_CONTROL_REVIEW
    )
    assert len(r260.load_tiny_live_fresh_cycle_one_shot_records(log_dir=tmp_path, limit=0)) == 1
    _assert_safe(payload, r253=True, r253b=True)
    _assert_no_secret_values(payload)


def test_one_shot_blocks_if_r253_fails(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(r260, "run_or_preview_r253_readonly_refresh_step", lambda **_: _fail("r253", calls))
    payload = _run_confirmed(tmp_path)

    assert calls == ["r253"]
    assert payload["status"] == r260.TINY_LIVE_FRESH_CYCLE_ONE_SHOT_RECORDED
    assert payload["fresh_cycle_one_shot_overall_status"] == r260.TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R253
    assert payload["one_shot_checkpoint_matrix"]["r253_succeeded"] is False
    assert payload["one_shot_go_no_go_packet"]["next_required_step"] == "R253_REFRESH_AGAIN"
    _assert_safe(payload, r253=True, r253b=False)


def test_one_shot_blocks_if_r253b_fails(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(r260, "run_or_preview_r253_readonly_refresh_step", lambda **_: _success("r253", calls))
    monkeypatch.setattr(r260, "run_or_preview_r253b_regeneration_step", lambda **_: _fail("r253b", calls))
    payload = _run_confirmed(tmp_path)

    assert calls == ["r253", "r253b"]
    assert payload["fresh_cycle_one_shot_overall_status"] == r260.TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R253B
    assert payload["one_shot_checkpoint_matrix"]["r253b_succeeded"] is False
    _assert_safe(payload, r253=True, r253b=False)


def test_one_shot_blocks_if_r254_fails(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(r260, "run_or_preview_r253_readonly_refresh_step", lambda **_: _success("r253", calls))
    monkeypatch.setattr(r260, "run_or_preview_r253b_regeneration_step", lambda **_: _success("r253b", calls))
    monkeypatch.setattr(r260, "run_or_preview_r254_submit_gate_preview_step", lambda **_: _fail("r254", calls))
    payload = _run_confirmed(tmp_path)

    assert calls == ["r253", "r253b", "r254"]
    assert payload["fresh_cycle_one_shot_overall_status"] == r260.TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R254
    assert payload["one_shot_checkpoint_matrix"]["r254_succeeded"] is False
    _assert_safe(payload, r253=True, r253b=True)


def test_one_shot_blocks_if_r255_dry_preview_fails(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(r260, "run_or_preview_r253_readonly_refresh_step", lambda **_: _success("r253", calls))
    monkeypatch.setattr(r260, "run_or_preview_r253b_regeneration_step", lambda **_: _success("r253b", calls))
    monkeypatch.setattr(r260, "run_or_preview_r254_submit_gate_preview_step", lambda **_: _success("r254", calls))
    monkeypatch.setattr(r260, "run_or_preview_r255_dry_preview_step", lambda **_: _fail("r255", calls))
    payload = _run_confirmed(tmp_path)

    assert calls == ["r253", "r253b", "r254", "r255"]
    assert payload["fresh_cycle_one_shot_overall_status"] == r260.TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R255
    assert payload["one_shot_checkpoint_matrix"]["r255_dry_preview_succeeded"] is False
    _assert_safe(payload, r253=True, r253b=True)


def test_one_shot_blocks_if_r258_recheck_fails(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(r260, "run_or_preview_r253_readonly_refresh_step", lambda **_: _success("r253", calls))
    monkeypatch.setattr(r260, "run_or_preview_r253b_regeneration_step", lambda **_: _success("r253b", calls))
    monkeypatch.setattr(r260, "run_or_preview_r254_submit_gate_preview_step", lambda **_: _success("r254", calls))
    monkeypatch.setattr(r260, "run_or_preview_r255_dry_preview_step", lambda **_: _success("r255", calls))
    monkeypatch.setattr(r260, "run_or_preview_r258_manual_checkpoint_recheck_step", lambda **_: _fail("r258", calls))
    payload = _run_confirmed(tmp_path)

    assert calls == ["r253", "r253b", "r254", "r255", "r258"]
    assert payload["fresh_cycle_one_shot_overall_status"] == r260.TINY_LIVE_FRESH_CYCLE_ONE_SHOT_BLOCKED_BY_R258
    assert payload["one_shot_checkpoint_matrix"]["r258_recheck_succeeded"] is False
    _assert_safe(payload, r253=True, r253b=True)


def test_no_binance_order_endpoint_submit_live_control_or_config_mutation(tmp_path: Path, monkeypatch) -> None:
    risk = tmp_path / "tiny_live_risk_contracts.json"
    lane = tmp_path / "lane_controls.json"
    env_file = tmp_path / "binance-signing.env"
    risk.write_text('{"unchanged":true}\n', encoding="utf-8")
    lane.write_text('{"unchanged":true}\n', encoding="utf-8")
    env_file.write_text(f"BINANCE_API_KEY={SECRET_SENTINEL}\n", encoding="utf-8")
    before = (risk.read_text(encoding="utf-8"), lane.read_text(encoding="utf-8"), env_file.read_text(encoding="utf-8"))
    calls: list[str] = []
    _patch_successful_steps(monkeypatch, calls)

    payload = _run_confirmed(tmp_path)

    assert before == (
        risk.read_text(encoding="utf-8"),
        lane.read_text(encoding="utf-8"),
        env_file.read_text(encoding="utf-8"),
    )
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["submit_attempted"] is False
    assert payload["safety"]["order_placed"] is False
    assert payload["safety"]["live_controls_armed_by_phase"] is False
    assert payload["safety"]["config_written"] is False
    assert payload["safety"]["lane_controls_written"] is False
    _assert_no_secret_values(payload)


def _run_confirmed(tmp_path: Path) -> dict[str, object]:
    return r260.build_tiny_live_fresh_cycle_one_shot_orchestrator(
        log_dir=tmp_path,
        run_fresh_cycle_one_shot=True,
        record_fresh_cycle_one_shot=True,
        confirm_tiny_live_fresh_cycle_one_shot=r260.CONFIRM_TINY_LIVE_FRESH_CYCLE_ONE_SHOT_PHRASE,
    )


def _patch_successful_steps(monkeypatch, calls: list[str]) -> None:
    monkeypatch.setattr(r260, "run_or_preview_r253_readonly_refresh_step", lambda **_: _success("r253", calls))
    monkeypatch.setattr(r260, "run_or_preview_r253b_regeneration_step", lambda **_: _success("r253b", calls))
    monkeypatch.setattr(r260, "run_or_preview_r254_submit_gate_preview_step", lambda **_: _success("r254", calls))
    monkeypatch.setattr(r260, "run_or_preview_r255_dry_preview_step", lambda **_: _success("r255", calls))
    monkeypatch.setattr(r260, "run_or_preview_r258_manual_checkpoint_recheck_step", lambda **_: _success("r258", calls))


def _success(name: str, calls: list[str]) -> dict[str, object]:
    calls.append(name)
    result = {"attempted": True, "succeeded": True, "blocked_by": []}
    if name == "r253":
        result["fresh_mark_price"] = 63675.0
    if name == "r253b":
        result["signed_requests_count"] = 3
    return result


def _fail(name: str, calls: list[str]) -> dict[str, object]:
    calls.append(name)
    result = {"attempted": True, "succeeded": False, "blocked_by": [f"{name}_failed"]}
    if name == "r253":
        result["fresh_mark_price"] = None
    if name == "r253b":
        result["signed_requests_count"] = None
    return result


def _assert_preview_step_results(payload: dict[str, object]) -> None:
    results = payload["one_shot_step_results"]
    assert isinstance(results, dict)
    for result in results.values():
        assert result["attempted"] is False
        assert result["succeeded"] is False


def _assert_safe(payload: dict[str, object], *, r253: bool, r253b: bool) -> None:
    safety = payload["safety"]
    assert isinstance(safety, dict)
    for key in (
        "env_written",
        "env_mutated",
        "external_env_file_written",
        "config_written",
        "risk_contract_config_written",
        "lane_controls_written",
        "live_config_written",
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
        "live_controls_armed_by_phase",
        "secrets_shown",
        "secrets_persisted",
        "secret_values_in_output",
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert safety[key] is False
    assert safety["binance_exchange_info_endpoint_called"] is r253
    assert safety["binance_mark_price_endpoint_called"] is r253
    assert safety["network_allowed"] is r253
    assert safety["hmac_signature_created"] is r253b
    assert safety["signed_request_written"] is r253b
    assert safety["signed_order_request_created"] is r253b
    assert safety["signed_trading_request_created"] is r253b
    assert safety["fresh_cycle_one_shot_only"] is True
    assert safety["paper_live_separation_intact"] is True


def _assert_no_secret_values(payload: dict[str, object]) -> None:
    raw = json.dumps(payload, sort_keys=True)
    assert SECRET_SENTINEL not in raw
    assert "BINANCE_API_KEY" not in raw
    assert "BINANCE_API_SECRET" not in raw
