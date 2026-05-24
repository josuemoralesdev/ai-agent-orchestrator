"""R124 safe operator lane-control command interface.

This module mutates only lane-control config intent after explicit operator
confirmation. It never creates order payloads, places orders, calls Binance,
mutates env files, or changes global live flags.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.lane_control import (
    DEFAULT_CONFIG_PATH,
    SAFETY_FALSE,
    evaluate_lane_permission,
    load_lane_controls,
)

CONFIRM_LANE_CHANGE_PHRASE = "I CONFIRM LANE CONFIG CHANGE ONLY; NO ORDER; NO ENV CHANGE."
LANE_COMMAND_LEDGER = "lane_control_commands.ndjson"

LANE_COMMAND_LIST = "LANE_COMMAND_LIST"
LANE_COMMAND_PREVIEW = "LANE_COMMAND_PREVIEW"
LANE_COMMAND_APPLIED = "LANE_COMMAND_APPLIED"
LANE_COMMAND_REJECTED = "LANE_COMMAND_REJECTED"

ALLOWED_ACTIONS = {
    "list",
    "preview-set-mode",
    "set-mode",
    "disable-lane",
    "enable-paper",
    "enable-armed-dry-run",
    "request-tiny-live-mode",
}
ALLOWED_MODES = {"disabled", "paper", "armed_dry_run", "tiny_live"}
ACTION_MODES = {
    "disable-lane": "disabled",
    "enable-paper": "paper",
    "enable-armed-dry-run": "armed_dry_run",
    "request-tiny-live-mode": "tiny_live",
}
COMMAND_SAFETY_FALSE = {
    **SAFETY_FALSE,
    "env_mutated": False,
    "global_live_flags_changed": False,
}
SOURCE_SURFACES_USED = [
    "operator.lane_control.load_lane_controls",
    "operator.lane_control.evaluate_lane_permission",
    "configs/hammer_radar/lane_controls.json",
    "R106 first-live activation gate remains authoritative for tiny_live",
]


def load_current_lane_config(config_path: str | Path | None = None) -> dict[str, Any]:
    return load_lane_controls(config_path)


def validate_requested_lane_mode_change(
    *,
    action: str,
    lane_key: str | None = None,
    mode: str | None = None,
    apply: bool = False,
    confirm_lane_change: str | None = None,
    request_tiny_live: bool = False,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    controls = load_current_lane_config(config_path)
    requested_action = _normalize_action(action)
    requested_mode = _requested_mode(requested_action, mode)
    confirmation_valid = confirm_lane_change == CONFIRM_LANE_CHANGE_PHRASE
    blockers: list[str] = []
    warnings: list[str] = []

    if requested_action not in ALLOWED_ACTIONS:
        blockers.append(f"unsupported lane command action: {requested_action or 'MISSING'}")

    if requested_action != "list" and not lane_key:
        blockers.append("lane_key is required for lane mode changes")

    lane = _find_lane(controls, lane_key)
    if requested_action != "list" and lane is None:
        blockers.append("unknown lane_key; R124 rejects unknown lanes by default")

    if requested_action != "list" and requested_mode not in ALLOWED_MODES:
        blockers.append(f"invalid requested lane mode: {requested_mode or 'MISSING'}")

    if requested_mode == "tiny_live" and not request_tiny_live:
        blockers.append("tiny_live mode requires --request-tiny-live")

    if apply and not confirmation_valid:
        blockers.append("exact lane config change confirmation phrase is required for apply")

    if requested_action == "preview-set-mode" and apply:
        warnings.append("preview-set-mode ignores apply and remains preview-only")

    if requested_action == "list" and apply:
        warnings.append("list action ignores apply and never writes config")

    if requested_action != "list":
        warnings.append("lane mode is operator intent only; it is not execution permission")
    if requested_mode == "tiny_live":
        warnings.append("tiny_live lane mode remains blocked unless R106/global gates are ready")

    return {
        "valid": not blockers,
        "action": requested_action,
        "lane_key": lane_key,
        "requested_mode": requested_mode,
        "previous_mode": str(lane.get("mode") or "disabled") if lane else None,
        "apply_requested": bool(apply),
        "confirmation_valid": bool(confirmation_valid),
        "tiny_live_requested": bool(request_tiny_live),
        "blockers": blockers,
        "warnings": warnings,
        "lane": lane,
        "controls": controls,
    }


def build_lane_command_preview(
    *,
    action: str,
    lane_key: str | None = None,
    mode: str | None = None,
    apply: bool = False,
    confirm_lane_change: str | None = None,
    request_tiny_live: bool = False,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    global_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validation = validate_requested_lane_mode_change(
        action=action,
        lane_key=lane_key,
        mode=mode,
        apply=apply,
        confirm_lane_change=confirm_lane_change,
        request_tiny_live=request_tiny_live,
        config_path=config_path,
    )
    generated_at = datetime.now(UTC).isoformat()
    action_name = validation["action"]
    requested_mode = validation["requested_mode"]
    previous_mode = validation["previous_mode"]
    resulting_mode = previous_mode if validation["blockers"] else (requested_mode or previous_mode)

    if action_name == "list":
        status = LANE_COMMAND_LIST
    elif validation["blockers"]:
        status = LANE_COMMAND_REJECTED
    else:
        status = LANE_COMMAND_PREVIEW

    controls_after = _controls_with_mode(validation["controls"], lane_key, resulting_mode)
    return _command_result(
        status=status,
        generated_at=generated_at,
        action=action_name,
        lane_key=lane_key,
        requested_mode=requested_mode,
        previous_mode=previous_mode,
        resulting_mode=resulting_mode,
        apply_requested=validation["apply_requested"],
        confirmation_valid=validation["confirmation_valid"],
        tiny_live_requested=validation["tiny_live_requested"],
        config_written=False,
        ledger_written=False,
        blockers=validation["blockers"],
        warnings=validation["warnings"],
        lane_status_after_change=_lane_status_after_change(
            lane_key=lane_key,
            controls=controls_after,
            log_dir=log_dir,
            live_eligibility_matrix=live_eligibility_matrix,
            global_gate=global_gate,
        ),
        lanes=_compact_lanes(validation["controls"]) if action_name == "list" else None,
    )


def apply_lane_command(
    *,
    action: str,
    lane_key: str | None = None,
    mode: str | None = None,
    apply: bool = False,
    confirm_lane_change: str | None = None,
    request_tiny_live: bool = False,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    global_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    preview = build_lane_command_preview(
        action=action,
        lane_key=lane_key,
        mode=mode,
        apply=apply,
        confirm_lane_change=confirm_lane_change,
        request_tiny_live=request_tiny_live,
        log_dir=log_dir,
        config_path=config_path,
        live_eligibility_matrix=live_eligibility_matrix,
        global_gate=global_gate,
    )
    if preview["status"] == LANE_COMMAND_REJECTED or preview["action"] == "list":
        return preview
    if not apply:
        return preview
    if not preview["confirmation_valid"]:
        return {**preview, "status": LANE_COMMAND_REJECTED, "blockers": [*preview["blockers"], "exact lane config change confirmation phrase is required for apply"]}

    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    _write_lane_mode(path, str(lane_key), str(preview["resulting_mode"]))
    controls_after = load_current_lane_config(path)
    applied = {
        **preview,
        "status": LANE_COMMAND_APPLIED,
        "config_written": True,
        "lane_status_after_change": _lane_status_after_change(
            lane_key=lane_key,
            controls=controls_after,
            log_dir=log_dir,
            live_eligibility_matrix=live_eligibility_matrix,
            global_gate=global_gate,
        ),
    }
    ledger_written = _append_lane_command_ledger(applied, log_dir=log_dir)
    return {**applied, "ledger_written": ledger_written}


def format_lane_command_result_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _command_result(
    *,
    status: str,
    generated_at: str,
    action: str,
    lane_key: str | None,
    requested_mode: str | None,
    previous_mode: str | None,
    resulting_mode: str | None,
    apply_requested: bool,
    confirmation_valid: bool,
    tiny_live_requested: bool,
    config_written: bool,
    ledger_written: bool,
    blockers: list[str],
    warnings: list[str],
    lane_status_after_change: dict[str, Any] | None,
    lanes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "generated_at": generated_at,
        "action": action,
        "lane_key": lane_key,
        "requested_mode": requested_mode,
        "previous_mode": previous_mode,
        "resulting_mode": resulting_mode,
        "apply_requested": bool(apply_requested),
        "confirmation_valid": bool(confirmation_valid),
        "tiny_live_requested": bool(tiny_live_requested),
        "config_written": bool(config_written),
        "ledger_written": bool(ledger_written),
        "blockers": list(blockers),
        "warnings": list(warnings),
        "lane_status_after_change": lane_status_after_change,
        "safety": dict(COMMAND_SAFETY_FALSE),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }
    if lanes is not None:
        payload["lanes"] = lanes
        payload["configured_lanes_count"] = len(lanes)
    return payload


def _append_lane_command_ledger(payload: Mapping[str, Any], *, log_dir: str | Path | None) -> bool:
    ledger_dir = Path(log_dir) if log_dir is not None else Path("logs/hammer_radar_forward")
    ledger_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "event_type": "LANE_CONTROL_COMMAND",
        "command_id": str(uuid4()),
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "action": payload.get("action"),
        "lane_key": payload.get("lane_key"),
        "requested_mode": payload.get("requested_mode"),
        "previous_mode": payload.get("previous_mode"),
        "resulting_mode": payload.get("resulting_mode"),
        "apply_requested": payload.get("apply_requested"),
        "confirmation_valid": payload.get("confirmation_valid"),
        "tiny_live_requested": payload.get("tiny_live_requested"),
        "config_written": payload.get("config_written"),
        "status": payload.get("status"),
        "blockers": list(payload.get("blockers") or []),
        "warnings": list(payload.get("warnings") or []),
        "safety": dict(payload.get("safety") or COMMAND_SAFETY_FALSE),
        "source_surfaces_used": list(payload.get("source_surfaces_used") or SOURCE_SURFACES_USED),
    }
    with (ledger_dir / LANE_COMMAND_LEDGER).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return True


def _write_lane_mode(config_path: Path, lane_key: str, mode: str) -> None:
    with config_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    changed = False
    for lane in raw.get("lanes", []):
        loaded_key = _lane_key_from_raw(lane)
        if loaded_key == lane_key:
            lane["mode"] = mode
            changed = True
            break
    if not changed:
        raise ValueError(f"unknown lane_key: {lane_key}")
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(raw, handle, indent=2)
        handle.write("\n")


def _lane_status_after_change(
    *,
    lane_key: str | None,
    controls: Mapping[str, Any],
    log_dir: str | Path | None,
    live_eligibility_matrix: Mapping[str, Any] | None,
    global_gate: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not lane_key:
        return None
    lane = _find_lane(controls, lane_key)
    if lane is None:
        return None
    status = evaluate_lane_permission(
        lane.get("symbol"),
        lane.get("timeframe"),
        lane.get("direction"),
        lane.get("entry_mode"),
        controls=controls,
        live_eligibility_matrix=live_eligibility_matrix,
        global_gate=global_gate,
        log_dir=log_dir,
    )
    return {
        "status": status.get("status"),
        "mode": status.get("mode"),
        "lane_key": status.get("lane_key"),
        "blockers": list(status.get("blockers") or [])[:5],
        "risk_limits": status.get("risk_limits"),
        "safety": status.get("safety"),
    }


def _controls_with_mode(controls: Mapping[str, Any], lane_key: str | None, mode: str | None) -> dict[str, Any]:
    lanes = [dict(lane) for lane in controls.get("lanes") or []]
    if lane_key and mode:
        for lane in lanes:
            if lane.get("lane_key") == lane_key:
                lane["mode"] = mode
                break
    return {
        **dict(controls),
        "lanes": lanes,
        "lane_map": {str(lane.get("lane_key")): lane for lane in lanes},
    }


def _compact_lanes(controls: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "lane_key": lane.get("lane_key"),
            "mode": lane.get("mode"),
            "risk_limits": {
                "max_daily_trades": lane.get("max_daily_trades"),
                "max_daily_loss_pct": lane.get("max_daily_loss_pct"),
                "cooldown_after_loss_minutes": lane.get("cooldown_after_loss_minutes"),
                "require_protective_orders": lane.get("require_protective_orders"),
            },
            "freshness_seconds": lane.get("freshness_seconds"),
        }
        for lane in controls.get("lanes") or []
    ]


def _find_lane(controls: Mapping[str, Any], lane_key: str | None) -> dict[str, Any] | None:
    if not lane_key:
        return None
    lane = (controls.get("lane_map") or {}).get(str(lane_key))
    return dict(lane) if lane else None


def _requested_mode(action: str, mode: str | None) -> str | None:
    if action in ACTION_MODES:
        return ACTION_MODES[action]
    if mode is None:
        return None
    return str(mode).strip().lower()


def _normalize_action(action: str | None) -> str:
    return str(action or "").strip().lower()


def _lane_key_from_raw(lane: Mapping[str, Any]) -> str:
    from src.app.hammer_radar.operator.lane_control import normalize_lane_key

    return normalize_lane_key(
        lane.get("symbol"),
        lane.get("timeframe"),
        lane.get("direction"),
        lane.get("entry_mode"),
    )
