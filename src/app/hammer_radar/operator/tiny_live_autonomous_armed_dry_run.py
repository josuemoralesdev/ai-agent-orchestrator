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
    PAPER_ONLY,
    build_explicit_lane_risk_contract,
    build_exact_lane_risk_contract_status,
)

CONFIG_PATH = Path("configs/hammer_radar/autonomous_arming_state.json")
LEDGER_FILENAME = "tiny_live_autonomous_armed_dry_run.ndjson"
CREATED_BY_PHASE = "R275_AUTONOMOUS_ARMED_LANE_DRY_RUN"
REHEARSAL_CREATED_BY_PHASE = "R276_AUTONOMOUS_ARMED_LANE_REHEARSAL_FIXTURE"
REAL_CANDIDATE_BINDING_PHASE = "R277_REAL_CANDIDATE_AUTONOMOUS_DRY_RUN_BINDING"

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
SUPPORTED_REHEARSAL_FIXTURE_LANES = {
    "BTCUSDT|44m|long|ladder_close_50_618",
    "BTCUSDT|44m|short|ladder_close_50_618",
    "BTCUSDT|55m|long|ladder_close_50_618",
}


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
    rehearsal_fixture_lane: str | None = None,
    rehearsal_arm_fixture_lane: bool = False,
    real_candidate_dry_run_bind: bool = False,
    dry_run_arm_real_candidate_lane: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else RISK_CONTRACT_CONFIG_PATH
    arming_state = load_autonomous_arming_state(config_path)
    rehearsal = _build_rehearsal_fixture_watch(rehearsal_fixture_lane, generated_at=generated_at)
    if rehearsal and rehearsal_arm_fixture_lane:
        arming_state = _with_rehearsal_fixture_arming(arming_state, lane_key=str(rehearsal["lane_key"]))
    candidate_watch = (
        rehearsal["candidate_watch"]
        if rehearsal
        else build_live_qualified_fresh_candidate_watch(log_dir=resolved_log_dir)
    )
    alert_packet = candidate_watch.get("candidate_alert_packet") if isinstance(candidate_watch.get("candidate_alert_packet"), Mapping) else {}
    selected_candidate = alert_packet.get("current_candidate") if isinstance(alert_packet.get("current_candidate"), Mapping) else None
    strategy_evidence = alert_packet.get("strategy_evidence") if isinstance(alert_packet.get("strategy_evidence"), Mapping) else {}
    selected_candidate = _annotate_selected_candidate_for_binding(
        selected_candidate=selected_candidate,
        alert_packet=alert_packet,
        strategy_evidence=strategy_evidence,
        rehearsal=bool(rehearsal),
    )
    lane_key = str((selected_candidate or {}).get("lane_key") or "")
    direction = str((selected_candidate or {}).get("direction") or "")
    if real_candidate_dry_run_bind and dry_run_arm_real_candidate_lane and selected_candidate and not rehearsal:
        arming_state = _with_real_candidate_dry_run_arming(arming_state, lane_key=lane_key)

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
    real_binding_blockers = (
        _real_candidate_binding_blockers(
            selected_candidate=selected_candidate,
            alert_packet=alert_packet,
            strategy_evidence=strategy_evidence,
            rehearsal=bool(rehearsal),
        )
        if selected_candidate and not rehearsal
        else []
    )
    blockers.extend(real_binding_blockers)

    risk_contract = (
        _build_rehearsal_fixture_risk_contract(lane_key=lane_key, generated_at=generated_at)
        if rehearsal and lane_key in SUPPORTED_REHEARSAL_FIXTURE_LANES
        else build_exact_lane_risk_contract_status(
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
        risk_blockers = _risk_contract_blockers(risk_contract, arming_state=arming_state)
        exchange_blockers = _exchange_minimum_blockers(selected_candidate, arming_state=arming_state)
        duplicate_blockers = _duplicate_blockers(lane_key=lane_key, selected_candidate=selected_candidate, log_dir=resolved_log_dir, today=generated_at.date())
        blockers.extend(risk_blockers)
        blockers.extend(exchange_blockers)
        blockers.extend(duplicate_blockers)
    else:
        risk_blockers = []
        exchange_blockers = []
        duplicate_blockers = []
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
            "created_by_phase": _created_by_phase(
                rehearsal=bool(rehearsal),
                real_candidate_dry_run_bind=bool(real_candidate_dry_run_bind),
            ),
            "rehearsal_supported": True,
            "real_candidate_binding_supported": True,
            "real_candidate_dry_run_bind_requested": bool(real_candidate_dry_run_bind),
            "dry_run_arm_real_candidate_lane_requested": bool(dry_run_arm_real_candidate_lane),
            "supported_rehearsal_fixture_lanes": sorted(SUPPORTED_REHEARSAL_FIXTURE_LANES),
            "rehearsal_mode": bool(rehearsal),
            "fixture_candidate": bool(rehearsal),
            "real_market_signal": bool(selected_candidate and not rehearsal and selected_candidate.get("real_market_signal") is True),
            "real_candidate_source": selected_candidate.get("real_candidate_source") if selected_candidate else None,
            "source_signal_id": selected_candidate.get("source_signal_id") if selected_candidate else None,
            "source_lane_key": selected_candidate.get("source_lane_key") if selected_candidate else None,
            "source_age_minutes": selected_candidate.get("source_age_minutes") if selected_candidate else None,
            "real_order_forbidden": True,
            "submit_allowed": False,
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
            "real_candidate_dry_run_binding_matrix": _build_real_candidate_binding_matrix(
                selected_candidate=selected_candidate,
                alert_packet=alert_packet,
                arming_state=arming_state,
                risk_contract=risk_contract,
                strategy_blockers=strategy_blockers,
                real_binding_blockers=real_binding_blockers,
                risk_blockers=risk_blockers,
                exchange_blockers=exchange_blockers,
                duplicate_blockers=duplicate_blockers,
                blockers=blockers,
                rehearsal=bool(rehearsal),
            ),
            "dry_run_go_no_go": {
                "go": status == AUTO_DRY_RUN_READY,
                "status": status,
                "dry_run_only": True,
                "rehearsal_mode": bool(rehearsal),
                "real_candidate_binding_supported": True,
                "real_candidate_dry_run_go_no_go": status,
                "real_order_forbidden": True,
                "submit_allowed": False,
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
    if record_autonomous_dry_run and (status == AUTO_DRY_RUN_READY or rehearsal):
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
        "submit_allowed": False,
        "real_order_forbidden": True,
    }
    return {
        "triplet_id": uuid4().hex,
        "lane_key": selected_candidate.get("lane_key"),
        "source_signal_id": selected_candidate.get("signal_id"),
        "source_lane_key": selected_candidate.get("lane_key"),
        "source_age_minutes": selected_candidate.get("age_minutes"),
        "built_from_real_market_signal": selected_candidate.get("real_market_signal") is True,
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
        "record_id": f"{_record_prefix(payload)}_{uuid4().hex}",
        "autonomous_dry_run_recorded": True,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    path = Path(log_dir) / LEDGER_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def _record_prefix(payload: Mapping[str, Any]) -> str:
    if payload.get("rehearsal_mode") is True:
        return "r276_rehearsal_auto_dry_run"
    if payload.get("real_market_signal") is True:
        return "r277_real_candidate_auto_dry_run"
    return "r275_auto_dry_run"


def _created_by_phase(*, rehearsal: bool, real_candidate_dry_run_bind: bool) -> str:
    if rehearsal:
        return REHEARSAL_CREATED_BY_PHASE
    if real_candidate_dry_run_bind:
        return REAL_CANDIDATE_BINDING_PHASE
    return CREATED_BY_PHASE


def load_latest_autonomous_rehearsal_record(*, log_dir: str | Path | None = None) -> dict[str, Any] | None:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    for row in _read_ndjson_reverse(Path(resolved_log_dir) / LEDGER_FILENAME):
        if row.get("rehearsal_mode") is True and row.get("fixture_candidate") is True:
            return row
    return None


def load_latest_autonomous_real_candidate_record(*, log_dir: str | Path | None = None) -> dict[str, Any] | None:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    for row in _read_ndjson_reverse(Path(resolved_log_dir) / LEDGER_FILENAME):
        if (
            row.get("rehearsal_mode") is not True
            and row.get("fixture_candidate") is not True
            and row.get("real_market_signal") is True
        ):
            return row
    return None


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


def _with_rehearsal_fixture_arming(arming_state: Mapping[str, Any], *, lane_key: str) -> dict[str, Any]:
    state = dict(arming_state)
    state.update(
        {
            "global_auto_live_enabled": True,
            "auto_execute_mode": "dry_run_only",
            "armed_lane_key": lane_key,
            "allowed_lane_keys": sorted(set([*list(state.get("allowed_lane_keys") or []), lane_key])),
            "lane_auto_live_enabled_keys": sorted(set([*list(state.get("lane_auto_live_enabled_keys") or []), lane_key])),
            "any_lane_auto_armed": True,
            "rehearsal_arming_override": True,
            "rehearsal_mode": True,
            "real_live_execution_enabled": False,
            "live_execution_enabled": False,
            "submit_allowed": False,
        }
    )
    lanes = [dict(item) for item in state.get("lanes") or [] if isinstance(item, Mapping)]
    lanes.append(
        {
            "lane_key": lane_key,
            "lane_auto_live_enabled": True,
            "rehearsal_mode": True,
            "dry_run_only": True,
            "real_order_forbidden": True,
        }
    )
    state["lanes"] = lanes
    return state


def _with_real_candidate_dry_run_arming(arming_state: Mapping[str, Any], *, lane_key: str) -> dict[str, Any]:
    state = dict(arming_state)
    state.update(
        {
            "global_auto_live_enabled": True,
            "auto_execute_mode": "dry_run_only",
            "armed_lane_key": lane_key,
            "allowed_lane_keys": sorted(set([*list(state.get("allowed_lane_keys") or []), lane_key])),
            "lane_auto_live_enabled_keys": sorted(set([*list(state.get("lane_auto_live_enabled_keys") or []), lane_key])),
            "any_lane_auto_armed": True,
            "real_candidate_diagnostic_arming_override": True,
            "dry_run_only": True,
            "real_live_execution_enabled": False,
            "live_execution_enabled": False,
            "submit_allowed": False,
        }
    )
    lanes = [dict(item) for item in state.get("lanes") or [] if isinstance(item, Mapping)]
    lanes.append(
        {
            "lane_key": lane_key,
            "lane_auto_live_enabled": True,
            "real_candidate_diagnostic_arming_override": True,
            "dry_run_only": True,
            "real_order_forbidden": True,
        }
    )
    state["lanes"] = lanes
    return state


def _annotate_selected_candidate_for_binding(
    *,
    selected_candidate: Mapping[str, Any] | None,
    alert_packet: Mapping[str, Any],
    strategy_evidence: Mapping[str, Any],
    rehearsal: bool,
) -> dict[str, Any] | None:
    if not selected_candidate:
        return None
    candidate = dict(selected_candidate)
    if rehearsal:
        candidate["fixture_candidate"] = True
        candidate["real_market_signal"] = False
        return candidate
    candidate.setdefault("fixture_candidate", False)
    candidate.setdefault("rehearsal_mode", False)
    candidate["real_market_signal"] = not (
        candidate.get("fixture_candidate") is True or candidate.get("rehearsal_mode") is True
    )
    candidate["real_candidate_source"] = "qualified_candidate_watch"
    candidate["source_signal_id"] = candidate.get("signal_id")
    candidate["source_lane_key"] = candidate.get("lane_key")
    candidate["source_age_minutes"] = candidate.get("age_minutes")
    candidate["source_watch_status"] = alert_packet.get("status")
    candidate["source_watch_category"] = strategy_evidence.get("live_qualification_class") or strategy_evidence.get("watch_category")
    return candidate


def _real_candidate_binding_blockers(
    *,
    selected_candidate: Mapping[str, Any],
    alert_packet: Mapping[str, Any],
    strategy_evidence: Mapping[str, Any],
    rehearsal: bool,
) -> list[str]:
    if rehearsal:
        return []
    blockers: list[str] = []
    if selected_candidate.get("fixture_candidate") is True:
        blockers.append("fixture_candidate_rejected_in_real_candidate_mode")
    if selected_candidate.get("real_market_signal") is not True:
        blockers.append("real_market_signal_required_for_real_candidate_mode")
    if selected_candidate.get("real_candidate_source") != "qualified_candidate_watch":
        blockers.append("real_candidate_source_not_qualified_candidate_watch")
    if not str(selected_candidate.get("source_signal_id") or selected_candidate.get("signal_id") or ""):
        blockers.append("source_signal_id_missing")
    if not str(selected_candidate.get("source_lane_key") or selected_candidate.get("lane_key") or ""):
        blockers.append("source_lane_key_missing")
    if alert_packet.get("status") != WATCH_FOUND:
        blockers.append("selected_candidate_not_live_qualified")
    live_class = str(strategy_evidence.get("live_qualification_class") or strategy_evidence.get("watch_category") or "")
    if live_class == NEAR_MISS_INCUBATOR:
        blockers.append("selected_candidate_from_near_miss_incubator")
    if live_class == PAPER_ONLY:
        blockers.append("selected_candidate_from_paper_only")
    if live_class != LIVE_QUALIFIED:
        blockers.append("selected_candidate_live_qualification_class_not_live_qualified")
    text = " ".join(str(value or "") for value in [selected_candidate, alert_packet, strategy_evidence]).lower()
    if "betrayal" in text or "inverse" in text:
        blockers.append("selected_candidate_betrayal_inverse_family")
    return _dedupe(blockers)


def _build_real_candidate_binding_matrix(
    *,
    selected_candidate: Mapping[str, Any] | None,
    alert_packet: Mapping[str, Any],
    arming_state: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
    strategy_blockers: list[str],
    real_binding_blockers: list[str],
    risk_blockers: list[str],
    exchange_blockers: list[str],
    duplicate_blockers: list[str],
    blockers: list[str],
    rehearsal: bool,
) -> dict[str, Any]:
    lane_key = str((selected_candidate or {}).get("lane_key") or "")
    armed_keys = set(arming_state.get("lane_auto_live_enabled_keys") or [])
    protective_ready = bool(
        selected_candidate
        and selected_candidate.get("stop") is not None
        and selected_candidate.get("take_profit") is not None
        and (risk_contract.get("contract") or {}).get("protective_stop_required") is True
        and (risk_contract.get("contract") or {}).get("take_profit_required") is True
    )
    return {
        "real_fresh_candidate_exists": bool(selected_candidate and not rehearsal),
        "candidate_is_live_qualified": alert_packet.get("status") == WATCH_FOUND and not real_binding_blockers,
        "exact_lane_auto_armed": bool(
            lane_key
            and arming_state.get("armed_lane_key") == lane_key
            and lane_key in set(arming_state.get("allowed_lane_keys") or [])
            and lane_key in armed_keys
        ),
        "global_auto_live_enabled": arming_state.get("global_auto_live_enabled") is True,
        "risk_contract_valid": risk_contract.get("risk_contract_valid") is True and not risk_blockers,
        "exchange_minimum_valid": bool(selected_candidate) and not exchange_blockers,
        "strategy_valid": bool(selected_candidate) and not strategy_blockers and not real_binding_blockers,
        "idempotency_clean": bool(selected_candidate) and not duplicate_blockers,
        "protective_orders_ready": protective_ready,
        "final_command_available": False,
        "real_order_forbidden": True,
        "submit_allowed": False,
        "ready": bool(selected_candidate and not blockers and not rehearsal),
        "blockers": list(blockers),
    }


def _build_rehearsal_fixture_watch(fixture_lane: str | None, *, generated_at: datetime) -> dict[str, Any] | None:
    if not fixture_lane:
        return None
    parts = str(fixture_lane).split("|")
    if len(parts) != 4:
        candidate = {
            "signal_id": f"REHEARSAL_INVALID_{uuid4().hex}",
            "symbol": "BTCUSDT",
            "timeframe": "",
            "direction": "",
            "entry_mode": "",
            "lane_key": str(fixture_lane),
            "age_minutes": 0.0,
            "freshness_status": "fresh",
            "fixture_candidate": True,
            "real_market_signal": False,
        }
        evidence = _fixture_strategy_evidence(lane_key=str(fixture_lane), timeframe="", direction="", live_class=PAPER_ONLY)
        status = "WATCH_BLOCKED_PAPER_ONLY"
        blocked_by = ["rehearsal_fixture_lane_key_invalid"]
    else:
        symbol, timeframe, direction, entry_mode = parts
        lane_key = "|".join(parts)
        live_class = _fixture_live_class(lane_key=lane_key, timeframe=timeframe, direction=direction)
        status = WATCH_FOUND if live_class == LIVE_QUALIFIED else (
            "WATCH_BLOCKED_NEAR_MISS" if live_class == NEAR_MISS_INCUBATOR else "WATCH_BLOCKED_PAPER_ONLY"
        )
        if _fixture_is_betrayal(lane_key=lane_key, direction=direction):
            status = "WATCH_BLOCKED_BETRAYAL"
        blocked_by = [] if status == WATCH_FOUND else [status.lower()]
        prices = _fixture_prices(direction=direction)
        candidate = {
            "signal_id": f"REHEARSAL_{generated_at.strftime('%Y%m%dT%H%M%S')}_{timeframe}_{direction}",
            "symbol": symbol,
            "timeframe": timeframe,
            "direction": direction,
            "entry_mode": entry_mode,
            "lane_key": lane_key,
            "age_minutes": 1.0,
            "freshness_status": "fresh",
            "entry": prices["entry"],
            "stop": prices["stop"],
            "take_profit": prices["take_profit"],
            "score": 88.0 if live_class == LIVE_QUALIFIED else 44.0,
            "tier": "LIVE_QUALIFIED" if live_class == LIVE_QUALIFIED else "REHEARSAL_BLOCKED",
            "rehearsal_mode": True,
            "fixture_candidate": True,
            "real_market_signal": False,
            "real_order_forbidden": True,
            "submit_allowed": False,
        }
        evidence = _fixture_strategy_evidence(lane_key=lane_key, timeframe=timeframe, direction=direction, live_class=live_class)
    alert_packet = {
        **_safety_fields(),
        "event_type": "QUALIFIED_CANDIDATE_WATCH_REHEARSAL_FIXTURE",
        "status": status,
        "current_candidate": candidate,
        "strategy_evidence": evidence,
        "operator_packet": {
            "recommended_action": "REVIEW_REHEARSAL_DRY_RUN_PACKET" if status == WATCH_FOUND else "REHEARSAL_BLOCKED_EXPECTED",
            "final_command_available": False,
            "submit_allowed_from_codex": False,
            "operator_review_only": True,
            "no_live_order_placed": True,
        },
        "blocked_by": blocked_by,
        "rehearsal_mode": True,
        "fixture_candidate": True,
        "real_market_signal": False,
        "real_order_forbidden": True,
        "submit_allowed": False,
    }
    return {
        "lane_key": candidate["lane_key"],
        "candidate_watch": {
            **_safety_fields(),
            "event_type": "LIVE_QUALIFIED_FRESH_CANDIDATE_WATCH_REHEARSAL_FIXTURE",
            "status": status,
            "current_fresh_candidate_status": status,
            "qualified_fresh_candidate_exists": status == WATCH_FOUND,
            "fresh_candidate_lane_keys": [candidate["lane_key"]],
            "qualified_fresh_candidate_lane_keys": [candidate["lane_key"]] if status == WATCH_FOUND else [],
            "current_candidate_lane_key": candidate["lane_key"],
            "candidate_alert_packet": alert_packet,
            "blocked_by": blocked_by,
            "rehearsal_mode": True,
            "fixture_candidate": True,
            "real_market_signal": False,
        },
    }


def _fixture_live_class(*, lane_key: str, timeframe: str, direction: str) -> str:
    if _fixture_is_betrayal(lane_key=lane_key, direction=direction):
        return PAPER_ONLY
    if lane_key in SUPPORTED_REHEARSAL_FIXTURE_LANES:
        return LIVE_QUALIFIED
    if lane_key == "BTCUSDT|8m|short|ladder_close_50_618":
        return NEAR_MISS_INCUBATOR
    return PAPER_ONLY


def _fixture_is_betrayal(*, lane_key: str, direction: str) -> bool:
    text = f"{lane_key} {direction}".lower()
    return "betrayal" in text or "inverse" in text


def _fixture_strategy_evidence(*, lane_key: str, timeframe: str, direction: str, live_class: str) -> dict[str, Any]:
    win_rate = 62.0 if live_class == LIVE_QUALIFIED else (53.33 if live_class == NEAR_MISS_INCUBATOR else 47.27)
    avg_pnl = 0.18 if live_class == LIVE_QUALIFIED else (0.05 if live_class == NEAR_MISS_INCUBATOR else -0.02)
    return {
        "lane_key": lane_key,
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": "ladder_close_50_618",
        "live_qualification_class": live_class,
        "watch_category": live_class,
        "win_rate_pct": win_rate,
        "sample_count": 40,
        "avg_pnl_pct": avg_pnl,
        "rehearsal_mode": True,
        "fixture_candidate": True,
        "real_market_signal": False,
    }


def _fixture_prices(*, direction: str) -> dict[str, float]:
    if direction == "short":
        return {"entry": 70000.0, "stop": 70700.0, "take_profit": 68600.0}
    return {"entry": 70000.0, "stop": 69300.0, "take_profit": 71400.0}


def _build_rehearsal_fixture_risk_contract(*, lane_key: str, generated_at: datetime) -> dict[str, Any]:
    contract = build_explicit_lane_risk_contract(
        lane_key=lane_key,
        strategy_qualification={
            "lane_key": lane_key,
            "win_rate_pct": 62.0,
            "sample_count": 40,
            "avg_pnl_pct": 0.18,
            "min_sample": 30,
            "min_win_rate_pct": 55.0,
            "qualification_status": "QUALIFIED",
        },
        now=generated_at,
    )
    contract.update(
        {
            "created_by_phase": REHEARSAL_CREATED_BY_PHASE,
            "rehearsal_mode": True,
            "fixture_candidate": True,
            "real_market_signal": False,
            "live_execution_enabled": False,
            "live_authorized": False,
            "order_payload_forbidden_until_live_gate": True,
            "binance_call_forbidden_until_live_gate": True,
        }
    )
    return {
        **_safety_fields(),
        "lane_key": lane_key,
        "risk_contract_path": "in_memory_rehearsal_fixture",
        "exact_contract_found": True,
        "risk_contract_valid": True,
        "contract": contract,
        "validation_summary": {"risk_contract_valid": True, "blocked_by": [], "rehearsal_mode": True},
        "blocked_by": [],
        "no_cross_lane_borrowing": True,
        "rehearsal_mode": True,
        "fixture_candidate": True,
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
    if selected_candidate.get("fixture_candidate") is True or selected_candidate.get("rehearsal_mode") is True:
        return []
    signal_id = str(selected_candidate.get("signal_id") or "")
    records = [row for row in _read_ndjson_reverse(log_dir / LEDGER_FILENAME) if row.get("rehearsal_mode") is not True]
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
        "real_order_forbidden": True,
        "submit_allowed": False,
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
