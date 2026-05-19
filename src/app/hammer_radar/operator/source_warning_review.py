"""R91 source warning review and candidate support rehydration.

This module diagnoses why the current source chain does not support the tiny
live candidate. It never creates order payloads, calls Binance, checks balances,
mutates env files, or enables live execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_candle_archive import build_betrayal_candle_archive_status
from src.app.hammer_radar.operator.live_arming_preflight import build_live_arming_preflight
from src.app.hammer_radar.operator.miro_fish_quality_gate import build_miro_fish_quality_gate
from src.app.hammer_radar.operator.review_record_aggregator import build_review_record_arming_snapshot
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID, build_tiny_live_risk_contract_payload

PHASE = "R91"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "SOURCE_WARNING_REVIEW_CANDIDATE_SUPPORT_REHYDRATION_ONLY_NO_ORDER"
REPORT_FILENAME = "source_warning_review.json"

SOURCE_WARNING_REVIEW_ONLY = "SOURCE_WARNING_REVIEW_ONLY"
SOURCE_CHAIN_CLEAN_CURRENT_SUPPORT_PRESENT = "SOURCE_CHAIN_CLEAN_CURRENT_SUPPORT_PRESENT"
SOURCE_CHAIN_WARNINGS_PRESENT = "SOURCE_CHAIN_WARNINGS_PRESENT"
SOURCE_CHAIN_CANDIDATE_NOT_SUPPORTED_CURRENTLY = "SOURCE_CHAIN_CANDIDATE_NOT_SUPPORTED_CURRENTLY"
SOURCE_CHAIN_CANDIDATE_SUPPORT_REHYDRATED_FOR_REVIEW = "SOURCE_CHAIN_CANDIDATE_SUPPORT_REHYDRATED_FOR_REVIEW"
SOURCE_CHAIN_CANDIDATE_REVALIDATION_REQUIRED = "SOURCE_CHAIN_CANDIDATE_REVALIDATION_REQUIRED"
SOURCE_CHAIN_DATA_INSUFFICIENT = "SOURCE_CHAIN_DATA_INSUFFICIENT"
SOURCE_CHAIN_ARCHIVE_WARNING_ONLY = "SOURCE_CHAIN_ARCHIVE_WARNING_ONLY"
SOURCE_CHAIN_NON_EXECUTABLE_ONLY = "SOURCE_CHAIN_NON_EXECUTABLE_ONLY"

REHYDRATION_NOT_NEEDED = "REHYDRATION_NOT_NEEDED"
REHYDRATION_AVAILABLE_FOR_REVIEW = "REHYDRATION_AVAILABLE_FOR_REVIEW"
REHYDRATION_BLOCKED_BY_MISSING_HISTORICAL_CONTEXT = "REHYDRATION_BLOCKED_BY_MISSING_HISTORICAL_CONTEXT"
REHYDRATION_REVIEW_ONLY_NOT_CURRENT_SUPPORT = "REHYDRATION_REVIEW_ONLY_NOT_CURRENT_SUPPORT"
REHYDRATION_REVALIDATION_REQUIRED = "REHYDRATION_REVALIDATION_REQUIRED"

ARCHIVE_INTEGRITY_WARNING = "ARCHIVE_INTEGRITY_WARNING"
CANDIDATE_SUPPORT_MISSING = "CANDIDATE_SUPPORT_MISSING"
CURRENT_SOURCE_DATA_INSUFFICIENT = "CURRENT_SOURCE_DATA_INSUFFICIENT"
STRATEGY_PERFORMANCE_DRIFT = "STRATEGY_PERFORMANCE_DRIFT"
RUNTIME_DATA_STALE = "RUNTIME_DATA_STALE"
UNKNOWN_SOURCE_WARNING = "UNKNOWN_SOURCE_WARNING"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

DOCUMENTED_PRIOR_CONTEXT_SOURCE = "docs/hammer_radar/R84_LIVE_FUNDING_FINAL_ARMING_PREFLIGHT.md"
DOCUMENTED_PRIOR_CONTEXT = {
    "historical_candidate_id": DEFAULT_CANDIDATE_ID,
    "historical_miro_fish_status": "MIRO_FISH_SUPPORTS_CANDIDATE",
    "historical_score": 96,
    "historical_source_recommendation": "ELIGIBLE_FOR_FUTURE_TINY_LIVE",
    "historical_markov_regime": "BULL_TREND",
    "historical_context_source": "DOCUMENTED_PRIOR_REVIEW_CONTEXT",
    "historical_context_path": DOCUMENTED_PRIOR_CONTEXT_SOURCE,
}

NO_ORDER_NOTE = "R91 reviews source warnings only. No orders, no payloads, no env changes, no network, no Binance."


def build_source_warning_review(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    dry_run: bool = True,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC).isoformat()
    quality = build_miro_fish_quality_gate(family="NORMAL", log_dir=resolved_log_dir)
    preflight = build_live_arming_preflight(candidate_id=candidate_id, log_dir=resolved_log_dir)
    risk_contract = build_tiny_live_risk_contract_payload(candidate_id=candidate_id)
    archive = build_betrayal_candle_archive_status(log_dir=resolved_log_dir)
    snapshot = build_review_record_arming_snapshot(candidate_id=candidate_id, dry_run=True, write=False, log_dir=resolved_log_dir)

    current_support = _current_candidate_support(candidate_id=candidate_id, quality=quality)
    preflight_diagnostic = _current_preflight_diagnostic(preflight)
    risk_continuity = _risk_contract_continuity(risk_contract=risk_contract, snapshot=snapshot)
    hash_continuity = _hash_chain_continuity(snapshot)
    classification = _source_warning_classification(
        current_support=current_support,
        preflight_diagnostic=preflight_diagnostic,
        archive=archive,
        snapshot=snapshot,
    )
    rehydration = _rehydrated_review_context(candidate_id=candidate_id, current_support=current_support)
    statuses = _source_warning_statuses(
        current_support=current_support,
        classification=classification,
        rehydration=rehydration,
        archive=archive,
    )
    readiness_effect = {
        "readiness_class": "SOURCE_CHAIN_NEEDS_REVIEW"
        if classification != "NONE"
        else "CANDIDATE_REVALIDATION_REQUIRED",
        "live_readiness_changed": False,
        "rehydrated_review_context_only": rehydration["rehydration_status"] == REHYDRATION_AVAILABLE_FOR_REVIEW,
        "execution_permission": False,
        "notes": [
            "R91 diagnostics do not alter R90 readiness.",
            "Rehydrated context is historical review context, not current live support.",
        ],
    }
    blockers = _blockers(
        current_support=current_support,
        preflight_diagnostic=preflight_diagnostic,
        classification=classification,
        rehydration=rehydration,
        snapshot=snapshot,
    )

    payload = _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at,
            "candidate_id": candidate_id,
            "risk_contract_hash": risk_continuity["current_risk_contract_hash"],
            "packet_hash": hash_continuity["current_packet_hash"],
            "source_warning_statuses": statuses,
            "current_candidate_support": current_support,
            "current_preflight_diagnostic": preflight_diagnostic,
            "risk_contract_continuity": risk_continuity,
            "hash_chain_continuity": hash_continuity,
            "source_warning_classification": classification,
            "rehydrated_review_context": rehydration,
            "readiness_effect": readiness_effect,
            "next_action_recommendation": _next_action_recommendation(classification, current_support, rehydration),
            "blockers": blockers,
            "dry_run": bool(dry_run),
            "write": bool(write),
            "report_written": False,
            "report_path": str(source_warning_review_path(resolved_log_dir)),
            "notes": [
                NO_ORDER_NOTE,
                "R91 does not mark the candidate live-ready.",
                "R87 boundary and missing R89 review records remain blockers.",
            ],
            "review_only": True,
            "executable": False,
            "env_modified": False,
            "order_type": "not_created",
            "order_payload_created": False,
            "execution_attempted": False,
            "network_allowed": False,
            "secrets_shown": False,
            **_safety_fields(),
        }
    )
    if write and not dry_run:
        write_source_warning_review(payload, log_dir=resolved_log_dir)
        payload["report_written"] = True
    return _sanitize(payload)


def source_warning_review_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / REPORT_FILENAME


def write_source_warning_review(report: Mapping[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = source_warning_review_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_sanitize(dict(report)), handle, sort_keys=True, indent=2)
        handle.write("\n")


def format_source_warning_review_text(payload: Mapping[str, Any]) -> str:
    support = payload.get("current_candidate_support") if isinstance(payload.get("current_candidate_support"), dict) else {}
    preflight = payload.get("current_preflight_diagnostic") if isinstance(payload.get("current_preflight_diagnostic"), dict) else {}
    rehydration = payload.get("rehydrated_review_context") if isinstance(payload.get("rehydrated_review_context"), dict) else {}
    hash_chain = payload.get("hash_chain_continuity") if isinstance(payload.get("hash_chain_continuity"), dict) else {}
    return "\n".join(
        [
            f"R91 Source Warning Review status: {payload.get('status')}",
            str(payload.get("execution_mode")),
            f"candidate_id: {payload.get('candidate_id')}",
            f"risk_contract_hash: {payload.get('risk_contract_hash')}",
            f"packet_hash: {payload.get('packet_hash')}",
            f"source_warning_classification: {payload.get('source_warning_classification')}",
            f"candidate_present_currently: {support.get('candidate_present_currently')}",
            f"current_final_quality_status: {support.get('final_quality_status')}",
            f"current_preflight_status: {preflight.get('final_preflight_status')}",
            f"primary_root_blocker: {preflight.get('primary_root_blocker')}",
            f"cascading_risk_funding_blockers: {preflight.get('cascading_risk_funding_blockers')}",
            f"rehydration_status: {rehydration.get('rehydration_status')}",
            f"hash_chain_consistent: {hash_chain.get('hash_chain_consistent')}",
            f"next_action_recommendation: {payload.get('next_action_recommendation')}",
            f"report_written: {payload.get('report_written')} report_path: {payload.get('report_path')}",
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            "No-order/no-network/no-env-change safety note: R91 is diagnostic and rehydration review only.",
            NO_ORDER_NOTE,
        ]
    )


def _current_candidate_support(*, candidate_id: str, quality: Mapping[str, Any]) -> dict[str, Any]:
    candidates = []
    for key in ("top_supported_candidates", "operator_review_candidates", "blocked_or_rejected_candidates"):
        rows = quality.get(key) if isinstance(quality.get(key), list) else []
        candidates.extend(row for row in rows if isinstance(row, dict))
    match = next((row for row in candidates if row.get("candidate_id") == candidate_id), None)
    if match:
        reason = "current_candidate_found"
        present = True
    else:
        reason = _missing_candidate_reason(quality)
        present = False
    return {
        "candidate_present_currently": present,
        "candidate_id": candidate_id,
        "final_quality_status": match.get("final_quality_status") if match else None,
        "final_quality_score": match.get("final_quality_score") if match else None,
        "source_recommendation": match.get("source_recommendation") if match else None,
        "markov_regime": match.get("markov_regime") if match else None,
        "markov_gate_status": match.get("markov_gate_status") if match else None,
        "missing_reason": None if present else reason,
        "supported_candidates_count": len(quality.get("top_supported_candidates") or []),
        "blocked_or_rejected_count": len(quality.get("blocked_or_rejected_candidates") or []),
    }


def _missing_candidate_reason(quality: Mapping[str, Any]) -> str:
    blockers = quality.get("blockers") if isinstance(quality.get("blockers"), list) else []
    if any("insufficient" in str(item).lower() for item in blockers):
        return "data_insufficient"
    if not quality.get("top_supported_candidates") and not quality.get("blocked_or_rejected_candidates"):
        return "no_candidate_found"
    return "candidate_filtered_out"


def _current_preflight_diagnostic(preflight: Mapping[str, Any]) -> dict[str, Any]:
    blockers = list(preflight.get("blockers") or [])
    hierarchy = (
        preflight.get("preflight_blocker_hierarchy")
        if isinstance(preflight.get("preflight_blocker_hierarchy"), dict)
        else {}
    )
    primary = list(hierarchy.get("primary_blockers") or [])
    secondary = list(hierarchy.get("secondary_blockers") or [])
    cascading = list(hierarchy.get("cascading_blockers") or [])
    strategy_quality_only = preflight.get("final_preflight_status") == "BLOCKED_BY_STRATEGY_QUALITY"
    return {
        "phase": preflight.get("phase"),
        "final_preflight_status": preflight.get("final_preflight_status"),
        "blocked_by_strategy_quality": strategy_quality_only,
        "blockers": blockers,
        "preflight_blocker_hierarchy": hierarchy,
        "primary_root_blocker": primary[0] if primary else None,
        "primary_blockers": primary,
        "secondary_blockers": secondary,
        "cascading_risk_funding_blockers": [
            blocker
            for blocker in cascading
            if any(token in str(blocker) for token in ("risk_contract", "funding", "max_loss", "margin"))
        ],
        "not_evaluated": hierarchy.get("not_evaluated") or {},
        "independent_continuity": hierarchy.get("independent_continuity") or {},
        "top_candidate_preflight": preflight.get("top_candidate_preflight"),
    }


def _risk_contract_continuity(*, risk_contract: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    validation = risk_contract.get("validation") if isinstance(risk_contract.get("validation"), dict) else {}
    hash_summary = snapshot.get("hash_chain_summary") if isinstance(snapshot.get("hash_chain_summary"), dict) else {}
    return {
        "risk_contract_valid_for_preflight": validation.get("validation_status") == "RISK_CONTRACT_VALID_FOR_PREFLIGHT",
        "validation_status": validation.get("validation_status"),
        "current_risk_contract_hash": hash_summary.get("current_risk_contract_hash"),
        "risk_contract_candidate_id": risk_contract.get("candidate_id"),
    }


def _hash_chain_continuity(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    hash_summary = snapshot.get("hash_chain_summary") if isinstance(snapshot.get("hash_chain_summary"), dict) else {}
    return {
        "hash_chain_consistent": bool(hash_summary.get("hash_chain_consistent")),
        "current_risk_contract_hash": hash_summary.get("current_risk_contract_hash"),
        "current_packet_hash": hash_summary.get("current_packet_hash"),
        "hash_chain_items": hash_summary.get("hash_chain_items") or {},
        "hash_chain_blockers": hash_summary.get("hash_chain_blockers") or [],
    }


def _source_warning_classification(
    *,
    current_support: Mapping[str, Any],
    preflight_diagnostic: Mapping[str, Any],
    archive: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> str:
    warnings = archive.get("archive_integrity_warnings") if isinstance(archive.get("archive_integrity_warnings"), dict) else {}
    if int(warnings.get("malformed_json_lines") or 0) or int(warnings.get("non_object_json_lines") or 0):
        return ARCHIVE_INTEGRITY_WARNING
    if not current_support.get("candidate_present_currently"):
        if current_support.get("missing_reason") == "data_insufficient":
            return CURRENT_SOURCE_DATA_INSUFFICIENT
        return CANDIDATE_SUPPORT_MISSING
    if preflight_diagnostic.get("blocked_by_strategy_quality"):
        return STRATEGY_PERFORMANCE_DRIFT
    if (snapshot.get("source_chain_summary") or {}).get("source_warning_review_required"):
        return UNKNOWN_SOURCE_WARNING
    return "NONE"


def _rehydrated_review_context(*, candidate_id: str, current_support: Mapping[str, Any]) -> dict[str, Any]:
    if current_support.get("candidate_present_currently"):
        return {
            "rehydration_status": REHYDRATION_NOT_NEEDED,
            "rehydrated_review_context": False,
        }
    if candidate_id == DOCUMENTED_PRIOR_CONTEXT["historical_candidate_id"]:
        return {
            **DOCUMENTED_PRIOR_CONTEXT,
            "rehydration_status": REHYDRATION_AVAILABLE_FOR_REVIEW,
            "secondary_status": REHYDRATION_REVIEW_ONLY_NOT_CURRENT_SUPPORT,
            "rehydrated_review_context": True,
            "current_support": False,
            "live_permission": False,
        }
    return {
        "rehydration_status": REHYDRATION_BLOCKED_BY_MISSING_HISTORICAL_CONTEXT,
        "secondary_status": REHYDRATION_REVALIDATION_REQUIRED,
        "rehydrated_review_context": False,
        "current_support": False,
        "live_permission": False,
    }


def _source_warning_statuses(
    *,
    current_support: Mapping[str, Any],
    classification: str,
    rehydration: Mapping[str, Any],
    archive: Mapping[str, Any],
) -> list[str]:
    statuses = [SOURCE_WARNING_REVIEW_ONLY]
    warnings = archive.get("archive_integrity_warnings") if isinstance(archive.get("archive_integrity_warnings"), dict) else {}
    if classification == "NONE" and current_support.get("candidate_present_currently"):
        statuses.append(SOURCE_CHAIN_CLEAN_CURRENT_SUPPORT_PRESENT)
    else:
        statuses.append(SOURCE_CHAIN_WARNINGS_PRESENT)
    if not current_support.get("candidate_present_currently"):
        statuses.append(SOURCE_CHAIN_CANDIDATE_NOT_SUPPORTED_CURRENTLY)
    if rehydration.get("rehydration_status") == REHYDRATION_AVAILABLE_FOR_REVIEW:
        statuses.append(SOURCE_CHAIN_CANDIDATE_SUPPORT_REHYDRATED_FOR_REVIEW)
    if classification in {CANDIDATE_SUPPORT_MISSING, CURRENT_SOURCE_DATA_INSUFFICIENT, STRATEGY_PERFORMANCE_DRIFT}:
        statuses.append(SOURCE_CHAIN_CANDIDATE_REVALIDATION_REQUIRED)
    if classification == CURRENT_SOURCE_DATA_INSUFFICIENT:
        statuses.append(SOURCE_CHAIN_DATA_INSUFFICIENT)
    if int(warnings.get("malformed_json_lines") or 0) or int(warnings.get("non_object_json_lines") or 0):
        statuses.append(SOURCE_CHAIN_ARCHIVE_WARNING_ONLY)
    statuses.append(SOURCE_CHAIN_NON_EXECUTABLE_ONLY)
    return list(dict.fromkeys(statuses))


def _next_action_recommendation(
    classification: str,
    current_support: Mapping[str, Any],
    rehydration: Mapping[str, Any],
) -> str:
    if classification == ARCHIVE_INTEGRITY_WARNING:
        return "R92 Archive/Data Hygiene Report"
    if classification in {CURRENT_SOURCE_DATA_INSUFFICIENT, CANDIDATE_SUPPORT_MISSING}:
        return "R92 Current Candidate Revalidation from Fresh Runtime Data"
    if classification == STRATEGY_PERFORMANCE_DRIFT:
        return "R92 Source Chain Repair for Strategy Performance Inputs"
    if current_support.get("candidate_present_currently") and rehydration.get("rehydration_status") == REHYDRATION_NOT_NEEDED:
        return "R92 Human Confirmation Write Trial"
    return "R92 Current Candidate Revalidation from Fresh Runtime Data"


def _blockers(
    *,
    current_support: Mapping[str, Any],
    preflight_diagnostic: Mapping[str, Any],
    classification: str,
    rehydration: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> list[str]:
    blockers = []
    if classification != "NONE":
        blockers.append(str(classification).lower())
    if not current_support.get("candidate_present_currently"):
        blockers.append("r83_candidate_not_supported_in_current_source_chain")
    blockers.extend(preflight_diagnostic.get("primary_blockers") or preflight_diagnostic.get("blockers") or [])
    blockers.extend(preflight_diagnostic.get("secondary_blockers") or [])
    blockers.extend((snapshot.get("blocker_summary") or {}).get("blockers") or [])
    if rehydration.get("rehydration_status") != REHYDRATION_NOT_NEEDED:
        blockers.append(str(rehydration.get("rehydration_status")).lower())
    blockers.append("r91_review_only_not_live_permission")
    return list(dict.fromkeys(str(item) for item in blockers if item))


def _safety_fields() -> dict[str, Any]:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "order_payload_created": ORDER_PAYLOAD_CREATED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in (
            "live_execution_enabled",
            "allow_live_orders",
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "order_payload_created",
            "network_allowed",
            "secrets_shown",
            "executable",
            "env_modified",
            "execution_permission",
            "live_permission",
        ):
            if key in sanitized:
                sanitized[key] = False
        if "global_kill_switch" in sanitized:
            sanitized["global_kill_switch"] = True
        if "review_only" in sanitized:
            sanitized["review_only"] = True
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
