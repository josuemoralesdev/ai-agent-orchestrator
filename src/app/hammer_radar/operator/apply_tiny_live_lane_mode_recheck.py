"""R148 apply tiny-live lane mode recheck/runbook surface.

This module emits an operator-safe apply-and-recheck runbook for moving the
already-unlocked BTCUSDT 13m/44m lanes to tiny_live intent through the existing
R124/R147 lane-control-command path. It never applies lane config, creates
payloads, calls Binance, mutates env files, or enables live execution.
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
from src.app.hammer_radar.operator.binance_readonly import build_binance_readonly_status
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_command_interface import CONFIRM_LANE_CHANGE_PHRASE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, load_lane_controls
from src.app.hammer_radar.operator.strategy_performance import (
    ELIGIBLE_FOR_FUTURE_TINY_LIVE,
    build_live_eligibility_matrix,
)

TINY_LIVE_LANE_MODE_RECHECK_PREVIEW = "TINY_LIVE_LANE_MODE_RECHECK_PREVIEW"
TINY_LIVE_LANE_MODE_RECHECK_READY = "TINY_LIVE_LANE_MODE_RECHECK_READY"
TINY_LIVE_LANE_MODE_RECHECK_REJECTED = "TINY_LIVE_LANE_MODE_RECHECK_REJECTED"
TINY_LIVE_LANE_MODE_RECHECK_RECORDED = "TINY_LIVE_LANE_MODE_RECHECK_RECORDED"
TINY_LIVE_LANE_MODE_RECHECK_BLOCKED = "TINY_LIVE_LANE_MODE_RECHECK_BLOCKED"
TINY_LIVE_LANE_MODE_RECHECK_ERROR = "TINY_LIVE_LANE_MODE_RECHECK_ERROR"

APPLY_TINY_LIVE_LANE_MODE_ON_MAIN = "APPLY_TINY_LIVE_LANE_MODE_ON_MAIN"
RECHECK_TINY_LIVE_GATES = "RECHECK_TINY_LIVE_GATES"
RUN_POST_BRIDGE_WATCHER = "RUN_POST_BRIDGE_WATCHER"
WAIT_FOR_FRESH_NORMALIZED_CANDIDATE = "WAIT_FOR_FRESH_NORMALIZED_CANDIDATE"
STOP_SAFETY_BLOCK = "STOP_SAFETY_BLOCK"

PRIMARY_TARGET_LANE = "BTCUSDT|13m|long|ladder_close_50_618"
SECONDARY_TARGET_LANE = "BTCUSDT|44m|long|ladder_close_50_618"
DEFAULT_TARGET_LANES = (PRIMARY_TARGET_LANE, SECONDARY_TARGET_LANE)
TARGET_MODE = "tiny_live"

EVENT_TYPE = "TINY_LIVE_LANE_MODE_RECHECK"
LEDGER_FILENAME = "tiny_live_lane_mode_rechecks.ndjson"
CONFIRM_TINY_LIVE_LANE_MODE_RECHECK_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE LANE MODE RECHECK RECORDING ONLY; NO ORDER; NO BINANCE CALL."
)

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
}

SOURCE_SURFACES_USED = [
    "operator.lane_control.load_lane_controls",
    "operator.strategy_performance.build_live_eligibility_matrix",
    "operator.lane_command_interface.CONFIRM_LANE_CHANGE_PHRASE",
    "operator.binance_readonly.build_binance_readonly_status",
    "operator.first_tiny_live_lane_execution_gate CLI recheck command",
    "operator.post_bridge_watcher_proof_capture_recheck CLI recheck command",
    "operator.fresh_candidate_paper_proof_capture_loop safe watcher command",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_default_tiny_live_lane_targets() -> list[str]:
    return list(DEFAULT_TARGET_LANES)


def validate_tiny_live_lane_targets(
    *,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    all_target_lanes: bool = False,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    targets = _target_lanes(
        lane_keys=lane_keys,
        lane_keys_csv=lane_keys_csv,
        all_target_lanes=all_target_lanes,
    )
    blockers: list[str] = []
    if not targets:
        blockers.append("at least one lane key or --all-target-lanes is required")
    if len(set(targets)) != len(targets):
        blockers.append("duplicate target lane keys are not allowed")
    malformed = [lane_key for lane_key in targets if len(lane_key.split("|")) != 4]
    if malformed:
        blockers.append(f"invalid lane key format: {', '.join(malformed)}")
    try:
        controls = load_lane_controls(config_path)
        configured = set((controls.get("lane_map") or {}).keys())
        unknown = [lane_key for lane_key in targets if lane_key not in configured]
        if unknown:
            blockers.append(f"unknown configured lane key: {', '.join(unknown)}")
    except Exception as exc:
        blockers.append(f"lane control config could not be loaded: {exc.__class__.__name__}")
    return {
        "valid": not blockers,
        "target_lanes": targets,
        "blockers": _dedupe(blockers),
    }


def build_lane_mode_apply_commands(target_lanes: list[str]) -> list[str]:
    return [
        " ".join(
            [
                "PYTHONPATH=.",
                ".venv/bin/python -m src.app.hammer_radar.operator.inspect",
                "--log-dir logs/hammer_radar_forward",
                "lane-control-command",
                "--action set-mode",
                f'--lane-key "{lane_key}"',
                "--mode tiny_live",
                "--request-tiny-live",
                "--apply",
                f'--confirm-lane-change "{CONFIRM_LANE_CHANGE_PHRASE}"',
            ]
        )
        for lane_key in target_lanes
    ]


def build_lane_mode_recheck_commands(target_lanes: list[str]) -> list[str]:
    lane_filter = " or ".join(f'.lane_key=="{lane_key}"' for lane_key in target_lanes) or "false"
    return [
        " ".join(
            [
                "PYTHONPATH=.",
                ".venv/bin/python -m src.app.hammer_radar.operator.inspect",
                "--log-dir logs/hammer_radar_forward",
                "lane-control-status",
                f"| jq '.lanes[] | select({lane_filter})'",
            ]
        ),
        *[
            " ".join(
                [
                    "PYTHONPATH=.",
                    ".venv/bin/python -m src.app.hammer_radar.operator.inspect",
                    "--log-dir logs/hammer_radar_forward",
                    "first-tiny-live-lane-execution-gate",
                    f'--lane-key "{lane_key}"',
                ]
            )
            for lane_key in target_lanes
        ],
        " ".join(
            [
                "PYTHONPATH=.",
                ".venv/bin/python -m src.app.hammer_radar.operator.inspect",
                "--log-dir logs/hammer_radar_forward",
                "post-bridge-watcher-proof-capture-recheck",
                "--trace-all-unlocked-lanes",
            ]
        ),
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward binance-readonly-status",
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward live-safety",
        " ".join(
            [
                "PYTHONPATH=.",
                ".venv/bin/python -m src.app.hammer_radar.operator.inspect",
                "--log-dir logs/hammer_radar_forward",
                "fresh-candidate-paper-proof-capture-loop",
                "--watch-all-recommended-lanes",
                "--max-iterations 60",
                "--sleep-seconds 60",
                "--run-watch-loop",
                "--record-watch",
                "--confirm-watch-loop",
                '"I CONFIRM FRESH CANDIDATE PAPER PROOF WATCH ONLY; NO ORDER; NO BINANCE CALL."',
            ]
        ),
    ]


def build_apply_tiny_live_lane_mode_recheck_preview(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    all_target_lanes: bool = False,
    record_recheck: bool = False,
    confirm_recheck: str | None = None,
    include_apply_commands: bool = False,
    include_post_apply_recheck_commands: bool = False,
    config_path: str | Path | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    return build_tiny_live_lane_mode_recheck_status(
        log_dir=log_dir,
        lane_keys=lane_keys,
        lane_keys_csv=lane_keys_csv,
        all_target_lanes=all_target_lanes,
        record_recheck=record_recheck,
        confirm_recheck=confirm_recheck,
        include_apply_commands=include_apply_commands,
        include_post_apply_recheck_commands=include_post_apply_recheck_commands,
        config_path=config_path,
        live_eligibility_matrix=live_eligibility_matrix,
        now=now,
    )


def build_tiny_live_lane_mode_recheck_status(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    all_target_lanes: bool = False,
    record_recheck: bool = False,
    confirm_recheck: str | None = None,
    include_apply_commands: bool = False,
    include_post_apply_recheck_commands: bool = False,
    config_path: str | Path | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_recheck == CONFIRM_TINY_LIVE_LANE_MODE_RECHECK_RECORDING_PHRASE
    try:
        validation = validate_tiny_live_lane_targets(
            lane_keys=lane_keys,
            lane_keys_csv=lane_keys_csv,
            all_target_lanes=all_target_lanes,
            config_path=config_path,
        )
        current_modes = _current_lane_modes(
            target_lanes=validation["target_lanes"],
            log_dir=resolved_log_dir,
            config_path=config_path,
            live_eligibility_matrix=live_eligibility_matrix,
        )
        blockers = list(validation["blockers"])
        safety = dict(SAFETY)
        safety.update(_combined_lane_safety(current_modes))
        if any(safety.get(key) is True for key, expected_false in SAFETY.items() if expected_false is False):
            blockers.append("safety boundary reported a true unsafe flag")
        apply_commands = build_lane_mode_apply_commands(validation["target_lanes"]) if include_apply_commands else []
        recheck_commands = (
            build_lane_mode_recheck_commands(validation["target_lanes"])
            if include_post_apply_recheck_commands
            else []
        )
        any_needs_apply = any(bool(row.get("needs_apply")) for row in current_modes.values())
        status = TINY_LIVE_LANE_MODE_RECHECK_READY
        next_operator_move = RECHECK_TINY_LIVE_GATES
        why = "All target lanes already show tiny_live intent; recheck gates and watcher state."
        if blockers:
            status = TINY_LIVE_LANE_MODE_RECHECK_BLOCKED
            next_operator_move = STOP_SAFETY_BLOCK
            why = "R148 recheck is blocked by target validation or safety state."
        elif any_needs_apply:
            status = TINY_LIVE_LANE_MODE_RECHECK_PREVIEW
            next_operator_move = APPLY_TINY_LIVE_LANE_MODE_ON_MAIN
            why = "Target lanes are eligible runbook targets but still need human-run lane mode apply after merge on main."
        if record_recheck and not confirmation_valid:
            status = TINY_LIVE_LANE_MODE_RECHECK_REJECTED
            next_operator_move = STOP_SAFETY_BLOCK
            why = "Exact R148 recording-only confirmation phrase is required; no recheck/runbook was recorded."
        payload = _payload(
            status=status,
            generated_at=generated_at,
            record_recheck_requested=record_recheck,
            confirmation_valid=confirmation_valid,
            recheck_recorded=False,
            recheck_id=None,
            target_lanes=validation["target_lanes"],
            current_lane_modes=current_modes,
            binance_readonly_summary=_binance_readonly_summary(),
            apply_commands=apply_commands,
            post_apply_recheck_commands=recheck_commands,
            next_operator_move=next_operator_move,
            why=why,
            safety=safety,
        )
        if record_recheck and confirmation_valid and not blockers:
            record = append_tiny_live_lane_mode_recheck_record(payload, log_dir=resolved_log_dir)
            payload.update(
                {
                    "status": TINY_LIVE_LANE_MODE_RECHECK_RECORDED,
                    "recheck_recorded": True,
                    "recheck_id": record["recheck_id"],
                    "next_operator_move": next_operator_move,
                    "ledger_path": str(tiny_live_lane_mode_recheck_records_path(resolved_log_dir)),
                }
            )
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            _payload(
                status=TINY_LIVE_LANE_MODE_RECHECK_ERROR,
                generated_at=generated_at,
                record_recheck_requested=record_recheck,
                confirmation_valid=confirmation_valid,
                recheck_recorded=False,
                recheck_id=None,
                target_lanes=[],
                current_lane_modes={},
                binance_readonly_summary=_binance_readonly_summary(),
                apply_commands=[],
                post_apply_recheck_commands=[],
                next_operator_move=STOP_SAFETY_BLOCK,
                why=f"R148 recheck boundary failed: {exc.__class__.__name__}.",
                safety=dict(SAFETY),
                error=exc.__class__.__name__,
            )
        )


def append_tiny_live_lane_mode_recheck_record(
    payload: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = tiny_live_lane_mode_recheck_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "recheck_id": payload.get("recheck_id") or f"tiny_live_lane_mode_recheck_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": TINY_LIVE_LANE_MODE_RECHECK_RECORDED,
            "target_lanes": list(payload.get("target_lanes") or []),
            "current_lane_modes": dict(payload.get("current_lane_modes") or {}),
            "binance_readonly_summary": dict(payload.get("binance_readonly_summary") or {}),
            "apply_commands": list(payload.get("apply_commands") or []),
            "post_apply_recheck_commands": list(payload.get("post_apply_recheck_commands") or []),
            "expected_after_apply": dict(payload.get("expected_after_apply") or _expected_after_apply()),
            "next_operator_move": payload.get("next_operator_move"),
            "why": payload.get("why"),
            "safety": dict(payload.get("safety") or SAFETY),
            "source_surfaces_used": list(payload.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return record


def load_tiny_live_lane_mode_recheck_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_lane_mode_recheck_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records = read_recent_ndjson_records(path, limit=limit if limit > 0 else 100_000, max_bytes=16_777_216)
    if limit <= 0:
        records = list(reversed(records))
    return [_sanitize(record) for record in records]


def summarize_tiny_live_lane_mode_rechecks(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    move_counts = Counter(str(record.get("next_operator_move") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "next_operator_move_counts": dict(sorted(move_counts.items())),
        "last_recheck_id": records[0].get("recheck_id") if records else None,
        "safety": dict(SAFETY),
    }


def format_tiny_live_lane_mode_recheck_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def tiny_live_lane_mode_recheck_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _payload(
    *,
    status: str,
    generated_at: datetime,
    record_recheck_requested: bool,
    confirmation_valid: bool,
    recheck_recorded: bool,
    recheck_id: str | None,
    target_lanes: list[str],
    current_lane_modes: Mapping[str, Any],
    binance_readonly_summary: Mapping[str, Any],
    apply_commands: list[str],
    post_apply_recheck_commands: list[str],
    next_operator_move: str,
    why: str,
    safety: Mapping[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "generated_at": generated_at.isoformat(),
        "record_recheck_requested": bool(record_recheck_requested),
        "confirmation_valid": bool(confirmation_valid),
        "recheck_recorded": bool(recheck_recorded),
        "recheck_id": recheck_id,
        "target_lanes": list(target_lanes),
        "current_lane_modes": dict(current_lane_modes),
        "binance_readonly_summary": dict(binance_readonly_summary),
        "apply_commands": list(apply_commands),
        "post_apply_recheck_commands": list(post_apply_recheck_commands),
        "expected_after_apply": _expected_after_apply(),
        "next_operator_move": next_operator_move,
        "why": why,
        "do_not_run_yet": [
            "live-connector-submit",
            "any order endpoint",
            "global live flag arming",
        ],
        "safety": dict(safety),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }
    if error:
        payload["error"] = error
    return payload


def _target_lanes(
    *,
    lane_keys: list[str] | None,
    lane_keys_csv: str | None,
    all_target_lanes: bool,
) -> list[str]:
    requested = [*_split_lane_keys(lane_keys_csv), *[str(item).strip() for item in lane_keys or [] if str(item).strip()]]
    if all_target_lanes:
        requested.extend(build_default_tiny_live_lane_targets())
    return _dedupe(requested)


def _current_lane_modes(
    *,
    target_lanes: list[str],
    log_dir: str | Path,
    config_path: str | Path | None,
    live_eligibility_matrix: Mapping[str, Any] | None,
) -> dict[str, Any]:
    controls = load_lane_controls(config_path)
    matrix = live_eligibility_matrix if live_eligibility_matrix is not None else build_live_eligibility_matrix(log_dir=log_dir)
    lane_map = controls.get("lane_map") or {}
    return {
        lane_key: _lane_mode_summary(lane_key, lane_map.get(lane_key), matrix)
        for lane_key in target_lanes
    }


def _lane_mode_summary(lane_key: str, lane: Mapping[str, Any] | None, matrix: Mapping[str, Any]) -> dict[str, Any]:
    current_mode = str((lane or {}).get("mode") or "missing").strip().lower()
    return {
        "current_mode": current_mode,
        "target_mode": TARGET_MODE,
        "needs_apply": current_mode != TARGET_MODE,
        "eligible_future_tiny_live": _eligible_future_tiny_live(lane, matrix),
        "safety": dict(SAFETY),
    }


def _eligible_future_tiny_live(lane: Mapping[str, Any] | None, matrix: Mapping[str, Any]) -> bool:
    if not lane:
        return False
    for row in matrix.get("recommendations") or []:
        if (
            str(row.get("symbol") or lane.get("symbol") or "").strip().upper() in {"", str(lane.get("symbol") or "").strip().upper()}
            and str(row.get("timeframe") or "").strip().lower() == str(lane.get("timeframe") or "").strip().lower()
            and str(row.get("direction") or "").strip().lower() == str(lane.get("direction") or "").strip().lower()
            and str(row.get("entry_mode") or "").strip().lower() == str(lane.get("entry_mode") or "").strip().lower()
        ):
            return str(row.get("recommendation") or "") == ELIGIBLE_FOR_FUTURE_TINY_LIVE
    return False


def _binance_readonly_summary() -> dict[str, Any]:
    status = build_binance_readonly_status()
    return {
        "connector_status": status.get("connector_status"),
        "read_only": bool(status.get("read_only")),
        "api_key_present": bool(status.get("api_key_present")),
        "api_secret_present": bool(status.get("api_secret_present")),
        "live_execution_enabled": False,
        "order_placed": False,
    }


def _expected_after_apply() -> dict[str, Any]:
    return {
        "lane_modes": TARGET_MODE,
        "live_execution_enabled": False,
        "global_kill_switch_remains_authoritative": True,
        "orders_allowed": False,
        "remaining_blockers_likely": [
            "fresh autonomous paper proof missing",
            "fresh normalized candidate missing",
            "global gates not ready",
            "kill switch active",
            "live flags disabled",
        ],
    }


def _combined_lane_safety(current_lane_modes: Mapping[str, Any]) -> dict[str, Any]:
    combined = dict(SAFETY)
    for row in current_lane_modes.values():
        for key, value in dict((row or {}).get("safety") or {}).items():
            if key in combined and combined[key] is False:
                combined[key] = bool(combined[key]) or bool(value)
            elif key in combined and combined[key] is True:
                combined[key] = bool(combined[key]) and bool(value)
    return combined


def _split_lane_keys(value: str | None) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
