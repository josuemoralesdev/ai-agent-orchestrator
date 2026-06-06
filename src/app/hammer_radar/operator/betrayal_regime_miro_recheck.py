"""R213 betrayal regime + Miro Fish recheck.

Paper-only audit composer for betrayal aggregate candidates. It reuses R212,
R211, R210, local R82/R83 gates, and local candle archives without network,
Binance, order payloads, config writes, lane changes, promotion, or live
authorization.
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

BETRAYAL_REGIME_MIRO_RECHECK_READY = "BETRAYAL_REGIME_MIRO_RECHECK_READY"
BETRAYAL_REGIME_MIRO_RECHECK_REJECTED = "BETRAYAL_REGIME_MIRO_RECHECK_REJECTED"
BETRAYAL_REGIME_MIRO_RECHECK_RECORDED = "BETRAYAL_REGIME_MIRO_RECHECK_RECORDED"
BETRAYAL_REGIME_MIRO_RECHECK_BLOCKED = "BETRAYAL_REGIME_MIRO_RECHECK_BLOCKED"
BETRAYAL_REGIME_MIRO_RECHECK_ERROR = "BETRAYAL_REGIME_MIRO_RECHECK_ERROR"

BETRAYAL_REGIME_SUPPORT_AVAILABLE = "BETRAYAL_REGIME_SUPPORT_AVAILABLE"
BETRAYAL_REGIME_NEUTRAL_OR_PENDING = "BETRAYAL_REGIME_NEUTRAL_OR_PENDING"
BETRAYAL_REGIME_REJECTS_CANDIDATE = "BETRAYAL_REGIME_REJECTS_CANDIDATE"
BETRAYAL_MIRO_SUPPORT_AVAILABLE = "BETRAYAL_MIRO_SUPPORT_AVAILABLE"
BETRAYAL_MIRO_PENDING_OR_BLOCKED = "BETRAYAL_MIRO_PENDING_OR_BLOCKED"
BETRAYAL_EVENT_DIRECTION_SPLIT_STILL_REQUIRED = "BETRAYAL_EVENT_DIRECTION_SPLIT_STILL_REQUIRED"
BETRAYAL_NOT_LIVE_AUTHORIZED = "BETRAYAL_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_REGIME_MIRO_RECHECK"
LEDGER_FILENAME = "betrayal_regime_miro_recheck.ndjson"
CONFIRM_BETRAYAL_REGIME_MIRO_RECHECK_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL REGIME MIRO RECHECK RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

TARGET_TIMEFRAMES = ("222m", "88m", "55m")
TARGET_CANDIDATES = ("222m aggregate", "88m aggregate", "55m aggregate_if_available")
DEFAULT_SYMBOL = "BTCUSDT"

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
    "logs/hammer_radar_forward/betrayal_event_tracker.ndjson",
    "logs/hammer_radar_forward/betrayal_paper_matrix_context.ndjson",
    "logs/hammer_radar_forward/betrayal_true_inverse_refresh.ndjson",
    "logs/hammer_radar_forward/markov_regime_gate.ndjson",
    "logs/hammer_radar_forward/miro_fish_quality_gate.ndjson",
    "logs/hammer_radar_forward/candle_archive/BTCUSDT_222m.ndjson",
    "logs/hammer_radar_forward/candle_archive/BTCUSDT_88m.ndjson",
    "logs/hammer_radar_forward/candle_archive/BTCUSDT_55m.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_betrayal_regime_miro_recheck(
    *,
    log_dir: str | Path | None = None,
    record_recheck: bool = False,
    confirm_betrayal_regime_miro_recheck: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_regime_miro_recheck == CONFIRM_BETRAYAL_REGIME_MIRO_RECHECK_RECORDING_PHRASE
    )
    try:
        event_tracker = load_latest_betrayal_event_tracker(log_dir=resolved_log_dir)
        matrix_context = load_latest_betrayal_paper_matrix_context(log_dir=resolved_log_dir)
        true_inverse = load_latest_betrayal_true_inverse_refresh(log_dir=resolved_log_dir)
        markov_gate = load_existing_markov_regime_gate(log_dir=resolved_log_dir)
        miro_gate = load_existing_miro_fish_quality_gate(log_dir=resolved_log_dir)
        candles = load_betrayal_local_candles_for_regime(log_dir=resolved_log_dir)
        regime_context = build_betrayal_regime_context(
            markov_regime_gate=markov_gate,
            local_candles=candles,
            log_dir=resolved_log_dir,
        )
        miro_context = build_betrayal_miro_fish_context(
            miro_fish_gate=miro_gate,
            log_dir=resolved_log_dir,
        )
        rows = build_betrayal_regime_miro_candidate_rows(
            betrayal_event_tracker=event_tracker,
            betrayal_matrix_context=matrix_context,
            betrayal_true_inverse_refresh=true_inverse,
            betrayal_regime_context=regime_context,
            betrayal_miro_fish_context=miro_context,
        )
        gap_report = build_betrayal_regime_miro_gap_report(
            betrayal_event_tracker=event_tracker,
            betrayal_matrix_context=matrix_context,
            true_inverse_refresh=true_inverse,
            regime_context=regime_context,
            miro_context=miro_context,
            candidate_rows=rows,
        )
        recommendations = build_betrayal_regime_miro_recommendations(gap_report)
        regime_miro_status = classify_betrayal_regime_miro_status(gap_report=gap_report, candidate_rows=rows)
        payload = {
            "status": _top_level_status(
                record_recheck=record_recheck,
                confirmation_valid=confirmation_valid,
                has_inputs=bool(event_tracker and matrix_context and true_inverse),
            ),
            "generated_at": generated_at.isoformat(),
            "recheck_recorded": False,
            "recheck_id": None,
            "record_recheck_requested": bool(record_recheck),
            "confirmation_valid": bool(confirmation_valid),
            "target_scope": {
                "betrayal_candidates": list(TARGET_CANDIDATES),
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": {
                "betrayal_event_tracker_found": bool(event_tracker),
                "betrayal_matrix_context_found": bool(matrix_context),
                "true_inverse_refresh_found": bool(true_inverse),
                "markov_regime_gate_found": bool(markov_gate),
                "miro_fish_gate_found": bool(miro_gate),
                "local_candles_loaded": {timeframe: len(candles.get(timeframe, [])) for timeframe in TARGET_TIMEFRAMES},
            },
            "betrayal_regime_context": regime_context,
            "betrayal_miro_fish_context": miro_context,
            "betrayal_regime_miro_candidate_rows": rows,
            "betrayal_regime_miro_gap_report": gap_report,
            "betrayal_regime_miro_recommendations": recommendations,
            "regime_miro_status": regime_miro_status,
            "recommended_next_operator_move": _recommended_next_operator_move(gap_report),
            "recommended_next_engineering_move": _recommended_next_engineering_move(gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_recheck and confirmation_valid and rows:
            record = append_betrayal_regime_miro_recheck_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_REGIME_MIRO_RECHECK_RECORDED
            payload["recheck_recorded"] = True
            payload["recheck_id"] = record["recheck_id"]
            payload["ledger_path"] = str(betrayal_regime_miro_recheck_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_REGIME_MIRO_RECHECK_ERROR,
                "generated_at": generated_at.isoformat(),
                "recheck_recorded": False,
                "recheck_id": None,
                "record_recheck_requested": bool(record_recheck),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "target_scope": {"betrayal_candidates": list(TARGET_CANDIDATES), "paper_only": True, "live_authorized": False},
                "input_summary": {},
                "betrayal_regime_context": _missing_context("regime"),
                "betrayal_miro_fish_context": _missing_context("miro"),
                "betrayal_regime_miro_candidate_rows": [],
                "betrayal_regime_miro_gap_report": _empty_gap_report(),
                "betrayal_regime_miro_recommendations": [],
                "regime_miro_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_WEEKEND_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Fix R213 composer error; keep betrayal paper-only.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_betrayal_event_tracker(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_event_tracker.ndjson")


def load_latest_betrayal_paper_matrix_context(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_paper_matrix_context.ndjson")


def load_latest_betrayal_true_inverse_refresh(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_true_inverse_refresh.ndjson")


def load_existing_markov_regime_gate(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "markov_regime_gate.ndjson")


def load_existing_miro_fish_quality_gate(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _latest_record(get_log_dir(log_dir, use_env=True) / "miro_fish_quality_gate.ndjson")


def load_betrayal_local_candles_for_regime(
    *,
    log_dir: str | Path | None = None,
    symbol: str = DEFAULT_SYMBOL,
    limit: int = 120,
) -> dict[str, list[dict[str, Any]]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    candles = {}
    for timeframe in TARGET_TIMEFRAMES:
        path = resolved_log_dir / "candle_archive" / f"{symbol}_{timeframe}.ndjson"
        rows = _read_ndjson(path)
        candles[timeframe] = rows[-limit:] if limit > 0 else rows
    return candles


def build_betrayal_regime_context(
    *,
    markov_regime_gate: Mapping[str, Any] | None = None,
    local_candles: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    contexts: dict[str, dict[str, Any]] = {}
    existing_rows = _rows_by_timeframe(
        [
            *_list_field(markov_regime_gate or {}, "aggregate_candidate_regime_gates"),
            *_list_field(markov_regime_gate or {}, "betrayal_candidate_regime_gates"),
        ]
    )
    if not existing_rows and markov_regime_gate:
        existing_rows = _regime_summary_rows(markov_regime_gate)
    for timeframe in TARGET_TIMEFRAMES:
        row = existing_rows.get(timeframe)
        if row:
            contexts[timeframe] = _regime_context_from_existing_row(row)
            continue
        preview = _local_regime_preview(timeframe, list((local_candles or {}).get(timeframe, [])))
        if preview["regime_source"] == "missing" and log_dir is not None:
            preview["notes"].append("existing Markov gate ledger was not found; no candle preview available")
        contexts[timeframe] = preview
    return _sanitize(contexts)


def build_betrayal_miro_fish_context(
    *,
    miro_fish_gate: Mapping[str, Any] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    source_gate = dict(miro_fish_gate or {})
    source = "existing_miro_gate" if source_gate else "missing"
    if not source_gate and log_dir is not None:
        try:
            from src.app.hammer_radar.operator.markov_regime_gate import BETRAYAL
            from src.app.hammer_radar.operator.miro_fish_quality_gate import build_miro_fish_quality_gate

            source_gate = build_miro_fish_quality_gate(family=BETRAYAL, log_dir=log_dir)
            source = "existing_miro_gate"
        except Exception:
            source_gate = {}
            source = "missing"
    rows = _rows_by_timeframe(_list_field(source_gate, "betrayal_candidate_quality_gates"))
    contexts = {}
    for timeframe in TARGET_TIMEFRAMES:
        row = rows.get(timeframe)
        if row:
            contexts[timeframe] = _miro_context_from_row(row, source=source)
        else:
            contexts[timeframe] = {
                "miro_status": BETRAYAL_MIRO_PENDING_OR_BLOCKED,
                "miro_support": "pending",
                "miro_source": source if source != "existing_miro_gate" else "missing",
                "miro_fish_support_found": False,
                "notes": ["Miro Fish support was not found for this betrayal candidate; support is not fabricated."],
            }
    return _sanitize(contexts)


def build_betrayal_regime_miro_candidate_rows(
    *,
    betrayal_event_tracker: Mapping[str, Any],
    betrayal_matrix_context: Mapping[str, Any],
    betrayal_true_inverse_refresh: Mapping[str, Any],
    betrayal_regime_context: Mapping[str, Mapping[str, Any]],
    betrayal_miro_fish_context: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    matrix_rows = _matrix_rows_by_timeframe(betrayal_matrix_context, betrayal_true_inverse_refresh)
    event_status = str(betrayal_event_tracker.get("event_tracker_status") or UNKNOWN_NEEDS_MANUAL_REVIEW)
    direction_split_resolved = _direction_split_resolved(betrayal_event_tracker)
    rows = []
    for timeframe in TARGET_TIMEFRAMES:
        matrix = matrix_rows.get(timeframe)
        if not matrix:
            continue
        regime = betrayal_regime_context.get(timeframe, {})
        miro = betrayal_miro_fish_context.get(timeframe, {})
        inherited_warnings = set(_list_field(matrix, "risk_warnings"))
        if betrayal_event_tracker:
            inherited_warnings.discard("event_tracker_missing")
        if regime.get("regime_support") in {"supports", "neutral"}:
            inherited_warnings.discard("regime_support_missing_or_pending")
        if miro.get("miro_support") not in {"supports", "neutral"}:
            inherited_warnings.add("miro_fish_missing_or_pending")
        risk_warnings = sorted(
            {
                *inherited_warnings,
                *([] if direction_split_resolved else ["direction_split_missing"]),
                *([] if betrayal_event_tracker else ["event_tracker_missing"]),
                *([] if regime.get("regime_support") != "rejects" else ["regime_rejects_candidate"]),
                *([] if miro.get("miro_support") != "rejects" else ["miro_rejects_candidate"]),
                "paper_review_only",
                "not_live_ready",
                "not_promoted",
            }
        )
        paper_status = _candidate_paper_review_status(
            true_inverse_found=bool(betrayal_true_inverse_refresh),
            event_tracker_found=bool(betrayal_event_tracker),
            direction_split_resolved=direction_split_resolved,
            regime_support=str(regime.get("regime_support") or "pending"),
            miro_support=str(miro.get("miro_support") or "pending"),
        )
        rows.append(
            {
                "candidate": f"{timeframe} aggregate",
                "context_score": matrix.get("context_score"),
                "resolved_true_inverse_samples": _to_int(matrix.get("resolved_true_inverse_samples")),
                "event_tracker_status": event_status,
                "direction_split_resolved": bool(direction_split_resolved),
                "regime_support": regime.get("regime_support", "pending"),
                "regime_status": regime.get("regime_status", BETRAYAL_REGIME_NEUTRAL_OR_PENDING),
                "miro_support": miro.get("miro_support", "pending"),
                "miro_status": miro.get("miro_status", BETRAYAL_MIRO_PENDING_OR_BLOCKED),
                "paper_review_status": paper_status,
                "live_ready": False,
                "promotion_allowed": False,
                "risk_warnings": risk_warnings,
                "why": _candidate_why(timeframe, matrix, regime, miro, direction_split_resolved),
            }
        )
    return _sanitize(rows)


def build_betrayal_regime_miro_gap_report(
    *,
    betrayal_event_tracker: Mapping[str, Any],
    betrayal_matrix_context: Mapping[str, Any],
    true_inverse_refresh: Mapping[str, Any],
    regime_context: Mapping[str, Mapping[str, Any]],
    miro_context: Mapping[str, Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    direction_split_missing = not _direction_split_resolved(betrayal_event_tracker)
    miro_pending = any(row.get("miro_support") in {"pending", "rejects"} for row in miro_context.values())
    regime_pending = any(row.get("regime_support") in {"pending", "rejects"} for row in regime_context.values())
    hard = [
        "betrayal_not_live_authorized",
        "betrayal_not_promoted",
        "tiny_live_excluded",
        "config_writes_forbidden",
        "orders_forbidden",
        "binance_calls_forbidden",
    ]
    if not betrayal_event_tracker:
        hard.append("event_tracker_missing")
    if direction_split_missing:
        hard.append("direction_split_missing")
    if not true_inverse_refresh:
        hard.append("true_inverse_refresh_missing")
    if not betrayal_matrix_context:
        hard.append("betrayal_matrix_context_missing")
    if regime_pending:
        hard.append("regime_gate_missing_or_pending")
    if miro_pending:
        hard.append("miro_fish_missing_or_pending")
    return _sanitize(
        {
            "direction_split_missing": bool(direction_split_missing),
            "miro_fish_missing_or_pending": bool(miro_pending),
            "regime_gate_missing_or_pending": bool(regime_pending),
            "event_tracker_missing": not bool(betrayal_event_tracker),
            "betrayal_matrix_context_missing": not bool(betrayal_matrix_context),
            "true_inverse_refresh_missing": not bool(true_inverse_refresh),
            "candidate_rows_available": bool(candidate_rows),
            "hard_live_blockers": hard,
        }
    )


def build_betrayal_regime_miro_recommendations(gap_report: Mapping[str, Any]) -> list[dict[str, str]]:
    recommendations = []
    if gap_report.get("direction_split_missing"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "RESOLVE_DIRECTION_SPLIT",
                "future_phase": "R215",
                "why": "Aggregate betrayal candidates still cannot become direction-specific validation rows.",
            }
        )
    if gap_report.get("miro_fish_missing_or_pending"):
        recommendations.append(
            {
                "priority": "HIGH",
                "recommended_action": "BUILD_MIRO_FISH_RECHECK",
                "future_phase": "R214",
                "why": "Miro Fish context is pending, blocked, or not supportive for at least one betrayal candidate.",
            }
        )
    recommendations.append(
        {
            "priority": "HIGH",
            "recommended_action": "KEEP_PAPER_ONLY",
            "future_phase": "R213",
            "why": "Regime and Miro support are audit context only and cannot authorize live betrayal.",
        }
    )
    if gap_report.get("event_tracker_missing"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "BUILD_EVENT_OUTCOME_RESOLVER",
                "future_phase": "R214",
                "why": "Event tracking must exist before outcome resolving can be trusted.",
            }
        )
    return recommendations


def classify_betrayal_regime_miro_status(
    *,
    gap_report: Mapping[str, Any],
    candidate_rows: Sequence[Mapping[str, Any]],
) -> str:
    if not candidate_rows:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if gap_report.get("direction_split_missing"):
        return BETRAYAL_EVENT_DIRECTION_SPLIT_STILL_REQUIRED
    if gap_report.get("miro_fish_missing_or_pending"):
        return BETRAYAL_MIRO_PENDING_OR_BLOCKED
    if gap_report.get("regime_gate_missing_or_pending"):
        return BETRAYAL_REGIME_NEUTRAL_OR_PENDING
    if any(row.get("regime_support") == "rejects" for row in candidate_rows):
        return BETRAYAL_REGIME_REJECTS_CANDIDATE
    if any(row.get("regime_support") == "supports" for row in candidate_rows):
        return BETRAYAL_REGIME_SUPPORT_AVAILABLE
    return BETRAYAL_NOT_LIVE_AUTHORIZED


def append_betrayal_regime_miro_recheck_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_regime_miro_recheck_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "recheck_id": str(record.get("recheck_id") or f"r213_betrayal_regime_miro_recheck_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": BETRAYAL_REGIME_MIRO_RECHECK_RECORDED,
            "generated_at": record.get("generated_at"),
            "record_recheck_requested": bool(record.get("record_recheck_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_scope": dict(record.get("target_scope") or {}),
            "input_summary": dict(record.get("input_summary") or {}),
            "betrayal_regime_context": dict(record.get("betrayal_regime_context") or {}),
            "betrayal_miro_fish_context": dict(record.get("betrayal_miro_fish_context") or {}),
            "betrayal_regime_miro_candidate_rows": list(record.get("betrayal_regime_miro_candidate_rows") or []),
            "betrayal_regime_miro_gap_report": dict(record.get("betrayal_regime_miro_gap_report") or {}),
            "betrayal_regime_miro_recommendations": list(record.get("betrayal_regime_miro_recommendations") or []),
            "regime_miro_status": record.get("regime_miro_status"),
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


def load_betrayal_regime_miro_recheck_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_regime_miro_recheck_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_betrayal_regime_miro_recheck_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "regime_miro_status_counts": dict(
            sorted(Counter(str(record.get("regime_miro_status") or "UNKNOWN") for record in records).items())
        ),
        "last_recheck_id": latest.get("recheck_id") if isinstance(latest, Mapping) else None,
        "safety": dict(SAFETY),
    }


def betrayal_regime_miro_recheck_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_regime_miro_recheck_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _regime_context_from_existing_row(row: Mapping[str, Any]) -> dict[str, Any]:
    status = str(row.get("gate_status") or "")
    if "REJECTS" in status:
        support = "rejects"
        regime_status = BETRAYAL_REGIME_REJECTS_CANDIDATE
    elif "SUPPORTS" in status:
        support = "supports"
        regime_status = BETRAYAL_REGIME_SUPPORT_AVAILABLE
    else:
        support = "neutral"
        regime_status = BETRAYAL_REGIME_NEUTRAL_OR_PENDING
    return {
        "regime_status": regime_status,
        "regime_support": support,
        "regime_source": "existing_markov_gate",
        "current_regime": row.get("current_regime"),
        "regime_confidence": row.get("regime_confidence"),
        "notes": [str(row.get("gate_reason") or "Existing Markov gate row reused as paper-only context.")],
    }


def _local_regime_preview(timeframe: str, candles: list[Mapping[str, Any]]) -> dict[str, Any]:
    valid = [_valid_candle(row) for row in candles]
    valid = [row for row in valid if row]
    if len(valid) < 5:
        return {
            "regime_status": BETRAYAL_REGIME_NEUTRAL_OR_PENDING,
            "regime_support": "pending",
            "regime_source": "missing",
            "notes": ["No existing Markov gate ledger and insufficient local candles for preview."],
        }
    first = valid[0]["close"]
    last = valid[-1]["close"]
    total_return = _pct_change(first, last)
    ranges = [_pct_change(row["low"], row["high"]) for row in valid if row["low"] > 0]
    avg_range = sum(ranges) / len(ranges) if ranges else 0.0
    returns = [_pct_change(left["close"], right["close"]) for left, right in zip(valid, valid[1:], strict=False)]
    roughness = sum(abs(item) for item in returns) / len(returns) if returns else 0.0
    if total_return <= -1.0:
        support = "supports"
        status = BETRAYAL_REGIME_SUPPORT_AVAILABLE
    elif total_return >= 1.0:
        support = "rejects"
        status = BETRAYAL_REGIME_REJECTS_CANDIDATE
    else:
        support = "neutral"
        status = BETRAYAL_REGIME_NEUTRAL_OR_PENDING
    return {
        "regime_status": status,
        "regime_support": support,
        "regime_source": "local_preview",
        "trend_direction": "down" if total_return < -0.4 else "up" if total_return > 0.4 else "flat",
        "volatility_regime": "high" if avg_range >= 4.0 or roughness >= 2.5 else "normal",
        "momentum_roughness": round(roughness, 4),
        "candle_count": len(valid),
        "notes": [
            f"Local candle preview only for {timeframe}; it is not a replacement for the Markov gate.",
            f"total_return_pct={round(total_return, 4)} avg_range_pct={round(avg_range, 4)}",
        ],
    }


def _miro_context_from_row(row: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    status = str(row.get("final_quality_status") or "")
    if "SUPPORTS" in status:
        support = "supports"
        miro_status = BETRAYAL_MIRO_SUPPORT_AVAILABLE
    elif "REJECT" in status:
        support = "rejects"
        miro_status = BETRAYAL_MIRO_PENDING_OR_BLOCKED
    elif "BLOCKED" in status or "NEEDS_MORE" in status:
        support = "pending"
        miro_status = BETRAYAL_MIRO_PENDING_OR_BLOCKED
    else:
        support = "neutral"
        miro_status = BETRAYAL_MIRO_PENDING_OR_BLOCKED
    return {
        "miro_status": miro_status,
        "miro_support": support,
        "miro_source": source,
        "miro_fish_support_found": support == "supports",
        "final_quality_status": status,
        "final_quality_score": row.get("final_quality_score"),
        "notes": [str(row.get("operator_note") or "Existing Miro Fish quality row reused as paper-only context.")],
    }


def _matrix_rows_by_timeframe(
    matrix_context: Mapping[str, Any],
    true_inverse_refresh: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    rows = {}
    for row in _list_field(matrix_context, "betrayal_context_rows"):
        timeframe = str(row.get("timeframe") or "").lower()
        if timeframe:
            rows[timeframe] = row
    summary = true_inverse_refresh.get("candidate_true_inverse_summary")
    if isinstance(summary, Mapping):
        for timeframe, row in summary.items():
            key = str(timeframe).lower()
            if key not in rows and isinstance(row, Mapping):
                rows[key] = {"candidate": f"{key} aggregate", "timeframe": key, **dict(row)}
    return rows


def _direction_split_resolved(event_tracker: Mapping[str, Any]) -> bool:
    gap = event_tracker.get("event_tracker_gap_report") if isinstance(event_tracker.get("event_tracker_gap_report"), Mapping) else {}
    preview = event_tracker.get("event_tracker_preview") if isinstance(event_tracker.get("event_tracker_preview"), Mapping) else {}
    return bool(event_tracker) and not bool(gap.get("direction_split_missing", True)) and _to_int(preview.get("direction_specific_events")) > 0


def _candidate_paper_review_status(
    *,
    true_inverse_found: bool,
    event_tracker_found: bool,
    direction_split_resolved: bool,
    regime_support: str,
    miro_support: str,
) -> str:
    if not true_inverse_found or not event_tracker_found:
        return "PAPER_REVIEW_BLOCKED_MISSING_INPUTS"
    if not direction_split_resolved:
        return "PAPER_REVIEW_BLOCKED_DIRECTION_SPLIT"
    if regime_support == "rejects" or miro_support == "rejects":
        return "PAPER_REVIEW_REJECTED_BY_CONTEXT"
    if regime_support == "supports" and miro_support in {"supports", "neutral"}:
        return "PAPER_REVIEW_CONTEXT_SUPPORTED_NOT_LIVE"
    return "PAPER_REVIEW_PENDING_CONTEXT"


def _candidate_why(
    timeframe: str,
    matrix: Mapping[str, Any],
    regime: Mapping[str, Any],
    miro: Mapping[str, Any],
    direction_split_resolved: bool,
) -> str:
    split = "direction split is resolved" if direction_split_resolved else "direction split remains unresolved"
    return (
        f"{timeframe} aggregate keeps R211 context_score={matrix.get('context_score')} and "
        f"{_to_int(matrix.get('resolved_true_inverse_samples'))} true-inverse sample(s); {split}. "
        f"Regime={regime.get('regime_support', 'pending')} and Miro={miro.get('miro_support', 'pending')} "
        "are paper-only review context and do not authorize live or promotion."
    )


def _rows_by_timeframe(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result = {}
    for row in rows:
        timeframe = str(row.get("timeframe") or "").lower()
        if timeframe in TARGET_TIMEFRAMES and timeframe not in result:
            result[timeframe] = row
    return result


def _regime_summary_rows(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    summary = payload.get("regime_summary") if isinstance(payload.get("regime_summary"), Mapping) else {}
    return {str(key).lower(): value for key, value in summary.items() if isinstance(value, Mapping)}


def _recommended_next_operator_move(gap_report: Mapping[str, Any]) -> str:
    if gap_report.get("direction_split_missing"):
        return "RUN_R215_BETRAYAL_DIRECTION_SPLIT_RESOLVER"
    if gap_report.get("event_tracker_missing"):
        return "RUN_R214_BETRAYAL_EVENT_OUTCOME_RESOLVER"
    if gap_report.get("miro_fish_missing_or_pending") or gap_report.get("regime_gate_missing_or_pending"):
        return "KEEP_WEEKEND_FISHERMAN_RUNNING"
    return "KEEP_WEEKEND_FISHERMAN_RUNNING"


def _recommended_next_engineering_move(gap_report: Mapping[str, Any]) -> str:
    if gap_report.get("direction_split_missing"):
        return "Build R215 direction split resolver from local paper signals/captures only; keep betrayal paper-only."
    if gap_report.get("event_tracker_missing"):
        return "Build R214 event outcome resolver after R212 tracker evidence is present."
    return "Keep R213 as audit context only; do not write config, promote betrayal, or infer live readiness."


def _top_level_status(*, record_recheck: bool, confirmation_valid: bool, has_inputs: bool) -> str:
    if record_recheck and not confirmation_valid:
        return BETRAYAL_REGIME_MIRO_RECHECK_REJECTED
    if not has_inputs:
        return BETRAYAL_REGIME_MIRO_RECHECK_BLOCKED
    if record_recheck and confirmation_valid:
        return BETRAYAL_REGIME_MIRO_RECHECK_RECORDED
    return BETRAYAL_REGIME_MIRO_RECHECK_READY


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


def _missing_context(kind: str) -> dict[str, dict[str, Any]]:
    if kind == "miro":
        return {
            timeframe: {
                "miro_status": BETRAYAL_MIRO_PENDING_OR_BLOCKED,
                "miro_support": "pending",
                "miro_source": "missing",
                "notes": ["Miro Fish support missing or blocked."],
            }
            for timeframe in TARGET_TIMEFRAMES
        }
    return {
        timeframe: {
            "regime_status": BETRAYAL_REGIME_NEUTRAL_OR_PENDING,
            "regime_support": "pending",
            "regime_source": "missing",
            "notes": ["Regime context missing or pending."],
        }
        for timeframe in TARGET_TIMEFRAMES
    }


def _empty_gap_report() -> dict[str, Any]:
    return {
        "direction_split_missing": True,
        "miro_fish_missing_or_pending": True,
        "regime_gate_missing_or_pending": True,
        "event_tracker_missing": True,
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
    records = []
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


def _valid_candle(row: Mapping[str, Any]) -> dict[str, float] | None:
    try:
        return {
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _pct_change(left: float, right: float) -> float:
    if left == 0:
        return 0.0
    return ((right - left) / left) * 100.0


def _list_field(payload: Mapping[str, Any], key: str) -> list:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key, value in SAFETY.items():
            if key in sanitized:
                sanitized[key] = value
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
