"""R145 entry-mode derivation bridge for watched lane candidates.

This module is a read-path normalization bridge. It never mutates source signal
logs, creates order payloads, calls Binance, signs requests, mutates env files,
or enables live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, load_lane_controls, normalize_lane_key
from src.app.hammer_radar.operator.strategy_performance import PREFERRED_ENTRY_MODE
from src.app.hammer_radar.operator.tiny_live_lane_unlock_contract import build_lane_unlock_contract

ENTRY_MODE_DERIVATION_BRIDGE_PREVIEW = "ENTRY_MODE_DERIVATION_BRIDGE_PREVIEW"
ENTRY_MODE_DERIVATION_BRIDGE_READY = "ENTRY_MODE_DERIVATION_BRIDGE_READY"
ENTRY_MODE_DERIVATION_BRIDGE_REJECTED = "ENTRY_MODE_DERIVATION_BRIDGE_REJECTED"
ENTRY_MODE_DERIVATION_BRIDGE_RECORDED = "ENTRY_MODE_DERIVATION_BRIDGE_RECORDED"
ENTRY_MODE_DERIVATION_BRIDGE_BLOCKED = "ENTRY_MODE_DERIVATION_BRIDGE_BLOCKED"
ENTRY_MODE_DERIVATION_BRIDGE_ERROR = "ENTRY_MODE_DERIVATION_BRIDGE_ERROR"

EVENT_TYPE = "ENTRY_MODE_DERIVATION_BRIDGE"
LEDGER_FILENAME = "entry_mode_derivation_bridge_records.ndjson"
CONFIRM_ENTRY_MODE_DERIVATION_BRIDGE_RECORDING_PHRASE = (
    "I CONFIRM ENTRY MODE DERIVATION BRIDGE RECORDING ONLY; NO ORDER; NO BINANCE CALL."
)
DERIVATION_SOURCE = "R145_ENTRY_MODE_DERIVATION_BRIDGE"
PRIMARY_WATCHED_LANE = "BTCUSDT|13m|long|ladder_close_50_618"
SECONDARY_WATCHED_LANE = "BTCUSDT|44m|long|ladder_close_50_618"
TARGET_WATCHED_LANES = (PRIMARY_WATCHED_LANE, SECONDARY_WATCHED_LANE)
TARGET_SYMBOL = "BTCUSDT"
TARGET_DIRECTION = "long"
TARGET_TIMEFRAMES = {"13m", "44m"}
DEFAULT_LATEST_SIGNALS = 100
MAX_LATEST_SIGNALS = 1000

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
    "logs/hammer_radar_forward/signals.ndjson",
    "operator.tiny_live_lane_unlock_contract.build_lane_unlock_contract(status_only=True)",
    "operator.strategy_performance.PREFERRED_ENTRY_MODE",
    "operator.lane_control.normalize_lane_key",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def derive_entry_mode_for_signal(
    signal: Mapping[str, Any] | object,
    *,
    watched_lanes: list[Mapping[str, Any]] | None = None,
) -> str | None:
    raw = _candidate_mapping(signal)
    existing = _entry_mode(raw)
    if existing:
        return existing
    lane = _matching_watched_lane(raw, watched_lanes or [], exact=False)
    if lane and _lane_is_r145_target(lane):
        return PREFERRED_ENTRY_MODE
    return None


def derive_lane_key_for_signal(
    signal: Mapping[str, Any] | object,
    *,
    watched_lanes: list[Mapping[str, Any]] | None = None,
) -> str | None:
    raw = _candidate_mapping(signal)
    entry_mode = derive_entry_mode_for_signal(raw, watched_lanes=watched_lanes)
    if not entry_mode:
        return None
    return normalize_lane_key(_symbol(raw), _timeframe(raw), _direction(raw), entry_mode)


def normalize_signal_for_watched_lane(
    signal: Mapping[str, Any] | object,
    *,
    watched_lanes: list[Mapping[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    raw = _candidate_mapping(signal)
    raw_entry_mode = _entry_mode(raw)
    after_entry_mode = derive_entry_mode_for_signal(raw, watched_lanes=watched_lanes)
    normalized = dict(raw)
    if after_entry_mode:
        normalized["entry_mode"] = after_entry_mode
    normalized["candidate_id"] = _candidate_id(raw)
    normalized["signal_id"] = _candidate_id(raw)
    normalized["generated_at"] = _timestamp(raw)
    normalized["timestamp"] = _timestamp(raw)
    normalized["before_bridge_entry_mode"] = raw_entry_mode
    normalized["after_bridge_entry_mode"] = after_entry_mode
    normalized["derived_entry_mode"] = raw_entry_mode is None and after_entry_mode == PREFERRED_ENTRY_MODE
    normalized["derivation_source"] = DERIVATION_SOURCE if normalized["derived_entry_mode"] else "signal_record"
    normalized["after_bridge_lane_key"] = derive_lane_key_for_signal(normalized, watched_lanes=watched_lanes)
    normalized["lane_key"] = normalized["after_bridge_lane_key"] or normalized.get("lane_key")
    normalized["bridge_would_match_watched_lane"] = bool(
        normalized["after_bridge_lane_key"]
        and normalized["after_bridge_lane_key"] in {str(lane.get("lane_key") or "") for lane in watched_lanes}
    )
    freshness = _freshness_status(normalized, watched_lanes=watched_lanes, now=now)
    normalized["freshness_status_after_bridge"] = freshness["status"]
    normalized["bridge_would_still_block_reason"] = freshness["blocked_reason"]
    return _sanitize(normalized)


def normalize_candidate_for_unlocked_watched_lanes(
    candidate: Mapping[str, Any] | object,
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    trace_all_unlocked_lanes: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    context = build_watched_lane_context(
        log_dir=log_dir,
        lane_keys=lane_keys,
        lane_keys_csv=lane_keys_csv,
        trace_all_unlocked_lanes=trace_all_unlocked_lanes,
        now=now,
    )
    return normalize_signal_for_watched_lane(
        candidate,
        watched_lanes=list(context["watched_lanes"]),
        now=now,
    )


def normalize_candidates_for_lane_key(
    candidates: list[Mapping[str, Any] | object],
    *,
    lane_key: str,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    watched_lanes = [_lane_spec(lane_key)]
    return [normalize_signal_for_watched_lane(candidate, watched_lanes=watched_lanes, now=now) for candidate in candidates]


def build_watched_lane_context(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    trace_all_unlocked_lanes: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    explicit_keys = _dedupe([*list(lane_keys or []), *_split_lane_keys(lane_keys_csv)])
    unlock_status = build_lane_unlock_contract(log_dir=log_dir, status_only=True, now=now)
    unlocked = [
        _lane_spec(str(lane.get("lane_key") or ""))
        for lane in unlock_status.get("lanes") or []
        if isinstance(lane, Mapping) and str(lane.get("lane_key") or "")
    ]
    if explicit_keys:
        selected = [_lane_spec(key) for key in explicit_keys]
        source = "explicit_lane_keys"
    elif trace_all_unlocked_lanes and unlocked:
        selected = unlocked
        source = "r143_unlock_contract"
    elif unlocked:
        selected = unlocked
        source = "r143_unlock_contract"
    else:
        selected = [_lane_spec(key) for key in TARGET_WATCHED_LANES]
        source = "fallback_r145_target_lanes"
    selected = [lane for lane in selected if _lane_is_r145_target(lane)]
    return {
        "watched_lanes": selected,
        "unlock_contract_status": {
            "status": unlock_status.get("status"),
            "execution_state": unlock_status.get("execution_state"),
            "unlock_contract_id": unlock_status.get("unlock_contract_id"),
            "latest_contract_id": unlock_status.get("latest_contract_id"),
            "source": source,
            "fallback_used": source == "fallback_r145_target_lanes",
            "unlocked_lane_keys": [lane["lane_key"] for lane in unlocked],
        },
    }


def build_entry_mode_derivation_bridge_preview(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    trace_all_unlocked_lanes: bool = False,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    now: datetime | None = None,
) -> dict[str, Any]:
    return build_entry_mode_derivation_bridge_status(
        log_dir=log_dir,
        lane_keys=lane_keys,
        lane_keys_csv=lane_keys_csv,
        trace_all_unlocked_lanes=trace_all_unlocked_lanes,
        latest_signals=latest_signals,
        record_bridge=False,
        confirm_bridge=None,
        now=now,
    )


def build_entry_mode_derivation_bridge_status(
    *,
    log_dir: str | Path | None = None,
    lane_keys: list[str] | None = None,
    lane_keys_csv: str | None = None,
    trace_all_unlocked_lanes: bool = False,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    record_bridge: bool = False,
    confirm_bridge: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    bounded_latest = _bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS)
    confirmation_valid = confirm_bridge == CONFIRM_ENTRY_MODE_DERIVATION_BRIDGE_RECORDING_PHRASE
    try:
        context = build_watched_lane_context(
            log_dir=resolved_log_dir,
            lane_keys=lane_keys,
            lane_keys_csv=lane_keys_csv,
            trace_all_unlocked_lanes=trace_all_unlocked_lanes,
            now=generated_at,
        )
        watched_lanes = list(context["watched_lanes"])
        signals = load_recent_signal_records(log_dir=resolved_log_dir, limit=bounded_latest)
        normalized = [
            normalize_signal_for_watched_lane(signal, watched_lanes=watched_lanes, now=generated_at)
            for signal in signals
        ]
        summary = _recent_signal_bridge_summary(normalized)
        examples = _normalized_examples(normalized)
        status = ENTRY_MODE_DERIVATION_BRIDGE_READY
        bridge_recorded = False
        bridge_id = None
        if record_bridge and not confirmation_valid:
            status = ENTRY_MODE_DERIVATION_BRIDGE_REJECTED
        elif record_bridge:
            status = ENTRY_MODE_DERIVATION_BRIDGE_RECORDED
            bridge_id = f"entry_mode_derivation_bridge_{uuid4().hex}"
            bridge_recorded = True
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "bridge_recorded": bridge_recorded,
            "bridge_id": bridge_id,
            "watched_lanes": watched_lanes,
            "unlock_contract_status": context["unlock_contract_status"],
            "normalization_rules": _normalization_rules(),
            "recent_signal_bridge_summary": summary,
            "normalized_signal_examples": examples,
            "r142_effect_preview": _r142_effect_preview(),
            "best_next_engineering_move": _best_next_engineering_move(summary),
            "recommended_next_commands": _recommended_next_commands(),
            "record_bridge_requested": bool(record_bridge),
            "confirmation_valid": bool(confirmation_valid),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_bridge and confirmation_valid:
            append_entry_mode_derivation_bridge_record(payload, log_dir=resolved_log_dir)
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive diagnostic surface
        return _sanitize(
            {
                "status": ENTRY_MODE_DERIVATION_BRIDGE_ERROR,
                "generated_at": generated_at.isoformat(),
                "bridge_recorded": False,
                "bridge_id": None,
                "watched_lanes": [],
                "unlock_contract_status": {},
                "normalization_rules": _normalization_rules(),
                "recent_signal_bridge_summary": {},
                "normalized_signal_examples": [],
                "r142_effect_preview": _r142_effect_preview(),
                "best_next_engineering_move": "Fix R145 bridge preview error before using watcher integration.",
                "recommended_next_commands": _recommended_next_commands(),
                "record_bridge_requested": bool(record_bridge),
                "confirmation_valid": bool(confirmation_valid),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def append_entry_mode_derivation_bridge_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = entry_mode_derivation_bridge_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "bridge_id": record.get("bridge_id") or f"entry_mode_derivation_bridge_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "watched_lanes": list(record.get("watched_lanes") or []),
            "normalization_rules": dict(record.get("normalization_rules") or {}),
            "recent_signal_bridge_summary": dict(record.get("recent_signal_bridge_summary") or {}),
            "normalized_signal_examples": list(record.get("normalized_signal_examples") or []),
            "r142_effect_preview": dict(record.get("r142_effect_preview") or {}),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_entry_mode_derivation_bridge_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = entry_mode_derivation_bridge_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records = read_recent_ndjson_records(path, limit=limit if limit > 0 else 100_000, max_bytes=16_777_216)
    if limit <= 0:
        records = list(reversed(records))
    return [_sanitize(record) for record in records]


def summarize_entry_mode_derivation_bridge_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "last_bridge_id": records[0].get("bridge_id") if records else None,
        "safety": dict(SAFETY),
    }


def entry_mode_derivation_bridge_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def load_recent_signal_records(*, log_dir: str | Path | None = None, limit: int = DEFAULT_LATEST_SIGNALS) -> list[dict[str, Any]]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    records = read_recent_ndjson_records(
        resolved_log_dir / "signals.ndjson",
        limit=_bounded_int(limit, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS),
        max_bytes=2_097_152,
    )
    return [_sanitize(_candidate_mapping(record)) for record in records]


def format_entry_mode_derivation_bridge_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _recent_signal_bridge_summary(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "signals_checked": len(rows),
        "would_normalize_count": sum(1 for row in rows if row.get("derived_entry_mode")),
        "would_match_watched_lane_count": sum(1 for row in rows if row.get("bridge_would_match_watched_lane")),
        "would_remain_stale_count": sum(1 for row in rows if row.get("bridge_would_still_block_reason") == "candidate is stale"),
        "not_watched_count": sum(1 for row in rows if not row.get("bridge_would_match_watched_lane")),
    }


def _normalized_examples(rows: list[Mapping[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("bridge_would_match_watched_lane") and not row.get("derived_entry_mode"):
            continue
        examples.append(
            {
                "signal_id": row.get("signal_id") or row.get("candidate_id"),
                "raw_entry_mode": row.get("before_bridge_entry_mode"),
                "derived_entry_mode": row.get("after_bridge_entry_mode") if row.get("derived_entry_mode") else None,
                "derived_lane_key": row.get("after_bridge_lane_key"),
                "would_match_watched_lane": bool(row.get("bridge_would_match_watched_lane")),
                "freshness_status_after_bridge": row.get("freshness_status_after_bridge"),
                "paper_eligible_after_bridge": None,
                "blocked_reason_after_bridge": row.get("bridge_would_still_block_reason"),
            }
        )
        if len(examples) >= limit:
            break
    return examples


def _normalization_rules() -> dict[str, Any]:
    return {
        "runtime_read_path_only": True,
        "mutates_signal_logs": False,
        "symbol": TARGET_SYMBOL,
        "timeframes": sorted(TARGET_TIMEFRAMES),
        "direction": TARGET_DIRECTION,
        "entry_mode_if_missing": PREFERRED_ENTRY_MODE,
        "requires_unlocked_or_explicit_lane": True,
        "preserves_existing_entry_mode": True,
        "does_not_bypass_freshness": True,
        "does_not_create_paper_proof": True,
        "does_not_authorize_live_execution": True,
    }


def _r142_effect_preview() -> dict[str, Any]:
    return {
        "expected_change": "fresh signals can be evaluated against watched lane keys",
        "does_not_force_paper_proof": True,
        "does_not_bypass_freshness": True,
    }


def _best_next_engineering_move(summary: Mapping[str, int]) -> str:
    if int(summary.get("would_normalize_count") or 0) > 0:
        return "Run R142 watcher during the next fresh BTCUSDT 13m/44m long signal window."
    return "Wait for a watched BTCUSDT 13m/44m long signal or inspect R144 trace gaps."


def _recommended_next_commands() -> list[str]:
    return [
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward entry-mode-derivation-bridge --trace-all-unlocked-lanes",
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward signal-to-watcher-eligibility-trace --trace-all-unlocked-lanes",
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward fresh-candidate-paper-proof-capture-loop --watch-all-recommended-lanes",
    ]


def _freshness_status(
    row: Mapping[str, Any],
    *,
    watched_lanes: list[Mapping[str, Any]],
    now: datetime | None,
) -> dict[str, str | None]:
    lane_key = str(row.get("after_bridge_lane_key") or "")
    lane = next((item for item in watched_lanes if item.get("lane_key") == lane_key), None)
    if not lane:
        return {"status": "UNKNOWN", "blocked_reason": "not watched"}
    freshness_seconds = _lane_freshness_seconds(lane)
    if str(row.get("freshness_status") or "").strip().lower() == "expired":
        return {"status": "STALE", "blocked_reason": "candidate is stale"}
    age = _candidate_age_seconds(_timestamp(row), now or datetime.now(UTC))
    if age is None or freshness_seconds is None or freshness_seconds <= 0:
        return {"status": "UNKNOWN", "blocked_reason": "freshness unknown"}
    if age > freshness_seconds:
        return {"status": "STALE", "blocked_reason": "candidate is stale"}
    return {"status": "FRESH", "blocked_reason": None}


def _lane_freshness_seconds(lane: Mapping[str, Any]) -> int | None:
    value = lane.get("freshness_seconds")
    if value not in (None, ""):
        return _int_or_none(value)
    try:
        controls = load_lane_controls()
    except Exception:
        return None
    configured = (controls.get("lane_map") or {}).get(str(lane.get("lane_key") or ""))
    return _int_or_none((configured or {}).get("freshness_seconds"))


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


def _matching_watched_lane(row: Mapping[str, Any], watched_lanes: list[Mapping[str, Any]], *, exact: bool) -> dict[str, Any] | None:
    for lane in watched_lanes:
        if lane.get("symbol") != _symbol(row):
            continue
        if lane.get("timeframe") != _timeframe(row):
            continue
        if lane.get("direction") != _direction(row):
            continue
        if exact and lane.get("entry_mode") != _entry_mode(row):
            continue
        return dict(lane)
    return None


def _lane_is_r145_target(lane: Mapping[str, Any]) -> bool:
    return (
        str(lane.get("symbol") or "").strip().upper() == TARGET_SYMBOL
        and str(lane.get("timeframe") or "").strip().lower() in TARGET_TIMEFRAMES
        and str(lane.get("direction") or "").strip().lower() == TARGET_DIRECTION
        and str(lane.get("entry_mode") or "").strip().lower() == PREFERRED_ENTRY_MODE
        and str(lane.get("lane_key") or "") in TARGET_WATCHED_LANES
    )


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
            "entry",
            "entry_price",
            "fib_618",
            "stop",
            "stop_price",
            "take_profit",
            "take_profit_price",
        )
        if hasattr(candidate, key)
    }


def _lane_spec(lane_key: str) -> dict[str, Any]:
    parts = [*str(lane_key or "").split("|"), "", "", "", ""][:4]
    return {
        "lane_key": normalize_lane_key(parts[0], parts[1], parts[2], parts[3]),
        "symbol": str(parts[0] or "").strip().upper(),
        "timeframe": str(parts[1] or "").strip().lower(),
        "direction": str(parts[2] or "").strip().lower(),
        "entry_mode": str(parts[3] or "").strip().lower(),
    }


def _symbol(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol") or "").strip().upper()


def _timeframe(row: Mapping[str, Any]) -> str:
    return str(row.get("timeframe") or "").strip().lower()


def _direction(row: Mapping[str, Any]) -> str:
    return str(row.get("direction") or row.get("latest_direction") or "").strip().lower()


def _entry_mode(row: Mapping[str, Any]) -> str | None:
    value = row.get("entry_mode")
    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    return text or None


def _timestamp(row: Mapping[str, Any]) -> str | None:
    value = row.get("generated_at") or row.get("timestamp") or row.get("closed_at") or row.get("detected_at")
    return str(value) if value not in (None, "") else None


def _candidate_id(row: Mapping[str, Any]) -> str:
    value = row.get("candidate_id") or row.get("signal_id")
    if value not in (None, ""):
        return str(value)
    return "|".join(part for part in (_symbol(row), _timeframe(row), _direction(row), str(_timestamp(row) or "")) if part)


def _split_lane_keys(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _bounded_int(value: int, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value
