"""R183 Keter signal-origin scoring layer.

This module ranks paper-only signal origins by quality/readiness. It reads
local ledgers only and never calls Binance, creates payloads, mutates
env/config, changes lane modes, promotes origins, or authorizes live execution.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.multi_lane_evidence_ranking import (
    LEDGER_FILENAME as MULTI_LANE_RANKING_LEDGER_FILENAME,
    load_multi_lane_evidence_ranking_records,
)
from src.app.hammer_radar.operator.signal_origin_registry import (
    DETECTOR_AVAILABLE,
    INFERRED_FROM_EXISTING_FIELDS,
    REGISTRY_ONLY,
    UNKNOWN,
    UNKNOWN_ORIGIN,
    build_signal_origin_registry,
    build_signal_origin_registry_preview,
    load_signal_origin_registry_records,
)

KETER_SIGNAL_ORIGIN_SCORING_READY = "KETER_SIGNAL_ORIGIN_SCORING_READY"
KETER_SIGNAL_ORIGIN_SCORING_REJECTED = "KETER_SIGNAL_ORIGIN_SCORING_REJECTED"
KETER_SIGNAL_ORIGIN_SCORING_RECORDED = "KETER_SIGNAL_ORIGIN_SCORING_RECORDED"
KETER_SIGNAL_ORIGIN_SCORING_BLOCKED = "KETER_SIGNAL_ORIGIN_SCORING_BLOCKED"
KETER_SIGNAL_ORIGIN_SCORING_ERROR = "KETER_SIGNAL_ORIGIN_SCORING_ERROR"

ORIGIN_READY_FOR_PAPER_TRACKING = "ORIGIN_READY_FOR_PAPER_TRACKING"
ORIGIN_NEEDS_DETECTOR = "ORIGIN_NEEDS_DETECTOR"
ORIGIN_NEEDS_MORE_TAGGED_DATA = "ORIGIN_NEEDS_MORE_TAGGED_DATA"
ORIGIN_REFERENCE_ONLY = "ORIGIN_REFERENCE_ONLY"
ORIGIN_UNKNOWN = "ORIGIN_UNKNOWN"
ORIGIN_NOT_LIVE_AUTHORIZED = "ORIGIN_NOT_LIVE_AUTHORIZED"

EVENT_TYPE = "KETER_SIGNAL_ORIGIN_SCORING"
LEDGER_FILENAME = "keter_signal_origin_scoring.ndjson"
CONFIRM_KETER_SIGNAL_ORIGIN_SCORING_RECORDING_PHRASE = (
    "I CONFIRM KETER SIGNAL ORIGIN SCORING RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_REGISTRY_RECORDS = 100
DEFAULT_LATEST_RANKING_RECORDS = 100
MAX_LATEST_RECORDS = 5000

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
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
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
    "live_authorization_created": False,
    "signal_origin_promoted": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/signal_origin_registry.ndjson",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_lane_paper_harvester.ndjson",
    f"logs/hammer_radar_forward/{MULTI_LANE_RANKING_LEDGER_FILENAME}",
    "logs/hammer_radar_forward/outcomes.ndjson",
    "logs/hammer_radar_forward/paper_executions.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
    "operator.signal_origin_registry.build_signal_origin_registry_preview",
    "operator.multi_lane_evidence_ranking.load_multi_lane_evidence_ranking_records",
]


def build_keter_signal_origin_scoring(
    *,
    log_dir: str | Path | None = None,
    latest_registry_records: int = DEFAULT_LATEST_REGISTRY_RECORDS,
    latest_ranking_records: int = DEFAULT_LATEST_RANKING_RECORDS,
    record_scoring: bool = False,
    confirm_keter_origin_scoring: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_keter_origin_scoring == CONFIRM_KETER_SIGNAL_ORIGIN_SCORING_RECORDING_PHRASE
    try:
        registry_record = load_latest_signal_origin_registry_record(
            log_dir=resolved_log_dir,
            latest_registry_records=latest_registry_records,
            now=generated_at,
        )
        registry = list(registry_record.get("registry") or build_signal_origin_registry())
        feed_summary = dict(registry_record.get("feed_summary") or {})
        ranking_records = load_multi_lane_evidence_ranking_records(
            log_dir=resolved_log_dir,
            limit=_bounded_int(latest_ranking_records, 0, MAX_LATEST_RECORDS, DEFAULT_LATEST_RANKING_RECORDS),
        )
        lane_scores = _latest_lane_scores(ranking_records)
        historical = _build_origin_historical_outcomes(log_dir=resolved_log_dir)
        rankings = build_keter_origin_ranking(
            registry=registry,
            feed_summary=feed_summary,
            lane_scores=lane_scores,
            historical=historical,
            generated_at=generated_at,
        )
        by_lane = score_signal_origin_by_lane(
            registry=registry,
            feed_summary=feed_summary,
            lane_scores=lane_scores,
            historical=historical,
            generated_at=generated_at,
        )
        status = KETER_SIGNAL_ORIGIN_SCORING_READY if rankings else KETER_SIGNAL_ORIGIN_SCORING_BLOCKED
        if record_scoring and not confirmation_valid:
            status = KETER_SIGNAL_ORIGIN_SCORING_REJECTED
        elif record_scoring and confirmation_valid:
            status = KETER_SIGNAL_ORIGIN_SCORING_RECORDED
        detector_priorities = build_detector_priority_recommendations(rankings)
        tracking = build_origin_tracking_recommendations(rankings)
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "scoring_recorded": False,
            "scoring_id": None,
            "record_scoring_requested": bool(record_scoring),
            "confirmation_valid": bool(confirmation_valid),
            "keter_origin_rankings": rankings,
            "by_lane_origin_scores": by_lane,
            "detector_priority_recommendations": detector_priorities,
            "origin_tracking_recommendations": tracking,
            "current_best_origin": _current_best_origin(rankings),
            "recommended_next_operator_move": _recommended_next_operator_move(rankings, detector_priorities),
            "recommended_next_engineering_move": _recommended_next_engineering_move(rankings, detector_priorities),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "registry_source": registry_record.get("registry_source"),
        }
        if record_scoring and confirmation_valid:
            record = append_keter_signal_origin_scoring_record(payload, log_dir=resolved_log_dir)
            payload["scoring_recorded"] = True
            payload["scoring_id"] = record["scoring_id"]
            payload["ledger_path"] = str(keter_signal_origin_scoring_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": KETER_SIGNAL_ORIGIN_SCORING_ERROR,
                "generated_at": generated_at.isoformat(),
                "scoring_recorded": False,
                "scoring_id": None,
                "record_scoring_requested": bool(record_scoring),
                "confirmation_valid": bool(confirmation_valid),
                "keter_origin_rankings": [],
                "by_lane_origin_scores": {},
                "detector_priority_recommendations": [],
                "origin_tracking_recommendations": [],
                "current_best_origin": None,
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R183 Keter scoring error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_signal_origin_registry_record(
    *,
    log_dir: str | Path | None = None,
    latest_registry_records: int = DEFAULT_LATEST_REGISTRY_RECORDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    records = load_signal_origin_registry_records(
        log_dir=log_dir,
        limit=_bounded_int(latest_registry_records, 1, MAX_LATEST_RECORDS, DEFAULT_LATEST_REGISTRY_RECORDS),
    )
    if records:
        latest = dict(records[0])
        latest["registry_source"] = "signal_origin_registry_ledger"
        return latest
    preview = build_signal_origin_registry_preview(log_dir=log_dir, record_registry=False, now=now)
    preview["registry_source"] = "signal_origin_registry_preview"
    return preview


def build_origin_quality_dimensions(
    *,
    origin_entry: Mapping[str, Any],
    feed_summary: Mapping[str, Any],
    lane_scores: Mapping[str, Any] | None = None,
    historical: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, int]:
    origin = str(origin_entry.get("signal_origin") or UNKNOWN_ORIGIN)
    availability = str(origin_entry.get("availability") or UNKNOWN)
    tagged_count = int((feed_summary.get("by_origin") or {}).get(origin) or 0)
    lanes = _origin_lane_counts(origin, feed_summary)
    historical_row = dict((historical or {}).get(origin) or {})
    dimensions = {
        "detector_availability_score": _detector_availability_score(availability),
        "tagged_data_score": min(100, tagged_count * 12),
        "lane_coverage_score": _lane_coverage_score(origin=origin, lanes=lanes, lane_scores=lane_scores or {}),
        "freshness_score": _freshness_score(origin=origin, feed_summary=feed_summary, generated_at=generated_at),
        "historical_outcome_score": _historical_outcome_score(historical_row),
        "reversal_context_score": _reversal_context_score(origin_entry),
        "conflict_penalty": _conflict_penalty(origin=origin, availability=availability, tagged_count=tagged_count),
    }
    return {key: int(max(0, min(100, value))) for key, value in dimensions.items()}


def score_signal_origin(
    *,
    origin_entry: Mapping[str, Any],
    feed_summary: Mapping[str, Any],
    lane_scores: Mapping[str, Any] | None = None,
    historical: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    origin = str(origin_entry.get("signal_origin") or UNKNOWN_ORIGIN)
    availability = str(origin_entry.get("availability") or UNKNOWN)
    dimensions = build_origin_quality_dimensions(
        origin_entry=origin_entry,
        feed_summary=feed_summary,
        lane_scores=lane_scores,
        historical=historical,
        generated_at=generated_at,
    )
    weighted = (
        dimensions["detector_availability_score"] * 0.24
        + dimensions["tagged_data_score"] * 0.18
        + dimensions["lane_coverage_score"] * 0.14
        + dimensions["freshness_score"] * 0.12
        + dimensions["historical_outcome_score"] * 0.14
        + dimensions["reversal_context_score"] * 0.18
        - dimensions["conflict_penalty"] * 0.30
    )
    score = int(round(max(0.0, min(100.0, weighted))))
    if availability == REGISTRY_ONLY:
        score = min(score, 39)
    if origin == UNKNOWN_ORIGIN:
        score = min(score, 19)
    tagged_count = int((feed_summary.get("by_origin") or {}).get(origin) or 0)
    readiness = build_origin_readiness_classification(
        signal_origin=origin,
        availability=availability,
        tagged_record_count=tagged_count,
        keter_score=score,
    )
    top_lanes = _top_lanes(origin, feed_summary)
    return {
        "signal_origin": origin,
        "availability": availability,
        "keter_score": score,
        "score_band": _score_band(score),
        "readiness": readiness,
        "dimension_scores": dimensions,
        "tagged_record_count": tagged_count,
        "top_lanes": top_lanes,
        "why": _why(origin=origin, availability=availability, score=score, tagged_count=tagged_count, top_lanes=top_lanes),
        "blockers": _blockers(origin=origin, availability=availability, tagged_count=tagged_count, score=score),
        "live_authorized": False,
        "paper_only": True,
    }


def score_signal_origin_by_lane(
    *,
    registry: list[Mapping[str, Any]],
    feed_summary: Mapping[str, Any],
    lane_scores: Mapping[str, Any] | None = None,
    historical: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, list[dict[str, Any]]]:
    entries = {str(entry.get("signal_origin") or UNKNOWN_ORIGIN): entry for entry in registry}
    result: dict[str, list[dict[str, Any]]] = {}
    for lane_key, origin_counts in sorted(((feed_summary.get("by_lane_and_origin") or {}).items())):
        rows = []
        for origin, count in sorted((origin_counts or {}).items()):
            entry = entries.get(str(origin), {"signal_origin": origin, "availability": UNKNOWN, "origin_type": "fallback"})
            row = score_signal_origin(
                origin_entry=entry,
                feed_summary=feed_summary,
                lane_scores=lane_scores,
                historical=historical,
                generated_at=generated_at,
            )
            lane_bonus = min(8, int((lane_scores or {}).get(str(lane_key), 0) // 12)
                             if isinstance((lane_scores or {}).get(str(lane_key)), int | float) else 0)
            rows.append(
                {
                    "signal_origin": row["signal_origin"],
                    "keter_score": max(0, min(100, int(row["keter_score"]) + lane_bonus)),
                    "tagged_record_count": int(count or 0),
                }
            )
        result[str(lane_key)] = sorted(rows, key=lambda item: (-int(item["keter_score"]), str(item["signal_origin"])))
    return result


def build_origin_readiness_classification(
    *,
    signal_origin: str,
    availability: str,
    tagged_record_count: int,
    keter_score: int,
) -> str:
    if signal_origin == UNKNOWN_ORIGIN:
        return ORIGIN_UNKNOWN
    if availability == REGISTRY_ONLY:
        return ORIGIN_NEEDS_DETECTOR
    if tagged_record_count <= 0:
        return ORIGIN_NEEDS_MORE_TAGGED_DATA
    if keter_score >= 50:
        return ORIGIN_READY_FOR_PAPER_TRACKING
    return ORIGIN_NOT_LIVE_AUTHORIZED


def build_detector_priority_recommendations(rankings: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    recommendations = []
    for row in rankings:
        origin = str(row.get("signal_origin") or UNKNOWN_ORIGIN)
        if row.get("availability") != REGISTRY_ONLY:
            continue
        if origin == "three_black_crows":
            priority = "HIGH"
            reason = "operator-prioritized bearish reversal pattern but registry-only until detector exists"
        elif origin in {"bearish_engulfing", "bullish_engulfing", "exhaustion_wick"}:
            priority = "MEDIUM"
            reason = f"{origin} is registry-only and needs explicit detector work before paper readiness scoring."
        else:
            priority = "LOW"
            reason = f"{origin} remains registry-only and should not rank as trade-ready until detector support exists."
        recommendations.append({"signal_origin": origin, "priority": priority, "reason": reason})
    return sorted(recommendations, key=lambda item: (_priority_sort(item["priority"]), item["signal_origin"]))


def build_origin_tracking_recommendations(rankings: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    recommendations = []
    for row in rankings:
        if row.get("readiness") == ORIGIN_READY_FOR_PAPER_TRACKING:
            recommendations.append(
                {
                    "signal_origin": row["signal_origin"],
                    "priority": "HIGH" if int(row.get("keter_score") or 0) >= 70 else "MEDIUM",
                    "reason": "existing detector/tagged data supports paper evidence tracking; no live authority is created",
                }
            )
        elif row.get("availability") in {DETECTOR_AVAILABLE, INFERRED_FROM_EXISTING_FIELDS} and int(row.get("tagged_record_count") or 0) <= 0:
            recommendations.append(
                {
                    "signal_origin": row["signal_origin"],
                    "priority": "LOW",
                    "reason": "detector or inference path exists, but tagged evidence needs more paper records",
                }
            )
    return sorted(recommendations, key=lambda item: (_priority_sort(item["priority"]), item["signal_origin"]))


def build_keter_origin_ranking(
    *,
    registry: list[Mapping[str, Any]],
    feed_summary: Mapping[str, Any],
    lane_scores: Mapping[str, Any] | None = None,
    historical: Mapping[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> list[dict[str, Any]]:
    rows = [
        score_signal_origin(
            origin_entry=entry,
            feed_summary=feed_summary,
            lane_scores=lane_scores,
            historical=historical,
            generated_at=generated_at,
        )
        for entry in registry
    ]
    return sorted(
        rows,
        key=lambda row: (-int(row["keter_score"]), -int(row["tagged_record_count"]), str(row["signal_origin"])),
    )


def append_keter_signal_origin_scoring_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = keter_signal_origin_scoring_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "scoring_id": str(record.get("scoring_id") or f"r183_keter_signal_origin_scoring_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_scoring_requested": bool(record.get("record_scoring_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "keter_origin_rankings": list(record.get("keter_origin_rankings") or []),
            "by_lane_origin_scores": dict(record.get("by_lane_origin_scores") or {}),
            "detector_priority_recommendations": list(record.get("detector_priority_recommendations") or []),
            "origin_tracking_recommendations": list(record.get("origin_tracking_recommendations") or []),
            "current_best_origin": record.get("current_best_origin"),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_keter_signal_origin_scoring_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = keter_signal_origin_scoring_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_keter_signal_origin_scoring_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    best = latest.get("current_best_origin") if isinstance(latest.get("current_best_origin"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_scoring_id": latest.get("scoring_id"),
        "last_best_origin": best.get("signal_origin"),
        "safety": dict(SAFETY),
    }


def keter_signal_origin_scoring_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_keter_signal_origin_scoring_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), indent=2, sort_keys=True)


def _latest_lane_scores(records: list[Mapping[str, Any]]) -> dict[str, int]:
    latest = records[0] if records else {}
    scores: dict[str, int] = {}
    for row in latest.get("ranked_lanes") or []:
        if isinstance(row, Mapping):
            scores[str(row.get("lane_key") or "")] = int(row.get("score") or 0)
    return scores


def _build_origin_historical_outcomes(*, log_dir: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, list[float]] = defaultdict(list)
    for filename in ("outcomes.ndjson", "paper_executions.ndjson"):
        for record in read_recent_ndjson_records(log_dir / filename, limit=10000, max_bytes=32_000_000):
            if not isinstance(record, Mapping):
                continue
            origin = str(record.get("signal_origin") or record.get("origin") or "").strip()
            if not origin:
                continue
            pnl = _number_or_none(record.get("pnl_pct") or record.get("pnl_percent") or record.get("realized_pnl_pct"))
            if pnl is None:
                continue
            rows[origin].append(pnl)
    summary = {}
    for origin, pnls in rows.items():
        wins = sum(1 for value in pnls if value > 0)
        total = sum(pnls)
        summary[origin] = {
            "paper_outcome_count": len(pnls),
            "win_rate_pct": round((wins / len(pnls)) * 100.0, 2) if pnls else None,
            "avg_pnl_pct": round(total / len(pnls), 4) if pnls else None,
            "total_pnl_pct": round(total, 4),
        }
    return summary


def _detector_availability_score(availability: str) -> int:
    if availability == DETECTOR_AVAILABLE:
        return 95
    if availability == INFERRED_FROM_EXISTING_FIELDS:
        return 76
    if availability == REGISTRY_ONLY:
        return 12
    return 5


def _origin_lane_counts(origin: str, feed_summary: Mapping[str, Any]) -> dict[str, int]:
    counts = {}
    for lane_key, by_origin in (feed_summary.get("by_lane_and_origin") or {}).items():
        count = int((by_origin or {}).get(origin) or 0)
        if count > 0:
            counts[str(lane_key)] = count
    return counts


def _lane_coverage_score(*, origin: str, lanes: Mapping[str, int], lane_scores: Mapping[str, Any]) -> int:
    if not lanes:
        return 0
    coverage = min(70, len(lanes) * 18)
    best_lane_bonus = 0
    for lane_key, count in lanes.items():
        raw_lane_score = _number_or_none(lane_scores.get(lane_key))
        if raw_lane_score is not None:
            best_lane_bonus = max(best_lane_bonus, min(30, int(raw_lane_score * 0.3)))
        elif int(count or 0) > 0:
            best_lane_bonus = max(best_lane_bonus, min(20, int(count) * 4))
    if origin == "hammer_wick_reversal":
        best_lane_bonus += 5
    return min(100, coverage + best_lane_bonus)


def _freshness_score(*, origin: str, feed_summary: Mapping[str, Any], generated_at: datetime | None) -> int:
    examples = (feed_summary.get("examples_by_origin") or {}).get(origin) or []
    if not examples:
        return 0
    freshish = 0
    for example in examples:
        if not isinstance(example, Mapping):
            continue
        text = " ".join(str(example.get(key) or "") for key in ("freshness", "freshness_status", "status", "source"))
        if "fresh" in text.lower() or "harvester" in text.lower() or "signals" in text.lower():
            freshish += 1
    return min(100, 45 + freshish * 15)


def _historical_outcome_score(row: Mapping[str, Any]) -> int:
    count = int(row.get("paper_outcome_count") or 0)
    if count <= 0:
        return 0
    score = min(40, count * 4)
    win_rate = _number_or_none(row.get("win_rate_pct"))
    avg_pnl = _number_or_none(row.get("avg_pnl_pct"))
    total_pnl = _number_or_none(row.get("total_pnl_pct"))
    if win_rate is not None:
        score += 25 if win_rate >= 52.0 else max(0, int(win_rate / 52.0 * 20))
    if avg_pnl is not None and avg_pnl > 0:
        score += 20
    if total_pnl is not None and total_pnl > 0:
        score += 15
    return min(100, score)


def _reversal_context_score(origin_entry: Mapping[str, Any]) -> int:
    origin_type = str(origin_entry.get("origin_type") or "").lower()
    origin = str(origin_entry.get("signal_origin") or "")
    if "reversal" in origin_type or "rejection" in origin_type or "exhaustion" in origin_type:
        return 90
    if "divergence" in origin or "divergence" in origin_type:
        return 82
    if "continuation" in origin_type or "confirmation" in origin_type:
        return 55
    return 35


def _conflict_penalty(*, origin: str, availability: str, tagged_count: int) -> int:
    penalty = 0
    if availability == REGISTRY_ONLY:
        penalty += 55
    if availability == UNKNOWN or origin == UNKNOWN_ORIGIN:
        penalty += 75
    if tagged_count <= 0:
        penalty += 20
    return min(100, penalty)


def _score_band(score: int) -> str:
    if score <= 24:
        return "registry / unknown / not actionable"
    if score <= 49:
        return "needs detector or more data"
    if score <= 69:
        return "paper tracking candidate"
    if score <= 84:
        return "strong paper origin candidate"
    return "high-priority origin for next matrix work"


def _top_lanes(origin: str, feed_summary: Mapping[str, Any]) -> list[str]:
    counts = _origin_lane_counts(origin, feed_summary)
    return [lane for lane, _ in sorted(counts.items(), key=lambda item: (-int(item[1]), item[0]))[:5]]


def _why(*, origin: str, availability: str, score: int, tagged_count: int, top_lanes: list[str]) -> str:
    if availability == REGISTRY_ONLY:
        return f"{origin} is registry-only; it can be detector priority but not trade-ready scoring evidence."
    if origin == UNKNOWN_ORIGIN:
        return "Unknown/unclassified records are penalized because they do not explain why a setup exists."
    if tagged_count <= 0:
        return f"{origin} has detector or inference support, but no tagged paper records in the current feed summary."
    lane_text = f" across {len(top_lanes)} lane(s)" if top_lanes else ""
    return f"{origin} has {availability.lower()} support and {tagged_count} tagged paper record(s){lane_text}; score remains paper-only."


def _blockers(*, origin: str, availability: str, tagged_count: int, score: int) -> list[str]:
    blockers = ["no live authorization in R183"]
    if availability == REGISTRY_ONLY:
        blockers.append("detector unavailable; registry-only origins cannot be trade-ready")
    if origin == UNKNOWN_ORIGIN:
        blockers.append("origin is unknown/unclassified")
    if tagged_count <= 0:
        blockers.append("tagged paper evidence unavailable")
    if score < 50:
        blockers.append("Keter score below paper-tracking candidate band")
    return _dedupe(blockers)


def _current_best_origin(rankings: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    for row in rankings:
        if row.get("availability") != REGISTRY_ONLY and row.get("signal_origin") != UNKNOWN_ORIGIN:
            return {
                "signal_origin": row.get("signal_origin"),
                "reason": row.get("why"),
                "keter_score": row.get("keter_score"),
            }
    return None


def _recommended_next_operator_move(rankings: list[Mapping[str, Any]], detector_priorities: list[Mapping[str, Any]]) -> str:
    if any(int(row.get("keter_score") or 0) >= 50 for row in rankings if row.get("availability") != REGISTRY_ONLY):
        return "RUN_R184_SIGNAL_ORIGIN_LANE_MATRIX"
    if any(row.get("signal_origin") == "three_black_crows" and row.get("priority") == "HIGH" for row in detector_priorities):
        return "RUN_THREE_BLACK_CROWS_DETECTOR_PHASE"
    return "KEEP_MULTI_LANE_HARVESTER_RUNNING"


def _recommended_next_engineering_move(rankings: list[Mapping[str, Any]], detector_priorities: list[Mapping[str, Any]]) -> str:
    if any(row.get("signal_origin") == "three_black_crows" and row.get("priority") == "HIGH" for row in detector_priorities):
        return "Build a Three Black Crows detector before treating that origin as paper-ready; keep it non-live."
    if any(row.get("readiness") == ORIGIN_READY_FOR_PAPER_TRACKING for row in rankings):
        return "Build R184 lane x origin matrix over paper-only Keter scores and R181 lane rankings."
    return "Keep collecting tagged paper evidence and rerun R183 preview."


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


def _priority_sort(priority: str) -> int:
    return {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(str(priority), 9)


def _number_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounded_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
