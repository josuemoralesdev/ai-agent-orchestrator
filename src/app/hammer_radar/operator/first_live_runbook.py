"""First protected tiny-live runbook and enablement gate.

R47 is an operator checklist only. It never changes environment variables,
restarts services, calls Binance, or places orders.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.execution.binance_futures_connector import (
    DEFAULT_ALLOWED_SYMBOLS,
    DEFAULT_MARGIN_MODE,
    DEFAULT_MAX_LEVERAGE,
    DEFAULT_MAX_POSITION_USD,
    LIVE_ORDER_ENABLED,
    build_connector_status,
    build_protective_status,
    load_connector_attempts,
    load_protective_attempts,
)
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.live_approval import load_live_approval_requests
from src.app.hammer_radar.operator.live_preflight import (
    PROMOTED_STRATEGY_KEY,
    build_promoted_strategy_preflight,
)
from src.app.hammer_radar.operator.strategy_promotion_watcher import build_strategy_promotion_status

FIRST_LIVE_EVALUATIONS_FILENAME = "first_live_runbook_evaluations.ndjson"

WAITING_FOR_PROMOTED_SIGNAL = "WAITING_FOR_PROMOTED_SIGNAL"
WAITING_FOR_EXACT_APPROVAL = "WAITING_FOR_EXACT_APPROVAL"
WAITING_FOR_TEST_ORDER = "WAITING_FOR_TEST_ORDER"
WAITING_FOR_PROTECTIVE_READY = "WAITING_FOR_PROTECTIVE_READY"
READY_FOR_OPERATOR_ENABLEMENT = "READY_FOR_OPERATOR_ENABLEMENT"
ENABLEMENT_BLOCKED = "ENABLEMENT_BLOCKED"
ENABLEMENT_PLAN_READY = "ENABLEMENT_PLAN_READY"
LOCKED_AFTER_ATTEMPT = "LOCKED_AFTER_ATTEMPT"

GO_FOR_ENABLEMENT_PLAN = "GO_FOR_ENABLEMENT_PLAN"
NO_GO = "NO_GO"

TEST_ORDER_VALID_STATUSES = {"TEST_ORDER_SENT", "TEST_ORDER_MOCK_VALIDATED", "TEST_ORDER_VALIDATED"}
PROTECTIVE_READY_STATUSES = {"PROTECTIVE_TEST_MOCK_VALIDATED", "PROTECTIVE_ORDERS_SENT"}
LIVE_ORDER_STATUSES = {"LIVE_ORDER_SENT", "LIVE_ORDER_MOCK_PLACED"}


def build_first_live_runbook(
    *,
    log_dir: str | Path | None = None,
    preflight_pack: dict[str, Any] | None = None,
    connector_status: dict[str, Any] | None = None,
    protective_status: dict[str, Any] | None = None,
    strategy_promotion_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    preflight = preflight_pack or build_promoted_strategy_preflight(log_dir=resolved_log_dir)
    connector = connector_status or build_connector_status(log_dir=resolved_log_dir)
    protective = protective_status or build_protective_status(log_dir=resolved_log_dir)
    promotion = strategy_promotion_status or build_strategy_promotion_status(log_dir=resolved_log_dir)
    signal_id = _signal_id(preflight)
    strategy_key = preflight.get("strategy_key")
    checklist = _build_checklist(
        preflight=preflight,
        connector_status=connector,
        protective_status=protective,
        signal_id=signal_id,
        log_dir=resolved_log_dir,
    )
    blockers = [item["blocker"] for item in checklist.values() if not item["passed"] and item.get("blocker")]
    runbook_status = _runbook_status(checklist, signal_id=signal_id)
    gate_decision = GO_FOR_ENABLEMENT_PLAN if runbook_status in {ENABLEMENT_PLAN_READY, READY_FOR_OPERATOR_ENABLEMENT} else NO_GO
    enablement_plan = _enablement_plan(signal_id) if gate_decision == GO_FOR_ENABLEMENT_PLAN else []
    return {
        "evaluation_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "runbook_status": runbook_status,
        "gate_decision": gate_decision,
        "signal_id": signal_id,
        "strategy_key": strategy_key,
        "promoted_strategy": promotion.get("eligible_strategies", [])[:3],
        "preflight": preflight,
        "checklist": checklist,
        "blockers": list(dict.fromkeys(blockers)),
        "enablement_plan": enablement_plan,
        "message_payloads": [_message_payload(runbook_status, gate_decision, signal_id)],
        "send_enabled": False,
        "live_execution_enabled": bool(connector.get("live_execution_enabled")),
        "allow_live_orders": bool(connector.get("allow_live_orders")),
        "global_kill_switch": bool(connector.get("global_kill_switch", True)),
        "order_placed": False,
        "real_order_placed": False,
        "secrets_shown": False,
    }


def evaluate_first_live_runbook(
    *,
    log_dir: str | Path | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    evaluation = build_first_live_runbook(log_dir=resolved_log_dir, **kwargs)
    existing = load_first_live_runbook_evaluations(limit=0, log_dir=resolved_log_dir)
    dedupe_key = _dedupe_key(evaluation)
    for record in existing:
        if record.get("dedupe_key") == dedupe_key:
            duplicate = dict(evaluation)
            duplicate["recorded"] = False
            duplicate["dedupe_key"] = dedupe_key
            duplicate["existing_evaluation_id"] = record.get("evaluation_id")
            duplicate["first_live_runbook_evaluations_path"] = str(first_live_runbook_evaluations_path(resolved_log_dir))
            return duplicate
    record = dict(evaluation)
    record["dedupe_key"] = dedupe_key
    append_first_live_runbook_evaluation(record, log_dir=resolved_log_dir)
    record["recorded"] = True
    record["first_live_runbook_evaluations_path"] = str(first_live_runbook_evaluations_path(resolved_log_dir))
    return record


def append_first_live_runbook_evaluation(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_runbook_evaluations_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_first_live_runbook_evaluations(
    *,
    limit: int = 50,
    evaluation_id: str | None = None,
    signal_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_runbook_evaluations_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if evaluation_id is not None and record.get("evaluation_id") != evaluation_id:
                continue
            if signal_id is not None and record.get("signal_id") != signal_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def first_live_runbook_evaluations_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / FIRST_LIVE_EVALUATIONS_FILENAME


def _build_checklist(
    *,
    preflight: dict[str, Any],
    connector_status: dict[str, Any],
    protective_status: dict[str, Any],
    signal_id: str | None,
    log_dir: Path,
) -> dict[str, dict[str, Any]]:
    candidate = preflight.get("candidate") or {}
    exact_found = _has_exact_approval(signal_id, log_dir=log_dir)
    test_validated = _has_test_order_validated(signal_id, log_dir=log_dir)
    protective_ready = _protective_ready(signal_id, protective_status=protective_status, log_dir=log_dir)
    order_lock = _order_lock_state(signal_id, log_dir=log_dir)
    live_safety_status = preflight.get("live_safety_status")
    return {
        "promoted_strategy_ready": _check(preflight.get("promoted_strategy_ready") is True, "promoted strategy is not ready"),
        "fresh_promoted_signal_found": _check(
            preflight.get("matching_fresh_signal_found") is True,
            "no fresh promoted BTCUSDT 13m long signal",
        ),
        "exact_live_approval_found": _check(exact_found, "exact LIVE APPROVE <signal_id> is missing"),
        "exact_live_approval_matches_signal": _check(exact_found and bool(signal_id), "exact approval does not match current signal_id"),
        "ticket_status_proposed": _check(preflight.get("ticket_status") == "PROPOSED", f"ticket_status is {preflight.get('ticket_status', 'UNKNOWN')}"),
        "dry_run_valid": _check(preflight.get("dry_run_status") == "VALID", f"dry_run_status is {preflight.get('dry_run_status', 'UNKNOWN')}"),
        "live_safety_pass_or_switch_blocked_only": _check(
            live_safety_status in {"PASS", "WOULD_BE_ALLOWED_IF_LIVE_ENABLED"},
            f"live_safety_status is {live_safety_status or 'UNKNOWN'}",
        ),
        "test_order_validated_for_signal": _check(test_validated, "successful test-order is required for signal_id"),
        "protective_orders_required": _check(protective_status.get("protective_orders_required") is True, "protective orders must be required"),
        "protective_orders_ready": _check(protective_ready, "protective stop/take-profit live order path not ready"),
        "protective_stop_ready": _check(protective_ready, "protective stop is not ready"),
        "protective_take_profit_ready": _check(protective_ready, "protective take-profit is not ready"),
        "connector_mode_live_enabled": _check(connector_status.get("connector_mode") == LIVE_ORDER_ENABLED, "connector_mode is not LIVE_ORDER_ENABLED"),
        "binance_live_enabled": _check(connector_status.get("binance_live_enabled") is True, "HAMMER_BINANCE_LIVE_ENABLED is false"),
        "live_execution_enabled": _check(connector_status.get("live_execution_enabled") is True, "live_execution_enabled is false"),
        "allow_live_orders": _check(connector_status.get("allow_live_orders") is True, "allow_live_orders is false"),
        "global_kill_switch_off": _check(connector_status.get("global_kill_switch") is False, "global kill switch is active"),
        "one_trade_today_available": _check(order_lock["one_trade_today_available"], order_lock["one_trade_blocker"]),
        "no_duplicate_signal_order": _check(order_lock["no_duplicate_signal_order"], order_lock["duplicate_blocker"]),
        "position_cap_ok": _check(float(connector_status.get("configured_max_position_usd", DEFAULT_MAX_POSITION_USD)) <= DEFAULT_MAX_POSITION_USD, "position cap exceeds 44 USDT"),
        "leverage_cap_ok": _check(float(connector_status.get("configured_max_leverage", DEFAULT_MAX_LEVERAGE)) <= DEFAULT_MAX_LEVERAGE, "leverage cap exceeds 3"),
        "isolated_margin_ok": _check(connector_status.get("configured_margin_mode", DEFAULT_MARGIN_MODE) == DEFAULT_MARGIN_MODE, "margin mode must be isolated"),
        "no_naked_entry": _check(protective_status.get("protective_orders_required") is True and protective_ready, "naked live entry is blocked"),
        "secrets_hidden": _check(connector_status.get("secrets_shown") is False and protective_status.get("secrets_shown") is False, "secrets must remain hidden"),
        "symbol_btcusdt_only": _check(candidate.get("symbol") in {None, DEFAULT_ALLOWED_SYMBOLS[0]}, "symbol must be BTCUSDT"),
        "timeframe_13m_only": _check(candidate.get("timeframe") in {None, "13m"}, "timeframe must be 13m"),
        "direction_long_only": _check(candidate.get("direction") in {None, "long"}, "direction must be long"),
        "promoted_strategy_only": _check(preflight.get("strategy_key") in {None, PROMOTED_STRATEGY_KEY}, f"strategy_key must be {PROMOTED_STRATEGY_KEY}"),
    }


def _runbook_status(checklist: dict[str, dict[str, Any]], *, signal_id: str | None) -> str:
    if not checklist["one_trade_today_available"]["passed"] or not checklist["no_duplicate_signal_order"]["passed"]:
        return LOCKED_AFTER_ATTEMPT
    if not checklist["promoted_strategy_ready"]["passed"] or not checklist["fresh_promoted_signal_found"]["passed"]:
        return WAITING_FOR_PROMOTED_SIGNAL
    if not checklist["exact_live_approval_found"]["passed"] or not checklist["exact_live_approval_matches_signal"]["passed"]:
        return WAITING_FOR_EXACT_APPROVAL
    if not checklist["test_order_validated_for_signal"]["passed"]:
        return WAITING_FOR_TEST_ORDER
    if not checklist["protective_orders_ready"]["passed"] or not checklist["no_naked_entry"]["passed"]:
        return WAITING_FOR_PROTECTIVE_READY
    non_switch_keys = [
        "ticket_status_proposed",
        "dry_run_valid",
        "live_safety_pass_or_switch_blocked_only",
        "protective_orders_required",
        "protective_stop_ready",
        "protective_take_profit_ready",
        "position_cap_ok",
        "leverage_cap_ok",
        "isolated_margin_ok",
        "secrets_hidden",
        "symbol_btcusdt_only",
        "timeframe_13m_only",
        "direction_long_only",
        "promoted_strategy_only",
    ]
    if not all(checklist[key]["passed"] for key in non_switch_keys):
        return ENABLEMENT_BLOCKED
    switch_keys = [
        "connector_mode_live_enabled",
        "binance_live_enabled",
        "live_execution_enabled",
        "allow_live_orders",
        "global_kill_switch_off",
    ]
    if all(checklist[key]["passed"] for key in switch_keys):
        return READY_FOR_OPERATOR_ENABLEMENT
    return ENABLEMENT_PLAN_READY if signal_id else WAITING_FOR_PROMOTED_SIGNAL


def _enablement_plan(signal_id: str | None) -> list[str]:
    exact = signal_id or "<signal_id>"
    return [
        f"Confirm exact signal_id: {exact}.",
        "Confirm protective stop and take-profit previews.",
        "Confirm Binance test-order validation for the same signal_id.",
        "Stop system or reload env safely if needed.",
        "Set HAMMER_BINANCE_CONNECTOR_MODE=LIVE_ORDER_ENABLED.",
        "Set HAMMER_BINANCE_LIVE_ENABLED=true.",
        "Set HAMMER_LIVE_EXECUTION_ENABLED=true.",
        "Set HAMMER_ALLOW_LIVE_ORDERS=true.",
        "Set HAMMER_GLOBAL_KILL_SWITCH=false.",
        "Restart hammer-approval-api.service manually.",
        "Re-run /first-live/runbook and verify GO_FOR_ENABLEMENT_PLAN or READY_FOR_OPERATOR_ENABLEMENT.",
        "Execute one protected tiny-live order manually through the gated endpoint.",
        "Immediately restore HAMMER_LIVE_EXECUTION_ENABLED=false.",
        "Immediately restore HAMMER_ALLOW_LIVE_ORDERS=false.",
        "Immediately restore HAMMER_GLOBAL_KILL_SWITCH=true.",
        "Immediately restore HAMMER_BINANCE_CONNECTOR_MODE=DRY_RUN_ONLY.",
        "Restart hammer-approval-api.service manually again.",
        "Verify order_placed / attempt logs.",
        "Verify system locked again.",
    ]


def _has_exact_approval(signal_id: str | None, *, log_dir: Path) -> bool:
    if not signal_id:
        return False
    for record in load_live_approval_requests(limit=0, signal_id=signal_id, log_dir=log_dir):
        if (
            record.get("normalized_action") == "live_approve_exact"
            and record.get("parse_status") == "ACCEPTED"
            and record.get("signal_id") == signal_id
        ):
            return True
    return False


def _has_test_order_validated(signal_id: str | None, *, log_dir: Path) -> bool:
    if not signal_id:
        return False
    return any(
        record.get("endpoint") == "test_order" and record.get("status") in TEST_ORDER_VALID_STATUSES
        for record in load_connector_attempts(limit=0, signal_id=signal_id, log_dir=log_dir)
    )


def _protective_ready(signal_id: str | None, *, protective_status: dict[str, Any], log_dir: Path) -> bool:
    if protective_status.get("protective_orders_ready") is True:
        return True
    if not signal_id:
        return False
    return any(
        record.get("status") in PROTECTIVE_READY_STATUSES
        for record in load_protective_attempts(limit=0, signal_id=signal_id, log_dir=log_dir)
    )


def _order_lock_state(signal_id: str | None, *, log_dir: Path) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    live_records = [
        record
        for record in load_connector_attempts(limit=0, log_dir=log_dir)
        if record.get("status") in LIVE_ORDER_STATUSES or record.get("order_placed") is True
    ]
    duplicate = bool(signal_id and any(record.get("signal_id") == signal_id for record in live_records))
    today_used = any(_record_date(record) == today for record in live_records)
    return {
        "no_duplicate_signal_order": not duplicate,
        "duplicate_blocker": f"live order already recorded for signal_id {signal_id}" if duplicate else "",
        "one_trade_today_available": not today_used,
        "one_trade_blocker": "max live trades per day already reached" if today_used else "",
    }


def _record_date(record: dict[str, Any]) -> object:
    try:
        return datetime.fromisoformat(str(record.get("created_at"))).date()
    except ValueError:
        return None


def _check(passed: bool, blocker: str) -> dict[str, Any]:
    return {"passed": bool(passed), "blocker": None if passed else blocker}


def _signal_id(preflight: dict[str, Any]) -> str | None:
    value = preflight.get("candidate_signal_id") or preflight.get("signal_id")
    return str(value) if value else None


def _dedupe_key(evaluation: dict[str, Any]) -> str:
    blockers_hash = hashlib.sha256(json.dumps(evaluation.get("blockers", []), sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return "|".join(
        [
            str(evaluation.get("runbook_status")),
            str(evaluation.get("gate_decision")),
            str(evaluation.get("signal_id")),
            blockers_hash,
        ]
    )


def _message_payload(runbook_status: str, gate_decision: str, signal_id: str | None) -> dict[str, Any]:
    return {
        "send_enabled": False,
        "text": (
            "First live runbook only. No order placed. No env switches changed. "
            f"status={runbook_status} gate={gate_decision} signal_id={signal_id or 'none'}. "
            "GO means enablement plan may be followed manually, not automatic execution."
        ),
    }
