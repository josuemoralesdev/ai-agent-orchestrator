"""R65 first-live exact-chain operator runbook.

This module reports the current first-live chain state and the next operator
command needed to build a fresh R50-R64 chain. It never places orders, signs
payloads, edits env files, or calls Binance.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir, get_signals_path
from src.app.hammer_radar.operator.first_live_adapter_verification import build_first_live_adapter_status
from src.app.hammer_radar.operator.first_live_execution_gate import build_first_live_execution_gate
from src.app.hammer_radar.operator.first_live_ladder_submit_adapter import build_first_live_ladder_submit_status
from src.app.hammer_radar.operator.first_live_protective_adapter import build_first_live_protective_status
from src.app.hammer_radar.operator.first_live_readiness import build_first_live_readiness_status
from src.app.hammer_radar.operator.first_live_test_order_gate import build_first_live_test_order_status
from src.app.hammer_radar.operator.first_microscopic_live_attempt import build_first_microscopic_live_profile
from src.app.hammer_radar.operator.live_approval import load_live_approval_requests
from src.app.hammer_radar.operator.live_arming_checklist import build_live_arming_status
from src.app.hammer_radar.operator.live_arming_runbook import build_live_arming_runbook
from src.app.hammer_radar.operator.live_begins import build_live_begins_status
from src.app.hammer_radar.operator.live_execution_intent import load_live_execution_intents
from src.app.hammer_radar.operator.live_execution_preview import build_live_execution_preview
from src.app.hammer_radar.operator.live_executor_rehearsal import load_live_executor_rehearsals
from src.app.hammer_radar.operator.live_executor_transport import build_live_executor_transport_status

PHASE = "R65"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "FIRST_LIVE_CHAIN_RUNBOOK_ONLY"
CHECKS_FILENAME = "first_live_chain_checks.ndjson"
FAST_RECORD_LIMIT = 100
FAST_SIGNAL_LIMIT = 50
FIRST_LIVE_FRESHNESS_POLICY = "strict_first_live"
FIRST_LIVE_FRESHNESS_CUTOFFS_MINUTES = {
    "4m": 4.5,
    "8m": 8.5,
    "13m": 13.5,
}

ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False


def build_first_live_chain_status(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    detail: str = "fast",
) -> dict[str, Any]:
    if str(detail or "fast").lower() == "full":
        return _evaluate_full(log_dir=log_dir, env=env, persist=False)
    return _evaluate_fast(log_dir=log_dir, env=env, persist=False)


def evaluate_and_record_first_live_chain_check(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    detail: str = "fast",
) -> dict[str, Any]:
    if str(detail or "fast").lower() == "full":
        return _evaluate_full(log_dir=log_dir, env=env, persist=True)
    return _evaluate_fast(log_dir=log_dir, env=env, persist=True)


def list_first_live_chain_checks(
    *,
    limit: int = 20,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    records = load_first_live_chain_checks(limit=limit, status=status, log_dir=get_log_dir(log_dir, use_env=True))
    return {
        "result_status": "ACCEPTED",
        "phase": PHASE,
        "count": len(records),
        "checks": records,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def load_first_live_chain_checks(
    *,
    limit: int = 50,
    status: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_chain_checks_path(get_log_dir(log_dir, use_env=True))
    records: list[dict[str, Any]] = []
    read_limit = limit if limit > 0 else FAST_RECORD_LIMIT
    for record in read_recent_ndjson_records(path, limit=read_limit):
        if status is not None and record.get("status") != status:
            continue
        records.append(_sanitize_record(record))
        if limit > 0 and len(records) >= limit:
            break
    return records


def read_recent_ndjson_records(path: str | Path, *, limit: int = FAST_RECORD_LIMIT, max_bytes: int = 262_144) -> list[dict[str, Any]]:
    resolved = Path(path)
    if limit <= 0 or not resolved.exists():
        return []
    size = resolved.stat().st_size
    offset = max(0, size - max_bytes)
    with resolved.open("rb") as handle:
        handle.seek(offset)
        data = handle.read()
    if offset > 0:
        data = data.split(b"\n", 1)[-1]
    lines = [line.strip() for line in data.splitlines() if line.strip()]
    records: list[dict[str, Any]] = []
    for line in reversed(lines):
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict):
            records.append(record)
        if len(records) >= limit:
            break
    return records


def first_live_chain_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / CHECKS_FILENAME


def append_first_live_chain_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_chain_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def format_first_live_chain_operator_message(payload: dict[str, Any], *, section: str = "status") -> str:
    signal = payload.get("current_signal") or {}
    chain = payload.get("chain_state") or {}
    next_action = payload.get("next_action") or {}
    blockers = payload.get("blockers") or []
    blocker_text = "; ".join(str(item) for item in blockers[:6]) if blockers else "none"
    if section == "next":
        return "\n".join(
            [
                f"R65 first-live next: {payload.get('status')}",
                f"next: {next_action.get('kind')} | {next_action.get('telegram_command') or next_action.get('command') or 'no command'}",
                f"reason: {next_action.get('reason')}",
                "RUNBOOK_ONLY. No order placed. real_order_placed=false.",
            ]
        )
    if section in {"runbook", "sequence"}:
        sequence = payload.get("operator_sequence") or []
        detail = "; ".join(
            f"{item.get('step')}. {item.get('name')} complete={item.get('complete')} cmd={item.get('telegram_command') or item.get('api_hint')}"
            for item in sequence[:8]
        )
        return "\n".join(
            [
                f"R65 first-live sequence: {payload.get('status')}",
                detail or "no sequence available",
                "RUNBOOK_ONLY. No order placed. real_order_placed=false.",
            ]
        )
    return "\n".join(
        [
            f"R65 first-live chain: {payload.get('status')}",
            f"signal: {signal.get('signal_id') or 'none'} fresh={signal.get('fresh')} profile_match={signal.get('matches_first_live_profile')}",
            (
                "chain: "
                f"approval={chain.get('approval_found')} intent={chain.get('execution_intent_found')} "
                f"rehearsal={chain.get('executor_rehearsal_found')} exact={chain.get('exact_chain_resolved')}"
            ),
            f"next: {next_action.get('telegram_command') or next_action.get('command') or next_action.get('kind')}",
            f"blockers: {blocker_text}",
            "RUNBOOK_ONLY. No order placed. real_order_placed=false.",
        ]
    )


def format_first_live_chain_checks_operator_message(payload: dict[str, Any]) -> str:
    checks = payload.get("checks") or []
    detail = "none"
    if checks:
        detail = "; ".join(f"{item.get('created_at')} {item.get('status')}" for item in checks[:5])
    return "\n".join(
        [
            "R65 first-live chain checks",
            "FIRST_LIVE_CHAIN_RUNBOOK_ONLY list. No order placed.",
            f"count: {payload.get('count', 0)}",
            f"checks: {detail}",
            "order_placed=false real_order_placed=false secrets_shown=false",
        ]
    )


def _evaluate_fast(*, log_dir: str | Path | None, env: Mapping[str, str] | None, persist: bool) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    created_at = datetime.now(UTC)
    current_signal = _current_signal_fast(log_dir=resolved_log_dir, now=created_at)
    signal_id = current_signal.get("signal_id")
    chain_state = (
        _chain_state_fast(signal_id=signal_id, log_dir=resolved_log_dir, now=created_at)
        if current_signal.get("fresh") is True and current_signal.get("matches_first_live_profile") is True
        else _empty_chain_state()
    )
    exact_chain = chain_state.get("exact_chain_resolved") is True
    test_order_gate = (
        build_first_live_test_order_status(
            signal_id=signal_id,
            execution_intent_id=chain_state.get("execution_intent_id"),
            executor_rehearsal_id=chain_state.get("executor_rehearsal_id"),
            log_dir=resolved_log_dir,
            env=os.environ if env is None else env,
        )
        if exact_chain
        else _fast_test_order_gate_stub()
    )
    phase_statuses = _phase_statuses_fast(
        chain_state=chain_state,
        test_order_gate=test_order_gate,
        exact_chain=exact_chain,
    )
    next_action = _next_action(current_signal=current_signal, chain_state=chain_state, test_order_gate=test_order_gate)
    status = _status(next_action=next_action, test_order_gate=test_order_gate)
    operator_sequence = _operator_sequence(current_signal=current_signal, chain_state=chain_state, test_order_gate=test_order_gate)
    blockers = _blockers(current_signal=current_signal, chain_state=chain_state, test_order_gate=test_order_gate)
    duration_ms = round((datetime.now(UTC) - started_at).total_seconds() * 1000, 3)
    payload = {
        "status": status,
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "created_at": created_at.isoformat(),
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "current_signal": current_signal,
        "chain_state": chain_state,
        "phase_statuses": phase_statuses,
        "next_action": next_action,
        "operator_sequence": operator_sequence,
        "blockers": blockers,
        "operator_action": _operator_action(next_action),
        "performance": {
            "mode": "fast",
            "duration_ms": duration_ms,
            "heavy_builders_skipped": not exact_chain,
            "ndjson_scan_limited": True,
            "recent_record_limit": FAST_RECORD_LIMIT,
            "recent_signal_limit": FAST_SIGNAL_LIMIT,
        },
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "first_live_chain_checks_path": str(first_live_chain_checks_path(resolved_log_dir)),
    }
    if persist:
        record = _record(payload)
        append_first_live_chain_check(record, log_dir=resolved_log_dir)
        payload["check_id"] = record["check_id"]
    return _sanitize_nested(payload)


def _evaluate_full(*, log_dir: str | Path | None, env: Mapping[str, str] | None, persist: bool) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    created_at = datetime.now(UTC)
    preview = build_live_execution_preview(log_dir=resolved_log_dir, env=source)
    profile_payload = build_first_microscopic_live_profile(log_dir=resolved_log_dir, env=source)
    profile = _profile(profile_payload.get("profile") or {})
    current_signal = _current_signal(preview=preview, profile=profile)
    signal_id = current_signal.get("signal_id")
    chain_state = _chain_state(signal_id=signal_id, log_dir=resolved_log_dir, now=created_at)
    intent_id = chain_state.get("execution_intent_id")
    rehearsal_id = chain_state.get("executor_rehearsal_id")
    test_order_gate = build_first_live_test_order_status(
        signal_id=signal_id,
        execution_intent_id=intent_id,
        executor_rehearsal_id=rehearsal_id,
        log_dir=resolved_log_dir,
        env=source,
    )
    ladder = build_first_live_ladder_submit_status(
        signal_id=signal_id,
        execution_intent_id=intent_id,
        executor_rehearsal_id=rehearsal_id,
        log_dir=resolved_log_dir,
        env=source,
    )
    protective = build_first_live_protective_status(
        signal_id=signal_id,
        execution_intent_id=intent_id,
        executor_rehearsal_id=rehearsal_id,
        log_dir=resolved_log_dir,
        env=source,
    )
    phase_statuses = _phase_statuses(
        profile_status=str(profile_payload.get("status") or "PROFILE_READY"),
        test_order_gate=test_order_gate,
        ladder=ladder,
        protective=protective,
        signal_id=signal_id,
        intent_id=intent_id,
        rehearsal_id=rehearsal_id,
        log_dir=resolved_log_dir,
        env=source,
    )
    next_action = _next_action(
        current_signal=current_signal,
        chain_state=chain_state,
        test_order_gate=test_order_gate,
    )
    status = _status(next_action=next_action, test_order_gate=test_order_gate)
    operator_sequence = _operator_sequence(
        current_signal=current_signal,
        chain_state=chain_state,
        test_order_gate=test_order_gate,
    )
    blockers = _blockers(
        current_signal=current_signal,
        chain_state=chain_state,
        test_order_gate=test_order_gate,
    )
    payload = {
        "status": status,
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "created_at": created_at.isoformat(),
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "current_signal": current_signal,
        "chain_state": chain_state,
        "phase_statuses": phase_statuses,
        "next_action": next_action,
        "operator_sequence": operator_sequence,
        "blockers": blockers,
        "operator_action": _operator_action(next_action),
        "performance": {
            "mode": "full",
            "duration_ms": round((datetime.now(UTC) - started_at).total_seconds() * 1000, 3),
            "heavy_builders_skipped": False,
            "ndjson_scan_limited": False,
        },
        "secrets_shown": SECRETS_SHOWN,
        "audit_event_recorded": persist,
        "first_live_chain_checks_path": str(first_live_chain_checks_path(resolved_log_dir)),
    }
    if persist:
        record = _record(payload)
        append_first_live_chain_check(record, log_dir=resolved_log_dir)
        payload["check_id"] = record["check_id"]
    return _sanitize_nested(payload)


def _current_signal_fast(*, log_dir: Path, now: datetime) -> dict[str, Any]:
    for record in read_recent_ndjson_records(get_signals_path(log_dir), limit=FAST_SIGNAL_LIMIT):
        signal_id = _clean(record.get("signal_id"))
        if not signal_id:
            continue
        timestamp = _clean(record.get("timestamp")) or _timestamp_from_signal_id(signal_id)
        age = _age_minutes_at(timestamp or signal_id, now=now)
        timeframe = record.get("timeframe")
        cutoff = first_live_freshness_cutoff_minutes(timeframe)
        first_live_fresh = is_first_live_signal_fresh(timeframe=timeframe, age_minutes=age)
        raw_fresh = _raw_freshness(record, default=(age is not None and age <= 30.0))
        symbol = str(record.get("symbol") or "").upper() or None
        direction = str(record.get("direction") or "").lower() or None
        return {
            "signal_id": signal_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "fresh": first_live_fresh,
            "raw_fresh": raw_fresh,
            "first_live_fresh": first_live_fresh,
            "freshness_cutoff_minutes": cutoff,
            "freshness_policy": FIRST_LIVE_FRESHNESS_POLICY,
            "age_minutes": age,
            "matches_first_live_profile": bool(symbol == "BTCUSDT" and direction == "long"),
            "source": "signals_ndjson_recent",
        }
    return {
        "signal_id": None,
        "symbol": None,
        "timeframe": None,
        "direction": None,
        "fresh": False,
        "raw_fresh": False,
        "first_live_fresh": False,
        "freshness_cutoff_minutes": None,
        "freshness_policy": FIRST_LIVE_FRESHNESS_POLICY,
        "age_minutes": None,
        "matches_first_live_profile": False,
        "source": "signals_ndjson_recent",
    }


def _chain_state_fast(*, signal_id: str | None, log_dir: Path, now: datetime) -> dict[str, Any]:
    approval_found = _approval_found_fast(signal_id, log_dir=log_dir)
    intent = _latest_intent_fast(signal_id=signal_id, log_dir=log_dir, now=now) if approval_found else None
    intent_id = _clean((intent or {}).get("execution_intent_id"))
    intent_found = intent is not None and intent.get("status") == "INTENT_READY" and _intent_unexpired(intent, now=now)
    rehearsal = (
        _latest_rehearsal_fast(signal_id=signal_id, execution_intent_id=intent_id, log_dir=log_dir)
        if intent_found
        else None
    )
    rehearsal_id = _clean((rehearsal or {}).get("executor_rehearsal_id"))
    rehearsal_found = rehearsal is not None and rehearsal.get("status") == "REHEARSAL_READY"
    exact_chain_resolved = bool(
        signal_id
        and approval_found
        and intent_found
        and rehearsal_found
        and (intent or {}).get("signal_id") == signal_id
        and (rehearsal or {}).get("signal_id") == signal_id
        and (rehearsal or {}).get("execution_intent_id") == intent_id
    )
    blockers = []
    if signal_id and not approval_found:
        blockers.append("exact LIVE APPROVE <signal_id> is missing")
    if approval_found and not intent_found:
        blockers.append("R52 execution intent is missing")
    if intent_found and not rehearsal_found:
        blockers.append("R53 executor rehearsal is missing")
    if signal_id and approval_found and intent_found and rehearsal_found and not exact_chain_resolved:
        blockers.append("approval, intent, and rehearsal ids do not match")
    return {
        "approval_found": approval_found,
        "execution_intent_found": intent_found,
        "executor_rehearsal_found": rehearsal_found,
        "exact_chain_resolved": exact_chain_resolved,
        "execution_intent_id": intent_id,
        "executor_rehearsal_id": rehearsal_id,
        "blockers": blockers,
    }


def _empty_chain_state() -> dict[str, Any]:
    return {
        "approval_found": False,
        "execution_intent_found": False,
        "executor_rehearsal_found": False,
        "exact_chain_resolved": False,
        "execution_intent_id": None,
        "executor_rehearsal_id": None,
        "blockers": [],
    }


def _fast_test_order_gate_stub() -> dict[str, Any]:
    return {
        "status": "EXACT_CHAIN_MISSING",
        "payload_readiness": {
            "entry_payload_ready": False,
            "protective_payloads_ready": False,
        },
        "test_order_status": {"test_order_validated_for_signal": False},
        "live_eligibility": {"eligible_for_manual_env_arming": False},
        "blockers": [],
    }


def _phase_statuses_fast(*, chain_state: dict[str, Any], test_order_gate: dict[str, Any], exact_chain: bool) -> dict[str, Any]:
    return {
        "r50_live_begins": "NOT_EVALUATED_FAST",
        "r51_preview": "NOT_EVALUATED_FAST",
        "r52_intent": "INTENT_READY" if chain_state.get("execution_intent_found") is True else "MISSING",
        "r53_rehearsal": "REHEARSAL_READY" if chain_state.get("executor_rehearsal_found") is True else "MISSING",
        "r54_arming": "NOT_EVALUATED_FAST",
        "r55_gate": "NOT_EVALUATED_FAST",
        "r56_transport": "NOT_EVALUATED_FAST",
        "r57_runbook": "NOT_EVALUATED_FAST",
        "r58_profile": "PROFILE_READY",
        "r59_readiness": "UNKNOWN_FAST",
        "r60_caps": "READY",
        "r61_adapter": "ADAPTERS_PARTIAL",
        "r62_ladder": "LADDER_ADAPTER_PARTIAL" if not exact_chain else "NOT_EVALUATED_FAST",
        "r63_protective": "PROTECTIVE_PLAN_PARTIAL" if not exact_chain else "NOT_EVALUATED_FAST",
        "r64_test_order_gate": test_order_gate.get("status") or "EXACT_CHAIN_MISSING",
    }


def _current_signal(*, preview: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    signal_id = _clean(preview.get("latest_signal_id"))
    raw_fresh = bool(signal_id and preview.get("status") == "PREVIEW_READY" and str(preview.get("freshness_status") or "fresh").lower() in {"fresh", "ok", "valid"})
    age = _age_minutes(signal_id)
    cutoff = first_live_freshness_cutoff_minutes(preview.get("timeframe"))
    first_live_fresh = bool(signal_id and raw_fresh and is_first_live_signal_fresh(timeframe=preview.get("timeframe"), age_minutes=age))
    return {
        "signal_id": signal_id,
        "symbol": preview.get("symbol"),
        "timeframe": preview.get("timeframe"),
        "direction": preview.get("direction"),
        "fresh": first_live_fresh,
        "raw_fresh": raw_fresh,
        "first_live_fresh": first_live_fresh,
        "freshness_cutoff_minutes": cutoff,
        "freshness_policy": FIRST_LIVE_FRESHNESS_POLICY,
        "age_minutes": age,
        "matches_first_live_profile": _matches_first_live_profile(preview=preview, profile=profile),
        "source": "live_execution_preview" if signal_id else None,
    }


def _chain_state(*, signal_id: str | None, log_dir: Path, now: datetime) -> dict[str, Any]:
    approval_found = _approval_found(signal_id, log_dir=log_dir)
    intent = _latest_intent(signal_id=signal_id, log_dir=log_dir, now=now)
    intent_id = _clean((intent or {}).get("execution_intent_id"))
    rehearsal = _latest_rehearsal(signal_id=signal_id, execution_intent_id=intent_id, log_dir=log_dir)
    rehearsal_id = _clean((rehearsal or {}).get("executor_rehearsal_id"))
    intent_found = intent is not None and intent.get("status") == "INTENT_READY" and _intent_unexpired(intent, now=now)
    rehearsal_found = rehearsal is not None and rehearsal.get("status") == "REHEARSAL_READY"
    exact_chain_resolved = bool(
        signal_id
        and approval_found
        and intent_found
        and rehearsal_found
        and (intent or {}).get("signal_id") == signal_id
        and (rehearsal or {}).get("signal_id") == signal_id
        and (rehearsal or {}).get("execution_intent_id") == intent_id
    )
    blockers = []
    if signal_id and not approval_found:
        blockers.append("exact LIVE APPROVE <signal_id> is missing")
    if approval_found and not intent_found:
        blockers.append("R52 execution intent is missing")
    if intent_found and not rehearsal_found:
        blockers.append("R53 executor rehearsal is missing")
    if signal_id and approval_found and intent_found and rehearsal_found and not exact_chain_resolved:
        blockers.append("approval, intent, and rehearsal ids do not match")
    return {
        "approval_found": approval_found,
        "execution_intent_found": intent_found,
        "executor_rehearsal_found": rehearsal_found,
        "exact_chain_resolved": exact_chain_resolved,
        "execution_intent_id": intent_id,
        "executor_rehearsal_id": rehearsal_id,
        "blockers": blockers,
    }


def _phase_statuses(
    *,
    profile_status: str,
    test_order_gate: dict[str, Any],
    ladder: dict[str, Any],
    protective: dict[str, Any],
    signal_id: str | None,
    intent_id: str | None,
    rehearsal_id: str | None,
    log_dir: Path,
    env: Mapping[str, str],
) -> dict[str, Any]:
    live_begins = build_live_begins_status(log_dir=log_dir, env=env)
    preview = build_live_execution_preview(log_dir=log_dir, env=env)
    arming = build_live_arming_status(log_dir=log_dir, env=env)
    gate = build_first_live_execution_gate(signal_id=signal_id, execution_intent_id=intent_id, executor_rehearsal_id=rehearsal_id, log_dir=log_dir, env=env)
    transport = build_live_executor_transport_status(signal_id=signal_id, execution_intent_id=intent_id, executor_rehearsal_id=rehearsal_id, log_dir=log_dir, env=env)
    readiness = build_first_live_readiness_status(log_dir=log_dir, env=env)
    adapter = build_first_live_adapter_status(log_dir=log_dir, env=env)
    runbook = build_live_arming_runbook(log_dir=log_dir, env=env)
    return {
        "r50_live_begins": live_begins.get("status") or "BLOCKED",
        "r51_preview": preview.get("status") or "BLOCKED",
        "r52_intent": gate.get("intent_status") or "MISSING",
        "r53_rehearsal": gate.get("rehearsal_status") or "MISSING",
        "r54_arming": arming.get("status") or "BLOCKED",
        "r55_gate": gate.get("status") or "REJECTED",
        "r56_transport": transport.get("status") or "REJECTED",
        "r57_runbook": runbook.get("status") or runbook.get("runbook_status") or "BLOCKED",
        "r58_profile": profile_status,
        "r59_readiness": readiness.get("status") or "BLOCKED",
        "r60_caps": "READY" if _caps_ready(readiness) else "BLOCKED",
        "r61_adapter": adapter.get("status") or "ADAPTERS_PARTIAL",
        "r62_ladder": ladder.get("status") or "LADDER_ADAPTER_PARTIAL",
        "r63_protective": protective.get("status") or "PROTECTIVE_PLAN_PARTIAL",
        "r64_test_order_gate": test_order_gate.get("status") or "EXACT_CHAIN_MISSING",
    }


def _next_action(*, current_signal: dict[str, Any], chain_state: dict[str, Any], test_order_gate: dict[str, Any]) -> dict[str, Any]:
    signal_id = current_signal.get("signal_id")
    intent_id = chain_state.get("execution_intent_id")
    rehearsal_id = chain_state.get("executor_rehearsal_id")
    if current_signal.get("fresh") is not True or current_signal.get("matches_first_live_profile") is not True:
        return _action("wait_for_signal", "FIRST LIVE CHAIN", "GET /live/first-chain/status", "fresh BTCUSDT first-live signal is not available")
    if chain_state.get("approval_found") is not True:
        return _action("approve_signal", f"LIVE APPROVE {signal_id}", f"POST /live-approval/evaluate text='LIVE APPROVE {signal_id}'", "exact human approval is required")
    if chain_state.get("execution_intent_found") is not True:
        return _action("create_intent", f"LIVE INTENT {signal_id}", "POST /live/execution-intent", "R52 execution intent is required")
    if chain_state.get("executor_rehearsal_found") is not True:
        return _action("run_rehearsal", f"LIVE REHEARSAL {intent_id}" if intent_id else None, "POST /live/executor-rehearsal", "R53 executor rehearsal is required")
    readiness = test_order_gate.get("payload_readiness") if isinstance(test_order_gate.get("payload_readiness"), dict) else {}
    if readiness.get("protective_payloads_ready") is not True or readiness.get("entry_payload_ready") is not True:
        return _action("check_payloads", f"FIRST LIVE PAYLOAD READINESS {rehearsal_id}" if rehearsal_id else "FIRST LIVE PAYLOAD READINESS", "GET /live/first-test-order/status", "exact entry/protective payload readiness is incomplete")
    test_order = test_order_gate.get("test_order_status") if isinstance(test_order_gate.get("test_order_status"), dict) else {}
    if test_order.get("test_order_validated_for_signal") is not True:
        return _action("validate_test_order", f"FIRST LIVE TEST ORDER {rehearsal_id}" if rehearsal_id else "FIRST LIVE TEST ORDER", "POST /live/first-test-order/check", "successful test-order validation is required before live")
    eligibility = test_order_gate.get("live_eligibility") if isinstance(test_order_gate.get("live_eligibility"), dict) else {}
    if eligibility.get("eligible_for_manual_env_arming") is True:
        return _action("manual_env_review", "LIVE ARMING", "GET /live/arming/status", "manual env arming, funds, and final review remain required")
    return _action("final_review", "FIRST LIVE GATE", "POST /live/first-execution-gate/check", "final operator review remains required")


def _status(*, next_action: dict[str, Any], test_order_gate: dict[str, Any]) -> str:
    kind = next_action.get("kind")
    if kind == "wait_for_signal":
        return "WAITING_FOR_FRESH_SIGNAL"
    if kind == "approve_signal":
        return "WAITING_FOR_APPROVAL"
    if kind == "create_intent":
        return "WAITING_FOR_INTENT"
    if kind == "run_rehearsal":
        return "WAITING_FOR_REHEARSAL"
    if kind == "check_payloads":
        return "WAITING_FOR_PAYLOAD_READY"
    if kind == "validate_test_order":
        return "WAITING_FOR_TEST_ORDER"
    if kind == "manual_env_review":
        return "READY_FOR_MANUAL_ENV_ARMING"
    if kind == "final_review" and test_order_gate.get("status") in {"TEST_ORDER_VALIDATED", "READY_FOR_MANUAL_ENV_ARMING"}:
        return "READY_FOR_FINAL_REVIEW"
    return "BLOCKED"


def _operator_sequence(*, current_signal: dict[str, Any], chain_state: dict[str, Any], test_order_gate: dict[str, Any]) -> list[dict[str, Any]]:
    signal_id = current_signal.get("signal_id")
    intent_id = chain_state.get("execution_intent_id")
    rehearsal_id = chain_state.get("executor_rehearsal_id")
    payload_readiness = test_order_gate.get("payload_readiness") if isinstance(test_order_gate.get("payload_readiness"), dict) else {}
    test_order = test_order_gate.get("test_order_status") if isinstance(test_order_gate.get("test_order_status"), dict) else {}
    return [
        _step(1, "Find fresh first-live signal", "FIRST LIVE CHAIN", "GET /live/first-chain/status", current_signal.get("fresh") is True and current_signal.get("matches_first_live_profile") is True),
        _step(2, "Approve exact signal", f"LIVE APPROVE {signal_id}" if signal_id else None, "POST /live-approval/evaluate", chain_state.get("approval_found") is True),
        _step(3, "Create execution intent", f"LIVE INTENT {signal_id}" if signal_id else None, "POST /live/execution-intent", chain_state.get("execution_intent_found") is True),
        _step(4, "Run executor rehearsal", f"LIVE REHEARSAL {intent_id}" if intent_id else None, "POST /live/executor-rehearsal", chain_state.get("executor_rehearsal_found") is True),
        _step(5, "Check exact payload readiness", f"FIRST LIVE PAYLOAD READINESS {rehearsal_id}" if rehearsal_id else "FIRST LIVE PAYLOAD READINESS", "GET /live/first-test-order/status", payload_readiness.get("protective_payloads_ready") is True and payload_readiness.get("entry_payload_ready") is True),
        _step(6, "Validate exact test-order", f"FIRST LIVE TEST ORDER {rehearsal_id}" if rehearsal_id else "FIRST LIVE TEST ORDER", "POST /live/first-test-order/check", test_order.get("test_order_validated_for_signal") is True),
        _step(7, "Manual env and funds review", "LIVE ARMING", "GET /live/arming/status", False),
        _step(8, "Final protected review", "FIRST LIVE GATE", "POST /live/first-execution-gate/check", False),
    ]


def _blockers(*, current_signal: dict[str, Any], chain_state: dict[str, Any], test_order_gate: dict[str, Any]) -> list[str]:
    blockers = []
    if current_signal.get("fresh") is not True:
        blockers.append("fresh first-live signal is not available")
    if current_signal.get("matches_first_live_profile") is not True:
        blockers.append("current signal does not match first-live BTCUSDT profile")
    blockers.extend(chain_state.get("blockers") or [])
    blockers.extend(test_order_gate.get("blockers") or [])
    return list(dict.fromkeys(str(item) for item in blockers if item))


def _record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "check_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "first_live_chain_runbook_check",
        "created_at": payload.get("created_at"),
        "status": payload.get("status"),
        "current_signal": payload.get("current_signal"),
        "chain_state": payload.get("chain_state"),
        "phase_statuses": payload.get("phase_statuses"),
        "next_action": payload.get("next_action"),
        "operator_sequence": payload.get("operator_sequence"),
        "blockers": payload.get("blockers"),
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize_record(record: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "check_id",
        "phase",
        "event_type",
        "created_at",
        "status",
        "current_signal",
        "chain_state",
        "phase_statuses",
        "next_action",
        "operator_sequence",
        "blockers",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "network_allowed",
        "secrets_shown",
    }
    sanitized = {key: record.get(key) for key in allowed if key in record}
    sanitized["order_placed"] = False
    sanitized["real_order_placed"] = False
    sanitized["execution_attempted"] = False
    sanitized["network_allowed"] = False
    sanitized["secrets_shown"] = False
    return _sanitize_nested(sanitized)


def _approval_found(signal_id: str | None, *, log_dir: Path) -> bool:
    if not signal_id:
        return False
    for record in load_live_approval_requests(limit=0, signal_id=signal_id, log_dir=log_dir):
        if (
            record.get("normalized_action") == "live_approve_exact"
            and record.get("parse_status") == "ACCEPTED"
            and record.get("signal_id") == signal_id
        ):
            return True
    return False


def _approval_found_fast(signal_id: str | None, *, log_dir: Path) -> bool:
    if not signal_id:
        return False
    from src.app.hammer_radar.operator.live_approval import live_approval_requests_path

    for record in read_recent_ndjson_records(live_approval_requests_path(log_dir), limit=FAST_RECORD_LIMIT):
        if (
            record.get("normalized_action") == "live_approve_exact"
            and record.get("parse_status") == "ACCEPTED"
            and record.get("signal_id") == signal_id
        ):
            return True
    return False


def _latest_intent(*, signal_id: str | None, log_dir: Path, now: datetime) -> dict[str, Any] | None:
    if not signal_id:
        return None
    records = load_live_execution_intents(limit=0, signal_id=signal_id, log_dir=log_dir)
    for record in records:
        if _intent_unexpired(record, now=now):
            return record
    return records[0] if records else None


def _latest_intent_fast(*, signal_id: str | None, log_dir: Path, now: datetime) -> dict[str, Any] | None:
    if not signal_id:
        return None
    from src.app.hammer_radar.operator.live_execution_intent import live_execution_intents_path

    fallback = None
    for record in read_recent_ndjson_records(live_execution_intents_path(log_dir), limit=FAST_RECORD_LIMIT):
        if record.get("signal_id") != signal_id:
            continue
        sanitized = _sanitize_intent_fast(record)
        fallback = fallback or sanitized
        if _intent_unexpired(sanitized, now=now):
            return sanitized
    return fallback


def _latest_rehearsal(*, signal_id: str | None, execution_intent_id: str | None, log_dir: Path) -> dict[str, Any] | None:
    if not signal_id and not execution_intent_id:
        return None
    records = load_live_executor_rehearsals(limit=0, signal_id=signal_id, execution_intent_id=execution_intent_id, log_dir=log_dir)
    for record in records:
        if record.get("status") == "REHEARSAL_READY" and record.get("execution_mode") == "REHEARSAL_ONLY":
            return record
    return records[0] if records else None


def _latest_rehearsal_fast(*, signal_id: str | None, execution_intent_id: str | None, log_dir: Path) -> dict[str, Any] | None:
    if not signal_id and not execution_intent_id:
        return None
    from src.app.hammer_radar.operator.live_executor_rehearsal import live_executor_rehearsals_path

    fallback = None
    for record in read_recent_ndjson_records(live_executor_rehearsals_path(log_dir), limit=FAST_RECORD_LIMIT):
        if signal_id is not None and record.get("signal_id") != signal_id:
            continue
        if execution_intent_id is not None and record.get("execution_intent_id") != execution_intent_id:
            continue
        sanitized = _sanitize_rehearsal_fast(record)
        fallback = fallback or sanitized
        if sanitized.get("status") == "REHEARSAL_READY" and sanitized.get("execution_mode") == "REHEARSAL_ONLY":
            return sanitized
    return fallback


def _sanitize_intent_fast(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "execution_intent_id": _clean(record.get("execution_intent_id")),
        "status": record.get("status"),
        "execution_mode": record.get("execution_mode"),
        "signal_id": record.get("signal_id"),
        "preview_hash": record.get("preview_hash"),
        "created_at": record.get("created_at"),
        "expires_at": record.get("expires_at"),
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }


def _sanitize_rehearsal_fast(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "executor_rehearsal_id": _clean(record.get("executor_rehearsal_id")),
        "execution_intent_id": _clean(record.get("execution_intent_id")),
        "status": record.get("status"),
        "execution_mode": record.get("execution_mode"),
        "signal_id": record.get("signal_id"),
        "preview_hash": record.get("preview_hash"),
        "created_at": record.get("created_at"),
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "network_allowed": False,
        "secrets_shown": False,
    }


def _intent_unexpired(record: dict[str, Any] | None, *, now: datetime) -> bool:
    if not record or record.get("status") != "INTENT_READY":
        return False
    expires_at = _parse_datetime(record.get("expires_at"))
    return expires_at is not None and expires_at > now


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _matches_first_live_profile(*, preview: dict[str, Any], profile: dict[str, Any]) -> bool:
    return (
        preview.get("symbol") == "BTCUSDT"
        and str(preview.get("direction") or "").lower() == "long"
        and profile.get("symbol") == "BTCUSDT"
        and profile.get("margin_usdt") == 44.0
        and profile.get("leverage") == 10
        and profile.get("notional_usdt") == 440.0
        and profile.get("max_notional_usdt") == 444.0
        and profile.get("margin_mode") == "ISOLATED"
        and profile.get("entry_mode") == "LADDER"
        and profile.get("protective_orders_required") is True
        and profile.get("one_attempt_only") is True
    )


def is_first_live_signal_fresh(*, timeframe: object, age_minutes: float | None) -> bool:
    cutoff = first_live_freshness_cutoff_minutes(timeframe)
    return bool(cutoff is not None and age_minutes is not None and age_minutes <= cutoff)


def first_live_freshness_cutoff_minutes(timeframe: object) -> float | None:
    key = str(timeframe or "").strip().lower()
    return FIRST_LIVE_FRESHNESS_CUTOFFS_MINUTES.get(key)


def _raw_freshness(record: Mapping[str, Any], *, default: bool) -> bool:
    if isinstance(record.get("fresh"), bool):
        return bool(record["fresh"])
    freshness = record.get("freshness_status")
    if freshness is not None:
        return str(freshness).strip().lower() in {"fresh", "ok", "valid"}
    return bool(default)


def _profile(source: Mapping[str, Any]) -> dict[str, Any]:
    margin = _float(source.get("margin_usdt"), 44.0)
    leverage = int(_float(source.get("leverage"), 10.0))
    max_notional = _float(source.get("max_notional_usdt"), 444.0)
    return {
        "symbol": str(source.get("symbol") or "BTCUSDT").upper(),
        "margin_usdt": margin,
        "leverage": leverage,
        "notional_usdt": margin * leverage,
        "max_notional_usdt": max_notional,
        "margin_mode": str(source.get("margin_mode") or "ISOLATED").upper(),
        "entry_mode": str(source.get("entry_mode") or "LADDER").upper(),
        "protective_orders_required": bool(source.get("protective_orders_required", True)),
        "one_attempt_only": bool(source.get("one_attempt_only", True)),
    }


def _caps_ready(readiness: dict[str, Any]) -> bool:
    caps = readiness.get("cap_status") if isinstance(readiness.get("cap_status"), dict) else {}
    return caps.get("first_live_cap_semantics_ok") is True or caps.get("caps_ok") is True


def _operator_action(next_action: dict[str, Any]) -> str:
    kind = next_action.get("kind")
    if kind == "wait_for_signal":
        return "wait for fresh signal"
    if kind == "approve_signal":
        return "approve exact signal"
    if kind == "create_intent":
        return "create intent"
    if kind == "run_rehearsal":
        return "run rehearsal"
    if kind == "check_payloads":
        return "check protective payload readiness"
    if kind == "validate_test_order":
        return "validate test-order"
    return "manual review / keep blocked"


def _action(kind: str, telegram_command: str | None, api_hint: str | None, reason: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "command": telegram_command,
        "telegram_command": telegram_command,
        "api_command": api_hint,
        "reason": reason,
    }


def _step(step: int, name: str, telegram_command: str | None, api_hint: str | None, complete: bool) -> dict[str, Any]:
    return {
        "step": step,
        "name": name,
        "telegram_command": telegram_command,
        "api_hint": api_hint,
        "required": True,
        "complete": bool(complete),
    }


def _age_minutes(signal_id: str | None) -> float | None:
    if not signal_id:
        return None
    parts = str(signal_id).split("|")
    if len(parts) != 4:
        return None
    parsed = _parse_datetime(parts[3])
    if parsed is None:
        return None
    age = datetime.now(UTC) - parsed
    return max(0.0, round(age.total_seconds() / 60.0, 2))


def _age_minutes_at(timestamp_or_signal_id: str | None, *, now: datetime) -> float | None:
    if not timestamp_or_signal_id:
        return None
    timestamp = _timestamp_from_signal_id(timestamp_or_signal_id) or timestamp_or_signal_id
    parsed = _parse_datetime(timestamp)
    if parsed is None:
        return None
    age = now - parsed
    return max(0.0, round(age.total_seconds() / 60.0, 2))


def _timestamp_from_signal_id(signal_id: str | None) -> str | None:
    if not signal_id:
        return None
    parts = str(signal_id).split("|")
    if len(parts) != 4:
        return None
    return parts[3]


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _sanitize_nested(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered != "secrets_shown" and any(
                token in lowered for token in ("secret", "token", "api_key", "apikey", "signature", "auth", "query_string")
            ):
                continue
            sanitized[key] = _sanitize_nested(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_nested(item) for item in value]
    return value
