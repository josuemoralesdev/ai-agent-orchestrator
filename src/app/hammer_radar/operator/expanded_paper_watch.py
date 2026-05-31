"""R153 expanded paper watch and opportunity recheck.

This module observes expanded BTCUSDT paper lanes only. It reads local ledgers
and lane controls, can append a local watch record after exact confirmation,
and never creates order payloads, calls Binance, mutates env/config, changes
global live flags, or authorizes live execution.
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
from src.app.hammer_radar.operator.paper_opportunity_expansion import (
    DEFAULT_TIMEFRAMES,
    TARGET_ENTRY_MODE,
    TARGET_SYMBOL,
    TARGET_TINY_LIVE_LANES,
)

EXPANDED_PAPER_WATCH_PREVIEW = "EXPANDED_PAPER_WATCH_PREVIEW"
EXPANDED_PAPER_WATCH_READY = "EXPANDED_PAPER_WATCH_READY"
EXPANDED_PAPER_WATCH_REJECTED = "EXPANDED_PAPER_WATCH_REJECTED"
EXPANDED_PAPER_WATCH_RECORDED = "EXPANDED_PAPER_WATCH_RECORDED"
EXPANDED_PAPER_WATCH_TIMEOUT = "EXPANDED_PAPER_WATCH_TIMEOUT"
EXPANDED_PAPER_WATCH_CAPTURED_PAPER_SIGNAL = "EXPANDED_PAPER_WATCH_CAPTURED_PAPER_SIGNAL"
EXPANDED_PAPER_WATCH_BLOCKED = "EXPANDED_PAPER_WATCH_BLOCKED"
EXPANDED_PAPER_WATCH_ERROR = "EXPANDED_PAPER_WATCH_ERROR"

EVENT_TYPE = "EXPANDED_PAPER_WATCH"
LEDGER_FILENAME = "expanded_paper_watch.ndjson"
CONFIRM_EXPANDED_PAPER_WATCH_RECORDING_PHRASE = (
    "I CONFIRM EXPANDED PAPER WATCH RECORDING ONLY; NO LIVE LANES; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_SIGNALS = 1000
MAX_LATEST_SIGNALS = 20000
DEFAULT_LATEST_SCANS = 2000
MAX_LATEST_SCANS = 50000

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    "operator.lane_control.load_lane_controls",
    "operator.lane_control.normalize_lane_key",
    "operator.paper_opportunity_expansion TARGET_TINY_LIVE_LANES",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_expanded_paper_watch_preview(
    *,
    log_dir: str | Path | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    all_paper_lanes: bool = False,
    include_tiny_live_targets_as_observed: bool = False,
    record_watch: bool = False,
    confirm_expanded_paper_watch: str | None = None,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_expanded_paper_watch == CONFIRM_EXPANDED_PAPER_WATCH_RECORDING_PHRASE
    try:
        scope = build_expanded_paper_lane_scope(
            all_paper_lanes=all_paper_lanes,
            include_tiny_live_targets_as_observed=include_tiny_live_targets_as_observed,
            config_path=config_path,
        )
        distribution = build_expanded_paper_distribution(
            log_dir=resolved_log_dir,
            paper_lanes=scope["paper_lanes"],
            latest_signals=latest_signals,
            latest_scans=latest_scans,
            now=generated_at,
        )
        opportunity_summary = evaluate_expanded_paper_candidates(
            paper_lanes=scope["paper_lanes"],
            candidate_distribution=distribution,
        )
        status = _status_for_preview(scope, opportunity_summary)
        if record_watch and not confirmation_valid:
            status = EXPANDED_PAPER_WATCH_REJECTED
        elif record_watch and confirmation_valid:
            status = EXPANDED_PAPER_WATCH_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "record_watch_requested": bool(record_watch),
            "confirmation_valid": bool(confirmation_valid),
            "watch_recorded": False,
            "watch_id": None,
            "expanded_scope": scope["expanded_scope"],
            "lane_config_state": scope["lane_config_state"],
            "candidate_distribution": distribution,
            "paper_opportunity_summary": opportunity_summary,
            "recommended_next_operator_move": _recommended_next_operator_move(status, opportunity_summary),
            "recommended_next_engineering_move": _recommended_next_engineering_move(status, opportunity_summary),
            "safe_commands": _safe_commands(),
            "do_not_run_yet": [
                "live-connector-submit",
                "any order endpoint",
                "global live flag arming",
                "kill switch disable",
                "set short lane tiny_live",
            ],
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_watch and confirmation_valid:
            record = append_expanded_paper_watch_record(payload, log_dir=resolved_log_dir)
            payload["watch_recorded"] = True
            payload["watch_id"] = record["watch_id"]
            payload["ledger_path"] = str(expanded_paper_watch_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": EXPANDED_PAPER_WATCH_ERROR,
                "generated_at": generated_at.isoformat(),
                "record_watch_requested": bool(record_watch),
                "confirmation_valid": bool(confirmation_valid),
                "watch_recorded": False,
                "watch_id": None,
                "expanded_scope": {
                    "paper_lanes": [],
                    "tiny_live_lanes_observed_but_not_changed": [],
                    "directions_covered": [],
                    "timeframes_covered": [],
                },
                "lane_config_state": {},
                "candidate_distribution": {},
                "paper_opportunity_summary": {
                    "fresh_paper_candidates_count": 0,
                    "paper_capture_candidates": [],
                    "short_paper_candidates_count": 0,
                    "long_paper_candidates_count": 0,
                    "best_next_paper_lane_family": "NONE",
                },
                "recommended_next_operator_move": "WAIT_FOR_FRESH_PAPER_CANDIDATE",
                "recommended_next_engineering_move": "Fix the R153 expanded paper watch error before changing lanes.",
                "safe_commands": _safe_commands(),
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


def build_expanded_paper_lane_scope(
    *,
    all_paper_lanes: bool = False,
    include_tiny_live_targets_as_observed: bool = False,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    controls = load_lane_controls(Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH)
    lanes = [dict(lane) for lane in controls.get("lanes") or []]
    paper_lanes = [
        _compact_lane(lane)
        for lane in lanes
        if _is_btcusdt_target_entry(lane) and str(lane.get("mode") or "").strip().lower() == "paper"
    ]
    if not all_paper_lanes:
        paper_lanes = [
            lane
            for lane in paper_lanes
            if lane["timeframe"] in set(DEFAULT_TIMEFRAMES) and lane["direction"] in {"long", "short"}
        ]
    tiny_lanes = [
        _compact_lane(lane)
        for lane in lanes
        if include_tiny_live_targets_as_observed
        and _lane_key(lane) in set(TARGET_TINY_LIVE_LANES)
        and str(lane.get("mode") or "").strip().lower() == "tiny_live"
    ]
    observed = [*paper_lanes, *tiny_lanes]
    lane_config_state = {
        lane["lane_key"]: {
            "mode": lane["mode"],
            "is_paper_observation_lane": lane["mode"] == "paper",
            "is_tiny_live_target": lane["lane_key"] in set(TARGET_TINY_LIVE_LANES),
        }
        for lane in sorted(observed, key=lambda item: item["lane_key"])
    }
    return {
        "paper_lanes": sorted(paper_lanes, key=lambda item: item["lane_key"]),
        "tiny_live_lanes_observed_but_not_changed": sorted(tiny_lanes, key=lambda item: item["lane_key"]),
        "lane_config_state": lane_config_state,
        "expanded_scope": {
            "paper_lanes": sorted(paper_lanes, key=lambda item: item["lane_key"]),
            "tiny_live_lanes_observed_but_not_changed": sorted(tiny_lanes, key=lambda item: item["lane_key"]),
            "directions_covered": sorted({lane["direction"] for lane in observed if lane.get("direction")}),
            "timeframes_covered": _ordered_timeframes([lane["timeframe"] for lane in observed]),
        },
    }


def build_expanded_paper_distribution(
    *,
    log_dir: str | Path | None = None,
    paper_lanes: list[Mapping[str, Any]] | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_scans: int = DEFAULT_LATEST_SCANS,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    bounded_signals = _bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS)
    bounded_scans = _bounded_int(latest_scans, 1, MAX_LATEST_SCANS, DEFAULT_LATEST_SCANS)
    signal_records = read_recent_ndjson_records(resolved_log_dir / "signals.ndjson", limit=bounded_signals, max_bytes=16_777_216)
    scan_records = read_recent_ndjson_records(
        resolved_log_dir / "multi_symbol_paper_scans.ndjson",
        limit=bounded_scans,
        max_bytes=32_000_000,
    )
    rows = [
        *[_candidate_row(record, "signals.ndjson", generated_at) for record in signal_records],
        *[_candidate_row(record, "multi_symbol_paper_scans.ndjson", generated_at) for record in scan_records],
    ]
    rows = [row for row in rows if row["symbol"] == TARGET_SYMBOL and row["timeframe"] and row["direction"]]
    lane_map = {str(lane.get("lane_key") or _lane_key(lane)): _compact_lane(lane) for lane in paper_lanes or []}
    fresh_by_lane: Counter[str] = Counter()
    stale_by_lane: Counter[str] = Counter()
    by_tf_dir: Counter[str] = Counter()
    candidates_by_lane: dict[str, list[dict[str, Any]]] = {key: [] for key in lane_map}

    for row in rows:
        by_tf_dir[f"{row['timeframe']}|{row['direction']}"] += 1
        lane_key = normalize_lane_key(row["symbol"], row["timeframe"], row["direction"], row["entry_mode"] or TARGET_ENTRY_MODE)
        lane = lane_map.get(lane_key)
        if not lane:
            continue
        candidate = _candidate_for_lane(row, lane, generated_at)
        if len(candidates_by_lane[lane_key]) < 20:
            candidates_by_lane[lane_key].append(candidate)
        if candidate["fresh"]:
            fresh_by_lane[lane_key] += 1
        else:
            stale_by_lane[lane_key] += 1

    return {
        "generated_at": generated_at.isoformat(),
        "latest_signals_checked": len(signal_records),
        "latest_scans_checked": len(scan_records),
        "by_timeframe_direction": dict(sorted(by_tf_dir.items(), key=lambda item: _timeframe_direction_sort_key(item[0]))),
        "fresh_by_lane": dict(sorted(fresh_by_lane.items())),
        "stale_by_lane": dict(sorted(stale_by_lane.items())),
        "top_fresh_lanes": _top_lane_counts(fresh_by_lane),
        "top_stale_lanes": _top_lane_counts(stale_by_lane),
        "paper_lane_candidates": {key: value for key, value in sorted(candidates_by_lane.items()) if value},
        "safety": dict(SAFETY),
    }


def evaluate_expanded_paper_candidates(
    *,
    paper_lanes: list[Mapping[str, Any]],
    candidate_distribution: Mapping[str, Any],
) -> dict[str, Any]:
    lane_map = {str(lane.get("lane_key") or _lane_key(lane)): _compact_lane(lane) for lane in paper_lanes}
    fresh_by_lane = dict(candidate_distribution.get("fresh_by_lane") or {})
    candidates_by_lane = dict(candidate_distribution.get("paper_lane_candidates") or {})
    capture_candidates: list[dict[str, Any]] = []
    for lane_key, count in sorted(fresh_by_lane.items()):
        if int(count or 0) <= 0:
            continue
        lane = lane_map.get(lane_key)
        if not lane:
            continue
        latest = list(candidates_by_lane.get(lane_key) or [])[:3]
        capture_candidates.append(
            {
                "lane_key": lane_key,
                "timeframe": lane["timeframe"],
                "direction": lane["direction"],
                "fresh_candidates": int(count),
                "latest_candidates": latest,
            }
        )
    short_count = sum(item["fresh_candidates"] for item in capture_candidates if item["direction"] == "short")
    long_count = sum(item["fresh_candidates"] for item in capture_candidates if item["direction"] == "long")
    return {
        "fresh_paper_candidates_count": sum(item["fresh_candidates"] for item in capture_candidates),
        "paper_capture_candidates": capture_candidates,
        "short_paper_candidates_count": short_count,
        "long_paper_candidates_count": long_count,
        "best_next_paper_lane_family": _best_lane_family(capture_candidates),
    }


def build_expanded_paper_safe_watch_command(*, record: bool = False) -> str:
    command = (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward expanded-paper-watch "
        "--latest-signals 1000 --latest-scans 2000 --all-paper-lanes "
        "--include-tiny-live-targets-as-observed"
    )
    if record:
        command += (
            " --record-watch --confirm-expanded-paper-watch "
            '"I CONFIRM EXPANDED PAPER WATCH RECORDING ONLY; NO LIVE LANES; NO ORDER; NO BINANCE CALL."'
        )
    return command


def append_expanded_paper_watch_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = expanded_paper_watch_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "watch_id": record.get("watch_id") or f"expanded_paper_watch_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "record_watch_requested": bool(record.get("record_watch_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "expanded_scope": dict(record.get("expanded_scope") or {}),
            "lane_config_state": dict(record.get("lane_config_state") or {}),
            "candidate_distribution": dict(record.get("candidate_distribution") or {}),
            "paper_opportunity_summary": dict(record.get("paper_opportunity_summary") or {}),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_expanded_paper_watch_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = expanded_paper_watch_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records = read_recent_ndjson_records(path, limit=limit if limit > 0 else 100000, max_bytes=16_777_216)
    if limit <= 0:
        records = list(reversed(records))
    return [_sanitize(record) for record in records]


def summarize_expanded_paper_watch_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    captured = [
        record
        for record in records
        if int((record.get("paper_opportunity_summary") or {}).get("fresh_paper_candidates_count") or 0) > 0
    ]
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_watch_id": records[0].get("watch_id") if records else None,
        "fresh_candidate_records_count": len(captured),
        "last_best_next_paper_lane_family": (captured[0].get("paper_opportunity_summary") or {}).get("best_next_paper_lane_family")
        if captured
        else None,
        "safety": dict(SAFETY),
    }


def expanded_paper_watch_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_expanded_paper_watch_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _status_for_preview(scope: Mapping[str, Any], opportunity_summary: Mapping[str, Any]) -> str:
    if not scope.get("paper_lanes"):
        return EXPANDED_PAPER_WATCH_BLOCKED
    if int(opportunity_summary.get("fresh_paper_candidates_count") or 0) > 0:
        return EXPANDED_PAPER_WATCH_CAPTURED_PAPER_SIGNAL
    return EXPANDED_PAPER_WATCH_PREVIEW


def _candidate_row(record: Mapping[str, Any], source: str, now: datetime) -> dict[str, Any]:
    raw = dict(record)
    symbol = str(_first_present(raw, "symbol", "base_symbol") or "").strip().upper()
    timeframe = str(_first_present(raw, "timeframe", "tf", "interval") or "").strip().lower()
    direction = str(_first_present(raw, "direction", "bias_direction", "side") or "").strip().lower()
    if direction in {"buy", "bull", "bullish"}:
        direction = "long"
    if direction in {"sell", "bear", "bearish"}:
        direction = "short"
    entry_mode = str(_first_present(raw, "entry_mode", "mode") or TARGET_ENTRY_MODE).strip().lower()
    timestamp = _first_present(raw, "generated_at", "timestamp", "closed_at", "detected_at")
    return {
        "source": source,
        "candidate_id": str(_first_present(raw, "candidate_id", "signal_id", "id") or ""),
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "timestamp": str(timestamp or ""),
        "age_seconds": _age_seconds(timestamp, now),
    }


def _candidate_for_lane(row: Mapping[str, Any], lane: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    age = _age_seconds(row.get("timestamp"), now)
    freshness_seconds = int(lane.get("freshness_seconds") or 0)
    fresh = age is not None and freshness_seconds > 0 and age <= freshness_seconds
    return {
        "candidate_id": row.get("candidate_id") or _fallback_candidate_id(row),
        "source": row.get("source"),
        "timestamp": row.get("timestamp"),
        "age_seconds": age,
        "freshness_seconds": freshness_seconds,
        "fresh": fresh,
    }


def _recommended_next_operator_move(status: str, summary: Mapping[str, Any]) -> str:
    if status == EXPANDED_PAPER_WATCH_REJECTED:
        return "RUN_EXPANDED_PAPER_WATCH"
    if int(summary.get("fresh_paper_candidates_count") or 0) > 0:
        return "RECORD_EXPANDED_PAPER_EVIDENCE"
    if status in {EXPANDED_PAPER_WATCH_RECORDED, EXPANDED_PAPER_WATCH_CAPTURED_PAPER_SIGNAL}:
        return "RUN_R154_PROMOTION_CANDIDATE_AUDIT"
    return "WAIT_FOR_FRESH_PAPER_CANDIDATE"


def _recommended_next_engineering_move(status: str, summary: Mapping[str, Any]) -> str:
    if status == EXPANDED_PAPER_WATCH_BLOCKED:
        return "Verify R152 lane expansion was applied before adding new watcher behavior."
    if int(summary.get("fresh_paper_candidates_count") or 0) > 0:
        return "Prepare R154 promotion candidate audit from expanded paper watch records and outcome stats."
    return "Keep R153 watch surface paper-only and rerun during a fresh expanded-lane signal window."


def _safe_commands() -> list[str]:
    return [
        build_expanded_paper_safe_watch_command(record=False),
        build_expanded_paper_safe_watch_command(record=True),
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward candidate-source-freshness-audit --latest-signals 1000 --latest-scans 2000",
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward paper-opportunity-expansion --latest-signals 1000 --latest-scans 2000 --include-default-expansion",
    ]


def _best_lane_family(candidates: list[Mapping[str, Any]]) -> str:
    if not candidates:
        return "NONE"
    counts: Counter[str] = Counter()
    for item in candidates:
        counts[f"{item.get('timeframe')}|{item.get('direction')}"] += int(item.get("fresh_candidates") or 0)
    return counts.most_common(1)[0][0]


def _top_lane_counts(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"lane_key": lane_key, "count": int(count)}
        for lane_key, count in sorted(counter.items(), key=lambda item: (-int(item[1]), item[0]))[:10]
    ]


def _compact_lane(lane: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "lane_key": str(lane.get("lane_key") or _lane_key(lane)),
        "symbol": str(lane.get("symbol") or "").strip().upper(),
        "timeframe": str(lane.get("timeframe") or "").strip().lower(),
        "direction": str(lane.get("direction") or "").strip().lower(),
        "entry_mode": str(lane.get("entry_mode") or TARGET_ENTRY_MODE).strip().lower(),
        "mode": str(lane.get("mode") or "disabled").strip().lower(),
        "max_daily_trades": int(lane.get("max_daily_trades") or 0),
        "max_daily_loss_pct": float(lane.get("max_daily_loss_pct") or 0.0),
        "freshness_seconds": int(lane.get("freshness_seconds") or 0),
        "cooldown_after_loss_minutes": int(lane.get("cooldown_after_loss_minutes") or 0),
        "require_protective_orders": bool(lane.get("require_protective_orders")),
    }


def _lane_key(lane: Mapping[str, Any]) -> str:
    return normalize_lane_key(lane.get("symbol"), lane.get("timeframe"), lane.get("direction"), lane.get("entry_mode"))


def _is_btcusdt_target_entry(lane: Mapping[str, Any]) -> bool:
    return (
        str(lane.get("symbol") or "").strip().upper() == TARGET_SYMBOL
        and str(lane.get("entry_mode") or "").strip().lower() == TARGET_ENTRY_MODE
    )


def _age_seconds(value: object, now: datetime) -> int | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return max(0, int((now - parsed).total_seconds()))


def _parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _fallback_candidate_id(row: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("source") or "candidate"),
            str(row.get("symbol") or ""),
            str(row.get("timeframe") or ""),
            str(row.get("direction") or ""),
            str(row.get("timestamp") or ""),
        ]
    )


def _ordered_timeframes(values: list[str] | tuple[str, ...]) -> list[str]:
    return sorted({str(value or "").strip().lower() for value in values if str(value or "").strip()}, key=_timeframe_sort_key)


def _timeframe_sort_key(value: str) -> tuple[int, str]:
    text = str(value or "").lower()
    digits = "".join(ch for ch in text if ch.isdigit())
    unit = "".join(ch for ch in text if ch.isalpha())
    multiplier = {"m": 1, "h": 60, "d": 1440}.get(unit or "m", 1)
    return (int(digits or 0) * multiplier, text)


def _timeframe_direction_sort_key(value: str) -> tuple[int, str]:
    timeframe = str(value or "").split("|", 1)[0]
    return (*_timeframe_sort_key(timeframe), str(value))


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
