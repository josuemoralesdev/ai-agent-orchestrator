"""Telegram first-live approval challenge records.

R48 challenge approval records exact approval intent only. It never executes,
enables live switches, restarts services, or calls Binance.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_runbook import build_first_live_runbook
from src.app.hammer_radar.operator.live_approval import evaluate_live_approval_request
from src.app.hammer_radar.operator.live_preflight import PROMOTED_STRATEGY_KEY, build_promoted_strategy_preflight

CHALLENGES_FILENAME = "telegram_approval_challenges.ndjson"
ENV_CHALLENGE_TTL_SECONDS = "HAMMER_TELEGRAM_APPROVAL_CHALLENGE_TTL_SECONDS"
DEFAULT_CHALLENGE_TTL_SECONDS = 90

CREATED = "CREATED"
APPROVED = "APPROVED"
EXPIRED = "EXPIRED"
REJECTED = "REJECTED"
BLOCKED = "BLOCKED"


def create_first_live_approval_challenge(
    *,
    log_dir: str | Path | None = None,
    runbook: dict[str, Any] | None = None,
    preflight_pack: dict[str, Any] | None = None,
    ttl_seconds: int | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    preflight = preflight_pack or build_promoted_strategy_preflight(log_dir=resolved_log_dir)
    current_runbook = runbook or build_first_live_runbook(log_dir=resolved_log_dir, preflight_pack=preflight)
    candidate = preflight.get("candidate") or {}
    blockers = _challenge_blockers(preflight=preflight, candidate=candidate)
    if blockers:
        return _challenge_response(
            status=BLOCKED,
            result_status="BLOCKED",
            message="Approval challenge blocked. " + "; ".join(blockers[:4]),
            blockers=blockers,
            challenge=None,
            code=None,
        )
    ttl = ttl_seconds if ttl_seconds is not None else _env_int(os.environ.get(ENV_CHALLENGE_TTL_SECONDS), DEFAULT_CHALLENGE_TTL_SECONDS)
    code = _unique_code(log_dir=resolved_log_dir)
    now = datetime.now(UTC)
    challenge = {
        "challenge_id": uuid4().hex,
        "challenge_code_hash": _hash_code(code),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=ttl)).isoformat(),
        "status": CREATED,
        "signal_id": preflight.get("candidate_signal_id") or preflight.get("signal_id"),
        "strategy_key": preflight.get("strategy_key"),
        "symbol": candidate.get("symbol"),
        "timeframe": candidate.get("timeframe"),
        "direction": candidate.get("direction"),
        "entry": candidate.get("entry"),
        "stop": candidate.get("stop"),
        "take_profit": candidate.get("take_profit"),
        "position_usd": 44,
        "leverage": candidate.get("leverage") or 2,
        "operator_reply": None,
        "approval_action_created": False,
        "exact_approval_text": None,
        "live_execution_enabled": False,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }
    append_telegram_approval_challenge(challenge, log_dir=resolved_log_dir)
    message = _challenge_message(challenge, code=code, runbook=current_runbook, ttl_seconds=ttl)
    return _challenge_response(
        status=CREATED,
        result_status="ACCEPTED",
        message=message,
        blockers=[],
        challenge=challenge,
        code=code,
    )


def process_first_live_challenge_reply(
    *,
    text: str | None,
    source: str = "telegram",
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    raw_text = (text or "").strip()
    parts = raw_text.split()
    if len(parts) != 2 or parts[0].upper() != "YES":
        return _challenge_response(
            status=REJECTED,
            result_status="REJECTED",
            message="Raw YES is rejected. Reply exactly YES <challenge_code> for an active challenge.",
            blockers=["YES requires an active challenge code"],
            challenge=None,
            code=None,
            reason="YES requires an active challenge code",
        )
    code = parts[1].strip()
    latest = _latest_record_for_code(code, log_dir=resolved_log_dir)
    if latest is None:
        return _challenge_response(
            status=REJECTED,
            result_status="REJECTED",
            message="Challenge code rejected: unknown code. No order placed.",
            blockers=["unknown challenge code"],
            challenge=None,
            code=None,
            reason="unknown challenge code",
        )
    if latest.get("status") == APPROVED:
        return _append_terminal_record(
            latest,
            status=REJECTED,
            result_status="REJECTED",
            message="Challenge code rejected: already used. No order placed.",
            operator_reply=raw_text,
            reason="already used challenge code",
            log_dir=resolved_log_dir,
        )
    expires_at = _parse_datetime(latest.get("expires_at"))
    if latest.get("status") != CREATED or expires_at is None or datetime.now(UTC) >= expires_at:
        return _append_terminal_record(
            latest,
            status=EXPIRED,
            result_status="REJECTED",
            message="Challenge code rejected: expired. No order placed.",
            operator_reply=raw_text,
            reason="expired challenge code",
            log_dir=resolved_log_dir,
        )
    signal_id = str(latest.get("signal_id") or "")
    approval = evaluate_live_approval_request(
        text=f"LIVE APPROVE {signal_id}",
        source=source,
        log_dir=resolved_log_dir,
    )
    approved = dict(latest)
    approved.update(
        {
            "challenge_id": latest["challenge_id"],
            "created_at": datetime.now(UTC).isoformat(),
            "status": APPROVED,
            "operator_reply": "YES <hidden>",
            "approval_action_created": True,
            "exact_approval_text": f"LIVE APPROVE {signal_id}",
            "approval_request_id": approval.get("request_id"),
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "secrets_shown": False,
        }
    )
    append_telegram_approval_challenge(approved, log_dir=resolved_log_dir)
    return _challenge_response(
        status=APPROVED,
        result_status="ACCEPTED",
        message=f"Approval recorded for {signal_id}. Approval is not execution. No live order placed.",
        blockers=[],
        challenge=approved,
        code=None,
        approval=approval,
    )


def append_telegram_approval_challenge(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = telegram_approval_challenges_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_telegram_approval_challenges(
    *,
    limit: int = 50,
    challenge_id: str | None = None,
    signal_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    records = list(reversed(_load_raw_challenges(log_dir=log_dir, challenge_id=challenge_id, signal_id=signal_id)))
    if limit > 0:
        return [_sanitize_challenge(record) for record in records[:limit]]
    return [_sanitize_challenge(record) for record in records]


def telegram_approval_challenges_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / CHALLENGES_FILENAME


def _challenge_blockers(*, preflight: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    blockers = []
    if preflight.get("promoted_strategy_ready") is not True:
        blockers.append("promoted strategy is not ready")
    if preflight.get("matching_fresh_signal_found") is not True:
        blockers.append("no fresh promoted signal")
    if not (preflight.get("candidate_signal_id") or preflight.get("signal_id")):
        blockers.append("signal_id is missing")
    if preflight.get("strategy_key") != PROMOTED_STRATEGY_KEY:
        blockers.append(f"strategy_key must be {PROMOTED_STRATEGY_KEY}")
    if candidate.get("symbol") != "BTCUSDT":
        blockers.append("candidate is not BTCUSDT")
    if candidate.get("timeframe") != "13m":
        blockers.append("candidate timeframe is not 13m")
    if candidate.get("direction") != "long":
        blockers.append("candidate direction is not long")
    if candidate.get("freshness_status") not in {None, "fresh"}:
        blockers.append("candidate is not fresh")
    if candidate.get("decision") == "FORBIDDEN" or candidate.get("reject_reason"):
        blockers.append("candidate is forbidden or rejected")
    for field in ("entry", "stop", "take_profit"):
        if candidate.get(field) is None:
            blockers.append(f"{field} is missing")
    return list(dict.fromkeys(blockers))


def _challenge_message(challenge: dict[str, Any], *, code: str, runbook: dict[str, Any], ttl_seconds: int) -> str:
    return "\n".join(
        [
            "Hammer Radar - First Live Approval Challenge",
            f"Candidate: {challenge.get('symbol')} {challenge.get('timeframe')} {challenge.get('direction')}",
            f"Signal: {challenge.get('signal_id')}",
            f"Entry: {challenge.get('entry')}",
            f"Stop: {challenge.get('stop')}",
            f"Take profit: {challenge.get('take_profit')}",
            f"Position: {challenge.get('position_usd')} USDT",
            f"Leverage: {challenge.get('leverage')}x",
            f"Protection: {'ready' if (runbook.get('checklist') or {}).get('protective_orders_ready', {}).get('passed') else 'not ready'}",
            f"Test order: {'validated' if (runbook.get('checklist') or {}).get('test_order_validated_for_signal', {}).get('passed') else 'not validated'}",
            f"Runbook: {runbook.get('runbook_status')}/{runbook.get('gate_decision')}",
            "",
            "Reply exactly:",
            f"YES {code}",
            "",
            f"Expires in: {ttl_seconds} seconds",
            "Approval is not execution.",
            "No live order is placed by this command.",
        ]
    )


def _challenge_response(
    *,
    status: str,
    result_status: str,
    message: str,
    blockers: list[str],
    challenge: dict[str, Any] | None,
    code: str | None,
    reason: str | None = None,
    approval: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "result_status": result_status,
        "challenge_status": status,
        "status": status,
        "reason": reason,
        "message": message,
        "telegram_compatible": {"send_enabled": False, "text": message},
        "challenge": _sanitize_challenge(challenge) if challenge else None,
        "challenge_code": code,
        "approval": approval,
        "blockers": blockers,
        "live_execution_enabled": False,
        "allow_live_orders": False,
        "global_kill_switch": True,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "secrets_shown": False,
    }


def _append_terminal_record(
    latest: dict[str, Any],
    *,
    status: str,
    result_status: str,
    message: str,
    operator_reply: str,
    reason: str,
    log_dir: Path,
) -> dict[str, Any]:
    record = dict(latest)
    record.update(
        {
            "created_at": datetime.now(UTC).isoformat(),
            "status": status,
            "operator_reply": _sanitize_reply(operator_reply),
            "approval_action_created": False,
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "secrets_shown": False,
        }
    )
    append_telegram_approval_challenge(record, log_dir=log_dir)
    return _challenge_response(
        status=status,
        result_status=result_status,
        message=message,
        blockers=[reason],
        challenge=record,
        code=None,
        reason=reason,
    )


def _latest_record_for_code(code: str, *, log_dir: Path) -> dict[str, Any] | None:
    code_hash = _hash_code(code)
    for record in reversed(_load_raw_challenges(log_dir=log_dir)):
        if hmac.compare_digest(str(record.get("challenge_code_hash") or ""), code_hash):
            return record
    return None


def _unique_code(*, log_dir: Path) -> str:
    active_hashes = {record.get("challenge_code_hash") for record in _load_raw_challenges(log_dir=log_dir)}
    for _ in range(20):
        code = secrets.token_hex(3)
        if _hash_code(code) not in active_hashes:
            return code
    return secrets.token_hex(4)


def _load_raw_challenges(
    *,
    log_dir: str | Path | None = None,
    challenge_id: str | None = None,
    signal_id: str | None = None,
) -> list[dict[str, Any]]:
    path = telegram_approval_challenges_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if challenge_id is not None and record.get("challenge_id") != challenge_id:
                continue
            if signal_id is not None and record.get("signal_id") != signal_id:
                continue
            records.append(record)
    return records


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode("utf-8")).hexdigest()


def _sanitize_challenge(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    sanitized = dict(record)
    sanitized["challenge_code_hash"] = "<hidden>" if sanitized.get("challenge_code_hash") else None
    if sanitized.get("operator_reply"):
        sanitized["operator_reply"] = _sanitize_reply(str(sanitized["operator_reply"]))
    return sanitized


def _sanitize_reply(value: str) -> str:
    if value.upper().startswith("YES "):
        return "YES <hidden>"
    return value[:200]


def _parse_datetime(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _env_int(value: str | None, default: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return default
    return max(parsed, 1)
