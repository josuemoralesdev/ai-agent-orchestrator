from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.app.hammer_radar.operator.tiny_live_controls_arming import ARMING_CONFIRMATION_PHRASE, OFFICIAL_LANE_KEY
from src.app.hammer_radar.operator.tiny_live_risk_contract_fix import (
    DIAGNOSTIC_CONFIRMATION_PHRASE,
    FIX_CONFIRMATION_PHRASE,
    build_tiny_live_risk_contract_diagnostic,
    load_tiny_live_risk_contract_fix_records,
    validate_tiny_live_risk_contract_fix_safety,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _append_ndjson(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _fixtures(tmp_path: Path, *, unsafe: bool = False) -> tuple[Path, Path, Path]:
    log_dir = tmp_path / "logs"
    lane_path = tmp_path / "lane_controls.json"
    risk_path = tmp_path / "tiny_live_risk_contracts.json"
    reference = 63675.0
    stop = 64309.3 if not unsafe else 65099.7
    _append_ndjson(
        log_dir / "tiny_live_fresh_cycle_one_shot.ndjson",
        {
            "target_scope": {"official_lane_key": OFFICIAL_LANE_KEY},
            "one_shot_output_validation": {
                "valid": True,
                "fresh_signed_request_available": True,
                "signed_request_fresh_enough_for_dry_preview": True,
                "dry_preview_recorded": True,
            },
            "one_shot_step_results": {
                "r253_readonly_refresh": {"fresh_mark_price": reference},
            },
        },
    )
    _append_ndjson(
        log_dir / "tiny_live_actual_submit_gate.ndjson",
        {
            "target_scope": {"official_lane_key": OFFICIAL_LANE_KEY},
            "actual_submit_gate_record_id": "r255_test",
            "actual_submit_dry_run_preview": {
                "orders": {
                    "main_order": {"quantity": 0.007, "type": "MARKET", "side": "SELL"},
                    "stop_order": {
                        "quantity": 0.007,
                        "type": "STOP_MARKET",
                        "side": "BUY",
                        "stopPrice": stop,
                        "reduceOnly": True,
                    },
                    "take_profit_order": {
                        "quantity": 0.007,
                        "type": "TAKE_PROFIT_MARKET",
                        "side": "BUY",
                        "reduceOnly": True,
                    },
                }
            },
            "signed_request_freshness": {"fresh_enough_for_real_submit": True},
        },
    )
    _write_json(
        lane_path,
        {
            "schema_version": "1.0",
            "lanes": [
                {"symbol": "ETHUSDT", "timeframe": "8m", "direction": "short", "entry_mode": "x", "mode": "paper"},
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "8m",
                    "direction": "short",
                    "entry_mode": "ladder_close_50_618",
                    "mode": "paper",
                    "max_daily_trades": 1,
                    "require_protective_orders": True,
                },
            ],
        },
    )
    _write_json(
        risk_path,
        {
            "risk_contracts": [
                {
                    "official_lane_key": OFFICIAL_LANE_KEY,
                    "symbol": "BTCUSDT",
                    "timeframe": "8m",
                    "direction": "short",
                    "entry_mode": "ladder_close_50_618",
                    "margin_budget_usdt": 44,
                    "tiny_live_margin_usdt": 44,
                    "max_margin_usdt": 44,
                    "max_loss_usdt": 4.44,
                    "max_notional_usdt": 440,
                    "max_position_notional_usdt": 440,
                    "leverage": 10,
                    "protective_stop_required": True,
                    "take_profit_required": True,
                    "live_execution_enabled": False,
                }
            ]
        },
    )
    return log_dir, lane_path, risk_path


def test_cli_preview_returns_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            "logs/hammer_radar_forward",
            "tiny-live-risk-contract-fix",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["target_scope"]["submit_allowed"] is False
    assert payload["safety"]["order_placed"] is False
    assert "risk_contract_diagnostic" in payload


def test_diagnostic_record_exact_phrase_records_only(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixtures(tmp_path)
    payload = build_tiny_live_risk_contract_diagnostic(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        record_risk_contract_diagnostic=True,
        confirm_risk_contract_diagnostic=DIAGNOSTIC_CONFIRMATION_PHRASE,
    )
    assert payload["risk_contract_diagnostic_recorded"] is True
    assert payload["risk_contract_fix_applied"] is False
    assert payload["safety"]["lane_controls_written"] is False
    assert load_tiny_live_risk_contract_fix_records(log_dir=log_dir, limit=0)


def test_wrong_fix_phrase_rejects(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixtures(tmp_path)
    payload = build_tiny_live_risk_contract_diagnostic(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        apply_risk_contract_fix=True,
        confirm_risk_contract_fix="wrong",
    )
    assert payload["status"] == "TINY_LIVE_RISK_CONTRACT_FIX_REJECTED"
    assert payload["confirmation_valid"] is False
    assert payload["risk_contract_fix_applied"] is False


def test_fix_plan_detects_root_cause_for_safe_contract(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixtures(tmp_path)
    payload = build_tiny_live_risk_contract_diagnostic(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
    )
    assert payload["risk_contract_diagnostic"]["root_cause"] == "already_valid"
    assert payload["controls_recheck_after_fix"]["risk_contract_valid"] is True


def test_unsafe_limit_increase_is_blocked() -> None:
    validation = validate_tiny_live_risk_contract_fix_safety(
        contract={"contract": {"margin_budget_usdt": 45, "leverage": 11, "max_notional_usdt": 441, "max_loss_usdt": 4.45}},
        fix_plan={"blocked_by": []},
    )
    assert validation["safe_to_apply"] is False
    assert "margin_budget_above_44" in validation["blocked_by"]
    assert "max_notional_above_440" in validation["blocked_by"]


def test_exact_fix_confirmation_applies_minimal_safe_fix_without_config_write(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixtures(tmp_path)
    before = risk_path.read_text(encoding="utf-8")
    payload = build_tiny_live_risk_contract_diagnostic(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        apply_risk_contract_fix=True,
        confirm_risk_contract_fix=FIX_CONFIRMATION_PHRASE,
    )
    assert payload["risk_contract_fix_applied"] is True
    assert payload["risk_contract_fix_result"]["risk_contract_valid_after"] is True
    assert risk_path.read_text(encoding="utf-8") == before
    assert payload["safety"]["risk_contract_config_written"] is False


def test_exact_fix_and_arm_controls_writes_only_lane_controls(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixtures(tmp_path)
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = json.loads(lane_path.read_text(encoding="utf-8"))
    payload = build_tiny_live_risk_contract_diagnostic(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        apply_risk_contract_fix=True,
        confirm_risk_contract_fix=FIX_CONFIRMATION_PHRASE,
        arm_controls_after_fix=True,
        confirm_arm_tiny_live_controls=ARMING_CONFIRMATION_PHRASE,
        operator_id="local_operator",
        reason="test",
    )
    after_lane = json.loads(lane_path.read_text(encoding="utf-8"))
    assert payload["controls_arming_recorded"] is True
    assert payload["safety"]["lane_controls_written"] is True
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert after_lane["lanes"][0] == before_lane["lanes"][0]
    assert after_lane["lanes"][1]["mode"] == "tiny_live"
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert "BINANCE_API_KEY" not in json.dumps(payload)
    assert "BINANCE_API_SECRET" not in json.dumps(payload)


def test_unsafe_risk_math_blocks_arm(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixtures(tmp_path, unsafe=True)
    payload = build_tiny_live_risk_contract_diagnostic(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        arm_controls_after_fix=True,
        confirm_arm_tiny_live_controls=ARMING_CONFIRMATION_PHRASE,
    )
    assert payload["risk_contract_diagnostic"]["root_cause"] == "unsafe_limits"
    assert payload["controls_arming_recorded"] is False
    assert payload["safety"]["lane_controls_written"] is False


def test_api_endpoints_exist() -> None:
    from fastapi.testclient import TestClient

    from src.app.hammer_radar.operator.approval_api import app

    client = TestClient(app)
    response = client.get("/tiny-live/risk-contract/review")
    assert response.status_code == 200
    assert response.json()["target_scope"]["submit_allowed"] is False
    rejected = client.post("/tiny-live/risk-contract/fix/apply", json={"confirm_risk_contract_fix": "wrong"})
    assert rejected.status_code == 200
    assert rejected.json()["confirmation_valid"] is False


def test_ui_risk_contract_display_has_no_submit_button() -> None:
    from src.app.hammer_radar.operator.approval_api import _operator_ui_html

    html = _operator_ui_html()
    section = html.split('<section id="tinyLiveControls"', 1)[1].split("</section>", 1)[0]
    assert "Risk contract root cause" in section
    assert "Risk contract fix status" in section
    assert "Submit" not in section
