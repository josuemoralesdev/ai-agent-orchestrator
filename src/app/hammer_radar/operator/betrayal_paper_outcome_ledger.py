"""R97 betrayal true-paper outcome ledger and tracking loop.

This module records only explicitly supplied local paper outcomes for R96
betrayal identities. It never creates orders, executable payloads, Binance
requests, balance checks, env mutations, or live readiness.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_true_paper_tracking import (
    PAPER_IDENTITY_CREATED,
    PAPER_READY_FOR_REVIEW,
    PAPER_TRACKING_READY,
    PRIMARY_MIN_TRUE_PAPER_SAMPLES,
    WATCHLIST_MIN_TRUE_PAPER_SAMPLES,
    build_betrayal_true_paper_scaffold,
    betrayal_true_paper_outcomes_path,
)

PHASE = "R97"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "BETRAYAL_PAPER_OUTCOME_LEDGER_ONLY_NO_ORDER"

BETRAYAL_PAPER_OUTCOME_LEDGER_ONLY = "BETRAYAL_PAPER_OUTCOME_LEDGER_ONLY"
BETRAYAL_LEDGER_SCHEMA_DECLARED = "BETRAYAL_LEDGER_SCHEMA_DECLARED"
BETRAYAL_LEDGER_EMPTY = "BETRAYAL_LEDGER_EMPTY"
BETRAYAL_LEDGER_RECORDS_FOUND = "BETRAYAL_LEDGER_RECORDS_FOUND"
BETRAYAL_OUTCOME_WRITE_DRY_RUN_ONLY = "BETRAYAL_OUTCOME_WRITE_DRY_RUN_ONLY"
BETRAYAL_OUTCOME_VALID_FOR_LOCAL_WRITE = "BETRAYAL_OUTCOME_VALID_FOR_LOCAL_WRITE"
BETRAYAL_OUTCOME_WRITTEN_LOCAL_ONLY = "BETRAYAL_OUTCOME_WRITTEN_LOCAL_ONLY"
BETRAYAL_OUTCOME_INVALID = "BETRAYAL_OUTCOME_INVALID"
BETRAYAL_OUTCOME_REJECTED_NO_MATCHING_IDENTITY = "BETRAYAL_OUTCOME_REJECTED_NO_MATCHING_IDENTITY"
BETRAYAL_PAPER_OUTCOMES_INSUFFICIENT = "BETRAYAL_PAPER_OUTCOMES_INSUFFICIENT"
BETRAYAL_PAPER_TRACKING_LOOP_READY = "BETRAYAL_PAPER_TRACKING_LOOP_READY"
BETRAYAL_NOT_LIVE_READY = "BETRAYAL_NOT_LIVE_READY"
BETRAYAL_NON_EXECUTABLE_ONLY = "BETRAYAL_NON_EXECUTABLE_ONLY"

PAPER_EVIDENCE_EMPTY = "PAPER_EVIDENCE_EMPTY"
PAPER_EVIDENCE_INSUFFICIENT = "PAPER_EVIDENCE_INSUFFICIENT"
PAPER_EVIDENCE_MIN_SAMPLE_REACHED = "PAPER_EVIDENCE_MIN_SAMPLE_REACHED"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R97 is betrayal paper outcome ledger/review only. No orders, no payloads, no env changes, no network, no Binance."


def build_betrayal_paper_outcome_status(
    *,
    signal_id: str | None = None,
    recent: int = 20,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC).isoformat()
    scaffold = build_betrayal_true_paper_scaffold(dry_run=True, write=False, log_dir=resolved_log_dir)
    identities = _identity_map(scaffold)
    records, invalid_records = load_betrayal_paper_outcomes(log_dir=resolved_log_dir)
    valid_records = [record for record in records if _record_matches_identity(record, identities)]
    identity_summaries = _identity_summaries(identities=identities, records=valid_records)
    if signal_id:
        identity_summaries = [row for row in identity_summaries if row.get("betrayal_paper_signal_id") == signal_id]
        valid_records = [row for row in valid_records if row.get("betrayal_paper_signal_id") == signal_id]
    ledger_path = betrayal_true_paper_outcomes_path(resolved_log_dir)
    summary = _ledger_summary(
        ledger_path=ledger_path,
        records=records,
        valid_records=valid_records,
        invalid_records=invalid_records,
        identity_summaries=identity_summaries,
        identities_count=len(identities),
    )
    payload = {
        "status": "OK",
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "generated_at": generated_at,
        "r97_statuses": _r97_statuses(summary),
        "ledger_path": str(ledger_path),
        "ledger_schema": betrayal_paper_outcome_schema(),
        "ledger_summary": summary,
        "identity_summaries": identity_summaries,
        "top_identity_summaries": _top_identities(identity_summaries),
        "recent_outcomes": valid_records[-max(0, int(recent)) :],
        "tracking_loop_status": BETRAYAL_PAPER_TRACKING_LOOP_READY,
        "next_action_recommendation": _next_action(identity_summaries),
        "notes": [
            NO_ORDER_NOTE,
            "Status reads never create paper outcomes.",
            "Aggregate-only identities require directional decomposition before outcomes are accepted.",
        ],
        "review_only": True,
        "executable": False,
        "env_modified": False,
        "order_type": "not_created",
        **_safety_fields(),
    }
    return _sanitize(payload)


def record_betrayal_paper_outcome(
    *,
    outcome: Mapping[str, Any] | None,
    dry_run: bool = True,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    ledger_path = betrayal_true_paper_outcomes_path(resolved_log_dir)
    scaffold = build_betrayal_true_paper_scaffold(dry_run=True, write=False, log_dir=resolved_log_dir)
    identities = _identity_map(scaffold)
    errors, normalized = validate_betrayal_paper_outcome(outcome, identities=identities)
    record_status = BETRAYAL_OUTCOME_INVALID if errors else BETRAYAL_OUTCOME_VALID_FOR_LOCAL_WRITE
    outcome_written = False
    if errors and any("no matching betrayal paper identity" in error for error in errors):
        record_status = BETRAYAL_OUTCOME_REJECTED_NO_MATCHING_IDENTITY
    if dry_run or not write:
        if not errors:
            record_status = BETRAYAL_OUTCOME_WRITE_DRY_RUN_ONLY
    elif not errors:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(normalized, sort_keys=True, separators=(",", ":")) + "\n")
        outcome_written = True
        record_status = BETRAYAL_OUTCOME_WRITTEN_LOCAL_ONLY
    status_payload = build_betrayal_paper_outcome_status(log_dir=resolved_log_dir)
    payload = {
        "status": "OK" if not errors else "ERROR",
        "phase": PHASE,
        "system": SYSTEM,
        "execution_mode": EXECUTION_MODE,
        "record_status": record_status,
        "validation_errors": errors,
        "validated_outcome": normalized if normalized else None,
        "outcome_written": outcome_written,
        "dry_run": bool(dry_run),
        "write": bool(write),
        "ledger_path": str(ledger_path),
        "ledger_summary": status_payload.get("ledger_summary"),
        "review_only": True,
        "executable": False,
        "env_modified": False,
        "order_type": "not_created",
        **_safety_fields(),
    }
    return _sanitize(payload)


def load_betrayal_paper_outcomes(*, log_dir: str | Path | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path = betrayal_true_paper_outcomes_path(log_dir)
    records: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    if not path.exists():
        return records, invalid
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                invalid.append({"line_number": line_number, "error": exc.__class__.__name__})
                continue
            if isinstance(record, dict):
                records.append(_sanitize(record))
            else:
                invalid.append({"line_number": line_number, "error": "record_not_object"})
    return records, invalid


def validate_betrayal_paper_outcome(
    outcome: Mapping[str, Any] | None,
    *,
    identities: Mapping[str, Mapping[str, Any]],
) -> tuple[list[str], dict[str, Any]]:
    if not isinstance(outcome, Mapping):
        return ["outcome object is required for validation/write"], {}
    record = dict(outcome)
    errors: list[str] = []
    signal_id = str(record.get("betrayal_paper_signal_id") or "")
    identity = identities.get(signal_id)
    if not identity:
        errors.append("no matching betrayal paper identity")
    else:
        if identity.get("aggregate_requires_directional_decomposition"):
            errors.append("aggregate-only betrayal identity requires directional decomposition before outcomes")
        _expect_equal(errors, record, "symbol", identity.get("symbol"))
        _expect_equal(errors, record, "timeframe", identity.get("timeframe"))
        if identity.get("audit_scope") == "direction_entry_mode":
            _expect_equal(errors, record, "direction", identity.get("betrayal_direction"))
            _expect_equal(errors, record, "entry_mode", identity.get("entry_mode"))
        supplied_hash = record.get("betrayal_paper_signal_hash") or record.get("candidate_hash")
        if supplied_hash and supplied_hash != identity.get("betrayal_paper_signal_hash"):
            errors.append("betrayal_paper_signal_hash does not match scaffold identity")
        record["betrayal_paper_signal_hash"] = identity.get("betrayal_paper_signal_hash")
    for key in (
        "outcome_id",
        "betrayal_paper_signal_id",
        "source_signal_id",
        "source_timestamp",
        "paper_exit_reason",
        "created_at",
        "data_source",
    ):
        if not record.get(key):
            errors.append(f"{key} is required")
    for key in ("paper_entry_price", "paper_stop_price", "paper_take_profit_price", "paper_exit_price", "paper_pnl_pct"):
        if not _is_number(record.get(key)):
            errors.append(f"{key} must be numeric")
    for key in ("max_adverse_excursion_pct", "max_favorable_excursion_pct"):
        if record.get(key) is not None and not _is_number(record.get(key)):
            errors.append(f"{key} must be numeric when supplied")
    if record.get("paper_result_win_loss") not in {"win", "loss"}:
        errors.append("paper_result_win_loss must be win or loss")
    if record.get("review_only") is not True:
        errors.append("review_only must remain true")
    if record.get("live_order_id") is not None:
        errors.append("live_order_id must remain null")
    for key in ("real_order_placed", "order_payload_created", "execution_attempted", "network_allowed", "secrets_shown"):
        if record.get(key) is not False:
            errors.append(f"{key} must remain false")
    normalized = _normalize_outcome(record)
    return errors, normalized


def betrayal_paper_outcome_schema() -> dict[str, Any]:
    return {
        "outcome_id": "string",
        "betrayal_paper_signal_id": "string",
        "betrayal_paper_signal_hash": "string",
        "symbol": "string",
        "timeframe": "string",
        "direction": "string",
        "entry_mode": "string",
        "source_signal_id": "string",
        "source_timestamp": "iso8601",
        "paper_entry_price": "number",
        "paper_stop_price": "number",
        "paper_take_profit_price": "number",
        "paper_exit_price": "number",
        "paper_exit_reason": "string",
        "paper_pnl_pct": "number",
        "paper_result_win_loss": "win|loss",
        "max_adverse_excursion_pct": "number|null",
        "max_favorable_excursion_pct": "number|null",
        "created_at": "iso8601",
        "closed_at": "iso8601|null",
        "data_source": "string",
        "review_only": True,
        "live_order_id": None,
        "real_order_placed": False,
        "order_payload_created": False,
        "execution_attempted": False,
        "network_allowed": False,
        "secrets_shown": False,
    }


def format_betrayal_paper_outcome_status_text(payload: Mapping[str, Any]) -> str:
    summary = payload.get("ledger_summary") if isinstance(payload.get("ledger_summary"), dict) else {}
    top = payload.get("top_identity_summaries") if isinstance(payload.get("top_identity_summaries"), list) else []
    lines = [
        f"R97 Betrayal Paper Outcome Ledger status: {payload.get('status')}",
        str(payload.get("execution_mode")),
        f"ledger_path: {payload.get('ledger_path')}",
        f"ledger_record_count: {summary.get('ledger_record_count')}",
        f"valid_record_count: {summary.get('valid_record_count')}",
        f"invalid_record_count: {summary.get('invalid_record_count')}",
        "top_identities:",
    ]
    if not top:
        lines.append("  none")
    for row in top[:8]:
        lines.append(
            "  "
            f"{row.get('betrayal_paper_signal_id')} outcomes={row.get('true_paper_outcomes_count')} "
            f"progress={row.get('true_paper_sample_progress_pct')}% "
            f"win_rate={row.get('paper_win_rate_pct')} total_pnl={row.get('paper_total_pnl_pct')} "
            f"maturity={row.get('maturity_status')} live_ready={row.get('live_ready')}"
        )
    lines.extend(
        [
            f"tracking_loop_status: {payload.get('tracking_loop_status')}",
            f"next_action_recommendation: {payload.get('next_action_recommendation')}",
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            "No-order/no-network/no-env-change safety note: R97 is local paper ledger only.",
            NO_ORDER_NOTE,
        ]
    )
    return "\n".join(lines)


def _identity_map(scaffold: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    candidates = scaffold.get("scaffold_candidates") if isinstance(scaffold.get("scaffold_candidates"), list) else []
    return {str(row.get("betrayal_paper_signal_id")): row for row in candidates if isinstance(row, dict) and row.get("betrayal_paper_signal_id")}


def _identity_summaries(*, identities: Mapping[str, Mapping[str, Any]], records: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, list[Mapping[str, Any]]] = {signal_id: [] for signal_id in identities}
    for record in records:
        signal_id = str(record.get("betrayal_paper_signal_id") or "")
        if signal_id in by_id:
            by_id[signal_id].append(record)
    summaries = [_identity_summary(identity, by_id.get(signal_id, [])) for signal_id, identity in identities.items()]
    return summaries


def _identity_summary(identity: Mapping[str, Any], records: list[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(records)
    min_samples = int(identity.get("true_paper_min_samples_required") or PRIMARY_MIN_TRUE_PAPER_SAMPLES)
    pnl_values = [float(row.get("paper_pnl_pct")) for row in records if _is_number(row.get("paper_pnl_pct"))]
    wins = sum(1 for row in records if row.get("paper_result_win_loss") == "win")
    evidence_status = PAPER_EVIDENCE_EMPTY
    maturity_status = identity.get("maturity_status") or PAPER_TRACKING_READY
    if count:
        evidence_status = PAPER_EVIDENCE_MIN_SAMPLE_REACHED if count >= min_samples else PAPER_EVIDENCE_INSUFFICIENT
        maturity_status = PAPER_READY_FOR_REVIEW if count >= min_samples and not identity.get("aggregate_requires_directional_decomposition") else BETRAYAL_PAPER_OUTCOMES_INSUFFICIENT
    if identity.get("aggregate_requires_directional_decomposition"):
        maturity_status = PAPER_IDENTITY_CREATED
    summary: dict[str, Any] = {
        "betrayal_paper_signal_id": identity.get("betrayal_paper_signal_id"),
        "betrayal_paper_signal_hash": identity.get("betrayal_paper_signal_hash"),
        "symbol": identity.get("symbol"),
        "timeframe": identity.get("timeframe"),
        "direction": identity.get("betrayal_direction"),
        "entry_mode": identity.get("entry_mode"),
        "maturity_status": maturity_status,
        "true_paper_outcomes_count": count,
        "true_paper_min_samples_required": min_samples,
        "true_paper_sample_progress_pct": round(min(100.0, (count / min_samples) * 100.0), 2) if min_samples else 0.0,
        "paper_evidence_status": evidence_status,
        "aggregate_requires_directional_decomposition": bool(identity.get("aggregate_requires_directional_decomposition")),
        "live_ready": False,
        "executable": False,
    }
    if pnl_values:
        summary.update(
            {
                "paper_win_rate_pct": round((wins / count) * 100.0, 2) if count else None,
                "paper_avg_pnl_pct": round(sum(pnl_values) / len(pnl_values), 4),
                "paper_total_pnl_pct": round(sum(pnl_values), 4),
                "paper_best_pnl_pct": round(max(pnl_values), 4),
                "paper_worst_pnl_pct": round(min(pnl_values), 4),
            }
        )
    return _sanitize(summary)


def _ledger_summary(
    *,
    ledger_path: Path,
    records: list[Mapping[str, Any]],
    valid_records: list[Mapping[str, Any]],
    invalid_records: list[Mapping[str, Any]],
    identity_summaries: list[Mapping[str, Any]],
    identities_count: int,
) -> dict[str, Any]:
    with_outcomes = [row for row in identity_summaries if int(row.get("true_paper_outcomes_count") or 0) > 0]
    min_reached = [row for row in identity_summaries if row.get("paper_evidence_status") == PAPER_EVIDENCE_MIN_SAMPLE_REACHED]
    return _sanitize(
        {
            "ledger_path": str(ledger_path),
            "ledger_exists": ledger_path.exists(),
            "ledger_record_count": len(records) + len(invalid_records),
            "valid_record_count": len(valid_records),
            "invalid_record_count": len(invalid_records) + max(0, len(records) - len(valid_records)),
            "identities_tracked": identities_count,
            "identities_with_outcomes": len(with_outcomes),
            "identities_min_sample_reached": len(min_reached),
            "top_identity_by_paper_pnl": _top_by(identity_summaries, "paper_total_pnl_pct"),
            "top_identity_by_paper_win_rate": _top_by(identity_summaries, "paper_win_rate_pct"),
            "audit_evidence_only_count": identities_count,
            "true_paper_required_count": identities_count,
        }
    )


def _top_identities(identity_summaries: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in sorted(
        identity_summaries,
        key=lambda row: (
            -int(row.get("true_paper_outcomes_count") or 0),
            -float(row.get("paper_total_pnl_pct") or 0.0),
        ),
    )[:8]
    ]


def _top_by(rows: list[Mapping[str, Any]], key: str) -> dict[str, Any] | None:
    eligible = [row for row in rows if row.get(key) is not None]
    if not eligible:
        return None
    return dict(max(eligible, key=lambda row: float(row.get(key) or 0.0)))


def _record_matches_identity(record: Mapping[str, Any], identities: Mapping[str, Mapping[str, Any]]) -> bool:
    errors, _ = validate_betrayal_paper_outcome(record, identities=identities)
    return not errors


def _normalize_outcome(record: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    for key in ("paper_entry_price", "paper_stop_price", "paper_take_profit_price", "paper_exit_price", "paper_pnl_pct"):
        if _is_number(normalized.get(key)):
            normalized[key] = float(normalized[key])
    for key in ("max_adverse_excursion_pct", "max_favorable_excursion_pct"):
        if _is_number(normalized.get(key)):
            normalized[key] = float(normalized[key])
    normalized["review_only"] = True
    normalized["live_order_id"] = None
    normalized["real_order_placed"] = False
    normalized["order_payload_created"] = False
    normalized["execution_attempted"] = False
    normalized["network_allowed"] = False
    normalized["secrets_shown"] = False
    return _sanitize(normalized)


def _r97_statuses(summary: Mapping[str, Any]) -> list[str]:
    statuses = [BETRAYAL_PAPER_OUTCOME_LEDGER_ONLY, BETRAYAL_LEDGER_SCHEMA_DECLARED]
    statuses.append(BETRAYAL_LEDGER_RECORDS_FOUND if int(summary.get("ledger_record_count") or 0) else BETRAYAL_LEDGER_EMPTY)
    statuses.extend([BETRAYAL_PAPER_TRACKING_LOOP_READY, BETRAYAL_NOT_LIVE_READY, BETRAYAL_NON_EXECUTABLE_ONLY])
    return list(dict.fromkeys(statuses))


def _next_action(identity_summaries: list[Mapping[str, Any]]) -> str:
    if any(int(row.get("true_paper_outcomes_count") or 0) >= int(row.get("true_paper_min_samples_required") or WATCHLIST_MIN_TRUE_PAPER_SAMPLES) for row in identity_summaries):
        return "R98 Betrayal Maturity Evaluator"
    return "R98 Betrayal Paper Signal Detector / Outcome Capture Loop"


def _expect_equal(errors: list[str], record: Mapping[str, Any], key: str, expected: Any) -> None:
    if record.get(key) != expected:
        errors.append(f"{key} must match scaffold identity")


def _is_number(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


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
