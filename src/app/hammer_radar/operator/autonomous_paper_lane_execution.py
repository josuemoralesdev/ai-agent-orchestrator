"""R125 autonomous paper lane execution records.

This module turns R123 routed candidates into append-only paper records only.
It never imports exchange clients, creates order payloads, calls Binance,
uses network access, mutates env files, or enables live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.archive import get_signals_path, load_signals
from src.app.hammer_radar.operator.fresh_signal_router import (
    EXPIRED_SIGNAL,
    NO_MATCHING_LANE,
    ROUTER_NO_CANDIDATES,
    ROUTER_NO_CANDIDATE_SOURCE,
    ROUTER_READY,
    ROUTED_TO_LANE,
    evaluate_candidate_against_lanes,
)
from src.app.hammer_radar.operator.lane_control import (
    SAFETY_FALSE,
    load_lane_controls,
)
from src.app.hammer_radar.operator.strategy_performance import build_live_eligibility_matrix

AUTONOMOUS_PAPER_LANE_EXECUTIONS_LEDGER = "autonomous_paper_lane_executions.ndjson"
CONFIRM_PAPER_ONLY_PHRASE = "I CONFIRM PAPER LANE EXECUTION ONLY; NO REAL ORDER; NO BINANCE CALL."

PAPER_LANE_PREVIEW = "PAPER_LANE_PREVIEW"
PAPER_LANE_REJECTED = "PAPER_LANE_REJECTED"
PAPER_LANE_RECORDED = "PAPER_LANE_RECORDED"
PAPER_LANE_PARTIAL = "PAPER_LANE_PARTIAL"

PAPER_ENTRY_RECORDED = "PAPER_ENTRY_RECORDED"
ARMED_DRY_RUN_ENTRY_RECORDED = "ARMED_DRY_RUN_ENTRY_RECORDED"
PAPER_SHADOW_FOR_TINY_LIVE = "PAPER_SHADOW_FOR_TINY_LIVE"
PAPER_BLOCKED = "PAPER_BLOCKED"

PAPER_RECORDING_MODES = {"paper", "armed_dry_run", "tiny_live"}
BLOCKING_SAFETY_KEYS = (
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "order_payload_created",
    "network_allowed",
    "secrets_shown",
)
PAPER_LANE_SAFETY = {
    **SAFETY_FALSE,
    "paper_live_separation_intact": True,
}
SOURCE_SURFACES_USED = [
    "operator.fresh_signal_router.evaluate_candidate_against_lanes",
    "operator.lane_control.load_lane_controls",
    "configs/hammer_radar/lane_controls.json",
    "logs/hammer_radar_forward/autonomous_paper_lane_executions.ndjson",
    "R125 paper-only confirmation phrase",
]


def load_paper_lane_executions(
    *,
    log_dir: str | Path | None = None,
    limit: int = 0,
    lane_key: str | None = None,
) -> list[dict[str, Any]]:
    path = _ledger_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if lane_key is not None and record.get("lane_key") != lane_key:
                continue
            records.append(record)
    if limit > 0:
        return list(reversed(records))[:limit]
    return records


def append_paper_lane_execution(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = _ledger_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(record)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return payload


def compute_lane_daily_count(
    lane_key: str,
    *,
    records: list[Mapping[str, Any]] | None = None,
    log_dir: str | Path | None = None,
    day: date | None = None,
) -> int:
    target_day = day or datetime.now(UTC).date()
    source_records = records if records is not None else load_paper_lane_executions(log_dir=log_dir)
    count = 0
    for record in source_records:
        if record.get("lane_key") != lane_key:
            continue
        if record.get("paper_action") == PAPER_BLOCKED:
            continue
        recorded_at = _parse_timestamp(record.get("recorded_at_utc"))
        if recorded_at and recorded_at.date() == target_day:
            count += 1
    return count


def compute_lane_cooldown_status(
    lane_key: str,
    *,
    cooldown_after_loss_minutes: int | None,
    records: list[Mapping[str, Any]] | None = None,
    log_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    cooldown_minutes = int(cooldown_after_loss_minutes or 0)
    if cooldown_minutes <= 0:
        return _cooldown_payload(active=False, until=None, source_record_id=None, remaining_seconds=0)

    source_records = records if records is not None else load_paper_lane_executions(log_dir=log_dir)
    loss_records = [
        record
        for record in source_records
        if record.get("lane_key") == lane_key and _record_indicates_loss(record)
    ]
    if not loss_records:
        return _cooldown_payload(active=False, until=None, source_record_id=None, remaining_seconds=0)

    latest_loss = max(loss_records, key=lambda row: _parse_timestamp(row.get("recorded_at_utc")) or datetime.min.replace(tzinfo=UTC))
    loss_at = _parse_timestamp(latest_loss.get("recorded_at_utc"))
    if loss_at is None:
        return _cooldown_payload(active=False, until=None, source_record_id=None, remaining_seconds=0)

    cooldown_until = loss_at + timedelta(minutes=cooldown_minutes)
    remaining_seconds = max((cooldown_until - generated_at).total_seconds(), 0.0)
    return _cooldown_payload(
        active=remaining_seconds > 0,
        until=cooldown_until.isoformat(),
        source_record_id=latest_loss.get("paper_execution_id"),
        remaining_seconds=remaining_seconds,
    )


def build_paper_execution_from_routed_candidate(
    routed_candidate: Mapping[str, Any],
    *,
    lane: Mapping[str, Any] | None = None,
    existing_records: list[Mapping[str, Any]] | None = None,
    pending_daily_count: int = 0,
    now: datetime | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    lane_key = str(routed_candidate.get("lane_key") or "")
    lane_record = dict(lane or {})
    lane_mode = str(routed_candidate.get("lane_mode") or lane_record.get("mode") or "disabled").strip().lower()
    risk_limits = _risk_limits(lane_record, routed_candidate)
    source_records = existing_records if existing_records is not None else load_paper_lane_executions(log_dir=log_dir)
    daily_count = compute_lane_daily_count(lane_key, records=source_records, day=generated_at.date()) + max(pending_daily_count, 0)
    cooldown = compute_lane_cooldown_status(
        lane_key,
        cooldown_after_loss_minutes=_int_or_none(risk_limits.get("cooldown_after_loss_minutes")),
        records=source_records,
        now=generated_at,
    )
    blockers = _candidate_blockers(routed_candidate, lane_record, lane_mode, risk_limits, daily_count, cooldown)
    paper_action = PAPER_BLOCKED if blockers else _paper_action_for_mode(lane_mode)
    safety = _safety_from_source(routed_candidate)
    if _source_safety_blocked(routed_candidate) or safety["paper_live_separation_intact"] is not True:
        paper_action = PAPER_BLOCKED

    return {
        "event_type": "AUTONOMOUS_PAPER_LANE_EXECUTION",
        "paper_execution_id": f"paper_lane_{uuid4().hex}",
        "recorded_at_utc": generated_at.isoformat(),
        "candidate_id": routed_candidate.get("candidate_id"),
        "lane_key": lane_key,
        "symbol": routed_candidate.get("symbol"),
        "timeframe": routed_candidate.get("timeframe"),
        "direction": routed_candidate.get("direction"),
        "entry_mode": routed_candidate.get("entry_mode"),
        "lane_mode": lane_mode,
        "route_status": routed_candidate.get("route_status"),
        "route_action": routed_candidate.get("route_action"),
        "paper_action": paper_action,
        "entry_reference": _entry_reference(routed_candidate),
        "risk_limits": risk_limits,
        "blockers": blockers,
        "safety": safety,
    }


def build_autonomous_paper_lane_execution_status(
    *,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    execute_paper: bool = False,
    lane_key: str | None = None,
    all_lanes: bool = False,
    confirm_paper_only: str | None = None,
    candidates: list[Mapping[str, Any] | object] | None = None,
    now: datetime | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    global_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    controls = load_lane_controls(config_path)
    selected_lane_keys = _selected_lane_keys(controls, lane_key=lane_key, all_lanes=all_lanes)
    router_status = _build_full_router_status(
        log_dir=resolved_log_dir,
        controls=controls,
        candidates=candidates,
        now=generated_at,
        live_eligibility_matrix=live_eligibility_matrix,
        global_gate=global_gate,
    )
    routed_candidates = _candidate_rows(router_status)
    existing_records = load_paper_lane_executions(log_dir=resolved_log_dir)
    daily_counts = {
        key: compute_lane_daily_count(key, records=existing_records, day=generated_at.date())
        for key in selected_lane_keys
    }
    cooldown_status = {
        key: compute_lane_cooldown_status(
            key,
            cooldown_after_loss_minutes=(controls.get("lane_map") or {}).get(key, {}).get("cooldown_after_loss_minutes"),
            records=existing_records,
            now=generated_at,
        )
        for key in selected_lane_keys
    }
    pending_daily_counts: Counter[str] = Counter()
    preview_records: list[dict[str, Any]] = []
    skipped_candidates: list[dict[str, Any]] = []
    for candidate in routed_candidates:
        candidate_lane_key = str(candidate.get("lane_key") or "")
        if lane_key and candidate_lane_key not in selected_lane_keys:
            skipped_candidates.append(_skip_payload(candidate, "lane not selected"))
            continue
        lane = (controls.get("lane_map") or {}).get(candidate_lane_key)
        record = build_paper_execution_from_routed_candidate(
            candidate,
            lane=lane,
            existing_records=existing_records,
            pending_daily_count=pending_daily_counts[candidate_lane_key],
            now=generated_at,
        )
        preview_records.append(record)
        if not record["blockers"]:
            pending_daily_counts[candidate_lane_key] += 1
        else:
            skipped_candidates.append(_skip_payload(candidate, "; ".join(record["blockers"])))

    recordable = [record for record in preview_records if record.get("paper_action") != PAPER_BLOCKED and not record.get("blockers")]
    blocked = [record for record in preview_records if record.get("paper_action") == PAPER_BLOCKED or record.get("blockers")]
    confirmation_valid = confirm_paper_only == CONFIRM_PAPER_ONLY_PHRASE
    rejection_reason = None
    recorded_ids: list[str] = []
    if execute_paper and not confirmation_valid:
        status = PAPER_LANE_REJECTED
        rejection_reason = "missing or invalid paper-only confirmation"
    elif not execute_paper:
        status = PAPER_LANE_PREVIEW
    else:
        for record in recordable:
            append_paper_lane_execution(record, log_dir=resolved_log_dir)
            recorded_ids.append(str(record["paper_execution_id"]))
        status = PAPER_LANE_RECORDED if recordable and len(recorded_ids) == len(recordable) and not blocked else PAPER_LANE_PARTIAL
        if blocked and recorded_ids:
            status = PAPER_LANE_PARTIAL

    payload = {
        "status": status,
        "generated_at": generated_at.isoformat(),
        "execute_paper_requested": bool(execute_paper),
        "confirmation_valid": bool(confirmation_valid),
        "selected_lane_keys": selected_lane_keys,
        "candidates_seen_count": int(router_status.get("candidates_seen_count") or 0),
        "routed_count": int(router_status.get("routed_count") or 0),
        "paper_recordable_count": len(recordable),
        "paper_blocked_count": len(blocked),
        "recorded_count": len(recorded_ids),
        "recorded_paper_execution_ids": recorded_ids,
        "skipped_candidates": skipped_candidates[:5],
        "lane_daily_counts": daily_counts,
        "lane_cooldown_status": cooldown_status,
        "preview_records": _compact_preview_records(preview_records),
        "safety": dict(PAPER_LANE_SAFETY),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
        "ledger_path": str(_ledger_path(resolved_log_dir)),
    }
    if rejection_reason:
        payload["rejection_reason"] = rejection_reason
    return payload


def format_autonomous_paper_lane_execution_status_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _ledger_path(log_dir: Path) -> Path:
    return log_dir / AUTONOMOUS_PAPER_LANE_EXECUTIONS_LEDGER


def _selected_lane_keys(controls: Mapping[str, Any], *, lane_key: str | None, all_lanes: bool) -> list[str]:
    if lane_key:
        return [str(lane_key)]
    lanes = list(controls.get("lanes") or [])
    if all_lanes or not lane_key:
        return [str(lane.get("lane_key")) for lane in lanes if lane.get("lane_key")]
    return []


def _candidate_rows(router_status: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("routed_candidates", "blocked_candidates", "expired_candidates", "no_matching_lane_candidates"):
        rows.extend(dict(row) for row in router_status.get(key, []) if isinstance(row, Mapping))
    return rows


def _build_full_router_status(
    *,
    log_dir: Path,
    controls: Mapping[str, Any],
    candidates: list[Mapping[str, Any] | object] | None,
    now: datetime,
    live_eligibility_matrix: Mapping[str, Any] | None,
    global_gate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source_candidates = candidates
    source_path = get_signals_path(log_dir)
    if source_candidates is None:
        if not source_path.exists():
            return _router_empty_status(ROUTER_NO_CANDIDATE_SOURCE)
        source_candidates = load_signals(log_dir)
    if not source_candidates:
        return _router_empty_status(ROUTER_NO_CANDIDATES)

    matrix = live_eligibility_matrix if live_eligibility_matrix is not None else build_live_eligibility_matrix(log_dir=log_dir)
    rows = [
        evaluate_candidate_against_lanes(
            candidate,
            controls=controls,
            live_eligibility_matrix=matrix,
            global_gate=global_gate,
            now=now,
            log_dir=log_dir,
        )
        for candidate in source_candidates
    ]
    counts = Counter(row.get("route_status") for row in rows)
    return {
        "status": ROUTER_READY,
        "candidates_seen_count": len(rows),
        "routed_count": counts.get(ROUTED_TO_LANE, 0),
        "blocked_count": counts.get("BLOCKED_BY_LANE", 0),
        "expired_count": counts.get(EXPIRED_SIGNAL, 0),
        "no_matching_lane_count": counts.get(NO_MATCHING_LANE, 0),
        "routed_candidates": [row for row in rows if row.get("route_status") == ROUTED_TO_LANE],
        "blocked_candidates": [row for row in rows if row.get("route_status") == "BLOCKED_BY_LANE"],
        "expired_candidates": [row for row in rows if row.get("route_status") == EXPIRED_SIGNAL],
        "no_matching_lane_candidates": [row for row in rows if row.get("route_status") == NO_MATCHING_LANE],
    }


def _router_empty_status(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "candidates_seen_count": 0,
        "routed_count": 0,
        "blocked_count": 0,
        "expired_count": 0,
        "no_matching_lane_count": 0,
        "routed_candidates": [],
        "blocked_candidates": [],
        "expired_candidates": [],
        "no_matching_lane_candidates": [],
    }


def _candidate_blockers(
    routed_candidate: Mapping[str, Any],
    lane: Mapping[str, Any],
    lane_mode: str,
    risk_limits: Mapping[str, Any],
    daily_count: int,
    cooldown: Mapping[str, Any],
) -> list[str]:
    blockers = list(routed_candidate.get("blockers") or [])
    if routed_candidate.get("route_status") != ROUTED_TO_LANE:
        blockers.append("candidate route_status is not ROUTED_TO_LANE")
    if not lane:
        blockers.append("no matching lane")
    if lane_mode in {"", "disabled", "off"}:
        blockers.append("lane disabled")
    if lane_mode not in PAPER_RECORDING_MODES:
        blockers.append(f"lane mode not paper/armed_dry_run/tiny_live shadow: {lane_mode or 'MISSING'}")
    if routed_candidate.get("candidate_age_seconds") is None:
        blockers.append("candidate freshness could not be confirmed")
    elif _float_or_none(routed_candidate.get("candidate_age_seconds")) is not None and _float_or_none(routed_candidate.get("freshness_seconds")) is not None:
        if float(routed_candidate["candidate_age_seconds"]) > float(routed_candidate["freshness_seconds"]):
            blockers.append("candidate is stale")
    max_daily_trades = _int_or_none(risk_limits.get("max_daily_trades"))
    if max_daily_trades is not None and max_daily_trades > 0 and daily_count >= max_daily_trades:
        blockers.append("lane max_daily_trades exceeded")
    if cooldown.get("active"):
        blockers.append("lane cooldown_after_loss_minutes is active")
    if _source_safety_blocked(routed_candidate):
        blockers.append("source safety reported execution/order/network/secret activity")
    return _dedupe(blockers)


def _paper_action_for_mode(mode: str) -> str:
    if mode == "paper":
        return PAPER_ENTRY_RECORDED
    if mode == "armed_dry_run":
        return ARMED_DRY_RUN_ENTRY_RECORDED
    if mode == "tiny_live":
        return PAPER_SHADOW_FOR_TINY_LIVE
    return PAPER_BLOCKED


def _entry_reference(row: Mapping[str, Any]) -> dict[str, float | None]:
    return {
        "entry": _float_or_none(_first_present(row, "entry", "entry_price", "fib_618")),
        "stop": _float_or_none(_first_present(row, "stop", "stop_price", "invalidation")),
        "take_profit": _float_or_none(_first_present(row, "take_profit", "take_profit_price", "target")),
        "score": _float_or_none(row.get("score")),
    }


def _risk_limits(lane: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    source = lane or row
    return {
        "max_daily_trades": _int_or_none(source.get("max_daily_trades")),
        "max_daily_loss_pct": _float_or_none(source.get("max_daily_loss_pct")),
        "cooldown_after_loss_minutes": _int_or_none(source.get("cooldown_after_loss_minutes")),
        "require_protective_orders": bool(source.get("require_protective_orders")),
    }


def _safety_from_source(row: Mapping[str, Any]) -> dict[str, bool]:
    source_safety = row.get("safety") if isinstance(row.get("safety"), Mapping) else {}
    payload = dict(PAPER_LANE_SAFETY)
    for key in BLOCKING_SAFETY_KEYS:
        payload[key] = bool(source_safety.get(key, False))
    payload["paper_live_separation_intact"] = not any(payload[key] for key in BLOCKING_SAFETY_KEYS)
    return payload


def _source_safety_blocked(row: Mapping[str, Any]) -> bool:
    safety = row.get("safety") if isinstance(row.get("safety"), Mapping) else {}
    return any(bool(safety.get(key)) for key in BLOCKING_SAFETY_KEYS)


def _compact_preview_records(records: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "paper_execution_id": record.get("paper_execution_id"),
            "candidate_id": record.get("candidate_id"),
            "lane_key": record.get("lane_key"),
            "lane_mode": record.get("lane_mode"),
            "route_status": record.get("route_status"),
            "route_action": record.get("route_action"),
            "paper_action": record.get("paper_action"),
            "blockers": list(record.get("blockers") or [])[:5],
            "safety": record.get("safety"),
        }
        for record in records[:5]
    ]


def _skip_payload(candidate: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate.get("candidate_id"),
        "lane_key": candidate.get("lane_key"),
        "route_status": candidate.get("route_status"),
        "reason": reason,
    }


def _cooldown_payload(
    *,
    active: bool,
    until: str | None,
    source_record_id: object,
    remaining_seconds: float,
) -> dict[str, Any]:
    return {
        "active": bool(active),
        "cooldown_until_utc": until,
        "source_paper_execution_id": source_record_id,
        "remaining_seconds": remaining_seconds,
    }


def _record_indicates_loss(record: Mapping[str, Any]) -> bool:
    outcome = str(_first_present(record, "outcome", "result", "close_reason") or "").strip().lower()
    if outcome in {"loss", "lost", "stop", "stopped", "stop_loss", "sl"}:
        return True
    pnl = _float_or_none(_first_present(record, "pnl_pct", "realized_pnl_pct", "pnl_usd"))
    return pnl is not None and pnl < 0


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _first_present(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
