"""R270B strategy-qualified tiny-live lane selection.

This module is local-config and local-ledger only. It never enables live
execution, creates order payloads, submits orders, or calls Binance.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.tiny_live_risk_contract_validation import (
    DEFAULT_MAX_LOSS_USDT,
    DEFAULT_RISK_CONTRACT_CONFIG_PATH,
    EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE,
    R267_MAX_LEVERAGE,
    R267_MAX_POSITION_NOTIONAL_USDT,
    build_tiny_live_risk_contract_validation_summary,
    load_tiny_live_risk_contract_for_lane,
)

BTC_SYMBOL = "BTCUSDT"
DEFAULT_MIN_SAMPLE = 30
PREFERRED_ENTRY_MODE = "ladder_close_50_618"
STRATEGY_PROMOTION_EVENTS_FILENAME = "strategy_promotion_events.ndjson"
DEFAULT_MIN_WIN_RATE_PCT = 55.0
NEAR_MISS_MIN_WIN_RATE_PCT = 53.0
LIVE_QUALIFIED = "LIVE_QUALIFIED"
NEAR_MISS_INCUBATOR = "NEAR_MISS_INCUBATOR"
PAPER_ONLY = "PAPER_ONLY"
R270B_CREATED_BY_PHASE = "R270B_STRATEGY_QUALIFIED_LANE_RISK_CONTRACT_SELECTION"
R270B_RISK_CONTRACT_APPLY_CONFIRMATION_PHRASE = (
    "I CONFIRM R270B EXACT LANE RISK CONTRACT APPLY ONLY; "
    "80 USDT NOTIONAL CAP; 10X LEVERAGE; NO LIVE ENABLEMENT; "
    "NO ORDER; NO BINANCE ORDER CALL."
)

LIVE_EXECUTION_ENABLED = False
LIVE_AUTHORIZED = False
ORDER_PLACED = False
REAL_ORDER_PLACED = False
SUBMIT_ATTEMPTED = False
BINANCE_ORDER_ENDPOINT_CALLED = False
SECRETS_SHOWN = False


def build_lane_key(
    *,
    symbol: object,
    timeframe: object,
    direction: object,
    entry_mode: object = PREFERRED_ENTRY_MODE,
) -> str:
    return "|".join(
        [
            str(symbol or ""),
            str(timeframe or ""),
            str(direction or ""),
            str(entry_mode or PREFERRED_ENTRY_MODE),
        ]
    )


def build_strategy_lane_qualification(
    *,
    symbol: object,
    timeframe: object,
    direction: object,
    entry_mode: object,
    log_dir: str | Path | None = None,
    evidence: Mapping[str, Any] | None = None,
    config: Any | None = None,
    min_win_rate_pct: float = DEFAULT_MIN_WIN_RATE_PCT,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    audit_config = config or _load_strategy_audit_config()
    min_sample = max(int(getattr(audit_config, "min_sample", DEFAULT_MIN_SAMPLE) or DEFAULT_MIN_SAMPLE), DEFAULT_MIN_SAMPLE)
    lane_key = build_lane_key(symbol=symbol, timeframe=timeframe, direction=direction, entry_mode=entry_mode)
    raw_evidence = dict(evidence) if isinstance(evidence, Mapping) else _find_strategy_evidence(resolved_log_dir, lane_key=lane_key)
    win_rate = _float_or_none(raw_evidence.get("win_rate_pct"))
    sample_count = _int_or_none(raw_evidence.get("sample_count") or raw_evidence.get("samples"))
    avg_pnl_pct = _float_or_none(raw_evidence.get("avg_pnl_pct"))
    live_classification = _classify_strategy_lane(
        win_rate_pct=win_rate,
        sample_count=sample_count,
        avg_pnl_pct=avg_pnl_pct,
        min_sample=min_sample,
        min_win_rate_pct=float(min_win_rate_pct),
    )
    blockers: list[str] = []
    if str(symbol or "") != BTC_SYMBOL:
        blockers.append("strategy_lane_symbol_not_BTCUSDT")
    if not str(timeframe or ""):
        blockers.append("strategy_lane_timeframe_missing")
    if str(direction or "") not in {"long", "short"}:
        blockers.append("strategy_lane_direction_not_long_or_short")
    if not str(entry_mode or ""):
        blockers.append("strategy_lane_entry_mode_missing")
    if win_rate is None:
        blockers.append("strategy_lane_win_rate_missing")
        blockers.append("strategy_evidence_missing")
    elif win_rate < float(min_win_rate_pct):
        blockers.append("strategy_near_miss_not_live_eligible")
        blockers.append("win_rate_below_operator_55_policy")
        blockers.append("strategy_lane_win_rate_below_55")
        blockers.append("strategy_win_rate_below_55")
    if sample_count is None:
        blockers.append("strategy_lane_sample_count_missing")
        blockers.append("strategy_evidence_missing")
    elif sample_count < min_sample:
        blockers.append("strategy_lane_sample_count_below_minimum")
        blockers.append("strategy_sample_count_below_minimum")
    if avg_pnl_pct is None:
        blockers.append("strategy_lane_avg_pnl_pct_missing")
        blockers.append("strategy_evidence_missing")
    elif avg_pnl_pct <= 0.0:
        blockers.append("strategy_lane_avg_pnl_pct_not_positive")
        blockers.append("strategy_avg_pnl_pct_not_positive")

    return {
        **_safety_fields(),
        "lane_key": lane_key,
        "strategy_qualified": not blockers,
        "qualification_status": "QUALIFIED" if not blockers else "BLOCKED",
        "live_qualification_class": live_classification,
        "watch_category": live_classification,
        "near_miss_incubator": live_classification == NEAR_MISS_INCUBATOR,
        "paper_only": live_classification == PAPER_ONLY,
        "manual_live_unlock_allowed": live_classification == LIVE_QUALIFIED and not blockers,
        "near_miss_min_win_rate_pct": NEAR_MISS_MIN_WIN_RATE_PCT,
        "win_rate_pct": win_rate,
        "sample_count": sample_count,
        "avg_pnl_pct": avg_pnl_pct,
        "min_sample": min_sample,
        "min_sample_count": min_sample,
        "min_win_rate_pct": float(min_win_rate_pct),
        "evidence_policy_all_timeframes_enabled": True,
        "symbol": str(symbol or ""),
        "timeframe": str(timeframe or ""),
        "direction": str(direction or ""),
        "entry_mode": str(entry_mode or ""),
        "raw_evidence": raw_evidence,
        "evidence_found": bool(raw_evidence),
        "blocked_by": _dedupe(blockers),
        "reason": "strategy evidence passes R270B tiny-live lane policy" if not blockers else "; ".join(_dedupe(blockers)),
    }


def build_exact_lane_risk_contract_status(
    *,
    lane_key: str,
    risk_contract_config_path: str | Path | None = None,
    strategy_qualification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    loaded = load_tiny_live_risk_contract_for_lane(
        risk_contract_config_path=risk_contract_config_path or DEFAULT_RISK_CONTRACT_CONFIG_PATH,
        official_lane_key=lane_key,
    )
    summary = build_tiny_live_risk_contract_validation_summary(risk_contract=loaded)
    contract = loaded.get("contract") if isinstance(loaded.get("contract"), Mapping) else {}
    exact_contract_found = bool(loaded.get("official_contract_found")) and _contract_lane_key(contract) == lane_key
    blockers: list[str] = []
    if not exact_contract_found:
        blockers.append("exact_lane_risk_contract_missing")
    if summary.get("risk_contract_valid") is not True:
        blockers.extend(str(item) for item in summary.get("blocked_by") or [])
    if contract and contract.get("live_execution_enabled") is True:
        blockers.append("risk_contract_live_execution_enabled_not_false")
    if contract and contract.get("live_authorized") not in {False, None}:
        blockers.append("risk_contract_live_authorized_not_false")
    if strategy_qualification and strategy_qualification.get("strategy_qualified") is not True:
        blockers.append("strategy_lane_not_qualified")
    return {
        **_safety_fields(),
        "lane_key": lane_key,
        "risk_contract_path": str(loaded.get("path") or risk_contract_config_path or DEFAULT_RISK_CONTRACT_CONFIG_PATH),
        "exact_contract_found": exact_contract_found,
        "risk_contract_valid": exact_contract_found and summary.get("risk_contract_valid") is True and not blockers,
        "contract": dict(contract),
        "validation_summary": summary,
        "blocked_by": _dedupe(blockers),
        "no_cross_lane_borrowing": True,
    }


def guarded_apply_exact_lane_risk_contract(
    *,
    lane_key: str,
    strategy_qualification: Mapping[str, Any],
    risk_contract_config_path: str | Path | None = None,
    apply_contract: bool = False,
    confirm_apply: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    path = Path(risk_contract_config_path) if risk_contract_config_path is not None else DEFAULT_RISK_CONTRACT_CONFIG_PATH
    confirmation_valid = confirm_apply == R270B_RISK_CONTRACT_APPLY_CONFIRMATION_PHRASE
    current = build_exact_lane_risk_contract_status(
        lane_key=lane_key,
        risk_contract_config_path=path,
        strategy_qualification=strategy_qualification,
    )
    blockers: list[str] = []
    if strategy_qualification.get("strategy_qualified") is not True:
        blockers.append("strategy_lane_not_qualified")
    if current.get("exact_contract_found") is True:
        blockers.append("exact_lane_risk_contract_already_exists")
    if apply_contract and not confirmation_valid:
        blockers.append("bad_confirmation")
    if not path.exists():
        blockers.append("risk_contract_config_missing")
    if blockers or not apply_contract:
        return {
            **_safety_fields(),
            "attempted": bool(apply_contract),
            "succeeded": False,
            "risk_contract_config_written": False,
            "confirmation_valid": bool(confirmation_valid),
            "lane_key": lane_key,
            "exact_contract_existed_before": bool(current.get("exact_contract_found")),
            "contract_preview": build_explicit_lane_risk_contract(
                lane_key=lane_key,
                strategy_qualification=strategy_qualification,
                now=now,
            ),
            "blocked_by": _dedupe(blockers),
        }

    raw = json.loads(path.read_text(encoding="utf-8"))
    updated = deepcopy(raw)
    contracts = updated.setdefault("risk_contracts", [])
    if not isinstance(contracts, list):
        return {
            **_safety_fields(),
            "attempted": True,
            "succeeded": False,
            "risk_contract_config_written": False,
            "confirmation_valid": True,
            "lane_key": lane_key,
            "exact_contract_existed_before": False,
            "contract_preview": {},
            "blocked_by": ["risk_contracts_not_list"],
        }
    contract = build_explicit_lane_risk_contract(lane_key=lane_key, strategy_qualification=strategy_qualification, now=now)
    contracts.append(contract)
    path.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        **_safety_fields(),
        "attempted": True,
        "succeeded": True,
        "risk_contract_config_written": True,
        "confirmation_valid": True,
        "lane_key": lane_key,
        "exact_contract_existed_before": False,
        "contract_preview": contract,
        "blocked_by": [],
    }


def build_explicit_lane_risk_contract(
    *,
    lane_key: str,
    strategy_qualification: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    symbol, timeframe, direction, entry_mode = _lane_parts(lane_key)
    generated_at = now or datetime.now(UTC)
    return {
        "official_lane_key": lane_key,
        "contract_id": f"r270b_contract_{symbol}_{timeframe}_{direction}_{entry_mode}",
        "created_at": generated_at.isoformat(),
        "created_by_phase": R270B_CREATED_BY_PHASE,
        "approval_status": "CONFIG_WRITTEN_NOT_LIVE_AUTHORIZED",
        "approved": False,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": entry_mode,
        "tiny_live_contract_mode": EXPLICIT_NOTIONAL_CAP_WITH_LEVERAGE_MODE,
        "max_position_notional_usdt": R267_MAX_POSITION_NOTIONAL_USDT,
        "max_notional_usdt": R267_MAX_POSITION_NOTIONAL_USDT,
        "leverage": R267_MAX_LEVERAGE,
        "margin_budget_usdt": 8.0,
        "tiny_live_margin_usdt": 8.0,
        "max_margin_usdt": 8.0,
        "max_loss_usdt": DEFAULT_MAX_LOSS_USDT,
        "margin_mode": "ISOLATED_REQUIRED",
        "protective_stop_required": True,
        "take_profit_required": True,
        "reduce_only_allowed": True,
        "live_execution_enabled": False,
        "live_authorized": False,
        "operator_final_approval_required": True,
        "order_payload_forbidden_until_live_gate": True,
        "binance_call_forbidden_until_live_gate": True,
        "source_strategy_qualification": {
            "lane_key": strategy_qualification.get("lane_key"),
            "win_rate_pct": strategy_qualification.get("win_rate_pct"),
            "sample_count": strategy_qualification.get("sample_count"),
            "avg_pnl_pct": strategy_qualification.get("avg_pnl_pct"),
            "min_sample": strategy_qualification.get("min_sample"),
            "min_win_rate_pct": strategy_qualification.get("min_win_rate_pct"),
            "qualification_status": strategy_qualification.get("qualification_status"),
        },
        "notes": [
            "R270B exact-lane contract only; no cross-lane borrowing.",
            "This config write does not enable live execution, create payloads, sign requests, or place orders.",
        ],
    }


def _find_strategy_evidence(log_dir: Path, *, lane_key: str) -> dict[str, Any]:
    for filename in (
        "strategy_promotion_status.ndjson",
        STRATEGY_PROMOTION_EVENTS_FILENAME,
        "strategy_performance.ndjson",
    ):
        for row in _read_ndjson_reverse(log_dir / filename):
            for candidate in _candidate_rows(row):
                candidate_lane = candidate.get("strategy_key") or candidate.get("lane_key") or _lane_key_from_mapping(candidate)
                if candidate_lane == lane_key:
                    return {**candidate, "_source_path": str(log_dir / filename)}
    try:
        from src.app.hammer_radar.operator.strategy_performance import build_live_eligibility_matrix

        matrix = build_live_eligibility_matrix(log_dir=log_dir)
    except Exception:
        matrix = {}
    for candidate in matrix.get("recommendations") or []:
        if not isinstance(candidate, Mapping):
            continue
        candidate_lane = candidate.get("strategy_key") or candidate.get("lane_key") or _lane_key_from_mapping(candidate)
        if candidate_lane == lane_key:
            return {**dict(candidate), "_source_path": "computed_live_eligibility_matrix"}
    return {}


def _load_strategy_audit_config() -> Any:
    from src.app.hammer_radar.operator.strategy_performance import load_strategy_audit_config

    return load_strategy_audit_config()


def _candidate_rows(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [dict(row)]
    for key in ("promotion_ready", "near_promotion", "blocked_candidates", "recommendations", "groups"):
        value = row.get(key)
        if isinstance(value, list):
            rows.extend(dict(item) for item in value if isinstance(item, Mapping))
        elif isinstance(value, Mapping):
            for nested in value.values():
                if isinstance(nested, list):
                    rows.extend(dict(item) for item in nested if isinstance(item, Mapping))
    return rows


def _read_ndjson_reverse(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
    return list(reversed(records))


def _lane_key_from_mapping(row: Mapping[str, Any]) -> str | None:
    if row.get("strategy_key"):
        return str(row["strategy_key"])
    if not any(row.get(key) for key in ("symbol", "timeframe", "direction")):
        return None
    return build_lane_key(
        symbol=row.get("symbol") or BTC_SYMBOL,
        timeframe=row.get("timeframe"),
        direction=row.get("direction"),
        entry_mode=row.get("entry_mode") or PREFERRED_ENTRY_MODE,
    )


def _contract_lane_key(contract: Mapping[str, Any]) -> str:
    return str(contract.get("official_lane_key") or "") or build_lane_key(
        symbol=contract.get("symbol"),
        timeframe=contract.get("timeframe"),
        direction=contract.get("direction"),
        entry_mode=contract.get("entry_mode"),
    )


def _lane_parts(lane_key: str) -> tuple[str, str, str, str]:
    parts = str(lane_key or "").split("|")
    padded = [*parts, "", "", "", ""]
    return padded[0], padded[1], padded[2], padded[3]


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _classify_strategy_lane(
    *,
    win_rate_pct: float | None,
    sample_count: int | None,
    avg_pnl_pct: float | None,
    min_sample: int,
    min_win_rate_pct: float,
) -> str:
    if sample_count is None or sample_count < min_sample:
        return PAPER_ONLY
    if avg_pnl_pct is None or avg_pnl_pct <= 0.0:
        return PAPER_ONLY
    if win_rate_pct is None:
        return PAPER_ONLY
    if win_rate_pct >= min_win_rate_pct:
        return LIVE_QUALIFIED
    if NEAR_MISS_MIN_WIN_RATE_PCT <= win_rate_pct < min_win_rate_pct:
        return NEAR_MISS_INCUBATOR
    return PAPER_ONLY


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _safety_fields() -> dict[str, Any]:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "live_authorized": LIVE_AUTHORIZED,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "submit_attempted": SUBMIT_ATTEMPTED,
        "binance_order_endpoint_called": BINANCE_ORDER_ENDPOINT_CALLED,
        "secrets_shown": SECRETS_SHOWN,
    }
