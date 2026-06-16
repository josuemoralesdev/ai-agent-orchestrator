from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import archive
from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.tiny_live_autonomous_armed_dry_run import (
    AUTO_DRY_RUN_BLOCKED,
    AUTO_DRY_RUN_READY,
    AUTO_DRY_RUN_WAIT,
    BLOCKED_BY_GLOBAL_ARMING,
    BLOCKED_BY_LANE_ARMING,
    BLOCKED_BY_BETRAYAL,
    BLOCKED_BY_NEAR_MISS,
    build_tiny_live_autonomous_armed_dry_run,
    default_autonomous_arming_state,
    load_autonomous_arming_state,
)
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import (
    build_explicit_lane_risk_contract,
)

LANE_44M_LONG = "BTCUSDT|44m|long|ladder_close_50_618"
LANE_44M_SHORT = "BTCUSDT|44m|short|ladder_close_50_618"
LANE_55M_LONG = "BTCUSDT|55m|long|ladder_close_50_618"
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"
LANE_13M_LONG = "BTCUSDT|13m|long|ladder_close_50_618"


def test_default_arming_state_is_off(tmp_path: Path) -> None:
    state = load_autonomous_arming_state(tmp_path / "missing.json")

    assert state["global_auto_live_enabled"] is False
    assert state["auto_execute_mode"] == "dry_run_only"
    assert state["armed_lane_key"] is None
    assert state["allowed_lane_keys"] == []
    assert state["any_lane_auto_armed"] is False


def test_no_current_candidate_waits(tmp_path: Path) -> None:
    _seed_strategy_status_lane(tmp_path, lane_key=LANE_44M_LONG, win_rate_pct=62.0, sample_count=40)

    payload = build_tiny_live_autonomous_armed_dry_run(
        log_dir=tmp_path,
        config_path=_arming_config(tmp_path, global_on=True, lane_key=LANE_44M_LONG),
        risk_contract_config_path=_risk_config(tmp_path, LANE_44M_LONG),
    )

    assert payload["status"] == AUTO_DRY_RUN_WAIT
    assert payload["real_order_placed"] is False
    assert payload["submit_attempted"] is False


def test_live_qualified_candidate_blocks_when_global_auto_off(tmp_path: Path) -> None:
    _seed_ready_candidate(tmp_path, LANE_44M_LONG)

    payload = build_tiny_live_autonomous_armed_dry_run(
        log_dir=tmp_path,
        config_path=_arming_config(tmp_path, global_on=False, lane_key=LANE_44M_LONG),
        risk_contract_config_path=_risk_config(tmp_path, LANE_44M_LONG),
    )

    assert payload["status"] == AUTO_DRY_RUN_BLOCKED
    assert BLOCKED_BY_GLOBAL_ARMING in payload["blockers"]
    assert payload["simulated_order_triplet"] is None


def test_global_on_but_exact_lane_off_blocks(tmp_path: Path) -> None:
    _seed_ready_candidate(tmp_path, LANE_44M_LONG)

    payload = build_tiny_live_autonomous_armed_dry_run(
        log_dir=tmp_path,
        config_path=_arming_config(tmp_path, global_on=True, lane_key=LANE_44M_LONG, lane_on=False),
        risk_contract_config_path=_risk_config(tmp_path, LANE_44M_LONG),
    )

    assert payload["status"] == AUTO_DRY_RUN_BLOCKED
    assert BLOCKED_BY_LANE_ARMING in payload["blockers"]


def test_near_miss_8m_short_cannot_auto_dry_run(tmp_path: Path) -> None:
    _seed_strategy_status_lane(tmp_path, lane_key=LANE_8M_SHORT, win_rate_pct=53.33, sample_count=30)
    archive.append_signal(_eligible_signal("fresh|8m|short", timeframe="8m", direction="short"), log_dir=tmp_path)

    payload = build_tiny_live_autonomous_armed_dry_run(
        log_dir=tmp_path,
        config_path=_arming_config(tmp_path, global_on=True, lane_key=LANE_8M_SHORT),
        risk_contract_config_path=_risk_config(tmp_path, LANE_8M_SHORT),
    )

    assert payload["status"] == AUTO_DRY_RUN_BLOCKED
    assert BLOCKED_BY_NEAR_MISS in payload["blockers"]
    assert payload["simulated_order_triplet"] is None


