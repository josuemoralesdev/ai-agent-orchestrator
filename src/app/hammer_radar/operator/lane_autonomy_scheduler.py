"""R128 lane autonomy scheduler scaffold.

This module wraps the R127 non-executing lane autonomy control loop in a
scheduler tick surface. It records scheduler audit ticks only after exact
confirmation and never creates order payloads, calls Binance, uses network
access, mutates env files, or enables live execution.
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
from src.app.hammer_radar.operator.lane_autonomy_control_loop import (
    CONFIRM_AUTONOMY_DECISION_RECORDING_PHRASE,
    build_lane_autonomy_control_loop_status,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, load_lane_controls

LANE_AUTONOMY_SCHEDULER_TICKS_LEDGER = "lane_autonomy_scheduler_ticks.ndjson"
CONFIRM_AUTONOMY_SCHEDULER_RECORDING_PHRASE = (
    "I CONFIRM AUTONOMY SCHEDULER RECORDING ONLY; NO ORDER; NO BINANCE CALL."
)

LANE_AUTONOMY_SCHEDULER_PREVIEW = "LANE_AUTONOMY_SCHEDULER_PREVIEW"
LANE_AUTONOMY_SCHEDULER_REJECTED = "LANE_AUTONOMY_SCHEDULER_REJECTED"
LANE_AUTONOMY_SCHEDULER_TICK_RECORDED = "LANE_AUTONOMY_SCHEDULER_TICK_RECORDED"

BLOCKING_SAFETY_KEYS = (
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "order_payload_created",
    "network_allowed",
    "secrets_shown",
)
SCHEDULER_SAFETY = {
    **SAFETY_FALSE,
    "paper_live_separation_intact": True,
}
SOURCE_SURFACES_USED = [
    "operator.lane_autonomy_control_loop.build_lane_autonomy_control_loop_status",
    "operator.lane_control.load_lane_controls",
    "configs/hammer_radar/lane_controls.json",
    "logs/hammer_radar_forward/lane_autonomy_decisions.ndjson",
    f"logs/hammer_radar_forward/{LANE_AUTONOMY_SCHEDULER_TICKS_LEDGER}",
    "R128 scheduler-record confirmation phrase",
]


def build_lane_autonomy_scheduler_status(
    *,
    log_dir: str | Path | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = load_scheduler_tick_records(log_dir=resolved_log_dir, limit=limit)
    return {
        "status": "LANE_AUTONOMY_SCHEDULER_STATUS",
        "generated_at": datetime.now(UTC).isoformat(),
        "ledger_path": str(_ledger_path(resolved_log_dir)),
        "recent_ticks": records,
        "scheduler_summary": summarize_scheduler_ticks(load_scheduler_tick_records(log_dir=resolved_log_dir, limit=0)),
        "safety": dict(SCHEDULER_SAFETY),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }


def run_lane_autonomy_scheduler_once(
    *,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    record_tick: bool = False,
    record_decisions: bool = False,
    lane_key: str | None = None,
    all_lanes: bool = False,
    confirm_scheduler_record: str | None = None,
    candidates: list[Mapping[str, Any] | object] | None = None,
    now: datetime | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    global_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_scheduler_record == CONFIRM_AUTONOMY_SCHEDULER_RECORDING_PHRASE
    loop_preview = build_lane_autonomy_control_loop_status(
        log_dir=resolved_log_dir,
        config_path=config_path,
        record_decision=False,
        lane_key=lane_key,
        all_lanes=all_lanes,
        candidates=candidates,
        now=generated_at,
        live_eligibility_matrix=live_eligibility_matrix,
        global_gate=global_gate,
    )
    blockers = _recording_blockers(loop_preview, config_path=config_path, lane_key=lane_key)
    blockers.extend(_candidate_source_safety_blockers(candidates))
    recording_requested = bool(record_tick or record_decisions)
    tick_recorded = False
    tick_record: dict[str, Any] | None = None
    recorded_decision_ids: list[str] = []
    rejection_reason = None

    if recording_requested and not confirmation_valid:
        status = LANE_AUTONOMY_SCHEDULER_REJECTED
        rejection_reason = "missing or invalid scheduler-record confirmation"
    elif recording_requested and blockers:
        status = LANE_AUTONOMY_SCHEDULER_REJECTED
        rejection_reason = "; ".join(_dedupe(blockers))
    elif not recording_requested:
        status = LANE_AUTONOMY_SCHEDULER_PREVIEW
    else:
        loop_recorded = loop_preview
        if record_decisions:
            loop_recorded = build_lane_autonomy_control_loop_status(
                log_dir=resolved_log_dir,
                config_path=config_path,
                record_decision=True,
                lane_key=lane_key,
                all_lanes=all_lanes,
                confirm_decision_record=CONFIRM_AUTONOMY_DECISION_RECORDING_PHRASE,
                candidates=candidates,
                now=generated_at,
                live_eligibility_matrix=live_eligibility_matrix,
                global_gate=global_gate,
            )
            if loop_recorded.get("status") in {"LANE_AUTONOMY_REJECTED", "LANE_AUTONOMY_PARTIAL"}:
                status = LANE_AUTONOMY_SCHEDULER_REJECTED
                rejection_reason = str(loop_recorded.get("rejection_reason") or "R127 decision recording was not fully accepted")
                return _status_payload(
                    status=status,
                    generated_at=generated_at,
                    once=True,
                    record_tick=record_tick,
                    record_decisions=record_decisions,
                    confirmation_valid=confirmation_valid,
                    loop_status=loop_recorded,
                    tick_recorded=False,
                    tick_id=None,
                    recorded_decision_ids=[],
                    rejection_reason=rejection_reason,
                    ledger_path=_ledger_path(resolved_log_dir),
                )
        recorded_decision_ids = [str(value) for value in loop_recorded.get("recorded_decision_ids") or []]
        tick_record = build_scheduler_tick_record(
            loop_status=loop_recorded,
            mode="record_decision" if record_decisions else "preview",
            recorded_decision_ids=recorded_decision_ids,
            now=generated_at,
        )
        if record_tick:
            append_scheduler_tick_record(tick_record, log_dir=resolved_log_dir)
            tick_recorded = True
            status = LANE_AUTONOMY_SCHEDULER_TICK_RECORDED
        else:
            status = LANE_AUTONOMY_SCHEDULER_PREVIEW

    if tick_record is None:
        tick_record = build_scheduler_tick_record(
            loop_status=loop_preview,
            mode="preview",
            recorded_decision_ids=recorded_decision_ids,
            now=generated_at,
        )
    return _status_payload(
        status=status,
        generated_at=generated_at,
        once=True,
        record_tick=record_tick,
        record_decisions=record_decisions,
        confirmation_valid=confirmation_valid,
        loop_status=loop_preview,
        tick_recorded=tick_recorded,
        tick_id=tick_record.get("tick_id"),
        recorded_decision_ids=recorded_decision_ids,
        rejection_reason=rejection_reason,
        ledger_path=_ledger_path(resolved_log_dir),
    )


def build_scheduler_tick_record(
    *,
    loop_status: Mapping[str, Any],
    mode: str = "preview",
    recorded_decision_ids: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    decisions = [row for row in loop_status.get("decisions") or [] if isinstance(row, Mapping)]
    return {
        "event_type": "LANE_AUTONOMY_SCHEDULER_TICK",
        "tick_id": f"lane_autonomy_scheduler_{uuid4().hex}",
        "recorded_at_utc": generated_at.isoformat(),
        "mode": mode if mode in {"preview", "record_decision"} else "preview",
        "lanes_evaluated_count": int(loop_status.get("lanes_evaluated_count") or 0),
        "candidates_seen_count": int(loop_status.get("candidates_seen_count") or 0),
        "decisions_count": int(loop_status.get("decisions_count") or 0),
        "recorded_decision_ids": list(recorded_decision_ids or loop_status.get("recorded_decision_ids") or []),
        "decision_summary": _decision_summary(decisions),
        "top_blockers": list(loop_status.get("top_blockers") or []),
        "safety": dict(SCHEDULER_SAFETY),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }


def append_scheduler_tick_record(
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


def load_scheduler_tick_records(
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


def summarize_scheduler_ticks(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    mode_counts = Counter(str(record.get("mode") or "UNKNOWN") for record in records)
    decision_counts: Counter[str] = Counter()
    for record in records:
        summary = record.get("decision_summary") if isinstance(record.get("decision_summary"), Mapping) else {}
        decision_counts.update({str(key): int(value) for key, value in (summary.get("decision_counts") or {}).items()})
    return {
        "records_count": len(records),
        "mode_counts": dict(sorted(mode_counts.items())),
        "decision_counts": dict(sorted(decision_counts.items())),
        "last_tick_id": records[-1].get("tick_id") if records else None,
        "safety": dict(SCHEDULER_SAFETY),
    }


def format_lane_autonomy_scheduler_status_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _status_payload(
    *,
    status: str,
    generated_at: datetime,
    once: bool,
    record_tick: bool,
    record_decisions: bool,
    confirmation_valid: bool,
    loop_status: Mapping[str, Any],
    tick_recorded: bool,
    tick_id: object,
    recorded_decision_ids: list[str],
    rejection_reason: str | None,
    ledger_path: Path,
) -> dict[str, Any]:
    decisions = [row for row in loop_status.get("decisions") or [] if isinstance(row, Mapping)]
    payload = {
        "status": status,
        "generated_at": generated_at.isoformat(),
        "once": bool(once),
        "record_tick_requested": bool(record_tick),
        "record_decisions_requested": bool(record_decisions),
        "confirmation_valid": bool(confirmation_valid),
        "selected_lane_keys": list(loop_status.get("selected_lane_keys") or []),
        "lanes_evaluated_count": int(loop_status.get("lanes_evaluated_count") or 0),
        "candidates_seen_count": int(loop_status.get("candidates_seen_count") or 0),
        "decisions_count": int(loop_status.get("decisions_count") or 0),
        "decisions": decisions[:25],
        "recorded_decision_ids": list(recorded_decision_ids),
        "tick_recorded": bool(tick_recorded),
        "tick_id": tick_id,
        "decision_summary": _decision_summary(decisions),
        "top_blockers": list(loop_status.get("top_blockers") or []),
        "scheduler_recommendation": _scheduler_recommendation(status, loop_status),
        "safety": dict(SCHEDULER_SAFETY),
        "ledger_path": str(ledger_path),
        "source_surfaces_used": list(SOURCE_SURFACES_USED),
    }
    if rejection_reason:
        payload["rejection_reason"] = rejection_reason
    return payload


def _recording_blockers(
    loop_status: Mapping[str, Any],
    *,
    config_path: str | Path | None,
    lane_key: str | None,
) -> list[str]:
    blockers: list[str] = []
    if lane_key:
        lane_map = load_lane_controls(config_path).get("lane_map") or {}
        if lane_key not in lane_map:
            blockers.append("selected lane not configured")
    safety = loop_status.get("safety") if isinstance(loop_status.get("safety"), Mapping) else {}
    for key in BLOCKING_SAFETY_KEYS:
        if safety.get(key) is True:
            blockers.append(f"source safety field is unsafe: {key}=true")
    if safety.get("paper_live_separation_intact") is False:
        blockers.append("paper_live_separation_intact false")
    for item in loop_status.get("top_blockers") or []:
        blocker = item.get("blocker") if isinstance(item, Mapping) else None
        if blocker == "route source returns error":
            blockers.append("route source error occurs")
        if blocker == "strategy intent would imply direct executable order payload":
            blockers.append("decision would imply direct order payload")
    return _dedupe(blockers)


def _candidate_source_safety_blockers(candidates: list[Mapping[str, Any] | object] | None) -> list[str]:
    blockers: list[str] = []
    for candidate in candidates or []:
        if not isinstance(candidate, Mapping):
            continue
        safety = candidate.get("safety") if isinstance(candidate.get("safety"), Mapping) else {}
        for key in BLOCKING_SAFETY_KEYS:
            if safety.get(key) is True:
                blockers.append(f"source safety field is unsafe: {key}=true")
        if safety.get("paper_live_separation_intact") is False:
            blockers.append("paper_live_separation_intact false")
    return _dedupe(blockers)


def _decision_summary(decisions: list[Mapping[str, Any]]) -> dict[str, Any]:
    decision_counts = Counter(str(row.get("autonomy_decision") or "UNKNOWN") for row in decisions)
    lane_counts = Counter(str(row.get("lane_key") or "UNKNOWN") for row in decisions)
    return {
        "decision_counts": dict(sorted(decision_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
    }


def _scheduler_recommendation(status: str, loop_status: Mapping[str, Any]) -> str:
    if status == LANE_AUTONOMY_SCHEDULER_REJECTED:
        return "do not record scheduler tick; clear blockers and rerun with exact confirmation"
    if loop_status.get("decisions_count"):
        return "review autonomy decisions; record scheduler tick only after exact confirmation"
    return "keep scheduler in preview until fresh lane candidates appear"


def _ledger_path(log_dir: Path) -> Path:
    return log_dir / LANE_AUTONOMY_SCHEDULER_TICKS_LEDGER


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
