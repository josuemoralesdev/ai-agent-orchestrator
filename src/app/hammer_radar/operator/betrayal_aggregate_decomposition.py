"""R217 betrayal aggregate decomposition.

Paper-only aggregate decomposition audit for betrayal candidates. It composes
R216/R215/R212/R210 and local evidence ledgers without mutating configs,
calling network/Binance, creating payloads, promoting betrayal, or authorizing
live execution.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_event_tracker import build_betrayal_event_identity
from src.app.hammer_radar.operator.betrayal_source_emitter_refresh import SCHEMA_VERSION as SOURCE_SCHEMA_VERSION
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE

BETRAYAL_AGGREGATE_DECOMPOSITION_READY = "BETRAYAL_AGGREGATE_DECOMPOSITION_READY"
BETRAYAL_AGGREGATE_DECOMPOSITION_REJECTED = "BETRAYAL_AGGREGATE_DECOMPOSITION_REJECTED"
BETRAYAL_AGGREGATE_DECOMPOSITION_RECORDED = "BETRAYAL_AGGREGATE_DECOMPOSITION_RECORDED"
BETRAYAL_AGGREGATE_DECOMPOSITION_BLOCKED = "BETRAYAL_AGGREGATE_DECOMPOSITION_BLOCKED"
BETRAYAL_AGGREGATE_DECOMPOSITION_ERROR = "BETRAYAL_AGGREGATE_DECOMPOSITION_ERROR"

AGGREGATE_DECOMPOSITION_READY_FOR_SOURCE_ROWS = "AGGREGATE_DECOMPOSITION_READY_FOR_SOURCE_ROWS"
AGGREGATE_DECOMPOSITION_PARTIAL = "AGGREGATE_DECOMPOSITION_PARTIAL"
AGGREGATE_DECOMPOSITION_BLOCKED = "AGGREGATE_DECOMPOSITION_BLOCKED"
AGGREGATE_DECOMPOSITION_REQUIRES_SOURCE_IDENTITY = "AGGREGATE_DECOMPOSITION_REQUIRES_SOURCE_IDENTITY"
AGGREGATE_DECOMPOSITION_REQUIRES_ENTRY_MODE = "AGGREGATE_DECOMPOSITION_REQUIRES_ENTRY_MODE"
AGGREGATE_DECOMPOSITION_NOT_LIVE_AUTHORIZED = "AGGREGATE_DECOMPOSITION_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_AGGREGATE_DECOMPOSITION"
LEDGER_FILENAME = "betrayal_aggregate_decomposition.ndjson"
CONFIRM_BETRAYAL_AGGREGATE_DECOMPOSITION_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL AGGREGATE DECOMPOSITION RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_SYMBOL = "BTCUSDT"
TARGET_TIMEFRAMES = ("222m", "88m", "55m")
OUTCOME_WINDOWS = [1, 3, 5, 10, 21, 34, 55]

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
    "logs/hammer_radar_forward/betrayal_source_emitter_refresh.ndjson",
    "logs/hammer_radar_forward/betrayal_direction_split_resolver.ndjson",
    "logs/hammer_radar_forward/betrayal_event_tracker.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_matrix_context.ndjson",
    "logs/hammer_radar_forward/betrayal_true_inverse_refresh.ndjson",
    "logs/hammer_radar_forward/betrayal_integration_recheck.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_resolutions.ndjson",
    "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_signals.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_expansion.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_heartbeats.ndjson",
    "docs/hammer_radar/R80_BETRAYAL_STRATEGY_AUDIT.md",
    "docs/hammer_radar/R95_DUAL_LANE_CANDIDATE_WATCH_NORMAL_BETRAYAL.md",
    "docs/hammer_radar/R96_BETRAYAL_TRUE_PAPER_TRACKING_SCAFFOLD.md",
    "docs/hammer_radar/R100_BETRAYAL_SOURCE_SIGNAL_EMITTER.md",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_aggregate_decomposition(
    *,
    log_dir: str | Path | None = None,
    record_decomposition: bool = False,
    confirm_betrayal_aggregate_decomposition: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_aggregate_decomposition
        == CONFIRM_BETRAYAL_AGGREGATE_DECOMPOSITION_RECORDING_PHRASE
    )
    try:
        source_refresh = load_latest_betrayal_source_emitter_refresh(log_dir=resolved_log_dir)
        direction_split = load_latest_betrayal_direction_split_resolver(log_dir=resolved_log_dir)
        event_tracker = load_latest_betrayal_event_tracker(log_dir=resolved_log_dir)
        true_inverse = load_latest_betrayal_true_inverse_refresh(log_dir=resolved_log_dir)
        shadow_outcomes = load_betrayal_shadow_outcomes(log_dir=resolved_log_dir)
        true_paper_outcomes = load_betrayal_true_paper_outcomes(log_dir=resolved_log_dir)
        paper_signals = load_betrayal_paper_signals(log_dir=resolved_log_dir)
        capture_seeds = load_full_spectrum_capture_seeds(log_dir=resolved_log_dir)
        grouped = group_betrayal_evidence_by_direction_entry(
            source_emitter_refresh=source_refresh,
            direction_split_resolver=direction_split,
            event_tracker=event_tracker,
            true_inverse_refresh=true_inverse,
            shadow_outcomes=shadow_outcomes,
            true_paper_outcomes=true_paper_outcomes,
            betrayal_paper_signals=paper_signals,
            full_spectrum_capture_seeds=capture_seeds,
        )
        rows = build_decomposition_rows(grouped_evidence=grouped)
        preview = build_v2_source_rows_preview(decomposition_rows=rows, generated_at=generated_at)
        gap_report = build_decomposition_gap_report(rows)
        recommendations = build_decomposition_recommendations(gap_report=gap_report, rows=rows)
        decomposition_status = classify_betrayal_aggregate_decomposition_status(rows=rows, gap_report=gap_report)
        payload = {
            "status": _top_level_status(
                record_decomposition=record_decomposition,
                confirmation_valid=confirmation_valid,
                rows=rows,
            ),
            "generated_at": generated_at.isoformat(),
            "decomposition_recorded": False,
            "decomposition_id": None,
            "record_decomposition_requested": bool(record_decomposition),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "betrayal_candidates": ["222m aggregate", "88m aggregate", "55m aggregate_if_available"],
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "source_emitter_refresh_found": bool(source_refresh),
                "direction_split_resolver_found": bool(direction_split),
                "event_tracker_found": bool(event_tracker),
                "true_inverse_refresh_found": bool(true_inverse),
                "shadow_outcomes_found": bool(shadow_outcomes),
                "shadow_outcome_count": len(shadow_outcomes),
                "true_paper_outcomes_found": bool(true_paper_outcomes),
                "true_paper_outcome_count": len(true_paper_outcomes),
                "betrayal_paper_signals_found": bool(paper_signals),
                "betrayal_paper_signal_count": len(paper_signals),
                "full_spectrum_capture_seed_count": len(capture_seeds),
            },
            "decomposition_rows": rows,
            "decomposition_summary": _decomposition_summary(rows),
            "v2_source_rows_preview": preview,
            "decomposition_gap_report": gap_report,
            "decomposition_recommendations": recommendations,
            "decomposition_status": decomposition_status,
            "recommended_next_operator_move": _recommended_next_operator_move(decomposition_status, gap_report),
            "recommended_next_engineering_move": _recommended_next_engineering_move(decomposition_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_decomposition and confirmation_valid and rows:
            record = append_betrayal_aggregate_decomposition_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_AGGREGATE_DECOMPOSITION_RECORDED
            payload["decomposition_recorded"] = True
            payload["decomposition_id"] = record["decomposition_id"]
            payload["ledger_path"] = str(betrayal_aggregate_decomposition_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_AGGREGATE_DECOMPOSITION_ERROR,
                "generated_at": generated_at.isoformat(),
                "decomposition_recorded": False,
                "decomposition_id": None,
                "record_decomposition_requested": bool(record_decomposition),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {
                    "betrayal_candidates": ["222m aggregate", "88m aggregate", "55m aggregate_if_available"],
                    "paper_only": True,
                    "live_authorized": False,
                },
                "input_summary": {},
                "decomposition_rows": [],
                "decomposition_summary": _decomposition_summary([]),
                "v2_source_rows_preview": [],
                "decomposition_gap_report": build_decomposition_gap_report([]),
                "decomposition_recommendations": [],
                "decomposition_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_WEEKEND_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R217 decomposition composer error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_betrayal_source_emitter_refresh(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_source_emitter_refresh.ndjson")


def load_latest_betrayal_direction_split_resolver(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_direction_split_resolver.ndjson")


def load_latest_betrayal_event_tracker(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_event_tracker.ndjson")


def load_latest_betrayal_true_inverse_refresh(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_true_inverse_refresh.ndjson")


def load_betrayal_shadow_outcomes(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_shadow_outcomes.ndjson")


def load_betrayal_true_paper_outcomes(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_true_paper_outcomes.ndjson")


def load_betrayal_paper_signals(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_paper_signals.ndjson")


def load_full_spectrum_capture_seeds(*, log_dir: str | Path | None = None, limit: int = 200) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    captures: list[dict[str, Any]] = []
    for filename in ("full_spectrum_harvester_heartbeats.ndjson", "full_spectrum_harvester_expansion.ndjson"):
        for record in _read_recent(resolved_log_dir / filename, limit=limit):
            captures.extend(_extract_capture_rows(record, source="full_spectrum_capture"))
    return _dedupe_raw_records(captures)


def group_betrayal_evidence_by_direction_entry(
    *,
    source_emitter_refresh: Mapping[str, Any],
    direction_split_resolver: Mapping[str, Any],
    event_tracker: Mapping[str, Any],
    true_inverse_refresh: Mapping[str, Any],
    shadow_outcomes: Sequence[Mapping[str, Any]],
    true_paper_outcomes: Sequence[Mapping[str, Any]],
    betrayal_paper_signals: Sequence[Mapping[str, Any]],
    full_spectrum_capture_seeds: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    raw_rows: list[dict[str, Any]] = []
    raw_rows.extend(_rows_from_payload(source_emitter_refresh, "source_emitter_refresh"))
    raw_rows.extend(_rows_from_payload(direction_split_resolver, "direction_split_resolver"))
    raw_rows.extend(_rows_from_payload(event_tracker, "event_tracker"))
    raw_rows.extend(_rows_from_payload(true_inverse_refresh, "true_inverse_refresh"))
    raw_rows.extend({**dict(row), "evidence_source": "shadow_outcome"} for row in shadow_outcomes if isinstance(row, Mapping))
    raw_rows.extend({**dict(row), "evidence_source": "true_paper_outcome"} for row in true_paper_outcomes if isinstance(row, Mapping))
    raw_rows.extend({**dict(row), "evidence_source": "betrayal_paper_signal"} for row in betrayal_paper_signals if isinstance(row, Mapping))
    raw_rows.extend({**dict(row), "evidence_source": "full_spectrum_capture"} for row in full_spectrum_capture_seeds if isinstance(row, Mapping))

    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        candidate = _candidate_label(row)
        timeframe = _candidate_timeframe(candidate)
        if timeframe not in TARGET_TIMEFRAMES:
            continue
        normalized = _normalize_evidence_row(row, candidate=candidate, timeframe=timeframe)
        key = (
            normalized["timeframe"],
            normalized.get("original_direction"),
            normalized.get("inverse_direction"),
            normalized.get("entry_mode"),
            normalized.get("source_identity"),
            normalized.get("source_family"),
        )
        groups[key].append(normalized)
    return [
        _sanitize(
            {
                "timeframe": key[0],
                "original_direction": key[1],
                "inverse_direction": key[2],
                "entry_mode": key[3],
                "source_identity": key[4],
                "source_family": key[5],
                "evidence_count": len(rows),
                "evidence_rows": rows,
            }
        )
        for key, rows in groups.items()
    ]


def build_decomposition_candidate(group: Mapping[str, Any]) -> dict[str, Any]:
    evidence_rows = [row for row in group.get("evidence_rows") or [] if isinstance(row, Mapping)]
    best = _best_evidence_row(evidence_rows)
    candidate = _candidate_label(best) if best else f"{group.get('timeframe')} aggregate"
    original = _normal_direction(best.get("original_direction") if best else group.get("original_direction"))
    inverse = _normal_direction(best.get("inverse_direction") if best else group.get("inverse_direction"))
    entry_mode = best.get("entry_mode") if best else group.get("entry_mode")
    source_identity = _source_identity(best) if best else _string_or_none(group.get("source_identity"))
    source_signal_id = _source_signal_id(best) if best else source_identity
    signal_timestamp = _signal_timestamp(best) if best else None
    lane_direction = _direction_from_lane_key(best.get("lane_key") if best else None)
    missing = _missing_decomposition_fields(
        timeframe=best.get("timeframe") if best else group.get("timeframe"),
        original_direction=original,
        inverse_direction=inverse,
        entry_mode=entry_mode,
        source_identity=source_identity,
        signal_timestamp=signal_timestamp,
    )
    status = _decomposition_status(
        original_direction=original,
        inverse_direction=inverse,
        entry_mode=entry_mode,
        source_identity=source_identity,
        signal_timestamp=signal_timestamp,
        lane_direction=lane_direction,
        evidence_rows=evidence_rows,
    )
    ready = status == AGGREGATE_DECOMPOSITION_READY_FOR_SOURCE_ROWS
    return _sanitize(
        {
            "candidate": candidate,
            "timeframe": best.get("timeframe") if best else group.get("timeframe"),
            "original_direction": original,
            "inverse_direction": inverse,
            "entry_mode": entry_mode,
            "source_identity": source_identity,
            "source_signal_id": source_signal_id,
            "signal_timestamp": signal_timestamp,
            "evidence_source": best.get("evidence_source") if best else None,
            "source_family": best.get("source_family") if best else group.get("source_family"),
            "lane_key": best.get("lane_key") if best else None,
            "lane_direction": lane_direction,
            "missing_fields": missing,
            "evidence_count": len(evidence_rows),
            "decomposition_status": status,
            "ready_for_v2_source_row": ready,
            "can_enter_event_outcome_resolver": ready,
            "can_count_as_validated_sample_now": False,
            "paper_only": True,
            "live_authorized": False,
            "promotion_allowed": False,
            "why": _decomposition_why(status=status, missing_fields=missing, lane_direction=lane_direction),
        }
    )


def build_decomposition_rows(*, grouped_evidence: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [build_decomposition_candidate(group) for group in grouped_evidence]
    rows = _dedupe_decomposition_rows(rows)
    present = {str(row.get("candidate")) for row in rows}
    for timeframe in TARGET_TIMEFRAMES:
        candidate = f"{timeframe} aggregate"
        if timeframe == "55m" and candidate not in present and not any(row.get("timeframe") == "55m" for row in rows):
            continue
        if candidate not in present:
            rows.append(
                _sanitize(
                    {
                        "candidate": candidate,
                        "timeframe": timeframe,
                        "original_direction": None,
                        "inverse_direction": None,
                        "entry_mode": None,
                        "source_identity": None,
                        "source_signal_id": None,
                        "signal_timestamp": None,
                        "evidence_source": "missing",
                        "source_family": "missing",
                        "lane_key": None,
                        "lane_direction": None,
                        "missing_fields": [
                            "original_direction",
                            "inverse_direction",
                            "entry_mode",
                            "source_identity",
                            "signal_timestamp",
                        ],
                        "evidence_count": 0,
                        "decomposition_status": AGGREGATE_DECOMPOSITION_BLOCKED,
                        "ready_for_v2_source_row": False,
                        "can_enter_event_outcome_resolver": False,
                        "can_count_as_validated_sample_now": False,
                        "paper_only": True,
                        "live_authorized": False,
                        "promotion_allowed": False,
                        "why": "No local explicit source evidence exists for this aggregate candidate.",
                    }
                )
            )
    return sorted(rows, key=lambda row: (str(row.get("timeframe")), str(row.get("candidate")), str(row.get("evidence_source"))))


def build_v2_source_rows_preview(
    *,
    decomposition_rows: Sequence[Mapping[str, Any]],
    generated_at: datetime | str | None = None,
) -> list[dict[str, Any]]:
    emitted_at = generated_at.isoformat() if isinstance(generated_at, datetime) else str(generated_at or datetime.now(UTC).isoformat())
    preview = []
    for row in decomposition_rows:
        original = _normal_direction(row.get("original_direction"))
        inverse = _normal_direction(row.get("inverse_direction"))
        emitted_direction = inverse if original and inverse and inverse == _opposite_direction(original) else None
        schema_complete = bool(row.get("ready_for_v2_source_row")) and emitted_direction is not None
        if not schema_complete:
            continue
        source_signal_id = _source_signal_id(row)
        signal_timestamp = _signal_timestamp(row)
        identity = build_betrayal_event_identity(
            symbol=str(row.get("symbol") or DEFAULT_SYMBOL),
            timeframe=str(row.get("timeframe") or "unknown"),
            candidate_label=str(row.get("candidate") or "unknown aggregate"),
            original_direction=original,
            inverse_direction=inverse,
            entry_mode=row.get("entry_mode"),
            source_signal_id=source_signal_id,
            signal_timestamp=signal_timestamp,
            event_timeframe=str(row.get("timeframe") or "unknown"),
            outcome_window=OUTCOME_WINDOWS,
        )
        preview.append(
            _sanitize(
                {
                    "schema_version": SOURCE_SCHEMA_VERSION,
                    "candidate": row.get("candidate"),
                    "symbol": row.get("symbol") or DEFAULT_SYMBOL,
                    "timeframe": row.get("timeframe"),
                    "entry_mode": row.get("entry_mode"),
                    "original_direction": original,
                    "inverse_direction": inverse,
                    "emitted_direction": emitted_direction,
                    "source_identity": row.get("source_identity") or source_signal_id,
                    "source_signal_id": source_signal_id,
                    "emitted_signal_id": _emitted_signal_id(row),
                    "source_signal_timestamp": signal_timestamp,
                    "emitted_at": emitted_at,
                    "lane_key": row.get("lane_key"),
                    "betrayal_event_identity": identity["event_identity"],
                    "betrayal_event_identity_hash": identity["event_identity_hash"],
                    "schema_complete": True,
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                }
            )
        )
    return preview


def build_decomposition_gap_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "missing_entry_mode": sum(1 for row in rows if not row.get("entry_mode")),
        "missing_source_identity": sum(1 for row in rows if not (row.get("source_identity") or row.get("source_signal_id"))),
        "missing_original_direction": sum(1 for row in rows if not row.get("original_direction")),
        "missing_inverse_direction": sum(1 for row in rows if not row.get("inverse_direction")),
        "missing_signal_timestamp": sum(1 for row in rows if not row.get("signal_timestamp")),
        "lane_direction_only_rows": sum(1 for row in rows if row.get("lane_direction") and not row.get("original_direction")),
        "aggregate_only_rows": sum(1 for row in rows if row.get("decomposition_status") == AGGREGATE_DECOMPOSITION_BLOCKED),
        "hard_live_blockers": [
            "betrayal_not_live_authorized",
            "betrayal_not_promoted",
            "aggregate_decomposition_is_paper_only",
            "config_writes_forbidden",
            "orders_forbidden",
            "binance_calls_forbidden",
            "live_authorization_forbidden",
        ],
    }


def build_decomposition_recommendations(
    *,
    gap_report: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    recommendations = []
    if any(row.get("ready_for_v2_source_row") for row in rows):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "APPEND_V2_SOURCE_ROWS",
                "future_phase": "R218",
                "why": "At least one local aggregate decomposition row is schema-complete for paper-only v2 source row append.",
            }
        )
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "RUN_EVENT_OUTCOME_RESOLVER",
                "future_phase": "R214",
                "why": "Schema-complete v2 source previews can be reviewed by the paper-only event outcome resolver after append.",
            }
        )
    if gap_report.get("missing_source_identity"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "COLLECT_SOURCE_IDENTITY",
                "future_phase": "R218",
                "why": "Partial rows still lack explicit source identity and must remain blocked from resolver-ready source rows.",
            }
        )
    if gap_report.get("missing_entry_mode"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "WIRE_SOURCE_EMITTER",
                "future_phase": "R218",
                "why": "Entry mode must be emitted by the local source; default ladder mode is not used as proof.",
            }
        )
    recommendations.append(
        {
            "priority": "LOW",
            "recommended_action": "KEEP_CONTEXT_ONLY",
            "future_phase": "R217",
            "why": "Aggregate decomposition is audit-only and cannot promote betrayal or authorize live execution.",
        }
    )
    return recommendations


def classify_betrayal_aggregate_decomposition_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
) -> str:
    if not rows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if any(row.get("ready_for_v2_source_row") for row in rows):
        return AGGREGATE_DECOMPOSITION_READY_FOR_SOURCE_ROWS
    if gap_report.get("missing_source_identity") and not gap_report.get("missing_entry_mode"):
        return AGGREGATE_DECOMPOSITION_REQUIRES_SOURCE_IDENTITY
    if gap_report.get("missing_entry_mode"):
        return AGGREGATE_DECOMPOSITION_REQUIRES_ENTRY_MODE
    if any(row.get("decomposition_status") == AGGREGATE_DECOMPOSITION_PARTIAL for row in rows):
        return AGGREGATE_DECOMPOSITION_PARTIAL
    if all(row.get("decomposition_status") == AGGREGATE_DECOMPOSITION_BLOCKED for row in rows):
        return AGGREGATE_DECOMPOSITION_BLOCKED
    return AGGREGATE_DECOMPOSITION_NOT_LIVE_AUTHORIZED


def append_betrayal_aggregate_decomposition_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_aggregate_decomposition_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "decomposition_id": str(record.get("decomposition_id") or f"r217_betrayal_aggregate_decomposition_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_AGGREGATE_DECOMPOSITION_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_decomposition_requested": bool(record.get("record_decomposition_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "decomposition_rows": list(record.get("decomposition_rows") or []),
            "decomposition_summary": dict(record.get("decomposition_summary") or {}),
            "v2_source_rows_preview": list(record.get("v2_source_rows_preview") or []),
            "decomposition_gap_report": dict(record.get("decomposition_gap_report") or {}),
            "decomposition_recommendations": list(record.get("decomposition_recommendations") or []),
            "decomposition_status": record.get("decomposition_status"),
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


def load_betrayal_aggregate_decomposition_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_aggregate_decomposition_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_betrayal_aggregate_decomposition_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    summary = latest.get("decomposition_summary") if isinstance(latest.get("decomposition_summary"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "decomposition_status_counts": dict(
            sorted(Counter(str(record.get("decomposition_status") or "UNKNOWN") for record in records).items())
        ),
        "last_decomposition_id": latest.get("decomposition_id") if isinstance(latest, Mapping) else None,
        "last_rows_reviewed": summary.get("rows_reviewed"),
        "last_ready_rows": summary.get("ready_rows"),
        "safety": dict(SAFETY),
    }


def betrayal_aggregate_decomposition_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_aggregate_decomposition_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _rows_from_payload(payload: Mapping[str, Any], source: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in (
        "source_candidate_rows",
        "direction_specific_source_preview",
        "direction_split_resolution_rows",
        "event_seed_candidates",
        "event_tracker_records_preview",
        "event_tracker_preview",
        "candidate_true_inverse_summary",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            rows.extend({**dict(row), "evidence_source": source} for row in value if isinstance(row, Mapping))
        elif isinstance(value, Mapping):
            rows.extend({**dict(row), "evidence_source": source} for row in _flatten_candidate_maps(value))
    return rows


def _flatten_candidate_maps(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = []
    for key, child in value.items():
        if isinstance(child, Mapping):
            rows.append({"candidate": key, **dict(child)})
        elif isinstance(child, list):
            rows.extend(row for row in child if isinstance(row, Mapping))
    return rows


def _normalize_evidence_row(row: Mapping[str, Any], *, candidate: str, timeframe: str) -> dict[str, Any]:
    source_identity = _source_identity(row)
    source_signal_id = _source_signal_id(row) or source_identity
    return _sanitize(
        {
            **dict(row),
            "candidate": candidate,
            "symbol": row.get("symbol") or DEFAULT_SYMBOL,
            "timeframe": timeframe,
            "original_direction": _normal_direction(row.get("original_direction") or row.get("source_original_direction")),
            "inverse_direction": _normal_direction(
                row.get("inverse_direction") or row.get("betrayal_direction") or row.get("shadow_direction")
            ),
            "entry_mode": row.get("entry_mode") or row.get("source_entry_mode"),
            "source_identity": source_identity,
            "source_signal_id": source_signal_id,
            "signal_timestamp": _signal_timestamp(row),
            "source_family": _source_family(row),
            "evidence_source": row.get("evidence_source") or row.get("source") or "unknown",
        }
    )


def _best_evidence_row(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    return dict(sorted(rows, key=_evidence_rank)[-1])


def _evidence_rank(row: Mapping[str, Any]) -> tuple[int, int, int, int, int, str]:
    source = str(row.get("evidence_source") or "")
    source_weight = {
        "betrayal_paper_signal": 5,
        "true_paper_outcome": 5,
        "source_emitter_refresh": 4,
        "direction_split_resolver": 3,
        "event_tracker": 2,
        "shadow_outcome": 2,
        "full_spectrum_capture": 1,
    }.get(source, 0)
    return (
        source_weight,
        int(bool(row.get("original_direction"))),
        int(bool(row.get("inverse_direction"))),
        int(bool(row.get("entry_mode"))),
        int(bool(_source_identity(row) and _signal_timestamp(row))),
        str(_signal_timestamp(row) or ""),
    )


def _missing_decomposition_fields(
    *,
    timeframe: Any,
    original_direction: str | None,
    inverse_direction: str | None,
    entry_mode: Any,
    source_identity: str | None,
    signal_timestamp: str | None,
) -> list[str]:
    missing = []
    if not timeframe:
        missing.append("timeframe")
    if not original_direction:
        missing.append("original_direction")
    if not inverse_direction or (original_direction and inverse_direction != _opposite_direction(original_direction)):
        missing.append("inverse_direction")
    if not entry_mode:
        missing.append("entry_mode")
    if not source_identity:
        missing.append("source_identity")
    if not signal_timestamp:
        missing.append("signal_timestamp")
    return missing


def _decomposition_status(
    *,
    original_direction: str | None,
    inverse_direction: str | None,
    entry_mode: Any,
    source_identity: str | None,
    signal_timestamp: str | None,
    lane_direction: str | None,
    evidence_rows: Sequence[Mapping[str, Any]],
) -> str:
    explicit_opposite = bool(original_direction and inverse_direction and inverse_direction == _opposite_direction(original_direction))
    if explicit_opposite and entry_mode and source_identity and signal_timestamp:
        return AGGREGATE_DECOMPOSITION_READY_FOR_SOURCE_ROWS
    if explicit_opposite and not source_identity:
        return AGGREGATE_DECOMPOSITION_REQUIRES_SOURCE_IDENTITY
    if explicit_opposite and not entry_mode:
        return AGGREGATE_DECOMPOSITION_REQUIRES_ENTRY_MODE
    if explicit_opposite:
        return AGGREGATE_DECOMPOSITION_PARTIAL
    if lane_direction or evidence_rows:
        return AGGREGATE_DECOMPOSITION_BLOCKED
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def _decomposition_why(*, status: str, missing_fields: Sequence[str], lane_direction: str | None) -> str:
    if status == AGGREGATE_DECOMPOSITION_READY_FOR_SOURCE_ROWS:
        return "Explicit local evidence has timeframe, original/inverse direction, entry mode, source identity, and timestamp for paper-only v2 preview."
    if status == AGGREGATE_DECOMPOSITION_REQUIRES_SOURCE_IDENTITY:
        return "Original/inverse direction is explicit, but source identity is missing; row cannot become resolver-ready."
    if status == AGGREGATE_DECOMPOSITION_REQUIRES_ENTRY_MODE:
        return "Original/inverse direction is explicit, but entry mode is missing; default ladder mode is not used as proof."
    if status == AGGREGATE_DECOMPOSITION_PARTIAL:
        return f"Direction schema is explicit but still incomplete: {', '.join(missing_fields)}."
    if lane_direction:
        return f"Lane key has {lane_direction}, but lane direction alone is not original/inverse proof."
    return "Aggregate context lacks explicit direction/source schema and remains blocked."


def _decomposition_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ready = [row for row in rows if row.get("ready_for_v2_source_row")]
    partial = [
        row
        for row in rows
        if row.get("decomposition_status")
        in {
            AGGREGATE_DECOMPOSITION_PARTIAL,
            AGGREGATE_DECOMPOSITION_REQUIRES_ENTRY_MODE,
            AGGREGATE_DECOMPOSITION_REQUIRES_SOURCE_IDENTITY,
        }
    ]
    blocked = [row for row in rows if row.get("decomposition_status") == AGGREGATE_DECOMPOSITION_BLOCKED]
    return {
        "rows_reviewed": len(rows),
        "ready_rows": len(ready),
        "partial_rows": len(partial),
        "blocked_rows": len(blocked),
        "ready_candidates": sorted({str(row.get("candidate")) for row in ready}),
        "partial_candidates": sorted({str(row.get("candidate")) for row in partial}),
        "blocked_candidates": sorted({str(row.get("candidate")) for row in blocked}),
    }


def _top_level_status(
    *,
    record_decomposition: bool,
    confirmation_valid: bool,
    rows: Sequence[Mapping[str, Any]],
) -> str:
    if record_decomposition and not confirmation_valid:
        return BETRAYAL_AGGREGATE_DECOMPOSITION_REJECTED
    if not rows:
        return BETRAYAL_AGGREGATE_DECOMPOSITION_BLOCKED
    if record_decomposition and confirmation_valid:
        return BETRAYAL_AGGREGATE_DECOMPOSITION_RECORDED
    return BETRAYAL_AGGREGATE_DECOMPOSITION_READY


def _recommended_next_operator_move(decomposition_status: str, gap_report: Mapping[str, Any]) -> str:
    if decomposition_status == AGGREGATE_DECOMPOSITION_READY_FOR_SOURCE_ROWS:
        return "RUN_R218_BETRAYAL_V2_SOURCE_ROW_APPEND"
    if gap_report.get("missing_entry_mode") or gap_report.get("missing_source_identity"):
        return "KEEP_WEEKEND_FISHERMAN_RUNNING"
    return "RUN_R208B_FISHERMAN_WATCHDOG_HARDENING"


def _recommended_next_engineering_move(decomposition_status: str, gap_report: Mapping[str, Any]) -> str:
    if decomposition_status == AGGREGATE_DECOMPOSITION_READY_FOR_SOURCE_ROWS:
        return "Build R218 append-only v2 source row writer that consumes only schema_complete=true previews."
    if gap_report.get("missing_entry_mode") or gap_report.get("missing_source_identity"):
        return "Keep source collection running and wire future emitters to include explicit entry_mode and source_identity."
    return "Keep R217 context-only until explicit local source schema appears."


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


def _extract_capture_rows(record: Mapping[str, Any], *, source: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("captured_candidates", "captures", "captured_rows"):
        value = record.get(key)
        if isinstance(value, list):
            rows.extend({**dict(row), "evidence_source": source} for row in value if isinstance(row, Mapping))
    capture_summary = record.get("capture_summary") if isinstance(record.get("capture_summary"), Mapping) else {}
    rows.extend(_capture_rows_from_summary(capture_summary, source=source))
    summaries = record.get("iteration_summaries")
    if isinstance(summaries, list):
        for summary in summaries:
            if not isinstance(summary, Mapping):
                continue
            nested = summary.get("capture_summary") if isinstance(summary.get("capture_summary"), Mapping) else {}
            rows.extend(_capture_rows_from_summary(nested, source=source))
    return rows


def _capture_rows_from_summary(capture_summary: Mapping[str, Any], *, source: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    examples = capture_summary.get("candidate_examples_by_lane")
    if isinstance(examples, Mapping):
        for lane_rows in examples.values():
            if isinstance(lane_rows, list):
                rows.extend({**dict(row), "evidence_source": source} for row in lane_rows if isinstance(row, Mapping))
    return rows


def _dedupe_raw_records(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
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


def _dedupe_decomposition_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for row in rows:
        key = (
            row.get("candidate"),
            row.get("original_direction"),
            row.get("inverse_direction"),
            row.get("entry_mode"),
            row.get("source_identity") or row.get("source_signal_id"),
            row.get("signal_timestamp"),
        )
        current = by_key.get(key)
        if current is None or _row_rank(row) >= _row_rank(current):
            by_key[key] = row
    return [_sanitize(dict(row)) for row in by_key.values()]


def _row_rank(row: Mapping[str, Any]) -> tuple[int, int]:
    status_weight = {
        AGGREGATE_DECOMPOSITION_READY_FOR_SOURCE_ROWS: 4,
        AGGREGATE_DECOMPOSITION_REQUIRES_SOURCE_IDENTITY: 3,
        AGGREGATE_DECOMPOSITION_REQUIRES_ENTRY_MODE: 3,
        AGGREGATE_DECOMPOSITION_PARTIAL: 2,
        AGGREGATE_DECOMPOSITION_BLOCKED: 1,
    }.get(str(row.get("decomposition_status")), 0)
    return (status_weight, int(row.get("evidence_count") or 0))


def _candidate_label(row: Mapping[str, Any]) -> str:
    candidate = row.get("candidate") or row.get("candidate_label")
    if candidate:
        text = str(candidate)
        return text if "aggregate" in text else f"{_candidate_timeframe(text)} aggregate"
    timeframe = str(row.get("timeframe") or _timeframe_from_lane_key(row.get("lane_key")) or "unknown")
    return f"{timeframe} aggregate"


def _candidate_timeframe(candidate: str) -> str:
    return str(candidate).split()[0]


def _timeframe_from_lane_key(lane_key: Any) -> str | None:
    parts = str(lane_key or "").split("|")
    if len(parts) >= 2:
        return parts[1]
    return None


def _direction_from_lane_key(lane_key: Any) -> str | None:
    parts = str(lane_key or "").split("|")
    if len(parts) >= 3:
        return _normal_direction(parts[2])
    return None


def _source_identity(row: Mapping[str, Any]) -> str | None:
    return _string_or_none(row.get("source_identity") or row.get("source_signal_id") or row.get("source_id"))


def _source_signal_id(row: Mapping[str, Any]) -> str | None:
    value = (
        row.get("source_signal_id")
        or row.get("signal_id")
        or row.get("emitted_signal_id")
        or row.get("betrayal_paper_signal_id")
        or row.get("source_capture_id")
        or row.get("capture_id")
        or row.get("candidate_id")
        or row.get("outcome_id")
    )
    return _string_or_none(value)


def _signal_timestamp(row: Mapping[str, Any]) -> str | None:
    value = (
        row.get("source_signal_timestamp")
        or row.get("signal_timestamp")
        or row.get("source_timestamp")
        or row.get("timestamp")
        or row.get("captured_at")
        or row.get("created_at")
        or row.get("generated_at")
    )
    return _string_or_none(value)


def _source_family(row: Mapping[str, Any]) -> str:
    source = str(row.get("source_family") or row.get("source") or row.get("evidence_source") or "unknown")
    if "paper_signal" in source:
        return "betrayal_paper_signal"
    if "outcome" in source:
        return "betrayal_outcome"
    if "shadow" in source:
        return "shadow_outcome"
    if "full_spectrum" in source or "capture" in source:
        return "full_spectrum_capture"
    if "event_tracker" in source:
        return "event_tracker"
    if "direction_split" in source:
        return "direction_split_resolver"
    if "source_emitter" in source:
        return "source_emitter_refresh"
    return source


def _normal_direction(value: Any) -> str | None:
    lowered = str(value or "").lower()
    if lowered in {"long", "short"}:
        return lowered
    return None


def _opposite_direction(value: Any) -> str | None:
    direction = _normal_direction(value)
    if direction == "long":
        return "short"
    if direction == "short":
        return "long"
    return None


def _emitted_signal_id(row: Mapping[str, Any]) -> str:
    stable = json.dumps(
        {
            "schema_version": SOURCE_SCHEMA_VERSION,
            "candidate": row.get("candidate"),
            "source_signal_id": _source_signal_id(row),
            "signal_timestamp": _signal_timestamp(row),
            "original_direction": _normal_direction(row.get("original_direction")),
            "inverse_direction": _normal_direction(row.get("inverse_direction")),
            "entry_mode": row.get("entry_mode"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"betrayal_source_emitter_v2|{hashlib.sha256(stable.encode('utf-8')).hexdigest()[:24]}"


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


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
