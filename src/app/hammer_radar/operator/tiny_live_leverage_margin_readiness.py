"""R283 leverage/margin readiness interpretation for one-shot tiny live.

This module interprets already-allowed read-only account/position context. It
never calls order, test-order, leverage, margin-type, or other mutation
endpoints and never marks the final one-shot command available.
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
from src.app.hammer_radar.operator.binance_account_read_env_contract import (
    KNOWN_SAFE_READONLY_ENV_FILE,
    load_allowed_readonly_env_file,
)
from src.app.hammer_radar.operator.binance_account_position_readonly import (
    build_account_position_readiness,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.tiny_live_live_authorization_write_gate import (
    load_tiny_live_risk_contract_config,
)

EVENT_TYPE = "TINY_LIVE_LEVERAGE_MARGIN_READINESS"
CREATED_BY_PHASE = "R283_LEVERAGE_MARGIN_READINESS_INTERPRETATION_FOR_ONE_SHOT_TINY_LIVE"
LEDGER_FILENAME = "tiny_live_leverage_margin_readiness.ndjson"
SYMBOL = "BTCUSDT"
OFFICIAL_LANE_KEY = "BTCUSDT|8m|short|ladder_close_50_618"
CONFIRM_BINANCE_READONLY_ACCOUNT_POSITION_PHRASE = (
    "I CONFIRM BINANCE READONLY ACCOUNT POSITION CHECK ONLY; NO ORDER; NO TEST ORDER; "
    "NO LEVERAGE CHANGE; NO MARGIN CHANGE."
)

LEVERAGE_MARGIN_READY = "LEVERAGE_MARGIN_READY"
LEVERAGE_MARGIN_BLOCKED = "LEVERAGE_MARGIN_BLOCKED"
LEVERAGE_MARGIN_NOT_CHECKED = "LEVERAGE_MARGIN_NOT_CHECKED"
LEVERAGE_MARGIN_REQUIRES_MANUAL_OPERATOR_REVIEW = "LEVERAGE_MARGIN_REQUIRES_MANUAL_OPERATOR_REVIEW"

EXACT_MATCH = "EXACT_MATCH"
ZERO_POSITION_METADATA_MISMATCH = "ZERO_POSITION_METADATA_MISMATCH"
NONZERO_POSITION_MISMATCH = "NONZERO_POSITION_MISMATCH"
UNKNOWN_FIELDS = "UNKNOWN_FIELDS"
MUTATION_REQUIRED = "MUTATION_REQUIRED"
NOT_CHECKED = "NOT_CHECKED"

SAFETY = {
    **SAFETY_FALSE,
    "env_written": False,
    "env_mutated": False,
    "config_written": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "submit_allowed": False,
    "submit_attempted": False,
    "order_placed": False,
    "real_order_placed": False,
    "execution_attempted": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "signed_trading_request_created": False,
    "signed_order_request_created": False,
    "leverage_change_called": False,
    "margin_change_called": False,
    "mutation_performed": False,
    "kill_switch_disabled": False,
    "paper_live_separation_intact": True,
    "signature_shown": False,
    "signed_url_shown": False,
    "secrets_shown": False,
    "secret_values_in_output": False,
    "final_command_available": False,
    "real_order_forbidden": True,
}


def build_tiny_live_leverage_margin_readiness(
    *,
    log_dir: str | Path | None = None,
    fetch_binance_readonly_account_position: bool = False,
    confirm_binance_readonly_account_position: str | None = None,
    load_discovered_binance_readonly_env: bool = False,
    binance_readonly_env_file: str | Path | None = None,
    account_position_snapshot: Mapping[str, Any] | None = None,
    risk_contract_config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    urlopen_func: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    loaded_runtime_env_summary = None
    if load_discovered_binance_readonly_env or binance_readonly_env_file is not None:
        loaded_runtime_env_summary = load_allowed_readonly_env_file(
            binance_readonly_env_file or KNOWN_SAFE_READONLY_ENV_FILE
        )
    source_env = os.environ if env is None else env
    risk_contract = _risk_contract_summary(
        Path(risk_contract_config_path) if risk_contract_config_path is not None else None
    )
    confirmation_valid = (
        confirm_binance_readonly_account_position == CONFIRM_BINANCE_READONLY_ACCOUNT_POSITION_PHRASE
    )
    if account_position_snapshot is not None:
        account_position = _snapshot_account_position(account_position_snapshot)
    else:
        account_position = build_account_position_readiness(
            fetch_requested=fetch_binance_readonly_account_position,
            confirmation_valid=confirmation_valid,
            env=source_env,
            symbol=SYMBOL,
            configured_margin_budget_usdt=risk_contract["configured_margin_budget_usdt"],
            configured_notional_cap_usdt=risk_contract["configured_notional_cap_usdt"],
            configured_leverage=risk_contract["configured_leverage"],
            urlopen_func=urlopen_func,
        )
    packet = interpret_leverage_margin_readiness(
        account_position=account_position,
        configured_leverage=risk_contract["configured_leverage"],
        configured_margin_mode="isolated",
        fetch_requested=fetch_binance_readonly_account_position or account_position_snapshot is not None,
    )
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "created_by_phase": CREATED_BY_PHASE,
            "generated_at": generated_at.isoformat(),
            "symbol": SYMBOL,
            "fetch_requested": bool(fetch_binance_readonly_account_position),
            "confirmation_valid": bool(confirmation_valid),
            "loaded_env_file_status": (loaded_runtime_env_summary or {}).get("loaded_env_file_status"),
            "loaded_env_names": (loaded_runtime_env_summary or {}).get("loaded_env_names", []),
            "loaded_secret_names_redacted": True,
            "env_file_values_printed": False,
            "account_position_readiness_status": account_position.get("account_position_readiness_status"),
            "account_position_binding": account_position,
            "safe_next_cli_command": safe_leverage_margin_readiness_cli_command(),
            **packet,
        }
    )
    if fetch_binance_readonly_account_position or account_position_snapshot is not None:
        payload = append_tiny_live_leverage_margin_readiness(payload, log_dir=resolved_log_dir)
    return payload


def interpret_leverage_margin_readiness(
    *,
    account_position: Mapping[str, Any],
    configured_leverage: float = 10.0,
    configured_margin_mode: str = "isolated",
    fetch_requested: bool = True,
) -> dict[str, Any]:
    safety = dict(SAFETY)
    _merge_safety(safety, account_position.get("safety") if isinstance(account_position.get("safety"), Mapping) else {})
    current_leverage = _number(
        account_position.get("current_leverage")
        if account_position.get("current_leverage") is not None
        else account_position.get("leverage")
    )
    current_margin_mode = _normalize_margin_mode(
        account_position.get("current_margin_mode")
        if account_position.get("current_margin_mode") is not None
        else account_position.get("margin_type")
    )
    position_amt = _number(account_position.get("btcusdt_position_amt"))
    position_notional = _number(account_position.get("btcusdt_position_notional"))
    zero_position = (
        position_amt is not None
        and position_notional is not None
        and abs(position_amt) == 0.0
        and abs(position_notional) == 0.0
    )
    open_conflict = account_position.get("open_position_conflict")
    if open_conflict is None and position_amt is not None and position_notional is not None:
        open_conflict = not zero_position
    leverage_matches = (
        current_leverage == float(configured_leverage)
        if current_leverage is not None
        else account_position.get("leverage_matches_expectation")
    )
    margin_matches = (
        current_margin_mode == _normalize_margin_mode(configured_margin_mode)
        if current_margin_mode
        else account_position.get("margin_mode_matches_expectation")
    )
    fields_unknown = current_leverage is None or not current_margin_mode
    mismatch = leverage_matches is not True or margin_matches is not True
    blockers: list[str] = []
    manual_only_adjustment_required = False
    mutation_required = False
    if not fetch_requested or account_position.get("position_risk_checked") is not True:
        status = LEVERAGE_MARGIN_NOT_CHECKED
        classification = NOT_CHECKED
        blockers.append("readonly_account_position_not_checked")
    elif fields_unknown:
        status = LEVERAGE_MARGIN_BLOCKED
        classification = UNKNOWN_FIELDS
        blockers.append("leverage_or_margin_fields_unavailable")
        manual_only_adjustment_required = True
        mutation_required = True
    elif not mismatch:
        status = LEVERAGE_MARGIN_READY
        classification = EXACT_MATCH
    elif open_conflict is True or zero_position is False:
        status = LEVERAGE_MARGIN_BLOCKED
        classification = NONZERO_POSITION_MISMATCH
        blockers.append("nonzero_btcusdt_position_with_leverage_margin_mismatch")
        manual_only_adjustment_required = True
        mutation_required = True
    elif zero_position is True:
        status = LEVERAGE_MARGIN_REQUIRES_MANUAL_OPERATOR_REVIEW
        classification = ZERO_POSITION_METADATA_MISMATCH
        blockers.append("zero_position_leverage_margin_metadata_mismatch_requires_manual_review")
        manual_only_adjustment_required = True
        mutation_required = True
    else:
        status = LEVERAGE_MARGIN_BLOCKED
        classification = MUTATION_REQUIRED
        blockers.append("leverage_margin_expectation_requires_manual_adjustment")
        manual_only_adjustment_required = True
        mutation_required = True
    blockers.extend(str(item) for item in account_position.get("readiness_blockers") or [] if item)
    if safety["leverage_change_called"] or safety["margin_change_called"] or safety["mutation_performed"]:
        status = LEVERAGE_MARGIN_BLOCKED
        classification = MUTATION_REQUIRED
        blockers.append("unsafe_mutation_endpoint_was_called")
        manual_only_adjustment_required = True
        mutation_required = True
    live_blocked = status != LEVERAGE_MARGIN_READY
    return {
        "status": status,
        "configured_leverage": float(configured_leverage),
        "configured_margin_mode": _normalize_margin_mode(configured_margin_mode),
        "current_leverage": current_leverage,
        "current_margin_mode": current_margin_mode,
        "leverage_matches_expectation": leverage_matches,
        "margin_mode_matches_expectation": margin_matches,
        "btcusdt_position_amt": position_amt,
        "btcusdt_position_notional": position_notional,
        "btcusdt_position_side": account_position.get("btcusdt_position_side"),
        "open_position_conflict": open_conflict,
        "zero_position": zero_position,
        "mismatch_classification": classification,
        "manual_only_adjustment_required": manual_only_adjustment_required,
        "mutation_required": mutation_required,
        "mutation_performed": False,
        "leverage_change_called": False,
        "margin_change_called": False,
        "live_submit_blocked_by_leverage_margin": live_blocked,
        "readiness_blockers": _dedupe(blockers),
        "recommended_operator_move": _recommended_operator_move(status, classification),
        "safe_manual_next_steps": _safe_manual_next_steps(status, classification),
        "final_command_available": False,
        "submit_allowed": False,
        "real_order_forbidden": True,
        "safety": safety,
    }


def safe_leverage_margin_readiness_cli_command() -> str:
    return (
        "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
        "--log-dir logs/hammer_radar_forward tiny-live-leverage-margin-readiness "
        "--load-discovered-binance-readonly-env --fetch-binance-readonly-account-position "
        "--confirm-binance-readonly-account-position "
        "\"I CONFIRM BINANCE READONLY ACCOUNT POSITION CHECK ONLY; NO ORDER; NO TEST ORDER; "
        "NO LEVERAGE CHANGE; NO MARGIN CHANGE.\""
    )


def append_tiny_live_leverage_margin_readiness(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = tiny_live_leverage_margin_readiness_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            **dict(record),
            "readiness_record_id": record.get("readiness_record_id")
            or f"r283_leverage_margin_readiness_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "final_command_available": False,
            "submit_allowed": False,
            "real_order_forbidden": True,
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_tiny_live_leverage_margin_readiness_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = tiny_live_leverage_margin_readiness_records_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    if limit <= 0:
        with path.open("r", encoding="utf-8") as handle:
            return [_sanitize(json.loads(line)) for line in handle if line.strip()]
    return [_sanitize(record) for record in read_recent_ndjson_records(path, limit=limit, max_bytes=8_388_608)]


def load_latest_tiny_live_leverage_margin_readiness(
    *, log_dir: str | Path | None = None
) -> dict[str, Any]:
    records = load_tiny_live_leverage_margin_readiness_records(log_dir=log_dir, limit=1)
    return records[0] if records else {}


def tiny_live_leverage_margin_readiness_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_tiny_live_leverage_margin_readiness_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _risk_contract_summary(risk_contract_config_path: Path | None) -> dict[str, Any]:
    try:
        config = load_tiny_live_risk_contract_config(
            risk_contract_config_path,
            official_lane_key=OFFICIAL_LANE_KEY,
        )
    except Exception:
        config = {}
    contract = config.get("matching_risk_contract") if isinstance(config.get("matching_risk_contract"), Mapping) else {}
    return {
        "configured_notional_cap_usdt": _number(
            contract.get("max_position_notional_usdt") or contract.get("max_notional_usdt")
        )
        or 80.0,
        "configured_leverage": _number(contract.get("leverage")) or 10.0,
        "configured_margin_budget_usdt": _number(
            contract.get("margin_budget_usdt") or contract.get("tiny_live_margin_usdt")
        )
        or 8.0,
    }


def _snapshot_account_position(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    current_margin_mode = snapshot.get("current_margin_mode", snapshot.get("margin_type"))
    current_leverage = snapshot.get("current_leverage", snapshot.get("leverage"))
    return {
        **dict(snapshot),
        "position_risk_checked": snapshot.get("position_risk_checked", True),
        "account_balance_checked": snapshot.get("account_balance_checked", True),
        "current_leverage": current_leverage,
        "current_margin_mode": current_margin_mode,
        "leverage": current_leverage,
        "margin_type": current_margin_mode,
        "safety": dict(snapshot.get("safety") if isinstance(snapshot.get("safety"), Mapping) else SAFETY),
        "secrets_shown": False,
    }


def _merge_safety(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key in target:
        if key in source:
            target[key] = bool(source.get(key))
    target["mutation_performed"] = False
    target["leverage_change_called"] = False
    target["margin_change_called"] = False
    target["binance_order_endpoint_called"] = False
    target["binance_test_order_endpoint_called"] = False
    target["signed_trading_request_created"] = False
    target["signed_order_request_created"] = False
    target["submit_allowed"] = False
    target["final_command_available"] = False
    target["real_order_forbidden"] = True
    target["secrets_shown"] = False
    target["secret_values_in_output"] = False


def _recommended_operator_move(status: str, classification: str) -> str:
    if status == LEVERAGE_MARGIN_READY:
        return "LEVERAGE_MARGIN_EXACT_MATCH_RECORDED_CONTINUE_READINESS_REVIEW_ONLY"
    if classification == ZERO_POSITION_METADATA_MISMATCH:
        return "MANUAL_OPERATOR_REVIEW_REQUIRED_BEFORE_ANY_ONE_SHOT_LIVE_GATE"
    if classification == NOT_CHECKED:
        return "RUN_SAFE_READONLY_ACCOUNT_POSITION_CHECK_BEFORE_ONE_SHOT_REVIEW"
    return "BLOCK_ONE_SHOT_LIVE_UNTIL_LEVERAGE_MARGIN_EXPECTATION_IS_PROVEN_WITHOUT_CODE_MUTATION"


def _safe_manual_next_steps(status: str, classification: str) -> list[str]:
    if status == LEVERAGE_MARGIN_READY:
        return ["Keep final command unavailable in R283 and continue the pre-live review chain."]
    if classification == NOT_CHECKED:
        return [safe_leverage_margin_readiness_cli_command()]
    return [
        "Do not submit a live order from this repo.",
        "Do not let Codex call leverage or margin mutation endpoints.",
        "If exchange settings need adjustment, perform it manually outside this code path and rerun the read-only check.",
    ]


def _normalize_margin_mode(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"isolated", "isolated_required"}:
        return "isolated"
    if text == "crossed":
        return "cross"
    return text


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if str(key) not in {"_signed_query", "signature", "query", "signed_url"}
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
