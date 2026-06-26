"""R309 human-reviewed expansion risk-contract write gate.

This module can append the exact R308-reviewed risk-contract rows only when the
operator supplies the exact R309 confirmation phrase. Default CLI behavior is
preview-only and never mutates config, arming state, env, live flags, leverage,
margin, order payloads, or Binance endpoints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.expansion_risk_contract_write_gate_preview import (
    PRIMARY_DRY_RUN_EXPANSION,
    REQUIRED_BASELINE,
    SECONDARY_WATCH_ONLY,
    WRITE_GATE_PREVIEW_READY,
    build_proposed_contract_row,
    build_r308_lane_specs,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.strategy_lab_preview import CURRENT_TINY_LIVE_LANE
from src.app.hammer_radar.operator.tiny_live_risk_contract_validation import (
    DEFAULT_MAX_LOSS_USDT,
    DEFAULT_RISK_CONTRACT_CONFIG_PATH,
    build_tiny_live_risk_contract_validation_summary,
)

EVENT_TYPE = "R309_HUMAN_REVIEWED_RISK_CONTRACT_WRITE_GATE"
CREATED_BY_PHASE = "R309_HUMAN_REVIEWED_RISK_CONTRACT_WRITE_GATE"
LEDGER_FILENAME = "expansion_risk_contract_human_reviewed_write_gate.ndjson"
CONFIRMATION_PHRASE = "WRITE RISK CONTRACTS FOR R308 REVIEWED LANES"

WRITE_GATE_PREVIEW_READY_FOR_CONFIRMATION = "WRITE_GATE_PREVIEW_READY_FOR_CONFIRMATION"
WRITE_GATE_REJECTED_BAD_CONFIRMATION = "WRITE_GATE_REJECTED_BAD_CONFIRMATION"
WRITE_GATE_BLOCKED_BY_VALIDATION = "WRITE_GATE_BLOCKED_BY_VALIDATION"
WRITE_GATE_WRITTEN = "WRITE_GATE_WRITTEN"
WRITE_GATE_NOOP_ALL_ROWS_EXIST = "WRITE_GATE_NOOP_ALL_ROWS_EXIST"

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
    "global_live_flags_changed": False,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_mutated": False,
}


def build_expansion_risk_contract_human_reviewed_write_gate(
    *,
    log_dir: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    apply: bool = False,
    confirmation: str | None = None,
    write_ledger: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = now or datetime.now(UTC)
    config_path = (
        Path(risk_contract_config_path)
        if risk_contract_config_path is not None
        else DEFAULT_RISK_CONTRACT_CONFIG_PATH
    )
    config_before = _load_config(config_path)
    existing_keys_before = _existing_contract_keys(config_before)
    max_loss_derivation = _derive_max_loss(config_before)
    proposed_rows = _build_r308_proposed_rows(
        existing_keys=existing_keys_before,
        max_loss_derivation=max_loss_derivation,
    )
    proposed_by_key = {str(row["official_lane_key"]): row for row in proposed_rows}
    proposed_keys = list(proposed_by_key)
    would_add_lane_keys = [key for key in proposed_keys if key not in existing_keys_before]
    skipped_existing_lane_keys = [key for key in proposed_keys if key in existing_keys_before]
    row_validations = _validate_proposed_rows(proposed_rows)
    validation_status = _validation_status(row_validations)
    confirmation_matched = confirmation == CONFIRMATION_PHRASE
    config_sha256_before = _sha256_file(config_path)
    backup_path: str | None = None
    added_lane_keys: list[str] = []
    config_written = False

    if apply and not confirmation_matched:
        status = WRITE_GATE_REJECTED_BAD_CONFIRMATION
        blocked_by = ["exact_confirmation_phrase_required"]
    elif apply and validation_status["valid"] is not True:
        status = WRITE_GATE_BLOCKED_BY_VALIDATION
        blocked_by = list(validation_status["blocked_by"])
    elif apply and not would_add_lane_keys:
        status = WRITE_GATE_NOOP_ALL_ROWS_EXIST
        blocked_by = []
    elif apply and confirmation_matched:
        backup_path = _backup_config(config_path, generated_at=generated_at)
        contracts_to_append = [
            dict(proposed_by_key[lane_key]["proposed_contract"]) for lane_key in would_add_lane_keys
        ]
        merged = _append_missing_contracts(config_before, contracts_to_append)
        _atomic_write_json(config_path, merged)
        config_written = True
        added_lane_keys = list(would_add_lane_keys)
        status = WRITE_GATE_WRITTEN
        blocked_by = []
    else:
        status = WRITE_GATE_PREVIEW_READY_FOR_CONFIRMATION if validation_status["valid"] else WRITE_GATE_BLOCKED_BY_VALIDATION
        blocked_by = [] if validation_status["valid"] else list(validation_status["blocked_by"])

    config_after = _load_config(config_path)
    existing_keys_after = _existing_contract_keys(config_after)
    post_write_validation = _post_write_validation(
        config_after=config_after,
        added_lane_keys=added_lane_keys,
    )
    safety = dict(SAFETY)
    if config_written:
        safety["config_written"] = True
        safety["risk_contract_config_mutated"] = True

    payload = {
        "event_type": EVENT_TYPE,
        "created_by_phase": CREATED_BY_PHASE,
        "gate_id": f"r309_human_reviewed_risk_contract_write_gate_{uuid4().hex}",
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "ledger_path": str(records_path(resolved_log_dir)),
        "current_first_tiny_live_lane": CURRENT_TINY_LIVE_LANE,
        "current_first_tiny_live_lane_unchanged": True,
        "risk_contract_config_path": str(config_path),
        "apply_requested": bool(apply),
        "preview_only": not bool(apply),
        "confirmation_phrase_matched": bool(confirmation_matched),
        "confirmation_phrase_required": CONFIRMATION_PHRASE,
        "status": status,
        "blocked_by": blocked_by,
        "proposed_contract_rows": proposed_rows,
        "proposed_contract_count": len(proposed_rows),
        "max_loss_derivation": max_loss_derivation,
        "would_add_lane_keys": would_add_lane_keys if not config_written else [],
        "skipped_existing_lane_keys": skipped_existing_lane_keys,
        "added_lane_keys": added_lane_keys,
        "existing_lane_keys_before": existing_keys_before,
        "existing_lane_keys_after": existing_keys_after,
        "validation_status": validation_status,
        "row_validations": row_validations,
        "backup_created": backup_path is not None,
        "backup_path": backup_path,
        "config_sha256_before": config_sha256_before,
        "config_sha256_after": _sha256_file(config_path),
        "post_write_validation": post_write_validation,
        "recommended_r310_path": _recommended_r310_path(config_written=config_written),
        "manual_apply_command_preview": (
            "PYTHONPATH=. .venv/bin/python -m "
            "src.app.hammer_radar.operator.expansion_risk_contract_human_reviewed_write_gate "
            "--log-dir logs/hammer_radar_forward --apply "
            f'--confirmation "{CONFIRMATION_PHRASE}"'
        ),
        "source_surfaces_used": [
            "configs/hammer_radar/tiny_live_risk_contracts.json",
            "configs/hammer_radar/autonomous_arming_state.json",
            "src/app/hammer_radar/operator/expansion_risk_contract_write_gate_preview.py",
            "src/app/hammer_radar/operator/tiny_live_risk_contract_validation.py",
            "src/app/hammer_radar/operator/inspect.py",
        ],
        "safety": safety,
        **safety,
    }
    safe_payload = _sanitize(payload, force_safety=not config_written)
    if write_ledger:
        append_record(safe_payload, log_dir=resolved_log_dir)
    return safe_payload


def load_expansion_risk_contract_human_reviewed_write_gate_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    return read_recent_ndjson_records(records_path(get_log_dir(log_dir, use_env=True)), limit=limit)


def append_record(record: Mapping[str, Any], *, log_dir: str | Path) -> None:
    path = records_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_gate_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def format_gate_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "R309 HUMAN-REVIEWED RISK CONTRACT WRITE GATE",
        f"archive_log_dir: {payload.get('archive_log_dir')}",
        f"event_type: {payload.get('event_type')}",
        "",
        "CURRENT CONFIG PATH",
        f"risk_contract_config_path: {payload.get('risk_contract_config_path')}",
        f"config_sha256_before: {payload.get('config_sha256_before')}",
        f"config_sha256_after: {payload.get('config_sha256_after')}",
        "",
        "GATE STATUS",
        f"status: {payload.get('status')}",
        f"apply_requested: {payload.get('apply_requested')}",
        f"confirmation_phrase_matched: {payload.get('confirmation_phrase_matched')}",
        f"config_written: {payload.get('config_written')}",
        f"risk_contract_config_mutated: {payload.get('risk_contract_config_mutated')}",
        "",
        "PROPOSED ROWS",
        f"proposed_contract_count: {payload.get('proposed_contract_count')}",
        f"would_add_lane_keys: {', '.join(payload.get('would_add_lane_keys') or []) or 'none'}",
        f"skipped_existing_lane_keys: {', '.join(payload.get('skipped_existing_lane_keys') or []) or 'none'}",
        f"added_lane_keys: {', '.join(payload.get('added_lane_keys') or []) or 'none'}",
        "",
        "VALIDATION STATUS",
        f"valid: {(payload.get('validation_status') or {}).get('valid')}",
        f"blocked_by: {', '.join((payload.get('validation_status') or {}).get('blocked_by') or []) or 'none'}",
        "",
        "BACKUP",
        f"backup_created: {payload.get('backup_created')}",
        f"backup_path: {payload.get('backup_path') or 'none'}",
        "",
        "SAFETY FLAGS",
    ]
    for key in SAFETY:
        lines.append(f"{key}: {payload.get(key)}")
    lines.extend(
        [
            "",
            "MANUAL APPLY COMMAND PREVIEW",
            str(payload.get("manual_apply_command_preview")),
            "",
            "RECOMMENDED R310 PATH",
            str(payload.get("recommended_r310_path")),
        ]
    )
    return "\n".join(lines)


def _build_r308_proposed_rows(
    *,
    existing_keys: Sequence[str],
    max_loss_derivation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        build_proposed_contract_row(
            lane_key=lane_key,
            lane_role=lane_role,
            existing_keys=existing_keys,
            max_loss_derivation=max_loss_derivation,
        )
        for lane_key, lane_role in build_r308_lane_specs()
    ]


def _validate_proposed_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    validations: list[dict[str, Any]] = []
    for row in rows:
        contract = row.get("proposed_contract") if isinstance(row.get("proposed_contract"), Mapping) else {}
        validation = build_tiny_live_risk_contract_validation_summary(risk_contract=contract)
        blocked_by = list(validation.get("blocked_by") or [])
        if row.get("write_gate_status") != WRITE_GATE_PREVIEW_READY:
            blocked_by.append("r308_proposed_row_not_preview_ready")
        if contract.get("live_execution_enabled") is not False:
            blocked_by.append("new_contract_live_execution_enabled_not_false")
        if contract.get("allow_live_orders") is not False:
            blocked_by.append("new_contract_allow_live_orders_not_false")
        validations.append(
            {
                "official_lane_key": row.get("official_lane_key"),
                "valid": not blocked_by,
                "blocked_by": _dedupe(blocked_by),
                "risk_contract_validation": validation,
            }
        )
    return validations


def _validation_status(validations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    blocked_by: list[str] = []
    invalid_lane_keys: list[str] = []
    for validation in validations:
        if validation.get("valid") is not True:
            invalid_lane_keys.append(str(validation.get("official_lane_key") or ""))
            blocked_by.extend(str(item) for item in validation.get("blocked_by") or [])
    return {
        "valid": not invalid_lane_keys,
        "invalid_lane_keys": _dedupe(invalid_lane_keys),
        "blocked_by": _dedupe(blocked_by),
    }


def _post_write_validation(
    *,
    config_after: Mapping[str, Any],
    added_lane_keys: Sequence[str],
) -> dict[str, Any]:
    rows = _risk_contracts(config_after)
    by_key = {_best_contract_key(row): row for row in rows}
    added = []
    for lane_key in added_lane_keys:
        row = by_key.get(lane_key, {})
        validation = build_tiny_live_risk_contract_validation_summary(risk_contract=row)
        added.append(
            {
                "official_lane_key": lane_key,
                "found_after_reload": bool(row),
                "valid_after_reload": bool(row) and validation.get("risk_contract_valid") is True,
                "live_execution_enabled": row.get("live_execution_enabled") is True,
                "allow_live_orders": row.get("allow_live_orders") is True,
                "validation": validation,
            }
        )
    return {
        "added_rows_checked": len(added),
        "all_added_rows_found": all(row["found_after_reload"] for row in added) if added else True,
        "all_added_rows_valid": all(row["valid_after_reload"] for row in added) if added else True,
        "added_rows": added,
    }


def _append_missing_contracts(
    config: Mapping[str, Any],
    contracts_to_append: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    merged = _sanitize(dict(config), force_safety=False)
    existing = _risk_contracts(merged)
    existing_keys = set(_existing_contract_keys(merged))
    appended = list(existing)
    for contract in contracts_to_append:
        lane_key = _best_contract_key(contract)
        if lane_key and lane_key not in existing_keys:
            appended.append(_sanitize(dict(contract), force_safety=False))
            existing_keys.add(lane_key)
    merged["risk_contracts"] = appended
    return merged


def _backup_config(path: Path, *, generated_at: datetime) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.r309_backup_{stamp}")
    backup.write_bytes(path.read_bytes() if path.exists() else b"")
    return str(backup)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as handle:
        handle.write(text)
        tmp_path = Path(handle.name)
    tmp_path.replace(path)


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"funding_config": {}, "risk_contracts": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"funding_config": {}, "risk_contracts": []}


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


def _risk_contracts(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in config.get("risk_contracts") or [] if isinstance(row, Mapping)]


def _existing_contract_keys(config: Mapping[str, Any]) -> list[str]:
    keys: list[str] = []
    for row in _risk_contracts(config):
        key = _best_contract_key(row)
        if key:
            keys.append(key)
    return _dedupe(keys)


def _best_contract_key(row: Mapping[str, Any]) -> str:
    official = str(row.get("official_lane_key") or row.get("lane_key") or "")
    if official:
        return official
    return "|".join(str(row.get(key) or "") for key in ("symbol", "timeframe", "direction", "entry_mode"))


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


def _recommended_r310_path(*, config_written: bool) -> str:
    if config_written:
        return (
            "R310 Multi-Lane Dry-Run Observation Scheduler: observe baseline and primary lanes "
            "in dry-run only; no live execution and no arming mutation."
        )
    return "R310 Operator Review And Apply Risk Contracts: manual operator decision step, not automatic."


def _dedupe(items: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def _sanitize(value: Any, *, force_safety: bool) -> Any:
    if isinstance(value, Mapping):
        sanitized = {str(key): _sanitize(item, force_safety=force_safety) for key, item in value.items()}
        if force_safety:
            for key, safety_value in SAFETY.items():
                if key in sanitized:
                    sanitized[key] = safety_value
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item, force_safety=force_safety) for item in value]
    return value


def _main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.app.hammer_radar.operator.expansion_risk_contract_human_reviewed_write_gate"
    )
    parser.add_argument("--log-dir", default=None)
    parser.add_argument("--risk-contract-config-path", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirmation", default=None)
    parser.add_argument("--no-ledger", action="store_true")
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args()
    payload = build_expansion_risk_contract_human_reviewed_write_gate(
        log_dir=args.log_dir,
        risk_contract_config_path=args.risk_contract_config_path,
        apply=args.apply,
        confirmation=args.confirmation,
        write_ledger=not args.no_ledger,
    )
    print(format_gate_text(payload) if args.text else format_gate_json(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
