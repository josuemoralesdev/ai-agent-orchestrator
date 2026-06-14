from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.app.hammer_radar.operator import tiny_live_percentage_risk_contract_fit_regeneration as r262b

OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"
SECRET_SENTINEL = "R262B_SECRET_SHOULD_NOT_APPEAR"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    log_dir = tmp_path / "logs"
    risk_path = tmp_path / "tiny_live_risk_contracts.json"
    lane_path = tmp_path / "lane_controls.json"
    _write_json(
        risk_path,
        {
            "funding_config": {"max_margin_usdt": 44.0, "max_loss_usdt": 4.44},
            "risk_contracts": [
                {
                    "official_lane_key": OFFICIAL,
                    "symbol": "BTCUSDT",
                    "timeframe": "8m",
                    "direction": "short",
                    "entry_mode": "ladder_close_50_618",
                    "tiny_live_margin_usdt": 44,
                    "margin_budget_usdt": 44,
                    "max_margin_usdt": 44,
                    "max_loss_usdt": 4.44,
                    "max_notional_usdt": 440,
                    "max_position_notional_usdt": 440,
                    "leverage": 10,
                    "risk_reward_ratio": 2.0,
                    "live_execution_enabled": False,
                }
            ],
        },
    )
    _write_json(
        lane_path,
        {
            "schema_version": "1.0",
            "lanes": [
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "8m",
                    "direction": "short",
                    "entry_mode": "ladder_close_50_618",
                    "mode": "paper",
                }
            ],
        },
    )
    return log_dir, risk_path, lane_path


def test_cli_preview_returns_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            "logs/hammer_radar_forward",
            "tiny-live-percentage-risk-contract-fit",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == r262b.TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_READY
    assert payload["target_scope"]["submit_allowed"] is False
    assert payload["operator_intervention_model"]["resolved_position_margin_usdt"] == 44.0
    assert payload["operator_intervention_model"]["full_wallet_is_not_position_margin"] is True
    assert payload["safety"]["order_placed"] is False