def test_below_55_13m_and_4m_cannot_auto_dry_run(tmp_path: Path) -> None:
    for timeframe, lane_key in (
        ("13m", LANE_13M_LONG),
        ("4m", "BTCUSDT|4m|long|ladder_close_50_618"),
    ):
        log_dir = tmp_path / timeframe
        log_dir.mkdir()
        _seed_strategy_status_lane(log_dir, lane_key=lane_key, win_rate_pct=47.27, sample_count=55)
        archive.append_signal(_eligible_signal(f"fresh|{timeframe}|long", timeframe=timeframe, direction="long"), log_dir=log_dir)

        payload = build_tiny_live_autonomous_armed_dry_run(
            log_dir=log_dir,
            config_path=_arming_config(log_dir, global_on=True, lane_key=lane_key),
            risk_contract_config_path=_risk_config(log_dir, lane_key),
        )

        assert payload["status"] == AUTO_DRY_RUN_BLOCKED
        assert "strategy_win_rate_below_55" in payload["blockers"]
        assert payload["simulated_order_triplet"] is None


def test_betrayal_inverse_cannot_auto_dry_run(tmp_path: Path) -> None:
    _seed_strategy_status_lane(tmp_path, lane_key=LANE_44M_LONG, win_rate_pct=62.0, sample_count=40)
    archive.append_signal(_eligible_signal("betrayal|inverse|fresh", timeframe="44m", direction="long"), log_dir=tmp_path)

    payload = build_tiny_live_autonomous_armed_dry_run(
        log_dir=tmp_path,
        config_path=_arming_config(tmp_path, global_on=True, lane_key=LANE_44M_LONG),
        risk_contract_config_path=_risk_config(tmp_path, LANE_44M_LONG),
    )

    assert payload["status"] == AUTO_DRY_RUN_BLOCKED
    assert BLOCKED_BY_BETRAYAL in payload["blockers"]
    assert payload["simulated_order_triplet"] is None


