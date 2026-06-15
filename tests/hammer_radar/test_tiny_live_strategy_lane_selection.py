from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator import tiny_live_strategy_lane_selection as r270b

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
LANE_4M_LONG = "BTCUSDT|4m|long|ladder_close_50_618"
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"


def test_lane_with_win_rate_and_sample_minimum_qualifies(tmp_path: Path) -> None:
    payload = r270b.build_strategy_lane_qualification(
        symbol="BTCUSDT",
        timeframe="4m",
        direction="long",
        entry_mode="ladder_close_50_618",
        log_dir=tmp_path / "logs",
        evidence=_evidence(win_rate_pct=55.0, sample_count=30),
    )
    assert payload["strategy_qualified"] is True
    assert payload["win_rate_pct"] == 55.0
    assert payload["sample_count"] == 30
    assert payload["min_sample"] == 30
    assert payload["order_placed"] is False


def test_lane_below_55_blocks(tmp_path: Path) -> None:
    payload = r270b.build_strategy_lane_qualification(
        symbol="BTCUSDT",
        timeframe="4m",
        direction="long",
        entry_mode="ladder_close_50_618",
        log_dir=tmp_path / "logs",
        evidence=_evidence(win_rate_pct=54.99, sample_count=80),
    )
    assert payload["strategy_qualified"] is False
    assert payload["live_qualification_class"] == r270b.NEAR_MISS_INCUBATOR
    assert payload["near_miss_incubator"] is True
    assert payload["manual_live_unlock_allowed"] is False
    assert "strategy_near_miss_not_live_eligible" in payload["blocked_by"]
    assert "win_rate_below_operator_55_policy" in payload["blocked_by"]
    assert "strategy_lane_win_rate_below_55" in payload["blocked_by"]
    assert "strategy_win_rate_below_55" in payload["blocked_by"]


def test_13m_47_27_does_not_qualify(tmp_path: Path) -> None:
    payload = r270b.build_strategy_lane_qualification(
        symbol="BTCUSDT",
        timeframe="13m",
        direction="long",
        entry_mode="ladder_close_50_618",
        log_dir=tmp_path / "logs",
        evidence=_evidence(win_rate_pct=47.27, sample_count=55),
    )
    assert payload["strategy_qualified"] is False
    assert payload["live_qualification_class"] == r270b.PAPER_ONLY
    assert payload["paper_only"] is True
    assert payload["min_win_rate_pct"] == 55.0
    assert "win_rate_below_operator_55_policy" in payload["blocked_by"]
    assert "strategy_win_rate_below_55" in payload["blocked_by"]


def test_44m_58_57_qualifies_with_sample_minimum(tmp_path: Path) -> None:
    payload = r270b.build_strategy_lane_qualification(
        symbol="BTCUSDT",
        timeframe="44m",
        direction="long",
        entry_mode="ladder_close_50_618",
        log_dir=tmp_path / "logs",
        evidence=_evidence(win_rate_pct=58.57, sample_count=70),
    )
    assert payload["strategy_qualified"] is True
    assert payload["live_qualification_class"] == r270b.LIVE_QUALIFIED
    assert payload["manual_live_unlock_allowed"] is True
    assert payload["evidence_policy_all_timeframes_enabled"] is True


def test_53_to_54_99_enters_incubator_not_live(tmp_path: Path) -> None:
    payload = r270b.build_strategy_lane_qualification(
        symbol="BTCUSDT",
        timeframe="8m",
        direction="short",
        entry_mode="ladder_close_50_618",
        log_dir=tmp_path / "logs",
        evidence={
            **_evidence(win_rate_pct=53.0, sample_count=30),
            "strategy_key": LANE_8M_SHORT,
            "timeframe": "8m",
            "direction": "short",
        },
    )
    assert payload["strategy_qualified"] is False
    assert payload["live_qualification_class"] == r270b.NEAR_MISS_INCUBATOR
    assert payload["near_miss_incubator"] is True
    assert payload["manual_live_unlock_allowed"] is False
    assert "strategy_near_miss_not_live_eligible" in payload["blocked_by"]


def test_lane_below_sample_minimum_blocks(tmp_path: Path) -> None:
    payload = r270b.build_strategy_lane_qualification(
        symbol="BTCUSDT",
        timeframe="4m",
        direction="long",
        entry_mode="ladder_close_50_618",
        log_dir=tmp_path / "logs",
        evidence=_evidence(win_rate_pct=80.0, sample_count=29),
    )
    assert payload["strategy_qualified"] is False
    assert "strategy_lane_sample_count_below_minimum" in payload["blocked_by"]
    assert "strategy_sample_count_below_minimum" in payload["blocked_by"]


def test_lane_with_non_positive_avg_pnl_blocks(tmp_path: Path) -> None:
    payload = r270b.build_strategy_lane_qualification(
        symbol="BTCUSDT",
        timeframe="4m",
        direction="long",
        entry_mode="ladder_close_50_618",
        log_dir=tmp_path / "logs",
        evidence=_evidence(win_rate_pct=80.0, sample_count=40, avg_pnl_pct=0.0),
    )
    assert payload["strategy_qualified"] is False
    assert payload["avg_pnl_pct"] == 0.0
    assert "strategy_lane_avg_pnl_pct_not_positive" in payload["blocked_by"]
    assert "strategy_avg_pnl_pct_not_positive" in payload["blocked_by"]


