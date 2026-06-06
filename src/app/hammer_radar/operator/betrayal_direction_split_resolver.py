"""R215 betrayal direction split resolver.

Paper-only audit surface for betrayal aggregate candidates. It attempts to
resolve original/inverse direction only from explicit local schema and keeps
aggregate or lane-only evidence unresolved.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE

BETRAYAL_DIRECTION_SPLIT_RESOLVER_READY = "BETRAYAL_DIRECTION_SPLIT_RESOLVER_READY"
BETRAYAL_DIRECTION_SPLIT_RESOLVER_REJECTED = "BETRAYAL_DIRECTION_SPLIT_RESOLVER_REJECTED"
BETRAYAL_DIRECTION_SPLIT_RESOLVER_RECORDED = "BETRAYAL_DIRECTION_SPLIT_RESOLVER_RECORDED"
BETRAYAL_DIRECTION_SPLIT_RESOLVER_BLOCKED = "BETRAYAL_DIRECTION_SPLIT_RESOLVER_BLOCKED"
BETRAYAL_DIRECTION_SPLIT_RESOLVER_ERROR = "BETRAYAL_DIRECTION_SPLIT_RESOLVER_ERROR"

DIRECTION_SPLIT_RESOLVED_FOR_PAPER_REVIEW = "DIRECTION_SPLIT_RESOLVED_FOR_PAPER_REVIEW"
DIRECTION_SPLIT_PARTIAL = "DIRECTION_SPLIT_PARTIAL"
DIRECTION_SPLIT_STILL_REQUIRED = "DIRECTION_SPLIT_STILL_REQUIRED"
AGGREGATE_CONTEXT_ONLY = "AGGREGATE_CONTEXT_ONLY"
DIRECTION_SCHEMA_MISSING = "DIRECTION_SCHEMA_MISSING"
DIRECTION_SPLIT_NOT_LIVE_AUTHORIZED = "DIRECTION_SPLIT_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_DIRECTION_SPLIT_RESOLVER"
LEDGER_FILENAME = "betrayal_direction_split_resolver.ndjson"
CONFIRM_BETRAYAL_DIRECTION_SPLIT_RESOLVER_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL DIRECTION SPLIT RESOLVER RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

TARGET_TIMEFRAMES = ("222m", "88m", "55m")
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_ENTRY_MODE = "ladder_close_50_618"

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
    "ledger_rewritten": False,
    "destructive_write": False,
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
    "betrayal_live_authorized": False,
    "betrayal_promoted": False,
    "position_permission_created": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/betrayal_regime_miro_recheck.ndjson",
    "logs/hammer_radar_forward/betrayal_event_tracker.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_matrix_context.ndjson",
    "logs/hammer_radar_forward/betrayal_true_inverse_refresh.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_signals.ndjson",
    "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_expansion.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_heartbeats.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_direction_split_resolver(
    *,
    log_dir: str | Path | None = None,
    record_resolver: bool = False,
    confirm_betrayal_direction_split_resolver: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_direction_split_resolver
        == CONFIRM_BETRAYAL_DIRECTION_SPLIT_RESOLVER_RECORDING_PHRASE
    )
    try:
        regime_miro = load_latest_betrayal_regime_miro_recheck(log_dir=resolved_log_dir)
        event_tracker = load_latest_betrayal_event_tracker(log_dir=resolved_log_dir)
        matrix_context = load_latest_betrayal_paper_matrix_context(log_dir=resolved_log_dir)
        true_inverse = load_latest_betrayal_true_inverse_refresh(log_dir=resolved_log_dir)
        paper_signals = load_betrayal_paper_signals(log_dir=resolved_log_dir)
        true_outcomes = load_betrayal_true_paper_outcomes(log_dir=resolved_log_dir)
        shadow_outcomes = load_betrayal_shadow_outcomes(log_dir=resolved_log_dir)
        capture_seeds = load_full_spectrum_capture_seeds(log_dir=resolved_log_dir)
        rows = build_direction_split_resolution_rows(
            regime_miro_recheck=regime_miro,
            event_tracker=event_tracker,
            paper_matrix_context=matrix_context,
            true_inverse_refresh=true_inverse,
            betrayal_paper_signals=paper_signals,
            true_paper_outcomes=true_outcomes,
            shadow_outcomes=shadow_outcomes,
            full_spectrum_capture_seeds=capture_seeds,
        )
        gap_report = build_direction_split_gap_report(rows)
        recommendations = build_direction_split_recommendations(gap_report=gap_report, rows=rows)
        split_status = classify_betrayal_direction_split_status(rows=rows, gap_report=gap_report)
        payload = {
            "status": _top_level_status(
                record_resolver=record_resolver,
                confirmation_valid=confirmation_valid,
                rows=rows,
            ),
            "generated_at": generated_at.isoformat(),
            "resolver_recorded": False,
            "resolver_id": None,
            "record_resolver_requested": bool(record_resolver),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "betrayal_candidates": ["222m aggregate", "88m aggregate", "55m aggregate_if_available"],
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "regime_miro_recheck_found": bool(regime_miro),
                "event_tracker_found": bool(event_tracker),
                "paper_matrix_context_found": bool(matrix_context),
                "true_inverse_refresh_found": bool(true_inverse),
                "betrayal_paper_signals_found": bool(paper_signals),
                "betrayal_paper_signal_count": len(paper_signals),
                "true_paper_outcomes_found": bool(true_outcomes),
                "true_paper_outcome_count": len(true_outcomes),
                "shadow_outcomes_found": bool(shadow_outcomes),
                "shadow_outcome_count": len(shadow_outcomes),
                "full_spectrum_capture_seed_count": len(capture_seeds),
            },
            "direction_split_resolution_rows": rows,
            "direction_split_summary": _direction_split_summary(rows),
            "direction_split_gap_report": gap_report,
            "direction_split_recommendations": recommendations,
            "direction_split_status": split_status,
            "recommended_next_operator_move": _recommended_next_operator_move(split_status),
            "recommended_next_engineering_move": _recommended_next_engineering_move(split_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_resolver and confirmation_valid and rows:
            record = append_betrayal_direction_split_resolver_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_DIRECTION_SPLIT_RESOLVER_RECORDED
            payload["resolver_recorded"] = True
            payload["resolver_id"] = record["resolver_id"]
            payload["ledger_path"] = str(betrayal_direction_split_resolver_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_DIRECTION_SPLIT_RESOLVER_ERROR,
                "generated_at": generated_at.isoformat(),
                "resolver_recorded": False,
                "resolver_id": None,
                "record_resolver_requested": bool(record_resolver),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {
                    "betrayal_candidates": ["222m aggregate", "88m aggregate", "55m aggregate_if_available"],
                    "paper_only": True,
                    "live_authorized": False,
                },
                "input_summary": {},
                "direction_split_resolution_rows": [],
                "direction_split_summary": _direction_split_summary([]),
                "direction_split_gap_report": build_direction_split_gap_report([]),
                "direction_split_recommendations": [],
                "direction_split_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_WEEKEND_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R215 resolver composer error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_betrayal_regime_miro_recheck(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_regime_miro_recheck.ndjson")


def load_latest_betrayal_event_tracker(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_event_tracker.ndjson")


def load_latest_betrayal_paper_matrix_context(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_paper_matrix_context.ndjson")


def load_latest_betrayal_true_inverse_refresh(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_true_inverse_refresh.ndjson")


def load_betrayal_paper_signals(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_paper_signals.ndjson")


def load_betrayal_true_paper_outcomes(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_true_paper_outcomes.ndjson")


def load_betrayal_shadow_outcomes(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_shadow_outcomes.ndjson")


def load_full_spectrum_capture_seeds(*, log_dir: str | Path | None = None, limit: int = 200) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    captures: list[dict[str, Any]] = []
    for filename in ("full_spectrum_harvester_heartbeats.ndjson", "full_spectrum_harvester_expansion.ndjson"):
        for record in _read_recent(resolved_log_dir / filename, limit=limit):
            captures.extend(_extract_capture_rows(record, source="full_spectrum_capture"))
    return _dedupe_rows(captures)


def extract_direction_from_lane_key(lane_key: str | None) -> str | None:
    parts = str(lane_key or "").split("|")
    if len(parts) >= 3:
        return _normal_direction(parts[2])
    return None


def infer_inverse_direction(original_direction: str | None) -> str | None:
    direction = _normal_direction(original_direction)
    if direction == "long":
        return "short"
    if direction == "short":
        return "long"
    return None


def resolve_direction_split_candidate(
    record: Mapping[str, Any],
    *,
    candidate: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    lane_key = _lane_key(record)
    lane_direction = extract_direction_from_lane_key(lane_key)
    source_direction = _normal_direction(
        record.get("source_direction")
        or record.get("direction")
        or record.get("betrayal_direction")
        or record.get("shadow_direction")
        or record.get("inverse_direction")
    )
    original_direction = _normal_direction(record.get("original_direction") or record.get("source_original_direction"))
    inverse_direction = _normal_direction(
        record.get("inverse_direction") or record.get("betrayal_direction") or record.get("shadow_direction")
    )
    if original_direction and not inverse_direction:
        inverse_direction = infer_inverse_direction(original_direction)
    entry_mode = record.get("entry_mode") or record.get("source_entry_mode")
    signal_timestamp = _signal_timestamp(record)
    source_signal_id = _source_identity(record)
    context = _direction_context(
        record=record,
        lane_direction=lane_direction,
        original_direction=original_direction,
        inverse_direction=inverse_direction,
        entry_mode=entry_mode,
        signal_timestamp=signal_timestamp,
        source_signal_id=source_signal_id,
    )
    resolved = (
        context == "direction_specific"
        and bool(original_direction)
        and bool(inverse_direction)
        and inverse_direction == infer_inverse_direction(original_direction)
        and bool(entry_mode)
        and bool(signal_timestamp)
        and bool(source_signal_id)
    )
    return _sanitize(
        {
            "candidate": candidate or _candidate_label(record),
            "source": source or str(record.get("source") or "unknown"),
            "lane_key": lane_key,
            "source_signal_id": source_signal_id,
            "signal_timestamp": signal_timestamp,
            "source_direction": source_direction or lane_direction,
            "original_direction": original_direction,
            "inverse_direction": inverse_direction,
            "entry_mode": entry_mode,
            "direction_context": context,
            "direction_split_resolved": bool(resolved),
            "can_enter_event_outcome_resolver": bool(resolved),
            "can_count_as_validated_sample_now": False,
            "paper_only": True,
            "live_authorized": False,
            "why": _row_why(
                context=context,
                lane_direction=lane_direction,
                original_direction=original_direction,
                inverse_direction=inverse_direction,
                entry_mode=entry_mode,
                signal_timestamp=signal_timestamp,
                source_signal_id=source_signal_id,
            ),
        }
    )


def build_direction_split_resolution_rows(
    *,
    regime_miro_recheck: Mapping[str, Any],
    event_tracker: Mapping[str, Any],
    paper_matrix_context: Mapping[str, Any],
    true_inverse_refresh: Mapping[str, Any],
    betrayal_paper_signals: Sequence[Mapping[str, Any]],
    true_paper_outcomes: Sequence[Mapping[str, Any]],
    shadow_outcomes: Sequence[Mapping[str, Any]],
    full_spectrum_capture_seeds: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    del regime_miro_recheck, paper_matrix_context, true_inverse_refresh
    rows: list[dict[str, Any]] = []
    for row in _event_tracker_rows(event_tracker):
        rows.append(resolve_direction_split_candidate(row, candidate=_candidate_label(row), source="event_tracker"))
    for source, records in (
        ("betrayal_paper_signal", betrayal_paper_signals),
        ("true_paper_outcome", true_paper_outcomes),
        ("shadow_outcome", shadow_outcomes),
        ("full_spectrum_capture", full_spectrum_capture_seeds),
    ):
        for record in records:
            candidate = _candidate_label(record)
            if _candidate_timeframe(candidate) not in TARGET_TIMEFRAMES:
                continue
            rows.append(resolve_direction_split_candidate(record, candidate=candidate, source=source))
    return _dedupe_resolution_rows(rows)


def build_direction_split_gap_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "original_direction_missing": sum(1 for row in rows if not row.get("original_direction")),
        "inverse_direction_missing": sum(1 for row in rows if not row.get("inverse_direction")),
        "entry_mode_missing": sum(1 for row in rows if not row.get("entry_mode")),
        "signal_timestamp_missing": sum(1 for row in rows if not row.get("signal_timestamp")),
        "source_identity_missing": sum(1 for row in rows if not row.get("source_signal_id")),
        "aggregate_context_only_count": sum(1 for row in rows if row.get("direction_context") == "aggregate_context_only"),
        "partial_direction_split_count": sum(1 for row in rows if row.get("direction_context") == "partial"),
        "schema_missing_count": sum(1 for row in rows if row.get("direction_context") in {"unknown", "schema_missing"}),
        "hard_live_blockers": [
            "betrayal_not_live_authorized",
            "betrayal_not_promoted",
            "direction_split_audit_is_paper_only",
            "config_writes_forbidden",
            "orders_forbidden",
            "binance_calls_forbidden",
        ],
    }


def build_direction_split_recommendations(
    *,
    gap_report: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    resolved = [row for row in rows if row.get("direction_split_resolved")]
    recommendations = []
    if resolved:
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RUN_EVENT_OUTCOME_RESOLVER",
                "future_phase": "R214",
                "why": "At least one local row has explicit original/inverse direction schema for paper-only outcome resolving.",
            }
        )
    if gap_report.get("aggregate_context_only_count") or gap_report.get("partial_direction_split_count"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "WIRE_BETRAYAL_SOURCE_EMITTER",
                "future_phase": "R216",
                "why": "Future betrayal rows need explicit original and inverse direction fields; lane direction alone is not proof.",
            }
        )
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "COLLECT_DIRECTION_SPECIFIC_SIGNALS",
                "future_phase": "R216",
                "why": "Aggregate context must remain blocked until direction-entry-mode schema is local and explicit.",
            }
        )
    recommendations.append(
        {
            "priority": "LOW",
            "recommended_action": "KEEP_CONTEXT_ONLY",
            "future_phase": "R215",
            "why": "R215 cannot promote betrayal, authorize live, or count raw captures as validated samples.",
        }
    )
    return recommendations


def classify_betrayal_direction_split_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
) -> str:
    if not rows:
        return DIRECTION_SCHEMA_MISSING
    resolved_count = sum(1 for row in rows if row.get("direction_split_resolved"))
    if resolved_count and resolved_count == len(rows):
        return DIRECTION_SPLIT_RESOLVED_FOR_PAPER_REVIEW
    if resolved_count or gap_report.get("partial_direction_split_count"):
        return DIRECTION_SPLIT_PARTIAL
    if gap_report.get("aggregate_context_only_count"):
        return AGGREGATE_CONTEXT_ONLY
    if gap_report.get("schema_missing_count"):
        return DIRECTION_SCHEMA_MISSING
    return DIRECTION_SPLIT_STILL_REQUIRED


def append_betrayal_direction_split_resolver_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_direction_split_resolver_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "resolver_id": str(record.get("resolver_id") or f"r215_betrayal_direction_split_resolver_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_DIRECTION_SPLIT_RESOLVER_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_resolver_requested": bool(record.get("record_resolver_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "direction_split_resolution_rows": list(record.get("direction_split_resolution_rows") or []),
            "direction_split_summary": dict(record.get("direction_split_summary") or {}),
            "direction_split_gap_report": dict(record.get("direction_split_gap_report") or {}),
            "direction_split_recommendations": list(record.get("direction_split_recommendations") or []),
            "direction_split_status": record.get("direction_split_status"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_betrayal_direction_split_resolver_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_direction_split_resolver_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_betrayal_direction_split_resolver_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    summary = latest.get("direction_split_summary") if isinstance(latest.get("direction_split_summary"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "direction_split_status_counts": dict(
            sorted(Counter(str(record.get("direction_split_status") or "UNKNOWN") for record in records).items())
        ),
        "last_resolver_id": latest.get("resolver_id") if isinstance(latest, Mapping) else None,
        "last_rows_reviewed": summary.get("rows_reviewed"),
        "safety": dict(SAFETY),
    }


def betrayal_direction_split_resolver_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_direction_split_resolver_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _direction_split_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    resolved_candidates = sorted({str(row.get("candidate")) for row in rows if row.get("direction_split_resolved")})
    target_candidates = [f"{timeframe} aggregate" for timeframe in TARGET_TIMEFRAMES]
    blocked = sorted(
        candidate for candidate in target_candidates if candidate not in resolved_candidates and any(row.get("candidate") == candidate for row in rows)
    )
    return {
        "rows_reviewed": len(rows),
        "direction_split_resolved_count": sum(1 for row in rows if row.get("direction_split_resolved")),
        "partial_direction_split_count": sum(1 for row in rows if row.get("direction_context") == "partial"),
        "aggregate_context_only_count": sum(1 for row in rows if row.get("direction_context") == "aggregate_context_only"),
        "schema_missing_count": sum(1 for row in rows if row.get("direction_context") in {"unknown", "schema_missing"}),
        "candidates_with_resolved_direction_split": resolved_candidates,
        "candidates_still_blocked": blocked,
    }


def _event_tracker_rows(event_tracker: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = []
    for key in ("event_seed_candidates", "event_tracker_records_preview"):
        value = event_tracker.get(key)
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, Mapping))
    return rows


def _direction_context(
    *,
    record: Mapping[str, Any],
    lane_direction: str | None,
    original_direction: str | None,
    inverse_direction: str | None,
    entry_mode: Any,
    signal_timestamp: str | None,
    source_signal_id: str | None,
) -> str:
    explicit_context = str(record.get("direction_context") or "").lower()
    candidate_text = str(record.get("candidate") or record.get("candidate_label") or "")
    if explicit_context == "aggregate_context_only" or "aggregate" in candidate_text.lower() and not original_direction:
        return "aggregate_context_only"
    if original_direction and inverse_direction and entry_mode and signal_timestamp and source_signal_id:
        return "direction_specific"
    if lane_direction or original_direction or inverse_direction or entry_mode or signal_timestamp or source_signal_id:
        return "partial"
    return "unknown"


def _row_why(
    *,
    context: str,
    lane_direction: str | None,
    original_direction: str | None,
    inverse_direction: str | None,
    entry_mode: Any,
    signal_timestamp: str | None,
    source_signal_id: str | None,
) -> str:
    if context == "direction_specific" and original_direction and inverse_direction:
        return "Explicit local schema identifies original and inverse direction; paper-only outcome resolver may inspect it next."
    if context == "aggregate_context_only":
        return "Record is aggregate context only; lane direction is not treated as original/inverse proof."
    missing = []
    if not original_direction:
        missing.append("original_direction")
    if not inverse_direction:
        missing.append("inverse_direction")
    if not entry_mode:
        missing.append("entry_mode")
    if not signal_timestamp:
        missing.append("signal_timestamp")
    if not source_signal_id:
        missing.append("source_identity")
    if lane_direction:
        return f"Lane key has {lane_direction}, but explicit source/original schema is incomplete: {', '.join(missing)}."
    return f"Direction split schema is incomplete: {', '.join(missing) if missing else 'unknown schema gap'}."


def _extract_capture_rows(record: Mapping[str, Any], *, source: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("captured_candidates", "captures", "captured_rows"):
        value = record.get(key)
        if isinstance(value, list):
            rows.extend({**dict(row), "source": source} for row in value if isinstance(row, Mapping))
    capture_summary = record.get("capture_summary") if isinstance(record.get("capture_summary"), Mapping) else {}
    rows.extend(_capture_rows_from_summary(capture_summary, source=source))
    summaries = record.get("iteration_summaries")
    if isinstance(summaries, list):
        for summary in summaries:
            if not isinstance(summary, Mapping):
                continue
            capture_summary = summary.get("capture_summary") if isinstance(summary.get("capture_summary"), Mapping) else {}
            rows.extend(_capture_rows_from_summary(capture_summary, source=source))
    return rows


def _capture_rows_from_summary(capture_summary: Mapping[str, Any], *, source: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    examples = capture_summary.get("candidate_examples_by_lane")
    if isinstance(examples, Mapping):
        for lane_rows in examples.values():
            if isinstance(lane_rows, list):
                rows.extend({**dict(row), "source": source} for row in lane_rows if isinstance(row, Mapping))
    return rows


def _dedupe_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = (
            row.get("candidate_id")
            or row.get("capture_id")
            or row.get("source_signal_id")
            or row.get("emitted_signal_id")
            or f"{row.get('lane_key')}|{_signal_timestamp(row)}"
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(_sanitize(dict(row)))
    return deduped


def _dedupe_resolution_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = (
            row.get("candidate"),
            row.get("source"),
            row.get("lane_key"),
            row.get("source_signal_id"),
            row.get("signal_timestamp"),
            row.get("direction_context"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(_sanitize(dict(row)))
    return deduped


def _candidate_label(record: Mapping[str, Any]) -> str:
    candidate = record.get("candidate") or record.get("candidate_label")
    if candidate:
        text = str(candidate)
        return text if "aggregate" in text else f"{_candidate_timeframe(text)} aggregate"
    timeframe = str(record.get("timeframe") or _timeframe_from_lane_key(record.get("lane_key")) or "unknown")
    return f"{timeframe} aggregate"


def _candidate_timeframe(candidate: str) -> str:
    return str(candidate).split()[0]


def _timeframe_from_lane_key(lane_key: Any) -> str | None:
    parts = str(lane_key or "").split("|")
    if len(parts) >= 2:
        return parts[1]
    return None


def _lane_key(record: Mapping[str, Any]) -> str | None:
    lane_key = record.get("lane_key")
    if lane_key:
        return str(lane_key)
    symbol = record.get("symbol") or DEFAULT_SYMBOL
    timeframe = record.get("timeframe") or _candidate_timeframe(str(record.get("candidate") or "unknown"))
    direction = record.get("direction") or record.get("source_direction") or record.get("betrayal_direction")
    entry_mode = record.get("entry_mode") or record.get("source_entry_mode") or DEFAULT_ENTRY_MODE
    if direction:
        return f"{symbol}|{timeframe}|{direction}|{entry_mode}"
    return None


def _source_identity(record: Mapping[str, Any]) -> str | None:
    value = (
        record.get("source_signal_id")
        or record.get("signal_id")
        or record.get("emitted_signal_id")
        or record.get("betrayal_paper_signal_id")
        or record.get("source_capture_id")
        or record.get("capture_id")
        or record.get("candidate_id")
        or record.get("outcome_id")
    )
    return str(value) if value else None


def _signal_timestamp(record: Mapping[str, Any]) -> str | None:
    value = (
        record.get("signal_timestamp")
        or record.get("source_timestamp")
        or record.get("timestamp")
        or record.get("captured_at")
        or record.get("created_at")
        or record.get("generated_at")
    )
    return str(value) if value else None


def _normal_direction(value: Any) -> str | None:
    lowered = str(value or "").lower()
    if lowered in {"long", "short"}:
        return lowered
    return None


def _top_level_status(
    *,
    record_resolver: bool,
    confirmation_valid: bool,
    rows: Sequence[Mapping[str, Any]],
) -> str:
    if record_resolver and not confirmation_valid:
        return BETRAYAL_DIRECTION_SPLIT_RESOLVER_REJECTED
    if not rows:
        return BETRAYAL_DIRECTION_SPLIT_RESOLVER_BLOCKED
    if record_resolver and confirmation_valid:
        return BETRAYAL_DIRECTION_SPLIT_RESOLVER_RECORDED
    return BETRAYAL_DIRECTION_SPLIT_RESOLVER_READY


def _recommended_next_operator_move(split_status: str) -> str:
    if split_status == DIRECTION_SPLIT_RESOLVED_FOR_PAPER_REVIEW:
        return "RUN_R214_BETRAYAL_EVENT_OUTCOME_RESOLVER"
    if split_status == DIRECTION_SPLIT_PARTIAL:
        return "RUN_R216_BETRAYAL_SOURCE_EMITTER_REFRESH"
    return "KEEP_WEEKEND_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(split_status: str, gap_report: Mapping[str, Any]) -> str:
    if split_status == DIRECTION_SPLIT_RESOLVED_FOR_PAPER_REVIEW:
        return "Run R214 paper-only event outcome resolver; do not count rows as validated samples yet."
    if gap_report.get("aggregate_context_only_count") or gap_report.get("partial_direction_split_count"):
        return "Build R216 source emitter refresh so future betrayal rows carry explicit original/inverse direction."
    return "Keep collecting local betrayal paper signals; do not promote betrayal or infer live readiness."


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


def _latest_record(path: Path) -> dict[str, Any]:
    records = _read_recent(path, limit=1)
    return records[0] if records else {}


def _read_recent(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]
    except Exception:
        records = _read_ndjson(path)
        return list(reversed(records[-limit:]))


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(_sanitize(payload))
    return records


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_sanitize(child) for child in value]
    if isinstance(value, tuple):
        return [_sanitize(child) for child in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