def test_exact_live_qualified_armed_lane_can_build_long_triplet(tmp_path: Path) -> None:
    _seed_ready_candidate(tmp_path, LANE_44M_LONG)

    payload = build_tiny_live_autonomous_armed_dry_run(
        log_dir=tmp_path,
        config_path=_arming_config(tmp_path, global_on=True, lane_key=LANE_44M_LONG),
        risk_contract_config_path=_risk_config(tmp_path, LANE_44M_LONG),
        record_autonomous_dry_run=True,
        operator_id="test_operator",
        reason="test ready dry run",
    )

    triplet = payload["simulated_order_triplet"]
    assert payload["status"] == AUTO_DRY_RUN_READY
    assert payload["autonomous_dry_run_recorded"] is True
    assert triplet["entry_order"]["side"] == "BUY"
    assert triplet["protective_stop_order"]["side"] == "SELL"
    assert triplet["take_profit_order"]["side"] == "SELL"
    assert payload["real_order_placed"] is False
    assert payload["submit_attempted"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["secrets_shown"] is False
    assert payload["dry_run_go_no_go"]["final_command_available"] is False
    assert payload["notification_payload"]["send_enabled"] is False
    assert payload["notification_payload"]["visibility_only"] is True


def test_exact_live_qualified_armed_lane_can_build_short_triplet(tmp_path: Path) -> None:
    _seed_ready_candidate(tmp_path, LANE_44M_SHORT)

    payload = build_tiny_live_autonomous_armed_dry_run(
        log_dir=tmp_path,
        config_path=_arming_config(tmp_path, global_on=True, lane_key=LANE_44M_SHORT),
        risk_contract_config_path=_risk_config(tmp_path, LANE_44M_SHORT),
    )

    triplet = payload["simulated_order_triplet"]
    assert payload["status"] == AUTO_DRY_RUN_READY
    assert triplet["entry_order"]["side"] == "SELL"
    assert triplet["protective_stop_order"]["side"] == "BUY"
    assert triplet["take_profit_order"]["side"] == "BUY"
    assert triplet["binance_order_endpoint_called"] is False
    assert triplet["binance_test_order_endpoint_called"] is False


def test_rehearsal_fixture_44m_long_can_auto_dry_run_ready_without_config_mutation(tmp_path: Path) -> None:
    payload = build_tiny_live_autonomous_armed_dry_run(
        log_dir=tmp_path,
        rehearsal_fixture_lane=LANE_44M_LONG,
        rehearsal_arm_fixture_lane=True,
        record_autonomous_dry_run=True,
        operator_id="test_operator",
        reason="R276 rehearsal only",
    )

    triplet = payload["simulated_order_triplet"]
    assert payload["status"] == AUTO_DRY_RUN_READY
    assert payload["rehearsal_mode"] is True
    assert payload["fixture_candidate"] is True
    assert payload["real_market_signal"] is False
    assert payload["selected_candidate"]["signal_id"].startswith("REHEARSAL_")
    assert payload["selected_candidate"]["freshness_status"] == "fresh"
    assert payload["selected_candidate"]["age_minutes"] <= 5
    assert triplet["entry_order"]["side"] == "BUY"
    assert triplet["entry_order"]["type"] == "MARKET"
    assert triplet["protective_stop_order"]["side"] == "SELL"
    assert triplet["protective_stop_order"]["type"] == "STOP_MARKET"
    assert triplet["protective_stop_order"]["reduceOnly"] is True
    assert triplet["take_profit_order"]["side"] == "SELL"
    assert triplet["take_profit_order"]["type"] == "TAKE_PROFIT_MARKET"
    assert triplet["take_profit_order"]["reduceOnly"] is True
    assert payload["dry_run_go_no_go"]["go"] is True
    assert payload["dry_run_go_no_go"]["final_command_available"] is False
    assert payload["real_order_forbidden"] is True
    assert payload["order_placed"] is False
    assert payload["submit_attempted"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["safety"]["submit_allowed"] is False
    assert payload["safety"]["secrets_shown"] is False


def test_rehearsal_fixture_44m_short_can_auto_dry_run_ready_with_short_sides(tmp_path: Path) -> None:
    payload = build_tiny_live_autonomous_armed_dry_run(
        log_dir=tmp_path,
        rehearsal_fixture_lane=LANE_44M_SHORT,
        rehearsal_arm_fixture_lane=True,
    )

    triplet = payload["simulated_order_triplet"]
    assert payload["status"] == AUTO_DRY_RUN_READY
    assert payload["selected_candidate"]["real_market_signal"] is False
    assert triplet["entry_order"]["side"] == "SELL"
    assert triplet["entry_order"]["type"] == "MARKET"
    assert triplet["protective_stop_order"]["side"] == "BUY"
    assert triplet["protective_stop_order"]["type"] == "STOP_MARKET"
    assert triplet["protective_stop_order"]["reduceOnly"] is True
    assert triplet["take_profit_order"]["side"] == "BUY"
    assert triplet["take_profit_order"]["type"] == "TAKE_PROFIT_MARKET"
    assert triplet["take_profit_order"]["reduceOnly"] is True
    assert triplet["submit_attempted"] is False
    assert triplet["binance_order_endpoint_called"] is False
    assert triplet["binance_test_order_endpoint_called"] is False


def test_rehearsal_fixture_55m_long_can_auto_dry_run_ready(tmp_path: Path) -> None:
    payload = build_tiny_live_autonomous_armed_dry_run(
        log_dir=tmp_path,
        rehearsal_fixture_lane=LANE_55M_LONG,
        rehearsal_arm_fixture_lane=True,
    )

    assert payload["status"] == AUTO_DRY_RUN_READY
    assert payload["selected_candidate"]["lane_key"] == LANE_55M_LONG
    assert payload["simulated_order_triplet"]["entry_order"]["side"] == "BUY"
    assert payload["final_command_available"] is False


def test_rehearsal_fixture_requires_explicit_arm_to_be_ready(tmp_path: Path) -> None:
    payload = build_tiny_live_autonomous_armed_dry_run(
        log_dir=tmp_path,
        rehearsal_fixture_lane=LANE_44M_LONG,
        rehearsal_arm_fixture_lane=False,
    )

    assert payload["status"] == AUTO_DRY_RUN_BLOCKED
    assert BLOCKED_BY_GLOBAL_ARMING in payload["blockers"]
    assert payload["simulated_order_triplet"] is None


def test_negative_rehearsal_fixtures_never_become_auto_dry_run_ready(tmp_path: Path) -> None:
    for lane_key in (
        LANE_8M_SHORT,
        LANE_13M_LONG,
        "BTCUSDT|4m|long|ladder_close_50_618",
        "BTCUSDT|4m|short|ladder_close_50_618",
        "BTCUSDT|44m|betrayal_inverse|ladder_close_50_618",
    ):
        payload = build_tiny_live_autonomous_armed_dry_run(
            log_dir=tmp_path / lane_key.replace("|", "_"),
            rehearsal_fixture_lane=lane_key,
            rehearsal_arm_fixture_lane=True,
            record_autonomous_dry_run=True,
        )

        assert payload["rehearsal_mode"] is True
        assert payload["autonomous_dry_run_recorded"] is True
        assert payload["fixture_candidate"] is True
        assert payload["real_market_signal"] is False
        assert payload["status"] == AUTO_DRY_RUN_BLOCKED
        assert payload["dry_run_go_no_go"]["go"] is False
        assert payload["simulated_order_triplet"] is None
        assert payload["order_placed"] is False
        assert payload["submit_attempted"] is False
        assert payload["binance_order_endpoint_called"] is False
        assert payload["binance_test_order_endpoint_called"] is False
        assert payload["final_command_available"] is False


def test_autonomous_dry_run_endpoint_is_safe(tmp_path: Path) -> None:
    with patch.dict("os.environ", {LOG_DIR_ENV_VAR: str(tmp_path)}):
        response = TestClient(app).get("/tiny-live/autonomous-armed-dry-run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["arming_state"]["global_auto_live_enabled"] is False
    assert payload["status"] == AUTO_DRY_RUN_WAIT
    assert payload["real_order_placed"] is False
    assert payload["binance_order_endpoint_called"] is False


def _seed_ready_candidate(log_dir: Path, lane_key: str) -> None:
    _seed_strategy_status_lane(log_dir, lane_key=lane_key, win_rate_pct=62.0, sample_count=40)
    _symbol, timeframe, direction, _entry_mode = lane_key.split("|")
    archive.append_signal(
        _eligible_signal(f"fresh|{timeframe}|{direction}", timeframe=timeframe, direction=direction),
        log_dir=log_dir,
    )


def _seed_strategy_status_lane(log_dir: Path, *, lane_key: str, win_rate_pct: float, sample_count: int) -> None:
    _symbol, timeframe, direction, entry_mode = lane_key.split("|")
    row = {
        "strategy_key": lane_key,
        "sample_count": sample_count,
        "required_sample_count": 30,
        "win_rate_pct": win_rate_pct,
        "avg_pnl_pct": 0.1,
        "total_pnl_pct": round(0.1 * sample_count, 4),
        "entry_mode": entry_mode,
        "timeframe": timeframe,
        "direction": direction,
    }
    record = {
        "qualified_candidate_watch": {
            "live_qualified_lanes": [],
            "near_miss_incubator_lanes": [],
            "paper_only_lanes": [],
        }
    }
    if sample_count >= 30 and win_rate_pct >= 55.0:
        record["qualified_candidate_watch"]["live_qualified_lanes"].append(row)
    elif sample_count >= 30 and win_rate_pct >= 53.0:
        record["qualified_candidate_watch"]["near_miss_incubator_lanes"].append(row)
    else:
        record["qualified_candidate_watch"]["paper_only_lanes"].append(row)
    with (log_dir / "strategy_promotion_status.ndjson").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _eligible_signal(signal_id: str, *, timeframe: str, direction: str) -> SignalRecord:
    bearish = direction == "short"
    return SignalRecord(
        signal_id=signal_id,
        symbol="BTCUSDT",
        timeframe=timeframe,
        direction=direction,
        timestamp=(datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        hammer_strength=100.0,
        hammer_high=101.0,
        hammer_low=94.0,
        fib_50=100.5,
        fib_618=100.0,
        fib_650=99.5,
        fib_786=98.5,
        invalidation=105.0 if bearish else 95.0,
        bias_timeframe="4H",
        bias_direction="bearish" if bearish else "bullish",
        bias_aligned=True,
        same_direction_streak=0,
        opposite_direction_streak=0,
        tradable=True,
        trend_direction="bearish" if bearish else "bullish",
        trend_strength_score=0.6,
        rsi_state="overbought" if bearish else "neutral",
        rsi_value=70.0 if bearish else 50.0,
        divergence_type="bearish" if bearish else "bullish",
        divergence_confirmed=True,
    )


def _arming_config(log_dir: Path, *, global_on: bool, lane_key: str, lane_on: bool = True) -> Path:
    state = {
        **default_autonomous_arming_state(),
        "global_auto_live_enabled": global_on,
        "armed_lane_key": lane_key,
        "allowed_lane_keys": [lane_key],
        "lanes": [{"lane_key": lane_key, "lane_auto_live_enabled": lane_on}],
    }
    path = log_dir / "autonomous_arming_state.json"
    path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    return path


def _risk_config(log_dir: Path, lane_key: str) -> Path:
    contract = build_explicit_lane_risk_contract(
        lane_key=lane_key,
        strategy_qualification={
            "lane_key": lane_key,
            "win_rate_pct": 62.0,
            "sample_count": 40,
            "avg_pnl_pct": 0.1,
            "min_sample": 30,
            "min_win_rate_pct": 55.0,
            "qualification_status": "QUALIFIED",
        },
        now=datetime(2026, 6, 15, 12, 0, tzinfo=UTC),
    )
    path = log_dir / "tiny_live_risk_contracts.json"
    path.write_text(json.dumps({"risk_contracts": [contract]}, sort_keys=True), encoding="utf-8")
    return path
