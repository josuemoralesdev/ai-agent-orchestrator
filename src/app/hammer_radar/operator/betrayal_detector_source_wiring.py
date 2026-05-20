"""R99 detector source wiring and aggregate decomposition review.

This module diagnoses local source files for R98 betrayal paper detection and
reviews aggregate betrayal candidates for real directional decomposition
evidence. It is review/report only and never creates signals, outcomes, orders,
payloads, Binance requests, env mutations, risk contracts, or live readiness.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_paper_signal_detector import (
    build_betrayal_paper_signal_detector_status,
)
from src.app.hammer_radar.operator.betrayal_strategy_audit import (
    BETRAYAL_PRIMARY_CANDIDATE,
    BETRAYAL_WATCHLIST,
    build_betrayal_strategy_audit,
)
from src.app.hammer_radar.operator.betrayal_true_paper_tracking import build_betrayal_true_paper_scaffold

PHASE = "R99"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "BETRAYAL_DETECTOR_SOURCE_WIRING_222M_DECOMPOSITION_ONLY_NO_ORDER"
REPORT_FILENAME = "betrayal_detector_source_wiring_report.json"

BETRAYAL_DETECTOR_SOURCE_WIRING_ONLY = "BETRAYAL_DETECTOR_SOURCE_WIRING_ONLY"
DETECTOR_SOURCE_INVENTORY_READY = "DETECTOR_SOURCE_INVENTORY_READY"
DETECTOR_SOURCE_FOUND = "DETECTOR_SOURCE_FOUND"
DETECTOR_SOURCE_MISSING = "DETECTOR_SOURCE_MISSING"
DETECTOR_SOURCE_FIELDS_INCOMPLETE = "DETECTOR_SOURCE_FIELDS_INCOMPLETE"
DETECTOR_SOURCE_WIRING_RECOMMENDED = "DETECTOR_SOURCE_WIRING_RECOMMENDED"
DETECTOR_SOURCE_WIRING_AVAILABLE = "DETECTOR_SOURCE_WIRING_AVAILABLE"
AGGREGATE_DECOMPOSITION_REVIEW_READY = "AGGREGATE_DECOMPOSITION_REVIEW_READY"
AGGREGATE_DECOMPOSITION_AVAILABLE = "AGGREGATE_DECOMPOSITION_AVAILABLE"
AGGREGATE_DECOMPOSITION_NOT_AVAILABLE = "AGGREGATE_DECOMPOSITION_NOT_AVAILABLE"
AGGREGATE_DECOMPOSITION_MISSING_DIRECTION = "AGGREGATE_DECOMPOSITION_MISSING_DIRECTION"
AGGREGATE_DECOMPOSITION_MISSING_ENTRY_MODE = "AGGREGATE_DECOMPOSITION_MISSING_ENTRY_MODE"
AGGREGATE_DECOMPOSITION_REVIEW_ONLY = "AGGREGATE_DECOMPOSITION_REVIEW_ONLY"
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

NO_ORDER_NOTE = "R99 is detector source wiring and aggregate decomposition review only. No orders, no payloads, no env changes, no network, no Binance."

SOURCE_FILES = (
    ("signals", "signals.ndjson"),
    ("outcomes", "outcomes.ndjson"),
    ("paper_executions", "paper_executions.ndjson"),
    ("trade_tickets", "trade_tickets.ndjson"),
    ("positions", "positions.ndjson"),
    ("position_events", "position_events.ndjson"),
    ("betrayal_shadow_outcomes", "betrayal_shadow_outcomes.ndjson"),
    ("betrayal_shadow_resolutions", "betrayal_shadow_resolutions.ndjson"),
    ("paper_refresh_runs", "paper_refresh_runs.ndjson"),
)


def build_betrayal_detector_source_wiring(
    *,
    symbol: str = "BTCUSDT",
    timeframe: str | None = "222m",
    dry_run: bool = True,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC).isoformat()
    source_inventory = [_source_inventory_row(resolved_log_dir / filename, source_name=name) for name, filename in SOURCE_FILES]
    usable_sources = [row for row in source_inventory if row.get("usable_for_detector")]
    missing_sources = [row for row in source_inventory if not row.get("usable_for_detector")]
    r98 = _safe_r98_summary(resolved_log_dir)
    audit = _safe_audit(resolved_log_dir)
    scaffold = _safe_scaffold(resolved_log_dir)
    decomposition = _aggregate_decomposition_review(
        audit=audit,
        scaffold=scaffold,
        symbol=symbol,
        timeframe=timeframe,
    )
    diagnostic = _detector_wiring_diagnostic(source_inventory=source_inventory, r98=r98)
    payload = _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at,
            "r99_statuses": _r99_statuses(source_inventory=source_inventory, decomposition=decomposition),
            "source_inventory": source_inventory,
            "detector_wiring_diagnostic": diagnostic,
            "usable_detector_sources": usable_sources,
            "missing_detector_sources": missing_sources,
            "r98_current_summary": {
                "detection_source_status": r98.get("detection_source_status"),
                "detection_summary": r98.get("detection_summary"),
                "next_action_recommendation": r98.get("next_action_recommendation"),
            },
            "aggregate_decomposition_review": decomposition,
            "proposed_decomposition_identities": decomposition.get("proposed_decomposition_identities", []),
            "recommended_next_phase": _recommended_next_phase(diagnostic=diagnostic, decomposition=decomposition),
            "recommended_repair_scope": _recommended_repair_scope(diagnostic=diagnostic, decomposition=decomposition),
            "blockers": _blockers(diagnostic=diagnostic, decomposition=decomposition),
            "notes": [
                NO_ORDER_NOTE,
                "R99 inventories local sources only; it does not create detector signals or paper outcomes.",
                "Aggregate decomposition is proposed only from real direction/entry audit evidence.",
            ],
            "dry_run": bool(dry_run),
            "write": bool(write),
            "report_written": False,
            "report_path": str(betrayal_detector_source_wiring_report_path(resolved_log_dir)),
            "review_only": True,
            "executable": False,
            "env_modified": False,
            "order_type": "not_created",
            **_safety_fields(),
        }
    )
    if write and not dry_run:
        write_betrayal_detector_source_wiring_report(payload, log_dir=resolved_log_dir)
        payload["report_written"] = True
    return _sanitize(payload)


def betrayal_detector_source_wiring_report_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / REPORT_FILENAME


def write_betrayal_detector_source_wiring_report(report: Mapping[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = betrayal_detector_source_wiring_report_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_sanitize(dict(report)), handle, sort_keys=True, indent=2)
        handle.write("\n")


def format_betrayal_detector_source_wiring_text(payload: Mapping[str, Any]) -> str:
    inventory = payload.get("source_inventory") if isinstance(payload.get("source_inventory"), list) else []
    usable = payload.get("usable_detector_sources") if isinstance(payload.get("usable_detector_sources"), list) else []
    missing = payload.get("missing_detector_sources") if isinstance(payload.get("missing_detector_sources"), list) else []
    diagnostic = payload.get("detector_wiring_diagnostic") if isinstance(payload.get("detector_wiring_diagnostic"), dict) else {}
    decomposition = payload.get("aggregate_decomposition_review") if isinstance(payload.get("aggregate_decomposition_review"), dict) else {}
    proposed = payload.get("proposed_decomposition_identities") if isinstance(payload.get("proposed_decomposition_identities"), list) else []
    lines = [
        f"R99 Detector Source Wiring status: {payload.get('status')}",
        str(payload.get("execution_mode")),
        f"usable_detector_source_count: {len(usable)}",
        f"missing_or_invalid_source_count: {len(missing)}",
        f"r98_no_signal_reason: {diagnostic.get('r98_no_signal_reason')}",
        f"222m_decomposition_status: {decomposition.get('decomposition_status')}",
        "source_inventory:",
    ]
    for row in inventory:
        lines.append(
            "  "
            f"{row.get('source_name')} exists={row.get('exists')} records={row.get('record_count')} "
            f"usable={row.get('usable_for_detector')} missing={row.get('missing_required_fields')}"
        )
    lines.append("proposed_decomposition_identities:")
    if not proposed:
        lines.append("  none")
    for row in proposed[:8]:
        lines.append(
            "  "
            f"{row.get('betrayal_paper_signal_id')} samples={row.get('sample_count')} "
            f"inverse_win={row.get('naive_inverse_win_rate_pct')} status={row.get('decomposition_status')}"
        )
    lines.extend(
        [
            f"next_phase_recommendation: {payload.get('recommended_next_phase')}",
            f"recommended_repair_scope: {payload.get('recommended_repair_scope')}",
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            "No-order/no-network/no-env-change safety note: R99 is source wiring/decomposition review only.",
            NO_ORDER_NOTE,
        ]
    )
    return "\n".join(lines)


def _source_inventory_row(path: Path, *, source_name: str) -> dict[str, Any]:
    records, malformed = _read_ndjson(path)
    sample = records[0] if records else {}
    required = _required_fields_for_source(source_name)
    present, missing = _field_presence(sample, required)
    usable = bool(path.exists() and records and not missing)
    notes = []
    if source_name == "signals" and records and "entry_mode" in missing:
        notes.append("R98 currently requires explicit entry mode derivable from signal_id or entry_mode field.")
    if not path.exists():
        notes.append("source file missing")
    elif not records:
        notes.append("source has no readable records")
    return _sanitize(
        {
            "source_name": source_name,
            "path": str(path),
            "exists": path.exists(),
            "record_count": len(records) + malformed,
            "valid_record_count": len(records),
            "malformed_record_count": malformed,
            "required_fields_present": present,
            "missing_required_fields": missing,
            "usable_for_detector": usable,
            "detector_field_mapping": _field_mapping(source_name) if usable else {},
            "notes": notes,
        }
    )


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


def _required_fields_for_source(source_name: str) -> tuple[str, ...]:
    if source_name == "signals":
        return ("signal_id", "symbol", "timeframe", "direction", "timestamp", "entry_mode", "entry_price", "stop", "take_profit")
    if source_name == "outcomes":
        return ("signal_id", "symbol", "timeframe", "direction", "entry_mode", "timestamp", "entry_price", "exit_price", "pnl_pct")
    return ("symbol", "timeframe", "direction", "entry_mode", "timestamp")


def _field_presence(sample: Mapping[str, Any], required: tuple[str, ...]) -> tuple[list[str], list[str]]:
    present: list[str] = []
    missing: list[str] = []
    for field in required:
        if _has_detector_field(sample, field):
            present.append(field)
        else:
            missing.append(field)
    return present, missing


def _has_detector_field(sample: Mapping[str, Any], field: str) -> bool:
    if not sample:
        return False
    if field == "entry_mode":
        return bool(sample.get("entry_mode") or _entry_mode_from_signal_id(sample.get("signal_id")))
    if field == "entry_price":
        mode = sample.get("entry_mode") or _entry_mode_from_signal_id(sample.get("signal_id"))
        if mode and sample.get(str(mode)) is not None:
            return True
        return any(sample.get(key) is not None for key in ("entry_price", "signal_close", "fib_618", "fib_650"))
    if field == "stop":
        return any(sample.get(key) is not None for key in ("stop_price", "invalidation", "hammer_high", "hammer_low"))
    if field == "take_profit":
        return any(sample.get(key) is not None for key in ("take_profit_price", "hammer_high", "hammer_low"))
    if field == "timestamp":
        return bool(sample.get("timestamp") or sample.get("source_timestamp") or sample.get("created_at"))
    return sample.get(field) not in (None, "")


def _entry_mode_from_signal_id(signal_id: object) -> str | None:
    text = str(signal_id or "")
    for mode in ("fib_650", "fib_618", "fib_50", "fib_786", "ladder_close_50_618", "market_close"):
        if mode in text:
            return mode
    return None


def _field_mapping(source_name: str) -> dict[str, str]:
    if source_name == "signals":
        return {
            "signal_id": "source_signal_id",
            "timestamp": "source_timestamp",
            "symbol": "symbol",
            "timeframe": "timeframe",
            "direction": "source normal direction; detector inverts to betrayal direction",
            "entry_mode": "identity entry_mode",
            "fib_618/fib_650/signal_close": "paper_entry_price",
            "hammer_high/hammer_low": "paper_stop_price and paper_take_profit_price",
        }
    if source_name == "outcomes":
        return {
            "signal_id": "source_signal_id",
            "timestamp": "source_timestamp",
            "entry_mode": "identity entry_mode",
            "entry_price": "paper_entry_price",
            "exit_price": "paper_exit_price",
            "pnl_pct": "inverted paper_pnl_pct for betrayal side",
        }
    return {}


def _detector_wiring_diagnostic(*, source_inventory: list[Mapping[str, Any]], r98: Mapping[str, Any]) -> dict[str, Any]:
    signals = next((row for row in source_inventory if row.get("source_name") == "signals"), {})
    r98_summary = r98.get("detection_summary") if isinstance(r98.get("detection_summary"), dict) else {}
    no_signal_reason = "R98 found no detector-qualified source signals."
    if signals.get("exists") and int(signals.get("valid_record_count") or 0) > 0 and not signals.get("usable_for_detector"):
        no_signal_reason = "signals.ndjson exists, but current records are missing detector-required fields such as explicit entry_mode derivable by R98."
    elif not signals.get("exists"):
        no_signal_reason = "signals.ndjson is missing, so R98 has no local source signals to scan."
    elif int(r98_summary.get("detected_signal_count") or 0) == 0:
        no_signal_reason = "R98 source scan produced zero matched/prepared detections."
    usable = [row.get("source_name") for row in source_inventory if row.get("usable_for_detector")]
    return _sanitize(
        {
            "detector_source_status": DETECTOR_SOURCE_WIRING_AVAILABLE if usable else DETECTOR_SOURCE_WIRING_RECOMMENDED,
            "r98_detection_source_status": r98.get("detection_source_status"),
            "r98_detected_signal_count": r98_summary.get("detected_signal_count", 0),
            "r98_matched_signal_count": r98_summary.get("matched_signal_count", 0),
            "r98_no_signal_reason": no_signal_reason,
            "usable_source_names": usable,
            "wiring_gap": None if usable else "create local explicit-entry betrayal detector source records or emit entry_mode into signals.ndjson signal_id/field",
        }
    )


def _safe_r98_summary(log_dir: Path) -> dict[str, Any]:
    try:
        return build_betrayal_paper_signal_detector_status(log_dir=log_dir)
    except Exception as exc:
        return {
            "status": "ERROR",
            "phase": "R98",
            "detection_source_status": DETECTOR_SOURCE_FIELDS_INCOMPLETE,
            "detection_summary": {
                "detected_signal_count": 0,
                "matched_signal_count": 0,
                "prepared_open_tracking_count": 0,
                "prepared_closed_outcome_count": 0,
                "captured_outcome_count": 0,
            },
            "next_action_recommendation": "R99 source repair required before R98 scan",
            "error_type": exc.__class__.__name__,
            "review_only": True,
            "executable": False,
            **_safety_fields(),
        }


def _safe_audit(log_dir: Path) -> dict[str, Any]:
    try:
        return build_betrayal_strategy_audit(log_dir=log_dir)
    except Exception as exc:
        return {
            "status": "ERROR",
            "phase": "R80",
            "direction_entry_mode_primary_candidates": [],
            "direction_entry_mode_watchlist_candidates": [],
            "direction_entry_mode_rejected_candidates": [],
            "error_type": exc.__class__.__name__,
            "review_only": True,
            "executable": False,
            **_safety_fields(),
        }


def _safe_scaffold(log_dir: Path) -> dict[str, Any]:
    try:
        return build_betrayal_true_paper_scaffold(log_dir=log_dir)
    except Exception as exc:
        return {
            "status": "ERROR",
            "phase": "R96",
            "aggregate_candidates_needing_decomposition": [],
            "error_type": exc.__class__.__name__,
            "review_only": True,
            "executable": False,
            **_safety_fields(),
        }


def _aggregate_decomposition_review(
    *,
    audit: Mapping[str, Any],
    scaffold: Mapping[str, Any],
    symbol: str,
    timeframe: str | None,
) -> dict[str, Any]:
    target_timeframe = timeframe or "222m"
    aggregate = [
        row
        for row in scaffold.get("aggregate_candidates_needing_decomposition", [])
        if isinstance(row, dict) and row.get("timeframe") == target_timeframe
    ]
    directional_rows = _direction_rows_for_timeframe(audit, target_timeframe)
    eligible = [
        row for row in directional_rows if row.get("recommendation") in {BETRAYAL_PRIMARY_CANDIDATE, BETRAYAL_WATCHLIST}
    ]
    proposed = [_proposed_decomposition(row, symbol=symbol) for row in eligible]
    missing_fields = []
    if not directional_rows or not any(row.get("original_direction") for row in directional_rows):
        missing_fields.append("original_direction")
        missing_fields.append("betrayal_direction")
    if not directional_rows or not any(row.get("entry_mode") for row in directional_rows):
        missing_fields.append("entry_mode")
    status = AGGREGATE_DECOMPOSITION_AVAILABLE if proposed else AGGREGATE_DECOMPOSITION_NOT_AVAILABLE
    return _sanitize(
        {
            "aggregate_identity": aggregate[0].get("betrayal_paper_signal_id") if aggregate else None,
            "timeframe": target_timeframe,
            "decomposition_status": status,
            "directional_rows_found": len(directional_rows),
            "eligible_directional_rows_found": len(eligible),
            "missing_fields": list(dict.fromkeys(missing_fields)),
            "reviewed_directional_rows": directional_rows[:10],
            "proposed_decomposition_identities": proposed,
            "next_step": "R100 Betrayal Outcome Capture Scheduler / Paper Maturity Snapshot"
            if proposed
            else "R100 Source Signal Emitter for Betrayal Paper Detector or R100 222m Directional Audit Expansion",
            "review_only": True,
            "live_ready": False,
            "executable": False,
        }
    )


def _direction_rows_for_timeframe(audit: Mapping[str, Any], timeframe: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in (
        "direction_entry_mode_primary_candidates",
        "direction_entry_mode_watchlist_candidates",
        "direction_entry_mode_rejected_candidates",
    ):
        values = audit.get(key) if isinstance(audit.get(key), list) else []
        for row in values:
            if isinstance(row, dict) and row.get("timeframe") == timeframe:
                rows.append(row)
    return rows


def _proposed_decomposition(row: Mapping[str, Any], *, symbol: str) -> dict[str, Any]:
    original_direction = row.get("original_direction")
    betrayal_direction = row.get("betrayal_direction")
    entry_mode = row.get("entry_mode")
    signal_id = f"betrayal|{symbol}|{row.get('timeframe')}|{original_direction}_to_{betrayal_direction}|{entry_mode}|direction_entry_mode"
    betrayal = row.get("betrayal") if isinstance(row.get("betrayal"), dict) else {}
    return _sanitize(
        {
            "betrayal_paper_signal_id": signal_id,
            "evidence_source": "betrayal_strategy_audit.direction_entry_mode",
            "original_direction": original_direction,
            "betrayal_direction": betrayal_direction,
            "entry_mode": entry_mode,
            "sample_count": row.get("sample_count"),
            "naive_inverse_win_rate_pct": betrayal.get("win_rate_pct"),
            "naive_inverse_total_pnl_pct": betrayal.get("total_pnl_pct"),
            "decomposition_status": AGGREGATE_DECOMPOSITION_AVAILABLE,
            "confidence": row.get("confidence"),
            "review_only": True,
            "live_ready": False,
            "requires_true_paper_tracking": True,
            "executable": False,
        }
    )


def _r99_statuses(*, source_inventory: list[Mapping[str, Any]], decomposition: Mapping[str, Any]) -> list[str]:
    statuses = [BETRAYAL_DETECTOR_SOURCE_WIRING_ONLY, DETECTOR_SOURCE_INVENTORY_READY, AGGREGATE_DECOMPOSITION_REVIEW_READY]
    statuses.append(DETECTOR_SOURCE_FOUND if any(row.get("exists") for row in source_inventory) else DETECTOR_SOURCE_MISSING)
    if any(row.get("exists") and not row.get("usable_for_detector") for row in source_inventory):
        statuses.append(DETECTOR_SOURCE_FIELDS_INCOMPLETE)
    statuses.append(DETECTOR_SOURCE_WIRING_AVAILABLE if any(row.get("usable_for_detector") for row in source_inventory) else DETECTOR_SOURCE_WIRING_RECOMMENDED)
    statuses.append(str(decomposition.get("decomposition_status") or AGGREGATE_DECOMPOSITION_NOT_AVAILABLE))
    missing = decomposition.get("missing_fields") if isinstance(decomposition.get("missing_fields"), list) else []
    if "original_direction" in missing or "betrayal_direction" in missing:
        statuses.append(AGGREGATE_DECOMPOSITION_MISSING_DIRECTION)
    if "entry_mode" in missing:
        statuses.append(AGGREGATE_DECOMPOSITION_MISSING_ENTRY_MODE)
    statuses.extend([AGGREGATE_DECOMPOSITION_REVIEW_ONLY, BETRAYAL_NOT_LIVE_READY, BETRAYAL_NON_EXECUTABLE_ONLY])
    return list(dict.fromkeys(statuses))


def _recommended_next_phase(*, diagnostic: Mapping[str, Any], decomposition: Mapping[str, Any]) -> str:
    if decomposition.get("decomposition_status") == AGGREGATE_DECOMPOSITION_AVAILABLE:
        return "R100 Betrayal Outcome Capture Scheduler / Paper Maturity Snapshot"
    return "R100 Source Signal Emitter for Betrayal Paper Detector or R100 222m Directional Audit Expansion"


def _recommended_repair_scope(*, diagnostic: Mapping[str, Any], decomposition: Mapping[str, Any]) -> str:
    if diagnostic.get("usable_source_names"):
        return "wire R98 to usable explicit-entry source records and keep writes dry-run by default"
    if decomposition.get("decomposition_status") == AGGREGATE_DECOMPOSITION_AVAILABLE:
        return "emit local detector source records for proposed 222m directional identities"
    return "add explicit entry_mode signal emission and expand 222m directional audit evidence"


def _blockers(*, diagnostic: Mapping[str, Any], decomposition: Mapping[str, Any]) -> list[str]:
    blockers = ["true_paper_outcomes_empty", "risk_contract_not_created", "live_readiness_not_allowed"]
    if not diagnostic.get("usable_source_names"):
        blockers.append("no_usable_detector_source")
    if decomposition.get("decomposition_status") != AGGREGATE_DECOMPOSITION_AVAILABLE:
        blockers.append("222m_directional_decomposition_not_available")
    return blockers


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
        return [_sanitize(item) for item in payload]
    if isinstance(payload, Path):
        return str(payload)
    return payload
