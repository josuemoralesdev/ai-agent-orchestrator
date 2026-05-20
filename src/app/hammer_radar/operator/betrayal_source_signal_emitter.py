"""R100 source signal emitter for betrayal paper detector wiring.

This module emits local, review-only betrayal paper signal rows from trusted
local paper archives into an explicit-entry detector source file. It never
creates closed outcomes, order payloads, Binance requests, account checks, env
mutations, risk contracts, or live readiness.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_detector_source_wiring import build_betrayal_detector_source_wiring
from src.app.hammer_radar.operator.betrayal_true_paper_tracking import build_betrayal_true_paper_scaffold

PHASE = "R100"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "BETRAYAL_SOURCE_SIGNAL_EMITTER_ONLY_NO_ORDER"
OUTPUT_FILENAME = "betrayal_paper_signals.ndjson"
REPORT_FILENAME = "betrayal_source_signal_emitter_report.json"

BETRAYAL_SOURCE_SIGNAL_EMITTER_ONLY = "BETRAYAL_SOURCE_SIGNAL_EMITTER_ONLY"
BETRAYAL_SIGNAL_EMITTER_READY = "BETRAYAL_SIGNAL_EMITTER_READY"
BETRAYAL_SCAFFOLD_IDENTITIES_FOUND = "BETRAYAL_SCAFFOLD_IDENTITIES_FOUND"
BETRAYAL_USABLE_SOURCE_FOUND = "BETRAYAL_USABLE_SOURCE_FOUND"
BETRAYAL_EXPLICIT_ENTRY_SIGNALS_PREPARED = "BETRAYAL_EXPLICIT_ENTRY_SIGNALS_PREPARED"
BETRAYAL_NO_EMITTABLE_SIGNALS_FOUND = "BETRAYAL_NO_EMITTABLE_SIGNALS_FOUND"
BETRAYAL_SIGNAL_EMIT_DRY_RUN_ONLY = "BETRAYAL_SIGNAL_EMIT_DRY_RUN_ONLY"
BETRAYAL_SIGNAL_EMITTED_LOCAL_ONLY = "BETRAYAL_SIGNAL_EMITTED_LOCAL_ONLY"
BETRAYAL_DUPLICATE_EMISSION_SKIPPED = "BETRAYAL_DUPLICATE_EMISSION_SKIPPED"
BETRAYAL_AGGREGATE_SKIPPED_DECOMPOSITION_REQUIRED = "BETRAYAL_AGGREGATE_SKIPPED_DECOMPOSITION_REQUIRED"
BETRAYAL_NOT_LIVE_READY = "BETRAYAL_NOT_LIVE_READY"
BETRAYAL_NON_EXECUTABLE_ONLY = "BETRAYAL_NON_EXECUTABLE_ONLY"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R100 is local betrayal source signal emission only. No orders, no payloads, no env changes, no network, no Binance."
HISTORICAL_REPLAY_SOURCE = "outcomes_replay_for_detector_wiring"
HISTORICAL_REPLAY_STATUS = "historical_replay"


def build_betrayal_source_signal_emitter_status(
    *,
    max_signals: int = 20,
    identity_filter: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    return run_betrayal_source_signal_emitter(
        dry_run=True,
        write=False,
        max_signals=max_signals,
        identity_filter=identity_filter,
        allow_historical_replay=True,
        allow_fresh_current=False,
        log_dir=log_dir,
    )


def run_betrayal_source_signal_emitter(
    *,
    dry_run: bool = True,
    write: bool = False,
    max_signals: int = 20,
    identity_filter: str | None = None,
    allow_historical_replay: bool = True,
    allow_fresh_current: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC).isoformat()
    scaffold = build_betrayal_true_paper_scaffold(dry_run=True, write=False, log_dir=resolved_log_dir)
    source_wiring = build_betrayal_detector_source_wiring(dry_run=True, write=False, log_dir=resolved_log_dir)
    identities = _identity_map(scaffold, identity_filter=identity_filter)
    direction_identities = {
        signal_id: row for signal_id, row in identities.items() if row.get("audit_scope") == "direction_entry_mode"
    }
    aggregate_identities = [
        row for row in identities.values() if row.get("audit_scope") == "timeframe_aggregate"
    ]
    source_records, source_malformed = _read_ndjson(resolved_log_dir / "outcomes.ndjson")
    signals_by_id = _signals_by_id(resolved_log_dir / "signals.ndjson")
    existing_ids = _existing_emitted_signal_ids(resolved_log_dir)
    prepared: list[dict[str, Any]] = []
    emitted_count = 0
    duplicate_skipped = 0
    aggregate_skipped = 0
    missing_price_fields = 0
    missing_entry_mode = 0

    if allow_historical_replay:
        for record in reversed(source_records):
            if len(prepared) >= max(0, int(max_signals)):
                break
            result = _prepare_emission(
                outcome=record,
                identities=direction_identities,
                aggregate_identities=aggregate_identities,
                signals_by_id=signals_by_id,
                generated_at=generated_at,
            )
            reason = result.get("skip_reason")
            if reason == "missing_entry_mode":
                missing_entry_mode += 1
                continue
            if reason == "missing_price_fields":
                missing_price_fields += 1
                continue
            if reason == "aggregate_decomposition_required":
                aggregate_skipped += 1
                continue
            emission = result.get("emission")
            if not isinstance(emission, dict):
                continue
            if emission.get("emitted_signal_id") in existing_ids:
                emission["emission_status"] = BETRAYAL_DUPLICATE_EMISSION_SKIPPED
                duplicate_skipped += 1
                prepared.append(_sanitize(emission))
                continue
            if write and not dry_run:
                _append_emitted_signal(emission, log_dir=resolved_log_dir)
                existing_ids.add(str(emission.get("emitted_signal_id")))
                emission["emission_status"] = BETRAYAL_SIGNAL_EMITTED_LOCAL_ONLY
                emitted_count += 1
            else:
                emission["emission_status"] = BETRAYAL_SIGNAL_EMIT_DRY_RUN_ONLY
            prepared.append(_sanitize(emission))

    existing_after = _existing_emitted_signal_ids(resolved_log_dir)
    summary = _emitter_summary(
        source_records_scanned=len(source_records),
        source_malformed=source_malformed,
        scaffold_identity_count=len(identities),
        prepared_count=len([row for row in prepared if row.get("emission_status") != BETRAYAL_DUPLICATE_EMISSION_SKIPPED]),
        emitted_count=emitted_count,
        duplicate_skipped=duplicate_skipped,
        aggregate_skipped=aggregate_skipped,
        missing_price_fields=missing_price_fields,
        missing_entry_mode=missing_entry_mode,
        output_path=betrayal_paper_signals_path(resolved_log_dir),
        existing_before_count=len(existing_ids) - emitted_count if write and not dry_run else len(existing_ids),
        existing_after_count=len(existing_after),
        dry_run=dry_run,
        write=write,
    )
    payload = {
        "status": "OK",
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "generated_at": generated_at,
        "run_status": BETRAYAL_SIGNAL_EMITTED_LOCAL_ONLY if emitted_count else BETRAYAL_SIGNAL_EMIT_DRY_RUN_ONLY,
        "r100_statuses": _r100_statuses(summary=summary, identities_count=len(identities), source_wiring=source_wiring),
        "source_status": summary.get("source_status"),
        "source_wiring_summary": {
            "usable_detector_source_count": len(source_wiring.get("usable_detector_sources") or []),
            "detector_wiring_diagnostic": source_wiring.get("detector_wiring_diagnostic"),
        },
        "emitter_summary": summary,
        "output_path": str(betrayal_paper_signals_path(resolved_log_dir)),
        "report_path": str(betrayal_source_signal_emitter_report_path(resolved_log_dir)),
        "top_prepared_emissions": prepared[: max(0, int(max_signals))],
        "recent_emitted_signals": load_emitted_betrayal_paper_signals(limit=10, log_dir=resolved_log_dir),
        "emitted_signal_count": emitted_count,
        "duplicate_skipped_count": duplicate_skipped,
        "aggregate_skipped_count": aggregate_skipped,
        "missing_price_fields_count": missing_price_fields,
        "missing_entry_mode_count": missing_entry_mode,
        "dry_run": bool(dry_run),
        "write": bool(write),
        "allow_historical_replay": bool(allow_historical_replay),
        "allow_fresh_current": bool(allow_fresh_current),
        "report_written": False,
        "next_action_recommendation": "R101 Wire R98 Detector to R100 Emitted Signal Source",
        "notes": [
            NO_ORDER_NOTE,
            "Historical replay emissions are detector plumbing records, not fresh current market signals.",
            "Rows missing deterministic stop/take-profit data are skipped; R100 does not invent price risk geometry.",
        ],
        "review_only": True,
        "executable": False,
        "env_modified": False,
        "order_type": "not_created",
        **_safety_fields(),
    }
    if write and not dry_run:
        write_betrayal_source_signal_emitter_report(payload, log_dir=resolved_log_dir)
        payload["report_written"] = True
    return _sanitize(payload)


def betrayal_paper_signals_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / OUTPUT_FILENAME


def betrayal_source_signal_emitter_report_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / REPORT_FILENAME


def write_betrayal_source_signal_emitter_report(report: Mapping[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = betrayal_source_signal_emitter_report_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_sanitize(dict(report)), handle, sort_keys=True, indent=2)
        handle.write("\n")


def load_emitted_betrayal_paper_signals(*, limit: int = 50, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    records, _ = _read_ndjson(betrayal_paper_signals_path(log_dir))
    if limit <= 0:
        return []
    return [_sanitize(row) for row in records[-limit:]]


def format_betrayal_source_signal_emitter_text(payload: Mapping[str, Any]) -> str:
    summary = payload.get("emitter_summary") if isinstance(payload.get("emitter_summary"), dict) else {}
    top = payload.get("top_prepared_emissions") if isinstance(payload.get("top_prepared_emissions"), list) else []
    lines = [
        f"R100 Source Signal Emitter status: {payload.get('status')}",
        str(payload.get("execution_mode")),
        f"source_status: {payload.get('source_status')}",
        f"source_records_scanned: {summary.get('source_records_scanned')}",
        f"emittable_signal_count: {summary.get('emittable_signal_count')}",
        f"emitted_signal_count: {summary.get('emitted_signal_count')}",
        f"duplicate_skipped_count: {summary.get('duplicate_skipped_count')}",
        f"aggregate_skipped_count: {summary.get('aggregate_skipped_count')}",
        f"missing_price_fields_count: {summary.get('missing_price_fields_count')}",
        f"missing_entry_mode_count: {summary.get('missing_entry_mode_count')}",
        f"output_path: {summary.get('output_path')}",
        "top_prepared_emissions:",
    ]
    if not top:
        lines.append("  none")
    for row in top[:8]:
        lines.append(
            "  "
            f"{row.get('emitted_signal_id')} identity={row.get('betrayal_paper_signal_id')} "
            f"source={row.get('source_signal_id')} direction={row.get('direction')} "
            f"entry_mode={row.get('entry_mode')} freshness={row.get('signal_freshness')} "
            f"status={row.get('emission_status')}"
        )
    lines.extend(
        [
            f"next_phase_recommendation: {payload.get('next_action_recommendation')}",
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            "No-order/no-network/no-env-change safety note: R100 emits local review-only paper signal rows only.",
            NO_ORDER_NOTE,
        ]
    )
    return "\n".join(lines)


def _prepare_emission(
    *,
    outcome: Mapping[str, Any],
    identities: Mapping[str, Mapping[str, Any]],
    aggregate_identities: list[Mapping[str, Any]],
    signals_by_id: Mapping[str, Mapping[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    entry_mode = outcome.get("entry_mode")
    if not entry_mode:
        return {"skip_reason": "missing_entry_mode"}
    identity = _match_identity(outcome=outcome, entry_mode=str(entry_mode), identities=identities)
    if not identity:
        if _aggregate_identity_for_outcome(outcome, aggregate_identities):
            return {"skip_reason": "aggregate_decomposition_required"}
        return {"skip_reason": "no_matching_identity"}
    source_signal_id = str(outcome.get("signal_id") or "")
    source_signal = signals_by_id.get(source_signal_id, {})
    entry_price = _numeric(outcome.get("entry_price"))
    stop_price, take_profit = _stop_take_profit(
        source_signal=source_signal,
        betrayal_direction=str(identity.get("betrayal_direction")),
        entry_price=entry_price,
    )
    if entry_price is None or stop_price is None or take_profit is None:
        return {"skip_reason": "missing_price_fields", "betrayal_paper_signal_id": identity.get("betrayal_paper_signal_id")}
    source_timestamp = str(outcome.get("timestamp") or source_signal.get("timestamp") or "")
    freshness = HISTORICAL_REPLAY_STATUS
    emission = {
        "emitted_signal_id": _emitted_signal_id(
            betrayal_paper_signal_id=str(identity.get("betrayal_paper_signal_id")),
            source_signal_id=source_signal_id,
            source_timestamp=source_timestamp,
            entry_mode=str(entry_mode),
            signal_freshness=freshness,
        ),
        "betrayal_paper_signal_id": identity.get("betrayal_paper_signal_id"),
        "betrayal_paper_signal_hash": identity.get("betrayal_paper_signal_hash"),
        "source_signal_id": source_signal_id,
        "source_record_id": _source_record_id(outcome),
        "source_timestamp": source_timestamp,
        "emitted_at": generated_at,
        "symbol": outcome.get("symbol"),
        "timeframe": outcome.get("timeframe"),
        "original_direction": outcome.get("direction"),
        "betrayal_direction": identity.get("betrayal_direction"),
        "direction": identity.get("betrayal_direction"),
        "entry_mode": str(entry_mode),
        "paper_entry_price": entry_price,
        "paper_stop_price": stop_price,
        "paper_take_profit_price": take_profit,
        "signal_freshness": freshness,
        "is_fresh_current_signal": False,
        "data_source": HISTORICAL_REPLAY_SOURCE,
        "paper_signal_status": HISTORICAL_REPLAY_STATUS,
        "eligible_for_live": False,
        "review_only": True,
        "live_ready": False,
        "executable": False,
        "real_order_placed": False,
        "order_payload_created": False,
        "execution_attempted": False,
        "network_allowed": False,
        "secrets_shown": False,
    }
    return {"emission": _sanitize(emission)}


def _identity_map(scaffold: Mapping[str, Any], *, identity_filter: str | None) -> dict[str, Mapping[str, Any]]:
    candidates = scaffold.get("scaffold_candidates") if isinstance(scaffold.get("scaffold_candidates"), list) else []
    identities: dict[str, Mapping[str, Any]] = {}
    for row in candidates:
        if not isinstance(row, dict) or not row.get("betrayal_paper_signal_id"):
            continue
        if identity_filter and row.get("betrayal_paper_signal_id") != identity_filter:
            continue
        identities[str(row["betrayal_paper_signal_id"])] = row
    return identities


def _match_identity(
    *,
    outcome: Mapping[str, Any],
    entry_mode: str,
    identities: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    betrayal_direction = _invert_direction(str(outcome.get("direction")))
    for identity in identities.values():
        if identity.get("symbol") != outcome.get("symbol") or identity.get("timeframe") != outcome.get("timeframe"):
            continue
        if identity.get("original_direction") != outcome.get("direction"):
            continue
        if identity.get("betrayal_direction") != betrayal_direction:
            continue
        if identity.get("entry_mode") != entry_mode:
            continue
        return identity
    return None


def _aggregate_identity_for_outcome(
    outcome: Mapping[str, Any],
    aggregate_identities: list[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    for identity in aggregate_identities:
        if identity.get("symbol") == outcome.get("symbol") and identity.get("timeframe") == outcome.get("timeframe"):
            return identity
    return None


def _stop_take_profit(
    *,
    source_signal: Mapping[str, Any],
    betrayal_direction: str,
    entry_price: float | None,
) -> tuple[float | None, float | None]:
    if entry_price is None or not source_signal:
        return None, None
    if betrayal_direction == "short":
        stop = _numeric(source_signal.get("hammer_high") or source_signal.get("invalidation"))
        if stop is None:
            return None, None
        risk = abs(stop - entry_price)
        return round(stop, 8), round(entry_price - risk, 8)
    if betrayal_direction == "long":
        stop = _numeric(source_signal.get("hammer_low") or source_signal.get("invalidation"))
        if stop is None:
            return None, None
        risk = abs(entry_price - stop)
        return round(stop, 8), round(entry_price + risk, 8)
    return None, None


def _source_record_id(outcome: Mapping[str, Any]) -> str:
    stable = {
        "signal_id": outcome.get("signal_id"),
        "timestamp": outcome.get("timestamp"),
        "entry_mode": outcome.get("entry_mode"),
        "evaluated_at": outcome.get("evaluated_at"),
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _emitted_signal_id(
    *,
    betrayal_paper_signal_id: str,
    source_signal_id: str,
    source_timestamp: str,
    entry_mode: str,
    signal_freshness: str,
) -> str:
    stable = {
        "betrayal_paper_signal_id": betrayal_paper_signal_id,
        "source_signal_id": source_signal_id,
        "source_timestamp": source_timestamp,
        "entry_mode": entry_mode,
        "signal_freshness": signal_freshness,
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _existing_emitted_signal_ids(log_dir: Path) -> set[str]:
    records, _ = _read_ndjson(betrayal_paper_signals_path(log_dir))
    return {str(record.get("emitted_signal_id")) for record in records if record.get("emitted_signal_id")}


def _append_emitted_signal(emission: Mapping[str, Any], *, log_dir: Path) -> None:
    path = betrayal_paper_signals_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize(dict(emission)), sort_keys=True, separators=(",", ":")))
        handle.write("\n")


def _signals_by_id(path: Path) -> dict[str, Mapping[str, Any]]:
    records, _ = _read_ndjson(path)
    return {str(record.get("signal_id")): record for record in records if record.get("signal_id")}


def _read_ndjson(path: Path) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    records: list[dict[str, Any]] = []
    malformed = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(row, dict):
                records.append(row)
            else:
                malformed += 1
    return records, malformed


def _emitter_summary(
    *,
    source_records_scanned: int,
    source_malformed: int,
    scaffold_identity_count: int,
    prepared_count: int,
    emitted_count: int,
    duplicate_skipped: int,
    aggregate_skipped: int,
    missing_price_fields: int,
    missing_entry_mode: int,
    output_path: Path,
    existing_before_count: int,
    existing_after_count: int,
    dry_run: bool,
    write: bool,
) -> dict[str, Any]:
    return _sanitize(
        {
            "source_status": BETRAYAL_USABLE_SOURCE_FOUND if source_records_scanned else BETRAYAL_NO_EMITTABLE_SIGNALS_FOUND,
            "source_records_scanned": source_records_scanned,
            "source_malformed_record_count": source_malformed,
            "scaffold_identity_count": scaffold_identity_count,
            "emittable_signal_count": prepared_count,
            "emitted_signal_count": emitted_count,
            "duplicate_skipped_count": duplicate_skipped,
            "aggregate_skipped_count": aggregate_skipped,
            "missing_price_fields_count": missing_price_fields,
            "missing_entry_mode_count": missing_entry_mode,
            "output_path": str(output_path),
            "output_exists": output_path.exists(),
            "existing_emitted_signal_count": existing_before_count,
            "existing_emitted_signal_count_after": existing_after_count,
            "write_requested": bool(write),
            "dry_run": bool(dry_run),
            "live_ready_count": 0,
        }
    )


def _r100_statuses(
    *,
    summary: Mapping[str, Any],
    identities_count: int,
    source_wiring: Mapping[str, Any],
) -> list[str]:
    statuses = [BETRAYAL_SOURCE_SIGNAL_EMITTER_ONLY, BETRAYAL_SIGNAL_EMITTER_READY]
    if identities_count:
        statuses.append(BETRAYAL_SCAFFOLD_IDENTITIES_FOUND)
    if source_wiring.get("usable_detector_sources") or int(summary.get("source_records_scanned") or 0):
        statuses.append(BETRAYAL_USABLE_SOURCE_FOUND)
    if int(summary.get("emittable_signal_count") or 0):
        statuses.append(BETRAYAL_EXPLICIT_ENTRY_SIGNALS_PREPARED)
    else:
        statuses.append(BETRAYAL_NO_EMITTABLE_SIGNALS_FOUND)
    if int(summary.get("emitted_signal_count") or 0):
        statuses.append(BETRAYAL_SIGNAL_EMITTED_LOCAL_ONLY)
    else:
        statuses.append(BETRAYAL_SIGNAL_EMIT_DRY_RUN_ONLY)
    if int(summary.get("duplicate_skipped_count") or 0):
        statuses.append(BETRAYAL_DUPLICATE_EMISSION_SKIPPED)
    if int(summary.get("aggregate_skipped_count") or 0):
        statuses.append(BETRAYAL_AGGREGATE_SKIPPED_DECOMPOSITION_REQUIRED)
    statuses.extend([BETRAYAL_NOT_LIVE_READY, BETRAYAL_NON_EXECUTABLE_ONLY])
    return list(dict.fromkeys(statuses))


def _invert_direction(direction: str) -> str:
    return "short" if direction == "long" else "long"


def _numeric(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safety_fields() -> dict[str, Any]:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "order_payload_created": ORDER_PAYLOAD_CREATED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in (
            "live_execution_enabled",
            "allow_live_orders",
            "order_placed",
            "real_order_placed",
            "execution_attempted",
            "order_payload_created",
            "network_allowed",
            "secrets_shown",
            "executable",
            "env_modified",
            "live_ready",
            "eligible_for_live",
            "is_fresh_current_signal",
        ):
            if key in sanitized:
                sanitized[key] = False
        if "global_kill_switch" in sanitized:
            sanitized["global_kill_switch"] = True
        if "review_only" in sanitized:
            sanitized["review_only"] = True
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(_sanitize(item) for item in payload)
    return payload
