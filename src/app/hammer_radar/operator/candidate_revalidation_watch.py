"""R94 current candidate revalidation and Markov support watch.

This module is read-only. It watches current local strategy, Miro Fish,
Markov, R84, R87, R89, and hash-chain state without creating executable
payloads, calling Binance, checking balances, mutating env files, or enabling
live execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.human_confirmation_records import REQUIRED_RECORD_TYPES, build_human_confirmation_records_status
from src.app.hammer_radar.operator.live_arming_preflight import build_live_arming_preflight
from src.app.hammer_radar.operator.live_env_boundary_review import build_live_env_boundary_review
from src.app.hammer_radar.operator.markov_regime_gate import (
    BEAR_TREND,
    BULL_TREND,
    REGIME_SUPPORTS_CANDIDATE,
    build_markov_regime_gate,
)
from src.app.hammer_radar.operator.miro_fish_quality_gate import (
    MIRO_FISH_OPERATOR_REVIEW_ONLY,
    MIRO_FISH_SUPPORTS_CANDIDATE,
    build_miro_fish_quality_gate,
)
from src.app.hammer_radar.operator.review_record_aggregator import build_review_record_arming_snapshot
from src.app.hammer_radar.operator.strategy_performance import (
    ELIGIBLE_FOR_FUTURE_TINY_LIVE,
    build_live_eligibility_matrix,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import (
    DEFAULT_CANDIDATE_ID,
    RISK_CONTRACT_VALID_FOR_PREFLIGHT,
    build_tiny_live_risk_contract_payload,
)

PHASE = "R94"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "CURRENT_CANDIDATE_REVALIDATION_MARKOV_SUPPORT_WATCH_ONLY_NO_ORDER"
REPORT_FILENAME = "candidate_revalidation_watch.json"

CANDIDATE_REVALIDATION_WATCH_ONLY = "CANDIDATE_REVALIDATION_WATCH_ONLY"
CANDIDATE_PRESENT_CURRENTLY = "CANDIDATE_PRESENT_CURRENTLY"
CANDIDATE_MIRO_FISH_OPERATOR_REVIEW_ONLY = "CANDIDATE_MIRO_FISH_OPERATOR_REVIEW_ONLY"
CANDIDATE_MIRO_FISH_SUPPORT_RESTORED = "CANDIDATE_MIRO_FISH_SUPPORT_RESTORED"
MARKOV_SUPPORT_PENDING = "MARKOV_SUPPORT_PENDING"
MARKOV_SUPPORT_RESTORED = "MARKOV_SUPPORT_RESTORED"
STRATEGY_INPUTS_PRESENT = "STRATEGY_INPUTS_PRESENT"
STRATEGY_INPUTS_ACCEPTABLE_FOR_REVIEW = "STRATEGY_INPUTS_ACCEPTABLE_FOR_REVIEW"
PREFLIGHT_HIERARCHY_REPAIRED_CONFIRMED = "PREFLIGHT_HIERARCHY_REPAIRED_CONFIRMED"
CANDIDATE_REVALIDATION_REQUIRED = "CANDIDATE_REVALIDATION_REQUIRED"
CANDIDATE_REVALIDATION_PASSED_FOR_REVIEW_ONLY = "CANDIDATE_REVALIDATION_PASSED_FOR_REVIEW_ONLY"
CANDIDATE_REVALIDATION_NON_EXECUTABLE_ONLY = "CANDIDATE_REVALIDATION_NON_EXECUTABLE_ONLY"

WAIT_FOR_MARKOV_SUPPORT = "WAIT_FOR_MARKOV_SUPPORT"
WAIT_FOR_MIRO_FISH_SUPPORT = "WAIT_FOR_MIRO_FISH_SUPPORT"
CURRENT_SUPPORT_RESTORED_FOR_REVIEW = "CURRENT_SUPPORT_RESTORED_FOR_REVIEW"
STRATEGY_INPUTS_ACCEPTABLE_BUT_REGIME_PENDING = "STRATEGY_INPUTS_ACCEPTABLE_BUT_REGIME_PENDING"
STRATEGY_INPUTS_DEGRADED = "STRATEGY_INPUTS_DEGRADED"
SOURCE_DATA_STALE_OR_MISSING = "SOURCE_DATA_STALE_OR_MISSING"
CANDIDATE_NOT_PRESENT = "CANDIDATE_NOT_PRESENT"
NON_EXECUTABLE_REVALIDATION_ONLY = "NON_EXECUTABLE_REVALIDATION_ONLY"

ARCHITECT_SEAT_RECOMMENDS_WAIT_FOR_MARKOV_SUPPORT = "ARCHITECT_SEAT_RECOMMENDS_WAIT_FOR_MARKOV_SUPPORT"
ARCHITECT_SEAT_RECOMMENDS_CURRENT_REVALIDATION_WATCH = "ARCHITECT_SEAT_RECOMMENDS_CURRENT_REVALIDATION_WATCH"
ARCHITECT_SEAT_RECOMMENDS_NO_LIVE_ACTION = "ARCHITECT_SEAT_RECOMMENDS_NO_LIVE_ACTION"
ARCHITECT_SEAT_RECOMMENDS_HUMAN_RECORD_TRIAL_AFTER_SUPPORT_RESTORED = (
    "ARCHITECT_SEAT_RECOMMENDS_HUMAN_RECORD_TRIAL_AFTER_SUPPORT_RESTORED"
)

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

DOCUMENTED_PRIOR_MARKOV_REGIME = BULL_TREND
NO_ORDER_NOTE = "R94 watches current support only. No orders, no payloads, no env changes, no network, no Binance."


def build_candidate_revalidation_watch(
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
    matrix = build_live_eligibility_matrix(log_dir=resolved_log_dir)
    preflight = build_live_arming_preflight(candidate_id=candidate_id, log_dir=resolved_log_dir)
    risk_contract = build_tiny_live_risk_contract_payload(candidate_id=candidate_id)
    snapshot = build_review_record_arming_snapshot(candidate_id=candidate_id, dry_run=True, write=False, log_dir=resolved_log_dir)
    confirmations = build_human_confirmation_records_status(candidate_id=candidate_id, log_dir=resolved_log_dir)
    boundary = build_live_env_boundary_review(candidate_id=candidate_id, dry_run=True, write=False, log_dir=resolved_log_dir)

    candidate_identity = _candidate_identity(candidate_id=candidate_id, quality=quality)
    miro_watch = _miro_fish_watch(candidate_id=candidate_id, quality=quality)
    markov_watch = _markov_support_watch(candidate_id=candidate_id, markov=markov, candidate_identity=candidate_identity)
    strategy_watch = _strategy_input_watch(candidate_id=candidate_id, matrix=matrix, miro_watch=miro_watch)
    preflight_watch = _preflight_hierarchy_watch(preflight)
    risk_hash = _risk_hash_continuity(candidate_id=candidate_id, risk_contract=risk_contract, snapshot=snapshot)
    review_boundary = _review_record_and_boundary_status(confirmations=confirmations, boundary=boundary)
    support_restored = bool(
        miro_watch.get("support_restored")
        and markov_watch.get("markov_support_restored")
        and strategy_watch.get("strategy_inputs_acceptable_for_review")
    )
    revalidation_class = _revalidation_class(
        candidate_identity=candidate_identity,
        miro_watch=miro_watch,
        markov_watch=markov_watch,
        strategy_watch=strategy_watch,
        support_restored=support_restored,
    )
    statuses = _r94_statuses(
        candidate_identity=candidate_identity,
        miro_watch=miro_watch,
        markov_watch=markov_watch,
        strategy_watch=strategy_watch,
        preflight_watch=preflight_watch,
        support_restored=support_restored,
    )
    seat = _operator_architect_seat_review(
        revalidation_class=revalidation_class,
        support_restored=support_restored,
        markov_watch=markov_watch,
        miro_watch=miro_watch,
    )
    next_action = _next_action_recommendation(support_restored=support_restored, review_boundary=review_boundary)
    blockers = _blockers(
        candidate_identity=candidate_identity,
        miro_watch=miro_watch,
        markov_watch=markov_watch,
        strategy_watch=strategy_watch,
        preflight_watch=preflight_watch,
        risk_hash=risk_hash,
        review_boundary=review_boundary,
    )

    payload = _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at,
            "candidate_id": candidate_id,
            "risk_contract_hash": risk_hash.get("risk_contract_hash"),
            "packet_hash": risk_hash.get("packet_hash"),
            "r94_statuses": statuses,
            "revalidation_class": revalidation_class,
            "candidate_identity": candidate_identity,
            "miro_fish_watch": miro_watch,
            "markov_support_watch": markov_watch,
            "strategy_input_watch": strategy_watch,
            "preflight_hierarchy_watch": preflight_watch,
            "risk_hash_continuity": risk_hash,
            "review_record_and_boundary_status": review_boundary,
            "operator_architect_seat_review": seat,
            "revalidation_result": _revalidation_result(revalidation_class=revalidation_class, support_restored=support_restored),
            "support_restored": support_restored,
            "next_action_recommendation": next_action,
            "blockers": blockers,
            "dry_run": bool(dry_run),
            "write": bool(write),
            "report_written": False,
            "report_path": str(candidate_revalidation_watch_path(resolved_log_dir)),
            "notes": [
                NO_ORDER_NOTE,
                "Support restored is review-only and still does not bypass R84, R87, or R89.",
                "R94 does not force Miro Fish or Markov support.",
            ],
            "review_only": True,
            "executable": False,
            "env_modified": False,
            "order_type": "not_created",
            **_safety_fields(),
        }
    )
    if write and not dry_run:
        write_candidate_revalidation_watch(payload, log_dir=resolved_log_dir)
        payload["report_written"] = True
    return _sanitize(payload)


def candidate_revalidation_watch_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / REPORT_FILENAME


def write_candidate_revalidation_watch(report: Mapping[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = candidate_revalidation_watch_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_sanitize(dict(report)), handle, sort_keys=True, indent=2)
        handle.write("\n")


def format_candidate_revalidation_watch_text(payload: Mapping[str, Any]) -> str:
    miro = payload.get("miro_fish_watch") if isinstance(payload.get("miro_fish_watch"), dict) else {}
    markov = payload.get("markov_support_watch") if isinstance(payload.get("markov_support_watch"), dict) else {}
    strategy = payload.get("strategy_input_watch") if isinstance(payload.get("strategy_input_watch"), dict) else {}
    preflight = payload.get("preflight_hierarchy_watch") if isinstance(payload.get("preflight_hierarchy_watch"), dict) else {}
    return "\n".join(
        [
            f"R94 Candidate Revalidation Watch status: {payload.get('status')}",
            str(payload.get("execution_mode")),
            f"candidate_id: {payload.get('candidate_id')}",
            f"risk_contract_hash: {payload.get('risk_contract_hash')}",
            f"packet_hash: {payload.get('packet_hash')}",
            f"revalidation_class: {payload.get('revalidation_class')}",
            f"miro_fish_status: {miro.get('current_miro_fish_status')} score={miro.get('current_miro_fish_score')}",
            f"markov_regime: {markov.get('current_markov_regime')} gate={markov.get('current_markov_gate_status')}",
            (
                "strategy_inputs: "
                f"sample_count={strategy.get('sample_count')} win_rate_pct={strategy.get('win_rate_pct')} "
                f"avg_pnl_pct={strategy.get('avg_pnl_pct')} total_pnl_pct={strategy.get('total_pnl_pct')}"
            ),
            f"support_restored: {payload.get('support_restored')}",
            f"r84_hierarchy_status: {preflight.get('hierarchy_status')}",
            f"next_action_recommendation: {payload.get('next_action_recommendation')}",
            f"report_written: {payload.get('report_written')} report_path: {payload.get('report_path')}",
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            "No-order/no-network/no-env-change safety note: R94 is watch/revalidation only.",
            NO_ORDER_NOTE,
        ]
    )


def _candidate_identity(*, candidate_id: str, quality: Mapping[str, Any]) -> dict[str, Any]:
    match = _quality_candidate(candidate_id=candidate_id, quality=quality)
    parsed = _parse_candidate_id(candidate_id)
    return {
        "candidate_id": candidate_id,
        "candidate_present_currently": bool(match),
        "symbol": match.get("symbol") if match else parsed.get("symbol"),
        "timeframe": match.get("timeframe") if match else parsed.get("timeframe"),
        "direction": match.get("direction") if match else parsed.get("direction"),
        "entry_mode": match.get("entry_mode") if match else parsed.get("entry_mode"),
    }


def _miro_fish_watch(*, candidate_id: str, quality: Mapping[str, Any]) -> dict[str, Any]:
    match = _quality_candidate(candidate_id=candidate_id, quality=quality)
    votes = match.get("fish_votes") if isinstance(match, dict) and isinstance(match.get("fish_votes"), list) else []
    downgrade_reasons = [
        blocker
        for vote in votes
        for blocker in (vote.get("blockers") or [])
        if blocker
    ]
    status = match.get("final_quality_status") if match else None
    support_restored = status == MIRO_FISH_SUPPORTS_CANDIDATE
    requirements = []
    if not support_restored:
        requirements.extend(["Miro Fish final quality status must return to MIRO_FISH_SUPPORTS_CANDIDATE"])
        if "regime_not_supportive" in downgrade_reasons:
            requirements.append("Markov Regime Fish must stop warning on regime_not_supportive")
        if "risk_fields_unavailable" in downgrade_reasons:
            requirements.append("Risk Fish must receive explicit risk fields or supported downstream risk context")
    return {
        "candidate_id": candidate_id,
        "current_miro_fish_status": status,
        "current_miro_fish_score": match.get("final_quality_score") if match else None,
        "source_recommendation": match.get("source_recommendation") if match else None,
        "fish_votes": votes,
        "downgrade_reasons": list(dict.fromkeys(str(reason) for reason in downgrade_reasons)),
        "support_restored": support_restored,
        "support_restoration_requirements": requirements,
    }


def _markov_support_watch(
    *,
    candidate_id: str,
    markov: Mapping[str, Any],
    candidate_identity: Mapping[str, Any],
) -> dict[str, Any]:
    match = _markov_candidate(candidate_id=candidate_id, markov=markov)
    gate_status = match.get("gate_status") if match else None
    direction = str(candidate_identity.get("direction") or "")
    acceptable = [BULL_TREND] if direction == "long" else [BEAR_TREND] if direction == "short" else []
    restored = gate_status == REGIME_SUPPORTS_CANDIDATE
    current_regime = match.get("current_regime") if match else None
    return {
        "candidate_id": candidate_id,
        "current_markov_regime": current_regime,
        "current_markov_gate_status": gate_status,
        "prior_documented_markov_regime": DOCUMENTED_PRIOR_MARKOV_REGIME if candidate_id == DEFAULT_CANDIDATE_ID else None,
        "regime_confidence": match.get("regime_confidence") if match else None,
        "gate_reason": match.get("gate_reason") if match else None,
        "markov_support_restored": restored,
        "markov_support_required": True,
        "acceptable_markov_regimes": acceptable,
        "markov_watch_reason": (
            "Markov gate currently supports the candidate for review."
            if restored
            else f"Waiting for Markov gate to return {REGIME_SUPPORTS_CANDIDATE}; current regime is {current_regime}."
        ),
    }


def _strategy_input_watch(*, candidate_id: str, matrix: Mapping[str, Any], miro_watch: Mapping[str, Any]) -> dict[str, Any]:
    rows = matrix.get("recommendations") if isinstance(matrix.get("recommendations"), list) else []
    match = next((row for row in rows if _candidate_id_from_strategy_row(row) == candidate_id), None)
    blockers = list(match.get("blockers") or []) if match else ["strategy_performance_candidate_missing"]
    source_recommendation = match.get("recommendation") if match else miro_watch.get("source_recommendation")
    acceptable = bool(match and source_recommendation == ELIGIBLE_FOR_FUTURE_TINY_LIVE and not blockers)
    return {
        "candidate_id": candidate_id,
        "sample_count": match.get("sample_count") if match else None,
        "win_rate_pct": match.get("win_rate_pct") if match else None,
        "avg_pnl_pct": match.get("avg_pnl_pct") if match else None,
        "total_pnl_pct": match.get("total_pnl_pct") if match else None,
        "best_pnl_pct": match.get("best_pnl_pct") if match else None,
        "worst_pnl_pct": match.get("worst_pnl_pct") if match else None,
        "source_recommendation": source_recommendation,
        "strategy_inputs_present": bool(match),
        "strategy_inputs_acceptable_for_review": acceptable,
        "strategy_input_blockers": blockers,
    }


def _preflight_hierarchy_watch(preflight: Mapping[str, Any]) -> dict[str, Any]:
    hierarchy = preflight.get("preflight_blocker_hierarchy") if isinstance(preflight.get("preflight_blocker_hierarchy"), dict) else {}
    return {
        "final_preflight_status": preflight.get("final_preflight_status"),
        "primary_blockers": hierarchy.get("primary_blockers") or [],
        "secondary_blockers": hierarchy.get("secondary_blockers") or [],
        "not_evaluated": hierarchy.get("not_evaluated") or {},
        "hierarchy_status": hierarchy.get("hierarchy_status"),
        "hierarchy_repaired": hierarchy.get("hierarchy_status") == "PREFLIGHT_BLOCKER_HIERARCHY_REPAIRED",
    }


def _risk_hash_continuity(
    *,
    candidate_id: str,
    risk_contract: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    validation = risk_contract.get("validation") if isinstance(risk_contract.get("validation"), dict) else {}
    hash_summary = snapshot.get("hash_chain_summary") if isinstance(snapshot.get("hash_chain_summary"), dict) else {}
    return {
        "candidate_id": candidate_id,
        "risk_contract_hash": hash_summary.get("current_risk_contract_hash"),
        "packet_hash": hash_summary.get("current_packet_hash"),
        "risk_contract_continuity_valid": validation.get("validation_status") == RISK_CONTRACT_VALID_FOR_PREFLIGHT,
        "validation_status": validation.get("validation_status"),
        "hash_chain_consistent": bool(hash_summary.get("hash_chain_consistent")),
        "hash_chain_items": hash_summary.get("hash_chain_items") or {},
    }


def _review_record_and_boundary_status(
    *,
    confirmations: Mapping[str, Any],
    boundary: Mapping[str, Any],
) -> dict[str, Any]:
    summary = confirmations.get("summary") if isinstance(confirmations.get("summary"), dict) else {}
    missing = summary.get("missing_record_types") if isinstance(summary.get("missing_record_types"), list) else list(REQUIRED_RECORD_TYPES)
    return {
        "r89_review_records_complete": not missing,
        "missing_record_types": missing,
        "recorded_record_types": summary.get("recorded_record_types") or [],
        "r87_boundary_status": boundary.get("boundary_status"),
        "live_env_arming_allowed": False,
        "execution_boundary_intact": (boundary.get("execution_boundary_review") or {}).get("boundary_status") == "EXECUTION_BOUNDARY_INTACT",
    }


def _operator_architect_seat_review(
    *,
    revalidation_class: str,
    support_restored: bool,
    markov_watch: Mapping[str, Any],
    miro_watch: Mapping[str, Any],
) -> dict[str, Any]:
    positions = [ARCHITECT_SEAT_RECOMMENDS_NO_LIVE_ACTION, ARCHITECT_SEAT_RECOMMENDS_CURRENT_REVALIDATION_WATCH]
    if not markov_watch.get("markov_support_restored"):
        positions.append(ARCHITECT_SEAT_RECOMMENDS_WAIT_FOR_MARKOV_SUPPORT)
    if support_restored:
        positions.append(ARCHITECT_SEAT_RECOMMENDS_HUMAN_RECORD_TRIAL_AFTER_SUPPORT_RESTORED)
    return {
        "seat_name": "Operator/Architect Seat",
        "council_position": (
            "current council requires restored Miro Fish support, restored Markov support, R84 selection, "
            "R87 boundary review, and R89 records before later gates"
        ),
        "operator_architect_position": list(dict.fromkeys(positions)),
        "miro_fish_status_considered": miro_watch.get("current_miro_fish_status"),
        "markov_gate_status_considered": markov_watch.get("current_markov_gate_status"),
        "revalidation_class_considered": revalidation_class,
        "override_power": False,
        "execution_permission": False,
        "can_override_markov": False,
        "can_override_miro_fish": False,
        "can_bypass_r84": False,
        "can_bypass_r87": False,
        "can_bypass_r89": False,
    }


def _revalidation_class(
    *,
    candidate_identity: Mapping[str, Any],
    miro_watch: Mapping[str, Any],
    markov_watch: Mapping[str, Any],
    strategy_watch: Mapping[str, Any],
    support_restored: bool,
) -> str:
    if not candidate_identity.get("candidate_present_currently"):
        return CANDIDATE_NOT_PRESENT
    if not strategy_watch.get("strategy_inputs_present"):
        return SOURCE_DATA_STALE_OR_MISSING
    if not strategy_watch.get("strategy_inputs_acceptable_for_review"):
        return STRATEGY_INPUTS_DEGRADED
    if support_restored:
        return CURRENT_SUPPORT_RESTORED_FOR_REVIEW
    if not markov_watch.get("markov_support_restored"):
        return STRATEGY_INPUTS_ACCEPTABLE_BUT_REGIME_PENDING
    if not miro_watch.get("support_restored"):
        return WAIT_FOR_MIRO_FISH_SUPPORT
    return NON_EXECUTABLE_REVALIDATION_ONLY


def _r94_statuses(
    *,
    candidate_identity: Mapping[str, Any],
    miro_watch: Mapping[str, Any],
    markov_watch: Mapping[str, Any],
    strategy_watch: Mapping[str, Any],
    preflight_watch: Mapping[str, Any],
    support_restored: bool,
) -> list[str]:
    statuses = [CANDIDATE_REVALIDATION_WATCH_ONLY]
    if candidate_identity.get("candidate_present_currently"):
        statuses.append(CANDIDATE_PRESENT_CURRENTLY)
    if miro_watch.get("support_restored"):
        statuses.append(CANDIDATE_MIRO_FISH_SUPPORT_RESTORED)
    elif miro_watch.get("current_miro_fish_status") == MIRO_FISH_OPERATOR_REVIEW_ONLY:
        statuses.append(CANDIDATE_MIRO_FISH_OPERATOR_REVIEW_ONLY)
    statuses.append(MARKOV_SUPPORT_RESTORED if markov_watch.get("markov_support_restored") else MARKOV_SUPPORT_PENDING)
    if strategy_watch.get("strategy_inputs_present"):
        statuses.append(STRATEGY_INPUTS_PRESENT)
    if strategy_watch.get("strategy_inputs_acceptable_for_review"):
        statuses.append(STRATEGY_INPUTS_ACCEPTABLE_FOR_REVIEW)
    if preflight_watch.get("hierarchy_repaired"):
        statuses.append(PREFLIGHT_HIERARCHY_REPAIRED_CONFIRMED)
    statuses.append(CANDIDATE_REVALIDATION_PASSED_FOR_REVIEW_ONLY if support_restored else CANDIDATE_REVALIDATION_REQUIRED)
    statuses.append(CANDIDATE_REVALIDATION_NON_EXECUTABLE_ONLY)
    return list(dict.fromkeys(statuses))


def _next_action_recommendation(*, support_restored: bool, review_boundary: Mapping[str, Any]) -> str:
    if support_restored:
        return "R95 Human Confirmation Record Trial, still non-executable"
    if review_boundary.get("r89_review_records_complete"):
        return "R95 Markov Support Watch Scheduler / Candidate Revalidation Loop"
    return "R95 Markov Support Watch Scheduler / Candidate Revalidation Loop"


def _revalidation_result(*, revalidation_class: str, support_restored: bool) -> dict[str, Any]:
    return {
        "support_restored": support_restored,
        "revalidation_class": revalidation_class,
        "live_permission": False,
        "execution_permission": False,
        "operator_note": "R94 result is review-only and cannot create execution readiness.",
    }


def _blockers(
    *,
    candidate_identity: Mapping[str, Any],
    miro_watch: Mapping[str, Any],
    markov_watch: Mapping[str, Any],
    strategy_watch: Mapping[str, Any],
    preflight_watch: Mapping[str, Any],
    risk_hash: Mapping[str, Any],
    review_boundary: Mapping[str, Any],
) -> list[str]:
    blockers = []
    if not candidate_identity.get("candidate_present_currently"):
        blockers.append("candidate_not_present_currently")
    if not miro_watch.get("support_restored"):
        blockers.append("miro_fish_support_not_restored")
    if not markov_watch.get("markov_support_restored"):
        blockers.append("markov_support_not_restored")
    if not strategy_watch.get("strategy_inputs_acceptable_for_review"):
        blockers.extend(strategy_watch.get("strategy_input_blockers") or ["strategy_inputs_not_acceptable_for_review"])
    if not preflight_watch.get("hierarchy_repaired"):
        blockers.append("r84_preflight_hierarchy_not_repaired")
    blockers.extend(preflight_watch.get("primary_blockers") or [])
    if not risk_hash.get("risk_contract_continuity_valid"):
        blockers.append("risk_contract_continuity_invalid")
    if not risk_hash.get("hash_chain_consistent"):
        blockers.append("hash_chain_mismatch")
    if not review_boundary.get("r89_review_records_complete"):
        blockers.append("r89_review_records_missing")
    if review_boundary.get("r87_boundary_status") != "LIVE_ENV_LOCKED_SAFE":
        blockers.append("r87_boundary_blocks_live_arming")
    blockers.append("r94_watch_only_not_live_permission")
    return list(dict.fromkeys(str(blocker) for blocker in blockers if blocker))


def _quality_candidate(*, candidate_id: str, quality: Mapping[str, Any]) -> dict[str, Any]:
    candidates = []
    for key in ("top_supported_candidates", "operator_review_candidates", "blocked_or_rejected_candidates"):
        rows = quality.get(key) if isinstance(quality.get(key), list) else []
        candidates.extend(row for row in rows if isinstance(row, dict))
    return next((row for row in candidates if row.get("candidate_id") == candidate_id), {})


def _markov_candidate(*, candidate_id: str, markov: Mapping[str, Any]) -> dict[str, Any]:
    candidates = []
    for key in ("normal_candidate_regime_gates", "betrayal_candidate_regime_gates"):
        rows = markov.get(key) if isinstance(markov.get(key), list) else []
        candidates.extend(row for row in rows if isinstance(row, dict))
    return next((row for row in candidates if row.get("candidate_id") == candidate_id), {})


def _parse_candidate_id(candidate_id: str) -> dict[str, Any]:
    parts = candidate_id.split("|")
    if len(parts) >= 5:
        return {
            "symbol": parts[1],
            "timeframe": parts[2],
            "direction": parts[3],
            "entry_mode": parts[4],
        }
    return {}


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
            "live_env_arming_allowed",
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
    if isinstance(payload, tuple):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, Path):
        return str(payload)
    return payload
