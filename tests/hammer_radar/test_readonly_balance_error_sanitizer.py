from __future__ import annotations

import json
import urllib.error
from io import BytesIO

from src.app.hammer_radar.operator.readonly_balance_error_sanitizer import (
    build_sanitized_readonly_error,
    classify_http_status_hint,
    extract_binance_error_code,
    extract_binance_error_message,
    redact_sensitive_error_fields,
    sanitize_http_error,
)


def test_sanitize_httperror_extracts_timestamp_code_and_message_without_signed_material() -> None:
    error = urllib.error.HTTPError(
        "https://fapi.binance.com/fapi/v2/account?timestamp=1&signature=raw-signature-secret",
        400,
        "Bad Request",
        {"X-MBX-APIKEY": "abcd1234wxyz5678"},
        BytesIO(b'{"code":-1021,"msg":"Timestamp for this request is outside of the recvWindow."}'),
    )

    payload = sanitize_http_error(error, endpoint_family="futures_account_readonly")
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["error_type"] == "HTTPError"
    assert payload["http_status"] == 400
    assert payload["binance_code"] == -1021
    assert payload["binance_message"] == "Timestamp for this request is outside of the recvWindow."
    assert payload["endpoint_family"] == "futures_account_readonly"
    assert payload["retryable"] is True
    assert payload["sanitized_error_available"] is True
    assert "raw-signature-secret" not in rendered
    assert "abcd1234wxyz5678" not in rendered
    assert "https://fapi.binance.com" not in rendered


def test_sanitize_httperror_no_body_keeps_error_body_not_available_path() -> None:
    error = urllib.error.HTTPError(
        "https://fapi.binance.com/fapi/v2/account?timestamp=1&signature=raw-signature-secret",
        400,
        "Bad Request",
        {},
        BytesIO(b""),
    )

    payload = sanitize_http_error(error, endpoint_family="futures_account_readonly")

    assert payload["http_status"] == 400
    assert payload["binance_code"] is None
    assert payload["binance_message"] is None
    assert payload["body_available"] is False
    assert payload["sanitized_error_available"] is True


def test_extract_binance_error_fields_from_json_string() -> None:
    raw = '{"code":-2015,"msg":"Invalid API-key, IP, or permissions."}'

    assert extract_binance_error_code(raw) == -2015
    assert extract_binance_error_message(raw) == "Invalid API-key, IP, or permissions."


def test_classify_http_status_hint_sets_retryable_and_hint() -> None:
    hint = classify_http_status_hint(http_status=429, binance_code=None, binance_message="rate limit", endpoint_family="futures_account_readonly", sanitized_error_available=True)

    assert hint["status_hint"] == "NETWORK_OR_BINANCE_TEMPORARY_FAILURE"
    assert hint["retryable"] is True
    assert "retry" in hint["troubleshooting_hint"].lower()


def test_redact_sensitive_error_fields_removes_keys_and_query_material() -> None:
    payload = redact_sensitive_error_fields(
        {
            "url": "https://fapi.binance.com/fapi/v2/account?timestamp=1&signature=raw-signature-secret",
            "headers": {"X-MBX-APIKEY": "abcd1234wxyz5678"},
            "message": "bad request ?timestamp=1&signature=raw-signature-secret API secret secret-not-rendered",
            "safe": "kept",
        }
    )
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["safe"] == "kept"
    assert "?<redacted_query>" in payload["message"]
    assert "<redacted_secret>" in payload["message"]
    assert "raw-signature-secret" not in rendered
    assert "abcd1234wxyz5678" not in rendered
    assert "secret-not-rendered" not in rendered


def test_build_sanitized_readonly_error_normalizes_mapping_fields() -> None:
    payload = build_sanitized_readonly_error(
        {
            "error": "HTTPError",
            "sanitized_http_status": "404",
            "sanitized_binance_code": None,
            "sanitized_binance_message": "endpoint not found",
            "endpoint_family": "unexpected_family",
        },
        endpoint_family="futures_account_readonly",
    )

    assert payload["error_type"] == "HTTPError"
    assert payload["http_status"] == 404
    assert payload["endpoint_family"] == "unknown"
    assert payload["troubleshooting_hint"]
