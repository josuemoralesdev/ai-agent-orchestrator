"""R333C terminal-only Ultra Short Burst visual panel."""

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
    build_ultra_short_burst_backtest_adapter,
)

EVENT_TYPE = "R333C_ULTRA_SHORT_BURST_VISUAL_TERMINAL_PANEL"
CREATED_BY_PHASE = "R333C_ULTRA_SHORT_BURST_VISUAL_TERMINAL_PANEL"
LEDGER_FILENAME = "ultra_short_burst_visual_terminal_panel.ndjson"

READY = "ULTRA_SHORT_BURST_VISUAL_PANEL_READY"
PARTIAL = "ULTRA_SHORT_BURST_VISUAL_PANEL_PARTIAL"


def build_ultra_short_burst_visual_terminal_panel(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    timeframe: str = "all",
    leverage: str = "all",
    compact: bool = False,
    wide: bool = False,
    backtest_adapter_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    backtest = (
        dict(backtest_adapter_packet)
        if isinstance(backtest_adapter_packet, Mapping)
        else build_ultra_short_burst_backtest_adapter(
            log_dir=resolved_log_dir,
            write=False,
            now=generated_at,
            timeframe=timeframe,
            leverage=leverage,
        )
    )
    rows = [row for row in backtest.get("burst_backtest_rows") or [] if isinstance(row, Mapping)]
    panel_lines = _panel_lines(rows, compact=compact, wide=wide)
    warning_blocks = _warning_blocks(rows)
    verdict_blocks = _verdict_blocks(rows)
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "visual_terminal_panel_id": f"r333c_ultra_short_burst_visual_terminal_panel_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ultra_short_burst_visual_terminal_panel_path": str(packet_path(resolved_log_dir)),
        "visual_panel_status": READY if rows else PARTIAL,
        "blockers": [] if rows else ["no_backtest_rows_available"],
        "strategy_family": STRATEGY_FAMILY,
        "strategy_family_isolated": True,
        "paper_only": True,
        "panel_lines": panel_lines,
        "leverage_ladder": [f"{value}x" for value in _selected_leverage(leverage)],
        "checkpoint_timeline": [f"{value}s" for value in CHECKPOINT_GRID_SECONDS],
        "warning_blocks": warning_blocks,
        "verdict_blocks": verdict_blocks,
        "reason_codes": _reason_codes(rows),
        "visual_terminal_summary": {
            "panel_line_count": len(panel_lines),
            "warning_block_count": len(warning_blocks),
            "terminal_only": True,
            "hosted_ui": False,
            "live_permission": False,
        },
        "live_permission": False,
        "burst_live_permission": False,
        "terminal_only": True,
        "hosted_ui": False,
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


def load_ultra_short_burst_visual_terminal_panel_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(packet_path(get_log_dir(log_dir, use_env=True)), limit=limit, max_bytes=4_000_000)


def packet_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_ultra_short_burst_visual_terminal_panel_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_ultra_short_burst_visual_terminal_panel_text(payload: Mapping[str, Any]) -> str:
    return "\n".join(str(line) for line in payload.get("panel_lines") or [])


def _panel_lines(rows: Sequence[Mapping[str, Any]], *, compact: bool, wide: bool) -> list[str]:
    ready = sum(1 for row in rows if row.get("result_status") == "REPLAY_READY")
    sequence_unknown = sum(1 for row in rows if row.get("sequence_known") is False)
    statuses = sorted({str(row.get("result_status")) for row in rows if row.get("result_status")})
    lines = [
        "R333C ULTRA SHORT BURST VISUAL TERMINAL PANEL",
        "PAPER ONLY / LIVE PERMISSION FALSE",
        f"Strategy family: {STRATEGY_FAMILY} isolated=true",
        f"Leverage ladder: {' / '.join(f'{value}x' for value in LEVERAGE_GRID)}",
        f"Checkpoint timeline: {' | '.join(f'{value}s' for value in CHECKPOINT_GRID_SECONDS)}",
        "Fee drag warning: fee_drag_roe = fee_pct_round_trip * leverage; net ROE required.",
        "Liquidation proximity warning: 150x EXTREME DANGER; isolated-only future preview; no live permission.",
        "Sequence warning: sequence_unknown candle-only rows cannot promote to live.",
        f"Rows: total={len(rows)} replay_ready={ready} sequence_unknown={sequence_unknown}",
        f"Statuses: {', '.join(statuses) if statuses else 'none'}",
        "Verdict: PAPER_LAB_DIAGNOSTIC_ONLY_R333E_REQUIRED",
        "Reason codes: LIVE_PERMISSION_FALSE, SEQUENCE_UNKNOWN_BLOCKS_LIVE, GROSS_ONLY_FORBIDDEN",
    ]
    if not compact:
        lines.extend(
            [
                "Risk: no hosted UI, no web app, no submit, no final command.",
                "Next: R333E must audit sequence_known, fees, slippage, latency, liquidation proximity, and sample count.",
            ]
        )
    if wide:
        lines.append("Wide view: columns=tf side leverage checkpoint result sequence_known net_roe_formula")
        for row in rows[:12]:
            lines.append(
                f"{row.get('timeframe')} {row.get('side')} {row.get('leverage')}x "
                f"{row.get('checkpoint_seconds')}s {row.get('result_status')} "
                f"sequence_known={row.get('sequence_known')} net={row.get('net_roe_formula')}"
            )
    return lines


def _warning_blocks(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"code": "PAPER_ONLY_LIVE_FALSE", "message": "Paper-only diagnostic; live permission is false."},
        {"code": "FEE_DRAG_REQUIRED", "message": "Gross-only success classification is forbidden."},
        {"code": "LIQUIDATION_150X", "message": "150x requires explicit liquidation danger-zone modeling."},
        {
            "code": "SEQUENCE_UNKNOWN",
            "message": f"{sum(1 for row in rows if row.get('sequence_known') is False)} rows lack intrabar sequence proof.",
        },
    ]


def _verdict_blocks(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "verdict": "NOT_LIVE_READY",
            "reason": "R333E anti-fantasy fill gate and sequence-known evidence are required.",
            "rows_seen": len(rows),
            "live_permission": False,
        }
    ]


def _reason_codes(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    codes = ["LIVE_PERMISSION_FALSE", "R333E_REQUIRED", "GROSS_ONLY_FORBIDDEN"]
    if any(row.get("sequence_known") is False for row in rows):
        codes.append("SEQUENCE_UNKNOWN_BLOCKS_LIVE")
    if any(row.get("leverage") == 150 for row in rows):
        codes.append("LIQUIDATION_150X_EXTREME_DANGER")
    return codes


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
    parser = argparse.ArgumentParser(description="Build the R333C Ultra Short Burst terminal-only visual panel.")
    parser.add_argument("--log-dir", default=None)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--text", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--timeframe", choices=("all", "4m", "8m"), default="all")
    parser.add_argument("--leverage", choices=("all", "22", "44", "88", "150"), default="all")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--wide", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = build_ultra_short_burst_visual_terminal_panel(
        log_dir=args.log_dir,
        write=not args.no_write,
        timeframe=args.timeframe,
        leverage=args.leverage,
        compact=args.compact,
        wide=args.wide,
    )
    if args.text:
        print(format_ultra_short_burst_visual_terminal_panel_text(payload))
    else:
        print(format_ultra_short_burst_visual_terminal_panel_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
