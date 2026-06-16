"""R275 autonomous armed-lane dry-run executor.

This module is local dry-run orchestration only. It never signs requests,
submits orders, calls Binance order or test-order endpoints, reads secrets, or
enables real live execution.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.strategy_promotion_watcher import (
    WATCH_FOUND,
    build_live_qualified_fresh_candidate_watch,
)
from src.app.hammer_radar.operator.tiny_live_actual_submit_gate import RISK_CONTRACT_CONFIG_PATH
from src.app.hammer_radar.operator.tiny_live_strategy_lane_selection import (
    LIVE_QUALIFIED,
    NEAR_MISS_INCUBATOR,
    build_exact_lane_risk_contract_status,
)

CONFIG_PATH = Path("configs/hammer_radar/autonomous_arming_state.json")
LEDGER_FILENAME = "tiny_live_autonomous_armed_dry_run.ndjson"
CREATED_BY_PHASE = "R275_AUTONOMOUS_ARMED_LANE_DRY_RUN"

AUTO_DRY_RUN_WAIT = "AUTO_DRY_RUN_WAIT"
AUTO_DRY_RUN_BLOCKED = "AUTO_DRY_RUN_BLOCKED"
AUTO_DRY_RUN_READY = "AUTO_DRY_RUN_READY"

BLOCKED_BY_GLOBAL_ARMING = "BLOCKED_BY_GLOBAL_ARMING"
BLOCKED_BY_LANE_ARMING = "BLOCKED_BY_LANE_ARMING"
BLOCKED_BY_NEAR_MISS = "BLOCKED_BY_NEAR_MISS"
BLOCKED_BY_PAPER_ONLY = "BLOCKED_BY_PAPER_ONLY"
BLOCKED_BY_BETRAYAL = "BLOCKED_BY_BETRAYAL"

LIVE_EXECUTION_ENABLED = False
ALLOW_LIVE_ORDERS = False
GLOBAL_KILL_SWITCH = True
ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
SUBMIT_ATTEMPTED = False
BINANCE_ORDER_ENDPOINT_CALLED = False
BINANCE_TEST_ORDER_ENDPOINT_CALLED = False
SECRETS_SHOWN = False


def default_autonomous_arming_state() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "global_auto_live_enabled": False,
        "auto_execute_mode": "dry_run_only",
        "armed_lane_key": None,
        "allowed_lane_keys": [],
        "max_position_notional_usdt": 80.0,
        "leverage": 10.0,
        "max_trades_per_day": 1,
        "daily_loss_stop_usdt": 5.0,
        "require_protective_orders": True,
        "require_strategy_live_qualified": True,
        "require_no_betrayal": True,
        "require_not_near_miss": True,
        "lanes": [],
    }


def load_autonomous_arming_state(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path is not None else CONFIG_PATH
    state = default_autonomous_arming_state()
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, Mapping):
            state.update(dict(raw))
    return _normalize_arming_state(state, path=path)


def build_tiny_live_autonomous_armed_dry_run(
    *,
    log_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    risk_contract_config_path: str | Path | None = None,
    record_autonomous_dry_run: bool = False,
    operator_id: str = "local_operator",
    reason: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    arming_state = load_autonomous_arming_state(config_path)
    candidate_watch = build_live_qualified_fresh_candidate_watch(log_dir=resolved_log_dir)
    alert_packet = candidate_watch.get("candidate_alert_packet") if isinstance(candidate_watch.get("candidate_alert_packet"), Mapping) else {}
    selected_candidate = alert_packet.get("current_candidate") if isinstance(alert_packet.get("current_candidate"), Mapping) else None
    strategy_evidence = alert_packet.get("strategy_evidence") if isinstance(alert_packet.get("strategy_evidence"), Mapping) else {}
    lane_key = str((selected_candidate or {}).get("lane_key") or "")
    direction = str((selected_candidate or {}).get("direction") or "")

    blockers: list[str] = []
    status = AUTO_DRY_RUN_WAIT
    if not selected_candidate or alert_packet.get("status") != WATCH_FOUND:
        blockers.extend(str(item) for item in alert_packet.get("blocked_by") or ["no_current_fresh_live_qualified_candidate"])
    blockers.extend(_arming_blockers(arming_state, lane_key=lane_key))
    strategy_blockers = (
        _candidate_strategy_blockers(alert_packet=alert_packet, strategy_evidence=strategy_evidence)
        if selected_candidate
        else []
    )
    blockers.extend(strategy_blockers)

    risk_contract = (
        build_exact_lane_risk_contract_status(
            lane_key=lane_key,
            risk_contract_config_path=risk_path,
            strategy_qualification={
                "strategy_qualified": not strategy_blockers
            },
        )
        if lane_key
        else _empty_risk_contract_status(risk_path)
    )
    if selected_candidate:
        blockers.extend(_risk_contract_blockers(risk_contract, arming_state=arming_state))
        blockers.extend(_exchange_minimum_blockers(selected_candidate, arming_state=arming_state))
        blockers.extend(_duplicate_blockers(lane_key=lane_key, selected_candidate=selected_candidate, log_dir=resolved_log_dir, today=generated_at.date()))
    blockers = _dedupe(blockers)

    simulated_order_triplet = None
    if selected_candidate and not blockers:
        simulated_order_triplet = build_simulated_order_triplet(
            selected_candidate=selected_candidate,
            arming_state=arming_state,
        )
        status = AUTO_DRY_RUN_READY
    elif selected_candidate:
        status = AUTO_DRY_RUN_BLOCKED

    payload = _sanitize(
        {
            **_safety_fields(),
            "event_type": "AUTONOMOUS_ARMED_LANE_DRY_RUN",
            "created_by_phase": CREATED_BY_PHASE,
            "status": status,
            "generated_at": generated_at.isoformat(),
            "record_autonomous_dry_run_requested": bool(record_autonomous_dry_run),
            "autonomous_dry_run_recorded": False,
            "operator_intent": {
                "operator_id": str(operator_id or "local_operator"),
                "reason": str(reason or ""),
                "record_only": True,
            },
            "arming_state": arming_state,
            "candidate_watch_status": {
                "event_type": candidate_watch.get("event_type"),
                "status": alert_packet.get("status") or candidate_watch.get("status"),
                "current_fresh_candidate_status": candidate_watch.get("current_fresh_candidate_status"),
            },
            "selected_candidate": dict(selected_candidate) if selected_candidate else None,
            "strategy_evidence": dict(strategy_evidence),
            "exact_lane_risk_contract": risk_contract,
            "simulated_order_triplet": simulated_order_triplet,
            "dry_run_go_no_go": {
                "go": status == AUTO_DRY_RUN_READY,
                "status": status,
                "dry_run_only": True,
                "real_order_forbidden": True,
                "final_command_available": False,
            },
            "blockers": blockers,
            "next_required_step": _next_required_step(status=status, blockers=blockers),
            "notification_payload": build_autonomous_dry_run_notification_payload(
                status=status,
                lane_key=lane_key or None,
                blockers=blockers,
            ),
            "safety": _safety_fields(),
        }
    )
    if record_autonomous_dry_run and status == AUTO_DRY_RUN_READY:
        payload = append_autonomous_dry_run_record(payload, log_dir=resolved_log_dir)
    return payload


def build_simulated_order_triplet(*, selected_candidate: Mapping[str, Any], arming_state: Mapping[str, Any]) -> dict[str, Any]:
    direction = str(selected_candidate.get("direction") or "")
    entry = _float_or_none(selected_candidate.get("entry"))
    notional = float(arming_state.get("max_position_notional_usdt") or 80.0)
    quantity = _round_down((notional / entry) if entry else None, step="0.001")
    if direction == "long":
        entry_side, exit_side = "BUY", "SELL"
    else:
        entry_side, exit_side = "SELL", "BUY"
    common = {
        "symbol": selected_candidate.get("symbol"),
        "quantity": quantity,
        "positionSide": direction.upper(),
        "dry_run_only": True,
        "sent": False,
    }
    return {
        "triplet_id": uuid4().hex,
        "lane_key": selected_candidate.get("lane_key"),
        "entry_order": {
            **common,
            "side": entry_side,
            "type": "MARKET",
            "reduceOnly": False,
            "notional_usdt": notional,
            "leverage": arming_state.get("leverage"),
        },
        "protective_stop_order": {
            **common,
            "side": exit_side,
            "type": "STOP_MARKET",
            "stopPrice": selected_candidate.get("stop"),
            "reduceOnly": True,
        },
        "take_profit_order": {
            **common,
            "side": exit_side,
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": selected_candidate.get("take_profit"),
            "reduceOnly": True,
        },
        "binance_order_endpoint_called": False,
        "binance_test_order_endpoint_called": False,
        "real_order_placed": False,
        "submit_attempted": False,
    }


def build_autonomous_dry_run_notification_payload(*, status: str, lane_key: str | None, blockers: list[str]) -> dict[str, Any]:
    return {
        "channel": "telegram_compatible",
        "send_enabled": False,
        "sent": False,
        "status": "prepared_not_sent",
        "message": "\n".join(
            [
                f"autonomous dry-run {status.lower().replace('auto_dry_run_', '')}",
                f"lane: {lane_key or 'n/a'}",
                f"blockers: {'; '.join(blockers) if blockers else 'none'}",
                "audit/visibility only; notification is not the trigger.",
                "No submit. No order. No Binance order endpoint call.",
            ]
        ),
        "visibility_only": True,
        "human_trigger_required": False,
        "secrets_shown": False,
    }


def append_autonomous_dry_run_record(payload: dict[str, Any], *, log_dir: str | Path) -> dict[str, Any]:
    record = {
        **payload,
        "record_id": f"r275_auto_dry_run_{uuid4().hex}",
        "autonomous_dry_run_recorded": True,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    path = Path(log_dir) / LEDGER_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def format_tiny_live_autonomous_armed_dry_run_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _normalize_arming_state(state: Mapping[str, Any], *, path: Path) -> dict[str, Any]:
    lanes = [dict(item) for item in state.get("lanes") or [] if isinstance(item, Mapping)]
    lane_enabled_keys = {
        str(item.get("lane_key") or _lane_key_from_mapping(item))
        for item in lanes
        if item.get("lane_auto_live_enabled") is True
    }
    allowed = [str(item) for item in state.get("allowed_lane_keys") or [] if str(item)]
    armed_lane_key = state.get("armed_lane_key")
    return {
        **dict(state),
        "config_path": str(path),
        "global_auto_live_enabled": state.get("global_auto_live_enabled") is True,
        "auto_execute_mode": str(state.get("auto_execute_mode") or "dry_run_only"),
        "armed_lane_key": str(armed_lane_key) if armed_lane_key else None,
        "allowed_lane_keys": allowed,
        "lane_auto_live_enabled_keys": sorted(key for key in lane_enabled_keys if key),
        "any_lane_auto_armed": bool(lane_enabled_keys),
        "dry_run_only": True,
        "live_execution_enabled": False,
    }


def _arming_blockers(arming_state: Mapping[str, Any], *, lane_key: str) -> list[str]:
    blockers: list[str] = []
    if arming_state.get("auto_execute_mode") != "dry_run_only":
        blockers.append("auto_execute_mode_not_dry_run_only")
    if arming_state.get("global_auto_live_enabled") is not True:
        blockers.append(BLOCKED_BY_GLOBAL_ARMING)
    if lane_key:
        allowed = set(arming_state.get("allowed_lane_keys") or [])
        armed_keys = set(arming_state.get("lane_auto_live_enabled_keys") or [])
        if arming_state.get("armed_lane_key") != lane_key or lane_key not in allowed or lane_key not in armed_keys:
            blockers.append(BLOCKED_BY_LANE_ARMING)
    return blockers


def _candidate_strategy_blockers(*, alert_packet: Mapping[str, Any], strategy_evidence: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    status = str(alert_packet.get("status") or "")
    live_class = str(strategy_evidence.get("live_qualification_class") or "")
    if "betrayal" in " ".join(str(value or "") for value in [alert_packet, strategy_evidence]).lower() or status.endswith("BETRAYAL"):
        blockers.append(BLOCKED_BY_BETRAYAL)
    if live_class == NEAR_MISS_INCUBATOR or status.endswith("NEAR_MISS"):
        blockers.append(BLOCKED_BY_NEAR_MISS)
    if live_class != LIVE_QUALIFIED:
        blockers.append(BLOCKED_BY_PAPER_ONLY)
    if _float_or_none(strategy_evidence.get("win_rate_pct")) is None or float(strategy_evidence.get("win_rate_pct") or 0.0) < 55.0:
        blockers.append("strategy_win_rate_below_55")
    if int(strategy_evidence.get("sample_count") or 0) < 30:
        blockers.append("strategy_sample_count_below_30")
    if float(strategy_evidence.get("avg_pnl_pct") or 0.0) <= 0.0:
        blockers.append("strategy_avg_pnl_not_positive")
    return blockers


def _risk_contract_blockers(risk_contract: Mapping[str, Any], *, arming_state: Mapping[str, Any]) -> list[str]:
    contract = risk_contract.get("contract") if isinstance(risk_contract.get("contract"), Mapping) else {}
    blockers = [str(item) for item in risk_contract.get("blocked_by") or []]
    if risk_contract.get("risk_contract_valid") is not True:
        blockers.append("exact_lane_risk_contract_not_valid")
    if contract.get("tiny_live_contract_mode") != "explicit_notional_cap_with_leverage":
        blockers.append("risk_contract_mode_not_explicit_notional_cap_with_leverage")
    if _float_or_none(contract.get("max_position_notional_usdt") or contract.get("max_notional_usdt")) != 80.0:
        blockers.append("risk_contract_notional_cap_not_80")
    if _float_or_none(contract.get("leverage")) != 10.0:
        blockers.append("risk_contract_leverage_not_10")
    if abs(float(contract.get("margin_budget_usdt") or contract.get("tiny_live_margin_usdt") or 0.0) - 8.0) > 0.01:
        blockers.append("risk_contract_margin_budget_not_8")
    if float(arming_state.get("max_position_notional_usdt") or 0.0) > 80.0:
        blockers.append("arming_notional_cap_above_80")
    if _float_or_none(arming_state.get("leverage")) != 10.0:
        blockers.append("arming_leverage_not_10")
    if contract.get("protective_stop_required") is not True or contract.get("take_profit_required") is not True:
        blockers.append("protective_orders_not_required_by_contract")
    return _dedupe(blockers)


def _exchange_minimum_blockers(selected_candidate: Mapping[str, Any] | None, arming_state: Mapping[str, Any]) -> list[str]:
    if not selected_candidate:
        return []
    entry = _float_or_none(selected_candidate.get("entry"))
    notional = _float_or_none(arming_state.get("max_position_notional_usdt"))
    qty = (notional / entry) if entry and notional else None
    if notional is None or notional < 5.0:
        return ["exchange_min_notional_not_clear"]
    if _round_down(qty, step="0.001") is None:
        return ["exchange_quantity_step_not_clear"]
    return []


def _duplicate_blockers(*, lane_key: str, selected_candidate: Mapping[str, Any] | None, log_dir: Path, today: date) -> list[str]:
    if not selected_candidate:
        return []
    signal_id = str(selected_candidate.get("signal_id") or "")
    records = _read_ndjson_reverse(log_dir / LEDGER_FILENAME)
    blockers: list[str] = []
    if any(str(row.get("selected_candidate", {}).get("signal_id") or "") == signal_id for row in records if isinstance(row.get("selected_candidate"), Mapping)):
        blockers.append("duplicate_autonomous_dry_run_signal")
    today_records = [
        row for row in records
        if str(row.get("generated_at") or row.get("recorded_at") or "").startswith(today.isoformat())
        and str((row.get("selected_candidate") or {}).get("lane_key") or "") == lane_key
    ]
    if len(today_records) >= 1:
        blockers.append("max_trades_per_day_reached")
    return blockers


def _empty_risk_contract_status(risk_path: Path) -> dict[str, Any]:
    return {
        **_safety_fields(),
        "lane_key": None,
        "risk_contract_path": str(risk_path),
        "exact_contract_found": False,
        "risk_contract_valid": False,
        "contract": {},
        "validation_summary": {},
        "blocked_by": ["no_selected_lane"],
    }


def _next_required_step(*, status: str, blockers: list[str]) -> str:
    if status == AUTO_DRY_RUN_READY:
        return "REVIEW_AUTONOMOUS_DRY_RUN_PACKET_ONLY_REAL_ORDER_FORBIDDEN"
    if BLOCKED_BY_GLOBAL_ARMING in blockers:
        return "ARM_GLOBAL_AUTO_LIVE_DRY_RUN_ONLY_IF_OPERATOR_INTENDS"
    if BLOCKED_BY_LANE_ARMING in blockers:
        return "ARM_EXACT_LANE_DRY_RUN_ONLY_IF_OPERATOR_INTENDS"
    if status == AUTO_DRY_RUN_WAIT:
        return "WAIT_FOR_FRESH_LIVE_QUALIFIED_CANDIDATE"
    return "CLEAR_BLOCKERS_OR_WAIT"


def _lane_key_from_mapping(row: Mapping[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("symbol") or ""),
            str(row.get("timeframe") or ""),
            str(row.get("direction") or ""),
            str(row.get("entry_mode") or "ladder_close_50_618"),
        ]
    )


def _read_ndjson_reverse(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return list(reversed(rows))


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_down(value: float | None, *, step: str) -> float | None:
    if value is None or value <= 0.0:
        return None
    rounded = Decimal(str(value)).quantize(Decimal(step), rounding=ROUND_DOWN)
    return float(rounded) if rounded > 0 else None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _safety_fields() -> dict[str, Any]:
    return {
        "live_execution_enabled": LIVE_EXECUTION_ENABLED,
        "allow_live_orders": ALLOW_LIVE_ORDERS,
        "global_kill_switch": GLOBAL_KILL_SWITCH,
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "execution_attempted": EXECUTION_ATTEMPTED,
        "submit_attempted": SUBMIT_ATTEMPTED,
        "binance_order_endpoint_called": BINANCE_ORDER_ENDPOINT_CALLED,
        "binance_test_order_endpoint_called": BINANCE_TEST_ORDER_ENDPOINT_CALLED,
        "secrets_shown": SECRETS_SHOWN,
        "final_command_available": False,
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
