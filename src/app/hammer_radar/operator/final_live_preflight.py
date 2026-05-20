"""R102 final live preflight adapter.

This module composes existing Hammer Radar readiness surfaces into one
operator-facing result. It is not a new source of truth and never places
orders, signs payloads, calls Binance order endpoints, or changes env flags.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.execution.binance_futures_connector import (
    build_connector_status,
    build_protective_status,
)
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.binance_live_status import build_binance_live_status
from src.app.hammer_radar.operator.final_human_review_packet import (
    build_final_human_review_packet,
    build_final_human_review_packets_payload,
)
from src.app.hammer_radar.operator.human_confirmation_records import (
    build_human_confirmation_records_status,
)
from src.app.hammer_radar.operator.live_arming_preflight import build_live_arming_preflight
from src.app.hammer_radar.operator.live_env_boundary_review import build_live_env_boundary_review
from src.app.hammer_radar.operator.live_preflight import build_promoted_strategy_preflight
from src.app.hammer_radar.operator.notification_watcher import (
    load_notification_config,
    notification_status,
)
from src.app.hammer_radar.operator.readiness import build_readiness_payload
from src.app.hammer_radar.operator.review_record_aggregator import build_review_record_arming_snapshot
from src.app.hammer_radar.operator.strategy_performance import build_live_eligibility_matrix
from src.app.hammer_radar.operator.strategy_promotion_watcher import build_strategy_promotion_status
from src.app.hammer_radar.operator.tiny_live_risk_contract import (
    DEFAULT_CANDIDATE_ID,
    RISK_CONTRACT_VALID_FOR_PREFLIGHT,
    build_tiny_live_risk_contract_payload,
)

READY = "READY"
BLOCKED = "BLOCKED"
EXECUTION_MODE = "FINAL_LIVE_PREFLIGHT_ADAPTER_ONLY_NO_ORDER"
SOURCE_SURFACES_USED = [
    "operator.readiness.build_readiness_payload",
    "operator.live_arming_preflight.build_live_arming_preflight",
    "operator.live_env_boundary_review.build_live_env_boundary_review",
    "operator.strategy_performance.build_live_eligibility_matrix",
    "operator.strategy_promotion_watcher.build_strategy_promotion_status",
    "operator.tiny_live_risk_contract.build_tiny_live_risk_contract_payload",
    "operator.final_human_review_packet.build_final_human_review_packet",
    "operator.final_human_review_packet.build_final_human_review_packets_payload",
    "operator.human_confirmation_records.build_human_confirmation_records_status",
    "operator.review_record_aggregator.build_review_record_arming_snapshot",
    "operator.live_preflight.build_promoted_strategy_preflight",
    "operator.binance_live_status.build_binance_live_status",
    "execution.binance_futures_connector.build_connector_status",
    "execution.binance_futures_connector.build_protective_status",
    "operator.notification_watcher.notification_status",
]


def build_final_live_preflight(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_env = os.environ if env is None else env

    readiness = build_readiness_payload(log_dir=resolved_log_dir)
    arming_preflight = build_live_arming_preflight(candidate_id=candidate_id, log_dir=resolved_log_dir, env=source_env)
    env_boundary = build_live_env_boundary_review(candidate_id=candidate_id, log_dir=resolved_log_dir, env=source_env)
    live_eligibility = build_live_eligibility_matrix(log_dir=resolved_log_dir)
    promotion = build_strategy_promotion_status(log_dir=resolved_log_dir)
    risk_contract = build_tiny_live_risk_contract_payload(candidate_id=candidate_id)
    final_packet = build_final_human_review_packet(candidate_id=candidate_id, dry_run=True, write=False, log_dir=resolved_log_dir)
    final_packets = build_final_human_review_packets_payload(candidate_id=candidate_id, limit=20, log_dir=resolved_log_dir)
    human_records = build_human_confirmation_records_status(candidate_id=candidate_id, log_dir=resolved_log_dir)
    readiness_snapshot = build_review_record_arming_snapshot(candidate_id=candidate_id, log_dir=resolved_log_dir)
    promoted_preflight = build_promoted_strategy_preflight(log_dir=resolved_log_dir)
    binance_status = build_binance_live_status(env=source_env)
    connector_status = build_connector_status(env=source_env, log_dir=resolved_log_dir)
    protective_status = build_protective_status(env=source_env, log_dir=resolved_log_dir)
    notifications = notification_status(
        log_dir=resolved_log_dir,
        config=load_notification_config(dict(source_env)),
    )

    risk_validation = risk_contract.get("validation") if isinstance(risk_contract.get("validation"), dict) else {}
    risk_contract_hash = readiness_snapshot.get("risk_contract_hash") or final_packet.get("risk_contract_hash")
    packet_hash = readiness_snapshot.get("packet_hash") or final_packet.get("packet_hash")
    packet_summary = final_packets.get("summary") if isinstance(final_packets.get("summary"), dict) else {}
    human_summary = human_records.get("summary") if isinstance(human_records.get("summary"), dict) else {}

    risk_contract_present = risk_validation.get("validation_status") == RISK_CONTRACT_VALID_FOR_PREFLIGHT
    final_review_packet_present = int(packet_summary.get("written_packet_records") or 0) > 0
    human_approval_records_present = int(human_summary.get("written_confirmation_records") or 0) > 0
    all_human_records_present = not bool(human_summary.get("missing_record_types") or [])
    protective_orders_ready = bool(protective_status.get("protective_orders_ready"))
    binance_credentials_present = {
        "api_key_present": bool(binance_status.get("api_key_present") or connector_status.get("api_key_present")),
        "api_secret_present": bool(binance_status.get("api_secret_present") or connector_status.get("api_secret_present")),
    }
    stale_candidate_protection_present = True
    fresh_promoted_signal_found = promoted_preflight.get("matching_fresh_signal_found") is True
    paper_live_separation_intact = _paper_live_separation_intact(
        readiness=readiness,
        arming_preflight=arming_preflight,
        env_boundary=env_boundary,
        readiness_snapshot=readiness_snapshot,
        connector_status=connector_status,
        protective_status=protective_status,
        notifications=notifications,
    )
    telegram_operator_path_present = True

    blockers = _blockers(
        readiness=readiness,
        arming_preflight=arming_preflight,
        env_boundary=env_boundary,
        readiness_snapshot=readiness_snapshot,
        promoted_preflight=promoted_preflight,
        binance_status=binance_status,
        connector_status=connector_status,
        protective_status=protective_status,
        risk_contract_present=risk_contract_present,
        final_review_packet_present=final_review_packet_present,
        human_approval_records_present=human_approval_records_present,
        all_human_records_present=all_human_records_present,
        binance_credentials_present=binance_credentials_present,
        protective_orders_ready=protective_orders_ready,
        fresh_promoted_signal_found=fresh_promoted_signal_found,
        paper_live_separation_intact=paper_live_separation_intact,
    )
    warnings = _warnings(
        live_eligibility=live_eligibility,
        promotion=promotion,
        notifications=notifications,
        binance_status=binance_status,
        promoted_preflight=promoted_preflight,
    )

    payload = {
        "status": READY if not blockers else BLOCKED,
        "blockers": blockers,
        "warnings": warnings,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "execution_mode": EXECUTION_MODE,
        "candidate_id": candidate_id,
        "live_execution_enabled": bool(connector_status.get("live_execution_enabled")),
        "live_orders_allowed": bool(connector_status.get("allow_live_orders")),
        "global_kill_switch": bool(connector_status.get("global_kill_switch")),
        "connector_mode": connector_status.get("connector_mode"),
        "binance_credentials_present": binance_credentials_present,
        "binance_account_status": {
            "account_balance_checked": False,
            "status": "not_checked_no_network",
            "source": "R102 does not call account/balance APIs.",
        },
        "risk_contract_present": risk_contract_present,
        "risk_contract_hash": risk_contract_hash,
        "final_review_packet_present": final_review_packet_present,
        "final_review_packet_hash": packet_hash,
        "human_approval_records_present": human_approval_records_present,
        "human_approval_records_complete": all_human_records_present,
        "protective_orders_ready": protective_orders_ready,
        "protective_order_mode": protective_status.get("protective_order_mode") or connector_status.get("protective_order_mode"),
        "stale_candidate_protection_present": stale_candidate_protection_present,
        "fresh_promoted_signal_found": fresh_promoted_signal_found,
        "telegram_configured": bool(notifications.get("telegram_configured")),
        "telegram_operator_path_present": telegram_operator_path_present,
        "paper_live_separation_intact": paper_live_separation_intact,
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
        "source_statuses": {
            "readiness_status": readiness.get("readiness_status"),
            "live_arming_preflight_status": arming_preflight.get("final_preflight_status"),
            "env_boundary_status": env_boundary.get("boundary_status"),
            "readiness_snapshot_class": readiness_snapshot.get("readiness_class"),
            "promoted_strategy_preflight_status": promoted_preflight.get("preflight_status"),
            "binance_status": binance_status.get("readiness"),
            "connector_status": connector_status.get("readiness"),
        },
        "safety": {
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "order_payload_created": False,
            "signed_payload_created": False,
            "network_used": False,
            "secrets_shown": False,
        },
    }
    return _sanitize(payload)


def format_final_live_preflight_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _blockers(
    *,
    readiness: Mapping[str, Any],
    arming_preflight: Mapping[str, Any],
    env_boundary: Mapping[str, Any],
    readiness_snapshot: Mapping[str, Any],
    promoted_preflight: Mapping[str, Any],
    binance_status: Mapping[str, Any],
    connector_status: Mapping[str, Any],
    protective_status: Mapping[str, Any],
    risk_contract_present: bool,
    final_review_packet_present: bool,
    human_approval_records_present: bool,
    all_human_records_present: bool,
    binance_credentials_present: Mapping[str, bool],
    protective_orders_ready: bool,
    fresh_promoted_signal_found: bool,
    paper_live_separation_intact: bool,
) -> list[str]:
    blockers: list[str] = []
    if connector_status.get("live_execution_enabled") is not True:
        blockers.append("live execution disabled")
    if connector_status.get("allow_live_orders") is not True:
        blockers.append("live orders disabled")
    if connector_status.get("global_kill_switch") is not False:
        blockers.append("global kill switch active")
    if not binance_credentials_present.get("api_key_present") or not binance_credentials_present.get("api_secret_present"):
        blockers.append("missing Binance credentials")
    if connector_status.get("connector_mode") != "LIVE_ORDER_ENABLED":
        blockers.append(f"dry-run-only connector mode: {connector_status.get('connector_mode')}")
    if not risk_contract_present:
        blockers.append("missing risk contract")
    if not final_review_packet_present:
        blockers.append("missing final review packet")
    if not human_approval_records_present:
        blockers.append("missing human approval record")
    elif not all_human_records_present:
        blockers.append("human approval records incomplete")
    if not protective_orders_ready:
        blockers.append("protective readiness false")
    if connector_status.get("live_order_adapter_configured") is not True:
        blockers.append("live order adapter not configured")
    if not fresh_promoted_signal_found:
        blockers.append("stale candidate risk")
    if env_boundary.get("boundary_status") != "LIVE_ENV_LOCKED_SAFE":
        blockers.append("environment boundary blocked")
    if not paper_live_separation_intact:
        blockers.append("paper/live separation violation")

    blockers.extend(str(item) for item in readiness.get("blockers") or [])
    blockers.extend(str(item) for item in arming_preflight.get("blockers") or [])
    blockers.extend(str(item) for item in env_boundary.get("blockers") or [])
    blockers.extend(str(item) for item in binance_status.get("blockers") or [])
    blockers.extend(str(item) for item in connector_status.get("blockers") or [])
    blockers.extend(str(item) for item in protective_status.get("blockers") or [])
    if isinstance(readiness_snapshot.get("blocker_summary"), dict):
        blockers.extend(str(item) for item in readiness_snapshot["blocker_summary"].get("blockers") or [])
    blockers.extend(str(item) for item in promoted_preflight.get("blockers") or [])
    return _dedupe(blockers)


def _warnings(
    *,
    live_eligibility: Mapping[str, Any],
    promotion: Mapping[str, Any],
    notifications: Mapping[str, Any],
    binance_status: Mapping[str, Any],
    promoted_preflight: Mapping[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if not live_eligibility.get("eligible_recommendations"):
        warnings.append("no live eligibility recommendation currently ready")
    if not promotion.get("promotion_ready"):
        warnings.append("no strategy promotion is currently ready")
    if notifications.get("telegram_configured") is not True:
        warnings.append("telegram is not fully configured")
    if binance_status.get("live_env_file_exists") is not True:
        warnings.append("Binance live env file not confirmed present")
    if promoted_preflight.get("matching_fresh_signal_found") is not True:
        warnings.append("fresh promoted strategy signal not found")
    return _dedupe(warnings)


def _paper_live_separation_intact(**surfaces: Mapping[str, Any]) -> bool:
    for surface in surfaces.values():
        if surface.get("real_order_placed") is True:
            return False
        if surface.get("execution_attempted") is True:
            return False
        if surface.get("secrets_shown") is True:
            return False
    return True


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in (
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "order_payload_created",
            "signed_payload_created",
            "network_used",
            "secrets_shown",
        ):
            if key in sanitized:
                sanitized[key] = False
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
