"""R92 source-chain repair diagnostics for strategy performance inputs.

This module explains current Miro Fish / Markov / preflight drift without
forcing support, creating order payloads, calling Binance, mutating env files,
or changing live readiness.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.live_arming_preflight import build_live_arming_preflight
from src.app.hammer_radar.operator.markov_regime_gate import (
    BULL_TREND,
    LOW_VOLATILITY,
    REGIME_NEUTRAL_OR_INSUFFICIENT_DATA,
    REGIME_SUPPORTS_CANDIDATE,
    build_markov_regime_gate,
)
from src.app.hammer_radar.operator.miro_fish_quality_gate import (
    MIRO_FISH_OPERATOR_REVIEW_ONLY,
    MIRO_FISH_SUPPORTS_CANDIDATE,
    build_miro_fish_quality_gate,
)
from src.app.hammer_radar.operator.review_record_aggregator import build_review_record_arming_snapshot
from src.app.hammer_radar.operator.source_warning_review import build_source_warning_review
from src.app.hammer_radar.operator.strategy_performance import build_live_eligibility_matrix
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID, build_tiny_live_risk_contract_payload

PHASE = "R92"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "SOURCE_CHAIN_REPAIR_STRATEGY_PERFORMANCE_INPUTS_ONLY_NO_ORDER"
REPORT_FILENAME = "source_chain_repair_report.json"

SOURCE_CHAIN_REPAIR_REVIEW_ONLY = "SOURCE_CHAIN_REPAIR_REVIEW_ONLY"
STRATEGY_PERFORMANCE_DRIFT_CONFIRMED = "STRATEGY_PERFORMANCE_DRIFT_CONFIRMED"
MARKOV_REGIME_DRIFT_CONFIRMED = "MARKOV_REGIME_DRIFT_CONFIRMED"
MIRO_FISH_DOWNGRADE_CONFIRMED = "MIRO_FISH_DOWNGRADE_CONFIRMED"
PREFLIGHT_SELECTION_BLOCKED_BY_STRATEGY_QUALITY = "PREFLIGHT_SELECTION_BLOCKED_BY_STRATEGY_QUALITY"
RISK_CONTRACT_CONTINUITY_VALID = "RISK_CONTRACT_CONTINUITY_VALID"
FIELD_MAPPING_REPAIR_RECOMMENDED = "FIELD_MAPPING_REPAIR_RECOMMENDED"
CURRENT_REVALIDATION_REQUIRED = "CURRENT_REVALIDATION_REQUIRED"
OPERATOR_SEAT_REVIEW_REQUIRED = "OPERATOR_SEAT_REVIEW_REQUIRED"
SOURCE_CHAIN_NON_EXECUTABLE_ONLY = "SOURCE_CHAIN_NON_EXECUTABLE_ONLY"
PREFLIGHT_BLOCKER_HIERARCHY_REPAIRED = "PREFLIGHT_BLOCKER_HIERARCHY_REPAIRED"

LEGITIMATE_MARKET_REGIME_DRIFT = "LEGITIMATE_MARKET_REGIME_DRIFT"
MIRO_FISH_THRESHOLD_DOWNGRADE = "MIRO_FISH_THRESHOLD_DOWNGRADE"
PREFLIGHT_SELECTION_STRICTNESS = "PREFLIGHT_SELECTION_STRICTNESS"
R84_RISK_CONTRACT_LINKAGE_GAP = "R84_RISK_CONTRACT_LINKAGE_GAP"
STRATEGY_PERFORMANCE_INPUT_STALE = "STRATEGY_PERFORMANCE_INPUT_STALE"
STRATEGY_PERFORMANCE_INPUT_MISSING = "STRATEGY_PERFORMANCE_INPUT_MISSING"
FIELD_MAPPING_INCONSISTENCY = "FIELD_MAPPING_INCONSISTENCY"
NO_REPAIR_REQUIRED_REVALIDATION_ONLY = "NO_REPAIR_REQUIRED_REVALIDATION_ONLY"
UNKNOWN_REPAIR_CLASSIFICATION = "UNKNOWN_REPAIR_CLASSIFICATION"

OPERATOR_SEAT_REVIEW_ONLY = "OPERATOR_SEAT_REVIEW_ONLY"
OPERATOR_SEAT_AGREES_WITH_COUNCIL = "OPERATOR_SEAT_AGREES_WITH_COUNCIL"
OPERATOR_SEAT_DISAGREES_REVIEW_REQUIRED = "OPERATOR_SEAT_DISAGREES_REVIEW_REQUIRED"
OPERATOR_SEAT_REQUESTS_REVALIDATION = "OPERATOR_SEAT_REQUESTS_REVALIDATION"
OPERATOR_SEAT_NO_OVERRIDE_POWER = "OPERATOR_SEAT_NO_OVERRIDE_POWER"

ARCHITECT_SEAT_RECOMMENDS_REVALIDATION = "ARCHITECT_SEAT_RECOMMENDS_REVALIDATION"
ARCHITECT_SEAT_RECOMMENDS_SOURCE_MAPPING_REPAIR = "ARCHITECT_SEAT_RECOMMENDS_SOURCE_MAPPING_REPAIR"
ARCHITECT_SEAT_RECOMMENDS_WAIT_FOR_MARKOV_SUPPORT = "ARCHITECT_SEAT_RECOMMENDS_WAIT_FOR_MARKOV_SUPPORT"
ARCHITECT_SEAT_RECOMMENDS_HUMAN_RECORDS_ONLY_AFTER_SOURCE_REPAIR = (
    "ARCHITECT_SEAT_RECOMMENDS_HUMAN_RECORDS_ONLY_AFTER_SOURCE_REPAIR"
)
ARCHITECT_SEAT_RECOMMENDS_NO_LIVE_ACTION = "ARCHITECT_SEAT_RECOMMENDS_NO_LIVE_ACTION"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

DOCUMENTED_PRIOR_CONTEXT = {
    "candidate_id": DEFAULT_CANDIDATE_ID,
    "previous_documented_miro_fish_status": MIRO_FISH_SUPPORTS_CANDIDATE,
    "previous_documented_final_quality_score": 96,
    "previous_documented_source_recommendation": "ELIGIBLE_FOR_FUTURE_TINY_LIVE",
    "previous_documented_markov_regime": BULL_TREND,
    "context_source": "DOCUMENTED_PRIOR_REVIEW_CONTEXT",
    "context_path": "docs/hammer_radar/R84_LIVE_FUNDING_FINAL_ARMING_PREFLIGHT.md",
}

NO_ORDER_NOTE = "R92 repairs source-chain interpretation only. No orders, no payloads, no env changes, no network, no Binance."


def build_source_chain_repair(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    dry_run: bool = True,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC).isoformat()
    quality = build_miro_fish_quality_gate(family="NORMAL", log_dir=resolved_log_dir)
    markov = build_markov_regime_gate(log_dir=resolved_log_dir)
    preflight = build_live_arming_preflight(candidate_id=candidate_id, log_dir=resolved_log_dir)
    risk_contract = build_tiny_live_risk_contract_payload(candidate_id=candidate_id)
    matrix = build_live_eligibility_matrix(log_dir=resolved_log_dir)
    snapshot = build_review_record_arming_snapshot(candidate_id=candidate_id, dry_run=True, write=False, log_dir=resolved_log_dir)
    source_warning = build_source_warning_review(candidate_id=candidate_id, dry_run=True, write=False, log_dir=resolved_log_dir)

    miro_review = _current_miro_fish_review(candidate_id=candidate_id, quality=quality)
    markov_review = _current_markov_review(candidate_id=candidate_id, markov=markov, miro_review=miro_review)
    strategy_review = _strategy_performance_input_review(candidate_id=candidate_id, matrix=matrix, miro_review=miro_review)
    risk_continuity = _risk_contract_continuity(candidate_id=candidate_id, risk_contract=risk_contract, snapshot=snapshot)
    preflight_review = _preflight_selection_review(
        preflight=preflight,
        miro_review=miro_review,
        risk_continuity=risk_continuity,
    )
    hash_continuity = _hash_chain_continuity(snapshot)
    repair_classification = _repair_classification(
        miro_review=miro_review,
        markov_review=markov_review,
        strategy_review=strategy_review,
        preflight_review=preflight_review,
        risk_continuity=risk_continuity,
    )
    statuses = _r92_statuses(
        repair_classification=repair_classification,
        miro_review=miro_review,
        markov_review=markov_review,
        preflight_review=preflight_review,
        risk_continuity=risk_continuity,
    )
    operator_seat = _operator_architect_seat_review(
        repair_classification=repair_classification,
        miro_review=miro_review,
        markov_review=markov_review,
        preflight_review=preflight_review,
    )
    next_phase, repair_scope = _recommendation(repair_classification, preflight_review, markov_review)
    blockers = _blockers(
        source_warning=source_warning,
        miro_review=miro_review,
        markov_review=markov_review,
        preflight_review=preflight_review,
        risk_continuity=risk_continuity,
        hash_continuity=hash_continuity,
    )

    payload = _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at,
            "candidate_id": candidate_id,
            "risk_contract_hash": hash_continuity["current_risk_contract_hash"],
            "packet_hash": hash_continuity["current_packet_hash"],
            "r92_statuses": statuses,
            "repair_classification": repair_classification,
            "current_miro_fish_review": miro_review,
            "current_markov_review": markov_review,
            "strategy_performance_input_review": strategy_review,
            "preflight_selection_review": preflight_review,
            "risk_contract_continuity": risk_continuity,
            "hash_chain_continuity": hash_continuity,
            "operator_architect_seat_review": operator_seat,
            "recommended_next_phase": next_phase,
            "recommended_repair_scope": repair_scope,
            "no_live_reason": _no_live_reason(miro_review, markov_review, preflight_review),
            "blockers": blockers,
            "dry_run": bool(dry_run),
            "write": bool(write),
            "report_written": False,
            "report_path": str(source_chain_repair_path(resolved_log_dir)),
            "notes": [
                NO_ORDER_NOTE,
                "Operator/Architect Seat is advisory only and cannot override Markov, Miro Fish, R87, or missing records.",
                "R92 does not mark the candidate supported or live-ready.",
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
        write_source_chain_repair(payload, log_dir=resolved_log_dir)
        payload["report_written"] = True
    return _sanitize(payload)


def source_chain_repair_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / REPORT_FILENAME


def write_source_chain_repair(report: Mapping[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = source_chain_repair_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_sanitize(dict(report)), handle, sort_keys=True, indent=2)
        handle.write("\n")


def format_source_chain_repair_text(payload: Mapping[str, Any]) -> str:
    miro = payload.get("current_miro_fish_review") if isinstance(payload.get("current_miro_fish_review"), dict) else {}
    markov = payload.get("current_markov_review") if isinstance(payload.get("current_markov_review"), dict) else {}
    preflight = payload.get("preflight_selection_review") if isinstance(payload.get("preflight_selection_review"), dict) else {}
    risk = payload.get("risk_contract_continuity") if isinstance(payload.get("risk_contract_continuity"), dict) else {}
    seat = payload.get("operator_architect_seat_review") if isinstance(payload.get("operator_architect_seat_review"), dict) else {}
    hash_chain = payload.get("hash_chain_continuity") if isinstance(payload.get("hash_chain_continuity"), dict) else {}
    return "\n".join(
        [
            f"R92 Source Chain Repair status: {payload.get('status')}",
            str(payload.get("execution_mode")),
            f"candidate_id: {payload.get('candidate_id')}",
            f"risk_contract_hash: {payload.get('risk_contract_hash')}",
            f"packet_hash: {payload.get('packet_hash')}",
            f"repair_classification: {payload.get('repair_classification')}",
            f"miro_fish_status: {miro.get('final_quality_status')} score={miro.get('final_quality_score')}",
            f"markov_regime: {markov.get('markov_regime')} gate={markov.get('markov_gate_status')}",
            f"preflight_selection_status: {preflight.get('selection_status')}",
            f"primary_root_blocker: {preflight.get('primary_root_blocker')}",
            f"cascading_risk_funding_blockers: {preflight.get('cascading_risk_funding_blockers')}",
            f"risk_contract_continuity: {risk.get('continuity_status')}",
            f"hash_chain_consistent: {hash_chain.get('hash_chain_consistent')}",
            f"operator_architect_seat: {seat.get('architect_position')}",
            f"recommended_next_phase: {payload.get('recommended_next_phase')}",
            f"recommended_repair_scope: {payload.get('recommended_repair_scope')}",
            f"report_written: {payload.get('report_written')} report_path: {payload.get('report_path')}",
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            "No-order/no-network/no-env-change safety note: R92 is diagnostic and repair-review only.",
            NO_ORDER_NOTE,
        ]
    )


def _current_miro_fish_review(*, candidate_id: str, quality: Mapping[str, Any]) -> dict[str, Any]:
    candidates = []
    for key in ("top_supported_candidates", "operator_review_candidates", "blocked_or_rejected_candidates"):
        rows = quality.get(key) if isinstance(quality.get(key), list) else []
        candidates.extend(row for row in rows if isinstance(row, dict))
    match = next((row for row in candidates if row.get("candidate_id") == candidate_id), None)
    votes = match.get("fish_votes") if isinstance(match, dict) and isinstance(match.get("fish_votes"), list) else []
    downgrade_reasons = [
        blocker
        for vote in votes
        for blocker in (vote.get("blockers") or [])
        if blocker
    ]
    if match and match.get("final_quality_status") == MIRO_FISH_OPERATOR_REVIEW_ONLY and not downgrade_reasons:
        downgrade_reasons.append("mixed_fish_votes_do_not_reach_support_threshold")
    return {
        "candidate_present_currently": bool(match),
        "candidate_id": candidate_id,
        "final_quality_status": match.get("final_quality_status") if match else None,
        "final_quality_score": match.get("final_quality_score") if match else None,
        "source_recommendation": match.get("source_recommendation") if match else None,
        "fish_votes": votes,
        "downgrade_reasons": list(dict.fromkeys(str(reason) for reason in downgrade_reasons)),
        "supported_candidates_count": len(quality.get("top_supported_candidates") or []),
        "operator_review_candidates_count": len(quality.get("operator_review_candidates") or []),
        "blocked_or_rejected_count": len(quality.get("blocked_or_rejected_candidates") or []),
    }


def _current_markov_review(
    *,
    candidate_id: str,
    markov: Mapping[str, Any],
    miro_review: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = []
    for key in ("normal_candidate_regime_gates", "betrayal_candidate_regime_gates"):
        rows = markov.get(key) if isinstance(markov.get(key), list) else []
        candidates.extend(row for row in rows if isinstance(row, dict))
    match = next((row for row in candidates if row.get("candidate_id") == candidate_id), None)
    prior = DOCUMENTED_PRIOR_CONTEXT if candidate_id == DOCUMENTED_PRIOR_CONTEXT["candidate_id"] else {}
    regime = match.get("current_regime") if match else None
    gate_status = match.get("gate_status") if match else None
    drift = bool(prior and regime and regime != prior.get("previous_documented_markov_regime"))
    return {
        "candidate_id": candidate_id,
        "markov_regime": regime,
        "markov_gate_status": gate_status,
        "regime_confidence": match.get("regime_confidence") if match else None,
        "gate_reason": match.get("gate_reason") if match else None,
        "previous_documented_regime": prior.get("previous_documented_markov_regime"),
        "previous_context_source": prior.get("context_source"),
        "regime_drift_detected": drift,
        "likely_effect_on_candidate": _markov_effect(gate_status, miro_review),
    }


def _strategy_performance_input_review(
    *,
    candidate_id: str,
    matrix: Mapping[str, Any],
    miro_review: Mapping[str, Any],
) -> dict[str, Any]:
    rows = matrix.get("recommendations") if isinstance(matrix.get("recommendations"), list) else []
    match = next((row for row in rows if _candidate_id_from_strategy_row(row) == candidate_id), None)
    missing_fields = []
    for key in ("sample_count", "win_rate_pct", "avg_pnl_pct", "total_pnl_pct", "recommendation"):
        if not match or match.get(key) in (None, ""):
            missing_fields.append(key)
    return {
        "candidate_id": candidate_id,
        "source_recommendation": match.get("recommendation") if match else miro_review.get("source_recommendation"),
        "sample_count": match.get("sample_count") if match else None,
        "win_rate_pct": match.get("win_rate_pct") if match else None,
        "avg_pnl_pct": match.get("avg_pnl_pct") if match else None,
        "total_pnl_pct": match.get("total_pnl_pct") if match else None,
        "best_pnl_pct": match.get("best_pnl_pct") if match else None,
        "worst_pnl_pct": match.get("worst_pnl_pct") if match else None,
        "data_freshness": "not_available_from_strategy_matrix",
        "performance_source_path": matrix.get("archive_log_dir"),
        "missing_fields": missing_fields,
        "recommendation_blockers": match.get("blockers") if match else ["strategy_performance_candidate_missing"],
        "strategy_input_present": bool(match),
    }


def _preflight_selection_review(
    *,
    preflight: Mapping[str, Any],
    miro_review: Mapping[str, Any],
    risk_continuity: Mapping[str, Any],
) -> dict[str, Any]:
    blockers = list(preflight.get("blockers") or [])
    hierarchy = (
        preflight.get("preflight_blocker_hierarchy")
        if isinstance(preflight.get("preflight_blocker_hierarchy"), dict)
        else {}
    )
    primary = list(hierarchy.get("primary_blockers") or [])
    secondary = list(hierarchy.get("secondary_blockers") or [])
    cascading_from_hierarchy = list(hierarchy.get("cascading_blockers") or [])
    top_candidate = preflight.get("top_candidate_preflight")
    top_candidate_missing = top_candidate in (None, {}, []) or (
        isinstance(top_candidate, dict) and top_candidate.get("candidate_id") in (None, "")
    )
    no_supported = (
        top_candidate_missing
        and miro_review.get("candidate_present_currently")
        and miro_review.get("final_quality_status") != MIRO_FISH_SUPPORTS_CANDIDATE
    )
    cascading = cascading_from_hierarchy or [
        blocker
        for blocker in blockers
        if any(token in str(blocker) for token in ("risk_contract", "funding", "max_loss", "margin"))
    ]
    not_evaluated = hierarchy.get("not_evaluated") if isinstance(hierarchy.get("not_evaluated"), dict) else {}
    return {
        "final_preflight_status": preflight.get("final_preflight_status"),
        "top_candidate_preflight": top_candidate,
        "top_candidate_preflight_is_null": top_candidate_missing,
        "selection_status": "NO_SUPPORTED_MIRO_FISH_CANDIDATE_SELECTED" if no_supported else "PREFLIGHT_SELECTED_CANDIDATE",
        "primary_root_blocker": primary[0] if primary else "no_supported_miro_fish_candidate" if no_supported else None,
        "primary_blockers": primary,
        "secondary_blockers": secondary,
        "preflight_blocker_hierarchy": hierarchy,
        "preflight_blockers": blockers,
        "blocked_by_strategy_quality": preflight.get("final_preflight_status") == "BLOCKED_BY_STRATEGY_QUALITY",
        "risk_funding_missing_blockers_are_secondary": bool(
            no_supported
            and (
                secondary
                or cascading
                or not_evaluated.get("risk_contract")
                or not_evaluated.get("funding_config")
            )
            and risk_continuity.get("risk_contract_valid")
        ),
        "cascading_risk_funding_blockers": cascading,
        "not_evaluated": not_evaluated,
        "independent_continuity": hierarchy.get("independent_continuity") or {},
        "risk_contract_continuity_should_be_reported_separately": bool(no_supported and risk_continuity.get("risk_contract_valid")),
        "future_repair_recommendation": (
            "R84 preflight blocker hierarchy repaired; keep monitoring current candidate and Markov support"
            if hierarchy.get("hierarchy_status") == PREFLIGHT_BLOCKER_HIERARCHY_REPAIRED
            else "R93 improve R84 preflight blocker hierarchy: distinguish primary strategy-quality block from secondary risk/funding not evaluated"
            if no_supported and cascading
            else None
        ),
    }


def _risk_contract_continuity(*, candidate_id: str, risk_contract: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    validation = risk_contract.get("validation") if isinstance(risk_contract.get("validation"), dict) else {}
    funding = risk_contract.get("funding_config") if isinstance(risk_contract.get("funding_config"), dict) else {}
    contract = risk_contract.get("risk_contract") if isinstance(risk_contract.get("risk_contract"), dict) else {}
    hash_summary = snapshot.get("hash_chain_summary") if isinstance(snapshot.get("hash_chain_summary"), dict) else {}
    valid = validation.get("validation_status") == "RISK_CONTRACT_VALID_FOR_PREFLIGHT"
    matches = risk_contract.get("candidate_id") == candidate_id or contract.get("candidate_id") == candidate_id
    return {
        "risk_contract_valid": bool(valid),
        "validation_status": validation.get("validation_status"),
        "risk_contract_candidate_id": risk_contract.get("candidate_id") or contract.get("candidate_id"),
        "risk_contract_candidate_matches": bool(matches),
        "risk_contract_hash": hash_summary.get("current_risk_contract_hash"),
        "risk_contract_hash_matches_current": bool(hash_summary.get("hash_chain_consistent")),
        "funding_config_present": bool(funding.get("funding_config_present")),
        "continuity_status": RISK_CONTRACT_CONTINUITY_VALID if valid and matches else R84_RISK_CONTRACT_LINKAGE_GAP,
    }


def _hash_chain_continuity(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    hash_summary = snapshot.get("hash_chain_summary") if isinstance(snapshot.get("hash_chain_summary"), dict) else {}
    items = hash_summary.get("hash_chain_items") if isinstance(hash_summary.get("hash_chain_items"), dict) else {}
    return {
        "hash_chain_consistent": bool(hash_summary.get("hash_chain_consistent")),
        "current_risk_contract_hash": hash_summary.get("current_risk_contract_hash"),
        "current_packet_hash": hash_summary.get("current_packet_hash"),
        "r85_risk_contract_hash": items.get("r85_risk_contract_hash"),
        "r88_risk_contract_hash": items.get("r88_risk_contract_hash"),
        "r89_risk_contract_hash": items.get("r89_risk_contract_hash"),
        "r88_packet_hash": items.get("r88_packet_hash"),
        "r89_packet_hash": items.get("r89_packet_hash"),
        "hash_chain_items": items,
        "hash_chain_blockers": hash_summary.get("hash_chain_blockers") or [],
    }


def _repair_classification(
    *,
    miro_review: Mapping[str, Any],
    markov_review: Mapping[str, Any],
    strategy_review: Mapping[str, Any],
    preflight_review: Mapping[str, Any],
    risk_continuity: Mapping[str, Any],
) -> str:
    if not strategy_review.get("strategy_input_present"):
        return STRATEGY_PERFORMANCE_INPUT_MISSING
    if markov_review.get("regime_drift_detected") and markov_review.get("markov_regime") == LOW_VOLATILITY:
        return LEGITIMATE_MARKET_REGIME_DRIFT
    if miro_review.get("final_quality_status") == MIRO_FISH_OPERATOR_REVIEW_ONLY:
        return MIRO_FISH_THRESHOLD_DOWNGRADE
    if preflight_review.get("top_candidate_preflight_is_null") and risk_continuity.get("risk_contract_valid"):
        return PREFLIGHT_SELECTION_STRICTNESS
    if preflight_review.get("risk_contract_continuity_should_be_reported_separately"):
        return R84_RISK_CONTRACT_LINKAGE_GAP
    if strategy_review.get("missing_fields"):
        return STRATEGY_PERFORMANCE_INPUT_STALE
    return UNKNOWN_REPAIR_CLASSIFICATION


def _r92_statuses(
    *,
    repair_classification: str,
    miro_review: Mapping[str, Any],
    markov_review: Mapping[str, Any],
    preflight_review: Mapping[str, Any],
    risk_continuity: Mapping[str, Any],
) -> list[str]:
    statuses = [SOURCE_CHAIN_REPAIR_REVIEW_ONLY]
    if repair_classification in {LEGITIMATE_MARKET_REGIME_DRIFT, MIRO_FISH_THRESHOLD_DOWNGRADE, PREFLIGHT_SELECTION_STRICTNESS}:
        statuses.append(STRATEGY_PERFORMANCE_DRIFT_CONFIRMED)
    if markov_review.get("regime_drift_detected"):
        statuses.append(MARKOV_REGIME_DRIFT_CONFIRMED)
    if miro_review.get("final_quality_status") == MIRO_FISH_OPERATOR_REVIEW_ONLY:
        statuses.append(MIRO_FISH_DOWNGRADE_CONFIRMED)
    if preflight_review.get("blocked_by_strategy_quality"):
        statuses.append(PREFLIGHT_SELECTION_BLOCKED_BY_STRATEGY_QUALITY)
    if risk_continuity.get("continuity_status") == RISK_CONTRACT_CONTINUITY_VALID:
        statuses.append(RISK_CONTRACT_CONTINUITY_VALID)
    if preflight_review.get("risk_contract_continuity_should_be_reported_separately") and not preflight_review.get("preflight_blocker_hierarchy"):
        statuses.append(FIELD_MAPPING_REPAIR_RECOMMENDED)
    statuses.extend([CURRENT_REVALIDATION_REQUIRED, OPERATOR_SEAT_REVIEW_REQUIRED, SOURCE_CHAIN_NON_EXECUTABLE_ONLY])
    return list(dict.fromkeys(statuses))


def _operator_architect_seat_review(
    *,
    repair_classification: str,
    miro_review: Mapping[str, Any],
    markov_review: Mapping[str, Any],
    preflight_review: Mapping[str, Any],
) -> dict[str, Any]:
    architect_positions = [ARCHITECT_SEAT_RECOMMENDS_NO_LIVE_ACTION]
    if markov_review.get("markov_regime") == LOW_VOLATILITY:
        architect_positions.append(ARCHITECT_SEAT_RECOMMENDS_WAIT_FOR_MARKOV_SUPPORT)
    if miro_review.get("final_quality_status") == MIRO_FISH_OPERATOR_REVIEW_ONLY:
        architect_positions.append(ARCHITECT_SEAT_RECOMMENDS_REVALIDATION)
    if preflight_review.get("risk_contract_continuity_should_be_reported_separately") and not preflight_review.get("preflight_blocker_hierarchy"):
        architect_positions.append(ARCHITECT_SEAT_RECOMMENDS_SOURCE_MAPPING_REPAIR)
    architect_positions.append(ARCHITECT_SEAT_RECOMMENDS_HUMAN_RECORDS_ONLY_AFTER_SOURCE_REPAIR)
    return {
        "seat_name": "Operator/Architect Seat",
        "council_position": "current council keeps candidate review-only under Markov/Miro Fish/preflight blockers",
        "operator_position": "review_required",
        "architect_position": list(dict.fromkeys(architect_positions)),
        "repair_classification_considered": repair_classification,
        "disagreement_status": OPERATOR_SEAT_AGREES_WITH_COUNCIL,
        "seat_statuses": [
            OPERATOR_SEAT_REVIEW_ONLY,
            OPERATOR_SEAT_REQUESTS_REVALIDATION,
            OPERATOR_SEAT_NO_OVERRIDE_POWER,
        ],
        "override_power": False,
        "execution_permission": False,
        "can_override_markov": False,
        "can_override_miro_fish": False,
        "can_bypass_r87": False,
        "can_make_ticket_executable": False,
        "can_create_payloads": False,
        "notes": [
            "Operator/Architect Seat is advisory only.",
            "It can request revalidation or source mapping repair, but cannot override blockers.",
        ],
    }


def _recommendation(
    repair_classification: str,
    preflight_review: Mapping[str, Any],
    markov_review: Mapping[str, Any],
) -> tuple[str, str]:
    if preflight_review.get("risk_contract_continuity_should_be_reported_separately"):
        if preflight_review.get("preflight_blocker_hierarchy"):
            return (
                "R94 Current Candidate Revalidation + Markov Support Watch",
                "monitor current candidate under repaired R84 blocker hierarchy without forcing Miro Fish or Markov support",
            )
        return (
            "R93 R84 Preflight Blocker Hierarchy Repair",
            "separate primary strategy-quality blocker from cascading risk/funding not evaluated because no candidate selected",
        )
    if repair_classification in {LEGITIMATE_MARKET_REGIME_DRIFT, MIRO_FISH_THRESHOLD_DOWNGRADE}:
        return (
            "R93 Current Candidate Revalidation + Markov/Miro Fish Threshold Review",
            f"revalidate candidate under current {markov_review.get('markov_regime')} regime without forcing support",
        )
    return ("R93 Current Candidate Revalidation", "refresh and inspect strategy-performance inputs before any record-writing trial")


def _no_live_reason(
    miro_review: Mapping[str, Any],
    markov_review: Mapping[str, Any],
    preflight_review: Mapping[str, Any],
) -> str:
    return (
        "No live action: Miro Fish status is "
        f"{miro_review.get('final_quality_status')}, Markov gate is {markov_review.get('markov_gate_status')}, "
        f"and R84 preflight is {preflight_review.get('final_preflight_status')}; R87 and missing R89 records remain blockers."
    )


def _blockers(
    *,
    source_warning: Mapping[str, Any],
    miro_review: Mapping[str, Any],
    markov_review: Mapping[str, Any],
    preflight_review: Mapping[str, Any],
    risk_continuity: Mapping[str, Any],
    hash_continuity: Mapping[str, Any],
) -> list[str]:
    blockers = list(source_warning.get("blockers") or [])
    if miro_review.get("final_quality_status") != MIRO_FISH_SUPPORTS_CANDIDATE:
        blockers.append("miro_fish_not_supporting_candidate")
    if markov_review.get("markov_gate_status") != REGIME_SUPPORTS_CANDIDATE:
        blockers.append("markov_gate_not_supporting_candidate")
    if preflight_review.get("blocked_by_strategy_quality"):
        blockers.append("r84_blocked_by_strategy_quality")
    if preflight_review.get("risk_funding_missing_blockers_are_secondary"):
        blockers.append("r84_risk_funding_blockers_are_cascading_from_no_supported_candidate")
    if not risk_continuity.get("risk_contract_valid"):
        blockers.append("risk_contract_continuity_invalid")
    if not hash_continuity.get("hash_chain_consistent"):
        blockers.append("hash_chain_mismatch")
    blockers.extend(["operator_architect_seat_advisory_only", "live_execution_forbidden_in_r92"])
    return list(dict.fromkeys(str(blocker) for blocker in blockers if blocker))


def _markov_effect(gate_status: Any, miro_review: Mapping[str, Any]) -> str:
    if gate_status == REGIME_SUPPORTS_CANDIDATE:
        return "regime support can contribute a pass vote, but still does not grant live permission"
    if gate_status == REGIME_NEUTRAL_OR_INSUFFICIENT_DATA:
        return "neutral Markov gate causes Regime Fish warning and can downgrade support to operator review only"
    if miro_review.get("final_quality_status") == MIRO_FISH_OPERATOR_REVIEW_ONLY:
        return "non-supportive Markov context aligns with current Miro Fish operator-review result"
    return "Markov context requires current revalidation before any human record-writing trial"


def _candidate_id_from_strategy_row(row: Mapping[str, Any]) -> str:
    return f"normal|BTCUSDT|{row.get('timeframe')}|{row.get('direction')}|{row.get('entry_mode')}"


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


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
