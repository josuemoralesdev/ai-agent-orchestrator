"""R83 local Miro Fish quality gate for Hammer Radar candidates.

This is a deterministic local committee evaluator. It is not the external
MiroFish engine, does not call network services, and never creates live order
approval or execution side effects.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_candle_archive import build_betrayal_candle_archive_status
from src.app.hammer_radar.operator.betrayal_inverse_validation import build_betrayal_inverse_validation
from src.app.hammer_radar.operator.markov_regime_gate import (
    BETRAYAL,
    NORMAL,
    REGIME_REJECTS_CANDIDATE,
    REGIME_SUPPORTS_CANDIDATE,
    build_markov_regime_gate,
)
from src.app.hammer_radar.operator.strategy_performance import (
    ELIGIBLE_FOR_FUTURE_TINY_LIVE,
    INSUFFICIENT_DATA,
    PAPER_ONLY,
)

PHASE = "R83"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "MIRO_FISH_QUALITY_GATE_ONLY_NO_ORDER"

FISH_PASS = "FISH_PASS"
FISH_WARN = "FISH_WARN"
FISH_REJECT = "FISH_REJECT"
FISH_INSUFFICIENT_DATA = "FISH_INSUFFICIENT_DATA"
FISH_BLOCKED = "FISH_BLOCKED"

MIRO_FISH_SUPPORTS_CANDIDATE = "MIRO_FISH_SUPPORTS_CANDIDATE"
MIRO_FISH_OPERATOR_REVIEW_ONLY = "MIRO_FISH_OPERATOR_REVIEW_ONLY"
MIRO_FISH_NEEDS_MORE_EVIDENCE = "MIRO_FISH_NEEDS_MORE_EVIDENCE"
MIRO_FISH_REJECTS_CANDIDATE = "MIRO_FISH_REJECTS_CANDIDATE"
MIRO_FISH_BLOCKED = "MIRO_FISH_BLOCKED"

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_LIMIT = 120
SUPPORTED_FAMILIES = {NORMAL, BETRAYAL}
VOTE_SCORES = {
    FISH_PASS: 2,
    FISH_WARN: 1,
    FISH_INSUFFICIENT_DATA: 0,
    FISH_REJECT: -2,
    FISH_BLOCKED: -99,
}

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R83 is local read-only Miro Fish quality scoring. It does not approve or execute trades."


def build_miro_fish_quality_gate(
    *,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str | None = None,
    family: str | None = None,
    limit: int = DEFAULT_LIMIT,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC).isoformat()
    normalized_family = family.upper() if family else None
    markov = build_markov_regime_gate(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
        log_dir=resolved_log_dir,
    )
    inverse = build_betrayal_inverse_validation(log_dir=resolved_log_dir)
    candle_status = build_betrayal_candle_archive_status(symbol=symbol, timeframe=timeframe, log_dir=resolved_log_dir)
    source_candidates = [
        *_list_field(markov, "normal_candidate_regime_gates"),
        *_list_field(markov, "betrayal_candidate_regime_gates"),
    ]
    if normalized_family in SUPPORTED_FAMILIES:
        source_candidates = [
            row for row in source_candidates if str(row.get("candidate_family") or "").upper() == normalized_family
        ]
    if limit > 0:
        source_candidates = source_candidates[:limit]

    quality_rows = [
        evaluate_miro_fish_candidate(
            candidate,
            inverse_payload=inverse,
            candle_status=candle_status,
        )
        for candidate in source_candidates
    ]
    normal_rows = [row for row in quality_rows if row.get("candidate_family") == NORMAL]
    betrayal_rows = [row for row in quality_rows if row.get("candidate_family") == BETRAYAL]
    supported = [
        row for row in quality_rows if row.get("final_quality_status") == MIRO_FISH_SUPPORTS_CANDIDATE
    ]
    review = [
        row for row in quality_rows if row.get("final_quality_status") == MIRO_FISH_OPERATOR_REVIEW_ONLY
    ]
    blocked_or_rejected = [
        row
        for row in quality_rows
        if row.get("final_quality_status") in {MIRO_FISH_BLOCKED, MIRO_FISH_REJECTS_CANDIDATE}
    ]
    blockers = sorted(
        {
            str(blocker)
            for row in quality_rows
            for blocker in row.get("blockers", [])
            if blocker
        }
    )
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at,
            "archive_log_dir": str(resolved_log_dir),
            "config": {
                "symbol": symbol,
                "timeframe": timeframe,
                "family": normalized_family,
                "limit": int(limit),
                "scoring": VOTE_SCORES,
                "external_mirofish_engine": False,
            },
            "committee": _committee_summary(quality_rows),
            "normal_candidate_quality_gates": normal_rows,
            "betrayal_candidate_quality_gates": betrayal_rows,
            "top_supported_candidates": sorted(
                supported,
                key=lambda row: (-int(row.get("final_quality_score") or 0), str(row.get("candidate_id") or "")),
            )[:10],
            "operator_review_candidates": sorted(
                review,
                key=lambda row: (-int(row.get("final_quality_score") or 0), str(row.get("candidate_id") or "")),
            )[:10],
            "blocked_or_rejected_candidates": blocked_or_rejected[:20],
            "blockers": blockers,
            "notes": [
                NO_ORDER_NOTE,
                "This is a local committee-inspired evaluator, not the full external MiroFish simulator.",
                "Quality support is not live eligibility and does not bypass funding, protective order, or exact approval gates.",
                "Betrayal candidates remain blocked from strong support while true inverse validation is pending.",
            ],
            **_safety_fields(),
        }
    )


def evaluate_miro_fish_candidate(
    candidate: Mapping[str, Any],
    *,
    inverse_payload: Mapping[str, Any],
    candle_status: Mapping[str, Any],
) -> dict[str, Any]:
    votes = [
        _evidence_fish(candidate),
        _regime_fish(candidate),
        _risk_fish(candidate),
        _betrayal_fish(candidate),
        _data_integrity_fish(candidate, inverse_payload=inverse_payload, candle_status=candle_status),
        _operator_fish(candidate),
    ]
    final_status = _final_quality_status(candidate, votes)
    blockers = sorted(
        {
            str(blocker)
            for vote in votes
            for blocker in vote.get("blockers", [])
            if blocker
        }
    )
    score = _quality_score(votes)
    return _sanitize(
        {
            "candidate_id": candidate.get("candidate_id"),
            "candidate_family": candidate.get("candidate_family"),
            "audit_scope": candidate.get("audit_scope"),
            "symbol": candidate.get("symbol"),
            "timeframe": candidate.get("timeframe"),
            "direction": candidate.get("direction"),
            "betrayal_direction": candidate.get("betrayal_direction"),
            "entry_mode": candidate.get("entry_mode"),
            "source_recommendation": candidate.get("source_recommendation"),
            "markov_gate_status": candidate.get("gate_status"),
            "markov_regime": candidate.get("current_regime"),
            "true_inverse_validation_status": candidate.get("true_inverse_validation_status"),
            "fish_votes": votes,
            "final_quality_status": final_status,
            "final_quality_score": score,
            "blockers": blockers,
            "operator_note": _operator_note(final_status, candidate),
            **_safety_fields(),
        }
    )


def format_miro_fish_quality_gate_text(payload: Mapping[str, Any]) -> str:
    committee = payload.get("committee") if isinstance(payload.get("committee"), dict) else {}
    supported = _list_field(payload, "top_supported_candidates")
    review = _list_field(payload, "operator_review_candidates")
    blocked = _list_field(payload, "blocked_or_rejected_candidates")
    blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
    lines = [
        f"R83 Miro Fish Quality Gate: {payload.get('status')}",
        str(payload.get("execution_mode")),
        "No order placed. real_order_placed=false execution_attempted=false network_allowed=false secrets_shown=false.",
        "",
        "COMMITTEE SUMMARY",
        f"  candidates: {committee.get('candidate_count', 0)}",
        f"  supported: {committee.get('supported_count', 0)}",
        f"  review: {committee.get('operator_review_count', 0)}",
        f"  needs_more_evidence: {committee.get('needs_more_evidence_count', 0)}",
        f"  rejected_or_blocked: {committee.get('blocked_or_rejected_count', 0)}",
        "",
        "TOP SUPPORTED CANDIDATES",
    ]
    lines.extend(_format_quality_rows(supported))
    lines.extend(["", "OPERATOR REVIEW CANDIDATES"])
    lines.extend(_format_quality_rows(review))
    lines.extend(["", "BLOCKED / REJECTED CANDIDATES"])
    lines.extend(_format_quality_rows(blocked[:10]))
    lines.extend(["", f"blockers: {', '.join(str(item) for item in blockers) if blockers else 'none'}", NO_ORDER_NOTE])
    return "\n".join(lines)


def _evidence_fish(candidate: Mapping[str, Any]) -> dict[str, Any]:
    source = str(candidate.get("source_recommendation") or "")
    sample_count = int(candidate.get("source_sample_count") or 0)
    blockers = []
    if source == ELIGIBLE_FOR_FUTURE_TINY_LIVE and sample_count >= 30:
        status = FISH_PASS
        reason = "source recommendation and sample count support candidate evidence"
    elif source == INSUFFICIENT_DATA or sample_count < 30:
        status = FISH_INSUFFICIENT_DATA
        reason = "candidate needs more historical evidence"
        blockers.append("source_evidence_insufficient")
    elif source == PAPER_ONLY:
        status = FISH_WARN
        reason = "candidate is paper-only under source audit"
    elif "BETRAYAL" in source:
        status = FISH_WARN
        reason = "betrayal source evidence is audit-only until true inverse validation"
    else:
        status = FISH_WARN
        reason = "source recommendation is not strong support"
    return _fish_vote("Evidence Fish", status, reason, blockers)


def _regime_fish(candidate: Mapping[str, Any]) -> dict[str, Any]:
    gate_status = str(candidate.get("gate_status") or "")
    if gate_status == REGIME_SUPPORTS_CANDIDATE:
        return _fish_vote("Regime Fish", FISH_PASS, "R82 regime gate supports candidate context", [])
    if gate_status == REGIME_REJECTS_CANDIDATE:
        return _fish_vote("Regime Fish", FISH_REJECT, "R82 regime gate rejects candidate context", ["regime_rejects_candidate"])
    return _fish_vote("Regime Fish", FISH_WARN, "R82 regime gate is neutral or pending", ["regime_not_supportive"])


def _risk_fish(candidate: Mapping[str, Any]) -> dict[str, Any]:
    has_risk = all(candidate.get(key) not in (None, "") for key in ("entry_price", "stop_price", "take_profit_price"))
    if has_risk:
        return _fish_vote("Risk Fish", FISH_PASS, "candidate carries explicit entry/stop/take-profit risk fields", [])
    return _fish_vote("Risk Fish", FISH_WARN, "candidate has no explicit stop/take-profit risk fields in this surface", ["risk_fields_unavailable"])


def _betrayal_fish(candidate: Mapping[str, Any]) -> dict[str, Any]:
    if candidate.get("candidate_family") != BETRAYAL:
        return _fish_vote("Betrayal Fish", FISH_PASS, "normal candidate is outside betrayal validation path", [])
    blockers = []
    status = str(candidate.get("true_inverse_validation_status") or "")
    if "VALIDATED" not in status:
        blockers.append("true_inverse_validation_pending")
    if candidate.get("audit_scope") == "timeframe_aggregate":
        blockers.append("aggregate_betrayal_direction_context_only")
    if blockers:
        return _fish_vote("Betrayal Fish", FISH_BLOCKED, "betrayal candidate cannot receive strong approval yet", blockers)
    return _fish_vote("Betrayal Fish", FISH_WARN, "betrayal candidate has validation but remains review-only", [])


def _data_integrity_fish(
    candidate: Mapping[str, Any],
    *,
    inverse_payload: Mapping[str, Any],
    candle_status: Mapping[str, Any],
) -> dict[str, Any]:
    summary = inverse_payload.get("true_inverse_summary") if isinstance(inverse_payload.get("true_inverse_summary"), dict) else {}
    invalid = int(summary.get("invalid_resolution_records") or 0)
    if invalid > 0:
        return _fish_vote("Data Integrity Fish", FISH_BLOCKED, "invalid persisted resolution records are present", ["invalid_resolution_records_present"])
    timeframe = str(candidate.get("timeframe") or "")
    available = candle_status.get("available") if isinstance(candle_status.get("available"), list) else []
    matching = [row for row in available if row.get("timeframe") == timeframe]
    if matching and int(matching[0].get("candle_count") or 0) > 0:
        return _fish_vote("Data Integrity Fish", FISH_PASS, "local candle archive data is available and R81 invalid count is zero", [])
    return _fish_vote("Data Integrity Fish", FISH_INSUFFICIENT_DATA, "local candle archive data is missing for candidate timeframe", ["candle_archive_missing_for_timeframe"])


def _operator_fish(candidate: Mapping[str, Any]) -> dict[str, Any]:
    required = ("candidate_id", "candidate_family", "timeframe", "source_recommendation")
    missing = [key for key in required if candidate.get(key) in (None, "")]
    if missing:
        return _fish_vote("Operator Fish", FISH_INSUFFICIENT_DATA, "candidate lacks operator explanation fields", [f"missing_{key}" for key in missing])
    if candidate.get("candidate_family") == BETRAYAL:
        return _fish_vote("Operator Fish", FISH_WARN, "betrayal candidate is explainable but remains caution-only", [])
    return _fish_vote("Operator Fish", FISH_PASS, "candidate has clear source path and operator-readable identity", [])


def _final_quality_status(candidate: Mapping[str, Any], votes: list[dict[str, Any]]) -> str:
    statuses = {str(vote.get("vote_status") or "") for vote in votes}
    if FISH_BLOCKED in statuses:
        return MIRO_FISH_BLOCKED
    if FISH_REJECT in statuses:
        return MIRO_FISH_REJECTS_CANDIDATE
    if candidate.get("candidate_family") == BETRAYAL and str(candidate.get("true_inverse_validation_status") or "").find("VALIDATED") < 0:
        return MIRO_FISH_NEEDS_MORE_EVIDENCE
    if FISH_INSUFFICIENT_DATA in statuses:
        return MIRO_FISH_NEEDS_MORE_EVIDENCE
    pass_count = sum(1 for vote in votes if vote.get("vote_status") == FISH_PASS)
    warn_count = sum(1 for vote in votes if vote.get("vote_status") == FISH_WARN)
    if pass_count >= 4 and warn_count <= 1:
        return MIRO_FISH_SUPPORTS_CANDIDATE
    return MIRO_FISH_OPERATOR_REVIEW_ONLY


def _quality_score(votes: list[dict[str, Any]]) -> int:
    raw = sum(VOTE_SCORES.get(str(vote.get("vote_status") or ""), 0) for vote in votes)
    if any(vote.get("vote_status") == FISH_BLOCKED for vote in votes):
        return 0
    max_score = len(votes) * VOTE_SCORES[FISH_PASS]
    min_score = len(votes) * VOTE_SCORES[FISH_REJECT]
    return round(((raw - min_score) / (max_score - min_score)) * 100) if max_score != min_score else 0


def _fish_vote(name: str, status: str, reason: str, blockers: list[str]) -> dict[str, Any]:
    return {
        "fish": name,
        "vote_status": status,
        "score": VOTE_SCORES[status],
        "reason": reason,
        "blockers": blockers,
    }


def _committee_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_count": len(rows),
        "fish": [
            "Evidence Fish",
            "Regime Fish",
            "Risk Fish",
            "Betrayal Fish",
            "Data Integrity Fish",
            "Operator Fish",
        ],
        "vote_statuses": [FISH_PASS, FISH_WARN, FISH_REJECT, FISH_INSUFFICIENT_DATA, FISH_BLOCKED],
        "final_quality_statuses": [
            MIRO_FISH_SUPPORTS_CANDIDATE,
            MIRO_FISH_OPERATOR_REVIEW_ONLY,
            MIRO_FISH_NEEDS_MORE_EVIDENCE,
            MIRO_FISH_REJECTS_CANDIDATE,
            MIRO_FISH_BLOCKED,
        ],
        "supported_count": sum(1 for row in rows if row.get("final_quality_status") == MIRO_FISH_SUPPORTS_CANDIDATE),
        "operator_review_count": sum(1 for row in rows if row.get("final_quality_status") == MIRO_FISH_OPERATOR_REVIEW_ONLY),
        "needs_more_evidence_count": sum(1 for row in rows if row.get("final_quality_status") == MIRO_FISH_NEEDS_MORE_EVIDENCE),
        "blocked_or_rejected_count": sum(
            1 for row in rows if row.get("final_quality_status") in {MIRO_FISH_BLOCKED, MIRO_FISH_REJECTS_CANDIDATE}
        ),
    }


def _operator_note(status: str, candidate: Mapping[str, Any]) -> str:
    if status == MIRO_FISH_SUPPORTS_CANDIDATE:
        return "Local committee supports operator review; this is still not live approval."
    if status == MIRO_FISH_REJECTS_CANDIDATE:
        return "Local committee rejects this candidate under current evidence."
    if status == MIRO_FISH_BLOCKED:
        return "Candidate is blocked by a critical fish vote."
    if status == MIRO_FISH_NEEDS_MORE_EVIDENCE:
        return "Collect more paper, regime, or true inverse evidence before promotion."
    if candidate.get("candidate_family") == BETRAYAL:
        return "Betrayal candidate remains review-only until true inverse proof improves."
    return "Candidate is mixed and should remain operator-review only."


def _format_quality_rows(rows: list[Mapping[str, Any]]) -> list[str]:
    if not rows:
        return ["  none"]
    formatted = []
    for row in rows:
        formatted.append(
            "  "
            f"{row.get('final_quality_status')} score={row.get('final_quality_score')} "
            f"{row.get('candidate_family')} {row.get('timeframe')} "
            f"{row.get('direction') or row.get('betrayal_direction') or 'aggregate'} "
            f"source={row.get('source_recommendation')} regime={row.get('markov_regime')}"
        )
    return formatted


def _list_field(payload: Mapping[str, Any], key: str) -> list:
    value = payload.get(key)
    return value if isinstance(value, list) else []


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
        ):
            if key in sanitized:
                sanitized[key] = False
        if "global_kill_switch" in sanitized:
            sanitized["global_kill_switch"] = True
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
