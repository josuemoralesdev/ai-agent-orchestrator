"""R127 autonomous lane control loop scaffold.

This module composes R122 lane controls, R123 fresh routing, and R125 paper
ledger limit checks into non-executing autonomy decisions. It never creates
exchange order payloads, calls Binance, uses network access, mutates env files,
or enables live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir, get_signals_path, load_signals
from src.app.hammer_radar.operator.autonomous_paper_lane_execution import (
    compute_lane_cooldown_status,
    compute_lane_daily_count,
    load_paper_lane_executions,
)
from src.app.hammer_radar.operator.fresh_signal_router import (
    BLOCKED_BY_LANE,
    EXPIRED_SIGNAL,
    NO_MATCHING_LANE,
    ROUTER_ERROR,
    ROUTER_NO_CANDIDATES,
    ROUTER_NO_CANDIDATE_SOURCE,
    ROUTED_TO_LANE,
    evaluate_candidate_against_lanes,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, load_lane_controls
from src.app.hammer_radar.operator.strategy_performance import build_live_eligibility_matrix

LANE_AUTONOMY_DECISIONS_LEDGER = "lane_autonomy_decisions.ndjson"
CONFIRM_AUTONOMY_DECISION_RECORDING_PHRASE = (
    "I CONFIRM AUTONOMY DECISION RECORDING ONLY; NO ORDER; NO BINANCE CALL."
)

LANE_AUTONOMY_PREVIEW = "LANE_AUTONOMY_PREVIEW"
LANE_AUTONOMY_REJECTED = "LANE_AUTONOMY_REJECTED"
LANE_AUTONOMY_RECORDED = "LANE_AUTONOMY_RECORDED"
LANE_AUTONOMY_PARTIAL = "LANE_AUTONOMY_PARTIAL"

IGNORE = "IGNORE"
PAPER_OBSERVE = "PAPER_OBSERVE"
PAPER_ENTRY_INTENT = "PAPER_ENTRY_INTENT"
ARMED_DRY_RUN_INTENT = "ARMED_DRY_RUN_INTENT"
TINY_LIVE_GATE_REVIEW = "TINY_LIVE_GATE_REVIEW"
BLOCKED = "BLOCKED"

BLOCKING_SAFETY_KEYS = (
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "order_payload_created",
    "network_allowed",
    "secrets_shown",
)
AUTONOMY_SAFETY = {
    **SAFETY_FALSE,
    "paper_live_separation_intact": True,
}
SOURCE_SURFACES_USED = [
    "operator.lane_control.load_lane_controls",
    "operator.fresh_signal_router.evaluate_candidate_against_lanes",
    "operator.autonomous_paper_lane_execution.load_paper_lane_executions",
    "operator.autonomous_paper_lane_execution.compute_lane_daily_count",
    "operator.autonomous_paper_lane_execution.compute_lane_cooldown_status",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{LANE_AUTONOMY_DECISIONS_LEDGER}",
    "R127 autonomy decision-record confirmation phrase",
]
COMPACT_DECISION_OUTPUT_LIMIT = 25


def build_lane_autonomy_control_loop_status(
    *,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    record_decision: bool = False,
    lane_key: str | None = None,
    all_lanes: bool = False,
    confirm_decision_record: str | None = None,
    candidates: list[Mapping[str, Any] | object] | None = None,
    now: datetime | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    global_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    controls = load_lane_controls(config_path)
    selected_lane_keys = _selected_lane_keys(controls, lane_key=lane_key, all_lanes=all_lanes)
    confirmation_valid = confirm_decision_record == CONFIRM_AUTONOMY_DECISION_RECORDING_PHRASE
    fatal_blockers: list[str] = []

    if lane_key and lane_key not in (controls.get("lane_map") or {}):
        fatal_blockers.append("selected lane not configured")

    source_candidates, source_status = _source_candidates(candidates=candidates, log_dir=resolved_log_dir)
    if source_status == ROUTER_NO_CANDIDATE_SOURCE:
        source_candidates = []
    matrix = live_eligibility_matrix if live_eligibility_matrix is not None else build_live_eligibility_matrix(log_dir=resolved_log_dir)
    existing_records = load_paper_lane_executions(log_dir=resolved_log_dir)
    pending_daily_counts: Counter[str] = Counter()
    decisions: list[dict[str, Any]] = []

    if source_status == ROUTER_NO_CANDIDATES or source_status == ROUTER_NO_CANDIDATE_SOURCE:
        for key in selected_lane_keys:
            lane = (controls.get("lane_map") or {}).get(key)
            decisions.append(
                evaluate_lane_autonomy_decision(
                    routed_candidate={"lane_key": key, "route_status": source_status, "lane_mode": (lane or {}).get("mode"), "blockers": [source_status]},
                    lane=lane,
                    existing_records=existing_records,
                    pending_daily_count=0,
                    now=generated_at,
                )
            )
    else:
        for candidate in source_candidates:
            try:
                routed = evaluate_candidate_against_lanes(
                    candidate,
                    controls=controls,
                    live_eligibility_matrix=matrix,
                    global_gate=global_gate,
                    now=generated_at,
                    log_dir=resolved_log_dir,
                )
                routed = {**_candidate_extra_fields(candidate), **routed}
            except Exception:  # pragma: no cover - defensive diagnostic surface
                routed = {
                    **_candidate_extra_fields(candidate),
                    "route_status": ROUTER_ERROR,
                    "lane_key": None,
                    "lane_mode": "disabled",
                    "candidate_id": _candidate_extra_fields(candidate).get("candidate_id"),
                    "blockers": ["route source returned error"],
                    "safety": dict(AUTONOMY_SAFETY),
                }
            candidate_lane_key = str(routed.get("lane_key") or "")
            if lane_key and candidate_lane_key not in selected_lane_keys:
                continue
            if not all_lanes and not lane_key and candidate_lane_key not in selected_lane_keys:
                continue
            lane = (controls.get("lane_map") or {}).get(candidate_lane_key)
            decision = evaluate_lane_autonomy_decision(
                routed_candidate=routed,
                lane=lane,
                existing_records=existing_records,
                pending_daily_count=pending_daily_counts[candidate_lane_key],
                now=generated_at,
            )
            decisions.append(decision)
            if decision.get("autonomy_decision") in {PAPER_ENTRY_INTENT, ARMED_DRY_RUN_INTENT, TINY_LIVE_GATE_REVIEW}:
                pending_daily_counts[candidate_lane_key] += 1

    if any(decision.get("route_status") == ROUTER_ERROR for decision in decisions):
        fatal_blockers.append("route source returns error")
    unsafe_reasons = _unsafe_recording_reasons(decisions)
    fatal_blockers.extend(unsafe_reasons)

    recorded_ids: list[str] = []
    rejection_reason = None
    if record_decision and not confirmation_valid:
        status = LANE_AUTONOMY_REJECTED
        rejection_reason = "missing or invalid decision-record confirmation"
    elif record_decision and fatal_blockers:
        status = LANE_AUTONOMY_REJECTED
        rejection_reason = "; ".join(_dedupe(fatal_blockers))
    elif not record_decision:
        status = LANE_AUTONOMY_PREVIEW
    else:
        for decision in decisions:
            append_lane_autonomy_decision(decision, log_dir=resolved_log_dir)
            recorded_ids.append(str(decision["decision_id"]))
        status = LANE_AUTONOMY_RECORDED if len(recorded_ids) == len(decisions) else LANE_AUTONOMY_PARTIAL

    payload = {
        "status": status,
        "generated_at": generated_at.isoformat(),
        "record_decision_requested": bool(record_decision),
        "confirmation_valid": bool(confirmation_valid),
        "selected_lane_keys": selected_lane_keys,
        "lanes_evaluated_count": len(selected_lane_keys),
        "candidates_seen_count": len(source_candidates),
        "decisions_count": len(decisions),
        "recorded_count": len(recorded_ids),
        "recorded_decision_ids": recorded_ids,
        "decisions": [_compact_decision(decision) for decision in decisions[:COMPACT_DECISION_OUTPUT_LIMIT]],
        "top_blockers": _top_blockers(decisions + [{"blockers": fatal_blockers}]),
        "safety": _safety_summary(decisions),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
        "ledger_path": str(_ledger_path(resolved_log_dir)),
    }
    if rejection_reason:
        payload["rejection_reason"] = rejection_reason
    return payload


def evaluate_lane_autonomy_decision(
    routed_candidate: Mapping[str, Any],
    *,
    lane: Mapping[str, Any] | None = None,
    existing_records: list[Mapping[str, Any]] | None = None,
    pending_daily_count: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    lane_record = dict(lane or {})
    lane_key = str(routed_candidate.get("lane_key") or lane_record.get("lane_key") or "")
    lane_mode = str(routed_candidate.get("lane_mode") or lane_record.get("mode") or "disabled").strip().lower()
    risk_limits = _risk_limits(lane_record, routed_candidate)
    source_records = list(existing_records or [])
    daily_count = compute_lane_daily_count(lane_key, records=source_records, day=generated_at.date()) + max(pending_daily_count, 0)
    daily_loss_pct = _lane_daily_loss_pct(lane_key, records=source_records, day=generated_at.date())
    cooldown = compute_lane_cooldown_status(
        lane_key,
        cooldown_after_loss_minutes=_int_or_none(risk_limits.get("cooldown_after_loss_minutes")),
        records=source_records,
        now=generated_at,
    )
    blockers = _decision_blockers(
        routed_candidate=routed_candidate,
        lane=lane_record,
        lane_mode=lane_mode,
        risk_limits=risk_limits,
        daily_count=daily_count,
        daily_loss_pct=daily_loss_pct,
        cooldown=cooldown,
    )
    warnings = ["R127 records autonomy decisions only; it cannot place orders."]
    decision = _autonomy_decision(lane_mode=lane_mode, route_status=str(routed_candidate.get("route_status") or ""), blockers=blockers)
    strategy_intent = build_non_executing_strategy_intent(
        routed_candidate,
        lane=lane_record,
        risk_limits=risk_limits,
    )
    safety = _safety_from_source(routed_candidate)
    if _strategy_intent_is_executable(strategy_intent):
        decision = BLOCKED
        blockers.append("strategy intent would imply direct executable order payload")
    if safety["paper_live_separation_intact"] is not True:
        decision = BLOCKED
        blockers.append("source safety reported execution/order/network/secret activity")

    return {
        "event_type": "LANE_AUTONOMY_DECISION",
        "decision_id": f"lane_autonomy_{uuid4().hex}",
        "recorded_at_utc": generated_at.isoformat(),
        "lane_key": lane_key,
        "lane_mode": lane_mode,
        "candidate_id": routed_candidate.get("candidate_id"),
        "route_status": routed_candidate.get("route_status"),
        "autonomy_decision": decision,
        "strategy_intent": strategy_intent,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "safety": safety,
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }


def build_non_executing_strategy_intent(
    candidate: Mapping[str, Any],
    *,
    lane: Mapping[str, Any] | None = None,
    risk_limits: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    limits = dict(risk_limits or _risk_limits(lane or {}, candidate))
    protective_required = bool(limits.get("require_protective_orders"))
    if protective_required:
        protective_mode = "REQUIRED"
    elif limits.get("require_protective_orders") is False:
        protective_mode = "PREVIEW_ONLY"
    else:
        protective_mode = "UNKNOWN"
    return {
        "entry_reference": _float_or_none(_first_present(candidate, "entry_reference", "entry", "entry_price", "fib_618")),
        "stop_reference": _float_or_none(_first_present(candidate, "stop_reference", "stop", "stop_price", "invalidation")),
        "take_profit_reference": _float_or_none(
            _first_present(candidate, "take_profit_reference", "take_profit", "take_profit_price", "target")
        ),
        "score": _float_or_none(candidate.get("score")),
        "size_policy": {
            "type": "risk_contract_reference",
            "max_daily_loss_pct": _float_or_none(limits.get("max_daily_loss_pct")),
            "max_daily_trades": _int_or_none(limits.get("max_daily_trades")),
            "direct_live_quantity": None,
        },
        "exit_policy": {
            "protective_orders_required": protective_required,
            "protective_order_mode": protective_mode,
            "direct_exchange_payload": None,
        },
    }


def append_lane_autonomy_decision(
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


def load_lane_autonomy_decisions(
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


def summarize_lane_autonomy_decisions(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    decision_counts = Counter(str(record.get("autonomy_decision") or "UNKNOWN") for record in records)
    lane_counts = Counter(str(record.get("lane_key") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "decision_counts": dict(sorted(decision_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "top_blockers": _top_blockers(records),
        "safety": _safety_summary(records),
    }


def format_lane_autonomy_control_loop_status_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _ledger_path(log_dir: Path) -> Path:
    return log_dir / LANE_AUTONOMY_DECISIONS_LEDGER


def _source_candidates(*, candidates: list[Mapping[str, Any] | object] | None, log_dir: Path) -> tuple[list[Mapping[str, Any] | object], str]:
    if candidates is not None:
        return list(candidates), ROUTER_NO_CANDIDATES if not candidates else "provided_candidates"
    source_path = get_signals_path(log_dir)
    if not source_path.exists():
        return [], ROUTER_NO_CANDIDATE_SOURCE
    loaded = load_signals(log_dir)
    if not loaded:
        return [], ROUTER_NO_CANDIDATES
    return loaded, "signals_ndjson"


def _selected_lane_keys(controls: Mapping[str, Any], *, lane_key: str | None, all_lanes: bool) -> list[str]:
    if lane_key:
        return [str(lane_key)]
    lanes = list(controls.get("lanes") or [])
    if all_lanes or not lane_key:
        return [str(lane.get("lane_key")) for lane in lanes if lane.get("lane_key")]
    return []


def _decision_blockers(
    *,
    routed_candidate: Mapping[str, Any],
    lane: Mapping[str, Any],
    lane_mode: str,
    risk_limits: Mapping[str, Any],
    daily_count: int,
    daily_loss_pct: float,
    cooldown: Mapping[str, Any],
) -> list[str]:
    blockers = list(routed_candidate.get("blockers") or [])
    route_status = str(routed_candidate.get("route_status") or "")
    if route_status in {ROUTER_NO_CANDIDATE_SOURCE, ROUTER_NO_CANDIDATES}:
        return _dedupe(blockers or [route_status])
    if route_status == ROUTER_ERROR:
        blockers.append("route source returns error")
    if route_status == NO_MATCHING_LANE:
        blockers.append("no matching lane")
    if route_status == EXPIRED_SIGNAL:
        blockers.append("candidate is stale")
    if route_status == BLOCKED_BY_LANE:
        blockers.append("candidate blocked by lane permission")
    if not lane:
        blockers.append("no matching lane")
    if lane_mode in {"", "disabled", "off"}:
        blockers.append("lane disabled")
    if route_status != ROUTED_TO_LANE and route_status not in {NO_MATCHING_LANE, EXPIRED_SIGNAL, BLOCKED_BY_LANE, ROUTER_ERROR}:
        blockers.append(f"candidate route_status is not ROUTED_TO_LANE: {route_status or 'MISSING'}")
    max_daily_trades = _int_or_none(risk_limits.get("max_daily_trades"))
    if max_daily_trades is not None and max_daily_trades > 0 and daily_count >= max_daily_trades:
        blockers.append("lane max_daily_trades exceeded")
    max_daily_loss_pct = _float_or_none(risk_limits.get("max_daily_loss_pct"))
    if max_daily_loss_pct is not None and max_daily_loss_pct > 0 and daily_loss_pct >= max_daily_loss_pct:
        blockers.append("lane max_daily_loss_pct exceeded")
    if cooldown.get("active"):
        blockers.append("lane cooldown_after_loss_minutes is active")
    if _source_safety_blocked(routed_candidate):
        blockers.append("source safety reported execution/order/network/secret activity")
    return _dedupe(blockers)


def _autonomy_decision(*, lane_mode: str, route_status: str, blockers: list[str]) -> str:
    if route_status in {ROUTER_NO_CANDIDATE_SOURCE, ROUTER_NO_CANDIDATES, NO_MATCHING_LANE}:
        return IGNORE
    if blockers:
        return BLOCKED
    if route_status != ROUTED_TO_LANE:
        return IGNORE
    if lane_mode == "paper":
        return PAPER_ENTRY_INTENT
    if lane_mode == "armed_dry_run":
        return ARMED_DRY_RUN_INTENT
    if lane_mode == "tiny_live":
        return TINY_LIVE_GATE_REVIEW
    return PAPER_OBSERVE if lane_mode else IGNORE


def _risk_limits(lane: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    source = lane or row
    return {
        "max_daily_trades": _int_or_none(source.get("max_daily_trades")),
        "max_daily_loss_pct": _float_or_none(source.get("max_daily_loss_pct")),
        "cooldown_after_loss_minutes": _int_or_none(source.get("cooldown_after_loss_minutes")),
        "require_protective_orders": bool(source.get("require_protective_orders")),
    }


def _lane_daily_loss_pct(lane_key: str, *, records: list[Mapping[str, Any]], day: date) -> float:
    total = 0.0
    for record in records:
        if record.get("lane_key") != lane_key:
            continue
        recorded_at = _parse_timestamp(record.get("recorded_at_utc"))
        if recorded_at is None or recorded_at.date() != day:
            continue
        pnl = _float_or_none(_first_present(record, "pnl_pct", "realized_pnl_pct"))
        if pnl is not None and pnl < 0:
            total += abs(pnl)
    return total


def _candidate_extra_fields(candidate: Mapping[str, Any] | object) -> dict[str, Any]:
    if isinstance(candidate, Mapping):
        raw = dict(candidate)
    elif is_dataclass(candidate):
        raw = asdict(candidate)
    else:
        raw = {
            key: getattr(candidate, key)
            for key in (
                "candidate_id",
                "signal_id",
                "entry",
                "entry_price",
                "fib_618",
                "stop",
                "stop_price",
                "invalidation",
                "take_profit",
                "take_profit_price",
                "target",
                "score",
            )
            if hasattr(candidate, key)
        }
    if "candidate_id" not in raw and "signal_id" in raw:
        raw["candidate_id"] = raw.get("signal_id")
    return raw


def _safety_from_source(row: Mapping[str, Any]) -> dict[str, bool]:
    source_safety = row.get("safety") if isinstance(row.get("safety"), Mapping) else {}
    payload = dict(AUTONOMY_SAFETY)
    for key in BLOCKING_SAFETY_KEYS:
        payload[key] = bool(source_safety.get(key, False))
    payload["paper_live_separation_intact"] = not any(payload[key] for key in BLOCKING_SAFETY_KEYS)
    return payload


def _source_safety_blocked(row: Mapping[str, Any]) -> bool:
    safety = row.get("safety") if isinstance(row.get("safety"), Mapping) else {}
    return any(bool(safety.get(key)) for key in BLOCKING_SAFETY_KEYS)


def _strategy_intent_is_executable(intent: Mapping[str, Any]) -> bool:
    size_policy = intent.get("size_policy") if isinstance(intent.get("size_policy"), Mapping) else {}
    exit_policy = intent.get("exit_policy") if isinstance(intent.get("exit_policy"), Mapping) else {}
    return size_policy.get("direct_live_quantity") is not None or exit_policy.get("direct_exchange_payload") is not None


def _unsafe_recording_reasons(decisions: list[Mapping[str, Any]]) -> list[str]:
    reasons: list[str] = []
    for decision in decisions:
        safety = decision.get("safety") if isinstance(decision.get("safety"), Mapping) else {}
        for key in BLOCKING_SAFETY_KEYS:
            if safety.get(key) is True:
                reasons.append(f"safety field is unsafe: {key}=true")
        if safety.get("paper_live_separation_intact") is not True:
            reasons.append("paper_live_separation_intact false")
        intent = decision.get("strategy_intent") if isinstance(decision.get("strategy_intent"), Mapping) else {}
        if _strategy_intent_is_executable(intent):
            reasons.append("decision would imply direct executable order payload")
    return _dedupe(reasons)


def _compact_decision(decision: Mapping[str, Any]) -> dict[str, Any]:
    intent = decision.get("strategy_intent") if isinstance(decision.get("strategy_intent"), Mapping) else {}
    size_policy = intent.get("size_policy") if isinstance(intent.get("size_policy"), Mapping) else {}
    exit_policy = intent.get("exit_policy") if isinstance(intent.get("exit_policy"), Mapping) else {}
    return {
        "lane_key": decision.get("lane_key"),
        "lane_mode": decision.get("lane_mode"),
        "candidate_id": decision.get("candidate_id"),
        "route_status": decision.get("route_status"),
        "autonomy_decision": decision.get("autonomy_decision"),
        "strategy_intent_summary": {
            "has_entry_reference": intent.get("entry_reference") is not None,
            "has_stop_reference": intent.get("stop_reference") is not None,
            "has_take_profit_reference": intent.get("take_profit_reference") is not None,
            "size_policy_type": size_policy.get("type"),
            "exit_policy": exit_policy.get("protective_order_mode"),
        },
        "blockers": list(decision.get("blockers") or [])[:5],
    }


def _top_blockers(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(blocker for row in rows for blocker in list(row.get("blockers") or []))
    return [{"blocker": blocker, "count": count} for blocker, count in counts.most_common(5)]


def _safety_summary(rows: list[Mapping[str, Any]]) -> dict[str, bool]:
    summary = dict(AUTONOMY_SAFETY)
    for key in BLOCKING_SAFETY_KEYS:
        summary[key] = any(bool((row.get("safety") or {}).get(key)) for row in rows)
    summary["paper_live_separation_intact"] = all(
        (row.get("safety") or {}).get("paper_live_separation_intact") is True for row in rows
    ) if rows else True
    return summary


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