def test_historical_paper_only_timeframe_can_qualify_by_evidence(tmp_path: Path) -> None:
    payload = r270b.build_strategy_lane_qualification(
        symbol="BTCUSDT",
        timeframe="8m",
        direction="long",
        entry_mode="ladder_close_50_618",
        log_dir=tmp_path / "logs",
        evidence=_evidence(win_rate_pct=60.0, sample_count=31),
    )
    assert payload["strategy_qualified"] is True
    assert payload["timeframe"] == "8m"


def test_exact_risk_contract_required_and_no_cross_lane_borrowing(tmp_path: Path) -> None:
    risk_path = _write_risk_config(tmp_path / "risk.json", contracts=[_contract(LANE_8M_SHORT)])
    qualification = _qualification(LANE_4M_LONG)
    payload = r270b.build_exact_lane_risk_contract_status(
        lane_key=LANE_4M_LONG,
        risk_contract_config_path=risk_path,
        strategy_qualification=qualification,
    )
    assert payload["exact_contract_found"] is False
    assert payload["risk_contract_valid"] is False
    assert payload["no_cross_lane_borrowing"] is True
    assert "exact_lane_risk_contract_missing" in payload["blocked_by"]


def test_missing_exact_contract_can_be_created_only_by_guarded_qualified_policy(tmp_path: Path) -> None:
    risk_path = _write_risk_config(tmp_path / "risk.json", contracts=[_contract(LANE_8M_SHORT)])
    bad = r270b.guarded_apply_exact_lane_risk_contract(
        lane_key=LANE_4M_LONG,
        strategy_qualification=_qualification(LANE_4M_LONG),
        risk_contract_config_path=risk_path,
        apply_contract=True,
        confirm_apply="wrong",
        now=NOW,
    )
    assert bad["succeeded"] is False
    assert bad["risk_contract_config_written"] is False
    assert "bad_confirmation" in bad["blocked_by"]

    good = r270b.guarded_apply_exact_lane_risk_contract(
        lane_key=LANE_4M_LONG,
        strategy_qualification=_qualification(LANE_4M_LONG),
        risk_contract_config_path=risk_path,
        apply_contract=True,
        confirm_apply=r270b.R270B_RISK_CONTRACT_APPLY_CONFIRMATION_PHRASE,
        now=NOW,
    )
    assert good["succeeded"] is True
    assert good["risk_contract_config_written"] is True
    written = json.loads(risk_path.read_text(encoding="utf-8"))
    contract = next(row for row in written["risk_contracts"] if row["official_lane_key"] == LANE_4M_LONG)
    assert contract["max_position_notional_usdt"] == 80.0
    assert contract["max_notional_usdt"] == 80.0
    assert contract["leverage"] == 10.0
    assert contract["margin_budget_usdt"] == 8.0
    assert contract["live_execution_enabled"] is False
    assert contract["live_authorized"] is False


def test_unqualified_lane_cannot_create_contract(tmp_path: Path) -> None:
    risk_path = _write_risk_config(tmp_path / "risk.json", contracts=[])
    payload = r270b.guarded_apply_exact_lane_risk_contract(
        lane_key=LANE_4M_LONG,
        strategy_qualification={**_qualification(LANE_4M_LONG), "strategy_qualified": False, "blocked_by": ["sample"]},
        risk_contract_config_path=risk_path,
        apply_contract=True,
        confirm_apply=r270b.R270B_RISK_CONTRACT_APPLY_CONFIRMATION_PHRASE,
        now=NOW,
    )
    assert payload["succeeded"] is False
    assert payload["risk_contract_config_written"] is False
    assert "strategy_lane_not_qualified" in payload["blocked_by"]


def test_4m_long_contract_validates_when_evidence_qualifies(tmp_path: Path) -> None:
    risk_path = _write_risk_config(tmp_path / "risk.json", contracts=[_contract(LANE_4M_LONG)])
    qualification = _qualification(LANE_4M_LONG)
    payload = r270b.build_exact_lane_risk_contract_status(
        lane_key=LANE_4M_LONG,
        risk_contract_config_path=risk_path,
        strategy_qualification=qualification,
    )
    assert payload["exact_contract_found"] is True
    assert payload["risk_contract_valid"] is True
    assert payload["order_placed"] is False
    assert payload["submit_attempted"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["secrets_shown"] is False


def _evidence(*, win_rate_pct: float, sample_count: int, avg_pnl_pct: float = 0.1) -> dict:
    return {
        "strategy_key": LANE_4M_LONG,
        "symbol": "BTCUSDT",
        "timeframe": "4m",
        "direction": "long",
        "entry_mode": "ladder_close_50_618",
        "win_rate_pct": win_rate_pct,
        "sample_count": sample_count,
        "avg_pnl_pct": avg_pnl_pct,
    }


def _qualification(lane_key: str) -> dict:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    return {
        "lane_key": lane_key,
        "strategy_qualified": True,
        "qualification_status": "QUALIFIED",
        "win_rate_pct": 62.0,
        "sample_count": 40,
        "avg_pnl_pct": 0.1,
        "min_sample": 30,
        "min_win_rate_pct": 55.0,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "blocked_by": [],
    }


def _contract(lane_key: str) -> dict:
    symbol, timeframe, direction, entry_mode = lane_key.split("|")
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "tiny_live_contract_mode": "explicit_notional_cap_with_leverage",
        "max_position_notional_usdt": 80.0,
        "max_notional_usdt": 80.0,
        "leverage": 10.0,
        "margin_budget_usdt": 8.0,
        "max_loss_usdt": 4.44,
        "live_execution_enabled": False,
        "live_authorized": False,
    }


def _write_risk_config(path: Path, *, contracts: list[dict]) -> Path:
    path.write_text(json.dumps({"funding_config": {}, "risk_contracts": contracts}), encoding="utf-8")
    return path
