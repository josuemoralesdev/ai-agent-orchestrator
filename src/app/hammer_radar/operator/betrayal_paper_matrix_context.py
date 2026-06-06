"""R211 betrayal paper matrix context.

Paper-only composer that adds betrayal/inverse evidence as matrix context
without changing configs, lane modes, risk contracts, promotions, or live gates.
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
from src.app.hammer_radar.operator.betrayal_integration_recheck import PRIMARY_222M, WATCHLIST_88M
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE

BETRAYAL_PAPER_MATRIX_CONTEXT_READY = "BETRAYAL_PAPER_MATRIX_CONTEXT_READY"
BETRAYAL_PAPER_MATRIX_CONTEXT_REJECTED = "BETRAYAL_PAPER_MATRIX_CONTEXT_REJECTED"
BETRAYAL_PAPER_MATRIX_CONTEXT_RECORDED = "BETRAYAL_PAPER_MATRIX_CONTEXT_RECORDED"
BETRAYAL_PAPER_MATRIX_CONTEXT_BLOCKED = "BETRAYAL_PAPER_MATRIX_CONTEXT_BLOCKED"
BETRAYAL_PAPER_MATRIX_CONTEXT_ERROR = "BETRAYAL_PAPER_MATRIX_CONTEXT_ERROR"

BETRAYAL_CONTEXT_ADDED_PAPER_ONLY = "BETRAYAL_CONTEXT_ADDED_PAPER_ONLY"
BETRAYAL_CONTEXT_BLOCKED_PENDING_EVENT_TRACKER = "BETRAYAL_CONTEXT_BLOCKED_PENDING_EVENT_TRACKER"
BETRAYAL_CONTEXT_NEEDS_MORE_TRUE_INVERSE_SAMPLES = "BETRAYAL_CONTEXT_NEEDS_MORE_TRUE_INVERSE_SAMPLES"
BETRAYAL_CONTEXT_NOT_LIVE_AUTHORIZED = "BETRAYAL_CONTEXT_NOT_LIVE_AUTHORIZED"
BETRAYAL_MATRIX_REVIEW_READY_PAPER_ONLY = "BETRAYAL_MATRIX_REVIEW_READY_PAPER_ONLY"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_PAPER_MATRIX_CONTEXT"
LEDGER_FILENAME = "betrayal_paper_matrix_context.ndjson"
CONFIRM_BETRAYAL_PAPER_MATRIX_CONTEXT_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL PAPER MATRIX CONTEXT RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

TARGET_CANDIDATES = ("222m", "88m", "55m")
NORMAL_REFERENCE_FALLBACKS = (
    {"name": "8m short + hammer_wick_reversal", "score": 84, "paper_only": True},
    {"name": "8m short + bearish_engulfing", "score": 82, "paper_only": True},
    {"name": "8m short + three_black_crows", "score": 68, "paper_only": True},
)

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
    "logs/hammer_radar_forward/betrayal_true_inverse_refresh.ndjson",
    "logs/hammer_radar_forward/betrayal_integration_recheck.ndjson",
    "logs/hammer_radar_forward/pattern_lane_matrix_review.ndjson",
    "logs/hammer_radar_forward/anchor_signal_confluence_matrix.ndjson",
    "logs/hammer_radar_forward/tiny_live_readiness_gap_recheck.ndjson",
    "logs/hammer_radar_forward/weekend_paper_fisherman_supervisor.ndjson",
    "logs/hammer_radar_forward/full_spectrum_harvester_expansion.ndjson",
    "logs/hammer_radar_forward/markov_regime_gate.ndjson",
    "logs/hammer_radar_forward/miro_fish_quality_gate.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_paper_matrix_context(
    *,
    log_dir: str | Path | None = None,
    record_matrix: bool = False,
    confirm_betrayal_paper_matrix_context: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_paper_matrix_context == CONFIRM_BETRAYAL_PAPER_MATRIX_CONTEXT_RECORDING_PHRASE
    )
    try:
        true_inverse = load_latest_betrayal_true_inverse_refresh(log_dir=resolved_log_dir)
        integration = load_latest_betrayal_integration_recheck(log_dir=resolved_log_dir)
        pattern = load_latest_pattern_lane_matrix_review(log_dir=resolved_log_dir)
        anchor = load_latest_anchor_signal_confluence_matrix(log_dir=resolved_log_dir)
        tiny = load_latest_tiny_live_readiness_gap(log_dir=resolved_log_dir)
        weekend = _latest_record(resolved_log_dir / "weekend_paper_fisherman_supervisor.ndjson")
        full_spectrum = _latest_record(resolved_log_dir / "full_spectrum_harvester_expansion.ndjson")
        regime = _latest_record(resolved_log_dir / "markov_regime_gate.ndjson")
        miro = _latest_record(resolved_log_dir / "miro_fish_quality_gate.ndjson")
        rows = build_betrayal_context_rows(
            betrayal_true_inverse_refresh=true_inverse,
            betrayal_integration_recheck=integration,
            pattern_lane_matrix=pattern,
            anchor_confluence=anchor,
            tiny_live_readiness=tiny,
            regime_gate=regime,
            miro_fish_gate=miro,
        )
        comparison = build_betrayal_vs_normal_comparison(
            betrayal_context_rows=rows,
            pattern_lane_matrix=pattern,
            anchor_confluence=anchor,
        )
        gap_report = build_betrayal_matrix_gap_report(
            rows=rows,
            betrayal_integration_recheck=integration,
            pattern_lane_matrix=pattern,
            anchor_confluence=anchor,
            tiny_live_readiness=tiny,
            regime_gate=regime,
            miro_fish_gate=miro,
        )
        recommendations = build_betrayal_context_recommendations(gap_report=gap_report, rows=rows)
        matrix_status = classify_betrayal_paper_matrix_context_status(rows=rows, gap_report=gap_report)
        status = _top_level_status(
            record_matrix=record_matrix,
            confirmation_valid=confirmation_valid,
            has_rows=bool(rows),
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "matrix_recorded": False,
            "matrix_id": None,
            "record_matrix_requested": bool(record_matrix),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "betrayal_candidates": ["222m aggregate", "88m aggregate", "55m aggregate_if_available"],
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "betrayal_true_inverse_refresh_found": bool(true_inverse),
                "betrayal_integration_recheck_found": bool(integration),
                "pattern_lane_matrix_found": bool(pattern),
                "anchor_confluence_found": bool(anchor),
                "tiny_live_readiness_found": bool(tiny),
                "weekend_fisherman_found": bool(weekend),
                "full_spectrum_harvester_found": bool(full_spectrum),
            },
            "betrayal_context_rows": rows,
            "betrayal_vs_normal_comparison": comparison,
            "betrayal_matrix_gap_report": gap_report,
            "betrayal_context_recommendations": recommendations,
            "betrayal_matrix_status": matrix_status,
            "recommended_next_operator_move": _recommended_next_operator_move(gap_report),
            "recommended_next_engineering_move": _recommended_next_engineering_move(gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_matrix and confirmation_valid and rows:
            record = append_betrayal_paper_matrix_context_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_PAPER_MATRIX_CONTEXT_RECORDED
            payload["matrix_recorded"] = True
            payload["matrix_id"] = record["matrix_id"]
            payload["ledger_path"] = str(betrayal_paper_matrix_context_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_PAPER_MATRIX_CONTEXT_ERROR,
                "generated_at": generated_at.isoformat(),
                "matrix_recorded": False,
                "matrix_id": None,
                "record_matrix_requested": bool(record_matrix),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {
                    "betrayal_candidates": ["222m aggregate", "88m aggregate", "55m aggregate_if_available"],
                    "paper_only": True,
                    "live_authorized": False,
                },
                "input_summary": {},
                "betrayal_context_rows": [],
                "betrayal_vs_normal_comparison": build_betrayal_vs_normal_comparison(betrayal_context_rows=[]),
                "betrayal_matrix_gap_report": _empty_gap_report(),
                "betrayal_context_recommendations": [],
                "betrayal_matrix_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "RUN_R212_BETRAYAL_EVENT_TRACKER",
                "recommended_next_engineering_move": "Fix R211 context composer error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
            }
        )


def load_latest_betrayal_true_inverse_refresh(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_true_inverse_refresh.ndjson")


def load_latest_betrayal_integration_recheck(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_integration_recheck.ndjson")


def load_latest_pattern_lane_matrix_review(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "pattern_lane_matrix_review.ndjson")


def load_latest_anchor_signal_confluence_matrix(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "anchor_signal_confluence_matrix.ndjson")


def load_latest_tiny_live_readiness_gap(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "tiny_live_readiness_gap_recheck.ndjson")


def build_betrayal_context_rows(
    *,
    betrayal_true_inverse_refresh: Mapping[str, Any],
    betrayal_integration_recheck: Mapping[str, Any],
    pattern_lane_matrix: Mapping[str, Any],
    anchor_confluence: Mapping[str, Any],
    tiny_live_readiness: Mapping[str, Any],
    regime_gate: Mapping[str, Any] | None = None,
    miro_fish_gate: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    refresh_summary = betrayal_true_inverse_refresh.get("candidate_true_inverse_summary") or {}
    integration_summary = betrayal_integration_recheck.get("betrayal_candidate_summary") or {}
    rows = []
    for timeframe in TARGET_CANDIDATES:
        refresh = refresh_summary.get(timeframe)
        if not isinstance(refresh, Mapping):
            continue
        resolved = _to_int(refresh.get("resolved_true_inverse_samples"))
        if timeframe == "55m" and resolved <= 0:
            continue
        metadata = dict(integration_summary.get(timeframe) or _candidate_fallback(timeframe))
        row = {
            "candidate": f"{timeframe} aggregate",
            "label": refresh.get("label") or metadata.get("label"),
            "timeframe": timeframe,
            "original_win_rate_pct": _to_float(refresh.get("original_win_rate_pct", metadata.get("original_win_rate_pct"))),
            "naive_inverse_win_rate_pct": _to_float(
                refresh.get("naive_inverse_win_rate_pct", metadata.get("naive_inverse_win_rate_pct"))
            ),
            "resolved_true_inverse_samples": resolved,
            "shadow_outcome_count": _to_int(refresh.get("shadow_outcome_count")),
            "unresolved_shadow_samples": _to_int(refresh.get("unresolved_shadow_samples")),
            "validation_status": str(refresh.get("validation_status") or "UNKNOWN"),
            "live_ready": False,
            "promotion_allowed": False,
            "paper_only": True,
            "live_authorized": False,
            "lane_mode_eligible": False,
            "matrix_integration_status": _matrix_integration_status(betrayal_integration_recheck),
            "regime_support_found": bool(regime_gate),
            "miro_fish_support_found": bool(miro_fish_gate),
        }
        scored = score_betrayal_context_row(
            row,
            pattern_lane_matrix=pattern_lane_matrix,
            anchor_confluence=anchor_confluence,
            tiny_live_readiness=tiny_live_readiness,
        )
        rows.append(scored)
    return sorted(rows, key=lambda item: item["context_score"], reverse=True)


def score_betrayal_context_row(
    row: Mapping[str, Any],
    *,
    pattern_lane_matrix: Mapping[str, Any] | None = None,
    anchor_confluence: Mapping[str, Any] | None = None,
    tiny_live_readiness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = _to_int(row.get("resolved_true_inverse_samples"))
    shadow_count = _to_int(row.get("shadow_outcome_count"))
    unresolved = _to_int(row.get("unresolved_shadow_samples"))
    original_win_rate = _to_float(row.get("original_win_rate_pct"))
    naive_inverse = _to_float(row.get("naive_inverse_win_rate_pct"))
    validation_status = str(row.get("validation_status") or "")
    timeframe = str(row.get("timeframe") or "")
    warnings = [
        "paper_context_only",
        "not_live_ready",
        "not_promoted",
        "not_lane_mode_eligible",
        "event_tracker_missing",
        "aggregate_direction_only",
        "not_included_in_current_live_readiness",
    ]
    if unresolved:
        warnings.append("unresolved_shadow_samples")
    if not row.get("regime_support_found"):
        warnings.append("regime_support_missing_or_pending")
    if not row.get("miro_fish_support_found"):
        warnings.append("miro_fish_support_missing_or_pending")
    sample_depth = min(resolved / 40.0, 1.0) * 25.0
    validation = 20.0 if validation_status == "TRUE_INVERSE_VALIDATION_REFRESHED" else 0.0
    inverse_strength = ((100.0 - original_win_rate) / 100.0 * 15.0) if original_win_rate is not None else 6.0
    if naive_inverse is not None:
        inverse_strength = max(inverse_strength, naive_inverse / 100.0 * 15.0)
    coverage = _coverage_points(timeframe, pattern_lane_matrix or {}, anchor_confluence or {})
    unresolved_points = (1.0 - min(unresolved / max(shadow_count, 1), 1.0)) * 10.0
    regime_miro = (5.0 if row.get("regime_support_found") else 0.0) + (5.0 if row.get("miro_fish_support_found") else 0.0)
    integration = _integration_points(pattern_lane_matrix or {}, anchor_confluence or {}, tiny_live_readiness or {})
    penalty = 0.0
    penalty += 8.0
    penalty += min(unresolved, 20) * 0.35
    if not row.get("regime_support_found"):
        penalty += 4.0
    if not row.get("miro_fish_support_found"):
        penalty += 4.0
    penalty += 3.0
    penalty += 5.0
    score = round(max(0.0, min(100.0, sample_depth + validation + inverse_strength + coverage + unresolved_points + regime_miro + integration - penalty)), 2)
    readiness = (
        BETRAYAL_CONTEXT_ADDED_PAPER_ONLY
        if resolved >= 15 and validation_status == "TRUE_INVERSE_VALIDATION_REFRESHED"
        else BETRAYAL_CONTEXT_NEEDS_MORE_TRUE_INVERSE_SAMPLES
    )
    return {
        **dict(row),
        "context_score": score,
        "context_readiness": readiness,
        "risk_warnings": sorted(set(warnings)),
        "why": (
            f"{row.get('candidate')} has {resolved} refreshed true-inverse sample(s), {unresolved} unresolved "
            "shadow sample(s), and is added as paper matrix context only. It cannot promote betrayal or create live permission."
        ),
    }


def build_betrayal_vs_normal_comparison(
    *,
    betrayal_context_rows: Sequence[Mapping[str, Any]],
    pattern_lane_matrix: Mapping[str, Any] | None = None,
    anchor_confluence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normal_rows = _normal_reference_rows(pattern_lane_matrix or {})
    top = betrayal_context_rows[0] if betrayal_context_rows else {}
    return {
        "normal_reference_rows": normal_rows,
        "betrayal_rows": [
            {
                "candidate": row.get("candidate"),
                "context_score": row.get("context_score"),
                "context_readiness": row.get("context_readiness"),
                "paper_only": True,
                "live_authorized": False,
            }
            for row in betrayal_context_rows
        ],
        "anchor_confluence_reference": _anchor_reference(anchor_confluence or {}),
        "top_betrayal_candidate": top.get("candidate"),
        "betrayal_can_enter_paper_matrix": bool(betrayal_context_rows),
        "betrayal_can_enter_live_readiness": False,
        "why": "Betrayal rows are context-only paper evidence and are compared against normal paper references without live promotion.",
    }


def build_betrayal_matrix_gap_report(
    *,
    rows: Sequence[Mapping[str, Any]],
    betrayal_integration_recheck: Mapping[str, Any],
    pattern_lane_matrix: Mapping[str, Any],
    anchor_confluence: Mapping[str, Any],
    tiny_live_readiness: Mapping[str, Any],
    regime_gate: Mapping[str, Any] | None = None,
    miro_fish_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    integration_gap = betrayal_integration_recheck.get("current_stack_gap_report") or {}
    return {
        "event_tracker_missing": True,
        "regime_gate_missing_or_pending": not bool(regime_gate),
        "miro_fish_missing_or_pending": not bool(miro_fish_gate),
        "direction_split_missing": True,
        "tiny_live_excluded": True,
        "pattern_lane_matrix_found": bool(pattern_lane_matrix),
        "anchor_confluence_found": bool(anchor_confluence),
        "tiny_live_readiness_found": bool(tiny_live_readiness),
        "matrix_integration_missing_from_r209": bool(integration_gap.get("matrix_integration_missing", True)),
        "context_rows_available": bool(rows),
        "hard_live_blockers": [
            "betrayal_not_live_authorized",
            "betrayal_not_promoted",
            "event_tracker_missing",
            "regime_gate_missing_or_pending",
            "miro_fish_missing_or_pending",
            "direction_split_missing",
            "tiny_live_excluded",
            "config_writes_forbidden",
            "orders_forbidden",
        ],
    }


def build_betrayal_context_recommendations(
    *,
    gap_report: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    recommendations = [
        {
            "priority": "HIGH",
            "recommended_action": "BUILD_BETRAYAL_EVENT_TRACKER",
            "future_phase": "R212",
            "why": "Betrayal context needs deterministic future event identities before later scoring can trust event-level samples.",
        },
        {
            "priority": "HIGH",
            "recommended_action": "KEEP_PAPER_ONLY",
            "future_phase": "R211",
            "why": "R211 rows are context only and cannot create live readiness, lane mode eligibility, or promotion.",
        },
    ]
    if gap_report.get("regime_gate_missing_or_pending"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "RUN_REGIME_GATE",
                "future_phase": "R213",
                "why": "Betrayal candidates still need current regime support as paper-only context.",
            }
        )
    if gap_report.get("miro_fish_missing_or_pending"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "RUN_MIRO_FISH_GATE",
                "future_phase": "R213",
                "why": "Betrayal candidates still need Miro Fish quality review as paper-only context.",
            }
        )
    if rows:
        recommendations.append(
            {
                "priority": "LOW",
                "recommended_action": "RUN_R208B_FISHERMAN_WATCHDOG_HARDENING",
                "future_phase": "R208B",
                "why": "Keep paper-fishing reliability strong while betrayal event tracking is built.",
            }
        )
    return recommendations


def classify_betrayal_paper_matrix_context_status(
    *,
    rows: Sequence[Mapping[str, Any]],
    gap_report: Mapping[str, Any],
) -> str:
    if not rows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if all(_to_int(row.get("resolved_true_inverse_samples")) < 15 for row in rows):
        return BETRAYAL_CONTEXT_NEEDS_MORE_TRUE_INVERSE_SAMPLES
    if gap_report.get("event_tracker_missing"):
        return BETRAYAL_MATRIX_REVIEW_READY_PAPER_ONLY
    return BETRAYAL_CONTEXT_ADDED_PAPER_ONLY


def append_betrayal_paper_matrix_context_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_paper_matrix_context_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "matrix_id": str(record.get("matrix_id") or f"r211_betrayal_paper_matrix_context_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_PAPER_MATRIX_CONTEXT_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_matrix_requested": bool(record.get("record_matrix_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "betrayal_context_rows": list(record.get("betrayal_context_rows") or []),
            "betrayal_vs_normal_comparison": dict(record.get("betrayal_vs_normal_comparison") or {}),
            "betrayal_matrix_gap_report": dict(record.get("betrayal_matrix_gap_report") or {}),
            "betrayal_context_recommendations": list(record.get("betrayal_context_recommendations") or []),
            "betrayal_matrix_status": record.get("betrayal_matrix_status"),
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


def load_betrayal_paper_matrix_context_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_paper_matrix_context_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_betrayal_paper_matrix_context_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    rows = latest.get("betrayal_context_rows") if isinstance(latest.get("betrayal_context_rows"), list) else []
    top = rows[0] if rows and isinstance(rows[0], Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "matrix_status_counts": dict(
            sorted(Counter(str(record.get("betrayal_matrix_status") or "UNKNOWN") for record in records).items())
        ),
        "last_matrix_id": latest.get("matrix_id") if isinstance(latest, Mapping) else None,
        "last_top_betrayal_candidate": top.get("candidate"),
        "safety": dict(SAFETY),
    }


def betrayal_paper_matrix_context_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_paper_matrix_context_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _candidate_fallback(timeframe: str) -> dict[str, Any]:
    if timeframe == "222m":
        return dict(PRIMARY_222M)
    if timeframe == "88m":
        return dict(WATCHLIST_88M)
    return {
        "label": "BETRAYAL_OPTIONAL_WATCHLIST_FOUND_IN_HISTORY",
        "original_win_rate_pct": None,
        "naive_inverse_win_rate_pct": None,
        "live_ready": False,
    }


def _matrix_integration_status(recheck: Mapping[str, Any]) -> str:
    gap = recheck.get("current_stack_gap_report") or {}
    if gap.get("matrix_integration_missing", True):
        return "BETRAYAL_MATRIX_CONTEXT_MISSING_FROM_R203_R205_R206"
    return "BETRAYAL_MATRIX_CONTEXT_PRESENT"


def _coverage_points(timeframe: str, pattern: Mapping[str, Any], anchor: Mapping[str, Any]) -> float:
    points = 0.0
    matrix_rows = pattern.get("pattern_lane_pair_matrix") or []
    if any(timeframe.lower() == str(row.get("timeframe") or "").lower() for row in matrix_rows if isinstance(row, Mapping)):
        points += 7.5
    anchor_rows = anchor.get("anchor_signal_confluence_rows") or []
    if any(timeframe.lower() == str(row.get("timeframe") or "").lower() for row in anchor_rows if isinstance(row, Mapping)):
        points += 7.5
    return points


def _integration_points(pattern: Mapping[str, Any], anchor: Mapping[str, Any], tiny: Mapping[str, Any]) -> float:
    found_count = sum(1 for item in (pattern, anchor, tiny) if item)
    return min(5.0, found_count * 1.7)


def _normal_reference_rows(pattern: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    matrix = pattern.get("pattern_lane_pair_matrix") or []
    targets = {
        "hammer_wick_reversal": "8m short + hammer_wick_reversal",
        "bearish_engulfing": "8m short + bearish_engulfing",
        "three_black_crows": "8m short + three_black_crows",
    }
    for origin, name in targets.items():
        match = next(
            (
                item
                for item in matrix
                if isinstance(item, Mapping)
                and item.get("signal_origin") == origin
                and str(item.get("timeframe") or "").lower() == "8m"
                and item.get("direction") == "short"
            ),
            None,
        )
        if match:
            rows.append({"name": name, "score": _to_int(match.get("pair_score")), "paper_only": True})
    if len(rows) == len(targets):
        return rows
    return [dict(row) for row in NORMAL_REFERENCE_FALLBACKS]


def _anchor_reference(anchor: Mapping[str, Any]) -> dict[str, Any]:
    quality = anchor.get("confluence_evidence_quality_report") or {}
    return {
        "summary_level_only": bool(quality.get("summary_level_is_weaker_evidence", True)),
        "event_level_rows": _to_int(quality.get("event_level_rows")),
        "top_summary_confluence_score": _top_anchor_score(anchor),
    }


def _top_anchor_score(anchor: Mapping[str, Any]) -> int | None:
    rankings = anchor.get("anchor_signal_confluence_rankings") or anchor.get("best_confluence_candidates") or []
    if rankings and isinstance(rankings[0], Mapping):
        return _to_int(rankings[0].get("confluence_score"))
    return None


def _recommended_next_operator_move(gap_report: Mapping[str, Any]) -> str:
    if gap_report.get("event_tracker_missing"):
        return "RUN_R212_BETRAYAL_EVENT_TRACKER"
    if gap_report.get("regime_gate_missing_or_pending") or gap_report.get("miro_fish_missing_or_pending"):
        return "RUN_R213_BETRAYAL_REGIME_MIRO_RECHECK"
    return "KEEP_WEEKEND_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(gap_report: Mapping[str, Any]) -> str:
    if gap_report.get("event_tracker_missing"):
        return "Build R212 deterministic betrayal event tracker; keep R211 context paper-only and non-promotional."
    return "Recheck betrayal regime and Miro Fish context as paper-only evidence; do not write configs or authorize live."


def _top_level_status(*, record_matrix: bool, confirmation_valid: bool, has_rows: bool) -> str:
    if record_matrix and not confirmation_valid:
        return BETRAYAL_PAPER_MATRIX_CONTEXT_REJECTED
    if not has_rows:
        return BETRAYAL_PAPER_MATRIX_CONTEXT_BLOCKED
    if record_matrix and confirmation_valid:
        return BETRAYAL_PAPER_MATRIX_CONTEXT_RECORDED
    return BETRAYAL_PAPER_MATRIX_CONTEXT_READY


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


def _empty_gap_report() -> dict[str, Any]:
    return {
        "event_tracker_missing": True,
        "regime_gate_missing_or_pending": True,
        "miro_fish_missing_or_pending": True,
        "direction_split_missing": True,
        "tiny_live_excluded": True,
        "hard_live_blockers": ["composer_error", "betrayal_not_live_authorized"],
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


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float | None:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


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
