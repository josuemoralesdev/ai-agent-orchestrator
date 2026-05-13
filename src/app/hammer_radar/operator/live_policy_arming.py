"""R74 runtime env arming plan for live timeframe policies.

This module reports policy-only env arming status and manual runbook steps. It
never edits env files, restarts services, places orders, signs payloads, reads
secret values, or calls exchange networks.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_timeframe_policy import get_first_live_timeframe_policy

PHASE = "R74"
SYSTEM = "money_printing_machine_hammer_radar"
EXECUTION_MODE = "ENV_ARMING_PLAN_ONLY"
CHECKS_FILENAME = "live_policy_arming_checks.ndjson"

ORDER_PLACED = False
REAL_ORDER_PLACED = False
NETWORK_ALLOWED = False
SECRETS_SHOWN = False

RECOMMENDED_MANUAL_ENV_FILE = (
    "/home/josue/.config/hammer-radar/notifications.env or a dedicated policy env file"
)
MANUAL_RESTART_COMMANDS = [
    "sudo systemctl restart hammer-approval-api.service",
    "sudo systemctl restart hammer-telegram-polling.service",
]
SMOKE_COMMANDS = [
    "curl --max-time 5 -s http://127.0.0.1:8015/health | jq .",
    "curl --max-time 5 -s http://127.0.0.1:8015/live/timeframe-policy/status | jq .",
    "curl --max-time 5 -s http://127.0.0.1:8015/live/policy-arming/status | jq .",
    "curl --max-time 5 -s http://127.0.0.1:8015/live/first-candidates/status | jq .",
]
MICRO_CHANGES = [
    "HAMMER_MICRO_LIVE_ALLOWED=true",
    "HAMMER_MICRO_LIVE_TIMEFRAMES=4m,8m",
]
ACTIVE_CHANGES = [
    "HAMMER_ACTIVE_TIMEFRAME_LIVE_ALLOWED=true",
    "HAMMER_ACTIVE_TIMEFRAME_LIVE_TIMEFRAMES=22m,55m",
]
HIGHER_CHANGES = [
    "HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED=true",
    "HAMMER_HIGHER_TIMEFRAME_LIVE_TIMEFRAMES=444m,4H",
]
ROLLBACK_CHANGES = [
    "HAMMER_MICRO_LIVE_ALLOWED=false",
    "HAMMER_ACTIVE_TIMEFRAME_LIVE_ALLOWED=false",
    "HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED=false",
]


def build_live_policy_arming_status(
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    source = os.environ if env is None else env
    policy = get_first_live_timeframe_policy(env=source)
    execution_env = _execution_env(source)
    warnings = _warnings(execution_env=execution_env)
    policy_env = {
        "micro_live_allowed": policy["micro_live_allowed"],
        "micro_live_timeframes": list(policy["micro_live_timeframes"]),
        "active_timeframe_live_allowed": policy["active_timeframe_live_allowed"],
        "active_timeframe_live_timeframes": list(policy["active_timeframe_live_timeframes"]),
        "higher_timeframe_live_allowed": policy["higher_timeframe_live_allowed"],
        "higher_timeframe_live_timeframes": list(policy["higher_timeframe_live_timeframes"]),
    }
    policy_only_ready = bool(
        policy_env["micro_live_timeframes"]
        and policy_env["active_timeframe_live_timeframes"]
        and policy_env["higher_timeframe_live_timeframes"]
        and execution_env["live_execution_enabled"] is False
        and execution_env["allow_live_orders"] is False
    )
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "system": SYSTEM,
            "execution_mode": EXECUTION_MODE,
            "created_at": datetime.now(UTC).isoformat(),
            "order_placed": ORDER_PLACED,
            "real_order_placed": REAL_ORDER_PLACED,
            "network_allowed": NETWORK_ALLOWED,
            "secrets_shown": SECRETS_SHOWN,
            "policy_env": policy_env,
            "execution_env": execution_env,
            "arming_levels": {
                "policy_only": {
                    "ready": policy_only_ready,
                    "description": (
                        "allows FIRST LIVE NEXT to offer approval for selected micro/active/higher candidates, "
                        "but no live order execution"
                    ),
                },
                "live_execution": {
                    "ready": False,
                    "description": "actual order execution remains disabled",
                },
            },
            "recommended_manual_env_file": RECOMMENDED_MANUAL_ENV_FILE,
            "manual_changes": build_live_policy_arming_plan(target="both", env=source)["manual_changes"],
            "manual_restart_commands": list(MANUAL_RESTART_COMMANDS),
            "smoke_commands": list(SMOKE_COMMANDS),
            "rollback_changes": list(ROLLBACK_CHANGES),
            "blockers": [],
            "warnings": warnings,
        }
    )


def build_live_policy_arming_runbook(
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    status = build_live_policy_arming_status(env=env)
    return _sanitize(
        {
            **status,
            "runbook_name": "R74_POLICY_ARMING_RUNBOOK",
            "manual_steps": [
                "Edit the env file used by hammer-approval-api.service; do not paste secrets into chat.",
                "Add only the policy env switches needed for micro, active timeframe, higher timeframe, or a combined plan.",
                "Restart hammer-approval-api.service and hammer-telegram-polling.service manually.",
                "Run the smoke commands and verify policy booleans changed while order flags remain false.",
                "Use rollback changes and restart both services if policy arming must be disabled.",
            ],
            "plans": {
                "micro": build_live_policy_arming_plan(target="micro", env=env),
                "active": build_live_policy_arming_plan(target="active", env=env),
                "higher": build_live_policy_arming_plan(target="higher", env=env),
                "both": build_live_policy_arming_plan(target="both", env=env),
            },
        }
    )


def build_live_policy_arming_plan(
    *,
    target: str = "both",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    normalized = str(target or "both").strip().lower()
    if normalized == "micro":
        changes = list(MICRO_CHANGES)
    elif normalized == "active":
        changes = list(ACTIVE_CHANGES)
    elif normalized == "higher":
        changes = list(HIGHER_CHANGES)
    else:
        normalized = "both"
        changes = [*MICRO_CHANGES, *ACTIVE_CHANGES, *HIGHER_CHANGES]
    return _sanitize(
        {
            "status": "OK",
            "phase": PHASE,
            "target": normalized,
            "manual_changes": changes,
            "manual_restart_commands": list(MANUAL_RESTART_COMMANDS),
            "smoke_commands": list(SMOKE_COMMANDS),
            "rollback_changes": list(ROLLBACK_CHANGES),
            "recommended_manual_env_file": RECOMMENDED_MANUAL_ENV_FILE,
            "order_placed": ORDER_PLACED,
            "real_order_placed": REAL_ORDER_PLACED,
            "network_allowed": NETWORK_ALLOWED,
            "secrets_shown": SECRETS_SHOWN,
        }
    )


def evaluate_and_record_live_policy_arming_check(
    *,
    log_dir: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    payload = build_live_policy_arming_status(env=env)
    record = _check_record(payload)
    append_live_policy_arming_check(record, log_dir=resolved_log_dir)
    payload["audit_event_recorded"] = True
    payload["policy_arming_check_id"] = record["check_id"]
    payload["live_policy_arming_checks_path"] = str(live_policy_arming_checks_path(resolved_log_dir))
    return _sanitize(payload)


def load_live_policy_arming_checks(
    *,
    limit: int = 50,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = live_policy_arming_checks_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            records.append(_sanitize(record))
    records = list(reversed(records))
    return records[:limit] if limit > 0 else records


def live_policy_arming_checks_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / CHECKS_FILENAME


def append_live_policy_arming_check(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = live_policy_arming_checks_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_sanitize(record), sort_keys=True) + "\n")


def format_live_policy_arming_operator_message(payload: Mapping[str, Any], *, section: str = "status") -> str:
    policy_env = payload.get("policy_env") if isinstance(payload.get("policy_env"), dict) else {}
    execution_env = payload.get("execution_env") if isinstance(payload.get("execution_env"), dict) else {}
    if section == "runbook":
        changes = payload.get("manual_changes") if isinstance(payload.get("manual_changes"), list) else []
        restarts = payload.get("manual_restart_commands") if isinstance(payload.get("manual_restart_commands"), list) else []
        return "\n".join(
            [
                "R74 live policy runbook: OK",
                "POLICY_ONLY. No order placed. real_order_placed=false.",
                f"manual env: {'; '.join(str(item) for item in changes[:4])}",
                f"restart: {'; '.join(str(item) for item in restarts[:2])}",
                "smoke: /live/timeframe-policy/status then /live/policy-arming/status",
            ]
        )
    if section == "micro":
        return "\n".join(
            [
                f"R74 micro policy arming: enabled={policy_env.get('micro_live_allowed')}",
                "POLICY_ONLY. No order placed. real_order_placed=false.",
                f"timeframes: {','.join(policy_env.get('micro_live_timeframes') or [])}",
                "manual change: HAMMER_MICRO_LIVE_ALLOWED=true; HAMMER_MICRO_LIVE_TIMEFRAMES=4m,8m",
            ]
        )
    if section == "higher":
        return "\n".join(
            [
                f"R74 higher policy arming: enabled={policy_env.get('higher_timeframe_live_allowed')}",
                "POLICY_ONLY. No order placed. real_order_placed=false.",
                f"timeframes: {','.join(policy_env.get('higher_timeframe_live_timeframes') or [])}",
                "manual change: HAMMER_HIGHER_TIMEFRAME_LIVE_ALLOWED=true; HAMMER_HIGHER_TIMEFRAME_LIVE_TIMEFRAMES=444m,4H",
            ]
        )
    if section == "active":
        return "\n".join(
            [
                f"R74 active timeframe policy arming: enabled={policy_env.get('active_timeframe_live_allowed')}",
                "POLICY_ONLY. No order placed. real_order_placed=false.",
                f"timeframes: {','.join(policy_env.get('active_timeframe_live_timeframes') or [])}",
                "manual change: HAMMER_ACTIVE_TIMEFRAME_LIVE_ALLOWED=true; HAMMER_ACTIVE_TIMEFRAME_LIVE_TIMEFRAMES=22m,55m",
            ]
        )
    return "\n".join(
        [
            "R74 live policy arming: OK",
            "POLICY_ONLY. No order placed. real_order_placed=false.",
            (
                f"policy: micro={policy_env.get('micro_live_allowed')} "
                f"active={policy_env.get('active_timeframe_live_allowed')} "
                f"higher={policy_env.get('higher_timeframe_live_allowed')}"
            ),
            (
                f"execution: live_execution={execution_env.get('live_execution_enabled')} "
                f"allow_live_orders={execution_env.get('allow_live_orders')} "
                f"kill_switch={execution_env.get('global_kill_switch')}"
            ),
        ]
    )


def _execution_env(source: Mapping[str, str]) -> dict[str, Any]:
    return {
        "binance_live_enabled": _parse_bool(source.get("HAMMER_BINANCE_LIVE_ENABLED"), default=False),
        "live_execution_enabled": _parse_bool(source.get("HAMMER_LIVE_EXECUTION_ENABLED"), default=False),
        "allow_live_orders": _parse_bool(source.get("HAMMER_ALLOW_LIVE_ORDERS"), default=False),
        "global_kill_switch": _parse_bool(source.get("HAMMER_GLOBAL_KILL_SWITCH"), default=True),
        "protective_orders_enabled": _parse_bool(source.get("HAMMER_PROTECTIVE_ORDERS_ENABLED"), default=False),
        "protective_order_mode": str(source.get("HAMMER_PROTECTIVE_ORDER_MODE") or "PREVIEW_ONLY").strip() or "PREVIEW_ONLY",
        "connector_mode": str(source.get("HAMMER_BINANCE_CONNECTOR_MODE") or "DRY_RUN_ONLY").strip() or "DRY_RUN_ONLY",
    }


def _warnings(*, execution_env: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    if execution_env.get("live_execution_enabled") is True:
        warnings.append("HAMMER_LIVE_EXECUTION_ENABLED is true; R74 expects policy-only arming")
    if execution_env.get("allow_live_orders") is True:
        warnings.append("HAMMER_ALLOW_LIVE_ORDERS is true; R74 expects no live order arming")
    if execution_env.get("global_kill_switch") is not True:
        warnings.append("HAMMER_GLOBAL_KILL_SWITCH is false; keep execution arming separate from policy arming")
    if execution_env.get("connector_mode") == "LIVE_ORDER_ENABLED":
        warnings.append("HAMMER_BINANCE_CONNECTOR_MODE is LIVE_ORDER_ENABLED; R74 does not require this")
    return warnings


def _check_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "check_id": uuid4().hex,
        "phase": PHASE,
        "event_type": "live_policy_arming_check",
        "created_at": payload.get("created_at"),
        "status": payload.get("status"),
        "policy_env": payload.get("policy_env"),
        "execution_env": payload.get("execution_env"),
        "arming_levels": payload.get("arming_levels"),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "order_placed": ORDER_PLACED,
        "real_order_placed": REAL_ORDER_PLACED,
        "network_allowed": NETWORK_ALLOWED,
        "secrets_shown": SECRETS_SHOWN,
    }


def _parse_bool(raw: object, *, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized = {str(key): _sanitize(value) for key, value in payload.items()}
        for key in ("order_placed", "real_order_placed", "network_allowed", "secrets_shown"):
            if key in sanitized:
                sanitized[key] = False
        return sanitized
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    return payload
