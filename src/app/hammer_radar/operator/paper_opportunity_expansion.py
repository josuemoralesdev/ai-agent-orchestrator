"""R152 paper-only opportunity expansion preview/apply surface.

This module widens paper visibility only. It never creates order payloads,
calls Binance, mutates env files, changes global live flags, or authorizes live
execution.
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
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import DEFAULT_CONFIG_PATH, SAFETY_FALSE, load_lane_controls, normalize_lane_key
from src.app.hammer_radar.operator.strategy_performance import PREFERRED_ENTRY_MODE

PAPER_OPPORTUNITY_EXPANSION_PREVIEW = "PAPER_OPPORTUNITY_EXPANSION_PREVIEW"
PAPER_OPPORTUNITY_EXPANSION_READY = "PAPER_OPPORTUNITY_EXPANSION_READY"
PAPER_OPPORTUNITY_EXPANSION_REJECTED = "PAPER_OPPORTUNITY_EXPANSION_REJECTED"
PAPER_OPPORTUNITY_EXPANSION_APPLIED = "PAPER_OPPORTUNITY_EXPANSION_APPLIED"
PAPER_OPPORTUNITY_EXPANSION_BLOCKED = "PAPER_OPPORTUNITY_EXPANSION_BLOCKED"
PAPER_OPPORTUNITY_EXPANSION_ERROR = "PAPER_OPPORTUNITY_EXPANSION_ERROR"

EVENT_TYPE = "PAPER_OPPORTUNITY_EXPANSION"
LEDGER_FILENAME = "paper_opportunity_expansions.ndjson"
CONFIRM_PAPER_OPPORTUNITY_EXPANSION_PHRASE = (
    "I CONFIRM PAPER OPPORTUNITY EXPANSION ONLY; NO LIVE LANES; NO ORDER; NO BINANCE CALL."
)

TARGET_SYMBOL = "BTCUSDT"
TARGET_ENTRY_MODE = PREFERRED_ENTRY_MODE
TARGET_TINY_LIVE_LANES = (
    "BTCUSDT|13m|long|ladder_close_50_618",
    "BTCUSDT|44m|long|ladder_close_50_618",
)
DEFAULT_TIMEFRAMES = ("4m", "8m", "13m", "44m")
DEFAULT_LATEST_SIGNALS = 1000
MAX_LATEST_SIGNALS = 20000
DEFAULT_LATEST_SCANS = 2000
MAX_LATEST_SCANS = 50000

RISK_BY_TIMEFRAME = {
    "4m": {"max_daily_loss_pct": 0.10, "freshness_seconds": 30, "cooldown_after_loss_minutes": 120},
    "8m": {"max_daily_loss_pct": 0.15, "freshness_seconds": 60, "cooldown_after_loss_minutes": 120},
    "13m": {"max_daily_loss_pct": 0.20, "freshness_seconds": 120, "cooldown_after_loss_minutes": 120},
    "44m": {"max_daily_loss_pct": 0.20, "freshness_seconds": 300, "cooldown_after_loss_minutes": 180},
}

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "network_allowed": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "global_live_flags_changed": False,
    "config_written": False,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    "operator.lane_control.load_lane_controls",
    "operator.lane_control.normalize_lane_key",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_default_paper_expansion_lanes(*, timeframes: list[str] | tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    lanes: list[dict[str, Any]] = []
    for timeframe in _ordered_timeframes(timeframes or DEFAULT_TIMEFRAMES):
        if timeframe not in RISK_BY_TIMEFRAME:
            continue
        for direction in ("long", "short"):
            lane_key = normalize_lane_key(TARGET_SYMBOL, timeframe, direction, TARGET_ENTRY_MODE)
            risk = RISK_BY_TIMEFRAME[timeframe]
            lanes.append(
                {
                    "lane_key": lane_key,
                    "symbol": TARGET_SYMBOL,
                    "timeframe": timeframe,
                    "direction": direction,
                    "entry_mode": TARGET_ENTRY_MODE,
                    "mode": "tiny_live" if lane_key in TARGET_TINY_LIVE_LANES else "paper",
                    "max_daily_trades": 1,
                    "max_daily_loss_pct": risk["max_daily_loss_pct"],
                    "freshness_seconds": risk["freshness_seconds"],
                    "cooldown_after_loss_minutes": risk["cooldown_after_loss_minutes"],
                    "require_protective_orders": True,
                }
            )
    return lanes


def build_recent_btcusdt_timeframe_direction_distribution(
    *,
    log_dir: str | Path | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    bounded_signals = _bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS)
    bounded_scans = _bounded_int(latest_scans, 1, MAX_LATEST_SCANS, DEFAULT_LATEST_SCANS)
    signal_records = read_recent_ndjson_records(
        resolved_log_dir / "signals.ndjson",
        limit=bounded_signals,
        max_bytes=16_777_216,
    )
    scan_records = read_recent_ndjson_records(
        resolved_log_dir / "multi_symbol_paper_scans.ndjson",
        limit=bounded_scans,
        max_bytes=32_000_000,
    )
    signal_rows = [_candidate_row(record, "signals.ndjson") for record in signal_records]
    scan_rows = [_candidate_row(record, "multi_symbol_paper_scans.ndjson") for record in scan_records]
    signal_rows = [row for row in signal_rows if row["symbol"] == TARGET_SYMBOL and row["timeframe"]]
    scan_rows = [row for row in scan_rows if row["symbol"] == TARGET_SYMBOL and row["timeframe"]]
    combined = signal_rows + scan_rows
    by_tf_dir = Counter(f"{row['timeframe']}|{row['direction'] or 'unknown'}" for row in combined)
    by_timeframe = Counter(row["timeframe"] for row in combined)
    by_direction = Counter(row["direction"] or "unknown" for row in combined)
    recent_timeframes = _ordered_timeframes([*by_timeframe.keys(), *DEFAULT_TIMEFRAMES])
    return {
        "generated_at": (now or datetime.now(UTC)).isoformat(),
        "latest_signals_checked": len(signal_records),
        "latest_scans_checked": len(scan_records),
        "btcusdt_signal_rows": len(signal_rows),
        "btcusdt_scan_rows": len(scan_rows),
        "by_timeframe_direction": dict(sorted(by_tf_dir.items())),
        "by_timeframe": dict(sorted(by_timeframe.items(), key=lambda item: _timeframe_sort_key(item[0]))),
        "by_direction": dict(sorted(by_direction.items())),
        "target_tiny_live_lanes": list(TARGET_TINY_LIVE_LANES),
        "short_signal_count": sum(1 for row in signal_rows if row["direction"] == "short"),
        "long_signal_count": sum(1 for row in signal_rows if row["direction"] == "long"),
        "scanned_timeframes_seen": recent_timeframes,
        "safety": dict(SAFETY),
    }


def build_paper_opportunity_expansion_preview(
    *,
    log_dir: str | Path | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    include_default_expansion: bool = False,
    apply: bool = False,
    confirm_paper_expansion: str | None = None,
    record_expansion: bool = False,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_paper_expansion == CONFIRM_PAPER_OPPORTUNITY_EXPANSION_PHRASE
    resolved_config = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    try:
        controls = load_lane_controls(resolved_config)
        existing_lane_map = dict(controls.get("lane_map") or {})
        distribution = build_recent_btcusdt_timeframe_direction_distribution(
            log_dir=resolved_log_dir,
            latest_signals=latest_signals,
            latest_scans=latest_scans,
            now=generated_at,
        )
        proposed = build_default_paper_expansion_lanes() if include_default_expansion else []
        plan = validate_paper_expansion_plan(existing_lanes=list(existing_lane_map.values()), proposed_lanes=proposed)
        status = PAPER_OPPORTUNITY_EXPANSION_READY if plan["plan_valid"] else PAPER_OPPORTUNITY_EXPANSION_BLOCKED
        config_written = False
        expansion_recorded = False
        expansion_id = None
        ledger_path = None
        if not apply:
            status = PAPER_OPPORTUNITY_EXPANSION_PREVIEW
        elif not confirmation_valid:
            status = PAPER_OPPORTUNITY_EXPANSION_REJECTED
        elif plan["plan_valid"]:
            apply_result = apply_paper_opportunity_expansion_plan(
                config_path=resolved_config,
                lanes_to_add=plan["lanes_to_add"],
            )
            config_written = bool(apply_result["config_written"])
            status = PAPER_OPPORTUNITY_EXPANSION_APPLIED
        safety = {**SAFETY, "config_written": bool(config_written)}
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "apply_requested": bool(apply),
            "confirmation_valid": bool(confirmation_valid),
            "config_written": bool(config_written),
            "expansion_recorded": False,
            "expansion_id": None,
            "existing_lanes": {
                key: _compact_lane(lane)
                for key, lane in sorted(existing_lane_map.items())
            },
            "proposed_lanes": [_compact_lane(lane) for lane in proposed],
            "lanes_to_add": [_compact_lane(lane) for lane in plan["lanes_to_add"]],
            "lanes_to_preserve": [_compact_lane(lane) for lane in plan["lanes_to_preserve"]],
            "lanes_not_modified": [_compact_lane(lane) for lane in plan["lanes_not_modified"]],
            "forbidden_changes_blocked": list(plan["forbidden_changes_blocked"]),
            "recent_distribution": distribution,
            "paper_watch_scope": _paper_watch_scope(existing_lane_map, plan["lanes_to_add"]),
            "expected_after_apply": {
                "new_lanes_are_paper_only": True,
                "existing_tiny_live_lanes_preserved": _target_tiny_live_lanes_preserved(existing_lane_map),
                "live_execution_enabled": False,
                "orders_allowed": False,
            },
            "recommended_next_operator_move": _recommended_next_move(status, plan["lanes_to_add"]),
            "safe_commands": _safe_commands(plan["lanes_to_add"], existing_lane_map),
            "do_not_run_yet": [
                "live-connector-submit",
                "any order endpoint",
                "global live flag arming",
                "kill switch disable",
                "set short lane tiny_live",
            ],
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_expansion and status == PAPER_OPPORTUNITY_EXPANSION_APPLIED and confirmation_valid:
            record = append_paper_opportunity_expansion_record(payload, log_dir=resolved_log_dir)
            expansion_recorded = True
            expansion_id = record["expansion_id"]
            ledger_path = str(paper_opportunity_expansion_records_path(resolved_log_dir))
        payload["expansion_recorded"] = expansion_recorded
        payload["expansion_id"] = expansion_id
        if ledger_path:
            payload["ledger_path"] = ledger_path
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": PAPER_OPPORTUNITY_EXPANSION_ERROR,
                "generated_at": generated_at.isoformat(),
                "apply_requested": bool(apply),
                "confirmation_valid": bool(confirmation_valid),
                "config_written": False,
                "expansion_recorded": False,
                "expansion_id": None,
                "existing_lanes": {},
                "proposed_lanes": [],
                "lanes_to_add": [],
                "lanes_to_preserve": [],
                "lanes_not_modified": [],
                "forbidden_changes_blocked": [f"expansion failed: {exc.__class__.__name__}"],
                "recent_distribution": {},
                "paper_watch_scope": {},
                "expected_after_apply": {
                    "new_lanes_are_paper_only": False,
                    "existing_tiny_live_lanes_preserved": False,
                    "live_execution_enabled": False,
                    "orders_allowed": False,
                },
                "recommended_next_operator_move": "STOP_AND_REVIEW_R152_ERROR",
                "safe_commands": _safe_commands([], {}),
                "do_not_run_yet": [
                    "live-connector-submit",
                    "any order endpoint",
                    "global live flag arming",
                    "kill switch disable",
                    "set short lane tiny_live",
                ],
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def validate_paper_expansion_plan(
    *,
    existing_lanes: list[Mapping[str, Any]],
    proposed_lanes: list[Mapping[str, Any]],
) -> dict[str, Any]:
    existing_map = {str(lane.get("lane_key") or _lane_key(lane)): dict(lane) for lane in existing_lanes}
    lanes_to_add: list[dict[str, Any]] = []
    lanes_to_preserve: list[dict[str, Any]] = []
    forbidden: list[str] = []
    seen: set[str] = set()
    for raw_lane in proposed_lanes:
        lane = _normalize_expansion_lane(raw_lane)
        lane_key = lane["lane_key"]
        if lane_key in seen:
            forbidden.append(f"duplicate proposed lane blocked: {lane_key}")
            continue
        seen.add(lane_key)
        existing = existing_map.get(lane_key)
        if existing:
            if str(existing.get("mode") or "").strip().lower() == "tiny_live" and lane_key not in TARGET_TINY_LIVE_LANES:
                forbidden.append(f"non-target tiny_live lane already exists and is not expanded: {lane_key}")
            if lane_key in TARGET_TINY_LIVE_LANES and str(existing.get("mode") or "").strip().lower() != "tiny_live":
                forbidden.append(f"target tiny_live lane mode would not be preserved: {lane_key}")
            lanes_to_preserve.append(dict(existing))
            continue
        if lane["mode"] != "paper":
            forbidden.append(f"new lane must be paper only: {lane_key}")
            continue
        if lane["direction"] == "short" and lane["mode"] == "tiny_live":
            forbidden.append(f"short lane tiny_live blocked: {lane_key}")
            continue
        if lane["symbol"] != TARGET_SYMBOL:
            forbidden.append(f"non-BTCUSDT expansion blocked: {lane_key}")
            continue
        if not bool(lane.get("require_protective_orders")):
            forbidden.append(f"paper expansion lane requires protective order metadata: {lane_key}")
            continue
        lanes_to_add.append(lane)
    for lane in lanes_to_add:
        if str(lane.get("mode") or "") != "paper":
            forbidden.append(f"new expansion lane is not paper: {lane['lane_key']}")
    return {
        "plan_valid": not forbidden,
        "lanes_to_add": lanes_to_add,
        "lanes_to_preserve": lanes_to_preserve,
        "lanes_not_modified": list(existing_map.values()),
        "forbidden_changes_blocked": _dedupe(forbidden),
    }


def apply_paper_opportunity_expansion_plan(
    *,
    config_path: str | Path | None = None,
    lanes_to_add: list[Mapping[str, Any]],
) -> dict[str, Any]:
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    raw = _load_raw_lane_config(path)
    existing = load_lane_controls(path)
    validation = validate_paper_expansion_plan(
        existing_lanes=list((existing.get("lane_map") or {}).values()),
        proposed_lanes=list(lanes_to_add),
    )
    if validation["forbidden_changes_blocked"]:
        return {"config_written": False, "blockers": list(validation["forbidden_changes_blocked"])}
    if not validation["lanes_to_add"]:
        return {"config_written": False, "blockers": [], "reason": "no lanes to add"}
    raw_lanes = list(raw.get("lanes") or [])
    for lane in validation["lanes_to_add"]:
        raw_lanes.append(_raw_lane(lane))
    raw["lanes"] = raw_lanes
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return {"config_written": True, "lanes_added": [_compact_lane(lane) for lane in validation["lanes_to_add"]]}


def append_paper_opportunity_expansion_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = paper_opportunity_expansion_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "expansion_id": record.get("expansion_id") or f"paper_opportunity_expansion_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "apply_requested": bool(record.get("apply_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "config_written": bool(record.get("config_written")),
            "lanes_to_add": list(record.get("lanes_to_add") or []),
            "lanes_to_preserve": list(record.get("lanes_to_preserve") or []),
            "paper_watch_scope": dict(record.get("paper_watch_scope") or {}),
            "recent_distribution": dict(record.get("recent_distribution") or {}),
            "expected_after_apply": dict(record.get("expected_after_apply") or {}),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_paper_opportunity_expansion_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = paper_opportunity_expansion_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records = read_recent_ndjson_records(path, limit=limit if limit > 0 else 100000, max_bytes=16_777_216)
    if limit <= 0:
        records = list(reversed(records))
    return [_sanitize(record) for record in records]


def summarize_paper_opportunity_expansions(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_expansion_id": records[0].get("expansion_id") if records else None,
        "config_write_count": sum(1 for record in records if bool(record.get("config_written"))),
        "safety": dict(SAFETY),
    }


def paper_opportunity_expansion_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_paper_opportunity_expansion_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _load_raw_lane_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError("lane_controls.json root must be an object")
    if not isinstance(raw.get("lanes"), list):
        raw["lanes"] = []
    return raw


def _candidate_row(record: Mapping[str, Any], source: str) -> dict[str, Any]:
    raw = dict(record)
    symbol = str(_first_present(raw, "symbol", "base_symbol") or "").strip().upper()
    timeframe = str(_first_present(raw, "timeframe", "tf", "interval") or "").strip().lower()
    direction = str(_first_present(raw, "direction", "bias_direction", "side") or "").strip().lower()
    if direction in {"buy", "bull", "bullish"}:
        direction = "long"
    if direction in {"sell", "bear", "bearish"}:
        direction = "short"
    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "timestamp": _first_present(raw, "generated_at", "timestamp", "closed_at", "detected_at"),
    }


def _paper_watch_scope(existing_lane_map: Mapping[str, Any], lanes_to_add: list[Mapping[str, Any]]) -> dict[str, Any]:
    lanes = [dict(lane) for lane in existing_lane_map.values()] + [dict(lane) for lane in lanes_to_add]
    active = [lane for lane in lanes if str(lane.get("mode") or "").strip().lower() in {"paper", "tiny_live"}]
    paper = [lane for lane in active if str(lane.get("mode") or "").strip().lower() == "paper"]
    tiny = [lane for lane in active if str(lane.get("mode") or "").strip().lower() == "tiny_live"]
    return {
        "paper_lanes_count": len(paper),
        "tiny_live_lanes_count": len(tiny),
        "directions_covered": sorted({str(lane.get("direction") or "") for lane in active if lane.get("direction")}),
        "timeframes_covered": _ordered_timeframes([str(lane.get("timeframe") or "") for lane in active]),
        "paper_lane_keys": sorted(str(lane.get("lane_key") or _lane_key(lane)) for lane in paper),
        "tiny_live_lane_keys": sorted(str(lane.get("lane_key") or _lane_key(lane)) for lane in tiny),
        "no_live_permission_implied": True,
    }


def _safe_commands(lanes_to_add: list[Mapping[str, Any]], existing_lane_map: Mapping[str, Any]) -> list[str]:
    all_keys = sorted(
        {
            str(lane.get("lane_key") or _lane_key(lane))
            for lane in [*existing_lane_map.values(), *lanes_to_add]
            if str(lane.get("symbol") or "").upper() == TARGET_SYMBOL
            and str(lane.get("mode") or "").strip().lower() in {"paper", "tiny_live"}
        }
    )
    lane_csv = ",".join(all_keys)
    return [
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward paper-opportunity-expansion --latest-signals 1000 --latest-scans 2000 --include-default-expansion",
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward paper-opportunity-expansion --include-default-expansion --apply --record-expansion --confirm-paper-expansion \"I CONFIRM PAPER OPPORTUNITY EXPANSION ONLY; NO LIVE LANES; NO ORDER; NO BINANCE CALL.\"",
        f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward fresh-candidate-paper-proof-capture-loop --lane-keys {lane_csv} --max-iterations 720 --sleep-seconds 60 --latest-signals 1000 --latest-scans 2000 --iteration-timeout-seconds 30 --heartbeat-every 1",
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward paper-opportunity-expansion --latest-signals 1000 --latest-scans 2000 --include-default-expansion",
    ]


def _recommended_next_move(status: str, lanes_to_add: list[Mapping[str, Any]]) -> str:
    if status == PAPER_OPPORTUNITY_EXPANSION_PREVIEW and lanes_to_add:
        return "APPLY_PAPER_OPPORTUNITY_EXPANSION"
    if status == PAPER_OPPORTUNITY_EXPANSION_APPLIED:
        return "RUN_EXPANDED_PAPER_WATCH"
    if status == PAPER_OPPORTUNITY_EXPANSION_READY:
        return "APPLY_PAPER_OPPORTUNITY_EXPANSION"
    return "RUN_R153_OPPORTUNITY_DISTRIBUTION_RECHECK"


def _target_tiny_live_lanes_preserved(existing_lane_map: Mapping[str, Any]) -> bool:
    return all(str((existing_lane_map.get(key) or {}).get("mode") or "").strip().lower() == "tiny_live" for key in TARGET_TINY_LIVE_LANES)


def _normalize_expansion_lane(lane: Mapping[str, Any]) -> dict[str, Any]:
    symbol = str(lane.get("symbol") or TARGET_SYMBOL).strip().upper()
    timeframe = str(lane.get("timeframe") or "").strip().lower()
    direction = str(lane.get("direction") or "").strip().lower()
    entry_mode = str(lane.get("entry_mode") or TARGET_ENTRY_MODE).strip().lower()
    lane_key = normalize_lane_key(symbol, timeframe, direction, entry_mode)
    return {
        "lane_key": lane_key,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "mode": str(lane.get("mode") or "paper").strip().lower(),
        "max_daily_trades": int(lane.get("max_daily_trades") or 1),
        "max_daily_loss_pct": float(lane.get("max_daily_loss_pct") or 0.0),
        "freshness_seconds": int(lane.get("freshness_seconds") or 0),
        "cooldown_after_loss_minutes": int(lane.get("cooldown_after_loss_minutes") or 0),
        "require_protective_orders": bool(lane.get("require_protective_orders")),
    }


def _compact_lane(lane: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _normalize_expansion_lane(lane)
    return {
        "lane_key": normalized["lane_key"],
        "symbol": normalized["symbol"],
        "timeframe": normalized["timeframe"],
        "direction": normalized["direction"],
        "entry_mode": normalized["entry_mode"],
        "mode": normalized["mode"],
        "max_daily_trades": normalized["max_daily_trades"],
        "max_daily_loss_pct": normalized["max_daily_loss_pct"],
        "freshness_seconds": normalized["freshness_seconds"],
        "cooldown_after_loss_minutes": normalized["cooldown_after_loss_minutes"],
        "require_protective_orders": normalized["require_protective_orders"],
    }


def _raw_lane(lane: Mapping[str, Any]) -> dict[str, Any]:
    compact = _compact_lane(lane)
    compact.pop("lane_key", None)
    return compact


def _lane_key(lane: Mapping[str, Any]) -> str:
    return normalize_lane_key(lane.get("symbol"), lane.get("timeframe"), lane.get("direction"), lane.get("entry_mode"))


def _ordered_timeframes(values: list[str] | tuple[str, ...]) -> list[str]:
    return sorted({str(value or "").strip().lower() for value in values if str(value or "").strip()}, key=_timeframe_sort_key)


def _timeframe_sort_key(value: str) -> tuple[int, str]:
    text = str(value or "").lower()
    digits = "".join(ch for ch in text if ch.isdigit())
    unit = "".join(ch for ch in text if ch.isalpha())
    multiplier = {"m": 1, "h": 60, "d": 1440}.get(unit or "m", 1)
    return (int(digits or 0) * multiplier, text)


def _bounded_int(value: int, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _first_present(raw: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
