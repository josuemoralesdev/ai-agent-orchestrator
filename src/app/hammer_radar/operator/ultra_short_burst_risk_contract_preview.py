"""R333D preview-only Ultra Short Burst risk contract object."""

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
from src.app.hammer_radar.operator.ultra_short_burst_backtest_adapter import (
    CHECKPOINT_GRID_SECONDS,
    LEVERAGE_GRID,
    SAFETY,
    STRATEGY_FAMILY,
)
from src.app.hammer_radar.operator.ultra_short_leverage_burst_lab_design import (
    HARD_LOSS_ROE_GRID,
    MINIMUM_NET_ROE_TARGET_GRID,
    TIMEOUT_SECONDS_GRID,
)

EVENT_TYPE = "R333D_ULTRA_SHORT_BURST_RISK_CONTRACT_PREVIEW"
CREATED_BY_PHASE = "R333D_ULTRA_SHORT_BURST_RISK_CONTRACT_PREVIEW"
LEDGER_FILENAME = "ultra_short_burst_risk_contract_preview.ndjson"
READY = "ULTRA_SHORT_BURST_RISK_CONTRACT_PREVIEW_READY"


def build_ultra_short_burst_risk_contract_preview(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    timeframe: str = "all",
    leverage: str = "all",
    include_150x: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    leverage_grid = [
        value for value in _selected_leverage(leverage) if include_150x or value != 150 or leverage == "150"
    ]
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "risk_contract_preview_id": f"r333d_ultra_short_burst_risk_contract_preview_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ultra_short_burst_risk_contract_preview_path": str(packet_path(resolved_log_dir)),
        "risk_contract_preview_status": READY,
        "blockers": [],
        "strategy_family": STRATEGY_FAMILY,
        "strategy_family_isolated": True,
        "paper_only": True,
        "preview_only": True,
        "risk_contract_preview_only": True,
        "risk_contract_written": False,
        "risk_contract_config_mutated": False,
        "config_written": False,
        "isolated_margin_only": True,
        "cross_margin_allowed": False,
        "max_future_position_sizing_policy": "MICROSCOPIC_ONLY",
        "selected_timeframe": timeframe,
        "leverage_grid": leverage_grid,
        "timeout_grid": list(TIMEOUT_SECONDS_GRID),
        "checkpoint_grid_seconds": list(CHECKPOINT_GRID_SECONDS),
        "hard_loss_roe_grid": list(HARD_LOSS_ROE_GRID),
        "min_net_roe_target_grid": list(MINIMUM_NET_ROE_TARGET_GRID),
        "evidence_contract_required": True,
        "anti_fantasy_fill_gate_required": True,
        "separate_human_reviewed_burst_risk_contract_required": True,
        "live_permission": False,
        "burst_live_permission": False,
        "tiny_live_eligible_now": False,
        "future_requirements": [
            "R333E anti-fantasy fill gate before any future live discussion",
            "separate human-reviewed burst risk contract required",
            "sequence_known evidence required",
            "fee, slippage, latency, liquidation proximity, and sample count audit required",
        ],
        "danger_warnings": _danger_warnings(leverage_grid),
        "risk_contract_preview_summary": {
            "preview_only": True,
            "risk_contract_written": False,
            "config_written": False,
            "isolated_margin_only": True,
            "cross_margin_allowed": False,
            "anti_fantasy_fill_gate_required": True,
            "live_permission": False,
        },
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


def load_ultra_short_burst_risk_contract_preview_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(packet_path(get_log_dir(log_dir, use_env=True)), limit=limit, max_bytes=4_000_000)


def packet_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_ultra_short_burst_risk_contract_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_ultra_short_burst_risk_contract_preview_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R333D ULTRA SHORT BURST RISK CONTRACT PREVIEW",
        "PREVIEW ONLY / NO RISK CONTRACT WRITE / LIVE PERMISSION FALSE",
        f"risk_contract_preview_status: {payload.get('risk_contract_preview_status')}",
        f"strategy_family: {payload.get('strategy_family')}",
        f"preview_only: {payload.get('preview_only')}",
        f"risk_contract_written: {payload.get('risk_contract_written')}",
        f"config_written: {payload.get('config_written')}",
        f"isolated_margin_only: {payload.get('isolated_margin_only')}",
        f"cross_margin_allowed: {payload.get('cross_margin_allowed')}",
        f"max_future_position_sizing_policy: {payload.get('max_future_position_sizing_policy')}",
        f"leverage_grid: {payload.get('leverage_grid')}",
        f"timeout_grid: {payload.get('timeout_grid')}",
        f"hard_loss_roe_grid: {payload.get('hard_loss_roe_grid')}",
        f"min_net_roe_target_grid: {payload.get('min_net_roe_target_grid')}",
        f"anti_fantasy_fill_gate_required: {payload.get('anti_fantasy_fill_gate_required')}",
    ]
    for warning in payload.get("danger_warnings") or []:
        lines.append(str(warning))
    return "\n".join(lines)


def _danger_warnings(leverage_grid: Sequence[int]) -> list[str]:
    warnings = ["Cross margin forbidden; isolated margin only in any future preview."]
    if 150 in leverage_grid:
        warnings.append("150x EXTREME DANGER: no live permission and microscopic-only future sizing.")
    return warnings


def _selected_leverage(leverage: str) -> tuple[int, ...]:
    if leverage == "all":
        return tuple(LEVERAGE_GRID)
    try:
        value = int(leverage)
    except ValueError:
        return ()
    return (value,) if value in LEVERAGE_GRID else ()


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if any(token in str(key).lower() for token in ("secret", "token", "api_key", "signature")):
                sanitized[str(key)] = item if isinstance(item, bool) else "redacted"
            else:
                sanitized[str(key)] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the R333D Ultra Short Burst risk contract preview.")
    parser.add_argument("--log-dir", default=None)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--timeframe", choices=("all", "4m", "8m"), default="all")
    parser.add_argument("--leverage", choices=("all", "22", "44", "88", "150"), default="all")
    parser.add_argument("--include-150x", action="store_true", default=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = build_ultra_short_burst_risk_contract_preview(
        log_dir=args.log_dir,
        write=not args.no_write,
        timeframe=args.timeframe,
        leverage=args.leverage,
        include_150x=args.include_150x,
    )
    if args.text:
        print(format_ultra_short_burst_risk_contract_preview_text(payload))
    else:
        print(format_ultra_short_burst_risk_contract_preview_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
