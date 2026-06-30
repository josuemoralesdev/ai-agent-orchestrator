"""R333BCD combined Ultra Short Burst lab implementation pack."""

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
from src.app.hammer_radar.operator.strategy_lab_candidate_feed_expansion import BASELINE_LANE
from src.app.hammer_radar.operator.ultra_short_burst_backtest_adapter import (
    SAFETY,
    STRATEGY_FAMILY,
    build_ultra_short_burst_backtest_adapter,
    data_limitations,
    evidence_readiness_summary,
    no_live_mutation_summary,
)
from src.app.hammer_radar.operator.ultra_short_burst_risk_contract_preview import (
    build_ultra_short_burst_risk_contract_preview,
)
from src.app.hammer_radar.operator.ultra_short_burst_visual_terminal_panel import (
    build_ultra_short_burst_visual_terminal_panel,
)

EVENT_TYPE = "R333BCD_ULTRA_SHORT_BURST_LAB_IMPLEMENTATION_PACK"
CREATED_BY_PHASE = "R333BCD_ULTRA_SHORT_BURST_LAB_IMPLEMENTATION_PACK"
LEDGER_FILENAME = "ultra_short_burst_lab_implementation_pack.ndjson"

READY = "ULTRA_SHORT_BURST_LAB_IMPLEMENTATION_PACK_READY"
PARTIAL = "ULTRA_SHORT_BURST_LAB_IMPLEMENTATION_PACK_PARTIAL"
BLOCKED = "ULTRA_SHORT_BURST_LAB_IMPLEMENTATION_PACK_BLOCKED"


def build_ultra_short_burst_lab_implementation_pack(
    *,
    log_dir: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
    timeframe: str = "all",
    leverage: str = "all",
    compact: bool = False,
    wide: bool = False,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    backtest = build_ultra_short_burst_backtest_adapter(
        log_dir=resolved_log_dir,
        write=False,
        now=generated_at,
        timeframe=timeframe,
        leverage=leverage,
    )
    visual = build_ultra_short_burst_visual_terminal_panel(
        log_dir=resolved_log_dir,
        write=False,
        now=generated_at,
        timeframe=timeframe,
        leverage=leverage,
        compact=compact,
        wide=wide,
        backtest_adapter_packet=backtest,
    )
    risk_preview = build_ultra_short_burst_risk_contract_preview(
        log_dir=resolved_log_dir,
        write=False,
        now=generated_at,
        timeframe=timeframe,
        leverage=leverage,
        include_150x=True,
    )
    rows = [row for row in backtest.get("burst_backtest_rows") or [] if isinstance(row, Mapping)]
    blockers = _blockers(backtest, visual, risk_preview)
    status = BLOCKED if blockers else (READY if rows else PARTIAL)
    readiness = evidence_readiness_summary(rows)
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "implementation_pack_id": f"r333bcd_ultra_short_burst_lab_implementation_pack_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ultra_short_burst_lab_implementation_pack_path": str(packet_path(resolved_log_dir)),
        "implementation_pack_status": status,
        "blockers": blockers,
        "strategy_family": STRATEGY_FAMILY,
        "strategy_family_isolated": True,
        "paper_only": True,
        "burst_live_permission": False,
        "first_tiny_live_lane": BASELINE_LANE,
        "first_live_lane_change_allowed": False,
        "backtest_adapter_summary": backtest.get("backtest_adapter_summary"),
        "visual_terminal_summary": visual.get("visual_terminal_summary"),
        "risk_contract_preview_summary": risk_preview.get("risk_contract_preview_summary"),
        "burst_backtest_rows": rows,
        "visual_panel_lines": visual.get("panel_lines") or [],
        "risk_contract_preview": risk_preview,
        "data_limitations": data_limitations(),
        "sequence_unknown_summary": backtest.get("sequence_unknown_summary"),
        "evidence_readiness_summary": readiness,
        "recommended_r333e_path": recommended_r333e_path(),
        "recommended_r333f_path": recommended_r333f_path(),
        "recommended_r333g_path": recommended_r333g_path(),
        "recommended_tiny_live_path": recommended_tiny_live_path(),
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


def load_ultra_short_burst_lab_implementation_pack_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(packet_path(get_log_dir(log_dir, use_env=True)), limit=limit, max_bytes=10_000_000)


def packet_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_ultra_short_burst_lab_implementation_pack_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_ultra_short_burst_lab_implementation_pack_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R333BCD ULTRA SHORT BURST LAB IMPLEMENTATION PACK",
        "PAPER ONLY / LIVE PERMISSION FALSE",
        f"implementation_pack_status: {payload.get('implementation_pack_status')}",
        f"strategy_family: {payload.get('strategy_family')}",
        f"strategy_family_isolated: {payload.get('strategy_family_isolated')}",
        f"first_tiny_live_lane: {payload.get('first_tiny_live_lane')}",
        f"first_live_lane_change_allowed: {payload.get('first_live_lane_change_allowed')}",
        "",
        "BACKTEST SUMMARY",
    ]
    for key, value in (payload.get("backtest_adapter_summary") or {}).items():
        lines.append(f"{key}: {value}")
    lines.extend(["", "VISUAL PANEL PREVIEW"])
    lines.extend(str(line) for line in (payload.get("visual_panel_lines") or [])[:16])
    lines.extend(["", "RISK CONTRACT PREVIEW SUMMARY"])
    for key, value in (payload.get("risk_contract_preview_summary") or {}).items():
        lines.append(f"{key}: {value}")
    lines.extend(["", "SEQUENCE UNKNOWN SUMMARY"])
    for key, value in (payload.get("sequence_unknown_summary") or {}).items():
        lines.append(f"{key}: {value}")
    lines.extend(["", "EVIDENCE READINESS SUMMARY"])
    for key, value in (payload.get("evidence_readiness_summary") or {}).items():
        lines.append(f"{key}: {value}")
    lines.extend(["", "RECOMMENDED R333E/R333F"])
    lines.append(str(payload.get("recommended_r333e_path")))
    lines.append(str(payload.get("recommended_r333f_path")))
    lines.extend(["", "SAFETY FLAGS"])
    for key in SAFETY:
        lines.append(f"{key}: {(payload.get('safety') or {}).get(key)}")
    return "\n".join(lines)


