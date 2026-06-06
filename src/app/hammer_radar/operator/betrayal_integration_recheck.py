"""R209 betrayal integration recheck.

Paper-only audit composer for historical betrayal/inverse evidence and recent
matrix/readiness surfaces. It never calls Binance/network, creates payloads,
mutates env/config/lane/risk state, promotes origins/lanes, or authorizes live.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE

BETRAYAL_INTEGRATION_RECHECK_READY = "BETRAYAL_INTEGRATION_RECHECK_READY"
BETRAYAL_INTEGRATION_RECHECK_REJECTED = "BETRAYAL_INTEGRATION_RECHECK_REJECTED"
BETRAYAL_INTEGRATION_RECHECK_RECORDED = "BETRAYAL_INTEGRATION_RECHECK_RECORDED"
BETRAYAL_INTEGRATION_RECHECK_BLOCKED = "BETRAYAL_INTEGRATION_RECHECK_BLOCKED"
BETRAYAL_INTEGRATION_RECHECK_ERROR = "BETRAYAL_INTEGRATION_RECHECK_ERROR"

BETRAYAL_CONTEXT_AVAILABLE_NOT_INTEGRATED = "BETRAYAL_CONTEXT_AVAILABLE_NOT_INTEGRATED"
BETRAYAL_TRUE_INVERSE_VALIDATION_PENDING = "BETRAYAL_TRUE_INVERSE_VALIDATION_PENDING"
BETRAYAL_CAPTURE_LINKAGE_AVAILABLE = "BETRAYAL_CAPTURE_LINKAGE_AVAILABLE"
BETRAYAL_MATRIX_INTEGRATION_MISSING = "BETRAYAL_MATRIX_INTEGRATION_MISSING"
BETRAYAL_PAPER_ONLY_REVIEW_REQUIRED = "BETRAYAL_PAPER_ONLY_REVIEW_REQUIRED"
BETRAYAL_NOT_LIVE_AUTHORIZED = "BETRAYAL_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_INTEGRATION_RECHECK"
LEDGER_FILENAME = "betrayal_integration_recheck.ndjson"
CONFIRM_BETRAYAL_INTEGRATION_RECHECK_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL INTEGRATION RECHECK RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

PRIMARY_222M = {
    "label": "BETRAYAL_PRIMARY_CANDIDATE",
    "original_sample_count": 48,
    "original_win_rate_pct": 12.5,
    "naive_inverse_win_rate_pct": 87.5,
    "true_inverse_validation_required": True,
    "live_ready": False,
}
WATCHLIST_88M = {
    "label": "BETRAYAL_WATCHLIST",
    "original_sample_count": 90,
    "original_win_rate_pct": 36.67,
    "naive_inverse_win_rate_pct": 63.33,
    "true_inverse_validation_required": True,
    "live_ready": False,
}

DOC_PATHS = [
    "docs/hammer_radar/R80_BETRAYAL_STRATEGY_AUDIT.md",
    "docs/hammer_radar/R81_TRUE_INVERSE_PAPER_OUTCOME_VALIDATION.md",
    "docs/hammer_radar/R81_1_BETRAYAL_SHADOW_OUTCOME_RESOLVER.md",
    "docs/hammer_radar/R81_2_BETRAYAL_CANDLE_ARCHIVE_REPLAY_BRIDGE.md",
    "docs/hammer_radar/R81_3_SAFE_CANDLE_CAPTURE_BACKFILL_SOURCE.md",
    "docs/hammer_radar/R81_4_STRICT_BETRAYAL_RESOLVER_TIMESTAMP_ALIGNMENT.md",
    "docs/hammer_radar/R82_MARKOV_REGIME_GATE.md",
    "docs/hammer_radar/R83_MIRO_FISH_QUALITY_GATE.md",
    "docs/hammer_radar/R95_DUAL_LANE_CANDIDATE_WATCH_NORMAL_BETRAYAL.md",
    "docs/hammer_radar/R96_BETRAYAL_TRUE_PAPER_TRACKING_SCAFFOLD.md",
    "docs/hammer_radar/R100_BETRAYAL_SOURCE_SIGNAL_EMITTER.md",
    "docs/hammer_radar/live_readiness/R208A_WEEKEND_PAPER_FISHERMAN_SUPERVISOR.md",
    "docs/hammer_radar/live_readiness/R203_ANCHOR_SIGNAL_CONFLUENCE_MATRIX.md",
    "docs/hammer_radar/live_readiness/R205_PATTERN_LANE_MATRIX_REVIEW.md",
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
    *DOC_PATHS,
    "logs/hammer_radar_forward/weekend_paper_fisherman_supervisor.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_expansion.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_heartbeats.ndjson",
    "logs/hammer_radar_forward/anchor_signal_confluence_matrix.ndjson",
    "logs/hammer_radar_forward/pattern_lane_matrix_review.ndjson",
    "logs/hammer_radar_forward/tiny_live_readiness_gap_recheck.ndjson",
    "logs/hammer_radar_forward/betrayal_*.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_integration_recheck(
    *,
    log_dir: str | Path | None = None,
    record_recheck: bool = False,
    confirm_betrayal_integration_recheck: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_integration_recheck == CONFIRM_BETRAYAL_INTEGRATION_RECHECK_RECORDING_PHRASE
    )
    try:
        docs = load_betrayal_docs_context()
        audit_ledgers = load_betrayal_audit_ledgers(log_dir=resolved_log_dir)
        true_inverse = build_true_inverse_validation_summary(
            validation_status=load_true_inverse_validation_status(log_dir=resolved_log_dir),
            shadow_status=load_betrayal_shadow_outcome_status(log_dir=resolved_log_dir),
        )
        weekend = load_latest_weekend_fisherman_betrayal_summary(log_dir=resolved_log_dir)
        capture = build_betrayal_capture_linkage_summary(
            latest_capture=load_latest_full_spectrum_222m_capture(log_dir=resolved_log_dir),
            weekend_betrayal_summary=weekend,
        )
        current_matrix = load_current_matrix_integration_status(log_dir=resolved_log_dir)
        gap_report = build_betrayal_current_stack_gap_report(
            current_matrix_status=current_matrix,
            weekend_betrayal_summary=weekend,
        )
        candidate_summary = build_betrayal_candidate_summary(docs_context=docs, audit_ledgers=audit_ledgers)
        recommendations = build_betrayal_integration_recommendations(
            true_inverse_summary=true_inverse,
            capture_linkage=capture,
            gap_report=gap_report,
        )
        betrayal_status = classify_betrayal_integration_status(
            true_inverse_summary=true_inverse,
            capture_linkage=capture,
            gap_report=gap_report,
        )
        status = _top_level_status(
            record_recheck=record_recheck,
            confirmation_valid=confirmation_valid,
            gap_report=gap_report,
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "recheck_recorded": False,
            "recheck_id": None,
            "record_recheck_requested": bool(record_recheck),
            "confirmation_valid": bool(confirmation_valid),
            "betrayal_scope": {
                "primary_candidate": "222m aggregate",
                "watchlist_candidates": ["88m aggregate"] + (["55m aggregate"] if docs.get("optional_55m_found") else []),
                "paper_only": True,
                "live_authorized": False,
            },
            "betrayal_candidate_summary": candidate_summary,
            "true_inverse_validation_summary": true_inverse,
            "betrayal_capture_linkage": capture,
            "current_stack_gap_report": gap_report,
            "betrayal_integration_recommendations": recommendations,
            "betrayal_status": betrayal_status,
            "recommended_next_operator_move": _recommended_next_operator_move(
                true_inverse_summary=true_inverse,
                gap_report=gap_report,
            ),
            "recommended_next_engineering_move": _recommended_next_engineering_move(
                true_inverse_summary=true_inverse,
                capture_linkage=capture,
                gap_report=gap_report,
            ),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "input_status": {
                "docs_context": docs,
                "betrayal_audit_ledgers": audit_ledgers,
                "weekend_betrayal_summary": weekend,
                "current_matrix_status": current_matrix,
            },
        }
        if record_recheck and confirmation_valid:
            record = append_betrayal_integration_recheck_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_INTEGRATION_RECHECK_RECORDED
            payload["recheck_recorded"] = True
            payload["recheck_id"] = record["recheck_id"]
            payload["ledger_path"] = str(betrayal_integration_recheck_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_INTEGRATION_RECHECK_ERROR,
                "generated_at": generated_at.isoformat(),
                "recheck_recorded": False,
                "recheck_id": None,
                "record_recheck_requested": bool(record_recheck),
                "confirmation_valid": bool(confirmation_valid),
                "error": str(exc),
                "betrayal_scope": {
                    "primary_candidate": "222m aggregate",
                    "watchlist_candidates": ["88m aggregate"],
                    "paper_only": True,
                    "live_authorized": False,
                },
                "betrayal_candidate_summary": build_betrayal_candidate_summary(),
                "true_inverse_validation_summary": {
                    "validation_records_found": False,
                    "resolved_true_inverse_samples": 0,
                    "validation_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                    "validation_required_before_promotion": True,
                },
                "betrayal_capture_linkage": _empty_capture_linkage(),
                "current_stack_gap_report": _empty_gap_report(),
                "betrayal_integration_recommendations": [],
                "betrayal_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "RUN_R210_BETRAYAL_TRUE_INVERSE_REFRESH",
                "recommended_next_engineering_move": "Inspect local R80-R100 and R198-R208A ledgers before changing any matrix code.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_betrayal_docs_context(*, repo_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    docs: dict[str, Any] = {"docs_checked": [], "docs_found": [], "docs_missing": [], "optional_55m_found": False}
    for rel in DOC_PATHS:
        path = root / rel
        docs["docs_checked"].append(rel)
        if not path.exists():
            docs["docs_missing"].append(rel)
            continue
        docs["docs_found"].append(rel)
        text = path.read_text(encoding="utf-8", errors="replace")
        if "55m" in text and "BETRAYAL" in text.upper():
            docs["optional_55m_found"] = True
    docs["r80_facts"] = {
        "222m": dict(PRIMARY_222M),
        "88m": dict(WATCHLIST_88M),
    }
    docs["true_inverse_validation_required"] = True
    docs["regime_support_required"] = True
    docs["miro_fish_quality_required"] = True
    docs["live_ready"] = False
    return _sanitize(docs)


def load_betrayal_audit_ledgers(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    paths = sorted(resolved_log_dir.glob("betrayal_*.ndjson"))
    counts: dict[str, int] = {}
    latest_by_file: dict[str, str | None] = {}
    for path in paths:
        records = _read_recent(path, limit=1)
        counts[path.name] = _count_ndjson(path)
        latest_by_file[path.name] = _record_time(records[0]) if records else None
    return {
        "ledger_files_found": [path.name for path in paths],
        "ledger_record_counts": counts,
        "latest_record_at_by_file": latest_by_file,
        "true_paper_outcomes_found": "betrayal_true_paper_outcomes.ndjson" in counts,
        "shadow_outcomes_found": "betrayal_shadow_outcomes.ndjson" in counts,
        "shadow_resolutions_found": "betrayal_shadow_resolutions.ndjson" in counts,
        "safety": dict(SAFETY),
    }


def load_true_inverse_validation_status(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    true_paper = _read_recent(resolved_log_dir / "betrayal_true_paper_outcomes.ndjson", limit=500)
    shadow_resolutions = _read_recent(resolved_log_dir / "betrayal_shadow_resolutions.ndjson", limit=500)
    resolved_true = [
        record
        for record in [*true_paper, *shadow_resolutions]
        if str(record.get("timeframe") or "").lower() in {"222m", "88m", "55m"}
        and str(record.get("shadow_status") or record.get("outcome") or record.get("status") or "").lower()
        not in {"", "open", "unresolved", "no_data", "pending"}
    ]
    return {
        "validation_records_found": bool(true_paper or shadow_resolutions),
        "true_paper_outcome_records": len(true_paper),
        "shadow_resolution_records": len(shadow_resolutions),
        "resolved_true_inverse_samples": len(resolved_true),
        "validation_status": "TRUE_INVERSE_VALIDATION_PENDING" if len(resolved_true) < 30 else "TRUE_INVERSE_REVIEW_READY",
        "validation_required_before_promotion": True,
        "live_ready": False,
    }


def load_betrayal_shadow_outcome_status(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = _read_recent(resolved_log_dir / "betrayal_shadow_outcomes.ndjson", limit=1000)
    resolved = [
        record
        for record in records
        if str(record.get("shadow_status") or record.get("status") or "").upper()
        in {"SHADOW_WIN", "SHADOW_LOSS", "SHADOW_BREAKEVEN", "WIN", "LOSS", "BREAKEVEN"}
    ]
    return {
        "shadow_records_found": bool(records),
        "shadow_record_count": len(records),
        "resolved_shadow_records": len(resolved),
        "latest_shadow_record_at": _record_time(records[0]) if records else None,
    }


def load_latest_weekend_fisherman_betrayal_summary(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    record = _latest_record(get_log_dir(log_dir, use_env=True) / "weekend_paper_fisherman_supervisor.ndjson")
    summary = record.get("betrayal_watch_summary") if isinstance(record.get("betrayal_watch_summary"), dict) else {}
    return _sanitize(
        {
            "weekend_supervisor_found": bool(record),
            "weekend_supervisor_at": _record_time(record) if record else None,
            "betrayal_context_included": bool(summary.get("betrayal_context_included")),
            "betrayal_integrated_into_current_matrix": bool(summary.get("betrayal_integrated_into_current_matrix")),
            "latest_222m_capture_found": bool(summary.get("latest_222m_capture_found")),
            "latest_222m_capture_lane": summary.get("latest_222m_capture_lane"),
            "latest_222m_capture_at": summary.get("latest_222m_capture_at"),
            "betrayal_live_ready": bool(summary.get("betrayal_live_ready")),
            "true_inverse_validation_required": bool(summary.get("true_inverse_validation_required", True)),
        }
    )


def load_latest_full_spectrum_222m_capture(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    for path in (
        resolved_log_dir / "full_spectrum_harvester_heartbeats.ndjson",
        resolved_log_dir / "full_spectrum_harvester_expansion.ndjson",
    ):
        for record in _read_recent(path, limit=200):
            found = _extract_222m_capture(record)
            if found:
                return found
    return {}


def load_current_matrix_integration_status(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    pattern = _latest_record(resolved_log_dir / "pattern_lane_matrix_review.ndjson")
    anchor = _latest_record(resolved_log_dir / "anchor_signal_confluence_matrix.ndjson")
    tiny = _latest_record(resolved_log_dir / "tiny_live_readiness_gap_recheck.ndjson")
    return {
        "pattern_lane_matrix_found": bool(pattern),
        "pattern_lane_matrix_at": _record_time(pattern) if pattern else None,
        "anchor_confluence_matrix_found": bool(anchor),
        "anchor_confluence_matrix_at": _record_time(anchor) if anchor else None,
        "tiny_live_readiness_found": bool(tiny),
        "tiny_live_readiness_at": _record_time(tiny) if tiny else None,
        "included_in_pattern_lane_matrix": _contains_betrayal_matrix_context(pattern),
        "included_in_anchor_confluence_matrix": _contains_betrayal_matrix_context(anchor),
        "included_in_tiny_live_readiness": _contains_betrayal_matrix_context(tiny),
    }


def build_betrayal_candidate_summary(
    *,
    docs_context: Mapping[str, Any] | None = None,
    audit_ledgers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {"222m": dict(PRIMARY_222M), "88m": dict(WATCHLIST_88M)}
    if docs_context and docs_context.get("optional_55m_found"):
        summary["55m"] = {
            "label": "BETRAYAL_OPTIONAL_WATCHLIST_FOUND_IN_HISTORY",
            "original_sample_count": None,
            "original_win_rate_pct": None,
            "naive_inverse_win_rate_pct": None,
            "true_inverse_validation_required": True,
            "live_ready": False,
        }
    return summary


def build_true_inverse_validation_summary(
    *,
    validation_status: Mapping[str, Any],
    shadow_status: Mapping[str, Any],
) -> dict[str, Any]:
    resolved = int(validation_status.get("resolved_true_inverse_samples") or 0)
    return {
        "validation_records_found": bool(
            validation_status.get("validation_records_found") or shadow_status.get("shadow_records_found")
        ),
        "resolved_true_inverse_samples": resolved,
        "validation_status": str(validation_status.get("validation_status") or "TRUE_INVERSE_VALIDATION_PENDING"),
        "validation_required_before_promotion": True,
        "shadow_records_found": bool(shadow_status.get("shadow_records_found")),
        "shadow_record_count": int(shadow_status.get("shadow_record_count") or 0),
        "resolved_shadow_records": int(shadow_status.get("resolved_shadow_records") or 0),
        "naive_inverse_is_validated_edge": False,
        "live_ready": False,
    }


def build_betrayal_capture_linkage_summary(
    *,
    latest_capture: Mapping[str, Any],
    weekend_betrayal_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    fallback = weekend_betrayal_summary or {}
    lane = latest_capture.get("lane_key") or fallback.get("latest_222m_capture_lane")
    captured_at = latest_capture.get("captured_at") or fallback.get("latest_222m_capture_at")
    direction = _direction_from_lane(str(lane or ""))
    found = bool(lane and "|222m|" in str(lane).lower())
    return {
        "latest_222m_capture_found": found,
        "latest_222m_capture_lane": lane,
        "latest_222m_capture_at": captured_at,
        "capture_matches_primary_candidate_timeframe": found,
        "capture_direction_context": direction or ("aggregate_context_only" if found else "unknown"),
        "can_use_capture_as_true_inverse_sample_now": False,
        "why": (
            "A 222m full-spectrum capture links to the R80 aggregate betrayal timeframe, but it is only a raw paper capture; "
            "it needs event matching and true inverse outcome resolution before it can count as validation."
            if found
            else "No current local 222m full-spectrum capture was found in the inspected ledgers."
        ),
    }


def build_betrayal_current_stack_gap_report(
    *,
    current_matrix_status: Mapping[str, Any],
    weekend_betrayal_summary: Mapping[str, Any],
) -> dict[str, Any]:
    included_weekend = bool(weekend_betrayal_summary.get("betrayal_context_included"))
    included_pattern = bool(current_matrix_status.get("included_in_pattern_lane_matrix"))
    included_anchor = bool(current_matrix_status.get("included_in_anchor_confluence_matrix"))
    included_tiny = bool(current_matrix_status.get("included_in_tiny_live_readiness"))
    missing = not (included_pattern and included_anchor and included_tiny)
    return {
        "included_in_pattern_lane_matrix": included_pattern,
        "included_in_anchor_confluence_matrix": included_anchor,
        "included_in_tiny_live_readiness": included_tiny,
        "included_in_weekend_supervisor": included_weekend,
        "matrix_integration_missing": missing,
        "reason_if_missing": (
            "Betrayal context is present in R208A/weekend supervisor but is not an explicit betrayal-aware row in R203/R205/R206."
            if missing
            else "Betrayal context appears in all inspected current stack surfaces."
        ),
    }


def build_betrayal_integration_recommendations(
    *,
    true_inverse_summary: Mapping[str, Any],
    capture_linkage: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations = [
        {
            "priority": "HIGH",
            "recommended_action": "KEEP_AUDIT_ONLY",
            "future_phase": "R209",
            "why": "R80 naive inverse math is not true inverse paper validation and cannot imply live readiness.",
        },
        {
            "priority": "HIGH",
            "recommended_action": "BUILD_TRUE_INVERSE_EVENT_MATCHER",
            "future_phase": "R210",
            "why": "222m/88m betrayal candidates need local event-level matching and resolved true inverse outcomes before any promotion review.",
        },
    ]
    if capture_linkage.get("latest_222m_capture_found"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "COLLECT_MORE_BETRAYAL_PAPER",
                "future_phase": "R210",
                "why": "The latest 222m capture can seed paper matching, but cannot be counted as a validated inverse sample now.",
            }
        )
    if gap_report.get("matrix_integration_missing"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "ADD_PAPER_MATRIX_CONTEXT",
                "future_phase": "R211",
                "why": "Add a betrayal-aware paper matrix row after true inverse refresh, without scoring promotion or live authorization.",
            }
        )
    recommendations.append(
        {
            "priority": "LOW",
            "recommended_action": "DO_NOT_PROMOTE",
            "future_phase": "R209",
            "why": "Betrayal remains not live-ready, not promoted, and blocked from live authorization.",
        }
    )
    return recommendations


def classify_betrayal_integration_status(
    *,
    true_inverse_summary: Mapping[str, Any],
    capture_linkage: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> str:
    if gap_report.get("matrix_integration_missing"):
        return BETRAYAL_MATRIX_INTEGRATION_MISSING
    if capture_linkage.get("latest_222m_capture_found"):
        return BETRAYAL_CAPTURE_LINKAGE_AVAILABLE
    if true_inverse_summary.get("validation_required_before_promotion"):
        return BETRAYAL_TRUE_INVERSE_VALIDATION_PENDING
    return BETRAYAL_CONTEXT_AVAILABLE_NOT_INTEGRATED


def append_betrayal_integration_recheck_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_integration_recheck_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            **dict(record),
            "event_type": EVENT_TYPE,
            "recheck_id": str(record.get("recheck_id") or f"r209_betrayal_integration_recheck_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "recheck_recorded": True,
            "safety": dict(SAFETY),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_betrayal_integration_recheck_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_integration_recheck_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return [_sanitize(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_betrayal_integration_recheck_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "betrayal_status_counts": dict(
            sorted(Counter(str(record.get("betrayal_status") or "UNKNOWN") for record in records).items())
        ),
        "last_recheck_id": records[0].get("recheck_id") if records else None,
        "safety": dict(SAFETY),
    }


def betrayal_integration_recheck_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_integration_recheck_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _top_level_status(*, record_recheck: bool, confirmation_valid: bool, gap_report: Mapping[str, Any]) -> str:
    if record_recheck and not confirmation_valid:
        return BETRAYAL_INTEGRATION_RECHECK_REJECTED
    if record_recheck and confirmation_valid:
        return BETRAYAL_INTEGRATION_RECHECK_RECORDED
    if gap_report.get("matrix_integration_missing"):
        return BETRAYAL_INTEGRATION_RECHECK_BLOCKED
    return BETRAYAL_INTEGRATION_RECHECK_READY


def _recommended_next_operator_move(
    *,
    true_inverse_summary: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> str:
    if true_inverse_summary.get("validation_required_before_promotion"):
        return "RUN_R210_BETRAYAL_TRUE_INVERSE_REFRESH"
    if gap_report.get("matrix_integration_missing"):
        return "RUN_R207_EVENT_LEVEL_CONFLUENCE_MATCHER"
    return "KEEP_WEEKEND_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(
    *,
    true_inverse_summary: Mapping[str, Any],
    capture_linkage: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> str:
    if true_inverse_summary.get("validation_required_before_promotion"):
        return "Build R210 local true-inverse refresh before adding betrayal to paper matrices; do not promote or authorize live."
    if capture_linkage.get("latest_222m_capture_found") and gap_report.get("matrix_integration_missing"):
        return "Add betrayal-aware paper context only after event-level linkage and true inverse validation refresh."
    return "Keep betrayal context audit-only and continue local paper collection."


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


def _empty_capture_linkage() -> dict[str, Any]:
    return {
        "latest_222m_capture_found": False,
        "latest_222m_capture_lane": None,
        "latest_222m_capture_at": None,
        "capture_matches_primary_candidate_timeframe": False,
        "capture_direction_context": "unknown",
        "can_use_capture_as_true_inverse_sample_now": False,
        "why": "No current local 222m full-spectrum capture was found in the inspected ledgers.",
    }


def _empty_gap_report() -> dict[str, Any]:
    return {
        "included_in_pattern_lane_matrix": False,
        "included_in_anchor_confluence_matrix": False,
        "included_in_tiny_live_readiness": False,
        "included_in_weekend_supervisor": False,
        "matrix_integration_missing": True,
        "reason_if_missing": "Betrayal integration status could not be composed from local ledgers.",
    }


def _latest_record(path: Path) -> dict[str, Any]:
    records = _read_recent(path, limit=1)
    return records[0] if records else {}


def _read_recent(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]
    except Exception:
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
            if line.strip():
                records.append(_sanitize(json.loads(line)))
        return list(reversed(records))


def _count_ndjson(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())


def _extract_222m_capture(record: Mapping[str, Any]) -> dict[str, Any]:
    captured_at = _record_time(record)
    for lane in record.get("captured_lanes") or []:
        lane_text = str(lane)
        if "|222m|" in lane_text.lower():
            return {"lane_key": lane_text, "captured_at": captured_at}
    capture_summary = record.get("capture_summary") if isinstance(record.get("capture_summary"), dict) else {}
    for lane in capture_summary.get("captured_lanes") or []:
        lane_text = str(lane)
        if "|222m|" in lane_text.lower():
            return {"lane_key": lane_text, "captured_at": captured_at}
    for candidate in capture_summary.get("captured_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        lane_text = str(candidate.get("lane_key") or "")
        if "|222m|" in lane_text.lower():
            return {"lane_key": lane_text, "captured_at": candidate.get("timestamp") or captured_at}
    for examples in (capture_summary.get("candidate_examples_by_lane") or {}).values():
        for candidate in examples or []:
            if not isinstance(candidate, dict):
                continue
            lane_text = str(candidate.get("lane_key") or "")
            if "|222m|" in lane_text.lower() and candidate.get("capture_allowed"):
                return {"lane_key": lane_text, "captured_at": candidate.get("timestamp") or captured_at}
    return {}


def _record_time(record: Mapping[str, Any]) -> str | None:
    return (
        record.get("recorded_at_utc")
        or record.get("generated_at")
        or record.get("captured_at")
        or record.get("created_at")
        or record.get("timestamp")
    )


def _direction_from_lane(lane: str) -> str | None:
    parts = lane.split("|")
    if len(parts) >= 3 and parts[2].lower() in {"long", "short"}:
        return parts[2].lower()
    return None


def _contains_betrayal_matrix_context(record: Mapping[str, Any]) -> bool:
    if not record:
        return False
    text = json.dumps(_sanitize(dict(record)), sort_keys=True).lower()
    return "betrayal" in text or "true_inverse" in text


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_sanitize(child) for child in value]
    if isinstance(value, tuple):
        return [_sanitize(child) for child in value]
    if isinstance(value, Path):
        return str(value)
    return value
