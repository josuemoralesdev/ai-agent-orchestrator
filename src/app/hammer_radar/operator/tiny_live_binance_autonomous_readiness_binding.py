"""R279 Binance readiness binding for autonomous one-shot.

Default usage is local status only. The optional network path delegates to the
existing R242 public read-only precision / mark-price gate after the exact
confirmation phrase. This module does not sign requests, call private trading
endpoints, place orders, change leverage, change margin mode, or enable live
execution.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.binance_readonly import build_binance_readonly_status
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_autonomous_armed_dry_run import (
    CONFIG_PATH as AUTONOMOUS_ARMING_CONFIG_PATH,
    build_autonomous_dry_run_arming_status,
)
from src.app.hammer_radar.operator.tiny_live_binance_readonly_precision_mark_price_gate import (
    CONFIRM_TINY_LIVE_BINANCE_READONLY_FETCH_PHRASE,
    build_quantity_preview_from_readonly_data,
    build_tiny_live_binance_readonly_precision_mark_price_gate,
    load_tiny_live_binance_readonly_precision_mark_price_records,
)
from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import (
    load_tiny_live_risk_contract_config,
)

EVENT_TYPE = "BINANCE_AUTONOMOUS_ONE_SHOT_READINESS_BINDING"
CREATED_BY_PHASE = "R279_BINANCE_READINESS_BINDING_FOR_AUTONOMOUS_ONE_SHOT"
LEDGER_FILENAME = "tiny_live_binance_autonomous_readiness_binding.ndjson"
OFFICIAL_LANE_KEY = "BTCUSDT|8m|short|ladder_close_50_618"
SYMBOL = "BTCUSDT"

BINANCE_READINESS_NOT_REQUESTED = "BINANCE_READINESS_NOT_REQUESTED"
BINANCE_READINESS_BLOCKED = "BINANCE_READINESS_BLOCKED"
BINANCE_READINESS_READY = "BINANCE_READINESS_READY"

CONFIRM_BINANCE_READONLY_ACCOUNT_POSITION_PHRASE = (
    "I CONFIRM BINANCE READONLY ACCOUNT POSITION CHECK ONLY; NO ORDER; NO TEST ORDER; "
    "NO LEVERAGE CHANGE; NO MARGIN CHANGE."
)

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "lane_controls_written": False,
    "live_config_written": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "hmac_signature_created": False,
    "signed_request_created": False,
    "signed_order_request_created": False,
    "signed_trading_request_created": False,
    "signed_readonly_request_created": False,
    "submit_allowed": False,
    "submit_attempted": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "binance_account_endpoint_called": False,
    "binance_position_risk_endpoint_called": False,
    "binance_exchange_info_endpoint_called": False,
    "binance_mark_price_endpoint_called": False,
    "leverage_change_called": False,
    "margin_change_called": False,
    "cancel_order_endpoint_called": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "private_binance_endpoint_called": False,
    "signed_binance_endpoint_called": False,
    "network_allowed": False,
    "api_key_used": False,
    "api_secret_used": False,
    "signature_created": False,
    "kill_switch_disabled": False,
    "secrets_read": False,
    "secrets_shown": False,
    "secret_values_in_output": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
    "final_command_available": False,
    "real_order_forbidden": True,
}

SOURCE_SURFACES_USED = [
    "src/app/hammer_radar/operator/tiny_live_binance_readonly_precision_mark_price_gate.py",
    "src/app/hammer_radar/operator/tiny_live_autonomous_armed_dry_run.py",
    "src/app/hammer_radar/operator/binance_readonly.py",
    "configs/hammer_radar/autonomous_arming_state.json",
    "configs/hammer_radar/tiny_live_risk_contracts.json",
    "logs/hammer_radar_forward/tiny_live_binance_readonly_precision_mark_price_gate.ndjson",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_tiny_live_binance_autonomous_readiness_binding(
    *,
    log_dir: str | Path | None = None,
    fetch_binance_readonly_precision_mark_price: bool = False,
    confirm_tiny_live_binance_readonly_fetch: str | None = None,
    fetch_binance_readonly_account_position: bool = False,
    confirm_binance_readonly_account_position: str | None = None,
    risk_contract_config_path: str | Path | None = None,
    autonomous_arming_config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    account_position_snapshot: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    urlopen_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source_env = os.environ if env is None else env
    risk_path = Path(risk_contract_config_path) if risk_contract_config_path is not None else None
    arming_path = (
        Path(autonomous_arming_config_path)
        if autonomous_arming_config_path is not None
        else AUTONOMOUS_ARMING_CONFIG_PATH
    )
    readonly_requested = bool(fetch_binance_readonly_precision_mark_price or fetch_binance_readonly_account_position)
    precision_confirmation_valid = (
        confirm_tiny_live_binance_readonly_fetch == CONFIRM_TINY_LIVE_BINANCE_READONLY_FETCH_PHRASE
    )
    account_position_confirmation_valid = (
        confirm_binance_readonly_account_position == CONFIRM_BINANCE_READONLY_ACCOUNT_POSITION_PHRASE
    )
    safety = dict(SAFETY)

    credentials = _credentials_summary(source_env)
    risk_contract = _risk_contract_summary(risk_path)
    latest_record = load_latest_binance_autonomous_readiness_binding(log_dir=resolved_log_dir)
    precision_binding = _precision_binding(
        log_dir=resolved_log_dir,
        fetch_requested=fetch_binance_readonly_precision_mark_price,
        confirmation_valid=precision_confirmation_valid,
        confirmation=confirm_tiny_live_binance_readonly_fetch,
        risk_contract_config_path=risk_path,
        urlopen_func=urlopen_func,
    )
    safety.update(precision_binding["safety_delta"])
    account_position = _account_position_binding(
        fetch_requested=fetch_binance_readonly_account_position,
        confirmation_valid=account_position_confirmation_valid,
        account_position_snapshot=account_position_snapshot,
    )
    exchange = _exchange_minimum_summary(
        precision_binding["precision_snapshot"],
        precision_binding["mark_price_snapshot"],
        configured_notional_cap_usdt=risk_contract["configured_notional_cap_usdt"],
    )
    readiness_blockers = _readiness_blockers(
        readonly_requested=readonly_requested,
        fetch_binance_readonly_precision_mark_price=fetch_binance_readonly_precision_mark_price,
        precision_confirmation_valid=precision_confirmation_valid,
        fetch_binance_readonly_account_position=fetch_binance_readonly_account_position,
        account_position=account_position,
        exchange=exchange,
        risk_contract=risk_contract,
    )
    matrix = _autonomous_one_shot_matrix(
        log_dir=resolved_log_dir,
        arming_config_path=arming_path,
        binance_readiness_ready=not readiness_blockers and readonly_requested,
        exchange=exchange,
        account_position=account_position,
    )
    if not readonly_requested:
        status = BINANCE_READINESS_NOT_REQUESTED
    elif readiness_blockers:
        status = BINANCE_READINESS_BLOCKED
    else:
        status = BINANCE_READINESS_READY

    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "status": status,
            "generated_at": generated_at.isoformat(),
            "created_by_phase": CREATED_BY_PHASE,
            "binding_supported": True,
            "readonly_requested": readonly_requested,
            "readonly_confirmation_valid": bool(
                (
                    fetch_binance_readonly_precision_mark_price
                    and precision_confirmation_valid
                )
                or (
                    fetch_binance_readonly_account_position
                    and account_position_confirmation_valid
                )
            ),
            "credentials_configured": credentials["credentials_configured"],
            "credential_summary": credentials,
            "secrets_shown": False,
            "symbol": SYMBOL,
            "account_balance_checked": account_position["account_balance_checked"],
            "exchange_info_checked": precision_binding["exchange_info_checked"],
            "mark_price_checked": precision_binding["mark_price_checked"],
            "position_risk_checked": account_position["position_risk_checked"],
            "leverage_checked": account_position["leverage_checked"],
            "margin_mode_checked": account_position["margin_mode_checked"],
            "configured_notional_cap_usdt": risk_contract["configured_notional_cap_usdt"],
            "configured_leverage": risk_contract["configured_leverage"],
            "configured_margin_budget_usdt": risk_contract["configured_margin_budget_usdt"],
            "exchange_min_notional": exchange["exchange_min_notional"],
            "exchange_min_quantity": exchange["exchange_min_quantity"],
            "exchange_step_size": exchange["exchange_step_size"],
            "candidate_quantity_at_cap": exchange["candidate_quantity_at_cap"],
            "candidate_notional_at_cap": exchange["candidate_notional_at_cap"],
            "cap_clears_exchange_minimum": exchange["cap_clears_exchange_minimum"],
            "wallet_supports_minimum_tiny": account_position["wallet_supports_minimum_tiny"],
            "open_position_conflict": account_position["open_position_conflict"],
            "account_position_readiness_status": account_position["account_position_readiness_status"],
            "readiness_blockers": readiness_blockers,
            "latest_record": latest_record,
            "precision_mark_price_binding": precision_binding["summary"],
            "account_position_binding": account_position,
            "autonomous_one_shot_readiness_matrix": matrix,
            "safe_next_readonly_commands": safe_next_readonly_commands(),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
            "safety": safety,
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
    )
    if readonly_requested:
        payload = append_binance_autonomous_readiness_binding(payload, log_dir=resolved_log_dir)
    return payload


def safe_next_readonly_commands() -> list[str]:
    return [
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward tiny-live-binance-autonomous-readiness"
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward tiny-live-binance-autonomous-readiness "
            "--fetch-binance-readonly-precision-mark-price "
            "--confirm-tiny-live-binance-readonly-fetch "
            "\"I CONFIRM BINANCE READONLY PRECISION MARK PRICE CHECK ONLY; NO ORDER; NO SIGNATURE; NO PRIVATE ENDPOINT.\""
        ),
        (
            "Account/position read-only is blocked in R279 unless a future phase provides a complete safe "
            "account+position-risk adapter; no private endpoint is called by this binding."
        ),
    ]


def append_binance_autonomous_readiness_binding(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = binance_autonomous_readiness_binding_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            **dict(record),
            "event_type": EVENT_TYPE,
            "readiness_binding_id": record.get("readiness_binding_id")
            or f"r279_binance_autonomous_readiness_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_binance_autonomous_readiness_binding_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = binance_autonomous_readiness_binding_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=16_777_216)]


def load_latest_binance_autonomous_readiness_binding(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    records = load_binance_autonomous_readiness_binding_records(log_dir=log_dir, limit=1)
    if not records:
        return {}
    record = dict(records[0])
    return {
        "readiness_binding_id": record.get("readiness_binding_id"),
        "recorded_at_utc": record.get("recorded_at_utc"),
        "status": record.get("status"),
        "readonly_requested": record.get("readonly_requested") is True,
        "exchange_info_checked": record.get("exchange_info_checked") is True,
        "mark_price_checked": record.get("mark_price_checked") is True,
        "cap_clears_exchange_minimum": record.get("cap_clears_exchange_minimum"),
        "wallet_supports_minimum_tiny": record.get("wallet_supports_minimum_tiny"),
        "open_position_conflict": record.get("open_position_conflict"),
        "readiness_blockers": list(record.get("readiness_blockers") or []),
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
    }


def binance_autonomous_readiness_binding_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_binance_autonomous_readiness_binding_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _credentials_summary(env: Mapping[str, str]) -> dict[str, Any]:
    status = build_binance_readonly_status(env=env)
    return {
        "connector_status": status.get("connector_status"),
        "connector_mode": status.get("connector_mode"),
        "api_key_present": bool(status.get("api_key_present")),
        "api_secret_present": bool(status.get("api_secret_present")),
        "credentials_configured": bool(status.get("api_key_present") and status.get("api_secret_present")),
        "live_trading_env": status.get("live_trading_env"),
        "secrets_shown": False,
        "raw_secret_values_included": False,
        "blockers": list(status.get("blockers") or []),
        "warnings": list(status.get("warnings") or []),
    }


def _risk_contract_summary(risk_contract_config_path: Path | None) -> dict[str, Any]:
    try:
        config = load_tiny_live_risk_contract_config(
            risk_contract_config_path,
            official_lane_key=OFFICIAL_LANE_KEY,
        )
    except Exception:
        config = {}
    contract = config.get("matching_risk_contract") if isinstance(config.get("matching_risk_contract"), Mapping) else {}
    cap = _number(contract.get("max_position_notional_usdt") or contract.get("max_notional_usdt")) or 80.0
    leverage = _number(contract.get("leverage")) or 10.0
    margin = _number(contract.get("margin_budget_usdt") or contract.get("tiny_live_margin_usdt")) or 8.0
    return {
        "risk_contract_found": bool(contract),
        "configured_notional_cap_usdt": cap,
        "configured_leverage": leverage,
        "configured_margin_budget_usdt": margin,
        "leverage_expectation_met": leverage == 10.0,
        "margin_budget_expectation_met": margin == 8.0,
        "margin_mode_expectation": "ISOLATED_REQUIRED",
    }


def _precision_binding(
    *,
    log_dir: str | Path,
    fetch_requested: bool,
    confirmation_valid: bool,
    confirmation: str | None,
    risk_contract_config_path: Path | None,
    urlopen_func: Callable[..., Any] | None,
) -> dict[str, Any]:
    if fetch_requested:
        payload = build_tiny_live_binance_readonly_precision_mark_price_gate(
            log_dir=log_dir,
            fetch_binance_readonly=True,
            confirm_tiny_live_binance_readonly_fetch=confirmation,
            risk_contract_config_path=risk_contract_config_path,
            urlopen_func=urlopen_func,
        )
    else:
        records = load_tiny_live_binance_readonly_precision_mark_price_records(log_dir=log_dir, limit=1)
        payload = records[0] if records else {}
    readonly = payload.get("binance_readonly_result") if isinstance(payload.get("binance_readonly_result"), Mapping) else {}
    precision = readonly.get("precision_snapshot") if isinstance(readonly.get("precision_snapshot"), Mapping) else {}
    mark = readonly.get("mark_price_snapshot") if isinstance(readonly.get("mark_price_snapshot"), Mapping) else {}
    fetched = payload.get("readonly_fetch_performed") is True
    return {
        "precision_snapshot": precision,
        "mark_price_snapshot": mark,
        "exchange_info_checked": fetched and precision.get("found") is True,
        "mark_price_checked": fetched and mark.get("found") is True,
        "summary": {
            "fetch_requested": bool(fetch_requested),
            "confirmation_valid": bool(confirmation_valid),
            "status": payload.get("status"),
            "readonly_fetch_performed": fetched,
            "precision_snapshot_found": precision.get("found") is True,
            "mark_price_found": mark.get("found") is True,
            "order_endpoint_called": False,
            "test_order_endpoint_called": False,
            "signed_request_created": False,
        },
        "safety_delta": {
            "binance_exchange_info_endpoint_called": bool(
                fetch_requested
                and fetched
                and (payload.get("safety") or {}).get("binance_exchange_info_endpoint_called") is True
            ),
            "binance_mark_price_endpoint_called": bool(
                fetch_requested
                and fetched
                and (payload.get("safety") or {}).get("binance_mark_price_endpoint_called") is True
            ),
            "network_allowed": bool(fetch_requested and fetched),
        },
    }


def _account_position_binding(
    *,
    fetch_requested: bool,
    confirmation_valid: bool,
    account_position_snapshot: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if account_position_snapshot:
        wallet = _number(account_position_snapshot.get("available_balance_usdt"))
        conflict = account_position_snapshot.get("open_position_conflict")
        return {
            "fetch_requested": bool(fetch_requested),
            "confirmation_valid": bool(confirmation_valid),
            "account_position_readiness_status": "MOCKED_SAFE_TEST_SNAPSHOT",
            "account_balance_checked": True,
            "position_risk_checked": True,
            "leverage_checked": True,
            "margin_mode_checked": True,
            "available_balance_usdt": wallet,
            "wallet_supports_minimum_tiny": account_position_snapshot.get("wallet_supports_minimum_tiny"),
            "open_position_conflict": bool(conflict),
            "leverage_matches_expectation": account_position_snapshot.get("leverage_matches_expectation") is True,
            "margin_mode_matches_expectation": account_position_snapshot.get("margin_mode_matches_expectation") is True,
            "readiness_blockers": [str(item) for item in account_position_snapshot.get("readiness_blockers") or []],
            "no_private_endpoint_called_by_r279": True,
            "secrets_shown": False,
        }
    if fetch_requested and not confirmation_valid:
        status = "CONFIRMATION_INVALID"
        blocker = "readonly_account_position_confirmation_invalid"
    elif fetch_requested:
        status = "NOT_IMPLEMENTED_SAFELY"
        blocker = "readonly_account_position_check_not_available"
    else:
        status = "NOT_REQUESTED"
        blocker = "readonly_account_position_not_requested"
    return {
        "fetch_requested": bool(fetch_requested),
        "confirmation_valid": bool(confirmation_valid),
        "account_position_readiness_status": status,
        "account_balance_checked": False,
        "position_risk_checked": False,
        "leverage_checked": False,
        "margin_mode_checked": False,
        "available_balance_usdt": None,
        "wallet_supports_minimum_tiny": None,
        "open_position_conflict": None,
        "leverage_matches_expectation": None,
        "margin_mode_matches_expectation": None,
        "readiness_blockers": [blocker],
        "no_private_endpoint_called_by_r279": True,
        "secrets_shown": False,
    }


def _exchange_minimum_summary(
    precision: Mapping[str, Any],
    mark: Mapping[str, Any],
    *,
    configured_notional_cap_usdt: float,
) -> dict[str, Any]:
    quantity = build_quantity_preview_from_readonly_data(
        notional_cap_usdt=configured_notional_cap_usdt,
        precision_snapshot=precision,
        mark_price_snapshot=mark,
    )
    blockers = list(quantity.get("blocked_by") or [])
    return {
        "exchange_min_notional": precision.get("min_notional"),
        "exchange_min_quantity": precision.get("min_qty"),
        "exchange_step_size": precision.get("step_size"),
        "candidate_quantity_at_cap": quantity.get("quantity_rounded"),
        "candidate_notional_at_cap": quantity.get("notional_after_rounding"),
        "cap_clears_exchange_minimum": quantity.get("can_compute") is True,
        "exchange_minimum_ready": quantity.get("can_compute") is True,
        "blockers": blockers,
    }


def _readiness_blockers(
    *,
    readonly_requested: bool,
    fetch_binance_readonly_precision_mark_price: bool,
    precision_confirmation_valid: bool,
    fetch_binance_readonly_account_position: bool,
    account_position: Mapping[str, Any],
    exchange: Mapping[str, Any],
    risk_contract: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not readonly_requested:
        blockers.append("readonly_binance_readiness_not_requested")
    if fetch_binance_readonly_precision_mark_price and not precision_confirmation_valid:
        blockers.append("readonly_precision_mark_price_confirmation_invalid")
    if not exchange.get("exchange_minimum_ready"):
        blockers.extend(str(item) for item in exchange.get("blockers") or ["exchange_minimum_not_verified"])
    if fetch_binance_readonly_account_position and account_position.get("confirmation_valid") is not True:
        blockers.append("readonly_account_position_confirmation_invalid")
    blockers.extend(str(item) for item in account_position.get("readiness_blockers") or [] if item)
    if account_position.get("wallet_supports_minimum_tiny") is not True:
        blockers.append("wallet_supports_minimum_tiny_not_verified")
    if account_position.get("open_position_conflict") is not False:
        blockers.append("no_conflicting_position_not_verified")
    if risk_contract.get("configured_notional_cap_usdt") != 80.0:
        blockers.append("configured_notional_cap_not_80")
    if risk_contract.get("configured_leverage") != 10.0:
        blockers.append("configured_leverage_not_10")
    if risk_contract.get("configured_margin_budget_usdt") != 8.0:
        blockers.append("configured_margin_budget_not_8")
    return _dedupe(blockers)


def _autonomous_one_shot_matrix(
    *,
    log_dir: str | Path,
    arming_config_path: Path,
    binance_readiness_ready: bool,
    exchange: Mapping[str, Any],
    account_position: Mapping[str, Any],
) -> dict[str, Any]:
    arming = build_autonomous_dry_run_arming_status(log_dir=log_dir, config_path=arming_config_path)
    live_qualified = list(arming.get("live_qualified_lane_keys") or [])
    return {
        "autonomous_dry_run_arming_supported": True,
        "real_candidate_binding_supported": True,
        "dry_run_arming_default_off": arming.get("any_lane_auto_armed") is False,
        "live_qualified_lanes_available": bool(live_qualified),
        "binance_readiness_binding_supported": True,
        "binance_readiness_ready": bool(binance_readiness_ready),
        "exchange_minimum_ready": exchange.get("exchange_minimum_ready") is True,
        "wallet_ready": account_position.get("wallet_supports_minimum_tiny") is True,
        "no_conflicting_position": account_position.get("open_position_conflict") is False,
        "no_prior_live_submit": True,
        "final_command_available": False,
        "one_shot_live_allowed": False,
        "real_order_forbidden": True,
    }


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
