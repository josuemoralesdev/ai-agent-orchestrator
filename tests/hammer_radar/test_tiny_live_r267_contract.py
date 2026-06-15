from __future__ import annotations

from src.app.hammer_radar.operator.tiny_live_binance_readonly_precision_mark_price_gate import (
    build_exchange_minimum_tiny_live_decision_packet,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract_validation import (
    build_tiny_live_risk_contract_validation_summary,
)


def _r267_contract(**overrides: object) -> dict:
    contract = {
        "official_lane_key": "BTCUSDT|8m|short|ladder_close_50_618",
        "symbol": "BTCUSDT",
        "timeframe": "8m",
        "direction": "short",
        "entry_mode": "ladder_close_50_618",
        "tiny_live_contract_mode": "explicit_notional_cap_with_leverage",
        "max_position_notional_usdt": 80.0,
        "max_notional_usdt": 80.0,
        "leverage": 10.0,
        "margin_budget_usdt": 8.0,
        "tiny_live_margin_usdt": 8.0,
        "max_loss_usdt": 4.44,
        "live_execution_enabled": False,
    }
    contract.update(overrides)
    return {"contract": contract}


def test_r267_10x_80_notional_contract_is_valid_and_derives_margin() -> None:
    summary = build_tiny_live_risk_contract_validation_summary(
        risk_contract=_r267_contract(),
        candidate_notional_usdt=80.0,
        candidate_estimated_loss_usdt=4.44,
        min_notional=67.0,
    )

    assert summary["valid"] is True
    assert summary["tiny_live_contract_mode"] == "explicit_notional_cap_with_leverage"
    assert summary["max_position_notional_usdt"] == 80.0
    assert summary["leverage"] == 10.0
    assert summary["derived_margin_budget_usdt"] == 8.0
    assert summary["clears_exchange_minimum"] is True
    assert summary["blocked_by"] == []


def test_r267_10x_does_not_permit_800_notional() -> None:
    summary = build_tiny_live_risk_contract_validation_summary(
        risk_contract=_r267_contract(),
        candidate_notional_usdt=800.0,
    )

    assert summary["valid"] is False
    assert "candidate_notional_exceeds_position_notional_cap" in summary["blocked_by"]


def test_r267_rejects_configured_notional_above_80() -> None:
    summary = build_tiny_live_risk_contract_validation_summary(
        risk_contract=_r267_contract(max_position_notional_usdt=800.0, max_notional_usdt=800.0),
    )

    assert summary["valid"] is False
    assert "risk_contract_notional_cap_exceeds_80" in summary["blocked_by"]
    assert summary["higher_notional_interpretation_rejected"] is True


def test_r267_80_clears_exchange_minimum_when_minimum_below_80() -> None:
    packet = build_exchange_minimum_tiny_live_decision_packet(
        configured_cap_usdt=80,
        precision_snapshot={
            "found": True,
            "symbol": "BTCUSDT",
            "min_qty": 0.001,
            "step_size": 0.001,
            "min_notional": 5.0,
        },
        mark_price_snapshot={"found": True, "symbol": "BTCUSDT", "mark_price": 67000.0},
    )

    assert packet["configured_cap_possible"] is True
    assert packet["configured_cap_clears_exchange_minimum"] is True
    assert packet["minimum_valid_notional_after_rounding"] == 67.0
    assert packet["final_command_available"] is False
    assert packet["order_placed"] is False
    assert packet["binance_order_endpoint_called"] is False


def test_r267_below_exchange_minimum_remains_blocked_if_minimum_above_80() -> None:
    summary = build_tiny_live_risk_contract_validation_summary(
        risk_contract=_r267_contract(),
        candidate_notional_usdt=80.0,
        min_notional=81.0,
    )

    assert summary["valid"] is False
    assert summary["clears_exchange_minimum"] is False
    assert "proper_tiny_live_below_exchange_minimum" in summary["blocked_by"]