def test_wrong_confirmation_rejects_without_child_calls(tmp_path: Path, monkeypatch) -> None:
    log_dir, risk_path, _ = _fixture(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(r262b, "run_contract_fit_readonly_refresh", lambda **_: calls.append("r253"))

    payload = r262b.build_tiny_live_percentage_risk_contract_fit_regeneration(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        run_contract_fit_regeneration=True,
        record_contract_fit_regeneration=True,
        confirm_contract_fit_regeneration="wrong",
    )

    assert calls == []
    assert payload["status"] == r262b.TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["contract_fit_regeneration_recorded"] is False
    assert not (log_dir / r262b.LEDGER_FILENAME).exists()
    assert payload["safety"]["risk_contract_config_written"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False


def test_88_wallet_resolves_to_44_margin_and_440_notional(tmp_path: Path) -> None:
    _, risk_path, _ = _fixture(tmp_path)
    current = r262b.load_current_tiny_live_risk_contract(risk_contract_config_path=risk_path)
    model = r262b.derive_percentage_risk_contract_model(current)
    resolved = r262b.resolve_percentage_risk_contract_values(model)

    assert resolved["isolated_risk_wallet_usdt"] == 88.0
    assert resolved["position_margin_pct_of_wallet"] == 0.5
    assert resolved["resolved_position_margin_usdt"] == 44.0
    assert resolved["wallet_buffer_usdt"] == 44.0
    assert resolved["leverage"] == 10.0
    assert resolved["resolved_max_notional_usdt"] == 440.0
    assert resolved["resolved_max_loss_usdt"] <= 4.44


def test_quantity_reduces_to_fit_current_451_notional_case() -> None:
    resolved = {
        "resolved_max_notional_usdt": 440.0,
        "resolved_max_loss_usdt": 4.44,
        "leverage": 10.0,
    }
    before = r262b.validate_quantity_fits_contract(
        quantity=0.007,
        mark_price=64465.4,
        resolved_values=resolved,
        step_size=0.001,
        min_notional=5,
    )
    assert round(before["notional_usdt"], 4) == 451.2578
    assert "notional_exceeds_max_notional" in before["blocked_by"]

    qty = r262b.compute_contract_fit_quantity(
        fresh_mark_price=64465.4,
        max_notional_usdt=440,
        step_size=0.001,
        min_notional=5,
    )
    after = r262b.validate_quantity_fits_contract(
        quantity=qty["candidate_qty"],
        mark_price=64465.4,
        resolved_values=resolved,
        step_size=0.001,
        min_notional=5,
    )
    assert qty["candidate_qty"] == 0.006
    assert after["valid"] is True
    assert after["notional_usdt"] <= 440


def test_percentage_schema_update_does_not_loosen_risk(tmp_path: Path) -> None:
    _, risk_path, _ = _fixture(tmp_path)
    current = r262b.load_current_tiny_live_risk_contract(risk_contract_config_path=risk_path)
    model = r262b.derive_percentage_risk_contract_model(current)
    resolved = r262b.resolve_percentage_risk_contract_values(model)
    validation = r262b.validate_percentage_contract_same_or_stricter(
        current_contract=current["contract"],
        resolved_values=resolved,
    )
    result = r262b.apply_percentage_risk_contract_schema_update(
        risk_contract_config_path=risk_path,
        percentage_contract_model=model,
        resolved_values=resolved,
        safety_validation=validation,
        confirmation_valid=True,
    )
    contract = json.loads(risk_path.read_text(encoding="utf-8"))["risk_contracts"][0]

    assert result["risk_contract_config_written"] is True
    assert contract["uses_percentage_model"] is True
    assert contract["isolated_risk_wallet_usdt"] == 88.0
    assert contract["tiny_live_margin_usdt"] == 44.0
    assert contract["max_notional_usdt"] == 440.0
    assert contract["max_loss_usdt"] <= 4.44
    assert contract["leverage"] == 10.0


def test_exact_confirmation_runs_monkeypatched_child_gates_and_records(tmp_path: Path, monkeypatch) -> None:
    log_dir, risk_path, lane_path = _fixture(tmp_path)
    before_lane = lane_path.read_text(encoding="utf-8")
    monkeypatch.setenv("BINANCE_API_KEY", SECRET_SENTINEL)
    monkeypatch.setenv("BINANCE_API_SECRET", SECRET_SENTINEL)
    monkeypatch.setattr(
        r262b,
        "run_contract_fit_readonly_refresh",
        lambda **_: {
            "attempted": True,
            "succeeded": True,
            "fresh_mark_price": 64465.4,
            "step_size": 0.001,
            "min_notional": 5,
            "blocked_by": [],
        },
    )
    monkeypatch.setattr(
        r262b,
        "run_contract_fit_signed_regeneration",
        lambda **_: {"attempted": True, "succeeded": True, "signed_requests_count": 3, "blocked_by": []},
    )
    monkeypatch.setattr(
        r262b,
        "run_contract_fit_submit_preview",
        lambda **_: {"attempted": True, "succeeded": True, "blocked_by": []},
    )
    monkeypatch.setattr(
        r262b,
        "run_contract_fit_dry_preview",
        lambda **_: {"attempted": True, "succeeded": True, "risk_contract_valid": True, "blocked_by": []},
    )
    monkeypatch.setattr(
        r262b,
        "run_contract_fit_controls_review",
        lambda **_: {
            "attempted": True,
            "succeeded": True,
            "operator_should_arm_controls": True,
            "blocked_by": [],
        },
    )

    payload = r262b.build_tiny_live_percentage_risk_contract_fit_regeneration(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        run_contract_fit_regeneration=True,
        record_contract_fit_regeneration=True,
        confirm_contract_fit_regeneration=r262b.CONTRACT_FIT_CONFIRMATION_PHRASE,
    )
    raw = json.dumps(payload, sort_keys=True)

    assert payload["status"] == r262b.TINY_LIVE_PERCENTAGE_RISK_CONTRACT_FIT_RECORDED
    assert payload["contract_fit_regeneration_recorded"] is True
    assert payload["contract_fit_sizing_plan"]["candidate_qty"] == 0.006
    assert payload["contract_fit_sizing_plan"]["candidate_notional_usdt"] <= 440
    assert payload["output_validation"]["risk_contract_valid_after"] is True
    assert payload["go_no_go_packet"]["go_for_manual_submit_now"] is False
    assert payload["go_no_go_packet"]["go_for_controls_arming"] is True
    assert payload["safety"]["risk_contract_config_written"] is True
    assert payload["safety"]["lane_controls_written"] is False
    assert payload["safety"]["submit_attempted"] is False
    assert payload["safety"]["order_placed"] is False
    assert payload["safety"]["private_binance_endpoint_called"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert SECRET_SENTINEL not in raw
    assert len(r262b.load_tiny_live_percentage_contract_fit_records(log_dir=log_dir, limit=0)) == 1
