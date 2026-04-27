"""Friday manual tiny-live readiness checks for Hammer Radar."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.inspect import (
    LIVE_DECISION_ELIGIBLE,
    LIVE_DECISION_FORBIDDEN,
    LIVE_DECISION_PAPER_ONLY,
    build_live_candidate_snapshot,
)
from src.app.hammer_radar.operator.manual_outcomes import load_manual_outcomes

LIVE_EXECUTION_ENABLED = False
ORDER_PLACED = False
PROTOCOL = {
    "symbol": "BTCUSDT",
    "max_position_usd": 44,
    "preferred_leverage": 2,
    "max_leverage": 3,
    "margin": "isolated",
    "max_trades_per_day": 1,
    "hard_daily_stop": "one live loss or 5 USDT loss",
    "first_trade_requires_fresh_candidate": True,
    "long_only_default": True,
    "oversold_forbidden_first_test": True,
}


def build_readiness_payload(*, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC)
    snapshot = build_live_candidate_snapshot(
        limit=10,
        since_hours=24,
        min_score=90,
        symbol=PROTOCOL["symbol"],
        allow_short=False,
        allow_oversold=False,
        allow_trigger_flags=False,
        max_risk_usd=5.0,
        max_leverage=float(PROTOCOL["max_leverage"]),
        max_position_usd=float(PROTOCOL["max_position_usd"]),
        fresh_minutes=30,
        allow_expired=False,
        latest_only=False,
        log_dir=resolved_log_dir,
    )
    checks = snapshot["checks"]
    decisions = [check.decision for check in checks]
    latest_signal = max(snapshot["window_signals"], key=lambda signal: signal.timestamp, default=None)
    latest_age = _age_minutes(latest_signal.timestamp, generated_at) if latest_signal is not None else None
    eligible_checks = [
        check
        for check in checks
        if (
            check.decision == LIVE_DECISION_ELIGIBLE
            and check.freshness_status == "fresh"
            and check.candidate.signal.symbol == PROTOCOL["symbol"]
            and (check.capped_max_position_usd or 0.0) <= float(PROTOCOL["max_position_usd"])
            and check.suggested_leverage <= float(PROTOCOL["max_leverage"])
        )
    ]
    manual_outcomes = load_manual_outcomes(limit=0, log_dir=resolved_log_dir)
    today = generated_at.date()
    outcomes_today = [
        outcome
        for outcome in manual_outcomes
        if _record_date(outcome.get("created_at")) == today
    ]
    losses_today = sum(1 for outcome in outcomes_today if outcome.get("result") == "loss")
    pnl_usd_today = sum(float(outcome.get("pnl_usd") or 0.0) for outcome in outcomes_today)
    expired_eligible_count = sum(
        1
        for check in checks
        if (
            check.decision == LIVE_DECISION_ELIGIBLE
            and check.freshness_status == "expired"
        )
        or "freshness gate" in check.reason
    )

    blockers: list[str] = []
    if not eligible_checks:
        blockers.append("no fresh ELIGIBLE_TINY_LIVE BTCUSDT candidate")
    if not eligible_checks and expired_eligible_count:
        blockers.append("only expired otherwise-eligible candidates are available")
    if len(outcomes_today) >= int(PROTOCOL["max_trades_per_day"]):
        blockers.append("manual outcome already logged today")
    if losses_today > 0:
        blockers.append("at least one manual loss logged today")
    if pnl_usd_today <= -5.0:
        blockers.append("daily manual pnl is at or below -5 USDT")
    if LIVE_EXECUTION_ENABLED is not False:
        blockers.append("live_execution_enabled safety field is not false")
    if ORDER_PLACED is not False:
        blockers.append("order_placed safety field is not false")

    allowed_now = not blockers
    readiness_status = "READY" if allowed_now else "NOT_READY"
    reason_summary = (
        "fresh eligible BTCUSDT candidate available and no daily manual stop is active"
        if allowed_now
        else "; ".join(blockers)
    )
    next_required_action = (
        "Log decision before manual exchange action. App does not place orders."
        if allowed_now
        else "Wait for a fresh ELIGIBLE_TINY_LIVE BTCUSDT candidate and keep manual live trade disabled."
    )

    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "order_placed": ORDER_PLACED,
        "generated_at": generated_at.isoformat(),
        "archive_log_dir": str(resolved_log_dir),
        "readiness_status": readiness_status,
        "reason_summary": reason_summary,
        "protocol": dict(PROTOCOL),
        "current_state": {
            "fresh_eligible_count": len(eligible_checks),
            "expired_eligible_count": expired_eligible_count,
            "paper_only_count": decisions.count(LIVE_DECISION_PAPER_ONLY),
            "forbidden_count": decisions.count(LIVE_DECISION_FORBIDDEN),
            "latest_candidate_timestamp": latest_signal.timestamp if latest_signal is not None else None,
            "latest_candidate_age_minutes": latest_age,
            "manual_outcomes_today": len(outcomes_today),
            "losses_today": losses_today,
            "pnl_usd_today": pnl_usd_today,
        },
        "allowed_now": allowed_now,
        "blockers": blockers,
        "next_required_action": next_required_action,
        "today_timezone": "UTC",
    }


def build_readiness_text(*, log_dir: str | Path | None = None) -> str:
    payload = build_readiness_payload(log_dir=log_dir)
    state = payload["current_state"]
    protocol = payload["protocol"]
    lines = [
        "HAMMER RADAR FRIDAY READINESS",
        f"archive_log_dir: {payload['archive_log_dir']}",
        f"generated_at: {payload['generated_at']}",
        "today_timezone: UTC",
        "live_execution_enabled: false",
        "order_placed: false",
        f"readiness_status: {payload['readiness_status']}",
        f"allowed_now: {payload['allowed_now']}",
        f"reason_summary: {payload['reason_summary']}",
        f"next_required_action: {payload['next_required_action']}",
        "",
        "PROTOCOL",
        f"symbol: {protocol['symbol']}",
        f"max_position_usd: {protocol['max_position_usd']}",
        f"preferred_leverage: {protocol['preferred_leverage']}x",
        f"max_leverage: {protocol['max_leverage']}x",
        f"margin: {protocol['margin']}",
        f"max_trades_per_day: {protocol['max_trades_per_day']}",
        f"hard_daily_stop: {protocol['hard_daily_stop']}",
        f"first_trade_requires_fresh_candidate: {protocol['first_trade_requires_fresh_candidate']}",
        f"long_only_default: {protocol['long_only_default']}",
        f"oversold_forbidden_first_test: {protocol['oversold_forbidden_first_test']}",
        "",
        "CURRENT STATE",
        f"fresh_eligible_count: {state['fresh_eligible_count']}",
        f"expired_eligible_count: {state['expired_eligible_count']}",
        f"paper_only_count: {state['paper_only_count']}",
        f"forbidden_count: {state['forbidden_count']}",
        f"latest_candidate_timestamp: {state['latest_candidate_timestamp']}",
        f"latest_candidate_age_minutes: {state['latest_candidate_age_minutes']}",
        f"manual_outcomes_today: {state['manual_outcomes_today']}",
        f"losses_today: {state['losses_today']}",
        f"pnl_usd_today: {state['pnl_usd_today']}",
        "blockers: " + ("; ".join(payload["blockers"]) if payload["blockers"] else "none"),
    ]
    return "\n".join(lines)


def _record_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    parsed = _parse_datetime(value)
    return parsed.date() if parsed is not None else None


def _age_minutes(timestamp: str, generated_at: datetime) -> float | None:
    parsed = _parse_datetime(timestamp)
    if parsed is None:
        return None
    return (generated_at - parsed).total_seconds() / 60.0


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
