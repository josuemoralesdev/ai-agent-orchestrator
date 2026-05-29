"""R122 non-executing autonomous lane-control scaffold.

Lane controls are operator intent only. This module reads local config and
existing live-eligibility reports, but never creates order payloads, places
orders, calls Binance order endpoints, or enables live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.first_live_activation_gate import FIRST_LIVE_ACTIVATION_READY
from src.app.hammer_radar.operator.strategy_performance import (
    ELIGIBLE_FOR_FUTURE_TINY_LIVE,
    build_live_eligibility_matrix,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "hammer_radar" / "lane_controls.json"

LANE_ALLOWED = "LANE_ALLOWED"
LANE_BLOCKED = "LANE_BLOCKED"
LANE_DISABLED = "LANE_DISABLED"
DISABLED_MODES = {"", "disabled", "off"}
ACTIVE_MODES = {"paper", "armed_dry_run", "tiny_live"}

SAFETY_FALSE = {
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "network_allowed": False,
    "secrets_shown": False,
}

FAST_LANE_MODE_GLOBAL_GATE_STATUS = "GLOBAL_GATE_NOT_EVALUATED_FAST_LANE_MODE_PATH"
FAST_LANE_MODE_GLOBAL_GATE_BLOCKERS = [
    "global gate not evaluated in fast lane mode path",
    "live execution remains disabled",
    "global kill switch remains authoritative",
]


def normalize_lane_key(symbol: object, timeframe: object, direction: object, entry_mode: object) -> str:
    return "|".join(
        [
            str(symbol or "").strip().upper(),
            str(timeframe or "").strip().lower(),
            str(direction or "").strip().lower(),
            str(entry_mode or "").strip().lower(),
        ]
    )


def load_lane_controls(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    lanes = [_normalize_lane_record(row) for row in raw.get("lanes", [])]
    return {
        "schema_version": str(raw.get("schema_version") or "1.0"),
        "default_mode": str(raw.get("default_mode") or "disabled").strip().lower(),
        "config_path": str(path),
        "notes": list(raw.get("notes") or []),
        "lanes": lanes,
        "lane_map": {lane["lane_key"]: lane for lane in lanes},
    }


def list_lanes(controls: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    loaded = controls if controls is not None else load_lane_controls()
    return list(loaded.get("lanes") or [])


def build_fast_lane_mode_global_gate_sentinel() -> dict[str, Any]:
    return {
        "status": FAST_LANE_MODE_GLOBAL_GATE_STATUS,
        "ready": False,
        "execution_enabled": False,
        "execution_enabled_by_gate": False,
        "global_kill_switch_active": True,
        "allow_live_orders": False,
        "blockers": list(FAST_LANE_MODE_GLOBAL_GATE_BLOCKERS),
    }


def get_lane_by_tuple(
    symbol: object,
    timeframe: object,
    direction: object,
    entry_mode: object,
    *,
    controls: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    loaded = controls if controls is not None else load_lane_controls()
    lane_key = normalize_lane_key(symbol, timeframe, direction, entry_mode)
    lane = (loaded.get("lane_map") or {}).get(lane_key)
    if lane:
        return dict(lane)
    return _disabled_lane(symbol, timeframe, direction, entry_mode)


def evaluate_lane_permission(
    symbol: object,
    timeframe: object,
    direction: object,
    entry_mode: object,
    *,
    controls: Mapping[str, Any] | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    global_gate: Mapping[str, Any] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    loaded = controls if controls is not None else load_lane_controls()
    lane = get_lane_by_tuple(symbol, timeframe, direction, entry_mode, controls=loaded)
    matrix = live_eligibility_matrix if live_eligibility_matrix is not None else build_live_eligibility_matrix(log_dir=log_dir)
    eligibility = _matching_eligibility(lane, matrix)
    mode = str(lane.get("mode") or "disabled").strip().lower()
    blockers: list[str] = []

    if mode in DISABLED_MODES:
        status = LANE_DISABLED
        blockers.append("lane is disabled by default or config")
    elif mode == "paper":
        status = LANE_ALLOWED
    elif mode == "armed_dry_run":
        if _eligibility_recommendation(eligibility) == ELIGIBLE_FOR_FUTURE_TINY_LIVE:
            status = LANE_ALLOWED
        else:
            status = LANE_BLOCKED
            blockers.append(_eligibility_blocker(eligibility))
    elif mode == "tiny_live":
        gate = global_gate if global_gate is not None else _load_global_gate(log_dir=log_dir)
        if _eligibility_recommendation(eligibility) != ELIGIBLE_FOR_FUTURE_TINY_LIVE:
            blockers.append(_eligibility_blocker(eligibility))
        if gate.get("status") != FIRST_LIVE_ACTIVATION_READY:
            blockers.append("global first-live activation gate is not FIRST_LIVE_ACTIVATION_READY")
        if bool(gate.get("execution_enabled_by_gate")) is not True:
            blockers.append("global gate has not enabled execution")
        blockers.extend(str(item) for item in (gate.get("blockers") or [])[:3] if item)
        status = LANE_ALLOWED if not blockers else LANE_BLOCKED
    else:
        status = LANE_BLOCKED
        blockers.append(f"unsupported lane mode: {mode}")

    blockers.extend(str(item) for item in (eligibility or {}).get("blockers", [])[:3] if item)
    blockers = _dedupe(blockers)
    return {
        "status": status,
        "mode": mode,
        "lane_key": lane["lane_key"],
        "symbol": lane["symbol"],
        "timeframe": lane["timeframe"],
        "direction": lane["direction"],
        "entry_mode": lane["entry_mode"],
        "freshness_seconds": lane.get("freshness_seconds"),
        "risk_limits": _risk_limits(lane),
        "live_eligibility": _compact_eligibility(eligibility),
        "blockers": blockers,
        "safety": dict(SAFETY_FALSE),
    }


def build_lane_control_status(
    *,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    controls = load_lane_controls(config_path)
    matrix = live_eligibility_matrix if live_eligibility_matrix is not None else build_live_eligibility_matrix(log_dir=log_dir)
    lanes = [
        evaluate_lane_permission(
            lane["symbol"],
            lane["timeframe"],
            lane["direction"],
            lane["entry_mode"],
            controls=controls,
            live_eligibility_matrix=matrix,
            log_dir=log_dir,
        )
        for lane in list_lanes(controls)
    ]
    active_lanes = [lane for lane in lanes if lane["mode"] not in DISABLED_MODES]
    status_counts = Counter(lane["status"] for lane in lanes)
    blockers = _top_blockers(lanes)
    return {
        "status": "LANE_CONTROL_READY" if active_lanes else "LANE_CONTROL_DISABLED",
        "generated_at": datetime.now(UTC).isoformat(),
        "configured_lanes_count": len(lanes),
        "active_lanes_count": len(active_lanes),
        "lanes": [_lane_summary(lane) for lane in lanes],
        "eligible_future_tiny_live_lanes": [
            lane["lane_key"]
            for lane in lanes
            if (lane.get("live_eligibility") or {}).get("recommendation") == ELIGIBLE_FOR_FUTURE_TINY_LIVE
        ],
        "top_blockers": blockers,
        "status_counts": dict(sorted(status_counts.items())),
        "safety": _safety_summary(lanes),
    }


def format_lane_control_status_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _normalize_lane_record(row: Mapping[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").strip().upper()
    timeframe = str(row.get("timeframe") or "").strip().lower()
    direction = str(row.get("direction") or "").strip().lower()
    entry_mode = str(row.get("entry_mode") or "").strip().lower()
    mode = str(row.get("mode") or "disabled").strip().lower()
    lane = {
        "lane_key": normalize_lane_key(symbol, timeframe, direction, entry_mode),
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "mode": mode,
        "max_daily_trades": int(row.get("max_daily_trades") or 0),
        "max_daily_loss_pct": float(row.get("max_daily_loss_pct") or 0.0),
        "freshness_seconds": int(row.get("freshness_seconds") or 0),
        "cooldown_after_loss_minutes": int(row.get("cooldown_after_loss_minutes") or 0),
        "require_protective_orders": bool(row.get("require_protective_orders")),
    }
    return lane


def _disabled_lane(symbol: object, timeframe: object, direction: object, entry_mode: object) -> dict[str, Any]:
    lane_key = normalize_lane_key(symbol, timeframe, direction, entry_mode)
    parts = lane_key.split("|")
    return {
        "lane_key": lane_key,
        "symbol": parts[0],
        "timeframe": parts[1],
        "direction": parts[2],
        "entry_mode": parts[3],
        "mode": "disabled",
        "max_daily_trades": 0,
        "max_daily_loss_pct": 0.0,
        "freshness_seconds": 0,
        "cooldown_after_loss_minutes": 0,
        "require_protective_orders": True,
    }


def _matching_eligibility(lane: Mapping[str, Any], matrix: Mapping[str, Any]) -> dict[str, Any] | None:
    for row in matrix.get("recommendations", []):
        if (
            str(row.get("timeframe") or "").strip().lower() == lane["timeframe"]
            and str(row.get("direction") or "").strip().lower() == lane["direction"]
            and str(row.get("entry_mode") or "").strip().lower() == lane["entry_mode"]
        ):
            return dict(row)
    return None


def _eligibility_recommendation(row: Mapping[str, Any] | None) -> str | None:
    if not row:
        return None
    return str(row.get("recommendation") or "")


def _eligibility_blocker(row: Mapping[str, Any] | None) -> str:
    if not row:
        return "no matching live eligibility row for lane"
    recommendation = _eligibility_recommendation(row)
    return f"live eligibility recommendation is {recommendation or 'UNKNOWN'}"


def _compact_eligibility(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"recommendation": "MISSING", "sample_count": 0, "win_rate_pct": 0.0, "avg_pnl_pct": 0.0}
    return {
        "recommendation": row.get("recommendation"),
        "sample_count": row.get("sample_count"),
        "win_rate_pct": row.get("win_rate_pct"),
        "avg_pnl_pct": row.get("avg_pnl_pct"),
        "total_pnl_pct": row.get("total_pnl_pct"),
    }


def _risk_limits(lane: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "max_daily_trades": lane.get("max_daily_trades"),
        "max_daily_loss_pct": lane.get("max_daily_loss_pct"),
        "cooldown_after_loss_minutes": lane.get("cooldown_after_loss_minutes"),
        "require_protective_orders": lane.get("require_protective_orders"),
    }


def _load_global_gate(*, log_dir: str | Path | None) -> dict[str, Any]:
    from src.app.hammer_radar.operator.first_live_activation_gate import build_first_live_activation_gate

    return build_first_live_activation_gate(log_dir=log_dir, record=False)


def _lane_summary(lane: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lane_key": lane.get("lane_key"),
        "status": lane.get("status"),
        "mode": lane.get("mode"),
        "freshness_seconds": lane.get("freshness_seconds"),
        "risk_limits": lane.get("risk_limits"),
        "live_eligibility": lane.get("live_eligibility"),
        "blockers": list(lane.get("blockers") or [])[:3],
        "safety": lane.get("safety"),
    }


def _top_blockers(lanes: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(
        blocker
        for lane in lanes
        for blocker in list(lane.get("blockers") or [])
    )
    return [{"blocker": blocker, "count": count} for blocker, count in counts.most_common(5)]


def _safety_summary(lanes: list[Mapping[str, Any]]) -> dict[str, bool]:
    summary = dict(SAFETY_FALSE)
    for key in summary:
        summary[key] = any(bool((lane.get("safety") or {}).get(key)) for lane in lanes)
    return summary


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
