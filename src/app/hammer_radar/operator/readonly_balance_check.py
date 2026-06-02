"""R164 read-only Binance balance check if safe.

This module adds an explicit operator surface for a read-only USDT balance
check. Preview mode never uses network. The optional network path is gated by
R163 read-only connector state, local live flags, and paper lane state before a
private account-status request is signed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
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
    FORBIDDEN_ACTIONS,
    REQUIRED_CONNECTOR_MODE,
    build_binance_readonly_status,
)
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.funding_readonly_precheck import (
    DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT,
    build_live_flag_readiness_summary,
)
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.short_paper_evidence_capture_loop import CONFIRM_SHORT_PAPER_CAPTURE_PHRASE
from src.app.hammer_radar.operator.short_risk_contract_apply_review import (
    CONFIRM_SHORT_RISK_CONTRACT_APPLY_REVIEW_RECORDING_PHRASE,
)
from src.app.hammer_radar.operator.readonly_balance_error_sanitizer import sanitize_http_error
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY, build_short_strategy_target_family

READONLY_BALANCE_CHECK_READY = "READONLY_BALANCE_CHECK_READY"
READONLY_BALANCE_CHECK_REJECTED = "READONLY_BALANCE_CHECK_REJECTED"
READONLY_BALANCE_CHECK_RECORDED = "READONLY_BALANCE_CHECK_RECORDED"
READONLY_BALANCE_CHECK_BLOCKED = "READONLY_BALANCE_CHECK_BLOCKED"
READONLY_BALANCE_CHECK_ERROR = "READONLY_BALANCE_CHECK_ERROR"

BALANCE_NOT_CHECKED = "BALANCE_NOT_CHECKED"
READONLY_NETWORK_NOT_ALLOWED = "READONLY_NETWORK_NOT_ALLOWED"
READONLY_CONNECTOR_MISSING_ENV = "READONLY_CONNECTOR_MISSING_ENV"
READONLY_CONNECTOR_NOT_SAFE = "READONLY_CONNECTOR_NOT_SAFE"
READONLY_BALANCE_CHECK_NOT_AVAILABLE = "READONLY_BALANCE_CHECK_NOT_AVAILABLE"
READONLY_BALANCE_CHECK_FAILED = "READONLY_BALANCE_CHECK_FAILED"
ACCOUNT_NOT_FUNDED = "ACCOUNT_NOT_FUNDED"
ACCOUNT_FUNDED_BELOW_MINIMUM = "ACCOUNT_FUNDED_BELOW_MINIMUM"
ACCOUNT_FUNDED_READY_FOR_REVIEW = "ACCOUNT_FUNDED_READY_FOR_REVIEW"
UNKNOWN_NEEDS_MANUAL_REVIEW = "UNKNOWN_NEEDS_MANUAL_REVIEW"

FUND_ACCOUNT_LATER = "FUND_ACCOUNT_LATER"
KEEP_R157_RUNNING = "KEEP_R157_RUNNING"
RUN_R158_AFTER_MORE_CAPTURES = "RUN_R158_AFTER_MORE_CAPTURES"
RUN_R165_FUNDING_GATE_RECHECK = "RUN_R165_FUNDING_GATE_RECHECK"

EVENT_TYPE = "READONLY_BALANCE_CHECK"
LEDGER_FILENAME = "readonly_balance_checks.ndjson"
CONFIRM_READONLY_BALANCE_CHECK_RECORDING_PHRASE = (
    "I CONFIRM READONLY BALANCE CHECK RECORDING ONLY; NO ORDER; NO BINANCE TRADING CALL."
)
BINANCE_FUTURES_ACCOUNT_URL = "https://fapi.binance.com/fapi/v2/account"
DEFAULT_RECV_WINDOW_MS = 5000

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_request_created": False,
    "signed_request_created_scope": "none",
    "signed_trading_request_created": False,
    "signed_order_request_created": False,
    "signed_readonly_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "signature_shown": False,
    "signed_url_shown": False,
    "paper_live_separation_intact": True,
    "env_mutated": False,
    "config_written": False,
    "risk_contract_config_written": False,
    "global_live_flags_changed": False,
}

SOURCE_SURFACES_USED = [
    "configs/hammer_radar/lane_controls.json",
    "operator.binance_readonly.build_binance_readonly_status",
    "operator.funding_readonly_precheck.build_live_flag_readiness_summary",
    "operator.short_strategy_packet.build_short_strategy_target_family",
    "private R164 read-only Binance futures account adapter",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def build_readonly_balance_check(
    *,
    log_dir: str | Path | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    minimum_balance_usdt: float = DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT,
    allow_readonly_network_check: bool = False,
    recv_window_ms: int = DEFAULT_RECV_WINDOW_MS,
    record_balance_check: bool = False,
    confirm_readonly_balance_check: str | None = None,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_readonly_balance_check == CONFIRM_READONLY_BALANCE_CHECK_RECORDING_PHRASE
    source = os.environ if env is None else env
    minimum = float(minimum_balance_usdt)
    try:
        preflight = build_readonly_balance_preflight(
            lane_key=lane_key,
            config_path=config_path,
            env=source,
        )
        balance_check = perform_readonly_balance_check_if_allowed(
            readonly_preflight=preflight,
            minimum_balance_usdt=minimum,
            allow_readonly_network_check=allow_readonly_network_check,
            recv_window_ms=recv_window_ms,
            env=source,
        )
        balance_readiness = classify_balance_readiness(
            readonly_preflight=preflight,
            balance_check=balance_check,
            allow_readonly_network_check=allow_readonly_network_check,
        )
        blockers = build_balance_check_blockers(
            target_family=preflight["target_family"],
            readonly_preflight=preflight["readonly_preflight"],
            balance_check=balance_check,
            balance_readiness=balance_readiness,
        )
        status = READONLY_BALANCE_CHECK_READY if not blockers else READONLY_BALANCE_CHECK_BLOCKED
        if record_balance_check and not confirmation_valid:
            status = READONLY_BALANCE_CHECK_REJECTED
        elif record_balance_check and confirmation_valid:
            status = READONLY_BALANCE_CHECK_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "balance_check_recorded": False,
            "balance_check_id": None,
            "record_balance_check_requested": bool(record_balance_check),
            "confirmation_valid": bool(confirmation_valid),
            "allow_readonly_network_check": bool(allow_readonly_network_check),
            "target_family": preflight["target_family"],
            "readonly_preflight": preflight["readonly_preflight"],
            "balance_check": balance_check,
            "balance_readiness": balance_readiness,
            "blockers": blockers,
            "recommended_next_operator_move": _recommended_next_operator_move(balance_readiness),
            "recommended_next_engineering_move": _recommended_next_engineering_move(balance_readiness),
            "safe_commands": _safe_commands(preflight["target_family"]["lane_key"], minimum),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": _safety(
                network_allowed=allow_readonly_network_check,
                signed_readonly_request_created=bool(balance_check.get("signed_readonly_request_created")),
            ),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_balance_check and confirmation_valid:
            record = append_readonly_balance_check_record(payload, log_dir=resolved_log_dir)
            payload["balance_check_recorded"] = True
            payload["balance_check_id"] = record["balance_check_id"]
            payload["ledger_path"] = str(readonly_balance_check_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        target = _target_from_key(lane_key, mode="unknown")
        return _sanitize(
            {
                "status": READONLY_BALANCE_CHECK_ERROR,
                "generated_at": generated_at.isoformat(),
                "balance_check_recorded": False,
                "balance_check_id": None,
                "record_balance_check_requested": bool(record_balance_check),
                "confirmation_valid": bool(confirmation_valid),
                "allow_readonly_network_check": bool(allow_readonly_network_check),
                "target_family": target,
                "readonly_preflight": _empty_readonly_preflight(),
                "balance_check": _empty_balance_check(
                    minimum_balance_usdt=minimum,
                    network_check_requested=allow_readonly_network_check,
                    funding_status=UNKNOWN_NEEDS_MANUAL_REVIEW,
                ),
                "balance_readiness": UNKNOWN_NEEDS_MANUAL_REVIEW,
                "blockers": ["R164 read-only balance check build error must be fixed before funding review"],
                "recommended_next_operator_move": KEEP_R157_RUNNING,
                "recommended_next_engineering_move": "Fix R164 balance-check builder error; do not mutate env, config, lane mode, or live flags.",
                "safe_commands": _safe_commands(lane_key, minimum),
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": _safety(
                    network_allowed=allow_readonly_network_check,
                    signed_readonly_request_created=False,
                ),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_readonly_balance_preflight(
    *,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    config_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    source = os.environ if env is None else env
    target = build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)
    connector = build_binance_readonly_status(env=source)
    live_flags = build_live_flag_readiness_summary(env=source)
    allowed = list(connector.get("allowed_actions") or [])
    if "read_account_status" not in allowed and connector.get("api_key_present") and connector.get("api_secret_present"):
        allowed.append("read_account_status")
    readonly_preflight = {
        "connector_status": connector.get("connector_status") or "UNKNOWN",
        "connector_mode": connector.get("connector_mode") or "n/a",
        "api_key_present": bool(connector.get("api_key_present")),
        "api_secret_present": bool(connector.get("api_secret_present")),
        "api_key_preview": connector.get("api_key_preview") or "n/a",
        "live_flags_safe": bool(live_flags.get("live_flags_safe")),
        "secrets_shown": False,
        "allowed_actions": allowed,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "live_flag_readiness": live_flags,
        "blockers": list(connector.get("blockers") or []),
        "warnings": list(connector.get("warnings") or []),
    }
    return {
        "target_family": target,
        "readonly_preflight": readonly_preflight,
    }


def build_balance_check_blockers(
    *,
    target_family: Mapping[str, Any],
    readonly_preflight: Mapping[str, Any],
    balance_check: Mapping[str, Any],
    balance_readiness: str,
) -> list[str]:
    blockers: list[str] = []
    if target_family.get("lane_key") != DEFAULT_TARGET_LANE_KEY:
        blockers.append("target lane differs from R164 BTCUSDT 8m short family")
    if target_family.get("current_mode") != "paper":
        blockers.append("target lane must remain paper")
    if target_family.get("direction") != "short":
        blockers.append("target lane is not short")
    if readonly_preflight.get("connector_mode") != REQUIRED_CONNECTOR_MODE:
        blockers.append("BINANCE_CONNECTOR_MODE is not read_only")
    if not readonly_preflight.get("api_key_present"):
        blockers.append("BINANCE_API_KEY missing")
    if not readonly_preflight.get("api_secret_present"):
        blockers.append("BINANCE_API_SECRET missing")
    if readonly_preflight.get("live_flags_safe") is not True:
        blockers.append("live flags are not safe for read-only balance check")
    blockers.extend(str(item) for item in readonly_preflight.get("blockers") or [] if item)
    if balance_readiness != ACCOUNT_FUNDED_READY_FOR_REVIEW:
        blockers.append(f"balance readiness is {balance_readiness}")
    return _dedupe(blockers)


def perform_readonly_balance_check_if_allowed(
    *,
    readonly_preflight: Mapping[str, Any],
    minimum_balance_usdt: float = DEFAULT_MINIMUM_BALANCE_REQUIRED_ESTIMATE_USDT,
    allow_readonly_network_check: bool = False,
    recv_window_ms: int = DEFAULT_RECV_WINDOW_MS,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    preflight = dict(readonly_preflight.get("readonly_preflight") or readonly_preflight)
    source = os.environ if env is None else env
    if not allow_readonly_network_check:
        return _empty_balance_check(
            minimum_balance_usdt=minimum_balance_usdt,
            network_check_requested=False,
            funding_status=READONLY_NETWORK_NOT_ALLOWED,
        )
    unsafe_reason = _unsafe_preflight_reason(preflight)
    if unsafe_reason:
        return _empty_balance_check(
            minimum_balance_usdt=minimum_balance_usdt,
            network_check_requested=True,
            funding_status=READONLY_CONNECTOR_NOT_SAFE if preflight.get("connector_status") != CONNECTOR_STATUS_MISSING_ENV else READONLY_CONNECTOR_MISSING_ENV,
            blocked_reason=unsafe_reason,
        )

    try:
        account = _request_binance_futures_account_snapshot(env=source, recv_window_ms=recv_window_ms)
    except Exception as exc:
        result = _empty_balance_check(
            minimum_balance_usdt=minimum_balance_usdt,
            network_check_requested=True,
            funding_status=READONLY_BALANCE_CHECK_FAILED,
        )
        sanitized_error = sanitize_http_error(exc, endpoint_family="futures_account_readonly")
        result.update(
            {
                "network_check_attempted": True,
                "balance_check_attempted": True,
                "signed_readonly_request_created": True,
                "error": exc.__class__.__name__,
                **readonly_account_signature_diagnostics(recv_window_ms=recv_window_ms),
                **sanitized_error,
            }
        )
        return result

    available, wallet = _extract_asset_balances(account, asset="USDT")
    funding_status = _classify_amount(available_balance_usdt=available, minimum_balance_usdt=minimum_balance_usdt)
    return {
        "network_check_requested": True,
        "network_check_attempted": True,
        "balance_check_attempted": True,
        "asset": "USDT",
        "available_balance_usdt": available,
        "wallet_balance_usdt": wallet,
        "minimum_balance_required_estimate_usdt": float(minimum_balance_usdt),
        "funding_ready": funding_status == ACCOUNT_FUNDED_READY_FOR_REVIEW,
        "funding_status": funding_status,
        "signed_readonly_request_created": True,
        **readonly_account_signature_diagnostics(recv_window_ms=recv_window_ms),
    }


def classify_balance_readiness(
    *,
    readonly_preflight: Mapping[str, Any] | None = None,
    balance_check: Mapping[str, Any] | None = None,
    allow_readonly_network_check: bool = False,
) -> str:
    preflight = dict((readonly_preflight or {}).get("readonly_preflight") or readonly_preflight or {})
    balance = dict(balance_check or {})
    connector_status = preflight.get("connector_status")
    if preflight.get("live_flags_safe") is not True:
        return READONLY_CONNECTOR_NOT_SAFE
    if connector_status == CONNECTOR_STATUS_BLOCKED:
        return READONLY_CONNECTOR_NOT_SAFE
    if connector_status == CONNECTOR_STATUS_MISSING_ENV or not (
        preflight.get("api_key_present") and preflight.get("api_secret_present")
    ):
        return READONLY_CONNECTOR_MISSING_ENV
    if not allow_readonly_network_check:
        return READONLY_NETWORK_NOT_ALLOWED
    if balance.get("funding_status") in {
        READONLY_CONNECTOR_MISSING_ENV,
        READONLY_CONNECTOR_NOT_SAFE,
        READONLY_BALANCE_CHECK_NOT_AVAILABLE,
        READONLY_BALANCE_CHECK_FAILED,
        ACCOUNT_NOT_FUNDED,
        ACCOUNT_FUNDED_BELOW_MINIMUM,
        ACCOUNT_FUNDED_READY_FOR_REVIEW,
    }:
        return str(balance["funding_status"])
    if connector_status == CONNECTOR_STATUS_READY:
        return BALANCE_NOT_CHECKED
    return UNKNOWN_NEEDS_MANUAL_REVIEW


def append_readonly_balance_check_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = readonly_balance_check_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "balance_check_id": record.get("balance_check_id") or f"r164_readonly_balance_check_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_balance_check_requested": bool(record.get("record_balance_check_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "allow_readonly_network_check": bool(record.get("allow_readonly_network_check")),
            "target_family": dict(record.get("target_family") or {}),
            "readonly_preflight": dict(record.get("readonly_preflight") or {}),
            "balance_check": dict(record.get("balance_check") or {}),
            "balance_readiness": record.get("balance_readiness"),
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


def load_readonly_balance_check_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = readonly_balance_check_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_readonly_balance_checks(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    readiness_counts = Counter(str(record.get("balance_readiness") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "balance_readiness_counts": dict(sorted(readiness_counts.items())),
        "last_balance_check_id": latest.get("balance_check_id"),
        "last_target_lane": (latest.get("target_family") or {}).get("lane_key") if isinstance(latest.get("target_family"), Mapping) else None,
        "safety": _safety(network_allowed=False, signed_readonly_request_created=False),
    }


def readonly_balance_check_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_readonly_balance_check_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def build_readonly_account_query(params: Mapping[str, Any]) -> str:
    """Build the exact deterministic query string used for read-only account signing."""
    return urllib.parse.urlencode([(key, params[key]) for key in sorted(params)])


def sign_readonly_account_query(query_string: str, secret: str) -> str:
    """Sign a read-only account query string without including signature in the payload."""
    return hmac.new(str(secret).encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()


def build_readonly_signed_account_url_safely(
    *,
    endpoint_url: str,
    secret: str,
    timestamp_ms: int,
    recv_window_ms: int = DEFAULT_RECV_WINDOW_MS,
) -> str:
    params = {
        "timestamp": str(int(timestamp_ms)),
        "recvWindow": str(int(recv_window_ms)),
    }
    query = build_readonly_account_query(params)
    signature = sign_readonly_account_query(query, secret)
    return f"{endpoint_url}?{query}&signature={signature}"


def readonly_account_signature_diagnostics(*, recv_window_ms: int = DEFAULT_RECV_WINDOW_MS) -> dict[str, Any]:
    return {
        "endpoint_family": "futures_account_readonly",
        "signed_request_created_scope": "readonly_account_status_only",
        "timestamp_used": True,
        "recv_window_ms": int(recv_window_ms),
        "signed_query_param_keys": ["recvWindow", "timestamp"],
        "signature_shown": False,
        "signed_url_shown": False,
    }


def _request_binance_futures_account_snapshot(
    *,
    env: Mapping[str, str],
    recv_window_ms: int = DEFAULT_RECV_WINDOW_MS,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    api_key = str(env.get(ENV_API_KEY) or "").strip()
    api_secret = str(env.get(ENV_API_SECRET) or "").strip()
    if not api_key or not api_secret:
        raise RuntimeError("missing_readonly_credentials")
    url = build_readonly_signed_account_url_safely(
        endpoint_url=BINANCE_FUTURES_ACCOUNT_URL,
        secret=api_secret,
        timestamp_ms=int(time.time() * 1000),
        recv_window_ms=recv_window_ms,
    )
    request = urllib.request.Request(url, headers={"X-MBX-APIKEY": api_key}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError("unexpected_readonly_account_response")
    return decoded


def _extract_asset_balances(account: Mapping[str, Any], *, asset: str) -> tuple[float | None, float | None]:
    target_asset = asset.upper()
    for row in account.get("assets") or []:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("asset") or "").upper() != target_asset:
            continue
        return _float_or_none(row.get("availableBalance")), _float_or_none(row.get("walletBalance"))
    return None, None


def _classify_amount(*, available_balance_usdt: float | None, minimum_balance_usdt: float) -> str:
    if available_balance_usdt is None:
        return UNKNOWN_NEEDS_MANUAL_REVIEW
    if available_balance_usdt <= 0:
        return ACCOUNT_NOT_FUNDED
    if available_balance_usdt < float(minimum_balance_usdt):
        return ACCOUNT_FUNDED_BELOW_MINIMUM
    return ACCOUNT_FUNDED_READY_FOR_REVIEW


def _unsafe_preflight_reason(preflight: Mapping[str, Any]) -> str | None:
    if preflight.get("connector_status") != CONNECTOR_STATUS_READY:
        return f"connector_status is {preflight.get('connector_status') or 'UNKNOWN'}"
    if preflight.get("connector_mode") != REQUIRED_CONNECTOR_MODE:
        return "connector mode is not read_only"
    if preflight.get("live_flags_safe") is not True:
        return "live flags are not safe"
    if not preflight.get("api_key_present") or not preflight.get("api_secret_present"):
        return "read-only credentials are missing"
    if "read_account_status" not in set(preflight.get("allowed_actions") or []):
        return "read_account_status is not allowed by read-only preflight"
    return None


def _empty_readonly_preflight() -> dict[str, Any]:
    return {
        "connector_status": "UNKNOWN",
        "connector_mode": "n/a",
        "api_key_present": False,
        "api_secret_present": False,
        "api_key_preview": "n/a",
        "live_flags_safe": False,
        "secrets_shown": False,
        "allowed_actions": [],
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "live_flag_readiness": {},
        "blockers": [],
        "warnings": [],
    }


def _empty_balance_check(
    *,
    minimum_balance_usdt: float,
    network_check_requested: bool,
    funding_status: str,
    blocked_reason: str | None = None,
) -> dict[str, Any]:
    payload = {
        "network_check_requested": bool(network_check_requested),
        "network_check_attempted": False,
        "balance_check_attempted": False,
        "asset": "USDT",
        "available_balance_usdt": None,
        "wallet_balance_usdt": None,
        "minimum_balance_required_estimate_usdt": float(minimum_balance_usdt),
        "funding_ready": False,
        "funding_status": funding_status,
        "signed_readonly_request_created": False,
    }
    if blocked_reason:
        payload["blocked_reason"] = blocked_reason
    return payload


def _safe_commands(lane_key: str, minimum_balance_usdt: float) -> list[str]:
    minimum = _format_float(minimum_balance_usdt)
    return [
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward readonly-balance-check "
            f'--lane-key "{lane_key}" --minimum-balance-usdt {minimum}'
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward readonly-balance-check "
            f'--lane-key "{lane_key}" --minimum-balance-usdt {minimum} --allow-readonly-network-check'
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward funding-readonly-precheck "
            f'--lane-key "{lane_key}" --minimum-balance-usdt {minimum}'
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


def _recommended_next_operator_move(balance_readiness: str) -> str:
    if balance_readiness in {READONLY_CONNECTOR_MISSING_ENV, ACCOUNT_NOT_FUNDED, ACCOUNT_FUNDED_BELOW_MINIMUM}:
        return FUND_ACCOUNT_LATER
    if balance_readiness == ACCOUNT_FUNDED_READY_FOR_REVIEW:
        return RUN_R165_FUNDING_GATE_RECHECK
    if balance_readiness in {READONLY_NETWORK_NOT_ALLOWED, READONLY_BALANCE_CHECK_FAILED, READONLY_CONNECTOR_NOT_SAFE}:
        return KEEP_R157_RUNNING
    return RUN_R158_AFTER_MORE_CAPTURES


def _recommended_next_engineering_move(balance_readiness: str) -> str:
    if balance_readiness == ACCOUNT_FUNDED_READY_FOR_REVIEW:
        return "Run R165 to sync the recorded balance result with R158 evidence and R162 contract review; do not enable live execution."
    if balance_readiness == READONLY_NETWORK_NOT_ALLOWED:
        return "Operator may rerun R164 with --allow-readonly-network-check after reviewing tests and safety output."
    if balance_readiness == READONLY_CONNECTOR_MISSING_ENV:
        return "Operator must configure read-only env outside Codex; Codex must not edit env files or print secrets."
    if balance_readiness == READONLY_CONNECTOR_NOT_SAFE:
        return "Keep the balance check blocked until read-only mode and disabled live flags are proven safe."
    return "Keep R157/R158 evidence and R162 review flows separate from funding; no live execution changes."


def _safety(*, network_allowed: bool, signed_readonly_request_created: bool) -> dict[str, Any]:
    payload = dict(SAFETY)
    payload["network_allowed"] = bool(network_allowed)
    payload["signed_readonly_request_created"] = bool(signed_readonly_request_created)
    payload["signed_request_created_scope"] = "readonly_account_status_only" if signed_readonly_request_created else "none"
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


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
