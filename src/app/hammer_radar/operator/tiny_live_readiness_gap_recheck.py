"""R206 tiny-live readiness gap recheck.

This module composes the latest local evidence/readiness ledgers into a
read-only distance report. It never calls Binance/network, mutates env/config,
creates order payloads, changes lane modes, or authorizes live execution.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.anchor_signal_confluence_matrix import (
    LEDGER_FILENAME as ANCHOR_CONFLUENCE_LEDGER_FILENAME,
    load_anchor_signal_confluence_matrix_records,
)
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.capture_count_sync_8m_short import (
    build_capture_count_sync_8m_short,
    load_capture_count_sync_records,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.funding_gate_role_specific_sync import (
    LEDGER_FILENAME as FUNDING_GATE_LEDGER_FILENAME,
    load_funding_gate_role_specific_sync_records,
)
from src.app.hammer_radar.operator.funding_readonly_precheck import DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT
from src.app.hammer_radar.operator.full_spectrum_harvester_expansion import (
    HEARTBEAT_LEDGER_FILENAME as FULL_SPECTRUM_HEARTBEAT_LEDGER_FILENAME,
    LEDGER_FILENAME as FULL_SPECTRUM_LEDGER_FILENAME,
    load_full_spectrum_harvester_records,
)
from src.app.hammer_radar.operator.lane_control import DEFAULT_CONFIG_PATH, SAFETY_FALSE, load_lane_controls
from src.app.hammer_radar.operator.pattern_lane_matrix_review import (
    LEDGER_FILENAME as PATTERN_LANE_MATRIX_LEDGER_FILENAME,
    load_pattern_lane_matrix_review_records,
)
from src.app.hammer_radar.operator.readonly_balance_check import (
    ACCOUNT_FUNDED_READY_FOR_REVIEW,
    ACCOUNT_NOT_FUNDED,
    LEDGER_FILENAME as READONLY_BALANCE_LEDGER_FILENAME,
    load_readonly_balance_check_records,
)
from src.app.hammer_radar.operator.short_risk_contract_draft_preview import (
    RISK_CONTRACT_CONFIG_PATH,
    TARGET_CANDIDATE_ID,
    load_existing_tiny_live_risk_contracts,
)
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY, MIN_FRESH_CANDIDATES

TINY_LIVE_READINESS_GAP_RECHECK_READY = "TINY_LIVE_READINESS_GAP_RECHECK_READY"
TINY_LIVE_READINESS_GAP_RECHECK_REJECTED = "TINY_LIVE_READINESS_GAP_RECHECK_REJECTED"
TINY_LIVE_READINESS_GAP_RECHECK_RECORDED = "TINY_LIVE_READINESS_GAP_RECHECK_RECORDED"
TINY_LIVE_READINESS_GAP_RECHECK_BLOCKED = "TINY_LIVE_READINESS_GAP_RECHECK_BLOCKED"
TINY_LIVE_READINESS_GAP_RECHECK_ERROR = "TINY_LIVE_READINESS_GAP_RECHECK_ERROR"

NOT_CLOSE_FUNDING_AND_EVIDENCE_BLOCKED = "NOT_CLOSE_FUNDING_AND_EVIDENCE_BLOCKED"
NOT_CLOSE_EVIDENCE_BLOCKED = "NOT_CLOSE_EVIDENCE_BLOCKED"
STRUCTURALLY_CLOSE_OPERATIONALLY_BLOCKED = "STRUCTURALLY_CLOSE_OPERATIONALLY_BLOCKED"
CLOSE_AFTER_FUNDING_AND_CAPTURE_THRESHOLD = "CLOSE_AFTER_FUNDING_AND_CAPTURE_THRESHOLD"
READY_FOR_TINY_LIVE_REVIEW_PACKET = "READY_FOR_TINY_LIVE_REVIEW_PACKET"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "TINY_LIVE_READINESS_GAP_RECHECK"
LEDGER_FILENAME = "tiny_live_readiness_gap_recheck.ndjson"
CONFIRM_TINY_LIVE_GAP_RECHECK_RECORDING_PHRASE = (
    "I CONFIRM TINY LIVE READINESS GAP RECHECK RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

PRIMARY_LANE = DEFAULT_TARGET_LANE_KEY
PRIMARY_SIGNAL_ORIGIN = "hammer_wick_reversal"
SECONDARY_SIGNAL_ORIGINS = ["bearish_engulfing", "three_black_crows"]

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "registry_config_written": False,
    "scoring_config_written": False,
    "matrix_config_written": False,
    "risk_contract_config_written": False,
    "lane_config_written": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "network_allowed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
    "live_authorization_created": False,
    "signal_origin_promoted": False,
    "lane_promoted": False,
    "pattern_family_live_authorized": False,
    "anchor_live_authorized": False,
    "confluence_live_authorized": False,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{FULL_SPECTRUM_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{ANCHOR_CONFLUENCE_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{PATTERN_LANE_MATRIX_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{FUNDING_GATE_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{READONLY_BALANCE_LEDGER_FILENAME}",
    "logs/hammer_radar_forward/capture_count_sync_8m_short.ndjson",
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_readiness_gap_recheck(
    *,
    log_dir: str | Path | None = None,
    record_recheck: bool = False,
    confirm_tiny_live_gap_recheck: str | None = None,
    config_path: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_tiny_live_gap_recheck == CONFIRM_TINY_LIVE_GAP_RECHECK_RECORDING_PHRASE
    try:
        pattern_lane = load_latest_pattern_lane_matrix_status(log_dir=resolved_log_dir)
        anchor_confluence = load_latest_anchor_confluence_status(log_dir=resolved_log_dir)
        harvester = load_latest_full_spectrum_harvester_status(log_dir=resolved_log_dir, now=generated_at)
        evidence_stack = build_evidence_stack_summary(
            pattern_lane_matrix_status=pattern_lane,
            anchor_confluence_status=anchor_confluence,
            full_spectrum_harvester_status=harvester,
        )
        capture = load_latest_capture_count_status(
            log_dir=resolved_log_dir,
            config_path=config_path,
            now=generated_at,
        )
        funding = load_latest_funding_status_from_local_ledgers(log_dir=resolved_log_dir)
        lane_mode = load_lane_mode_status(config_path=config_path)
        risk_contract = load_risk_contract_status(risk_contract_config_path=risk_contract_config_path)
        live_flags = load_live_flag_status(env=env)
        operational = {
            "funding_status": funding["funding_status"],
            "available_balance_usdt": funding["available_balance_usdt"],
            "minimum_required_usdt": funding["minimum_required_usdt"],
            "fresh_capture_count": capture["fresh_capture_count"],
            "required_fresh_capture_count": capture["required_fresh_capture_count"],
            "capture_threshold_met": capture["capture_threshold_met"],
            "risk_contract_applied": risk_contract["risk_contract_applied"],
            "lane_mode": lane_mode["lane_mode"],
            "operator_approval": False,
            "live_flags_armed": live_flags["live_flags_armed"],
            "kill_switch_allows_live": live_flags["kill_switch_allows_live"],
            "read_only_key_separation_ok": funding["read_only_key_separation_ok"],
        }
        blockers = build_tiny_live_blocker_list(
            evidence_stack_summary=evidence_stack,
            operational_readiness=operational,
            funding_status=funding,
            capture_status=capture,
            risk_contract_status=risk_contract,
            lane_mode_status=lane_mode,
            live_flag_status=live_flags,
        )
        distance = classify_tiny_live_distance(
            evidence_stack_summary=evidence_stack,
            operational_readiness=operational,
            blockers=blockers,
        )
        roadmap = build_tiny_live_readiness_roadmap(
            evidence_stack_summary=evidence_stack,
            operational_readiness=operational,
            blockers=blockers,
        )
        status = TINY_LIVE_READINESS_GAP_RECHECK_READY if not _hard_blockers(blockers) else TINY_LIVE_READINESS_GAP_RECHECK_BLOCKED
        if record_recheck and not confirmation_valid:
            status = TINY_LIVE_READINESS_GAP_RECHECK_REJECTED
        elif record_recheck and confirmation_valid:
            status = TINY_LIVE_READINESS_GAP_RECHECK_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "recheck_recorded": False,
            "recheck_id": None,
            "record_recheck_requested": bool(record_recheck),
            "confirmation_valid": bool(confirmation_valid),
            "candidate_context": {
                "primary_lane": PRIMARY_LANE,
                "primary_signal_origin": PRIMARY_SIGNAL_ORIGIN,
                "secondary_signal_origins": list(SECONDARY_SIGNAL_ORIGINS),
                "paper_only": True,
                "live_authorized": False,
            },
            "evidence_stack_summary": evidence_stack,
            "operational_readiness": operational,
            "tiny_live_blockers": blockers,
            "tiny_live_distance": distance,
            "tiny_live_readiness_roadmap": roadmap,
            "recommended_next_operator_move": _recommended_next_operator_move(
                evidence_stack_summary=evidence_stack,
                operational_readiness=operational,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(
                evidence_stack_summary=evidence_stack,
                operational_readiness=operational,
            ),
            "do_not_run_yet": _do_not_run_yet(),
            "input_status": {
                "funding": funding,
                "capture": capture,
                "risk_contract": risk_contract,
                "lane_mode": lane_mode,
                "live_flags": live_flags,
                "pattern_lane_matrix": pattern_lane,
                "anchor_confluence": anchor_confluence,
                "full_spectrum_harvester": harvester,
            },
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_recheck and confirmation_valid:
            record = append_tiny_live_readiness_gap_recheck_record(payload, log_dir=resolved_log_dir)
            payload["recheck_recorded"] = True
            payload["recheck_id"] = record["recheck_id"]
            payload["ledger_path"] = str(tiny_live_readiness_gap_recheck_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": TINY_LIVE_READINESS_GAP_RECHECK_ERROR,
                "generated_at": generated_at.isoformat(),
                "recheck_recorded": False,
                "recheck_id": None,
                "record_recheck_requested": bool(record_recheck),
                "confirmation_valid": bool(confirmation_valid),
                "candidate_context": {
                    "primary_lane": PRIMARY_LANE,
                    "primary_signal_origin": PRIMARY_SIGNAL_ORIGIN,
                    "secondary_signal_origins": list(SECONDARY_SIGNAL_ORIGINS),
                    "paper_only": True,
                    "live_authorized": False,
                },
                "evidence_stack_summary": _empty_evidence_stack_summary(),
                "operational_readiness": _empty_operational_readiness(),
                "tiny_live_blockers": [
                    {
                        "blocker": "recheck_builder_error",
                        "severity": "HARD",
                        "current": exc.__class__.__name__,
                        "required": "R206 builder must complete before any readiness interpretation",
                        "recommended_action": "Fix the local R206 audit builder and rerun preview only.",
                    }
                ],
                "tiny_live_distance": {
                    "distance": UNKNOWN_NEEDS_MANUAL_REVIEW,
                    "plain_english": "The audit could not classify readiness from local evidence.",
                    "estimated_phases_after_hard_blockers_clear": "unknown",
                    "can_fund_now": True,
                    "should_fund_now": "operator_decision_not_required_for_this_audit",
                    "funding_alone_is_not_enough": True,
                },
                "tiny_live_readiness_roadmap": build_tiny_live_readiness_roadmap(
                    evidence_stack_summary=_empty_evidence_stack_summary(),
                    operational_readiness=_empty_operational_readiness(),
                    blockers=[],
                ),
                "recommended_next_operator_move": "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R206 local readiness-gap recheck before planning any live review packet.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_capture_count_status(
    *,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    records = load_capture_count_sync_records(log_dir=log_dir, limit=1)
    latest = records[0] if records else build_capture_count_sync_8m_short(
        log_dir=log_dir,
        config_path=config_path,
        now=now,
    )
    capture_count = dict(latest.get("capture_count") or {})
    return {
        "record_found": bool(records),
        "source_ledger": "capture_count_sync_8m_short.ndjson" if records else "short_paper_evidence_capture.ndjson",
        "fresh_capture_count": _int_value(capture_count.get("fresh_capture_count")),
        "required_fresh_capture_count": _int_value(
            capture_count.get("required_fresh_capture_count"),
            default=MIN_FRESH_CANDIDATES,
        ),
        "capture_threshold_met": bool(capture_count.get("threshold_met")),
        "threshold_status": latest.get("threshold_status"),
        "watcher_status": dict(latest.get("watcher_status") or {}),
        "latest_captured_signal_id": capture_count.get("latest_captured_signal_id"),
    }


def load_latest_funding_status_from_local_ledgers(
    *,
    log_dir: str | Path | None = None,
    minimum_required_usdt: float = DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT,
) -> dict[str, Any]:
    sync_records = load_funding_gate_role_specific_sync_records(log_dir=log_dir, limit=1)
    balance_records = load_readonly_balance_check_records(log_dir=log_dir, limit=1)
    latest_sync = sync_records[0] if sync_records else {}
    latest_balance = balance_records[0] if balance_records else {}
    balance_state = dict(latest_sync.get("latest_balance_state") or {})
    if not balance_state and latest_balance:
        check = dict(latest_balance.get("balance_check") or {})
        balance_state = {
            "balance_readiness": latest_balance.get("balance_readiness") or check.get("funding_status"),
            "available_balance_usdt": check.get("available_balance_usdt"),
            "minimum_balance_required_estimate_usdt": check.get("minimum_balance_required_estimate_usdt"),
            "funding_ready": check.get("funding_ready"),
        }
    funding_status = _normalize_funding_status(balance_state.get("balance_readiness"))
    available = _float_or_none(balance_state.get("available_balance_usdt"))
    required = _float_or_none(balance_state.get("minimum_balance_required_estimate_usdt")) or float(minimum_required_usdt)
    if funding_status == "FUNDED" and (available is None or available < required):
        funding_status = ACCOUNT_NOT_FUNDED if available == 0 else "UNKNOWN"
    role_state = dict(latest_sync.get("account_read_role_state") or {})
    read_only_key_separation_ok = None
    if role_state:
        read_only_key_separation_ok = (
            role_state.get("role_specific_pair_present") is True
            and role_state.get("legacy_fallback_used") is False
            and role_state.get("future_live_disabled") is True
        )
    return {
        "record_found": bool(sync_records or balance_records),
        "funding_status": funding_status,
        "available_balance_usdt": available,
        "minimum_required_usdt": required,
        "funding_ready": funding_status == "FUNDED" and available is not None and available >= required,
        "read_only_key_separation_ok": read_only_key_separation_ok,
        "source_ledgers": [FUNDING_GATE_LEDGER_FILENAME, READONLY_BALANCE_LEDGER_FILENAME],
    }


def load_lane_mode_status(
    *,
    lane_key: str = PRIMARY_LANE,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    controls = load_lane_controls(Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH)
    lane = _find_lane(controls.get("lanes") or [], lane_key)
    mode = str((lane or {}).get("mode") or "unknown")
    return {
        "lane_key": lane_key,
        "lane_mode": mode,
        "lane_found": bool(lane),
        "source_config": str(config_path or DEFAULT_CONFIG_PATH),
        "config_write_allowed": False,
    }


def load_risk_contract_status(
    *,
    risk_contract_config_path: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    config = load_existing_tiny_live_risk_contracts(config_path=path)
    contracts = list(config.get("risk_contracts") or [])
    target = None
    for contract in contracts:
        if not isinstance(contract, Mapping):
            continue
        keys = {
            str(contract.get("candidate_id") or ""),
            _lane_key_from_contract(contract),
        }
        if TARGET_CANDIDATE_ID in keys or PRIMARY_LANE in keys:
            target = dict(contract)
            break
    applied = bool(target and target.get("enabled_for_preflight") is True)
    return {
        "risk_contract_applied": applied,
        "target_contract_exists": bool(target),
        "target_candidate_id": TARGET_CANDIDATE_ID,
        "minimum_required_usdt": _float_or_none((target or {}).get("max_margin_usdt"))
        or _float_or_none((config.get("funding_config") or {}).get("max_margin_usdt"))
        or DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT,
        "source_config": str(path),
        "config_write_allowed": False,
    }


def load_live_flag_status(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    live_execution_enabled = _truthy(source.get("HAMMER_LIVE_EXECUTION_ENABLED"))
    allow_live_orders = _truthy(source.get("HAMMER_ALLOW_LIVE_ORDERS"))
    binance_live_enabled = _truthy(source.get("BINANCE_LIVE_TRADING_ENABLED"))
    kill_switch_engaged = _truthy(source.get("HAMMER_GLOBAL_KILL_SWITCH"), default=True)
    return {
        "live_flags_armed": bool(live_execution_enabled and allow_live_orders and binance_live_enabled),
        "kill_switch_allows_live": not kill_switch_engaged,
        "live_execution_enabled": live_execution_enabled,
        "allow_live_orders": allow_live_orders,
        "binance_live_trading_enabled": binance_live_enabled,
        "global_kill_switch_engaged": kill_switch_engaged,
        "source": "env_boolean_names_only_no_values_exposed",
    }


def load_latest_pattern_lane_matrix_status(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_pattern_lane_matrix_review_records(log_dir=log_dir, limit=1)
    if not records:
        return {"record_found": False, "source_ledger": PATTERN_LANE_MATRIX_LEDGER_FILENAME}
    latest = records[0]
    rows = list(latest.get("pattern_lane_pair_matrix") or [])
    pairs = {
        str(row.get("signal_origin")): row
        for row in rows
        if isinstance(row, Mapping) and row.get("lane_key") == PRIMARY_LANE
    }
    return {
        "record_found": True,
        "source_ledger": PATTERN_LANE_MATRIX_LEDGER_FILENAME,
        "matrix_id": latest.get("matrix_id"),
        "matrix_status": latest.get("matrix_status"),
        "primary_pair_score": _score_for(pairs, PRIMARY_SIGNAL_ORIGIN),
        "secondary_pair_scores": {origin: _score_for(pairs, origin) for origin in SECONDARY_SIGNAL_ORIGINS},
        "paper_only": True,
        "live_authorized": False,
    }


def load_latest_anchor_confluence_status(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    records = load_anchor_signal_confluence_matrix_records(log_dir=log_dir, limit=1)
    if not records:
        return {"record_found": False, "source_ledger": ANCHOR_CONFLUENCE_LEDGER_FILENAME}
    latest = records[0]
    summary = dict(latest.get("input_summary") or {})
    summary_matches = _int_value(summary.get("summary_level_matches_found"))
    event_matches = _int_value(summary.get("event_level_matches_found"))
    return {
        "record_found": True,
        "source_ledger": ANCHOR_CONFLUENCE_LEDGER_FILENAME,
        "matrix_id": latest.get("matrix_id"),
        "confluence_status": latest.get("confluence_status"),
        "summary_level_matches_found": summary_matches,
        "event_level_matches_found": event_matches,
        "summary_level_confluence_available": summary_matches > 0,
        "event_level_confluence_available": event_matches > 0,
        "paper_only": True,
        "live_authorized": False,
    }


def load_latest_full_spectrum_harvester_status(
    *,
    log_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = load_full_spectrum_harvester_records(log_dir=resolved_log_dir, limit=1)
    heartbeat = _latest_ndjson_record(Path(resolved_log_dir) / FULL_SPECTRUM_HEARTBEAT_LEDGER_FILENAME)
    latest = records[0] if records else {}
    heartbeat_generated = _parse_dt(heartbeat.get("generated_at")) if heartbeat else None
    age_seconds = None
    if heartbeat_generated is not None:
        age_seconds = max(0, int(((now or datetime.now(UTC)) - heartbeat_generated).total_seconds()))
    return {
        "record_found": bool(records),
        "source_ledger": FULL_SPECTRUM_LEDGER_FILENAME,
        "harvest_id": latest.get("harvest_id"),
        "status": latest.get("status"),
        "latest_heartbeat_found": bool(heartbeat),
        "latest_heartbeat_status": heartbeat.get("status") if heartbeat else None,
        "latest_heartbeat_age_seconds": age_seconds,
        "full_spectrum_harvester_running_or_recent": bool(heartbeat and age_seconds is not None and age_seconds <= 900),
        "paper_only": True,
        "live_authorized": False,
    }


def build_evidence_stack_summary(
    *,
    pattern_lane_matrix_status: Mapping[str, Any],
    anchor_confluence_status: Mapping[str, Any],
    full_spectrum_harvester_status: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "pattern_lane_matrix_found": bool(pattern_lane_matrix_status.get("record_found")),
        "anchor_confluence_found": bool(anchor_confluence_status.get("record_found")),
        "full_spectrum_harvester_found": bool(full_spectrum_harvester_status.get("record_found")),
        "primary_pair_score": pattern_lane_matrix_status.get("primary_pair_score"),
        "secondary_pair_scores": dict(pattern_lane_matrix_status.get("secondary_pair_scores") or {}),
        "summary_level_confluence_available": bool(anchor_confluence_status.get("summary_level_confluence_available")),
        "event_level_confluence_available": bool(anchor_confluence_status.get("event_level_confluence_available")),
        "full_spectrum_harvester_running_or_recent": bool(
            full_spectrum_harvester_status.get("full_spectrum_harvester_running_or_recent")
        ),
    }


def build_tiny_live_blocker_list(
    *,
    evidence_stack_summary: Mapping[str, Any],
    operational_readiness: Mapping[str, Any],
    funding_status: Mapping[str, Any],
    capture_status: Mapping[str, Any],
    risk_contract_status: Mapping[str, Any],
    lane_mode_status: Mapping[str, Any],
    live_flag_status: Mapping[str, Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if operational_readiness.get("funding_status") != "FUNDED":
        blockers.append(_blocker("funding", "HARD", funding_status.get("funding_status"), "FUNDED with available USDT >= minimum", "Check local read-only funding status; fund only by operator decision outside this audit."))
    elif _float_or_none(operational_readiness.get("available_balance_usdt")) is None or float(operational_readiness.get("available_balance_usdt") or 0) < float(operational_readiness.get("minimum_required_usdt") or 0):
        blockers.append(_blocker("funding", "HARD", f"{operational_readiness.get('available_balance_usdt')} USDT", f">= {operational_readiness.get('minimum_required_usdt')} USDT", "Bring available balance above the current risk-contract minimum before any later review."))
    if operational_readiness.get("capture_threshold_met") is not True:
        blockers.append(_blocker("fresh_capture_threshold", "HARD", f"{capture_status.get('fresh_capture_count')} / {capture_status.get('required_fresh_capture_count')}", f">= {capture_status.get('required_fresh_capture_count')} fresh captures", "Run R208 capture threshold recovery/monitoring; keep it paper-only."))
    if operational_readiness.get("risk_contract_applied") is not True:
        blockers.append(_blocker("risk_contract", "HARD", "missing/not applied for BTCUSDT 8m short", "applied target risk contract", "Use a later explicit safe config phase only after evidence/funding are ready."))
    if operational_readiness.get("lane_mode") != "tiny_live":
        blockers.append(_blocker("lane_mode", "HARD", lane_mode_status.get("lane_mode"), "tiny_live candidate/armed review mode", "Do not change lane mode in R206; keep paper until a future approved phase."))
    if operational_readiness.get("operator_approval") is not True:
        blockers.append(_blocker("operator_approval", "HARD", "false", "explicit future operator approval", "Collect approval only in a later review packet phase."))
    if operational_readiness.get("live_flags_armed") is not True:
        blockers.append(_blocker("live_flags", "HARD", "false", "intentionally armed live flags", "Do not arm live flags in this audit."))
    if operational_readiness.get("kill_switch_allows_live") is not True:
        blockers.append(_blocker("kill_switch", "HARD", str(live_flag_status.get("global_kill_switch_engaged")), "kill switch policy allows the later action", "Do not disable the kill switch in this audit."))
    if evidence_stack_summary.get("event_level_confluence_available") is not True:
        blockers.append(_blocker("event_level_confluence_optional", "SOFT", "summary-level only", "event-level timestamp confluence from R207", "Run R207 before using confluence as supporting evidence; do not infer live readiness from confluence alone."))
    if evidence_stack_summary.get("pattern_lane_matrix_found") is not True:
        blockers.append(_blocker("pattern_lane_matrix", "INFO", "missing local R205 record", "latest R205 pattern lane matrix", "Rerun R205 preview/record if the local ledger is missing."))
    if evidence_stack_summary.get("full_spectrum_harvester_running_or_recent") is not True:
        blockers.append(_blocker("full_spectrum_harvester_recentness", "INFO", "not recent/unknown", "recent R198 harvester heartbeat", "Keep the full-spectrum paper harvester running for visibility."))
    return blockers


def classify_tiny_live_distance(
    *,
    evidence_stack_summary: Mapping[str, Any],
    operational_readiness: Mapping[str, Any],
    blockers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    hard_names = {str(blocker.get("blocker")) for blocker in blockers if blocker.get("severity") == "HARD"}
    funding_blocked = "funding" in hard_names
    capture_blocked = "fresh_capture_threshold" in hard_names
    evidence_missing = evidence_stack_summary.get("pattern_lane_matrix_found") is not True
    operational_hard = hard_names - {"funding", "fresh_capture_threshold"}
    if funding_blocked and (capture_blocked or evidence_missing):
        distance = NOT_CLOSE_FUNDING_AND_EVIDENCE_BLOCKED
        phases = "5-8"
        plain = "Paper evidence improved, but tiny-live is not close because funding and fresh/evidence gates are still blocked."
    elif capture_blocked or evidence_missing:
        distance = NOT_CLOSE_EVIDENCE_BLOCKED
        phases = "3-5"
        plain = "Funding is not the only issue; the chosen lane still needs fresh evidence threshold recovery before live review."
    elif operational_hard:
        distance = STRUCTURALLY_CLOSE_OPERATIONALLY_BLOCKED
        phases = "2-4"
        plain = "The evidence stack is structurally interesting, but operational gates still block tiny-live."
    elif funding_blocked:
        distance = CLOSE_AFTER_FUNDING_AND_CAPTURE_THRESHOLD
        phases = "2-4"
        plain = "The lane would be close only after funding is verified and all later operational gates are reviewed."
    elif not hard_names:
        distance = READY_FOR_TINY_LIVE_REVIEW_PACKET
        phases = "2-4"
        plain = "Local gates are clear enough to build a non-executing tiny-live review packet; final preflight is still a later phase."
    else:
        distance = UNKNOWN_NEEDS_MANUAL_REVIEW
        phases = "unknown"
        plain = "The local evidence is incomplete and needs manual review."
    return {
        "distance": distance,
        "plain_english": plain,
        "estimated_phases_after_hard_blockers_clear": phases,
        "can_fund_now": True,
        "should_fund_now": "operator_decision_not_required_for_this_audit",
        "funding_alone_is_not_enough": True,
    }


def build_tiny_live_readiness_roadmap(
    *,
    evidence_stack_summary: Mapping[str, Any],
    operational_readiness: Mapping[str, Any],
    blockers: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    roadmap = [
        {
            "priority": 1,
            "phase": "R207",
            "action": "Build event-level anchor/signal confluence timestamp matcher.",
            "why": "R203 found summary-level confluence only; event-level confluence is still missing and must remain support-only.",
        },
        {
            "priority": 2,
            "phase": "R208",
            "action": "Recover and monitor BTCUSDT 8m short fresh capture threshold to 10/10.",
            "why": "Tiny-live review stays hard-blocked until the primary lane reaches the fresh capture threshold.",
        },
        {
            "priority": 3,
            "phase": "R209",
            "action": "Recheck funding from local read-only balance evidence after the operator decides funding status.",
            "why": "Funding must be verified from an existing gated read-only path; R206 does not call Binance.",
        },
        {
            "priority": 4,
            "phase": "R210",
            "action": "Prepare a risk-contract apply review only after evidence and funding are clear.",
            "why": "The current target risk contract is not applied for BTCUSDT 8m short and must not be written by this audit.",
        },
        {
            "priority": 5,
            "phase": "R211",
            "action": "Build a non-executing tiny-live review packet if all hard blockers clear.",
            "why": "Operator approval, lane mode, live flags, kill-switch policy, and final preflight belong in later explicit phases.",
        },
    ]
    if evidence_stack_summary.get("full_spectrum_harvester_running_or_recent") is not True:
        roadmap.insert(
            0,
            {
                "priority": 1,
                "phase": "R206A",
                "action": "Keep the R198 full-spectrum paper harvester running or refresh its local heartbeat.",
                "why": "Current paper coverage visibility should stay fresh while readiness blockers are cleared.",
            },
        )
        for index, row in enumerate(roadmap, start=1):
            row["priority"] = index
    _ = operational_readiness, blockers
    return roadmap


def append_tiny_live_readiness_gap_recheck_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_readiness_gap_recheck_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "recheck_id": record.get("recheck_id") or f"r206_tiny_live_readiness_gap_recheck_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_recheck_requested": bool(record.get("record_recheck_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "candidate_context": dict(record.get("candidate_context") or {}),
            "evidence_stack_summary": dict(record.get("evidence_stack_summary") or {}),
            "operational_readiness": dict(record.get("operational_readiness") or {}),
            "tiny_live_blockers": list(record.get("tiny_live_blockers") or []),
            "tiny_live_distance": dict(record.get("tiny_live_distance") or {}),
            "tiny_live_readiness_roadmap": list(record.get("tiny_live_readiness_roadmap") or []),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_readiness_gap_recheck_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_readiness_gap_recheck_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_tiny_live_readiness_gap_recheck_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    distance_counts = Counter(
        str((record.get("tiny_live_distance") or {}).get("distance") or "UNKNOWN")
        for record in records
        if isinstance(record.get("tiny_live_distance"), Mapping)
    )
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "tiny_live_distance_counts": dict(sorted(distance_counts.items())),
        "last_recheck_id": latest.get("recheck_id"),
        "last_distance": (latest.get("tiny_live_distance") or {}).get("distance") if isinstance(latest.get("tiny_live_distance"), Mapping) else None,
        "safety": dict(SAFETY),
    }


def tiny_live_readiness_gap_recheck_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_readiness_gap_recheck_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _recommended_next_operator_move(
    *,
    evidence_stack_summary: Mapping[str, Any],
    operational_readiness: Mapping[str, Any],
) -> str:
    if operational_readiness.get("funding_status") != "FUNDED":
        return "CHECK_READONLY_FUNDING_STATUS"
    if operational_readiness.get("capture_threshold_met") is not True:
        return "RUN_R208_CAPTURE_THRESHOLD_RECOVERY"
    if evidence_stack_summary.get("event_level_confluence_available") is not True:
        return "RUN_R207_EVENT_LEVEL_CONFLUENCE_MATCHER"
    return "KEEP_FULL_SPECTRUM_HARVESTER_RUNNING"


def _recommended_next_engineering_move(
    *,
    evidence_stack_summary: Mapping[str, Any],
    operational_readiness: Mapping[str, Any],
) -> str:
    if evidence_stack_summary.get("event_level_confluence_available") is not True:
        return "Implement R207 event-level confluence matcher using local timestamps only; keep it paper-only."
    if operational_readiness.get("capture_threshold_met") is not True:
        return "Implement R208 capture threshold recovery for BTCUSDT 8m short with no config writes or network calls."
    return "Prepare a non-executing tiny-live review packet only after funding, risk contract, lane mode, approval, flags, and kill-switch blockers clear."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set any lane tiny_live",
        "write risk contract config",
        "transfer",
        "withdraw",
    ]


def _blocker(blocker: str, severity: str, current: Any, required: Any, recommended_action: str) -> dict[str, Any]:
    return {
        "blocker": blocker,
        "severity": severity,
        "current": "UNKNOWN" if current is None else str(current),
        "required": str(required),
        "recommended_action": recommended_action,
    }


def _hard_blockers(blockers: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [blocker for blocker in blockers if blocker.get("severity") == "HARD"]


def _find_lane(lanes: Sequence[Any], lane_key: str) -> Mapping[str, Any] | None:
    for lane in lanes:
        if not isinstance(lane, Mapping):
            continue
        if _lane_key_from_contract(lane) == lane_key:
            return lane
    return None


def _lane_key_from_contract(contract: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(contract.get("symbol") or "").upper(),
            str(contract.get("timeframe") or ""),
            str(contract.get("direction") or "").lower(),
            str(contract.get("entry_mode") or ""),
        ]
    )


def _score_for(rows_by_origin: Mapping[str, Any], origin: str) -> Any:
    row = rows_by_origin.get(origin)
    if isinstance(row, Mapping):
        return row.get("pair_score")
    return None


def _latest_ndjson_record(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    records = read_recent_ndjson_records(path, limit=1, max_bytes=16_777_216)
    return dict(records[0]) if records else {}


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_funding_status(value: Any) -> str:
    raw = str(value or "UNKNOWN")
    if raw in {ACCOUNT_FUNDED_READY_FOR_REVIEW, "FUNDED", "FUNDING_SYNC_READY_FOR_REVIEW"}:
        return "FUNDED"
    if raw in {ACCOUNT_NOT_FUNDED, "FUNDING_SYNC_ACCOUNT_NOT_FUNDED"}:
        return ACCOUNT_NOT_FUNDED
    return "UNKNOWN"


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_value(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _empty_evidence_stack_summary() -> dict[str, Any]:
    return {
        "pattern_lane_matrix_found": False,
        "anchor_confluence_found": False,
        "full_spectrum_harvester_found": False,
        "primary_pair_score": None,
        "secondary_pair_scores": {},
        "summary_level_confluence_available": False,
        "event_level_confluence_available": False,
        "full_spectrum_harvester_running_or_recent": False,
    }


def _empty_operational_readiness() -> dict[str, Any]:
    return {
        "funding_status": "UNKNOWN",
        "available_balance_usdt": None,
        "minimum_required_usdt": DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT,
        "fresh_capture_count": 0,
        "required_fresh_capture_count": MIN_FRESH_CANDIDATES,
        "capture_threshold_met": False,
        "risk_contract_applied": False,
        "lane_mode": "unknown",
        "operator_approval": False,
        "live_flags_armed": False,
        "kill_switch_allows_live": False,
        "read_only_key_separation_ok": None,
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
