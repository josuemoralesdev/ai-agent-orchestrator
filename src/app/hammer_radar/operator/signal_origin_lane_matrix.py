"""R184 signal-origin x lane matrix.

This module composes local R181 lane rankings and R183 Keter origin scoring
only. It never calls Binance, creates payloads, mutates env/config, changes
lane modes, promotes lanes/origins, or authorizes live execution.
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
from src.app.hammer_radar.operator.keter_signal_origin_scoring import (
    LEDGER_FILENAME as KETER_SIGNAL_ORIGIN_SCORING_LEDGER_FILENAME,
    build_keter_signal_origin_scoring,
    load_keter_signal_origin_scoring_records,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.multi_lane_evidence_ranking import (
    LEDGER_FILENAME as MULTI_LANE_RANKING_LEDGER_FILENAME,
    build_multi_lane_evidence_ranking,
    load_multi_lane_evidence_ranking_records,
)
from src.app.hammer_radar.operator.signal_origin_registry import (
    DETECTOR_AVAILABLE,
    INFERRED_FROM_EXISTING_FIELDS,
    REGISTRY_ONLY,
    UNKNOWN,
    UNKNOWN_ORIGIN,
)
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY

SIGNAL_ORIGIN_LANE_MATRIX_READY = "SIGNAL_ORIGIN_LANE_MATRIX_READY"
SIGNAL_ORIGIN_LANE_MATRIX_REJECTED = "SIGNAL_ORIGIN_LANE_MATRIX_REJECTED"
SIGNAL_ORIGIN_LANE_MATRIX_RECORDED = "SIGNAL_ORIGIN_LANE_MATRIX_RECORDED"
SIGNAL_ORIGIN_LANE_MATRIX_BLOCKED = "SIGNAL_ORIGIN_LANE_MATRIX_BLOCKED"
SIGNAL_ORIGIN_LANE_MATRIX_ERROR = "SIGNAL_ORIGIN_LANE_MATRIX_ERROR"

PAIR_READY_FOR_PAPER_TRACKING = "PAIR_READY_FOR_PAPER_TRACKING"
PAIR_NEEDS_MORE_FRESH_CAPTURES = "PAIR_NEEDS_MORE_FRESH_CAPTURES"
PAIR_NEEDS_DETECTOR = "PAIR_NEEDS_DETECTOR"
PAIR_NEEDS_MORE_TAGGED_DATA = "PAIR_NEEDS_MORE_TAGGED_DATA"
PAIR_REFERENCE_ONLY = "PAIR_REFERENCE_ONLY"
PAIR_NOT_LIVE_AUTHORIZED = "PAIR_NOT_LIVE_AUTHORIZED"
PAIR_UNKNOWN = "PAIR_UNKNOWN"

EVENT_TYPE = "SIGNAL_ORIGIN_LANE_MATRIX"
LEDGER_FILENAME = "signal_origin_lane_matrix.ndjson"
CONFIRM_SIGNAL_ORIGIN_LANE_MATRIX_RECORDING_PHRASE = (
    "I CONFIRM SIGNAL ORIGIN LANE MATRIX RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_RANKING_RECORDS = 100
DEFAULT_LATEST_SCORING_RECORDS = 100
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
    "lane_promoted": False,
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{MULTI_LANE_RANKING_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{KETER_SIGNAL_ORIGIN_SCORING_LEDGER_FILENAME}",
    "logs/hammer_radar_forward/signal_origin_registry.ndjson",
    "logs/hammer_radar_forward/multi_lane_paper_harvester.ndjson",
    "logs/hammer_radar_forward/short_paper_evidence_capture.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
    "operator.multi_lane_evidence_ranking.build_multi_lane_evidence_ranking",
    "operator.keter_signal_origin_scoring.build_keter_signal_origin_scoring",
]


def build_signal_origin_lane_matrix(
    *,
    log_dir: str | Path | None = None,
    latest_ranking_records: int = DEFAULT_LATEST_RANKING_RECORDS,
    latest_scoring_records: int = DEFAULT_LATEST_SCORING_RECORDS,
    record_matrix: bool = False,
    confirm_signal_origin_lane_matrix: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_signal_origin_lane_matrix == CONFIRM_SIGNAL_ORIGIN_LANE_MATRIX_RECORDING_PHRASE
    try:
        ranking = load_latest_multi_lane_evidence_ranking(
            log_dir=resolved_log_dir,
            latest_ranking_records=latest_ranking_records,
            now=generated_at,
        )
        scoring = load_latest_keter_signal_origin_scoring(
            log_dir=resolved_log_dir,
            latest_scoring_records=latest_scoring_records,
            now=generated_at,
        )
        pairs = build_lane_origin_pairs(ranking=ranking, scoring=scoring)
        current_best = build_current_best_lane_origin_pair(pairs)
        detector_priority_pairs = build_detector_priority_lane_origin_pairs(
            ranking=ranking,
            scoring=scoring,
            pairs=pairs,
        )
        next_actions = build_matrix_next_actions(
            current_best_pair=current_best,
            detector_priority_pairs=detector_priority_pairs,
            pairs=pairs,
        )
        status = SIGNAL_ORIGIN_LANE_MATRIX_READY if pairs else SIGNAL_ORIGIN_LANE_MATRIX_BLOCKED
        if record_matrix and not confirmation_valid:
            status = SIGNAL_ORIGIN_LANE_MATRIX_REJECTED
        elif record_matrix and confirmation_valid:
            status = SIGNAL_ORIGIN_LANE_MATRIX_RECORDED
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "matrix_recorded": False,
            "matrix_id": None,
            "record_matrix_requested": bool(record_matrix),
            "confirmation_valid": bool(confirmation_valid),
            "lane_origin_matrix": pairs,
            "current_best_pair": current_best,
            "detector_priority_pairs": detector_priority_pairs,
            "matrix_summary": _matrix_summary(pairs, current_best),
            "recommended_next_operator_move": next_actions["recommended_next_operator_move"],
            "recommended_next_engineering_move": next_actions["recommended_next_engineering_move"],
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "ranking_source": ranking.get("ranking_source"),
            "scoring_source": scoring.get("scoring_source"),
        }
        if record_matrix and confirmation_valid:
            record = append_signal_origin_lane_matrix_record(payload, log_dir=resolved_log_dir)
            payload["matrix_recorded"] = True
            payload["matrix_id"] = record["matrix_id"]
            payload["ledger_path"] = str(signal_origin_lane_matrix_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": SIGNAL_ORIGIN_LANE_MATRIX_ERROR,
                "generated_at": generated_at.isoformat(),
                "matrix_recorded": False,
                "matrix_id": None,
                "record_matrix_requested": bool(record_matrix),
                "confirmation_valid": bool(confirmation_valid),
                "lane_origin_matrix": [],
                "current_best_pair": None,
                "detector_priority_pairs": [],
                "matrix_summary": _matrix_summary([], None),
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R184 matrix error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_latest_multi_lane_evidence_ranking(
    *,
    log_dir: str | Path | None = None,
    latest_ranking_records: int = DEFAULT_LATEST_RANKING_RECORDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    records = load_multi_lane_evidence_ranking_records(
        log_dir=log_dir,
        limit=_bounded_int(latest_ranking_records, 1, MAX_LATEST_RECORDS, DEFAULT_LATEST_RANKING_RECORDS),
    )
    if records:
        latest = dict(records[0])
        latest["ranking_source"] = "multi_lane_evidence_ranking_ledger"
        return latest
    preview = build_multi_lane_evidence_ranking(log_dir=log_dir, record_ranking=False, now=now)
    preview["ranking_source"] = "multi_lane_evidence_ranking_preview"
    return preview


def load_latest_keter_signal_origin_scoring(
    *,
    log_dir: str | Path | None = None,
    latest_scoring_records: int = DEFAULT_LATEST_SCORING_RECORDS,
    now: datetime | None = None,
) -> dict[str, Any]:
    records = load_keter_signal_origin_scoring_records(
        log_dir=log_dir,
        limit=_bounded_int(latest_scoring_records, 1, MAX_LATEST_RECORDS, DEFAULT_LATEST_SCORING_RECORDS),
    )
    if records:
        latest = dict(records[0])
        latest["scoring_source"] = "keter_signal_origin_scoring_ledger"
        return latest
    preview = build_keter_signal_origin_scoring(log_dir=log_dir, record_scoring=False, now=now)
    preview["scoring_source"] = "keter_signal_origin_scoring_preview"
    return preview


def build_lane_origin_pairs(*, ranking: Mapping[str, Any], scoring: Mapping[str, Any]) -> list[dict[str, Any]]:
    origins = [row for row in scoring.get("keter_origin_rankings") or [] if isinstance(row, Mapping)]
    by_lane_origin = scoring.get("by_lane_origin_scores") or {}
    pairs = []
    for lane in ranking.get("ranked_lanes") or []:
        if not isinstance(lane, Mapping):
            continue
        lane_key = str(lane.get("lane_key") or "")
        lane_origin_counts = {
            str(row.get("signal_origin") or UNKNOWN_ORIGIN): int(row.get("tagged_record_count") or 0)
            for row in by_lane_origin.get(lane_key, [])
            if isinstance(row, Mapping)
        }
        for origin in origins:
            tagged_count = lane_origin_counts.get(str(origin.get("signal_origin") or UNKNOWN_ORIGIN), 0)
            pair = score_lane_origin_pair(lane=lane, origin=origin, tagged_record_count_for_lane=tagged_count)
            pairs.append(pair)
    return sorted(
        pairs,
        key=lambda row: (
            -int(row["pair_score"]),
            str(row["pair_readiness"]) != PAIR_READY_FOR_PAPER_TRACKING,
            str(row["lane_key"]) != DEFAULT_TARGET_LANE_KEY,
            str(row["signal_origin"]),
        ),
    )


def score_lane_origin_pair(
    *,
    lane: Mapping[str, Any],
    origin: Mapping[str, Any],
    tagged_record_count_for_lane: int | None = None,
) -> dict[str, Any]:
    lane_key = str(lane.get("lane_key") or "")
    signal_origin = str(origin.get("signal_origin") or UNKNOWN_ORIGIN)
    lane_score = _bounded_int(lane.get("score"), 0, 100, 0)
    origin_score = _bounded_int(origin.get("keter_score"), 0, 100, 0)
    fresh_count = _bounded_int(lane.get("fresh_capture_count"), 0, 1_000_000, 0)
    required = max(1, _bounded_int(lane.get("fresh_threshold_required"), 1, 1_000_000, 10))
    threshold_met = bool(lane.get("fresh_threshold_met"))
    threshold_progress_score = min(100, int(round((fresh_count / required) * 100)))
    tagged_count = _bounded_int(tagged_record_count_for_lane, 0, 1_000_000, 0)
    tagged_density_score = min(100, tagged_count)
    availability = str(origin.get("availability") or UNKNOWN)
    reference_only = bool(lane.get("reference_only")) or str(lane.get("mode") or "").startswith("tiny_live")
    raw_score = round(
        lane_score * 0.40
        + origin_score * 0.35
        + tagged_density_score * 0.15
        + threshold_progress_score * 0.10
    )
    score = int(raw_score)
    blockers = ["no live authorization in R184"]
    if availability == REGISTRY_ONLY:
        score -= 35
        blockers.append("detector unavailable; registry-only origins cannot be trade-ready")
    if signal_origin == UNKNOWN_ORIGIN or availability == UNKNOWN:
        score -= 45
        blockers.append("origin is unknown/unclassified")
    if reference_only:
        score -= 25
        blockers.append("reference-only tiny-live lane cannot become a new paper candidate door")
    if fresh_count <= 0:
        blockers.append("no fresh captures for this lane; stale activity cannot create readiness")
    elif not threshold_met:
        blockers.append("fresh capture count below threshold")
    if tagged_count <= 0:
        blockers.append("tagged lane/origin paper evidence unavailable")
    if availability == REGISTRY_ONLY:
        score = min(score, 49)
    if signal_origin == UNKNOWN_ORIGIN:
        score = min(score, 19)
    if reference_only:
        score = min(score, 69)
    score = max(0, min(100, score))
    readiness = classify_lane_origin_pair_readiness(
        lane=lane,
        origin=origin,
        pair_score=score,
        tagged_record_count_for_lane=tagged_count,
    )
    why = _pair_why(
        lane_key=lane_key,
        signal_origin=signal_origin,
        availability=availability,
        readiness=readiness,
        pair_score=score,
        fresh_count=fresh_count,
        required=required,
        tagged_count=tagged_count,
        reference_only=reference_only,
    )
    return _sanitize(
        {
            "lane_key": lane_key,
            "signal_origin": signal_origin,
            "lane_score": lane_score,
            "origin_keter_score": origin_score,
            "pair_score": score,
            "pair_readiness": readiness,
            "fresh_capture_count": fresh_count,
            "required_fresh_capture_count": required,
            "threshold_met": threshold_met,
            "origin_availability": availability,
            "tagged_record_count_for_lane": tagged_count,
            "paper_only": True,
            "live_authorized": False,
            "reference_only": reference_only,
            "lane_promoted": False,
            "signal_origin_promoted": False,
            "score_inputs": {
                "lane_score": lane_score,
                "origin_keter_score": origin_score,
                "tagged_density_score": tagged_density_score,
                "threshold_progress_score": threshold_progress_score,
            },
            "why": why,
            "blockers": _dedupe(blockers),
        }
    )


def classify_lane_origin_pair_readiness(
    *,
    lane: Mapping[str, Any],
    origin: Mapping[str, Any],
    pair_score: int,
    tagged_record_count_for_lane: int,
) -> str:
    signal_origin = str(origin.get("signal_origin") or UNKNOWN_ORIGIN)
    availability = str(origin.get("availability") or UNKNOWN)
    reference_only = bool(lane.get("reference_only")) or str(lane.get("mode") or "").startswith("tiny_live")
    if reference_only:
        return PAIR_REFERENCE_ONLY
    if signal_origin == UNKNOWN_ORIGIN or availability == UNKNOWN:
        return PAIR_UNKNOWN
    if availability == REGISTRY_ONLY:
        return PAIR_NEEDS_DETECTOR
    if tagged_record_count_for_lane <= 0:
        return PAIR_NEEDS_MORE_TAGGED_DATA
    if int(lane.get("fresh_capture_count") or 0) <= 0:
        return PAIR_NEEDS_MORE_FRESH_CAPTURES
    if pair_score >= 50 and availability in {DETECTOR_AVAILABLE, INFERRED_FROM_EXISTING_FIELDS}:
        return PAIR_READY_FOR_PAPER_TRACKING
    return PAIR_NOT_LIVE_AUTHORIZED


def build_current_best_lane_origin_pair(pairs: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    ready = [row for row in pairs if row.get("pair_readiness") == PAIR_READY_FOR_PAPER_TRACKING]
    candidates = ready or [row for row in pairs if row.get("pair_readiness") not in {PAIR_NEEDS_DETECTOR, PAIR_REFERENCE_ONLY, PAIR_UNKNOWN}]
    if not candidates:
        return None
    best = sorted(
        candidates,
        key=lambda row: (
            -int(row.get("pair_score") or 0),
            str(row.get("lane_key") or "") != DEFAULT_TARGET_LANE_KEY,
            str(row.get("signal_origin") or ""),
        ),
    )[0]
    return {
        "lane_key": best.get("lane_key"),
        "signal_origin": best.get("signal_origin"),
        "pair_score": best.get("pair_score"),
        "pair_readiness": best.get("pair_readiness"),
        "why": best.get("why"),
        "live_authorized": False,
        "paper_only": True,
    }


def build_detector_priority_lane_origin_pairs(
    *,
    ranking: Mapping[str, Any],
    scoring: Mapping[str, Any],
    pairs: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    lane_keys = [str(row.get("lane_key") or "") for row in ranking.get("ranked_lanes") or [] if isinstance(row, Mapping)]
    lead_lane = DEFAULT_TARGET_LANE_KEY if DEFAULT_TARGET_LANE_KEY in lane_keys else (lane_keys[0] if lane_keys else DEFAULT_TARGET_LANE_KEY)
    priorities = {str(row.get("signal_origin") or UNKNOWN_ORIGIN): row for row in scoring.get("detector_priority_recommendations") or [] if isinstance(row, Mapping)}
    result = []
    for pair in pairs:
        origin = str(pair.get("signal_origin") or UNKNOWN_ORIGIN)
        if pair.get("pair_readiness") != PAIR_NEEDS_DETECTOR:
            continue
        priority_row = priorities.get(origin, {})
        priority = str(priority_row.get("priority") or ("HIGH" if origin == "three_black_crows" else "LOW"))
        lane_key = str(pair.get("lane_key") or "")
        if origin == "three_black_crows" and lane_key != lead_lane:
            continue
        if origin == "three_black_crows":
            why = "operator-prioritized bearish origin for current lead lane, but detector missing"
        else:
            why = str(priority_row.get("reason") or f"{origin} is registry-only and needs detector work before paper readiness.")
        result.append(
            {
                "lane_key": lane_key,
                "signal_origin": origin,
                "priority": priority,
                "pair_score": pair.get("pair_score"),
                "why": why,
                "paper_only": True,
                "live_authorized": False,
            }
        )
    return sorted(result, key=lambda row: (_priority_sort(str(row["priority"])), str(row["lane_key"]), str(row["signal_origin"])))


def build_matrix_next_actions(
    *,
    current_best_pair: Mapping[str, Any] | None,
    detector_priority_pairs: list[Mapping[str, Any]],
    pairs: list[Mapping[str, Any]],
) -> dict[str, str]:
    operator_moves = ["KEEP_MULTI_LANE_HARVESTER_RUNNING", "KEEP_8M_SHORT_WATCHER_RUNNING"]
    if any(row.get("signal_origin") == "three_black_crows" and row.get("priority") == "HIGH" for row in detector_priority_pairs):
        operator_moves.append("RUN_R185_THREE_BLACK_CROWS_DETECTOR_PREVIEW")
    if current_best_pair:
        engineering = (
            f"Run R185 Three Black Crows detector preview for {DEFAULT_TARGET_LANE_KEY}; keep "
            f"{current_best_pair.get('lane_key')} + {current_best_pair.get('signal_origin')} as paper-tracking lead only."
        )
    elif pairs:
        engineering = "Keep harvesting and rerun R184 after more tagged lane/origin evidence; no config or live changes."
    else:
        engineering = "Rebuild R181/R183 local ledgers, then rerun R184 preview only."
    return {
        "recommended_next_operator_move": "|".join(_dedupe(operator_moves)),
        "recommended_next_engineering_move": engineering,
    }


def append_signal_origin_lane_matrix_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = signal_origin_lane_matrix_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "matrix_id": str(record.get("matrix_id") or f"r184_signal_origin_lane_matrix_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_matrix_requested": bool(record.get("record_matrix_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "lane_origin_matrix": list(record.get("lane_origin_matrix") or []),
            "current_best_pair": record.get("current_best_pair"),
            "detector_priority_pairs": list(record.get("detector_priority_pairs") or []),
            "matrix_summary": dict(record.get("matrix_summary") or {}),
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


def load_signal_origin_lane_matrix_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = signal_origin_lane_matrix_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_signal_origin_lane_matrix_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    best = latest.get("current_best_pair") if isinstance(latest.get("current_best_pair"), Mapping) else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_matrix_id": latest.get("matrix_id"),
        "last_best_lane": best.get("lane_key"),
        "last_best_origin": best.get("signal_origin"),
        "safety": dict(SAFETY),
    }


def signal_origin_lane_matrix_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_signal_origin_lane_matrix_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _matrix_summary(pairs: list[Mapping[str, Any]], current_best: Mapping[str, Any] | None) -> dict[str, Any]:
    readiness_counts = Counter(str(row.get("pair_readiness") or PAIR_UNKNOWN) for row in pairs)
    return {
        "pairs_scored": len(pairs),
        "paper_tracking_pairs": int(readiness_counts.get(PAIR_READY_FOR_PAPER_TRACKING, 0)),
        "detector_needed_pairs": int(readiness_counts.get(PAIR_NEEDS_DETECTOR, 0)),
        "reference_only_pairs": int(readiness_counts.get(PAIR_REFERENCE_ONLY, 0)),
        "top_lane": (current_best or {}).get("lane_key"),
        "top_origin": (current_best or {}).get("signal_origin"),
    }


def _pair_why(
    *,
    lane_key: str,
    signal_origin: str,
    availability: str,
    readiness: str,
    pair_score: int,
    fresh_count: int,
    required: int,
    tagged_count: int,
    reference_only: bool,
) -> str:
    if reference_only:
        return f"{lane_key} is reference-only; {signal_origin} can inform comparison but cannot become a new paper door."
    if availability == REGISTRY_ONLY:
        return f"{signal_origin} is detector-priority only for {lane_key}; registry-only origins are not trade-ready."
    if signal_origin == UNKNOWN_ORIGIN:
        return f"{lane_key} has unknown origin evidence; unknown origins are reference/audit only."
    if tagged_count <= 0:
        return f"{lane_key} + {signal_origin} needs tagged lane/origin paper records before tracking readiness."
    if fresh_count < required:
        return f"{lane_key} + {signal_origin} leads paper tracking with score {pair_score}, but fresh captures remain below threshold."
    if readiness == PAIR_READY_FOR_PAPER_TRACKING:
        return f"{lane_key} + {signal_origin} has lane score, Keter score, tagged data, and fresh captures for paper tracking only."
    return f"{lane_key} + {signal_origin} scored {pair_score}; it remains paper-only and not live-authorized."


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
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
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
