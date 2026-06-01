"""Sanitize read-only Binance balance errors for operator diagnostics."""

from __future__ import annotations

import json
import re
import urllib.error
from collections.abc import Mapping
from typing import Any

ENDPOINT_FUTURES_ACCOUNT_READONLY = "futures_account_readonly"
ENDPOINT_SPOT_ACCOUNT_READONLY = "spot_account_readonly"
ENDPOINT_UNKNOWN = "unknown"

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "api-secret",
    "api_secret",
    "secret",
    "signature",
    "x-mbx-apikey",
    "headers",
    "url",
    "query",
)
_QUERY_RE = re.compile(r"\?[^ \t\r\n\"']+")
_SIGNATURE_RE = re.compile(r"signature=[^&\s\"']+", re.IGNORECASE)
_API_KEY_RE = re.compile(r"(?i)x-mbx-apikey[^,.;\s]*")
_SECRET_RE = re.compile(r"(?i)(api[-_ ]?secret|secret)[^,.;\s]*")


def sanitize_http_error(error: BaseException | Mapping[str, Any], *, endpoint_family: str = ENDPOINT_UNKNOWN) -> dict[str, Any]:
    """Return safe read-only HTTP error metadata without signed request material."""
    if isinstance(error, Mapping):
        return build_sanitized_readonly_error(error, endpoint_family=endpoint_family)

    status = _int_or_none(getattr(error, "code", None) or getattr(error, "status", None))
    code: int | None = None
    message: str | None = None
    body_available = False
    error_type = error.__class__.__name__

    if isinstance(error, urllib.error.HTTPError):
        body = _read_http_error_body(error)
        body_available = bool(body)
        parsed = _parse_json_object(body)
        if parsed:
            code = extract_binance_error_code(parsed)
            message = extract_binance_error_message(parsed)
        elif body:
            message = _clean_message(body)
    else:
        message = _clean_message(str(error) or None)

    return build_sanitized_readonly_error(
        {
            "error_type": error_type,
            "http_status": status,
            "binance_code": code,
            "binance_message": message,
            "endpoint_family": endpoint_family,
            "body_available": body_available,
        },
        endpoint_family=endpoint_family,
    )


def extract_binance_error_code(value: Mapping[str, Any] | str | bytes | None) -> int | None:
    parsed = _coerce_json_object(value)
    if not parsed:
        return None
    return _int_or_none(parsed.get("code"))


def extract_binance_error_message(value: Mapping[str, Any] | str | bytes | None) -> str | None:
    parsed = _coerce_json_object(value)
    if not parsed:
        return _clean_message(value)
    return _clean_message(parsed.get("msg") or parsed.get("message"))


def classify_http_status_hint(
    *,
    http_status: int | None = None,
    binance_code: int | None = None,
    binance_message: str | None = None,
    endpoint_family: str = ENDPOINT_UNKNOWN,
    sanitized_error_available: bool | None = None,
) -> dict[str, Any]:
    status = _int_or_none(http_status)
    code = _int_or_none(binance_code)
    message = str(binance_message or "").lower()
    endpoint = str(endpoint_family or ENDPOINT_UNKNOWN)
    available = bool(sanitized_error_available)

    classification = "UNKNOWN_HTTP_ERROR"
    retryable: bool | None = False
    hint = "Review sanitized HTTP status, Binance code/message, and endpoint family."

    if not available and status is None and code is None and not message:
        classification = "ERROR_BODY_NOT_AVAILABLE"
        retryable = None
        hint = "R164 did not capture sanitized HTTP status, Binance code, or Binance message; rerun the read-only check after R166."
    elif code in {-1021, -1022} or status == 400 or "timestamp" in message or "recvwindow" in message or "signature" in message:
        classification = "HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE"
        retryable = code == -1021 or "timestamp" in message or "recvwindow" in message
        hint = "Check system clock synchronization, recvWindow, and the read-only request signature path."
    elif status in {401, 403} or code in {-2014, -2015} or "ip" in message or "permission" in message or "api-key" in message or "api key" in message:
        classification = "HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION"
        retryable = False
        hint = "Check API key read-only permission and IP allowlist for this host."
    elif status == 404 or "not found" in message or "endpoint" in message:
        classification = "HTTP_404_OR_ENDPOINT_MISMATCH"
        retryable = False
        hint = "Check whether the futures or spot account read-only endpoint family matches the account."
    elif "futures account" in message and ("not" in message or "enable" in message):
        classification = "FUTURES_ACCOUNT_NOT_ENABLED_OR_WRONG_ACCOUNT_TYPE"
        retryable = False
        hint = "Check whether Futures is enabled for the key/account and whether the endpoint family is correct."
    elif "account type" in message or "not enabled" in message:
        classification = "FUTURES_ACCOUNT_NOT_ENABLED_OR_WRONG_ACCOUNT_TYPE"
        retryable = False
        hint = "Check whether the selected account type supports this read-only account endpoint."
    elif status in {418, 429, 451} or (status is not None and 500 <= status <= 599):
        classification = "NETWORK_OR_BINANCE_TEMPORARY_FAILURE"
        retryable = True
        hint = "Wait and retry the explicit read-only check; review rate limit, regional block, or Binance availability."
    elif "unavailable" in message or "temporar" in message:
        classification = "READONLY_BALANCE_ENDPOINT_UNAVAILABLE"
        retryable = True
        hint = "Read-only account endpoint appears unavailable; retry later or verify Binance product availability."
    elif endpoint not in {ENDPOINT_FUTURES_ACCOUNT_READONLY, ENDPOINT_SPOT_ACCOUNT_READONLY, ENDPOINT_UNKNOWN}:
        classification = "HTTP_404_OR_ENDPOINT_MISMATCH"
        retryable = False
        hint = "Unknown endpoint family reported; verify the read-only account endpoint wiring."

    return {
        "status_hint": classification,
        "retryable": retryable,
        "troubleshooting_hint": hint,
    }


