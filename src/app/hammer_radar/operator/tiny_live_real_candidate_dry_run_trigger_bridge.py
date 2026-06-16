"""R298 real-candidate dry-run trigger bridge.

This bridge reads the existing fresh trigger watch output and certifies whether
the current real candidate would trigger the already-approved dry-run lane. It
does not accept simulation flags, create executable payloads, submit orders, or
call Binance order/test-order/mutation endpoints.
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
from src.app.hammer_radar.operator.strategy_promotion_watcher import WATCH_FOUND
from src.app.hammer_radar.operator.tiny_live_autonomous_trigger_scheduler_timer_health import (
    build_autonomous_trigger_scheduler_timer_health,
)
from src.app.hammer_radar.operator.tiny_live_dry_run_lane_arming_rehearsal import (
    ALLOWED_LANE_KEYS,
    DRY_RUN_LANE_ARMING_REHEARSAL_SIMULATED_TRIGGER_RECORDED,
    build_tiny_live_dry_run_lane_arming_rehearsal,
    validate_r294_dry_run_lane,
)
from src.app.hammer_radar.operator.tiny_live_fresh_trigger_watch import (
    FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW,
    build_latest_or_not_checked_fresh_trigger_watch,
)
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import LIVE_QUALIFIED
from src.app.hammer_radar.operator.tiny_live_timer_integrated_test_only_matching_trigger_rehearsal import (
    LEDGER_FILENAME as R297_LEDGER_FILENAME,
    TIMER_INTEGRATED_TEST_ONLY_MATCHING_TRIGGER_REHEARSAL_CERTIFIED,
    load_tiny_live_timer_integrated_test_only_matching_trigger_rehearsal_records,
)

EVENT_TYPE = "TINY_LIVE_REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE"
CREATED_BY_PHASE = "R298_REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE"
LEDGER_FILENAME = "tiny_live_real_candidate_dry_run_trigger_bridge.ndjson"

REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT = (
    "REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT"
)
REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED = (
    "REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED"
)
REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED = (
    "REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED"
)

DEFAULT_REQUESTED_LANE_KEY = "BTCUSDT|44m|long|ladder_close_50_618"
REAL_CANDIDATE_SOURCE = "fresh_trigger_watch"
SIMULATED_DRY_RUN_MODE = "REAL_CANDIDATE_SIMULATED_DRY_RUN_ONLY"

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


def build_tiny_live_real_candidate_dry_run_trigger_bridge(
    *,
    lane_key: str | None = None,
    operator_id: str = "local_operator",
    reason: str | None = None,
    log_dir: str | Path | None = None,
    record_real_candidate_dry_run_trigger_bridge: bool = False,
    fresh_trigger_watch_packet: Mapping[str, Any] | None = None,
    timer_health_packet: Mapping[str, Any] | None = None,
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
    fresh_watch = (
        dict(fresh_trigger_watch_packet)
        if isinstance(fresh_trigger_watch_packet, Mapping)
        else build_latest_or_not_checked_fresh_trigger_watch(log_dir=resolved_log_dir)
    )
    candidate = _candidate_from_fresh_watch(fresh_watch)
    current_exists = candidate.get("exists") is True
    current_lane = str(candidate.get("lane_key") or "")
    candidate_matches_requested_lane = bool(
        current_exists and requested_lane and current_lane == requested_lane
    )
    r297_seen = _r297_certified_seen(log_dir=resolved_log_dir)

    blockers = _blockers(
        lane_validation=lane_validation,
        requested_lane=requested_lane,
        candidate=candidate,
        fresh_watch=fresh_watch,
        candidate_matches_requested_lane=candidate_matches_requested_lane,
    )
    lifecycle_probe = _empty_lifecycle_probe()
    if current_exists and candidate_matches_requested_lane and not blockers:
        lifecycle_probe = build_tiny_live_dry_run_lane_arming_rehearsal(
            log_dir=resolved_log_dir,
            lane_key=requested_lane,
            operator_id="r298_real_candidate_bridge",
            reason="R298 in-memory real-candidate dry-run bridge; no submit; no order.",
            record_dry_run_lane_arming_rehearsal=False,
            timer_health_packet=timer_health,
            current_candidate_packet=candidate,
            now=generated_at,
        )
        if (
            lifecycle_probe.get("status")
            != DRY_RUN_LANE_ARMING_REHEARSAL_SIMULATED_TRIGGER_RECORDED
        ):
            blockers.extend(
                str(item)
                for item in lifecycle_probe.get("blockers")
                or ["simulated_dry_run_lifecycle_not_recorded"]
            )

    blockers = _dedupe(blockers)
    simulated_recorded = bool(
        current_exists
        and candidate_matches_requested_lane
        and not blockers
        and lifecycle_probe.get("status")
        == DRY_RUN_LANE_ARMING_REHEARSAL_SIMULATED_TRIGGER_RECORDED
    )
    lifecycle = _lifecycle(lifecycle_probe, enabled=simulated_recorded)
    status = _status(
        current_exists=current_exists,
        simulated_recorded=simulated_recorded,
        blockers=blockers,
    )
    panel = _panel(
        status=status,
        requested_lane=requested_lane,
        candidate=candidate,
        candidate_matches_requested_lane=candidate_matches_requested_lane,
        timer_health=timer_health,
        lifecycle=lifecycle,
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
            "current_real_candidate_exists": current_exists,
            "current_real_candidate_lane_key": current_lane or None,
            "current_real_candidate_signal_id": candidate.get("signal_id"),
            "current_real_candidate_freshness_status": candidate.get("freshness_status"),
            "current_real_candidate_live_qualification_class": candidate.get(
                "live_qualification_class"
            ),
            "candidate_matches_requested_lane": candidate_matches_requested_lane,
            "lane_is_live_qualified": lane_validation.get("lane_is_live_qualified") is True,
            "lane_is_near_miss": lane_validation.get("lane_is_near_miss") is True,
            "lane_is_paper_only": lane_validation.get("lane_is_paper_only") is True,
            "exact_lane_risk_contract": lane_validation.get("exact_lane_risk_contract"),
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
            "timer_active": timer_health.get("timer_active") is True,
            "recent_tick_seen": timer_health.get("recent_tick_seen") is True,
            "recent_tick_count": int(timer_health.get("recent_tick_count") or 0),
            "r297_test_only_path_certified_seen": r297_seen,
            "real_candidate_bridge_supported": True,
            "simulated_dry_run_trigger_recorded": simulated_recorded,
            "simulated_open_record": lifecycle["simulated_open_record"],
            "simulated_protective_orders": lifecycle["simulated_protective_orders"],
            "simulated_close_plan": lifecycle["simulated_close_plan"],
            "simulated_lifecycle_status": lifecycle["simulated_lifecycle_status"],
            "no_matching_candidate_action": "WAIT",
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
            "real_candidate_dry_run_trigger_bridge_panel": panel,
            "record_real_candidate_dry_run_trigger_bridge_requested": bool(
                record_real_candidate_dry_run_trigger_bridge
            ),
            "real_candidate_dry_run_trigger_bridge_recorded": False,
            "fresh_trigger_watch_status": fresh_watch.get("status"),
            "fresh_trigger_watch_packet": fresh_watch,
            "timer_health_packet": timer_health,
            "source_surfaces_used": [
                "src/app/hammer_radar/operator/tiny_live_fresh_trigger_watch.py",
                "src/app/hammer_radar/operator/tiny_live_one_shot_pre_activation_gate.py",
                "src/app/hammer_radar/operator/tiny_live_dry_run_lane_arming_rehearsal.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_loop.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_trigger_scheduler_timer_health.py",
                "src/app/hammer_radar/operator/tiny_live_timer_integrated_test_only_matching_trigger_rehearsal.py",
                "configs/hammer_radar/autonomous_arming_state.json",
                "configs/hammer_radar/tiny_live_risk_contracts.json",
                f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
                f"logs/hammer_radar_forward/{R297_LEDGER_FILENAME}",
            ],
        }
    )
    if record_real_candidate_dry_run_trigger_bridge:
        payload = append_tiny_live_real_candidate_dry_run_trigger_bridge(
            payload,
            log_dir=resolved_log_dir,
        )
    return payload


def build_status_tiny_live_real_candidate_dry_run_trigger_bridge(
    *, lane_key: str | None = None, log_dir: str | Path | None = None
) -> dict[str, Any]:
    return build_tiny_live_real_candidate_dry_run_trigger_bridge(
        lane_key=lane_key,
        log_dir=log_dir,
        operator_id="api_status_read_model",
        reason="R298 safe read-only status; real fresh-trigger-watch candidate only; no record; no submit; no order.",
        record_real_candidate_dry_run_trigger_bridge=False,
    )


def load_latest_tiny_live_real_candidate_dry_run_trigger_bridge(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    records = load_tiny_live_real_candidate_dry_run_trigger_bridge_records(
        log_dir=log_dir,
        limit=1,
    )
    return records[0] if records else {}


def load_tiny_live_real_candidate_dry_run_trigger_bridge_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [
        _sanitize(record)
        for record in read_recent_ndjson_records(path, limit=limit, max_bytes=8_388_608)
    ]


def append_tiny_live_real_candidate_dry_run_trigger_bridge(
    record: Mapping[str, Any], *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    payload = _safe_public_payload(
        {
            **dict(record),
            "real_candidate_dry_run_trigger_bridge_record_id": record.get(
                "real_candidate_dry_run_trigger_bridge_record_id"
            )
            or f"r298_real_candidate_dry_run_trigger_bridge_{uuid4().hex}",
            "real_candidate_dry_run_trigger_bridge_recorded": True,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
        }
    )
    path = Path(get_log_dir(log_dir, use_env=True)) / LEDGER_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def format_tiny_live_real_candidate_dry_run_trigger_bridge_json(
    payload: Mapping[str, Any],
) -> str:
    return json.dumps(_safe_public_payload(payload), sort_keys=True, separators=(",", ":"))


def _candidate_from_fresh_watch(packet: Mapping[str, Any]) -> dict[str, Any]:
    exists = packet.get("current_fresh_candidate_exists") is True
    lane_key = packet.get("current_candidate_lane_key")
    freshness_status = _freshness_status(packet)
    live_class = (
        packet.get("current_candidate_watch_category")
        or packet.get("current_real_candidate_live_qualification_class")
        or (LIVE_QUALIFIED if packet.get("current_candidate_is_live_qualified") is True else None)
    )
    parts = str(lane_key or "").split("|")
    return _sanitize(
        {
            "exists": exists,
            "lane_key": lane_key,
            "signal_id": packet.get("current_candidate_signal_id"),
            "symbol": parts[0] if len(parts) == 4 else packet.get("current_candidate_symbol"),
            "timeframe": packet.get("current_candidate_timeframe")
            or (parts[1] if len(parts) == 4 else None),
            "direction": packet.get("current_candidate_direction")
            or (parts[2] if len(parts) == 4 else None),
            "entry_mode": packet.get("current_candidate_entry_mode")
            or (parts[3] if len(parts) == 4 else None),
            "age_minutes": packet.get("current_candidate_age_minutes"),
            "freshness_status": freshness_status,
            "live_qualification_class": live_class,
            "entry": packet.get("current_candidate_entry"),
            "stop": packet.get("current_candidate_stop"),
            "take_profit": packet.get("current_candidate_take_profit"),
            "source_status": packet.get("status"),
            "packet_event_type": packet.get("event_type"),
        }
    )


def _freshness_status(packet: Mapping[str, Any]) -> str | None:
    explicit = packet.get("current_candidate_freshness_status")
    if explicit:
        return str(explicit)
    if packet.get("current_fresh_candidate_exists") is True:
        return "fresh"
    return None


def _blockers(
    *,
    lane_validation: Mapping[str, Any],
    requested_lane: str,
    candidate: Mapping[str, Any],
    fresh_watch: Mapping[str, Any],
    candidate_matches_requested_lane: bool,
) -> list[str]:
    blockers = list(lane_validation.get("blockers") or [])
    if lane_validation.get("lane_is_live_qualified") is True:
        if lane_validation.get("exact_lane_risk_contract") is None:
            blockers.append("exact_risk_contract_missing")
    else:
        blockers.append("requested_lane_not_live_qualified")
    if not candidate.get("exists"):
        return _dedupe(blockers)
    required_missing = [
        name
        for name in ("lane_key", "signal_id", "timeframe", "direction", "entry_mode")
        if not candidate.get(name)
    ]
    if required_missing:
        blockers.append("candidate_missing_required_fields")
    if not candidate_matches_requested_lane:
        blockers.append("real_candidate_lane_mismatch")
    if not _candidate_is_fresh(candidate):
        blockers.append("candidate_not_fresh")
    if not _candidate_is_live_qualified(candidate, fresh_watch):
        blockers.append("candidate_not_live_qualified")
    if requested_lane and requested_lane not in ALLOWED_LANE_KEYS:
        blockers.append("requested_lane_not_live_qualified")
    return _dedupe(_normalize_blockers(blockers))


def _candidate_is_fresh(candidate: Mapping[str, Any]) -> bool:
    status = str(candidate.get("freshness_status") or "").lower()
    if status in {"expired", "stale", "not_fresh"}:
        return False
    if status:
        return "fresh" in status
    return candidate.get("exists") is True


def _candidate_is_live_qualified(
    candidate: Mapping[str, Any], fresh_watch: Mapping[str, Any]
) -> bool:
    live_class = str(candidate.get("live_qualification_class") or "")
    return bool(
        live_class == LIVE_QUALIFIED
        and (
            fresh_watch.get("current_candidate_is_live_qualified") is True
            or fresh_watch.get("status") == FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW
            or fresh_watch.get("candidate_watch_status") == WATCH_FOUND
        )
    )


def _normalize_blockers(blockers: Sequence[str]) -> list[str]:
    replacements = {
        "near_miss_lane_rejected": "requested_lane_not_live_qualified",
        "paper_only_lane_rejected": "requested_lane_not_live_qualified",
        "lane_not_live_qualified_by_strategy_evidence": "requested_lane_not_live_qualified",
        "exact_lane_risk_contract_missing": "exact_risk_contract_missing",
    }
    return [replacements.get(str(item), str(item)) for item in blockers if str(item)]


def _lifecycle(probe: Mapping[str, Any], *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {
            "simulated_open_record": None,
            "simulated_protective_orders": None,
            "simulated_close_plan": None,
            "simulated_lifecycle_status": "SIMULATED_DRY_RUN_LIFECYCLE_NOT_RECORDED",
        }
    return {
        "simulated_open_record": _with_mode(probe.get("simulated_open_record")),
        "simulated_protective_orders": _with_mode(probe.get("simulated_protective_orders")),
        "simulated_close_plan": _with_mode(probe.get("simulated_close_plan")),
        "simulated_lifecycle_status": "SIMULATED_DRY_RUN_LIFECYCLE_RECORDED",
    }


def _with_mode(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    result = dict(value)
    result["mode"] = SIMULATED_DRY_RUN_MODE
    result["order_placed"] = False
    result["executable_payload_created"] = False
    result["submit_allowed"] = False
    result["final_command_available"] = False
    return _sanitize(result)


def _empty_lifecycle_probe() -> dict[str, Any]:
    return {
        "status": None,
        "blockers": [],
        "simulated_open_record": None,
        "simulated_protective_orders": None,
        "simulated_close_plan": None,
    }


def _status(
    *, current_exists: bool, simulated_recorded: bool, blockers: Sequence[str]
) -> str:
    if blockers:
        return REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED
    if not current_exists and not blockers:
        return REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT
    if simulated_recorded and not blockers:
        return REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED
    return REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_BLOCKED


def _panel(
    *,
    status: str,
    requested_lane: str,
    candidate: Mapping[str, Any],
    candidate_matches_requested_lane: bool,
    timer_health: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    blockers: Sequence[str],
) -> dict[str, Any]:
    if status == REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_CERTIFIED:
        recommended = "REVIEW_REAL_CANDIDATE_SIMULATED_DRY_RUN_LIFECYCLE_KEEP_SUBMIT_DISABLED"
    elif status == REAL_CANDIDATE_DRY_RUN_TRIGGER_BRIDGE_READY_TO_WAIT:
        recommended = "KEEP_WAITING_FOR_REAL_MATCHING_FRESH_LIVE_QUALIFIED_CANDIDATE"
    else:
        recommended = "CLEAR_R298_REAL_CANDIDATE_BRIDGE_BLOCKERS_OR_KEEP_WAITING: " + "; ".join(blockers)
    return _sanitize(
        {
            "status": status,
            "requested_lane_key": requested_lane or None,
            "real_candidate_summary": {
                "exists": candidate.get("exists") is True,
                "lane_key": candidate.get("lane_key"),
                "signal_id": candidate.get("signal_id"),
                "freshness_status": candidate.get("freshness_status"),
                "live_qualification_class": candidate.get("live_qualification_class"),
            },
            "match_status": {
                "candidate_matches_requested_lane": candidate_matches_requested_lane,
                "exact_lane_only": True,
                "no_cross_lane_borrowing": True,
            },
            "dry_run_simulated_lifecycle_summary": {
                "simulated_dry_run_trigger_recorded": lifecycle.get(
                    "simulated_lifecycle_status"
                )
                == "SIMULATED_DRY_RUN_LIFECYCLE_RECORDED",
                "simulated_lifecycle_status": lifecycle.get("simulated_lifecycle_status"),
                "simulated_open_record": lifecycle.get("simulated_open_record"),
                "simulated_protective_orders": lifecycle.get("simulated_protective_orders"),
                "simulated_close_plan": lifecycle.get("simulated_close_plan"),
            },
            "blockers": list(blockers),
            "timer_health": {
                "timer_health_status": timer_health.get("status"),
                "timer_active": timer_health.get("timer_active") is True,
                "recent_tick_seen": timer_health.get("recent_tick_seen") is True,
                "recent_tick_count": int(timer_health.get("recent_tick_count") or 0),
            },
            "recommended_next_operator_move": recommended,
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )


def _r297_certified_seen(*, log_dir: str | Path) -> bool:
    return any(
        record.get("status")
        == TIMER_INTEGRATED_TEST_ONLY_MATCHING_TRIGGER_REHEARSAL_CERTIFIED
        and record.get("simulated_trigger_recorded") is True
        for record in load_tiny_live_timer_integrated_test_only_matching_trigger_rehearsal_records(
            log_dir=log_dir,
            limit=20,
        )
    )


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
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