def recommended_r333e_path() -> dict[str, Any]:
    return {
        "phase": "R333E Burst Lab Evidence Audit And Anti-Fantasy Fill Gate",
        "must_audit": [
            "sequence_known",
            "fees",
            "slippage",
            "latency",
            "liquidation_proximity",
            "sample_count",
        ],
        "purpose": "reject candle-only fantasy fills and gross-only readiness",
    }


def recommended_r333f_path() -> dict[str, Any]:
    return {
        "phase": "R333F Tiny Burst Live Activation Gate",
        "future_only": True,
        "requires_r333e_pass": True,
        "must_not_be_implemented_now": True,
    }


def recommended_r333g_path() -> dict[str, Any]:
    return {
        "phase": "R333G Ultra-Short Burst Terminal Operator Console Refinement",
        "purpose": "future terminal refinement after R333E audit findings",
    }


def recommended_tiny_live_path() -> list[str]:
    return [
        f"First Tiny Live remains {BASELINE_LANE}.",
        "Tiny Live remains separately gated.",
        "R333F is future-only and requires R333E plus a separate human-reviewed burst risk contract.",
    ]


def _blockers(*packets: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for packet in packets:
        blockers.extend(str(item) for item in packet.get("blockers") or [])
    return list(dict.fromkeys(blockers))


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
    parser = argparse.ArgumentParser(description="Build the R333BCD Ultra Short Burst lab implementation pack.")
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
    payload = build_ultra_short_burst_lab_implementation_pack(
        log_dir=args.log_dir,
        write=not args.no_write,
        timeframe=args.timeframe,
        leverage=args.leverage,
        compact=args.compact,
        wide=args.wide,
    )
    if args.text:
        print(format_ultra_short_burst_lab_implementation_pack_text(payload))
    else:
        print(format_ultra_short_burst_lab_implementation_pack_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
