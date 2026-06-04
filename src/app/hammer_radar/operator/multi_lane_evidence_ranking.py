"""R181 multi-lane evidence ranking and next-door selection.

This module ranks local paper evidence only. It does not call Binance, create
order payloads, mutate env/config, change lane modes, or authorize execution.
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
from src.app.hammer_radar.operator.lane_control import DEFAULT_CONFIG_PATH, SAFETY_FALSE
from src.app.hammer_radar.operator.multi_lane_paper_capture_harvester import (
    DEFAULT_CAPTURE_THRESHOLD_PER_LANE,
    HEARTBEAT_LEDGER_FILENAME as MULTI_LANE_HEARTBEAT_LEDGER_FILENAME,
    LEDGER_FILENAME as MULTI_LANE_HARVEST_LEDGER_FILENAME,
    build_lane_capture_counts,
    build_multi_lane_harvest_scope,
    load_multi_lane_harvester_records,
    multi_lane_harvester_heartbeats_path,
)
from src.app.hammer_radar.operator.paper_execution import load_paper_executions
from src.app.hammer_radar.operator.promotion_candidate_audit import (
    build_lane_family_performance_summary,
    load_recent_expanded_paper_watch_records,
    load_recent_outcome_records,
)
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import LEDGER_FILENAME as SHORT_CAPTURE_LEDGER_FILENAME
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY, MIN_FRESH_CANDIDATES
from src.app.hammer_radar.operator.capture_count_sync_8m_short import load_short_capture_records

MULTI_LANE_EVIDENCE_RANKING_READY = "MULTI_LANE_EVIDENCE_RANKING_READY"
MULTI_LANE_EVIDENCE_RANKING_REJECTED = "MULTI_LANE_EVIDENCE_RANKING_REJECTED"
MULTI_LANE_EVIDENCE_RANKING_RECORDED = "MULTI_LANE_EVIDENCE_RANKING_RECORDED"
MULTI_LANE_EVIDENCE_RANKING_BLOCKED = "MULTI_LANE_EVIDENCE_RANKING_BLOCKED"
MULTI_LANE_EVIDENCE_RANKING_ERROR = "MULTI_LANE_EVIDENCE_RANKING_ERROR"

KEEP_HARVESTING_INSUFFICIENT_EVIDENCE = "KEEP_HARVESTING_INSUFFICIENT_EVIDENCE"
EIGHT_M_SHORT_REMAINS_LEAD = "EIGHT_M_SHORT_REMAINS_LEAD"
NEW_LANE_CANDIDATE_EMERGED = "NEW_LANE_CANDIDATE_EMERGED"
ONE_OR_MORE_LANES_READY_FOR_EVIDENCE_RECHECK = "ONE_OR_MORE_LANES_READY_FOR_EVIDENCE_RECHECK"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "MULTI_LANE_EVIDENCE_RANKING"
LEDGER_FILENAME = "multi_lane_evidence_rankings.ndjson"
CONFIRM_MULTI_LANE_RANKING_RECORDING_PHRASE = (
    "I CONFIRM MULTI LANE EVIDENCE RANKING RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_HARVEST_RECORDS = 5000
DEFAULT_LATEST_SINGLE_LANE_CAPTURES = 5000
DEFAULT_LATEST_WATCH_RECORDS = 1000
DEFAULT_LATEST_OUTCOMES = 10000

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
}

SOURCE_SURFACES_USED = [
    f"logs/hammer_radar_forward/{MULTI_LANE_HARVEST_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{MULTI_LANE_HEARTBEAT_LEDGER_FILENAME}",
    f"logs/hammer_radar_forward/{SHORT_CAPTURE_LEDGER_FILENAME}",
    "logs/hammer_radar_forward/expanded_paper_watch.ndjson",
    "logs/hammer_radar_forward/outcomes.ndjson",
    "logs/hammer_radar_forward/paper_executions.ndjson",
    "operator.multi_lane_paper_capture_harvester.build_multi_lane_harvest_scope",
    "operator.multi_lane_paper_capture_harvester.build_lane_capture_counts",
    "operator.capture_count_sync_8m_short.load_short_capture_records",
    "operator.promotion_candidate_audit.build_lane_family_performance_summary",
]


def build_multi_lane_evidence_ranking(
    *,
    log_dir: str | Path | None = None,
    latest_harvest_records: int = DEFAULT_LATEST_HARVEST_RECORDS,
    latest_single_lane_captures: int = DEFAULT_LATEST_SINGLE_LANE_CAPTURES,
    latest_watch_records: int = DEFAULT_LATEST_WATCH_RECORDS,
    latest_outcomes: int = DEFAULT_LATEST_OUTCOMES,
    fresh_threshold_required: int = DEFAULT_CAPTURE_THRESHOLD_PER_LANE,
    record_ranking: bool = False,
    confirm_multi_lane_ranking: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_multi_lane_ranking == CONFIRM_MULTI_LANE_RANKING_RECORDING_PHRASE
    try:
        scope = build_multi_lane_harvest_scope(config_path=config_path or DEFAULT_CONFIG_PATH)
        harvest_records = load_multi_lane_harvest_records(log_dir=resolved_log_dir, limit=latest_harvest_records)
        single_lane_records = load_single_lane_capture_records(
            log_dir=resolved_log_dir,
            lane_key=DEFAULT_TARGET_LANE_KEY,
            limit=latest_single_lane_captures,
        )
        watch_records = load_recent_expanded_paper_watch_records(log_dir=resolved_log_dir, limit=latest_watch_records)
        outcome_records = load_recent_outcome_records(log_dir=resolved_log_dir, limit=latest_outcomes)
        paper_execution_records = load_paper_executions(limit=0, log_dir=resolved_log_dir)
        capture_counts = build_lane_capture_counts(
            log_dir=resolved_log_dir,
            scope=scope,
            required_fresh_capture_count=fresh_threshold_required,
            config_path=config_path,
        )
        flow = _aggregate_harvest_flow(harvest_records=harvest_records, watch_records=watch_records)
        lanes = [*scope.get("paper_lanes", []), *scope.get("observed_tiny_live_lanes", [])]
        ranked_lanes = []
        for lane in lanes:
            evidence = build_lane_evidence_summary(
                lane=lane,
                capture_counts=capture_counts,
                flow=flow,
                single_lane_records=single_lane_records,
                fresh_threshold_required=fresh_threshold_required,
            )
            historical = build_lane_historical_performance_summary(
                lane=lane,
                outcome_records=outcome_records,
                paper_execution_records=paper_execution_records,
            )
            score = score_lane_candidate(lane=lane, evidence=evidence, historical=historical)
            readiness = classify_lane_readiness(lane=lane, evidence=evidence, historical=historical, score=score)
            ranked_lanes.append(
                {
                    "lane_key": lane["lane_key"],
                    "mode": _ranking_mode(lane),
                    "fresh_capture_count": evidence["fresh_capture_count"],
                    "fresh_threshold_required": evidence["fresh_threshold_required"],
                    "fresh_threshold_met": evidence["fresh_threshold_met"],
                    "historical_win_rate_pct": historical["win_rate_pct"],
                    "avg_pnl_pct": historical["avg_pnl_pct"],
                    "paper_outcome_count": historical["paper_outcome_count"],
                    "score": score,
                    "score_band": _score_band(score),
                    "readiness": readiness,
                    "why": _why(lane=lane, evidence=evidence, historical=historical, score=score, readiness=readiness),
                    "blockers": build_ranking_blockers(lane=lane, evidence=evidence, historical=historical, readiness=readiness),
                    "fresh_by_lane": evidence["fresh_by_lane"],
                    "stale_by_lane": evidence["stale_by_lane"],
                    "historical_total_pnl_pct": historical["total_pnl_pct"],
                    "direction_pressure": evidence["direction_pressure"],
                    "short_strategy_scaffolding_present": evidence["short_strategy_scaffolding_present"],
                    "reference_only": lane.get("mode") == "tiny_live",
                }
            )
        ranked_lanes = sorted(ranked_lanes, key=lambda row: (-int(row["score"]), -int(row["fresh_capture_count"]), _lane_sort_key(row["lane_key"])))
        current_lead = _current_lead(ranked_lanes)
        next_door = build_next_door_selection(ranked_lanes=ranked_lanes, current_lead=current_lead)
        harvest_summary = _build_harvest_summary(harvest_records=harvest_records, flow=flow)
        blockers = _build_top_blockers(ranked_lanes=ranked_lanes, next_door=next_door)
        status = MULTI_LANE_EVIDENCE_RANKING_READY if ranked_lanes else MULTI_LANE_EVIDENCE_RANKING_BLOCKED
        if record_ranking and not confirmation_valid:
            status = MULTI_LANE_EVIDENCE_RANKING_REJECTED
        elif record_ranking and confirmation_valid:
            status = MULTI_LANE_EVIDENCE_RANKING_RECORDED
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "ranking_recorded": False,
            "ranking_id": None,
            "record_ranking_requested": bool(record_ranking),
            "confirmation_valid": bool(confirmation_valid),
            "ranked_lanes": ranked_lanes,
            "current_lead": current_lead,
            "next_door_selection": next_door,
            "harvest_summary": harvest_summary,
            "blockers": blockers,
            "recommended_next_operator_move": _recommended_next_operator_move(next_door=next_door, current_lead=current_lead),
            "recommended_next_engineering_move": _recommended_next_engineering_move(next_door=next_door),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_ranking and confirmation_valid:
            record = append_multi_lane_evidence_ranking_record(payload, log_dir=resolved_log_dir)
            payload["ranking_recorded"] = True
            payload["ranking_id"] = record["ranking_id"]
            payload["ledger_path"] = str(multi_lane_evidence_ranking_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": MULTI_LANE_EVIDENCE_RANKING_ERROR,
                "generated_at": generated_at.isoformat(),
                "ranking_recorded": False,
                "ranking_id": None,
                "record_ranking_requested": bool(record_ranking),
                "confirmation_valid": bool(confirmation_valid),
                "ranked_lanes": [],
                "current_lead": {"lane_key": DEFAULT_TARGET_LANE_KEY, "reason": "ranking builder error", "fresh_capture_count": 0},
                "next_door_selection": {
                    "selected_lane": DEFAULT_TARGET_LANE_KEY,
                    "selection_type": "KEEP_HARVESTING",
                    "confidence": "LOW",
                    "why": "R181 ranking hit a build error; manual review is required.",
                    "next_required_phase": "R182",
                },
                "harvest_summary": _empty_harvest_summary(),
                "blockers": ["R181 ranking build error must be fixed before selecting any next door"],
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R181 ranking error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def load_multi_lane_harvest_records(*, log_dir: str | Path | None = None, limit: int = DEFAULT_LATEST_HARVEST_RECORDS) -> list[dict[str, Any]]:
    return load_multi_lane_harvester_records(log_dir=log_dir, limit=max(0, int(limit)))


def load_single_lane_capture_records(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    limit: int = DEFAULT_LATEST_SINGLE_LANE_CAPTURES,
) -> list[dict[str, Any]]:
    return load_short_capture_records(log_dir=log_dir, lane_key=lane_key, limit=max(0, int(limit)))


def build_lane_evidence_summary(
    *,
    lane: Mapping[str, Any],
    capture_counts: Mapping[str, Any],
    flow: Mapping[str, Any],
    single_lane_records: list[Mapping[str, Any]] | None = None,
    fresh_threshold_required: int = DEFAULT_CAPTURE_THRESHOLD_PER_LANE,
) -> dict[str, Any]:
    lane_key = str(lane.get("lane_key") or "")
    count_row = dict((capture_counts or {}).get(lane_key) or {})
    single_ids = []
    if lane_key == DEFAULT_TARGET_LANE_KEY:
        for record in single_lane_records or []:
            if record.get("paper_evidence_captured") is True:
                signal_id = str(record.get("captured_signal_id") or "").strip()
                if signal_id and signal_id not in single_ids:
                    single_ids.append(signal_id)
    fresh_count = max(int(count_row.get("fresh_capture_count") or 0), len(single_ids))
    required = int(count_row.get("required_fresh_capture_count") or fresh_threshold_required)
    fresh_by_lane = int((flow.get("fresh_by_lane") or {}).get(lane_key) or 0)
    stale_by_lane = int((flow.get("stale_by_lane") or {}).get(lane_key) or 0)
    direction = str(lane.get("direction") or "").strip().lower()
    return {
        "fresh_capture_count": fresh_count,
        "fresh_threshold_required": required,
        "fresh_threshold_met": fresh_count >= required,
        "fresh_threshold_progress_pct": round((fresh_count / required) * 100.0, 2) if required else 0.0,
        "fresh_by_lane": fresh_by_lane,
        "stale_by_lane": stale_by_lane,
        "observed_tiny_live_by_lane": int((flow.get("observed_tiny_live_by_lane") or {}).get(lane_key) or 0),
        "direction_pressure": int((flow.get("direction_pressure") or {}).get(direction) or 0),
        "short_strategy_scaffolding_present": lane_key == DEFAULT_TARGET_LANE_KEY,
    }


def build_lane_historical_performance_summary(
    *,
    lane: Mapping[str, Any],
    outcome_records: list[Mapping[str, Any]] | None = None,
    paper_execution_records: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return build_lane_family_performance_summary(
        lane,
        outcome_records=outcome_records or [],
        paper_execution_records=paper_execution_records or [],
    )


def score_lane_candidate(*, lane: Mapping[str, Any], evidence: Mapping[str, Any], historical: Mapping[str, Any]) -> int:
    score = 0
    fresh_count = int(evidence.get("fresh_capture_count") or 0)
    required = max(1, int(evidence.get("fresh_threshold_required") or MIN_FRESH_CANDIDATES))
    fresh_by_lane = int(evidence.get("fresh_by_lane") or 0)
    stale_by_lane = int(evidence.get("stale_by_lane") or 0)
    outcomes = int(historical.get("paper_outcome_count") or 0)
    win_rate = _number_or_none(historical.get("win_rate_pct"))
    avg_pnl = _number_or_none(historical.get("avg_pnl_pct"))
    total_pnl = _number_or_none(historical.get("total_pnl_pct"))

    score += min(45, int((fresh_count / required) * 45))
    score += min(10, fresh_by_lane * 2)
    score += min(5, stale_by_lane // 10)
    score += min(15, int((outcomes / 30) * 15)) if outcomes else 0
    if win_rate is not None:
        score += 10 if win_rate >= 52.0 else max(0, int((win_rate / 52.0) * 7))
    if avg_pnl is not None and avg_pnl > 0:
        score += 8
    if total_pnl is not None and total_pnl > 0:
        score += 4
    if lane.get("mode") == "paper":
        score += 3
    if lane.get("mode") == "tiny_live":
        score -= 15
    if evidence.get("short_strategy_scaffolding_present"):
        score += 5
    return max(0, min(100, score))


def classify_lane_readiness(*, lane: Mapping[str, Any], evidence: Mapping[str, Any], historical: Mapping[str, Any], score: int) -> str:
    if lane.get("mode") == "tiny_live":
        return KEEP_HARVESTING_INSUFFICIENT_EVIDENCE
    if int(evidence.get("fresh_capture_count") or 0) <= 0 and int(evidence.get("fresh_by_lane") or 0) <= 0:
        return KEEP_HARVESTING_INSUFFICIENT_EVIDENCE
    if evidence.get("fresh_threshold_met") is True and score >= 75:
        return ONE_OR_MORE_LANES_READY_FOR_EVIDENCE_RECHECK
    if lane.get("lane_key") == DEFAULT_TARGET_LANE_KEY and int(evidence.get("fresh_capture_count") or 0) > 0:
        return EIGHT_M_SHORT_REMAINS_LEAD
    if score >= 85:
        return NEW_LANE_CANDIDATE_EMERGED
    if score >= 40:
        return KEEP_HARVESTING_INSUFFICIENT_EVIDENCE
    return KEEP_HARVESTING_INSUFFICIENT_EVIDENCE


def build_next_door_selection(*, ranked_lanes: list[Mapping[str, Any]], current_lead: Mapping[str, Any]) -> dict[str, Any]:
    paper_rows = [row for row in ranked_lanes if row.get("mode") == "paper"]
    eight = next((row for row in ranked_lanes if row.get("lane_key") == DEFAULT_TARGET_LANE_KEY), None)
    best = paper_rows[0] if paper_rows else None
    if best and best.get("lane_key") != DEFAULT_TARGET_LANE_KEY and int(best.get("fresh_capture_count") or 0) > int((eight or {}).get("fresh_capture_count") or 0):
        return {
            "selected_lane": best["lane_key"],
            "selection_type": "NEW_LANE_CANDIDATE",
            "confidence": "HIGH" if int(best.get("fresh_capture_count") or 0) >= int(best.get("fresh_threshold_required") or 10) else "MEDIUM",
            "why": f"{best['lane_key']} has overtaken 8m short on fresh captured evidence; this is paper-only selection for review.",
            "next_required_phase": "R182",
        }
    if eight and int(eight.get("fresh_capture_count") or 0) >= int(eight.get("fresh_threshold_required") or 10):
        return {
            "selected_lane": DEFAULT_TARGET_LANE_KEY,
            "selection_type": "KEEP_8M_SHORT",
            "confidence": "HIGH",
            "why": "8m short remains lead and has met the fresh capture threshold for R177 evidence recheck.",
            "next_required_phase": "R177",
        }
    if eight and best and best.get("lane_key") == DEFAULT_TARGET_LANE_KEY and int(eight.get("fresh_capture_count") or 0) > 0:
        return {
            "selected_lane": DEFAULT_TARGET_LANE_KEY,
            "selection_type": "KEEP_8M_SHORT",
            "confidence": "MEDIUM",
            "why": "8m short remains the strongest paper lane, but fresh evidence is still below threshold.",
            "next_required_phase": "R177",
        }
    return {
        "selected_lane": DEFAULT_TARGET_LANE_KEY,
        "selection_type": "KEEP_HARVESTING",
        "confidence": "LOW",
        "why": "No paper lane has enough fresh captured evidence to select a new tiny-live candidate door.",
        "next_required_phase": "R182",
    }


def build_ranking_blockers(*, lane: Mapping[str, Any], evidence: Mapping[str, Any], historical: Mapping[str, Any], readiness: str) -> list[str]:
    blockers: list[str] = []
    if lane.get("mode") == "tiny_live":
        blockers.append("tiny-live incumbent is observed as reference only and cannot become a new paper candidate door")
    if int(evidence.get("fresh_capture_count") or 0) < int(evidence.get("fresh_threshold_required") or 10):
        blockers.append("fresh capture count below threshold")
    if int(evidence.get("fresh_capture_count") or 0) <= 0 and int(evidence.get("stale_by_lane") or 0) > 0:
        blockers.append("stale activity exists but stale count alone is not readiness evidence")
    if int(historical.get("paper_outcome_count") or 0) <= 0:
        blockers.append("historical paper outcome sample unavailable")
    if historical.get("avg_pnl_pct") is None:
        blockers.append("avg_pnl_pct unavailable")
    if lane.get("direction") == "short" and lane.get("lane_key") != DEFAULT_TARGET_LANE_KEY:
        blockers.append("short lane needs future short-specific strategy review before any tiny-live path")
    if readiness == UNKNOWN_NEEDS_MANUAL_REVIEW:
        blockers.append("manual review needed before ranking interpretation")
    return _dedupe(blockers)


def append_multi_lane_evidence_ranking_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = multi_lane_evidence_ranking_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "ranking_id": str(record.get("ranking_id") or f"r181_multi_lane_evidence_ranking_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_ranking_requested": bool(record.get("record_ranking_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "ranked_lanes": list(record.get("ranked_lanes") or []),
            "current_lead": dict(record.get("current_lead") or {}),
            "next_door_selection": dict(record.get("next_door_selection") or {}),
            "harvest_summary": dict(record.get("harvest_summary") or {}),
            "blockers": list(record.get("blockers") or []),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_multi_lane_evidence_ranking_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = multi_lane_evidence_ranking_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_multi_lane_evidence_rankings(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_ranking_id": latest.get("ranking_id"),
        "last_selected_lane": (latest.get("next_door_selection") or {}).get("selected_lane"),
        "safety": dict(SAFETY),
    }


def multi_lane_evidence_ranking_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_multi_lane_evidence_ranking_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _aggregate_harvest_flow(*, harvest_records: list[Mapping[str, Any]], watch_records: list[Mapping[str, Any]]) -> dict[str, Any]:
    fresh: Counter[str] = Counter()
    stale: Counter[str] = Counter()
    observed: Counter[str] = Counter()
    direction_pressure: Counter[str] = Counter()
    for record in harvest_records:
        summary = record.get("capture_summary") or {}
        fresh.update({str(key): int(value or 0) for key, value in (summary.get("fresh_by_lane") or {}).items()})
        stale.update({str(key): int(value or 0) for key, value in (summary.get("stale_by_lane") or {}).items()})
        observed.update({str(key): int(value or 0) for key, value in (summary.get("observed_tiny_live_by_lane") or {}).items()})
    for record in watch_records:
        distribution = record.get("candidate_distribution") or {}
        fresh.update({str(key): int(value or 0) for key, value in (distribution.get("fresh_by_lane") or {}).items()})
        stale.update({str(key): int(value or 0) for key, value in (distribution.get("stale_by_lane") or {}).items()})
        for lane_key, value in (distribution.get("by_timeframe_direction") or {}).items():
            parts = str(lane_key).split("|")
            direction = parts[-1] if parts else ""
            if direction:
                direction_pressure[direction] += int(value or 0)
    for lane_key, count in {**fresh, **stale, **observed}.items():
        parts = str(lane_key).split("|")
        if len(parts) >= 3:
            direction_pressure[parts[2]] += int(count or 0)
    return {
        "fresh_by_lane": dict(sorted(fresh.items())),
        "stale_by_lane": dict(sorted(stale.items())),
        "observed_tiny_live_by_lane": dict(sorted(observed.items())),
        "direction_pressure": dict(sorted(direction_pressure.items())),
    }


def _current_lead(ranked_lanes: list[Mapping[str, Any]]) -> dict[str, Any]:
    eight = next((row for row in ranked_lanes if row.get("lane_key") == DEFAULT_TARGET_LANE_KEY), {})
    best = next((row for row in ranked_lanes if row.get("mode") == "paper"), eight)
    if best and best.get("lane_key") != DEFAULT_TARGET_LANE_KEY:
        reason = f"{best.get('lane_key')} currently ranks above 8m short."
    elif int(eight.get("fresh_capture_count") or 0) > 0:
        reason = "8m short remains lead by score and fresh captured evidence."
    else:
        reason = "8m short is the incumbent lead, but fresh captured evidence remains below threshold."
    return {
        "lane_key": DEFAULT_TARGET_LANE_KEY,
        "reason": reason,
        "fresh_capture_count": int(eight.get("fresh_capture_count") or 0),
    }


def _build_harvest_summary(*, harvest_records: list[Mapping[str, Any]], flow: Mapping[str, Any]) -> dict[str, Any]:
    latest = harvest_records[0] if harvest_records else {}
    return {
        "multi_lane_records_found": len(harvest_records),
        "latest_harvest_status": latest.get("harvest_status") or latest.get("status"),
        "lanes_with_fresh_flow": sorted([key for key, value in (flow.get("fresh_by_lane") or {}).items() if int(value or 0) > 0]),
        "lanes_with_only_stale_activity": sorted(
            [
                key
                for key, value in (flow.get("stale_by_lane") or {}).items()
                if int(value or 0) > 0 and int((flow.get("fresh_by_lane") or {}).get(key) or 0) <= 0
            ]
        ),
    }


def _build_top_blockers(*, ranked_lanes: list[Mapping[str, Any]], next_door: Mapping[str, Any]) -> list[str]:
    blockers = []
    if next_door.get("selection_type") == "KEEP_HARVESTING":
        blockers.append("insufficient fresh captured paper evidence for next-door selection")
    if not any(row.get("fresh_threshold_met") for row in ranked_lanes if row.get("mode") == "paper"):
        blockers.append("no paper lane has met the fresh capture threshold")
    blockers.extend(str(item) for row in ranked_lanes[:3] for item in row.get("blockers", [])[:2])
    return _dedupe(blockers)


def _recommended_next_operator_move(*, next_door: Mapping[str, Any], current_lead: Mapping[str, Any]) -> str:
    if next_door.get("selection_type") == "NEW_LANE_CANDIDATE":
        return "RUN_R182_SIGNAL_ORIGIN_REGISTRY"
    if next_door.get("selection_type") == "KEEP_8M_SHORT" and int(current_lead.get("fresh_capture_count") or 0) >= MIN_FRESH_CANDIDATES:
        return "RUN_R177_IF_8M_SHORT_REACHES_10"
    if next_door.get("selection_type") == "KEEP_8M_SHORT":
        return "KEEP_8M_SHORT_WATCHER_RUNNING"
    return "KEEP_MULTI_LANE_HARVESTER_RUNNING"


def _recommended_next_engineering_move(*, next_door: Mapping[str, Any]) -> str:
    if next_door.get("selection_type") == "NEW_LANE_CANDIDATE":
        return "Build R182 signal origin registry and pattern feed expansion for the selected paper lane; keep it paper-only."
    if next_door.get("next_required_phase") == "R177":
        return "Run R177 only after 8m short reaches 10 fresh captures; do not write config or call Binance."
    return "Keep R180 harvesting and add R182 signal-origin tagging if fresh evidence remains dispersed."


def _why(*, lane: Mapping[str, Any], evidence: Mapping[str, Any], historical: Mapping[str, Any], score: int, readiness: str) -> str:
    if lane.get("mode") == "tiny_live":
        return "Reference-only tiny-live incumbent; it informs comparison but cannot auto-promote or become a new door."
    if int(evidence.get("fresh_capture_count") or 0) <= 0 and int(evidence.get("stale_by_lane") or 0) > 0:
        return "Only stale activity is present, so the lane stays in harvest mode."
    if evidence.get("fresh_threshold_met"):
        return "Fresh capture threshold is met; evidence recheck is the next safe paper-only review step."
    if lane.get("lane_key") == DEFAULT_TARGET_LANE_KEY and int(evidence.get("fresh_capture_count") or 0) > 0:
        return "8m short has the strongest captured evidence so far but remains below threshold."
    return f"Score {score} with readiness {readiness}; keep collecting fresh paper evidence before any lane decision."


def _ranking_mode(lane: Mapping[str, Any]) -> str:
    return "tiny_live_observed_reference" if lane.get("mode") == "tiny_live" else str(lane.get("mode") or "paper")


def _score_band(score: int) -> str:
    if score >= 85:
        return "strong next-door candidate, still paper-only"
    if score >= 75:
        return "candidate for evidence recheck"
    if score >= 60:
        return "watchlist"
    if score >= 40:
        return "keep harvesting"
    return "weak"


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


def _empty_harvest_summary() -> dict[str, Any]:
    return {
        "multi_lane_records_found": 0,
        "latest_harvest_status": None,
        "lanes_with_fresh_flow": [],
        "lanes_with_only_stale_activity": [],
    }


def _lane_sort_key(lane_key: object) -> tuple[int, str, str]:
    parts = str(lane_key or "").split("|")
    timeframe = parts[1] if len(parts) > 1 else ""
    direction = parts[2] if len(parts) > 2 else ""
    return (_timeframe_minutes(timeframe), direction, str(lane_key or ""))


def _timeframe_minutes(value: str) -> int:
    text = str(value or "").lower()
    digits = "".join(ch for ch in text if ch.isdigit())
    unit = "".join(ch for ch in text if ch.isalpha())
    multiplier = {"m": 1, "h": 60, "d": 1440}.get(unit or "m", 1)
    return int(digits or 0) * multiplier


def _number_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
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
    if isinstance(value, datetime):
        return value.isoformat()
    return value
