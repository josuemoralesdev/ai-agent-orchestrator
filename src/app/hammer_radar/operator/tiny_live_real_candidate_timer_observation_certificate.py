"""R299 real-candidate timer observation certificate.

This module observes the existing dry-run timer/scheduler context and the R298
real-candidate bridge. It does not inject candidates, expose simulation flags,
create executable payloads, submit orders, or call Binance order endpoints.
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
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler import (
    LEDGER_FILENAME as SCHEDULER_LEDGER_FILENAME,
    build_latest_or_idle_autonomous_trigger_scheduler,
    load_tiny_live_autonomous_trigger_scheduler_records,
)
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler_timer_health import (
    build_autonomous_trigger_scheduler_timer_health,
)
from src.app.hammer_radar.operator.tiny_live_dry_run_lane_arming_rehearsal import (
    ALLOWED_LANE_KEYS,
    validate_r294_dry_run_lane,
)
from src.app.hammer_radar.operator.tiny_live_real_candidate_dry_run_trigger_bridge import (
    LEDGER_FILENAME as R298_LEDGER_FILENAME,
    REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED,
    REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED,
    REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT,
    build_status_tiny_live_real_candidate_dry_run_trigger_bridge,
)

EVENT_TYPE = "TINY_LIVE_REAL_CANDIDATE_TIMER_OBSERVATION_CERTIFICATE"
CREATED_BY_PHASE = "R299_REAL_CANDIDATE_TIMER_OBSERVATION_CERTIFICATE"
LEDGER_FILENAME = "tiny_live_real_candidate_timer_observation_certificate.ndjson"

REAL_CANDIDATE_TIMER_OBSERVATION_READY_TO_WAIT_CERTIFIED = (
    "REAL_CANDIDATE_TIMER_OBSERVATION_READY_TO_WAIT_CERTIFIED"
)
REAL_CANDIDATE_TIMER_OBSERVATION_TRIGGER_CERTIFIED = (
    "REAL_CANDIDATE_TIMER_OBSERVATION_TRIGGER_CERTIFIED"
)
REAL_CANDIDATE_TIMER_OBSERVATION_BLOCKED = "REAL_CANDIDATE_TIMER_OBSERVATION_BLOCKED"

DEFAULT_REQUESTED_LANE_KEY = "BTCUSDT|44m|long|ladder_close_50_618"
REAL_CANDIDATE_SOURCE = "fresh_trigger_watch_via_r298_bridge"

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "risk_contract_mutated": False,
    "lane_controls_written": False,
    "live_config_written": False,
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
}


def build_tiny_live_real_candidate_timer_observation_certificate(
    *,
    lane_key: str | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    log_dir: str | Path | None = None,
    record_real_candidate_timer_observation_certificate: bool = False,
    timer_health_packet: Mapping[str, Any] | None = None,
    scheduler_records: Sequence[Mapping[str, Any]] | None = None,
    r298_bridge_packet: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    requested_lane = (
        DEFAULT_REQUESTED_LANE_KEY if lane_key is None else str(lane_key).strip()
    )
    requested_operator_id = str(operator_id or "").strip()
    requested_reason = str(reason or "").strip()
    lane_validation = validate_r294_dry_run_lane(requested_lane)
    timer_health = (
        dict(timer_health_packet)
        if isinstance(timer_health_packet, Mapping)
        else build_autonomous_trigger_scheduler_timer_health(log_dir=resolved_log_dir)
    )
    records = (
        [dict(record) for record in scheduler_records]
        if scheduler_records is not None
        else load_tiny_live_autonomous_trigger_scheduler_records(
            log_dir=resolved_log_dir,
            limit=20,
        )
    )
    scheduler_latest = (
        records[-1]
        if records
        else build_latest_or_idle_autonomous_trigger_scheduler(log_dir=resolved_log_dir)
    )
    r298_bridge = (
        dict(r298_bridge_packet)
        if isinstance(r298_bridge_packet, Mapping)
        else build_status_tiny_live_real_candidate_dry_run_trigger_bridge(
            log_dir=resolved_log_dir,
            lane_key=requested_lane,
        )
    )

    timer_active = timer_health.get("timer_active") is True
    timer_loaded = timer_health.get("timer_loaded") is True
    recent_tick_seen = timer_health.get("recent_tick_seen") is True
    recent_tick_count = int(timer_health.get("recent_tick_count") or 0)
    scheduler_recent_ticks_observed = _scheduler_tick_summary(records)
    scheduler_latest_status = str(scheduler_latest.get("status") or "")
    scheduler_latest_trigger_loop_status = str(
        scheduler_latest.get("trigger_loop_status") or ""
    )
    scheduler_latest_candidate_lane_key = scheduler_latest.get("current_candidate_lane_key")
    r298_bridge_status = str(r298_bridge.get("status") or "")
    r298_bridge_record_seen = bool(
        r298_bridge.get("event_type") == "TINY_LIVE_REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE"
        or r298_bridge.get("real_candidate_dry_run_trigger_bridge_recorded") is True
        or r298_bridge.get("real_candidate_dry_run_trigger_bridge_record_id")
        or r298_bridge_status
    )
    current_exists = r298_bridge.get("current_real_candidate_exists") is True
    current_lane = r298_bridge.get("current_real_candidate_lane_key")
    candidate_matches_requested_lane = r298_bridge.get("candidate_matches_requested_lane") is True
    simulated_dry_run_trigger_recorded = (
        r298_bridge.get("simulated_dry_run_trigger_recorded") is True
    )

    blockers = list(lane_validation.get("blockers") or [])
    if lane_validation.get("lane_is_live_qualified") is not True:
        blockers.append("requested_lane_not_live_qualified")
    if not r298_bridge_record_seen:
        blockers.append("r298_bridge_missing")
    if r298_bridge_status == REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED:
        blockers.extend(str(item) for item in r298_bridge.get("blockers") or [])
    elif r298_bridge_status not in {
        REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT,
        REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED,
    }:
        blockers.append("r298_bridge_status_not_certifiable")
    if not timer_active:
        blockers.append("timer_not_active")
    if not recent_tick_seen or recent_tick_count <= 0:
        blockers.append("timer_recent_tick_missing")
    if not records:
        blockers.append("scheduler_recent_tick_missing")
    blockers = _dedupe(_normalize_blockers(blockers))

    status = _status(r298_bridge_status=r298_bridge_status, blockers=blockers)
    observation_summary = _observation_summary(
        status=status,
        timer_health=timer_health,
        scheduler_latest=scheduler_latest,
        r298_bridge=r298_bridge,
        blockers=blockers,
    )
    panel = _panel(
        status=status,
        requested_lane=requested_lane,
        observation_summary=observation_summary,
        timer_health=timer_health,
        scheduler_latest=scheduler_latest,
        r298_bridge=r298_bridge,
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
            "allowed_lane_keys": list(ALLOWED_LANE_KEYS),
            "lane_is_live_qualified": lane_validation.get("lane_is_live_qualified") is True,
            "exact_lane_only": True,
            "no_cross_lane_borrowing": True,
            "real_candidate_source": REAL_CANDIDATE_SOURCE,
            "test_only": False,
            "fake_candidate_used": False,
            "dry_run_only": True,
            "live_execution_enabled": False,
            "allow_live_orders": False,
            "global_kill_switch": True,
            "timer_health_status": timer_health.get("status"),
            "timer_active": timer_active,
            "timer_loaded": timer_loaded,
            "recent_tick_seen": recent_tick_seen,
            "recent_tick_count": recent_tick_count,
            "scheduler_recent_ticks_observed": scheduler_recent_ticks_observed,
            "scheduler_latest_status": scheduler_latest_status or None,
            "scheduler_latest_trigger_loop_status": (
                scheduler_latest_trigger_loop_status or None
            ),
            "scheduler_latest_candidate_lane_key": scheduler_latest_candidate_lane_key,
            "r298_bridge_status": r298_bridge_status or None,
            "r298_bridge_record_seen": r298_bridge_record_seen,
            "current_real_candidate_exists": current_exists,
            "current_real_candidate_lane_key": current_lane,
            "current_real_candidate_signal_id": r298_bridge.get(
                "current_real_candidate_signal_id"
            ),
            "current_real_candidate_freshness_status": r298_bridge.get(
                "current_real_candidate_freshness_status"
            ),
            "current_real_candidate_live_qualification_class": r298_bridge.get(
                "current_real_candidate_live_qualification_class"
            ),
            "candidate_matches_requested_lane": candidate_matches_requested_lane,
            "simulated_dry_run_trigger_recorded": simulated_dry_run_trigger_recorded,
            "simulated_lifecycle_status": r298_bridge.get("simulated_lifecycle_status"),
            "simulated_open_record": r298_bridge.get("simulated_open_record"),
            "simulated_protective_orders": r298_bridge.get("simulated_protective_orders"),
            "simulated_close_plan": r298_bridge.get("simulated_close_plan"),
            "no_matching_candidate_action": "WAIT",
            "observation_summary": observation_summary,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "executable_payload_created": False,
            "order_payload_created": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "binance_order_endpoint_called": False,
            "binance_test_order_endpoint_called": False,
            "per_signal_operator_approval_required": False,
            "blockers": blockers,
            "safety": dict(SAFETY),
            "real_candidate_timer_observation_certificate_panel": panel,
            "record_real_candidate_timer_observation_certificate_requested": bool(
                record_real_candidate_timer_observation_certificate
            ),
            "real_candidate_timer_observation_certificate_recorded": False,
            "timer_health_packet": timer_health,
            "r298_bridge_packet": r298_bridge,
            "source_surfaces_used": [
                "src/app/hammer_radar/operator/tiny_live_real_candidate_dry_run_trigger_bridge.py",
                "src/app/hammer_radar/operator/tiny_live_fresh_trigger_watch.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_loop.py",
                "src/app/hammer_radar/operator/tiny_live_timer_observed_armed_lane_wait_certificate.py",
                "src/app/hammer_radar/operator/tiny_live_dry_run_lane_arming_rehearsal.py",
                "configs/hammer_radar/autonomous_arming_state.json",
                "configs/hammer_radar/tiny_live_risk_contracts.json",
                f"logs/hammer_radar_forward/{SCHEDULER_LEDGER_FILENAME}",
                f"logs/hammer_radar_forward/{R298_LEDGER_FILENAME}",
                f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
            ],
        }
    )
    if record_real_candidate_timer_observation_certificate:
        payload = append_tiny_live_real_candidate_timer_observation_certificate(
            payload,
            log_dir=resolved_log_dir,
        )
    return payload


def build_status_tiny_live_real_candidate_timer_observation_certificate(
    *, lane_key: str | None = None, log_dir: str | Path | None = None
) -> dict[str, Any]:
    return build_tiny_live_real_candidate_timer_observation_certificate(
        lane_key=lane_key,
        log_dir=log_dir,
        operator_id="api_status_read_model",
        reason="R299 safe read-only status; observe R298 real-candidate bridge and timer context; no record; no submit; no order.",
        record_real_candidate_timer_observation_certificate=False,
    )


def load_latest_tiny_live_real_candidate_timer_observation_certificate(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    records = load_tiny_live_real_candidate_timer_observation_certificate_records(
        log_dir=log_dir,
        limit=1,
    )
    return records[0] if records else {}


def load_tiny_live_real_candidate_timer_observation_certificate_records(
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


def append_tiny_live_real_candidate_timer_observation_certificate(
    record: Mapping[str, Any], *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    payload = _safe_public_payload(
        {
            **dict(record),
            "real_candidate_timer_observation_certificate_record_id": record.get(
                "real_candidate_timer_observation_certificate_record_id"
            )
            or f"r299_real_candidate_timer_observation_certificate_{uuid4().hex}",
            "real_candidate_timer_observation_certificate_recorded": True,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
        }
    )
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def format_tiny_live_real_candidate_timer_observation_certificate_json(
    payload: Mapping[str, Any],
) -> str:
    return json.dumps(_safe_public_payload(payload), sort_keys=True, separators=(",", ":"))


def _status(*, r298_bridge_status: str, blockers: Sequence[str]) -> str:
    if blockers:
        return REAL_CANDIDATE_TIMER_OBSERVATION_BLOCKED
    if r298_bridge_status == REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED:
        return REAL_CANDIDATE_TIMER_OBSERVATION_TRIGGER_CERTIFIED
    if r298_bridge_status == REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT:
        return REAL_CANDIDATE_TIMER_OBSERVATION_READY_TO_WAIT_CERTIFIED
    return REAL_CANDIDATE_TIMER_OBSERVATION_BLOCKED


def _scheduler_tick_summary(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return _sanitize(
        [
            {
                "status": record.get("status"),
                "trigger_loop_status": record.get("trigger_loop_status"),
                "candidate_lane_key": record.get("current_candidate_lane_key"),
                "generated_at": record.get("generated_at"),
                "recorded_at_utc": record.get("recorded_at_utc"),
                "final_command_available": False,
                "submit_allowed": False,
                "real_order_forbidden": True,
            }
            for record in records
        ]
    )


def _observation_summary(
    *,
    status: str,
    timer_health: Mapping[str, Any],
    scheduler_latest: Mapping[str, Any],
    r298_bridge: Mapping[str, Any],
    blockers: Sequence[str],
) -> dict[str, Any]:
    return _sanitize(
        {
            "status": status,
            "timer": {
                "timer_health_status": timer_health.get("status"),
                "timer_active": timer_health.get("timer_active") is True,
                "timer_loaded": timer_health.get("timer_loaded") is True,
                "recent_tick_seen": timer_health.get("recent_tick_seen") is True,
                "recent_tick_count": int(timer_health.get("recent_tick_count") or 0),
            },
            "scheduler": {
                "latest_status": scheduler_latest.get("status"),
                "latest_trigger_loop_status": scheduler_latest.get("trigger_loop_status"),
                "latest_candidate_lane_key": scheduler_latest.get("current_candidate_lane_key"),
            },
            "r298_bridge": {
                "status": r298_bridge.get("status"),
                "current_real_candidate_exists": (
                    r298_bridge.get("current_real_candidate_exists") is True
                ),
                "candidate_matches_requested_lane": (
                    r298_bridge.get("candidate_matches_requested_lane") is True
                ),
                "simulated_dry_run_trigger_recorded": (
                    r298_bridge.get("simulated_dry_run_trigger_recorded") is True
                ),
                "test_only": False,
                "fake_candidate_used": False,
            },
            "blockers": list(blockers),
        }
    )


def _panel(
    *,
    status: str,
    requested_lane: str,
    observation_summary: Mapping[str, Any],
    timer_health: Mapping[str, Any],
    scheduler_latest: Mapping[str, Any],
    r298_bridge: Mapping[str, Any],
    blockers: Sequence[str],
) -> dict[str, Any]:
    if status == REAL_CANDIDATE_TIMER_OBSERVATION_TRIGGER_CERTIFIED:
        recommended = "REVIEW_R298_REAL_CANDIDATE_DRY_RUN_LIFECYCLE_KEEP_SUBMIT_DISABLED"
    elif status == REAL_CANDIDATE_TIMER_OBSERVATION_READY_TO_WAIT_CERTIFIED:
        recommended = "KEEP_TIMER_SCHEDULER_RUNNING_AND_WAIT_FOR_REAL_MATCHING_CANDIDATE"
    else:
        recommended = "CLEAR_R299_TIMER_OR_R298_BRIDGE_BLOCKERS: " + "; ".join(blockers)
    return _safe_public_payload(
        {
            "status": status,
            "requested_lane_key": requested_lane or None,
            "timer_scheduler_observation_summary": {
                "timer_health_status": timer_health.get("status"),
                "timer_active": timer_health.get("timer_active") is True,
                "timer_loaded": timer_health.get("timer_loaded") is True,
                "recent_tick_seen": timer_health.get("recent_tick_seen") is True,
                "recent_tick_count": int(timer_health.get("recent_tick_count") or 0),
                "scheduler_latest_status": scheduler_latest.get("status"),
                "scheduler_latest_trigger_loop_status": scheduler_latest.get(
                    "trigger_loop_status"
                ),
                "scheduler_latest_candidate_lane_key": scheduler_latest.get(
                    "current_candidate_lane_key"
                ),
            },
            "r298_bridge_summary": {
                "status": r298_bridge.get("status"),
                "record_seen": bool(r298_bridge.get("status")),
                "source": REAL_CANDIDATE_SOURCE,
                "test_only": False,
                "fake_candidate_used": False,
            },
            "real_candidate_summary": {
                "exists": r298_bridge.get("current_real_candidate_exists") is True,
                "lane_key": r298_bridge.get("current_real_candidate_lane_key"),
                "signal_id": r298_bridge.get("current_real_candidate_signal_id"),
                "freshness_status": r298_bridge.get("current_real_candidate_freshness_status"),
                "live_qualification_class": r298_bridge.get(
                    "current_real_candidate_live_qualification_class"
                ),
                "candidate_matches_requested_lane": r298_bridge.get(
                    "candidate_matches_requested_lane"
                )
                is True,
            },
            "simulated_lifecycle_summary": {
                "simulated_dry_run_trigger_recorded": r298_bridge.get(
                    "simulated_dry_run_trigger_recorded"
                )
                is True,
                "simulated_lifecycle_status": r298_bridge.get("simulated_lifecycle_status"),
                "simulated_open_record": r298_bridge.get("simulated_open_record"),
                "simulated_protective_orders": r298_bridge.get(
                    "simulated_protective_orders"
                ),
                "simulated_close_plan": r298_bridge.get("simulated_close_plan"),
            },
            "observation_summary": dict(observation_summary),
            "blockers": list(blockers),
            "recommended_next_operator_move": recommended,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )


def _normalize_blockers(blockers: Sequence[str]) -> list[str]:
    replacements = {
        "near_miss_lane_rejected": "requested_lane_not_live_qualified",
        "paper_only_lane_rejected": "requested_lane_not_live_qualified",
        "lane_not_live_qualified_by_strategy_evidence": "requested_lane_not_live_qualified",
        "exact_lane_risk_contract_missing": "exact_risk_contract_missing",
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
