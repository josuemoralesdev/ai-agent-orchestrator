from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

from src.app.hammer_radar.operator.archive import append_signal
from src.app.hammer_radar.operator.models import SignalRecord
from src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion import BASELINE_LANE
from src.app.hammer_radar.operator.ultra_short_burst_backtest_adapter import (
    CHECKPOINT_GRID_SECONDS,
    EVENT_TYPE as BACKTEST_EVENT,
    LEVERAGE_GRID,
    MODEL_PREVIEW_NOT_TRADE_RESULT,
    SAFETY,
    SEQUENCE_UNKNOWN,
    SOURCE_SUMMARY_ONLY,
    STRATEGY_FAMILY,
    build_ultra_short_burst_backtest_adapter,
)
from src.app.hammer_radar.operator.ultra_short_burst_lab_implementation_pack import (
    EVENT_TYPE as PACK_EVENT,
    READY as PACK_READY,
    build_ultra_short_burst_lab_implementation_pack,
)
from src.app.hammer_radar.operator.ultra_short_burst_risk_contract_preview import (
    EVENT_TYPE as RISK_EVENT,
    READY as RISK_READY,
    build_ultra_short_burst_risk_contract_preview,
)
from src.app.hammer_radar.operator.ultra_short_burst_visual_terminal_panel import (
    EVENT_TYPE as VISUAL_EVENT,
    READY as VISUAL_READY,
    build_ultra_short_burst_visual_terminal_panel,
)

NOW = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)


def test_builds_r333b_backtest_adapter_packet(tmp_path: Path) -> None:
    log_dir = _seed_signals(tmp_path)
    payload = build_ultra_short_burst_backtest_adapter(log_dir=log_dir, write=True, now=NOW)

    assert payload["event_type"] == BACKTEST_EVENT
    assert payload["strategy_family"] == STRATEGY_FAMILY
    assert payload["strategy_family_isolated"] is True
    assert payload["paper_only"] is True
    assert payload["burst_live_permission"] is False
    assert set(payload["candidate_timeframes"]) == {"4m", "8m"}
    assert set(payload["candidate_leverage_grid"]) == {22, 44, 88, 150}
    assert payload["checkpoint_grid_seconds"] == [22, 44, 66, 88, 132, 176]
    assert (log_dir / "ultra_short_burst_backtest_adapter.ndjson").exists()


def test_backtest_rows_include_schema_and_sequence_unknown_policy(tmp_path: Path) -> None:
    payload = build_ultra_short_burst_backtest_adapter(log_dir=_seed_signals(tmp_path), write=False, now=NOW)
    rows = payload["burst_backtest_rows"]
    assert rows
    required = {
        "burst_row_id",
        "strategy_family",
        "timeframe",
        "side",
        "lane_key",
        "source_signal_id",
        "source_signal_status",
        "detection_timestamp_status",
        "entry_model",
        "entry_timestamp_status",
        "leverage",
        "checkpoint_seconds",
        "fee_pct_round_trip",
        "slippage_pct_round_trip",
        "fee_drag_roe",
        "estimated_slippage_roe",
        "gross_roe_target_pct",
        "price_move_pct_for_gross_roe",
        "net_roe_formula",
        "sequence_known",
        "sequence_status",
        "result_status",
        "evidence_quality",
        "liquidation_proximity_warning",
        "live_permission",
        "burst_live_permission",
        "tiny_live_eligible_now",
        "standard_55_policy_applies",
        "tiny_live_inheritance",
        "promotion_event_written",
        "risk_contract_write_required",
        "risk_contract_written",
        "observed_expansion_written",
        "scheduler_required",
        "synthetic_performance_created",
        "blockers",
    }
    assert required <= set(rows[0])
    assert any(row["timeframe"] == "4m" for row in rows)
    assert any(row["timeframe"] == "8m" for row in rows)
    assert all(row["sequence_known"] is False for row in rows)
    assert all(row["sequence_status"] == SEQUENCE_UNKNOWN for row in rows)
    assert all(row["live_permission"] is False for row in rows)
    assert all(row["burst_live_permission"] is False for row in rows)
    assert all(row["result_status"] in {SOURCE_SUMMARY_ONLY, MODEL_PREVIEW_NOT_TRADE_RESULT} for row in rows)
    assert all(row["fee_drag_roe"] == row["fee_pct_round_trip"] * row["leverage"] for row in rows)
    assert all(row["estimated_slippage_roe"] == row["slippage_pct_round_trip"] * row["leverage"] for row in rows)
    assert all(row["net_roe_formula"] is None for row in rows if row["gross_roe_target_pct"] is None)
    assert any("150x" in row["liquidation_proximity_warning"] for row in rows if row["leverage"] == 150)