def redact_sensitive_error_fields(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        clean: dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                continue
            clean[key_text] = redact_sensitive_error_fields(value)
        return clean
    if isinstance(payload, list):
        return [redact_sensitive_error_fields(item) for item in payload]
    if isinstance(payload, tuple):
        return [redact_sensitive_error_fields(item) for item in payload]
    if isinstance(payload, bytes):
        return _clean_message(payload.decode("utf-8", errors="replace"))
    if isinstance(payload, str):
        return _clean_message(payload)
    return payload


def build_sanitized_readonly_error(
    error: BaseException | Mapping[str, Any],
    *,
    endpoint_family: str = ENDPOINT_UNKNOWN,
) -> dict[str, Any]:
    if not isinstance(error, Mapping):
        return sanitize_http_error(error, endpoint_family=endpoint_family)

    status = _int_or_none(error.get("http_status") or error.get("sanitized_http_status"))
    code = _int_or_none(error.get("binance_code") or error.get("sanitized_binance_code"))
    message = _clean_message(error.get("binance_message") or error.get("sanitized_binance_message"))
    family = _clean_endpoint_family(error.get("endpoint_family") or endpoint_family)
    error_type = str(error.get("error_type") or error.get("error") or "UNKNOWN")
    body_available = bool(error.get("body_available"))
    sanitized_error_available = bool(status is not None or code is not None or message)
    hint = classify_http_status_hint(
        http_status=status,
        binance_code=code,
        binance_message=message,
        endpoint_family=family,
        sanitized_error_available=sanitized_error_available,
    )
    payload = {
        "error_type": error_type,
        "http_status": status,
        "binance_code": code,
        "binance_message": message,
        "endpoint_family": family,
        "body_available": body_available,
        "retryable": hint["retryable"],
        "troubleshooting_hint": hint["troubleshooting_hint"],
        "sanitized_error_available": sanitized_error_available,
    }
    return redact_sensitive_error_fields(payload)


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


def _coerce_json_object(value: Mapping[str, Any] | str | bytes | None) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return _parse_json_object(value)


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
    text = _SIGNATURE_RE.sub("signature=<redacted>", text)
    text = _QUERY_RE.sub("?<redacted_query>", text)
    text = _API_KEY_RE.sub("<redacted_api_key>", text)
    text = _SECRET_RE.sub("<redacted_secret>", text)
    return text[:240]


def _clean_endpoint_family(value: Any) -> str:
    family = str(value or ENDPOINT_UNKNOWN)
    if family in {ENDPOINT_FUTURES_ACCOUNT_READONLY, ENDPOINT_SPOT_ACCOUNT_READONLY}:
        return family
    return ENDPOINT_UNKNOWN


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(part in lower for part in _SENSITIVE_KEY_PARTS)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
