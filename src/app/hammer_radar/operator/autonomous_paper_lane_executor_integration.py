"""R129 scheduler-to-paper lane executor integration.

This module connects R128 scheduler decisions to R125 paper lane execution
records. It is paper-only and never creates exchange payloads, calls Binance,
uses network access, mutates env files, or enables live execution.
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
from src.app.hammer_radar.operator.autonomous_paper_lane_execution import (
    AUTONOMOUS_PAPER_LANE_EXECUTIONS_LEDGER,
    PAPER_BLOCKED,
    PAPER_LANE_SAFETY,
    append_paper_lane_execution,
    build_paper_execution_from_routed_candidate,
    load_paper_lane_executions,
)
from src.app.hammer_radar.operator.fresh_signal_router import ROUTED_TO_LANE
from src.app.hammer_radar.operator.lane_autonomy_control_loop import (
    ARMED_DRY_RUN_INTENT,
    BLOCKED,
    IGNORE,
    PAPER_ENTRY_INTENT,
    PAPER_OBSERVE,
    TINY_LIVE_GATE_REVIEW,
)
from src.app.hammer_radar.operator.lane_autonomy_scheduler import (
    CONFIRM_AUTONOMY_SCHEDULER_RECORDING_PHRASE,
    run_lane_autonomy_scheduler_once,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, load_lane_controls

AUTONOMOUS_PAPER_LANE_EXECUTOR_INTEGRATIONS_LEDGER = "autonomous_paper_lane_executor_integrations.ndjson"
CONFIRM_PAPER_INTEGRATION_PHRASE = (
    "I CONFIRM AUTONOMOUS PAPER LANE INTEGRATION ONLY; NO REAL ORDER; NO BINANCE CALL."
)

PAPER_EXECUTOR_INTEGRATION_STATUS = "PAPER_EXECUTOR_INTEGRATION_STATUS"
PAPER_EXECUTOR_INTEGRATION_PREVIEW = "PAPER_EXECUTOR_INTEGRATION_PREVIEW"
PAPER_EXECUTOR_INTEGRATION_REJECTED = "PAPER_EXECUTOR_INTEGRATION_REJECTED"
PAPER_EXECUTOR_INTEGRATION_RECORDED = "PAPER_EXECUTOR_INTEGRATION_RECORDED"
PAPER_EXECUTOR_INTEGRATION_PARTIAL = "PAPER_EXECUTOR_INTEGRATION_PARTIAL"

ELIGIBLE_AUTONOMY_DECISIONS = {
    PAPER_ENTRY_INTENT,
    ARMED_DRY_RUN_INTENT,
    TINY_LIVE_GATE_REVIEW,
}
INELIGIBLE_AUTONOMY_DECISIONS = {IGNORE, PAPER_OBSERVE, BLOCKED}
BLOCKING_SAFETY_KEYS = (
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "order_payload_created",
    "network_allowed",
    "secrets_shown",
)
PAPER_EXECUTOR_INTEGRATION_SAFETY = {
    **SAFETY_FALSE,
    "paper_live_separation_intact": True,
}
SOURCE_SURFACES_USED = [
    "operator.lane_autonomy_scheduler.run_lane_autonomy_scheduler_once",
    "operator.lane_autonomy_control_loop autonomy decisions",
    "operator.autonomous_paper_lane_execution.build_paper_execution_from_routed_candidate",
    "operator.autonomous_paper_lane_execution.append_paper_lane_execution",
    "operator.autonomous_paper_lane_execution.load_paper_lane_executions",
    "operator.lane_control.load_lane_controls",
    "configs/hammer_radar/lane_controls.json",
    f"logs/hammer_radar_forward/{AUTONOMOUS_PAPER_LANE_EXECUTOR_INTEGRATIONS_LEDGER}",
    f"logs/hammer_radar_forward/{AUTONOMOUS_PAPER_LANE_EXECUTIONS_LEDGER}",
    "R129 paper integration confirmation phrase",
]


def build_autonomous_paper_lane_executor_integration_status(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = load_paper_executor_integration_records(log_dir=resolved_log_dir, limit=limit)
    return {
        "status": PAPER_EXECUTOR_INTEGRATION_STATUS,
        "generated_at": datetime.now(UTC).isoformat(),
        "ledger_path": str(_ledger_path(resolved_log_dir)),
        "paper_execution_ledger_path": str(resolved_log_dir / AUTONOMOUS_PAPER_LANE_EXECUTIONS_LEDGER),
        "recent_integrations": records,
        "integration_summary": summarize_paper_executor_integration_records(
            load_paper_executor_integration_records(log_dir=resolved_log_dir, limit=0)
        ),
        "safety": dict(PAPER_EXECUTOR_INTEGRATION_SAFETY),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }


def select_paper_executable_decisions(
    decisions: list[Mapping[str, Any]],
    *,
    controls: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    lane_map = controls.get("lane_map") if isinstance((controls or {}).get("lane_map"), Mapping) else {}
    eligible: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for decision in decisions:
        normalized = dict(decision)
        lane_key = str(normalized.get("lane_key") or "")
        autonomy_decision = str(normalized.get("autonomy_decision") or "UNKNOWN")
        blockers = list(normalized.get("blockers") or [])
        if blockers:
            blocked.append(_blocked_decision(normalized, "; ".join(blockers)))
            continue
        if autonomy_decision not in ELIGIBLE_AUTONOMY_DECISIONS:
            reason = _ineligible_reason(autonomy_decision)
            blocked.append(_blocked_decision(normalized, reason))
            continue
        if lane_map and lane_key not in lane_map:
            blocked.append(_blocked_decision(normalized, "selected lane not configured"))
            continue
        if _source_safety_blocked(normalized):
            blocked.append(_blocked_decision(normalized, "source safety reported execution/order/network/secret activity"))
            continue
        if _strategy_intent_is_executable(normalized.get("strategy_intent")):
            blocked.append(_blocked_decision(normalized, "strategy intent would imply direct executable order payload"))
            continue
        eligible.append(normalized)
    return {"eligible_decisions": eligible, "blocked_decisions": blocked}


def build_paper_execution_from_autonomy_decision(
    decision: Mapping[str, Any],
    *,
    lane: Mapping[str, Any] | None = None,
    existing_records: list[Mapping[str, Any]] | None = None,
    pending_daily_count: int = 0,
    now: datetime | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    routed_candidate = _routed_candidate_from_decision(decision, lane=lane)
    record = build_paper_execution_from_routed_candidate(
        routed_candidate,
        lane=lane,
        existing_records=existing_records,
        pending_daily_count=pending_daily_count,
        now=now,
        log_dir=log_dir,
    )
    return {
        **record,
        "source_autonomy_decision": decision.get("autonomy_decision"),
        "source_decision_id": decision.get("decision_id"),
        "paper_shadow_only": decision.get("autonomy_decision") == TINY_LIVE_GATE_REVIEW,
    }


def run_autonomous_paper_lane_executor_once(
    *,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    record_paper: bool = False,
    record_scheduler_tick: bool = False,
    record_decisions: bool = False,
    lane_key: str | None = None,
    all_lanes: bool = False,
    confirm_paper_integration: str | None = None,
    candidates: list[Mapping[str, Any] | object] | None = None,
    now: datetime | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    global_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    controls = load_lane_controls(config_path)
    selected_lane_keys = _selected_lane_keys(controls, lane_key=lane_key, all_lanes=all_lanes)
    confirmation_valid = confirm_paper_integration == CONFIRM_PAPER_INTEGRATION_PHRASE
    recording_allowed = bool(record_paper and confirmation_valid)
    scheduler_status = run_lane_autonomy_scheduler_once(
        log_dir=resolved_log_dir,
        config_path=config_path,
        record_tick=bool(record_scheduler_tick and recording_allowed),
        record_decisions=bool(record_decisions and recording_allowed),
        lane_key=lane_key,
        all_lanes=all_lanes,
        confirm_scheduler_record=CONFIRM_AUTONOMY_SCHEDULER_RECORDING_PHRASE if recording_allowed else None,
        candidates=candidates,
        now=generated_at,
        live_eligibility_matrix=live_eligibility_matrix,
        global_gate=global_gate,
    )
    decisions = [dict(row) for row in scheduler_status.get("decisions") or [] if isinstance(row, Mapping)]
    selected = select_paper_executable_decisions(decisions, controls=controls)
    eligible_decisions = selected["eligible_decisions"]
    blocked_decisions = selected["blocked_decisions"]
    existing_records = load_paper_lane_executions(log_dir=resolved_log_dir)
    pending_daily_counts: Counter[str] = Counter()
    preview_records: list[dict[str, Any]] = []
    for decision in eligible_decisions:
        lane = (controls.get("lane_map") or {}).get(str(decision.get("lane_key") or ""))
        record = build_paper_execution_from_autonomy_decision(
            decision,
            lane=lane,
            existing_records=existing_records,
            pending_daily_count=pending_daily_counts[str(decision.get("lane_key") or "")],
            now=generated_at,
            log_dir=resolved_log_dir,
        )
        preview_records.append(record)
        if record.get("paper_action") != PAPER_BLOCKED and not record.get("blockers"):
            pending_daily_counts[str(decision.get("lane_key") or "")] += 1
        else:
            blocked_decisions.append(_blocked_execution_record(record))

    recordable = [record for record in preview_records if record.get("paper_action") != PAPER_BLOCKED and not record.get("blockers")]
    fatal_blockers = _fatal_recording_blockers(
        scheduler_status=scheduler_status,
        selected_lane_keys=selected_lane_keys,
        controls=controls,
        lane_key=lane_key,
        candidate_records=preview_records,
        blocked_decisions=blocked_decisions,
    )
    paper_execution_ids: list[str] = []
    integration_recorded = False
    integration_id: str | None = None
    rejection_reason = None

    if record_paper and not confirmation_valid:
        status = PAPER_EXECUTOR_INTEGRATION_REJECTED
        rejection_reason = "missing or invalid paper integration confirmation"
    elif record_paper and fatal_blockers:
        status = PAPER_EXECUTOR_INTEGRATION_REJECTED
        rejection_reason = "; ".join(_dedupe(fatal_blockers))
    elif not record_paper:
        status = PAPER_EXECUTOR_INTEGRATION_PREVIEW
    else:
        for record in recordable:
            appended = append_paper_lane_execution(record, log_dir=resolved_log_dir)
            paper_execution_ids.append(str(appended["paper_execution_id"]))
        status = (
            PAPER_EXECUTOR_INTEGRATION_RECORDED
            if len(paper_execution_ids) == len(recordable) and not blocked_decisions
            else PAPER_EXECUTOR_INTEGRATION_PARTIAL
        )
        integration_record = build_paper_executor_integration_record(
            mode="record_paper",
            status=status,
            scheduler_status=scheduler_status,
            decisions_seen_count=len(decisions),
            blocked_decisions=blocked_decisions,
            paper_execution_ids=paper_execution_ids,
            recorded_at_utc=generated_at.isoformat(),
        )
        append_paper_executor_integration_record(integration_record, log_dir=resolved_log_dir)
        integration_recorded = True
        integration_id = str(integration_record["integration_id"])

    if integration_id is None and record_paper and not rejection_reason:
        integration_id = f"paper_executor_integration_{uuid4().hex}"

    payload = {
        "status": status,
        "generated_at": generated_at.isoformat(),
        "record_paper_requested": bool(record_paper),
        "record_scheduler_tick_requested": bool(record_scheduler_tick),
        "record_decisions_requested": bool(record_decisions),
        "confirmation_valid": bool(confirmation_valid),
        "selected_lane_keys": selected_lane_keys,
        "scheduler_status": scheduler_status.get("status"),
        "lanes_evaluated_count": int(scheduler_status.get("lanes_evaluated_count") or 0),
        "candidates_seen_count": int(scheduler_status.get("candidates_seen_count") or 0),
        "decisions_seen_count": len(decisions),
        "paper_eligible_decisions_count": len(eligible_decisions),
        "paper_blocked_decisions_count": len(blocked_decisions),
        "paper_execution_records_created": len(paper_execution_ids),
        "paper_execution_ids": paper_execution_ids,
        "candidate_decisions": _compact_decisions(eligible_decisions),
        "blocked_decisions": blocked_decisions[:10],
        "top_blockers": _top_blockers(blocked_decisions + [{"blockers": fatal_blockers}]),
        "integration_recorded": integration_recorded,
        "integration_id": integration_id,
        "safety": dict(PAPER_EXECUTOR_INTEGRATION_SAFETY),
        "ledger_path": str(_ledger_path(resolved_log_dir)),
        "paper_execution_ledger_path": str(resolved_log_dir / AUTONOMOUS_PAPER_LANE_EXECUTIONS_LEDGER),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }
    if rejection_reason:
        payload["rejection_reason"] = rejection_reason
    return payload


def build_paper_executor_integration_record(
    *,
    mode: str,
    status: str,
    scheduler_status: Mapping[str, Any],
    decisions_seen_count: int,
    blocked_decisions: list[Mapping[str, Any]],
    paper_execution_ids: list[str],
    recorded_at_utc: str | None = None,
) -> dict[str, Any]:
    return {
        "event_type": "AUTONOMOUS_PAPER_LANE_EXECUTOR_INTEGRATION",
        "integration_id": f"paper_executor_integration_{uuid4().hex}",
        "recorded_at_utc": recorded_at_utc or datetime.now(UTC).isoformat(),
        "mode": mode if mode in {"preview", "record_paper"} else "preview",
        "status": status,
        "scheduler_status": scheduler_status.get("status"),
        "decisions_seen_count": int(decisions_seen_count),
        "paper_eligible_decisions_count": max(int(decisions_seen_count) - len(blocked_decisions), 0),
        "paper_blocked_decisions_count": len(blocked_decisions),
        "paper_execution_records_created": len(paper_execution_ids),
        "paper_execution_ids": list(paper_execution_ids),
        "blocked_decisions": list(blocked_decisions)[:10],
        "top_blockers": _top_blockers(blocked_decisions),
        "safety": dict(PAPER_EXECUTOR_INTEGRATION_SAFETY),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }


def append_paper_executor_integration_record(
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


def load_paper_executor_integration_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = _ledger_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    if limit > 0:
        return list(reversed(records))[:limit]
    return records


def summarize_paper_executor_integration_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    mode_counts = Counter(str(record.get("mode") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "mode_counts": dict(sorted(mode_counts.items())),
        "paper_execution_records_created": sum(int(record.get("paper_execution_records_created") or 0) for record in records),
        "top_blockers": _top_blockers(records),
        "safety": dict(PAPER_EXECUTOR_INTEGRATION_SAFETY),
    }


def format_autonomous_paper_lane_executor_integration_status_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _routed_candidate_from_decision(decision: Mapping[str, Any], *, lane: Mapping[str, Any] | None) -> dict[str, Any]:
    lane_record = dict(lane or {})
    lane_mode = str(decision.get("lane_mode") or lane_record.get("mode") or "disabled").strip().lower()
    strategy_intent = decision.get("strategy_intent") if isinstance(decision.get("strategy_intent"), Mapping) else {}
    intent_summary = (
        decision.get("strategy_intent_summary")
        if isinstance(decision.get("strategy_intent_summary"), Mapping)
        else {}
    )
    entry_reference = strategy_intent.get("entry_reference") if strategy_intent else None
    stop_reference = strategy_intent.get("stop_reference") if strategy_intent else None
    take_profit_reference = strategy_intent.get("take_profit_reference") if strategy_intent else None
    if entry_reference is None and intent_summary.get("has_entry_reference") is True:
        entry_reference = None
    return {
        "candidate_id": decision.get("candidate_id"),
        "lane_key": decision.get("lane_key") or lane_record.get("lane_key"),
        "symbol": lane_record.get("symbol"),
        "timeframe": lane_record.get("timeframe"),
        "direction": lane_record.get("direction"),
        "entry_mode": lane_record.get("entry_mode"),
        "lane_mode": lane_mode,
        "route_status": decision.get("route_status") or ROUTED_TO_LANE,
        "route_action": _route_action_for_decision(str(decision.get("autonomy_decision") or "")),
        "candidate_age_seconds": 0,
        "freshness_seconds": lane_record.get("freshness_seconds"),
        "entry_reference": entry_reference,
        "stop_reference": stop_reference,
        "take_profit_reference": take_profit_reference,
        "score": strategy_intent.get("score") if strategy_intent else None,
        "safety": _safety_from_source(decision),
    }


def _route_action_for_decision(autonomy_decision: str) -> str:
    if autonomy_decision == PAPER_ENTRY_INTENT:
        return "PAPER_OBSERVE"
    if autonomy_decision == ARMED_DRY_RUN_INTENT:
        return "ARMED_DRY_RUN_OBSERVE"
    if autonomy_decision == TINY_LIVE_GATE_REVIEW:
        return "TINY_LIVE_BLOCKED_BY_GLOBAL_GATES"
    return "IGNORE"


def _fatal_recording_blockers(
    *,
    scheduler_status: Mapping[str, Any],
    selected_lane_keys: list[str],
    controls: Mapping[str, Any],
    lane_key: str | None,
    candidate_records: list[Mapping[str, Any]],
    blocked_decisions: list[Mapping[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    lane_map = controls.get("lane_map") if isinstance(controls.get("lane_map"), Mapping) else {}
    if lane_key and lane_key not in lane_map:
        blockers.append("selected lane not configured")
    for key in selected_lane_keys:
        if key not in lane_map:
            blockers.append("selected lane not configured")
    safety = scheduler_status.get("safety") if isinstance(scheduler_status.get("safety"), Mapping) else {}
    blockers.extend(_safety_blockers(safety, prefix="source safety field is unsafe"))
    if safety.get("paper_live_separation_intact") is False:
        blockers.append("paper_live_separation_intact false")
    if scheduler_status.get("status") == "LANE_AUTONOMY_SCHEDULER_REJECTED":
        blockers.append(str(scheduler_status.get("rejection_reason") or "scheduler rejected recording"))
    for record in candidate_records:
        for blocker in record.get("blockers") or []:
            if blocker in {
                "lane max_daily_trades exceeded",
                "lane cooldown_after_loss_minutes is active",
                "paper execution builder reports unsafe state",
            }:
                blockers.append(str(blocker))
        record_safety = record.get("safety") if isinstance(record.get("safety"), Mapping) else {}
        blockers.extend(_safety_blockers(record_safety, prefix="paper execution builder reports unsafe state"))
        if record_safety.get("paper_live_separation_intact") is False:
            blockers.append("paper execution builder reports unsafe state")
    for decision in blocked_decisions:
        for blocker in decision.get("blockers") or []:
            if str(blocker) in {
                "lane max_daily_trades exceeded",
                "lane cooldown_after_loss_minutes is active",
                "strategy intent would imply direct executable order payload",
                "source safety reported execution/order/network/secret activity",
            }:
                blockers.append(str(blocker))
    return _dedupe(blockers)


def _safety_blockers(safety: Mapping[str, Any], *, prefix: str) -> list[str]:
    return [f"{prefix}: {key}=true" for key in BLOCKING_SAFETY_KEYS if safety.get(key) is True]


def _source_safety_blocked(row: Mapping[str, Any]) -> bool:
    safety = row.get("safety") if isinstance(row.get("safety"), Mapping) else {}
    return any(bool(safety.get(key)) for key in BLOCKING_SAFETY_KEYS) or safety.get("paper_live_separation_intact") is False


def _safety_from_source(row: Mapping[str, Any]) -> dict[str, bool]:
    source_safety = row.get("safety") if isinstance(row.get("safety"), Mapping) else {}
    payload = dict(PAPER_LANE_SAFETY)
    for key in BLOCKING_SAFETY_KEYS:
        payload[key] = bool(source_safety.get(key, False))
    payload["paper_live_separation_intact"] = not any(payload[key] for key in BLOCKING_SAFETY_KEYS)
    if source_safety.get("paper_live_separation_intact") is False:
        payload["paper_live_separation_intact"] = False
    return payload


def _strategy_intent_is_executable(intent: object) -> bool:
    if not isinstance(intent, Mapping):
        return False
    size_policy = intent.get("size_policy") if isinstance(intent.get("size_policy"), Mapping) else {}
    exit_policy = intent.get("exit_policy") if isinstance(intent.get("exit_policy"), Mapping) else {}
    return size_policy.get("direct_live_quantity") is not None or exit_policy.get("direct_exchange_payload") is not None


def _blocked_decision(decision: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {
        "decision_id": decision.get("decision_id"),
        "candidate_id": decision.get("candidate_id"),
        "lane_key": decision.get("lane_key"),
        "autonomy_decision": decision.get("autonomy_decision"),
        "route_status": decision.get("route_status"),
        "blockers": [reason],
    }


def _blocked_execution_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision_id": record.get("source_decision_id"),
        "candidate_id": record.get("candidate_id"),
        "lane_key": record.get("lane_key"),
        "autonomy_decision": record.get("source_autonomy_decision"),
        "route_status": record.get("route_status"),
        "blockers": list(record.get("blockers") or ["paper execution builder reports blocked state"]),
    }


def _ineligible_reason(autonomy_decision: str) -> str:
    if autonomy_decision in INELIGIBLE_AUTONOMY_DECISIONS:
        return f"autonomy decision is not paper executable: {autonomy_decision}"
    return f"unknown autonomy decision is not paper executable: {autonomy_decision}"


def _selected_lane_keys(controls: Mapping[str, Any], *, lane_key: str | None, all_lanes: bool) -> list[str]:
    if lane_key:
        return [str(lane_key)]
    lanes = list(controls.get("lanes") or [])
    if all_lanes or not lane_key:
        return [str(lane.get("lane_key")) for lane in lanes if lane.get("lane_key")]
    return []


def _compact_decisions(decisions: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "decision_id": decision.get("decision_id"),
            "candidate_id": decision.get("candidate_id"),
            "lane_key": decision.get("lane_key"),
            "lane_mode": decision.get("lane_mode"),
            "route_status": decision.get("route_status"),
            "autonomy_decision": decision.get("autonomy_decision"),
        }
        for decision in decisions[:10]
    ]


def _top_blockers(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(blocker for row in rows for blocker in list(row.get("blockers") or []))
    return [{"blocker": blocker, "count": count} for blocker, count in counts.most_common(5)]


def _ledger_path(log_dir: Path) -> Path:
    return log_dir / AUTONOMOUS_PAPER_LANE_EXECUTOR_INTEGRATIONS_LEDGER


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
