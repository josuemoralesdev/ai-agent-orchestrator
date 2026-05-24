"""R123 fresh signal router over R122 lane controls.

This module is diagnostic and non-executing. It maps local Hammer Radar signal
or candidate records into R122 lane-control evaluation and never creates order
payloads, places orders, calls Binance, uses network, mutates env files, or
enables live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir, get_signals_path, load_signals
from src.app.hammer_radar.operator.lane_control import (
    LANE_ALLOWED,
    LANE_DISABLED,
    SAFETY_FALSE,
    build_lane_control_status,
    evaluate_lane_permission,
    load_lane_controls,
    normalize_lane_key,
)
from src.app.hammer_radar.operator.strategy_performance import (
    PREFERRED_ENTRY_MODE,
    build_live_eligibility_matrix,
)

ROUTED_TO_LANE = "ROUTED_TO_LANE"
BLOCKED_BY_LANE = "BLOCKED_BY_LANE"
EXPIRED_SIGNAL = "EXPIRED_SIGNAL"
NO_MATCHING_LANE = "NO_MATCHING_LANE"
ROUTER_NO_CANDIDATE = "ROUTER_NO_CANDIDATE"
ROUTER_ERROR = "ROUTER_ERROR"

ROUTER_NO_CANDIDATE_SOURCE = "ROUTER_NO_CANDIDATE_SOURCE"
ROUTER_NO_CANDIDATES = "ROUTER_NO_CANDIDATES"
ROUTER_READY = "ROUTER_READY"

PAPER_OBSERVE = "PAPER_OBSERVE"
ARMED_DRY_RUN_OBSERVE = "ARMED_DRY_RUN_OBSERVE"
TINY_LIVE_BLOCKED_BY_GLOBAL_GATES = "TINY_LIVE_BLOCKED_BY_GLOBAL_GATES"
IGNORE = "IGNORE"


def normalize_candidate(candidate: Mapping[str, Any] | object) -> dict[str, Any]:
    raw = _candidate_mapping(candidate)
    symbol = str(raw.get("symbol") or "").strip().upper()
    timeframe = str(raw.get("timeframe") or "").strip().lower()
    direction = str(raw.get("direction") or "").strip().lower()
    entry_mode = str(raw.get("entry_mode") or PREFERRED_ENTRY_MODE).strip().lower()
    timestamp = _first_present(raw, "generated_at", "timestamp", "closed_at", "detected_at")
    candidate_id = _first_present(raw, "candidate_id", "signal_id") or _fallback_candidate_id(
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        timestamp=timestamp,
    )
    return {
        "candidate_id": str(candidate_id or ""),
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "generated_at": str(timestamp or ""),
        "score": raw.get("score"),
        "tier": raw.get("tier"),
        "freshness_status": raw.get("freshness_status"),
        "source_type": type(candidate).__name__,
    }


def build_lane_key_from_candidate(candidate: Mapping[str, Any] | object) -> str:
    normalized = normalize_candidate(candidate)
    return normalize_lane_key(
        normalized.get("symbol"),
        normalized.get("timeframe"),
        normalized.get("direction"),
        normalized.get("entry_mode"),
    )


def evaluate_candidate_against_lanes(
    candidate: Mapping[str, Any] | object,
    *,
    controls: Mapping[str, Any] | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    global_gate: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    normalized = normalize_candidate(candidate)
    lane_key = build_lane_key_from_candidate(normalized)
    loaded_controls = controls if controls is not None else load_lane_controls()
    lane_map = loaded_controls.get("lane_map") if isinstance(loaded_controls.get("lane_map"), Mapping) else {}
    matching_lane = lane_map.get(lane_key)

    if not _has_candidate_identity(normalized):
        return _route_payload(
            normalized=normalized,
            lane_key=lane_key,
            route_status=ROUTER_NO_CANDIDATE,
            candidate_age_seconds=None,
            freshness_seconds=None,
            lane_mode="disabled",
            lane_status=LANE_DISABLED,
            blockers=["candidate is missing symbol, timeframe, direction, or entry_mode"],
            route_action=IGNORE,
        )

    if not matching_lane:
        return _route_payload(
            normalized=normalized,
            lane_key=lane_key,
            route_status=NO_MATCHING_LANE,
            candidate_age_seconds=_candidate_age_seconds(normalized.get("generated_at"), generated_at),
            freshness_seconds=None,
            lane_mode="disabled",
            lane_status=LANE_DISABLED,
            blockers=["no matching R122 lane for candidate"],
            route_action=IGNORE,
        )

    freshness_seconds = _int_or_none(matching_lane.get("freshness_seconds"))
    candidate_age_seconds = _candidate_age_seconds(normalized.get("generated_at"), generated_at)
    if not _is_fresh(candidate_age_seconds, freshness_seconds, normalized.get("freshness_status")):
        return _route_payload(
            normalized=normalized,
            lane_key=lane_key,
            route_status=EXPIRED_SIGNAL,
            candidate_age_seconds=candidate_age_seconds,
            freshness_seconds=freshness_seconds,
            lane_mode=str(matching_lane.get("mode") or "disabled").strip().lower(),
            lane_status="EXPIRED",
            blockers=["candidate is older than lane freshness_seconds"],
            route_action=IGNORE,
        )

    permission = evaluate_lane_permission(
        normalized["symbol"],
        normalized["timeframe"],
        normalized["direction"],
        normalized["entry_mode"],
        controls=loaded_controls,
        live_eligibility_matrix=live_eligibility_matrix,
        global_gate=global_gate,
        log_dir=log_dir,
    )
    lane_mode = str(permission.get("mode") or "disabled").strip().lower()
    lane_status = str(permission.get("status") or "")
    blockers = list(permission.get("blockers") or [])
    if lane_status == LANE_ALLOWED:
        return _route_payload(
            normalized=normalized,
            lane_key=lane_key,
            route_status=ROUTED_TO_LANE,
            candidate_age_seconds=candidate_age_seconds,
            freshness_seconds=freshness_seconds,
            lane_mode=lane_mode,
            lane_status=lane_status,
            blockers=blockers,
            route_action=_route_action_for_allowed_mode(lane_mode),
        )

    return _route_payload(
        normalized=normalized,
        lane_key=lane_key,
        route_status=BLOCKED_BY_LANE,
        candidate_age_seconds=candidate_age_seconds,
        freshness_seconds=freshness_seconds,
        lane_mode=lane_mode,
        lane_status=lane_status,
        blockers=blockers or [f"lane permission status is {lane_status or 'UNKNOWN'}"],
        route_action=_route_action_for_blocked_mode(lane_mode),
    )


def build_fresh_signal_router_status(
    *,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    candidates: list[Mapping[str, Any] | object] | None = None,
    now: datetime | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    global_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_path = get_signals_path(resolved_log_dir)
    source_status = "provided_candidates"
    source_candidates = candidates
    if source_candidates is None:
        source_status = "signals_ndjson"
        if not source_path.exists():
            return _empty_status(
                status=ROUTER_NO_CANDIDATE_SOURCE,
                generated_at=generated_at,
                source_path=source_path,
                reason="signals.ndjson candidate source is missing",
                log_dir=resolved_log_dir,
                config_path=config_path,
            )
        source_candidates = load_signals(resolved_log_dir)
    if not source_candidates:
        return _empty_status(
            status=ROUTER_NO_CANDIDATES,
            generated_at=generated_at,
            source_path=source_path,
            reason="no candidates available for routing",
            log_dir=resolved_log_dir,
            config_path=config_path,
        )

    controls = load_lane_controls(config_path)
    matrix = live_eligibility_matrix if live_eligibility_matrix is not None else build_live_eligibility_matrix(log_dir=resolved_log_dir)
    routed: list[dict[str, Any]] = []
    for candidate in source_candidates:
        try:
            routed.append(
                evaluate_candidate_against_lanes(
                    candidate,
                    controls=controls,
                    live_eligibility_matrix=matrix,
                    global_gate=global_gate,
                    now=generated_at,
                    log_dir=resolved_log_dir,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive status surface
            normalized = normalize_candidate(candidate)
            routed.append(
                _route_payload(
                    normalized=normalized,
                    lane_key=build_lane_key_from_candidate(normalized),
                    route_status=ROUTER_ERROR,
                    candidate_age_seconds=None,
                    freshness_seconds=None,
                    lane_mode="disabled",
                    lane_status="ROUTER_ERROR",
                    blockers=[f"router error: {type(exc).__name__}"],
                    route_action=IGNORE,
                )
            )

    counts = Counter(row["route_status"] for row in routed)
    lane_summary = build_lane_control_status(
        log_dir=resolved_log_dir,
        config_path=config_path,
        live_eligibility_matrix=matrix,
    )
    return {
        "status": ROUTER_READY,
        "generated_at": generated_at.isoformat(),
        "candidate_source": source_status,
        "candidate_source_path": str(source_path),
        "candidates_seen_count": len(routed),
        "routed_count": counts.get(ROUTED_TO_LANE, 0),
        "expired_count": counts.get(EXPIRED_SIGNAL, 0),
        "blocked_count": counts.get(BLOCKED_BY_LANE, 0),
        "no_matching_lane_count": counts.get(NO_MATCHING_LANE, 0),
        "routed_candidates": _compact_candidates(routed, ROUTED_TO_LANE),
        "blocked_candidates": _compact_candidates(routed, BLOCKED_BY_LANE),
        "expired_candidates": _compact_candidates(routed, EXPIRED_SIGNAL),
        "lane_summary": _compact_lane_summary(lane_summary),
        "top_blockers": _top_blockers(routed),
        "safety": _safety_summary(routed),
    }


def format_fresh_signal_router_status_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _candidate_mapping(candidate: Mapping[str, Any] | object) -> dict[str, Any]:
    if isinstance(candidate, Mapping):
        return dict(candidate)
    if is_dataclass(candidate):
        return asdict(candidate)
    return {
        key: getattr(candidate, key)
        for key in (
            "symbol",
            "timeframe",
            "direction",
            "entry_mode",
            "candidate_id",
            "signal_id",
            "generated_at",
            "timestamp",
            "closed_at",
            "detected_at",
            "score",
            "tier",
            "freshness_status",
        )
        if hasattr(candidate, key)
    }


def _first_present(raw: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _fallback_candidate_id(*, symbol: str, timeframe: str, direction: str, timestamp: Any) -> str:
    parts = [part for part in (symbol, timeframe, direction, str(timestamp or "").strip()) if part]
    return "|".join(parts)


def _has_candidate_identity(candidate: Mapping[str, Any]) -> bool:
    return all(str(candidate.get(key) or "").strip() for key in ("symbol", "timeframe", "direction", "entry_mode"))


def _candidate_age_seconds(timestamp: object, now: datetime) -> float | None:
    parsed = _parse_timestamp(timestamp)
    if parsed is None:
        return None
    return max((now - parsed).total_seconds(), 0.0)


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


def _is_fresh(age_seconds: float | None, freshness_seconds: int | None, freshness_status: object) -> bool:
    if str(freshness_status or "").strip().lower() == "expired":
        return False
    if age_seconds is None:
        return False
    if freshness_seconds is None or freshness_seconds <= 0:
        return False
    return age_seconds <= freshness_seconds


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _route_action_for_allowed_mode(mode: str) -> str:
    if mode == "paper":
        return PAPER_OBSERVE
    if mode == "armed_dry_run":
        return ARMED_DRY_RUN_OBSERVE
    if mode == "tiny_live":
        return TINY_LIVE_BLOCKED_BY_GLOBAL_GATES
    return IGNORE


def _route_action_for_blocked_mode(mode: str) -> str:
    if mode == "tiny_live":
        return TINY_LIVE_BLOCKED_BY_GLOBAL_GATES
    return IGNORE


def _route_payload(
    *,
    normalized: Mapping[str, Any],
    lane_key: str,
    route_status: str,
    candidate_age_seconds: float | None,
    freshness_seconds: int | None,
    lane_mode: str,
    lane_status: str,
    blockers: list[str],
    route_action: str,
) -> dict[str, Any]:
    return {
        "route_status": route_status,
        "candidate_id": normalized.get("candidate_id"),
        "lane_key": lane_key,
        "symbol": normalized.get("symbol"),
        "timeframe": normalized.get("timeframe"),
        "direction": normalized.get("direction"),
        "entry_mode": normalized.get("entry_mode"),
        "candidate_age_seconds": candidate_age_seconds,
        "freshness_seconds": freshness_seconds,
        "lane_mode": lane_mode,
        "lane_status": lane_status,
        "blockers": _dedupe(blockers),
        "route_action": route_action,
        "safety": dict(SAFETY_FALSE),
    }


def _empty_status(
    *,
    status: str,
    generated_at: datetime,
    source_path: Path,
    reason: str,
    log_dir: Path,
    config_path: str | Path | None,
) -> dict[str, Any]:
    lane_summary = build_lane_control_status(log_dir=log_dir, config_path=config_path, live_eligibility_matrix={"recommendations": []})
    return {
        "status": status,
        "generated_at": generated_at.isoformat(),
        "candidate_source": "signals_ndjson",
        "candidate_source_path": str(source_path),
        "reason": reason,
        "candidates_seen_count": 0,
        "routed_count": 0,
        "expired_count": 0,
        "blocked_count": 0,
        "no_matching_lane_count": 0,
        "routed_candidates": [],
        "blocked_candidates": [],
        "expired_candidates": [],
        "lane_summary": _compact_lane_summary(lane_summary),
        "top_blockers": [],
        "safety": dict(SAFETY_FALSE),
    }


def _compact_candidates(rows: list[Mapping[str, Any]], status: str, *, limit: int = 12) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if row.get("route_status") != status:
            continue
        result.append(
            {
                "candidate_id": row.get("candidate_id"),
                "lane_key": row.get("lane_key"),
                "route_status": row.get("route_status"),
                "route_action": row.get("route_action"),
                "candidate_age_seconds": row.get("candidate_age_seconds"),
                "freshness_seconds": row.get("freshness_seconds"),
                "lane_mode": row.get("lane_mode"),
                "lane_status": row.get("lane_status"),
                "blockers": list(row.get("blockers") or [])[:3],
            }
        )
        if len(result) >= limit:
            break
    return result


def _compact_lane_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status"),
        "configured_lanes_count": payload.get("configured_lanes_count"),
        "active_lanes_count": payload.get("active_lanes_count"),
        "status_counts": payload.get("status_counts"),
        "top_blockers": payload.get("top_blockers"),
        "safety": payload.get("safety"),
    }


def _top_blockers(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(blocker for row in rows for blocker in list(row.get("blockers") or []))
    return [{"blocker": blocker, "count": count} for blocker, count in counts.most_common(5)]


def _safety_summary(rows: list[Mapping[str, Any]]) -> dict[str, bool]:
    summary = dict(SAFETY_FALSE)
    for key in summary:
        summary[key] = any(bool((row.get("safety") or {}).get(key)) for row in rows)
    return summary


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
