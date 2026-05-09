"""R72 selected higher-timeframe live policy/profile gate.

This module evaluates whether an explicitly selected higher-timeframe candidate
may enter the first-live approval chain. It is policy/profile only and never
places orders, signs payloads, mutates env files, or calls exchange networks.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from src.app.hammer_radar.operator.strategy_performance import (
    DEFAULT_BLOCKED_TIMEFRAMES,
    DEFAULT_CONTEXT_ONLY_TIMEFRAMES,
    DEFAULT_PAPER_ONLY_TIMEFRAMES,
    load_strategy_audit_config,
)

PHASE = "R72"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "HIGHER_TIMEFRAME_POLICY_PROFILE_ONLY"
PROFILE_NAME = "SELECTED_HIGHER_TIMEFRAME_REVIEW"

ENV_HIGHER_TIMEFRAME_ALLOWED = "HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED"
ENV_HIGHER_TIMEFRAME_ALLOWLIST = "HAMMER_HIGHER_TIMEFRAME_LIVE_TIMEFRAMES"
DEFAULT_ALLOWED_SELECTED_TIMEFRAMES = ("444m", "4H")
HIGHER_TIMEFRAME_CANDIDATES = ("444m", "888m", "4H", "13H", "13D")

ORDER_PLACED = False
REAL_ORDER_PLACED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

DEFAULT_PROFILE = {
    "symbol": "BTCUSDT",
    "margin_usdt": 44.0,
    "leverage": 10,
    "max_notional_usdt": 444.0,
    "margin_mode": "ISOLATED",
    "protective_orders_required": True,
    "one_attempt_only": True,
    "no_auto_entry": True,
    "no_automatic_selection": True,
    "no_order_by_default": True,
}

REQUIRES = {
    "exact_selection": True,
    "exact_live_approve": True,
    "intent": True,
    "rehearsal": True,
    "protective_orders": True,
    "test_order": True,
    "manual_env_review": True,
    "final_gate": True,
}


def get_higher_timeframe_live_policy(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    audit = load_strategy_audit_config(dict(source))
    enabled = _parse_bool(source.get(ENV_HIGHER_TIMEFRAME_ALLOWED), default=False)
    allowlist = _parse_timeframes(
        source.get(ENV_HIGHER_TIMEFRAME_ALLOWLIST),
        default=DEFAULT_ALLOWED_SELECTED_TIMEFRAMES,
    )
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "profile_name": PROFILE_NAME,
            "higher_timeframe_live_allowed": enabled,
            "selected_required": True,
            "allowed_selected_timeframes": list(allowlist),
            "blocked_timeframes": list(audit.blocked_timeframes),
            "context_only_timeframes": list(audit.context_only_timeframes),
            "paper_only_timeframes": list(audit.paper_only_timeframes),
            "default_allowed_selected_timeframes": list(DEFAULT_ALLOWED_SELECTED_TIMEFRAMES),
            "requires": dict(REQUIRES),
            "profile": dict(DEFAULT_PROFILE),
            "future_ramp_options": {
                "larger_margin_profiles_available": False,
                "automatic_size_ramp_enabled": False,
                "note": "R72 keeps higher-timeframe sizing on first-live defaults.",
            },
            "enable_hint": (
                f"set {ENV_HIGHER_TIMEFRAME_ALLOWED}=true and {ENV_HIGHER_TIMEFRAME_ALLOWLIST}=444m,4H"
                if not enabled
                else None
            ),
            "order_placed": ORDER_PLACED,
            "real_order_placed": REAL_ORDER_PLACED,
            "network_allowed": NETWORK_ALLOWED,
            "secrets_shown": SECRETS_SHOWN,
        }
    )


def evaluate_higher_timeframe_live_policy(
    candidate: Mapping[str, Any] | None,
    *,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    policy = get_higher_timeframe_live_policy(env=env)
    created_at = now or datetime.now(UTC)
    candidate = candidate or {}
    timeframe = _normalize_timeframe(candidate.get("timeframe"))
    symbol = str(candidate.get("symbol") or "").upper()
    direction = str(candidate.get("direction") or "").lower()
    queue_fresh = candidate.get("queue_fresh") is True
    selected = candidate.get("selected") is True or candidate.get("exact_selection") is True
    blockers: list[str] = []

    if not timeframe:
        blockers.append("candidate timeframe is missing")
    if symbol != "BTCUSDT":
        blockers.append("candidate symbol is not BTCUSDT")
    if direction != "long":
        blockers.append("candidate direction is not long")
    if not selected:
        blockers.append("exact candidate selection is required")
    if not queue_fresh:
        blockers.append("selected candidate is not queue-fresh")
    if not policy["higher_timeframe_live_allowed"]:
        blockers.append("higher timeframe live policy is disabled")

    audit = load_strategy_audit_config(dict(os.environ if env is None else env))
    if timeframe in audit.paper_only_timeframes:
        status = "PAPER_ONLY"
        blockers.append("timeframe remains paper-only by strategy policy")
    elif timeframe in audit.context_only_timeframes and timeframe not in policy["allowed_selected_timeframes"]:
        status = "CONTEXT_ONLY"
        blockers.append("timeframe is context-only and not selected higher-timeframe allowlisted")
    elif timeframe in audit.blocked_timeframes and timeframe not in policy["allowed_selected_timeframes"]:
        status = "BLOCKED"
        blockers.append("timeframe is blocked and not selected higher-timeframe allowlisted")
    elif timeframe in audit.allowed_tiny_live_timeframes:
        status = "TINY_LIVE_ALLOWED"
    elif timeframe in policy["allowed_selected_timeframes"]:
        status = "SELECTED_HIGHER_TIMEFRAME_ALLOWED"
    elif timeframe in HIGHER_TIMEFRAME_CANDIDATES:
        status = "SELECTED_BUT_NOT_LIVE_ELIGIBLE"
        blockers.append("timeframe is not in selected higher-timeframe allowlist")
    else:
        status = "BLOCKED"
        blockers.append("timeframe is not supported by higher-timeframe profile")

    candidate_allowed = bool(
        status == "SELECTED_HIGHER_TIMEFRAME_ALLOWED"
        and policy["higher_timeframe_live_allowed"] is True
        and selected
        and queue_fresh
        and symbol == "BTCUSDT"
        and direction == "long"
    )
    if not candidate_allowed and status == "SELECTED_HIGHER_TIMEFRAME_ALLOWED":
        status = "SELECTED_BUT_NOT_LIVE_ELIGIBLE"

    return _sanitize(
        {
            **policy,
            "created_at": created_at.isoformat(),
            "candidate_signal_id": candidate.get("signal_id"),
            "candidate_timeframe": timeframe,
            "candidate_allowed": candidate_allowed,
            "candidate_policy_status": status,
            "blockers": list(dict.fromkeys(blockers)),
            "near_expiration_warning": _near_expiration_warning(candidate),
            "order_placed": ORDER_PLACED,
            "real_order_placed": REAL_ORDER_PLACED,
            "network_allowed": NETWORK_ALLOWED,
            "secrets_shown": SECRETS_SHOWN,
        }
    )


def _near_expiration_warning(candidate: Mapping[str, Any]) -> str | None:
    age = _float_or_none(candidate.get("age_minutes"))
    cutoff = _float_or_none(candidate.get("queue_freshness_cutoff_minutes"))
    if age is None or cutoff is None or cutoff <= 0:
        return None
    remaining = cutoff - age
    if remaining <= 0:
        return "selected candidate is expired"
    if remaining <= min(15.0, cutoff * 0.1):
        return f"selected candidate expires in {round(remaining, 2)} minutes"
    return None


def _parse_timeframes(raw: str | None, *, default: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None or raw.strip() == "":
        return default
    values = tuple(_normalize_timeframe(part.strip()) for part in raw.split(",") if part.strip())
    return tuple(value for value in values if value)


def _normalize_timeframe(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    known = {
        "4m": "4m",
        "8m": "8m",
        "13m": "13m",
        "22m": "22m",
        "44m": "44m",
        "55m": "55m",
        "88m": "88m",
        "222m": "222m",
        "444m": "444m",
        "888m": "888m",
        "4h": "4H",
        "13h": "13H",
        "13d": "13D",
    }
    return known.get(raw.lower(), raw)


def _parse_bool(raw: object, *, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in ("order_placed", "real_order_placed", "network_allowed", "secrets_shown"):
            if key in sanitized:
                sanitized[key] = False
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
