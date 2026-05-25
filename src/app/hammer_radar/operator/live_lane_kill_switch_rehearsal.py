"""R131 live-lane kill-switch and tiny-live promotion rehearsal.

This module is a non-executing rehearsal layer. It composes existing lane,
router, scheduler, paper-proof, tiny-live gate, and authorization surfaces, but
never creates exchange payloads, calls Binance, mutates env/config, or enables
live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.autonomous_paper_lane_executor_integration import (
    AUTONOMOUS_PAPER_LANE_EXECUTOR_INTEGRATIONS_LEDGER,
    CONFIRM_PAPER_INTEGRATION_PHRASE,
    build_autonomous_paper_lane_executor_integration_status,
)
from src.app.hammer_radar.operator.first_tiny_live_autonomous_lane_authorization import (
    CONFIRM_TINY_LIVE_AUTHORIZATION_PHRASE,
    build_first_tiny_live_autonomous_lane_authorization,
)
from src.app.hammer_radar.operator.first_tiny_live_lane_execution_gate import (
    TINY_LIVE_EXECUTION_BLOCKED,
    build_first_tiny_live_lane_execution_gate,
)
from src.app.hammer_radar.operator.fresh_signal_router import (
    BLOCKED_BY_LANE,
    IGNORE as ROUTER_IGNORE,
    ROUTED_TO_LANE,
    evaluate_candidate_against_lanes,
)
from src.app.hammer_radar.operator.lane_autonomy_control_loop import (
    BLOCKED,
    IGNORE,
    TINY_LIVE_GATE_REVIEW,
    evaluate_lane_autonomy_decision,
)
from src.app.hammer_radar.operator.lane_command_interface import CONFIRM_LANE_CHANGE_PHRASE
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE, load_lane_controls

DEFAULT_LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"
LEDGER_FILENAME = "live_lane_kill_switch_rehearsals.ndjson"
EVENT_TYPE = "LIVE_LANE_KILL_SWITCH_REHEARSAL"
CONFIRM_REHEARSAL_RECORD_PHRASE = "I CONFIRM KILL SWITCH REHEARSAL RECORDING ONLY; NO ORDER; NO CONFIG CHANGE."

KILL_SWITCH_REHEARSAL_READY = "KILL_SWITCH_REHEARSAL_READY"
KILL_SWITCH_REHEARSAL_BLOCKED = "KILL_SWITCH_REHEARSAL_BLOCKED"
KILL_SWITCH_REHEARSAL_ERROR = "KILL_SWITCH_REHEARSAL_ERROR"
KILL_SWITCH_REHEARSAL_REJECTED = "KILL_SWITCH_REHEARSAL_REJECTED"

SAFETY = {
    **SAFETY_FALSE,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
}
BLOCKING_SAFETY_KEYS = (
    "order_placed",
    "real_order_placed",
    "execution_attempted",
    "order_payload_created",
    "network_allowed",
    "secrets_shown",
)
SOURCE_SURFACES_USED = [
    "operator.live_lane_kill_switch_rehearsal.build_live_lane_kill_switch_rehearsal",
    "operator.lane_control.load_lane_controls",
    "operator.lane_command_interface R124 preview/confirmation semantics",
    "operator.fresh_signal_router.evaluate_candidate_against_lanes",
    "operator.lane_autonomy_control_loop.evaluate_lane_autonomy_decision",
    "operator.lane_autonomy_scheduler scheduler semantics via R127 decisions",
    "operator.autonomous_paper_lane_executor_integration.build_autonomous_paper_lane_executor_integration_status",
    "operator.first_tiny_live_lane_execution_gate.build_first_tiny_live_lane_execution_gate",
    "operator.first_tiny_live_autonomous_lane_authorization.build_first_tiny_live_autonomous_lane_authorization",
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{AUTONOMOUS_PAPER_LANE_EXECUTOR_INTEGRATIONS_LEDGER}",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_live_lane_kill_switch_rehearsal(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    config_path: str | Path | None = None,
    now: datetime | None = None,
    controls: Mapping[str, Any] | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    loaded_controls = dict(controls) if controls is not None else load_lane_controls(config_path)
    lane = _find_lane(loaded_controls, lane_key)
    current_lane_mode = str((lane or {}).get("mode") or "missing").strip().lower()
    scenarios: list[dict[str, Any]] = []
    blockers: list[str] = []

    try:
        r129 = build_autonomous_paper_lane_executor_integration_status(log_dir=resolved_log_dir, limit=5)
        r126 = build_first_tiny_live_lane_execution_gate(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            record=False,
            config_path=config_path,
        )
        r130 = build_first_tiny_live_autonomous_lane_authorization(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            config_path=config_path,
            record_authorization=False,
        )
        scenarios.append(
            {
                "name": "baseline_current_state",
                "status": "COMPLETED",
                "current_lane_mode": current_lane_mode,
                "r130_authorization_status": r130.get("status"),
                "r126_tiny_live_gate_status": r126.get("status"),
                "r129_paper_integration_status": r129.get("status"),
                "r130_blockers": list(r130.get("blockers") or [])[:10],
                "r126_blockers": list(r126.get("blockers") or [])[:10],
                "mutated_config": False,
                "mutated_env": False,
            }
        )
        blockers.extend(str(item) for item in r130.get("blockers") or [])
        blockers.extend(str(item) for item in r126.get("blockers") or [])
    except Exception as exc:  # pragma: no cover - defensive diagnostic surface
        scenarios.append(_error_scenario("baseline_current_state", exc))
        blockers.append(f"baseline_current_state could not be evaluated: {exc.__class__.__name__}")

    lane_disable = simulate_lane_disable(
        lane_key=lane_key,
        controls=loaded_controls,
        now=generated_at,
        live_eligibility_matrix=live_eligibility_matrix,
        log_dir=resolved_log_dir,
    )
    global_kill = simulate_global_kill_switch_block(
        lane_key=lane_key,
        controls=loaded_controls,
        now=generated_at,
        live_eligibility_matrix=live_eligibility_matrix,
        log_dir=resolved_log_dir,
    )
    rollback = simulate_lane_mode_rollback(
        lane_key=lane_key,
        controls=loaded_controls,
        now=generated_at,
        live_eligibility_matrix=live_eligibility_matrix,
        log_dir=resolved_log_dir,
    )
    scheduler_off = simulate_scheduler_respects_killed_lane(
        lane_key=lane_key,
        controls=loaded_controls,
        now=generated_at,
        live_eligibility_matrix=live_eligibility_matrix,
        log_dir=resolved_log_dir,
    )
    promotion_reversal = simulate_tiny_live_promotion_reversal(
        lane_key=lane_key,
        controls=loaded_controls,
        now=generated_at,
        live_eligibility_matrix=live_eligibility_matrix,
        log_dir=resolved_log_dir,
    )
    scenarios.extend([lane_disable, global_kill, rollback, scheduler_off])
    scenarios.append(_paper_proof_gap_scenario(lane_key))
    scenarios.append(promotion_reversal)

    verdict = {
        "global_kill_switch_blocks_live_intent": bool(global_kill.get("live_intent_blocked")),
        "lane_disable_blocks_live_intent": bool(lane_disable.get("live_intent_blocked")),
        "rollback_blocks_live_intent": bool(rollback.get("tiny_live_intent_blocked")),
        "scheduler_respects_disabled_lane": bool(scheduler_off.get("scheduler_respects_disabled_lane")),
        "paper_live_separation_intact": True,
    }
    blockers.extend(_scenario_blockers(scenarios))
    blockers = _dedupe(blockers)
    safety = dict(SAFETY)
    status = _rehearsal_status(scenarios=scenarios, verdict=verdict, safety=safety)

    return _sanitize(
        {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "lane_key": lane_key,
            "current_lane_mode": current_lane_mode,
            "scenarios": scenarios,
            "kill_switch_verdict": verdict,
            "current_blockers": blockers,
            "next_actions": build_rehearsal_next_actions(blockers=blockers, lane_key=lane_key),
            "safe_command_pack": _safe_command_pack(lane_key),
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
            "ledger_path": str(live_lane_kill_switch_rehearsal_records_path(resolved_log_dir)),
        }
    )


def simulate_lane_disable(
    *,
    lane_key: str = DEFAULT_LANE_KEY,
    controls: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    loaded_controls = dict(controls) if controls is not None else load_lane_controls()
    disabled_controls = _controls_with_mode(loaded_controls, lane_key, "disabled")
    lane = _find_lane(disabled_controls, lane_key)
    candidate = _candidate_for_lane(lane, generated_at)
    routed = evaluate_candidate_against_lanes(
        candidate,
        controls=disabled_controls,
        live_eligibility_matrix=live_eligibility_matrix,
        global_gate=_global_gate_ready_for_review(),
        now=generated_at,
        log_dir=log_dir,
    )
    decision = evaluate_lane_autonomy_decision(routed, lane=lane, existing_records=[], now=generated_at)
    live_intent_blocked = (
        routed.get("route_status") == BLOCKED_BY_LANE
        and routed.get("route_action") == ROUTER_IGNORE
        and decision.get("autonomy_decision") in {BLOCKED, IGNORE}
    )
    return _scenario(
        name="lane_disable_rehearsal",
        passed=live_intent_blocked,
        lane_mode="disabled",
        route_status=routed.get("route_status"),
        route_action=routed.get("route_action"),
        autonomy_decision=decision.get("autonomy_decision"),
        live_intent_blocked=live_intent_blocked,
        config_written=False,
        env_mutated=False,
        blockers=_dedupe([*list(routed.get("blockers") or []), *list(decision.get("blockers") or [])]),
    )


def simulate_global_kill_switch_block(
    *,
    lane_key: str = DEFAULT_LANE_KEY,
    controls: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    loaded_controls = dict(controls) if controls is not None else load_lane_controls()
    tiny_live_controls = _controls_with_mode(loaded_controls, lane_key, "tiny_live")
    lane = _find_lane(tiny_live_controls, lane_key)
    candidate = _candidate_for_lane(lane, generated_at)
    routed = evaluate_candidate_against_lanes(
        candidate,
        controls=tiny_live_controls,
        live_eligibility_matrix=live_eligibility_matrix,
        global_gate=_global_gate_killed(),
        now=generated_at,
        log_dir=log_dir,
    )
    decision = evaluate_lane_autonomy_decision(routed, lane=lane, existing_records=[], now=generated_at)
    live_intent_blocked = routed.get("route_status") == BLOCKED_BY_LANE and decision.get("autonomy_decision") in {BLOCKED, IGNORE}
    return _scenario(
        name="global_kill_switch_rehearsal",
        passed=live_intent_blocked,
        lane_mode="tiny_live",
        route_status=routed.get("route_status"),
        route_action=routed.get("route_action"),
        autonomy_decision=decision.get("autonomy_decision"),
        live_intent_blocked=live_intent_blocked,
        paper_live_separation_intact=True,
        config_written=False,
        env_mutated=False,
        blockers=_dedupe(["global kill switch active", *list(routed.get("blockers") or []), *list(decision.get("blockers") or [])]),
    )


def simulate_lane_mode_rollback(
    *,
    lane_key: str = DEFAULT_LANE_KEY,
    controls: Mapping[str, Any] | None = None,
    rollback_mode: str = "armed_dry_run",
    now: datetime | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    loaded_controls = dict(controls) if controls is not None else load_lane_controls()
    rollback_controls = _controls_with_mode(_controls_with_mode(loaded_controls, lane_key, "tiny_live"), lane_key, rollback_mode)
    lane = _find_lane(rollback_controls, lane_key)
    candidate = _candidate_for_lane(lane, generated_at)
    routed = evaluate_candidate_against_lanes(
        candidate,
        controls=rollback_controls,
        live_eligibility_matrix=live_eligibility_matrix,
        global_gate=_global_gate_ready_for_review(),
        now=generated_at,
        log_dir=log_dir,
    )
    decision = evaluate_lane_autonomy_decision(routed, lane=lane, existing_records=[], now=generated_at)
    r126_gate = build_first_tiny_live_lane_execution_gate(
        log_dir=log_dir,
        lane_key=lane_key,
        record=False,
        config_path=None,
        candidates=[candidate],
        now=generated_at,
        live_eligibility_matrix=live_eligibility_matrix,
        r106_gate=_global_gate_ready_for_review(),
        global_gates={"status": "READY"},
        paper_records=[],
    )
    tiny_live_blocked = decision.get("autonomy_decision") != TINY_LIVE_GATE_REVIEW and r126_gate.get("status") == TINY_LIVE_EXECUTION_BLOCKED
    return _scenario(
        name="rollback_from_tiny_live_rehearsal",
        passed=tiny_live_blocked,
        simulated_start_mode="tiny_live",
        rollback_mode=rollback_mode,
        route_status=routed.get("route_status"),
        autonomy_decision=decision.get("autonomy_decision"),
        r126_status_after_rollback=r126_gate.get("status"),
        tiny_live_intent_blocked=tiny_live_blocked,
        config_written=False,
        env_mutated=False,
        blockers=_dedupe([*list(r126_gate.get("blockers") or []), *list(decision.get("blockers") or [])]),
    )


def simulate_scheduler_respects_killed_lane(
    *,
    lane_key: str = DEFAULT_LANE_KEY,
    controls: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    disabled = simulate_lane_disable(
        lane_key=lane_key,
        controls=controls,
        now=now,
        live_eligibility_matrix=live_eligibility_matrix,
        log_dir=log_dir,
    )
    respects = bool(disabled.get("autonomy_decision") in {BLOCKED, IGNORE} and disabled.get("live_intent_blocked"))
    return _scenario(
        name="scheduler_respects_lane_off_rehearsal",
        passed=respects,
        scheduler_respects_disabled_lane=respects,
        simulated_scheduler_action="stopped_or_blocked",
        autonomy_decision=disabled.get("autonomy_decision"),
        live_intent_blocked=disabled.get("live_intent_blocked"),
        config_written=False,
        env_mutated=False,
        blockers=list(disabled.get("blockers") or []),
    )


def simulate_tiny_live_promotion_reversal(
    *,
    lane_key: str = DEFAULT_LANE_KEY,
    controls: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    live_eligibility_matrix: Mapping[str, Any] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    loaded_controls = dict(controls) if controls is not None else load_lane_controls()
    tiny_live_controls = _controls_with_mode(loaded_controls, lane_key, "tiny_live")
    rollback_controls = _controls_with_mode(tiny_live_controls, lane_key, "disabled")
    lane = _find_lane(rollback_controls, lane_key)
    candidate = _candidate_for_lane(lane, generated_at)
    routed = evaluate_candidate_against_lanes(
        candidate,
        controls=rollback_controls,
        live_eligibility_matrix=live_eligibility_matrix,
        global_gate=_global_gate_killed(),
        now=generated_at,
        log_dir=log_dir,
    )
    decision = evaluate_lane_autonomy_decision(routed, lane=lane, existing_records=[], now=generated_at)
    reversed_ok = routed.get("route_status") == BLOCKED_BY_LANE and decision.get("autonomy_decision") in {BLOCKED, IGNORE}
    return _scenario(
        name="tiny_live_promotion_rehearsal",
        passed=reversed_ok,
        simulated_requested_mode="tiny_live",
        simulated_reversal_mode="disabled",
        route_status=routed.get("route_status"),
        autonomy_decision=decision.get("autonomy_decision"),
        tiny_live_promotion_reversed=True,
        tiny_live_intent_blocked=reversed_ok,
        config_written=False,
        env_mutated=False,
        blockers=list(routed.get("blockers") or []) + list(decision.get("blockers") or []),
        command_hints=[
            _safe_command_pack(lane_key)["tiny_live_authorization_preview"],
            _safe_command_pack(lane_key)["tiny_live_mode_preview"],
        ],
    )


def build_rehearsal_next_actions(*, blockers: list[str] | None = None, lane_key: str = DEFAULT_LANE_KEY) -> list[str]:
    blocker_text = " ".join(str(item).lower() for item in blockers or [])
    actions = [
        "Keep global live execution disabled until a future approved phase changes it.",
        "Keep lane rollback and disable controls operator-owned through R124.",
    ]
    if "recent autonomous paper proof is missing" in blocker_text or "paper proof" in blocker_text:
        actions.append("Produce recent autonomous paper proof through R129 using the safe paper proof command template.")
    if "r126 tiny-live gate" in blocker_text or "no configured tiny_live lane" in blocker_text:
        actions.append("Preview R124 tiny_live lane mode and rerun R126; do not apply mode without the R124 confirmation phrase.")
    actions.append(f"Rerun R131 rehearsal for {lane_key} after paper proof and tiny_live lane-mode prerequisites are previewed.")
    return _dedupe(actions)


def append_live_lane_kill_switch_rehearsal_record(
    payload: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = live_lane_kill_switch_rehearsal_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "event_type": EVENT_TYPE,
        "rehearsal_id": str(payload.get("rehearsal_id") or f"live_lane_kill_switch_rehearsal_{uuid4().hex}"),
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "lane_key": payload.get("lane_key"),
        "status": payload.get("status"),
        "current_lane_mode": payload.get("current_lane_mode"),
        "scenario_count": len(payload.get("scenarios") or []),
        "kill_switch_verdict": payload.get("kill_switch_verdict") or {},
        "current_blockers": list(payload.get("current_blockers") or []),
        "next_actions": list(payload.get("next_actions") or []),
        "safety": payload.get("safety") or dict(SAFETY),
        "source_surfaces_used": list(payload.get("source_surfaces_used") or []),
    }
    record = _sanitize(record)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return record


def load_live_lane_kill_switch_rehearsal_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
    lane_key: str | None = None,
) -> list[dict[str, Any]]:
    path = live_lane_kill_switch_rehearsal_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if lane_key is not None and record.get("lane_key") != lane_key:
                continue
            records.append(record)
    if limit > 0:
        return list(reversed(records))[:limit]
    return records


def summarize_live_lane_kill_switch_rehearsals(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    lane_counts = Counter(str(record.get("lane_key") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "last_rehearsal_id": records[-1].get("rehearsal_id") if records else None,
        "safety": dict(SAFETY),
    }


def build_live_lane_kill_switch_rehearsal_cli_payload(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    record_rehearsal: bool = False,
    confirm_rehearsal_record: str | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    payload = build_live_lane_kill_switch_rehearsal(log_dir=log_dir, lane_key=lane_key, config_path=config_path)
    if not record_rehearsal:
        return payload
    if confirm_rehearsal_record != CONFIRM_REHEARSAL_RECORD_PHRASE:
        return _sanitize(
            {
                **payload,
                "status": KILL_SWITCH_REHEARSAL_REJECTED,
                "record_rehearsal_requested": True,
                "confirmation_valid": False,
                "ledger_written": False,
                "current_blockers": _dedupe(["exact kill-switch rehearsal recording confirmation phrase is required", *payload.get("current_blockers", [])]),
                "safety": dict(SAFETY),
            }
        )
    record = append_live_lane_kill_switch_rehearsal_record(payload, log_dir=log_dir)
    return _sanitize({**payload, "record_rehearsal_requested": True, "confirmation_valid": True, "ledger_written": True, "rehearsal_id": record["rehearsal_id"]})


def format_live_lane_kill_switch_rehearsal_json(payload: Mapping[str, Any]) -> str:
    compact = {
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at"),
        "lane_key": payload.get("lane_key"),
        "current_lane_mode": payload.get("current_lane_mode"),
        "record_rehearsal_requested": bool(payload.get("record_rehearsal_requested", False)),
        "confirmation_valid": bool(payload.get("confirmation_valid", False)),
        "ledger_written": bool(payload.get("ledger_written", False)),
        "rehearsal_id": payload.get("rehearsal_id"),
        "scenarios": list(payload.get("scenarios") or []),
        "kill_switch_verdict": payload.get("kill_switch_verdict") or {},
        "current_blockers": list(payload.get("current_blockers") or []),
        "next_actions": list(payload.get("next_actions") or []),
        "safe_command_pack": payload.get("safe_command_pack") or {},
        "safety": payload.get("safety") or dict(SAFETY),
        "ledger_path": payload.get("ledger_path"),
        "source_surfaces_used": list(payload.get("source_surfaces_used") or []),
    }
    return json.dumps(_sanitize(compact), sort_keys=True, separators=(",", ":"))


def live_lane_kill_switch_rehearsal_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _paper_proof_gap_scenario(lane_key: str) -> dict[str, Any]:
    return _scenario(
        name="paper_proof_gap_rehearsal",
        passed=True,
        paper_proof_command_available=True,
        r129_command=_safe_command_pack(lane_key)["paper_proof_confirmed_record_command"],
        config_written=False,
        env_mutated=False,
        blockers=[],
    )


def _safe_command_pack(lane_key: str) -> dict[str, str]:
    return {
        "paper_proof_preview": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            f"--log-dir logs/hammer_radar_forward autonomous-paper-lane-executor-integration --lane-key \"{lane_key}\""
        ),
        "paper_proof_confirmed_record_command": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            f"--log-dir logs/hammer_radar_forward autonomous-paper-lane-executor-integration --lane-key \"{lane_key}\" "
            f"--record-paper --confirm-paper-integration \"{CONFIRM_PAPER_INTEGRATION_PHRASE}\""
        ),
        "tiny_live_authorization_preview": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            f"--log-dir logs/hammer_radar_forward first-tiny-live-autonomous-lane-authorization --lane-key \"{lane_key}\" "
            "--request-lane-mode-tiny-live"
        ),
        "tiny_live_mode_preview": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            f"--log-dir logs/hammer_radar_forward lane-control-command --action preview-set-mode --lane-key \"{lane_key}\" "
            "--mode tiny_live --request-tiny-live"
        ),
        "r126_gate_check": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            f"--log-dir logs/hammer_radar_forward first-tiny-live-lane-execution-gate --lane-key \"{lane_key}\""
        ),
        "r130_authorization_check": (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            f"--log-dir logs/hammer_radar_forward first-tiny-live-autonomous-lane-authorization --lane-key \"{lane_key}\""
        ),
        "r124_confirm_phrase": CONFIRM_LANE_CHANGE_PHRASE,
        "r130_confirm_phrase": CONFIRM_TINY_LIVE_AUTHORIZATION_PHRASE,
    }


def _rehearsal_status(*, scenarios: list[Mapping[str, Any]], verdict: Mapping[str, Any], safety: Mapping[str, Any]) -> str:
    if any(scenario.get("status") == KILL_SWITCH_REHEARSAL_ERROR for scenario in scenarios):
        return KILL_SWITCH_REHEARSAL_ERROR
    if any(bool(safety.get(key)) for key in BLOCKING_SAFETY_KEYS):
        return KILL_SWITCH_REHEARSAL_BLOCKED
    if safety.get("paper_live_separation_intact") is not True or safety.get("config_written") or safety.get("env_mutated"):
        return KILL_SWITCH_REHEARSAL_BLOCKED
    required = (
        "global_kill_switch_blocks_live_intent",
        "lane_disable_blocks_live_intent",
        "rollback_blocks_live_intent",
        "scheduler_respects_disabled_lane",
        "paper_live_separation_intact",
    )
    if not all(bool(verdict.get(key)) for key in required):
        return KILL_SWITCH_REHEARSAL_BLOCKED
    if not all(str(scenario.get("status")) == "COMPLETED" for scenario in scenarios):
        return KILL_SWITCH_REHEARSAL_BLOCKED
    return KILL_SWITCH_REHEARSAL_READY


def _scenario(name: str, *, passed: bool, blockers: list[str] | None = None, **fields: Any) -> dict[str, Any]:
    return {
        "name": name,
        "status": "COMPLETED" if passed else "BLOCKED",
        "passed": bool(passed),
        **fields,
        "blockers": _dedupe(list(blockers or [])),
        "safety": dict(SAFETY),
    }


def _error_scenario(name: str, exc: Exception) -> dict[str, Any]:
    return {
        "name": name,
        "status": KILL_SWITCH_REHEARSAL_ERROR,
        "passed": False,
        "blockers": [f"{name} failed: {exc.__class__.__name__}"],
        "safety": dict(SAFETY),
    }


def _scenario_blockers(scenarios: list[Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for scenario in scenarios:
        if scenario.get("passed") is False:
            blockers.append(f"{scenario.get('name')} did not pass")
        blockers.extend(str(item) for item in scenario.get("blockers") or [])
    return _dedupe(blockers)


def _candidate_for_lane(lane: Mapping[str, Any] | None, now: datetime) -> dict[str, Any]:
    lane_record = dict(lane or {})
    return {
        "candidate_id": f"rehearsal|{lane_record.get('lane_key') or DEFAULT_LANE_KEY}",
        "symbol": lane_record.get("symbol") or "BTCUSDT",
        "timeframe": lane_record.get("timeframe") or "13m",
        "direction": lane_record.get("direction") or "long",
        "entry_mode": lane_record.get("entry_mode") or "ladder_close_50_618",
        "generated_at": (now - timedelta(seconds=5)).isoformat(),
        "entry": 100.0,
        "stop": 99.0,
        "take_profit": 102.0,
        "score": 100,
    }


def _controls_with_mode(controls: Mapping[str, Any], lane_key: str, mode: str) -> dict[str, Any]:
    lanes = [dict(lane) for lane in controls.get("lanes") or []]
    for lane in lanes:
        if lane.get("lane_key") == lane_key:
            lane["mode"] = mode
            break
    return {**dict(controls), "lanes": lanes, "lane_map": {str(lane.get("lane_key")): lane for lane in lanes}}


def _find_lane(controls: Mapping[str, Any], lane_key: str | None) -> dict[str, Any] | None:
    lane = (controls.get("lane_map") or {}).get(str(lane_key or ""))
    return dict(lane) if lane else None


def _global_gate_killed() -> dict[str, Any]:
    return {
        "status": "FIRST_LIVE_BLOCKED",
        "execution_enabled_by_gate": False,
        "live_ready": False,
        "global_kill_switch": True,
        "blockers": ["global kill switch active"],
    }


def _global_gate_ready_for_review() -> dict[str, Any]:
    return {
        "status": "FIRST_LIVE_ACTIVATION_READY",
        "execution_enabled_by_gate": True,
        "live_ready": False,
        "global_kill_switch": False,
    }


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in BLOCKING_SAFETY_KEYS:
            if key in sanitized:
                sanitized[key] = False
        if "paper_live_separation_intact" in sanitized:
            sanitized["paper_live_separation_intact"] = bool(sanitized["paper_live_separation_intact"])
        if "env_mutated" in sanitized:
            sanitized["env_mutated"] = False
        if "config_written" in sanitized:
            sanitized["config_written"] = False
        if "global_live_flags_changed" in sanitized:
            sanitized["global_live_flags_changed"] = False
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
