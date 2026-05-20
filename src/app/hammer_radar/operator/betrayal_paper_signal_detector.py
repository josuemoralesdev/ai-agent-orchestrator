"""R98 betrayal paper signal detector and outcome capture loop.

This module reads local Hammer Radar paper signal/outcome archives, matches
fresh source signals to R96 betrayal paper identities, prepares open tracking
records, and captures closed paper outcomes through the R97 ledger validator.
It never creates live orders, executable payloads, Binance requests, account
checks, env mutations, risk contracts, or live readiness.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir, load_outcomes, load_signals
from src.app.hammer_radar.operator.betrayal_paper_outcome_ledger import (
    BETRAYAL_OUTCOME_WRITTEN_LOCAL_ONLY,
    build_betrayal_paper_outcome_status,
    load_betrayal_paper_outcomes,
    record_betrayal_paper_outcome,
)
from src.app.hammer_radar.operator.betrayal_true_paper_tracking import build_betrayal_true_paper_scaffold

PHASE = "R98"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "BETRAYAL_PAPER_SIGNAL_DETECTOR_ONLY_NO_ORDER"
REPORT_FILENAME = "betrayal_paper_signal_detector_report.json"

BETRAYAL_PAPER_SIGNAL_DETECTOR_ONLY = "BETRAYAL_PAPER_SIGNAL_DETECTOR_ONLY"
BETRAYAL_SIGNAL_DETECTION_READY = "BETRAYAL_SIGNAL_DETECTION_READY"
BETRAYAL_SCAFFOLD_IDENTITIES_FOUND = "BETRAYAL_SCAFFOLD_IDENTITIES_FOUND"
BETRAYAL_LEDGER_READY = "BETRAYAL_LEDGER_READY"
BETRAYAL_NO_FRESH_SIGNALS_FOUND = "BETRAYAL_NO_FRESH_SIGNALS_FOUND"
BETRAYAL_FRESH_SIGNALS_FOUND = "BETRAYAL_FRESH_SIGNALS_FOUND"
BETRAYAL_SIGNAL_MATCHED_TO_IDENTITY = "BETRAYAL_SIGNAL_MATCHED_TO_IDENTITY"
BETRAYAL_SIGNAL_UNMATCHED_TO_IDENTITY = "BETRAYAL_SIGNAL_UNMATCHED_TO_IDENTITY"
BETRAYAL_OPEN_PAPER_TRACKING_PREPARED = "BETRAYAL_OPEN_PAPER_TRACKING_PREPARED"
BETRAYAL_CLOSED_PAPER_OUTCOME_PREPARED = "BETRAYAL_CLOSED_PAPER_OUTCOME_PREPARED"
BETRAYAL_OUTCOME_WRITE_DRY_RUN_ONLY = "BETRAYAL_OUTCOME_WRITE_DRY_RUN_ONLY"
BETRAYAL_OUTCOME_CAPTURED_LOCAL_ONLY = "BETRAYAL_OUTCOME_CAPTURED_LOCAL_ONLY"
BETRAYAL_DUPLICATE_SIGNAL_SKIPPED = "BETRAYAL_DUPLICATE_SIGNAL_SKIPPED"
BETRAYAL_AGGREGATE_DECOMPOSITION_REQUIRED = "BETRAYAL_AGGREGATE_DECOMPOSITION_REQUIRED"
BETRAYAL_NOT_LIVE_READY = "BETRAYAL_NOT_LIVE_READY"
BETRAYAL_NON_EXECUTABLE_ONLY = "BETRAYAL_NON_EXECUTABLE_ONLY"

SIGNAL_DETECTED = "SIGNAL_DETECTED"
SIGNAL_MATCHED_TO_BETRAYAL_IDENTITY = "SIGNAL_MATCHED_TO_BETRAYAL_IDENTITY"
SIGNAL_OPEN_TRACKING_ONLY = "SIGNAL_OPEN_TRACKING_ONLY"
SIGNAL_CLOSED_OUTCOME_READY = "SIGNAL_CLOSED_OUTCOME_READY"
SIGNAL_REJECTED_NO_MATCHING_IDENTITY = "SIGNAL_REJECTED_NO_MATCHING_IDENTITY"
SIGNAL_REJECTED_AGGREGATE_ONLY = "SIGNAL_REJECTED_AGGREGATE_ONLY"
SIGNAL_REJECTED_MISSING_ENTRY = "SIGNAL_REJECTED_MISSING_ENTRY"
SIGNAL_REJECTED_MISSING_STOP_OR_TP = "SIGNAL_REJECTED_MISSING_STOP_OR_TP"
SIGNAL_REJECTED_DUPLICATE = "SIGNAL_REJECTED_DUPLICATE"
SIGNAL_REVIEW_ONLY = "SIGNAL_REVIEW_ONLY"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R98 is betrayal paper signal detection/capture only. No orders, no payloads, no env changes, no network, no Binance."


def build_betrayal_paper_signal_detector_status(
    *,
    max_signals: int = 20,
    identity_filter: str | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    return run_betrayal_paper_signal_detector(
        dry_run=True,
        write=False,
        max_signals=max_signals,
        identity_filter=identity_filter,
        allow_open_tracking=True,
        allow_closed_outcomes=True,
        log_dir=log_dir,
    )


def run_betrayal_paper_signal_detector(
    *,
    dry_run: bool = True,
    write: bool = False,
    max_signals: int = 20,
    identity_filter: str | None = None,
    allow_open_tracking: bool = True,
    allow_closed_outcomes: bool = True,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC).isoformat()
    scaffold = build_betrayal_true_paper_scaffold(dry_run=True, write=False, log_dir=resolved_log_dir)
    identities = _identity_map(scaffold, identity_filter=identity_filter)
    ledger_before = build_betrayal_paper_outcome_status(log_dir=resolved_log_dir)
    before_count = int((ledger_before.get("ledger_summary") or {}).get("ledger_record_count") or 0)
    existing_outcome_ids = _existing_outcome_ids(resolved_log_dir)
    source_signals = load_signals(resolved_log_dir)
    source_outcomes = {record.signal_id: record for record in load_outcomes(resolved_log_dir)}
    detections: list[dict[str, Any]] = []
    captured = 0
    duplicate_skipped = 0
    aggregate_rejected = 0

    for signal in reversed(source_signals):
        if len(detections) >= max(0, int(max_signals)):
            break
        detection = _detect_signal(
            signal=signal,
            outcome=source_outcomes.get(signal.signal_id),
            identities=identities,
            allow_open_tracking=allow_open_tracking,
            allow_closed_outcomes=allow_closed_outcomes,
        )
        if not detection:
            continue
        outcome_payload = detection.get("prepared_outcome")
        outcome_id = outcome_payload.get("outcome_id") if isinstance(outcome_payload, dict) else None
        if outcome_id and outcome_id in existing_outcome_ids:
            detection["signal_status"] = SIGNAL_REJECTED_DUPLICATE
            detection["capture_status"] = BETRAYAL_DUPLICATE_SIGNAL_SKIPPED
            duplicate_skipped += 1
        elif (
            write
            and not dry_run
            and detection.get("paper_status") == "closed"
            and isinstance(outcome_payload, dict)
        ):
            result = record_betrayal_paper_outcome(outcome=outcome_payload, dry_run=False, write=True, log_dir=resolved_log_dir)
            detection["capture_result"] = result
            if result.get("record_status") == BETRAYAL_OUTCOME_WRITTEN_LOCAL_ONLY:
                detection["capture_status"] = BETRAYAL_OUTCOME_CAPTURED_LOCAL_ONLY
                captured += 1
                if outcome_id:
                    existing_outcome_ids.add(str(outcome_id))
            else:
                detection["capture_status"] = result.get("record_status")
        elif detection.get("paper_status") == "closed":
            detection["capture_status"] = BETRAYAL_OUTCOME_WRITE_DRY_RUN_ONLY
        if detection.get("signal_status") == SIGNAL_REJECTED_AGGREGATE_ONLY:
            aggregate_rejected += 1
        detections.append(_sanitize(detection))

    ledger_after = build_betrayal_paper_outcome_status(log_dir=resolved_log_dir)
    after_count = int((ledger_after.get("ledger_summary") or {}).get("ledger_record_count") or 0)
    summary = _detection_summary(
        detections=detections,
        captured=captured,
        duplicate_skipped=duplicate_skipped,
        aggregate_rejected=aggregate_rejected,
        before_count=before_count,
        after_count=after_count,
        ledger_after=ledger_after,
    )
    payload = {
        "status": "OK",
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "generated_at": generated_at,
        "run_status": BETRAYAL_OUTCOME_CAPTURED_LOCAL_ONLY if captured else BETRAYAL_OUTCOME_WRITE_DRY_RUN_ONLY,
        "r98_statuses": _r98_statuses(summary, identities_count=len(identities)),
        "detection_source_status": summary.get("detection_source_status"),
        "source_summary": {
            "signals_path": str(resolved_log_dir / "signals.ndjson"),
            "outcomes_path": str(resolved_log_dir / "outcomes.ndjson"),
            "source_signal_count": len(source_signals),
            "source_outcome_count": len(source_outcomes),
        },
        "detection_summary": summary,
        "prepared_detections": detections,
        "top_matched_identities": _top_matched_identities(detections),
        "ledger_summary": ledger_after.get("ledger_summary"),
        "ledger_record_count_before": before_count,
        "ledger_record_count_after": after_count,
        "outcomes_written": captured,
        "dry_run": bool(dry_run),
        "write": bool(write),
        "allow_open_tracking": bool(allow_open_tracking),
        "allow_closed_outcomes": bool(allow_closed_outcomes),
        "report_path": str(betrayal_paper_signal_detector_report_path(resolved_log_dir)),
        "report_written": False,
        "next_action_recommendation": _next_action(summary),
        "notes": [
            NO_ORDER_NOTE,
            "Open tracking records are prepared only; R97 ledger writes remain closed-outcome validation only.",
            "Closed outcomes are written only from existing local OutcomeRecord evidence and through R97 validation.",
        ],
        "review_only": True,
        "executable": False,
        "env_modified": False,
        "order_type": "not_created",
        **_safety_fields(),
    }
    if write and not dry_run:
        write_betrayal_paper_signal_detector_report(payload, log_dir=resolved_log_dir)
        payload["report_written"] = True
    return _sanitize(payload)


def betrayal_paper_signal_detector_report_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / REPORT_FILENAME


def write_betrayal_paper_signal_detector_report(report: Mapping[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = betrayal_paper_signal_detector_report_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_sanitize(dict(report)), handle, sort_keys=True, indent=2)
        handle.write("\n")


def format_betrayal_paper_signal_detector_text(payload: Mapping[str, Any]) -> str:
    summary = payload.get("detection_summary") if isinstance(payload.get("detection_summary"), dict) else {}
    top = payload.get("top_matched_identities") if isinstance(payload.get("top_matched_identities"), list) else []
    lines = [
        f"R98 Betrayal Paper Signal Detector status: {payload.get('status')}",
        str(payload.get("execution_mode")),
        f"detection_source_status: {payload.get('detection_source_status')}",
        f"detected_signal_count: {summary.get('detected_signal_count')}",
        f"matched_signal_count: {summary.get('matched_signal_count')}",
        f"prepared_open_tracking_count: {summary.get('prepared_open_tracking_count')}",
        f"prepared_closed_outcome_count: {summary.get('prepared_closed_outcome_count')}",
        f"captured_outcome_count: {summary.get('captured_outcome_count')}",
        f"duplicate_skipped_count: {summary.get('duplicate_skipped_count')}",
        f"aggregate_rejected_count: {summary.get('aggregate_rejected_count')}",
        f"ledger_record_count_before: {summary.get('ledger_record_count_before')}",
        f"ledger_record_count_after: {summary.get('ledger_record_count_after')}",
        "top_matched_identities:",
    ]
    if not top:
        lines.append("  none")
    for row in top[:8]:
        lines.append(f"  {row.get('betrayal_paper_signal_id')} matched={row.get('matched_signal_count')}")
    lines.extend(
        [
            f"next_action_recommendation: {payload.get('next_action_recommendation')}",
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            "No-order/no-network/no-env-change safety note: R98 is local paper signal detection/capture only.",
            NO_ORDER_NOTE,
        ]
    )
    return "\n".join(lines)


def _detect_signal(
    *,
    signal: Any,
    outcome: Any | None,
    identities: Mapping[str, Mapping[str, Any]],
    allow_open_tracking: bool,
    allow_closed_outcomes: bool,
) -> dict[str, Any] | None:
    entry_mode = _entry_mode_from_signal(signal)
    if entry_mode is None:
        return None
    entry_price = _entry_price(signal, entry_mode)
    matched = _match_identity(signal=signal, entry_mode=entry_mode, identities=identities)
    base = {
        "signal_status": SIGNAL_DETECTED,
        "source_signal_id": signal.signal_id,
        "source_timestamp": signal.timestamp,
        "source_symbol": signal.symbol,
        "source_timeframe": signal.timeframe,
        "source_direction": signal.direction,
        "source_entry_mode": entry_mode,
        "review_only": True,
        "live_ready": False,
        "executable": False,
        **_safety_fields(),
    }
    if not matched:
        aggregate = _aggregate_identity_for_signal(signal, identities)
        if aggregate:
            return {
                **base,
                "signal_status": SIGNAL_REJECTED_AGGREGATE_ONLY,
                "r98_status": BETRAYAL_AGGREGATE_DECOMPOSITION_REQUIRED,
                "betrayal_paper_signal_id": aggregate.get("betrayal_paper_signal_id"),
                "aggregate_requires_directional_decomposition": True,
            }
        return {**base, "signal_status": SIGNAL_REJECTED_NO_MATCHING_IDENTITY, "r98_status": BETRAYAL_SIGNAL_UNMATCHED_TO_IDENTITY}
    if matched.get("aggregate_requires_directional_decomposition"):
        return {
            **base,
            "signal_status": SIGNAL_REJECTED_AGGREGATE_ONLY,
            "r98_status": BETRAYAL_AGGREGATE_DECOMPOSITION_REQUIRED,
            "betrayal_paper_signal_id": matched.get("betrayal_paper_signal_id"),
            "aggregate_requires_directional_decomposition": True,
        }
    if entry_price is None:
        return {**base, "signal_status": SIGNAL_REJECTED_MISSING_ENTRY, "betrayal_paper_signal_id": matched.get("betrayal_paper_signal_id")}
    stop_price, take_profit = _stop_take_profit(signal=signal, betrayal_direction=str(matched.get("betrayal_direction")), entry_price=entry_price)
    if stop_price is None or take_profit is None:
        return {**base, "signal_status": SIGNAL_REJECTED_MISSING_STOP_OR_TP, "betrayal_paper_signal_id": matched.get("betrayal_paper_signal_id")}
    if outcome and allow_closed_outcomes:
        payload = _closed_outcome_payload(
            signal=signal,
            outcome=outcome,
            identity=matched,
            entry_price=entry_price,
            stop_price=stop_price,
            take_profit=take_profit,
        )
        return {
            **base,
            "signal_status": SIGNAL_CLOSED_OUTCOME_READY,
            "r98_status": BETRAYAL_CLOSED_PAPER_OUTCOME_PREPARED,
            "paper_status": "closed",
            "betrayal_paper_signal_id": matched.get("betrayal_paper_signal_id"),
            "prepared_outcome": payload,
        }
    if allow_open_tracking:
        payload = _open_tracking_payload(
            signal=signal,
            identity=matched,
            entry_price=entry_price,
            stop_price=stop_price,
            take_profit=take_profit,
        )
        return {
            **base,
            "signal_status": SIGNAL_OPEN_TRACKING_ONLY,
            "r98_status": BETRAYAL_OPEN_PAPER_TRACKING_PREPARED,
            "paper_status": "open",
            "betrayal_paper_signal_id": matched.get("betrayal_paper_signal_id"),
            "prepared_outcome": payload,
        }
    return None


def _closed_outcome_payload(
    *,
    signal: Any,
    outcome: Any,
    identity: Mapping[str, Any],
    entry_price: float,
    stop_price: float,
    take_profit: float,
) -> dict[str, Any]:
    closed_at = outcome.evaluated_at
    pnl = round(-float(outcome.pnl_pct), 4)
    result = "win" if pnl > 0 else "loss"
    paper_status = "closed"
    return _sanitize(
        {
            "outcome_id": _outcome_id(
                betrayal_paper_signal_id=str(identity.get("betrayal_paper_signal_id")),
                source_signal_id=signal.signal_id,
                source_timestamp=signal.timestamp,
                paper_status=paper_status,
                closed_at=closed_at,
            ),
            "betrayal_paper_signal_id": identity.get("betrayal_paper_signal_id"),
            "betrayal_paper_signal_hash": identity.get("betrayal_paper_signal_hash"),
            "symbol": signal.symbol,
            "timeframe": signal.timeframe,
            "direction": identity.get("betrayal_direction"),
            "entry_mode": identity.get("entry_mode"),
            "source_signal_id": signal.signal_id,
            "source_timestamp": signal.timestamp,
            "paper_entry_price": entry_price,
            "paper_stop_price": stop_price,
            "paper_take_profit_price": take_profit,
            "paper_exit_price": outcome.exit_price,
            "paper_exit_reason": "stop" if result == "loss" else "take_profit",
            "paper_pnl_pct": pnl,
            "paper_result_win_loss": result,
            "max_adverse_excursion_pct": round(-abs(float(outcome.mfe_pct)), 4),
            "max_favorable_excursion_pct": round(abs(float(outcome.mae_pct)), 4),
            "created_at": datetime.now(UTC).isoformat(),
            "closed_at": closed_at,
            "data_source": "local_archive_outcomes",
            "paper_status": paper_status,
            "review_only": True,
            "live_order_id": None,
            "real_order_placed": False,
            "order_payload_created": False,
            "execution_attempted": False,
            "network_allowed": False,
            "secrets_shown": False,
        }
    )


def _open_tracking_payload(
    *,
    signal: Any,
    identity: Mapping[str, Any],
    entry_price: float,
    stop_price: float,
    take_profit: float,
) -> dict[str, Any]:
    paper_status = "open"
    return _sanitize(
        {
            "outcome_id": _outcome_id(
                betrayal_paper_signal_id=str(identity.get("betrayal_paper_signal_id")),
                source_signal_id=signal.signal_id,
                source_timestamp=signal.timestamp,
                paper_status=paper_status,
                closed_at=None,
            ),
            "betrayal_paper_signal_id": identity.get("betrayal_paper_signal_id"),
            "betrayal_paper_signal_hash": identity.get("betrayal_paper_signal_hash"),
            "symbol": signal.symbol,
            "timeframe": signal.timeframe,
            "direction": identity.get("betrayal_direction"),
            "entry_mode": identity.get("entry_mode"),
            "source_signal_id": signal.signal_id,
            "source_timestamp": signal.timestamp,
            "paper_entry_price": entry_price,
            "paper_stop_price": stop_price,
            "paper_take_profit_price": take_profit,
            "paper_exit_price": None,
            "paper_exit_reason": None,
            "paper_pnl_pct": None,
            "paper_result_win_loss": None,
            "max_adverse_excursion_pct": None,
            "max_favorable_excursion_pct": None,
            "created_at": datetime.now(UTC).isoformat(),
            "closed_at": None,
            "data_source": "local_archive_signals",
            "paper_status": paper_status,
            "review_only": True,
            "live_order_id": None,
            "real_order_placed": False,
            "order_payload_created": False,
            "execution_attempted": False,
            "network_allowed": False,
            "secrets_shown": False,
        }
    )


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


def _match_identity(*, signal: Any, entry_mode: str, identities: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any] | None:
    betrayal_direction = _invert_direction(signal.direction)
    for identity in identities.values():
        if identity.get("audit_scope") != "direction_entry_mode":
            continue
        if identity.get("symbol") != signal.symbol or identity.get("timeframe") != signal.timeframe:
            continue
        if identity.get("original_direction") != signal.direction:
            continue
        if identity.get("betrayal_direction") != betrayal_direction:
            continue
        if identity.get("entry_mode") != entry_mode:
            continue
        return identity
    return None


def _aggregate_identity_for_signal(signal: Any, identities: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any] | None:
    for identity in identities.values():
        if identity.get("audit_scope") == "timeframe_aggregate" and identity.get("symbol") == signal.symbol and identity.get("timeframe") == signal.timeframe:
            return identity
    return None


def _entry_mode_from_signal(signal: Any) -> str | None:
    signal_id = str(signal.signal_id)
    for mode in ("fib_650", "fib_618", "fib_50", "fib_786", "ladder_close_50_618", "market_close"):
        if mode in signal_id:
            return mode
    return None


def _entry_price(signal: Any, entry_mode: str) -> float | None:
    value = getattr(signal, entry_mode, None)
    if value is None and entry_mode == "market_close":
        value = signal.signal_close
    if value is None and entry_mode == "ladder_close_50_618":
        values = [signal.signal_close, signal.fib_50, signal.fib_618]
        usable = [float(item) for item in values if item is not None]
        return round(sum(usable) / len(usable), 8) if usable else None
    return float(value) if value is not None else None


def _stop_take_profit(*, signal: Any, betrayal_direction: str, entry_price: float) -> tuple[float | None, float | None]:
    if betrayal_direction == "short":
        stop = float(signal.hammer_high)
        risk = abs(stop - entry_price)
        return stop, entry_price - risk
    if betrayal_direction == "long":
        stop = float(signal.hammer_low)
        risk = abs(entry_price - stop)
        return stop, entry_price + risk
    return None, None


def _outcome_id(
    *,
    betrayal_paper_signal_id: str,
    source_signal_id: str,
    source_timestamp: str,
    paper_status: str,
    closed_at: str | None,
) -> str:
    stable = {
        "betrayal_paper_signal_id": betrayal_paper_signal_id,
        "source_signal_id": source_signal_id,
        "source_timestamp": source_timestamp,
        "paper_status": paper_status,
        "closed_at": closed_at,
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _existing_outcome_ids(log_dir: Path) -> set[str]:
    records, _ = load_betrayal_paper_outcomes(log_dir=log_dir)
    return {str(record.get("outcome_id")) for record in records if record.get("outcome_id")}


def _detection_summary(
    *,
    detections: list[Mapping[str, Any]],
    captured: int,
    duplicate_skipped: int,
    aggregate_rejected: int,
    before_count: int,
    after_count: int,
    ledger_after: Mapping[str, Any],
) -> dict[str, Any]:
    matched = [row for row in detections if row.get("signal_status") in {SIGNAL_OPEN_TRACKING_ONLY, SIGNAL_CLOSED_OUTCOME_READY}]
    unmatched = [row for row in detections if row.get("signal_status") == SIGNAL_REJECTED_NO_MATCHING_IDENTITY]
    open_rows = [row for row in detections if row.get("signal_status") == SIGNAL_OPEN_TRACKING_ONLY]
    closed_rows = [row for row in detections if row.get("signal_status") == SIGNAL_CLOSED_OUTCOME_READY]
    ledger_summary = ledger_after.get("ledger_summary") if isinstance(ledger_after.get("ledger_summary"), dict) else {}
    return _sanitize(
        {
            "detection_source_status": _source_status_from_count(len(detections)),
            "detected_signal_count": len(detections),
            "matched_signal_count": len(matched),
            "unmatched_signal_count": len(unmatched),
            "prepared_open_tracking_count": len(open_rows),
            "prepared_closed_outcome_count": len(closed_rows),
            "captured_outcome_count": captured,
            "duplicate_skipped_count": duplicate_skipped,
            "aggregate_rejected_count": aggregate_rejected,
            "ledger_record_count_before": before_count,
            "ledger_record_count_after": after_count,
            "true_paper_outcomes_count": ledger_summary.get("valid_record_count", 0),
            "identities_with_outcomes": ledger_summary.get("identities_with_outcomes", 0),
            "live_ready_count": 0,
        }
    )


def _r98_statuses(summary: Mapping[str, Any], *, identities_count: int) -> list[str]:
    statuses = [BETRAYAL_PAPER_SIGNAL_DETECTOR_ONLY, BETRAYAL_SIGNAL_DETECTION_READY, BETRAYAL_LEDGER_READY]
    if identities_count:
        statuses.append(BETRAYAL_SCAFFOLD_IDENTITIES_FOUND)
    statuses.append(BETRAYAL_FRESH_SIGNALS_FOUND if int(summary.get("detected_signal_count") or 0) else BETRAYAL_NO_FRESH_SIGNALS_FOUND)
    if int(summary.get("matched_signal_count") or 0):
        statuses.append(BETRAYAL_SIGNAL_MATCHED_TO_IDENTITY)
    if int(summary.get("unmatched_signal_count") or 0):
        statuses.append(BETRAYAL_SIGNAL_UNMATCHED_TO_IDENTITY)
    if int(summary.get("prepared_open_tracking_count") or 0):
        statuses.append(BETRAYAL_OPEN_PAPER_TRACKING_PREPARED)
    if int(summary.get("prepared_closed_outcome_count") or 0):
        statuses.append(BETRAYAL_CLOSED_PAPER_OUTCOME_PREPARED)
    if int(summary.get("captured_outcome_count") or 0):
        statuses.append(BETRAYAL_OUTCOME_CAPTURED_LOCAL_ONLY)
    else:
        statuses.append(BETRAYAL_OUTCOME_WRITE_DRY_RUN_ONLY)
    if int(summary.get("duplicate_skipped_count") or 0):
        statuses.append(BETRAYAL_DUPLICATE_SIGNAL_SKIPPED)
    if int(summary.get("aggregate_rejected_count") or 0):
        statuses.append(BETRAYAL_AGGREGATE_DECOMPOSITION_REQUIRED)
    statuses.extend([BETRAYAL_NOT_LIVE_READY, BETRAYAL_NON_EXECUTABLE_ONLY])
    return list(dict.fromkeys(statuses))


def _top_matched_identities(detections: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in detections:
        signal_id = row.get("betrayal_paper_signal_id")
        if signal_id and row.get("signal_status") in {SIGNAL_OPEN_TRACKING_ONLY, SIGNAL_CLOSED_OUTCOME_READY}:
            counts[str(signal_id)] = counts.get(str(signal_id), 0) + 1
    return [
        {"betrayal_paper_signal_id": signal_id, "matched_signal_count": count, "live_ready": False, "executable": False}
        for signal_id, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _source_status_from_count(count: int) -> str:
    return BETRAYAL_FRESH_SIGNALS_FOUND if count else BETRAYAL_NO_FRESH_SIGNALS_FOUND


def _next_action(summary: Mapping[str, Any]) -> str:
    if int(summary.get("detected_signal_count") or 0) == 0:
        return "R99 Betrayal Directional Decomposition for 222m or detector source wiring"
    return "R99 Betrayal Outcome Capture Scheduler / Paper Maturity Snapshot"


def _invert_direction(direction: str) -> str:
    return "short" if direction == "long" else "long"


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
        if "live_order_id" in sanitized:
            sanitized["live_order_id"] = None
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, tuple):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, Path):
        return str(payload)
    return payload
