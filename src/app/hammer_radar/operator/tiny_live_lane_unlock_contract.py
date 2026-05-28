"""R143 tiny-live lane unlock contract.

This module records operator lane-unlock intent only. It never creates order
payloads, calls Binance, signs requests, mutates env files, changes global live
flags, disables kill switches, or places orders.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.lane_control import load_lane_controls

TINY_LIVE_LANE_UNLOCK_PREVIEW = "TINY_LIVE_LANE_UNLOCK_PREVIEW"
TINY_LIVE_LANE_UNLOCK_REJECTED = "TINY_LIVE_LANE_UNLOCK_REJECTED"
TINY_LIVE_LANE_UNLOCK_RECORDED = "TINY_LIVE_LANE_UNLOCK_RECORDED"
TINY_LIVE_LANE_UNLOCK_BLOCKED = "TINY_LIVE_LANE_UNLOCK_BLOCKED"
UNLOCKED_WAITING_FOR_CONDITIONS = "UNLOCKED_WAITING_FOR_CONDITIONS"
TINY_LIVE_LANE_UNLOCK_ERROR = "TINY_LIVE_LANE_UNLOCK_ERROR"

LOCKED = "LOCKED"
EVENT_TYPE = "TINY_LIVE_LANE_UNLOCK_CONTRACT"
LEDGER_FILENAME = "tiny_live_lane_unlock_contracts.ndjson"
CONFIRM_TINY_LIVE_LANE_UNLOCK_CONTRACT_PHRASE = (
    "I CONFIRM TINY LIVE LANE UNLOCK CONTRACT ONLY; NO ORDER; NO BINANCE CALL."
)

PRIMARY_UNLOCK_LANE = "BTCUSDT|13m|long|ladder_close_50_618"
SECONDARY_UNLOCK_LANE = "BTCUSDT|44m|long|ladder_close_50_618"
RECOMMENDED_UNLOCK_LANES = (PRIMARY_UNLOCK_LANE, SECONDARY_UNLOCK_LANE)

OPERATOR_INTENT = "unlock lanes for tiny-live condition-waiting mode"
DOES_NOT_AUTHORIZE = [
    "order placement",
    "Binance order endpoint calls",
    "Binance test-order endpoint calls",
    "protective order endpoint calls",
    "signed requests",
    "executable order payloads",
    "executable protective payloads",
    "global live flag mutation",
    "kill switch disablement",
    "env mutation",
    "bypassing R106/global gates",
    "bypassing protective policy",
]
REQUIRED_FUTURE_CONDITIONS = [
    "fresh routed candidate",
    "paper proof / or configured proof waiver if later approved",
    "R126 gate clear",
    "R130 tiny-live authorization clear",
    "protective policy clear",
    "risk contract clear",
    "global gates clear",
    "kill switch intentionally reviewed",
    "live execution flags explicitly armed in future phase",
]
SAFETY = {
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "network_allowed": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "secrets_shown": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
}
SOURCE_SURFACES_USED = [
    "operator.tiny_live_lane_unlock_contract.build_tiny_live_lane_unlock_contract_preview",
    "operator.lane_control.load_lane_controls",
    "operator.lane_command_interface R124 safe lane mode command remains the mutation interface",
    "operator.first_tiny_live_lane_execution_gate R126 remains future execution gate",
    "operator.first_tiny_live_autonomous_lane_authorization R130 remains future lane authorization gate",
    "operator.live_lane_kill_switch_rehearsal R131 remains kill-switch review evidence",
    "operator.autonomous_lane_live_ready_burn_down R138 remains blocker inventory",
    "operator.fresh_candidate_paper_proof_capture_loop R142 remains fresh candidate watcher",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_default_unlock_lane_specs() -> list[dict[str, Any]]:
    return [_lane_spec(lane_key, role) for lane_key, role in ((PRIMARY_UNLOCK_LANE, "primary"), (SECONDARY_UNLOCK_LANE, "secondary"))]


def validate_lane_unlock_request(
    *,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    unlock_all_recommended_lanes: bool = False,
    record_unlock_contract: bool = False,
    confirm_unlock_contract: str | None = None,
    apply_lane_mode_if_safe: bool = False,
    status_only: bool = False,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    lanes = _requested_lane_specs(
        lane_keys=lane_keys,
        lane_keys_csv=lane_keys_csv,
        unlock_all_recommended_lanes=unlock_all_recommended_lanes,
        status_only=status_only,
    )
    confirmation_valid = confirm_unlock_contract == CONFIRM_TINY_LIVE_LANE_UNLOCK_CONTRACT_PHRASE
    blockers: list[str] = []
    warnings: list[str] = []

    if status_only:
        return {
            "valid": True,
            "lanes": lanes,
            "confirmation_valid": confirmation_valid,
            "blockers": [],
            "warnings": [],
        }

    if not lanes:
        blockers.append("at least one lane key or --unlock-all-recommended-lanes is required")

    seen = {spec["lane_key"] for spec in lanes}
    if len(seen) != len(lanes):
        blockers.append("duplicate lane keys are not allowed")

    invalid = [spec["lane_key"] for spec in lanes if not _lane_key_is_well_formed(spec["lane_key"])]
    if invalid:
        blockers.append(f"invalid lane key format: {', '.join(invalid)}")

    try:
        controls = load_lane_controls(config_path)
        configured = set((controls.get("lane_map") or {}).keys())
        unknown = [spec["lane_key"] for spec in lanes if spec["lane_key"] not in configured]
        if unknown:
            blockers.append(f"unknown configured lane key: {', '.join(unknown)}")
    except Exception as exc:
        blockers.append(f"lane control config could not be loaded: {exc.__class__.__name__}")

    if record_unlock_contract and not confirmation_valid:
        blockers.append("exact tiny-live lane unlock contract confirmation phrase is required")

    if apply_lane_mode_if_safe:
        warnings.append("lane mode apply is deferred to the existing R124 lane-control-command interface")

    return {
        "valid": not blockers,
        "lanes": lanes,
        "confirmation_valid": confirmation_valid,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
    }


def build_tiny_live_lane_unlock_contract_preview(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    unlock_all_recommended_lanes: bool = False,
    record_unlock_contract: bool = False,
    confirm_unlock_contract: str | None = None,
    apply_lane_mode_if_safe: bool = False,
    status_only: bool = False,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    if status_only:
        return build_lane_unlock_status(log_dir=resolved_log_dir, now=generated_at)

    validation = validate_lane_unlock_request(
        lane_keys=lane_keys,
        lane_keys_csv=lane_keys_csv,
        unlock_all_recommended_lanes=unlock_all_recommended_lanes,
        record_unlock_contract=record_unlock_contract,
        confirm_unlock_contract=confirm_unlock_contract,
        apply_lane_mode_if_safe=apply_lane_mode_if_safe,
        status_only=status_only,
        config_path=config_path,
    )
    if validation["blockers"]:
        status = TINY_LIVE_LANE_UNLOCK_REJECTED if record_unlock_contract else TINY_LIVE_LANE_UNLOCK_BLOCKED
    else:
        status = TINY_LIVE_LANE_UNLOCK_PREVIEW
    return _status_payload(
        status=status,
        generated_at=generated_at,
        lanes=validation["lanes"],
        unlock_contract_recorded=False,
        unlock_contract_id=None,
        execution_state=LOCKED,
        operator_intent_valid=not validation["blockers"],
        confirmation_valid=validation["confirmation_valid"],
        lane_mode_apply_requested=apply_lane_mode_if_safe,
        lane_mode_apply_result=_lane_mode_apply_result(apply_lane_mode_if_safe),
        blockers=validation["blockers"],
        warnings=validation["warnings"],
        next_operator_move=_next_operator_move(status),
        recommended_next_commands=_recommended_next_commands(validation["lanes"]),
        ledger_path=_ledger_path(resolved_log_dir),
    )


def build_lane_unlock_contract(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    unlock_all_recommended_lanes: bool = False,
    record_unlock_contract: bool = False,
    confirm_unlock_contract: str | None = None,
    apply_lane_mode_if_safe: bool = False,
    status_only: bool = False,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    if status_only:
        return build_lane_unlock_status(log_dir=resolved_log_dir, now=generated_at)

    preview = build_tiny_live_lane_unlock_contract_preview(
        log_dir=resolved_log_dir,
        lane_keys=lane_keys,
        lane_keys_csv=lane_keys_csv,
        unlock_all_recommended_lanes=unlock_all_recommended_lanes,
        record_unlock_contract=record_unlock_contract,
        confirm_unlock_contract=confirm_unlock_contract,
        apply_lane_mode_if_safe=apply_lane_mode_if_safe,
        config_path=config_path,
        now=generated_at,
    )
    if preview["status"] in {TINY_LIVE_LANE_UNLOCK_REJECTED, TINY_LIVE_LANE_UNLOCK_BLOCKED}:
        return preview
    if not record_unlock_contract:
        return preview

    unlock_contract_id = f"tiny_live_lane_unlock_{uuid4().hex}"
    record = _contract_record(
        unlock_contract_id=unlock_contract_id,
        recorded_at_utc=generated_at.isoformat(),
        lanes=list(preview["lanes"]),
    )
    append_lane_unlock_contract_record(record, log_dir=resolved_log_dir)
    return _status_payload(
        status=TINY_LIVE_LANE_UNLOCK_RECORDED,
        generated_at=generated_at,
        lanes=list(preview["lanes"]),
        unlock_contract_recorded=True,
        unlock_contract_id=unlock_contract_id,
        execution_state=UNLOCKED_WAITING_FOR_CONDITIONS,
        operator_intent_valid=True,
        confirmation_valid=True,
        lane_mode_apply_requested=apply_lane_mode_if_safe,
        lane_mode_apply_result=_lane_mode_apply_result(apply_lane_mode_if_safe),
        blockers=[],
        warnings=list(preview.get("warnings") or []),
        next_operator_move="Wait for fresh routed candidates and future gates; do not place orders from this contract.",
        recommended_next_commands=_recommended_next_commands(list(preview["lanes"])),
        ledger_path=_ledger_path(resolved_log_dir),
    )


def append_lane_unlock_contract_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = _ledger_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(record)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_lane_unlock_contract_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = _ledger_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    if limit > 0:
        return list(reversed(records))[:limit]
    return records


def summarize_lane_unlock_contracts(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    lanes = Counter()
    for record in records:
        for lane in record.get("lanes") or []:
            if isinstance(lane, Mapping):
                lanes[str(lane.get("lane_key") or "")] += 1
            else:
                lanes[str(lane)] += 1
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "lane_counts": dict(sorted((key, value) for key, value in lanes.items() if key)),
        "latest_unlock_contract_id": records[-1].get("unlock_contract_id") if records else None,
        "safety": dict(SAFETY),
    }


def build_lane_unlock_status(*, log_dir: str | Path | None = None, now: datetime | None = None, limit: int = 20) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    all_records = load_lane_unlock_contract_records(log_dir=resolved_log_dir, limit=0)
    recent_records = list(reversed(all_records))[:limit]
    latest = all_records[-1] if all_records else None
    if latest:
        lanes = [_normalize_lane_record(lane) for lane in latest.get("lanes") or []]
        return _status_payload(
            status=UNLOCKED_WAITING_FOR_CONDITIONS,
            generated_at=generated_at,
            lanes=lanes,
            unlock_contract_recorded=True,
            unlock_contract_id=str(latest.get("unlock_contract_id") or ""),
            execution_state=UNLOCKED_WAITING_FOR_CONDITIONS,
            operator_intent_valid=True,
            confirmation_valid=bool(latest.get("operator_confirmation_valid", True)),
            lane_mode_apply_requested=False,
            lane_mode_apply_result=_lane_mode_apply_result(False),
            blockers=[],
            warnings=[],
            next_operator_move="Wait for fresh routed candidates and future gates; the latest contract is intent only.",
            recommended_next_commands=_recommended_next_commands(lanes),
            ledger_path=_ledger_path(resolved_log_dir),
            recent_records=recent_records,
            summary=summarize_lane_unlock_contracts(all_records),
        )
    return _status_payload(
        status=TINY_LIVE_LANE_UNLOCK_BLOCKED,
        generated_at=generated_at,
        lanes=[],
        unlock_contract_recorded=False,
        unlock_contract_id=None,
        execution_state=LOCKED,
        operator_intent_valid=False,
        confirmation_valid=False,
        lane_mode_apply_requested=False,
        lane_mode_apply_result=_lane_mode_apply_result(False),
        blockers=["no tiny-live lane unlock contract has been recorded"],
        warnings=[],
        next_operator_move="Preview or record an unlock contract with the exact R143 confirmation phrase.",
        recommended_next_commands=[],
        ledger_path=_ledger_path(resolved_log_dir),
        recent_records=[],
        summary=summarize_lane_unlock_contracts([]),
    )


def build_unlock_waiting_for_conditions_status(*, lanes: list[Mapping[str, Any]], unlock_contract_id: str | None = None) -> dict[str, Any]:
    return {
        "status": UNLOCKED_WAITING_FOR_CONDITIONS,
        "execution_state": UNLOCKED_WAITING_FOR_CONDITIONS,
        "unlock_contract_id": unlock_contract_id,
        "lanes": [_normalize_lane_record(lane) for lane in lanes],
        "required_future_conditions": list(REQUIRED_FUTURE_CONDITIONS),
        "does_not_authorize": list(DOES_NOT_AUTHORIZE),
        "safety": dict(SAFETY),
    }


def format_tiny_live_lane_unlock_contract_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _contract_record(*, unlock_contract_id: str, recorded_at_utc: str, lanes: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "event_type": EVENT_TYPE,
        "unlock_contract_id": unlock_contract_id,
        "recorded_at_utc": recorded_at_utc,
        "status": TINY_LIVE_LANE_UNLOCK_RECORDED,
        "lanes": [_normalize_lane_record(lane) for lane in lanes],
        "operator_intent": OPERATOR_INTENT,
        "operator_confirmation_valid": True,
        "execution_state": UNLOCKED_WAITING_FOR_CONDITIONS,
        "does_not_authorize": list(DOES_NOT_AUTHORIZE),
        "required_future_conditions": list(REQUIRED_FUTURE_CONDITIONS),
        "safety": dict(SAFETY),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }


def _status_payload(
    *,
    status: str,
    generated_at: datetime,
    lanes: list[Mapping[str, Any]],
    unlock_contract_recorded: bool,
    unlock_contract_id: str | None,
    execution_state: str,
    operator_intent_valid: bool,
    confirmation_valid: bool,
    lane_mode_apply_requested: bool,
    lane_mode_apply_result: dict[str, Any],
    blockers: list[str],
    warnings: list[str],
    next_operator_move: str,
    recommended_next_commands: list[str],
    ledger_path: Path,
    recent_records: list[Mapping[str, Any]] | None = None,
    summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "generated_at": generated_at.isoformat(),
        "lanes": [_normalize_lane_record(lane) for lane in lanes],
        "unlock_contract_recorded": bool(unlock_contract_recorded),
        "unlock_contract_id": unlock_contract_id,
        "latest_contract_id": unlock_contract_id,
        "execution_state": execution_state,
        "operator_intent_valid": bool(operator_intent_valid),
        "confirmation_valid": bool(confirmation_valid),
        "lane_mode_apply_requested": bool(lane_mode_apply_requested),
        "lane_mode_apply_result": dict(lane_mode_apply_result),
        "required_future_conditions": list(REQUIRED_FUTURE_CONDITIONS),
        "does_not_authorize": list(DOES_NOT_AUTHORIZE),
        "blockers": list(blockers),
        "warnings": list(warnings),
        "next_operator_move": next_operator_move,
        "recommended_next_commands": list(recommended_next_commands),
        "ledger_path": str(ledger_path),
        "safety": dict(SAFETY),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }
    if recent_records is not None:
        payload["recent_records"] = list(recent_records)
    if summary is not None:
        payload["summary"] = dict(summary)
    return payload


def _requested_lane_specs(
    *,
    lane_keys: list[str] | None,
    lane_keys_csv: str | None,
    unlock_all_recommended_lanes: bool,
    status_only: bool,
) -> list[dict[str, Any]]:
    if status_only:
        return []
    keys: list[str] = []
    for value in lane_keys or []:
        keys.extend(_split_lane_keys(value))
    keys.extend(_split_lane_keys(lane_keys_csv))
    if unlock_all_recommended_lanes:
        keys.extend(RECOMMENDED_UNLOCK_LANES)
    return [_lane_spec(key, _lane_role(key)) for key in _dedupe(keys)]


def _lane_spec(lane_key: str, role: str | None = None) -> dict[str, Any]:
    parts = str(lane_key or "").split("|")
    padded = [*parts, "", "", "", ""][:4]
    return {
        "lane_key": str(lane_key or "").strip(),
        "role": role or _lane_role(lane_key),
        "symbol": padded[0].strip().upper(),
        "timeframe": padded[1].strip().lower(),
        "direction": padded[2].strip().lower(),
        "entry_mode": padded[3].strip().lower(),
    }


def _normalize_lane_record(lane: Mapping[str, Any] | object) -> dict[str, Any]:
    if isinstance(lane, Mapping):
        lane_key = str(lane.get("lane_key") or "")
    else:
        lane_key = str(lane or "")
    spec = _lane_spec(lane_key)
    if isinstance(lane, Mapping) and lane.get("role"):
        spec["role"] = str(lane.get("role"))
    return spec


def _split_lane_keys(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _lane_key_is_well_formed(lane_key: str) -> bool:
    parts = str(lane_key or "").split("|")
    return len(parts) == 4 and all(part.strip() for part in parts)


def _lane_role(lane_key: str) -> str:
    if lane_key == PRIMARY_UNLOCK_LANE:
        return "primary"
    if lane_key == SECONDARY_UNLOCK_LANE:
        return "secondary"
    return "operator_selected"


def _lane_mode_apply_result(requested: bool) -> dict[str, Any]:
    if not requested:
        return {
            "status": "NOT_REQUESTED",
            "config_written": False,
            "reason": "R143 default is record-only and preview-only unless a contract write is explicitly confirmed.",
        }
    return {
        "status": TINY_LIVE_LANE_UNLOCK_BLOCKED,
        "config_written": False,
        "reason": "R143 does not mutate lane config; use R124 lane-control-command for existing lane mode changes.",
        "recommended_interface": "lane-control-command",
    }


def _recommended_next_commands(lanes: list[Mapping[str, Any]]) -> list[str]:
    commands = [
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward tiny-live-lane-unlock-contract --status-only",
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward fresh-candidate-paper-proof-capture-loop --watch-all-recommended-lanes",
    ]
    for lane in lanes[:2]:
        lane_key = str(lane.get("lane_key") or "")
        if lane_key:
            commands.append(
                "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
                f"--log-dir logs/hammer_radar_forward autonomous-lane-live-ready-burn-down --lane-key \"{lane_key}\""
            )
    return commands


def _next_operator_move(status: str) -> str:
    if status == TINY_LIVE_LANE_UNLOCK_PREVIEW:
        return "Preview only. Record the unlock contract only with the exact R143 confirmation phrase."
    if status == TINY_LIVE_LANE_UNLOCK_REJECTED:
        return "Fix confirmation or lane selection; no unlock contract was recorded."
    return "Fix blockers; no unlock contract was recorded."


def _ledger_path(log_dir: str | Path | None) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
