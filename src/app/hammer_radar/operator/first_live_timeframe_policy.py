"""R73 unified first-live timeframe policy matrix.

This module is policy/profile only. It never places orders, signs payloads,
edits env files, reads secrets, or calls exchange networks.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

PHASE = "R73"
SYSTEM = "money_printing_machine_hammer_radar"
POLICY_NAME = "UNIFIED_FIRST_LIVE_TIMEFRAME_POLICY"
EXECUTION_MODE = "POLICY_MATRIX_ONLY_NO_ORDER"

ENV_MICRO_LIVE_ALLOWED = "HAMMER_MICRO_LIVE_ALLOWED"
ENV_MICRO_LIVE_TIMEFRAMES = "HAMMER_MICRO_LIVE_TIMEFRAMES"
ENV_TINY_LIVE_TIMEFRAMES = "HAMMER_TINY_LIVE_TIMEFRAMES"
ENV_HIGHER_TIMEFRAME_ALLOWED = "HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED"
ENV_HIGHER_TIMEFRAME_ALLOWLIST = "HAMMER_HIGHER_TIMEFRAME_LIVE_TIMEFRAMES"

DEFAULT_MICRO_LIVE_TIMEFRAMES = ("4m", "8m")
DEFAULT_TINY_LIVE_TIMEFRAMES = ("13m", "44m")
DEFAULT_HIGHER_TIMEFRAME_LIVE_TIMEFRAMES = ("444m", "4H")
CONTEXT_ONLY_TIMEFRAMES = ("88m", "888m", "13H", "13D")
BLOCKED_TIMEFRAMES = ("22m", "55m", "222m")

ORDER_PLACED = False
REAL_ORDER_PLACED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

BASE_PROFILE = {
    "symbol": "BTCUSDT",
    "margin_usdt": 44.0,
    "leverage": 10,
    "max_notional_usdt": 444.0,
    "margin_mode": "ISOLATED",
    "protective_orders_required": True,
    "one_attempt_only": True,
    "no_order_by_default": True,
}

REQUIRES_BASE = {
    "intent": True,
    "rehearsal": True,
    "protective_orders": True,
    "test_order": True,
    "manual_env_review": True,
    "final_gate": True,
}

FRESHNESS_CUTOFFS_MINUTES = {
    "4m": 4.5,
    "8m": 8.5,
    "13m": 13.5,
    "44m": 44.5,
    "444m": 444.5,
    "4H": 240.5,
}


def get_first_live_timeframe_policy(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    micro_live_allowed = _parse_bool(source.get(ENV_MICRO_LIVE_ALLOWED), default=False)
    higher_timeframe_live_allowed = _parse_bool(source.get(ENV_HIGHER_TIMEFRAME_ALLOWED), default=False)
    micro_live_timeframes = _parse_timeframes(source.get(ENV_MICRO_LIVE_TIMEFRAMES), default=DEFAULT_MICRO_LIVE_TIMEFRAMES)
    tiny_live_timeframes = _parse_timeframes(source.get(ENV_TINY_LIVE_TIMEFRAMES), default=DEFAULT_TINY_LIVE_TIMEFRAMES)
    higher_timeframe_live_timeframes = _parse_timeframes(
        source.get(ENV_HIGHER_TIMEFRAME_ALLOWLIST),
        default=DEFAULT_HIGHER_TIMEFRAME_LIVE_TIMEFRAMES,
    )
    profiles = {
        "MICRO_SELECTED_REVIEW": {
            **BASE_PROFILE,
            "profile_name": "MICRO_SELECTED_REVIEW",
            "timeframes": list(micro_live_timeframes),
            "requires_explicit_selection": True,
            "freshness_cutoffs_minutes": {tf: FRESHNESS_CUTOFFS_MINUTES[tf] for tf in micro_live_timeframes if tf in FRESHNESS_CUTOFFS_MINUTES},
        },
        "TINY_LIVE_REVIEW": {
            **BASE_PROFILE,
            "profile_name": "TINY_LIVE_REVIEW",
            "timeframes": list(tiny_live_timeframes),
            "requires_explicit_selection": False,
            "freshness_cutoffs_minutes": {tf: FRESHNESS_CUTOFFS_MINUTES[tf] for tf in tiny_live_timeframes if tf in FRESHNESS_CUTOFFS_MINUTES},
        },
        "SELECTED_HIGHER_TIMEFRAME_REVIEW": {
            **BASE_PROFILE,
            "profile_name": "SELECTED_HIGHER_TIMEFRAME_REVIEW",
            "timeframes": list(higher_timeframe_live_timeframes),
            "requires_explicit_selection": True,
            "freshness_cutoffs_minutes": {
                tf: FRESHNESS_CUTOFFS_MINUTES[tf] for tf in higher_timeframe_live_timeframes if tf in FRESHNESS_CUTOFFS_MINUTES
            },
        },
    }
    matrix = {
        "4m": {"category": "micro", "default_status": "PAPER_ONLY", "enabled_status": "MICRO_SELECTED_ALLOWED"},
        "8m": {"category": "micro", "default_status": "PAPER_ONLY", "enabled_status": "MICRO_SELECTED_ALLOWED"},
        "13m": {"category": "tiny", "default_status": "TINY_LIVE_ALLOWED"},
        "44m": {"category": "tiny", "default_status": "TINY_LIVE_ALLOWED"},
        "444m": {
            "category": "higher",
            "default_status": "SELECTED_BUT_NOT_LIVE_ELIGIBLE",
            "enabled_status": "SELECTED_HIGHER_TIMEFRAME_ALLOWED",
        },
        "4H": {
            "category": "higher",
            "default_status": "SELECTED_BUT_NOT_LIVE_ELIGIBLE",
            "enabled_status": "SELECTED_HIGHER_TIMEFRAME_ALLOWED",
        },
    }
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "policy_name": POLICY_NAME,
            "micro_live_allowed": micro_live_allowed,
            "micro_live_timeframes": list(micro_live_timeframes),
            "tiny_live_timeframes": list(tiny_live_timeframes),
            "higher_timeframe_live_allowed": higher_timeframe_live_allowed,
            "higher_timeframe_live_timeframes": list(higher_timeframe_live_timeframes),
            "profiles": profiles,
            "matrix": matrix,
            "requires": dict(REQUIRES_BASE),
            "enable_hints": {
                "micro": f"set {ENV_MICRO_LIVE_ALLOWED}=true and {ENV_MICRO_LIVE_TIMEFRAMES}=4m,8m"
                if not micro_live_allowed
                else None,
                "higher_timeframe": f"set {ENV_HIGHER_TIMEFRAME_ALLOWED}=true and {ENV_HIGHER_TIMEFRAME_ALLOWLIST}=444m,4H"
                if not higher_timeframe_live_allowed
                else None,
            },
            "order_placed": ORDER_PLACED,
            "real_order_placed": REAL_ORDER_PLACED,
            "network_allowed": NETWORK_ALLOWED,
            "secrets_shown": SECRETS_SHOWN,
        }
    )


def evaluate_first_live_timeframe_candidate(
    candidate: Mapping[str, Any] | None,
    *,
    env: Mapping[str, str] | None = None,
    selected: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    policy = get_first_live_timeframe_policy(env=env)
    candidate = candidate or {}
    timeframe = _normalize_timeframe(candidate.get("timeframe"))
    symbol = str(candidate.get("symbol") or "").upper()
    direction = str(candidate.get("direction") or "").lower()
    is_selected = selected or candidate.get("selected") is True or candidate.get("exact_selection") is True
    age = _float_or_none(candidate.get("age_minutes"))
    queue_fresh = candidate.get("queue_fresh")
    if queue_fresh is None:
        queue_fresh = _fresh_by_age(timeframe, age)
    first_live_match = symbol == "BTCUSDT" and direction == "long"
    blockers: list[str] = []
    category = _category(timeframe, policy)
    requires_selection = category in {"micro", "higher"}
    profile_name: str | None = None
    profile: dict[str, Any] | None = None

    if category == "micro":
        profile_name = "MICRO_SELECTED_REVIEW"
        if policy["micro_live_allowed"] and timeframe in policy["micro_live_timeframes"]:
            policy_status = "MICRO_SELECTED_ALLOWED"
        else:
            policy_status = "PAPER_ONLY"
            blockers.append("micro live policy is disabled")
    elif category == "tiny":
        profile_name = "TINY_LIVE_REVIEW"
        policy_status = "TINY_LIVE_ALLOWED"
    elif category == "higher":
        profile_name = "SELECTED_HIGHER_TIMEFRAME_REVIEW"
        if policy["higher_timeframe_live_allowed"] and timeframe in policy["higher_timeframe_live_timeframes"]:
            policy_status = "SELECTED_HIGHER_TIMEFRAME_ALLOWED"
        else:
            policy_status = "SELECTED_BUT_NOT_LIVE_ELIGIBLE"
            blockers.append("higher timeframe live policy is disabled or timeframe is not allowlisted")
    elif category == "context":
        policy_status = "CONTEXT_ONLY"
        blockers.append("timeframe is context-only")
    else:
        policy_status = "BLOCKED"
        blockers.append("timeframe is blocked from live")

    if profile_name is not None:
        profile = dict(policy["profiles"][profile_name])
    if not timeframe:
        blockers.append("candidate timeframe is missing")
    if not first_live_match:
        blockers.append("candidate does not match BTCUSDT long first-live profile")
    if queue_fresh is not True:
        blockers.append("candidate is outside strict first-live freshness window")
    if requires_selection and not is_selected:
        blockers.append("explicit candidate selection is required")

    live_candidate_allowed = bool(
        first_live_match
        and queue_fresh is True
        and policy_status in {"MICRO_SELECTED_ALLOWED", "TINY_LIVE_ALLOWED", "SELECTED_HIGHER_TIMEFRAME_ALLOWED"}
        and (not requires_selection or is_selected)
    )
    approval_allowed = live_candidate_allowed

    return _sanitize(
        {
            "signal_id": candidate.get("signal_id"),
            "timeframe": timeframe,
            "direction": direction or None,
            "selected": is_selected,
            "category": category,
            "profile_name": profile_name,
            "live_candidate_allowed": live_candidate_allowed,
            "approval_allowed": approval_allowed,
            "policy_status": policy_status,
            "requires_selection": requires_selection,
            "requires": {**REQUIRES_BASE, "exact_selection": requires_selection, "exact_live_approve": True},
            "profile": profile,
            "freshness_cutoff_minutes": FRESHNESS_CUTOFFS_MINUTES.get(timeframe or ""),
            "strict_fresh": queue_fresh is True,
            "blockers": list(dict.fromkeys(blockers)),
            "evaluated_at": (now or datetime.now(UTC)).isoformat(),
            "order_placed": ORDER_PLACED,
            "real_order_placed": REAL_ORDER_PLACED,
            "network_allowed": NETWORK_ALLOWED,
            "secrets_shown": SECRETS_SHOWN,
        }
    )


def _category(timeframe: str | None, policy: Mapping[str, Any]) -> str:
    if not timeframe:
        return "blocked"
    if timeframe in policy.get("micro_live_timeframes", []) or timeframe in DEFAULT_MICRO_LIVE_TIMEFRAMES:
        return "micro"
    if timeframe in policy.get("tiny_live_timeframes", []) or timeframe in DEFAULT_TINY_LIVE_TIMEFRAMES:
        return "tiny"
    if timeframe in policy.get("higher_timeframe_live_timeframes", []) or timeframe in DEFAULT_HIGHER_TIMEFRAME_LIVE_TIMEFRAMES:
        return "higher"
    if timeframe in CONTEXT_ONLY_TIMEFRAMES:
        return "context"
    return "blocked"


def _fresh_by_age(timeframe: str | None, age_minutes: float | None) -> bool:
    cutoff = FRESHNESS_CUTOFFS_MINUTES.get(timeframe or "")
    return bool(cutoff is not None and age_minutes is not None and age_minutes <= cutoff)


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
