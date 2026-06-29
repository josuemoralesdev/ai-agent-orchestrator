"""R333A read-only Ultra Short Leverage Burst lab design packet."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion import BASELINE_LANE, SAFETY as BASE_SAFETY

EVENT_TYPE = "R333A_ULTRA_SHORT_LEVERAGE_BURST_LAB_DESIGN_PACKET"
CREATED_BY_PHASE = "R333A_ULTRA_SHORT_LEVERAGE_BURST_LAB_DESIGN_PACKET"
LEDGER_FILENAME = "ultra_short_leverage_burst_lab_design.ndjson"

READY = "ULTRA_SHORT_LEVERAGE_BURST_LAB_DESIGN_READY"
BLOCKED = "ULTRA_SHORT_LEVERAGE_BURST_LAB_DESIGN_BLOCKED"
STRATEGY_FAMILY = "ULTRA_SHORT_LEVERAGE_BURST"

CANDIDATE_TIMEFRAMES = ("4m", "8m")
LEVERAGE_GRID = (22, 44, 88, 150)
CHECKPOINT_GRID_SECONDS = (22, 44, 66, 88, 132, 176)
GROSS_ROE_TARGET_GRID = (5, 10, 15, 22)
MINIMUM_NET_ROE_TARGET_GRID = (2, 3, 5, 8)
HARD_LOSS_ROE_GRID = (-5, -8, -10, -12)
TIMEOUT_SECONDS_GRID = (44, 66, 88, 132, 176)

SAFETY: dict[str, bool] = {
    **BASE_SAFETY,
    "observed_expansion_written": False,
    "synthetic_performance_created": False,
    "burst_live_permission": False,
    "burst_family_isolated": True,
}


def build_ultra_short_leverage_burst_lab_design(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    timeframe: str = "all",
    include_150x: bool = True,
    include_visual_spec: bool = True,
    include_risk_contract_preview_spec: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    selected_timeframes = _selected_timeframes(timeframe)
    leverage_grid = [value for value in LEVERAGE_GRID if include_150x or value != 150]
    blockers = _packet_blockers(selected_timeframes=selected_timeframes, leverage_grid=leverage_grid)
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "ultra_short_leverage_burst_lab_design_id": f"r333a_ultra_short_leverage_burst_lab_design_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ultra_short_leverage_burst_lab_design_path": str(packet_path(resolved_log_dir)),
        "burst_lab_design_status": BLOCKED if blockers else READY,
        "blockers": blockers,
        "strategy_family": STRATEGY_FAMILY,
        "strategy_family_isolated": True,
        "paper_only": True,
        "burst_live_permission": False,
        "first_tiny_live_lane": BASELINE_LANE,
        "first_live_lane_change_allowed": False,
        "candidate_timeframes": _candidate_timeframes(selected_timeframes),
        "signal_source_policy": _signal_source_policy(),
        "leverage_grid": _leverage_grid(leverage_grid),
        "checkpoint_grid_seconds": list(CHECKPOINT_GRID_SECONDS),
        "checkpoint_policy_design": _checkpoint_policy_design(),
        "exit_policy_design": _exit_policy_design(),
        "fee_slippage_model_design": _fee_slippage_model_design(),
        "liquidation_proximity_model_design": _liquidation_proximity_model_design(),
        "required_market_data_design": _required_market_data_design(),
        "evidence_contract": _evidence_contract(),
        "visual_terminal_design_spec": _visual_terminal_design_spec() if include_visual_spec else {"included": False},
        "future_backtest_adapter_spec": _future_backtest_adapter_spec(),
        "future_visual_panel_spec": _future_visual_panel_spec() if include_visual_spec else {"included": False},
        "future_risk_contract_preview_spec": (
            _future_risk_contract_preview_spec() if include_risk_contract_preview_spec else {"included": False}
        ),
        "recommended_r333b_path": _recommended_r333b_path(),
        "recommended_r333c_path": _recommended_r333c_path(),
        "recommended_r333d_path": _recommended_r333d_path(),
        "recommended_r333e_path": _recommended_r333e_path(),
        "recommended_r333f_path": _recommended_r333f_path(),
        "recommended_tiny_live_path": _recommended_tiny_live_path(),
        "no_live_mutation_summary": _no_live_mutation_summary(),
        "live_permission_count": 0,
        "source_surfaces_used": _source_surfaces(resolved_log_dir),
        "safety": dict(SAFETY),
        **dict(SAFETY),
    }
    safe_payload = _sanitize(payload)
    if write:
        append_packet(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def append_packet(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = packet_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_ultra_short_leverage_burst_lab_design_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(packet_path(get_log_dir(log_dir, use_env=True)), limit=limit, max_bytes=2_000_000)


def packet_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_ultra_short_leverage_burst_lab_design_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_ultra_short_leverage_burst_lab_design_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R333A ULTRA SHORT LEVERAGE BURST LAB DESIGN PACKET",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        f"burst_lab_design_status: {payload.get('burst_lab_design_status')}",
        "",
        "STRATEGY FAMILY",
        f"strategy_family: {payload.get('strategy_family')}",
        f"strategy_family_isolated: {payload.get('strategy_family_isolated')}",
        f"paper_only: {payload.get('paper_only')}",
        f"burst_live_permission: {payload.get('burst_live_permission')}",
        "",
        "FIRST TINY LIVE LANE",
        f"first_tiny_live_lane: {payload.get('first_tiny_live_lane')}",
        f"first_live_lane_change_allowed: {payload.get('first_live_lane_change_allowed')}",
        "",
        "CANDIDATE TIMEFRAMES",
    ]
    for row in payload.get("candidate_timeframes") or []:
        if isinstance(row, Mapping):
            lines.append(
                f"{row.get('timeframe')}: mode={row.get('candidate_mode')} "
                f"standard_promotion={row.get('standard_promotion_allowed')} tiny_live={row.get('tiny_live_permission')}"
            )
    lines.extend(["", "LEVERAGE GRID"])
    for row in payload.get("leverage_grid") or []:
        if isinstance(row, Mapping):
            lines.append(
                f"{row.get('leverage')}x: 15pct_gross_move={row.get('price_move_pct_for_15pct_gross_roe')}% "
                f"fee_drag_sensitive={row.get('fee_drag_sensitivity')} live_permission={row.get('live_permission')}"
            )
    lines.extend(["", "CHECKPOINT GRID", ", ".join(str(value) for value in payload.get("checkpoint_grid_seconds") or [])])
    evidence = payload.get("evidence_contract") if isinstance(payload.get("evidence_contract"), Mapping) else {}
    lines.extend(
        [
            "",
            "EVIDENCE CONTRACT SUMMARY",
            f"minimum_sample_count_per_profile: {evidence.get('minimum_sample_count_per_profile')}",
            f"preferred_sample_count_per_profile: {evidence.get('preferred_sample_count_per_profile')}",
            f"minimum_net_win_rate_after_fees_slippage_pct: {evidence.get('minimum_net_win_rate_after_fees_slippage_pct')}",
            f"minimum_profit_factor: {evidence.get('minimum_profit_factor')}",
            f"gross_only_roe_readiness_allowed: {evidence.get('gross_only_roe_readiness_allowed')}",
            f"standard_55_policy_applies: {evidence.get('standard_55_policy_applies')}",
            f"tiny_live_inheritance: {evidence.get('tiny_live_inheritance')}",
        ]
    )
    lines.extend(["", "FEE / SLIPPAGE / LIQUIDATION WARNINGS"])
    fee = payload.get("fee_slippage_model_design") if isinstance(payload.get("fee_slippage_model_design"), Mapping) else {}
    liq = payload.get("liquidation_proximity_model_design") if isinstance(payload.get("liquidation_proximity_model_design"), Mapping) else {}
    lines.append(f"net_roe_formula: {fee.get('net_roe_formula')}")
    lines.append(f"fee_drag_roe_formula: {fee.get('fee_drag_roe_formula')}")
    lines.append(f"liquidation_warning: {liq.get('explicit_150x_warning')}")
    lines.extend(["", "VISUAL TERMINAL DESIGN PREVIEW"])
    visual = payload.get("visual_terminal_design_spec") if isinstance(payload.get("visual_terminal_design_spec"), Mapping) else {}
    for line in visual.get("preview_lines") or []:
        lines.append(str(line))
    lines.extend(["", "RECOMMENDED FUTURE PHASES"])
    for key in ("recommended_r333b_path", "recommended_r333c_path", "recommended_r333d_path"):
        lines.append(str(payload.get(key)))
    lines.extend(["", "SAFETY FLAGS"])
    safety = payload.get("safety") if isinstance(payload.get("safety"), Mapping) else {}
    for key in SAFETY:
        lines.append(f"{key}: {safety.get(key)}")
    return "\n".join(lines)


def _selected_timeframes(timeframe: str) -> tuple[str, ...]:
    if timeframe == "all":
        return CANDIDATE_TIMEFRAMES
    if timeframe in CANDIDATE_TIMEFRAMES:
        return (timeframe,)
    return ()


def _packet_blockers(*, selected_timeframes: Sequence[str], leverage_grid: Sequence[int]) -> list[str]:
    blockers: list[str] = []
    if not selected_timeframes:
        blockers.append("no_candidate_timeframes_selected")
    if not leverage_grid:
        blockers.append("no_leverage_grid_selected")
    return blockers


def _candidate_timeframes(selected_timeframes: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {
            "timeframe": timeframe,
            "candidate_mode": "paper_only",
            "burst_lab_only": True,
            "standard_promotion_allowed": False,
            "tiny_live_permission": False,
            "observed_expansion_write": False,
        }
        for timeframe in selected_timeframes
    ]


def _signal_source_policy() -> dict[str, Any]:
    return {
        "source_requirement": "signal_must_come_from_existing_radar_or_strategy_signal_surfaces",
        "entry_timestamp_policy": "exact_signal_detection_time_required_when_available",
        "candle_close_proxy_policy": "if_only_candle_close_is_available_fill_model_is_approximate",
        "stale_signal_replay_allowed_for_live_like_evidence": False,
        "signal_age_must_be_measured": True,
        "immediate_entry_definition": (
            "first_valid_paper_fill_after_detection_timestamp_not_next_candle_close_unless_only_available_proxy"
        ),
    }


def _leverage_grid(leverage_values: Sequence[int]) -> list[dict[str, Any]]:
    rows = []
    for leverage in leverage_values:
        rows.append(
            {
                "leverage": leverage,
                "gross_roe_target_examples_pct": list(GROSS_ROE_TARGET_GRID),
                "price_move_pct_for_15pct_gross_roe": round(15 / leverage, 4),
                "price_move_pct_for_gross_roe_formula": "gross_roe_pct / leverage",
                "liquidation_proximity_warning": (
                    "150x requires explicit liquidation danger-zone modeling"
                    if leverage == 150
                    else "high leverage requires adverse move and margin-mode modeling"
                ),
                "fee_drag_sensitivity": "fee and slippage drag scales by leverage",
                "live_permission": False,
            }
        )
    return rows


def _checkpoint_policy_design() -> dict[str, Any]:
    return {
        "checkpoint_grid_seconds": list(CHECKPOINT_GRID_SECONDS),
        "primary_operator_concept": "first_44s_checkpoint",
        "second_wave_checks_seconds": [66, 88],
        "optional_micro_checks_seconds": [22],
        "hard_timeout_exit_design": True,
        "early_take_profit_design": True,
        "adverse_velocity_exit_design": True,
    }


def _exit_policy_design() -> dict[str, Any]:
    return {
        "gross_roe_target_grid": list(GROSS_ROE_TARGET_GRID),
        "minimum_net_roe_target_grid": list(MINIMUM_NET_ROE_TARGET_GRID),
        "hard_loss_roe_grid": list(HARD_LOSS_ROE_GRID),
        "timeout_seconds_grid": list(TIMEOUT_SECONDS_GRID),
        "trailing_after_target_design": True,
        "close_at_first_net_target_design": True,
        "close_at_hard_timeout_design": True,
        "close_on_adverse_velocity_design": True,
        "averaging_down_allowed": False,
        "second_entry_requires_new_independent_signal": True,
        "gross_only_success_classification_allowed": False,
    }


def _fee_slippage_model_design() -> dict[str, Any]:
    return {
        "gross_roe_is_sufficient": False,
        "net_roe_after_fees_required": True,
        "round_trip_maker_taker_fee_required": True,
        "entry_and_exit_slippage_required": True,
        "latency_model_separate": True,
        "unknown_fees_slippage_result_confidence": "lower_confidence",
        "ready_using_gross_roe_only_allowed": False,
        "notional_fee_pct_round_trip_formula": "entry_fee_pct + exit_fee_pct",
        "fee_drag_roe_formula": "notional_fee_pct_round_trip * leverage",
        "estimated_slippage_roe_formula": "estimated_slippage_pct_round_trip * leverage",
        "net_roe_formula": "gross_roe - fee_drag_roe - estimated_slippage_roe",
    }


def _liquidation_proximity_model_design() -> dict[str, Any]:
    return {
        "estimated_adverse_price_move_to_danger_zone_required": True,
        "liquidation_proximity_modeled_not_ignored": True,
        "explicit_150x_warning": "150x has microscopic adverse-move tolerance and no live permission.",
        "future_tiny_burst_live_position_sizing": "microscopic_only_if_future_gate_passes",
        "future_margin_mode": "isolated_only",
        "cross_margin_allowed": False,
        "live_permission_r333a_to_r333d": False,
    }


def _required_market_data_design() -> dict[str, Any]:
    return {
        "best": "tick_trade_data_or_second_level_mark_or_last_price",
        "acceptable_for_early_lab": "sub_minute_replay_if_available",
        "poor": "candle_only_ohlc",
        "candle_only_ohlc_sequence_risk": "cannot_prove_whether_take_profit_or_stop_loss_happened_first",
        "candle_only_sequence_flag": "sequence_unknown",
        "sequence_unknown_can_promote_to_live": False,
        "future_r333b_capture_requirements": [
            "detection_timestamp",
            "first_fill_timestamp",
            "checkpoint_prices",
            "entry_exit_fee_assumptions",
            "entry_exit_slippage_assumptions",
            "latency_ms",
            "sequence_known",
            "max_adverse_excursion",
            "max_favorable_excursion",
        ],
    }


def _evidence_contract() -> dict[str, Any]:
    return {
        "minimum_sample_count_per_profile": 100,
        "preferred_sample_count_per_profile": 300,
        "minimum_net_win_rate_after_fees_slippage_pct": 60,
        "minimum_profit_factor": 1.31,
        "profit_factor_operator": ">",
        "max_adverse_excursion_known_required": True,
        "timeout_behavior_known_required": True,
        "fee_model_included_required": True,
        "slippage_model_included_required": True,
        "latency_model_included_required": True,
        "liquidation_proximity_model_included_required": True,
        "sequence_known_preferred": True,
        "gross_only_roe_readiness_allowed": False,
        "candle_only_fantasy_fills_allowed": False,
        "stale_shadow_outcomes_allowed": False,
        "standard_55_policy_applies": False,
        "tiny_live_inheritance": False,
        "separate_human_reviewed_burst_risk_contract_required": True,
    }


def _visual_terminal_design_spec() -> dict[str, Any]:
    return {
        "surface": "terminal_panel_not_website",
        "required_blocks": [
            "leverage_ladder",
            "checkpoint_timeline",
            "net_roe_bars",
            "fee_drag_warning",
            "liquidation_proximity_warning",
            "verdict_line",
            "paper_only_live_permission_line",
            "reason_codes",
        ],
        "preview_lines": [
            "ULTRA BURST LAB - BTCUSDT",
            "Signal TF / side / age: 4m or 8m / long|short / measured_seconds",
            "Entry mode: instant paper",
            "Leverage grid: 22x / 44x / 88x / 150x",
            "Checkpoints: 22s | 44s | 66s | 88s | 132s | 176s",
            "Net ROE bars: gross - fee_drag - slippage_drag",
            "Fee drag warning: required before any verdict",
            "Liquidation proximity warning: mandatory for 150x",
            "Verdict: DESIGN_ONLY_NO_LIVE_PERMISSION",
            "Live Permission: FALSE",
        ],
    }


def _future_backtest_adapter_spec() -> dict[str, Any]:
    return {
        "phase": "R333B Ultra-Short Burst Backtest Adapter",
        "paper_only": True,
        "input_signals": "existing_radar_or_strategy_signal_surfaces",
        "required_market_data": "tick_or_second_level_preferred",
        "must_emit_sequence_known": True,
        "must_emit_net_roe_after_fees_slippage": True,
        "must_not_write_synthetic_performance": True,
    }


def _future_visual_panel_spec() -> dict[str, Any]:
    return {
        "phase": "R333C Ultra-Short Burst Visual Terminal Panel",
        "terminal_only": True,
        "must_show_live_permission_false": True,
        "must_show_fee_drag_and_liquidation_warning": True,
    }


def _future_risk_contract_preview_spec() -> dict[str, Any]:
    return {
        "phase": "R333D Human-Reviewed Burst Risk Contract Preview",
        "preview_only": True,
        "writes_risk_contract": False,
        "requires_evidence_contract_before_any_future_activation": True,
        "isolated_margin_only_preview": True,
        "cross_margin_allowed": False,
        "live_permission": False,
    }


def _recommended_r333b_path() -> dict[str, Any]:
    return {"phase": "R333B Ultra-Short Burst Backtest Adapter", "purpose": "implement paper-only replay adapter"}


def _recommended_r333c_path() -> dict[str, Any]:
    return {"phase": "R333C Ultra-Short Burst Visual Terminal Panel", "purpose": "render terminal-only burst diagnostics"}


def _recommended_r333d_path() -> dict[str, Any]:
    return {"phase": "R333D Human-Reviewed Burst Risk Contract Preview", "purpose": "preview only; no config write"}


def _recommended_r333e_path() -> dict[str, Any]:
    return {"phase": "R333E Burst Lab Evidence Audit And Anti-Fantasy Fill Gate", "purpose": "reject sequence-unknown fantasy fills"}


def _recommended_r333f_path() -> dict[str, Any]:
    return {
        "phase": "R333F Tiny Burst Live Activation Gate",
        "purpose": "only if evidence contract passes in future",
        "live_permission_in_r333a": False,
    }


def _recommended_tiny_live_path() -> list[str]:
    return [
        f"First Tiny Live remains {BASELINE_LANE}.",
        "R333A does not inherit Tiny Live permissions.",
        "R333A does not change the first Tiny Live lane.",
        "Any future tiny-burst-live path requires a separate human-reviewed burst risk contract and later activation gate.",
    ]


def _no_live_mutation_summary() -> dict[str, bool]:
    return {
        "no_orders": True,
        "no_binance_order_or_test_order_endpoints": True,
        "no_leverage_or_margin_change": True,
        "no_live_flag_mutation": True,
        "no_kill_switch_mutation": True,
        "no_arming_mutation": True,
        "no_submit": True,
        "no_final_command": True,
        "no_first_tiny_live_lane_change": True,
        "no_promotion_event_write": True,
        "no_risk_contract_write": True,
        "no_observed_expansion_write": True,
        "no_config_or_env_mutation": True,
        "no_systemd_mutation": True,
        "no_scheduler_start": True,
        "no_telegram_send": True,
        "no_synthetic_performance_creation": True,
    }


def _source_surfaces(log_dir: Path) -> list[str]:
    return [
        "docs/hammer_radar/live_readiness/R332_STRATEGY_LAB_CAPTURED_SOURCE_DATA_MERGE_INTO_ADAPTER_ROWS.md",
        "docs/hammer_radar/live_readiness/R331_STRATEGY_LAB_SOURCE_DATA_CAPTURE_ADAPTER_IMPLEMENTATION.md",
        "docs/hammer_radar/live_readiness/R329_STRATEGY_LAB_ADAPTER_OUTPUT_BATCH_EXECUTION_PACKET.md",
        "docs/hammer_radar/live_readiness/R328_STRATEGY_LAB_EVIDENCE_ADAPTER_IMPLEMENTATION_PACK.md",
        "docs/hammer_radar/live_readiness/R325_STRATEGY_LAB_PROMOTION_REVIEW_PACKET.md",
        "src/app/hammer_radar/operator/strategy_lab_captured_source_data_merge.py",
        "src/app/hammer_radar/operator/strategy_lab_source_data_capture_adapter.py",
        "src/app/hammer_radar/operator/strategy_lab_adapter_output_batch_execution_packet.py",
        "src/app/hammer_radar/operator/strategy_lab_evidence_adapter_pack.py",
        "src/app/hammer_radar/operator/inspect.py",
        "configs/hammer_radar/tiny_live_risk_contracts.json",
        "configs/hammer_radar/autonomous_arming_state.json",
        str(log_dir / "strategy_lab_captured_source_data_merge.ndjson"),
        str(log_dir / "strategy_lab_source_data_capture_adapter.ndjson"),
        str(log_dir / "strategy_lab_adapter_output_batch_execution_packet.ndjson"),
        str(log_dir / "strategy_lab_evidence_adapter_pack.ndjson"),
        str(log_dir / "multi_lane_dry_run_observation.ndjson"),
    ]


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if any(token in str(key).lower() for token in ("secret", "token", "api_key", "signature")):
                sanitized[str(key)] = False if isinstance(item, bool) else "redacted"
            else:
                sanitized[str(key)] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the R333A Ultra Short Leverage Burst lab design packet.")
    parser.add_argument("--log-dir", default=None)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--timeframe", choices=("all", "4m", "8m"), default="all")
    parser.add_argument("--include-150x", action="store_true", default=True)
    parser.add_argument("--include-visual-spec", action="store_true", default=True)
    parser.add_argument("--include-risk-contract-preview-spec", action="store_true", default=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = build_ultra_short_leverage_burst_lab_design(
        log_dir=args.log_dir,
        write=not args.no_write,
        timeframe=args.timeframe,
        include_150x=args.include_150x,
        include_visual_spec=args.include_visual_spec,
        include_risk_contract_preview_spec=args.include_risk_contract_preview_spec,
    )
    if args.text:
        print(format_ultra_short_leverage_burst_lab_design_text(payload))
    else:
        print(format_ultra_short_leverage_burst_lab_design_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
