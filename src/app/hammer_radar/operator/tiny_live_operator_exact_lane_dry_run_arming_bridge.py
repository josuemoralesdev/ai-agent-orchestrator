"""R300 operator exact-lane dry-run arming bridge.

This module observes the existing R278 autonomous dry-run arming state and
R298/R299 real-candidate timer surfaces. It never arms, disarms, mutates config,
creates executable payloads, submits orders, or calls Binance endpoints.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_autonomous_armed_dry_run import (
    CONFIG_PATH as AUTONOMOUS_ARMING_CONFIG_PATH,
    DRY_RUN_ARMING_CONFIRMATION_PHRASE,
    DRY_RUN_DISARM_CONFIRMATION_PHRASE,
    load_autonomous_arming_state,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler_timer_health import (
    build_autonomous_trigger_scheduler_timer_health,
)
from src.app.hammer_radar.operator.tiny_live_dry_run_lane_arming_rehearsal import (
    ALLOWED_LANE_KEYS,
    validate_r294_dry_run_lane,
)
from src.app.hammer_radar.operator.tiny_live_real_candidate_dry_run_trigger_bridge import (
    build_status_tiny_live_real_candidate_dry_run_trigger_bridge,
)
from src.app.hammer_radar.operator.tiny_live_real_candidate_timer_observation_certificate import (
    build_tiny_live_real_candidate_timer_observation_certificate,
)

EVENT_TYPE = "TINY_LIVE_OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE"
CREATED_BY_PHASE = "R300_OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE"
LEDGER_FILENAME = "tiny_live_operator_exact_lane_dry_run_arming_bridge.ndjson"

DEFAULT_REQUESTED_LANE_KEY = "BTCUSDT|44m|long|ladder_close_50_618"

OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_NOT_ARMED = (
    "OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_NOT_ARMED"
)
OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_ARMED_CERTIFIED = (
    "OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_ARMED_CERTIFIED"
)
OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_BLOCKED = (
    "OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_BLOCKED"
)

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "risk_contract_mutated": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "codex_arming_performed": False,
    "codex_config_mutation_performed": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "final_command_available": False,
    "submit_allowed": False,
    "submit_attempted": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "leverage_change_called": False,
    "margin_change_called": False,
    "mutation_performed": False,
    "signed_trading_request_created": False,
    "signed_order_request_created": False,
    "signed_request_created": False,
    "signed_url_shown": False,
    "signature_shown": False,
    "secrets_shown": False,
    "secret_values_in_output": False,
    "kill_switch_disabled": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "real_order_forbidden": True,
    "per_signal_operator_approval_required": False,
    "live_execution_enabled": False,
    "allow_live_orders": False,
    "global_kill_switch": True,
}


def build_tiny_live_operator_exact_lane_dry_run_arming_bridge(
    *,
    lane_key: str | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    log_dir: str | Path | None = None,
    record_operator_exact_lane_dry_run_arming_bridge: bool = False,
    autonomous_arming_config_path: str | Path | None = None,
    arming_state_packet: Mapping[str, Any] | None = None,
    timer_health_packet: Mapping[str, Any] | None = None,
    r298_bridge_packet: Mapping[str, Any] | None = None,
    r299_timer_observation_packet: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    requested_lane = (
        DEFAULT_REQUESTED_LANE_KEY if lane_key is None else str(lane_key).strip()
    )
    requested_operator_id = str(operator_id or "").strip()
    requested_reason = str(reason or "").strip()
    arming_path = (
        Path(autonomous_arming_config_path)
        if autonomous_arming_config_path is not None
        else AUTONOMOUS_ARMING_CONFIG_PATH
    )
    arming_state = (
        dict(arming_state_packet)
        if isinstance(arming_state_packet, Mapping)
        else load_autonomous_arming_state(arming_path)
    )
    lane_validation = validate_r294_dry_run_lane(requested_lane)
    timer_health = (
        dict(timer_health_packet)
        if isinstance(timer_health_packet, Mapping)
        else build_autonomous_trigger_scheduler_timer_health(log_dir=resolved_log_dir)
    )
    r298_bridge = (
        dict(r298_bridge_packet)
        if isinstance(r298_bridge_packet, Mapping)
        else build_status_tiny_live_real_candidate_dry_run_trigger_bridge(
            log_dir=resolved_log_dir,
            lane_key=requested_lane,
        )
    )
    r299_timer_observation = (
        dict(r299_timer_observation_packet)
        if isinstance(r299_timer_observation_packet, Mapping)
        else build_tiny_live_real_candidate_timer_observation_certificate(
            log_dir=resolved_log_dir,
            lane_key=requested_lane,
            operator_id="r300_read_only_bridge",
            reason="R300 reads R299 status only; no record; no submit; no order.",
            record_real_candidate_timer_observation_certificate=False,
            timer_health_packet=timer_health,
            r298_bridge_packet=r298_bridge,
        )
    )

    allowed_lane_keys = list(ALLOWED_LANE_KEYS)
    lane_auto_live_enabled_keys = [
        str(item)
        for item in arming_state.get("lane_auto_live_enabled_keys") or []
        if str(item)
    ]
    global_auto_live_enabled = arming_state.get("global_auto_live_enabled") is True
    armed_lane_key = arming_state.get("armed_lane_key")
    allowed_from_state = [
        str(item) for item in arming_state.get("allowed_lane_keys") or [] if str(item)
    ]
    requested_in_allowed = requested_lane in allowed_from_state
    requested_in_lane_enabled = requested_lane in lane_auto_live_enabled_keys
    exact_lane_auto_armed = bool(
        lane_validation.get("lane_is_live_qualified") is True
        and global_auto_live_enabled
        and armed_lane_key == requested_lane
        and requested_in_allowed
        and requested_in_lane_enabled
    )
    any_lane_auto_armed = arming_state.get("any_lane_auto_armed") is True

    blockers = _blockers(
        lane_validation=lane_validation,
        requested_lane=requested_lane,
    )
    status = _status(
        lane_validation=lane_validation,
        exact_lane_auto_armed=exact_lane_auto_armed,
        blockers=blockers,
    )
    operator_manual_action_required = (
        status == OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_NOT_ARMED
    )
    manual_commands = _manual_commands(
        lane_key=requested_lane,
        operator_id=requested_operator_id or "local_operator",
        reason=requested_reason
        or "R300 manual operator dry-run arming only; no Codex arming; no submit; no order.",
    )
    panel = _panel(
        status=status,
        requested_lane=requested_lane,
        arming_state=arming_state,
        r298_bridge=r298_bridge,
        r299_timer_observation=r299_timer_observation,
        timer_health=timer_health,
        manual_commands=manual_commands,
        blockers=blockers,
    )

    payload = _safe_public_payload(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "generated_at": generated_at.isoformat(),
            "status": status,
            "requested_lane_key": requested_lane or None,
            "requested_operator_id": requested_operator_id or None,
            "requested_reason": requested_reason,
            "allowed_lane_keys": allowed_lane_keys,
            "live_qualified_lane_keys": allowed_lane_keys,
            "lane_is_live_qualified": lane_validation.get("lane_is_live_qualified") is True,
            "lane_is_near_miss": lane_validation.get("lane_is_near_miss") is True,
            "lane_is_paper_only": lane_validation.get("lane_is_paper_only") is True,
            "exact_lane_only": True,
            "no_cross_lane_borrowing": True,
            "dry_run_only": True,
            "test_only": False,
            "fake_candidate_used": False,
            "operator_manual_action_required": operator_manual_action_required,
            "codex_arming_performed": False,
            "codex_config_mutation_performed": False,
            "autonomous_arming_config_path": str(arming_path),
            "arming_state_loaded": arming_path.exists()
            or isinstance(arming_state_packet, Mapping),
            "global_auto_live_enabled": global_auto_live_enabled,
            "exact_lane_auto_armed": exact_lane_auto_armed,
            "any_lane_auto_armed": any_lane_auto_armed,
            "armed_lane_key": armed_lane_key,
            "lane_auto_live_enabled_keys": lane_auto_live_enabled_keys,
            "requested_lane_in_allowed_lane_keys": requested_in_allowed,
            "requested_lane_in_lane_auto_live_enabled_keys": requested_in_lane_enabled,
            "current_real_candidate_exists": r298_bridge.get("current_real_candidate_exists")
            is True,
            "current_real_candidate_lane_key": r298_bridge.get(
                "current_real_candidate_lane_key"
            ),
            "r298_bridge_status": r298_bridge.get("status"),
            "r299_timer_observation_status": r299_timer_observation.get("status"),
            "timer_health_status": timer_health.get("status"),
            "timer_active": timer_health.get("timer_active") is True,
            "recent_tick_seen": timer_health.get("recent_tick_seen") is True,
            "recent_tick_count": int(timer_health.get("recent_tick_count") or 0),
            **manual_commands,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "executable_payload_created": False,
            "order_payload_created": False,
            "order_placed": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "per_signal_operator_approval_required": False,
            "blockers": blockers,
            "safety": dict(SAFETY),
            "operator_exact_lane_dry_run_arming_bridge_panel": panel,
            "record_operator_exact_lane_dry_run_arming_bridge_requested": bool(
                record_operator_exact_lane_dry_run_arming_bridge
            ),
            "operator_exact_lane_dry_run_arming_bridge_recorded": False,
            "r298_bridge_packet": r298_bridge,
            "r299_timer_observation_packet": r299_timer_observation,
            "timer_health_packet": timer_health,
            "source_surfaces_used": [
                "src/app/hammer_radar/operator/tiny_live_autonomous_armed_dry_run.py",
                "src/app/hammer_radar/operator/tiny_live_real_candidate_timer_observation_certificate.py",
                "src/app/hammer_radar/operator/tiny_live_real_candidate_dry_run_trigger_bridge.py",
                "src/app/hammer_radar/operator/tiny_live_fresh_trigger_watch.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_loop.py",
                "src/app/hammer_radar/operator/tiny_live_timer_observed_armed_lane_wait_certificate.py",
                "src/app/hammer_radar/operator/tiny_live_dry_run_lane_arming_rehearsal.py",
                "configs/hammer_radar/autonomous_arming_state.json",
                "configs/hammer_radar/tiny_live_risk_contracts.json",
                f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
            ],
        }
    )
    if record_operator_exact_lane_dry_run_arming_bridge:
        payload = append_tiny_live_operator_exact_lane_dry_run_arming_bridge(
            payload,
            log_dir=resolved_log_dir,
        )
    return payload


def build_status_tiny_live_operator_exact_lane_dry_run_arming_bridge(
    *, lane_key: str | None = None, log_dir: str | Path | None = None
) -> dict[str, Any]:
    return build_tiny_live_operator_exact_lane_dry_run_arming_bridge(
        lane_key=lane_key,
        log_dir=log_dir,
        operator_id="api_status_read_model",
        reason="R300 safe read-only status; no record; no arming; no config mutation; no submit; no order.",
        record_operator_exact_lane_dry_run_arming_bridge=False,
    )


def load_tiny_live_operator_exact_lane_dry_run_arming_bridge_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_safe_public_payload(json.loads(line)) for line in handle if line.strip()]
    return [
        _safe_public_payload(record)
        for record in read_recent_ndjson_records(path, limit=limit, max_bytes=8_388_608)
    ]


def append_tiny_live_operator_exact_lane_dry_run_arming_bridge(
    record: Mapping[str, Any], *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    payload = _safe_public_payload(
        {
            **dict(record),
            "operator_exact_lane_dry_run_arming_bridge_record_id": record.get(
                "operator_exact_lane_dry_run_arming_bridge_record_id"
            )
            or f"r300_operator_exact_lane_dry_run_arming_bridge_{uuid4().hex}",
            "operator_exact_lane_dry_run_arming_bridge_recorded": True,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
        }
    )
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def format_tiny_live_operator_exact_lane_dry_run_arming_bridge_json(
    payload: Mapping[str, Any],
) -> str:
    return json.dumps(_safe_public_payload(payload), sort_keys=True, separators=(",", ":"))


def _status(
    *,
    lane_validation: Mapping[str, Any],
    exact_lane_auto_armed: bool,
    blockers: Sequence[str],
) -> str:
    if blockers or lane_validation.get("lane_is_live_qualified") is not True:
        return OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_BLOCKED
    if exact_lane_auto_armed:
        return OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_ARMED_CERTIFIED
    return OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_NOT_ARMED


def _blockers(*, lane_validation: Mapping[str, Any], requested_lane: str) -> list[str]:
    blockers = list(lane_validation.get("blockers") or [])
    if not requested_lane:
        blockers.append("lane_key_required")
    if lane_validation.get("lane_is_near_miss") is True:
        blockers.append("requested_lane_is_near_miss")
    if lane_validation.get("lane_is_paper_only") is True:
        blockers.append("requested_lane_is_paper_only")
    if lane_validation.get("lane_is_live_qualified") is not True:
        blockers.append("requested_lane_not_live_qualified")
    return _dedupe(_normalize_blockers(blockers))


def _manual_commands(*, lane_key: str, operator_id: str, reason: str) -> dict[str, str]:
    prefix = "DO_NOT_RUN_FROM_CODEX MANUAL_OPERATOR_ONLY DRY_RUN_ONLY NO_ORDER:"
    base = (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward "
    )
    safe_reason = reason.replace('"', "'")
    return {
        "manual_operator_arm_command": (
            f"{prefix} {base}tiny-live-autonomous-dry-run-arm-lane "
            f'--lane-key "{lane_key}" --operator-id "{operator_id}" '
            f'--reason "{safe_reason}" '
            f'--confirm-dry-run-autonomous-arming "{DRY_RUN_ARMING_CONFIRMATION_PHRASE}"'
        ),
        "manual_operator_disarm_command": (
            f"{prefix} {base}tiny-live-autonomous-dry-run-disarm-lane "
            f'--lane-key "{lane_key}" --operator-id "{operator_id}" '
            f'--reason "R300 manual operator disarm dry-run arming; no submit; no order." '
            f'--confirm-dry-run-autonomous-disarm "{DRY_RUN_DISARM_CONFIRMATION_PHRASE}"'
        ),
        "manual_operator_status_command": (
            f"{prefix} {base}tiny-live-autonomous-dry-run-arming-status"
        ),
    }


def _panel(
    *,
    status: str,
    requested_lane: str,
    arming_state: Mapping[str, Any],
    r298_bridge: Mapping[str, Any],
    r299_timer_observation: Mapping[str, Any],
    timer_health: Mapping[str, Any],
    manual_commands: Mapping[str, str],
    blockers: Sequence[str],
) -> dict[str, Any]:
    if status == OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_ARMED_CERTIFIED:
        recommended = "KEEP_WAITING_FOR_R298_R299_REAL_MATCHING_CANDIDATE_DRY_RUN_ONLY"
    elif status == OPERATOR_EXACT_LANE_DRY_RUN_ARMING_BRIDGE_NOT_ARMED:
        recommended = "OPERATOR_MAY_MANUALLY_ARM_EXACT_LANE_OUTSIDE_CODEX_IF_DESIRED"
    else:
        recommended = "DO_NOT_ARM_CLEAR_REQUESTED_LANE_BLOCKERS: " + "; ".join(blockers)
    return _safe_public_payload(
        {
            "status": status,
            "requested_lane_key": requested_lane or None,
            "current_arming_state": {
                "global_auto_live_enabled": arming_state.get("global_auto_live_enabled")
                is True,
                "armed_lane_key": arming_state.get("armed_lane_key"),
                "allowed_lane_keys": list(arming_state.get("allowed_lane_keys") or []),
                "lane_auto_live_enabled_keys": list(
                    arming_state.get("lane_auto_live_enabled_keys") or []
                ),
                "any_lane_auto_armed": arming_state.get("any_lane_auto_armed") is True,
            },
            "r298_summary": {
                "status": r298_bridge.get("status"),
                "current_real_candidate_exists": r298_bridge.get(
                    "current_real_candidate_exists"
                )
                is True,
                "current_real_candidate_lane_key": r298_bridge.get(
                    "current_real_candidate_lane_key"
                ),
            },
            "r299_summary": {
                "status": r299_timer_observation.get("status"),
                "timer_active": r299_timer_observation.get("timer_active") is True,
                "recent_tick_seen": r299_timer_observation.get("recent_tick_seen")
                is True,
                "recent_tick_count": int(
                    r299_timer_observation.get("recent_tick_count") or 0
                ),
            },
            "timer_health": {
                "timer_health_status": timer_health.get("status"),
                "timer_active": timer_health.get("timer_active") is True,
                "recent_tick_seen": timer_health.get("recent_tick_seen") is True,
                "recent_tick_count": int(timer_health.get("recent_tick_count") or 0),
            },
            "manual_operator_commands": dict(manual_commands),
            "blockers": list(blockers),
            "recommended_next_operator_move": recommended,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )


def _normalize_blockers(blockers: Sequence[str]) -> list[str]:
    replacements = {
        "near_miss_lane_rejected": "requested_lane_is_near_miss",
        "paper_only_lane_rejected": "requested_lane_is_paper_only",
        "lane_not_live_qualified_by_strategy_evidence": "requested_lane_not_live_qualified",
    }
    return [replacements.get(str(item), str(item)) for item in blockers if str(item)]


def _safe_public_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = _sanitize(dict(payload))
    result["final_command_available"] = False
    result["submit_allowed"] = False
    result["real_order_forbidden"] = True
    result["executable_payload_created"] = False
    result["order_payload_created"] = False
    result["order_placed"] = False
    result["real_order_placed"] = False
    result["execution_attempted"] = False
    result["binance_order_endpoint_called"] = False
    result["binance_test_order_endpoint_called"] = False
    result["per_signal_operator_approval_required"] = False
    result["live_execution_enabled"] = False
    result["allow_live_orders"] = False
    result["global_kill_switch"] = True
    result["test_only"] = False
    result["fake_candidate_used"] = False
    result["dry_run_only"] = True
    result["codex_arming_performed"] = False
    result["codex_config_mutation_performed"] = False
    result["safety"] = dict(SAFETY)
    return result


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            text = str(key).lower()
            if "secret" in text and key not in {"secrets_shown", "secret_values_in_output"}:
                clean[key] = "***REDACTED***" if item else item
                continue
            if "signature" in text and key not in {
                "signature_shown",
                "signed_order_request_created",
                "signed_trading_request_created",
                "signed_request_created",
            }:
                clean[key] = "***REDACTED***" if item else item
                continue
            if "signed_url" in text and key != "signed_url_shown":
                clean[key] = "***REDACTED***" if item else item
                continue
            clean[str(key)] = _sanitize(item)
        return clean
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
