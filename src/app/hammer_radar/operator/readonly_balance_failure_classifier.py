"""R165 read-only balance failure classifier and funding-gate recheck.

This module reads R164 balance-check records, classifies sanitized read-only
failure metadata, and can append a recheck record after exact confirmation. It
does not call Binance, create order payloads, mutate configuration, or enable
live execution.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.first_live_chain_runbook import read_recent_ndjson_records
from src.app.hammer_radar.operator.lane_control import SAFETY_FALSE
from src.app.hammer_radar.operator.readonly_balance_error_sanitizer import sanitize_http_error
from src.app.hammer_radar.operator.short_strategy_packet import DEFAULT_TARGET_LANE_KEY, build_short_strategy_target_family

READONLY_BALANCE_FAILURE_RECHECK_READY = "READONLY_BALANCE_FAILURE_RECHECK_READY"
READONLY_BALANCE_FAILURE_RECHECK_REJECTED = "READONLY_BALANCE_FAILURE_RECHECK_REJECTED"
READONLY_BALANCE_FAILURE_RECHECK_RECORDED = "READONLY_BALANCE_FAILURE_RECHECK_RECORDED"
READONLY_BALANCE_FAILURE_RECHECK_BLOCKED = "READONLY_BALANCE_FAILURE_RECHECK_BLOCKED"
READONLY_BALANCE_FAILURE_RECHECK_ERROR = "READONLY_BALANCE_FAILURE_RECHECK_ERROR"

HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION = "HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION"
HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE = "HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE"
HTTP_404_OR_ENDPOINT_MISMATCH = "HTTP_404_OR_ENDPOINT_MISMATCH"
FUTURES_ACCOUNT_NOT_ENABLED_OR_WRONG_ACCOUNT_TYPE = "FUTURES_ACCOUNT_NOT_ENABLED_OR_WRONG_ACCOUNT_TYPE"
READONLY_BALANCE_ENDPOINT_UNAVAILABLE = "READONLY_BALANCE_ENDPOINT_UNAVAILABLE"
NETWORK_OR_BINANCE_TEMPORARY_FAILURE = "NETWORK_OR_BINANCE_TEMPORARY_FAILURE"
ERROR_BODY_NOT_AVAILABLE = "ERROR_BODY_NOT_AVAILABLE"
UNKNOWN_HTTP_ERROR = "UNKNOWN_HTTP_ERROR"

EVENT_TYPE = "READONLY_BALANCE_FAILURE_RECHECK"
LEDGER_FILENAME = "readonly_balance_failure_rechecks.ndjson"
CONFIRM_READONLY_BALANCE_FAILURE_RECHECK_RECORDING_PHRASE = (
    "I CONFIRM READONLY BALANCE FAILURE RECHECK RECORDING ONLY; NO ORDER; NO BINANCE TRADING CALL."
)

SAFETY = {
    **SAFETY_FALSE,
    "real_order_placed": False,
    "order_payload_created": False,
    "executable_payload_created": False,
    "protective_payload_created": False,
    "signed_trading_request_created": False,
    "signed_order_request_created": False,
    "binance_order_endpoint_called": False,
    "binance_test_order_endpoint_called": False,
    "protective_order_endpoint_called": False,
    "transfer_endpoint_called": False,
    "withdraw_endpoint_called": False,
    "secrets_shown": False,
    "signature_shown": False,
    "signed_url_shown": False,
    "env_mutated": False,
    "config_written": False,
    "global_live_flags_changed": False,
    "paper_live_separation_intact": True,
}

SOURCE_SURFACES_USED = [
    "operator.readonly_balance_check R164 balance-check ledger",
    "operator.short_strategy_packet.build_short_strategy_target_family",
    f"logs/hammer_radar_forward/{LEDGER_FILENAME}",
]


def sanitize_readonly_balance_error(error: BaseException | Mapping[str, Any], *, endpoint_family: str = "unknown") -> dict[str, Any]:
    """Return only safe failure metadata from a read-only balance exception."""
    return sanitize_http_error(error, endpoint_family=endpoint_family)


def classify_readonly_balance_failure(
    *,
    last_balance_check_summary: Mapping[str, Any] | None = None,
    balance_check: Mapping[str, Any] | None = None,
) -> str:
    summary = dict(last_balance_check_summary or {})
    detail = dict(balance_check or {})
    status = _int_or_none(
        summary.get("sanitized_http_status")
        or summary.get("http_status")
        or detail.get("sanitized_http_status")
        or detail.get("http_status")
    )
    code = _int_or_none(
        summary.get("sanitized_binance_code")
        or summary.get("binance_code")
        or detail.get("sanitized_binance_code")
        or detail.get("binance_code")
    )
    message = str(
        summary.get("sanitized_binance_message")
        or summary.get("binance_message")
        or detail.get("sanitized_binance_message")
        or detail.get("binance_message")
        or ""
    ).lower()
    error_type = str(summary.get("error_type") or detail.get("error_type") or detail.get("error") or "")
    balance_readiness = str(summary.get("balance_readiness") or detail.get("funding_status") or "")
    sanitized_error_available = summary.get("sanitized_error_available")
    if sanitized_error_available is None:
        sanitized_error_available = detail.get("sanitized_error_available")
    body_available = summary.get("body_available")
    if body_available is None:
        body_available = detail.get("body_available")

    if sanitized_error_available is False and "httperror" in error_type.lower():
        return ERROR_BODY_NOT_AVAILABLE
    if body_available is False and "httperror" in error_type.lower() and code is None and not message:
        return ERROR_BODY_NOT_AVAILABLE
    if "futures account" in message and ("not" in message or "enable" in message):
        return FUTURES_ACCOUNT_NOT_ENABLED_OR_WRONG_ACCOUNT_TYPE
    if "account type" in message or "not enabled" in message:
        return FUTURES_ACCOUNT_NOT_ENABLED_OR_WRONG_ACCOUNT_TYPE
    if status in {401, 403}:
        return HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION
    if status == 400:
        return HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE
    if status == 404:
        return HTTP_404_OR_ENDPOINT_MISMATCH
    if status in {418, 429, 451} or (status is not None and 500 <= status <= 599):
        return NETWORK_OR_BINANCE_TEMPORARY_FAILURE
    if code in {-1021, -1022}:
        return HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE
    if code in {-2014, -2015}:
        return HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION
    if "timestamp" in message or "recvwindow" in message or "signature" in message:
        return HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE
    if "ip" in message or "permission" in message or "api-key" in message or "api key" in message:
        return HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION
    if "not found" in message or "endpoint" in message:
        return HTTP_404_OR_ENDPOINT_MISMATCH
    if "unavailable" in message or "temporar" in message:
        return READONLY_BALANCE_ENDPOINT_UNAVAILABLE
    if balance_readiness == "READONLY_BALANCE_CHECK_FAILED" and status is None and code is None and not message:
        return ERROR_BODY_NOT_AVAILABLE
    if "httperror" in error_type.lower() and status is None and code is None and not message:
        return ERROR_BODY_NOT_AVAILABLE
    if "httperror" in error_type.lower():
        return UNKNOWN_HTTP_ERROR
    return NETWORK_OR_BINANCE_TEMPORARY_FAILURE


def build_readonly_balance_failure_recheck(
    *,
    log_dir: str | Path | None = None,
    latest_balance_checks: int = 50,
    record_recheck: bool = False,
    confirm_readonly_balance_failure_recheck: str | None = None,
    lane_key: str = DEFAULT_TARGET_LANE_KEY,
    config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    confirmation_valid = confirm_readonly_balance_failure_recheck == CONFIRM_READONLY_BALANCE_FAILURE_RECHECK_RECORDING_PHRASE
    try:
        target = build_short_strategy_target_family(lane_key=lane_key, config_path=config_path)
        records = _load_balance_check_records(log_dir=resolved_log_dir, limit=latest_balance_checks)
        last_record = records[0] if records else {}
        last_summary = _last_balance_check_summary(last_record)
        balance_check = dict(last_record.get("balance_check") or {})
        failure_classification = classify_readonly_balance_failure(
            last_balance_check_summary=last_summary,
            balance_check=balance_check,
        )
        ready = bool(records) and last_summary.get("balance_readiness") == "READONLY_BALANCE_CHECK_FAILED"
        status = READONLY_BALANCE_FAILURE_RECHECK_READY if ready else READONLY_BALANCE_FAILURE_RECHECK_BLOCKED
        if record_recheck and not confirmation_valid:
            status = READONLY_BALANCE_FAILURE_RECHECK_REJECTED
        elif record_recheck and confirmation_valid:
            status = READONLY_BALANCE_FAILURE_RECHECK_RECORDED

        payload = {
            "status": status,
            "generated_at": generated_at.isoformat(),
            "record_recheck_requested": bool(record_recheck),
            "confirmation_valid": bool(confirmation_valid),
            "recheck_recorded": False,
            "recheck_id": None,
            "target_family": target,
            "latest_balance_checks_requested": int(latest_balance_checks),
            "last_balance_check_summary": last_summary,
            "failure_classification": failure_classification,
            "likely_causes": _likely_causes(failure_classification),
            "operator_actions": _operator_actions(failure_classification),
            "operator_checklist": _operator_checklist(failure_classification),
            "safe_recheck_commands": _safe_recheck_commands(latest_balance_checks),
            "do_not_run_yet": _do_not_run_yet(),
            "safety": dict(SAFETY),
            "source_surfaces_used": list(SOURCE_SURFACES_USED),
        }
        if record_recheck and confirmation_valid:
            record = append_readonly_balance_failure_recheck_record(payload, log_dir=resolved_log_dir)
            payload["recheck_recorded"] = True
            payload["recheck_id"] = record["recheck_id"]
            payload["ledger_path"] = str(readonly_balance_failure_recheck_records_path(resolved_log_dir))
        return _sanitize(payload)
    except Exception as exc:  # pragma: no cover - defensive operator surface
        return _sanitize(
            {
                "status": READONLY_BALANCE_FAILURE_RECHECK_ERROR,
                "generated_at": generated_at.isoformat(),
                "record_recheck_requested": bool(record_recheck),
                "confirmation_valid": bool(confirmation_valid),
                "recheck_recorded": False,
                "recheck_id": None,
                "target_family": _target_from_key(lane_key, mode="unknown"),
                "last_balance_check_summary": _empty_last_balance_check_summary(),
                "failure_classification": UNKNOWN_HTTP_ERROR,
                "likely_causes": _likely_causes(UNKNOWN_HTTP_ERROR),
                "operator_actions": _operator_actions(UNKNOWN_HTTP_ERROR),
                "operator_checklist": _operator_checklist(UNKNOWN_HTTP_ERROR),
                "safe_recheck_commands": _safe_recheck_commands(latest_balance_checks),
                "do_not_run_yet": _do_not_run_yet(),
                "error": exc.__class__.__name__,
                "safety": dict(SAFETY),
                "source_surfaces_used": list(SOURCE_SURFACES_USED),
            }
        )


def build_readonly_balance_failure_next_actions(failure_classification: str) -> dict[str, Any]:
    return {
        "failure_classification": failure_classification,
        "likely_causes": _likely_causes(failure_classification),
        "operator_actions": _operator_actions(failure_classification),
        "operator_checklist": _operator_checklist(failure_classification),
        "safe_recheck_commands": _safe_recheck_commands(50),
        "do_not_run_yet": _do_not_run_yet(),
        "safety": dict(SAFETY),
    }


def append_readonly_balance_failure_recheck_record(
    record: Mapping[str, Any],
    *,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = readonly_balance_failure_recheck_records_path(get_log_dir(log_dir, use_env=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _sanitize(
        {
            "event_type": EVENT_TYPE,
            "recheck_id": record.get("recheck_id") or f"r165_readonly_balance_failure_recheck_{uuid4().hex}",
            "recorded_at_utc": datetime.now(UTC).isoformat(),
            "status": record.get("status"),
            "generated_at": record.get("generated_at"),
            "record_recheck_requested": bool(record.get("record_recheck_requested")),
            "confirmation_valid": bool(record.get("confirmation_valid")),
            "target_family": dict(record.get("target_family") or {}),
            "last_balance_check_summary": dict(record.get("last_balance_check_summary") or {}),
            "failure_classification": record.get("failure_classification"),
            "likely_causes": list(record.get("likely_causes") or []),
            "operator_actions": list(record.get("operator_actions") or []),
            "operator_checklist": list(record.get("operator_checklist") or []),
            "safe_recheck_commands": list(record.get("safe_recheck_commands") or []),
            "do_not_run_yet": list(record.get("do_not_run_yet") or []),
            "safety": dict(record.get("safety") or SAFETY),
            "source_surfaces_used": list(record.get("source_surfaces_used") or SOURCE_SURFACES_USED),
        }
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def load_readonly_balance_failure_recheck_records(
    *,
    log_dir: str | Path | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    path = readonly_balance_failure_recheck_records_path(get_log_dir(log_dir, use_env=True))
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


def summarize_readonly_balance_failure_rechecks(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "UNKNOWN") for record in records)
    classification_counts = Counter(str(record.get("failure_classification") or "UNKNOWN") for record in records)
    latest = records[0] if records else {}
    return {
        "records_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "failure_classification_counts": dict(sorted(classification_counts.items())),
        "last_recheck_id": latest.get("recheck_id"),
        "last_failure_classification": latest.get("failure_classification"),
        "safety": dict(SAFETY),
    }


def readonly_balance_failure_recheck_records_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / LEDGER_FILENAME


def format_readonly_balance_failure_recheck_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(payload), sort_keys=True, separators=(",", ":"))


def _load_balance_check_records(*, log_dir: str | Path, limit: int) -> list[dict[str, Any]]:
    from src.app.hammer_radar.operator.readonly_balance_check import load_readonly_balance_check_records

    return load_readonly_balance_check_records(log_dir=log_dir, limit=limit)


def _last_balance_check_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    if not record:
        return _empty_last_balance_check_summary()
    balance = dict(record.get("balance_check") or {})
    return {
        "status": record.get("status") or "UNKNOWN",
        "balance_readiness": record.get("balance_readiness") or balance.get("funding_status") or "UNKNOWN",
        "network_check_attempted": bool(balance.get("network_check_attempted")),
        "balance_check_attempted": bool(balance.get("balance_check_attempted")),
        "signed_readonly_request_created": bool(balance.get("signed_readonly_request_created")),
        "signed_trading_request_created": bool((record.get("safety") or {}).get("signed_trading_request_created")),
        "error_type": balance.get("error_type") or balance.get("error"),
        "sanitized_http_status": _int_or_none(balance.get("http_status") or balance.get("sanitized_http_status")),
        "sanitized_binance_code": _int_or_none(balance.get("binance_code") or balance.get("sanitized_binance_code")),
        "sanitized_binance_message": _clean_message(balance.get("binance_message") or balance.get("sanitized_binance_message")),
        "endpoint_family": balance.get("endpoint_family") or "unknown",
        "retryable": balance.get("retryable"),
        "troubleshooting_hint": balance.get("troubleshooting_hint"),
        "sanitized_error_available": balance.get("sanitized_error_available"),
        "body_available": balance.get("body_available"),
    }


def _empty_last_balance_check_summary() -> dict[str, Any]:
    return {
        "status": "READONLY_BALANCE_CHECK_BLOCKED",
        "balance_readiness": "READONLY_BALANCE_CHECK_FAILED",
        "network_check_attempted": False,
        "balance_check_attempted": False,
        "signed_readonly_request_created": False,
        "signed_trading_request_created": False,
        "error_type": "HTTPError",
        "sanitized_http_status": None,
        "sanitized_binance_code": None,
        "sanitized_binance_message": None,
        "endpoint_family": "unknown",
        "retryable": None,
        "troubleshooting_hint": "No sanitized error metadata is available yet; rerun R164 after R166.",
        "sanitized_error_available": False,
        "body_available": False,
    }


def _likely_causes(failure_classification: str) -> list[str]:
    causes = {
        HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION: [
            "API key may lack futures/account read permission",
            "API key IP restriction may not include this host",
            "read-only key may be rejected by Binance account endpoint",
        ],
        HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE: [
            "system clock may be skewed",
            "recvWindow may be too narrow",
            "read-only signature may not match Binance expectations",
            "after R167 fixed signing, key/secret mismatch may remain possible",
        ],
        HTTP_404_OR_ENDPOINT_MISMATCH: [
            "wrong Binance endpoint may be in use",
            "spot/futures endpoint family may not match the account",
        ],
        FUTURES_ACCOUNT_NOT_ENABLED_OR_WRONG_ACCOUNT_TYPE: [
            "futures account may not be enabled",
            "connector may be using futures status for a spot-only account",
        ],
        READONLY_BALANCE_ENDPOINT_UNAVAILABLE: [
            "Binance read-only account endpoint may be unavailable",
            "regional or product availability may block the endpoint",
        ],
        NETWORK_OR_BINANCE_TEMPORARY_FAILURE: [
            "temporary Binance or network failure",
            "rate limit or regional block may require operator review",
        ],
        ERROR_BODY_NOT_AVAILABLE: [
            "HTTP status/body was not captured by the previous R164 record",
            "connector may still be hiding error details too aggressively",
        ],
        UNKNOWN_HTTP_ERROR: [
            "HTTP error did not match known read-only balance failure classes",
            "more sanitized status/code/message detail is needed",
        ],
    }
    return list(causes.get(failure_classification, causes[UNKNOWN_HTTP_ERROR]))


def _operator_actions(failure_classification: str) -> list[str]:
    actions = {
        HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION: [
            "check API key permissions include read-only account/futures status",
            "check IP restriction includes this operator host",
            "rerun readonly-balance-check only after key/IP settings are confirmed",
        ],
        HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE: [
            "check system clock synchronization",
            "check recvWindow tolerance",
            "if -1022 persists after R167, verify the API key and secret belong together",
            "rerun readonly-balance-check only after clock/signature/key-secret path is reviewed",
        ],
        HTTP_404_OR_ENDPOINT_MISMATCH: [
            "verify endpoint family is futures_account_readonly for the BTCUSDT 8m short funding path",
            "check whether this key/account should use spot_account_readonly instead",
            "do not add order, test-order, protective, transfer, or withdraw endpoints",
        ],
        FUTURES_ACCOUNT_NOT_ENABLED_OR_WRONG_ACCOUNT_TYPE: [
            "check Futures account enabled status in Binance UI",
            "check whether the API key belongs to the expected account type",
            "keep funding gate blocked until account type is confirmed",
        ],
        READONLY_BALANCE_ENDPOINT_UNAVAILABLE: [
            "wait and retry the explicit read-only balance check later",
            "check Binance status or regional product availability",
            "keep the no-network failure recheck as the default diagnostic command",
        ],
        NETWORK_OR_BINANCE_TEMPORARY_FAILURE: [
            "wait and retry the explicit read-only balance check later",
            "check rate-limit, regional block, or temporary Binance issue",
            "do not broaden the network scope beyond read-only account/balance",
        ],
        ERROR_BODY_NOT_AVAILABLE: [
            "rerun R164 after R166 so sanitized HTTP status/code/message can be captured",
            "do not inspect raw signed URLs, query strings, headers, or secrets",
            "keep funding and live execution blocked until sanitized metadata is available",
        ],
        UNKNOWN_HTTP_ERROR: [
            "review sanitized http_status, binance_code, binance_message, and endpoint_family",
            "check API key/IP, Futures enablement, system clock, recvWindow, and endpoint family",
            "keep the next recheck read-only and non-executing",
        ],
    }
    return list(actions.get(failure_classification, actions[UNKNOWN_HTTP_ERROR]))


def _operator_checklist(failure_classification: str) -> list[str]:
    checklist = [
        "key permission check",
        "IP restriction check",
        "Futures account enabled check",
        "system clock / recvWindow check",
        "endpoint family check",
    ]
    if failure_classification == HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION:
        return checklist[:2] + checklist[4:]
    if failure_classification == HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE:
        return [checklist[3], checklist[4]]
    if failure_classification == HTTP_404_OR_ENDPOINT_MISMATCH:
        return [checklist[4], checklist[2]]
    if failure_classification == FUTURES_ACCOUNT_NOT_ENABLED_OR_WRONG_ACCOUNT_TYPE:
        return [checklist[2], checklist[4], checklist[0]]
    return checklist


def _safe_recheck_commands(latest_balance_checks: int) -> list[str]:
    latest = max(int(latest_balance_checks), 1)
    return [
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward readonly-balance-failure-recheck "
            f"--latest-balance-checks {latest}"
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward readonly-balance-check "
            "--minimum-balance-usdt 44"
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward readonly-balance-check "
            "--minimum-balance-usdt 44 --allow-readonly-network-check"
        ),
        (
            "PYTHONPATH=. .venv/bin/python -m src.app.hammer_radar.operator.inspect "
            "--log-dir logs/hammer_radar_forward funding-readonly-precheck "
            "--minimum-balance-usdt 44"
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


def _read_http_error_body(error: urllib.error.HTTPError) -> str | None:
    try:
        raw = error.read()
    except Exception:
        return None
    if not raw:
        return None
    try:
        return raw.decode("utf-8", errors="replace")
    except AttributeError:
        return str(raw)


def _parse_json_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _clean_message(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    lower = text.lower()
    if "signature=" in lower:
        text = text[: lower.find("signature=")] + "signature=<redacted>"
    for marker in ("api_key", "apikey", "api-secret", "secret", "x-mbx-apikey"):
        if marker in text.lower():
            text = text.replace(marker, "<redacted>")
    return text[:240]


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


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sanitize(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        clean: dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key)
            if key_text.lower() in {"signature", "headers", "url", "query", "api_key", "api_secret", "x-mbx-apikey"}:
                continue
            clean[key_text] = _sanitize(value)
        return clean
    if isinstance(payload, list):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, tuple):
        return [_sanitize(item) for item in payload]
    if isinstance(payload, str):
        if "signature=" in payload.lower():
            return payload[: payload.lower().find("signature=")] + "signature=<redacted>"
    return payload
