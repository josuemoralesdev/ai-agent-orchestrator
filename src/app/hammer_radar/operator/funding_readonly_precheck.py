"""R163 read-only funding precheck and balance gate.

This module composes local lane controls, sanitized env presence checks, and
the existing Binance read-only status helper. It does not create order payloads,
sign requests, call Binance endpoints, mutate env/config, or authorize live
execution.
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

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.binance_readonly import (
    CONNECTOR_STATUS_BLOCKED,
    CONNECTOR_STATUS_MISSING_ENV,
    CONNECTOR_STATUS_READY,
    ENV_API_KEY,
    ENV_API_SECRET,
    ENV_CONNECTOR_MODE,
    ENV_LIVE_TRADING_ENABLED,
    FORBIDDEN_ACTIONS,
    REQUIRED_CONNECTOR_MODE,
    build_binance_readonly_status,
)
from src.app.hammer_radar.operator.binance_live_status import (
    ENV_ALLOW_LIVE_ORDERS,
    ENV_GLOBAL_KILL_SWITCH,
    ENV_LIVE_EXECUTION_ENABLED,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import CONFIRM_SHORT_PAPER_CAPTURE_PHRASE
from src.app.hammer_radar.operator.short_risk_contract_apply_review import (
    CONFIRM_SHORT_RISK_CONTRACT_APPLY_REVIEW_RECORDING_PHRASE,
)
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY, build_short_strategy_target_family

FUNDING_READONLY_PRECHECK_READY = "FUNDING_READONLY_PRECHECK_READY"
FUNDING_READONLY_PRECHECK_REJECTED = "FUNDING_READONLY_PRECHECK_REJECTED"
FUNDING_READONLY_PRECHECK_RECORDED = "FUNDING_READONLY_PRECHECK_RECORDED"
FUNDING_READONLY_PRECHECK_BLOCKED = "FUNDING_READONLY_PRECHECK_BLOCKED"
FUNDING_READONLY_PRECHECK_ERROR = "FUNDING_READONLY_PRECHECK_ERROR"

FUNDING_NOT_CHECKED = "FUNDING_NOT_CHECKED"
READONLY_CONNECTOR_MISSING_ENV = "READONLY_CONNECTOR_MISSING_ENV"
READONLY_CONNECTOR_READY_BALANCE_NOT_CHECKED = "READONLY_CONNECTOR_READY_BALANCE_NOT_CHECKED"
READONLY_BALANCE_CHECK_NOT_AVAILABLE = "READONLY_BALANCE_CHECK_NOT_AVAILABLE"
READONLY_BALANCE_CHECK_BLOCKED = "READONLY_BALANCE_CHECK_BLOCKED"
ACCOUNT_NOT_FUNDED = "ACCOUNT_NOT_FUNDED"
ACCOUNT_FUNDED_BELOW_MINIMUM = "ACCOUNT_FUNDED_BELOW_MINIMUM"
ACCOUNT_FUNDED_READY_FOR_REVIEW = "ACCOUNT_FUNDED_READY_FOR_REVIEW"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

FUND_ACCOUNT_LATER = "FUND_ACCOUNT_LATER"
KEEP_R157_RUNNING = "KEEP_R157_RUNNING"
RUN_R158_AFTER_MORE_CAPTURES = "RUN_R158_AFTER_MORE_CAPTURES"
RUN_R164_READONLY_BALANCE_CHECK_IF_SAFE = "RUN_R164_READONLY_BALANCE_CHECK_IF_SAFE"

DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT = 44.0
EVENT_TYPE = "FUNDING_READONLY_PRECHECK"
LEDGER_FILENAME = "funding_readonly_prechecks.ndjson"
CONFIRM_FUNDING_READONLY_PRECHECK_RECORDING_PHRASE = (
    "I CONFIRM FUNDING READONLY PRECHECK RECORDING ONLY; NO ORDER; NO BINANCE TRADING CALL."
)

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "secrets_shown": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "global_live_flags_changed": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "operator.binance_readonly.build_binance_readonly_status",
    "operator.binance_live_status env constants",
    "operator.short_strategy_packet.build_short_strategy_target_family",
    "operator.short_risk_contract_apply_review safe R162 command",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_funding_readonly_precheck(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    minimum_balance_usdt: float = DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT,
    allow_readonly_network_check: bool = False,
    record_precheck: bool = False,
    confirm_funding_readonly_precheck: str | None = None,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_funding_readonly_precheck == CONFIRM_FUNDING_READONLY_PRECHECK_RECORDING_PHRASE
    source = os.environ if env is None else env
    minimum = float(minimum_balance_usdt)
    safety = _safety(allow_readonly_network_check=allow_readonly_network_check)
    try:
        target = build_target_lane_funding_context(lane_key=lane_key, config_path=config_path)
        local_env = build_local_env_readiness_summary(env=source)
        live_flags = build_live_flag_readiness_summary(env=source)
        readonly_connector = build_readonly_connector_summary(
            env=source,
            allow_readonly_network_check=allow_readonly_network_check,
        )
        balance_gate = build_balance_gate_summary(
            readonly_connector=readonly_connector,
            minimum_balance_usdt=minimum,
            allow_readonly_network_check=allow_readonly_network_check,
        )
        funding_readiness = classify_funding_readiness(
            local_env_readiness=local_env,
            live_flag_readiness=live_flags,
            readonly_connector=readonly_connector,
            balance_gate=balance_gate,
        )
        blockers = _blockers(
            target_family=target,
            local_env_readiness=local_env,
            live_flag_readiness=live_flags,
            readonly_connector=readonly_connector,
            balance_gate=balance_gate,
            funding_readiness=funding_readiness,
        )
        status = FUNDING_READONLY_PRECHECK_READY if _preview_ready(target, live_flags, readonly_connector) else FUNDING_READONLY_PRECHECK_BLOCKED
        if record_precheck and not confirmation_valid:
            status = FUNDING_READONLY_PRECHECK_REJECTED
        elif record_precheck and confirmation_valid:
            status = FUNDING_READONLY_PRECHECK_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "precheck_recorded": False,
            "precheck_id": None,
            "record_precheck_requested": bool(record_precheck),
            "confirmation_valid": bool(confirmation_valid),
            "allow_readonly_network_check": bool(allow_readonly_network_check),
            "target_family": target,
            "local_env_readiness": local_env,
            "live_flag_readiness": live_flags,
            "readonly_connector": readonly_connector,
            "balance_gate": balance_gate,
            "funding_readiness": funding_readiness,
            "blockers": blockers,
            "recommended_next_operator_move": _recommended_next_operator_move(funding_readiness),
            "recommended_next_engineering_move": _recommended_next_engineering_move(funding_readiness),
            "safe_commands": _safe_commands(target["lane_key"], minimum),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_precheck and confirmation_valid:
            record = append_funding_readonly_precheck_record(payload, log_dir=resolved_log_dir)
            payload["precheck_recorded"] = True
            payload["precheck_id"] = record["precheck_id"]
            payload["ledger_path"] = str(funding_readonly_precheck_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        target = _target_from_key(lane_key, mode="unknown")
        return _sanitize(
            {
                "status": FUNDING_READONLY_PRECHECK_ERROR,
                "generated_at": generated_at.isoformat(),
                "precheck_recorded": False,
                "precheck_id": None,
                "record_precheck_requested": bool(record_precheck),
                "confirmation_valid": bool(confirmation_valid),
                "allow_readonly_network_check": bool(allow_readonly_network_check),
                "target_family": target,
                "local_env_readiness": build_local_env_readiness_summary(env=source),
                "live_flag_readiness": build_live_flag_readiness_summary(env=source),
                "readonly_connector": build_readonly_connector_summary(
                    env=source,
                    allow_readonly_network_check=allow_readonly_network_check,
                ),
                "balance_gate": build_balance_gate_summary(minimum_balance_usdt=minimum),
                "funding_readiness": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "blockers": ["R163 funding read-only precheck build error must be fixed before review"],
                "recommended_next_operator_move": KEEP_R157_RUNNING,
                "recommended_next_engineering_move": "Fix R163 precheck builder error; do not mutate env, config, lane mode, or live flags.",
                "safe_commands": _safe_commands(lane_key, minimum),
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": safety,
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_local_env_readiness_summary(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    mode = _env_value(source, ENV_CONNECTOR_MODE)
    api_key = _env_value(source, ENV_API_KEY)
    api_secret = _env_value(source, ENV_API_SECRET)
    return {
        "binance_connector_mode_present": bool(mode),
        "binance_connector_mode": mode or "n/a",
        "api_key_present": bool(api_key),
        "api_secret_present": bool(api_secret),
        "api_key_preview": _preview_api_key(api_key) or "n/a",
        "secrets_shown": False,
    }


def build_live_flag_readiness_summary(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = os.environ if env is None else env
    binance_live = _env_bool_or_none(source, ENV_LIVE_TRADING_ENABLED)
    hammer_live = _env_bool_or_none(source, ENV_LIVE_EXECUTION_ENABLED)
    allow_orders = _env_bool_or_none(source, ENV_ALLOW_LIVE_ORDERS)
    kill_switch = _env_bool_or_none(source, ENV_GLOBAL_KILL_SWITCH)
    kill_switch_status = "enabled" if kill_switch is not False else "unknown"
    live_flags_safe = binance_live is not True and hammer_live is not True and allow_orders is not True and kill_switch is not False
    return {
        "binance_live_trading_enabled": binance_live,
        "hammer_live_execution_enabled": hammer_live,
        "hammer_allow_live_orders": allow_orders,
        "global_kill_switch_status": kill_switch_status,
        "live_flags_safe": bool(live_flags_safe),
    }


def build_readonly_connector_summary(
    *,
    env: Mapping[str, str] | None = None,
    allow_readonly_network_check: bool = False,
) -> dict[str, Any]:
    status = build_binance_readonly_status(env=env)
    allowed = list(status.get("allowed_actions") or ["read_exchange_info"])
    if "read_exchange_info" not in allowed:
        allowed.insert(0, "read_exchange_info")
    if status.get("api_key_present") and status.get("api_secret_present") and "read_account_status" not in allowed:
        allowed.append("read_account_status")
    return {
        "connector_status": status.get("connector_status") or "UNKNOWN",
        "allowed_actions": allowed,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "network_check_available": False,
        "network_check_attempted": False,
        "network_check_requested": bool(allow_readonly_network_check),
        "source_connector_name": status.get("connector_name"),
        "read_only": bool(status.get("read_only")),
        "blockers": list(status.get("blockers") or []),
        "warnings": list(status.get("warnings") or []),
    }


def build_balance_gate_summary(
    *,
    readonly_connector: Mapping[str, Any] | None = None,
    minimum_balance_usdt: float = DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT,
    allow_readonly_network_check: bool = False,
    available_balance_usdt: float | None = None,
) -> dict[str, Any]:
    connector = dict(readonly_connector or {})
    minimum = float(minimum_balance_usdt)
    balance_check_available = bool(connector.get("network_check_available"))
    balance_check_attempted = False
    funding_status = FUNDING_NOT_CHECKED
    funding_ready = False
    if allow_readonly_network_check and not balance_check_available:
        funding_status = READONLY_BALANCE_CHECK_NOT_AVAILABLE
    elif connector.get("connector_status") == CONNECTOR_STATUS_BLOCKED:
        funding_status = READONLY_BALANCE_CHECK_BLOCKED
    elif available_balance_usdt is not None:
        balance_check_attempted = True
        if available_balance_usdt <= 0:
            funding_status = ACCOUNT_NOT_FUNDED
        elif available_balance_usdt < minimum:
            funding_status = ACCOUNT_FUNDED_BELOW_MINIMUM
        else:
            funding_status = ACCOUNT_FUNDED_READY_FOR_REVIEW
            funding_ready = True
    return {
        "balance_check_attempted": balance_check_attempted,
        "balance_check_available": balance_check_available,
        "asset": "USDT",
        "available_balance_usdt": available_balance_usdt,
        "minimum_balance_required_estimate_usdt": minimum,
        "funding_ready": funding_ready,
        "funding_status": funding_status,
    }


def build_target_lane_funding_context(
    *,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    return build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)


def classify_funding_readiness(
    *,
    local_env_readiness: Mapping[str, Any] | None = None,
    live_flag_readiness: Mapping[str, Any] | None = None,
    readonly_connector: Mapping[str, Any] | None = None,
    balance_gate: Mapping[str, Any] | None = None,
) -> str:
    local_env = dict(local_env_readiness or {})
    live_flags = dict(live_flag_readiness or {})
    connector = dict(readonly_connector or {})
    balance = dict(balance_gate or {})
    connector_status = connector.get("connector_status")
    balance_status = balance.get("funding_status")
    if live_flags and live_flags.get("live_flags_safe") is not True:
        return READONLY_BALANCE_CHECK_BLOCKED
    if connector_status == CONNECTOR_STATUS_BLOCKED:
        return READONLY_BALANCE_CHECK_BLOCKED
    if connector_status == CONNECTOR_STATUS_MISSING_ENV or not (
        local_env.get("binance_connector_mode_present")
        and local_env.get("api_key_present")
        and local_env.get("api_secret_present")
    ):
        return READONLY_CONNECTOR_MISSING_ENV
    if balance_status in {
        READONLY_BALANCE_CHECK_NOT_AVAILABLE,
        READONLY_BALANCE_CHECK_BLOCKED,
        ACCOUNT_NOT_FUNDED,
        ACCOUNT_FUNDED_BELOW_MINIMUM,
        ACCOUNT_FUNDED_READY_FOR_REVIEW,
    }:
        return str(balance_status)
    if connector_status == CONNECTOR_STATUS_READY:
        return READONLY_CONNECTOR_READY_BALANCE_NOT_CHECKED
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_funding_readonly_precheck_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = funding_readonly_precheck_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "precheck_id": record.get("precheck_id") or f"r163_funding_readonly_precheck_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_precheck_requested": bool(record.get("record_precheck_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "allow_readonly_network_check": bool(record.get("allow_readonly_network_check")),
            "target_family": dict(record.get("target_family") or {}),
            "local_env_readiness": dict(record.get("local_env_readiness") or {}),
            "live_flag_readiness": dict(record.get("live_flag_readiness") or {}),
            "readonly_connector": dict(record.get("readonly_connector") or {}),
            "balance_gate": dict(record.get("balance_gate") or {}),
            "funding_readiness": record.get("funding_readiness"),
            "blockers": list(record.get("blockers") or []),
            "recommended_next_operator_move": record.get("recommended_next_operator_move"),
            "recommended_next_engineering_move": record.get("recommended_next_engineering_move"),
            "safe_commands": list(record.get("safe_commands") or []),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_funding_readonly_precheck_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = funding_readonly_precheck_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(_sanitize(json.loads(line)))
        return records
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=32_000_000)]


def summarize_funding_readonly_prechecks(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    readiness_counts = Counter(str(record.get("funding_readiness") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "funding_readiness_counts": dict(sorted(readiness_counts.items())),
        "last_precheck_id": latest.get("precheck_id"),
        "last_target_lane": (latest.get("target_family") or {}).get("lane_key") if isinstance(latest.get("target_family"), Mapping) else None,
        "safety": _safety(allow_readonly_network_check=False),
    }


def funding_readonly_precheck_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_funding_readonly_precheck_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _safe_commands(lane_key: str, minimum_balance_usdt: float) -> list[str]:
    minimum = _format_float(minimum_balance_usdt)
    return [
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward funding-readonly-precheck "
            f'--lane-key "{lane_key}" --minimum-balance-usdt {minimum}'
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward funding-readonly-precheck "
            f'--lane-key "{lane_key}" --minimum-balance-usdt {minimum} --record-precheck '
            f'--confirm-funding-readonly-precheck "{CONFIRM_FUNDING_READONLY_PRECHECK_RECORDING_PHRASE}"'
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward short-paper-evidence-capture-loop "
            f'--lane-key "{lane_key}" --latest-signals 500 --latest-scans 1000 '
            "--max-iterations 720 --sleep-seconds 60 --iteration-timeout-seconds 30 --heartbeat-every 1 "
            "--run-capture-loop --record-capture --confirm-short-paper-capture "
            f'"{CONFIRM_SHORT_PAPER_CAPTURE_PHRASE}"'
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward short-evidence-recheck-packet "
            f'--lane-key "{lane_key}" --latest-captures 200 --latest-outcomes 10000 --latest-signals 3000 --latest-betrayal 5000'
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward short-risk-contract-apply-review "
            f'--lane-key "{lane_key}" --latest-captures 200 --latest-drafts 50 --record-review '
            f'--confirm-short-risk-contract-apply-review "{CONFIRM_SHORT_RISK_CONTRACT_APPLY_REVIEW_RECORDING_PHRASE}"'
        ),
    ]


def _do_not_run_yet() -> list[str]:
    return [
        "live-connector-submit",
        "any order endpoint",
        "global live flag arming",
        "kill switch disable",
        "set short lane tiny_live",
        "set new lane tiny_live",
        "write risk contract config",
        "funds-dependent execution",
        "signed order request",
        "protective order submit",
        "withdraw",
        "transfer",
    ]


def _blockers(
    *,
    target_family: Mapping[str, Any],
    local_env_readiness: Mapping[str, Any],
    live_flag_readiness: Mapping[str, Any],
    readonly_connector: Mapping[str, Any],
    balance_gate: Mapping[str, Any],
    funding_readiness: str,
) -> list[str]:
    blockers: list[str] = []
    if target_family.get("lane_key") != DEFAULT_TARGET_LANE_KEY:
        blockers.append("target lane differs from R163 BTCUSDT 8m short family")
    if target_family.get("current_mode") != "paper":
        blockers.append("target lane must remain paper")
    if target_family.get("direction") != "short":
        blockers.append("target lane is not short")
    if local_env_readiness.get("binance_connector_mode") != REQUIRED_CONNECTOR_MODE:
        blockers.append("BINANCE_CONNECTOR_MODE is not read_only")
    if not local_env_readiness.get("api_key_present"):
        blockers.append("BINANCE_API_KEY missing")
    if not local_env_readiness.get("api_secret_present"):
        blockers.append("BINANCE_API_SECRET missing")
    if live_flag_readiness.get("live_flags_safe") is not True:
        blockers.append("live flags are not safe for read-only precheck")
    blockers.extend(str(item) for item in readonly_connector.get("blockers") or [] if item)
    if balance_gate.get("funding_ready") is not True:
        blockers.append(f"funding is {funding_readiness}")
    blockers.append("fresh captures still need R157/R158 threshold review before any future live discussion")
    blockers.append("risk contract remains draft/review only until a separate future config phase")
    return _dedupe(blockers)


def _recommended_next_operator_move(funding_readiness: str) -> str:
    if funding_readiness in {READONLY_CONNECTOR_MISSING_ENV, ACCOUNT_NOT_FUNDED, ACCOUNT_FUNDED_BELOW_MINIMUM}:
        return FUND_ACCOUNT_LATER
    if funding_readiness == READONLY_CONNECTOR_READY_BALANCE_NOT_CHECKED:
        return RUN_R164_READONLY_BALANCE_CHECK_IF_SAFE
    if funding_readiness == READONLY_BALANCE_CHECK_NOT_AVAILABLE:
        return KEEP_R157_RUNNING
    return RUN_R158_AFTER_MORE_CAPTURES


def _recommended_next_engineering_move(funding_readiness: str) -> str:
    if funding_readiness == READONLY_CONNECTOR_READY_BALANCE_NOT_CHECKED:
        return "R164 may add a read-only balance check only if an existing safe connector helper supports it; do not implement new signing infrastructure."
    if funding_readiness == READONLY_BALANCE_CHECK_NOT_AVAILABLE:
        return "Keep funding blocked or add R164 only after a safe existing read-only balance helper exists; no ad hoc Binance signing."
    if funding_readiness == READONLY_CONNECTOR_MISSING_ENV:
        return "Operator must configure read-only env outside Codex; Codex must not edit env files or print secrets."
    return "Keep R157/R158 evidence and R162 review flows separate from funding; no live execution changes."


def _preview_ready(
    target_family: Mapping[str, Any],
    live_flag_readiness: Mapping[str, Any],
    readonly_connector: Mapping[str, Any],
) -> bool:
    return (
        target_family.get("current_mode") == "paper"
        and target_family.get("direction") == "short"
        and live_flag_readiness.get("live_flags_safe") is True
        and readonly_connector.get("connector_status") != CONNECTOR_STATUS_BLOCKED
    )


def _safety(*, allow_readonly_network_check: bool) -> dict[str, Any]:
    payload = dict(SAFETY)
    payload["network_allowed"] = bool(allow_readonly_network_check)
    return payload


def _target_from_key(lane_key: str, *, mode: str) -> dict[str, Any]:
    parts = str(lane_key).split("|")
    return {
        "lane_key": lane_key,
        "symbol": parts[0] if len(parts) > 0 else "UNKNOWN",
        "timeframe": parts[1] if len(parts) > 1 else "unknown",
        "direction": parts[2] if len(parts) > 2 else "unknown",
        "entry_mode": parts[3] if len(parts) > 3 else "unknown",
        "current_mode": mode,
    }


def _env_value(source: Mapping[str, str], key: str) -> str:
    return str(source.get(key) or "").strip()


def _env_bool_or_none(source: Mapping[str, str], key: str) -> bool | None:
    value = _env_value(source, key).lower()
    if not value:
        return None
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def _preview_api_key(api_key: str) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 8:
        return f"{api_key[:2]}...{api_key[-2:]}"
    return f"{api_key[:4]}...{api_key[-4:]}"


def _format_float(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(float(value))


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return {str(key): _sanitize(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, tuple):
        return [_sanitize(item) for item in payload]
    return payload
