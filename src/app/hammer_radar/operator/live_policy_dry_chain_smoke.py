"""R75 policy-armed dry chain smoke for Hammer Radar.

This module verifies that selected micro and higher-timeframe candidates can
enter the approval/intent chain under policy-armed env simulation. It never
places orders, calls Binance, edits env files, or enables live execution.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_candidate_queue import (
    build_first_live_candidate_queue,
    load_selected_signal,
    select_first_live_candidate,
    selected_signal_path,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import build_first_live_chain_status
from src.app.hammer_radar.operator.first_live_timeframe_policy import get_first_live_timeframe_policy
from src.app.hammer_radar.operator.live_approval import evaluate_live_approval_request
from src.app.hammer_radar.operator.live_execution_intent import append_live_execution_intent, compute_preview_hash
from src.app.hammer_radar.operator.live_policy_arming import build_live_policy_arming_status

PHASE = "R75"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "POLICY_ARMED_DRY_CHAIN_SMOKE_ONLY"
SMOKES_FILENAME = "live_policy_dry_chain_smokes.ndjson"
SOURCE = "r75_policy_armed_dry_chain_smoke"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
EXECUTION_ATTEMPTED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

SCENARIOS = ("micro", "higher", "both")
MICRO_TIMEFRAMES = ("4m", "8m")
HIGHER_TIMEFRAMES = ("444m", "4H")


def build_policy_armed_dry_chain_smoke_status(
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    source = os.environ if env is None else env
    arming = build_live_policy_arming_status(env=source)
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "created_at": datetime.now(UTC).isoformat(),
            "order_placed": ORDER_PLACED,
            "real_order_placed": REAL_ORDER_PLACED,
            "execution_attempted": EXECUTION_ATTEMPTED,
            "network_allowed": NETWORK_ALLOWED,
            "secrets_shown": SECRETS_SHOWN,
            "actual_policy_env": arming.get("policy_env"),
            "actual_execution_env": arming.get("execution_env"),
            "available_scenarios": list(SCENARIOS),
            "dry_smoke_supported": True,
            "warnings": [
                "dry smoke may inject policy env for evaluation only; it does not edit service env files",
                "execution remains disabled",
            ],
        }
    )


def build_policy_armed_dry_chain_runbook(
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    status = build_policy_armed_dry_chain_smoke_status(env=env)
    return _sanitize(
        {
            **status,
            "runbook_name": "R75_POLICY_ARMED_DRY_CHAIN_SMOKE",
            "manual_steps": [
                "Confirm R74 policy arming status and execution env separation.",
                "Run /live/policy-dry-chain/check with scenario micro, higher, or both.",
                "Expect BLOCKED if no queue-fresh candidate exists for the scenario.",
                "If a candidate exists, verify selection, approval, and dry intent steps reach the chain without orders.",
                "Continue to R76 funded readiness only after order_placed and real_order_placed remain false.",
            ],
            "api_commands": [
                "GET /live/policy-dry-chain/status",
                "GET /live/policy-dry-chain/runbook",
                "POST /live/policy-dry-chain/check {\"scenario\":\"micro\"}",
                "POST /live/policy-dry-chain/check {\"scenario\":\"higher\"}",
            ],
            "telegram_commands": [
                "LIVE POLICY DRY SMOKE",
                "LIVE MICRO DRY SMOKE",
                "LIVE HIGHER DRY SMOKE",
                "LIVE POLICY DRY RUNBOOK",
            ],
        }
    )


def run_policy_armed_dry_chain_smoke(
    *,
    scenario: str = "micro",
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
    signal_id: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    normalized = _normalize_scenario(scenario)
    if normalized == "both":
        return _run_both(env=env, log_dir=log_dir, signal_id=signal_id, persist=persist)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = dict(os.environ if env is None else env)
    simulated_env = _scenario_env(normalized, source)
    previous_selection = load_selected_signal(log_dir=resolved_log_dir)
    created_at = datetime.now(UTC)
    steps: list[dict[str, Any]] = []
    blockers: list[str] = []
    selected_id: str | None = None
    try:
        with _temporary_env_overlay(simulated_env):
            queue = build_first_live_candidate_queue(log_dir=resolved_log_dir, env=simulated_env, now=created_at)
            candidate = _choose_candidate(queue, scenario=normalized, signal_id=signal_id)
            if candidate is None:
                reason = f"no queue-fresh {'micro' if normalized == 'micro' else 'higher-timeframe'} candidate available"
                blockers.append(reason)
                steps.append(_step("candidate_selected", "BLOCKED", reason=reason))
                payload = _payload(
                    status="BLOCKED",
                    scenario=normalized,
                    simulated_env=simulated_env,
                    selected_signal_id=None,
                    steps=steps,
                    chain_result={},
                    blockers=blockers,
                    created_at=created_at,
                    env=source,
                )
                if persist:
                    _record(payload, log_dir=resolved_log_dir)
                return payload
            selected_id = str(candidate.get("signal_id"))
            selection = select_first_live_candidate(
                signal_id=selected_id,
                log_dir=resolved_log_dir,
                source=SOURCE,
                reason=f"R75 dry smoke {normalized}",
                env=simulated_env,
            )
            steps.append(_step("candidate_selected", "OK" if selection.get("status") == "ACCEPTED" else "BLOCKED", result=selection))
            first_next = build_first_live_chain_status(log_dir=resolved_log_dir, env=simulated_env)
            first_ok = (first_next.get("next_action") or {}).get("kind") == "approve_signal"
            steps.append(_step("first_live_next", "OK" if first_ok else "BLOCKED", result=first_next, next_action=first_next.get("next_action")))
            if not first_ok:
                blockers.append("FIRST LIVE NEXT did not offer LIVE APPROVE")
                return _finish(normalized, simulated_env, selected_id, steps, blockers, created_at, source, resolved_log_dir, persist)
            approval = evaluate_live_approval_request(
                text=f"LIVE APPROVE {selected_id}",
                source=SOURCE,
                log_dir=resolved_log_dir,
                persist=True,
            )
            approval_ok = approval.get("parse_status") == "ACCEPTED"
            steps.append(_step("live_approve", "OK" if approval_ok else "BLOCKED", result=approval))
            post_approval = build_first_live_chain_status(log_dir=resolved_log_dir, env=simulated_env)
            post_approval_ok = (post_approval.get("next_action") or {}).get("kind") == "create_intent"
            steps.append(
                _step(
                    "post_approval_next",
                    "OK" if post_approval_ok else "BLOCKED",
                    result=post_approval,
                    next_action=post_approval.get("next_action"),
                )
            )
            if not post_approval_ok:
                blockers.append("post-approval FIRST LIVE NEXT did not request LIVE INTENT")
                return _finish(normalized, simulated_env, selected_id, steps, blockers, created_at, source, resolved_log_dir, persist)
            intent = _append_dry_intent(selected_id, candidate=candidate, log_dir=resolved_log_dir)
            steps.append(_step("live_intent", "OK", result=intent))
            post_intent = build_first_live_chain_status(log_dir=resolved_log_dir, env=simulated_env)
            post_intent_ok = (post_intent.get("next_action") or {}).get("kind") == "run_rehearsal"
            steps.append(
                _step(
                    "post_intent_next",
                    "OK" if post_intent_ok else "BLOCKED",
                    result=post_intent,
                    next_action=post_intent.get("next_action"),
                )
            )
            if not post_intent_ok:
                blockers.append("post-intent FIRST LIVE NEXT did not request LIVE REHEARSAL")
            return _finish(normalized, simulated_env, selected_id, steps, blockers, created_at, source, resolved_log_dir, persist)
    finally:
        _restore_selection(previous_selection, log_dir=resolved_log_dir)


def load_policy_armed_dry_chain_smokes(
    *,
    limit: int = 50,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = policy_armed_dry_chain_smokes_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(_sanitize(json.loads(line)))
    records = list(reversed(records))
    return records[:limit] if limit > 0 else records


def policy_armed_dry_chain_smokes_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / SMOKES_FILENAME


def format_policy_armed_dry_chain_operator_message(payload: Mapping[str, Any], *, section: str = "status") -> str:
    if section == "runbook":
        return "\n".join(
            [
                "R75 policy dry chain runbook: OK",
                "DRY_CHAIN_ONLY. No order placed. real_order_placed=false.",
                "Run LIVE MICRO DRY SMOKE or LIVE HIGHER DRY SMOKE when queue-fresh candidates exist.",
            ]
        )
    if section == "status":
        return "\n".join(
            [
                f"R75 policy dry chain smoke: {payload.get('status')}",
                "DRY_CHAIN_ONLY. No order placed. real_order_placed=false.",
                f"supported={payload.get('dry_smoke_supported')} scenarios={','.join(payload.get('available_scenarios') or [])}",
            ]
        )
    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    detail = "; ".join(f"{step.get('name')}={step.get('status')}" for step in steps[:6])
    blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
    return "\n".join(
        [
            f"R75 {payload.get('scenario')} dry chain smoke: {payload.get('status')}",
            "DRY_CHAIN_ONLY. No order placed. real_order_placed=false.",
            f"signal: {payload.get('selected_signal_id') or 'none'}",
            f"steps: {detail or 'none'}",
            f"blockers: {'; '.join(str(item) for item in blockers[:3]) if blockers else 'none'}",
        ]
    )


def _run_both(
    *,
    env: Mapping[str, str] | None,
    log_dir: str | Path | None,
    signal_id: str | None,
    persist: bool,
) -> dict[str, Any]:
    micro = run_policy_armed_dry_chain_smoke(scenario="micro", env=env, log_dir=log_dir, signal_id=signal_id, persist=False)
    higher = run_policy_armed_dry_chain_smoke(scenario="higher", env=env, log_dir=log_dir, persist=False)
    status = "OK" if "OK" in {micro.get("status"), higher.get("status")} else "BLOCKED"
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    payload = _sanitize(
        {
            "status": status,
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "created_at": datetime.now(UTC).isoformat(),
            "scenario": "both",
            "results": {"micro": micro, "higher": higher},
            "steps": [
                _step("micro_policy_armed_dry_chain", str(micro.get("status") or "BLOCKED"), result=micro),
                _step("higher_policy_armed_dry_chain", str(higher.get("status") or "BLOCKED"), result=higher),
            ],
            "chain_result": {
                "micro_status": micro.get("status"),
                "higher_status": higher.get("status"),
            },
            "actual_execution_env": build_live_policy_arming_status(env=source).get("execution_env"),
            "order_placed": ORDER_PLACED,
            "real_order_placed": REAL_ORDER_PLACED,
            "execution_attempted": EXECUTION_ATTEMPTED,
            "network_allowed": NETWORK_ALLOWED,
            "secrets_shown": SECRETS_SHOWN,
            "blockers": [*(micro.get("blockers") or []), *(higher.get("blockers") or [])],
        }
    )
    if persist:
        _record(payload, log_dir=resolved_log_dir)
    return payload


def _finish(
    scenario: str,
    simulated_env: Mapping[str, str],
    selected_id: str,
    steps: list[dict[str, Any]],
    blockers: list[str],
    created_at: datetime,
    source: Mapping[str, str],
    log_dir: Path,
    persist: bool,
) -> dict[str, Any]:
    chain = build_first_live_chain_status(log_dir=log_dir, env=simulated_env)
    chain_state = chain.get("chain_state") if isinstance(chain.get("chain_state"), dict) else {}
    payload = _payload(
        status="OK" if not blockers else "BLOCKED",
        scenario=scenario,
        simulated_env=simulated_env,
        selected_signal_id=selected_id,
        steps=steps,
        chain_result={
            "approval_found": chain_state.get("approval_found") is True,
            "execution_intent_found": chain_state.get("execution_intent_found") is True,
            "next_action_kind": (chain.get("next_action") or {}).get("kind"),
        },
        blockers=blockers,
        created_at=created_at,
        env=source,
    )
    if persist:
        _record(payload, log_dir=log_dir)
    return payload


def _payload(
    *,
    status: str,
    scenario: str,
    simulated_env: Mapping[str, str],
    selected_signal_id: str | None,
    steps: list[dict[str, Any]],
    chain_result: Mapping[str, Any],
    blockers: list[str],
    created_at: datetime,
    env: Mapping[str, str],
) -> dict[str, Any]:
    return _sanitize(
        {
            "status": status,
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "created_at": created_at.isoformat(),
            "scenario": scenario,
            "simulated_policy_env": _policy_env(simulated_env),
            "actual_execution_env": build_live_policy_arming_status(env=env).get("execution_env"),
            "selected_signal_id": selected_signal_id,
            "steps": steps,
            "chain_result": dict(chain_result),
            "order_placed": ORDER_PLACED,
            "real_order_placed": REAL_ORDER_PLACED,
            "execution_attempted": EXECUTION_ATTEMPTED,
            "network_allowed": NETWORK_ALLOWED,
            "secrets_shown": SECRETS_SHOWN,
            "blockers": list(dict.fromkeys(blockers)),
        }
    )


def _choose_candidate(queue: Mapping[str, Any], *, scenario: str, signal_id: str | None) -> dict[str, Any] | None:
    buckets = queue.get("buckets") if isinstance(queue.get("buckets"), dict) else {}
    wanted = MICRO_TIMEFRAMES if scenario == "micro" else HIGHER_TIMEFRAMES
    for items in buckets.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if signal_id and item.get("signal_id") != signal_id:
                continue
            if item.get("timeframe") in wanted and item.get("symbol") == "BTCUSDT" and item.get("direction") == "long" and item.get("queue_fresh") is True:
                return item
    return None


def _append_dry_intent(signal_id: str, *, candidate: Mapping[str, Any], log_dir: Path) -> dict[str, Any]:
    created_at = datetime.now(UTC)
    intent_id = uuid4().hex
    preview = {
        "latest_signal_id": signal_id,
        "symbol": candidate.get("symbol"),
        "timeframe": candidate.get("timeframe"),
        "direction": candidate.get("direction"),
        "entry": candidate.get("entry"),
        "stop": candidate.get("stop"),
        "take_profit": candidate.get("take_profit"),
        "margin_usdt": 44.0,
        "leverage": 10,
        "notional_usdt": 440.0,
        "execution_mode": "R75_DRY_INTENT_PREVIEW",
    }
    record = {
        "execution_intent_id": intent_id,
        "created_at": created_at.isoformat(),
        "expires_at": (created_at + timedelta(seconds=300)).isoformat(),
        "phase": "R75",
        "event_type": "live_execution_intent",
        "source": SOURCE,
        "dry_run": True,
        "status": "INTENT_READY",
        "signal_id": signal_id,
        "preview_hash": compute_preview_hash(preview),
        "approval_status": "APPROVED",
        "live_begins_status": "R75_DRY_CHAIN_SMOKE",
        "preview_status": "PREVIEW_READY",
        "execution_mode": "INTENT_ONLY",
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "blockers": [],
        "secrets_shown": False,
    }
    append_live_execution_intent(record, log_dir=log_dir)
    return _sanitize(record)


def _record(payload: Mapping[str, Any], *, log_dir: Path) -> None:
    path = policy_armed_dry_chain_smokes_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "smoke_id": uuid4().hex,
        "event_type": "live_policy_dry_chain_smoke",
        **dict(payload),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize(record), sort_keys=True) + "\n")


def _restore_selection(previous: Mapping[str, Any] | None, *, log_dir: Path) -> None:
    path = selected_signal_path(log_dir)
    if previous:
        path.write_text(json.dumps(_sanitize(dict(previous)), sort_keys=True) + "\n", encoding="utf-8")
    elif path.exists():
        path.unlink()


def _scenario_env(scenario: str, source: Mapping[str, str]) -> dict[str, str]:
    env = dict(source)
    env.setdefault("HAMMER_LIVE_EXECUTION_ENABLED", "false")
    env.setdefault("HAMMER_ALLOW_LIVE_ORDERS", "false")
    env.setdefault("HAMMER_GLOBAL_KILL_SWITCH", "true")
    if scenario in {"micro", "both"}:
        env["HAMMER_MICRO_LIVE_ALLOWED"] = "true"
        env["HAMMER_MICRO_LIVE_TIMEFRAMES"] = "4m,8m"
    if scenario in {"higher", "both"}:
        env["HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED"] = "true"
        env["HAMMER_HIGHER_TIMEFRAME_LIVE_TIMEFRAMES"] = "444m,4H"
    return env


def _policy_env(env: Mapping[str, str]) -> dict[str, Any]:
    policy = get_first_live_timeframe_policy(env=env)
    return {
        "micro_live_allowed": policy.get("micro_live_allowed") is True,
        "micro_live_timeframes": policy.get("micro_live_timeframes") or [],
        "higher_timeframe_live_allowed": policy.get("higher_timeframe_live_allowed") is True,
        "higher_timeframe_live_timeframes": policy.get("higher_timeframe_live_timeframes") or [],
    }


def _step(name: str, status: str, *, reason: str | None = None, result: Mapping[str, Any] | None = None, next_action: Any = None) -> dict[str, Any]:
    return _sanitize(
        {
            "name": name,
            "status": status,
            "reason": reason,
            "next_action": next_action,
            "result_status": (result or {}).get("status") or (result or {}).get("result_status"),
            "order_placed": False,
            "real_order_placed": False,
            "execution_attempted": False,
            "secrets_shown": False,
        }
    )


def _normalize_scenario(value: object) -> str:
    normalized = str(value or "micro").strip().lower()
    return normalized if normalized in SCENARIOS else "micro"


@contextmanager
def _temporary_env_overlay(values: Mapping[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            os.environ[str(key)] = str(value)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in ("order_placed", "real_order_placed", "execution_attempted", "network_allowed", "secrets_shown"):
            if key in sanitized:
                sanitized[key] = False
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
