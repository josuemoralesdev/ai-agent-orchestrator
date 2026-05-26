"""R138.5 burn-down command pack sanity check.

This module validates the R138 autonomous-lane burn-down command pack and
returns a compact next-actions view. It is diagnostic only: it never places
orders, creates payloads, signs requests, calls Binance, or mutates env/config.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.app.hammer_radar.operator.autonomous_lane_live_ready_burn_down import (
    DEFAULT_LANE_KEY,
    build_autonomous_lane_live_ready_burn_down,
)

COMMAND_PACK_SAFE = "COMMAND_PACK_SAFE"
COMMAND_PACK_UNSAFE = "COMMAND_PACK_UNSAFE"

DANGEROUS_COMMAND_TERMS = (
    "execute_live_order",
    "submit_test_order",
    "submit_protective_test",
    "build_signed",
    "signature",
    "BINANCE_API_SECRET",
    "BINANCE_API_KEY=",
    "/fapi/v1/order",
    "--apply",
    "systemctl restart",
    "sudo",
    "export HAMMER_LIVE",
    "HAMMER_ALLOW_LIVE_ORDERS=true",
    "HAMMER_GLOBAL_KILL_SWITCH=false",
)

SAFETY = {
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "order_payload_created": False,
    "signed_request_created": False,
    "network_allowed": False,
    "secrets_shown": False,
    "env_mutated": False,
    "config_written": False,
}


def build_burn_down_command_pack_sanity(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_LANE_KEY,
    source_statuses: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    burn_down = build_autonomous_lane_live_ready_burn_down(
        log_dir=log_dir,
        lane_key=lane_key,
        source_statuses=source_statuses,
    )
    command_pack = _mapping(burn_down.get("operator_command_pack"))
    validation = validate_safe_command_pack(command_pack)
    return {
        "status": COMMAND_PACK_SAFE if validation["unsafe_command_count"] == 0 else COMMAND_PACK_UNSAFE,
        "lane_key": str(burn_down.get("lane_key") or lane_key),
        "unsafe_command_count": validation["unsafe_command_count"],
        "unsafe_findings": validation["unsafe_findings"],
        "next_three_safe_actions": build_next_three_safe_actions(burn_down, unsafe_findings=validation["unsafe_findings"]),
        "safety": dict(SAFETY),
    }


def validate_safe_command_pack(command_pack: Mapping[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    unsafe_keys: set[str] = set()
    for command_key, command in _iter_command_strings(command_pack):
        for term in DANGEROUS_COMMAND_TERMS:
            if term in command:
                unsafe_keys.add(command_key)
                findings.append(
                    {
                        "command_key": command_key,
                        "dangerous_term": term,
                        "command": command,
                    }
                )
    return {
        "unsafe_command_count": len(unsafe_keys),
        "unsafe_findings": findings,
    }


def build_next_three_safe_actions(
    burn_down: Mapping[str, Any],
    *,
    unsafe_findings: list[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    unsafe_commands = {str(item.get("command")) for item in unsafe_findings or [] if item.get("command")}
    actions: list[dict[str, Any]] = []
    for step in burn_down.get("dependency_chain") or []:
        if not isinstance(step, Mapping):
            continue
        command = str(step.get("safe_check_command") or "").strip()
        if not command or command in unsafe_commands:
            continue
        if _command_has_dangerous_term(command):
            continue
        if step.get("blocked_now") is False:
            continue
        actions.append(
            {
                "rank": len(actions) + 1,
                "action": str(step.get("title") or step.get("id") or "Run safe burn-down check"),
                "command": command,
                "why": f"R138 dependency step: {step.get('category') or 'UNKNOWN'}",
            }
        )
        if len(actions) == 3:
            return actions

    command_pack = _mapping(burn_down.get("operator_command_pack"))
    fallback_specs = (
        ("fresh_signal_router_status", "Check fresh routed candidate status", "Confirms whether the lane has a current routed candidate."),
        (
            "autonomous_paper_lane_executor_integration_preview",
            "Preview autonomous paper proof",
            "Keeps proof gathering paper-only before tiny-live review.",
        ),
        ("first_tiny_live_lane_execution_gate", "Recheck tiny-live lane gate", "Shows the current non-executing lane gate blockers."),
    )
    for key, action, why in fallback_specs:
        command = str(command_pack.get(key) or "").strip()
        if not command or command in unsafe_commands or _command_has_dangerous_term(command):
            continue
        actions.append({"rank": len(actions) + 1, "action": action, "command": command, "why": why})
        if len(actions) == 3:
            break
    return actions


def format_burn_down_command_pack_sanity_json(payload: Mapping[str, Any]) -> str:
    compact = {
        "status": payload.get("status"),
        "lane_key": payload.get("lane_key"),
        "unsafe_command_count": int(payload.get("unsafe_command_count") or 0),
        "unsafe_findings": list(payload.get("unsafe_findings") or []),
        "next_three_safe_actions": list(payload.get("next_three_safe_actions") or [])[:3],
        "safety": payload.get("safety") or dict(SAFETY),
    }
    return json.dumps(compact, sort_keys=True, separators=(",", ":"))


def _iter_command_strings(command_pack: Mapping[str, Any]) -> list[tuple[str, str]]:
    commands: list[tuple[str, str]] = []
    for key, value in command_pack.items():
        if isinstance(value, str):
            commands.append((str(key), value))
        elif isinstance(value, Mapping):
            for child_key, child_value in _iter_command_strings(value):
                commands.append((f"{key}.{child_key}", child_value))
        elif isinstance(value, list | tuple):
            for index, child_value in enumerate(value):
                if isinstance(child_value, str):
                    commands.append((f"{key}.{index}", child_value))
                elif isinstance(child_value, Mapping):
                    for child_key, nested_value in _iter_command_strings(child_value):
                        commands.append((f"{key}.{index}.{child_key}", nested_value))
    return commands


def _command_has_dangerous_term(command: str) -> bool:
    return any(term in command for term in DANGEROUS_COMMAND_TERMS)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
