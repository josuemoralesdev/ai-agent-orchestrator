"""R308 expansion risk-contract write-gate preview.

This module prepares preview-only proposed risk-contract rows for the R306/R307
expansion lanes. It never writes config, mutates arming state, enables live
execution, creates submit/final commands, changes leverage/margin, or calls
Binance order/test-order endpoints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.expansion_risk_contract_preview_repair import (
    PRIMARY_DRY_RUN_EXPANSION_LANES,
    SECONDARY_WATCH_ONLY_LANES,
    build_lane_key,
    lane_parts,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.strategy_lab_preview import CURRENT_TINY_LIVE_LANE
from src.app.hammer_radar.operator.tiny_live_risk_contract_validation import (
    DEFAULT_MAX_LOSS_USDT,
    DEFAULT_RISK_CONTRACT_CONFIG_PATH,
    EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE,
    build_tiny_live_risk_contract_validation_summary,
)

EVENT_TYPE = "R308_EXPANSION_RISK_CONTRACT_WRITE_GATE_PREVIEW"
CREATED_BY_PHASE = "R308_EXPANSION_RISK_CONTRACT_WRITE_GATE_PREVIEW"
LEDGER_FILENAME = "expansion_risk_contract_write_gate_preview.ndjson"

REQUIRED_BASELINE = "REQUIRED_BASELINE"
PRIMARY_DRY_RUN_EXPANSION = "PRIMARY_DRY_RUN_EXPANSION"
SECONDARY_WATCH_ONLY = "SECONDARY_WATCH_ONLY"

WRITE_GATE_PREVIEW_READY = "WRITE_GATE_PREVIEW_READY"
WRITE_GATE_PREVIEW_BLOCKED_OPERATOR_REVIEW_REQUIRED = (
    "WRITE_GATE_PREVIEW_BLOCKED_OPERATOR_REVIEW_REQUIRED"
)
FUTURE_CONFIRMATION_PHRASE_PREVIEW = "WRITE RISK CONTRACTS FOR R308 REVIEWED LANES"

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
    "write_gate_preview_only": True,
}


def build_expansion_risk_contract_write_gate_preview(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    write: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    config_path = (
        Path(risk_contract_config_path)
        if risk_contract_config_path is not None
        else DEFAULT_RISK_CONTRACT_CONFIG_PATH
    )
    existing_config = _load_config(config_path)
    existing_keys = _existing_contract_keys(existing_config)
    max_loss = _derive_max_loss(existing_config)
    proposed_rows = [
        build_proposed_contract_row(
            lane_key=lane_key,
            lane_role=lane_role,
            existing_keys=existing_keys,
            max_loss_derivation=max_loss,
        )
        for lane_key, lane_role in build_r308_lane_specs()
    ]
    rows_to_add = [row for row in proposed_rows if row["official_lane_key"] not in existing_keys]
    missing_review_fields = _missing_operator_review_fields(proposed_rows)
    diff_preview = build_diff_preview(
        config_path=config_path,
        existing_config=existing_config,
        proposed_rows=proposed_rows,
    )
    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "preview_id": f"r308_expansion_risk_contract_write_gate_preview_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "expansion_risk_contract_write_gate_preview_path": str(preview_path(resolved_log_dir)),
        "current_first_tiny_live_lane": CURRENT_TINY_LIVE_LANE,
        "current_first_tiny_live_lane_unchanged": True,
        "proposed_contract_rows": proposed_rows,
        "proposed_contract_count": len(proposed_rows),
        "proposed_new_contract_count": len(rows_to_add),
        "baseline_proposed_contract_status": _role_status(proposed_rows, REQUIRED_BASELINE),
        "primary_expansion_proposed_contract_statuses": _role_statuses(
            proposed_rows,
            PRIMARY_DRY_RUN_EXPANSION,
        ),
        "secondary_watch_only_proposed_contract_statuses": _role_statuses(
            proposed_rows,
            SECONDARY_WATCH_ONLY,
        ),
        "max_loss_derivation": max_loss,
        "missing_operator_review_fields": missing_review_fields,
        "diff_preview": diff_preview,
        "future_confirmation_phrase_preview": FUTURE_CONFIRMATION_PHRASE_PREVIEW,
        "future_confirmation_phrase_active": False,
        "future_confirmation_phrase_executable": False,
        "recommended_r309_path": _recommended_r309_path(proposed_rows),
        "source_surfaces_used": [
            "configs/hammer_radar/tiny_live_risk_contracts.json",
            "configs/hammer_radar/autonomous_arming_state.json",
            "src/app/hammer_radar/operator/expansion_risk_contract_preview_repair.py",
            "src/app/hammer_radar/operator/tiny_live_risk_contract_validation.py",
            "src/app/hammer_radar/operator/tiny_live_risk_contract_config_write_gate.py",
            "src/app/hammer_radar/operator/inspect.py",
        ],
        "why_r308_does_not_write_config": (
            "R308 is a write-gate preview packet only. It has no write flag, no active "
            "confirmation phrase, and no apply function for risk-contract config mutation."
        ),
        "safety": dict(SAFETY),
        **dict(SAFETY),
    }
    safe_payload = _sanitize(payload)
    if write:
        append_preview(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def build_proposed_contract_row(
    *,
    lane_key: str,
    lane_role: str,
    existing_keys: Sequence[str],
    max_loss_derivation: Mapping[str, Any],
) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = lane_parts(lane_key)
    official_lane_key = build_lane_key(
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        entry_mode=entry_mode,
    )
    contract = build_proposed_contract(
        official_lane_key=official_lane_key,
        max_loss_derivation=max_loss_derivation,
    )
    validation_preview = build_tiny_live_risk_contract_validation_summary(risk_contract=contract)
    missing_fields = _missing_required_fields(contract)
    blocked_by = list(validation_preview.get("blocked_by") or [])
    if contract.get("max_loss_usdt") is None:
        blocked_by.append("risk_contract_max_loss_requires_operator_review")
    if official_lane_key in existing_keys:
        blocked_by.append("exact_lane_risk_contract_already_exists_no_new_row_needed")
    blocked_by = _dedupe(blocked_by)
    operator_review_required = bool(missing_fields or contract.get("max_loss_usdt") is None)
    status = (
        WRITE_GATE_PREVIEW_BLOCKED_OPERATOR_REVIEW_REQUIRED
        if operator_review_required or contract.get("max_loss_usdt") is None
        else WRITE_GATE_PREVIEW_READY
    )
    return _sanitize(
        {
            "proposed_contract_key": official_lane_key,
            "official_lane_key": official_lane_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": entry_mode,
            "lane_role": lane_role,
            "proposed_contract": contract,
            "validation_preview": validation_preview,
            "missing_fields_after_preview": missing_fields,
            "operator_review_required": operator_review_required,
            "human_write_gate_review_required": True,
            "write_gate_status": status,
            "blocked_by": blocked_by,
            "future_confirmation_phrase_preview": FUTURE_CONFIRMATION_PHRASE_PREVIEW,
            "future_confirmation_phrase_active": False,
            "future_confirmation_phrase_executable": False,
            "config_written": False,
            **dict(SAFETY),
        }
    )


def build_proposed_contract(
    *,
    official_lane_key: str,
    max_loss_derivation: Mapping[str, Any],
) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = lane_parts(official_lane_key)
    max_loss = max_loss_derivation.get("max_loss_usdt") if max_loss_derivation.get("derived") is True else None
    requires_review = max_loss is None
    return _sanitize(
        {
            "official_lane_key": official_lane_key,
            "contract_version": "r308_expansion_risk_contract_preview_v1",
            "created_by_phase": CREATED_BY_PHASE,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": entry_mode,
            "tiny_live_contract_mode": EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE,
            "margin_mode": "isolated",
            "leverage": 10,
            "max_position_notional_usdt": 80,
            "max_notional_usdt": 80,
            "margin_budget_usdt": 8,
            "max_margin_usdt": 8,
            "tiny_live_margin_usdt": 8,
            "max_loss_usdt": max_loss,
            "max_loss_derivation_source": max_loss_derivation.get("source"),
            "requires_operator_review": requires_review,
            "max_trades_per_day": 1,
            "daily_loss_stop_usdt": 5,
            "protective_orders_required": True,
            "protective_stop_required": True,
            "take_profit_required": True,
            "enabled_for_preflight": False,
            "approval_status": "R308_PREVIEW_ONLY_NOT_WRITTEN",
            "live_authorized": False,
            "live_execution_enabled": False,
            "allow_live_orders": False,
            "order_payload_forbidden_until_future_live_gate": True,
            "binance_call_forbidden_until_future_live_gate": True,
            "operator_final_approval_required": True,
            "notes": [
                "R308 preview row only; not written to config.",
                "Future R309 write gate must require explicit human confirmation before any config mutation.",
            ],
            "risk_contract_config_mutated": False,
            "config_written": False,
        }
    )


def build_diff_preview(
    *,
    config_path: Path,
    existing_config: Mapping[str, Any],
    proposed_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    existing_keys = _existing_contract_keys(existing_config)
    proposed_keys = [str(row.get("official_lane_key") or "") for row in proposed_rows if row.get("official_lane_key")]
    would_add = [key for key in proposed_keys if key not in existing_keys]
    return _sanitize(
        {
            "existing_contract_count": len(_risk_contracts(existing_config)),
            "proposed_new_contract_count": len(would_add),
            "would_add_lane_keys": would_add,
            "would_not_modify_existing_keys": existing_keys,
            "would_not_delete_keys": existing_keys,
            "config_path": str(config_path),
            "config_sha256_before": _sha256_file(config_path),
            "config_written": False,
            "risk_contract_config_mutated": False,
        }
    )


def build_r308_lane_specs() -> list[tuple[str, str]]:
    return [
        (CURRENT_TINY_LIVE_LANE, REQUIRED_BASELINE),
        *((lane, PRIMARY_DRY_RUN_EXPANSION) for lane in PRIMARY_DRY_RUN_EXPANSION_LANES),
        *((lane, SECONDARY_WATCH_ONLY) for lane in SECONDARY_WATCH_ONLY_LANES),
    ]


def append_preview(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = preview_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_expansion_risk_contract_write_gate_preview_records(
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
    diff = payload.get("diff_preview") if isinstance(payload.get("diff_preview"), Mapping) else {}
    max_loss = payload.get("max_loss_derivation") if isinstance(payload.get("max_loss_derivation"), Mapping) else {}
    lines = [
        "R308 EXPANSION RISK CONTRACT WRITE-GATE PREVIEW",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        "",
        "CURRENT CONFIG PATH",
        f"config_path: {diff.get('config_path')}",
        f"config_sha256_before: {diff.get('config_sha256_before')}",
        "",
        "PROPOSED CONTRACT COUNT",
        f"proposed_contract_count: {payload.get('proposed_contract_count')}",
        f"proposed_new_contract_count: {payload.get('proposed_new_contract_count')}",
        "",
        "BASELINE PROPOSED CONTRACT STATUS",
    ]
    lines.extend(_format_rows(payload, REQUIRED_BASELINE))
    lines.extend(["", "PRIMARY EXPANSION PROPOSED CONTRACT STATUSES"])
    lines.extend(_format_rows(payload, PRIMARY_DRY_RUN_EXPANSION))
    lines.extend(["", "SECONDARY WATCH-ONLY STATUSES"])
    lines.extend(_format_rows(payload, SECONDARY_WATCH_ONLY))
    lines.extend(
        [
            "",
            "MISSING OPERATOR REVIEW FIELDS",
            ", ".join(payload.get("missing_operator_review_fields") or []) or "none",
            "",
            "MAX LOSS DERIVATION",
            f"derived: {max_loss.get('derived')}",
            f"max_loss_usdt: {max_loss.get('max_loss_usdt')}",
            f"source: {max_loss.get('source')}",
            f"blocked_by: {','.join(max_loss.get('blocked_by') or []) or 'none'}",
            "",
            "FUTURE CONFIRMATION PHRASE PREVIEW",
            str(payload.get("future_confirmation_phrase_preview")),
            f"future_confirmation_phrase_active: {payload.get('future_confirmation_phrase_active')}",
            f"future_confirmation_phrase_executable: {payload.get('future_confirmation_phrase_executable')}",
            "",
            "SAFETY FLAGS",
        ]
    )
    for key in SAFETY:
        lines.append(f"{key}: {payload.get(key)}")
    lines.extend(
        [
            "",
            "RECOMMENDED R309 PATH",
            str(payload.get("recommended_r309_path")),
        ]
    )
    return "\n".join(lines)


def _format_rows(payload: Mapping[str, Any], role: str) -> list[str]:
    rows: list[str] = []
    for row in payload.get("proposed_contract_rows") or []:
        if isinstance(row, Mapping) and row.get("lane_role") == role:
            rows.append(
                f"{row.get('official_lane_key')} | status={row.get('write_gate_status')} "
                f"operator_review_required={row.get('operator_review_required')} "
                f"missing={','.join(row.get('missing_fields_after_preview') or []) or 'none'}"
            )
    return rows or ["none"]


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"funding_config": {}, "risk_contracts": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"funding_config": {}, "risk_contracts": []}


def _risk_contracts(config: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [row for row in config.get("risk_contracts") or [] if isinstance(row, Mapping)]


def _existing_contract_keys(config: Mapping[str, Any]) -> list[str]:
    keys: list[str] = []
    for row in _risk_contracts(config):
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


def _derive_max_loss(config: Mapping[str, Any]) -> dict[str, Any]:
    funding = config.get("funding_config") if isinstance(config.get("funding_config"), Mapping) else {}
    value = _number(funding.get("max_loss_usdt"))
    if value is not None and 0 < value <= DEFAULT_MAX_LOSS_USDT + 0.000001:
        return {
            "derived": True,
            "max_loss_usdt": value,
            "source": "funding_config.max_loss_usdt",
            "requires_operator_review": False,
            "blocked_by": [],
        }
    return {
        "derived": False,
        "max_loss_usdt": None,
        "source": "not_safely_derivable",
        "requires_operator_review": True,
        "blocked_by": ["risk_contract_max_loss_requires_operator_review"],
    }


def _missing_required_fields(contract: Mapping[str, Any]) -> list[str]:
    required = (
        "official_lane_key",
        "symbol",
        "timeframe",
        "direction",
        "entry_mode",
        "margin_mode",
        "leverage",
        "max_position_notional_usdt",
        "margin_budget_usdt",
        "max_loss_usdt",
        "max_trades_per_day",
        "daily_loss_stop_usdt",
        "protective_orders_required",
        "live_execution_enabled",
        "allow_live_orders",
    )
    return [key for key in required if contract.get(key) is None]


def _missing_operator_review_fields(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    fields: list[str] = []
    for row in rows:
        for field in row.get("missing_fields_after_preview") or []:
            fields.append(f"{row.get('official_lane_key')}:{field}")
    return _dedupe(fields)


def _role_status(rows: Sequence[Mapping[str, Any]], role: str) -> dict[str, Any]:
    statuses = _role_statuses(rows, role)
    return statuses[0] if statuses else {}


def _role_statuses(rows: Sequence[Mapping[str, Any]], role: str) -> list[dict[str, Any]]:
    return [
        {
            "official_lane_key": row.get("official_lane_key"),
            "write_gate_status": row.get("write_gate_status"),
            "operator_review_required": row.get("operator_review_required"),
            "missing_fields_after_preview": list(row.get("missing_fields_after_preview") or []),
            "blocked_by": list(row.get("blocked_by") or []),
        }
        for row in rows
        if row.get("lane_role") == role
    ]


def _recommended_r309_path(rows: Sequence[Mapping[str, Any]]) -> str:
    blocked = any(row.get("write_gate_status") != WRITE_GATE_PREVIEW_READY for row in rows)
    if blocked:
        return "R309 Max Loss Derivation Review"
    return "R309 Human-Reviewed Risk Contract Write Gate"


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        prog="python -m src.app.hammer_radar.operator.expansion_risk_contract_write_gate_preview"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--risk-contract-config-path", default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args()
    payload = build_expansion_risk_contract_write_gate_preview(
        log_dir=args.log_dir,
        risk_contract_config_path=args.risk_contract_config_path,
        write=not args.no_write,
    )
    print(format_preview_text(payload) if args.text else format_preview_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
