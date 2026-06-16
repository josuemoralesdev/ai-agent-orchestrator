"""Strategy promotion watcher for Hammer Radar.

This module watches R40 recommendation rows and records review-only promotion
events. It never enables live execution, places orders, reads secrets, sends
network requests, or creates signed order payloads.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.strategy_performance import (
    BTC_SYMBOL,
    ELIGIBLE_FOR_FUTURE_TINY_LIVE,
    INSUFFICIENT_DATA,
    LEGACY_MIN_WIN_RATE,
    PREFERRED_ENTRY_MODE,
    StrategyAuditConfig,
    TINY_LIVE_MIN_WIN_RATE,
    build_live_eligibility_matrix,
    load_strategy_audit_config,
)
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import (
    BTC_SYMBOL as TINY_LIVE_BTC_SYMBOL,
    LIVE_QUALIFIED,
    NEAR_MISS_INCUBATOR,
    NEAR_MISS_MIN_WIN_RATE_PCT,
    PAPER_ONLY,
    build_lane_key,
)

STRATEGY_PROMOTION_EVENTS_FILENAME = "strategy_promotion_events.ndjson"
STRATEGY_NEAR_PROMOTION = "STRATEGY_NEAR_PROMOTION"
STRATEGY_PROMOTION_READY = "STRATEGY_PROMOTION_READY"
STRATEGY_PROMOTION_ALREADY_RECORDED = "STRATEGY_PROMOTION_ALREADY_RECORDED"
STRATEGY_PROMOTION_BLOCKED = "STRATEGY_PROMOTION_BLOCKED"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
SECRETS_SHOWN = False
SUBMIT_ATTEMPTED = False
BINANCE_ORDER_ENDPOINT_CALLED = False
BINANCE_TEST_ORDER_ENDPOINT_CALLED = False
REAL_ORDER_PLACED = False
DEFAULT_NEAR_PROMOTION_SAMPLE_GAP = 5
QUALIFIED_CANDIDATE_EVENT_TYPE = "LIVE_QUALIFIED_FRESH_CANDIDATE_WATCH"
WATCH_WAIT = "WAIT"
WATCH_FOUND = "LIVE_QUALIFIED_FRESH_CANDIDATE_FOUND"
WATCH_BLOCKED_NEAR_MISS = "BLOCKED_NEAR_MISS"
WATCH_BLOCKED_PAPER_ONLY = "BLOCKED_PAPER_ONLY"
WATCH_BLOCKED_BETRAYAL = "BLOCKED_BETRAYAL"


def build_strategy_promotion_status(
    *,
    log_dir: str | Path | None = None,
    config: StrategyAuditConfig | None = None,
    near_sample_gap: int = DEFAULT_NEAR_PROMOTION_SAMPLE_GAP,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    audit_config = _tiny_live_policy_config(config or load_strategy_audit_config())
    matrix = build_live_eligibility_matrix(log_dir=resolved_log_dir, config=audit_config)
    rows = _merge_candidate_rows(
        list(matrix.get("recommendations") or []),
        _latest_strategy_promotion_status_rows(resolved_log_dir),
    )
    eligible = [_promotion_payload(row, event_type=STRATEGY_PROMOTION_READY, config=audit_config) for row in rows if _is_ready(row, config=audit_config)]
    near = [
        _promotion_payload(row, event_type=STRATEGY_NEAR_PROMOTION, config=audit_config)
        for row in rows
        if _is_near_promotion(row, config=audit_config, near_sample_gap=near_sample_gap)
    ]
    blocked = [
        _promotion_payload(row, event_type=STRATEGY_PROMOTION_BLOCKED, config=audit_config)
        for row in rows
        if _is_blocked_promotion_candidate(row, config=audit_config)
    ]
    candidate_watch = _qualified_candidate_watch(rows, config=audit_config, log_dir=resolved_log_dir)
    events = load_strategy_promotion_events(limit=1, log_dir=resolved_log_dir)
    return {
        **_safety_fields(),
        "generated_at": datetime.now(UTC).isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "strategy_promotion_events_path": str(strategy_promotion_events_path(resolved_log_dir)),
        "config": {
            **audit_config.to_dict(),
            "min_win_rate": TINY_LIVE_MIN_WIN_RATE,
            "min_win_rate_pct": TINY_LIVE_MIN_WIN_RATE,
            "legacy_min_win_rate_pct": LEGACY_MIN_WIN_RATE,
            "tiny_live_min_win_rate_pct": TINY_LIVE_MIN_WIN_RATE,
            "near_miss_min_win_rate_pct": NEAR_MISS_MIN_WIN_RATE_PCT,
            "min_sample_count": audit_config.min_sample,
            "evidence_policy_all_timeframes_enabled": True,
            "near_promotion_sample_gap": near_sample_gap,
        },
        "near_promotion": near,
        "promotion_ready": eligible,
        "blocked_candidates": blocked,
        "qualified_candidate_watch": candidate_watch,
        "live_qualified_lanes": candidate_watch["live_qualified_lanes"],
        "near_miss_incubator_lanes": candidate_watch["near_miss_incubator_lanes"],
        "paper_only_lanes": candidate_watch["paper_only_lanes"],
        "current_fresh_candidate_status": candidate_watch["current_fresh_candidate_status"],
        "latest_promotion_event": events[0] if events else None,
        "message_payloads": [build_promotion_message(row) for row in [*eligible, *near]],
    }


def build_live_qualified_fresh_candidate_watch(
    *,
    log_dir: str | Path | None = None,
    config: StrategyAuditConfig | None = None,
    near_sample_gap: int = DEFAULT_NEAR_PROMOTION_SAMPLE_GAP,
) -> dict[str, Any]:
    status = build_strategy_promotion_status(
        log_dir=log_dir,
        config=config,
        near_sample_gap=near_sample_gap,
    )
    watch = dict(status.get("qualified_candidate_watch") or {})
    return {
        **_safety_fields(),
        "event_type": QUALIFIED_CANDIDATE_EVENT_TYPE,
        "generated_at": status.get("generated_at"),
        "archive_log_dir": status.get("archive_log_dir"),
        "live_qualified_lanes": list(status.get("live_qualified_lanes") or []),
        "near_miss_incubator_lanes": list(status.get("near_miss_incubator_lanes") or []),
        "paper_only_lanes": list(status.get("paper_only_lanes") or []),
        "current_fresh_candidate_status": watch.get("current_fresh_candidate_status") or {},
        "candidate_alert_packet": watch.get("candidate_alert_packet") or _empty_candidate_alert_packet(),
        "telegram_compatible_payload": watch.get("telegram_compatible_payload")
        or _watch_telegram_payload(None, status=WATCH_WAIT),
        "safety": _watch_safety(),
    }


def check_strategy_promotions(
    *,
    log_dir: str | Path | None = None,
    config: StrategyAuditConfig | None = None,
    near_sample_gap: int = DEFAULT_NEAR_PROMOTION_SAMPLE_GAP,
    record_blocked: bool = False,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    status = build_strategy_promotion_status(
        log_dir=resolved_log_dir,
        config=config,
        near_sample_gap=near_sample_gap,
    )
    candidates = [*status["promotion_ready"], *status["near_promotion"]]
    if record_blocked:
        candidates.extend(status["blocked_candidates"])

    existing = load_strategy_promotion_events(limit=0, log_dir=resolved_log_dir)
    existing_dedupe_keys = {str(record.get("dedupe_key")) for record in existing if record.get("dedupe_key")}
    recorded_events: list[dict[str, Any]] = []
    skipped_events: list[dict[str, Any]] = []
    for candidate in candidates:
        event = _event_from_payload(candidate, log_dir=resolved_log_dir)
        if event["dedupe_key"] in existing_dedupe_keys:
            skipped_events.append(
                {
                    **candidate,
                    "event_type": STRATEGY_PROMOTION_ALREADY_RECORDED,
                    "dedupe_key": event["dedupe_key"],
                    "operator_note": "Strategy promotion event already recorded for this metric state.",
                }
            )
            continue
        append_strategy_promotion_event(event, log_dir=resolved_log_dir)
        existing_dedupe_keys.add(event["dedupe_key"])
        recorded_events.append(event)

    return {
        **_safety_fields(),
        "generated_at": datetime.now(UTC).isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "strategy_promotion_events_path": str(strategy_promotion_events_path(resolved_log_dir)),
        "recorded": bool(recorded_events),
        "recorded_events": recorded_events,
        "skipped_events": skipped_events,
        "near_promotion": status["near_promotion"],
        "promotion_ready": status["promotion_ready"],
        "message_payloads": [build_promotion_message(event) for event in recorded_events],
        "telegram": {"sent": False, "status": "not_requested"},
    }


def load_strategy_promotion_events(
    *,
    limit: int = 50,
    event_id: str | None = None,
    strategy_key: str | None = None,
    log_dir: str | Path,
) -> list[dict[str, Any]]:
    path = strategy_promotion_events_path(log_dir)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if event_id is not None and record.get("event_id") != event_id:
                continue
            if strategy_key is not None and record.get("strategy_key") != strategy_key:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def append_strategy_promotion_event(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = strategy_promotion_events_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def strategy_promotion_events_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / STRATEGY_PROMOTION_EVENTS_FILENAME


def build_promotion_message(payload: dict[str, Any]) -> dict[str, Any]:
    message = "\n".join(
        [
            "Hammer Radar strategy promotion watcher",
            f"event_type: {payload.get('event_type')}",
            "Future tiny-live review candidate.",
            "Recommendation only, not permission to execute.",
            "Exact LIVE APPROVE <signal_id> and all live safety gates are still required.",
            "Execution remains disabled.",
            "No live orders.",
            f"strategy: {payload.get('strategy_key')}",
            f"samples: {payload.get('sample_count')}/{payload.get('required_sample_count')}",
            f"win_rate_pct: {payload.get('win_rate_pct')}",
            f"avg_pnl_pct: {payload.get('avg_pnl_pct')}",
            f"total_pnl_pct: {payload.get('total_pnl_pct')}",
        ]
    )
    return {
        "channel": "telegram_compatible",
        "send_enabled": False,
        "message": message,
        "secrets_shown": SECRETS_SHOWN,
    }


def _promotion_payload(row: dict[str, Any], *, event_type: str, config: StrategyAuditConfig) -> dict[str, Any]:
    strategy_key = _strategy_key(row)
    return {
        "event_type": event_type,
        "strategy_key": strategy_key,
        "timeframe": row.get("timeframe"),
        "direction": row.get("direction"),
        "entry_mode": row.get("entry_mode"),
        "sample_count": int(row.get("sample_count") or 0),
        "required_sample_count": config.min_sample,
        "min_sample_count": config.min_sample,
        "legacy_min_win_rate_pct": LEGACY_MIN_WIN_RATE,
        "tiny_live_min_win_rate_pct": TINY_LIVE_MIN_WIN_RATE,
        "min_win_rate_pct": TINY_LIVE_MIN_WIN_RATE,
        "evidence_policy_all_timeframes_enabled": True,
        "win_rate_pct": row.get("win_rate_pct"),
        "avg_pnl_pct": row.get("avg_pnl_pct"),
        "total_pnl_pct": row.get("total_pnl_pct"),
        "recommendation": row.get("recommendation"),
        "blockers": list(row.get("blockers") or []),
        "operator_note": _operator_note(event_type),
        **_safety_fields(),
    }


def _event_from_payload(payload: dict[str, Any], *, log_dir: Path) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat()
    return {
        "event_id": uuid4().hex,
        "created_at": created_at,
        "archive_log_dir": str(log_dir),
        "dedupe_key": _dedupe_key(payload),
        **payload,
    }


def _is_ready(row: dict[str, Any], *, config: StrategyAuditConfig) -> bool:
    return (
        row.get("recommendation") == ELIGIBLE_FOR_FUTURE_TINY_LIVE
        and _base_strategy_match(row, config=config)
        and row.get("live_execution_enabled") is False
        and row.get("order_placed") is False
        and row.get("execution_enabled") is False
        and row.get("no_order_payload_created") is True
    )


def _is_near_promotion(row: dict[str, Any], *, config: StrategyAuditConfig, near_sample_gap: int) -> bool:
    sample_count = int(row.get("sample_count") or 0)
    return (
        row.get("recommendation") == INSUFFICIENT_DATA
        and _base_strategy_match(row, config=config)
        and 0 < config.min_sample - sample_count <= near_sample_gap
        and float(row.get("avg_pnl_pct") or 0.0) > 0.0
        and float(row.get("total_pnl_pct") or 0.0) > 0.0
        and float(row.get("win_rate_pct") or 0.0) >= config.min_win_rate
    )


def _is_blocked_promotion_candidate(row: dict[str, Any], *, config: StrategyAuditConfig) -> bool:
    return (
        str(row.get("direction") or "") in {"long", "short"}
        and str(row.get("entry_mode") or "") == PREFERRED_ENTRY_MODE
        and row.get("recommendation") not in {ELIGIBLE_FOR_FUTURE_TINY_LIVE, INSUFFICIENT_DATA}
    )


def _qualified_candidate_watch(rows: list[dict[str, Any]], *, config: StrategyAuditConfig, log_dir: Path) -> dict[str, Any]:
    live_qualified: list[dict[str, Any]] = []
    near_miss: list[dict[str, Any]] = []
    paper_only: list[dict[str, Any]] = []
    for row in rows:
        if not _base_strategy_match(row, config=config):
            continue
        payload = _watch_lane_payload(row, config=config)
        category = payload["watch_category"]
        if category == LIVE_QUALIFIED:
            live_qualified.append(payload)
        elif category == NEAR_MISS_INCUBATOR:
            near_miss.append(payload)
        else:
            paper_only.append(payload)
    fresh_status = _current_fresh_candidate_status(
        lane_payloads={
            str(row["strategy_key"]): row
            for row in [*live_qualified, *near_miss, *paper_only]
        },
        log_dir=log_dir,
    )
    alert_packet = fresh_status.get("candidate_alert_packet") if isinstance(fresh_status.get("candidate_alert_packet"), dict) else _empty_candidate_alert_packet()
    return {
        "event_type": QUALIFIED_CANDIDATE_EVENT_TYPE,
        "status": alert_packet.get("status", WATCH_WAIT),
        "live_qualified_lanes": live_qualified,
        "near_miss_incubator_lanes": near_miss,
        "paper_only_lanes": paper_only,
        "current_fresh_candidate_status": fresh_status,
        "candidate_alert_packet": alert_packet,
        "operator_packet": alert_packet.get("operator_packet") or {},
        "telegram_compatible_payload": _watch_telegram_payload(
            alert_packet,
            status=str(alert_packet.get("status") or WATCH_WAIT),
        ),
        "next_action": alert_packet.get("operator_packet", {}).get("recommended_action")
        or ("WAIT" if fresh_status["qualified_fresh_candidate_exists"] is not True else "REVIEW_MANUAL_ONLY_UNLOCK_PACKET"),
        "manual_unlock_available_only_for": LIVE_QUALIFIED,
        "near_miss_manual_unlock_available": False,
        "strategy_lab_recommendation": "Use NEAR_MISS_INCUBATOR lanes for future Strategy Lab work; do not unlock live.",
        "safety": _watch_safety(),
        **_safety_fields(),
    }


def _watch_lane_payload(row: dict[str, Any], *, config: StrategyAuditConfig) -> dict[str, Any]:
    sample_count = int(row.get("sample_count") or 0)
    win_rate = float(row.get("win_rate_pct") or 0.0)
    avg_pnl = float(row.get("avg_pnl_pct") or 0.0)
    if sample_count >= config.min_sample and avg_pnl > 0.0 and win_rate >= TINY_LIVE_MIN_WIN_RATE:
        category = LIVE_QUALIFIED
    elif sample_count >= config.min_sample and avg_pnl > 0.0 and NEAR_MISS_MIN_WIN_RATE_PCT <= win_rate < TINY_LIVE_MIN_WIN_RATE:
        category = NEAR_MISS_INCUBATOR
    else:
        category = PAPER_ONLY
    blockers: list[str] = []
    if category == NEAR_MISS_INCUBATOR:
        blockers.append("strategy_near_miss_not_live_eligible")
    elif category == PAPER_ONLY:
        blockers.extend(str(item) for item in row.get("blockers") or [])
        if win_rate < TINY_LIVE_MIN_WIN_RATE:
            blockers.append("strategy_near_miss_not_live_eligible")
    return {
        "strategy_key": _strategy_key(row),
        "watch_category": category,
        "timeframe": row.get("timeframe"),
        "direction": row.get("direction"),
        "entry_mode": row.get("entry_mode"),
        "sample_count": sample_count,
        "required_sample_count": config.min_sample,
        "win_rate_pct": row.get("win_rate_pct"),
        "avg_pnl_pct": row.get("avg_pnl_pct"),
        "total_pnl_pct": row.get("total_pnl_pct"),
        "manual_live_unlock_available": category == LIVE_QUALIFIED,
        "final_command_available": False,
        "recommended_next_action": "WAIT_FOR_FRESH_CANDIDATE" if category == LIVE_QUALIFIED else "STRATEGY_LAB_PAPER_REVIEW",
        "blockers": _dedupe(blockers),
        **_safety_fields(),
    }


def _current_fresh_candidate_status(*, lane_payloads: dict[str, dict[str, Any]], log_dir: Path) -> dict[str, Any]:
    try:
        from src.app.hammer_radar.operator.inspect import build_live_candidate_snapshot
        from src.app.hammer_radar.operator.readiness import PROTOCOL

        snapshot = build_live_candidate_snapshot(
            limit=10,
            since_hours=24,
            min_score=90,
            symbol=TINY_LIVE_BTC_SYMBOL,
            allow_short=True,
            allow_oversold=False,
            allow_trigger_flags=False,
            max_risk_usd=5.0,
            max_leverage=float(PROTOCOL["max_leverage"]),
            max_position_usd=float(PROTOCOL["max_position_usd"]),
            fresh_minutes=30,
            allow_expired=False,
            latest_only=False,
            log_dir=log_dir,
        )
    except Exception as exc:  # pragma: no cover - defensive status surface
        return {
            "qualified_fresh_candidate_exists": False,
            "fresh_candidate_lane_keys": [],
            "qualified_fresh_candidate_lane_keys": [],
            "next_action": "WAIT",
            "candidate_alert_packet": _empty_candidate_alert_packet(blocked_by=[f"candidate_snapshot_unavailable_{exc.__class__.__name__}"]),
            "blocked_by": [f"readiness_status_unavailable_{exc.__class__.__name__}"],
            **_safety_fields(),
        }
    checks = list(snapshot.get("checks") or [])
    fresh_checks = [
        check
        for check in checks
        if getattr(check, "freshness_status", None) == "fresh"
        and getattr(getattr(check, "candidate", None), "signal", None) is not None
        and getattr(check.candidate.signal, "symbol", None) == TINY_LIVE_BTC_SYMBOL
    ]
    fresh_lanes = [_lane_key_for_check(check) for check in fresh_checks]
    qualified_fresh = [lane for lane in fresh_lanes if (lane_payloads.get(lane) or {}).get("watch_category") == LIVE_QUALIFIED]
    current = fresh_checks[0] if fresh_checks else None
    alert_packet = _candidate_alert_packet(current, lane_payloads=lane_payloads, log_dir=log_dir)
    return {
        "qualified_fresh_candidate_exists": bool(qualified_fresh),
        "fresh_candidate_lane_keys": fresh_lanes,
        "qualified_fresh_candidate_lane_keys": qualified_fresh,
        "current_candidate_lane_key": _lane_key_for_check(current) if current is not None else None,
        "current_fresh_candidate_status": alert_packet.get("status"),
        "candidate_alert_packet": alert_packet,
        "next_action": alert_packet.get("operator_packet", {}).get("recommended_action") or "WAIT",
        "blocked_by": [] if alert_packet.get("status") == WATCH_FOUND else list(alert_packet.get("blocked_by") or ["no_qualified_fresh_candidate"]),
        **_safety_fields(),
    }


def _candidate_alert_packet(check: Any | None, *, lane_payloads: dict[str, dict[str, Any]], log_dir: Path) -> dict[str, Any]:
    if check is None:
        return _empty_candidate_alert_packet()
    lane_key = _lane_key_for_check(check)
    lane = lane_payloads.get(lane_key) or {}
    category = str(lane.get("watch_category") or PAPER_ONLY)
    current_candidate = _current_candidate_payload(check, lane_key=lane_key)
    evidence = _strategy_evidence_payload(lane, category=category)
    blocked_by: list[str] = []
    status = WATCH_WAIT
    recommended_action = "WAIT"
    manual_unlock_next_step = "WAIT_FOR_LIVE_QUALIFIED_FRESH_CANDIDATE"
    if _candidate_is_betrayal_or_inverse(check):
        status = WATCH_BLOCKED_BETRAYAL
        blocked_by.append("betrayal_inverse_candidate_not_live_eligible")
        recommended_action = "WAIT"
        manual_unlock_next_step = "BLOCKED_BETRAYAL_OR_INVERSE"
    elif category == NEAR_MISS_INCUBATOR:
        status = WATCH_BLOCKED_NEAR_MISS
        blocked_by.append("strategy_near_miss_not_live_eligible")
        recommended_action = "STRATEGY_LAB_PAPER_REVIEW"
        manual_unlock_next_step = "WATCHLIST_INCUBATOR_ONLY"
    elif category != LIVE_QUALIFIED:
        status = WATCH_BLOCKED_PAPER_ONLY
        blocked_by.append("strategy_paper_only_not_live_eligible")
        recommended_action = "STRATEGY_LAB_PAPER_REVIEW"
        manual_unlock_next_step = "PAPER_ONLY_REVIEW"
    else:
        blocked_by.extend(_live_qualified_evidence_blockers(lane))
        blocked_by.extend(_candidate_field_blockers(check, lane_key=lane_key))
        if blocked_by:
            status = WATCH_BLOCKED_PAPER_ONLY
            recommended_action = "STRATEGY_LAB_PAPER_REVIEW"
            manual_unlock_next_step = "BLOCKED_UNTIL_EXACT_LANE_POLICY_CLEAN"
        else:
            status = WATCH_FOUND
            recommended_action = "REVIEW_MANUAL_ONLY_UNLOCK_PACKET"
            manual_unlock_next_step = "RUN_FINAL_CONSOLE_AND_MANUAL_UNLOCK_REVIEW"
    if category in {NEAR_MISS_INCUBATOR, PAPER_ONLY} and "strategy_near_miss_not_live_eligible" in (lane.get("blockers") or []):
        blocked_by.append("strategy_near_miss_not_live_eligible")
    operator_packet = {
        "recommended_action": recommended_action,
        "manual_unlock_next_step": manual_unlock_next_step,
        "final_command_available": False,
        "submit_allowed_from_codex": False,
        "operator_review_only": True,
        "no_live_order_placed": True,
    }
    return {
        **_safety_fields(),
        "event_type": QUALIFIED_CANDIDATE_EVENT_TYPE,
        "status": status,
        "current_candidate": current_candidate,
        "strategy_evidence": evidence,
        "operator_packet": operator_packet,
        "blocked_by": _dedupe(blocked_by),
        "final_command_available": False,
        "submit_allowed_from_codex": False,
        "submit_attempted": SUBMIT_ATTEMPTED,
        "binance_order_endpoint_called": BINANCE_ORDER_ENDPOINT_CALLED,
        "binance_test_order_endpoint_called": BINANCE_TEST_ORDER_ENDPOINT_CALLED,
        "real_order_placed": REAL_ORDER_PLACED,
        "telegram_compatible_payload": _watch_telegram_payload({"current_candidate": current_candidate, "strategy_evidence": evidence}, status=status),
        "safety": _watch_safety(),
    }


def _empty_candidate_alert_packet(*, blocked_by: list[str] | None = None) -> dict[str, Any]:
    return {
        **_safety_fields(),
        "event_type": QUALIFIED_CANDIDATE_EVENT_TYPE,
        "status": WATCH_WAIT,
        "current_candidate": None,
        "strategy_evidence": None,
        "operator_packet": {
            "recommended_action": "WAIT",
            "manual_unlock_next_step": "WAIT_FOR_LIVE_QUALIFIED_FRESH_CANDIDATE",
            "final_command_available": False,
            "submit_allowed_from_codex": False,
            "operator_review_only": True,
            "no_live_order_placed": True,
        },
        "blocked_by": blocked_by or ["no_current_fresh_candidate"],
        "final_command_available": False,
        "submit_allowed_from_codex": False,
        "submit_attempted": SUBMIT_ATTEMPTED,
        "binance_order_endpoint_called": BINANCE_ORDER_ENDPOINT_CALLED,
        "binance_test_order_endpoint_called": BINANCE_TEST_ORDER_ENDPOINT_CALLED,
        "real_order_placed": REAL_ORDER_PLACED,
        "safety": _watch_safety(),
    }


def _current_candidate_payload(check: Any, *, lane_key: str) -> dict[str, Any]:
    signal = check.candidate.signal
    return {
        "signal_id": signal.signal_id,
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "direction": signal.direction,
        "entry_mode": PREFERRED_ENTRY_MODE,
        "lane_key": lane_key,
        "age_minutes": check.age_minutes,
        "freshness_status": check.freshness_status,
        "entry": check.entry,
        "stop": check.stop,
        "take_profit": check.take_profit,
    }


def _strategy_evidence_payload(lane: dict[str, Any], *, category: str) -> dict[str, Any]:
    return {
        "win_rate_pct": lane.get("win_rate_pct"),
        "sample_count": lane.get("sample_count"),
        "min_sample_count": lane.get("required_sample_count"),
        "avg_pnl_pct": lane.get("avg_pnl_pct"),
        "live_qualification_class": category,
    }


def _live_qualified_evidence_blockers(lane: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if str(lane.get("strategy_key") or "") == "":
        blockers.append("strategy_evidence_missing")
    if float(lane.get("win_rate_pct") or 0.0) < TINY_LIVE_MIN_WIN_RATE:
        blockers.append("win_rate_below_operator_55_policy")
    if int(lane.get("sample_count") or 0) < int(lane.get("required_sample_count") or 30):
        blockers.append("strategy_sample_count_below_minimum")
    if float(lane.get("avg_pnl_pct") or 0.0) <= 0.0:
        blockers.append("strategy_avg_pnl_pct_not_positive")
    return blockers


def _candidate_field_blockers(check: Any, *, lane_key: str) -> list[str]:
    signal = check.candidate.signal
    blockers: list[str] = []
    if signal.symbol != TINY_LIVE_BTC_SYMBOL:
        blockers.append("candidate_symbol_not_BTCUSDT")
    if check.freshness_status != "fresh":
        blockers.append("candidate_not_fresh")
    if check.entry is None:
        blockers.append("candidate_entry_missing")
    if check.stop is None:
        blockers.append("candidate_stop_missing")
    if check.take_profit is None:
        blockers.append("candidate_take_profit_missing")
    if lane_key != build_lane_key(
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        direction=signal.direction,
        entry_mode=PREFERRED_ENTRY_MODE,
    ):
        blockers.append("candidate_lane_key_mismatch")
    return blockers


def _candidate_is_betrayal_or_inverse(check: Any) -> bool:
    signal = check.candidate.signal
    text = " ".join(
        str(value or "")
        for value in (
            signal.signal_id,
            getattr(signal, "signal_origin_family", None),
            getattr(signal, "origin_family", None),
            getattr(signal, "source_type", None),
            signal.direction,
        )
    ).lower()
    return "betrayal" in text or "inverse" in text or signal.direction == "inverse"


def _lane_key_for_check(check: Any | None) -> str:
    if check is None:
        return ""
    signal = check.candidate.signal
    return build_lane_key(
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        direction=signal.direction,
        entry_mode=PREFERRED_ENTRY_MODE,
    )


def _watch_telegram_payload(packet: dict[str, Any] | None, *, status: str) -> dict[str, Any]:
    candidate = (packet or {}).get("current_candidate") or {}
    evidence = (packet or {}).get("strategy_evidence") or {}
    if status != WATCH_FOUND:
        message = "\n".join(
            [
                "Hammer Radar live-qualified fresh candidate watcher",
                f"status: {status}",
                "No Telegram send by default.",
                "operator review only; no live order placed.",
            ]
        )
    else:
        message = "\n".join(
            [
                "LIVE_QUALIFIED_FRESH_CANDIDATE_FOUND",
                f"lane: {candidate.get('lane_key') or 'n/a'}",
                f"win_rate_pct: {evidence.get('win_rate_pct')}",
                f"sample_count: {evidence.get('sample_count')}/{evidence.get('min_sample_count')}",
                f"direction: {candidate.get('direction') or 'n/a'}",
                f"entry: {candidate.get('entry')}",
                f"stop: {candidate.get('stop')}",
                f"take_profit: {candidate.get('take_profit')}",
                "operator review only; no live order placed.",
            ]
        )
    return {
        "channel": "telegram_compatible",
        "send_enabled": False,
        "sent": False,
        "status": "prepared_not_sent",
        "message": message,
        "secrets_shown": SECRETS_SHOWN,
    }


def _watch_safety() -> dict[str, Any]:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "submit_attempted": SUBMIT_ATTEMPTED,
        "binance_order_endpoint_called": BINANCE_ORDER_ENDPOINT_CALLED,
        "binance_test_order_endpoint_called": BINANCE_TEST_ORDER_ENDPOINT_CALLED,
        "order_payload_created": ORDER_PAYLOAD_CREATED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _latest_strategy_promotion_status_rows(log_dir: Path) -> list[dict[str, Any]]:
    records = _read_ndjson_reverse(log_dir / "strategy_promotion_status.ndjson")
    if not records:
        return []
    latest = records[0]
    rows: list[dict[str, Any]] = []
    for key in (
        "promotion_ready",
        "live_qualified_lanes",
        "near_miss_incubator_lanes",
        "paper_only_lanes",
        "blocked_candidates",
        "recommendations",
    ):
        value = latest.get(key)
        if isinstance(value, list):
            rows.extend(_normalize_strategy_row(dict(item)) for item in value if isinstance(item, dict))
    watch = latest.get("qualified_candidate_watch")
    if isinstance(watch, dict):
        for key in ("live_qualified_lanes", "near_miss_incubator_lanes", "paper_only_lanes"):
            value = watch.get(key)
            if isinstance(value, list):
                rows.extend(_normalize_strategy_row(dict(item)) for item in value if isinstance(item, dict))
    return rows


def _read_ndjson_reverse(path: Path) -> list[dict[str, Any]]:
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
                records.append(payload)
    return list(reversed(records))


def _merge_candidate_rows(primary: list[dict[str, Any]], fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in [*fallback, *primary]:
        if not isinstance(row, dict):
            continue
        key = row.get("strategy_key") or _strategy_key(row)
        merged[str(key)] = row
    return list(merged.values())


def _normalize_strategy_row(row: dict[str, Any]) -> dict[str, Any]:
    lane = row.get("strategy_key") or row.get("lane_key")
    if isinstance(lane, str):
        parts = [*lane.split("|"), "", "", "", ""]
        row.setdefault("symbol", parts[0])
        row.setdefault("timeframe", parts[1])
        row.setdefault("direction", parts[2])
        row.setdefault("entry_mode", parts[3])
    return row


def _base_strategy_match(row: dict[str, Any], *, config: StrategyAuditConfig) -> bool:
    return (
        str(row.get("symbol") or BTC_SYMBOL) == BTC_SYMBOL
        and str(row.get("direction") or "") in {"long", "short"}
        and str(row.get("entry_mode") or "") == PREFERRED_ENTRY_MODE
    )


def _strategy_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("symbol") or BTC_SYMBOL),
            str(row.get("timeframe") or "unknown"),
            str(row.get("direction") or "unknown"),
            str(row.get("entry_mode") or "unknown"),
        ]
    )


def _dedupe_key(payload: dict[str, Any]) -> str:
    return "|".join(
        [
            str(payload.get("strategy_key")),
            str(payload.get("event_type")),
            str(payload.get("recommendation")),
            str(payload.get("sample_count")),
            str(payload.get("win_rate_pct")),
            str(payload.get("avg_pnl_pct")),
            str(payload.get("total_pnl_pct")),
        ]
    )


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _operator_note(event_type: str) -> str:
    if event_type == STRATEGY_PROMOTION_READY:
        return (
            "Future tiny-live review candidate. Recommendation only, not permission to execute. "
            "Exact LIVE APPROVE <signal_id> and all live safety gates are still required."
        )
    if event_type == STRATEGY_NEAR_PROMOTION:
        return "Near promotion threshold. Keep collecting paper samples. Execution remains disabled."
    return "Promotion blocked or already recorded. No live orders."


def _safety_fields() -> dict[str, Any]:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "submit_attempted": SUBMIT_ATTEMPTED,
        "binance_order_endpoint_called": BINANCE_ORDER_ENDPOINT_CALLED,
        "binance_test_order_endpoint_called": BINANCE_TEST_ORDER_ENDPOINT_CALLED,
        "order_payload_created": ORDER_PAYLOAD_CREATED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _tiny_live_policy_config(config: StrategyAuditConfig) -> StrategyAuditConfig:
    return StrategyAuditConfig(
        min_sample=max(int(config.min_sample or 0), 30),
        min_win_rate=TINY_LIVE_MIN_WIN_RATE,
        allowed_tiny_live_timeframes=config.allowed_tiny_live_timeframes,
        paper_only_timeframes=config.paper_only_timeframes,
        context_only_timeframes=config.context_only_timeframes,
        blocked_timeframes=config.blocked_timeframes,
    )
