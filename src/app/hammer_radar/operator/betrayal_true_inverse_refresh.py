"""R210 betrayal true inverse refresh.

Local paper-only refresh surface for betrayal true-inverse validation evidence.
It composes R209 context, R80-R100 docs, shadow records, true-paper ledgers,
local candle archives, and full-spectrum captures without network, Binance,
orders, config writes, lane promotion, or live authorization.
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
from src.app.hammer_radar.operator.betrayal_candle_archive import load_archive_candles
from src.app.hammer_radar.operator.betrayal_integration_recheck import (
    PRIMARY_222M,
    WATCHLIST_88M,
    build_betrayal_integration_recheck,
    load_latest_full_spectrum_222m_capture,
)
from src.app.hammer_radar.operator.betrayal_shadow_outcomes import RESOLVED_STATUSES
from src.app.hammer_radar.operator.betrayal_shadow_resolver import (
    load_betrayal_shadow_resolutions as _load_shadow_resolutions,
    resolve_shadow_record,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records

BETRAYAL_TRUE_INVERSE_REFRESH_READY = "BETRAYAL_TRUE_INVERSE_REFRESH_READY"
BETRAYAL_TRUE_INVERSE_REFRESH_REJECTED = "BETRAYAL_TRUE_INVERSE_REFRESH_REJECTED"
BETRAYAL_TRUE_INVERSE_REFRESH_RECORDED = "BETRAYAL_TRUE_INVERSE_REFRESH_RECORDED"
BETRAYAL_TRUE_INVERSE_REFRESH_BLOCKED = "BETRAYAL_TRUE_INVERSE_REFRESH_BLOCKED"
BETRAYAL_TRUE_INVERSE_REFRESH_ERROR = "BETRAYAL_TRUE_INVERSE_REFRESH_ERROR"

TRUE_INVERSE_VALIDATION_REFRESHED = "TRUE_INVERSE_VALIDATION_REFRESHED"
TRUE_INVERSE_VALIDATION_PENDING = "TRUE_INVERSE_VALIDATION_PENDING"
TRUE_INVERSE_NO_RESOLVABLE_SAMPLES = "TRUE_INVERSE_NO_RESOLVABLE_SAMPLES"
TRUE_INVERSE_CANDLE_COVERAGE_MISSING = "TRUE_INVERSE_CANDLE_COVERAGE_MISSING"
TRUE_INVERSE_TIMESTAMP_ALIGNMENT_BLOCKED = "TRUE_INVERSE_TIMESTAMP_ALIGNMENT_BLOCKED"
TRUE_INVERSE_CAPTURE_LINKED_NOT_VALIDATED = "TRUE_INVERSE_CAPTURE_LINKED_NOT_VALIDATED"
TRUE_INVERSE_NOT_LIVE_AUTHORIZED = "TRUE_INVERSE_NOT_LIVE_AUTHORIZED"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "BETRAYAL_TRUE_INVERSE_REFRESH"
LEDGER_FILENAME = "betrayal_true_inverse_refresh.ndjson"
CONFIRM_BETRAYAL_TRUE_INVERSE_REFRESH_RECORDING_PHRASE = (
    "I CONFIRM BETRAYAL TRUE INVERSE REFRESH RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

TARGET_TIMEFRAMES = ("222m", "88m", "55m")
TARGET_SYMBOL = "BTCUSDT"

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
    "docs/hammer_radar/live_readiness/R209_BETRAYAL_INTEGRATION_RECHECK.md",
]

SAFETY = {
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


def build_betrayal_true_inverse_refresh(
    *,
    log_dir: str | Path | None = None,
    record_refresh: bool = False,
    confirm_betrayal_true_inverse_refresh: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = (
        confirm_betrayal_true_inverse_refresh == CONFIRM_BETRAYAL_TRUE_INVERSE_REFRESH_RECORDING_PHRASE
    )
    try:
        integration = load_latest_betrayal_integration_recheck(log_dir=resolved_log_dir)
        docs = load_betrayal_candidate_docs_context()
        shadows = load_betrayal_shadow_outcomes(log_dir=resolved_log_dir)
        resolutions = load_betrayal_shadow_resolutions(log_dir=resolved_log_dir)
        true_paper = load_betrayal_true_paper_outcomes(log_dir=resolved_log_dir)
        paper_signals = load_betrayal_paper_signals(log_dir=resolved_log_dir)
        candles = load_local_betrayal_candles(log_dir=resolved_log_dir)
        capture = load_latest_222m_full_spectrum_capture(log_dir=resolved_log_dir)
        previews = [
            resolve_true_inverse_outcome_preview(record, local_candles=candles)
            for record in shadows
            if str(record.get("timeframe") or "") in TARGET_TIMEFRAMES
        ]
        candidate_summary = build_candidate_true_inverse_summary(
            shadow_outcomes=shadows,
            shadow_resolutions=resolutions,
            true_paper_outcomes=true_paper,
            previews=previews,
            local_candles=candles,
            docs_context=docs,
        )
        capture_summary = build_capture_seed_validation_summary(
            capture_linkage=link_capture_to_betrayal_candidate(capture)
        )
        gap_report = build_betrayal_validation_gap_report(
            shadow_outcomes=shadows,
            previews=previews,
            local_candles=candles,
            candidate_summary=candidate_summary,
        )
        recommendations = build_betrayal_refresh_recommendations(
            candidate_summary=candidate_summary,
            capture_seed_validation_summary=capture_summary,
            gap_report=gap_report,
        )
        refresh_status = classify_betrayal_true_inverse_refresh_status(
            candidate_summary=candidate_summary,
            capture_seed_validation_summary=capture_summary,
            gap_report=gap_report,
        )
        status = _top_level_status(
            record_refresh=record_refresh,
            confirmation_valid=confirmation_valid,
            refresh_status=refresh_status,
        )
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "refresh_recorded": False,
            "refresh_id": None,
            "record_refresh_requested": bool(record_refresh),
            "confirmation_valid": bool(confirmation_valid),
            "betrayal_scope": {
                "primary_candidate": "222m aggregate",
                "watchlist_candidates": ["88m aggregate"] + (["55m aggregate_if_found"] if docs["optional_55m_found"] else []),
                "paper_only": True,
                "live_authorized": False,
            },
            "input_summary": _input_summary(
                integration=integration,
                shadow_outcomes=shadows,
                shadow_resolutions=resolutions,
                true_paper_outcomes=true_paper,
                paper_signals=paper_signals,
                local_candles=candles,
                latest_222m_capture=capture,
            ),
            "candidate_true_inverse_summary": candidate_summary,
            "capture_seed_validation_summary": capture_summary,
            "validation_gap_report": gap_report,
            "refresh_recommendations": recommendations,
            "refresh_status": refresh_status,
            "recommended_next_operator_move": _recommended_next_operator_move(refresh_status),
            "recommended_next_engineering_move": _recommended_next_engineering_move(refresh_status, gap_report),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": _source_surfaces(),
            "input_context": {
                "latest_integration_recheck": integration,
                "docs_context": docs,
            },
        }
        if record_refresh and confirmation_valid:
            record = append_betrayal_true_inverse_refresh_record(payload, log_dir=resolved_log_dir)
            payload["status"] = BETRAYAL_TRUE_INVERSE_REFRESH_RECORDED
            payload["refresh_recorded"] = True
            payload["refresh_id"] = record["refresh_id"]
            payload["ledger_path"] = str(betrayal_true_inverse_refresh_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": BETRAYAL_TRUE_INVERSE_REFRESH_ERROR,
                "generated_at": generated_at.isoformat(),
                "refresh_recorded": False,
                "refresh_id": None,
                "record_refresh_requested": bool(record_refresh),
                "confirmation_valid": bool(confirmation_valid),
                "error": str(exc),
                "betrayal_scope": {
                    "primary_candidate": "222m aggregate",
                    "watchlist_candidates": ["88m aggregate"],
                    "paper_only": True,
                    "live_authorized": False,
                },
                "input_summary": {},
                "candidate_true_inverse_summary": _default_candidate_summary(),
                "capture_seed_validation_summary": _empty_capture_summary(),
                "validation_gap_report": _empty_gap_report(),
                "refresh_recommendations": [],
                "refresh_status": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "recommended_next_operator_move": "KEEP_WEEKEND_FISHERMAN_RUNNING",
                "recommended_next_engineering_move": "Inspect local betrayal ledgers manually; do not change config or live gates.",
                "do_not_run_yet": _do_not_run_yet(),
                "safety": dict(SAFETY),
            }
        )


def load_latest_betrayal_integration_recheck(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    record = _latest_record(get_log_dir(log_dir, use_env=True) / "betrayal_integration_recheck.ndjson")
    return record or build_betrayal_integration_recheck(log_dir=log_dir)


def load_betrayal_shadow_outcomes(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_shadow_outcomes.ndjson")


def load_betrayal_shadow_resolutions(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    try:
        return [_sanitize(record) for record in _load_shadow_resolutions(log_dir=log_dir, newest_first=False)]
    except Exception:
        return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_shadow_resolutions.ndjson")


def load_betrayal_true_paper_outcomes(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_true_paper_outcomes.ndjson")


def load_betrayal_paper_signals(*, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    return _read_ndjson(get_log_dir(log_dir, use_env=True) / "betrayal_paper_signals.ndjson")


def load_betrayal_candidate_docs_context(*, repo_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    found: list[str] = []
    missing: list[str] = []
    optional_55m_found = False
    for rel in DOC_PATHS:
        path = root / rel
        if not path.exists():
            missing.append(rel)
            continue
        found.append(rel)
        text = path.read_text(encoding="utf-8", errors="replace")
        if "55m" in text and "BETRAYAL" in text.upper():
            optional_55m_found = True
    return {
        "docs_checked": list(DOC_PATHS),
        "docs_found": found,
        "docs_missing": missing,
        "optional_55m_found": optional_55m_found,
        "candidate_facts": _candidate_facts(optional_55m_found=optional_55m_found),
        "naive_inverse_audit_only": True,
        "regime_prerequisites_required": ["R82_MARKOV_REGIME_GATE", "R83_MIRO_FISH_QUALITY_GATE"],
        "live_ready": False,
    }


def load_local_betrayal_candles(*, log_dir: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    return {
        timeframe: load_archive_candles(log_dir=resolved_log_dir, symbol=TARGET_SYMBOL, timeframe=timeframe)
        for timeframe in TARGET_TIMEFRAMES
    }


def load_latest_222m_full_spectrum_capture(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    return _sanitize(load_latest_full_spectrum_222m_capture(log_dir=log_dir))


def match_shadow_outcome_to_local_candles(
    shadow_outcome: Mapping[str, Any],
    *,
    local_candles: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    timeframe = str(shadow_outcome.get("timeframe") or "")
    candles = list(local_candles.get(timeframe) or [])
    result = resolve_shadow_record(shadow_outcome, candles=candles)
    return _sanitize(
        {
            "shadow_outcome_id": shadow_outcome.get("shadow_outcome_id"),
            "symbol": shadow_outcome.get("symbol"),
            "timeframe": timeframe,
            "preview_status": result.get("shadow_status"),
            "resolved": result.get("shadow_status") in RESOLVED_STATUSES,
            "temporal_alignment_ok": result.get("temporal_alignment_ok") is True,
            "resolution_blockers": result.get("resolution_blockers") or [],
            "resolved_candle_timestamp": result.get("resolved_candle_timestamp"),
            "true_inverse_pnl_pct": result.get("true_inverse_pnl_pct"),
            "shadow_close_reason": result.get("shadow_close_reason"),
        }
    )


def resolve_true_inverse_outcome_preview(
    shadow_outcome: Mapping[str, Any],
    *,
    local_candles: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    required_missing = [
        key
        for key in ("symbol", "timeframe", "signal_timestamp", "shadow_direction", "shadow_entry", "shadow_stop", "shadow_take_profit")
        if shadow_outcome.get(key) in (None, "")
    ]
    match = match_shadow_outcome_to_local_candles(shadow_outcome, local_candles=local_candles)
    counted = (
        not required_missing
        and match["resolved"] is True
        and match["temporal_alignment_ok"] is True
        and str(shadow_outcome.get("symbol") or "").upper() == TARGET_SYMBOL
        and str(shadow_outcome.get("timeframe") or "") in TARGET_TIMEFRAMES
    )
    blockers = list(match.get("resolution_blockers") or [])
    blockers.extend(f"missing_{key}" for key in required_missing)
    return _sanitize(
        {
            **match,
            "counted_as_true_inverse_refresh_sample": bool(counted),
            "counted_as_live_edge": False,
            "naive_inverse_counted": False,
            "blockers": sorted(set(blockers)),
        }
    )


def link_capture_to_betrayal_candidate(capture: Mapping[str, Any]) -> dict[str, Any]:
    lane = str(capture.get("lane_key") or "")
    parts = lane.split("|")
    return {
        "latest_222m_capture_lane": lane or None,
        "latest_222m_capture_at": capture.get("captured_at"),
        "capture_matches_222m": "|222m|" in lane.lower(),
        "symbol": parts[0] if len(parts) >= 1 else None,
        "timeframe": parts[1] if len(parts) >= 2 else None,
        "direction": parts[2] if len(parts) >= 3 else None,
        "entry_mode": parts[3] if len(parts) >= 4 else None,
        "capture_has_outcome_schema": False,
    }


def build_candidate_true_inverse_summary(
    *,
    shadow_outcomes: list[dict[str, Any]],
    shadow_resolutions: list[dict[str, Any]],
    true_paper_outcomes: list[dict[str, Any]],
    previews: list[dict[str, Any]],
    local_candles: Mapping[str, list[dict[str, Any]]],
    docs_context: Mapping[str, Any],
) -> dict[str, Any]:
    summary = _default_candidate_summary(include_55m=bool(docs_context.get("optional_55m_found")))
    for timeframe, row in summary.items():
        target_shadows = [record for record in shadow_outcomes if record.get("timeframe") == timeframe]
        target_previews = [record for record in previews if record.get("timeframe") == timeframe]
        resolved_preview = _dedupe_resolved_previews(target_previews)
        persisted_resolved = [
            record for record in shadow_resolutions if record.get("timeframe") == timeframe and _is_resolved(record)
        ]
        true_paper_resolved = [
            record for record in true_paper_outcomes if record.get("timeframe") == timeframe and _is_resolved(record)
        ]
        resolved_samples = _dedupe_samples([*persisted_resolved, *true_paper_resolved, *resolved_preview])
        wins = sum(1 for record in resolved_samples if _is_win(record))
        refreshed_win_rate = round((wins / len(resolved_samples)) * 100.0, 2) if resolved_samples else None
        blockers = _candidate_blockers(
            timeframe=timeframe,
            shadow_outcomes=target_shadows,
            previews=target_previews,
            candles=local_candles.get(timeframe) or [],
        )
        validation_status = _candidate_validation_status(
            resolved_samples=resolved_samples,
            shadow_outcomes=target_shadows,
            blockers=blockers,
        )
        row.update(
            {
                "resolved_true_inverse_samples": len(resolved_samples),
                "unresolved_shadow_samples": max(len(target_shadows) - len(resolved_preview), 0),
                "refreshed_win_rate_pct": refreshed_win_rate,
                "validation_status": validation_status,
                "live_ready": False,
                "promotion_allowed": False,
                "why": _candidate_why(
                    validation_status=validation_status,
                    resolved_count=len(resolved_samples),
                    blockers=blockers,
                ),
                "naive_inverse_counted_as_validated_edge": False,
                "shadow_outcome_count": len(target_shadows),
                "local_candle_count": len(local_candles.get(timeframe) or []),
                "blockers": blockers,
            }
        )
    return _sanitize(summary)


def build_capture_seed_validation_summary(*, capture_linkage: Mapping[str, Any]) -> dict[str, Any]:
    linked = bool(capture_linkage.get("capture_matches_222m"))
    return {
        "latest_222m_capture_lane": capture_linkage.get("latest_222m_capture_lane"),
        "capture_matches_222m": linked,
        "capture_can_seed_true_inverse_tracking": linked,
        "capture_counted_as_validated_sample": False,
        "required_next_step": (
            "Track the linked 222m capture through a deterministic betrayal event tracker and local outcome window."
            if linked
            else "Keep full-spectrum harvester running until a 222m capture with event schema is available."
        ),
        "validation_status": TRUE_INVERSE_CAPTURE_LINKED_NOT_VALIDATED if linked else TRUE_INVERSE_VALIDATION_PENDING,
    }


def build_betrayal_validation_gap_report(
    *,
    shadow_outcomes: list[dict[str, Any]],
    previews: list[dict[str, Any]],
    local_candles: Mapping[str, list[dict[str, Any]]],
    candidate_summary: Mapping[str, Any],
) -> dict[str, Any]:
    missing_candles = [timeframe for timeframe in TARGET_TIMEFRAMES if not local_candles.get(timeframe)]
    missing_shadow_schema = sorted(
        {
            f"{record.get('timeframe')}:missing_{key}"
            for record in shadow_outcomes
            if str(record.get("timeframe") or "") in TARGET_TIMEFRAMES
            for key in ("signal_timestamp", "shadow_direction", "shadow_entry", "shadow_stop", "shadow_take_profit")
            if record.get(key) in (None, "")
        }
    )
    missing_direction_split = [
        timeframe
        for timeframe in ("222m", "88m")
        if not any(record.get("timeframe") == timeframe and record.get("shadow_direction") for record in shadow_outcomes)
    ]
    timestamp_alignment_blockers = sorted(
        {
            str(blocker)
            for record in previews
            for blocker in record.get("blockers", [])
            if "timestamp" in str(blocker) or "temporal" in str(blocker) or "alignment" in str(blocker)
        }
    )
    duplicate_or_unresolved_counts = {
        timeframe: {
            "shadow_outcomes": int((candidate_summary.get(timeframe) or {}).get("shadow_outcome_count") or 0),
            "resolved_true_inverse_samples": int(
                (candidate_summary.get(timeframe) or {}).get("resolved_true_inverse_samples") or 0
            ),
            "unresolved_shadow_samples": int((candidate_summary.get(timeframe) or {}).get("unresolved_shadow_samples") or 0),
        }
        for timeframe in candidate_summary
    }
    matrix_blocked = not any(
        int((candidate_summary.get(timeframe) or {}).get("resolved_true_inverse_samples") or 0) > 0
        for timeframe in ("222m", "88m")
    )
    return {
        "missing_candles": missing_candles,
        "missing_shadow_schema": missing_shadow_schema,
        "missing_direction_split": missing_direction_split,
        "timestamp_alignment_blockers": timestamp_alignment_blockers,
        "duplicate_or_unresolved_counts": duplicate_or_unresolved_counts,
        "matrix_integration_blocked_until_refresh": matrix_blocked,
    }


def build_betrayal_refresh_recommendations(
    *,
    candidate_summary: Mapping[str, Any],
    capture_seed_validation_summary: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommendations = [
        {
            "priority": "HIGH",
            "recommended_action": "BUILD_BETRAYAL_EVENT_TRACKER",
            "future_phase": "R212",
            "why": "Future betrayal samples need deterministic event identities, declared outcome windows, and schema-complete records.",
        },
        {
            "priority": "HIGH",
            "recommended_action": "KEEP_BLOCKED",
            "future_phase": "R210",
            "why": "Naive inverse audit math and raw captures remain separated from validated true-inverse edge.",
        },
    ]
    if gap_report.get("matrix_integration_blocked_until_refresh"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "COLLECT_MORE_SHADOW_OUTCOMES",
                "future_phase": "R212",
                "why": "No primary/watchlist candidate has enough refreshed true-inverse evidence for paper matrix context.",
            }
        )
    else:
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "ADD_PAPER_MATRIX_CONTEXT",
                "future_phase": "R211",
                "why": "Refreshed local evidence can be shown as paper-only context, still with no promotion or live readiness.",
            }
        )
    if capture_seed_validation_summary.get("capture_can_seed_true_inverse_tracking"):
        recommendations.append(
            {
                "priority": "MEDIUM",
                "recommended_action": "BUILD_BETRAYAL_EVENT_TRACKER",
                "future_phase": "R212",
                "why": "The latest 222m capture can seed future tracking but is not a validated sample.",
            }
        )
    return recommendations


def classify_betrayal_true_inverse_refresh_status(
    *,
    candidate_summary: Mapping[str, Any],
    capture_seed_validation_summary: Mapping[str, Any],
    gap_report: Mapping[str, Any],
) -> str:
    resolved = sum(
        int((candidate_summary.get(timeframe) or {}).get("resolved_true_inverse_samples") or 0)
        for timeframe in ("222m", "88m")
    )
    if resolved > 0:
        return TRUE_INVERSE_VALIDATION_REFRESHED
    if gap_report.get("missing_candles"):
        return TRUE_INVERSE_CANDLE_COVERAGE_MISSING
    if gap_report.get("timestamp_alignment_blockers"):
        return TRUE_INVERSE_TIMESTAMP_ALIGNMENT_BLOCKED
    if capture_seed_validation_summary.get("capture_matches_222m"):
        return TRUE_INVERSE_CAPTURE_LINKED_NOT_VALIDATED
    if not any(int((candidate_summary.get(tf) or {}).get("shadow_outcome_count") or 0) for tf in ("222m", "88m", "55m")):
        return TRUE_INVERSE_NO_RESOLVABLE_SAMPLES
    return TRUE_INVERSE_VALIDATION_PENDING


def append_betrayal_true_inverse_refresh_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = betrayal_true_inverse_refresh_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            **dict(record),
            "event_type": EVENT_TYPE,
            "refresh_id": str(record.get("refresh_id") or f"r210_betrayal_true_inverse_refresh_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "refresh_recorded": True,
            "safety": dict(SAFETY),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_betrayal_true_inverse_refresh_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = betrayal_true_inverse_refresh_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        return _read_ndjson(path)
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_betrayal_true_inverse_refresh_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(Counter(str(record.get("status") or "UNKNOWN") for record in records).items())),
        "refresh_status_counts": dict(
            sorted(Counter(str(record.get("refresh_status") or "UNKNOWN") for record in records).items())
        ),
        "last_refresh_id": records[0].get("refresh_id") if records else None,
        "safety": dict(SAFETY),
    }


def betrayal_true_inverse_refresh_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_betrayal_true_inverse_refresh_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), sort_keys=True, separators=(",", ":"))


def _input_summary(
    *,
    integration: Mapping[str, Any],
    shadow_outcomes: list[dict[str, Any]],
    shadow_resolutions: list[dict[str, Any]],
    true_paper_outcomes: list[dict[str, Any]],
    paper_signals: list[dict[str, Any]],
    local_candles: Mapping[str, list[dict[str, Any]]],
    latest_222m_capture: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "integration_recheck_found": bool(integration),
        "shadow_outcomes_found": bool(shadow_outcomes),
        "shadow_outcome_count": len(shadow_outcomes),
        "shadow_resolutions_found": bool(shadow_resolutions),
        "shadow_resolution_count": len(shadow_resolutions),
        "true_paper_outcomes_found": bool(true_paper_outcomes),
        "true_paper_outcome_count": len(true_paper_outcomes),
        "betrayal_paper_signals_found": bool(paper_signals),
        "betrayal_paper_signal_count": len(paper_signals),
        "local_candles_loaded": {timeframe: len(local_candles.get(timeframe) or []) for timeframe in TARGET_TIMEFRAMES},
        "latest_222m_capture_found": bool(latest_222m_capture),
    }


def _candidate_facts(*, optional_55m_found: bool) -> dict[str, dict[str, Any]]:
    facts = {"222m": dict(PRIMARY_222M), "88m": dict(WATCHLIST_88M)}
    if optional_55m_found:
        facts["55m"] = {
            "label": "BETRAYAL_OPTIONAL_WATCHLIST_FOUND_IN_HISTORY",
            "original_sample_count": None,
            "original_win_rate_pct": None,
            "naive_inverse_win_rate_pct": None,
            "true_inverse_validation_required": True,
            "live_ready": False,
        }
    return facts


def _default_candidate_summary(*, include_55m: bool = False) -> dict[str, dict[str, Any]]:
    rows = {
        "222m": {
            "label": "BETRAYAL_PRIMARY_CANDIDATE",
            "original_sample_count": 48,
            "original_win_rate_pct": 12.5,
            "naive_inverse_win_rate_pct": 87.5,
        },
        "88m": {
            "label": "BETRAYAL_WATCHLIST",
            "original_sample_count": 90,
            "original_win_rate_pct": 36.67,
            "naive_inverse_win_rate_pct": 63.33,
        },
    }
    if include_55m:
        rows["55m"] = {
            "label": "BETRAYAL_OPTIONAL_WATCHLIST_FOUND_IN_HISTORY",
            "original_sample_count": None,
            "original_win_rate_pct": None,
            "naive_inverse_win_rate_pct": None,
        }
    for row in rows.values():
        row.update(
            {
                "resolved_true_inverse_samples": 0,
                "unresolved_shadow_samples": 0,
                "refreshed_win_rate_pct": None,
                "validation_status": TRUE_INVERSE_VALIDATION_PENDING,
                "live_ready": False,
                "promotion_allowed": False,
                "why": "No refreshed local true-inverse samples have been counted.",
            }
        )
    return rows


def _candidate_validation_status(
    *,
    resolved_samples: list[Mapping[str, Any]],
    shadow_outcomes: list[Mapping[str, Any]],
    blockers: list[str],
) -> str:
    if resolved_samples:
        return TRUE_INVERSE_VALIDATION_REFRESHED
    if not shadow_outcomes:
        return TRUE_INVERSE_NO_RESOLVABLE_SAMPLES
    if any("no_local_candles" in blocker for blocker in blockers):
        return TRUE_INVERSE_CANDLE_COVERAGE_MISSING
    if any("timestamp" in blocker or "temporal" in blocker or "alignment" in blocker for blocker in blockers):
        return TRUE_INVERSE_TIMESTAMP_ALIGNMENT_BLOCKED
    return TRUE_INVERSE_VALIDATION_PENDING


def _candidate_blockers(
    *,
    timeframe: str,
    shadow_outcomes: list[Mapping[str, Any]],
    previews: list[Mapping[str, Any]],
    candles: list[Mapping[str, Any]],
) -> list[str]:
    blockers: set[str] = set()
    if not candles:
        blockers.add(f"{timeframe}:no_local_candles")
    if not shadow_outcomes:
        blockers.add(f"{timeframe}:no_shadow_outcomes")
    for preview in previews:
        for blocker in preview.get("blockers", []):
            blockers.add(f"{timeframe}:{blocker}")
    return sorted(blockers)


def _candidate_why(*, validation_status: str, resolved_count: int, blockers: list[str]) -> str:
    if validation_status == TRUE_INVERSE_VALIDATION_REFRESHED:
        return (
            f"{resolved_count} strict local paper true-inverse sample(s) were refreshed from schema-complete "
            "shadow/resolution/true-paper evidence. This remains paper-only and not live-ready."
        )
    if validation_status == TRUE_INVERSE_CANDLE_COVERAGE_MISSING:
        return "Local candle coverage is missing for this candidate timeframe."
    if validation_status == TRUE_INVERSE_TIMESTAMP_ALIGNMENT_BLOCKED:
        return "Local evidence exists, but strict timestamp alignment blocked validation."
    if validation_status == TRUE_INVERSE_NO_RESOLVABLE_SAMPLES:
        return "No target-timeframe betrayal shadow or true-paper samples were found."
    if blockers:
        return "Refresh remains pending because schema, candle, or alignment blockers remain."
    return "Refresh remains pending; no sample met all strict true-inverse counting rules."


def _dedupe_resolved_previews(previews: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return _dedupe_samples([dict(record) for record in previews if record.get("counted_as_true_inverse_refresh_sample")])


def _dedupe_samples(records: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(
            record.get("shadow_outcome_id")
            or record.get("betrayal_paper_signal_id")
            or record.get("signal_id")
            or record.get("original_signal_id")
            or "|".join(
                str(record.get(field) or "")
                for field in ("symbol", "timeframe", "signal_timestamp", "shadow_direction", "resolved_candle_timestamp")
            )
        )
        if key and key not in by_key:
            by_key[key] = _sanitize(dict(record))
    return list(by_key.values())


def _is_resolved(record: Mapping[str, Any]) -> bool:
    status = str(record.get("shadow_status") or record.get("outcome") or record.get("status") or "").upper()
    return status in {*(str(item).upper() for item in RESOLVED_STATUSES), "WIN", "LOSS", "BREAKEVEN", "PROFIT", "STOPPED"}


def _is_win(record: Mapping[str, Any]) -> bool:
    status = str(record.get("shadow_status") or record.get("outcome") or record.get("status") or "").upper()
    if status in {"SHADOW_WIN", "WIN", "PROFIT"}:
        return True
    pnl = record.get("true_inverse_pnl_pct") if record.get("true_inverse_pnl_pct") is not None else record.get("pnl_pct")
    try:
        return float(pnl) > 0
    except (TypeError, ValueError):
        return False


def _top_level_status(*, record_refresh: bool, confirmation_valid: bool, refresh_status: str) -> str:
    if record_refresh and not confirmation_valid:
        return BETRAYAL_TRUE_INVERSE_REFRESH_REJECTED
    if record_refresh and confirmation_valid:
        return BETRAYAL_TRUE_INVERSE_REFRESH_RECORDED
    if refresh_status == TRUE_INVERSE_VALIDATION_REFRESHED:
        return BETRAYAL_TRUE_INVERSE_REFRESH_READY
    return BETRAYAL_TRUE_INVERSE_REFRESH_BLOCKED


def _recommended_next_operator_move(refresh_status: str) -> str:
    if refresh_status == TRUE_INVERSE_VALIDATION_REFRESHED:
        return "RUN_R211_BETRAYAL_PAPER_MATRIX_CONTEXT"
    if refresh_status == TRUE_INVERSE_CAPTURE_LINKED_NOT_VALIDATED:
        return "KEEP_WEEKEND_FISHERMAN_RUNNING"
    return "RUN_R212_BETRAYAL_EVENT_TRACKER"


def _recommended_next_engineering_move(refresh_status: str, gap_report: Mapping[str, Any]) -> str:
    if refresh_status == TRUE_INVERSE_VALIDATION_REFRESHED:
        return "Add R211 paper-only betrayal matrix context; do not write config, promote betrayal, or infer live readiness."
    if gap_report.get("missing_candles"):
        return "Backfill local candle archives through existing local-only archive bridge; do not fetch or call Binance."
    return "Build R212 deterministic betrayal event tracker to collect schema-complete future samples."


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


def _empty_capture_summary() -> dict[str, Any]:
    return {
        "latest_222m_capture_lane": None,
        "capture_matches_222m": False,
        "capture_can_seed_true_inverse_tracking": False,
        "capture_counted_as_validated_sample": False,
        "required_next_step": "No capture linkage was available.",
    }


def _empty_gap_report() -> dict[str, Any]:
    return {
        "missing_candles": [],
        "missing_shadow_schema": [],
        "missing_direction_split": [],
        "timestamp_alignment_blockers": [],
        "duplicate_or_unresolved_counts": {},
        "matrix_integration_blocked_until_refresh": True,
    }


def _source_surfaces() -> list[str]:
    return [
        *DOC_PATHS,
        "logs/hammer_radar_forward/betrayal_integration_recheck.ndjson",
        "logs/hammer_radar_forward/betrayal_shadow_outcomes.ndjson",
        "logs/hammer_radar_forward/betrayal_shadow_resolutions.ndjson",
        "logs/hammer_radar_forward/betrayal_true_paper_outcomes.ndjson",
        "logs/hammer_radar_forward/betrayal_paper_signals.ndjson",
        "logs/hammer_radar_forward/full_spectrum_harvester_expansion.ndjson",
        "logs/hammer_radar_forward/candle_archive/BTCUSDT_222m.ndjson",
        "logs/hammer_radar_forward/candle_archive/BTCUSDT_88m.ndjson",
        "logs/hammer_radar_forward/candle_archive/BTCUSDT_55m.ndjson",
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
    return value
