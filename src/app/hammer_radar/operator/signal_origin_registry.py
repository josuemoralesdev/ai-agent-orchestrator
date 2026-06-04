"""R182 paper-only signal origin registry and feed summary.

This module classifies local paper signal records by signal origin. It never
calls Binance, creates order payloads, mutates env/config, changes lane modes,
promotes origins, or authorizes live execution.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir, get_signals_path
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, normalize_lane_key
from src.app.hammer_radar.operator.multi_lane_paper_capture_harvester import (
    LEDGER_FILENAME as MULTI_LANE_HARVESTER_LEDGER_FILENAME,
)
from src.app.hammer_radar.operator.strategy_performance import PREFERRED_ENTRY_MODE

SIGNAL_ORIGIN_REGISTRY_READY = "SIGNAL_ORIGIN_REGISTRY_READY"
SIGNAL_ORIGIN_REGISTRY_REJECTED = "SIGNAL_ORIGIN_REGISTRY_REJECTED"
SIGNAL_ORIGIN_REGISTRY_RECORDED = "SIGNAL_ORIGIN_REGISTRY_RECORDED"
SIGNAL_ORIGIN_REGISTRY_BLOCKED = "SIGNAL_ORIGIN_REGISTRY_BLOCKED"
SIGNAL_ORIGIN_REGISTRY_ERROR = "SIGNAL_ORIGIN_REGISTRY_ERROR"

DETECTOR_AVAILABLE = "DETECTOR_AVAILABLE"
REGISTRY_ONLY = "REGISTRY_ONLY"
INFERRED_FROM_EXISTING_FIELDS = "INFERRED_FROM_EXISTING_FIELDS"
UNKNOWN = "UNKNOWN"

EVENT_TYPE = "SIGNAL_ORIGIN_REGISTRY"
LEDGER_FILENAME = "signal_origin_registry.ndjson"
CONFIRM_SIGNAL_ORIGIN_REGISTRY_RECORDING_PHRASE = (
    "I CONFIRM SIGNAL ORIGIN REGISTRY RECORDING ONLY; NO CONFIG WRITE; NO ORDER; NO BINANCE CALL."
)

DEFAULT_LATEST_SIGNALS = 1000
DEFAULT_LATEST_HARVEST_RECORDS = 500
MAX_LATEST_SIGNALS = 20000
MAX_LATEST_HARVEST_RECORDS = 50000

UNKNOWN_ORIGIN = "unknown_or_unclassified"

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_config_written": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "global_live_flags_changed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
    "live_authorization_created": False,
    "signal_origin_promoted": False,
}

SOURCE_SURFACES_USED = [
    "logs/hammer_radar_forward/signals.ndjson",
    "logs/hammer_radar_forward/multi_symbol_paper_scans.ndjson",
    f"logs/hammer_radar_forward/{MULTI_LANE_HARVESTER_LEDGER_FILENAME}",
    "operator.lane_control.normalize_lane_key",
    "operator.strategy_performance.PREFERRED_ENTRY_MODE",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_signal_origin_registry() -> list[dict[str, Any]]:
    entries = [
        _entry(
            "hammer_wick_reversal",
            aliases=["hammer", "wick_reversal", "long_wick_rejection"],
            origin_type="reversal/rejection",
            direction_support=["long", "short"],
            availability=DETECTOR_AVAILABLE,
            description="Existing hammer and wick rejection fields can identify this origin.",
        ),
        _entry(
            "golden_pocket_rejection",
            aliases=["golden_pocket", "gp_rejection", "ladder_close_50_618"],
            origin_type="retrace/rejection",
            direction_support=["long", "short"],
            availability=INFERRED_FROM_EXISTING_FIELDS,
            description="Existing ladder_close_50_618 entry-mode records can be tagged as golden-pocket rejection context.",
        ),
        _entry(
            "three_black_crows",
            aliases=["3_black_crows", "three_bearish_candles"],
            origin_type="bearish reversal/bearish continuation",
            direction_support=["short"],
            availability=REGISTRY_ONLY,
            available_for_tagging=False,
            description="Registry-only bearish candle-pattern family until a detector is added.",
        ),
        _entry(
            "three_white_soldiers",
            aliases=["3_white_soldiers", "three_bullish_candles"],
            origin_type="bullish reversal/bullish continuation",
            direction_support=["long"],
            availability=REGISTRY_ONLY,
            available_for_tagging=False,
            description="Registry-only bullish candle-pattern family until a detector is added.",
        ),
        _entry(
            "bearish_engulfing",
            aliases=["engulfing_bearish"],
            origin_type="bearish reversal",
            direction_support=["short"],
            availability=REGISTRY_ONLY,
            available_for_tagging=False,
            description="Registry-only bearish engulfing family until a detector is added.",
        ),
        _entry(
            "bullish_engulfing",
            aliases=["engulfing_bullish"],
            origin_type="bullish reversal",
            direction_support=["long"],
            availability=REGISTRY_ONLY,
            available_for_tagging=False,
            description="Registry-only bullish engulfing family until a detector is added.",
        ),
        _entry(
            "rsi_divergence_bearish",
            aliases=["bearish_divergence", "rsi_bear_div"],
            origin_type="momentum divergence",
            direction_support=["short"],
            availability=INFERRED_FROM_EXISTING_FIELDS,
            description="Existing RSI divergence metadata can tag confirmed bearish divergence records.",
        ),
        _entry(
            "rsi_divergence_bullish",
            aliases=["bullish_divergence", "rsi_bull_div"],
            origin_type="momentum divergence",
            direction_support=["long"],
            availability=INFERRED_FROM_EXISTING_FIELDS,
            description="Existing RSI divergence metadata can tag confirmed bullish divergence records.",
        ),
        _entry(
            "breakdown_retest",
            aliases=["breakdown_retest_short", "support_break_retest"],
            origin_type="continuation/confirmation",
            direction_support=["short"],
            availability=REGISTRY_ONLY,
            available_for_tagging=False,
            description="Registry-only continuation family until a retest detector is added.",
        ),
        _entry(
            "breakout_retest",
            aliases=["breakout_retest_long", "resistance_break_retest"],
            origin_type="continuation/confirmation",
            direction_support=["long"],
            availability=REGISTRY_ONLY,
            available_for_tagging=False,
            description="Registry-only continuation family until a retest detector is added.",
        ),
        _entry(
            "exhaustion_wick",
            aliases=["exhaustion", "terminal_wick"],
            origin_type="exhaustion/reversal",
            direction_support=["long", "short"],
            availability=REGISTRY_ONLY,
            available_for_tagging=False,
            description="Registry-only exhaustion wick family until explicit wick-location detection is added.",
        ),
        _entry(
            UNKNOWN_ORIGIN,
            aliases=["unknown", "unclassified"],
            origin_type="fallback",
            direction_support=["long", "short", "unknown"],
            availability=UNKNOWN,
            description="Fallback origin when current fields do not support a confident origin tag.",
        ),
    ]
    return entries


def normalize_signal_origin(value: object) -> str:
    normalized = _normalize_token(value)
    if not normalized:
        return UNKNOWN_ORIGIN
    aliases: dict[str, str] = {}
    for entry in build_signal_origin_registry():
        origin = str(entry["signal_origin"])
        aliases[origin] = origin
        for alias in entry.get("aliases") or []:
            aliases[_normalize_token(alias)] = origin
    return aliases.get(normalized, UNKNOWN_ORIGIN)


def infer_signal_origin_from_record(record: Mapping[str, Any] | object) -> str:
    raw = _record_mapping(record)
    explicit = _first_present(raw, "signal_origin", "origin", "pattern_family", "pattern", "setup_origin", "setup_type")
    explicit_origin = normalize_signal_origin(explicit)
    if explicit_origin != UNKNOWN_ORIGIN:
        return explicit_origin

    divergence_type = _divergence_type(raw)
    if _truthy(_first_present(raw, "divergence_confirmed", "rsi_divergence_confirmed")) and divergence_type:
        if divergence_type == "bearish":
            return "rsi_divergence_bearish"
        if divergence_type == "bullish":
            return "rsi_divergence_bullish"

    entry_mode = _explicit_entry_mode(raw)
    lane_key = str(raw.get("lane_key") or raw.get("after_bridge_lane_key") or "").strip().lower()
    if normalize_signal_origin(entry_mode) == "golden_pocket_rejection" or "ladder_close_50_618" in lane_key:
        return "golden_pocket_rejection"

    if _has_hammer_wick_fields(raw):
        return "hammer_wick_reversal"

    reject_reason = _normalize_token(_first_present(raw, "reject_reason", "reason"))
    if "wick" in reject_reason or "hammer" in reject_reason:
        return "hammer_wick_reversal"

    return UNKNOWN_ORIGIN


def tag_signal_records_with_origin(records: list[Mapping[str, Any] | object]) -> list[dict[str, Any]]:
    tagged = []
    for record in records:
        raw = _record_mapping(record)
        origin = infer_signal_origin_from_record(raw)
        tagged.append(
            _sanitize(
                {
                    **raw,
                    "signal_origin": origin,
                    "signal_origin_availability": _availability_for_origin(origin),
                    "signal_origin_live_authorized": False,
                    "signal_origin_paper_only": True,
                }
            )
        )
    return tagged


def build_signal_origin_feed_summary(
    records: list[Mapping[str, Any] | object],
    *,
    registry: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    registry_entries = list(registry or build_signal_origin_registry())
    origin_order = [str(entry.get("signal_origin") or UNKNOWN_ORIGIN) for entry in registry_entries]
    tagged = tag_signal_records_with_origin(records)
    by_origin: Counter[str] = Counter()
    by_lane_and_origin: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in tagged:
        origin = str(record.get("signal_origin") or UNKNOWN_ORIGIN)
        lane_key = _lane_key(record)
        by_origin[origin] += 1
        if lane_key:
            by_lane_and_origin[lane_key][origin] += 1
        if len(examples[origin]) < 5:
            examples[origin].append(_compact_record(record, lane_key=lane_key))
    complete_by_origin = {origin: int(by_origin.get(origin, 0)) for origin in origin_order}
    return {
        "records_checked": len(records),
        "records_tagged": len(tagged),
        "by_origin": complete_by_origin,
        "by_lane_and_origin": {
            lane_key: {origin: int(counts.get(origin, 0)) for origin in origin_order if int(counts.get(origin, 0)) > 0}
            for lane_key, counts in sorted(by_lane_and_origin.items())
        },
        "examples_by_origin": {origin: rows for origin, rows in sorted(examples.items())},
    }


def build_signal_origin_registry_preview(
    *,
    log_dir: str | Path | None = None,
    latest_signals: int = DEFAULT_LATEST_SIGNALS,
    latest_harvest_records: int = DEFAULT_LATEST_HARVEST_RECORDS,
    record_registry: bool = False,
    confirm_signal_origin_registry: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_signal_origin_registry == CONFIRM_SIGNAL_ORIGIN_REGISTRY_RECORDING_PHRASE
    try:
        registry = build_signal_origin_registry()
        records = _load_feed_records(
            log_dir=resolved_log_dir,
            latest_signals=latest_signals,
            latest_harvest_records=latest_harvest_records,
        )
        feed_summary = build_signal_origin_feed_summary(records, registry=registry)
        status = SIGNAL_ORIGIN_REGISTRY_READY if registry else SIGNAL_ORIGIN_REGISTRY_BLOCKED
        if record_registry and not confirmation_valid:
            status = SIGNAL_ORIGIN_REGISTRY_REJECTED
        elif record_registry and confirmation_valid:
            status = SIGNAL_ORIGIN_REGISTRY_RECORDED
        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "registry_recorded": False,
            "registry_id": None,
            "record_registry_requested": bool(record_registry),
            "confirmation_valid": bool(confirmation_valid),
            "registry": registry,
            "feed_summary": feed_summary,
            "origin_gaps": _origin_gaps(registry),
            "recommended_next_operator_move": _recommended_next_operator_move(feed_summary),
            "recommended_next_engineering_move": _recommended_next_engineering_move(feed_summary),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_registry and confirmation_valid:
            record = append_signal_origin_registry_record(payload, log_dir=resolved_log_dir)
            payload["registry_recorded"] = True
            payload["registry_id"] = record["registry_id"]
            payload["ledger_path"] = str(signal_origin_registry_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": SIGNAL_ORIGIN_REGISTRY_ERROR,
                "generated_at": generated_at.isoformat(),
                "registry_recorded": False,
                "registry_id": None,
                "record_registry_requested": bool(record_registry),
                "confirmation_valid": bool(confirmation_valid),
                "registry": build_signal_origin_registry(),
                "feed_summary": {
                    "records_checked": 0,
                    "records_tagged": 0,
                    "by_origin": {},
                    "by_lane_and_origin": {},
                    "examples_by_origin": {},
                },
                "origin_gaps": _origin_gaps(build_signal_origin_registry()),
                "recommended_next_operator_move": "KEEP_MULTI_LANE_HARVESTER_RUNNING",
                "recommended_next_engineering_move": "Fix R182 registry preview error and rerun preview only.",
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def append_signal_origin_registry_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    path = signal_origin_registry_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "registry_id": str(record.get("registry_id") or f"r182_signal_origin_registry_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_registry_requested": bool(record.get("record_registry_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "registry": list(record.get("registry") or []),
            "feed_summary": dict(record.get("feed_summary") or {}),
            "origin_gaps": list(record.get("origin_gaps") or []),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "do_not_run_yet": list(record.get("do_not_run_yet") or _do_not_run_yet()),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_signal_origin_registry_records(*, log_dir: str | Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = signal_origin_registry_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def summarize_signal_origin_registry_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    origin_counts: Counter[str] = Counter()
    for record in records:
        for origin, count in ((record.get("feed_summary") or {}).get("by_origin") or {}).items():
            origin_counts[str(origin)] += int(count or 0)
    return {
        "records": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "origin_counts": dict(sorted(origin_counts.items())),
        "latest_registry_id": str(records[-1].get("registry_id") or "") if records else None,
    }


def signal_origin_registry_records_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / LEDGER_FILENAME


def format_signal_origin_registry_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _entry(
    signal_origin: str,
    *,
    aliases: list[str],
    origin_type: str,
    direction_support: list[str],
    availability: str,
    description: str,
    available_for_tagging: bool = True,
) -> dict[str, Any]:
    return {
        "signal_origin": signal_origin,
        "aliases": aliases,
        "origin_type": origin_type,
        "direction_support": direction_support,
        "availability": availability,
        "available_for_tagging": bool(available_for_tagging),
        "description": description,
        "live_authorized": False,
        "paper_only": True,
    }


def _load_feed_records(
    *,
    log_dir: Path,
    latest_signals: int,
    latest_harvest_records: int,
) -> list[dict[str, Any]]:
    bounded_signals = _bounded_int(latest_signals, 1, MAX_LATEST_SIGNALS, DEFAULT_LATEST_SIGNALS)
    bounded_harvest = _bounded_int(latest_harvest_records, 0, MAX_LATEST_HARVEST_RECORDS, DEFAULT_LATEST_HARVEST_RECORDS)
    signal_records = [
        _source_record(record, source="signals.ndjson")
        for record in read_recent_ndjson_records(get_signals_path(log_dir), limit=bounded_signals, max_bytes=16_777_216)
    ]
    scan_records = [
        _source_record(record, source="multi_symbol_paper_scans.ndjson")
        for record in read_recent_ndjson_records(log_dir / "multi_symbol_paper_scans.ndjson", limit=bounded_signals, max_bytes=32_000_000)
    ]
    harvest_records: list[dict[str, Any]] = []
    if bounded_harvest > 0:
        for record in read_recent_ndjson_records(log_dir / MULTI_LANE_HARVESTER_LEDGER_FILENAME, limit=bounded_harvest, max_bytes=32_000_000):
            for candidate in (record.get("captured_candidates") or (record.get("capture_summary") or {}).get("captured_candidates") or []):
                if isinstance(candidate, Mapping):
                    harvest_records.append(_source_record(candidate, source=MULTI_LANE_HARVESTER_LEDGER_FILENAME))
    return [*signal_records, *scan_records, *harvest_records]


def _source_record(record: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    raw = dict(record)
    raw["source"] = source
    return raw


def _availability_for_origin(origin: str) -> str:
    for entry in build_signal_origin_registry():
        if entry["signal_origin"] == origin:
            return str(entry["availability"])
    return UNKNOWN


def _origin_gaps(registry: list[Mapping[str, Any]]) -> list[str]:
    gaps = []
    for entry in registry:
        if entry.get("availability") == REGISTRY_ONLY:
            origin = str(entry.get("signal_origin") or UNKNOWN_ORIGIN)
            if origin == "three_black_crows":
                gaps.append("three_black_crows is registry-only until detector is added")
            elif origin in {"bearish_engulfing", "bullish_engulfing"}:
                continue
            else:
                gaps.append(f"{origin} is registry-only until detector is added")
    gaps.append("engulfing patterns are registry-only until detector is added")
    return _dedupe(gaps)


def _recommended_next_operator_move(feed_summary: Mapping[str, Any]) -> str:
    by_origin = feed_summary.get("by_origin") or {}
    if int(by_origin.get("unknown_or_unclassified") or 0) >= int(feed_summary.get("records_checked") or 0):
        return "KEEP_MULTI_LANE_HARVESTER_RUNNING"
    if int(by_origin.get("three_black_crows") or 0) > 0:
        return "RUN_R183_KETER_SIGNAL_ORIGIN_SCORING"
    return "RUN_R183_KETER_SIGNAL_ORIGIN_SCORING"


def _recommended_next_engineering_move(feed_summary: Mapping[str, Any]) -> str:
    by_origin = feed_summary.get("by_origin") or {}
    if int(by_origin.get("unknown_or_unclassified") or 0) > 0:
        return "Add R183 Keter signal-origin scoring, then consider detector phases for registry-only pattern families."
    return "Add R183 Keter signal-origin scoring over tagged paper origins before any detector or promotion phase."


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set any lane tiny_live",
        "write risk contract config",
        "transfer",
        "withdraw",
    ]


def _record_mapping(record: Mapping[str, Any] | object) -> dict[str, Any]:
    if isinstance(record, Mapping):
        return dict(record)
    if is_dataclass(record):
        return asdict(record)
    if hasattr(record, "to_dict"):
        value = record.to_dict()
        if isinstance(value, Mapping):
            return dict(value)
    return {key: getattr(record, key) for key in dir(record) if not key.startswith("_") and not callable(getattr(record, key))}


def _lane_key(record: Mapping[str, Any]) -> str:
    existing = str(record.get("lane_key") or record.get("after_bridge_lane_key") or "").strip()
    if existing:
        return existing
    return normalize_lane_key(_symbol(record), _timeframe(record), _direction(record), _entry_mode(record))


def _compact_record(record: Mapping[str, Any], *, lane_key: str) -> dict[str, Any]:
    return {
        "signal_id": str(_first_present(record, "signal_id", "candidate_id", "id") or ""),
        "source": str(record.get("source") or ""),
        "lane_key": lane_key,
        "symbol": _symbol(record),
        "timeframe": _timeframe(record),
        "direction": _direction(record),
        "entry_mode": _entry_mode(record),
        "signal_origin": str(record.get("signal_origin") or UNKNOWN_ORIGIN),
    }


def _symbol(record: Mapping[str, Any]) -> str:
    return str(_first_present(record, "symbol", "base_symbol") or "").strip().upper()


def _timeframe(record: Mapping[str, Any]) -> str:
    return str(_first_present(record, "timeframe", "tf", "interval") or "").strip().lower()


def _direction(record: Mapping[str, Any]) -> str:
    direction = str(_first_present(record, "direction", "bias_direction", "side") or "").strip().lower()
    if direction in {"buy", "bull", "bullish"}:
        return "long"
    if direction in {"sell", "bear", "bearish"}:
        return "short"
    return direction


def _entry_mode(record: Mapping[str, Any]) -> str:
    return str(_first_present(record, "entry_mode", "mode") or PREFERRED_ENTRY_MODE).strip().lower()


def _explicit_entry_mode(record: Mapping[str, Any]) -> str:
    return str(_first_present(record, "entry_mode", "mode") or "").strip().lower()


def _divergence_type(record: Mapping[str, Any]) -> str:
    explicit = str(_first_present(record, "divergence_type", "rsi_divergence_type") or "").strip().lower()
    if explicit:
        return explicit
    nested = record.get("divergence")
    if isinstance(nested, Mapping):
        return str(nested.get("type") or "").strip().lower()
    return ""


def _has_hammer_wick_fields(record: Mapping[str, Any]) -> bool:
    if _positive_number(_first_present(record, "hammer_strength", "wick_strength", "wick_rejection_strength")):
        return True
    if any(key in record for key in ("hammer_high", "hammer_low", "wick_high", "wick_low")):
        return True
    return _truthy(_first_present(record, "hammer_detected", "wick_rejection", "long_wick_rejection"))


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record.get(key) not in (None, ""):
            return record.get(key)
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "confirmed"}
    return bool(value)


def _positive_number(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _normalize_token(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_").replace("/", "_")


def _bounded_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
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