def test_builds_r333c_visual_terminal_panel(tmp_path: Path) -> None:
    backtest = build_ultra_short_burst_backtest_adapter(log_dir=_seed_signals(tmp_path), write=False, now=NOW)
    payload = build_ultra_short_burst_visual_terminal_panel(
        log_dir=tmp_path / "logs",
        write=False,
        now=NOW,
        backtest_adapter_packet=backtest,
    )
    text = "\n".join(payload["panel_lines"])

    assert payload["event_type"] == VISUAL_EVENT
    assert payload["visual_panel_status"] == VISUAL_READY
    assert payload["terminal_only"] is True
    assert payload["hosted_ui"] is False
    assert payload["live_permission"] is False
    assert "PAPER ONLY / LIVE PERMISSION FALSE" in text
    assert "Leverage ladder: 22x / 44x / 88x / 150x" in text
    assert "Checkpoint timeline: 22s | 44s | 66s | 88s | 132s | 176s" in text
    assert "Fee drag warning" in text
    assert "Liquidation proximity warning" in text
    assert "Sequence warning" in text


def test_builds_r333d_risk_contract_preview(tmp_path: Path) -> None:
    payload = build_ultra_short_burst_risk_contract_preview(
        log_dir=tmp_path / "logs",
        write=False,
        now=NOW,
        include_150x=True,
    )

    assert payload["event_type"] == RISK_EVENT
    assert payload["risk_contract_preview_status"] == RISK_READY
    assert payload["preview_only"] is True
    assert payload["risk_contract_written"] is False
    assert payload["config_written"] is False
    assert payload["cross_margin_allowed"] is False
    assert payload["isolated_margin_only"] is True
    assert payload["evidence_contract_required"] is True
    assert payload["anti_fantasy_fill_gate_required"] is True
    assert set(payload["leverage_grid"]) == {22, 44, 88, 150}
    assert "150x EXTREME DANGER" in " ".join(payload["danger_warnings"])


def test_builds_combined_r333bcd_implementation_pack_and_safety(tmp_path: Path) -> None:
    env_before = dict(os.environ)
    payload = build_ultra_short_burst_lab_implementation_pack(log_dir=_seed_signals(tmp_path), write=True, now=NOW)
    readiness = payload["evidence_readiness_summary"]

    assert dict(os.environ) == env_before
    assert payload["event_type"] == PACK_EVENT
    assert payload["implementation_pack_status"] == PACK_READY
    assert payload["strategy_family"] == STRATEGY_FAMILY
    assert payload["strategy_family_isolated"] is True
    assert payload["paper_only"] is True
    assert payload["burst_live_permission"] is False
    assert payload["first_tiny_live_lane"] == BASELINE_LANE
    assert payload["first_live_lane_change_allowed"] is False
    assert payload["risk_contract_preview"]["preview_only"] is True
    assert payload["risk_contract_preview"]["risk_contract_written"] is False
    assert payload["risk_contract_preview"]["config_written"] is False
    assert readiness["rows_seen"] > 0
    assert readiness["live_permission_count"] == 0
    assert readiness["burst_live_permission_count"] == 0
    assert readiness["risk_contract_written_count"] == 0
    assert readiness["synthetic_performance_created_count"] == 0
    assert readiness["gross_only_ready_rows"] == 0
    assert readiness["sequence_unknown_live_ready_rows"] == 0
    assert readiness["sequence_unknown_rows"] > 0
    assert "R333E Burst Lab Evidence Audit" in payload["recommended_r333e_path"]["phase"]
    assert payload["recommended_r333f_path"]["future_only"] is True
    assert (Path(payload["archive_log_dir"]) / "ultra_short_burst_lab_implementation_pack.ndjson").exists()
    for key, expected in SAFETY.items():
        assert payload[key] is expected
        assert payload["safety"][key] is expected
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


