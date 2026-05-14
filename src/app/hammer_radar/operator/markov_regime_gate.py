"""R82 Markov-style regime gate for Hammer Radar strategy candidates.

This module is read-only operator evidence. It uses local candle archives and
local strategy audit rows to classify regime context; it never fetches market
data, places orders, or changes live readiness.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.betrayal_candle_archive import load_archive_candles
from src.app.hammer_radar.operator.betrayal_inverse_validation import (
    TRUE_INVERSE_VALIDATED_PRIMARY,
    TRUE_INVERSE_VALIDATED_WATCHLIST,
    build_betrayal_inverse_validation,
)
from src.app.hammer_radar.operator.betrayal_strategy_audit import (
    BETRAYAL_PRIMARY_CANDIDATE,
    BETRAYAL_WATCHLIST,
    build_betrayal_strategy_audit,
)
from src.app.hammer_radar.operator.strategy_performance import (
    BTC_SYMBOL,
    build_live_eligibility_matrix,
)

PHASE = "R82"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "MARKOV_REGIME_GATE_ONLY_NO_ORDER"

BULL_TREND = "BULL_TREND"
BEAR_TREND = "BEAR_TREND"
RANGE = "RANGE"
HIGH_VOLATILITY = "HIGH_VOLATILITY"
LOW_VOLATILITY = "LOW_VOLATILITY"
TRANSITION = "TRANSITION"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

UP_STRONG = "UP_STRONG"
UP_WEAK = "UP_WEAK"
DOWN_STRONG = "DOWN_STRONG"
DOWN_WEAK = "DOWN_WEAK"
FLAT = "FLAT"
VOL_SPIKE = "VOL_SPIKE"

NORMAL = "NORMAL"
BETRAYAL = "BETRAYAL"

REGIME_SUPPORTS_CANDIDATE = "REGIME_SUPPORTS_CANDIDATE"
REGIME_REJECTS_CANDIDATE = "REGIME_REJECTS_CANDIDATE"
REGIME_NEUTRAL_OR_INSUFFICIENT_DATA = "REGIME_NEUTRAL_OR_INSUFFICIENT_DATA"
REGIME_PENDING_MORE_CANDLES = "REGIME_PENDING_MORE_CANDLES"

DEFAULT_SYMBOL = BTC_SYMBOL
DEFAULT_LIMIT = 120
MIN_CANDLES = 5
NORMAL_FOCUS_TIMEFRAMES = {"13m", "44m"}
BETRAYAL_TARGET_TIMEFRAMES = {"222m", "88m", "55m"}
VALIDATED_TRUE_INVERSE_STATUSES = {TRUE_INVERSE_VALIDATED_PRIMARY, TRUE_INVERSE_VALIDATED_WATCHLIST}

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
ORDER_PAYLOAD_CREATED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

NO_ORDER_NOTE = "R82 is a read-only regime filter. It does not approve or execute trades."


def build_markov_regime_gate(
    *,
    symbol: str = DEFAULT_SYMBOL,
    timeframe: str | None = None,
    limit: int = DEFAULT_LIMIT,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    generated_at = datetime.now(UTC).isoformat()
    normal_candidates = _normal_candidates(log_dir=resolved_log_dir, symbol=symbol)
    betrayal_candidates = _betrayal_candidates(log_dir=resolved_log_dir, symbol=symbol)
    if timeframe:
        normal_candidates = [row for row in normal_candidates if row.get("timeframe") == timeframe]
        betrayal_candidates = [row for row in betrayal_candidates if row.get("timeframe") == timeframe]

    candidate_timeframes = sorted(
        {
            str(row.get("timeframe"))
            for row in [*normal_candidates, *betrayal_candidates]
            if row.get("timeframe")
        }
    )
    if timeframe and timeframe not in candidate_timeframes:
        candidate_timeframes.append(timeframe)
    regimes = {
        item: classify_markov_regime(symbol=symbol, timeframe=item, limit=limit, log_dir=resolved_log_dir)
        for item in candidate_timeframes
    }
    normal_gates = [_candidate_gate(candidate, regimes=regimes) for candidate in normal_candidates]
    betrayal_gates = [_candidate_gate(candidate, regimes=regimes) for candidate in betrayal_candidates]
    aggregate_gates = [row for row in betrayal_gates if row.get("audit_scope") == "timeframe_aggregate"]
    direction_gates = [row for row in betrayal_gates if row.get("audit_scope") == "direction_entry_mode"]
    blockers = sorted(
        {
            str(blocker)
            for row in [*normal_gates, *betrayal_gates]
            for blocker in row.get("blockers", [])
            if blocker
        }
    )
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "generated_at": generated_at,
            "archive_log_dir": str(resolved_log_dir),
            "config": {
                "symbol": symbol,
                "timeframe": timeframe,
                "limit": int(limit),
                "min_candles": MIN_CANDLES,
                "data_source": "local candle_archive only",
            },
            "regime_summary": regimes,
            "transition_matrix_summary": {
                key: value.get("transition_summary", {}) for key, value in regimes.items()
            },
            "normal_candidate_regime_gates": normal_gates,
            "betrayal_candidate_regime_gates": betrayal_gates,
            "aggregate_candidate_regime_gates": aggregate_gates,
            "direction_entry_mode_candidate_regime_gates": direction_gates,
            "blockers": blockers,
            "notes": [
                NO_ORDER_NOTE,
                "Regime support is context only and never live eligibility.",
                "Betrayal candidates still require true inverse paper validation before any future consideration.",
                "R82 does not replace the normal 13m/44m promotion review path.",
            ],
            **_safety_fields(),
        }
    )


def classify_markov_regime(
    *,
    symbol: str,
    timeframe: str,
    limit: int = DEFAULT_LIMIT,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    candles = load_archive_candles(log_dir=log_dir, symbol=symbol, timeframe=timeframe)
    candles = sorted(candles, key=lambda row: str(row.get("open_time") or row.get("timestamp") or ""))
    if limit > 0:
        candles = candles[-limit:]
    if len(candles) < MIN_CANDLES:
        return _regime_payload(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            current_regime=INSUFFICIENT_DATA,
            confidence=0.0,
            micro_states=[],
            blockers=[f"candle_count below minimum {MIN_CANDLES}"],
        )

    returns = _returns(candles)
    ranges = [_range_pct(candle) for candle in candles]
    avg_abs_return = sum(abs(item) for item in returns) / len(returns) if returns else 0.0
    avg_range = sum(ranges) / len(ranges) if ranges else 0.0
    total_return = _pct_change(float(candles[0]["close"]), float(candles[-1]["close"]))
    micro_states = _micro_states(candles)
    state_counts = Counter(micro_states)
    transition_summary = _transition_summary(micro_states)
    current_regime = _regime_from_features(
        total_return=total_return,
        avg_abs_return=avg_abs_return,
        avg_range=avg_range,
        state_counts=state_counts,
        sample_count=len(candles),
    )
    confidence = _confidence(current_regime=current_regime, state_counts=state_counts, sample_count=len(micro_states))
    return _regime_payload(
        symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        current_regime=current_regime,
        confidence=confidence,
        micro_states=micro_states,
        blockers=[],
        total_return_pct=total_return,
        avg_abs_return_pct=avg_abs_return,
        avg_range_pct=avg_range,
        transition_summary=transition_summary,
    )


def format_markov_regime_gate_text(payload: Mapping[str, Any]) -> str:
    regimes = payload.get("regime_summary") if isinstance(payload.get("regime_summary"), dict) else {}
    normal = _list_field(payload, "normal_candidate_regime_gates")
    betrayal = _list_field(payload, "betrayal_candidate_regime_gates")
    blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
    lines = [
        f"R82 Markov Regime Gate: {payload.get('status')}",
        str(payload.get("execution_mode")),
        "No order placed. real_order_placed=false execution_attempted=false network_allowed=false secrets_shown=false.",
        "",
        "CURRENT REGIME SUMMARY",
    ]
    if not regimes:
        lines.append("  none")
    for timeframe, row in regimes.items():
        lines.append(
            f"  {timeframe}: {row.get('current_regime')} "
            f"confidence={row.get('regime_confidence')} candles={row.get('candle_count')}"
        )
    lines.extend(["", "NORMAL CANDIDATE GATES"])
    lines.extend(_format_gate_rows(normal))
    lines.extend(["", "BETRAYAL CANDIDATE GATES"])
    lines.extend(_format_gate_rows(betrayal))
    lines.extend(["", f"blockers: {', '.join(str(item) for item in blockers) if blockers else 'none'}", NO_ORDER_NOTE])
    return "\n".join(lines)


def _normal_candidates(*, log_dir: Path, symbol: str) -> list[dict[str, Any]]:
    matrix = build_live_eligibility_matrix(log_dir=log_dir)
    rows = matrix.get("recommendations") if isinstance(matrix.get("recommendations"), list) else []
    candidates = []
    for row in rows:
        timeframe = str(row.get("timeframe") or "")
        if timeframe not in NORMAL_FOCUS_TIMEFRAMES:
            continue
        candidates.append(
            {
                "candidate_id": f"normal|{symbol}|{timeframe}|{row.get('direction')}|{row.get('entry_mode')}",
                "candidate_family": NORMAL,
                "audit_scope": "normal_direction_entry_mode",
                "symbol": symbol,
                "timeframe": timeframe,
                "direction": row.get("direction"),
                "entry_mode": row.get("entry_mode"),
                "source_recommendation": row.get("recommendation"),
                "source_sample_count": row.get("sample_count"),
            }
        )
    return candidates


def _betrayal_candidates(*, log_dir: Path, symbol: str) -> list[dict[str, Any]]:
    audit = build_betrayal_strategy_audit(log_dir=log_dir)
    inverse = build_betrayal_inverse_validation(log_dir=log_dir)
    validation_statuses = _validation_status_map(inverse)
    aggregate_sources = [
        *_list_field(audit, "timeframe_aggregate_primary_candidates"),
        *_list_field(audit, "timeframe_aggregate_watchlist_candidates"),
    ]
    direction_sources = [
        *_list_field(audit, "direction_entry_mode_primary_candidates"),
        *_list_field(audit, "direction_entry_mode_watchlist_candidates"),
    ]
    candidates = []
    for row in aggregate_sources:
        timeframe = str(row.get("timeframe") or "")
        if timeframe not in BETRAYAL_TARGET_TIMEFRAMES:
            continue
        key = _candidate_validation_key(row)
        candidates.append(
            {
                "candidate_id": f"betrayal|aggregate|{symbol}|{timeframe}",
                "candidate_family": BETRAYAL,
                "audit_scope": "timeframe_aggregate",
                "symbol": symbol,
                "timeframe": timeframe,
                "direction": None,
                "betrayal_direction": row.get("betrayal_direction"),
                "entry_mode": None,
                "source_recommendation": row.get("recommendation"),
                "true_inverse_validation_status": validation_statuses.get(key),
                "source_sample_count": row.get("sample_count"),
            }
        )
    for row in direction_sources:
        key = _candidate_validation_key(row)
        candidates.append(
            {
                "candidate_id": (
                    f"betrayal|direction_entry_mode|{symbol}|{row.get('timeframe')}|"
                    f"{row.get('original_direction')}->{row.get('betrayal_direction')}|{row.get('entry_mode')}"
                ),
                "candidate_family": BETRAYAL,
                "audit_scope": "direction_entry_mode",
                "symbol": symbol,
                "timeframe": row.get("timeframe"),
                "direction": row.get("betrayal_direction"),
                "original_direction": row.get("original_direction"),
                "betrayal_direction": row.get("betrayal_direction"),
                "entry_mode": row.get("entry_mode"),
                "source_recommendation": row.get("recommendation"),
                "true_inverse_validation_status": validation_statuses.get(key),
                "source_sample_count": row.get("sample_count"),
            }
        )
    return candidates


def _candidate_gate(candidate: Mapping[str, Any], *, regimes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    timeframe = str(candidate.get("timeframe") or "")
    regime = regimes.get(timeframe, {})
    current_regime = str(regime.get("current_regime") or INSUFFICIENT_DATA)
    direction = candidate.get("direction")
    blockers = []
    if current_regime == INSUFFICIENT_DATA:
        blockers.append("insufficient_regime_candles")
    if candidate.get("candidate_family") == BETRAYAL:
        validation_status = candidate.get("true_inverse_validation_status")
        if validation_status not in VALIDATED_TRUE_INVERSE_STATUSES:
            blockers.append("true_inverse_validation_pending")
        if candidate.get("audit_scope") == "timeframe_aggregate" and not direction:
            blockers.append("aggregate_betrayal_direction_context_only")
    gate_status, reason = _gate_status_for_direction(
        direction=str(direction or ""),
        current_regime=current_regime,
        candidate_family=str(candidate.get("candidate_family") or ""),
        audit_scope=str(candidate.get("audit_scope") or ""),
    )
    if current_regime == INSUFFICIENT_DATA:
        gate_status = REGIME_PENDING_MORE_CANDLES
        reason = "regime classifier has insufficient local candle data"
    return _sanitize(
        {
            **dict(candidate),
            "current_regime": current_regime,
            "regime_confidence": regime.get("regime_confidence", 0.0),
            "transition_summary": regime.get("transition_summary", {}),
            "gate_status": gate_status,
            "gate_reason": reason,
            "blockers": blockers,
            "operator_note": _operator_note(gate_status, candidate_family=str(candidate.get("candidate_family") or "")),
            **_safety_fields(),
        }
    )


def _gate_status_for_direction(
    *,
    direction: str,
    current_regime: str,
    candidate_family: str,
    audit_scope: str,
) -> tuple[str, str]:
    if candidate_family == BETRAYAL and audit_scope == "timeframe_aggregate" and not direction:
        return REGIME_NEUTRAL_OR_INSUFFICIENT_DATA, "aggregate betrayal candidate has no validated direction split"
    if direction == "long":
        if current_regime == BULL_TREND:
            return REGIME_SUPPORTS_CANDIDATE, "bull trend supports long candidate context"
        if current_regime == BEAR_TREND:
            return REGIME_REJECTS_CANDIDATE, "bear trend rejects long candidate context"
    if direction == "short":
        if current_regime == BEAR_TREND:
            return REGIME_SUPPORTS_CANDIDATE, "bear trend supports short candidate context"
        if current_regime == BULL_TREND:
            return REGIME_REJECTS_CANDIDATE, "bull trend rejects short candidate context"
    return REGIME_NEUTRAL_OR_INSUFFICIENT_DATA, f"{current_regime} is contextual or neutral for this candidate"


def _regime_from_features(
    *,
    total_return: float,
    avg_abs_return: float,
    avg_range: float,
    state_counts: Counter,
    sample_count: int,
) -> str:
    if avg_abs_return >= 2.5 or avg_range >= 4.0 or state_counts[VOL_SPIKE] >= max(2, sample_count // 3):
        return HIGH_VOLATILITY
    if abs(total_return) <= 0.4 and avg_abs_return <= 0.5:
        return LOW_VOLATILITY if avg_range <= 0.6 else RANGE
    up_count = state_counts[UP_STRONG] + state_counts[UP_WEAK]
    down_count = state_counts[DOWN_STRONG] + state_counts[DOWN_WEAK]
    if total_return >= 1.0 and up_count > down_count:
        return BULL_TREND
    if total_return <= -1.0 and down_count > up_count:
        return BEAR_TREND
    if abs(total_return) <= 1.0 and abs(up_count - down_count) <= max(1, sample_count // 5):
        return RANGE
    return TRANSITION


def _micro_states(candles: list[Mapping[str, Any]]) -> list[str]:
    states = []
    previous_close = float(candles[0]["close"])
    for candle in candles[1:]:
        close = float(candle["close"])
        candle_return = _pct_change(previous_close, close)
        candle_range = _range_pct(candle)
        if candle_range >= 4.0 or abs(candle_return) >= 2.5:
            states.append(VOL_SPIKE)
        elif candle_return >= 1.0:
            states.append(UP_STRONG)
        elif candle_return > 0.15:
            states.append(UP_WEAK)
        elif candle_return <= -1.0:
            states.append(DOWN_STRONG)
        elif candle_return < -0.15:
            states.append(DOWN_WEAK)
        else:
            states.append(FLAT)
        previous_close = close
    return states


def _transition_summary(states: list[str]) -> dict[str, Any]:
    transitions: dict[str, Counter] = {}
    for left, right in zip(states, states[1:], strict=False):
        transitions.setdefault(left, Counter())[right] += 1
    matrix = {}
    for state, counts in transitions.items():
        total = sum(counts.values())
        matrix[state] = {
            "total": total,
            "probabilities": {
                target: round(count / total, 4) for target, count in sorted(counts.items())
            },
        }
    latest_state = states[-1] if states else None
    latest_next = matrix.get(latest_state, {}).get("probabilities", {}) if latest_state else {}
    return {
        "state_count": len(states),
        "latest_state": latest_state,
        "state_distribution": {
            state: round(count / len(states), 4) for state, count in sorted(Counter(states).items())
        }
        if states
        else {},
        "matrix": matrix,
        "latest_state_next_probabilities": latest_next,
    }


def _regime_payload(
    *,
    symbol: str,
    timeframe: str,
    candles: list[Mapping[str, Any]],
    current_regime: str,
    confidence: float,
    micro_states: list[str],
    blockers: list[str],
    total_return_pct: float | None = None,
    avg_abs_return_pct: float | None = None,
    avg_range_pct: float | None = None,
    transition_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _sanitize(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "current_regime": current_regime,
            "regime_confidence": round(confidence, 4),
            "candle_count": len(candles),
            "earliest_candle": str(candles[0].get("open_time") or candles[0].get("timestamp"))
            if candles
            else None,
            "latest_candle": str(candles[-1].get("open_time") or candles[-1].get("timestamp"))
            if candles
            else None,
            "features": {
                "total_return_pct": round(total_return_pct, 4) if total_return_pct is not None else None,
                "avg_abs_return_pct": round(avg_abs_return_pct, 4)
                if avg_abs_return_pct is not None
                else None,
                "avg_range_pct": round(avg_range_pct, 4) if avg_range_pct is not None else None,
                "micro_state_count": len(micro_states),
            },
            "transition_summary": dict(transition_summary or _transition_summary(micro_states)),
            "blockers": blockers,
            **_safety_fields(),
        }
    )


def _validation_status_map(payload: Mapping[str, Any]) -> dict[tuple[Any, ...], str]:
    rows = [
        *_list_field(payload, "timeframe_aggregate_validations"),
        *_list_field(payload, "direction_entry_mode_validations"),
    ]
    return {_candidate_validation_key(row): str(row.get("validation_status")) for row in rows}


def _candidate_validation_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("audit_scope"),
        row.get("timeframe"),
        row.get("original_direction"),
        row.get("betrayal_direction"),
        row.get("entry_mode"),
    )


def _returns(candles: list[Mapping[str, Any]]) -> list[float]:
    values = []
    previous_close = float(candles[0]["close"])
    for candle in candles[1:]:
        close = float(candle["close"])
        values.append(_pct_change(previous_close, close))
        previous_close = close
    return values


def _range_pct(candle: Mapping[str, Any]) -> float:
    low = float(candle.get("low") or 0.0)
    high = float(candle.get("high") or 0.0)
    close = float(candle.get("close") or 0.0)
    denominator = close if close else 1.0
    return ((high - low) / denominator) * 100.0


def _pct_change(left: float, right: float) -> float:
    if left == 0.0:
        return 0.0
    return ((right - left) / left) * 100.0


def _confidence(*, current_regime: str, state_counts: Counter, sample_count: int) -> float:
    if current_regime == INSUFFICIENT_DATA or sample_count == 0:
        return 0.0
    if current_regime == BULL_TREND:
        support = state_counts[UP_STRONG] + state_counts[UP_WEAK]
    elif current_regime == BEAR_TREND:
        support = state_counts[DOWN_STRONG] + state_counts[DOWN_WEAK]
    elif current_regime == HIGH_VOLATILITY:
        support = state_counts[VOL_SPIKE]
    elif current_regime in {RANGE, LOW_VOLATILITY}:
        support = state_counts[FLAT] + state_counts[UP_WEAK] + state_counts[DOWN_WEAK]
    else:
        support = sample_count - max(state_counts.values(), default=0)
    return min(1.0, max(0.0, support / sample_count))


def _operator_note(gate_status: str, *, candidate_family: str) -> str:
    if gate_status == REGIME_SUPPORTS_CANDIDATE:
        return "Regime supports this candidate context; this is not live approval."
    if gate_status == REGIME_REJECTS_CANDIDATE:
        return "Regime rejects this candidate context; keep it out of promotion until context changes."
    if gate_status == REGIME_PENDING_MORE_CANDLES:
        return "Collect more local candle archive data before using regime context."
    if candidate_family == BETRAYAL:
        return "Regime is contextual only; betrayal candidates still need true inverse validation."
    return "Regime is neutral or inconclusive for this candidate."


def _format_gate_rows(rows: list[Mapping[str, Any]]) -> list[str]:
    if not rows:
        return ["  none"]
    formatted = []
    for row in rows:
        formatted.append(
            "  "
            f"{row.get('gate_status')} {row.get('candidate_family')} "
            f"{row.get('timeframe')} {row.get('direction') or row.get('betrayal_direction') or 'aggregate'} "
            f"regime={row.get('current_regime')} confidence={row.get('regime_confidence')} "
            f"source={row.get('source_recommendation')}"
        )
    return formatted


def _list_field(payload: Mapping[str, Any], key: str) -> list:
    value = payload.get(key)
    return value if isinstance(value, list) else []


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
        ):
            if key in sanitized:
                sanitized[key] = False
        if "global_kill_switch" in sanitized:
            sanitized["global_kill_switch"] = True
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
