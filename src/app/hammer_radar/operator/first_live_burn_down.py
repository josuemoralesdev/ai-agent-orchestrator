"""R110 first-live readiness burn-down pack.

This module composes the R102-R109 readiness surfaces into a prioritized
operator checklist for the next live-readiness push. It is diagnostic only:
it never enables live execution, places orders, signs payloads, calls Binance
order endpoints, or changes environment flags.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_activation_gate import (
    FIRST_LIVE_ACTIVATION_READY,
    build_first_live_activation_gate,
    load_first_live_activation_gate_checks,
)
from src.app.hammer_radar.operator.first_live_operator_approval_cockpit import (
    build_operator_approval_cockpit_state,
    load_operator_approval_cockpit_intents,
)
from src.app.hammer_radar.operator.one_tiny_live_order_protocol import (
    CONFIRMATION_PHRASE_TEMPLATE,
    build_one_tiny_live_order_protocol_check,
    load_one_tiny_live_order_protocol_checks,
)
from src.app.hammer_radar.operator.tiny_live_armed_dry_run import (
    build_tiny_live_armed_dry_run,
    load_tiny_live_armed_dry_runs,
)
from src.app.hammer_radar.operator.tiny_live_risk_contract import DEFAULT_CANDIDATE_ID

STATUS = "BURN_DOWN_READY"
EVENT_TYPE = "FIRST_LIVE_BURN_DOWN_REPORT"
REPORTS_FILENAME = "first_live_burn_down_reports.ndjson"
SOURCE_SURFACE = "operator.first_live_burn_down.build_first_live_burn_down"

GROUP_ORDER = [
    "candidate_blockers",
    "approval_record_blockers",
    "environment_flag_blockers",
    "binance_credential_blockers",
    "account_funding_blockers",
    "protective_order_blockers",
    "adapter_blockers",
    "strategy_quality_blockers",
    "telegram_blockers",
    "confirmation_phrase_blockers",
    "unknown_or_manual_check_blockers",
]


def _cmd(command: str) -> str:
    return f"PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect --log-dir logs/hammer_radar_forward {command}"


GROUP_META = {
    "candidate_blockers": {
        "owner": "MARKET",
        "can_clear_tomorrow": True,
        "next_action": "Wait for, identify, or regenerate a fresh promoted candidate before re-running the readiness chain.",
        "verification_command": _cmd("final-live-preflight"),
        "related_phase": "R102/R106",
    },
    "approval_record_blockers": {
        "owner": "OPERATOR",
        "can_clear_tomorrow": True,
        "next_action": "Record and verify the final approval intent plus required human review records for the same candidate and hashes.",
        "verification_command": _cmd("tiny-live-armed-dry-run"),
        "related_phase": "R103/R104/R106",
    },
    "environment_flag_blockers": {
        "owner": "CONFIG",
        "can_clear_tomorrow": True,
        "next_action": "Review live env and kill-switch state without editing flags in R110; only a later authorized phase may change live flags.",
        "verification_command": _cmd("final-live-preflight"),
        "related_phase": "R102/R106",
    },
    "binance_credential_blockers": {
        "owner": "CONFIG",
        "can_clear_tomorrow": True,
        "next_action": "Configure Binance credential presence safely in private operator-managed env, reporting booleans only and never values.",
        "verification_command": _cmd("final-live-preflight"),
        "related_phase": "R102/R106",
    },
    "account_funding_blockers": {
        "owner": "EXCHANGE",
        "can_clear_tomorrow": True,
        "next_action": "Verify account funding, conflicting positions, and margin readiness through an explicitly safe read-only operator procedure.",
        "verification_command": _cmd("first-live-activation-gate"),
        "related_phase": "R106/R111",
    },
    "protective_order_blockers": {
        "owner": "CODE",
        "can_clear_tomorrow": True,
        "next_action": "Verify protective stop and take-profit readiness before any future activation-ready decision.",
        "verification_command": _cmd("one-tiny-live-order-protocol"),
        "related_phase": "R105/R106",
    },
    "adapter_blockers": {
        "owner": "CODE",
        "can_clear_tomorrow": True,
        "next_action": "Verify the live adapter boundary and keep it non-executing unless a later explicit phase authorizes execution.",
        "verification_command": _cmd("first-live-activation-gate"),
        "related_phase": "R105/R106",
    },
    "strategy_quality_blockers": {
        "owner": "MARKET",
        "can_clear_tomorrow": True,
        "next_action": "Confirm the promoted setup quality, freshness, and hash consistency before clearing approval records.",
        "verification_command": _cmd("final-live-preflight"),
        "related_phase": "R102/R106",
    },
    "telegram_blockers": {
        "owner": "OPERATOR",
        "can_clear_tomorrow": True,
        "next_action": "Verify Telegram final approval intent exists as audit input only; do not wire it to execution.",
        "verification_command": _cmd("tiny-live-armed-dry-run"),
        "related_phase": "R103/R104",
    },
    "confirmation_phrase_blockers": {
        "owner": "OPERATOR",
        "can_clear_tomorrow": True,
        "next_action": "Prepare the exact future confirmation phrase record, but do not treat it as execution authority in R110.",
        "verification_command": _cmd("first-live-activation-gate"),
        "related_phase": "R105/R106",
    },
    "unknown_or_manual_check_blockers": {
        "owner": "UNKNOWN",
        "can_clear_tomorrow": False,
        "next_action": "Keep manual unknowns blocked until R111 converts each one into an auditable prerequisite-clearing check.",
        "verification_command": _cmd("first-live-burn-down"),
        "related_phase": "R110/R111",
    },
}


def build_first_live_burn_down(
    *,
    candidate_id: str = DEFAULT_CANDIDATE_ID,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    record: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)

    surfaces = _load_latest_surfaces(candidate_id=candidate_id, log_dir=resolved_log_dir, env=env)
    dry_run = surfaces["dry_run"]
    protocol = surfaces["protocol"]
    activation_gate = surfaces["activation_gate"]
    cockpit = surfaces["cockpit"]

    blocker_groups = _blocker_groups(dry_run=dry_run, protocol=protocol, activation_gate=activation_gate, cockpit=cockpit)
    gate_chain = {
        "final_preflight_status": cockpit.get("final_preflight_status"),
        "tiny_live_armed_dry_run_status": cockpit.get("tiny_live_armed_dry_run_status"),
        "protocol_status": cockpit.get("protocol_status"),
        "first_live_activation_gate_status": cockpit.get("first_live_activation_gate_status"),
        "cockpit_status": cockpit.get("status"),
        "sacred_button_state": cockpit.get("sacred_button_state") or {},
    }
    source_surfaces = _source_surfaces(cockpit=cockpit)
    checked_at = datetime.now(UTC).isoformat()
    report = {
        "event_type": EVENT_TYPE,
        "report_id": uuid4().hex,
        "status": STATUS,
        "checked_at_utc": checked_at,
        "recorded_at_utc": checked_at,
        "live_ready": False,
        "execution_enabled_by_burn_down": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "candidate_id": candidate_id,
        "current_gate_chain": gate_chain,
        "blocker_groups": blocker_groups,
        "priority_burn_down": _priority_burn_down(),
        "morning_command_pack": _morning_command_pack(),
        "human_checklist": _human_checklist(),
        "readiness_path": [
            "BLOCKED",
            "READY",
            "READY_FOR_DRY_RUN",
            "PROTOCOL_PREREQS_READY",
            "FIRST_LIVE_ACTIVATION_READY",
            "future explicit execution authorization",
        ],
        "next_phase_recommendation": {
            "phase": "R111",
            "title": "first-live activation prerequisite clearing",
            "scope": "Clear prerequisites only: approval records, environment review, protective readiness, candidate freshness, account/funding verification, final preflight consistency, and sacred button state review.",
            "not_order_placement": True,
        },
        "ledger_path": str(first_live_burn_down_reports_path(resolved_log_dir)),
        "source_surfaces_used": source_surfaces,
        "source_statuses": {
            "R102": cockpit.get("final_preflight_status"),
            "R104": cockpit.get("tiny_live_armed_dry_run_status"),
            "R105": cockpit.get("protocol_status"),
            "R106": cockpit.get("first_live_activation_gate_status"),
            "R109": cockpit.get("status"),
        },
        "paper_live_separation_intact": _paper_live_separation_intact(cockpit=cockpit),
    }
    report = _sanitize(report)
    if record:
        append_first_live_burn_down_report(report, log_dir=resolved_log_dir)
    return report


def append_first_live_burn_down_report(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = first_live_burn_down_reports_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_first_live_burn_down_reports(
    *,
    limit: int = 50,
    report_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = first_live_burn_down_reports_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if report_id is not None and record.get("report_id") != report_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def first_live_burn_down_reports_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / REPORTS_FILENAME


def format_first_live_burn_down_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(dict(payload)), indent=2, sort_keys=True)


def _load_latest_surfaces(
    *,
    candidate_id: str,
    log_dir: Path,
    env: Mapping[str, str] | None,
) -> dict[str, dict[str, Any]]:
    dry_run = _latest_record(load_tiny_live_armed_dry_runs(limit=1, candidate_id=candidate_id, log_dir=log_dir))
    protocol = _latest_record(load_one_tiny_live_order_protocol_checks(limit=1, log_dir=log_dir))
    activation_gate = _latest_record(load_first_live_activation_gate_checks(limit=1, log_dir=log_dir))
    if dry_run and protocol and activation_gate:
        cockpit = _cockpit_state_from_latest_records(
            candidate_id=candidate_id,
            log_dir=log_dir,
            activation_gate=activation_gate,
            dry_run=dry_run,
            protocol=protocol,
        )
        return {
            "dry_run": dry_run,
            "protocol": protocol,
            "activation_gate": activation_gate,
            "cockpit": cockpit,
        }

    dry_run = build_tiny_live_armed_dry_run(candidate_id=candidate_id, log_dir=log_dir, env=env, record=False)
    protocol = build_one_tiny_live_order_protocol_check(candidate_id=candidate_id, log_dir=log_dir, env=env, record=False)
    activation_gate = build_first_live_activation_gate(candidate_id=candidate_id, log_dir=log_dir, env=env, record=False)
    cockpit = build_operator_approval_cockpit_state(candidate_id=candidate_id, log_dir=log_dir, env=env)
    return {
        "dry_run": dry_run,
        "protocol": protocol,
        "activation_gate": activation_gate,
        "cockpit": cockpit,
    }


def _latest_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    return records[0] if records else None


def _cockpit_state_from_latest_records(
    *,
    candidate_id: str,
    log_dir: Path,
    activation_gate: Mapping[str, Any],
    dry_run: Mapping[str, Any],
    protocol: Mapping[str, Any],
) -> dict[str, Any]:
    latest_intent = _latest_record(load_operator_approval_cockpit_intents(limit=1, candidate_id=candidate_id, log_dir=log_dir))
    activation_status = str(activation_gate.get("status") or "FIRST_LIVE_BLOCKED")
    window_status = "MISSING"
    status = "INTENT_RECORDED" if latest_intent and latest_intent.get("accepted_as_intent") is True else "BLOCKED"
    if activation_status == FIRST_LIVE_ACTIVATION_READY:
        status = "READY_FOR_REVIEW" if not latest_intent else status
    sacred_button_state = _fallback_sacred_button_state(
        first_live_activation_gate_status=activation_status,
        approval_window_status=window_status,
    )
    blockers = list(
        dict.fromkeys(
            [
                *[str(item) for item in activation_gate.get("blockers") or []],
                *[f"final preflight: {item}" for item in dry_run.get("final_preflight_blockers") or []],
                *[f"dry run: {item}" for item in dry_run.get("blockers") or []],
                *[f"protocol: {item}" for item in protocol.get("blockers") or []],
            ]
        )
    )
    return {
        "status": status,
        "final_preflight_status": dry_run.get("final_preflight_status") or activation_gate.get("final_preflight_status"),
        "tiny_live_armed_dry_run_status": dry_run.get("status") or activation_gate.get("tiny_live_armed_dry_run_status"),
        "protocol_status": protocol.get("status") or activation_gate.get("one_tiny_live_order_protocol_status"),
        "first_live_activation_gate_status": activation_status,
        "approval_window_status": window_status,
        "sacred_button_state": sacred_button_state,
        "blockers": blockers,
        "live_ready": False,
        "execution_enabled_by_ui": False,
        "order_placed": False,
        "real_order_placed": False,
        "execution_attempted": False,
        "real_order_possible": False,
        "secrets_shown": False,
        "source_surfaces_used": [
            "operator.first_live_operator_approval_cockpit.latest_record_adapter",
            *[str(item) for item in activation_gate.get("source_surfaces_used") or []],
            *[str(item) for item in dry_run.get("source_surfaces_used") or []],
            *[str(item) for item in protocol.get("source_surfaces_used") or []],
        ],
    }


def _fallback_sacred_button_state(*, first_live_activation_gate_status: str, approval_window_status: str) -> dict[str, Any]:
    if approval_window_status == "EXPIRED":
        label = "EXPIRED"
        visual_state = "EXPIRED"
        reason = "Approval window expired."
    elif first_live_activation_gate_status != FIRST_LIVE_ACTIVATION_READY:
        label = "BLOCKED BY R106"
        visual_state = "LOCKED"
        reason = "R106 first-live activation gate is not ready."
    elif approval_window_status == "OPEN":
        label = "RECORD INTENT ONLY"
        visual_state = "REVIEWABLE"
        reason = "Intent prerequisites are satisfied."
    else:
        label = "SACRED BUTTON LOCKED"
        visual_state = "LOCKED"
        reason = "Approval window is not open."
    return {
        "label": label,
        "enabled": bool(first_live_activation_gate_status == FIRST_LIVE_ACTIVATION_READY and approval_window_status == "OPEN"),
        "reason": reason,
        "visual_state": visual_state,
        "can_place_order": False,
        "records_intent_only": True,
        "confirmation_phrase_required": True,
        "confirmation_phrase_template": CONFIRMATION_PHRASE_TEMPLATE,
        "safety_copy": "This does not place an order.",
    }


def _blocker_groups(
    *,
    dry_run: Mapping[str, Any],
    protocol: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
    cockpit: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    blockers = _all_blockers(dry_run=dry_run, protocol=protocol, activation_gate=activation_gate, cockpit=cockpit)
    grouped = {name: [] for name in GROUP_ORDER}
    for blocker in blockers:
        grouped[_group_for_blocker(blocker)].append(blocker)

    result: dict[str, dict[str, Any]] = {}
    for name in GROUP_ORDER:
        meta = GROUP_META[name]
        group_blockers = list(dict.fromkeys(grouped[name]))
        result[name] = {
            "blockers": group_blockers,
            "count": len(group_blockers),
            "owner": meta["owner"],
            "can_clear_tomorrow": meta["can_clear_tomorrow"],
            "next_action": meta["next_action"],
            "verification_command": meta["verification_command"],
            "related_phase": meta["related_phase"],
        }
    return result


def _all_blockers(
    *,
    dry_run: Mapping[str, Any],
    protocol: Mapping[str, Any],
    activation_gate: Mapping[str, Any],
    cockpit: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    for payload in (activation_gate, dry_run, protocol, cockpit):
        blockers.extend(str(item) for item in payload.get("blockers") or [])
    blockers.extend(str(item) for item in dry_run.get("final_preflight_blockers") or [])
    return list(dict.fromkeys(blockers))


def _group_for_blocker(blocker: str) -> str:
    text = blocker.lower()
    if any(term in text for term in ("stale candidate", "candidate stale", "fresh promoted", "candidate_id")):
        return "candidate_blockers"
    if any(term in text for term in ("approval intent", "human approval", "review packet", "packet hash", "risk contract hash", "final review packet", "r85", "r86", "r88")):
        return "approval_record_blockers"
    if any(term in text for term in ("live execution", "live orders", "kill switch", "environment boundary", "env boundary", "live env", "flag state")):
        return "environment_flag_blockers"
    if "credential" in text or "api key" in text or "api secret" in text or "binance" in text:
        return "binance_credential_blockers"
    if any(term in text for term in ("account", "funding", "balance", "conflicting position", "open/conflicting", "position size", "max loss")):
        return "account_funding_blockers"
    if "protective" in text or "stop" in text or "take-profit" in text:
        return "protective_order_blockers"
    if "adapter" in text or "connector mode" in text or "dry-run-only connector" in text:
        return "adapter_blockers"
    if any(term in text for term in ("strategy", "promotion", "eligibility", "quality", "miro", "markov")):
        return "strategy_quality_blockers"
    if "telegram" in text:
        return "telegram_blockers"
    if "confirmation phrase" in text:
        return "confirmation_phrase_blockers"
    return "unknown_or_manual_check_blockers"


def _priority_burn_down() -> list[dict[str, Any]]:
    actions = [
        ("Wait for or identify fresh promoted candidate.", "candidate_blockers", _cmd("final-live-preflight")),
        ("Verify R102 final-live-preflight status.", "environment_flag_blockers", _cmd("final-live-preflight")),
        ("Record/verify final approval intent.", "approval_record_blockers", _cmd("tiny-live-armed-dry-run")),
        ("Complete human approval/review records.", "approval_record_blockers", _cmd("final-live-preflight")),
        ("Configure Binance credentials safely, without exposing values.", "binance_credential_blockers", _cmd("final-live-preflight")),
        ("Verify account/funding without placing orders.", "account_funding_blockers", _cmd("first-live-activation-gate")),
        ("Configure protective order readiness.", "protective_order_blockers", _cmd("one-tiny-live-order-protocol")),
        ("Verify live adapter boundary.", "adapter_blockers", _cmd("first-live-activation-gate")),
        ("Define tiny position size and max loss cap.", "account_funding_blockers", _cmd("first-live-activation-gate")),
        ("Re-run R102/R104/R105/R106/R109 state.", "unknown_or_manual_check_blockers", _cmd("first-live-burn-down")),
        ("Confirm sacred button remains intent-only.", "confirmation_phrase_blockers", "curl -s http://127.0.0.1:8015/operator/approval-cockpit/state"),
        ("Only then prepare future explicit authorization phase.", "unknown_or_manual_check_blockers", _cmd("first-live-burn-down")),
    ]
    return [
        {
            "priority": index,
            "action": action,
            "blocker_group": group,
            "verification_command": command,
        }
        for index, (action, group, command) in enumerate(actions, start=1)
    ]


def _morning_command_pack() -> dict[str, str]:
    return {
        "final_live_preflight": _cmd("final-live-preflight"),
        "tiny_live_armed_dry_run": _cmd("tiny-live-armed-dry-run"),
        "one_tiny_live_order_protocol": _cmd("one-tiny-live-order-protocol"),
        "first_live_activation_gate": _cmd("first-live-activation-gate"),
        "approval_cockpit_state_curl": "curl -s http://127.0.0.1:8015/operator/approval-cockpit/state",
        "first_live_burn_down": _cmd("first-live-burn-down"),
    }


def _human_checklist() -> list[dict[str, Any]]:
    items = [
        "candidate fresh?",
        "hashes match?",
        "R106 ready?",
        "protective orders ready?",
        "max loss known?",
        "exchange funding checked?",
        "kill switch understood?",
        "emergency cancel path known?",
        "no conflicting position?",
        "no second order before postmortem?",
    ]
    return [{"item": item, "checked": False} for item in items]


def _source_surfaces(*, cockpit: Mapping[str, Any]) -> list[str]:
    sources = [
        SOURCE_SURFACE,
        "R102 final-live-preflight",
        "R104 tiny-live-armed-dry-run",
        "R105 one-tiny-live-order-protocol",
        "R106 first-live-activation-gate",
        "R109 first-live cockpit sacred button state",
        "operator.final_live_preflight.build_final_live_preflight",
        "operator.tiny_live_armed_dry_run.build_tiny_live_armed_dry_run",
        "operator.one_tiny_live_order_protocol.build_one_tiny_live_order_protocol_check",
        "operator.first_live_activation_gate.build_first_live_activation_gate",
        "operator.first_live_operator_approval_cockpit.build_operator_approval_cockpit_state",
    ]
    sources.extend(str(item) for item in cockpit.get("source_surfaces_used") or [])
    return list(dict.fromkeys(sources))


def _paper_live_separation_intact(*, cockpit: Mapping[str, Any]) -> bool:
    return cockpit.get("real_order_possible") is False and cockpit.get("execution_enabled_by_ui") is False


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    rendered = json.dumps(payload, sort_keys=True)
    secret_tokens = ("api_secret", "api key", "telegram_bot_token", "secret-api", "secret-telegram", "auth header")
    if any(token in rendered.lower() for token in secret_tokens):
        payload = dict(payload)
        payload["secrets_shown"] = False
    return payload
