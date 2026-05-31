"""R154 promotion candidate audit from expanded paper evidence.

This module ranks expanded BTCUSDT paper lane families for future review only.
It never promotes lanes, writes lane config, creates order payloads, calls
Binance, mutates env/global flags, or authorizes live execution.
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
from src.app.hammer_radar.operator.expanded_paper_watch import (
    build_expanded_paper_distribution,
    build_expanded_paper_safe_watch_command,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import DEFAULT_CONFIG_PATH, SAFETY_FALSE, load_lane_controls, normalize_lane_key
from src.app.hammer_radar.operator.paper_opportunity_expansion import (
    DEFAULT_TIMEFRAMES,
    TARGET_ENTRY_MODE,
    TARGET_SYMBOL,
    TARGET_TINY_LIVE_LANES,
)
from src.app.hammer_radar.operator.paper_execution import load_paper_executions

PROMOTION_CANDIDATE_AUDIT_READY = "PROMOTION_CANDIDATE_AUDIT_READY"
PROMOTION_CANDIDATE_AUDIT_REJECTED = "PROMOTION_CANDIDATE_AUDIT_REJECTED"
PROMOTION_CANDIDATE_AUDIT_RECORDED = "PROMOTION_CANDIDATE_AUDIT_RECORDED"
PROMOTION_CANDIDATE_AUDIT_BLOCKED = "PROMOTION_CANDIDATE_AUDIT_BLOCKED"
PROMOTION_CANDIDATE_AUDIT_ERROR = "PROMOTION_CANDIDATE_AUDIT_ERROR"

NOT_ENOUGH_EVIDENCE = "NOT_ENOUGH_EVIDENCE"
PAPER_ONLY_CONTINUE_COLLECTING = "PAPER_ONLY_CONTINUE_COLLECTING"
WATCHLIST_FOR_FUTURE_TINY_LIVE = "WATCHLIST_FOR_FUTURE_TINY_LIVE"
STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW = "STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW"
DO_NOT_PROMOTE = "DO_NOT_PROMOTE"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

EVENT_TYPE = "PROMOTION_CANDIDATE_AUDIT"
LEDGER_FILENAME = "promotion_candidate_audits.ndjson"
CONFIRM_PROMOTION_CANDIDATE_AUDIT_RECORDING_PHRASE = (
    "I CONFIRM PROMOTION CANDIDATE AUDIT RECORDING ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_OUTCOMES = 5000
MAX_LATEST_OUTCOMES = 100000
DEFAULT_LATEST_SIGNALS = 2000
MAX_LATEST_SIGNALS = 50000
DEFAULT_LATEST_WATCH_RECORDS = 200
MAX_LATEST_WATCH_RECORDS = 10000

MIN_STRONG_PAPER_OUTCOMES = 30
MIN_FRESH_CANDIDATES = 10
PREFERRED_WIN_RATE_PCT = 52.0

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "network_allowed": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "logs/hammer_radar_forward/outcomes.ndjson",
    "logs/hammer_radar_forward/paper_executions.ndjson",
    "logs/hammer_radar_forward/expanded_paper_watch.ndjson",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    "operator.expanded_paper_watch.build_expanded_paper_distribution",
    "operator.paper_execution.load_paper_executions",
    "operator.lane_control.load_lane_controls",
    "operator.lane_control.normalize_lane_key",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_promotion_candidate_audit(
    *,
    log_dir: str | Path | None = None,
    latest_outcomes: int = DEFAULT_LATEST_OUTCOMES,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_watch_records: int = DEFAULT_LATEST_WATCH_RECORDS,
    include_paper_lanes: bool = False,
    include_tiny_live_incumbents: bool = False,
    record_audit: bool = False,
    confirm_promotion_audit: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_promotion_audit == CONFIRM_PROMOTION_CANDIDATE_AUDIT_RECORDING_PHRASE
    try:
        lanes = _target_lanes(
            config_path=config_path,
            include_paper_lanes=include_paper_lanes,
            include_tiny_live_incumbents=include_tiny_live_incumbents,
        )
        outcomes = load_recent_outcome_records(log_dir=resolved_log_dir, limit=latest_outcomes)
        paper_executions = load_paper_executions(limit=0, log_dir=resolved_log_dir)
        watch_records = load_recent_expanded_paper_watch_records(log_dir=resolved_log_dir, limit=latest_watch_records)
        paper_lanes = [lane for lane in lanes if lane["mode"] == "paper"]
        current_distribution = build_expanded_paper_distribution(
            log_dir=resolved_log_dir,
            paper_lanes=paper_lanes,
            latest_signals=latest_signals,
            latest_scans=latest_signals,
            now=generated_at,
        )

        lane_families: dict[str, Any] = {}
        for lane in lanes:
            lane_key = lane["lane_key"]
            performance = build_lane_family_performance_summary(
                lane,
                outcome_records=outcomes,
                paper_execution_records=paper_executions,
            )
            opportunity = build_lane_family_opportunity_summary(
                lane,
                current_distribution=current_distribution,
                watch_records=watch_records,
            )
            score = score_promotion_candidate_family(performance=performance, opportunity=opportunity)
            readiness = classify_promotion_candidate_readiness(
                lane=lane,
                performance=performance,
                opportunity=opportunity,
                promotion_score=score,
            )
            lane_families[lane_key] = {
                "mode": lane["mode"],
                "direction": lane["direction"],
                "timeframe": lane["timeframe"],
                "entry_mode": lane["entry_mode"],
                "performance": performance,
                "opportunity": opportunity,
                "promotion_score": score,
                "readiness": readiness,
                "why": _why(readiness, lane=lane, performance=performance, opportunity=opportunity),
                "risks": _risks(lane=lane, performance=performance, opportunity=opportunity, readiness=readiness),
                "recommended_next_action": _recommended_lane_action(lane=lane, readiness=readiness),
            }

        ranked = _ranked_candidates(lane_families)
        status = PROMOTION_CANDIDATE_AUDIT_READY if lane_families else PROMOTION_CANDIDATE_AUDIT_BLOCKED
        if record_audit and not confirmation_valid:
            status = PROMOTION_CANDIDATE_AUDIT_REJECTED
        elif record_audit and confirmation_valid:
            status = PROMOTION_CANDIDATE_AUDIT_RECORDED

        short_review = _short_lane_review(lane_families)
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "audit_recorded": False,
            "audit_id": None,
            "record_audit_requested": bool(record_audit),
            "confirmation_valid": bool(confirmation_valid),
            "lane_families": lane_families,
            "ranked_candidates": ranked,
            "incumbent_tiny_live_review": _incumbent_tiny_live_review(lane_families),
            "short_lane_review": short_review,
            "recommended_next_operator_move": _recommended_next_operator_move(ranked, short_review),
            "recommended_next_engineering_move": _recommended_next_engineering_move(ranked, short_review),
            "do_not_run_yet": [
                "live-connector-submit",
                "any order endpoint",
                "global live flag arming",
                "kill switch disable",
                "set short lane tiny_live",
                "set new lane tiny_live",
            ],
            "safe_commands": _safe_commands(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_audit and confirmation_valid:
            record = append_promotion_candidate_audit_record(payload, log_dir=resolved_log_dir)
            payload["audit_recorded"] = True
            payload["audit_id"] = record["audit_id"]
            payload["ledger_path"] = str(promotion_candidate_audit_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": PROMOTION_CANDIDATE_AUDIT_ERROR,
                "generated_at": generated_at.isoformat(),
                "audit_recorded": False,
                "audit_id": None,
                "record_audit_requested": bool(record_audit),
                "confirmation_valid": bool(confirmation_valid),
                "lane_families": {},
                "ranked_candidates": [],
                "incumbent_tiny_live_review": {},
                "short_lane_review": {
                    "shorts_seen": False,
                    "best_short_family": None,
                    "shorts_remain_paper_only": True,
                    "requires_future_short_strategy_review": True,
                },
                "recommended_next_operator_move": "WAIT_FOR_MORE_EVIDENCE",
                "recommended_next_engineering_move": "Fix the R154 audit error before considering any promotion packet.",
                "do_not_run_yet": [
                    "live-connector-submit",
                    "any order endpoint",
                    "global live flag arming",
                    "kill switch disable",
                    "set short lane tiny_live",
                    "set new lane tiny_live",
                ],
                "safe_commands": _safe_commands(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_lane_family_key(lane: Mapping[str, Any] | None = None, /, **kwargs: Any) -> str:
    source = dict(lane or {})
    source.update(kwargs)
    return normalize_lane_key(source.get("symbol"), source.get("timeframe"), source.get("direction"), source.get("entry_mode"))


def load_recent_outcome_records(*, log_dir: str | Path | None = None, limit: int = DEFAULT_LATEST_OUTCOMES) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    bounded = _bounded_int(limit, 1, MAX_LATEST_OUTCOMES, DEFAULT_LATEST_OUTCOMES)
    return [_sanitize(record) for record in read_recent_ndjson_records(resolved_log_dir / "outcomes.ndjson", limit=bounded, max_bytes=64_000_000)]


def load_recent_expanded_paper_watch_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = DEFAULT_LATEST_WATCH_RECORDS,
) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    bounded = _bounded_int(limit, 1, MAX_LATEST_WATCH_RECORDS, DEFAULT_LATEST_WATCH_RECORDS)
    path = resolved_log_dir / "expanded_paper_watch.ndjson"
    if not path.exists():
        return []
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=bounded, max_bytes=32_000_000)]


def build_lane_family_performance_summary(
    lane: Mapping[str, Any],
    *,
    outcome_records: list[Mapping[str, Any]] | None = None,
    paper_execution_records: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    lane_key = str(lane.get("lane_key") or build_lane_family_key(lane))
    matching_attempts = [record for record in outcome_records or [] if _record_lane_key(record) == lane_key]
    filled = [record for record in matching_attempts if _filled(record) and _number_or_none(record.get("pnl_pct")) is not None]
    pnl_values = [float(record.get("pnl_pct")) for record in filled]
    wins = sum(1 for value in pnl_values if value > 0.0)
    losses = sum(1 for value in pnl_values if value <= 0.0)
    stops = sum(1 for record in filled if _stop_hit(record))
    start, end = _evidence_window([*matching_attempts, *(paper_execution_records or [])], lane_key=lane_key)
    execution_count = sum(1 for record in paper_execution_records or [] if _record_lane_key(record) == lane_key)
    attempt_count = len(matching_attempts)
    paper_outcome_count = len(filled)
    return {
        "signal_count": attempt_count,
        "paper_execution_count": execution_count,
        "paper_outcome_count": paper_outcome_count,
        "win_count": wins,
        "loss_count": losses,
        "stop_count": stops,
        "win_rate_pct": round((wins / paper_outcome_count) * 100.0, 2) if paper_outcome_count else None,
        "avg_pnl_pct": round(sum(pnl_values) / paper_outcome_count, 4) if paper_outcome_count else None,
        "total_pnl_pct": round(sum(pnl_values), 4) if paper_outcome_count else None,
        "fill_rate_pct": round((paper_outcome_count / attempt_count) * 100.0, 2) if attempt_count else None,
        "evidence_window_start": start,
        "evidence_window_end": end,
        "sample_count_quality": _sample_quality(paper_outcome_count),
    }


def build_lane_family_opportunity_summary(
    lane: Mapping[str, Any],
    *,
    current_distribution: Mapping[str, Any] | None = None,
    watch_records: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    lane_key = str(lane.get("lane_key") or build_lane_family_key(lane))
    current_fresh = int((current_distribution or {}).get("fresh_by_lane", {}).get(lane_key) or 0)
    current_stale = int((current_distribution or {}).get("stale_by_lane", {}).get(lane_key) or 0)
    fresh = current_fresh
    stale = current_stale
    pressure = Counter()
    starts: list[str] = []
    ends: list[str] = []
    for record in watch_records or []:
        distribution = record.get("candidate_distribution") or {}
        fresh += int((distribution.get("fresh_by_lane") or {}).get(lane_key) or 0)
        stale += int((distribution.get("stale_by_lane") or {}).get(lane_key) or 0)
        for key, value in (distribution.get("by_timeframe_direction") or {}).items():
            if str(key).endswith(f"|{lane.get('direction')}"):
                pressure[str(key)] += int(value or 0)
        for key in ("generated_at", "recorded_at_utc"):
            if record.get(key):
                starts.append(str(record.get(key)))
                ends.append(str(record.get(key)))
    total_candidates = fresh + stale
    return {
        "fresh_candidate_count": fresh,
        "stale_candidate_count": stale,
        "freshness_hit_rate_pct": round((fresh / total_candidates) * 100.0, 2) if total_candidates else None,
        "recent_direction_pressure": dict(sorted(pressure.items())),
        "current_fresh_candidate_count": current_fresh,
        "current_stale_candidate_count": current_stale,
        "expanded_watch_records_checked": len(watch_records or []),
        "evidence_window_start": min(starts) if starts else None,
        "evidence_window_end": max(ends) if ends else None,
        "sample_count_quality": _opportunity_quality(fresh),
    }


def score_promotion_candidate_family(*, performance: Mapping[str, Any], opportunity: Mapping[str, Any]) -> int:
    score = 0
    outcomes = int(performance.get("paper_outcome_count") or 0)
    fresh = int(opportunity.get("fresh_candidate_count") or 0)
    win_rate = _number_or_none(performance.get("win_rate_pct"))
    avg_pnl = _number_or_none(performance.get("avg_pnl_pct"))
    total_pnl = _number_or_none(performance.get("total_pnl_pct"))
    freshness_rate = _number_or_none(opportunity.get("freshness_hit_rate_pct"))
    stops = int(performance.get("stop_count") or 0)
    if outcomes >= MIN_STRONG_PAPER_OUTCOMES:
        score += 25
    else:
        score += min(20, int((outcomes / MIN_STRONG_PAPER_OUTCOMES) * 20)) if outcomes else 0
    if fresh >= MIN_FRESH_CANDIDATES:
        score += 20
    else:
        score += min(15, int((fresh / MIN_FRESH_CANDIDATES) * 15)) if fresh else 0
    if win_rate is not None:
        score += 20 if win_rate >= PREFERRED_WIN_RATE_PCT else max(0, int((win_rate / PREFERRED_WIN_RATE_PCT) * 15))
    if avg_pnl is not None and avg_pnl > 0.0:
        score += 15
    if total_pnl is not None and total_pnl > 0.0:
        score += 10
    if freshness_rate is not None and freshness_rate > 0.0:
        score += 5
    if outcomes and stops / outcomes > 0.5:
        score -= 25
    return max(0, min(100, score))


def classify_promotion_candidate_readiness(
    *,
    lane: Mapping[str, Any],
    performance: Mapping[str, Any],
    opportunity: Mapping[str, Any],
    promotion_score: int,
) -> str:
    outcomes = int(performance.get("paper_outcome_count") or 0)
    fresh = int(opportunity.get("fresh_candidate_count") or 0)
    stops = int(performance.get("stop_count") or 0)
    win_rate = _number_or_none(performance.get("win_rate_pct"))
    avg_pnl = _number_or_none(performance.get("avg_pnl_pct"))
    if outcomes <= 0 and fresh <= 0:
        return NOT_ENOUGH_EVIDENCE
    if outcomes and stops / outcomes > 0.6:
        return DO_NOT_PROMOTE
    if outcomes >= MIN_STRONG_PAPER_OUTCOMES and avg_pnl is not None and avg_pnl <= 0.0:
        return DO_NOT_PROMOTE
    if outcomes < MIN_STRONG_PAPER_OUTCOMES or fresh < MIN_FRESH_CANDIDATES:
        return NOT_ENOUGH_EVIDENCE
    if win_rate is None or avg_pnl is None:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if win_rate >= PREFERRED_WIN_RATE_PCT and avg_pnl > 0.0 and promotion_score >= 75:
        return STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW
    if avg_pnl > 0.0 and promotion_score >= 55:
        return WATCHLIST_FOR_FUTURE_TINY_LIVE
    return PAPER_ONLY_CONTINUE_COLLECTING


def append_promotion_candidate_audit_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = promotion_candidate_audit_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "audit_id": record.get("audit_id") or f"promotion_candidate_audit_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "record_audit_requested": bool(record.get("record_audit_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "lane_families": dict(record.get("lane_families") or {}),
            "ranked_candidates": list(record.get("ranked_candidates") or []),
            "incumbent_tiny_live_review": dict(record.get("incumbent_tiny_live_review") or {}),
            "short_lane_review": dict(record.get("short_lane_review") or {}),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safe_commands": list(record.get("safe_commands") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_promotion_candidate_audit_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = promotion_candidate_audit_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records = read_recent_ndjson_records(path, limit=limit if limit > 0 else 100000, max_bytes=32_000_000)
    if limit <= 0:
        records = list(reversed(records))
    return [_sanitize(record) for record in records]


def summarize_promotion_candidate_audits(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    ranked = list(latest.get("ranked_candidates") or [])
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_audit_id": latest.get("audit_id"),
        "last_best_candidate": ranked[0].get("lane_key") if ranked else None,
        "safety": dict(SAFETY),
    }


def promotion_candidate_audit_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_promotion_candidate_audit_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _target_lanes(
    *,
    config_path: str | Path | None,
    include_paper_lanes: bool,
    include_tiny_live_incumbents: bool,
) -> list[dict[str, Any]]:
    controls = load_lane_controls(Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH)
    lanes = []
    for lane in controls.get("lanes") or []:
        compact = _compact_lane(lane)
        if compact["symbol"] != TARGET_SYMBOL or compact["entry_mode"] != TARGET_ENTRY_MODE:
            continue
        if compact["timeframe"] not in set(DEFAULT_TIMEFRAMES) or compact["direction"] not in {"long", "short"}:
            continue
        if compact["mode"] == "paper" and include_paper_lanes:
            lanes.append(compact)
        elif compact["mode"] == "tiny_live" and include_tiny_live_incumbents:
            lanes.append(compact)
    return sorted(lanes, key=lambda item: _lane_sort_key(item["lane_key"]))


def _compact_lane(lane: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lane_key": str(lane.get("lane_key") or build_lane_family_key(lane)),
        "symbol": str(lane.get("symbol") or "").strip().upper(),
        "timeframe": str(lane.get("timeframe") or "").strip().lower(),
        "direction": str(lane.get("direction") or "").strip().lower(),
        "entry_mode": str(lane.get("entry_mode") or TARGET_ENTRY_MODE).strip().lower(),
        "mode": str(lane.get("mode") or "disabled").strip().lower(),
        "max_daily_trades": int(lane.get("max_daily_trades") or 0),
        "max_daily_loss_pct": float(lane.get("max_daily_loss_pct") or 0.0),
        "freshness_seconds": int(lane.get("freshness_seconds") or 0),
        "cooldown_after_loss_minutes": int(lane.get("cooldown_after_loss_minutes") or 0),
        "require_protective_orders": bool(lane.get("require_protective_orders")),
    }


def _record_lane_key(record: Mapping[str, Any]) -> str:
    ticket = record.get("ticket") if isinstance(record.get("ticket"), Mapping) else {}
    symbol = _first_present(record, "symbol", "base_symbol") or _first_present(ticket, "symbol")
    timeframe = _first_present(record, "timeframe", "tf", "interval") or _first_present(ticket, "timeframe")
    direction = _normalize_direction(_first_present(record, "direction", "side") or _first_present(ticket, "direction"))
    entry_mode = _first_present(record, "entry_mode", "mode") or _first_present(ticket, "entry_mode") or TARGET_ENTRY_MODE
    return normalize_lane_key(symbol, timeframe, direction, entry_mode)


def _filled(record: Mapping[str, Any]) -> bool:
    status = str(record.get("fill_status") or record.get("status") or "").strip().lower()
    if status in {"filled", "partial", "paper_closed", "closed"}:
        return True
    if status in {"no_fill", "no_trade"}:
        return False
    return _number_or_none(record.get("pnl_pct")) is not None


def _stop_hit(record: Mapping[str, Any]) -> bool:
    outcome = str(record.get("outcome") or record.get("close_reason") or "").strip().lower()
    return bool(record.get("stop_hit")) or "stop" in outcome


def _evidence_window(records: list[Mapping[str, Any]], *, lane_key: str) -> tuple[str | None, str | None]:
    timestamps = [
        str(_first_present(record, "evaluated_at", "created_at", "timestamp", "recorded_at_utc") or "")
        for record in records
        if _record_lane_key(record) == lane_key
    ]
    timestamps = [value for value in timestamps if value]
    return (min(timestamps), max(timestamps)) if timestamps else (None, None)


def _sample_quality(count: int) -> str:
    if count <= 0:
        return "NO_OUTCOMES"
    if count < MIN_STRONG_PAPER_OUTCOMES:
        return "LOW_SAMPLE"
    if count < MIN_STRONG_PAPER_OUTCOMES * 3:
        return "DEVELOPING"
    return "USABLE_SAMPLE"


def _opportunity_quality(fresh: int) -> str:
    if fresh <= 0:
        return "NO_FRESH_CANDIDATES"
    if fresh < MIN_FRESH_CANDIDATES:
        return "LOW_FRESH_SAMPLE"
    return "USABLE_FRESH_SAMPLE"


def _ranked_candidates(lane_families: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for lane_key, payload in lane_families.items():
        if payload.get("mode") != "paper":
            continue
        rows.append(
            {
                "lane_key": lane_key,
                "mode": payload.get("mode"),
                "direction": payload.get("direction"),
                "timeframe": payload.get("timeframe"),
                "entry_mode": payload.get("entry_mode"),
                "promotion_score": payload.get("promotion_score"),
                "readiness": payload.get("readiness"),
                "recommended_next_action": payload.get("recommended_next_action"),
            }
        )
    return sorted(rows, key=lambda row: (-int(row.get("promotion_score") or 0), _lane_sort_key(str(row.get("lane_key") or ""))))


def _incumbent_tiny_live_review(lane_families: Mapping[str, Any]) -> dict[str, Any]:
    incumbents = {key: value for key, value in lane_families.items() if value.get("mode") == "tiny_live"}
    return {
        "incumbents_seen": bool(incumbents),
        "incumbent_lane_keys": sorted(incumbents),
        "review_only": True,
        "mode_changes_recommended": False,
        "recommended_action": "KEEP_INCUMBENTS_AS_IS_OR_REVIEW_SEPARATELY",
        "lanes": incumbents,
    }


def _short_lane_review(lane_families: Mapping[str, Any]) -> dict[str, Any]:
    shorts = {key: value for key, value in lane_families.items() if value.get("direction") == "short"}
    ranked = sorted(shorts.items(), key=lambda item: (-int(item[1].get("promotion_score") or 0), _lane_sort_key(item[0])))
    return {
        "shorts_seen": bool(shorts),
        "best_short_family": ranked[0][0] if ranked else None,
        "shorts_remain_paper_only": True,
        "requires_future_short_strategy_review": True,
        "review_requirement": (
            "Future short tiny_live requires separate strategy review: opposite golden pocket as resistance, "
            "short-specific stop/TP, and explicit operator approval."
        ),
    }


def _recommended_next_operator_move(ranked: list[Mapping[str, Any]], short_review: Mapping[str, Any]) -> str:
    if not ranked:
        return "WAIT_FOR_MORE_EVIDENCE"
    best = ranked[0]
    if best.get("direction") == "short" and best.get("readiness") in {
        WATCHLIST_FOR_FUTURE_TINY_LIVE,
        STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW,
    }:
        return "RUN_R155_SHORT_STRATEGY_REVIEW"
    if best.get("readiness") == STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW:
        return "RUN_R155_PROMOTION_PACKET_FOR_TOP_PAPER_LANE"
    if best.get("readiness") in {WATCHLIST_FOR_FUTURE_TINY_LIVE, PAPER_ONLY_CONTINUE_COLLECTING}:
        return "KEEP_COLLECTING_EXPANDED_PAPER"
    return "WAIT_FOR_MORE_EVIDENCE"


def _recommended_next_engineering_move(ranked: list[Mapping[str, Any]], short_review: Mapping[str, Any]) -> str:
    if ranked and ranked[0].get("direction") == "short":
        return "Prepare R155 short strategy review only; do not create lane mode changes."
    if ranked and ranked[0].get("readiness") == STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW:
        return "Prepare an R155 promotion packet surface for the top paper lane; keep config unchanged."
    return "Keep R153/R154 paper evidence collection running until sample thresholds are meaningful."


def _safe_commands() -> list[str]:
    return [
        build_expanded_paper_safe_watch_command(record=False),
        build_expanded_paper_safe_watch_command(record=True),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward promotion-candidate-audit "
            "--latest-outcomes 5000 --latest-signals 2000 --latest-watch-records 200 "
            "--include-paper-lanes --include-tiny-live-incumbents --record-audit "
            '--confirm-promotion-audit "I CONFIRM PROMOTION CANDIDATE AUDIT RECORDING ONLY; NO LANE CHANGES; NO ORDER; NO BINANCE CALL."'
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward candidate-source-freshness-audit "
            "--latest-signals 1000 --latest-scans 2000"
        ),
    ]


def _why(readiness: str, *, lane: Mapping[str, Any], performance: Mapping[str, Any], opportunity: Mapping[str, Any]) -> str:
    if readiness == NOT_ENOUGH_EVIDENCE:
        return "Paper outcome or fresh candidate samples are below R154 thresholds."
    if readiness == DO_NOT_PROMOTE:
        return "Paper evidence is negative or stop-dominated; this lane should not be promoted."
    if readiness == STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW:
        return "Paper evidence meets R154 sample, freshness, win-rate, and positive average PnL checks; review is still required."
    if readiness == WATCHLIST_FOR_FUTURE_TINY_LIVE:
        return "Paper evidence is constructive but requires more review before any future tiny-live consideration."
    if readiness == PAPER_ONLY_CONTINUE_COLLECTING:
        return "Evidence exists but is not strong enough for a promotion packet."
    return "Missing fields require manual review before interpreting readiness."


def _risks(*, lane: Mapping[str, Any], performance: Mapping[str, Any], opportunity: Mapping[str, Any], readiness: str) -> list[str]:
    risks: list[str] = []
    if int(performance.get("paper_outcome_count") or 0) < MIN_STRONG_PAPER_OUTCOMES:
        risks.append("paper outcome sample below 30")
    if int(opportunity.get("fresh_candidate_count") or 0) < MIN_FRESH_CANDIDATES:
        risks.append("fresh candidate sample below 10")
    if performance.get("avg_pnl_pct") is None:
        risks.append("avg_pnl_pct unavailable")
    if opportunity.get("freshness_hit_rate_pct") in (None, 0):
        risks.append("freshness hit rate missing or zero")
    if lane.get("direction") == "short":
        risks.append("short tiny_live requires separate short strategy review and operator approval")
    if lane.get("mode") == "tiny_live":
        risks.append("incumbent tiny_live reference only; R154 does not change existing lane modes")
    return risks


def _recommended_lane_action(*, lane: Mapping[str, Any], readiness: str) -> str:
    if lane.get("mode") == "tiny_live":
        return "REFERENCE_ONLY_KEEP_OR_REVIEW_SEPARATELY"
    if lane.get("direction") == "short" and readiness in {WATCHLIST_FOR_FUTURE_TINY_LIVE, STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW}:
        return "RUN_R155_SHORT_STRATEGY_REVIEW_BEFORE_ANY_PACKET"
    if readiness == STRONG_PAPER_CANDIDATE_REQUIRES_REVIEW:
        return "RUN_R155_PROMOTION_PACKET_FOR_TOP_PAPER_LANE"
    if readiness in {DO_NOT_PROMOTE, NOT_ENOUGH_EVIDENCE}:
        return "KEEP_PAPER_ONLY_AND_COLLECT_OR_REVIEW"
    return "KEEP_COLLECTING_EXPANDED_PAPER"


def _lane_sort_key(lane_key: str) -> tuple[int, str, str]:
    parts = str(lane_key).split("|")
    timeframe = parts[1] if len(parts) > 1 else ""
    direction = parts[2] if len(parts) > 2 else ""
    return (_timeframe_minutes(timeframe), direction, lane_key)


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


def _bounded_int(value: int, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _first_present(raw: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_direction(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"buy", "bull", "bullish"}:
        return "long"
    if text in {"sell", "bear", "bearish"}:
        return "short"
    return text


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
