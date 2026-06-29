from __future__ import annotations

import json
import os
import subprocess
from importlib import import_module
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion import BASELINE_LANE
from src.app.hammer_radar.operator.ultra_short_leverage_burst_lab_design import (
    EVENT_TYPE,
    LEDGER_FILENAME,
    READY,
    SAFETY,
    STRATEGY_FAMILY,
    build_ultra_short_leverage_burst_lab_design,
    load_ultra_short_leverage_burst_lab_design_records,
)

NOW = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)


def test_builds_burst_lab_design_packet(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    payload = _build(log_dir)
    records = load_ultra_short_leverage_burst_lab_design_records(log_dir=log_dir)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["burst_lab_design_status"] == READY
    assert (log_dir / LEDGER_FILENAME).exists()
    assert len(records) == 1


def test_strategy_family_is_ultra_short_leverage_burst_and_isolated(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["strategy_family"] == STRATEGY_FAMILY
    assert payload["strategy_family_isolated"] is True
    assert payload["paper_only"] is True
    assert payload["burst_live_permission"] is False


def test_candidate_timeframes_include_4m_and_8m(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert {row["timeframe"] for row in payload["candidate_timeframes"]} == {"4m", "8m"}
    assert all(row["candidate_mode"] == "paper_only" for row in payload["candidate_timeframes"])
    assert all(row["burst_lab_only"] is True for row in payload["candidate_timeframes"])
    assert all(row["standard_promotion_allowed"] is False for row in payload["candidate_timeframes"])
    assert all(row["tiny_live_permission"] is False for row in payload["candidate_timeframes"])
    assert all(row["observed_expansion_write"] is False for row in payload["candidate_timeframes"])


def test_leverage_grid_includes_required_values_and_150x_math(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)
    rows = {row["leverage"]: row for row in payload["leverage_grid"]}

    assert set(rows) == {22, 44, 88, 150}
    assert rows[150]["price_move_pct_for_15pct_gross_roe"] == 0.1
    assert rows[150]["price_move_pct_for_gross_roe_formula"] == "gross_roe_pct / leverage"
    assert "150x" in rows[150]["liquidation_proximity_warning"]
    assert all(row["live_permission"] is False for row in rows.values())


def test_checkpoint_grid_includes_required_seconds(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["checkpoint_grid_seconds"] == [22, 44, 66, 88, 132, 176]
    assert payload["checkpoint_policy_design"]["primary_operator_concept"] == "first_44s_checkpoint"
    assert payload["checkpoint_policy_design"]["second_wave_checks_seconds"] == [66, 88]
    assert payload["checkpoint_policy_design"]["hard_timeout_exit_design"] is True


def test_fee_drag_and_net_roe_formulas_present(tmp_path: Path) -> None:
    model = _build(tmp_path / "logs", write=False)["fee_slippage_model_design"]

    assert model["gross_roe_is_sufficient"] is False
    assert model["fee_drag_roe_formula"] == "notional_fee_pct_round_trip * leverage"
    assert model["estimated_slippage_roe_formula"] == "estimated_slippage_pct_round_trip * leverage"
    assert model["net_roe_formula"] == "gross_roe - fee_drag_roe - estimated_slippage_roe"
    assert model["ready_using_gross_roe_only_allowed"] is False


def test_exit_policy_forbids_gross_only_success(tmp_path: Path) -> None:
    policy = _build(tmp_path / "logs", write=False)["exit_policy_design"]

    assert policy["gross_roe_target_grid"] == [5, 10, 15, 22]
    assert policy["minimum_net_roe_target_grid"] == [2, 3, 5, 8]
    assert policy["hard_loss_roe_grid"] == [-5, -8, -10, -12]
    assert policy["timeout_seconds_grid"] == [44, 66, 88, 132, 176]
    assert policy["gross_only_success_classification_allowed"] is False
    assert policy["averaging_down_allowed"] is False


def test_candle_only_ohlc_sequence_risk_and_no_live_promotion(tmp_path: Path) -> None:
    data = _build(tmp_path / "logs", write=False)["required_market_data_design"]

    assert data["poor"] == "candle_only_ohlc"
    assert "cannot_prove" in data["candle_only_ohlc_sequence_risk"]
    assert data["candle_only_sequence_flag"] == "sequence_unknown"
    assert data["sequence_unknown_can_promote_to_live"] is False


def test_evidence_contract_thresholds_and_separation(tmp_path: Path) -> None:
    contract = _build(tmp_path / "logs", write=False)["evidence_contract"]

    assert contract["minimum_sample_count_per_profile"] >= 100
    assert contract["preferred_sample_count_per_profile"] >= 300
    assert contract["minimum_net_win_rate_after_fees_slippage_pct"] >= 60
    assert contract["minimum_profit_factor"] > 1.3
    assert contract["profit_factor_operator"] == ">"
    assert contract["gross_only_roe_readiness_allowed"] is False
    assert contract["candle_only_fantasy_fills_allowed"] is False
    assert contract["standard_55_policy_applies"] is False
    assert contract["tiny_live_inheritance"] is False


def test_visual_terminal_and_future_paths_present(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["visual_terminal_design_spec"]["surface"] == "terminal_panel_not_website"
    assert "leverage_ladder" in payload["visual_terminal_design_spec"]["required_blocks"]
    assert "Live Permission: FALSE" in payload["visual_terminal_design_spec"]["preview_lines"]
    assert payload["recommended_r333b_path"]["phase"] == "R333B Ultra-Short Burst Backtest Adapter"
    assert payload["recommended_r333c_path"]["phase"] == "R333C Ultra-Short Burst Visual Terminal Panel"
    assert payload["recommended_r333d_path"]["phase"] == "R333D Human-Reviewed Burst Risk Contract Preview"


def test_first_tiny_live_lane_preserved(tmp_path: Path) -> None:
    payload = _build(tmp_path / "logs", write=False)

    assert payload["first_tiny_live_lane"] == BASELINE_LANE
    assert payload["first_live_lane_change_allowed"] is False
    assert "does not inherit Tiny Live permissions" in " ".join(payload["recommended_tiny_live_path"])


def test_required_safety_flags_are_false_or_safe(tmp_path: Path) -> None:
    env_before = dict(os.environ)
    payload = _build(tmp_path / "logs", write=False)

    assert dict(os.environ) == env_before
    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected
    assert payload["live_permission_count"] == 0
    assert payload["promotion_event_written"] is False
    assert payload["risk_contract_config_mutated"] is False
    assert payload["observed_expansion_written"] is False
    assert payload["scheduler_started"] is False
    assert payload["synthetic_performance_created"] is False
    assert payload["config_written"] is False
    assert payload["env_mutated"] is False
    assert payload["env_written"] is False
    assert payload["autonomous_arming_state_changed"] is False
    assert payload["systemd_unit_mutated"] is False
    assert payload["order_placed"] is False
    assert payload["real_order_placed"] is False
    assert payload["execution_attempted"] is False
    assert payload["submit_allowed"] is False
    assert payload["final_command_available"] is False
    assert payload["binance_order_endpoint_called"] is False
    assert payload["binance_test_order_endpoint_called"] is False
    assert payload["telegram_send_called"] is False
    assert payload["telegram_message_sent"] is False
    assert payload["real_telegram_send_called"] is False
    assert payload["real_telegram_message_sent"] is False


def test_inspect_route_works(tmp_path: Path) -> None:
    result = _run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "ultra-short-leverage-burst-lab-design",
            "--no-write",
        ]
    )
    payload = json.loads(result.stdout)

    assert payload["event_type"] == EVENT_TYPE
    assert payload["strategy_family"] == STRATEGY_FAMILY
    assert payload["burst_lab_design_status"] == READY


def test_operator_script_exists_and_prints_required_sections(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/hammer_print_r333a_ultra_short_leverage_burst_lab_design.sh"
    result = subprocess.run(
        ["bash", str(script)],
        cwd=root,
        env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(tmp_path / "logs")},
        text=True,
        capture_output=True,
        check=True,
    )

    assert script.exists()
    for section in (
        "R333A ULTRA SHORT LEVERAGE BURST LAB DESIGN PACKET",
        "STRATEGY FAMILY",
        "family_isolated",
        "paper_only",
        "FIRST TINY LIVE LANE",
        "CANDIDATE TIMEFRAMES",
        "LEVERAGE GRID",
        "CHECKPOINT GRID",
        "EVIDENCE CONTRACT SUMMARY",
        "FEE / SLIPPAGE / LIQUIDATION WARNINGS",
        "VISUAL TERMINAL DESIGN PREVIEW",
        "RECOMMENDED FUTURE PHASES",
        "SAFETY FLAGS",
    ):
        assert section in result.stdout


def test_r332_r331_r329_r314_surfaces_remain_importable() -> None:
    modules = (
        "src.app.hammer_radar.operator.strategy_lab_captured_source_data_merge",
        "src.app.hammer_radar.operator.strategy_lab_source_data_capture_adapter",
        "src.app.hammer_radar.operator.strategy_lab_adapter_output_batch_execution_packet",
        "src.app.hammer_radar.operator.strategy_lab_evidence_adapter_pack",
        "src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion",
        "src.app.hammer_radar.operator.multi_lane_observation_health_panel",
    )

    for module_name in modules:
        assert import_module(module_name)


def _build(log_dir: Path, *, write: bool = True) -> dict[str, object]:
    return build_ultra_short_leverage_burst_lab_design(log_dir=log_dir, write=write, now=NOW)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        command,
        cwd=root,
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
