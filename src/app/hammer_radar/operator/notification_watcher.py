"""Telegram readiness notification watcher for Hammer Radar.

This module is alert-only. It never places orders, never enables live execution,
and never stores Telegram credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.exchange_dry_run import build_exchange_dry_run
from src.app.hammer_radar.operator.inspect import LiveCandidateCheck, build_live_candidate_snapshot
from src.app.hammer_radar.operator.live_safety import evaluate_live_safety
from src.app.hammer_radar.operator.manual_outcomes import load_manual_outcomes
from src.app.hammer_radar.operator.paper_execution import load_paper_executions
from src.app.hammer_radar.operator.readiness import LIVE_EXECUTION_ENABLED, ORDER_PLACED, PROTOCOL, build_readiness_payload
from src.app.hammer_radar.operator.strategy_config import load_strategy_config
from src.app.hammer_radar.operator.trade_ticket import build_trade_ticket, load_trade_ticket_records

ALERTS_FILENAME = "readiness_alerts.ndjson"
LIVE_READY = "LIVE_READY"
READY_TRADE_CANDIDATE = LIVE_READY
ACTIONABLE_PAPER = "ACTIONABLE_PAPER"
EXPIRING_SOON = "EXPIRING_SOON"
EXPIRED_MISSED = "EXPIRED_MISSED"
SYSTEM_STILL_BLOCKED = "SYSTEM_STILL_BLOCKED"
ACTIONABLE_PAPER_TIER = "ACTIONABLE_PAPER_CANDIDATE"
ACTIONABLE_PAPER_MIN_SCORE = 80
DEFAULT_FRESH_MINUTES = 30
DEFAULT_EXPIRING_SOON_MINUTES = 5


@dataclass(frozen=True)
class NotificationConfig:
    telegram_enabled: bool
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    min_interval_seconds: int
    poll_seconds: int
    require_dry_run_valid: bool
    require_proposed_ticket: bool
    blocked_alert_enabled: bool
    actionable_paper_enabled: bool
    actionable_paper_min_score: int
    expiring_soon_minutes: int
    expired_missed_record_enabled: bool

    @property
    def token_present(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def chat_id_present(self) -> bool:
        return bool(self.telegram_chat_id)

    @property
    def telegram_configured(self) -> bool:
        return self.token_present and self.chat_id_present

    def safe_status(self) -> dict[str, Any]:
        return {
            "telegram_enabled": self.telegram_enabled,
            "telegram_configured": self.telegram_configured,
            "token_present": self.token_present,
            "chat_id_present": self.chat_id_present,
            "token_preview": None,
            "min_interval_seconds": self.min_interval_seconds,
            "poll_seconds": self.poll_seconds,
            "require_dry_run_valid": self.require_dry_run_valid,
            "require_proposed_ticket": self.require_proposed_ticket,
            "actionable_paper_enabled": self.actionable_paper_enabled,
            "actionable_paper_min_score": self.actionable_paper_min_score,
            "expiring_soon_minutes": self.expiring_soon_minutes,
            "expired_missed_record_enabled": self.expired_missed_record_enabled,
        }


TelegramSender = Callable[[str, str], dict[str, Any]]


def load_notification_config(env: dict[str, str] | None = None) -> NotificationConfig:
    source = os.environ if env is None else env
    return NotificationConfig(
        telegram_enabled=_env_bool(source.get("HAMMER_ALERT_TELEGRAM_ENABLED"), default=False),
        telegram_bot_token=_clean_secret(source.get("TELEGRAM_BOT_TOKEN")),
        telegram_chat_id=_clean_secret(source.get("TELEGRAM_CHAT_ID")),
        min_interval_seconds=_env_int(source.get("HAMMER_ALERT_MIN_INTERVAL_SECONDS"), default=300, minimum=0),
        poll_seconds=_env_int(source.get("HAMMER_ALERT_POLL_SECONDS"), default=60, minimum=1),
        require_dry_run_valid=_env_bool(source.get("HAMMER_ALERT_REQUIRE_DRY_RUN_VALID"), default=True),
        require_proposed_ticket=_env_bool(source.get("HAMMER_ALERT_REQUIRE_PROPOSED_TICKET"), default=True),
        blocked_alert_enabled=_env_bool(source.get("HAMMER_ALERT_SYSTEM_STILL_BLOCKED_ENABLED"), default=False),
        actionable_paper_enabled=_env_bool(source.get("HAMMER_ALERT_ACTIONABLE_PAPER_ENABLED"), default=True),
        actionable_paper_min_score=_env_int(
            source.get("HAMMER_ALERT_ACTIONABLE_PAPER_MIN_SCORE"),
            default=ACTIONABLE_PAPER_MIN_SCORE,
            minimum=0,
        ),
        expiring_soon_minutes=_env_int(
            source.get("HAMMER_ALERT_EXPIRING_SOON_MINUTES"),
            default=DEFAULT_EXPIRING_SOON_MINUTES,
            minimum=0,
        ),
        expired_missed_record_enabled=_env_bool(source.get("HAMMER_ALERT_EXPIRED_MISSED_RECORD_ENABLED"), default=True),
    )


def build_readiness_notification_snapshot(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    readiness = build_readiness_payload(log_dir=resolved_log_dir)
    ticket = build_trade_ticket(log_dir=resolved_log_dir)
    candidate_snapshot = build_live_candidate_snapshot(
        limit=10,
        since_hours=24,
        min_score=ACTIONABLE_PAPER_MIN_SCORE,
        symbol=PROTOCOL["symbol"],
        allow_short=True,
        allow_oversold=True,
        allow_trigger_flags=True,
        max_risk_usd=5.0,
        max_leverage=float(PROTOCOL["max_leverage"]),
        max_position_usd=float(PROTOCOL["max_position_usd"]),
        fresh_minutes=DEFAULT_FRESH_MINUTES,
        allow_expired=False,
        latest_only=False,
        log_dir=resolved_log_dir,
    )
    exchange_dry_run = build_exchange_dry_run(ticket)
    live_safety = evaluate_live_safety(
        readiness=readiness,
        ticket=ticket,
        exchange_dry_run=exchange_dry_run,
        decisions=load_trade_ticket_records(limit=0, log_dir=resolved_log_dir),
        paper_executions=load_paper_executions(limit=0, log_dir=resolved_log_dir),
        manual_outcomes=load_manual_outcomes(limit=0, log_dir=resolved_log_dir),
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "readiness": readiness,
        "ticket": ticket,
        "candidate_snapshot": candidate_snapshot,
        "exchange_dry_run": exchange_dry_run,
        "live_safety": live_safety,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
    }


def evaluate_alert(snapshot: dict[str, Any], config: NotificationConfig | None = None) -> dict[str, Any]:
    config = config or load_notification_config()
    readiness = snapshot.get("readiness") or {}
    ticket = snapshot.get("ticket") or {}
    dry_run = snapshot.get("exchange_dry_run") or {}
    live_safety = snapshot.get("live_safety") or {}

    checks = {
        "readiness_ready": readiness.get("readiness_status") == "READY",
        "allowed_now": readiness.get("allowed_now") is True,
        "ticket_proposed": (not config.require_proposed_ticket) or ticket.get("ticket_status") == "PROPOSED",
        "dry_run_valid": (not config.require_dry_run_valid) or dry_run.get("validation_status") == "VALID",
        "live_execution_disabled": snapshot.get("live_execution_enabled") is False,
        "order_not_placed": snapshot.get("order_placed") is False,
    }
    strict_would_alert = all(checks.values())
    candidate_alert = _evaluate_candidate_alert(snapshot, config) if config.actionable_paper_enabled else None
    alert_type = LIVE_READY if strict_would_alert else None
    would_alert = strict_would_alert
    candidate_payload = None
    if not would_alert and candidate_alert is not None:
        alert_type = candidate_alert["alert_type"]
        would_alert = candidate_alert["would_alert"]
        candidate_payload = candidate_alert
    if not would_alert and config.blocked_alert_enabled:
        alert_type = SYSTEM_STILL_BLOCKED
        would_alert = True

    return {
        "would_alert": would_alert,
        "alert_type": alert_type,
        "signal_id": (candidate_payload or {}).get("signal_id") or ticket.get("signal_id"),
        "readiness_status": readiness.get("readiness_status", "UNKNOWN"),
        "ticket_status": ticket.get("ticket_status", "UNKNOWN"),
        "dry_run_status": dry_run.get("validation_status", "UNKNOWN"),
        "live_safety_status": live_safety.get("live_safety_status", "UNKNOWN"),
        "checks": checks,
        "candidate": (candidate_payload or {}).get("candidate"),
        "message": (
            build_telegram_message(snapshot, alert_type=alert_type, candidate=(candidate_payload or {}).get("candidate"))
            if alert_type
            else None
        ),
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
    }


def build_telegram_message(
    snapshot: dict[str, Any],
    *,
    alert_type: str | None = LIVE_READY,
    candidate: dict[str, Any] | None = None,
) -> str:
    ticket = snapshot.get("ticket") or {}
    dry_run = snapshot.get("exchange_dry_run") or {}
    live_safety = snapshot.get("live_safety") or {}
    if alert_type == SYSTEM_STILL_BLOCKED:
        readiness = snapshot.get("readiness") or {}
        return "\n".join(
            [
                "Hammer Radar still blocked",
                f"readiness: {readiness.get('readiness_status', 'UNKNOWN')}",
                f"ticket: {ticket.get('ticket_status', 'UNKNOWN')}",
                f"dry_run: {dry_run.get('validation_status', 'UNKNOWN')}",
                "Alerts only. No order placement.",
            ]
        )
    if alert_type in {ACTIONABLE_PAPER, EXPIRING_SOON, EXPIRED_MISSED}:
        payload = candidate or {}
        return "\n".join(
            [
                "Hammer Radar operator alert",
                f"alert_type: {alert_type or 'n/a'}",
                f"signal_id: {payload.get('signal_id') or 'n/a'}",
                f"symbol: {payload.get('symbol') or 'n/a'}",
                f"timeframe: {payload.get('timeframe') or 'n/a'}",
                f"direction: {payload.get('direction') or 'n/a'}",
                f"entry: {_format_value(payload.get('entry'))}",
                f"stop: {_format_value(payload.get('stop'))}",
                f"take_profit: {_format_value(payload.get('take_profit'))}",
                f"score: {_format_value(payload.get('score'))}",
                f"tier: {payload.get('tier') or 'n/a'}",
                f"age_minutes: {_format_value(payload.get('age_minutes'))}",
                f"freshness_status: {payload.get('freshness_status') or 'n/a'}",
                f"reason: {payload.get('reason') or 'n/a'}",
                "live_execution_enabled=false",
                "order_placed=false",
                f"operator action: {payload.get('operator_action') or 'watch / approve paper / wait for next fresh candidate'}",
            ]
        )
    return "\n".join(
        [
            "Hammer Radar READY candidate",
            f"alert_type: {alert_type or 'n/a'}",
            f"symbol: {ticket.get('symbol') or 'n/a'}",
            f"signal_id: {ticket.get('signal_id') or 'n/a'}",
            f"direction/timeframe: {ticket.get('direction') or 'n/a'}/{ticket.get('timeframe') or 'n/a'}",
            f"entry: {_format_value(ticket.get('entry'))}",
            f"stop: {_format_value(ticket.get('stop'))}",
            f"take_profit: {_format_value(ticket.get('take_profit'))}",
            f"suggested_position_usd: {_format_value(ticket.get('suggested_position_usd'))}",
            f"suggested_leverage: {_format_value(ticket.get('suggested_leverage'))}",
            f"dry_run status: {dry_run.get('validation_status', 'UNKNOWN')}",
            f"live_safety status: {live_safety.get('live_safety_status', 'UNKNOWN')}",
            "live_execution_enabled=false",
            "order_placed=false",
            "operator action: approve paper",
        ]
    )


def send_telegram_message(token: str, chat_id: str, message: str, *, timeout: float = 10.0) -> dict[str, Any]:
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
        parsed = json.loads(body) if body else {}
        return {"sent": bool(parsed.get("ok", False)), "status": "sent" if parsed.get("ok") else "rejected"}
    except urllib.error.HTTPError as exc:
        return {"sent": False, "status": "http_error", "error": f"HTTP {exc.code}"}
    except urllib.error.URLError as exc:
        return {"sent": False, "status": "url_error", "error": str(exc.reason)}
    except TimeoutError:
        return {"sent": False, "status": "timeout"}
    except Exception as exc:  # pragma: no cover - defensive safety for watcher mode.
        return {"sent": False, "status": "error", "error": exc.__class__.__name__}


def check_notifications(
    *,
    send: bool = False,
    channel: str = "none",
    log_dir: str | Path | None = None,
    config: NotificationConfig | None = None,
    telegram_sender: TelegramSender | None = None,
) -> dict[str, Any]:
    config = config or load_notification_config()
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    snapshot = build_readiness_notification_snapshot(log_dir=resolved_log_dir)
    evaluation = evaluate_alert(snapshot, config)
    dedupe = evaluate_dedupe(evaluation, log_dir=resolved_log_dir, config=config)
    telegram_result: dict[str, Any] = {"sent": False, "status": "not_requested"}
    recorded = False
    if evaluation["alert_type"] == EXPIRED_MISSED and config.expired_missed_record_enabled and dedupe["allowed"]:
        append_alert_record(
            build_alert_record(
                evaluation,
                telegram_sent=False,
                message=evaluation["message"] or "",
                dedupe_key=dedupe.get("dedupe_key"),
            ),
            log_dir=resolved_log_dir,
        )
        recorded = True

    if send and channel == "telegram" and evaluation["would_alert"] and evaluation["alert_type"] != EXPIRED_MISSED:
        if not config.telegram_enabled:
            telegram_result = {"sent": False, "status": "telegram_disabled"}
        elif not config.telegram_configured:
            telegram_result = {"sent": False, "status": "telegram_not_configured"}
        elif not dedupe["allowed"]:
            telegram_result = {"sent": False, "status": "deduped", "reason": dedupe["reason"]}
        else:
            sender = telegram_sender or _sender_from_config(config)
            telegram_result = sender(config.telegram_chat_id or "", evaluation["message"] or "")
            if telegram_result.get("sent") is True:
                append_alert_record(
                    build_alert_record(
                        evaluation,
                        telegram_sent=True,
                        message=evaluation["message"] or "",
                        dedupe_key=dedupe.get("dedupe_key"),
                    ),
                    log_dir=resolved_log_dir,
                )
                recorded = True
    elif send and channel not in {"none", "telegram"}:
        telegram_result = {"sent": False, "status": f"unsupported_channel:{channel}"}

    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "would_alert": evaluation["would_alert"],
        "alert_type": evaluation["alert_type"],
        "signal_id": evaluation["signal_id"],
        "readiness_status": evaluation["readiness_status"],
        "ticket_status": evaluation["ticket_status"],
        "dry_run_status": evaluation["dry_run_status"],
        "live_safety_status": evaluation["live_safety_status"],
        "checks": evaluation["checks"],
        "candidate": evaluation.get("candidate"),
        "message": evaluation.get("message"),
        "send_requested": bool(send),
        "channel": channel,
        "dedupe_allowed": dedupe["allowed"],
        "dedupe_reason": dedupe["reason"],
        "telegram": telegram_result,
        "recorded": recorded,
        "secrets_shown": False,
        "config": config.safe_status(),
    }


def notification_status(*, log_dir: str | Path | None = None, config: NotificationConfig | None = None) -> dict[str, Any]:
    config = config or load_notification_config()
    records = load_alert_records(limit=0, log_dir=log_dir)
    last_alert = records[0] if records else None
    counts_by_type: dict[str, int] = {}
    for record in records:
        alert_type = str(record.get("alert_type") or "UNKNOWN")
        counts_by_type[alert_type] = counts_by_type.get(alert_type, 0) + 1
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "telegram_enabled": config.telegram_enabled,
        "telegram_configured": config.telegram_configured,
        "token_present": config.token_present,
        "chat_id_present": config.chat_id_present,
        "alerts_recorded": len(records),
        "alert_counts": counts_by_type,
        "last_alert": last_alert,
        "secrets_shown": False,
    }


def build_alert_record(
    evaluation: dict[str, Any],
    *,
    telegram_sent: bool,
    message: str,
    dedupe_key: str | None = None,
) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat()
    alert_type = str(evaluation.get("alert_type") or "UNKNOWN")
    signal_id = evaluation.get("signal_id")
    alert_id = _alert_id(alert_type=alert_type, signal_id=signal_id, created_at=created_at)
    return {
        "alert_id": alert_id,
        "created_at": created_at,
        "alert_type": alert_type,
        "signal_id": signal_id,
        "readiness_status": evaluation.get("readiness_status"),
        "ticket_status": evaluation.get("ticket_status"),
        "dry_run_status": evaluation.get("dry_run_status"),
        "live_safety_status": evaluation.get("live_safety_status"),
        "candidate": evaluation.get("candidate"),
        "telegram_sent": bool(telegram_sent),
        "message": message,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "dedupe_key": dedupe_key,
    }


def append_alert_record(record: dict[str, Any], *, log_dir: str | Path | None = None) -> None:
    path = _alerts_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_alert_records(*, limit: int = 50, log_dir: str | Path | None = None) -> list[dict[str, Any]]:
    path = _alerts_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def evaluate_dedupe(
    evaluation: dict[str, Any],
    *,
    log_dir: str | Path | None = None,
    config: NotificationConfig | None = None,
) -> dict[str, Any]:
    config = config or load_notification_config()
    alert_type = evaluation.get("alert_type")
    if (not evaluation.get("would_alert") and alert_type != EXPIRED_MISSED) or not alert_type:
        return {"allowed": False, "reason": "no_alert"}

    now = datetime.now(UTC)
    signal_id = evaluation.get("signal_id")
    fallback_key = _fallback_dedupe_key(evaluation, now=now, interval_seconds=config.min_interval_seconds)
    for record in load_alert_records(limit=0, log_dir=log_dir):
        if record.get("telegram_sent") is not True and record.get("alert_type") != EXPIRED_MISSED:
            continue
        created_at = _parse_datetime(record.get("created_at"))
        if record.get("telegram_sent") is True and created_at is not None and config.min_interval_seconds > 0:
            age_seconds = (now - created_at).total_seconds()
            if 0 <= age_seconds < config.min_interval_seconds:
                return {"allowed": False, "reason": "global_min_interval"}
        if signal_id and record.get("signal_id") == signal_id:
            return {"allowed": False, "reason": "duplicate_signal_alert"}
        if record.get("alert_type") != alert_type:
            continue
        if not signal_id and record.get("dedupe_key") == fallback_key:
            return {"allowed": False, "reason": "duplicate_status_bucket"}
    return {"allowed": True, "reason": "allowed", "dedupe_key": fallback_key}


def _evaluate_candidate_alert(snapshot: dict[str, Any], config: NotificationConfig) -> dict[str, Any] | None:
    checks = list((snapshot.get("candidate_snapshot") or {}).get("checks") or [])
    candidate = _select_operator_candidate(checks, min_score=config.actionable_paper_min_score)
    if candidate is None:
        return None
    payload = _candidate_payload(candidate)
    if candidate.freshness_status == "expired":
        payload["alert_type"] = EXPIRED_MISSED
        payload["reason"] = _operator_visibility_reason(
            candidate,
            prefix="BTCUSDT paper candidate expired before operator visibility",
        )
        payload["operator_action"] = "wait for next fresh candidate"
        return {
            "would_alert": False,
            "alert_type": EXPIRED_MISSED,
            "signal_id": payload["signal_id"],
            "candidate": payload,
        }
    if _is_expiring_soon(candidate, expiring_soon_minutes=config.expiring_soon_minutes):
        payload["alert_type"] = EXPIRING_SOON
        payload["reason"] = _operator_visibility_reason(
            candidate,
            prefix="fresh BTCUSDT paper candidate for operator visibility only is near freshness expiry",
        )
        payload["operator_action"] = "watch / approve paper / wait for next fresh candidate"
        return {
            "would_alert": True,
            "alert_type": EXPIRING_SOON,
            "signal_id": payload["signal_id"],
            "candidate": payload,
        }
    payload["alert_type"] = ACTIONABLE_PAPER
    payload["reason"] = _operator_visibility_reason(
        candidate,
        prefix="fresh BTCUSDT paper candidate for operator visibility only",
    )
    payload["operator_action"] = "watch / approve paper / wait for next fresh candidate"
    return {
        "would_alert": True,
        "alert_type": ACTIONABLE_PAPER,
        "signal_id": payload["signal_id"],
        "candidate": payload,
    }


def _select_operator_candidate(checks: list[LiveCandidateCheck], *, min_score: int) -> LiveCandidateCheck | None:
    strategy_config = load_strategy_config()
    min_hammer_strength = strategy_config.minimum_hammer_strength
    candidates = [
        check
        for check in checks
        if check.candidate.signal.symbol == PROTOCOL["symbol"]
        and check.candidate.signal.tradable is True
        and not check.candidate.signal.reject_reason
        and check.candidate.signal.hammer_strength >= min_hammer_strength
        and check.candidate.tier == ACTIONABLE_PAPER_TIER
        and check.candidate.score >= min_score
        and check.entry is not None
        and check.stop is not None
        and check.take_profit is not None
        and check.candidate.signal.direction in {"long", "short"}
    ]
    candidates.sort(
        key=lambda check: (
            check.freshness_status == "fresh",
            check.age_minutes is not None,
            -(check.age_minutes or 0.0),
            check.candidate.score,
            check.candidate.signal.timestamp,
        ),
        reverse=True,
    )
    return candidates[0] if candidates else None


def _is_expiring_soon(candidate: LiveCandidateCheck, *, expiring_soon_minutes: int) -> bool:
    if candidate.freshness_status != "fresh" or candidate.age_minutes is None or expiring_soon_minutes <= 0:
        return False
    return candidate.age_minutes >= max(candidate.fresh_minutes - expiring_soon_minutes, 0)


def _candidate_payload(candidate: LiveCandidateCheck) -> dict[str, Any]:
    signal = candidate.candidate.signal
    min_hammer_strength = load_strategy_config().minimum_hammer_strength
    return {
        "alert_type": None,
        "signal_id": signal.signal_id,
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "direction": signal.direction,
        "entry": candidate.entry,
        "stop": candidate.stop,
        "take_profit": candidate.take_profit,
        "score": candidate.candidate.score,
        "tier": candidate.candidate.tier,
        "hammer_strength": signal.hammer_strength,
        "minimum_hammer_strength": min_hammer_strength,
        "age_minutes": candidate.age_minutes,
        "freshness_status": candidate.freshness_status,
        "reason": candidate.reason,
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "operator_action": "watch / approve paper / wait for next fresh candidate",
    }


def _operator_visibility_reason(candidate: LiveCandidateCheck, *, prefix: str) -> str:
    direction_note = ""
    if candidate.candidate.signal.direction == "short":
        direction_note = "; short is paper/operator visibility only, not live approval"
    return (
        f"{prefix}; live readiness is not implied; checklist_status={candidate.decision}; "
        f"operator_context={_operator_context(candidate)}{direction_note}"
    )


def _operator_context(candidate: LiveCandidateCheck) -> str:
    if candidate.reason == "passes conservative manual tiny-live checklist":
        return "candidate fields are complete for paper/operator review"
    return candidate.reason


def build_notification_status_text(*, log_dir: str | Path | None = None) -> str:
    status = notification_status(log_dir=log_dir)
    lines = [
        "HAMMER RADAR NOTIFICATION STATUS",
        "live_execution_enabled: false",
        "order_placed: false",
        f"telegram_enabled: {str(status['telegram_enabled']).lower()}",
        f"telegram_configured: {str(status['telegram_configured']).lower()}",
        f"token_present: {str(status['token_present']).lower()}",
        f"chat_id_present: {str(status['chat_id_present']).lower()}",
        "token_preview: n/a",
        f"alerts_recorded: {status['alerts_recorded']}",
        f"last_alert: {_format_last_alert(status['last_alert'])}",
        "secrets_shown: false",
    ]
    return "\n".join(lines)


def build_notification_check_text(
    *,
    send: bool = False,
    channel: str = "none",
    log_dir: str | Path | None = None,
) -> str:
    payload = check_notifications(send=send, channel=channel, log_dir=log_dir)
    lines = [
        "HAMMER RADAR NOTIFICATION CHECK",
        "live_execution_enabled: false",
        "order_placed: false",
        f"would_alert: {str(payload['would_alert']).lower()}",
        f"alert_type: {payload['alert_type'] or 'none'}",
        f"signal_id: {payload['signal_id'] or 'n/a'}",
        f"readiness_status: {payload['readiness_status']}",
        f"ticket_status: {payload['ticket_status']}",
        f"dry_run_status: {payload['dry_run_status']}",
        f"live_safety_status: {payload['live_safety_status']}",
        f"send_requested: {str(payload['send_requested']).lower()}",
        f"channel: {payload['channel']}",
        f"telegram_status: {(payload.get('telegram') or {}).get('status')}",
        f"recorded: {str(payload['recorded']).lower()}",
        "secrets_shown: false",
    ]
    return "\n".join(lines)


def build_readiness_alerts_text(*, limit: int = 50, log_dir: str | Path | None = None) -> str:
    records = load_alert_records(limit=limit, log_dir=log_dir)
    lines = [
        "HAMMER RADAR READINESS ALERTS",
        "live_execution_enabled: false",
        "order_placed: false",
    ]
    if not records:
        return "\n".join([*lines, "no readiness alerts"])
    for record in records:
        lines.append(
            f"{record.get('created_at')} | {record.get('alert_id')} | {record.get('alert_type')} | "
            f"signal={record.get('signal_id') or 'n/a'} | telegram_sent={record.get('telegram_sent')}"
        )
    return "\n".join(lines)


def watch(*, log_dir: str | Path | None = None) -> int:
    config = load_notification_config()
    print(
        "notification_watcher started "
        f"telegram_enabled={config.telegram_enabled} telegram_configured={config.telegram_configured} "
        "live_execution_enabled=false order_placed=false",
        flush=True,
    )
    while True:
        try:
            channel = "telegram" if config.telegram_enabled else "none"
            result = check_notifications(send=config.telegram_enabled, channel=channel, log_dir=log_dir, config=config)
            print(
                f"{datetime.now(UTC).isoformat()} would_alert={result['would_alert']} "
                f"alert_type={result['alert_type'] or 'none'} telegram_status={result['telegram']['status']} "
                f"recorded={result['recorded']}",
                flush=True,
            )
        except Exception as exc:  # pragma: no cover - long-running process guard.
            print(f"{datetime.now(UTC).isoformat()} notification_watcher_error={exc.__class__.__name__}", flush=True)
        time.sleep(config.poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m src.app.hammer_radar.operator.notification_watcher")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--log-dir", default=None)
    args = parser.parse_args()
    if args.watch:
        return watch(log_dir=args.log_dir)
    print(build_notification_check_text(send=False, channel="none", log_dir=args.log_dir))
    return 0


def _sender_from_config(config: NotificationConfig) -> TelegramSender:
    def _send(chat_id: str, message: str) -> dict[str, Any]:
        return send_telegram_message(config.telegram_bot_token or "", chat_id, message)

    return _send


def _alerts_path(log_dir: Path) -> Path:
    return log_dir / ALERTS_FILENAME


def _alert_id(*, alert_type: str, signal_id: object, created_at: str) -> str:
    digest = hashlib.sha256(f"{alert_type}|{signal_id}|{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"alert_{digest}"


def _fallback_dedupe_key(evaluation: dict[str, Any], *, now: datetime, interval_seconds: int) -> str:
    bucket_size = max(interval_seconds, 1)
    bucket = int(now.timestamp() // bucket_size)
    parts = [
        str(evaluation.get("alert_type")),
        str(evaluation.get("readiness_status")),
        str(evaluation.get("ticket_status")),
        str(evaluation.get("dry_run_status")),
        str(bucket),
    ]
    return "|".join(parts)


def _env_bool(value: str | None, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(value: str | None, *, default: int, minimum: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(parsed, minimum)


def _clean_secret(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _format_value(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _format_last_alert(record: dict[str, Any] | None) -> str:
    if not record:
        return "none"
    return f"{record.get('created_at')} | {record.get('alert_type')} | signal={record.get('signal_id') or 'n/a'}"


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
