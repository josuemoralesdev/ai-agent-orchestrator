"""R95 dual-lane candidate watch for normal and betrayal lanes.

This module compares the current normal-candidate revalidation watch with the
betrayal audit lane. It is review-only and never creates orders, executable
payloads, Binance requests, balance checks, env mutations, or live permission.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_strategy_audit import (
    BETRAYAL_PRIMARY_CANDIDATE,
    BETRAYAL_WATCHLIST,
    build_betrayal_strategy_audit,
)
from src.app.hammer_radar.operator.candidate_revalidation_watch import (
    CURRENT_SUPPORT_RESTORED_FOR_REVIEW,
    STRATEGY_INPUTS_ACCEPTABLE_BUT_REGIME_PENDING,
    build_candidate_revalidation_watch,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

PHASE = "R95"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "DUAL_LANE_CANDIDATE_WATCH_NORMAL_BETRAYAL_ONLY_NO_ORDER"
REPORT_FILENAME = "dual_lane_candidate_watch.json"

DUAL_LANE_CANDIDATE_WATCH_ONLY = "DUAL_LANE_CANDIDATE_WATCH_ONLY"
NORMAL_LANE_ACTIVE = "NORMAL_LANE_ACTIVE"
NORMAL_SUPPORT_PENDING = "NORMAL_SUPPORT_PENDING"
NORMAL_SUPPORT_RESTORED = "NORMAL_SUPPORT_RESTORED"
BETRAYAL_LANE_ACTIVE = "BETRAYAL_LANE_ACTIVE"
BETRAYAL_AUDIT_EVIDENCE_PRESENT = "BETRAYAL_AUDIT_EVIDENCE_PRESENT"
BETRAYAL_TRUE_PAPER_REQUIRED = "BETRAYAL_TRUE_PAPER_REQUIRED"
BETRAYAL_CANDIDATE_MATURATION_REQUIRED = "BETRAYAL_CANDIDATE_MATURATION_REQUIRED"
NO_LANE_LIVE_READY = "NO_LANE_LIVE_READY"
DUAL_LANE_NON_EXECUTABLE_ONLY = "DUAL_LANE_NON_EXECUTABLE_ONLY"

NORMAL_WAIT_FOR_MARKOV_SUPPORT = "NORMAL_WAIT_FOR_MARKOV_SUPPORT"
NORMAL_WAIT_FOR_MIRO_FISH_SUPPORT = "NORMAL_WAIT_FOR_MIRO_FISH_SUPPORT"
NORMAL_SUPPORT_RESTORED_FOR_REVIEW_ONLY = "NORMAL_SUPPORT_RESTORED_FOR_REVIEW_ONLY"
NORMAL_STRATEGY_INPUTS_ACCEPTABLE_BUT_REGIME_PENDING = "NORMAL_STRATEGY_INPUTS_ACCEPTABLE_BUT_REGIME_PENDING"
NORMAL_NOT_READY = "NORMAL_NOT_READY"

BETRAYAL_AUDIT_ONLY = "BETRAYAL_AUDIT_ONLY"
BETRAYAL_PAPER_TRACKING_REQUIRED = "BETRAYAL_PAPER_TRACKING_REQUIRED"
BETRAYAL_NEAR_PAPER_CANDIDATE = "BETRAYAL_NEAR_PAPER_CANDIDATE"
BETRAYAL_TRUE_PAPER_READY_FOR_REVIEW = "BETRAYAL_TRUE_PAPER_READY_FOR_REVIEW"
BETRAYAL_DATA_INSUFFICIENT = "BETRAYAL_DATA_INSUFFICIENT"
BETRAYAL_NOT_READY = "BETRAYAL_NOT_READY"

DUAL_LANE_WAITING = "DUAL_LANE_WAITING"
NORMAL_LANE_LEADS = "NORMAL_LANE_LEADS"
BETRAYAL_LANE_LEADS_AUDIT_ONLY = "BETRAYAL_LANE_LEADS_AUDIT_ONLY"
BETRAYAL_LANE_NEEDS_TRUE_PAPER = "BETRAYAL_LANE_NEEDS_TRUE_PAPER"
BOTH_LANES_BLOCKED = "BOTH_LANES_BLOCKED"
NON_EXECUTABLE_REVIEW_ONLY = "NON_EXECUTABLE_REVIEW_ONLY"

NAIVE_INVERSE_AUDIT_EVIDENCE_ONLY = "NAIVE_INVERSE_AUDIT_EVIDENCE_ONLY"
AUDIT_ONLY = "AUDIT_ONLY"
NEEDS_TRUE_PAPER_TRACKING = "NEEDS_TRUE_PAPER_TRACKING"

ARCHITECT_SEAT_RECOMMENDS_WAIT_FOR_MARKOV_SUPPORT = "ARCHITECT_SEAT_RECOMMENDS_WAIT_FOR_MARKOV_SUPPORT"
ARCHITECT_SEAT_RECOMMENDS_BETRAYAL_MATURATION_LANE = "ARCHITECT_SEAT_RECOMMENDS_BETRAYAL_MATURATION_LANE"
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

NO_ORDER_NOTE = "R95 is dual-lane watch/review only. No orders, no payloads, no env changes, no network, no Binance."


def build_dual_lane_candidate_watch(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    dry_run: bool = True,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC).isoformat()
    normal_watch = build_candidate_revalidation_watch(
        candidate_id=candidate_id,
        dry_run=True,
        write=False,
        log_dir=resolved_log_dir,
    )
    betrayal_audit = build_betrayal_strategy_audit(log_dir=resolved_log_dir)
    normal_lane = _normal_lane(normal_watch)
    betrayal_lane = _betrayal_lane(betrayal_audit)
    comparison = _dual_lane_comparison(normal_lane=normal_lane, betrayal_lane=betrayal_lane)
    overall = _overall_lane_class(normal_lane=normal_lane, betrayal_lane=betrayal_lane)
    seat = _operator_architect_seat_review(normal_lane=normal_lane, betrayal_lane=betrayal_lane, comparison=comparison)
    statuses = _r95_statuses(normal_lane=normal_lane, betrayal_lane=betrayal_lane)
    blockers = _blockers(normal_lane=normal_lane, betrayal_lane=betrayal_lane)
    next_action = _next_action_recommendation(betrayal_lane=betrayal_lane)

    payload = _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at,
            "normal_candidate_id": candidate_id,
            "risk_contract_hash": normal_watch.get("risk_contract_hash"),
            "packet_hash": normal_watch.get("packet_hash"),
            "r95_statuses": statuses,
            "overall_lane_class": overall,
            "normal_lane": normal_lane,
            "betrayal_lane": betrayal_lane,
            "dual_lane_comparison": comparison,
            "operator_architect_seat_review": seat,
            "next_action_recommendation": next_action,
            "blockers": blockers,
            "dry_run": bool(dry_run),
            "write": bool(write),
            "report_written": False,
            "report_path": str(dual_lane_candidate_watch_path(resolved_log_dir)),
            "notes": [
                NO_ORDER_NOTE,
                "Normal lane support must be restored by Miro Fish and Markov; R95 does not force support.",
                "Betrayal lane evidence is audit-only until true inverse paper tracking exists.",
                "No lane can bypass R84, R87, R89, or later live gates.",
            ],
            "review_only": True,
            "executable": False,
            "env_modified": False,
            "order_type": "not_created",
            **_safety_fields(),
        }
    )
    if write and not dry_run:
        write_dual_lane_candidate_watch(payload, log_dir=resolved_log_dir)
        payload["report_written"] = True
    return _sanitize(payload)


def dual_lane_candidate_watch_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / REPORT_FILENAME


def write_dual_lane_candidate_watch(report: Mapping[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = dual_lane_candidate_watch_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_sanitize(dict(report)), handle, sort_keys=True, indent=2)
        handle.write("\n")


def format_dual_lane_candidate_watch_text(payload: Mapping[str, Any]) -> str:
    normal = payload.get("normal_lane") if isinstance(payload.get("normal_lane"), dict) else {}
    betrayal = payload.get("betrayal_lane") if isinstance(payload.get("betrayal_lane"), dict) else {}
    top = betrayal.get("top_betrayal_candidates") if isinstance(betrayal.get("top_betrayal_candidates"), list) else []
    lines = [
        f"R95 Dual Lane Candidate Watch status: {payload.get('status')}",
        str(payload.get("execution_mode")),
        f"normal_lane_status: {normal.get('normal_lane_status')}",
        f"normal_revalidation_class: {normal.get('revalidation_class')}",
        f"normal_support_restored: {normal.get('support_restored')}",
        f"betrayal_lane_status: {betrayal.get('betrayal_lane_status')}",
        f"betrayal_lane_class: {betrayal.get('betrayal_lane_class')}",
        "top_betrayal_candidates:",
    ]
    if not top:
        lines.append("  none")
    for row in top[:5]:
        lines.append(
            "  "
            f"{row.get('candidate_classification')} {row.get('timeframe')} "
            f"{row.get('original_direction')}->{row.get('betrayal_direction')} "
            f"samples={row.get('sample_count')} inverse_win={row.get('naive_inverse_win_rate_pct')} "
            f"inverse_total={row.get('naive_inverse_total_pnl_pct')} maturity={row.get('maturity_status')}"
        )
    lines.extend(
        [
            f"overall_lane_class: {payload.get('overall_lane_class')}",
            f"next_action_recommendation: {payload.get('next_action_recommendation')}",
            f"report_written: {payload.get('report_written')} report_path: {payload.get('report_path')}",
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            "No-order/no-network/no-env-change safety note: R95 is dual-lane watch only.",
            NO_ORDER_NOTE,
        ]
    )
    return "\n".join(lines)


def _normal_lane(normal_watch: Mapping[str, Any]) -> dict[str, Any]:
    identity = normal_watch.get("candidate_identity") if isinstance(normal_watch.get("candidate_identity"), dict) else {}
    miro = normal_watch.get("miro_fish_watch") if isinstance(normal_watch.get("miro_fish_watch"), dict) else {}
    markov = normal_watch.get("markov_support_watch") if isinstance(normal_watch.get("markov_support_watch"), dict) else {}
    strategy = normal_watch.get("strategy_input_watch") if isinstance(normal_watch.get("strategy_input_watch"), dict) else {}
    support_restored = bool(normal_watch.get("support_restored"))
    revalidation_class = normal_watch.get("revalidation_class")
    lane_class = _normal_lane_class(normal_watch)
    return {
        "normal_lane_status": NORMAL_SUPPORT_RESTORED if support_restored else NORMAL_SUPPORT_PENDING,
        "normal_lane_class": lane_class,
        "candidate_id": normal_watch.get("candidate_id"),
        "candidate_present_currently": identity.get("candidate_present_currently"),
        "current_miro_fish_status": miro.get("current_miro_fish_status"),
        "current_miro_fish_score": miro.get("current_miro_fish_score"),
        "current_markov_regime": markov.get("current_markov_regime"),
        "current_markov_gate_status": markov.get("current_markov_gate_status"),
        "strategy_inputs": {
            "sample_count": strategy.get("sample_count"),
            "win_rate_pct": strategy.get("win_rate_pct"),
            "avg_pnl_pct": strategy.get("avg_pnl_pct"),
            "total_pnl_pct": strategy.get("total_pnl_pct"),
            "source_recommendation": strategy.get("source_recommendation"),
            "strategy_inputs_acceptable_for_review": strategy.get("strategy_inputs_acceptable_for_review"),
        },
        "support_restored": support_restored,
        "revalidation_class": revalidation_class,
        "next_action": normal_watch.get("next_action_recommendation"),
        "live_ready": False,
        "executable": False,
    }


def _normal_lane_class(normal_watch: Mapping[str, Any]) -> str:
    if normal_watch.get("support_restored"):
        return NORMAL_SUPPORT_RESTORED_FOR_REVIEW_ONLY
    revalidation_class = normal_watch.get("revalidation_class")
    if revalidation_class == STRATEGY_INPUTS_ACCEPTABLE_BUT_REGIME_PENDING:
        return NORMAL_STRATEGY_INPUTS_ACCEPTABLE_BUT_REGIME_PENDING
    markov = normal_watch.get("markov_support_watch") if isinstance(normal_watch.get("markov_support_watch"), dict) else {}
    miro = normal_watch.get("miro_fish_watch") if isinstance(normal_watch.get("miro_fish_watch"), dict) else {}
    if not markov.get("markov_support_restored"):
        return NORMAL_WAIT_FOR_MARKOV_SUPPORT
    if not miro.get("support_restored"):
        return NORMAL_WAIT_FOR_MIRO_FISH_SUPPORT
    if revalidation_class == CURRENT_SUPPORT_RESTORED_FOR_REVIEW:
        return NORMAL_SUPPORT_RESTORED_FOR_REVIEW_ONLY
    return NORMAL_NOT_READY


def _betrayal_lane(audit: Mapping[str, Any]) -> dict[str, Any]:
    primary = [
        *_normalized_candidates(audit.get("timeframe_aggregate_primary_candidates"), audit_scope="timeframe_aggregate"),
        *_normalized_candidates(audit.get("direction_entry_mode_primary_candidates"), audit_scope="direction_entry_mode"),
    ]
    watchlist = [
        *_normalized_candidates(audit.get("timeframe_aggregate_watchlist_candidates"), audit_scope="timeframe_aggregate"),
        *_normalized_candidates(audit.get("direction_entry_mode_watchlist_candidates"), audit_scope="direction_entry_mode"),
    ]
    rejected = [
        *_list_field(audit, "timeframe_aggregate_rejected_candidates"),
        *_list_field(audit, "direction_entry_mode_rejected_candidates"),
    ]
    top = sorted([*primary, *watchlist], key=_betrayal_sort_key)
    evidence_present = bool(primary or watchlist)
    lane_class = BETRAYAL_PAPER_TRACKING_REQUIRED if evidence_present else BETRAYAL_DATA_INSUFFICIENT
    return {
        "betrayal_lane_status": BETRAYAL_AUDIT_EVIDENCE_PRESENT if evidence_present else "BETRAYAL_AUDIT_EVIDENCE_NOT_CURRENTLY_PRESENT",
        "betrayal_lane_class": lane_class,
        "betrayal_audit_status": audit.get("status"),
        "primary_candidates": primary,
        "watchlist_candidates": watchlist,
        "rejected_count": len(rejected),
        "top_betrayal_candidates": top[:10],
        "true_paper_required": True,
        "live_ready": False,
        "evidence_label": NAIVE_INVERSE_AUDIT_EVIDENCE_ONLY if evidence_present else "NO_CURRENT_BETRAYAL_AUDIT_CANDIDATES",
        "required_next_steps": _betrayal_required_steps(),
    }


def _normalized_candidates(rows: Any, *, audit_scope: str) -> list[dict[str, Any]]:
    normalized = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        original = row.get("original") if isinstance(row.get("original"), dict) else {}
        betrayal = row.get("betrayal") if isinstance(row.get("betrayal"), dict) else {}
        classification = row.get("recommendation")
        normalized.append(
            {
                "candidate_classification": classification,
                "audit_scope": row.get("audit_scope") or audit_scope,
                "timeframe": row.get("timeframe"),
                "original_direction": row.get("original_direction"),
                "betrayal_direction": row.get("betrayal_direction"),
                "entry_mode": row.get("entry_mode"),
                "sample_count": row.get("sample_count"),
                "original_win_rate_pct": original.get("win_rate_pct"),
                "naive_inverse_win_rate_pct": betrayal.get("win_rate_pct"),
                "original_total_pnl_pct": original.get("total_pnl_pct"),
                "naive_inverse_total_pnl_pct": betrayal.get("total_pnl_pct"),
                "original_avg_pnl_pct": original.get("avg_pnl_pct"),
                "naive_inverse_avg_pnl_pct": betrayal.get("avg_pnl_pct"),
                "maturity_status": NEEDS_TRUE_PAPER_TRACKING
                if classification in {BETRAYAL_PRIMARY_CANDIDATE, BETRAYAL_WATCHLIST}
                else AUDIT_ONLY,
                "true_paper_required": True,
                "live_ready": False,
                "evidence_label": NAIVE_INVERSE_AUDIT_EVIDENCE_ONLY,
                "audit_score": _audit_score(row),
                "required_next_steps": _betrayal_required_steps(),
            }
        )
    return normalized


def _audit_score(row: Mapping[str, Any]) -> float:
    betrayal = row.get("betrayal") if isinstance(row.get("betrayal"), dict) else {}
    classification_bonus = 100.0 if row.get("recommendation") == BETRAYAL_PRIMARY_CANDIDATE else 50.0
    return round(
        classification_bonus
        + float(row.get("sample_count") or 0) / 10.0
        + float(betrayal.get("win_rate_pct") or 0.0)
        + max(0.0, float(betrayal.get("total_pnl_pct") or 0.0)),
        4,
    )


def _betrayal_required_steps() -> list[str]:
    return [
        "create betrayal paper signal identity",
        "track actual inverse entries/exits",
        "record stop/take-profit behavior",
        "collect minimum samples",
        "evaluate with Miro Fish/Markov equivalent",
        "only then consider risk contract",
    ]


def _dual_lane_comparison(*, normal_lane: Mapping[str, Any], betrayal_lane: Mapping[str, Any]) -> dict[str, Any]:
    betrayal_has_evidence = bool(betrayal_lane.get("top_betrayal_candidates"))
    if normal_lane.get("support_restored"):
        leading = "normal"
        why = "Normal lane has support restored for review only; R87/R89 still block live readiness."
    elif betrayal_has_evidence:
        leading = "betrayal_audit_opportunity"
        why = "Betrayal lane has audit evidence, but it needs true paper tracking before any review packet."
    else:
        leading = "normal_watch"
        why = "Normal lane remains the tracked candidate while betrayal has no current audit candidates."
    return {
        "normal_lane_status": normal_lane.get("normal_lane_status"),
        "betrayal_lane_status": betrayal_lane.get("betrayal_lane_status"),
        "normal_lane_score": normal_lane.get("current_miro_fish_score"),
        "betrayal_lane_audit_score": (betrayal_lane.get("top_betrayal_candidates") or [{}])[0].get("audit_score")
        if betrayal_has_evidence
        else None,
        "leading_lane": leading,
        "why": why,
        "no_live_reason": "No lane is live-ready; betrayal is audit-only and normal still must satisfy Miro Fish/Markov plus R84/R87/R89.",
    }


def _overall_lane_class(*, normal_lane: Mapping[str, Any], betrayal_lane: Mapping[str, Any]) -> str:
    if normal_lane.get("support_restored"):
        return NORMAL_LANE_LEADS
    if betrayal_lane.get("top_betrayal_candidates"):
        return BETRAYAL_LANE_NEEDS_TRUE_PAPER
    if normal_lane.get("candidate_present_currently"):
        return DUAL_LANE_WAITING
    return BOTH_LANES_BLOCKED


def _operator_architect_seat_review(
    *,
    normal_lane: Mapping[str, Any],
    betrayal_lane: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> dict[str, Any]:
    positions = [ARCHITECT_SEAT_RECOMMENDS_NO_LIVE_ACTION]
    if not normal_lane.get("support_restored"):
        positions.append(ARCHITECT_SEAT_RECOMMENDS_WAIT_FOR_MARKOV_SUPPORT)
    if betrayal_lane.get("top_betrayal_candidates"):
        positions.append(ARCHITECT_SEAT_RECOMMENDS_BETRAYAL_MATURATION_LANE)
    return {
        "seat_name": "Operator/Architect Seat",
        "council_position": "dual-lane watch is advisory; neither lane can bypass support, boundary, records, or execution gates",
        "operator_architect_position": list(dict.fromkeys(positions)),
        "normal_lane_opinion": "wait for Markov/Miro Fish support restoration",
        "betrayal_lane_opinion": "mature betrayal audit candidates through true paper tracking before promotion",
        "leading_lane_considered": comparison.get("leading_lane"),
        "override_power": False,
        "execution_permission": False,
        "can_override_miro_fish": False,
        "can_override_markov": False,
        "can_bypass_r84": False,
        "can_bypass_r87": False,
        "can_bypass_r89": False,
    }


def _r95_statuses(*, normal_lane: Mapping[str, Any], betrayal_lane: Mapping[str, Any]) -> list[str]:
    statuses = [DUAL_LANE_CANDIDATE_WATCH_ONLY, NORMAL_LANE_ACTIVE, BETRAYAL_LANE_ACTIVE]
    statuses.append(NORMAL_SUPPORT_RESTORED if normal_lane.get("support_restored") else NORMAL_SUPPORT_PENDING)
    if betrayal_lane.get("top_betrayal_candidates"):
        statuses.extend(
            [
                BETRAYAL_AUDIT_EVIDENCE_PRESENT,
                BETRAYAL_TRUE_PAPER_REQUIRED,
                BETRAYAL_CANDIDATE_MATURATION_REQUIRED,
            ]
        )
    statuses.extend([NO_LANE_LIVE_READY, DUAL_LANE_NON_EXECUTABLE_ONLY])
    return list(dict.fromkeys(statuses))


def _blockers(*, normal_lane: Mapping[str, Any], betrayal_lane: Mapping[str, Any]) -> list[str]:
    blockers = []
    if not normal_lane.get("support_restored"):
        blockers.append("normal_support_not_restored")
    if betrayal_lane.get("top_betrayal_candidates"):
        blockers.append("betrayal_true_paper_tracking_required")
    else:
        blockers.append("betrayal_audit_candidates_not_currently_present")
    blockers.extend(["r87_boundary_still_applies", "r89_review_records_still_apply", "r95_watch_only_not_live_permission"])
    return list(dict.fromkeys(blockers))


def _next_action_recommendation(*, betrayal_lane: Mapping[str, Any]) -> str:
    if betrayal_lane.get("top_betrayal_candidates"):
        return "R96 Betrayal True Paper Tracking Scaffold"
    return "R96 Markov Support Watch Scheduler / Candidate Revalidation Loop"


def _list_field(payload: Mapping[str, Any], key: str) -> list:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _betrayal_sort_key(row: Mapping[str, Any]) -> tuple[float, int]:
    return (-float(row.get("audit_score") or 0.0), -int(row.get("sample_count") or 0))


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
            "live_ready",
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
