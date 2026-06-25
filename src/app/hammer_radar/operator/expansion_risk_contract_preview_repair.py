"""R307 read-only expansion risk-contract preview repair.

This module resolves exact lane risk contracts for the R306 expansion preview
and emits missing-contract templates for operator review only. It never writes
configuration, mutates arming state, calls Binance, changes leverage/margin, or
creates submit/final commands.
"""

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
from src.app.hammer_radar.operator.strategy_lab_preview import CURRENT_TINY_LIVE_LANE
from src.app.hammer_radar.operator.tiny_live_risk_contract_validation import (
    DEFAULT_RISK_CONTRACT_CONFIG_PATH,
    EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE,
    build_tiny_live_risk_contract_validation_summary,
)

EVENT_TYPE = "R307_EXPANSION_RISK_CONTRACT_PREVIEW_REPAIR"
CREATED_BY_PHASE = "R307_EXPANSION_RISK_CONTRACT_PREVIEW_REPAIR"
LEDGER_FILENAME = "expansion_risk_contract_preview_repair.ndjson"

CURRENT_FIRST_TINY_LIVE_BASELINE = "CURRENT_FIRST_TINY_LIVE_BASELINE"
PRIMARY_DRY_RUN_EXPANSION_CANDIDATE = "PRIMARY_DRY_RUN_EXPANSION_CANDIDATE"
SECONDARY_WATCH_ONLY_CANDIDATE = "SECONDARY_WATCH_ONLY_CANDIDATE"

NOT_NEEDED_CONTRACT_FOUND = "NOT_NEEDED_CONTRACT_FOUND"
PREVIEW_TEMPLATE_AVAILABLE_NOT_WRITTEN = "PREVIEW_TEMPLATE_AVAILABLE_NOT_WRITTEN"
BLOCKED_UNSUPPORTED_LANE = "BLOCKED_UNSUPPORTED_LANE"

PRIMARY_DRY_RUN_EXPANSION_LANES = (
    "BTCUSDT|44m|short|ladder_382_50_618",
    "BTCUSDT|44m|short|ladder_close_50_618",
    "BTCUSDT|55m|long|ladder_close_50_618",
)
SECONDARY_WATCH_ONLY_LANES = (
    "BTCUSDT|44m|short|ladder_22_44_22",
    "BTCUSDT|44m|long|ladder_382_50_618",
    "BTCUSDT|55m|long|market_close",
    "BTCUSDT|88m|long|ladder_382_50_618",
)

SAFETY = {
    "live_execution_enabled": False,
    "allow_live_orders": False,
    "global_kill_switch": True,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "submit_allowed": False,
    "final_command_available": False,
    "real_order_forbidden": True,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "leverage_change_called": False,
    "margin_change_called": False,
    "secrets_shown": False,
    "paper_live_separation_intact": True,
    "autonomous_arming_state_changed": False,
    "risk_contract_config_mutated": False,
    "global_live_flags_changed": False,
    "config_written": False,
    "env_written": False,
    "env_mutated": False,
}