def test_inspect_routes_work(tmp_path: Path) -> None:
    log_dir = _seed_signals(tmp_path)
    commands = (
        ("ultra-short-burst-backtest-adapter", BACKTEST_EVENT),
        ("ultra-short-burst-visual-terminal-panel", VISUAL_EVENT),
        ("ultra-short-burst-risk-contract-preview", RISK_EVENT),
        ("ultra-short-burst-lab-implementation-pack", PACK_EVENT),
    )
    for command, event_type in commands:
        result = _run(
            [
                ".venv/bin/python",
                "-m",
                "src.app.hammer_radar.operator.inspect",
                "--log-dir",
                str(log_dir),
                command,
                "--no-write",
            ]
        )
        payload = json.loads(result.stdout)
        assert payload["event_type"] == event_type
        assert payload["strategy_family"] == STRATEGY_FAMILY


def test_operator_scripts_exist_and_print_required_sections(tmp_path: Path) -> None:
    log_dir = _seed_signals(tmp_path)
    scripts = {
        "scripts/hammer_print_r333b_ultra_short_burst_backtest_adapter.sh": (
            "R333B ULTRA SHORT BURST BACKTEST ADAPTER",
            "BACKTEST SUMMARY",
            "SEQUENCE UNKNOWN SUMMARY",
            "EVIDENCE READINESS SUMMARY",
            "SAFETY FLAGS",
        ),
        "scripts/hammer_print_r333c_ultra_short_burst_visual_terminal_panel.sh": (
            "R333C ULTRA SHORT BURST VISUAL TERMINAL PANEL",
            "PAPER ONLY / LIVE PERMISSION FALSE",
            "Leverage ladder",
            "Checkpoint timeline",
        ),
        "scripts/hammer_print_r333d_ultra_short_burst_risk_contract_preview.sh": (
            "R333D ULTRA SHORT BURST RISK CONTRACT PREVIEW",
            "PREVIEW ONLY",
            "cross_margin_allowed: False",
            "anti_fantasy_fill_gate_required: True",
        ),
        "scripts/hammer_print_r333bcd_ultra_short_burst_lab_implementation_pack.sh": (
            "R333BCD ULTRA SHORT BURST LAB IMPLEMENTATION PACK",
            "BACKTEST SUMMARY",
            "VISUAL PANEL PREVIEW",
            "RISK CONTRACT PREVIEW SUMMARY",
            "SEQUENCE UNKNOWN SUMMARY",
            "EVIDENCE READINESS SUMMARY",
            "RECOMMENDED R333E/R333F",
            "SAFETY FLAGS",
        ),
    }
    root = Path(__file__).resolve().parents[2]
    for script, sections in scripts.items():
        result = subprocess.run(
            ["bash", script],
            cwd=root,
            env={**os.environ, "PYTHONPATH": ".", "LOG_DIR": str(log_dir)},
            text=True,
            capture_output=True,
            check=True,
        )
        assert (root / script).exists()
        for section in sections:
            assert section in result.stdout


def test_r333a_r332_r331_r314_surfaces_remain_importable() -> None:
    modules = (
        "src.app.hammer_radar.operator.ultra_short_leverage_burst_lab_design",
        "src.app.hammer_radar.operator.strategy_lab_captured_source_data_merge",
        "src.app.hammer_radar.operator.strategy_lab_source_data_capture_adapter",
        "src.app.hammer_radar.operator.strategy_lab_adapter_output_batch_execution_packet",
        "src.app.hammer_radar.operator.strategy_lab_evidence_adapter_pack",
        "src.app.hammer_radar.operator.multi_lane_observation_health_panel",
    )
    for module_name in modules:
        assert import_module(module_name)


def _seed_signals(tmp_path: Path) -> Path:
    log_dir = tmp_path / "logs"
    append_signal(_signal("sig-4m-long", "4m", "long"), log_dir=log_dir)
    append_signal(_signal("sig-8m-short", "8m", "short"), log_dir=log_dir)
    return log_dir


def _signal(signal_id: str, timeframe: str, direction: str) -> SignalRecord:
    return SignalRecord(
        signal_id=signal_id,
        symbol="BTCUSDT",
        timeframe=timeframe,
        direction=direction,
        timestamp=NOW.isoformat(),
        hammer_strength=80.0,
        hammer_high=101.0,
        hammer_low=99.0,
        fib_50=100.0,
        fib_618=100.5,
        fib_650=100.6,
        fib_786=101.0,
        invalidation=98.5,
        bias_timeframe="44m",
        bias_direction="bullish" if direction == "long" else "bearish",
        bias_aligned=True,
        same_direction_streak=2,
        opposite_direction_streak=0,
        tradable=True,
        signal_close=100.4,
    )


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
