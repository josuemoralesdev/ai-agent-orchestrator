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
    PREFERRED_ENTRY_MODE,
    StrategyAuditConfig,
    build_live_eligibility_matrix,
    load_strategy_audit_config,
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
DEFAULT_NEAR_PROMOTION_SAMPLE_GAP = 5


def build_strategy_promotion_status(
    *,
    log_dir: str | Path | None = None,
    config: StrategyAuditConfig | None = None,
    near_sample_gap: int = DEFAULT_NEAR_PROMOTION_SAMPLE_GAP,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    audit_config = config or load_strategy_audit_config()
    matrix = build_live_eligibility_matrix(log_dir=resolved_log_dir, config=audit_config)
    rows = list(matrix.get("recommendations") or [])
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
    events = load_strategy_promotion_events(limit=1, log_dir=resolved_log_dir)
    return {
        **_safety_fields(),
        "generated_at": datetime.now(UTC).isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "strategy_promotion_events_path": str(strategy_promotion_events_path(resolved_log_dir)),
        "config": {
            **audit_config.to_dict(),
            "near_promotion_sample_gap": near_sample_gap,
        },
        "near_promotion": near,
        "promotion_ready": eligible,
        "blocked_candidates": blocked,
        "latest_promotion_event": events[0] if events else None,
        "message_payloads": [build_promotion_message(row) for row in [*eligible, *near]],
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
        str(row.get("timeframe") or "") in config.allowed_tiny_live_timeframes
        and str(row.get("direction") or "") == "long"
        and str(row.get("entry_mode") or "") == PREFERRED_ENTRY_MODE
        and row.get("recommendation") not in {ELIGIBLE_FOR_FUTURE_TINY_LIVE, INSUFFICIENT_DATA}
    )


def _base_strategy_match(row: dict[str, Any], *, config: StrategyAuditConfig) -> bool:
    return (
        str(row.get("symbol") or BTC_SYMBOL) == BTC_SYMBOL
        and str(row.get("direction") or "") == "long"
        and str(row.get("entry_mode") or "") == PREFERRED_ENTRY_MODE
        and str(row.get("timeframe") or "") in config.allowed_tiny_live_timeframes
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
        "execution_attempted": EXECUTION_ATTEMPTED,
        "order_payload_created": ORDER_PAYLOAD_CREATED,
        "secrets_shown": SECRETS_SHOWN,
    }
