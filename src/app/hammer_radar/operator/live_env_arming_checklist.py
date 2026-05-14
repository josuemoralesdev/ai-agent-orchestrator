"""R86 live env arming checklist and manual funding confirmation.

This module records local, non-secret operator confirmations only. It never
changes env files, checks balances, calls Binance, creates order payloads, or
enables live execution.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID
from src.app.hammer_radar.operator.tiny_live_ticket_builder import build_tiny_live_ticket

PHASE = "R86"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "LIVE_ENV_ARMING_CHECKLIST_MANUAL_FUNDING_CONFIRMATION_ONLY_NO_ORDER"
CHECKLISTS_FILENAME = "live_env_arming_checklists.ndjson"

CHECKLIST_REQUIRED = "CHECKLIST_REQUIRED"
CHECKLIST_DRY_RUN_ONLY = "CHECKLIST_DRY_RUN_ONLY"
CHECKLIST_RECORDED_FOR_REVIEW = "CHECKLIST_RECORDED_FOR_REVIEW"
CHECKLIST_BLOCKED_BY_MISSING_CONFIRMATIONS = "CHECKLIST_BLOCKED_BY_MISSING_CONFIRMATIONS"
CHECKLIST_INVALID_CONFIRMATION = "CHECKLIST_INVALID_CONFIRMATION"
CHECKLIST_EXPIRED = "CHECKLIST_EXPIRED"
CHECKLIST_NON_EXECUTABLE_REVIEW_ONLY = "CHECKLIST_NON_EXECUTABLE_REVIEW_ONLY"

MANUAL_FUNDING_CONFIRMATION_REQUIRED = "MANUAL_FUNDING_CONFIRMATION_REQUIRED"
MANUAL_FUNDING_CONFIRMED_BY_OPERATOR = "MANUAL_FUNDING_CONFIRMED_BY_OPERATOR"
MANUAL_FUNDING_NOT_CONFIRMED = "MANUAL_FUNDING_NOT_CONFIRMED"
MANUAL_FUNDING_CONFIRMATION_INVALID = "MANUAL_FUNDING_CONFIRMATION_INVALID"
MANUAL_FUNDING_CHECK_DEFERRED_NO_NETWORK = "MANUAL_FUNDING_CHECK_DEFERRED_NO_NETWORK"

LIVE_ENV_LOCKED_SAFE_FOR_PREFLIGHT = "LIVE_ENV_LOCKED_SAFE_FOR_PREFLIGHT"
LIVE_ENV_ARMING_CONFIRMATION_REQUIRED = "LIVE_ENV_ARMING_CONFIRMATION_REQUIRED"
LIVE_ENV_ARMING_CONFIRMED_FOR_REVIEW = "LIVE_ENV_ARMING_CONFIRMED_FOR_REVIEW"
LIVE_ENV_NOT_ARMED = "LIVE_ENV_NOT_ARMED"
LIVE_ENV_CONFIRMATION_INVALID = "LIVE_ENV_CONFIRMATION_INVALID"

MANUAL_FUNDING_PHRASE = "CONFIRM_MANUAL_FUNDING BTCUSDT MAX_MARGIN_44 MAX_LOSS_4.44 NO_BALANCE_CHECK"
LIVE_ENV_REVIEW_PHRASE = "CONFIRM_LIVE_ENV_REVIEW_ONLY KILL_SWITCH_ON LIVE_EXEC_DISABLED NO_ORDER"
MAX_LOSS_ACK_PHRASE = "ACK_MAX_LOSS_4.44_USDT"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R86 records manual checklist confirmations only. No orders, no env changes, no network, no Binance."


def build_live_env_arming_checklist(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    risk_contract_hash: str | None = None,
    manual_funding_phrase: str | None = None,
    live_env_review_phrase: str | None = None,
    max_loss_ack_phrase: str | None = None,
    exact_candidate_ack_phrase: str | None = None,
    operator_note: str | None = None,
    dry_run: bool = True,
    write: bool = False,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    created_at = datetime.now(UTC)
    ticket = build_tiny_live_ticket(candidate_id=candidate_id, dry_run=True, write=False, log_dir=resolved_log_dir)
    expected_hash = str(ticket.get("risk_contract_hash") or "")
    expected_candidate_id = str(ticket.get("candidate_id") or candidate_id)
    required = required_phrases(candidate_id=expected_candidate_id, risk_contract_hash=expected_hash)
    confirmations = _confirmation_statuses(
        expected_hash=expected_hash,
        supplied_hash=risk_contract_hash,
        required=required,
        manual_funding_phrase=manual_funding_phrase,
        live_env_review_phrase=live_env_review_phrase,
        max_loss_ack_phrase=max_loss_ack_phrase,
        exact_candidate_ack_phrase=exact_candidate_ack_phrase,
    )
    checklist_status = _checklist_status(confirmations=confirmations, dry_run=dry_run, write=write)
    checklist = _checklist_payload(
        created_at=created_at,
        ticket=ticket,
        required=required,
        confirmations=confirmations,
        checklist_status=checklist_status,
        operator_note=operator_note,
        dry_run=dry_run,
        write=write,
        log_dir=resolved_log_dir,
    )
    checklist_written = False
    if write and not dry_run and checklist_status == CHECKLIST_RECORDED_FOR_REVIEW:
        append_live_env_arming_checklist(checklist, log_dir=resolved_log_dir)
        checklist_written = True
        checklist["checklist_written"] = True
    return _sanitize(
        {
            **checklist,
            "checklist_written": checklist_written,
            "notes": [
                NO_ORDER_NOTE,
                "Manual funding confirmation is not account balance verification.",
                "Recorded checklist confirmations are review-only and non-executable.",
            ],
            **_safety_fields(),
        }
    )


def build_live_env_arming_checklist_status(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    limit: int = 20,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    template = build_live_env_arming_checklist(candidate_id=candidate_id, dry_run=True, write=False, log_dir=resolved_log_dir)
    records = load_live_env_arming_checklists(limit=limit, candidate_id=candidate_id, log_dir=resolved_log_dir)
    latest = records[0] if records else None
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "checklist_path": str(live_env_arming_checklists_path(resolved_log_dir)),
            "summary": {
                "checklists_returned": len(records),
                "written_checklist_records": len(load_live_env_arming_checklists(limit=0, candidate_id=candidate_id, log_dir=resolved_log_dir)),
                "latest_checklist_status": latest.get("checklist_status") if latest else CHECKLIST_REQUIRED,
                "manual_funding_status": latest.get("manual_funding_status") if latest else MANUAL_FUNDING_CONFIRMATION_REQUIRED,
                "live_env_arming_status": latest.get("live_env_arming_status") if latest else LIVE_ENV_ARMING_CONFIRMATION_REQUIRED,
            },
            "latest_checklist": latest,
            "checklists": records,
            "required_phrases": template.get("required_phrases"),
            "notes": [NO_ORDER_NOTE],
            **_safety_fields(),
        }
    )


def required_phrases(*, candidate_id: str, risk_contract_hash: str) -> dict[str, str]:
    return {
        "manual_funding_phrase": MANUAL_FUNDING_PHRASE,
        "live_env_review_phrase": LIVE_ENV_REVIEW_PHRASE,
        "max_loss_ack_phrase": MAX_LOSS_ACK_PHRASE,
        "exact_candidate_ack_phrase": f"ACK_TINY_LIVE_CANDIDATE {candidate_id} {risk_contract_hash}",
    }


def live_env_arming_checklists_path(log_dir: str | Path | None = None) -> Path:
    return get_log_dir(log_dir, use_env=True) / CHECKLISTS_FILENAME


def append_live_env_arming_checklist(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = live_env_arming_checklists_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize(dict(record)), sort_keys=True) + "\n")


def load_live_env_arming_checklists(
    *,
    limit: int = 20,
    candidate_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = live_env_arming_checklists_path(log_dir)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if candidate_id and record.get("candidate_id") != candidate_id:
                continue
            records.append(_sanitize(record))
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def format_live_env_arming_checklist_text(payload: Mapping[str, Any]) -> str:
    required = payload.get("required_phrases") if isinstance(payload.get("required_phrases"), dict) else {}
    return "\n".join(
        [
            f"R86 Live Env Arming Checklist: {payload.get('status')}",
            str(payload.get("execution_mode")),
            f"candidate_id: {payload.get('candidate_id')}",
            f"risk_contract_hash: {payload.get('risk_contract_hash')}",
            f"checklist_status: {payload.get('checklist_status')}",
            f"manual_funding_status: {payload.get('manual_funding_status')}",
            f"live_env_arming_status: {payload.get('live_env_arming_status')}",
            f"manual_funding_phrase_required: {required.get('manual_funding_phrase')}",
            f"live_env_review_phrase_required: {required.get('live_env_review_phrase')}",
            f"max_loss_ack_phrase_required: {required.get('max_loss_ack_phrase')}",
            f"exact_candidate_ack_phrase_required: {required.get('exact_candidate_ack_phrase')}",
            f"dry_run: {payload.get('dry_run')} write: {payload.get('write')} checklist_written: {payload.get('checklist_written')}",
            f"executable: {payload.get('executable')} review_only: {payload.get('review_only')}",
            "No order placed. real_order_placed=false execution_attempted=false order_payload_created=false network_allowed=false secrets_shown=false.",
            NO_ORDER_NOTE,
        ]
    )


def _confirmation_statuses(
    *,
    expected_hash: str,
    supplied_hash: str | None,
    required: Mapping[str, str],
    manual_funding_phrase: str | None,
    live_env_review_phrase: str | None,
    max_loss_ack_phrase: str | None,
    exact_candidate_ack_phrase: str | None,
) -> dict[str, Any]:
    phrase_checks = {
        "manual_funding_phrase": _phrase_status(manual_funding_phrase, required["manual_funding_phrase"]),
        "live_env_review_phrase": _phrase_status(live_env_review_phrase, required["live_env_review_phrase"]),
        "max_loss_ack_phrase": _phrase_status(max_loss_ack_phrase, required["max_loss_ack_phrase"]),
        "exact_candidate_ack_phrase": _phrase_status(exact_candidate_ack_phrase, required["exact_candidate_ack_phrase"]),
    }
    hash_status = "CONFIRMED" if supplied_hash in (None, "", expected_hash) else "INVALID"
    blockers = []
    for key, status in phrase_checks.items():
        if status == "MISSING":
            blockers.append(f"{key}_missing")
        elif status == "INVALID":
            blockers.append(f"{key}_invalid")
    if hash_status == "INVALID":
        blockers.append("risk_contract_hash_mismatch")
    manual_status = (
        MANUAL_FUNDING_CONFIRMED_BY_OPERATOR
        if phrase_checks["manual_funding_phrase"] == "CONFIRMED" and hash_status != "INVALID"
        else MANUAL_FUNDING_CONFIRMATION_INVALID
        if phrase_checks["manual_funding_phrase"] == "INVALID" or hash_status == "INVALID"
        else MANUAL_FUNDING_CONFIRMATION_REQUIRED
    )
    live_status = (
        LIVE_ENV_ARMING_CONFIRMED_FOR_REVIEW
        if phrase_checks["live_env_review_phrase"] == "CONFIRMED" and hash_status != "INVALID"
        else LIVE_ENV_CONFIRMATION_INVALID
        if phrase_checks["live_env_review_phrase"] == "INVALID" or hash_status == "INVALID"
        else LIVE_ENV_ARMING_CONFIRMATION_REQUIRED
    )
    return {
        "phrase_checks": phrase_checks,
        "risk_contract_hash_status": hash_status,
        "manual_funding_status": manual_status,
        "live_env_arming_status": live_status,
        "blockers": blockers,
        "all_confirmed": not blockers and all(status == "CONFIRMED" for status in phrase_checks.values()),
        "any_invalid": any(status == "INVALID" for status in phrase_checks.values()) or hash_status == "INVALID",
    }


def _phrase_status(value: str | None, expected: str) -> str:
    if value is None or not str(value).strip():
        return "MISSING"
    if str(value).strip() == expected:
        return "CONFIRMED"
    return "INVALID"


def _checklist_status(*, confirmations: Mapping[str, Any], dry_run: bool, write: bool) -> str:
    if confirmations.get("any_invalid"):
        return CHECKLIST_INVALID_CONFIRMATION
    if not confirmations.get("all_confirmed"):
        return CHECKLIST_BLOCKED_BY_MISSING_CONFIRMATIONS
    if dry_run or not write:
        return CHECKLIST_DRY_RUN_ONLY
    return CHECKLIST_RECORDED_FOR_REVIEW


def _checklist_payload(
    *,
    created_at: datetime,
    ticket: Mapping[str, Any],
    required: Mapping[str, str],
    confirmations: Mapping[str, Any],
    checklist_status: str,
    operator_note: str | None,
    dry_run: bool,
    write: bool,
    log_dir: Path,
) -> dict[str, Any]:
    candidate_id = str(ticket.get("candidate_id") or DEFAULT_CANDIDATE_ID)
    risk_hash = str(ticket.get("risk_contract_hash") or "")
    checklist_id = _checklist_id(candidate_id=candidate_id, risk_contract_hash=risk_hash)
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "checklist_id": checklist_id,
            "checklist_status": checklist_status,
            "candidate_id": candidate_id,
            "ticket_id": ticket.get("ticket_id"),
            "risk_contract_hash": risk_hash,
            "approval_phrase_required": ticket.get("approval_phrase_required"),
            "required_phrases": dict(required),
            "manual_funding_status": confirmations.get("manual_funding_status"),
            "live_env_arming_status": confirmations.get("live_env_arming_status"),
            "operator_confirmations": confirmations.get("phrase_checks"),
            "funding_confirmation": confirmations.get("phrase_checks", {}).get("manual_funding_phrase"),
            "live_env_confirmation": confirmations.get("phrase_checks", {}).get("live_env_review_phrase"),
            "kill_switch_confirmation": confirmations.get("phrase_checks", {}).get("live_env_review_phrase"),
            "max_loss_acknowledgement": confirmations.get("phrase_checks", {}).get("max_loss_ack_phrase"),
            "max_margin_acknowledgement": confirmations.get("phrase_checks", {}).get("manual_funding_phrase"),
            "isolated_margin_acknowledgement": confirmations.get("phrase_checks", {}).get("manual_funding_phrase"),
            "no_network_acknowledgement": confirmations.get("phrase_checks", {}).get("manual_funding_phrase"),
            "no_order_acknowledgement": confirmations.get("phrase_checks", {}).get("live_env_review_phrase"),
            "created_at": created_at.isoformat(),
            "expires_at": (created_at + timedelta(hours=24)).isoformat(),
            "operator_note": operator_note or "",
            "dry_run": bool(dry_run),
            "write": bool(write),
            "checklist_written": False,
            "checklist_path": str(live_env_arming_checklists_path(log_dir)),
            "review_only": True,
            "executable": False,
            "env_modified": False,
            "account_balance_checked": False,
            "account_balance_source": "not_checked_no_network",
            "manual_funding_limitations": "Manual confirmation is not account-balance verification.",
            "blockers": confirmations.get("blockers", []),
            **_safety_fields(),
        }
    )


def _checklist_id(*, candidate_id: str, risk_contract_hash: str) -> str:
    digest = hashlib.sha256(f"{candidate_id}|{risk_contract_hash}|R86".encode("utf-8")).hexdigest()[:20]
    return f"r86-live-env-{digest}"


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
            "account_balance_checked",
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
    return payload
