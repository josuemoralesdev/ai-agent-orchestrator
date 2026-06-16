"""R286 fresh live-qualified trigger watch packet.

This surface is alert/visibility only. It reuses the R285 pre-activation gate
and current live-qualified candidate watch, but never submits, signs, mutates
controls, mutates risk contracts, or makes a final live command available.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.strategy_promotion_watcher import (
    WATCH_BLOCKED_NEAR_MISS,
    WATCH_BLOCKED_PAPER_ONLY,
    WATCH_FOUND,
    WATCH_WAIT,
)
from src.app.hammer_radar.operator.tiny_live_one_shot_pre_activation_gate import (
    APPROVED_LIVE_QUALIFIED_LANES,
    ONE_SHOT_PRE_ACTIVATION_BLOCKED,
    ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED,
    ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER,
    ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER,
    build_not_checked_pre_activation_gate_packet,
    build_tiny_live_one_shot_pre_activation_gate,
)
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import (
    LIVE_QUALIFIED,
    NEAR_MISS_INCUBATOR,
    PAPER_ONLY,
)

EVENT_TYPE = "TINY_LIVE_FRESH_LIVE_QUALIFIED_TRIGGER_WATCH"
CREATED_BY_PHASE = "R286_FRESH_LIVE_QUALIFIED_TRIGGER_WATCH_AND_ALERT_PACKET"
LEDGER_FILENAME = "tiny_live_fresh_trigger_watch.ndjson"

FRESH_TRIGGER_WAIT = "FRESH_TRIGGER_WAIT"
FRESH_TRIGGER_BLOCKED = "FRESH_TRIGGER_BLOCKED"
FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW = "FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW"
OPERATOR_ROLE = "arms_disarms_tunes_risk_not_per_signal_approval"
MACHINE_ROLE = "auto_triggers_when_armed_and_all_gates_open"
FRESH_TRIGGER_NOT_CHECKED = "FRESH_TRIGGER_NOT_CHECKED"

WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE = "WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE"
RUN_ONE_SHOT_DRY_RUN_TRIGGER_PACKET_OR_ARMING_REVIEW = (
    "RUN_ONE_SHOT_DRY_RUN_TRIGGER_PACKET_OR_ARMING_REVIEW"
)
STRATEGY_LAB_PAPER_REVIEW = "STRATEGY_LAB_PAPER_REVIEW"
RUN_READONLY_PRE_ACTIVATION_CHECKS = "RUN_READONLY_PRE_ACTIVATION_CHECKS"
CLEAR_PRE_ACTIVATION_BLOCKERS = "CLEAR_PRE_ACTIVATION_BLOCKERS"

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
}


def build_tiny_live_fresh_trigger_watch(
    *,
    log_dir: str | Path | None = None,
    fetch_binance_readonly_precision_mark_price: bool = False,
    confirm_tiny_live_binance_readonly_fetch: str | None = None,
    fetch_binance_readonly_account_position: bool = False,
    confirm_binance_readonly_account_position: str | None = None,
    load_discovered_binance_readonly_env: bool = False,
    binance_readonly_env_file: str | Path | None = None,
    record_trigger_watch: bool = False,
    operator_id: str = "local_operator",
    reason: str | None = None,
    send_telegram: bool = False,
    risk_contract_config_path: str | Path | None = None,
    autonomous_arming_config_path: str | Path | None = None,
    pre_activation_packet: Mapping[str, Any] | None = None,
    candidate_watch: Mapping[str, Any] | None = None,
    binance_readiness: Mapping[str, Any] | None = None,
    post_manual_verification: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    env: Mapping[str, str] | None = None,
    urlopen_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    fetch_requested = bool(
        fetch_binance_readonly_precision_mark_price
        or fetch_binance_readonly_account_position
        or load_discovered_binance_readonly_env
        or binance_readonly_env_file is not None
    )

    if pre_activation_packet is not None:
        pre_activation = dict(pre_activation_packet)
    elif fetch_requested or candidate_watch is not None or binance_readiness is not None or post_manual_verification is not None:
        pre_activation = build_tiny_live_one_shot_pre_activation_gate(
            log_dir=resolved_log_dir,
            fetch_binance_readonly_precision_mark_price=fetch_binance_readonly_precision_mark_price,
            confirm_tiny_live_binance_readonly_fetch=confirm_tiny_live_binance_readonly_fetch,
            fetch_binance_readonly_account_position=fetch_binance_readonly_account_position,
            confirm_binance_readonly_account_position=confirm_binance_readonly_account_position,
            load_discovered_binance_readonly_env=load_discovered_binance_readonly_env,
            binance_readonly_env_file=binance_readonly_env_file,
            risk_contract_config_path=risk_contract_config_path,
            autonomous_arming_config_path=autonomous_arming_config_path,
            candidate_watch=candidate_watch,
            binance_readiness=binance_readiness,
            post_manual_verification=post_manual_verification,
            now=generated_at,
            env=env,
            urlopen_func=urlopen_func,
        )
    else:
        pre_activation = build_not_checked_pre_activation_gate_packet(log_dir=resolved_log_dir)

    watch = (
        dict(candidate_watch)
        if candidate_watch is not None
        else dict(pre_activation.get("candidate_watch") or {})
    )
    candidate = _current_candidate(pre_activation, watch)
    evidence = _strategy_evidence(pre_activation, watch)
    candidate_alert = _candidate_alert(pre_activation, watch)
    candidate_status = str(candidate_alert.get("status") or pre_activation.get("candidate_watch_status") or WATCH_WAIT)
    live_class = str(
        evidence.get("live_qualification_class")
        or evidence.get("watch_category")
        or pre_activation.get("current_candidate_watch_category")
        or ""
    )
    lane_key = str(candidate.get("lane_key") or pre_activation.get("current_candidate_lane_key") or "")
    blockers = _decision_blockers(
        pre_activation=pre_activation,
        candidate=candidate,
        candidate_status=candidate_status,
        live_class=live_class,
        lane_key=lane_key,
    )
    status = _status(pre_activation, candidate, candidate_status, live_class, blockers)
    next_required_step = _next_required_step(status)
    recommended_operator_move = _recommended_operator_move(status, candidate_status, live_class)
    alert_should_send = bool(send_telegram and status == FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW)
    telegram_payload = _telegram_payload(
        status=status,
        candidate=candidate,
        pre_activation=pre_activation,
        next_required_step=next_required_step,
        alert_should_send=alert_should_send,
    )
    autonomous_status = pre_activation.get("autonomous_dry_run_arming_status")
    autonomous_status = autonomous_status if isinstance(autonomous_status, Mapping) else {}

    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "generated_at": generated_at.isoformat(),
            "operator_role": OPERATOR_ROLE,
            "machine_role": MACHINE_ROLE,
            "per_signal_operator_approval_required": False,
            "alert_is_visibility_only": True,
            "approved_live_qualified_lanes": sorted(APPROVED_LIVE_QUALIFIED_LANES),
            "status": status,
            "pre_activation_status": pre_activation.get("status"),
            "pre_activation_ready_to_wait": pre_activation.get("status")
            in {
                ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER,
                ONE_SHOT_PRE_ACTIVATION_READY_FOR_DRY_RUN_TRIGGER,
            },
            "binance_readiness_ready": pre_activation.get("binance_readiness_ready") is True,
            "wallet_ready": pre_activation.get("wallet_ready") is True,
            "leverage_margin_ready": pre_activation.get("leverage_margin_ready") is True,
            "no_conflicting_position": pre_activation.get("no_conflicting_position") is True,
            "current_fresh_candidate_exists": bool(candidate),
            "current_candidate_lane_key": lane_key or None,
            "current_candidate_signal_id": candidate.get("signal_id"),
            "current_candidate_timeframe": candidate.get("timeframe"),
            "current_candidate_direction": candidate.get("direction"),
            "current_candidate_entry_mode": candidate.get("entry_mode"),
            "current_candidate_age_minutes": _number(candidate.get("age_minutes")),
            "current_candidate_entry": _number(candidate.get("entry")),
            "current_candidate_stop": _number(candidate.get("stop")),
            "current_candidate_take_profit": _number(candidate.get("take_profit")),
            "current_candidate_is_live_qualified": _candidate_is_live_qualified(
                candidate_status, live_class
            ),
            "current_candidate_watch_category": live_class or None,
            "approved_lane_match": bool(lane_key and lane_key in APPROVED_LIVE_QUALIFIED_LANES),
            "exact_lane_risk_contract_found": pre_activation.get("exact_lane_risk_contract_found") is True,
            "exact_lane_risk_contract_valid": pre_activation.get("exact_lane_risk_contract_valid") is True,
            "protective_triplet_preview_available": (
                pre_activation.get("protective_triplet_preview_available") is True
            ),
            "protective_triplet_preview_valid": (
                pre_activation.get("protective_triplet_preview_valid") is True
            ),
            "autonomous_dry_run_status": autonomous_status.get("status"),
            "autonomous_dry_run_blockers": list(autonomous_status.get("blockers") or []),
            "next_required_step": next_required_step,
            "recommended_operator_move": recommended_operator_move,
            "alert_should_send": alert_should_send,
            "telegram_compatible_payload": telegram_payload,
            "telegram_send_result": {
                "send_requested": bool(send_telegram),
                "sent": False,
                "status": "prepared_not_sent" if not send_telegram else "send_not_implemented_by_r286",
                "secrets_shown": False,
            },
            "record_trigger_watch_requested": bool(record_trigger_watch),
            "trigger_watch_recorded": False,
            "operator_intent": {
                "operator_id": str(operator_id or "local_operator"),
                "reason": str(reason or ""),
                "record_only": True,
                "visibility_only": True,
            },
            "pre_activation_packet": pre_activation,
            "candidate_watch": watch,
            "blockers": blockers,
            "fresh_trigger_watch_panel": _panel(
                status=status,
                candidate=candidate,
                pre_activation=pre_activation,
                next_required_step=next_required_step,
                telegram_payload=telegram_payload,
            ),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "safety": _merged_safety(pre_activation),
            "source_surfaces_used": [
                "src/app/hammer_radar/operator/tiny_live_one_shot_pre_activation_gate.py",
                "src/app/hammer_radar/operator/tiny_live_autonomous_armed_dry_run.py",
                "src/app/hammer_radar/operator/strategy_promotion_watcher.py",
                "configs/hammer_radar/tiny_live_risk_contracts.json",
                "configs/hammer_radar/autonomous_arming_state.json",
                f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
            ],
        }
    )
    if record_trigger_watch:
        payload = append_tiny_live_fresh_trigger_watch(payload, log_dir=resolved_log_dir)
    return payload


def load_latest_tiny_live_fresh_trigger_watch(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_tiny_live_fresh_trigger_watch_records(log_dir=log_dir, limit=1)
    return records[0] if records else {}


def load_tiny_live_fresh_trigger_watch_records(
    *, log_dir: str | Path | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    path = tiny_live_fresh_trigger_watch_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=8_388_608)]


def append_tiny_live_fresh_trigger_watch(
    record: Mapping[str, Any], *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    payload = _sanitize(
        {
            **dict(record),
            "trigger_watch_record_id": record.get("trigger_watch_record_id")
            or f"r286_fresh_trigger_watch_{uuid4().hex}",
            "trigger_watch_recorded": True,
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "safety": _merged_safety(record),
        }
    )
    path = tiny_live_fresh_trigger_watch_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def tiny_live_fresh_trigger_watch_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_fresh_trigger_watch_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def build_latest_or_not_checked_fresh_trigger_watch(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    latest = load_latest_tiny_live_fresh_trigger_watch(log_dir=log_dir)
    if latest:
        latest["final_command_available"] = False
        latest["submit_allowed"] = False
        latest["real_order_forbidden"] = True
        latest["safety"] = _merged_safety(latest)
        return _sanitize(latest)
    return build_tiny_live_fresh_trigger_watch(log_dir=log_dir)


def _status(
    pre_activation: Mapping[str, Any],
    candidate: Mapping[str, Any],
    candidate_status: str,
    live_class: str,
    blockers: list[str],
) -> str:
    pre_status = str(pre_activation.get("status") or "")
    if pre_status == ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED:
        return FRESH_TRIGGER_NOT_CHECKED
    if pre_status == ONE_SHOT_PRE_ACTIVATION_BLOCKED and "pre_activation_not_ready" in blockers:
        return FRESH_TRIGGER_BLOCKED
    if not candidate:
        if pre_status == ONE_SHOT_PRE_ACTIVATION_READY_TO_WAIT_FOR_TRIGGER:
            return FRESH_TRIGGER_WAIT
        return FRESH_TRIGGER_BLOCKED
    if candidate_status in {WATCH_BLOCKED_PAPER_ONLY, WATCH_BLOCKED_NEAR_MISS} or live_class in {
        PAPER_ONLY,
        NEAR_MISS_INCUBATOR,
    }:
        return FRESH_TRIGGER_BLOCKED
    if not blockers and _candidate_is_live_qualified(candidate_status, live_class):
        return FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW
    return FRESH_TRIGGER_BLOCKED


def _decision_blockers(
    *,
    pre_activation: Mapping[str, Any],
    candidate: Mapping[str, Any],
    candidate_status: str,
    live_class: str,
    lane_key: str,
) -> list[str]:
    blockers: list[str] = []
    pre_status = str(pre_activation.get("status") or "")
    if pre_status in {ONE_SHOT_PRE_ACTIVATION_BLOCKED, ONE_SHOT_PRE_ACTIVATION_NOT_CHECKED}:
        blockers.append("pre_activation_not_ready")
    if not candidate:
        return _dedupe(blockers)
    if candidate_status == WATCH_BLOCKED_PAPER_ONLY or live_class == PAPER_ONLY:
        blockers.extend(["strategy_not_live_qualified", "paper_only"])
    if candidate_status == WATCH_BLOCKED_NEAR_MISS or live_class == NEAR_MISS_INCUBATOR:
        blockers.extend(["strategy_not_live_qualified", "near_miss"])
    if not _candidate_is_live_qualified(candidate_status, live_class):
        blockers.append("current_candidate_not_live_qualified")
    if not lane_key or lane_key not in APPROVED_LIVE_QUALIFIED_LANES:
        blockers.append("candidate_lane_not_approved_for_r286")
    if pre_activation.get("exact_lane_risk_contract_found") is not True:
        blockers.append("exact_lane_risk_contract_missing")
    elif pre_activation.get("exact_lane_risk_contract_valid") is not True:
        blockers.append("exact_lane_risk_contract_invalid")
    if pre_activation.get("protective_triplet_preview_available") is not True:
        blockers.append("protective_triplet_preview_missing")
    elif pre_activation.get("protective_triplet_preview_valid") is not True:
        blockers.append("protective_triplet_preview_invalid")
    for key in (
        "binance_readiness_ready",
        "wallet_ready",
        "leverage_margin_ready",
        "no_conflicting_position",
    ):
        if pre_activation.get(key) is not True:
            blockers.append(key.replace("_ready", "_not_ready"))
    return _dedupe(blockers)


def _next_required_step(status: str) -> str:
    if status == FRESH_TRIGGER_WAIT:
        return WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE
    if status == FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW:
        return RUN_ONE_SHOT_DRY_RUN_TRIGGER_PACKET_OR_ARMING_REVIEW
    if status == FRESH_TRIGGER_NOT_CHECKED:
        return RUN_READONLY_PRE_ACTIVATION_CHECKS
    return CLEAR_PRE_ACTIVATION_BLOCKERS


def _recommended_operator_move(status: str, candidate_status: str, live_class: str) -> str:
    if status == FRESH_TRIGGER_READY_FOR_OPERATOR_REVIEW:
        return RUN_ONE_SHOT_DRY_RUN_TRIGGER_PACKET_OR_ARMING_REVIEW
    if candidate_status in {WATCH_BLOCKED_PAPER_ONLY, WATCH_BLOCKED_NEAR_MISS} or live_class in {
        PAPER_ONLY,
        NEAR_MISS_INCUBATOR,
    }:
        return STRATEGY_LAB_PAPER_REVIEW
    if status == FRESH_TRIGGER_WAIT:
        return WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE
    if status == FRESH_TRIGGER_NOT_CHECKED:
        return RUN_READONLY_PRE_ACTIVATION_CHECKS
    return CLEAR_PRE_ACTIVATION_BLOCKERS


def _telegram_payload(
    *,
    status: str,
    candidate: Mapping[str, Any],
    pre_activation: Mapping[str, Any],
    next_required_step: str,
    alert_should_send: bool,
) -> dict[str, Any]:
    lane = candidate.get("lane_key") or pre_activation.get("current_candidate_lane_key") or "n/a"
    message = "\n".join(
        [
            "Hammer Radar one-shot trigger watch",
            f"status: {status}",
            f"lane: {lane}",
            f"signal_id: {candidate.get('signal_id') or 'n/a'}",
            f"timeframe/direction: {candidate.get('timeframe') or 'n/a'}/{candidate.get('direction') or 'n/a'}",
            f"entry/stop/take_profit: {candidate.get('entry') or 'n/a'} / {candidate.get('stop') or 'n/a'} / {candidate.get('take_profit') or 'n/a'}",
            f"age_minutes: {candidate.get('age_minutes') if candidate else 'n/a'}",
            "Binance readiness: "
            f"ready={pre_activation.get('binance_readiness_ready') is True} "
            f"wallet={pre_activation.get('wallet_ready') is True} "
            f"lev/margin={pre_activation.get('leverage_margin_ready') is True} "
            f"no_position_conflict={pre_activation.get('no_conflicting_position') is True}",
            "risk contract: "
            f"found={pre_activation.get('exact_lane_risk_contract_found') is True} "
            f"valid={pre_activation.get('exact_lane_risk_contract_valid') is True} "
            f"protective_preview={pre_activation.get('protective_triplet_preview_valid') is True}",
            f"dry-run next step: {next_required_step}",
            "Operator visibility only. Machine waits for gates and auto-triggers when autonomous mode is armed.",
            "No submit. No order. Operator approval is not a per-signal gate.",
        ]
    )
    return {
        "title": "Hammer Radar one-shot trigger watch",
        "channel": "telegram_compatible",
        "send_enabled": bool(alert_should_send),
        "sent": False,
        "status": "prepared_not_sent",
        "message": message,
        "visibility_only": True,
        "permission_gate": False,
        "per_signal_operator_approval_required": False,
        "secrets_shown": False,
    }


def _panel(
    *,
    status: str,
    candidate: Mapping[str, Any],
    pre_activation: Mapping[str, Any],
    next_required_step: str,
    telegram_payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "operator_role": OPERATOR_ROLE,
        "machine_role": MACHINE_ROLE,
        "per_signal_operator_approval_required": False,
        "alert_is_visibility_only": True,
        "status": status,
        "current_candidate_summary": {
            "lane_key": candidate.get("lane_key") or pre_activation.get("current_candidate_lane_key"),
            "signal_id": candidate.get("signal_id") or pre_activation.get("current_candidate_signal_id"),
            "timeframe": candidate.get("timeframe"),
            "direction": candidate.get("direction"),
            "entry_mode": candidate.get("entry_mode"),
            "age_minutes": _number(candidate.get("age_minutes")),
        },
        "approved_lane_match": pre_activation.get("approved_lane_match") is True,
        "pre_activation_status": pre_activation.get("status"),
        "risk_contract_status": {
            "found": pre_activation.get("exact_lane_risk_contract_found") is True,
            "valid": pre_activation.get("exact_lane_risk_contract_valid") is True,
        },
        "dry_run_arming_status": (
            pre_activation.get("autonomous_dry_run_arming_status") or {}
        ).get("status")
        if isinstance(pre_activation.get("autonomous_dry_run_arming_status"), Mapping)
        else None,
        "telegram_payload_prepared": bool(telegram_payload.get("message")),
        "telegram_send_enabled": telegram_payload.get("send_enabled") is True,
        "next_required_step": next_required_step,
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def _candidate_is_live_qualified(candidate_status: str, live_class: str) -> bool:
    return candidate_status == WATCH_FOUND and live_class == LIVE_QUALIFIED


def _current_candidate(pre_activation: Mapping[str, Any], watch: Mapping[str, Any]) -> dict[str, Any]:
    alert = _candidate_alert(pre_activation, watch)
    candidate = alert.get("current_candidate")
    if isinstance(candidate, Mapping):
        return dict(candidate)
    panel = pre_activation.get("one_shot_pre_activation_gate_panel")
    if isinstance(panel, Mapping) and isinstance(panel.get("candidate"), Mapping):
        return dict(panel["candidate"])
    return {}


def _strategy_evidence(pre_activation: Mapping[str, Any], watch: Mapping[str, Any]) -> dict[str, Any]:
    alert = _candidate_alert(pre_activation, watch)
    evidence = alert.get("strategy_evidence")
    return dict(evidence) if isinstance(evidence, Mapping) else {}


def _candidate_alert(pre_activation: Mapping[str, Any], watch: Mapping[str, Any]) -> dict[str, Any]:
    alert = watch.get("candidate_alert_packet")
    if isinstance(alert, Mapping):
        return dict(alert)
    candidate_watch = pre_activation.get("candidate_watch")
    if isinstance(candidate_watch, Mapping) and isinstance(candidate_watch.get("candidate_alert_packet"), Mapping):
        return dict(candidate_watch["candidate_alert_packet"])
    return {}


def _merged_safety(*surfaces: Mapping[str, Any]) -> dict[str, Any]:
    safety = dict(SAFETY)
    for surface in surfaces:
        source = surface.get("safety") if isinstance(surface.get("safety"), Mapping) else surface
        for key in list(safety):
            if key in source:
                if safety[key] is False:
                    safety[key] = source.get(key) is True
                elif safety[key] is True:
                    safety[key] = source.get(key) is not False
    safety.update(
        {
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
            "signed_url_shown": False,
            "signature_shown": False,
            "secrets_shown": False,
            "secret_values_in_output": False,
            "real_order_forbidden": True,
            "paper_live_separation_intact": True,
        }
    )
    return safety


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            text = str(key).lower()
            if "secret" in text and key not in {"secrets_shown", "secret_values_in_output", "loaded_secret_names_redacted"}:
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


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        text = str(item)
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output
