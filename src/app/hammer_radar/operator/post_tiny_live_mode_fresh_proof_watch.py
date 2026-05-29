"""R149 post tiny-live mode fresh proof watch prep.

This module records only a safe watch-prep runbook after target lanes have
been moved to tiny_live intent. It never starts the watcher, calls Binance,
creates payloads, mutates env/config, or changes global live flags.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.apply_tiny_live_lane_mode_recheck import (
    DEFAULT_TARGET_LANES,
    TARGET_MODE,
    validate_tiny_live_lane_targets,
)
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.binance_readonly import build_binance_readonly_status
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import (
    SAFETY_FALSE,
    build_fast_lane_status_global_gate_sentinel,
    evaluate_lane_permission,
    load_lane_controls,
)
from src.app.hammer_radar.operator.post_bridge_watcher_proof_capture_recheck import (
    build_post_bridge_watcher_proof_capture_recheck,
)

POST_TINY_LIVE_MODE_WATCH_PREVIEW = "POST_TINY_LIVE_MODE_WATCH_PREVIEW"
POST_TINY_LIVE_MODE_WATCH_READY = "POST_TINY_LIVE_MODE_WATCH_READY"
POST_TINY_LIVE_MODE_WATCH_REJECTED = "POST_TINY_LIVE_MODE_WATCH_REJECTED"
POST_TINY_LIVE_MODE_WATCH_RECORDED = "POST_TINY_LIVE_MODE_WATCH_RECORDED"
POST_TINY_LIVE_MODE_WATCH_BLOCKED = "POST_TINY_LIVE_MODE_WATCH_BLOCKED"
POST_TINY_LIVE_MODE_WATCH_ERROR = "POST_TINY_LIVE_MODE_WATCH_ERROR"

RUN_SAFE_FRESH_PROOF_WATCH = "RUN_SAFE_FRESH_PROOF_WATCH"
WAIT_FOR_FRESH_NORMALIZED_CANDIDATE = "WAIT_FOR_FRESH_NORMALIZED_CANDIDATE"
STOP_SAFETY_BLOCK = "STOP_SAFETY_BLOCK"

EVENT_TYPE = "POST_TINY_LIVE_MODE_FRESH_PROOF_WATCH"
LEDGER_FILENAME = "post_tiny_live_mode_fresh_proof_watch.ndjson"
CONFIRM_POST_TINY_LIVE_MODE_WATCH_RECORDING_PHRASE = (
    "I CONFIRM POST TINY LIVE MODE WATCH RECORDING ONLY; NO ORDER; NO BINANCE CALL."
)

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "network_allowed": False,
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
    "operator.lane_control.evaluate_lane_permission",
    "operator.lane_control.build_fast_lane_status_global_gate_sentinel",
    "operator.binance_readonly.build_binance_readonly_status",
    "operator.post_bridge_watcher_proof_capture_recheck.build_post_bridge_watcher_proof_capture_recheck",
    "operator.fresh_candidate_paper_proof_capture_loop safe watcher command",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_post_tiny_live_mode_fresh_proof_watch_preview(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    all_target_lanes: bool = False,
    include_watch_command: bool = False,
    record_watch_prep: bool = False,
    confirm_watch_prep: str | None = None,
    config_path: str | Path | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_watch_prep == CONFIRM_POST_TINY_LIVE_MODE_WATCH_RECORDING_PHRASE
    try:
        validation = validate_tiny_live_lane_targets(
            lane_keys=lane_keys,
            lane_keys_csv=lane_keys_csv,
            all_target_lanes=all_target_lanes,
            config_path=config_path,
        )
        lane_modes = build_post_tiny_live_mode_lane_state(
            target_lanes=validation["target_lanes"],
            log_dir=resolved_log_dir,
            config_path=config_path,
            live_eligibility_matrix=live_eligibility_matrix,
        )
        blockers = list(validation["blockers"])
        blockers.extend(_lane_state_blockers(lane_modes))
        safety = dict(SAFETY)
        if _unsafe_safety_seen(safety):
            blockers.append("safety boundary reported a true unsafe flag")

        status = POST_TINY_LIVE_MODE_WATCH_READY if not blockers else POST_TINY_LIVE_MODE_WATCH_BLOCKED
        next_operator_move = RUN_SAFE_FRESH_PROOF_WATCH if not blockers else STOP_SAFETY_BLOCK
        why = (
            "Target lanes are tiny_live intent only; run the safe fresh proof watcher and wait for a fresh normalized candidate."
            if not blockers
            else "R149 watch prep is blocked by target lane state or safety state."
        )
        if record_watch_prep and not confirmation_valid:
            status = POST_TINY_LIVE_MODE_WATCH_REJECTED
            next_operator_move = STOP_SAFETY_BLOCK
            why = "Exact R149 recording-only confirmation phrase is required; no watch prep was recorded."

        payload = _payload(
            status=status,
            generated_at=generated_at,
            record_watch_prep_requested=record_watch_prep,
            confirmation_valid=confirmation_valid,
            watch_prep_recorded=False,
            watch_prep_id=None,
            target_lanes=validation["target_lanes"],
            lane_modes=lane_modes,
            binance_readonly_summary=_binance_readonly_summary(),
            post_bridge_recheck_summary=_post_bridge_recheck_summary(log_dir=resolved_log_dir),
            safe_watch_command=build_post_tiny_live_mode_safe_watch_command() if include_watch_command else "",
            post_watch_recheck_commands=build_post_tiny_live_mode_recheck_commands(validation["target_lanes"]),
            next_operator_move=next_operator_move,
            why=why,
            safety=safety,
        )
        if record_watch_prep and confirmation_valid and not blockers:
            record = append_post_tiny_live_mode_watch_record(payload, log_dir=resolved_log_dir)
            payload.update(
                {
                    "status": POST_TINY_LIVE_MODE_WATCH_RECORDED,
                    "watch_prep_recorded": True,
                    "watch_prep_id": record["watch_prep_id"],
                    "ledger_path": str(post_tiny_live_mode_watch_records_path(resolved_log_dir)),
                }
            )
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator boundary
        return _sanitize(
            _payload(
                status=POST_TINY_LIVE_MODE_WATCH_ERROR,
                generated_at=generated_at,
                record_watch_prep_requested=record_watch_prep,
                confirmation_valid=confirmation_valid,
                watch_prep_recorded=False,
                watch_prep_id=None,
                target_lanes=[],
                lane_modes={},
                binance_readonly_summary=_binance_readonly_summary(),
                post_bridge_recheck_summary={"status": "ERROR", "error": exc.__class__.__name__},
                safe_watch_command=build_post_tiny_live_mode_safe_watch_command() if include_watch_command else "",
                post_watch_recheck_commands=[],
                next_operator_move=STOP_SAFETY_BLOCK,
                why=f"R149 watch prep boundary failed: {exc.__class__.__name__}.",
                safety=dict(SAFETY),
                error=exc.__class__.__name__,
            )
        )


def build_post_tiny_live_mode_lane_state(
    *,
    target_lanes: list[str] | None = None,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    controls = load_lane_controls(config_path)
    lane_map = controls.get("lane_map") or {}
    targets = list(target_lanes or DEFAULT_TARGET_LANES)
    result: dict[str, Any] = {}
    sentinel = build_fast_lane_status_global_gate_sentinel()
    for lane_key in targets:
        lane = lane_map.get(lane_key)
        if not isinstance(lane, Mapping):
            result[lane_key] = {
                "mode": "missing",
                "is_target_tiny_live": False,
                "status": "LANE_BLOCKED",
                "blockers": ["target lane is not configured"],
                "safety": dict(SAFETY),
            }
            continue
        permission = evaluate_lane_permission(
            lane.get("symbol"),
            lane.get("timeframe"),
            lane.get("direction"),
            lane.get("entry_mode"),
            controls=controls,
            live_eligibility_matrix=live_eligibility_matrix,
            global_gate=sentinel,
            log_dir=log_dir,
        )
        mode = str(permission.get("mode") or lane.get("mode") or "").strip().lower()
        blockers = list(permission.get("blockers") or [])
        if mode != TARGET_MODE:
            blockers.append(f"target lane mode is not tiny_live: {mode or 'MISSING'}")
        result[lane_key] = {
            "mode": mode,
            "is_target_tiny_live": mode == TARGET_MODE,
            "status": permission.get("status"),
            "blockers": _dedupe([str(item) for item in blockers if item]),
            "safety": dict(permission.get("safety") or SAFETY),
        }
    return result


def build_post_tiny_live_mode_safe_watch_command() -> str:
    return " ".join(
        [
            "PYTHONPATH=.",
            ".venv/bin/python -m src.app.hammer_radar.operator.inspect",
            "--log-dir logs/hammer_radar_forward",
            "fresh-candidate-paper-proof-capture-loop",
            "--watch-all-recommended-lanes",
            "--max-iterations 720",
            "--sleep-seconds 60",
            "--latest-signals 250",
            "--iteration-timeout-seconds 30",
            "--heartbeat-every 1",
            "--run-watch-loop",
            "--record-watch",
            "--confirm-watch-loop",
            '"I CONFIRM FRESH CANDIDATE PAPER PROOF WATCH ONLY; NO ORDER; NO BINANCE CALL."',
        ]
    )


def build_post_tiny_live_mode_recheck_commands(target_lanes: list[str] | None = None) -> list[str]:
    lanes = list(target_lanes or DEFAULT_TARGET_LANES)
    return [
        " ".join(
            [
                "PYTHONPATH=.",
                ".venv/bin/python -m src.app.hammer_radar.operator.inspect",
                "--log-dir logs/hammer_radar_forward",
                "post-bridge-watcher-proof-capture-recheck",
                "--trace-all-unlocked-lanes",
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
            for lane_key in lanes
        ],
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward live-safety",
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward binance-readonly-status",
    ]


def append_post_tiny_live_mode_watch_record(
    payload: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = post_tiny_live_mode_watch_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "watch_prep_id": payload.get("watch_prep_id") or f"post_tiny_live_watch_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": POST_TINY_LIVE_MODE_WATCH_RECORDED,
            "target_lanes": list(payload.get("target_lanes") or []),
            "lane_modes": dict(payload.get("lane_modes") or {}),
            "binance_readonly_summary": dict(payload.get("binance_readonly_summary") or {}),
            "post_bridge_recheck_summary": dict(payload.get("post_bridge_recheck_summary") or {}),
            "safe_watch_command": payload.get("safe_watch_command"),
            "post_watch_recheck_commands": list(payload.get("post_watch_recheck_commands") or []),
            "next_operator_move": payload.get("next_operator_move"),
            "why": payload.get("why"),
            "do_not_run_yet": list(payload.get("do_not_run_yet") or []),
            "safety": dict(payload.get("safety") or SAFETY),
            "source_surfaces_used": list(payload.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return record


def load_post_tiny_live_mode_watch_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = post_tiny_live_mode_watch_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records = read_recent_ndjson_records(path, limit=limit if limit > 0 else 100_000, max_bytes=16_777_216)
    if limit <= 0:
        records = list(reversed(records))
    return [_sanitize(record) for record in records]


def summarize_post_tiny_live_mode_watch_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    move_counts = Counter(str(record.get("next_operator_move") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "next_operator_move_counts": dict(sorted(move_counts.items())),
        "last_watch_prep_id": records[0].get("watch_prep_id") if records else None,
        "safety": dict(SAFETY),
    }


def format_post_tiny_live_mode_fresh_proof_watch_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def post_tiny_live_mode_watch_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _payload(
    *,
    status: str,
    generated_at: datetime,
    record_watch_prep_requested: bool,
    confirmation_valid: bool,
    watch_prep_recorded: bool,
    watch_prep_id: str | None,
    target_lanes: list[str],
    lane_modes: Mapping[str, Any],
    binance_readonly_summary: Mapping[str, Any],
    post_bridge_recheck_summary: Mapping[str, Any],
    safe_watch_command: str,
    post_watch_recheck_commands: list[str],
    next_operator_move: str,
    why: str,
    safety: Mapping[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "generated_at": generated_at.isoformat(),
        "record_watch_prep_requested": bool(record_watch_prep_requested),
        "confirmation_valid": bool(confirmation_valid),
        "watch_prep_recorded": bool(watch_prep_recorded),
        "watch_prep_id": watch_prep_id,
        "target_lanes": list(target_lanes),
        "lane_modes": dict(lane_modes),
        "binance_readonly_summary": dict(binance_readonly_summary),
        "post_bridge_recheck_summary": dict(post_bridge_recheck_summary),
        "safe_watch_command": safe_watch_command,
        "post_watch_recheck_commands": list(post_watch_recheck_commands),
        "next_operator_move": next_operator_move,
        "why": why,
        "do_not_run_yet": [
            "live-connector-submit",
            "any order endpoint",
            "global live flag arming",
            "kill switch disable",
        ],
        "safety": dict(safety),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }
    if error:
        payload["error"] = error
    return payload


def _binance_readonly_summary() -> dict[str, Any]:
    status = build_binance_readonly_status()
    return {
        "connector_status": status.get("connector_status"),
        "read_only": bool(status.get("read_only")),
        "api_key_present": bool(status.get("api_key_present")),
        "api_secret_present": bool(status.get("api_secret_present")),
        "connector_mode_present": bool(status.get("connector_mode")),
        "live_execution_enabled": False,
        "order_placed": False,
        "network_used": False,
        "secrets_shown": False,
        "blockers": list(status.get("blockers") or []),
        "warnings": list(status.get("warnings") or []),
    }


def _post_bridge_recheck_summary(*, log_dir: str | Path) -> dict[str, Any]:
    payload = build_post_bridge_watcher_proof_capture_recheck(
        log_dir=log_dir,
        trace_all_unlocked_lanes=True,
        record_recheck=False,
    )
    visibility = payload.get("normalized_candidate_visibility")
    readiness = payload.get("paper_capture_readiness")
    return {
        "status": payload.get("status"),
        "next_operator_move": payload.get("next_operator_move"),
        "why": payload.get("why"),
        "normalized_candidate_visibility": visibility if isinstance(visibility, Mapping) else {},
        "paper_capture_readiness": readiness if isinstance(readiness, Mapping) else {},
        "safety": dict(payload.get("safety") or SAFETY),
    }


def _lane_state_blockers(lane_modes: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for lane_key, state in lane_modes.items():
        if not isinstance(state, Mapping):
            blockers.append(f"{lane_key}: lane state missing")
            continue
        if state.get("mode") != TARGET_MODE:
            blockers.append(f"{lane_key}: target lane mode is not tiny_live")
        if state.get("is_target_tiny_live") is not True:
            blockers.append(f"{lane_key}: target tiny_live state is false")
    return _dedupe(blockers)


def _unsafe_safety_seen(safety: Mapping[str, Any]) -> bool:
    for key, expected in SAFETY.items():
        value = safety.get(key)
        if expected is False and value is True:
            return True
        if expected is True and value is False:
            return True
    return False


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


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
