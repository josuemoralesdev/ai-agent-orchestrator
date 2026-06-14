from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.app.hammer_radar.operator.tiny_live_controls_arming import (
    ARMING_CONFIRMATION_PHRASE,
    OFFICIAL_LANE_KEY,
    REVIEW_CONFIRMATION_PHRASE,
    build_tiny_live_controls_review,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _append_ndjson(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _fixture_paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    log_dir = tmp_path / "logs"
    lane_path = tmp_path / "lane_controls.json"
    risk_path = tmp_path / "tiny_live_risk_contracts.json"
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
        },
    )
    _append_ndjson(
        log_dir / "tiny_live_actual_submit_gate.ndjson",
        {
            "target_scope": {"official_lane_key": OFFICIAL_LANE_KEY},
            "actual_submit_gate_record_id": "r255_test",
            "actual_submit_dry_run_preview": {
                "orders": {
                    "main_order": {"quantity": 0.001, "type": "MARKET", "side": "SELL"},
                    "stop_order": {"quantity": 0.001, "type": "STOP_MARKET", "side": "BUY", "stopPrice": 63676.0},
                    "take_profit_order": {"quantity": 0.001, "type": "TAKE_PROFIT_MARKET", "side": "BUY"},
                }
            },
            "risk_contract_submit_summary": {"within_tiny_live_contract": True},
            "signed_request_freshness": {"fresh_enough_for_real_submit": True},
        },
    )
    _write_json(
        lane_path,
        {
            "schema_version": "1.0",
            "default_mode": "disabled",
            "notes": ["test"],
            "lanes": [
                {
                    "symbol": "ETHUSDT",
                    "timeframe": "8m",
                    "direction": "short",
                    "entry_mode": "ladder_close_50_618",
                    "mode": "paper",
                    "max_daily_trades": 1,
                },
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "8m",
                    "direction": "short",
                    "entry_mode": "ladder_close_50_618",
                    "mode": "paper",
                    "max_daily_trades": 1,
                    "max_daily_loss_pct": 0.15,
                    "freshness_seconds": 60,
                    "cooldown_after_loss_minutes": 120,
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
                    "max_loss_usdt": 4.44,
                    "max_notional_usdt": 440,
                    "tiny_live_margin_usdt": 44,
                    "leverage": 10,
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
            "tiny-live-controls-arming",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["target_scope"]["submit_allowed"] is False
    assert payload["safety"]["order_placed"] is False
    assert payload["controls_review_packet"]["submit_still_forbidden"] is True


def test_review_record_exact_phrase_records_review_only(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture_paths(tmp_path)
    payload = build_tiny_live_controls_review(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        record_controls_review=True,
        confirm_tiny_live_controls_review=REVIEW_CONFIRMATION_PHRASE,
    )
    assert payload["controls_review_recorded"] is True
    assert payload["controls_arming_recorded"] is False
    assert payload["safety"]["lane_controls_written"] is False
    assert (log_dir / "tiny_live_controls_arming.ndjson").exists()


def test_wrong_review_phrase_rejects(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture_paths(tmp_path)
    payload = build_tiny_live_controls_review(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        record_controls_review=True,
        confirm_tiny_live_controls_review="wrong",
    )
    assert payload["status"] == "TINY_LIVE_CONTROLS_ARMING_REJECTED"
    assert payload["controls_review_recorded"] is False
    assert payload["safety"]["lane_controls_written"] is False


def test_wrong_arming_phrase_rejects(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture_paths(tmp_path)
    payload = build_tiny_live_controls_review(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        arm_tiny_live_controls=True,
        confirm_arm_tiny_live_controls="wrong",
    )
    assert payload["status"] == "TINY_LIVE_CONTROLS_ARMING_REJECTED"
    assert payload["confirmation_valid"] is False
    assert payload["controls_arming_recorded"] is False
    assert payload["safety"]["lane_controls_written"] is False


def test_exact_arming_phrase_writes_only_official_lane_and_preserves_unrelated(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture_paths(tmp_path)
    before = json.loads(lane_path.read_text(encoding="utf-8"))
    payload = build_tiny_live_controls_review(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        arm_tiny_live_controls=True,
        confirm_arm_tiny_live_controls=ARMING_CONFIRMATION_PHRASE,
        operator_id="local_operator",
        reason="test arming",
    )
    after = json.loads(lane_path.read_text(encoding="utf-8"))
    assert payload["controls_arming_recorded"] is True
    assert payload["safety"]["lane_controls_written"] is True
    assert payload["safety"]["submit_allowed"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert after["lanes"][0] == before["lanes"][0]
    assert after["lanes"][1]["mode"] == "tiny_live"
    assert after["lanes"][1]["tiny_live_armed_by_phase"] == "R261"
    assert "BINANCE_API_KEY" not in json.dumps(payload)
    assert "BINANCE_API_SECRET" not in json.dumps(payload)


def test_risk_contract_invalid_blocks_arming(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture_paths(tmp_path)
    risk = json.loads(risk_path.read_text(encoding="utf-8"))
    risk["risk_contracts"][0]["max_notional_usdt"] = 1.0
    _write_json(risk_path, risk)
    payload = build_tiny_live_controls_review(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        arm_tiny_live_controls=True,
        confirm_arm_tiny_live_controls=ARMING_CONFIRMATION_PHRASE,
    )
    assert payload["controls_arming_recorded"] is False
    assert "risk_contract_invalid" in payload["arming_result"]["blocked_by"]
    assert payload["controls_arming_overall_status"] == "TINY_LIVE_CONTROLS_ARMING_BLOCKED_BY_RISK_CONTRACT"


def test_api_get_review_and_post_arm_requires_confirmation() -> None:
    from fastapi.testclient import TestClient

    from src.app.hammer_radar.operator.approval_api import app

    client = TestClient(app)
    get_response = client.get("/tiny-live/controls/review")
    assert get_response.status_code == 200
    assert get_response.json()["target_scope"]["submit_allowed"] is False

    post_response = client.post(
        "/tiny-live/controls/arm",
        json={"confirm_arm_tiny_live_controls": "wrong", "operator_id": "test"},
    )
    assert post_response.status_code == 200
    body = post_response.json()
    assert body["confirmation_valid"] is False
    assert body["controls_arming_recorded"] is False


def test_ui_card_has_no_submit_button() -> None:
    from src.app.hammer_radar.operator.approval_api import _operator_ui_html

    html = _operator_ui_html()
    section = html.split('<section id="tinyLiveControls"', 1)[1].split("</section>", 1)[0]
    assert "Submit" not in section
    assert "submit forbidden" in section
