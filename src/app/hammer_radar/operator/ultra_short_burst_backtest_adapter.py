"""R333B paper-only Ultra Short Burst backtest adapter."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir, load_signals
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion import BASELINE_LANE, SAFETY as BASE_SAFETY
from src.app.hammer_radar.operator.strategy_lab_captured_source_data_merge import (
    load_strategy_lab_captured_source_data_merge_records,
)
from src.app.hammer_radar.operator.ultra_short_leverage_burst_lab_design import (
    CHECKPOINT_GRID_SECONDS,
    GROSS_ROE_TARGET_GRID,
    LEVERAGE_GRID,
    STRATEGY_FAMILY,
)

EVENT_TYPE = "R333B_ULTRA_SHORT_BURST_BACKTEST_ADAPTER"
CREATED_BY_PHASE = "R333B_ULTRA_SHORT_BURST_BACKTEST_ADAPTER"
LEDGER_FILENAME = "ultra_short_burst_backtest_adapter.ndjson"

READY = "ULTRA_SHORT_BURST_BACKTEST_ADAPTER_READY"
PARTIAL = "ULTRA_SHORT_BURST_BACKTEST_ADAPTER_PARTIAL"
BLOCKED = "ULTRA_SHORT_BURST_BACKTEST_ADAPTER_BLOCKED"

CANDIDATE_TIMEFRAMES = ("4m", "8m")
SIDES = ("long", "short")
SOURCE_SUMMARY_ONLY = "SOURCE_SUMMARY_ONLY"
MODEL_PREVIEW_NOT_TRADE_RESULT = "MODEL_PREVIEW_NOT_TRADE_RESULT"
REPLAY_READY = "REPLAY_READY"
REPLAY_PENDING_INTRABAR_DATA = "REPLAY_PENDING_INTRABAR_DATA"
SEQUENCE_UNKNOWN = "SEQUENCE_UNKNOWN_CANDLE_ONLY_OR_NO_INTRABAR_PATH"
MISSING_TS = "MISSING_OR_APPROXIMATE"

SAFETY: dict[str, bool] = {
    **BASE_SAFETY,
    "observed_expansion_written": False,
    "synthetic_performance_created": False,
    "burst_live_permission": False,
    "burst_family_isolated": True,
    "risk_contract_preview_only": True,
    "risk_contract_written": False,
}

ROW_SAFETY: dict[str, bool] = {
    "live_permission": False,
    "burst_live_permission": False,
    "tiny_live_eligible_now": False,
    "standard_55_policy_applies": False,
    "tiny_live_inheritance": False,
    "promotion_event_written": False,
    "risk_contract_write_required": False,
    "risk_contract_written": False,
    "observed_expansion_written": False,
    "scheduler_required": False,
    "synthetic_performance_created": False,
}


def build_ultra_short_burst_backtest_adapter(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    timeframe: str = "all",
    leverage: str = "all",
    max_signals: int = 500,
    fee_pct_round_trip: float = 0.08,
    slippage_pct_round_trip: float = 0.02,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    selected_timeframes = _selected_timeframes(timeframe)
    selected_leverage = _selected_leverage(leverage)
    source_rows = _source_rows(resolved_log_dir, generated_at, max_signals=max_signals)
    filtered_sources = [
        row for row in source_rows if row.get("timeframe") in selected_timeframes and row.get("side") in SIDES
    ]
    burst_rows = _burst_rows(
        filtered_sources,
        selected_leverage=selected_leverage,
        fee_pct_round_trip=fee_pct_round_trip,
        slippage_pct_round_trip=slippage_pct_round_trip,
    )
    blockers = _blockers(selected_timeframes, selected_leverage)
    status = BLOCKED if blockers else (READY if burst_rows else PARTIAL)
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "burst_backtest_adapter_id": f"r333b_ultra_short_burst_backtest_adapter_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ultra_short_burst_backtest_adapter_path": str(packet_path(resolved_log_dir)),
        "backtest_adapter_status": status,
        "blockers": blockers,
        "strategy_family": STRATEGY_FAMILY,
        "strategy_family_isolated": True,
        "paper_only": True,
        "first_tiny_live_lane": BASELINE_LANE,
        "first_live_lane_change_allowed": False,
        "candidate_timeframes": list(CANDIDATE_TIMEFRAMES),
        "selected_timeframes": list(selected_timeframes),
        "candidate_leverage_grid": list(selected_leverage),
        "checkpoint_grid_seconds": list(CHECKPOINT_GRID_SECONDS),
        "gross_roe_target_grid": list(GROSS_ROE_TARGET_GRID),
        "fee_pct_round_trip": fee_pct_round_trip,
        "slippage_pct_round_trip": slippage_pct_round_trip,
        "source_summary": _source_summary(source_rows, filtered_sources),
        "burst_backtest_rows": burst_rows,
        "backtest_adapter_summary": _adapter_summary(burst_rows),
        "sequence_unknown_summary": _sequence_unknown_summary(burst_rows),
        "evidence_readiness_summary": evidence_readiness_summary(burst_rows),
        "data_limitations": data_limitations(),
        "source_surfaces_used": source_surfaces(resolved_log_dir),
        "no_live_mutation_summary": no_live_mutation_summary(),
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


def load_ultra_short_burst_backtest_adapter_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(packet_path(get_log_dir(log_dir, use_env=True)), limit=limit, max_bytes=8_000_000)


def packet_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_ultra_short_burst_backtest_adapter_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_ultra_short_burst_backtest_adapter_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R333B ULTRA SHORT BURST BACKTEST ADAPTER",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        f"backtest_adapter_status: {payload.get('backtest_adapter_status')}",
        "PAPER ONLY / LIVE PERMISSION FALSE",
        "",
        "STRATEGY FAMILY",
        f"strategy_family: {payload.get('strategy_family')}",
        f"strategy_family_isolated: {payload.get('strategy_family_isolated')}",
        "",
        "BACKTEST SUMMARY",
    ]
    for key, value in (payload.get("backtest_adapter_summary") or {}).items():
        lines.append(f"{key}: {value}")
    lines.extend(["", "SEQUENCE UNKNOWN SUMMARY"])
    for key, value in (payload.get("sequence_unknown_summary") or {}).items():
        lines.append(f"{key}: {value}")
    lines.extend(["", "EVIDENCE READINESS SUMMARY"])
    for key, value in (payload.get("evidence_readiness_summary") or {}).items():
        lines.append(f"{key}: {value}")
    lines.extend(["", "SAMPLE ROWS"])
    for row in (payload.get("burst_backtest_rows") or [])[:8]:
        if isinstance(row, Mapping):
            lines.append(
                f"{row.get('timeframe')} {row.get('side')} {row.get('leverage')}x "
                f"checkpoint={row.get('checkpoint_seconds')} result={row.get('result_status')} "
                f"sequence_known={row.get('sequence_known')} net_formula={row.get('net_roe_formula')}"
            )
    lines.extend(["", "SAFETY FLAGS"])
    for key in SAFETY:
        lines.append(f"{key}: {(payload.get('safety') or {}).get(key)}")
    return "\n".join(lines)


def evidence_readiness_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "rows_seen": len(rows),
        "replay_ready_rows": sum(1 for row in rows if row.get("result_status") == REPLAY_READY),
        "replay_pending_intrabar_data_rows": sum(1 for row in rows if row.get("result_status") == REPLAY_PENDING_INTRABAR_DATA),
        "source_summary_only_rows": sum(1 for row in rows if row.get("result_status") == SOURCE_SUMMARY_ONLY),
        "model_preview_not_trade_result_rows": sum(1 for row in rows if row.get("result_status") == MODEL_PREVIEW_NOT_TRADE_RESULT),
        "sequence_known_rows": sum(1 for row in rows if row.get("sequence_known") is True),
        "sequence_unknown_rows": sum(1 for row in rows if row.get("sequence_known") is False),
        "live_permission_count": sum(1 for row in rows if row.get("live_permission") is True),
        "burst_live_permission_count": sum(1 for row in rows if row.get("burst_live_permission") is True),
        "risk_contract_written_count": sum(1 for row in rows if row.get("risk_contract_written") is True),
        "synthetic_performance_created_count": sum(1 for row in rows if row.get("synthetic_performance_created") is True),
        "gross_only_ready_rows": 0,
        "sequence_unknown_live_ready_rows": sum(
            1 for row in rows if row.get("sequence_known") is False and row.get("live_permission") is True
        ),
    }


def data_limitations() -> list[str]:
    return [
        "exact detection timestamps may be missing",
        "second/tick-level price path may be missing",
        "candle-only OHLC cannot prove TP/SL sequence",
        "sequence_unknown cannot promote to live",
        "formula previews are not trade results",
        "no live readiness without R333E anti-fantasy fill gate",
    ]


def source_surfaces(log_dir: Path) -> list[str]:
    return [
        "logs/hammer_radar_forward/signals.ndjson",
        str(log_dir / "strategy_lab_captured_source_data_merge.ndjson"),
        str(log_dir / "strategy_lab_source_data_capture_adapter.ndjson"),
        str(log_dir / "strategy_lab_evidence_adapter_pack.ndjson"),
        str(log_dir / "ultra_short_leverage_burst_lab_design.ndjson"),
    ]


def no_live_mutation_summary() -> dict[str, bool]:
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


def _source_rows(log_dir: Path, generated_at: datetime, *, max_signals: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    merge_records = load_strategy_lab_captured_source_data_merge_records(log_dir=log_dir, limit=1)
    if merge_records:
        merge = merge_records[-1]
        for row in merge.get("merged_adapter_rows") or []:
            if isinstance(row, Mapping):
                rows.append(_normalize_source_mapping(row, source_type="strategy_lab_captured_source_data_merge"))
    for signal in load_signals(log_dir)[-max(max_signals, 0):]:
        if signal.timeframe in CANDIDATE_TIMEFRAMES and signal.direction in SIDES:
            rows.append(
                {
                    "source_type": "hammer_radar_signal",
                    "source_signal_id": signal.signal_id,
                    "lane_key": f"{signal.symbol}|{signal.timeframe}|{signal.direction}|instant_paper",
                    "symbol": signal.symbol,
                    "timeframe": signal.timeframe,
                    "side": signal.direction,
                    "entry_model": "instant_paper",
                    "source_signal_status": "SIGNAL_SUMMARY_AVAILABLE" if signal.tradable else "SIGNAL_SUMMARY_REJECTED",
                    "detection_timestamp": signal.timestamp,
                    "entry_price": signal.fib_618 or signal.signal_close,
                    "has_intrabar_path": False,
                    "has_trade_result": False,
                }
            )
    return rows[: max(max_signals, 0)]


def _normalize_source_mapping(row: Mapping[str, Any], *, source_type: str) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "source_signal_id": row.get("merged_row_id") or row.get("source_row_id") or row.get("row_id") or row.get("lane_key"),
        "lane_key": row.get("lane_key"),
        "symbol": row.get("symbol"),
        "timeframe": row.get("timeframe"),
        "side": row.get("side"),
        "entry_model": row.get("entry_mode") or "source_summary",
        "source_signal_status": row.get("merge_status") or row.get("capture_status") or row.get("evidence_status") or "SOURCE_SUMMARY_AVAILABLE",
        "detection_timestamp": row.get("detection_timestamp") or row.get("timestamp"),
        "entry_price": row.get("entry_price"),
        "has_intrabar_path": bool(row.get("intrabar_price_path") or row.get("checkpoint_prices")),
        "has_trade_result": row.get("gross_roe_pct") is not None,
        "gross_roe_pct": row.get("gross_roe_pct"),
    }


def _burst_rows(
    sources: Sequence[Mapping[str, Any]],
    *,
    selected_leverage: Sequence[int],
    fee_pct_round_trip: float,
    slippage_pct_round_trip: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    unique_sources = list({str(source.get("source_signal_id")) + str(source.get("lane_key")): source for source in sources}.values())
    for source_index, source in enumerate(unique_sources):
        has_result = source.get("has_trade_result") is True
        has_path = source.get("has_intrabar_path") is True
        for lev in selected_leverage:
            for checkpoint in CHECKPOINT_GRID_SECONDS:
                gross = _gross_roe(source, has_result=has_result)
                result_status = REPLAY_READY if has_path and has_result else MODEL_PREVIEW_NOT_TRADE_RESULT
                if not has_result:
                    result_status = SOURCE_SUMMARY_ONLY
                if has_path and not has_result:
                    result_status = REPLAY_PENDING_INTRABAR_DATA
                row = {
                    "burst_row_id": f"r333b|{source_index}|{source.get('source_signal_id')}|{lev}x|{checkpoint}s".replace(" ", "_"),
                    "strategy_family": STRATEGY_FAMILY,
                    "timeframe": source.get("timeframe"),
                    "side": source.get("side"),
                    "lane_key": source.get("lane_key"),
                    "source_signal_id": source.get("source_signal_id"),
                    "source_signal_status": source.get("source_signal_status"),
                    "detection_timestamp_status": "AVAILABLE" if source.get("detection_timestamp") else MISSING_TS,
                    "entry_model": source.get("entry_model") or "instant_paper",
                    "entry_timestamp_status": "AVAILABLE" if source.get("detection_timestamp") else MISSING_TS,
                    "leverage": lev,
                    "checkpoint_seconds": checkpoint,
                    "fee_pct_round_trip": fee_pct_round_trip,
                    "slippage_pct_round_trip": slippage_pct_round_trip,
                    "fee_drag_roe": round(fee_pct_round_trip * lev, 6),
                    "estimated_slippage_roe": round(slippage_pct_round_trip * lev, 6),
                    "gross_roe_target_pct": gross,
                    "price_move_pct_for_gross_roe": None if gross is None else round(gross / lev, 6),
                    "net_roe_formula": None
                    if gross is None
                    else round(gross - (fee_pct_round_trip * lev) - (slippage_pct_round_trip * lev), 6),
                    "sequence_known": False,
                    "sequence_status": SEQUENCE_UNKNOWN,
                    "result_status": result_status,
                    "evidence_quality": "SUMMARY_ONLY" if result_status == SOURCE_SUMMARY_ONLY else "SEQUENCE_UNKNOWN",
                    "liquidation_proximity_warning": _liquidation_warning(lev),
                    "blockers": _row_blockers(has_path=has_path, has_result=has_result),
                    **dict(ROW_SAFETY),
                }
                rows.append(row)
    return rows


def _gross_roe(source: Mapping[str, Any], *, has_result: bool) -> float | None:
    if not has_result:
        return None
    try:
        return round(float(source.get("gross_roe_pct")), 6)
    except (TypeError, ValueError):
        return None


def _row_blockers(*, has_path: bool, has_result: bool) -> list[str]:
    blockers = ["sequence_unknown_cannot_promote_to_live"]
    if not has_path:
        blockers.append("missing_tick_or_second_level_price_path")
    if not has_result:
        blockers.append("missing_replay_trade_result")
    blockers.append("requires_r333e_anti_fantasy_fill_gate")
    return blockers


def _liquidation_warning(leverage: int) -> str:
    if leverage == 150:
        return "150x EXTREME DANGER: microscopic adverse move tolerance; no live permission."
    return "high leverage requires liquidation proximity modeling before any future live discussion"


def _adapter_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "rows_seen": len(rows),
        "candidate_timeframes_seen": sorted({row.get("timeframe") for row in rows if row.get("timeframe")}),
        "candidate_sides_seen": sorted({row.get("side") for row in rows if row.get("side")}),
        "leverage_grid_seen": sorted({row.get("leverage") for row in rows if row.get("leverage")}),
        "checkpoint_grid_seen": sorted({row.get("checkpoint_seconds") for row in rows if row.get("checkpoint_seconds")}),
        "result_status_counts": dict(Counter(str(row.get("result_status")) for row in rows)),
        "live_permission_count": 0,
    }


def _sequence_unknown_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "sequence_known_rows": sum(1 for row in rows if row.get("sequence_known") is True),
        "sequence_unknown_rows": sum(1 for row in rows if row.get("sequence_known") is False),
        "sequence_unknown_policy": "sequence_unknown rows cannot be live-ready or promoted",
    }


def _source_summary(source_rows: Sequence[Mapping[str, Any]], filtered_sources: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "source_rows_seen": len(source_rows),
        "filtered_candidate_sources": len(filtered_sources),
        "source_types_seen": dict(Counter(str(row.get("source_type")) for row in source_rows)),
    }


def _selected_timeframes(timeframe: str) -> tuple[str, ...]:
    if timeframe == "all":
        return CANDIDATE_TIMEFRAMES
    if timeframe in CANDIDATE_TIMEFRAMES:
        return (timeframe,)
    return ()


def _selected_leverage(leverage: str) -> tuple[int, ...]:
    if leverage == "all":
        return tuple(LEVERAGE_GRID)
    try:
        value = int(leverage)
    except ValueError:
        return ()
    return (value,) if value in LEVERAGE_GRID else ()


def _blockers(timeframes: Sequence[str], leverage_grid: Sequence[int]) -> list[str]:
    blockers: list[str] = []
    if not timeframes:
        blockers.append("no_candidate_timeframes_selected")
    if not leverage_grid:
        blockers.append("no_leverage_grid_selected")
    return blockers


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
    parser = argparse.ArgumentParser(description="Build the R333B Ultra Short Burst paper backtest adapter.")
    parser.add_argument("--log-dir", default=None)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--timeframe", choices=("all", "4m", "8m"), default="all")
    parser.add_argument("--leverage", choices=("all", "22", "44", "88", "150"), default="all")
    parser.add_argument("--max-signals", type=int, default=500)
    parser.add_argument("--fee-pct-round-trip", type=float, default=0.08)
    parser.add_argument("--slippage-pct-round-trip", type=float, default=0.02)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = build_ultra_short_burst_backtest_adapter(
        log_dir=args.log_dir,
        write=not args.no_write,
        timeframe=args.timeframe,
        leverage=args.leverage,
        max_signals=args.max_signals,
        fee_pct_round_trip=args.fee_pct_round_trip,
        slippage_pct_round_trip=args.slippage_pct_round_trip,
    )
    if args.text:
        print(format_ultra_short_burst_backtest_adapter_text(payload))
    else:
        print(format_ultra_short_burst_backtest_adapter_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
