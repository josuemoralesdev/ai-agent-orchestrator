from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from src.app.hammer_radar.operator import tiny_live_final_console as r263
from src.app.hammer_radar.operator.tiny_live_actual_submit_reconciliation import (
    LIVE_SUBMIT_CONFIRMATION_PHRASE,
)

OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"
SECRET_SENTINEL = "R263_SECRET_SHOULD_NOT_APPEAR"
REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_LANE_CONTROLS = REPO_ROOT / "configs" / "hammer_radar" / "lane_controls.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _append_ndjson(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    log_dir = tmp_path / "logs"
    lane_path = tmp_path / "lane_controls.json"
    risk_path = tmp_path / "tiny_live_risk_contracts.json"
    _write_json(
        lane_path,
        {
            "schema_version": "1.0",
            "lanes": [
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "13m",
                    "direction": "long",
                    "entry_mode": "ladder_close_50_618",
                    "mode": "tiny_live",
                },
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "44m",
                    "direction": "long",
                    "entry_mode": "ladder_close_50_618",
                    "mode": "tiny_live",
                },
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "8m",
                    "direction": "short",
                    "entry_mode": "ladder_close_50_618",
                    "mode": "paper",
                },
            ],
        },
    )
    _write_json(
        risk_path,
        {
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
                    "max_notional_usdt": 44,
                    "max_position_notional_usdt": 44,
                    "tiny_live_contract_mode": "position_notional_cap",
                    "leverage": 1,
                    "live_execution_enabled": False,
                }
            ]
        },
    )
    _append_ndjson(
        log_dir / "tiny_live_percentage_risk_contract_fit.ndjson",
        {
            "target_scope": {"official_lane_key": OFFICIAL},
            "contract_fit_record_id": "r262b_test",
            "percentage_contract_model": {
                "uses_percentage_model": True,
                "resolved_values": {
                    "isolated_risk_wallet_usdt": 88,
                    "position_margin_pct_of_wallet": 0.5,
                    "resolved_position_margin_usdt": 44,
                    "leverage": 1,
                    "resolved_max_notional_usdt": 44,
                    "wallet_buffer_usdt": 44,
                },
            },
            "contract_fit_sizing_plan": {
                "candidate_qty": 0.006,
                "candidate_notional_usdt": 42.0,
                "candidate_margin_usdt": 42.0,
                "candidate_estimated_loss_usdt": 4.44,
                "fits_max_notional": True,
                "fits_max_loss": True,
                "fits_binance_step_size": True,
                "fits_binance_min_notional": True,
            },
            "output_validation": {
                "valid": True,
                "risk_contract_valid_after": True,
                "fresh_signed_request_available": True,
                "signed_request_fresh_enough_for_dry_preview": True,
            },
        },
    )
    _append_ndjson(
        log_dir / "tiny_live_submit_gate_preview.ndjson",
        {
            "target_scope": {"official_lane_key": OFFICIAL},
            "submit_gate_preview_recorded": True,
            "fresh_signed_request_summary": {"signed_requests_count": 3},
        },
    )
    _append_ndjson(
        log_dir / "tiny_live_actual_submit_gate.ndjson",
        {
            "target_scope": {"official_lane_key": OFFICIAL},
            "actual_submit_gate_preview_recorded": True,
            "actual_submit_dry_run_preview": {
                "orders": {
                    "main_order": {"side": "SELL", "quantity": 0.006, "type": "MARKET"},
                    "stop_order": {"side": "BUY", "quantity": 0.006, "reduceOnly": True, "type": "STOP_MARKET"},
                    "take_profit_order": {
                        "side": "BUY",
                        "quantity": 0.006,
                        "reduceOnly": True,
                        "type": "TAKE_PROFIT_MARKET",
                    },
                }
            },
            "risk_contract_submit_summary": {"within_tiny_live_contract": True},
        },
    )
    _append_ndjson(
        log_dir / "strategy_promotion_status.ndjson",
        {
            "promotion_ready": [
                {
                    "strategy_key": "BTCUSDT|13m|long|ladder_close_50_618",
                    "sample_count": 268,
                    "win_rate_pct": 47.39,
                    "avg_pnl_pct": 0.0043,
                    "total_pnl_pct": 1.154,
                },
                {
                    "strategy_key": "BTCUSDT|44m|long|ladder_close_50_618",
                    "sample_count": 69,
                    "win_rate_pct": 59.42,
                    "avg_pnl_pct": 0.0429,
                    "total_pnl_pct": 2.9622,
                },
            ]
        },
    )
    _append_ndjson(
        log_dir / "readiness_status.ndjson",
        {
            "readiness_status": "NOT_READY",
            "live_execution_enabled": False,
            "order_placed": False,
            "blockers": [
                "no fresh ELIGIBLE_TINY_LIVE BTCUSDT candidate",
                "only expired otherwise-eligible candidates are available",
            ],
            "current_state": {
                "fresh_eligible_count": 0,
                "expired_eligible_count": 1,
                "paper_only_count": 2,
                "latest_candidate_age_minutes": 20.66,
            },
        },
    )
    return log_dir, lane_path, risk_path


