"""R216 betrayal source emitter refresh.

Paper-only source-emitter contract refresh for future betrayal paper signals.
It composes R215/R212/R211/R210 local ledgers and previews v2 rows without
fabricating direction, mutating configs, calling network/Binance, or creating
orders.
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
from src.app.hammer_radar.operator.betrayal_event_tracker import build_betrayal_event_identity
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE

BETRAYAL_SOURCE_EMITTER_REFRESH_READY = "BETRAYAL_SOURCE_EMITTER_REFRESH_READY"
BETRAYAL_SOURCE_EMITTER_REFRESH_REJECTED = "BETRAYAL_SOURCE_EMITTER_REFRESH_REJECTED"
BETRAYAL_SOURCE_EMITTER_REFRESH_RECORDED = "BETRAYAL_SOURCE_EMITTER_REFRESH_RECORDED"
BETRAYAL_SOURCE_EMITTER_REFRESH_BLOCKED = "BETRAYAL_SOURCE_EMITTER_REFRESH_BLOCKED"
BETRAYAL_SOURCE_EMITTER_REFRESH_ERROR = "BETRAYAL_SOURCE_EMITTER_REFRESH_ERROR"

SOURCE_EMITTER_CONTRACT_READY = "SOURCE_EMITTER_CONTRACT_READY"
SOURCE_EMITTER_DIRECTION_SPECIFIC_PREVIEW_READY = "SOURCE_EMITTER_DIRECTION_SPECIFIC_PREVIEW_READY"
SOURCE_EMITTER_AGGREGATE_DECOMPOSITION_REQUIRED = "SOURCE_EMITTER_AGGREGATE_DECOMPOSITION_REQUIRED"
SOURCE_EMITTER_EXISTING_ROWS_INCOMPLETE = "SOURCE_EMITTER_EXISTING_ROWS_INCOMPLETE"
SOURCE_EMITTER_NOT_LIVE_AUTHORIZED = "SOURCE_EMITTER_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_SOURCE_EMITTER_REFRESH"
LEDGER_FILENAME = "betrayal_source_emitter_refresh.ndjson"
SCHEMA_VERSION = "betrayal_source_emitter_v2"
SOURCE_TYPE = "betrayal_source_emitter"
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_ENTRY_MODE = "ladder_close_50_618"
TARGET_TIMEFRAMES = ("222m", "88m", "55m")
OUTCOME_WINDOWS = [1, 3, 5, 10, 21, 34, 55]
CONFIRM_BETRAYAL_SOURCE_EMITTER_REFRESH_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL SOURCE EMITTER REFRESH RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

REQUIRED_FIELDS = [
    "schema_version",
    "source_type",
    "candidate",
    "symbol",
    "timeframe",
    "entry_mode",
    "original_direction",
    "inverse_direction",
    "emitted_direction",
    "source_identity",
    "source_signal_id",
    "emitted_signal_id",
    "source_signal_timestamp",
    "emitted_at",
    "lane_key",
    "betrayal_event_identity",
    "betrayal_event_identity_hash",
    "outcome_windows",
    "paper_only",
    "live_authorized",
    "promotion_allowed",
]

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
    "logs/hammer_radar_forward/betrayal_direction_split_resolver.ndjson",
    "logs/hammer_radar_forward/betrayal_event_tracker.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_matrix_context.ndjson",
    "logs/hammer_radar_forward/betrayal_true_inverse_refresh.ndjson",
    "logs/hammer_radar_forward/betrayal_integration_recheck.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_signals.ndjson",
    "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
    "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_expansion.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_source_emitter_refresh(
    *,
    log_dir: str | Path | None = None,
    record_refresh: bool = False,
    confirm_betrayal_source_emitter_refresh: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_source_emitter_refresh
        == CONFIRM_BETRAYAL_SOURCE_EMITTER_REFRESH_RECORDING_PHRASE
    )
    try:
        direction_split = load_latest_betrayal_direction_split_resolver(log_dir=resolved_log_dir)
        event_tracker = load_latest_betrayal_event_tracker(log_dir=resolved_log_dir)
        matrix_context = load_latest_betrayal_paper_matrix_context(log_dir=resolved_log_dir)
        true_inverse = load_latest_betrayal_true_inverse_refresh(log_dir=resolved_log_dir)
        paper_signals = load_existing_betrayal_paper_signals(log_dir=resolved_log_dir)
        source_emitter_records = load_existing_betrayal_source_emitter_records(log_dir=resolved_log_dir)
        contract = build_refreshed_betrayal_source_contract()
        candidate_rows = build_betrayal_source_candidate_rows(
            direction_split_resolver=direction_split,
            event_tracker=event_tracker,
            paper_matrix_context=matrix_context,
            true_inverse_refresh=true_inverse,
            existing_betrayal_paper_signals=paper_signals,
        )
        preview = build_direction_specific_source_preview(
            source_candidate_rows=candidate_rows,
            generated_at=generated_at,
        )
        decomposition = build_aggregate_decomposition_requirements(candidate_rows)
        gap_report = build_betrayal_source_emitter_gap_report(candidate_rows, preview)
        recommendations = build_betrayal_source_emitter_recommendations(gap_report=gap_report, candidate_rows=candidate_rows)
        source_status = classify_betrayal_source_emitter_refresh_status(
            source_candidate_rows=candidate_rows,
            gap_report=gap_report,
        )
        payload = {
            "status": _top_level_status(
                record_refresh=record_refresh,
                confirmation_valid=confirmation_valid,
                candidate_rows=candidate_rows,
            ),
            "generated_at": generated_at.isoformat(),
            "refresh_recorded": False,
            "refresh_id": None,
            "record_refresh_requested": bool(record_refresh),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "betrayal_candidates": ["222m aggregate", "88m aggregate", "55m aggregate_if_available"],
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "direction_split_resolver_found": bool(direction_split),
                "event_tracker_found": bool(event_tracker),
                "paper_matrix_context_found": bool(matrix_context),
                "true_inverse_refresh_found": bool(true_inverse),
                "existing_betrayal_paper_signals_found": bool(paper_signals),
                "existing_betrayal_paper_signal_count": len(paper_signals),
                "existing_source_emitter_records_found": bool(source_emitter_records),
                "existing_source_emitter_record_count": len(source_emitter_records),
            },
            "refreshed_source_contract": contract,
            "source_candidate_rows": candidate_rows,
            "direction_specific_source_preview": preview,
            "aggregate_decomposition_requirements": decomposition,
            "source_emitter_gap_report": gap_report,
            "source_emitter_recommendations": recommendations,
            "source_emitter_status": source_status,
            "recommended_next_operator_move": _recommended_next_operator_move(source_status, gap_report),
            "recommended_next_engineering_move": _recommended_next_engineering_move(source_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_refresh and confirmation_valid and candidate_rows:
            record = append_betrayal_source_emitter_refresh_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_SOURCE_EMITTER_REFRESH_RECORDED
            payload["refresh_recorded"] = True
            payload["refresh_id"] = record["refresh_id"]
            payload["ledger_path"] = str(betrayal_source_emitter_refresh_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_SOURCE_EMITTER_REFRESH_ERROR,
                "generated_at": generated_at.isoformat(),
                "refresh_recorded": False,
                "refresh_id": None,
                "record_refresh_requested": bool(record_refresh),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {
                    "betrayal_candidates": ["222m aggregate", "88m aggregate", "55m aggregate_if_available"],
                    "paper_only": True,
                    "live_authorized": False,
                },
                "input_summary": {},
                "refreshed_source_contract": build_refreshed_betrayal_source_contract(),
                "source_candidate_rows": [],
                "direction_specific_source_preview": [],
                "aggregate_decomposition_requirements": {},
                "source_emitter_gap_report": build_betrayal_source_emitter_gap_report([], []),
                "source_emitter_recommendations": [],
                "source_emitter_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_WEEKEND_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R216 source emitter refresh composer error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_betrayal_direction_split_resolver(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_direction_split_resolver.ndjson")


def load_latest_betrayal_event_tracker(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_event_tracker.ndjson")


def load_latest_betrayal_paper_matrix_context(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_paper_matrix_context.ndjson")


def load_latest_betrayal_true_inverse_refresh(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_true_inverse_refresh.ndjson")


def load_existing_betrayal_paper_signals(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_paper_signals.ndjson")


def load_existing_betrayal_source_emitter_records(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = load_betrayal_source_emitter_refresh_records(log_dir=resolved_log_dir, limit=0)
    report = _read_json(resolved_log_dir / "betrayal_source_signal_emitter_report.json")
    if report:
        records.append({"source": "betrayal_source_signal_emitter_report", **report})
    return [_sanitize(record) for record in records]


def build_refreshed_betrayal_source_contract() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "source_type": SOURCE_TYPE,
        "required_fields": list(REQUIRED_FIELDS),
        "direction_fields_required": True,
        "aggregate_decomposition_required": True,
        "paper_only": True,
        "live_authorized": False,
        "promotion_allowed": False,
        "direction_rules": [
            "original_direction must be explicit, not inferred from aggregate context.",
            "inverse_direction must be opposite(original_direction).",
            "emitted_direction must equal inverse_direction for betrayal tracking.",
            "lane direction alone is not enough unless source explicitly marks original/inverse direction.",
            "aggregate candidates must be decomposed before direction-specific rows can emit.",
        ],
    }


def build_betrayal_source_candidate_rows(
    *,
    direction_split_resolver: Mapping[str, Any],
    event_tracker: Mapping[str, Any],
    paper_matrix_context: Mapping[str, Any],
    true_inverse_refresh: Mapping[str, Any],
    existing_betrayal_paper_signals: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    del paper_matrix_context, true_inverse_refresh
    source_rows = _source_rows(direction_split_resolver, event_tracker, existing_betrayal_paper_signals)
    rows: list[dict[str, Any]] = []
    for timeframe in TARGET_TIMEFRAMES:
        candidate = f"{timeframe} aggregate"
        candidate_sources = [row for row in source_rows if _candidate_label(row) == candidate]
        if not candidate_sources and timeframe == "55m":
            continue
        best = _best_source_row(candidate_sources, candidate=candidate, timeframe=timeframe)
        missing = _missing_fields(best)
        context = _existing_direction_split(best)
        can_emit = not missing and context == "resolved"
        aggregate_required = context != "resolved"
        rows.append(
            _sanitize(
                {
                    "candidate": candidate,
                    "source_status": _candidate_source_status(
                        can_emit_direction_specific_now=can_emit,
                        aggregate_decomposition_required=aggregate_required,
                        missing_fields=missing,
                    ),
                    "existing_direction_split": context,
                    "can_emit_direction_specific_now": bool(can_emit),
                    "aggregate_decomposition_required": bool(aggregate_required),
                    "missing_fields": missing,
                    "source": best.get("source"),
                    "symbol": best.get("symbol") or DEFAULT_SYMBOL,
                    "timeframe": timeframe,
                    "entry_mode": best.get("entry_mode"),
                    "original_direction": _normal_direction(best.get("original_direction")),
                    "inverse_direction": _normal_direction(best.get("inverse_direction") or best.get("betrayal_direction")),
                    "source_direction": _normal_direction(best.get("source_direction") or _direction_from_lane_key(best.get("lane_key"))),
                    "source_signal_id": _source_signal_id(best),
                    "signal_timestamp": _signal_timestamp(best),
                    "lane_key": best.get("lane_key"),
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                    "why": _candidate_why(
                        candidate=candidate,
                        context=context,
                        missing_fields=missing,
                        lane_direction=_direction_from_lane_key(best.get("lane_key")),
                    ),
                }
            )
        )
    return rows


def build_direction_specific_source_preview(
    *,
    source_candidate_rows: Sequence[Mapping[str, Any]],
    generated_at: datetime | str | None = None,
) -> list[dict[str, Any]]:
    emitted_at = generated_at.isoformat() if isinstance(generated_at, datetime) else str(generated_at or datetime.now(UTC).isoformat())
    preview = []
    for row in source_candidate_rows:
        original = _normal_direction(row.get("original_direction"))
        inverse = _normal_direction(row.get("inverse_direction"))
        emitted_direction = inverse if original and inverse and inverse == _opposite_direction(original) else None
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
        emitted_signal_id = _emitted_signal_id(
            candidate=str(row.get("candidate") or ""),
            source_signal_id=source_signal_id,
            signal_timestamp=signal_timestamp,
            original_direction=original,
            inverse_direction=inverse,
            entry_mode=row.get("entry_mode"),
        )
        schema_complete = bool(row.get("can_emit_direction_specific_now")) and emitted_direction is not None
        preview.append(
            _sanitize(
                {
                    "schema_version": SCHEMA_VERSION,
                    "source_type": SOURCE_TYPE,
                    "candidate": row.get("candidate"),
                    "symbol": row.get("symbol") or DEFAULT_SYMBOL,
                    "timeframe": row.get("timeframe"),
                    "entry_mode": row.get("entry_mode"),
                    "original_direction": original,
                    "inverse_direction": inverse,
                    "emitted_direction": emitted_direction,
                    "source_identity": source_signal_id,
                    "source_signal_id": source_signal_id,
                    "emitted_signal_id": emitted_signal_id,
                    "source_signal_timestamp": signal_timestamp,
                    "emitted_at": emitted_at,
                    "lane_key": row.get("lane_key"),
                    "betrayal_event_identity": identity["event_identity"],
                    "betrayal_event_identity_hash": identity["event_identity_hash"],
                    "outcome_windows": list(OUTCOME_WINDOWS),
                    "schema_complete": schema_complete,
                    "aggregate_context_only": not schema_complete,
                    "blocked_from_event_outcome_resolver": not schema_complete,
                    "paper_only": True,
                    "live_authorized": False,
                    "promotion_allowed": False,
                }
            )
        )
    return preview


def build_aggregate_decomposition_requirements(source_candidate_rows: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    requirements: dict[str, list[str]] = {}
    default_requirements = [
        "direction-specific candidate identity",
        "explicit original_direction",
        "explicit inverse_direction",
        "explicit entry_mode",
        "source_identity/source_signal_id",
        "signal_timestamp",
        "outcome_windows",
    ]
    for row in source_candidate_rows:
        candidate = str(row.get("candidate") or "")
        missing = [str(item) for item in row.get("missing_fields") or []]
        if row.get("aggregate_decomposition_required"):
            requirements[candidate] = missing or list(default_requirements)
        else:
            requirements[candidate] = []
    for timeframe in TARGET_TIMEFRAMES:
        requirements.setdefault(f"{timeframe} aggregate", list(default_requirements))
    return requirements


def build_betrayal_source_emitter_gap_report(
    source_candidate_rows: Sequence[Mapping[str, Any]],
    direction_specific_source_preview: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "direction_specific_rows_ready": sum(1 for row in direction_specific_source_preview if row.get("schema_complete")),
        "aggregate_rows_blocked": sum(1 for row in source_candidate_rows if row.get("aggregate_decomposition_required")),
        "missing_original_direction": sum(1 for row in source_candidate_rows if "original_direction" in (row.get("missing_fields") or [])),
        "missing_inverse_direction": sum(1 for row in source_candidate_rows if "inverse_direction" in (row.get("missing_fields") or [])),
        "missing_entry_mode": sum(1 for row in source_candidate_rows if "entry_mode" in (row.get("missing_fields") or [])),
        "missing_source_identity": sum(1 for row in source_candidate_rows if "source_identity" in (row.get("missing_fields") or [])),
        "missing_signal_timestamp": sum(1 for row in source_candidate_rows if "signal_timestamp" in (row.get("missing_fields") or [])),
        "hard_live_blockers": [
            "betrayal_not_live_authorized",
            "betrayal_not_promoted",
            "source_emitter_refresh_is_paper_only",
            "config_writes_forbidden",
            "orders_forbidden",
            "binance_calls_forbidden",
            "direction_decomposition_required_before_outcome_resolver",
        ],
    }


def build_betrayal_source_emitter_recommendations(
    *,
    gap_report: Mapping[str, Any],
    candidate_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    recommendations = []
    if gap_report.get("aggregate_rows_blocked"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "DECOMPOSE_AGGREGATE_CANDIDATES",
                "future_phase": "R217",
                "why": "Aggregate candidates still lack explicit original/inverse source schema and cannot emit resolver-ready rows.",
            }
        )
    if gap_report.get("direction_specific_rows_ready"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "APPEND_V2_SOURCE_ROWS",
                "future_phase": "R216",
                "why": "At least one candidate has complete local v2 source schema for append-only paper rows.",
            }
        )
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "RUN_EVENT_OUTCOME_RESOLVER",
                "future_phase": "R214",
                "why": "Direction-specific source rows can be reviewed by the paper-only event outcome resolver.",
            }
        )
    if candidate_rows:
        recommendations.append(
            {
                "priority": "LOW",
                "recommended_action": "KEEP_CONTEXT_ONLY",
                "future_phase": "R216",
                "why": "R216 refreshes source schema only; it cannot promote betrayal or authorize live.",
            }
        )
    return recommendations


def classify_betrayal_source_emitter_refresh_status(
    *,
    source_candidate_rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
) -> str:
    if not source_candidate_rows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if gap_report.get("direction_specific_rows_ready"):
        return SOURCE_EMITTER_DIRECTION_SPECIFIC_PREVIEW_READY
    if gap_report.get("aggregate_rows_blocked"):
        return SOURCE_EMITTER_AGGREGATE_DECOMPOSITION_REQUIRED
    if any(row.get("missing_fields") for row in source_candidate_rows):
        return SOURCE_EMITTER_EXISTING_ROWS_INCOMPLETE
    return SOURCE_EMITTER_CONTRACT_READY


def append_betrayal_source_emitter_refresh_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_source_emitter_refresh_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "refresh_id": str(record.get("refresh_id") or f"r216_betrayal_source_emitter_refresh_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_SOURCE_EMITTER_REFRESH_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_refresh_requested": bool(record.get("record_refresh_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "refreshed_source_contract": dict(record.get("refreshed_source_contract") or {}),
            "source_candidate_rows": list(record.get("source_candidate_rows") or []),
            "direction_specific_source_preview": list(record.get("direction_specific_source_preview") or []),
            "aggregate_decomposition_requirements": dict(record.get("aggregate_decomposition_requirements") or {}),
            "source_emitter_gap_report": dict(record.get("source_emitter_gap_report") or {}),
            "source_emitter_recommendations": list(record.get("source_emitter_recommendations") or []),
            "source_emitter_status": record.get("source_emitter_status"),
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


def load_betrayal_source_emitter_refresh_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_source_emitter_refresh_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_betrayal_source_emitter_refresh_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    gap = latest.get("source_emitter_gap_report") if isinstance(latest.get("source_emitter_gap_report"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "source_emitter_status_counts": dict(
            sorted(Counter(str(record.get("source_emitter_status") or "UNKNOWN") for record in records).items())
        ),
        "last_refresh_id": latest.get("refresh_id") if isinstance(latest, Mapping) else None,
        "last_direction_specific_rows_ready": gap.get("direction_specific_rows_ready"),
        "last_aggregate_rows_blocked": gap.get("aggregate_rows_blocked"),
        "safety": dict(SAFETY),
    }


def betrayal_source_emitter_refresh_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_source_emitter_refresh_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _source_rows(
    direction_split_resolver: Mapping[str, Any],
    event_tracker: Mapping[str, Any],
    existing_betrayal_paper_signals: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for key in ("direction_split_resolution_rows",):
        value = direction_split_resolver.get(key)
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, Mapping))
    for key in ("event_tracker_records_preview", "event_seed_candidates"):
        value = event_tracker.get(key)
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, Mapping))
    rows.extend(row for row in existing_betrayal_paper_signals if isinstance(row, Mapping))
    return rows


def _best_source_row(rows: Sequence[Mapping[str, Any]], *, candidate: str, timeframe: str) -> dict[str, Any]:
    if not rows:
        return {"candidate": candidate, "timeframe": timeframe, "source": "missing"}
    resolved = [row for row in rows if _row_is_direction_specific(row)]
    if resolved:
        return dict(resolved[-1])
    partial = [row for row in rows if _existing_direction_split(row) == "partial"]
    if partial:
        return dict(partial[-1])
    return dict(rows[-1])


def _row_is_direction_specific(row: Mapping[str, Any]) -> bool:
    original = _normal_direction(row.get("original_direction"))
    inverse = _normal_direction(row.get("inverse_direction") or row.get("betrayal_direction"))
    return bool(
        original
        and inverse
        and inverse == _opposite_direction(original)
        and row.get("entry_mode")
        and _source_signal_id(row)
        and _signal_timestamp(row)
    )


def _missing_fields(row: Mapping[str, Any]) -> list[str]:
    missing = []
    original = _normal_direction(row.get("original_direction"))
    inverse = _normal_direction(row.get("inverse_direction") or row.get("betrayal_direction"))
    if not original:
        missing.append("original_direction")
    if not inverse or (original and inverse != _opposite_direction(original)):
        missing.append("inverse_direction")
    if not row.get("entry_mode"):
        missing.append("entry_mode")
    if not _source_signal_id(row):
        missing.append("source_identity")
    if not _signal_timestamp(row):
        missing.append("signal_timestamp")
    return missing


def _existing_direction_split(row: Mapping[str, Any]) -> str:
    context = str(row.get("direction_context") or "").lower()
    if _row_is_direction_specific(row) or row.get("direction_split_resolved") is True:
        return "resolved"
    if context == "aggregate_context_only" or str(row.get("candidate") or "").endswith("aggregate") and not row.get("original_direction"):
        return "aggregate_context_only"
    if context == "partial" or any((row.get("lane_key"), row.get("source_direction"), row.get("entry_mode"), _signal_timestamp(row))):
        return "partial"
    return "unknown"


def _candidate_source_status(
    *,
    can_emit_direction_specific_now: bool,
    aggregate_decomposition_required: bool,
    missing_fields: Sequence[str],
) -> str:
    if can_emit_direction_specific_now:
        return SOURCE_EMITTER_DIRECTION_SPECIFIC_PREVIEW_READY
    if aggregate_decomposition_required:
        return SOURCE_EMITTER_AGGREGATE_DECOMPOSITION_REQUIRED
    if missing_fields:
        return SOURCE_EMITTER_EXISTING_ROWS_INCOMPLETE
    return SOURCE_EMITTER_CONTRACT_READY


def _candidate_why(
    *,
    candidate: str,
    context: str,
    missing_fields: Sequence[str],
    lane_direction: str | None,
) -> str:
    if context == "resolved":
        return f"{candidate} has explicit original/inverse direction, entry mode, source identity, and timestamp for paper-only v2 preview."
    if context == "aggregate_context_only":
        return f"{candidate} remains aggregate context only and must be decomposed before event outcome resolving."
    if lane_direction:
        return (
            f"Lane key has {lane_direction}, but lane direction alone is not original/inverse proof; "
            f"missing {', '.join(missing_fields) if missing_fields else 'direction proof'}."
        )
    return f"{candidate} source schema is incomplete; missing {', '.join(missing_fields) if missing_fields else 'manual review'}."


def _recommended_next_operator_move(source_status: str, gap_report: Mapping[str, Any]) -> str:
    if source_status == SOURCE_EMITTER_DIRECTION_SPECIFIC_PREVIEW_READY:
        return "RUN_R214_BETRAYAL_EVENT_OUTCOME_RESOLVER"
    if gap_report.get("aggregate_rows_blocked"):
        return "RUN_R217_BETRAYAL_AGGREGATE_DECOMPOSITION"
    return "KEEP_WEEKEND_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(source_status: str, gap_report: Mapping[str, Any]) -> str:
    if source_status == SOURCE_EMITTER_DIRECTION_SPECIFIC_PREVIEW_READY:
        return "Wire R214 to consume only v2 source rows with schema_complete=true; keep paper-only."
    if gap_report.get("aggregate_rows_blocked"):
        return "Build R217 aggregate decomposition using local evidence only; do not fabricate original/inverse direction."
    return "Keep R216 contract as the v2 source schema and collect explicit local source rows before resolver work."


def _top_level_status(
    *,
    record_refresh: bool,
    confirmation_valid: bool,
    candidate_rows: Sequence[Mapping[str, Any]],
) -> str:
    if record_refresh and not confirmation_valid:
        return BETRAYAL_SOURCE_EMITTER_REFRESH_REJECTED
    if not candidate_rows:
        return BETRAYAL_SOURCE_EMITTER_REFRESH_BLOCKED
    if record_refresh and confirmation_valid:
        return BETRAYAL_SOURCE_EMITTER_REFRESH_RECORDED
    return BETRAYAL_SOURCE_EMITTER_REFRESH_READY


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


def _candidate_label(row: Mapping[str, Any]) -> str:
    candidate = row.get("candidate") or row.get("candidate_label")
    if candidate:
        text = str(candidate)
        return text if "aggregate" in text else f"{text.split()[0]} aggregate"
    timeframe = str(row.get("timeframe") or _timeframe_from_lane_key(row.get("lane_key")) or "unknown")
    return f"{timeframe} aggregate"


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


def _source_signal_id(row: Mapping[str, Any]) -> str | None:
    value = (
        row.get("source_signal_id")
        or row.get("source_identity")
        or row.get("signal_id")
        or row.get("emitted_signal_id")
        or row.get("betrayal_paper_signal_id")
        or row.get("source_capture_id")
        or row.get("capture_id")
        or row.get("candidate_id")
        or row.get("outcome_id")
    )
    return str(value) if value else None


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
    return str(value) if value else None


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


def _emitted_signal_id(
    *,
    candidate: str,
    source_signal_id: str | None,
    signal_timestamp: str | None,
    original_direction: str | None,
    inverse_direction: str | None,
    entry_mode: Any,
) -> str:
    stable = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "candidate": candidate,
            "source_signal_id": source_signal_id,
            "signal_timestamp": signal_timestamp,
            "original_direction": original_direction,
            "inverse_direction": inverse_direction,
            "entry_mode": entry_mode,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    import hashlib

    return f"betrayal_source_emitter_v2|{hashlib.sha256(stable.encode('utf-8')).hexdigest()[:24]}"


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


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return _sanitize(payload) if isinstance(payload, dict) else {}


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
