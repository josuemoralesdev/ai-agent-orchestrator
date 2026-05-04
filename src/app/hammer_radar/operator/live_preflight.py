"""Promoted strategy live preflight pack for Hammer Radar.

This module bridges strategy-level promotion to signal-level readiness. It is
preflight/reporting only and never places orders, reads secrets, calls Binance,
or creates signed order payloads.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.exchange_dry_run import build_current_exchange_dry_run
from src.app.hammer_radar.operator.inspect import (
    LIVE_DECISION_ELIGIBLE,
    LIVE_DECISION_FORBIDDEN,
    LiveCandidateCheck,
    build_live_candidate_snapshot,
)
from src.app.hammer_radar.operator.live_safety import build_current_live_safety
from src.app.hammer_radar.operator.readiness import build_readiness_payload
from src.app.hammer_radar.operator.strategy_performance import PREFERRED_ENTRY_MODE, StrategyAuditConfig
from src.app.hammer_radar.operator.strategy_promotion_watcher import (
    STRATEGY_PROMOTION_READY,
    build_strategy_promotion_status,
)
from src.app.hammer_radar.operator.trade_ticket import build_trade_ticket

LIVE_PREFLIGHT_PACKS_FILENAME = "live_preflight_packs.ndjson"

NO_PROMOTED_STRATEGY = "NO_PROMOTED_STRATEGY"
WAITING_FOR_FRESH_PROMOTED_SIGNAL = "WAITING_FOR_FRESH_PROMOTED_SIGNAL"
PROMOTED_SIGNAL_FOUND = "PROMOTED_SIGNAL_FOUND"
PREFLIGHT_BLOCKED = "PREFLIGHT_BLOCKED"
PREFLIGHT_READY_BUT_EXECUTION_DISABLED = "PREFLIGHT_READY_BUT_EXECUTION_DISABLED"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
SECRETS_SHOWN = False
PROMOTED_STRATEGY_KEY = f"BTCUSDT|13m|long|{PREFERRED_ENTRY_MODE}"


def build_promoted_strategy_preflight(
    *,
    log_dir: str | Path | None = None,
    config: StrategyAuditConfig | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    created_at = datetime.now(UTC).isoformat()
    promoted_strategy = _promoted_strategy(log_dir=resolved_log_dir, config=config)
    if promoted_strategy is None:
        return _pack(
            created_at=created_at,
            log_dir=resolved_log_dir,
            preflight_status=NO_PROMOTED_STRATEGY,
            promoted_strategy=None,
            candidate=None,
            readiness=None,
            ticket=None,
            dry_run=None,
            live_safety=None,
            blockers=["no promoted BTCUSDT 13m long ladder_close_50_618 strategy"],
            operator_next_action="Wait for R41 strategy promotion; do not approve live now.",
        )

    candidate = _matching_fresh_candidate(log_dir=resolved_log_dir)
    if candidate is None:
        return _pack(
            created_at=created_at,
            log_dir=resolved_log_dir,
            preflight_status=WAITING_FOR_FRESH_PROMOTED_SIGNAL,
            promoted_strategy=promoted_strategy,
            candidate=None,
            readiness=None,
            ticket=None,
            dry_run=None,
            live_safety=None,
            blockers=["no fresh BTCUSDT 13m long signal matching promoted strategy"],
            operator_next_action="Wait for fresh promoted signal; do not approve live now.",
        )

    signal_id = str(candidate.get("signal_id") or "")
    readiness = build_readiness_payload(log_dir=resolved_log_dir)
    ticket = build_trade_ticket(signal_id=signal_id, log_dir=resolved_log_dir)
    dry_run = build_current_exchange_dry_run(signal_id=signal_id, log_dir=resolved_log_dir)
    live_safety = build_current_live_safety(signal_id=signal_id, log_dir=resolved_log_dir)
    blockers = _combined_blockers(candidate, readiness, ticket, dry_run, live_safety)
    if (
        readiness.get("readiness_status") == "READY"
        and ticket.get("ticket_status") == "PROPOSED"
        and dry_run.get("validation_status") == "VALID"
    ):
        preflight_status = PREFLIGHT_READY_BUT_EXECUTION_DISABLED
        blockers.extend(
            [
                "live_execution_enabled is false",
                "allow_live_orders is false",
                "global kill switch is active",
                "execution remains disabled",
            ]
        )
        operator_next_action = f"Review only. Exact LIVE APPROVE {signal_id} required later; execution remains disabled."
    else:
        preflight_status = PREFLIGHT_BLOCKED
        operator_next_action = "Resolve preflight blockers; do not approve live now."

    return _pack(
        created_at=created_at,
        log_dir=resolved_log_dir,
        preflight_status=preflight_status,
        promoted_strategy=promoted_strategy,
        candidate=candidate,
        readiness=readiness,
        ticket=ticket,
        dry_run=dry_run,
        live_safety=live_safety,
        blockers=list(dict.fromkeys(blockers)),
        operator_next_action=operator_next_action,
    )


def evaluate_and_record_live_preflight(
    *,
    log_dir: str | Path | None = None,
    config: StrategyAuditConfig | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    pack = build_promoted_strategy_preflight(log_dir=resolved_log_dir, config=config)
    existing = load_live_preflight_packs(limit=0, log_dir=resolved_log_dir)
    existing_dedupe_keys = {str(record.get("dedupe_key")) for record in existing if record.get("dedupe_key")}
    record = dict(pack)
    record["dedupe_key"] = _dedupe_key(record)
    if record["dedupe_key"] in existing_dedupe_keys:
        return {
            **_safety_fields(),
            "recorded": False,
            "deduped": True,
            "preflight_pack": record,
            "live_preflight_packs_path": str(live_preflight_packs_path(resolved_log_dir)),
            "message_payloads": [build_preflight_message(record)],
        }
    append_live_preflight_pack(record, log_dir=resolved_log_dir)
    return {
        **_safety_fields(),
        "recorded": True,
        "deduped": False,
        "preflight_pack": record,
        "live_preflight_packs_path": str(live_preflight_packs_path(resolved_log_dir)),
        "message_payloads": [build_preflight_message(record)],
    }


def load_live_preflight_packs(
    *,
    limit: int = 50,
    preflight_id: str | None = None,
    strategy_key: str | None = None,
    log_dir: str | Path,
) -> list[dict[str, Any]]:
    path = live_preflight_packs_path(log_dir)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if preflight_id is not None and record.get("preflight_id") != preflight_id:
                continue
            if strategy_key is not None and record.get("strategy_key") != strategy_key:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def append_live_preflight_pack(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = live_preflight_packs_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def live_preflight_packs_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LIVE_PREFLIGHT_PACKS_FILENAME


def build_preflight_message(pack: dict[str, Any]) -> dict[str, Any]:
    if pack.get("matching_fresh_signal_found") is True:
        first_line = (
            f"Fresh promoted strategy signal found. Exact LIVE APPROVE {pack.get('candidate_signal_id')} required. "
            "Execution remains disabled."
        )
    elif pack.get("promoted_strategy_ready") is True:
        first_line = "Promoted strategy ready, waiting for fresh BTCUSDT 13m long signal."
    else:
        first_line = "No promoted strategy is ready for live preflight."
    message = "\n".join(
        [
            "Hammer Radar promoted strategy preflight",
            first_line,
            "Recommendation/preflight only, not permission to execute.",
            "No live orders.",
            "No signed payloads.",
            "Execution remains disabled.",
            f"preflight_status: {pack.get('preflight_status')}",
            f"strategy_key: {pack.get('strategy_key') or 'n/a'}",
            f"signal_id: {pack.get('candidate_signal_id') or 'n/a'}",
        ]
    )
    return {
        "channel": "telegram_compatible",
        "send_enabled": False,
        "message": message,
        "secrets_shown": SECRETS_SHOWN,
    }


def _pack(
    *,
    created_at: str,
    log_dir: Path,
    preflight_status: str,
    promoted_strategy: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    readiness: dict[str, Any] | None,
    ticket: dict[str, Any] | None,
    dry_run: dict[str, Any] | None,
    live_safety: dict[str, Any] | None,
    blockers: list[str],
    operator_next_action: str,
) -> dict[str, Any]:
    signal_id = (candidate or {}).get("signal_id")
    strategy_key = (promoted_strategy or {}).get("strategy_key") or PROMOTED_STRATEGY_KEY
    pack = {
        "preflight_id": uuid4().hex,
        "created_at": created_at,
        "archive_log_dir": str(log_dir),
        "preflight_status": preflight_status,
        "promoted_strategy_ready": promoted_strategy is not None,
        "promoted_strategy": promoted_strategy,
        "matching_fresh_signal_found": candidate is not None,
        "candidate_signal_id": signal_id,
        "signal_id": signal_id,
        "candidate": candidate,
        "strategy_key": strategy_key,
        "entry_mode_match": "unknown_from_candidate" if candidate is not None else None,
        "required_exact_command": f"LIVE APPROVE {signal_id}" if signal_id else None,
        "readiness_status": (readiness or {}).get("readiness_status", "UNKNOWN"),
        "ticket_status": (ticket or {}).get("ticket_status", "UNKNOWN"),
        "dry_run_status": (dry_run or {}).get("validation_status", "UNKNOWN"),
        "live_safety_status": (live_safety or {}).get("live_safety_status", "UNKNOWN"),
        "readiness": _summary(readiness, ("readiness_status", "allowed_now", "blockers")),
        "ticket": _summary(ticket, ("ticket_status", "ticket_id", "signal_id", "blockers")),
        "dry_run": _summary(dry_run, ("validation_status", "dry_run", "order_placed", "blockers")),
        "live_safety": _summary(live_safety, ("live_safety_status", "kill_switch_active", "allow_live_orders", "blockers")),
        "blockers": list(dict.fromkeys(blockers)),
        "passed_gates": list((live_safety or {}).get("passed_gates") or []),
        "failed_gates": list((live_safety or {}).get("failed_gates") or []),
        "operator_next_action": operator_next_action,
        **_safety_fields(),
    }
    pack["message_payloads"] = [build_preflight_message(pack)]
    pack["live_preflight_packs_path"] = str(live_preflight_packs_path(log_dir))
    return pack


def _promoted_strategy(*, log_dir: Path, config: StrategyAuditConfig | None) -> dict[str, Any] | None:
    status = build_strategy_promotion_status(log_dir=log_dir, config=config)
    for row in status.get("promotion_ready") or []:
        if row.get("strategy_key") == PROMOTED_STRATEGY_KEY and row.get("event_type") == STRATEGY_PROMOTION_READY:
            return row
    return None


def _matching_fresh_candidate(*, log_dir: Path) -> dict[str, Any] | None:
    snapshot = build_live_candidate_snapshot(
        limit=1000,
        since_hours=24,
        min_score=90,
        symbol="BTCUSDT",
        allow_short=False,
        allow_oversold=False,
        allow_trigger_flags=False,
        max_risk_usd=5.0,
        max_leverage=3.0,
        max_position_usd=44.0,
        fresh_minutes=30,
        allow_expired=False,
        latest_only=False,
        log_dir=log_dir,
    )
    matches = []
    for check in snapshot["checks"]:
        candidate = _candidate_snapshot(check)
        if _candidate_matches(candidate):
            matches.append(candidate)
    matches.sort(key=lambda row: row.get("age_minutes") if row.get("age_minutes") is not None else float("inf"))
    return matches[0] if matches else None


def _candidate_matches(candidate: dict[str, Any]) -> bool:
    return (
        candidate.get("symbol") == "BTCUSDT"
        and candidate.get("timeframe") == "13m"
        and candidate.get("direction") == "long"
        and candidate.get("freshness_status") == "fresh"
        and candidate.get("decision") == LIVE_DECISION_ELIGIBLE
        and candidate.get("decision") != LIVE_DECISION_FORBIDDEN
        and candidate.get("reject_reason") is None
        and candidate.get("tradable") is True
    )


def _candidate_snapshot(check: LiveCandidateCheck) -> dict[str, Any]:
    signal = check.candidate.signal
    return {
        "signal_id": signal.signal_id,
        "timestamp": signal.timestamp,
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "direction": signal.direction,
        "decision": check.decision,
        "reason": check.reason,
        "score": check.candidate.score,
        "tier": check.candidate.tier,
        "tradable": signal.tradable,
        "reject_reason": signal.reject_reason,
        "entry": check.entry,
        "stop": check.stop,
        "take_profit": check.take_profit,
        "age_minutes": check.age_minutes,
        "freshness_status": check.freshness_status,
        "entry_mode_match": "unknown_from_candidate",
        "entry_mode_note": (
            "Candidate archive does not carry entry_mode; conservative fallback matched BTCUSDT 13m long fresh eligible signal."
        ),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
    }


def _combined_blockers(
    candidate: dict[str, Any],
    readiness: dict[str, Any],
    ticket: dict[str, Any],
    dry_run: dict[str, Any],
    live_safety: dict[str, Any],
) -> list[str]:
    blockers = []
    if candidate.get("entry_mode_match") == "unknown_from_candidate":
        blockers.append("entry_mode unknown from candidate archive; exact signal approval still required")
    blockers.extend(str(item) for item in readiness.get("blockers") or [])
    blockers.extend(str(item) for item in ticket.get("blockers") or [])
    blockers.extend(str(item) for item in dry_run.get("blockers") or [])
    blockers.extend(str(item) for item in live_safety.get("blockers") or [])
    return blockers


def _summary(payload: dict[str, Any] | None, keys: tuple[str, ...]) -> dict[str, Any] | None:
    if payload is None:
        return None
    return {key: payload.get(key) for key in keys}


def _dedupe_key(pack: dict[str, Any]) -> str:
    return "|".join(
        [
            str(pack.get("strategy_key")),
            str(pack.get("preflight_status")),
            str(pack.get("candidate_signal_id")),
            str(pack.get("readiness_status")),
            str(pack.get("ticket_status")),
            str(pack.get("dry_run_status")),
            str(pack.get("live_safety_status")),
        ]
    )


def _safety_fields() -> dict[str, Any]:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "order_placed": ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "order_payload_created": ORDER_PAYLOAD_CREATED,
        "secrets_shown": SECRETS_SHOWN,
    }
