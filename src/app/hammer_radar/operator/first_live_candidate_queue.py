"""R71 multi-horizon first-live candidate queue.

This module is queue and selection state only. It reads local signal logs,
preserves recent candidates across horizon buckets, and never places orders or
calls exchange networks.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir, get_signals_path
from src.app.hammer_radar.operator.first_live_higher_timeframe_policy import (
    evaluate_higher_timeframe_live_policy,
    get_higher_timeframe_live_policy,
)
from src.app.hammer_radar.operator.first_live_timeframe_policy import (
    evaluate_first_live_timeframe_candidate,
    get_first_live_timeframe_policy,
)
from src.app.hammer_radar.operator.strategy_performance import (
    DEFAULT_ALLOWED_TINY_LIVE_TIMEFRAMES,
    DEFAULT_BLOCKED_TIMEFRAMES,
    DEFAULT_CONTEXT_ONLY_TIMEFRAMES,
    DEFAULT_PAPER_ONLY_TIMEFRAMES,
    load_strategy_audit_config,
)

PHASE = "R71"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "MULTI_HORIZON_CANDIDATE_QUEUE_ONLY"
SELECTED_SIGNAL_FILENAME = "first_live_selected_signal.json"
FIRST_LIVE_FRESHNESS_POLICY = "strict_first_live"
FIRST_LIVE_FRESHNESS_CUTOFFS_MINUTES = {
    "4m": 4.5,
    "8m": 8.5,
    "13m": 13.5,
}

ORDER_PLACED = False
REAL_ORDER_PLACED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

QUEUE_RECORD_LIMIT = 400
BUCKET_LIMIT = 5

HORIZON_BUCKETS = {
    "micro": ("4m", "8m", "13m"),
    "active": ("22m", "44m", "55m", "88m"),
    "swing": ("222m", "444m", "888m", "4H"),
    "macro": ("13H", "13D"),
}
QUEUE_FRESHNESS_CUTOFFS_MINUTES = {
    "4m": 4.5,
    "8m": 8.5,
    "13m": 13.5,
    "22m": 22.5,
    "44m": 44.5,
    "55m": 55.5,
    "88m": 88.5,
    "222m": 222.5,
    "444m": 444.5,
    "888m": 888.5,
    "4H": 240.5,
    "13H": 780.5,
    "13D": 18720.5,
}


def build_first_live_candidate_queue(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    per_bucket_limit: int = BUCKET_LIMIT,
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    created_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    candidates = _queue_candidates(resolved_log_dir, now=created_at, env=env)
    buckets = _bucket_candidates(candidates, per_bucket_limit=per_bucket_limit)
    selected_state = load_selected_signal(log_dir=resolved_log_dir)
    selection_status = _selection_status(selected_state=selected_state, candidates=candidates, log_dir=resolved_log_dir, env=env, now=created_at)
    selected_signal_id = selection_status.get("selected_signal_id") if selection_status.get("valid") is True else None
    if selection_status.get("status") == "EXPIRED":
        clear_selected_signal(log_dir=resolved_log_dir, source="system", reason="selected signal expired")
        selected_signal_id = None
    policy = _policy(env=env)
    higher_timeframe_policy = get_higher_timeframe_live_policy(env=env)
    unified_timeframe_policy = get_first_live_timeframe_policy(env=env)
    recommended_next = _recommended_next(candidates=candidates, selection_status=selection_status)
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "created_at": created_at.isoformat(),
            "order_placed": ORDER_PLACED,
            "real_order_placed": REAL_ORDER_PLACED,
            "network_allowed": NETWORK_ALLOWED,
            "selected_signal_id": selected_signal_id,
            "selection_status": selection_status,
            "buckets": buckets,
            "recommended_next": recommended_next,
            "policy": policy,
            "unified_timeframe_policy": unified_timeframe_policy,
            "higher_timeframe_policy": higher_timeframe_policy,
            "performance": {
                "mode": "fast",
                "duration_ms": round((datetime.now(UTC) - started_at).total_seconds() * 1000, 3),
                "ndjson_scan_limited": True,
                "recent_signal_limit": QUEUE_RECORD_LIMIT,
            },
            "secrets_shown": SECRETS_SHOWN,
        }
    )


def select_first_live_candidate(
    *,
    signal_id: str | None,
    log_dir: str | Path | None = None,
    source: str = "api",
    reason: str = "",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    cleaned = str(signal_id or "").strip()
    if not cleaned:
        return _selection_result("REJECTED", "missing signal_id", None, env=env, log_dir=resolved_log_dir)
    queue = build_first_live_candidate_queue(log_dir=resolved_log_dir, env=env)
    candidate = find_candidate_in_queue(queue, cleaned)
    if candidate is None:
        return _selection_result("REJECTED", "unknown signal_id", cleaned, queue=queue, env=env, log_dir=resolved_log_dir)
    if candidate.get("queue_fresh") is not True:
        return _selection_result("REJECTED", "candidate is stale for queue selection", cleaned, queue=queue, env=env, log_dir=resolved_log_dir)
    state = {
        "selected_signal_id": cleaned,
        "selected_at": datetime.now(UTC).isoformat(),
        "source": source,
        "reason": reason,
        "order_placed": False,
        "real_order_placed": False,
        "secrets_shown": False,
    }
    _write_selected_signal(state, log_dir=resolved_log_dir)
    return _selection_result("ACCEPTED", "candidate selected", cleaned, queue=build_first_live_candidate_queue(log_dir=resolved_log_dir, env=env), env=env, log_dir=resolved_log_dir)


def clear_selected_signal(
    *,
    log_dir: str | Path | None = None,
    source: str = "api",
    reason: str = "",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = selected_signal_path(resolved_log_dir)
    previous = load_selected_signal(log_dir=resolved_log_dir)
    if path.exists():
        path.unlink()
    return _sanitize(
        {
            "status": "CLEARED",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "cleared_at": datetime.now(UTC).isoformat(),
            "source": source,
            "reason": reason,
            "previous_selection": previous,
            "order_placed": False,
            "real_order_placed": False,
            "network_allowed": False,
            "secrets_shown": False,
            "policy": _policy(env=env),
            "unified_timeframe_policy": get_first_live_timeframe_policy(env=env),
            "higher_timeframe_policy": get_higher_timeframe_live_policy(env=env),
        }
    )


def load_selected_signal(*, log_dir: str | Path | None = None) -> dict[str, Any] | None:
    path = selected_signal_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _sanitize(payload) if isinstance(payload, dict) else None


def selected_signal_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / SELECTED_SIGNAL_FILENAME


def read_recent_ndjson_records(path: str | Path, *, limit: int = QUEUE_RECORD_LIMIT, max_bytes: int = 262_144) -> list[dict[str, Any]]:
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


def find_candidate_in_queue(queue: Mapping[str, Any], signal_id: str | None) -> dict[str, Any] | None:
    if not signal_id:
        return None
    buckets = queue.get("buckets") if isinstance(queue.get("buckets"), dict) else {}
    for items in buckets.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("signal_id") == signal_id:
                return item
    return None


def format_first_live_candidates_operator_message(payload: Mapping[str, Any]) -> str:
    buckets = payload.get("buckets") if isinstance(payload.get("buckets"), dict) else {}
    lines = ["R71 first-live candidates: OK"]
    for bucket in ("micro", "active", "swing", "macro"):
        items = buckets.get(bucket) if isinstance(buckets.get(bucket), list) else []
        top = items[0] if items else {}
        top_text = (
            f"{top.get('signal_id')} {top.get('timeframe')} {top.get('direction')} "
            f"live_allowed={top.get('live_candidate_allowed')}"
            if top
            else "none"
        )
        lines.append(f"{bucket}: count={len(items)} top={top_text}")
    selected = payload.get("selected_signal_id") or "none"
    lines.append(f"selected: {selected}")
    lines.append("CANDIDATE_QUEUE_ONLY. No order placed. real_order_placed=false.")
    return "\n".join(lines)


def format_first_live_selected_operator_message(payload: Mapping[str, Any]) -> str:
    selection = payload.get("selection_status") if isinstance(payload.get("selection_status"), dict) else {}
    candidate = selection.get("candidate") if isinstance(selection.get("candidate"), dict) else {}
    live_note = "not live-approvable" if candidate.get("live_candidate_allowed") is not True else "live-approvable"
    return "\n".join(
        [
            f"R71 first-live selected: {selection.get('status', 'NONE')}",
            f"signal: {selection.get('selected_signal_id') or 'none'}",
            f"timeframe: {candidate.get('timeframe') or 'none'} {live_note}={candidate.get('live_candidate_allowed')}",
            f"policy: {candidate.get('policy_status') or selection.get('reason') or 'none'}",
            "CANDIDATE_QUEUE_ONLY. No order placed. real_order_placed=false.",
        ]
    )


def _queue_candidates(log_dir: Path, *, now: datetime, env: Mapping[str, str] | None) -> list[dict[str, Any]]:
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for record in read_recent_ndjson_records(get_signals_path(log_dir), limit=QUEUE_RECORD_LIMIT, max_bytes=1_048_576):
        signal_id = _clean(record.get("signal_id"))
        if not signal_id or signal_id in seen:
            continue
        seen.add(signal_id)
        item = _candidate_item(record, now=now, env=env)
        if item is not None and item["queue_fresh"]:
            candidates.append(item)
    candidates.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    return candidates


def _candidate_item(record: Mapping[str, Any], *, now: datetime, env: Mapping[str, str] | None) -> dict[str, Any] | None:
    signal_id = _clean(record.get("signal_id"))
    timeframe = _normalize_timeframe(record.get("timeframe"))
    horizon = _horizon(timeframe)
    if not signal_id or not timeframe or not horizon:
        return None
    timestamp = _clean(record.get("timestamp")) or _timestamp_from_signal_id(signal_id)
    age = _age_minutes(timestamp, now=now)
    cutoff = QUEUE_FRESHNESS_CUTOFFS_MINUTES.get(timeframe)
    queue_fresh = bool(age is not None and cutoff is not None and age <= cutoff)
    raw_fresh = _raw_freshness(record, default=queue_fresh)
    symbol = str(record.get("symbol") or "").upper() or None
    direction = str(record.get("direction") or "").lower() or None
    policy_status, blockers = _policy_status(timeframe=timeframe, symbol=symbol, direction=direction, env=env)
    first_live_match = bool(symbol == "BTCUSDT" and direction == "long")
    unified_eval = evaluate_first_live_timeframe_candidate(
        {
            "signal_id": signal_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "age_minutes": age,
            "queue_fresh": queue_fresh,
        },
        env=env,
        selected=False,
        now=now,
    )
    policy_status = str(unified_eval.get("policy_status") or policy_status)
    live_allowed = unified_eval.get("live_candidate_allowed") is True
    blockers.extend(unified_eval.get("blockers") or [])
    if not first_live_match:
        blockers.append("candidate does not match BTCUSDT long first-live profile")
    if not queue_fresh:
        blockers.append("candidate is outside queue freshness window")
    return {
        "signal_id": signal_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "horizon": horizon,
        "timestamp": timestamp,
        "created_at": _clean(record.get("created_at")) or timestamp,
        "age_minutes": age,
        "queue_fresh": queue_fresh,
        "queue_freshness_cutoff_minutes": cutoff,
        "raw_fresh": raw_fresh,
        "first_live_profile_match": first_live_match,
        "matches_first_live_profile": first_live_match,
        "first_live_fresh": is_first_live_signal_fresh(timeframe=timeframe, age_minutes=age),
        "freshness_policy": FIRST_LIVE_FRESHNESS_POLICY,
        "current_policy_status": policy_status,
        "policy_status": policy_status,
        "unified_policy_status": policy_status,
        "unified_policy_category": unified_eval.get("category"),
        "unified_policy_profile_name": unified_eval.get("profile_name"),
        "unified_policy_evaluation": unified_eval,
        "profile_name": unified_eval.get("profile_name"),
        "requires_selection": unified_eval.get("requires_selection") is True,
        "live_candidate_allowed": live_allowed,
        "entry": _first_float(record, ("entry", "fib_50", "fib_618")),
        "stop": _first_float(record, ("stop", "invalidation", "hammer_low")),
        "take_profit": _first_float(record, ("take_profit", "target", "fib_786", "hammer_high")),
        "score": _first_float(record, ("score", "hammer_strength")),
        "tier": record.get("tier"),
        "blockers": list(dict.fromkeys(blockers)),
    }


def _bucket_candidates(candidates: list[dict[str, Any]], *, per_bucket_limit: int) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in HORIZON_BUCKETS}
    for item in candidates:
        bucket = item.get("horizon")
        if bucket in buckets and len(buckets[bucket]) < per_bucket_limit:
            buckets[bucket].append(item)
    return buckets


def _selection_status(
    *,
    selected_state: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    log_dir: Path,
    env: Mapping[str, str] | None,
    now: datetime,
) -> dict[str, Any]:
    if not selected_state or not selected_state.get("selected_signal_id"):
        return {"status": "NONE", "valid": False, "selected_signal_id": None, "candidate": None, "reason": "no selected signal"}
    selected_signal_id = str(selected_state.get("selected_signal_id"))
    candidate = next((item for item in candidates if item.get("signal_id") == selected_signal_id), None)
    if candidate is None:
        return {
            "status": "EXPIRED",
            "valid": False,
            "selected_signal_id": selected_signal_id,
            "candidate": None,
            "reason": "selected signal is no longer queue-fresh",
            "selection": selected_state,
            "selected_signal_path": str(selected_signal_path(log_dir)),
        }
    candidate = _candidate_with_selected_policy(candidate, env=env, now=now)
    if candidate.get("live_candidate_allowed") is not True:
        status = "SELECTED_BUT_NOT_LIVE_ELIGIBLE"
    else:
        status = "SELECTED_LIVE_ELIGIBLE"
    return {
        "status": status,
        "valid": True,
        "selected_signal_id": selected_signal_id,
        "candidate": candidate,
        "reason": "selected candidate preserved",
        "selection": selected_state,
        "selected_signal_path": str(selected_signal_path(log_dir)),
    }


def _candidate_with_selected_policy(candidate: dict[str, Any], *, env: Mapping[str, str] | None, now: datetime) -> dict[str, Any]:
    selected = {**candidate, "selected": True, "exact_selection": True}
    unified_eval = evaluate_first_live_timeframe_candidate(selected, env=env, selected=True, now=now)
    selected["unified_policy_evaluation"] = unified_eval
    selected["unified_policy_status"] = unified_eval.get("policy_status")
    selected["unified_policy_category"] = unified_eval.get("category")
    selected["unified_policy_profile_name"] = unified_eval.get("profile_name")
    selected["profile_name"] = unified_eval.get("profile_name")
    selected["requires_selection"] = unified_eval.get("requires_selection") is True
    if unified_eval.get("live_candidate_allowed") is True:
        selected["live_candidate_allowed"] = True
        selected["policy_status"] = str(unified_eval.get("policy_status"))
        selected["current_policy_status"] = selected["policy_status"]
        selected["first_live_profile_match"] = True
        selected["matches_first_live_profile"] = True
        selected["profile_match_reason"] = (
            "higher_timeframe_policy" if unified_eval.get("category") == "higher" else str(unified_eval.get("profile_name") or "unified_timeframe_policy")
        )
        selected["unified_timeframe_profile"] = True
        selected["blockers"] = []
        if unified_eval.get("category") == "higher":
            selected["higher_timeframe_profile"] = True
            selected["higher_timeframe_policy"] = evaluate_higher_timeframe_live_policy(selected, env=env, now=now)
        return selected
    if unified_eval.get("category") != "higher":
        selected["live_candidate_allowed"] = False
        selected["policy_status"] = str(unified_eval.get("policy_status") or "SELECTED_BUT_NOT_LIVE_ELIGIBLE")
        selected["current_policy_status"] = selected["policy_status"]
        selected["blockers"] = list(dict.fromkeys([*(selected.get("blockers") or []), *(unified_eval.get("blockers") or [])]))
        return selected
    higher_policy = evaluate_higher_timeframe_live_policy(selected, env=env, now=now)
    selected["higher_timeframe_policy"] = higher_policy
    selected["higher_timeframe_profile"] = higher_policy.get("candidate_allowed") is True
    if higher_policy.get("candidate_allowed") is True:
        selected["live_candidate_allowed"] = True
        selected["policy_status"] = "SELECTED_HIGHER_TIMEFRAME_ALLOWED"
        selected["current_policy_status"] = "SELECTED_HIGHER_TIMEFRAME_ALLOWED"
        selected["first_live_profile_match"] = True
        selected["matches_first_live_profile"] = True
        selected["profile_match_reason"] = "higher_timeframe_policy"
        selected["blockers"] = []
    else:
        selected["live_candidate_allowed"] = False
        selected["policy_status"] = str(higher_policy.get("candidate_policy_status") or "SELECTED_BUT_NOT_LIVE_ELIGIBLE")
        selected["current_policy_status"] = selected["policy_status"]
        selected["blockers"] = list(dict.fromkeys([*(selected.get("blockers") or []), *(unified_eval.get("blockers") or []), *(higher_policy.get("blockers") or [])]))
        if higher_policy.get("enable_hint"):
            selected["enable_hint"] = higher_policy.get("enable_hint")
    return selected


def _recommended_next(*, candidates: list[dict[str, Any]], selection_status: Mapping[str, Any]) -> dict[str, Any]:
    selected_candidate = selection_status.get("candidate") if isinstance(selection_status.get("candidate"), dict) else None
    if selected_candidate and selected_candidate.get("live_candidate_allowed") is True:
        signal_id = selected_candidate.get("signal_id")
        return {
            "kind": "approve_signal",
            "signal_id": signal_id,
            "telegram_command": f"LIVE APPROVE {signal_id}",
            "reason": "selected candidate is live-approvable and exact human approval is required",
        }
    if selected_candidate:
        return {
            "kind": "blocked",
            "signal_id": selected_candidate.get("signal_id"),
            "telegram_command": "FIRST LIVE SELECTED",
            "reason": "selected candidate is preserved but not live-approvable under current policy",
        }
    if candidates:
        return {
            "kind": "select_candidate",
            "signal_id": candidates[0].get("signal_id"),
            "telegram_command": f"FIRST LIVE SELECT {candidates[0].get('signal_id')}",
            "reason": "queue-fresh candidates are available for explicit operator selection",
        }
    return {"kind": "wait_for_signal", "signal_id": None, "telegram_command": "FIRST LIVE CANDIDATES", "reason": "no queue-fresh candidates available"}


def _selection_result(
    status: str,
    reason: str,
    signal_id: str | None,
    *,
    queue: dict[str, Any] | None = None,
    env: Mapping[str, str] | None,
    log_dir: Path,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "signal_id": signal_id,
        "reason": reason,
        "candidate": find_candidate_in_queue(queue or {}, signal_id),
        "candidate_queue": queue,
        "selected_signal_id": (queue or {}).get("selected_signal_id"),
        "selected_signal_path": str(selected_signal_path(log_dir)),
        "order_placed": False,
        "real_order_placed": False,
        "network_allowed": False,
        "secrets_shown": False,
        "policy": _policy(env=env),
        "higher_timeframe_policy": get_higher_timeframe_live_policy(env=env),
    }
    return _sanitize(payload)


def _policy_status(*, timeframe: str, symbol: str | None, direction: str | None, env: Mapping[str, str] | None = None) -> tuple[str, list[str]]:
    config = load_strategy_audit_config(dict(os.environ if env is None else env))
    blockers: list[str] = []
    if symbol != "BTCUSDT":
        blockers.append("symbol is not BTCUSDT")
    if direction != "long":
        blockers.append("direction is not long")
    if timeframe in config.context_only_timeframes:
        blockers.append("timeframe is context-only until explicitly promoted")
        return "CONTEXT_ONLY", blockers
    if timeframe in config.blocked_timeframes:
        blockers.append("timeframe is blocked from live by strategy audit defaults")
        return "BLOCKED", blockers
    if timeframe in config.paper_only_timeframes:
        blockers.append("timeframe remains paper-only by default")
        return "PAPER_ONLY", blockers
    if timeframe in config.allowed_tiny_live_timeframes:
        return "TINY_LIVE_ALLOWED", blockers
    if _horizon(timeframe) in {"swing", "macro"}:
        blockers.append("higher timeframe live candidate policy is disabled by default")
        return "HIGHER_TIMEFRAME_REVIEW", blockers
    blockers.append("timeframe is not live-enabled by policy")
    return "BLOCKED", blockers


def is_first_live_signal_fresh(*, timeframe: object, age_minutes: float | None) -> bool:
    cutoff = FIRST_LIVE_FRESHNESS_CUTOFFS_MINUTES.get(str(timeframe or "").strip().lower())
    return bool(cutoff is not None and age_minutes is not None and age_minutes <= cutoff)


def _policy(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    config = load_strategy_audit_config(dict(source))
    higher_policy = get_higher_timeframe_live_policy(env=env)
    return {
        "live_allowed_timeframes": list(config.allowed_tiny_live_timeframes),
        "allowed_tiny_live_timeframes": list(config.allowed_tiny_live_timeframes),
        "paper_only_timeframes": list(config.paper_only_timeframes),
        "context_only_timeframes": list(config.context_only_timeframes),
        "blocked_timeframes": list(config.blocked_timeframes),
        "higher_timeframe_live_allowed": higher_policy.get("higher_timeframe_live_allowed") is True,
        "higher_timeframe_allowed_selected_timeframes": higher_policy.get("allowed_selected_timeframes") or [],
        "higher_timeframe_enable_hint": higher_policy.get("enable_hint"),
        "micro_live_allowed": get_first_live_timeframe_policy(env=env).get("micro_live_allowed") is True,
        "micro_live_timeframes": get_first_live_timeframe_policy(env=env).get("micro_live_timeframes") or [],
        "defaults": {
            "allowed_tiny_live_timeframes": list(DEFAULT_ALLOWED_TINY_LIVE_TIMEFRAMES),
            "paper_only_timeframes": list(DEFAULT_PAPER_ONLY_TIMEFRAMES),
            "context_only_timeframes": list(DEFAULT_CONTEXT_ONLY_TIMEFRAMES),
            "blocked_timeframes": list(DEFAULT_BLOCKED_TIMEFRAMES),
        },
    }


def _write_selected_signal(payload: dict[str, Any], *, log_dir: Path) -> None:
    path = selected_signal_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize(payload), sort_keys=True) + "\n", encoding="utf-8")


def _horizon(timeframe: str | None) -> str | None:
    if not timeframe:
        return None
    for name, values in HORIZON_BUCKETS.items():
        if timeframe in values:
            return name
    return None


def _normalize_timeframe(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for values in HORIZON_BUCKETS.values():
        for timeframe in values:
            if raw.lower() == timeframe.lower():
                return timeframe
    return raw


def _age_minutes(timestamp: str | None, *, now: datetime) -> float | None:
    parsed = _parse_datetime(timestamp)
    if parsed is None:
        return None
    return max(0.0, round((now - parsed).total_seconds() / 60.0, 2))


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


def _timestamp_from_signal_id(signal_id: str | None) -> str | None:
    if not signal_id:
        return None
    parts = str(signal_id).split("|")
    return parts[3] if len(parts) == 4 else None


def _raw_freshness(record: Mapping[str, Any], *, default: bool) -> bool:
    if isinstance(record.get("fresh"), bool):
        return bool(record["fresh"])
    freshness = record.get("freshness_status")
    if freshness is not None:
        return str(freshness).strip().lower() in {"fresh", "ok", "valid"}
    return bool(default)


def _first_float(record: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = record.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _parse_bool(raw: object, *, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return default


def _clean(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in ("order_placed", "real_order_placed", "network_allowed", "secrets_shown"):
            if key in sanitized:
                sanitized[key] = False
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