def _append_exchange_minimum_record(log_dir: Path, *, mark_price: float = 70000.0) -> None:
    _append_ndjson(
        log_dir / "tiny_live_binance_readonly_precision_mark_price_gate.ndjson",
        {
            "target_scope": {"official_lane_key": OFFICIAL},
            "readonly_fetch_performed": True,
            "binance_readonly_result": {
                "fetched": True,
                "exchange_info_endpoint_called": True,
                "mark_price_endpoint_called": True,
                "order_endpoint_called": False,
                "account_endpoint_called": False,
                "signed_request_created": False,
                "precision_snapshot": {
                    "found": True,
                    "symbol": "BTCUSDT",
                    "quantity_precision": 3,
                    "min_qty": 0.001,
                    "step_size": 0.001,
                    "price_precision": 1,
                    "tick_size": 0.1,
                    "min_notional": 5.0,
                    "source": "binance_public_exchangeInfo",
                },
                "mark_price_snapshot": {
                    "found": True,
                    "symbol": "BTCUSDT",
                    "mark_price": mark_price,
                    "timestamp": 1781114400000,
                    "source": "binance_public_premiumIndex",
                },
            },
            "safety": {
                "order_placed": False,
                "binance_order_endpoint_called": False,
                "binance_test_order_endpoint_called": False,
                "secrets_shown": False,
            },
        },
    )


