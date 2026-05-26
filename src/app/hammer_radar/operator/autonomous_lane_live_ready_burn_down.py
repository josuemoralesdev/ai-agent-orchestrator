"""R138 autonomous lane live-ready burn-down.

This module composes existing autonomous-lane readiness surfaces into one
operator burn-down report. It is diagnostic only: it never creates executable
payloads, signs requests, calls Binance, mutates env/config, or places orders.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.execution.binance_futures_connector import (
    build_connector_status,
    build_protective_status,
)
from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.autonomous_paper_lane_executor_integration import (
    CONFIRM_PAPER_INTEGRATION_PHRASE,
    load_paper_executor_integration_records,
    run_autonomous_paper_lane_executor_once,
)
from src.app.hammer_radar.operator.binance_live_status import build_binance_live_status
from src.app.hammer_radar.operator.final_live_preflight import READY, build_final_live_preflight
from src.app.hammer_radar.operator.first_live_activation_gate import (
    FIRST_LIVE_ACTIVATION_READY,
    build_first_live_activation_gate,
)
from src.app.hammer_radar.operator.first_tiny_live_autonomous_lane_authorization import (
    CONFIRM_TINY_LIVE_AUTHORIZATION_PHRASE,
    TINY_LIVE_AUTHORIZATION_RECORDED,
    build_first_tiny_live_autonomous_lane_authorization,
    load_tiny_live_lane_authorization_records,
)
from src.app.hammer_radar.operator.first_tiny_live_lane_execution_gate import (
    TINY_LIVE_EXECUTION_READY,
    build_first_tiny_live_lane_execution_gate,
)
from src.app.hammer_radar.operator.first_tiny_live_order_payload_dry_authorization import (
    DRY_AUTHORIZATION_READY,
    build_first_tiny_live_order_payload_dry_authorization,
)
from src.app.hammer_radar.operator.fresh_signal_router import ROUTED_TO_LANE, build_fresh_signal_router_status
from src.app.hammer_radar.operator.lane_command_interface import CONFIRM_LANE_CHANGE_PHRASE
from src.app.hammer_radar.operator.lane_control import load_lane_controls
from src.app.hammer_radar.operator.live_adapter_boundary_final_review import (
    LIVE_ADAPTER_BOUNDARY_REVIEW_READY,
    build_live_adapter_boundary_final_review,
)
from src.app.hammer_radar.operator.live_adapter_execution_rehearsal import (
    LIVE_ADAPTER_REHEARSAL_READY_FOR_FUTURE_IMPLEMENTATION,
    build_live_adapter_execution_rehearsal,
)
from src.app.hammer_radar.operator.live_arming_preflight import build_live_arming_preflight
from src.app.hammer_radar.operator.live_env_boundary_review import LIVE_ENV_LOCKED_SAFE, build_live_env_boundary_review
from src.app.hammer_radar.operator.live_lane_kill_switch_rehearsal import (
    KILL_SWITCH_REHEARSAL_READY,
    build_live_lane_kill_switch_rehearsal,
)
from src.app.hammer_radar.operator.protective_order_dry_policy_review import (
    PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW,
    build_protective_order_dry_policy_review,
)
from src.app.hammer_radar.operator.protective_payload_dry_preview_boundary import (
    PROTECTIVE_PAYLOAD_READY_FOR_FUTURE_DRY_RUN,
    build_protective_payload_dry_preview_boundary,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import (
    RISK_CONTRACT_VALID_FOR_PREFLIGHT,
    build_tiny_live_risk_contract_payload,
)

LIVE_READY_BURN_DOWN_READY = "LIVE_READY_BURN_DOWN_READY"
LIVE_READY_BURN_DOWN_BLOCKED = "LIVE_READY_BURN_DOWN_BLOCKED"
LIVE_READY_BURN_DOWN_ERROR = "LIVE_READY_BURN_DOWN_ERROR"
LIVE_READY_BURN_DOWN_REJECTED = "LIVE_READY_BURN_DOWN_REJECTED"

EVENT_TYPE = "AUTONOMOUS_LANE_LIVE_READY_BURN_DOWN"
LEDGER_FILENAME = "autonomous_lane_live_ready_burn_downs.ndjson"
DEFAULT_LANE_KEY = "BTCUSDT|13m|long|ladder_close_50_618"
CONFIRM_BURN_DOWN_RECORDING_PHRASE = "I CONFIRM LIVE READY BURN DOWN RECORDING ONLY; NO ORDER; NO BINANCE CALL."

BLOCKER_CATEGORIES = {
    "EVIDENCE",
    "LANE_MODE",
    "AUTHORIZATION",
    "PAPER_PROOF",
    "PROTECTIVE_POLICY",
    "PROTECTIVE_PAYLOAD",
    "CREDENTIAL_BOUNDARY",
    "ADAPTER_BOUNDARY",
    "GLOBAL_GATE",
    "KILL_SWITCH",
    "ENV_FLAGS",
    "RISK_CONTRACT",
    "FRESH_SIGNAL",
    "UI_VISIBILITY",
    "UNKNOWN",
}
SEVERITY_ORDER = {
    "CRITICAL_BLOCKER": 0,
    "HIGH_BLOCKER": 1,
    "MEDIUM_BLOCKER": 2,
    "LOW_BLOCKER": 3,
    "INFO": 4,
}
SAFETY = {
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "network_allowed": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "secrets_shown": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
}
BLOCKING_SAFETY_KEYS = tuple(key for key, value in SAFETY.items() if value is False)

SOURCE_SURFACES_USED = [
    "operator.autonomous_lane_live_ready_burn_down.build_autonomous_lane_live_ready_burn_down",
    "operator.lane_control.load_lane_controls",
    "operator.fresh_signal_router.build_fresh_signal_router_status",
    "operator.autonomous_paper_lane_executor_integration.run_autonomous_paper_lane_executor_once",
    "operator.first_tiny_live_lane_execution_gate.build_first_tiny_live_lane_execution_gate",
    "operator.first_tiny_live_autonomous_lane_authorization.build_first_tiny_live_autonomous_lane_authorization",
    "operator.live_lane_kill_switch_rehearsal.build_live_lane_kill_switch_rehearsal",
    "operator.live_adapter_boundary_final_review.build_live_adapter_boundary_final_review",
    "operator.first_tiny_live_order_payload_dry_authorization.build_first_tiny_live_order_payload_dry_authorization",
    "operator.live_adapter_execution_rehearsal.build_live_adapter_execution_rehearsal",
    "operator.protective_order_dry_policy_review.build_protective_order_dry_policy_review",
    "operator.protective_payload_dry_preview_boundary.build_protective_payload_dry_preview_boundary",
    "operator.final_live_preflight.build_final_live_preflight",
    "operator.first_live_activation_gate.build_first_live_activation_gate",
    "operator.live_env_boundary_review.build_live_env_boundary_review",
    "operator.live_arming_preflight.build_live_arming_preflight",
    "operator.binance_live_status.build_binance_live_status",
    "execution.binance_futures_connector.build_connector_status",
    "execution.binance_futures_connector.build_protective_status",
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_autonomous_lane_live_ready_burn_down(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    source_statuses: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    try:
        statuses = (
            dict(source_statuses)
            if source_statuses is not None
            else collect_live_ready_source_statuses(
                log_dir=resolved_log_dir,
                lane_key=lane_key,
                config_path=config_path,
                env=env,
                now=generated_at,
            )
        )
        inventory = build_blocker_inventory(source_statuses=statuses, lane_key=lane_key)
        ranked = rank_live_ready_blockers(inventory)
        summary = _blocker_summary(ranked)
        dependency_chain = build_dependency_chain(ranked_blockers=ranked, lane_key=lane_key)
        probability_ladder = build_probability_ladder(ranked_blockers=ranked)
        command_pack = build_operator_burn_down_command_pack(lane_key=lane_key)
        live_ready_now = _live_ready_now(statuses, ranked)
        status = LIVE_READY_BURN_DOWN_READY if _safety_clean(SAFETY) else LIVE_READY_BURN_DOWN_BLOCKED
        return _sanitize(
            {
                "status": status,
                "generated_at": generated_at.isoformat(),
                "lane_key": lane_key,
                "live_ready_now": live_ready_now,
                "tiny_live_today_probability_pct": probability_ladder[0]["probability_pct"] if probability_ladder else 0,
                "tiny_live_next_session_probability_pct": probability_ladder[-1]["probability_pct"] if probability_ladder else 0,
                "source_statuses": statuses,
                "blocker_inventory": inventory,
                "ranked_blockers": ranked,
                "blocker_summary": summary,
                "dependency_chain": dependency_chain,
                "probability_ladder": probability_ladder,
                "recommended_clear_order": [item["id"] for item in ranked if item["severity"] != "INFO"],
                "operator_command_pack": command_pack,
                "next_phase_recommendation": {
                    "phase": "R139",
                    "title": "Live-ready blocker clearing operator pack",
                    "scope": "Clear or record evidence for R138 blockers in the recommended order without real orders, Binance calls, env mutation, or live flag changes.",
                    "not_order_placement": True,
                },
                "safety": dict(SAFETY),
                "source_surfaces_used": _source_surfaces(statuses),
            }
        )
    except Exception as exc:  # pragma: no cover - defensive diagnostic boundary
        return _sanitize(
            {
                "status": LIVE_READY_BURN_DOWN_ERROR,
                "generated_at": generated_at.isoformat(),
                "lane_key": lane_key,
                "live_ready_now": False,
                "tiny_live_today_probability_pct": 0,
                "tiny_live_next_session_probability_pct": 0,
                "source_statuses": {"error": exc.__class__.__name__},
                "blocker_inventory": [],
                "ranked_blockers": [],
                "blocker_summary": _blocker_summary([]),
                "dependency_chain": [],
                "probability_ladder": [],
                "recommended_clear_order": [],
                "operator_command_pack": build_operator_burn_down_command_pack(lane_key=lane_key),
                "next_phase_recommendation": {
                    "phase": "R138_RECHECK",
                    "title": "Repair burn-down source error",
                    "scope": "Fix source-surface evaluation before recording burn-down evidence.",
                    "not_order_placement": True,
                },
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def collect_live_ready_source_statuses(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_env = os.environ if env is None else env
    generated_at = now or datetime.now(UTC)
    candidate_id = f"normal|{lane_key}"
    controls = load_lane_controls(config_path)
    lane = _find_lane(controls, lane_key)
    lane_mode = str((lane or {}).get("mode") or "missing").strip().lower()
    risk_contract = build_tiny_live_risk_contract_payload(candidate_id=candidate_id)
    router = build_fresh_signal_router_status(log_dir=resolved_log_dir, config_path=config_path, now=generated_at)
    paper_integration = run_autonomous_paper_lane_executor_once(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        record_paper=False,
        record_scheduler_tick=False,
        record_decisions=False,
    )
    connector_status = build_connector_status(env=source_env, log_dir=resolved_log_dir)
    protective_status = build_protective_status(env=source_env, log_dir=resolved_log_dir)
    binance_status = build_binance_live_status(env=source_env)
    if lane_mode != "tiny_live":
        r126_gate = build_first_tiny_live_lane_execution_gate(
            log_dir=resolved_log_dir,
            lane_key=lane_key,
            record=False,
            config_path=config_path,
            env=source_env,
            risk_contract=risk_contract,
        )
        deferred = _deferred_status("NOT_EVALUATED_LANE_NOT_TINY_LIVE")
        return _sanitize(
            {
                "lane": lane or {},
                "lane_mode": lane_mode,
                "fresh_signal_router": router,
                "paper_integration": paper_integration,
                "paper_integration_records_summary": _paper_integration_records_summary(
                    _filter_lane_records(load_paper_executor_integration_records(log_dir=resolved_log_dir, limit=50), lane_key)
                ),
                "r126_tiny_live_gate": r126_gate,
                "r130_authorization": {
                    **deferred,
                    "status": "TINY_LIVE_AUTHORIZATION_BLOCKED",
                    "blockers": ["selected lane is not tiny_live; R130 recording deferred"],
                    "safety": dict(SAFETY),
                },
                "r130_authorization_records_summary": _authorization_records_summary(
                    load_tiny_live_lane_authorization_records(log_dir=resolved_log_dir, lane_key=lane_key, limit=20)
                ),
                "r131_kill_switch_rehearsal": {**deferred, "status": "KILL_SWITCH_REHEARSAL_BLOCKED", "current_blockers": ["selected lane is not tiny_live"], "safety": dict(SAFETY)},
                "r132_adapter_boundary": {**deferred, "status": "LIVE_ADAPTER_BOUNDARY_BLOCKED", "main_blockers": ["selected lane is not tiny_live"], "safety": dict(SAFETY)},
                "r134_dry_authorization": {**deferred, "status": "DRY_AUTHORIZATION_BLOCKED", "blockers": ["selected lane is not tiny_live"], "safety": dict(SAFETY)},
                "r135_adapter_rehearsal": {**deferred, "status": "LIVE_ADAPTER_REHEARSAL_BLOCKED", "main_blockers": ["selected lane is not tiny_live"], "safety": dict(SAFETY)},
                "r136_protective_policy": {**deferred, "status": "PROTECTIVE_POLICY_BLOCKED", "main_blockers": ["selected lane is not tiny_live"], "safety": dict(SAFETY)},
                "r137_protective_preview": {**deferred, "status": "PROTECTIVE_PAYLOAD_BLOCKED", "main_blockers": ["selected lane is not tiny_live"], "safety": dict(SAFETY)},
                "final_live_preflight": {
                    **deferred,
                    "status": "BLOCKED",
                    "blockers": ["final preflight recheck required after lane is tiny_live"],
                    "global_kill_switch": connector_status.get("global_kill_switch"),
                    "live_execution_enabled": connector_status.get("live_execution_enabled"),
                    "live_orders_allowed": connector_status.get("allow_live_orders"),
                    "connector_mode": connector_status.get("connector_mode"),
                    "binance_credentials_present": {
                        "api_key_present": bool(binance_status.get("api_key_present") or connector_status.get("api_key_present")),
                        "api_secret_present": bool(binance_status.get("api_secret_present") or connector_status.get("api_secret_present")),
                    },
                    "protective_orders_ready": protective_status.get("protective_orders_ready"),
                    "safety": dict(SAFETY),
                },
                "first_live_activation_gate": {**deferred, "status": "FIRST_LIVE_BLOCKED", "blockers": ["R106 recheck required after lane is tiny_live"], "safety": dict(SAFETY)},
                "live_env_boundary": {**deferred, "boundary_status": "LIVE_ENV_ARMING_NOT_ALLOWED_YET", "blockers": ["live env boundary recheck required"], "safety": dict(SAFETY)},
                "live_arming_preflight": {**deferred, "final_preflight_status": "BLOCKED_BY_LIVE_ENV_LOCKS", "blockers": ["live arming preflight recheck required"], "safety": dict(SAFETY)},
                "risk_contract": risk_contract,
                "binance_live_status": binance_status,
                "connector_status": connector_status,
                "protective_status": protective_status,
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )
    final_preflight = build_final_live_preflight(candidate_id=candidate_id, log_dir=resolved_log_dir, env=source_env)
    first_live_gate = build_first_live_activation_gate(
        candidate_id=candidate_id,
        log_dir=resolved_log_dir,
        env=source_env,
        record=False,
    )
    r126_gate = build_first_tiny_live_lane_execution_gate(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        record=False,
        config_path=config_path,
        env=source_env,
        risk_contract=risk_contract,
        global_gates=final_preflight,
        r106_gate=first_live_gate,
    )
    r130_authorization = build_first_tiny_live_autonomous_lane_authorization(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        record_authorization=False,
        config_path=config_path,
        controls=controls,
        r126_gate=r126_gate,
        risk_contract=risk_contract,
    )
    r131_rehearsal = build_live_lane_kill_switch_rehearsal(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        config_path=config_path,
    )
    r132_boundary = build_live_adapter_boundary_final_review(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        config_path=config_path,
        env=source_env,
    )
    r134_dry_authorization = build_first_tiny_live_order_payload_dry_authorization(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        record_dry_authorization=False,
        config_path=config_path,
        env=source_env,
        r126_gate=r126_gate,
        r130_authorization=r130_authorization,
        r131_rehearsal=r131_rehearsal,
        r132_boundary_review=r132_boundary,
        risk_contract=risk_contract,
    )
    r135_rehearsal = build_live_adapter_execution_rehearsal(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        record_rehearsal=False,
        env=source_env,
        dry_authorization=r134_dry_authorization,
        r132_boundary_review=r132_boundary,
    )
    r136_policy = build_protective_order_dry_policy_review(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        record_review=False,
        config_path=config_path,
        env=source_env,
        controls=controls,
        risk_contract=risk_contract,
        protective_readiness=protective_status,
        connector_status=connector_status,
        r132_boundary_review=r132_boundary,
        r134_dry_authorization=r134_dry_authorization,
        r135_rehearsal=r135_rehearsal,
    )
    r137_preview = build_protective_payload_dry_preview_boundary(
        log_dir=resolved_log_dir,
        lane_key=lane_key,
        record_preview=False,
        config_path=config_path,
        env=source_env,
        controls=controls,
        r136_policy_review=r136_policy,
        connector_status=connector_status,
        protective_status=protective_status,
    )
    return _sanitize(
        {
            "lane": lane or {},
            "lane_mode": str((lane or {}).get("mode") or "missing").strip().lower(),
            "fresh_signal_router": router,
            "paper_integration": paper_integration,
            "paper_integration_records_summary": _paper_integration_records_summary(
                _filter_lane_records(load_paper_executor_integration_records(log_dir=resolved_log_dir, limit=50), lane_key)
            ),
            "r126_tiny_live_gate": r126_gate,
            "r130_authorization": r130_authorization,
            "r130_authorization_records_summary": _authorization_records_summary(
                load_tiny_live_lane_authorization_records(log_dir=resolved_log_dir, lane_key=lane_key, limit=20)
            ),
            "r131_kill_switch_rehearsal": r131_rehearsal,
            "r132_adapter_boundary": r132_boundary,
            "r134_dry_authorization": r134_dry_authorization,
            "r135_adapter_rehearsal": r135_rehearsal,
            "r136_protective_policy": r136_policy,
            "r137_protective_preview": r137_preview,
            "final_live_preflight": final_preflight,
            "first_live_activation_gate": first_live_gate,
            "live_env_boundary": build_live_env_boundary_review(
                candidate_id=candidate_id,
                log_dir=resolved_log_dir,
                env=source_env,
            ),
            "live_arming_preflight": build_live_arming_preflight(
                candidate_id=candidate_id,
                log_dir=resolved_log_dir,
                env=source_env,
            ),
            "risk_contract": risk_contract,
            "binance_live_status": build_binance_live_status(env=source_env),
            "connector_status": connector_status,
            "protective_status": protective_status,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
    )


def build_blocker_inventory(*, source_statuses: Mapping[str, Any], lane_key: str = DEFAULT_LANE_KEY) -> list[dict[str, Any]]:
    command_pack = build_operator_burn_down_command_pack(lane_key=lane_key)
    blockers: list[dict[str, Any]] = []
    lane_mode = str(source_statuses.get("lane_mode") or _nested(source_statuses, "lane", "mode") or "missing").lower()
    if lane_mode != "tiny_live":
        blockers.append(
            _blocker(
                "LANE_MODE",
                "CRITICAL_BLOCKER",
                "Selected lane is not tiny_live",
                f"lane mode is {lane_mode}",
                "Tiny-live autonomous execution can only be reviewed for a selected tiny_live lane.",
                [],
                "lane_command_preview",
                command_pack["lane_control_status"],
                command_pack["first_tiny_live_autonomous_lane_authorization_preview"],
                None,
                "A non-tiny-live lane can only paper/shadow; treating it as live would bypass R124/R130 intent.",
                "Use R124/R130 path; R138 does not mutate lane config.",
            )
        )
    _add_source_blockers(blockers, source_statuses, command_pack, lane_key)
    blockers.extend(_safety_inventory(source_statuses, command_pack))
    return _assign_ids(_dedupe_blockers(blockers))


def rank_live_ready_blockers(blocker_inventory: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    category_rank = {
        "FRESH_SIGNAL": 0,
        "PAPER_PROOF": 1,
        "LANE_MODE": 2,
        "AUTHORIZATION": 3,
        "GLOBAL_GATE": 4,
        "KILL_SWITCH": 5,
        "ADAPTER_BOUNDARY": 6,
        "PROTECTIVE_POLICY": 7,
        "PROTECTIVE_PAYLOAD": 8,
        "CREDENTIAL_BOUNDARY": 9,
        "ENV_FLAGS": 10,
        "RISK_CONTRACT": 11,
        "EVIDENCE": 12,
        "UI_VISIBILITY": 13,
        "UNKNOWN": 14,
    }
    ranked = sorted(
        (dict(item) for item in blocker_inventory),
        key=lambda item: (
            SEVERITY_ORDER.get(str(item.get("severity")), 99),
            category_rank.get(str(item.get("category")), 99),
            str(item.get("title") or ""),
        ),
    )
    return _assign_ids(ranked)


def build_dependency_chain(*, ranked_blockers: list[Mapping[str, Any]] | None = None, lane_key: str = DEFAULT_LANE_KEY) -> list[dict[str, Any]]:
    present = {str(item.get("category")) for item in ranked_blockers or []}
    steps = [
        ("fresh_lane_router_check", "Fresh lane/router check.", "FRESH_SIGNAL", "fresh-signal-router-status"),
        ("paper_proof", "Record or verify recent autonomous paper proof via R129.", "PAPER_PROOF", "autonomous_paper_lane_executor_integration_preview"),
        ("tiny_live_lane_authorization", "Move or request lane toward tiny_live via R124/R130 path.", "LANE_MODE", "first_tiny_live_autonomous_lane_authorization_preview"),
        ("r126_gate", "Rerun R126 tiny-live gate.", "AUTHORIZATION", "first_tiny_live_lane_execution_gate"),
        ("kill_switch_rehearsal", "Rerun R131 kill-switch rehearsal.", "KILL_SWITCH", "live_lane_kill_switch_rehearsal"),
        ("adapter_boundary", "Rerun R132 adapter boundary.", "ADAPTER_BOUNDARY", "live_adapter_boundary_final_review"),
        ("protective_readiness", "Rerun R136/R137 protective policy and preview.", "PROTECTIVE_POLICY", "protective_order_dry_policy_review"),
        ("credential_evidence", "Provide credential presence evidence as booleans only.", "CREDENTIAL_BOUNDARY", "final-live-preflight"),
        ("global_preflights", "Rerun R102/R106/global preflights.", "GLOBAL_GATE", "first-live-activation-gate"),
        ("dry_authorization", "Rerun R134 dry authorization.", "AUTHORIZATION", "first_tiny_live_order_payload_dry_authorization"),
        ("future_adapter_review", "Future R139/R140 adapter final review.", "ADAPTER_BOUNDARY", "autonomous-lane-live-ready-burn-down"),
        ("future_execution_authorization", "Only later explicit execution authorization.", "UNKNOWN", "autonomous-lane-live-ready-burn-down"),
    ]
    command_pack = build_operator_burn_down_command_pack(lane_key=lane_key)
    return [
        {
            "step": idx,
            "id": step_id,
            "title": title,
            "category": category,
            "blocked_now": category in present,
            "safe_check_command": _command_for_mode(command_pack, command),
        }
        for idx, (step_id, title, category, command) in enumerate(steps, start=1)
    ]


def build_probability_ladder(*, ranked_blockers: list[Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    categories = {str(item.get("category")) for item in ranked_blockers or []}
    severity_counts = Counter(str(item.get("severity")) for item in ranked_blockers or [])
    current = max(1, 18 - severity_counts["CRITICAL_BLOCKER"] * 5 - severity_counts["HIGH_BLOCKER"] * 2)
    ladder_specs = [
        ("current_probability_pct", current, "Current state with all detected blockers."),
        ("after_paper_proof_pct", 30 if "PAPER_PROOF" in categories else 36, "After recent autonomous paper proof is recorded or verified."),
        ("after_tiny_live_lane_authorization_pct", 44, "After selected lane mode and R130 authorization evidence are aligned."),
        ("after_protective_readiness_pct", 56, "After R136/R137 protective policy and preview blockers are clear."),
        ("after_credentials_boundary_pct", 64, "After credential presence is evidenced as booleans only."),
        ("after_global_gate_readiness_pct", 72, "After R102/R106 and global preflights are rechecked."),
        ("after_adapter_boundary_pct", 81, "After adapter boundary and rehearsal are clear without executable behavior."),
        ("after_final_dry_authorization_pct", 88, "After R134 dry authorization is clear; still requires future explicit execution phase."),
    ]
    floor = 0
    ladder: list[dict[str, Any]] = []
    for label, estimate, note in ladder_specs:
        bounded = min(100, max(floor, int(estimate)))
        floor = bounded
        ladder.append({"id": label, "probability_pct": bounded, "basis": "heuristic_conservative", "operator_note": note})
    return ladder


def build_operator_burn_down_command_pack(*, lane_key: str = DEFAULT_LANE_KEY) -> dict[str, str]:
    quoted_lane = json.dumps(lane_key)
    return {
        "lane_control_status": _cmd("lane-control-status"),
        "fresh_signal_router_status": _cmd("fresh-signal-router-status"),
        "autonomous_paper_lane_executor_integration_preview": _cmd(
            f"autonomous-paper-lane-executor-integration --lane-key {quoted_lane}"
        ),
        "autonomous_paper_lane_executor_integration_record_template": _cmd(
            f"autonomous-paper-lane-executor-integration --lane-key {quoted_lane} "
            f"--record-paper --confirm-paper-integration {json.dumps(CONFIRM_PAPER_INTEGRATION_PHRASE)}"
        ),
        "lane_tiny_live_mode_preview": _cmd(
            f"lane-control-command --action request-tiny-live-mode --lane-key {quoted_lane} "
            "--mode tiny_live --request-tiny-live"
        ),
        "first_tiny_live_autonomous_lane_authorization_preview": _cmd(
            f"first-tiny-live-autonomous-lane-authorization --lane-key {quoted_lane} "
            "--request-lane-mode-tiny-live"
        ),
        "first_tiny_live_autonomous_lane_authorization_record_template": _cmd(
            f"first-tiny-live-autonomous-lane-authorization --lane-key {quoted_lane} "
            f"--record-authorization --confirm-tiny-live-authorization {json.dumps(CONFIRM_TINY_LIVE_AUTHORIZATION_PHRASE)}"
        ),
        "first_tiny_live_lane_execution_gate": _cmd(f"first-tiny-live-lane-execution-gate --lane-key {quoted_lane}"),
        "live_lane_kill_switch_rehearsal": _cmd(f"live-lane-kill-switch-rehearsal --lane-key {quoted_lane}"),
        "live_adapter_boundary_final_review": _cmd(f"live-adapter-boundary-final-review --lane-key {quoted_lane}"),
        "protective_order_dry_policy_review": _cmd(f"protective-order-dry-policy-review --lane-key {quoted_lane}"),
        "protective_payload_dry_preview_boundary": _cmd(f"protective-payload-dry-preview-boundary --lane-key {quoted_lane}"),
        "first_tiny_live_order_payload_dry_authorization": _cmd(
            f"first-tiny-live-order-payload-dry-authorization --lane-key {quoted_lane}"
        ),
        "final_live_preflight": _cmd("final-live-preflight"),
        "first_live_activation_gate": _cmd("first-live-activation-gate"),
        "autonomous_lane_live_ready_burn_down": _cmd(f"autonomous-lane-live-ready-burn-down --lane-key {quoted_lane}"),
    }


def append_live_ready_burn_down_record(record: Mapping[str, Any], *, log_dir: str | Path | None = None) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    path = live_ready_burn_down_records_path(resolved_log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "burn_down_id": str(record.get("burn_down_id") or f"r138_burn_down_{uuid4().hex}"),
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "lane_key": record.get("lane_key"),
            "live_ready_now": bool(record.get("live_ready_now")),
            "probability_ladder": list(record.get("probability_ladder") or []),
            "blocker_summary": record.get("blocker_summary") or {},
            "ranked_blockers": list(record.get("ranked_blockers") or []),
            "recommended_clear_order": list(record.get("recommended_clear_order") or []),
            "next_phase_recommendation": record.get("next_phase_recommendation") or {},
            "safety": record.get("safety") or dict(SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or []),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_live_ready_burn_down_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
    lane_key: str | None = None,
) -> list[dict[str, Any]]:
    path = live_ready_burn_down_records_path(get_log_dir(log_dir, use_env=True))
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
            records.append(_sanitize(record))
    if limit > 0:
        return list(reversed(records))[:limit]
    return records


def summarize_live_ready_burn_down_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    lane_counts = Counter(str(record.get("lane_key") or "UNKNOWN") for record in records)
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "last_burn_down_id": records[-1].get("burn_down_id") if records else None,
        "safety": dict(SAFETY),
    }


def build_autonomous_lane_live_ready_burn_down_cli_payload(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    record_burn_down: bool = False,
    confirm_burn_down: str | None = None,
) -> dict[str, Any]:
    payload = build_autonomous_lane_live_ready_burn_down(log_dir=log_dir, lane_key=lane_key)
    if not record_burn_down:
        return payload
    if confirm_burn_down != CONFIRM_BURN_DOWN_RECORDING_PHRASE:
        return _sanitize(
            {
                **payload,
                "status": LIVE_READY_BURN_DOWN_REJECTED,
                "record_burn_down_requested": True,
                "confirmation_valid": False,
                "ledger_written": False,
                "recording_blockers": ["exact R138 burn-down recording confirmation phrase is required"],
                "safety": dict(SAFETY),
            }
        )
    if payload.get("status") not in {LIVE_READY_BURN_DOWN_READY, LIVE_READY_BURN_DOWN_BLOCKED}:
        return _sanitize(
            {
                **payload,
                "record_burn_down_requested": True,
                "confirmation_valid": True,
                "ledger_written": False,
                "recording_blockers": ["burn-down report is not safe to record"],
                "safety": dict(SAFETY),
            }
        )
    record = append_live_ready_burn_down_record(payload, log_dir=log_dir)
    return _sanitize(
        {
            **payload,
            "record_burn_down_requested": True,
            "confirmation_valid": True,
            "ledger_written": True,
            "burn_down_id": record["burn_down_id"],
            "ledger_path": str(live_ready_burn_down_records_path(get_log_dir(log_dir, use_env=True))),
        }
    )


def format_autonomous_lane_live_ready_burn_down_json(payload: Mapping[str, Any]) -> str:
    compact = {
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at"),
        "lane_key": payload.get("lane_key"),
        "live_ready_now": bool(payload.get("live_ready_now")),
        "tiny_live_today_probability_pct": payload.get("tiny_live_today_probability_pct"),
        "tiny_live_next_session_probability_pct": payload.get("tiny_live_next_session_probability_pct"),
        "blocker_summary": payload.get("blocker_summary") or {},
        "ranked_blockers": list(payload.get("ranked_blockers") or []),
        "dependency_chain": list(payload.get("dependency_chain") or []),
        "probability_ladder": list(payload.get("probability_ladder") or []),
        "recommended_clear_order": list(payload.get("recommended_clear_order") or []),
        "operator_command_pack": payload.get("operator_command_pack") or {},
        "next_phase_recommendation": payload.get("next_phase_recommendation") or {},
        "record_burn_down_requested": bool(payload.get("record_burn_down_requested", False)),
        "confirmation_valid": bool(payload.get("confirmation_valid", False)),
        "ledger_written": bool(payload.get("ledger_written", False)),
        "burn_down_id": payload.get("burn_down_id"),
        "recording_blockers": list(payload.get("recording_blockers") or []),
        "safety": payload.get("safety") or dict(SAFETY),
        "source_surfaces_used": list(payload.get("source_surfaces_used") or []),
    }
    return json.dumps(_sanitize(compact), sort_keys=True, separators=(",", ":"))


def live_ready_burn_down_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def _add_source_blockers(
    blockers: list[dict[str, Any]],
    source_statuses: Mapping[str, Any],
    command_pack: Mapping[str, str],
    lane_key: str,
) -> None:
    router = _mapping(source_statuses.get("fresh_signal_router"))
    routed_count = int(router.get("routed_count") or 0)
    if routed_count <= 0 and not _has_routed_candidate(router, lane_key):
        blockers.append(
            _blocker("FRESH_SIGNAL", "HIGH_BLOCKER", "No fresh routed candidate", _status(router), "R126/R129 need a fresh routed candidate for the selected lane.", [], "read_only_recheck", command_pack["fresh_signal_router_status"], None, None, "Without a fresh candidate, paper proof and tiny-live review may be stale.", "Wait for a fresh signal or rerun the router after signal refresh.")
        )

    paper = _mapping(source_statuses.get("paper_integration"))
    paper_records = _mapping(source_statuses.get("paper_integration_records_summary"))
    r126 = _mapping(source_statuses.get("r126_tiny_live_gate"))
    if not _paper_proof_present(paper, paper_records, r126):
        blockers.append(
            _blocker("PAPER_PROOF", "CRITICAL_BLOCKER", "Recent autonomous paper proof missing", _status(paper), "The autonomous lane needs recent R125/R129 paper evidence before tiny-live review.", ["fresh_lane_router_check"], "operator_evidence_recording", command_pack["autonomous_paper_lane_executor_integration_preview"], command_pack["autonomous_paper_lane_executor_integration_record_template"], None, "Skipping paper proof would remove the last non-executing evidence layer before live review.", "Record paper-only proof with the exact R129 phrase when a routed candidate exists.")
        )

    if _status(r126) != TINY_LIVE_EXECUTION_READY:
        for text in _source_blocker_texts(r126):
            blockers.append(_from_text(text, "r126_tiny_live_gate", command_pack["first_tiny_live_lane_execution_gate"], lane_key))
        blockers.append(
            _blocker("AUTHORIZATION", "HIGH_BLOCKER", "R126 tiny-live gate blocked", _status(r126), "R126 is the lane-level tiny-live review packet before later dry authorization.", ["paper_proof", "tiny_live_lane_authorization"], "read_only_recheck", command_pack["first_tiny_live_lane_execution_gate"], None, None, "Skipping R126 would bypass the lane/global gate composition.", "Clear upstream blockers and rerun R126.")
        )

    auth = _mapping(source_statuses.get("r130_authorization"))
    auth_records = _mapping(source_statuses.get("r130_authorization_records_summary"))
    if _status(auth) != TINY_LIVE_AUTHORIZATION_RECORDED and auth_records.get("recorded_count", 0) <= 0:
        blockers.append(
            _blocker("AUTHORIZATION", "CRITICAL_BLOCKER", "Tiny-live authorization missing or blocked", _status(auth), "R130 records operator lane authorization intent only; R138 cannot replace it.", ["paper_proof", "r126_gate"], "operator_evidence_recording", command_pack["first_tiny_live_autonomous_lane_authorization_preview"], command_pack["first_tiny_live_autonomous_lane_authorization_record_template"], None, "Skipping R130 would treat diagnostics as authorization.", "Record R130 intent only after R126/paper prerequisites are clear.")
        )

    kill = _mapping(source_statuses.get("r131_kill_switch_rehearsal"))
    if _status(kill) != KILL_SWITCH_REHEARSAL_READY:
        blockers.append(
            _blocker("KILL_SWITCH", "HIGH_BLOCKER", "Kill-switch rehearsal not ready", _status(kill), "The lane must prove kill-switch and rollback paths before tiny-live execution can be considered.", ["r126_gate"], "read_only_recheck", command_pack["live_lane_kill_switch_rehearsal"], None, None, "Skipping this weakens operator rollback confidence.", "Rerun R131 and record evidence only when its exact phrase is used.")
        )

    adapter = _mapping(source_statuses.get("r132_adapter_boundary"))
    if _status(adapter) != LIVE_ADAPTER_BOUNDARY_REVIEW_READY or _source_blocker_texts(adapter):
        blockers.append(
            _blocker("ADAPTER_BOUNDARY", "HIGH_BLOCKER", "Live adapter boundary not clear", _status(adapter), "Adapter review must remain non-executing while proving no forbidden functions were called.", ["kill_switch_rehearsal"], "read_only_recheck", command_pack["live_adapter_boundary_final_review"], None, None, "Skipping adapter boundary review risks confusing diagnostics with executable adapter behavior.", "Rerun R132 after upstream blockers clear.")
        )

    _add_global_blockers(blockers, source_statuses, command_pack)
    _add_credential_blockers(blockers, source_statuses, command_pack)
    _add_protective_blockers(blockers, source_statuses, command_pack)

    dry_auth = _mapping(source_statuses.get("r134_dry_authorization"))
    if _status(dry_auth) != DRY_AUTHORIZATION_READY:
        blockers.append(
            _blocker("AUTHORIZATION", "MEDIUM_BLOCKER", "Order payload dry authorization blocked", _status(dry_auth), "R134 must be clear before future dry payload review, but it still cannot create executable payloads.", ["adapter_boundary", "protective_readiness"], "read_only_recheck", command_pack["first_tiny_live_order_payload_dry_authorization"], None, None, "Skipping dry authorization loses the non-executing review boundary.", "Rerun R134 only as preview until prerequisites are clear.")
        )
    rehearsal = _mapping(source_statuses.get("r135_adapter_rehearsal"))
    if _status(rehearsal) != LIVE_ADAPTER_REHEARSAL_READY_FOR_FUTURE_IMPLEMENTATION:
        blockers.append(
            _blocker("ADAPTER_BOUNDARY", "MEDIUM_BLOCKER", "Live adapter rehearsal not ready", _status(rehearsal), "R135 rehearses the adapter boundary without executable payloads.", ["dry_authorization"], "read_only_recheck", command_pack["live_adapter_boundary_final_review"], None, "R139/R140", "Skipping rehearsal can hide adapter boundary gaps.", "Keep this for future review after R134/R136/R137 are clear.")
        )


def _add_global_blockers(blockers: list[dict[str, Any]], source_statuses: Mapping[str, Any], command_pack: Mapping[str, str]) -> None:
    final = _mapping(source_statuses.get("final_live_preflight"))
    first = _mapping(source_statuses.get("first_live_activation_gate"))
    env_boundary = _mapping(source_statuses.get("live_env_boundary"))
    arming = _mapping(source_statuses.get("live_arming_preflight"))
    connector = _mapping(source_statuses.get("connector_status"))
    if _status(first) != FIRST_LIVE_ACTIVATION_READY:
        blockers.append(_blocker("GLOBAL_GATE", "CRITICAL_BLOCKER", "R106/global first-live activation gate blocked", _status(first), "R106 remains the global non-executing authority before future live execution.", ["global_preflights"], "read_only_recheck", command_pack["first_live_activation_gate"], None, None, "Skipping R106 bypasses global gates.", "Rerun R102/R106 after lane blockers clear."))
    if _status(final) != READY:
        blockers.append(_blocker("GLOBAL_GATE", "HIGH_BLOCKER", "Final preflight recheck required", _status(final), "R102 composes the global final live preflight.", ["credential_evidence", "protective_readiness"], "read_only_recheck", command_pack["final_live_preflight"], None, None, "Skipping R102 hides global env, credential, and protective blockers.", "Rerun final-live-preflight after source evidence changes."))
    if env_boundary.get("boundary_status") != LIVE_ENV_LOCKED_SAFE:
        blockers.append(_blocker("ENV_FLAGS", "HIGH_BLOCKER", "Live env boundary recheck required", str(env_boundary.get("boundary_status") or "UNKNOWN"), "Env boundary must be reviewed without mutating env files.", ["global_preflights"], "read_only_recheck", command_pack["final_live_preflight"], None, None, "Skipping env boundary review can hide unsafe live flags.", "Use R102/R87 read-only checks; R138 cannot edit env."))
    if str(arming.get("final_preflight_status") or "").startswith("BLOCKED"):
        blockers.append(_blocker("GLOBAL_GATE", "HIGH_BLOCKER", "Live arming preflight recheck required", str(arming.get("final_preflight_status") or "UNKNOWN"), "Live arming preflight remains a prerequisite review surface.", ["global_preflights"], "read_only_recheck", command_pack["final_live_preflight"], None, None, "Skipping arming preflight bypasses risk/funding/operator review.", "Rerun the arming preflight through final-live-preflight."))
    if connector.get("global_kill_switch") is not False:
        blockers.append(_blocker("KILL_SWITCH", "CRITICAL_BLOCKER", "Global kill switch active", "global_kill_switch=true", "Kill switch must remain explicit and reviewed before any future execution phase.", ["kill_switch_rehearsal"], "config_env_future_only", command_pack["final_live_preflight"], None, "future explicit arming phase", "Disabling it here would violate R138 safety.", "R138 reports only; do not change kill-switch state here."))
    if connector.get("live_execution_enabled") is not True:
        blockers.append(_blocker("ENV_FLAGS", "CRITICAL_BLOCKER", "Live execution disabled", "live_execution_enabled=false", "Live execution flags are intentionally disabled outside future authorized arming.", ["global_preflights"], "config_env_future_only", command_pack["final_live_preflight"], None, "future explicit arming phase", "Changing live flags in R138 would bypass global gates.", "Keep disabled; record as blocker."))
    if connector.get("allow_live_orders") is not True:
        blockers.append(_blocker("ENV_FLAGS", "CRITICAL_BLOCKER", "Live orders disabled", "allow_live_orders=false", "Live order placement remains disabled until a future explicitly authorized phase.", ["global_preflights"], "config_env_future_only", command_pack["final_live_preflight"], None, "future explicit execution phase", "Enabling orders here would violate R138.", "Keep disabled; record as blocker."))
    if str(connector.get("connector_mode") or "") == "DRY_RUN_ONLY":
        blockers.append(_blocker("ADAPTER_BOUNDARY", "HIGH_BLOCKER", "Connector mode DRY_RUN_ONLY", "connector_mode=DRY_RUN_ONLY", "The connector is deliberately non-executing.", ["adapter_boundary"], "future_phase_required", command_pack["live_adapter_boundary_final_review"], None, "R139/R140", "Changing connector mode here would create execution risk.", "Leave dry-run-only in R138."))
    if connector.get("live_order_adapter_configured") is not True:
        blockers.append(_blocker("ADAPTER_BOUNDARY", "HIGH_BLOCKER", "Live adapter not configured", "live_order_adapter_configured=false", "A future adapter review must explicitly configure execution behavior; R138 cannot.", ["adapter_boundary"], "future_phase_required", command_pack["live_adapter_boundary_final_review"], None, "R139/R140", "Pretending adapter readiness could lead to fake live readiness.", "Keep as future-phase blocker."))


def _add_credential_blockers(blockers: list[dict[str, Any]], source_statuses: Mapping[str, Any], command_pack: Mapping[str, str]) -> None:
    binance = _mapping(source_statuses.get("binance_live_status"))
    connector = _mapping(source_statuses.get("connector_status"))
    if not bool(binance.get("api_key_present") or connector.get("api_key_present")):
        blockers.append(_blocker("CREDENTIAL_BOUNDARY", "HIGH_BLOCKER", "Binance API key missing", "api_key_present=false", "Credential presence must be evidenced as a boolean only before future live review.", ["credential_evidence"], "config_env_future_only", command_pack["final_live_preflight"], None, "operator-managed private env setup", "Printing or editing credentials here would violate secret handling.", "Provide presence evidence only; never print values."))
    if not bool(binance.get("api_secret_present") or connector.get("api_secret_present")):
        blockers.append(_blocker("CREDENTIAL_BOUNDARY", "HIGH_BLOCKER", "Binance API secret missing", "api_secret_present=false", "Secret presence must be evidenced as a boolean only before future live review.", ["credential_evidence"], "config_env_future_only", command_pack["final_live_preflight"], None, "operator-managed private env setup", "Printing or editing secrets here would violate secret handling.", "Provide presence evidence only; never print values."))
    blockers.append(_blocker("CREDENTIAL_BOUNDARY", "INFO", "Signed request forbidden until future phase", "signed_request_created=false", "R138 cannot create signed request material.", ["future_execution_authorization"], "future_phase_required", command_pack["live_adapter_boundary_final_review"], None, "future explicit execution phase", "Creating signatures in R138 would cross the exchange boundary.", "Keep this as an informational hard boundary."))


def _add_protective_blockers(blockers: list[dict[str, Any]], source_statuses: Mapping[str, Any], command_pack: Mapping[str, str]) -> None:
    protective = _mapping(source_statuses.get("protective_status"))
    policy = _mapping(source_statuses.get("r136_protective_policy"))
    preview = _mapping(source_statuses.get("r137_protective_preview"))
    if protective.get("protective_orders_enabled") is not True:
        blockers.append(_blocker("PROTECTIVE_POLICY", "HIGH_BLOCKER", "Protective orders disabled", "protective_orders_enabled=false", "A future live entry must not proceed without protective stop/take-profit readiness.", ["protective_readiness"], "config_env_future_only", command_pack["protective_order_dry_policy_review"], None, "future explicit protective arming phase", "Skipping protective readiness risks naked entry.", "R138 does not enable protective orders."))
    if str(protective.get("protective_order_mode") or "UNKNOWN") == "PREVIEW_ONLY":
        blockers.append(_blocker("PROTECTIVE_PAYLOAD", "MEDIUM_BLOCKER", "Protective mode PREVIEW_ONLY", "protective_order_mode=PREVIEW_ONLY", "Preview-only mode is safe but not executable readiness.", ["protective_readiness"], "future_phase_required", command_pack["protective_payload_dry_preview_boundary"], None, "future explicit protective execution phase", "Changing mode here would cross R138 safety.", "Keep preview-only during R138."))
    if protective.get("protective_stop_supported") is not True:
        blockers.append(_blocker("PROTECTIVE_POLICY", "HIGH_BLOCKER", "Stop policy not ready", "protective_stop_supported=false", "Stop-loss policy must be ready before any future live entry.", ["protective_readiness"], "read_only_recheck", command_pack["protective_order_dry_policy_review"], None, None, "Skipping stop readiness creates naked downside risk.", "Rerun R136 after upstream prerequisites clear."))
    if protective.get("protective_take_profit_supported") is not True:
        blockers.append(_blocker("PROTECTIVE_POLICY", "MEDIUM_BLOCKER", "Take-profit policy not ready", "protective_take_profit_supported=false", "Take-profit readiness must be explicit for the protected tiny-live path.", ["protective_readiness"], "read_only_recheck", command_pack["protective_order_dry_policy_review"], None, None, "Skipping take-profit readiness weakens the protected protocol.", "Rerun R136 after upstream prerequisites clear."))
    if _status(policy) != PROTECTIVE_POLICY_READY_FOR_DRY_PAYLOAD_PREVIEW:
        blockers.append(_blocker("PROTECTIVE_POLICY", "HIGH_BLOCKER", "Protective dry policy not ready", _status(policy), "R136 must clear protective policy before R137 preview boundary can be trusted.", ["adapter_boundary"], "read_only_recheck", command_pack["protective_order_dry_policy_review"], None, None, "Skipping R136 duplicates or bypasses protective policy review.", "Clear R136 blockers through existing surfaces."))
    if _status(preview) != PROTECTIVE_PAYLOAD_READY_FOR_FUTURE_DRY_RUN:
        blockers.append(_blocker("PROTECTIVE_PAYLOAD", "HIGH_BLOCKER", "Protective dry payload not ready", _status(preview), "R137 must prove the dry preview boundary without creating protective payloads.", ["protective_readiness"], "read_only_recheck", command_pack["protective_payload_dry_preview_boundary"], None, None, "Skipping R137 hides protective preview-boundary issues.", "Rerun R137 as preview only."))


def _safety_inventory(source_statuses: Mapping[str, Any], command_pack: Mapping[str, str]) -> list[dict[str, Any]]:
    unsafe: list[dict[str, Any]] = []
    for surface, payload in source_statuses.items():
        safety = _mapping(_mapping(payload).get("safety"))
        for key in BLOCKING_SAFETY_KEYS:
            if safety.get(key) is True:
                unsafe.append(_blocker("UNKNOWN", "CRITICAL_BLOCKER", f"Paper/live separation violation: {key}", f"{surface}.{key}=true", "Any true execution safety flag blocks R138 live-readiness reporting.", [], "cannot_clear_here", command_pack["autonomous_lane_live_ready_burn_down"], None, None, "Ignoring true safety flags could hide accidental execution.", "Stop and inspect the source surface."))
        if safety and safety.get("paper_live_separation_intact") is False:
            unsafe.append(_blocker("UNKNOWN", "CRITICAL_BLOCKER", "Paper/live separation violation", f"{surface}.paper_live_separation_intact=false", "Paper/live separation must remain intact.", [], "cannot_clear_here", command_pack["autonomous_lane_live_ready_burn_down"], None, None, "Skipping this would violate the core safety invariant.", "Stop and inspect source safety."))
    return unsafe


def _from_text(text: str, source: str, command: str, lane_key: str) -> dict[str, Any]:
    lower = text.lower()
    if "paper proof" in lower or "paper execution" in lower:
        category, severity, mode = "PAPER_PROOF", "CRITICAL_BLOCKER", "operator_evidence_recording"
    elif "lane mode" in lower or "tiny_live" in lower:
        category, severity, mode = "LANE_MODE", "CRITICAL_BLOCKER", "lane_command_preview"
    elif "r106" in lower or "global" in lower or "final live preflight" in lower:
        category, severity, mode = "GLOBAL_GATE", "HIGH_BLOCKER", "read_only_recheck"
    elif "kill switch" in lower:
        category, severity, mode = "KILL_SWITCH", "HIGH_BLOCKER", "read_only_recheck"
    elif "credential" in lower or "api key" in lower or "api secret" in lower:
        category, severity, mode = "CREDENTIAL_BOUNDARY", "HIGH_BLOCKER", "config_env_future_only"
    elif "protective" in lower or "stop" in lower or "take-profit" in lower:
        category, severity, mode = "PROTECTIVE_POLICY", "HIGH_BLOCKER", "read_only_recheck"
    elif "fresh" in lower or "candidate" in lower:
        category, severity, mode = "FRESH_SIGNAL", "HIGH_BLOCKER", "read_only_recheck"
    elif "risk contract" in lower:
        category, severity, mode = "RISK_CONTRACT", "HIGH_BLOCKER", "read_only_recheck"
    else:
        category, severity, mode = "UNKNOWN", "MEDIUM_BLOCKER", "read_only_recheck"
    return _blocker(
        category,
        severity,
        text[:96],
        f"{source}: {text}",
        "Existing source surface reports this as a blocker for tiny-live readiness.",
        [],
        mode,
        command,
        None,
        None if mode != "future_phase_required" else "future explicit phase",
        "Skipping source blockers would duplicate or bypass existing readiness logic.",
        f"Clear through the source surface for lane {lane_key}.",
    )


def _blocker(
    category: str,
    severity: str,
    title: str,
    current_status: str,
    why_it_blocks_live: str,
    depends_on: list[str],
    clearing_mode: str,
    safe_check_command: str,
    safe_next_action_command: str | None,
    future_phase_required: str | None,
    risk_if_skipped: str,
    operator_note: str,
) -> dict[str, Any]:
    return {
        "id": "",
        "category": category if category in BLOCKER_CATEGORIES else "UNKNOWN",
        "severity": severity if severity in SEVERITY_ORDER else "INFO",
        "title": title,
        "current_status": current_status,
        "why_it_blocks_live": why_it_blocks_live,
        "depends_on": list(depends_on),
        "clearing_mode": clearing_mode,
        "safe_check_command": safe_check_command,
        "safe_next_action_command": safe_next_action_command,
        "future_phase_required": future_phase_required,
        "risk_if_skipped": risk_if_skipped,
        "operator_note": operator_note,
    }


def _blocker_summary(blockers: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "critical_count": sum(1 for item in blockers if item.get("severity") == "CRITICAL_BLOCKER"),
        "high_count": sum(1 for item in blockers if item.get("severity") == "HIGH_BLOCKER"),
        "medium_count": sum(1 for item in blockers if item.get("severity") == "MEDIUM_BLOCKER"),
        "low_count": sum(1 for item in blockers if item.get("severity") == "LOW_BLOCKER"),
        "evidence_count": sum(1 for item in blockers if item.get("clearing_mode") == "operator_evidence_recording"),
        "future_phase_count": sum(1 for item in blockers if item.get("future_phase_required")),
    }


def _assign_ids(blockers: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for index, blocker in enumerate(blockers, start=1):
        row = dict(blocker)
        row["id"] = f"B{index:03d}"
        result.append(row)
    return result


def _dedupe_blockers(blockers: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for blocker in blockers:
        key = (str(blocker.get("category")), str(blocker.get("title")))
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(blocker))
    return result


def _source_blocker_texts(payload: Mapping[str, Any]) -> list[str]:
    texts: list[str] = []
    for key in ("blockers", "main_blockers", "current_blockers"):
        texts.extend(str(item) for item in payload.get(key) or [] if item)
    prerequisites = payload.get("prerequisites") if isinstance(payload.get("prerequisites"), Mapping) else {}
    texts.extend(str(item) for item in prerequisites.get("blockers") or [] if item)
    return _dedupe(texts)


def _paper_proof_present(paper: Mapping[str, Any], paper_records: Mapping[str, Any], r126: Mapping[str, Any]) -> bool:
    if paper_records.get("recorded_count", 0) > 0:
        return True
    proof = r126.get("paper_proof") if isinstance(r126.get("paper_proof"), Mapping) else {}
    if proof.get("matched") is True:
        return True
    return bool(paper.get("recorded_count", 0) or paper.get("paper_records_written", 0))


def _paper_integration_records_summary(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "recorded_count": len(records),
        "latest_status": records[0].get("status") if records else "MISSING",
        "latest_recorded_at_utc": records[0].get("recorded_at_utc") if records else None,
    }


def _authorization_records_summary(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "recorded_count": len(records),
        "latest_status": records[0].get("authorization_status") or records[0].get("status") if records else "MISSING",
        "latest_recorded_at_utc": records[0].get("recorded_at_utc") if records else None,
    }


def _filter_lane_records(records: list[Mapping[str, Any]], lane_key: str) -> list[Mapping[str, Any]]:
    return [record for record in records if str(record.get("lane_key") or "") == lane_key]


def _deferred_status(reason: str) -> dict[str, Any]:
    return {
        "evaluation_status": reason,
        "source_note": "R138 deferred deeper evaluation until the selected lane clears the tiny_live prerequisite.",
        "safety": dict(SAFETY),
    }


def _live_ready_now(source_statuses: Mapping[str, Any], ranked: list[Mapping[str, Any]]) -> bool:
    if any(item.get("severity") != "INFO" for item in ranked):
        return False
    return (
        _status(_mapping(source_statuses.get("r126_tiny_live_gate"))) == TINY_LIVE_EXECUTION_READY
        and _status(_mapping(source_statuses.get("first_live_activation_gate"))) == FIRST_LIVE_ACTIVATION_READY
        and _status(_mapping(source_statuses.get("final_live_preflight"))) == READY
    )


def _source_surfaces(source_statuses: Mapping[str, Any]) -> list[str]:
    surfaces = list(SOURCE_SURFACES_USED)
    surfaces.extend(str(item) for item in source_statuses.get("source_surfaces_used") or [])
    return _dedupe(surfaces)


def _has_routed_candidate(router: Mapping[str, Any], lane_key: str) -> bool:
    for row in router.get("routed_candidates") or router.get("routed") or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("route_status") == ROUTED_TO_LANE and (not lane_key or row.get("lane_key") == lane_key):
            return True
    return False


def _find_lane(controls: Mapping[str, Any], lane_key: str) -> dict[str, Any] | None:
    lane = (controls.get("lane_map") or {}).get(lane_key)
    return dict(lane) if isinstance(lane, Mapping) else None


def _command_for_mode(command_pack: Mapping[str, str], mode: str) -> str:
    normalized = mode.replace("-", "_")
    return command_pack.get(normalized) or command_pack.get(mode) or command_pack["autonomous_lane_live_ready_burn_down"]


def _cmd(command: str) -> str:
    return f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward {command}"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _nested(payload: Mapping[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _status(payload: Mapping[str, Any]) -> str:
    return str(
        payload.get("status")
        or payload.get("readiness")
        or payload.get("boundary_status")
        or payload.get("final_preflight_status")
        or "UNKNOWN"
    )


def _safety_clean(safety: Mapping[str, Any]) -> bool:
    return all(safety.get(key) is False for key in BLOCKING_SAFETY_KEYS) and safety.get("paper_live_separation_intact") is True


def _dedupe(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        if value in (None, ""):
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(secret_key in lowered for secret_key in ("secret", "api_key", "signature", "token")):
                if lowered.endswith("_present") or lowered in {"api_key_present", "api_secret_present", "secrets_shown", "signed_request_created"}:
                    sanitized[key] = item
                else:
                    sanitized[key] = "<hidden>"
                continue
            sanitized[key] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
