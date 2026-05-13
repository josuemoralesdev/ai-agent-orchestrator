"""R81 true inverse paper outcome validation for betrayal candidates.

This module reads R80/R80.2 betrayal audit candidates and existing betrayal
shadow outcome records. It is reporting only: no orders, no network, no live
execution arming, and no signed payloads.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_shadow_outcomes import (
    RESOLVED_STATUSES,
    SHADOW_BREAKEVEN,
    SHADOW_LOSS,
    SHADOW_NO_DATA,
    SHADOW_OPEN,
    SHADOW_UNRESOLVED,
    SHADOW_WIN,
)
from src.app.hammer_radar.operator.betrayal_shadow_resolver import (
    load_betrayal_shadow_resolution_quality_summary,
    load_resolved_betrayal_shadow_records,
)
from src.app.hammer_radar.operator.betrayal_strategy_audit import (
    BETRAYAL_PRIMARY_CANDIDATE,
    BETRAYAL_WATCHLIST,
    build_betrayal_strategy_audit,
)

PHASE = "R81"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "TRUE_INVERSE_PAPER_OUTCOME_VALIDATION_ONLY_NO_ORDER"

TRUE_INVERSE_VALIDATED_PRIMARY = "TRUE_INVERSE_VALIDATED_PRIMARY"
TRUE_INVERSE_VALIDATED_WATCHLIST = "TRUE_INVERSE_VALIDATED_WATCHLIST"
TRUE_INVERSE_VALIDATION_PENDING = "TRUE_INVERSE_VALIDATION_PENDING"
INSUFFICIENT_TRUE_INVERSE_OUTCOMES = "INSUFFICIENT_TRUE_INVERSE_OUTCOMES"
TRUE_INVERSE_REJECTED = "TRUE_INVERSE_REJECTED"
TRUE_INVERSE_NO_DATA = "TRUE_INVERSE_NO_DATA"

DEFAULT_MIN_TRUE_INVERSE_SAMPLE = 30
DEFAULT_MIN_TRUE_INVERSE_WIN_RATE = 55.0
MAX_UNRESOLVED_RATIO = 0.5

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = (
    "R81 is paper/shadow/outcome validation only. True inverse validation does not make any "
    "betrayal strategy live-ready."
)


def build_betrayal_inverse_validation(
    *,
    log_dir: str | Path | None = None,
    min_true_inverse_sample: int = DEFAULT_MIN_TRUE_INVERSE_SAMPLE,
    min_true_inverse_win_rate: float = DEFAULT_MIN_TRUE_INVERSE_WIN_RATE,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC).isoformat()
    audit = build_betrayal_strategy_audit(log_dir=resolved_log_dir)
    records = load_resolved_betrayal_shadow_records(log_dir=resolved_log_dir)
    resolution_quality = load_betrayal_shadow_resolution_quality_summary(log_dir=resolved_log_dir)

    aggregate_candidates = [
        *_list_field(audit, "timeframe_aggregate_primary_candidates"),
        *_list_field(audit, "timeframe_aggregate_watchlist_candidates"),
    ]
    direction_candidates = [
        *_list_field(audit, "direction_entry_mode_primary_candidates"),
        *_list_field(audit, "direction_entry_mode_watchlist_candidates"),
    ]

    timeframe_aggregate_validations = [
        build_true_inverse_validation_row(
            candidate,
            records=records,
            min_true_inverse_sample=min_true_inverse_sample,
            min_true_inverse_win_rate=min_true_inverse_win_rate,
        )
        for candidate in aggregate_candidates
    ]
    direction_entry_mode_validations = [
        build_true_inverse_validation_row(
            candidate,
            records=records,
            min_true_inverse_sample=min_true_inverse_sample,
            min_true_inverse_win_rate=min_true_inverse_win_rate,
        )
        for candidate in direction_candidates
    ]
    validations = [*timeframe_aggregate_validations, *direction_entry_mode_validations]
    validations.sort(key=_sort_key)
    primary_validations = [
        row for row in validations if row["source_recommendation"] == BETRAYAL_PRIMARY_CANDIDATE
    ]
    watchlist_validations = [
        row for row in validations if row["source_recommendation"] == BETRAYAL_WATCHLIST
    ]
    unresolved_validations = [
        row
        for row in validations
        if row["validation_status"]
        in {TRUE_INVERSE_NO_DATA, TRUE_INVERSE_VALIDATION_PENDING, INSUFFICIENT_TRUE_INVERSE_OUTCOMES}
    ]
    rejected_validations = [
        row for row in validations if row["validation_status"] == TRUE_INVERSE_REJECTED
    ]

    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at,
            "archive_log_dir": str(resolved_log_dir),
            "config": {
                "min_true_inverse_sample": int(min_true_inverse_sample),
                "min_true_inverse_win_rate_pct": float(min_true_inverse_win_rate),
                "min_true_inverse_avg_pnl_pct_gt": 0.0,
                "min_true_inverse_total_pnl_pct_gt": 0.0,
                "max_unresolved_no_data_ratio": MAX_UNRESOLVED_RATIO,
            },
            "source_audit_summary": {
                "phase": audit.get("phase"),
                "execution_mode": audit.get("execution_mode"),
                "timeframe_aggregate_primary_candidates": len(
                    _list_field(audit, "timeframe_aggregate_primary_candidates")
                ),
                "timeframe_aggregate_watchlist_candidates": len(
                    _list_field(audit, "timeframe_aggregate_watchlist_candidates")
                ),
                "direction_entry_mode_primary_candidates": len(
                    _list_field(audit, "direction_entry_mode_primary_candidates")
                ),
                "direction_entry_mode_watchlist_candidates": len(
                    _list_field(audit, "direction_entry_mode_watchlist_candidates")
                ),
            },
            "true_inverse_summary": _true_inverse_summary(
                records=records,
                validations=validations,
                resolution_quality=resolution_quality,
            ),
            "timeframe_aggregate_validations": timeframe_aggregate_validations,
            "direction_entry_mode_validations": direction_entry_mode_validations,
            "primary_validations": primary_validations,
            "watchlist_validations": watchlist_validations,
            "unresolved_validations": unresolved_validations,
            "rejected_validations": rejected_validations,
            "notes": [
                NO_ORDER_NOTE,
                "R81 reads betrayal shadow outcome records and never places orders.",
                "Naive inverse audit evidence remains separate from true inverse paper outcomes.",
                "Validated R81 status is still not live eligibility.",
                "Run betrayal-shadow-track separately to collect more shadow outcome records.",
            ],
            **_safety_fields(),
        }
    )


def build_true_inverse_validation_row(
    candidate: Mapping[str, Any],
    *,
    records: list[dict],
    min_true_inverse_sample: int = DEFAULT_MIN_TRUE_INVERSE_SAMPLE,
    min_true_inverse_win_rate: float = DEFAULT_MIN_TRUE_INVERSE_WIN_RATE,
) -> dict[str, Any]:
    matching_records = _matching_records(candidate, records)
    stats = _stats(matching_records)
    blockers = _blockers(
        stats,
        min_true_inverse_sample=min_true_inverse_sample,
        min_true_inverse_win_rate=min_true_inverse_win_rate,
    )
    validation_status = _validation_status(
        candidate,
        stats,
        blockers=blockers,
        min_true_inverse_sample=min_true_inverse_sample,
    )
    return _sanitize(
        {
            "audit_scope": candidate.get("audit_scope"),
            "timeframe": candidate.get("timeframe"),
            "original_direction": candidate.get("original_direction"),
            "betrayal_direction": candidate.get("betrayal_direction"),
            "entry_mode": candidate.get("entry_mode"),
            "source_recommendation": candidate.get("recommendation"),
            "naive_betrayal": candidate.get("betrayal") if isinstance(candidate.get("betrayal"), dict) else {},
            "true_inverse_sample_count": stats["sample_count"],
            "true_inverse_wins": stats["wins"],
            "true_inverse_losses": stats["losses"],
            "true_inverse_win_rate_pct": stats["win_rate_pct"],
            "true_inverse_avg_pnl_pct": stats["avg_pnl_pct"],
            "true_inverse_total_pnl_pct": stats["total_pnl_pct"],
            "unresolved_no_data_count": stats["unresolved_no_data_count"],
            "validation_status": validation_status,
            "blockers": blockers,
            "operator_note": _operator_note(validation_status),
            **_safety_fields(),
        }
    )


def format_betrayal_inverse_validation_text(payload: Mapping[str, Any]) -> str:
    aggregate = _list_field(payload, "timeframe_aggregate_validations")
    direction = _list_field(payload, "direction_entry_mode_validations")
    summary = payload.get("true_inverse_summary") if isinstance(payload.get("true_inverse_summary"), dict) else {}
    lines = [
        f"R81 true inverse validation: {payload.get('status')}",
        str(payload.get("execution_mode")),
        "No order placed. real_order_placed=false execution_attempted=false network_allowed=false secrets_shown=false.",
        f"total_shadow_records: {summary.get('total_shadow_records', 0)}",
        f"resolved_shadow_records: {summary.get('resolved_shadow_records', 0)}",
        f"invalid_resolution_records: {summary.get('invalid_resolution_records', 0)}",
        "",
        "TIMEFRAME AGGREGATE TRUE INVERSE VALIDATION",
    ]
    lines.extend(_format_rows(aggregate))
    lines.extend(["", "DIRECTION / ENTRY-MODE TRUE INVERSE VALIDATION"])
    lines.extend(_format_rows(direction[:10]))
    lines.append(NO_ORDER_NOTE)
    return "\n".join(lines)


def _matching_records(candidate: Mapping[str, Any], records: list[dict]) -> list[dict]:
    audit_scope = str(candidate.get("audit_scope") or "")
    timeframe = candidate.get("timeframe")
    original_direction = candidate.get("original_direction")
    betrayal_direction = candidate.get("betrayal_direction")
    matched = [record for record in records if record.get("timeframe") == timeframe]
    if audit_scope == "direction_entry_mode":
        matched = [
            record
            for record in matched
            if record.get("original_direction") == original_direction
            and record.get("shadow_direction") == betrayal_direction
        ]
    return matched


def _stats(records: list[dict]) -> dict[str, Any]:
    wins = [record for record in records if record.get("shadow_status") == SHADOW_WIN]
    losses = [record for record in records if record.get("shadow_status") == SHADOW_LOSS]
    breakeven = [record for record in records if record.get("shadow_status") == SHADOW_BREAKEVEN]
    unresolved = [
        record
        for record in records
        if record.get("shadow_status") in {SHADOW_OPEN, SHADOW_NO_DATA, SHADOW_UNRESOLVED}
    ]
    resolved = [record for record in records if record.get("shadow_status") in RESOLVED_STATUSES]
    pnl_values = [
        float(record["shadow_pnl_pct"])
        for record in resolved
        if record.get("shadow_pnl_pct") is not None
    ]
    sample_count = len(resolved)
    total_pnl = round(sum(pnl_values), 4) if pnl_values else 0.0
    return {
        "sample_count": sample_count,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "unresolved_no_data_count": len(unresolved),
        "total_records": len(records),
        "win_rate_pct": round((len(wins) / sample_count) * 100.0, 2) if sample_count else None,
        "avg_pnl_pct": round(total_pnl / len(pnl_values), 4) if pnl_values else None,
        "total_pnl_pct": total_pnl if pnl_values else None,
    }


def _blockers(
    stats: Mapping[str, Any],
    *,
    min_true_inverse_sample: int,
    min_true_inverse_win_rate: float,
) -> list[str]:
    blockers: list[str] = []
    sample_count = int(stats.get("sample_count") or 0)
    total_records = int(stats.get("total_records") or 0)
    unresolved = int(stats.get("unresolved_no_data_count") or 0)
    win_rate = stats.get("win_rate_pct")
    avg_pnl = stats.get("avg_pnl_pct")
    total_pnl = stats.get("total_pnl_pct")
    if total_records == 0:
        blockers.append("no true inverse shadow outcome records")
    if sample_count < min_true_inverse_sample:
        blockers.append(f"true_inverse_sample_count below minimum {min_true_inverse_sample}")
    if win_rate is None or float(win_rate) < min_true_inverse_win_rate:
        blockers.append(f"true_inverse_win_rate_pct below minimum {min_true_inverse_win_rate}")
    if avg_pnl is None or float(avg_pnl) <= 0.0:
        blockers.append("true_inverse_avg_pnl_pct is not positive")
    if total_pnl is None or float(total_pnl) <= 0.0:
        blockers.append("true_inverse_total_pnl_pct is not positive")
    if total_records > 0 and unresolved / total_records > MAX_UNRESOLVED_RATIO:
        blockers.append("unresolved_no_data_count dominates true inverse records")
    return blockers


def _validation_status(
    candidate: Mapping[str, Any],
    stats: Mapping[str, Any],
    *,
    blockers: list[str],
    min_true_inverse_sample: int,
) -> str:
    sample_count = int(stats.get("sample_count") or 0)
    total_records = int(stats.get("total_records") or 0)
    source = candidate.get("recommendation")
    if total_records == 0:
        return TRUE_INVERSE_NO_DATA
    if sample_count == 0:
        return TRUE_INVERSE_VALIDATION_PENDING
    if sample_count < min_true_inverse_sample:
        return INSUFFICIENT_TRUE_INVERSE_OUTCOMES
    if not blockers:
        if source == BETRAYAL_PRIMARY_CANDIDATE:
            return TRUE_INVERSE_VALIDATED_PRIMARY
        if source == BETRAYAL_WATCHLIST:
            return TRUE_INVERSE_VALIDATED_WATCHLIST
    return TRUE_INVERSE_REJECTED


def _true_inverse_summary(
    *,
    records: list[dict],
    validations: list[dict],
    resolution_quality: Mapping[str, Any],
) -> dict[str, Any]:
    resolved = [record for record in records if record.get("shadow_status") in RESOLVED_STATUSES]
    return {
        "total_shadow_records": len(records),
        "resolved_shadow_records": len(resolved),
        "persisted_resolution_records": int(resolution_quality.get("persisted_resolution_records") or 0),
        "temporally_valid_resolved_records": int(
            resolution_quality.get("temporally_valid_resolved_records") or 0
        ),
        "temporally_invalid_resolved_records": int(
            resolution_quality.get("temporally_invalid_resolved_records") or 0
        ),
        "invalid_resolution_records": int(resolution_quality.get("invalid_resolution_records") or 0),
        "validation_targets": len(validations),
        "validated_primary": sum(
            1 for row in validations if row.get("validation_status") == TRUE_INVERSE_VALIDATED_PRIMARY
        ),
        "validated_watchlist": sum(
            1 for row in validations if row.get("validation_status") == TRUE_INVERSE_VALIDATED_WATCHLIST
        ),
        "pending_or_insufficient": sum(
            1
            for row in validations
            if row.get("validation_status")
            in {TRUE_INVERSE_NO_DATA, TRUE_INVERSE_VALIDATION_PENDING, INSUFFICIENT_TRUE_INVERSE_OUTCOMES}
        ),
        "rejected": sum(1 for row in validations if row.get("validation_status") == TRUE_INVERSE_REJECTED),
    }


def _format_rows(rows: list[Mapping[str, Any]]) -> list[str]:
    if not rows:
        return ["  none"]
    formatted = []
    for row in rows:
        formatted.append(
            "  "
            f"{row.get('validation_status')} { _format_group_identity(row) } "
            f"samples={row.get('true_inverse_sample_count')} "
            f"wins={row.get('true_inverse_wins')} losses={row.get('true_inverse_losses')} "
            f"win_rate={_format_optional(row.get('true_inverse_win_rate_pct'))} "
            f"total_pnl={_format_optional(row.get('true_inverse_total_pnl_pct'))} "
            f"unresolved={row.get('unresolved_no_data_count')}"
        )
    return formatted


def _format_group_identity(row: Mapping[str, Any]) -> str:
    timeframe = row.get("timeframe")
    original_direction = row.get("original_direction")
    betrayal_direction = row.get("betrayal_direction")
    entry_mode = row.get("entry_mode")
    if original_direction or betrayal_direction or entry_mode:
        return f"{timeframe} {original_direction}->{betrayal_direction} {entry_mode}"
    return f"{timeframe} aggregate"


def _operator_note(status: str) -> str:
    if status in {TRUE_INVERSE_VALIDATED_PRIMARY, TRUE_INVERSE_VALIDATED_WATCHLIST}:
        return "True inverse paper outcomes pass R81 thresholds; this is still not live eligibility."
    if status == TRUE_INVERSE_NO_DATA:
        return "No true inverse shadow outcome records yet; run betrayal-shadow-track and keep paper validation active."
    if status == INSUFFICIENT_TRUE_INVERSE_OUTCOMES:
        return "True inverse records exist but sample size is below R81 validation threshold."
    if status == TRUE_INVERSE_VALIDATION_PENDING:
        return "True inverse records exist but remain unresolved or no-data."
    return "True inverse records do not pass R81 thresholds; keep betrayal candidate out of live eligibility."


def _sort_key(row: Mapping[str, Any]) -> tuple[int, int, str, str, str]:
    rank = {
        BETRAYAL_PRIMARY_CANDIDATE: 0,
        BETRAYAL_WATCHLIST: 1,
    }.get(str(row.get("source_recommendation")), 9)
    return (
        rank,
        -int(row.get("true_inverse_sample_count") or 0),
        str(row.get("timeframe") or ""),
        str(row.get("original_direction") or ""),
        str(row.get("entry_mode") or ""),
    )


def _list_field(payload: Mapping[str, Any], key: str) -> list:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _format_optional(value: object) -> str:
    if value is None:
        return "n/a"
    return str(value)


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