def build_expansion_risk_contract_preview_repair(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    lanes = build_r307_lane_specs()
    lane_packets = [
        build_expansion_risk_contract_lane_preview(
            lane_key=lane_key,
            lane_role=lane_role,
            risk_contract_config_path=risk_contract_config_path,
        )
        for lane_key, lane_role in lanes
    ]
    missing = [row for row in lane_packets if row["exact_contract_found"] is not True]
    valid = [row for row in lane_packets if row["risk_contract_valid"] is True]
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "preview_id": f"r307_expansion_risk_contract_preview_repair_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "expansion_risk_contract_preview_repair_path": str(preview_path(resolved_log_dir)),
        "current_first_tiny_live_lane": CURRENT_TINY_LIVE_LANE,
        "current_first_tiny_live_lane_unchanged": True,
        "lane_packets": lane_packets,
        "baseline_contract_status": _lane_status(lane_packets, CURRENT_TINY_LIVE_LANE),
        "primary_candidate_contract_statuses": [
            _lane_status(lane_packets, lane_key) for lane_key in PRIMARY_DRY_RUN_EXPANSION_LANES
        ],
        "secondary_watch_only_contract_statuses": [
            _lane_status(lane_packets, lane_key) for lane_key in SECONDARY_WATCH_ONLY_LANES
        ],
        "missing_preview_templates_summary": {
            "missing_contract_count": len(missing),
            "valid_contract_count": len(valid),
            "missing_lane_keys": [row["lane_key"] for row in missing],
            "template_status": PREVIEW_TEMPLATE_AVAILABLE_NOT_WRITTEN if missing else NOT_NEEDED_CONTRACT_FOUND,
            "risk_contract_config_mutated": False,
            "config_written": False,
        },
        "recommended_r306_next_operator_move_after_repair": (
            "R306_PREVIEW_CAN_DISTINGUISH_MISSING_CONTRACTS_FROM_INVALID_MATCHES"
        ),
        "recommended_r308_path": (
            "R308 Expansion Risk Contract Write-Gate Preview"
            if missing
            else "R308 Multi-Lane Dry-Run Observation Scheduler"
        ),
        "source_surfaces_used": [
            "configs/hammer_radar/tiny_live_risk_contracts.json",
            "configs/hammer_radar/autonomous_arming_state.json",
            "src/app/hammer_radar/operator/tiny_live_risk_contract_validation.py",
            "src/app/hammer_radar/operator/eligible_lane_expansion_dry_run_preview.py",
        ],
        "safety": dict(SAFETY),
        **dict(SAFETY),
    }
    safe_payload = _sanitize(payload)
    if write:
        append_preview(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def build_expansion_risk_contract_lane_preview(
    *,
    lane_key: str,
    lane_role: str,
    risk_contract_config_path: str | Path | None = None,
) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = lane_parts(lane_key)
    normalized_lane_key = build_lane_key(symbol=symbol, timeframe=timeframe, direction=direction, entry_mode=entry_mode)
    path = Path(risk_contract_config_path) if risk_contract_config_path is not None else DEFAULT_RISK_CONTRACT_CONFIG_PATH
    raw = _load_config(path)
    contracts = raw.get("risk_contracts") if isinstance(raw.get("risk_contracts"), list) else []
    lookup_attempts: list[dict[str, Any]] = []
    matched_contract: dict[str, Any] = {}
    matched_key = None
    for row in contracts:
        if not isinstance(row, Mapping):
            continue
        candidates = _contract_lookup_keys(row)
        matched = normalized_lane_key in candidates
        lookup_attempts.append(
            {
                "contract_key": _best_contract_key(row),
                "candidate_keys": candidates,
                "matched": matched,
            }
        )
        if matched and not matched_contract:
            matched_contract = dict(row)
            matched_key = normalized_lane_key
    exact_contract_found = bool(matched_contract)
    validation_summary = (
        build_tiny_live_risk_contract_validation_summary(risk_contract=matched_contract)
        if exact_contract_found
        else _missing_validation_summary()
    )
    blocked_by: list[str] = []
    if not _supported_lane(symbol=symbol, timeframe=timeframe, direction=direction, entry_mode=entry_mode):
        blocked_by.append("unsupported_lane_for_r307_preview")
    if not exact_contract_found:
        blocked_by.append("exact_lane_risk_contract_missing")
    if exact_contract_found and validation_summary.get("risk_contract_valid") is not True:
        blocked_by.extend(str(item) for item in validation_summary.get("blocked_by") or [])
    if matched_contract.get("live_execution_enabled") is True:
        blocked_by.append("risk_contract_live_execution_enabled_not_false")
    if matched_contract.get("live_authorized") not in {False, None}:
        blocked_by.append("risk_contract_live_authorized_not_false")
    template = {} if exact_contract_found else _safe_preview_template(lane_key=normalized_lane_key)
    if template and template.get("max_loss_usdt") is None:
        blocked_by.append("risk_contract_max_loss_requires_operator_review")
    template_status = (
        NOT_NEEDED_CONTRACT_FOUND
        if exact_contract_found
        else PREVIEW_TEMPLATE_AVAILABLE_NOT_WRITTEN
        if _supported_lane(symbol=symbol, timeframe=timeframe, direction=direction, entry_mode=entry_mode)
        else BLOCKED_UNSUPPORTED_LANE
    )
    payload = {
        "lane_key": lane_key,
        "lane_role": lane_role,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "exact_contract_found": exact_contract_found,
        "risk_contract_valid": exact_contract_found and validation_summary.get("risk_contract_valid") is True and not blocked_by,
        "risk_contract_source_path": str(path),
        "matched_contract_key": matched_key,
        "matched_contract_schema_version": matched_contract.get("schema_version")
        or matched_contract.get("contract_version")
        or matched_contract.get("tiny_live_contract_mode"),
        "normalized_lane_key": normalized_lane_key,
        "lookup_attempts": lookup_attempts,
        "lookup_failure_reason": None if exact_contract_found else "no_contract_key_matched_normalized_lane_key",
        "validation_summary": validation_summary,
        "blocked_by": _dedupe(blocked_by),
        "safe_preview_template_if_missing": template,
        "safe_preview_template_status": template_status,
        "write_required_for_future": not exact_contract_found,
        "future_write_gate_required": not exact_contract_found,
        "contract_values": _contract_values(matched_contract),
        **dict(SAFETY),
    }
    return _sanitize(payload)


def build_r307_lane_specs() -> list[tuple[str, str]]:
    return [
        (CURRENT_TINY_LIVE_LANE, CURRENT_FIRST_TINY_LIVE_BASELINE),
        *((lane, PRIMARY_DRY_RUN_EXPANSION_CANDIDATE) for lane in PRIMARY_DRY_RUN_EXPANSION_LANES),
        *((lane, SECONDARY_WATCH_ONLY_CANDIDATE) for lane in SECONDARY_WATCH_ONLY_LANES),
    ]


def append_preview(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = preview_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_expansion_risk_contract_preview_repair_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(preview_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def preview_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_preview_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_preview_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R307 EXPANSION RISK CONTRACT PREVIEW REPAIR",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        "",
        "BASELINE LANE CONTRACT STATUS",
    ]
    for row in payload.get("lane_packets") or []:
        if isinstance(row, Mapping) and row.get("lane_role") == CURRENT_FIRST_TINY_LIVE_BASELINE:
            lines.append(_format_lane_line(row))
    lines.extend(["", "PRIMARY DRY-RUN CANDIDATE CONTRACT STATUS"])
    for row in payload.get("lane_packets") or []:
        if isinstance(row, Mapping) and row.get("lane_role") == PRIMARY_DRY_RUN_EXPANSION_CANDIDATE:
            lines.append(_format_lane_line(row))
    lines.extend(["", "SECONDARY WATCH-ONLY CONTRACT STATUS"])
    for row in payload.get("lane_packets") or []:
        if isinstance(row, Mapping) and row.get("lane_role") == SECONDARY_WATCH_ONLY_CANDIDATE:
            lines.append(_format_lane_line(row))
    summary = payload.get("missing_preview_templates_summary") if isinstance(payload.get("missing_preview_templates_summary"), Mapping) else {}
    lines.extend(
        [
            "",
            "MISSING PREVIEW TEMPLATES SUMMARY",
            f"missing_contract_count: {summary.get('missing_contract_count')}",
            f"missing_lane_keys: {', '.join(summary.get('missing_lane_keys') or []) or 'none'}",
            f"template_status: {summary.get('template_status')}",
            "",
            "R306 RECOMMENDED NEXT OPERATOR MOVE AFTER REPAIR",
            str(payload.get("recommended_r306_next_operator_move_after_repair")),
            "",
            "SAFETY FLAGS",
        ]
    )
    for key in SAFETY:
        lines.append(f"{key}: {payload.get(key)}")
    lines.extend(["", "RECOMMENDED R308 PATH", str(payload.get("recommended_r308_path"))])
    return "\n".join(lines)


def lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = [*str(lane_key or "").split("|"), "", "", "", ""]
    return parts[0], parts[1], parts[2], parts[3] or "ladder_close_50_618"


def build_lane_key(*, symbol: object, timeframe: object, direction: object, entry_mode: object) -> str:
    return "|".join(str(item or "") for item in (symbol, timeframe, direction, entry_mode))


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"risk_contracts": [], "funding_config": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"risk_contracts": [], "funding_config": {}}


def _contract_lookup_keys(row: Mapping[str, Any]) -> list[str]:
    keys = []
    for key in ("official_lane_key", "lane_key"):
        value = str(row.get(key) or "")
        if value:
            keys.append(value)
    derived = build_lane_key(
        symbol=row.get("symbol"),
        timeframe=row.get("timeframe"),
        direction=row.get("direction"),
        entry_mode=row.get("entry_mode"),
    )
    if derived.strip("|"):
        keys.append(derived)
    return _dedupe(keys)


def _best_contract_key(row: Mapping[str, Any]) -> str | None:
    for key in ("official_lane_key", "lane_key", "candidate_id", "contract_id"):
        if row.get(key):
            return str(row[key])
    keys = _contract_lookup_keys(row)
    return keys[0] if keys else None


def _missing_validation_summary() -> dict[str, Any]:
    return {
        "valid": False,
        "risk_contract_valid": False,
        "blocked_by": ["exact_lane_risk_contract_missing"],
    }


def _safe_preview_template(*, lane_key: str) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = lane_parts(lane_key)
    return {
        "official_lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "tiny_live_contract_mode": EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE,
        "leverage": 10,
        "margin_mode": "isolated",
        "max_position_notional_usdt": 80,
        "max_notional_usdt": 80,
        "margin_budget_usdt": 8,
        "max_loss_usdt": None,
        "max_trades_per_day": 1,
        "daily_loss_stop_usdt": 5,
        "protective_orders_required": True,
        "live_execution_enabled": False,
        "live_authorized": False,
        "approval_status": "PREVIEW_TEMPLATE_AVAILABLE_NOT_WRITTEN",
        "operator_review_required": True,
        "risk_contract_config_mutated": False,
        "config_written": False,
        "notes": [
            "R307 preview template only; not written to config.",
            "max_loss_usdt requires operator review before any future write gate.",
        ],
    }


def _contract_values(contract: Mapping[str, Any]) -> dict[str, Any]:
    if not contract:
        return {}
    return {
        "symbol": contract.get("symbol"),
        "timeframe": contract.get("timeframe"),
        "direction": contract.get("direction"),
        "entry_mode": contract.get("entry_mode"),
        "leverage": contract.get("leverage"),
        "margin_mode": contract.get("margin_mode"),
        "max_position_notional_usdt": contract.get("max_position_notional_usdt") or contract.get("max_notional_usdt"),
        "margin_budget_usdt": contract.get("margin_budget_usdt")
        or contract.get("tiny_live_margin_usdt")
        or contract.get("max_margin_usdt"),
        "max_loss_usdt": contract.get("max_loss_usdt"),
        "max_trades_per_day": contract.get("max_trades_per_day"),
        "daily_loss_stop_usdt": contract.get("daily_loss_stop_usdt"),
        "protective_orders_required": contract.get("protective_orders_required")
        if "protective_orders_required" in contract
        else contract.get("protective_stop_required") is True and contract.get("take_profit_required") is True,
    }


def _supported_lane(*, symbol: str, timeframe: str, direction: str, entry_mode: str) -> bool:
    return bool(symbol == "BTCUSDT" and timeframe and direction in {"long", "short"} and entry_mode)


def _lane_status(lane_packets: Sequence[Mapping[str, Any]], lane_key: str) -> dict[str, Any]:
    for row in lane_packets:
        if row.get("lane_key") == lane_key:
            return {
                "lane_key": row.get("lane_key"),
                "exact_contract_found": row.get("exact_contract_found"),
                "risk_contract_valid": row.get("risk_contract_valid"),
                "safe_preview_template_status": row.get("safe_preview_template_status"),
                "blocked_by": list(row.get("blocked_by") or []),
            }
    return {"lane_key": lane_key, "exact_contract_found": False, "risk_contract_valid": False}


def _format_lane_line(row: Mapping[str, Any]) -> str:
    return (
        f"{row.get('lane_key')} | exact_contract_found={row.get('exact_contract_found')} "
        f"risk_contract_valid={row.get('risk_contract_valid')} "
        f"template_status={row.get('safe_preview_template_status')} "
        f"blocked_by={','.join(row.get('blocked_by') or []) or 'none'}"
    )


def _dedupe(items: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key, value in SAFETY.items():
            if key in sanitized:
                sanitized[key] = value
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload


def _main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.app.hammer_radar.operator.expansion_risk_contract_preview_repair"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--risk-contract-config-path", default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args()
    payload = build_expansion_risk_contract_preview_repair(
        log_dir=args.log_dir,
        risk_contract_config_path=args.risk_contract_config_path,
        write=not args.no_write,
    )
    print(format_preview_text(payload) if args.text else format_preview_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