def test_cli_preview_returns_json() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            "logs/hammer_radar_forward",
            "tiny-live-final-console",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["target_scope"]["submit_allowed"] is False
    assert payload["target_scope"]["order_placed"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False


def test_review_record_exact_phrase_records_review_only(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    before_lane = lane_path.read_text(encoding="utf-8")
    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        record_final_console_review=True,
        confirm_final_console_review=r263.FINAL_CONSOLE_REVIEW_CONFIRMATION_PHRASE,
    )
    assert payload["final_console_review_recorded"] is True
    assert payload["final_console_controls_armed"] is False
    assert payload["safety"]["lane_controls_written"] is False
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert (log_dir / r263.LEDGER_FILENAME).exists()


def test_wrong_arming_phrase_rejects(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        arm_controls_from_final_console=True,
        confirm_final_console_controls_arming="wrong",
    )
    assert payload["status"] == r263.TINY_LIVE_FINAL_CONSOLE_ARMING_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["final_console_controls_armed"] is False
    assert payload["safety"]["lane_controls_written"] is False


def test_final_console_surfaces_current_4m_long_lane_expected_orders_and_origin(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    monkeypatch.setattr(r263, "build_trade_ticket", lambda **_: _long_trade_ticket())
    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
    )
    assert payload["current_proposed_ticket_lane"]["lane_key"] == "BTCUSDT|4m|long|ladder_close_50_618"
    assert payload["current_proposed_ticket_lane"]["matches_console_lane"] is False
    assert payload["lane_specific_expected_orders"]["main"].startswith("BUY MARKET")
    assert payload["lane_specific_expected_orders"]["stop"] == "SELL STOP_MARKET REDUCE_ONLY"
    assert payload["signal_origin_status"]["signal_origin_family"] == "standard"
    assert payload["submit_allowed"] is False
    assert payload["order_placed"] is False
    assert payload["binance_order_endpoint_called"] is False


def test_exact_arming_phrase_blocks_near_miss_or_paper_lane_without_writes(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")
    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        arm_controls_from_final_console=True,
        confirm_final_console_controls_arming=r263.FINAL_CONSOLE_CONTROLS_ARMING_CONFIRMATION_PHRASE,
        operator_id="local_operator",
        reason="R263 acceptance test",
    )
    assert payload["final_console_controls_armed"] is False
    assert payload["operator_choice_panel"]["experimental_lane_acceptance_recorded"] is False
    assert payload["safety"]["lane_controls_written"] is False
    assert payload["safety"]["risk_contract_config_written"] is False
    assert payload["safety"]["submit_attempted"] is False
    assert payload["safety"]["order_placed"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert "strategy_near_miss_not_live_eligible" in payload["controls_arming_result"]["blocked_by"]
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane


def test_cli_exact_arming_for_8m_short_keeps_injected_temp_lane_controls_unchanged(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    real_before = REAL_LANE_CONTROLS.read_text(encoding="utf-8")
    temp_before = lane_path.read_text(encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-final-console",
            "--lane-controls-path",
            str(lane_path),
            "--risk-contract-config-path",
            str(risk_path),
            "--arm-controls-from-final-console",
            "--confirm-final-console-controls-arming",
            r263.FINAL_CONSOLE_CONTROLS_ARMING_CONFIRMATION_PHRASE,
            "--operator-id",
            "local_operator",
            "--reason",
            "R263 temp path isolation test",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["final_console_controls_armed"] is False
    assert payload["safety"]["lane_controls_written"] is False
    assert "strategy_near_miss_not_live_eligible" in payload["controls_arming_result"]["blocked_by"]
    assert lane_path.read_text(encoding="utf-8") == temp_before
    assert REAL_LANE_CONTROLS.read_text(encoding="utf-8") == real_before


def test_r262b_valid_panel_loads_latest_record(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
    )
    panel = payload["contract_fit_panel"]
    assert panel["r262b_found"] is True
    assert panel["risk_contract_valid"] is True
    assert panel["candidate_qty"] == 0.006
    assert panel["fits_contract"] is True


def test_r270c_final_console_does_not_surface_stale_risk_as_active_without_ticket(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    risk = json.loads(risk_path.read_text(encoding="utf-8"))
    row = risk["risk_contracts"][0]
    row.update(
        {
            "tiny_live_contract_mode": "explicit_notional_cap_with_leverage",
            "max_position_notional_usdt": 80.0,
            "max_notional_usdt": 80.0,
            "leverage": 10.0,
            "margin_budget_usdt": 8.0,
            "tiny_live_margin_usdt": 8.0,
        }
    )
    risk_path.write_text(json.dumps(risk), encoding="utf-8")
    _append_exchange_minimum_record(log_dir, mark_price=67000.0)

    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
    )

    interpretation = payload["risk_contract_interpretation"]
    exchange = payload["exchange_minimum_decision_packet"]
    assert interpretation["active_context"] == "no_current_proposed_ticket"
    assert interpretation["no_current_proposed_ticket"] is True
    assert "no_current_proposed_ticket" in interpretation["blocked_by"]
    assert payload["previous_r264_preview"]["found"] is False
    assert payload["target_scope"]["historical_official_lane_key"] == OFFICIAL
    assert payload["current_proposed_ticket_lane"]["lane_key"] is None
    assert payload["current_proposed_ticket_lane"]["no_current_ticket"] is True
    assert payload["lane_specific_expected_orders"] is None
    assert exchange["configured_cap_clears_exchange_minimum"] is True
    assert payload["final_console_go_no_go_packet"]["next_required_step"] == "WAIT_FOR_LIVE_QUALIFIED_FRESH_CANDIDATE"
    assert payload["recommended_next_operator_move"].startswith("WAIT_FOR_LIVE_QUALIFIED_FRESH_CANDIDATE")
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["submit_attempted"] is False
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["secrets_shown"] is False


def test_no_current_ticket_suppresses_stale_jit_actual_submit_wording(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    _append_ndjson(
        log_dir / "tiny_live_jit_launch_packet.ndjson",
        {
            "target_scope": {"official_lane_key": OFFICIAL},
            "jit_validation": {"valid": True},
            "final_live_submit_command_packet": {
                "available": True,
                "command": "stale command should not appear",
                "confirmation_phrase": LIVE_SUBMIT_CONFIRMATION_PHRASE,
                "packet_lane_key": OFFICIAL,
                "expected_orders": {
                    "main": "SELL MARKET quantity must remain within 80 USDT notional cap",
                    "stop": "BUY STOP_MARKET REDUCE_ONLY",
                    "take_profit": "BUY TAKE_PROFIT_MARKET REDUCE_ONLY",
                },
                "gate_validation": {"valid": True, "blocked_by": []},
            },
        },
    )

    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
    )

    command = payload["final_live_submit_command_packet"]
    assert payload["current_proposed_ticket_lane"]["lane_key"] is None
    assert payload["lane_specific_expected_orders"] is None
    assert command["available"] is False
    assert command["command"] == ""
    assert command["confirmation_phrase"] == ""
    assert command["expected_orders"] is None
    assert command["packet_lane_key"] is None
    assert command["historical_official_lane_key"] == OFFICIAL
    assert "no_current_ticket" in command["gate_validation"]["blocked_by"]
    assert payload["final_console_go_no_go_packet"]["next_required_step"] == "WAIT_FOR_LIVE_QUALIFIED_FRESH_CANDIDATE"
    assert payload["recommended_next_operator_move"].startswith("WAIT_FOR_LIVE_QUALIFIED_FRESH_CANDIDATE")
    assert payload["final_command_available"] is False
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["submit_attempted"] is False
    assert payload["binance_order_endpoint_called"] is False


def test_r269_final_console_surfaces_fresh_candidate_status(tmp_path: Path, monkeypatch) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)

    monkeypatch.setattr(
        r263,
        "build_trade_ticket",
        lambda **_: {
            "ticket_status": "PROPOSED",
            "ticket_id": "tt_r269",
            "signal_id": "fresh|r269",
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "lane_key": OFFICIAL,
            "readiness_status": "READY",
            "allowed_now": True,
            "max_position_usd": 80.0,
            "suggested_position_usd": 80.0,
            "suggested_leverage": 10.0,
            "active_contract_mode": "explicit_notional_cap_with_leverage",
            "active_contract_max_notional_usdt": 80.0,
            "active_contract_leverage": 10.0,
            "active_contract_margin_budget_usdt": 8.0,
            "signal_origin": {
                "signal_id": "fresh|r269",
                "lane_key": OFFICIAL,
                "signal_origin_family": "standard",
                "betrayal_mode_involved": False,
                "betrayal_inverse_involved": False,
                "promotion_family": "standard",
                "promotion_status": "known_not_promotion_ready",
                "candidate_origin_classification": "standard checklist",
                "manual_unlock_allowed": True,
                "blocked_by": [],
            },
            "strategy_qualification": {
                "lane_key": OFFICIAL,
                "strategy_qualified": True,
                "qualification_status": "QUALIFIED",
                "win_rate_pct": 62.0,
                "sample_count": 40,
                "min_sample": 30,
                "min_win_rate_pct": 55.0,
                "blocked_by": [],
            },
            "strategy_qualified": True,
            "strategy_win_rate_pct": 62.0,
            "strategy_sample_count": 40,
            "strategy_min_sample": 30,
            "exact_risk_contract_status": {
                "lane_key": OFFICIAL,
                "exact_contract_found": True,
                "risk_contract_valid": True,
                "blocked_by": [],
            },
            "exact_risk_contract_found": True,
            "exact_risk_contract_valid": True,
            "blockers": [],
        },
    )

    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
    )

    fresh = payload["fresh_candidate_status"]
    interpretation = payload["risk_contract_interpretation"]
    assert payload["fresh_candidate_available"] is True
    assert payload["trade_ticket_status"] == "PROPOSED"
    assert fresh["signal_id"] == "fresh|r269"
    assert fresh["max_position_usd"] == 80.0
    assert fresh["suggested_position_usd"] == 80.0
    assert fresh["suggested_leverage"] == 10.0
    assert interpretation["active_context"] == "current_proposed_ticket"
    assert interpretation["max_position_notional_usdt"] == 80.0
    assert interpretation["leverage"] == 10.0
    assert interpretation["candidate_notional_usdt"] == 80.0
    assert payload["submit_allowed"] is False
    assert payload["order_placed"] is False
    assert payload["binance_order_endpoint_called"] is False


def test_8m_short_lane_marked_paper_only_promotion_mismatched(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
    )
    lane = payload["lane_intelligence_panel"]
    assert lane["execution_lane_timeframe_status"] == "paper_only"
    assert lane["execution_lane_promotion_status"] == "not_live_qualified"
    assert lane["live_qualification_class"] in {"PAPER_ONLY", "NEAR_MISS_INCUBATOR"}
    assert lane["execution_lane_direction_status"] == "experimental_short"
    assert lane["operator_acceptance_required"] is True


def test_legacy_promoted_lanes_are_relabelled_not_current_live_qualified(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
    )
    lane = payload["lane_intelligence_panel"]
    legacy = lane["historical_legacy_promoted_lanes"]
    assert lane["promoted_lanes"] == []
    assert lane["promoted_lanes_field_status"] == "deprecated_use_live_qualified_lanes_or_historical_legacy_promoted_lanes"
    assert "BTCUSDT|13m|long|ladder_close_50_618" in legacy
    assert "BTCUSDT|44m|long|ladder_close_50_618" in legacy
    assert "BTCUSDT|13m|long|ladder_close_50_618" not in lane["live_qualified_lanes"]


def test_readiness_not_ready_shown_when_no_fresh_eligible_candidate(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
    )
    assert payload["lane_intelligence_panel"]["readiness_status"] == "NOT_READY"
    assert payload["lane_intelligence_panel"]["fresh_eligible_count"] == 0
    assert "no fresh ELIGIBLE_TINY_LIVE BTCUSDT candidate" in payload["promotion_readiness_panel"]["readiness_blockers"]


def test_final_console_blocks_actual_submit(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
    )
    assert payload["final_console_go_no_go_packet"]["go_for_actual_submit_now"] is False
    assert payload["final_console_go_no_go_packet"]["operator_should_submit_now"] is False
    assert payload["target_scope"]["submit_allowed"] is False
    assert payload["final_console_matrix"]["submit_allowed"] is False


def test_exchange_minimum_below_44_blocks_final_command_without_modifying_config(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    _append_exchange_minimum_record(log_dir, mark_price=70000.0)
    before_risk = risk_path.read_text(encoding="utf-8")

    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
    )

    packet = payload["exchange_minimum_decision_packet"]
    assert packet["block_reason"] == "proper_tiny_live_below_exchange_minimum"
    assert packet["configured_proper_tiny_cap_usdt"] == 44.0
    assert packet["minimum_valid_quantity_after_rounding"] == 0.001
    assert packet["minimum_valid_notional_after_rounding"] == 70.0
    assert packet["wallet_supports_exchange_minimum_tiny"] is True
    assert packet["recommended_cap_usdt"] == 70.0
    assert packet["recommended_cap_applied"] is False
    assert payload["final_console_go_no_go_packet"]["go_for_actual_submit_now"] is False
    assert payload["final_console_go_no_go_packet"]["go_for_r264_actual_submit_checkpoint"] is False
    assert payload["final_console_go_no_go_packet"]["next_required_step"] == "WAIT_FOR_LIVE_QUALIFIED_FRESH_CANDIDATE"
    assert payload["recommended_next_operator_move"].startswith("WAIT_FOR_LIVE_QUALIFIED_FRESH_CANDIDATE")
    assert payload["final_command_available"] is False
    assert payload["order_placed"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["secrets_shown"] is False
    assert risk_path.read_text(encoding="utf-8") == before_risk


def test_operator_final_console_html_includes_exchange_minimum_reason() -> None:
    html = r263.render_tiny_live_final_console_html()
    assert "proper_tiny_live_below_exchange_minimum" in html
    assert "exchange minimum notional" in html
    assert "Copy exchange-minimum check" in html


def test_api_get_final_console_returns_json() -> None:
    from fastapi.testclient import TestClient

    from src.app.hammer_radar.operator.approval_api import app

    client = TestClient(app)
    response = client.get("/tiny-live/final-console")
    assert response.status_code == 200
    assert response.json()["target_scope"]["submit_allowed"] is False


def test_operator_final_console_route_is_read_only_html() -> None:
    from fastapi.testclient import TestClient

    from src.app.hammer_radar.operator.approval_api import app

    client = TestClient(app)
    response = client.get("/operator/tiny-live/final-console")
    assert response.status_code == 200
    assert "Read only" in response.text
    assert "no live submit button" in response.text
    assert "/fapi/v1/order" not in response.text


def test_margin_budget_10x_contract_displays_mismatch(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    risk = json.loads(risk_path.read_text(encoding="utf-8"))
    row = risk["risk_contracts"][0]
    row["tiny_live_contract_mode"] = "margin_budget_cap"
    row["max_notional_usdt"] = 440
    row["max_position_notional_usdt"] = 440
    row["leverage"] = 10
    risk_path.write_text(json.dumps(risk), encoding="utf-8")

    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
    )

    interpretation = payload["risk_contract_interpretation"]
    assert payload["contract_fit_panel"]["risk_contract_valid"] is False
    assert interpretation["valid"] is False
    assert interpretation["active_context"] == "no_current_proposed_ticket"
    assert "no_current_proposed_ticket" in interpretation["blocked_by"]
    assert "risk_contract_notional_cap_exceeds_44" in payload["contract_fit_panel"]["risk_contract_blockers"]
    assert payload["final_command_available"] is False
    assert payload["order_placed"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["secrets_shown"] is False


def test_api_post_arm_requires_exact_phrase() -> None:
    from fastapi.testclient import TestClient

    from src.app.hammer_radar.operator.approval_api import app

    client = TestClient(app)
    response = client.post(
        "/tiny-live/final-console/controls/arm",
        json={"confirm_final_console_controls_arming": "wrong", "operator_id": "test"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["confirmation_valid"] is False
    assert body["final_console_controls_armed"] is False


def test_ui_contains_no_actual_submit_button() -> None:
    from src.app.hammer_radar.operator.approval_api import _operator_ui_html

    html = _operator_ui_html()
    section = html.split('<section id="tinyLiveFinalConsole"', 1)[1].split("</section>", 1)[0]
    assert "NO SUBMIT FROM THIS SCREEN" in section
    assert "actual submit" not in section.lower()
    assert "button onclick=\"armTinyLiveFinalConsoleControls()\"" in section


def test_no_secrets_in_output(tmp_path: Path, monkeypatch) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    monkeypatch.setenv("BINANCE_API_KEY", SECRET_SENTINEL)
    monkeypatch.setenv("BINANCE_API_SECRET", SECRET_SENTINEL)
    payload = r263.build_tiny_live_final_console(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
    )
    raw = json.dumps(payload, sort_keys=True)
    assert SECRET_SENTINEL not in raw
    assert "BINANCE_API_KEY" not in raw
    assert "BINANCE_API_SECRET" not in raw
    assert all(value not in raw for value in os.environ.values() if value == SECRET_SENTINEL)


def _long_trade_ticket() -> dict:
    origin = {
        "signal_id": "fresh|r270|4m|long",
        "lane_key": "BTCUSDT|4m|long|ladder_close_50_618",
        "signal_origin_family": "standard",
        "betrayal_mode_involved": False,
        "betrayal_inverse_involved": False,
        "promotion_family": "standard",
        "promotion_status": "known_not_promotion_ready",
        "candidate_origin_classification": "standard checklist",
        "manual_unlock_allowed": True,
        "blocked_by": [],
        "source_record_found": True,
    }
    return {
        "ticket_status": "PROPOSED",
        "ticket_id": "tt_r270_4m_long",
        "signal_id": "fresh|r270|4m|long",
        "symbol": "BTCUSDT",
        "timeframe": "4m",
        "direction": "long",
        "entry_mode": "ladder_close_50_618",
        "lane_key": "BTCUSDT|4m|long|ladder_close_50_618",
        "readiness_status": "READY",
        "allowed_now": True,
        "max_position_usd": 80.0,
        "suggested_position_usd": 80.0,
        "suggested_leverage": 10.0,
        "active_contract_mode": "explicit_notional_cap_with_leverage",
        "active_contract_max_notional_usdt": 80.0,
        "active_contract_leverage": 10.0,
        "active_contract_margin_budget_usdt": 8.0,
        "machine_reason": "fixture",
        "blockers": [],
        "signal_origin": origin,
        "strategy_qualification": {
            "lane_key": "BTCUSDT|4m|long|ladder_close_50_618",
            "strategy_qualified": True,
            "qualification_status": "QUALIFIED",
            "win_rate_pct": 62.0,
            "sample_count": 40,
            "min_sample": 30,
            "min_win_rate_pct": 55.0,
            "blocked_by": [],
        },
        "strategy_qualified": True,
        "strategy_win_rate_pct": 62.0,
        "strategy_sample_count": 40,
        "strategy_min_sample": 30,
        "exact_risk_contract_status": {
            "lane_key": "BTCUSDT|4m|long|ladder_close_50_618",
            "exact_contract_found": True,
            "risk_contract_valid": True,
            "blocked_by": [],
        },
        "exact_risk_contract_found": True,
        "exact_risk_contract_valid": True,
        "order_placed": False,
        "real_order_placed": False,
        "submit_attempted": False,
        "binance_order_endpoint_called": False,
        "secrets_shown": False,
    }
