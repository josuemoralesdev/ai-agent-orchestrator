"""Default-blocked Binance Futures tiny-live connector for Hammer Radar.

R43 adds connector gating, audit records, and sanitized payload previews. It
does not read or expose secrets, does not sign payloads in dry-run mode, and
does not place a live order unless an explicit future adapter is supplied after
all live gates are enabled.
"""

from __future__ import annotations

import json
import os
import hmac
import hashlib
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from src.app.hammer_radar.operator.archive import get_log_dir
from src.app.hammer_radar.operator.binance_live_status import (
    ENV_ALLOW_LIVE_ORDERS,
    ENV_API_KEY,
    ENV_API_SECRET,
    ENV_BINANCE_LIVE_ENABLED,
    ENV_GLOBAL_KILL_SWITCH,
    ENV_LIVE_EXECUTION_ENABLED,
)
from src.app.hammer_radar.operator.live_approval import load_live_approval_requests
from src.app.hammer_radar.operator.live_preflight import (
    PREFLIGHT_READY_BUT_EXECUTION_DISABLED,
    PROMOTED_STRATEGY_KEY,
    build_promoted_strategy_preflight,
)

DRY_RUN_ONLY = "DRY_RUN_ONLY"
TEST_ORDER_ONLY = "TEST_ORDER_ONLY"
LIVE_ORDER_ENABLED = "LIVE_ORDER_ENABLED"
CONNECTOR_MODES = {DRY_RUN_ONLY, TEST_ORDER_ONLY, LIVE_ORDER_ENABLED}

ENV_CONNECTOR_MODE = "HAMMER_BINANCE_CONNECTOR_MODE"
ENV_ALLOWED_SYMBOLS = "HAMMER_LIVE_ALLOWED_SYMBOLS"
ENV_MAX_POSITION_USD = "HAMMER_LIVE_MAX_POSITION_USD"
ENV_MAX_LEVERAGE = "HAMMER_LIVE_MAX_LEVERAGE"
ENV_MARGIN_MODE = "HAMMER_LIVE_MARGIN_MODE"
ENV_REQUIRE_EXACT_APPROVAL = "HAMMER_LIVE_REQUIRE_EXACT_APPROVAL"
ENV_MAX_TRADES_PER_DAY = "HAMMER_LIVE_MAX_TRADES_PER_DAY"
ENV_TEST_ORDER_NETWORK_ENABLED = "HAMMER_BINANCE_TEST_ORDER_NETWORK_ENABLED"
ENV_BINANCE_BASE_URL = "HAMMER_BINANCE_BASE_URL"
ENV_RECV_WINDOW = "HAMMER_BINANCE_RECV_WINDOW"
ENV_PROTECTIVE_ORDERS_REQUIRED = "HAMMER_PROTECTIVE_ORDERS_REQUIRED"
ENV_PROTECTIVE_ORDERS_ENABLED = "HAMMER_PROTECTIVE_ORDERS_ENABLED"
ENV_PROTECTIVE_ORDER_MODE = "HAMMER_PROTECTIVE_ORDER_MODE"
ENV_PROTECTIVE_STOP_TYPE = "HAMMER_PROTECTIVE_STOP_TYPE"
ENV_PROTECTIVE_TAKE_PROFIT_TYPE = "HAMMER_PROTECTIVE_TAKE_PROFIT_TYPE"

ATTEMPTS_FILENAME = "binance_live_connector_attempts.ndjson"
PROTECTIVE_ATTEMPTS_FILENAME = "binance_protective_order_attempts.ndjson"
CONNECTOR_NAME = "binance_futures_tiny_live"
TEST_ORDER_ENDPOINT = "/fapi/v1/order/test"
REAL_ORDER_ENDPOINT = "/fapi/v1/order"
PROTECTIVE_ORDER_ENDPOINT = REAL_ORDER_ENDPOINT
DEFAULT_BASE_URL = "https://fapi.binance.com"
DEFAULT_RECV_WINDOW = 5000
DEFAULT_ALLOWED_SYMBOLS = ["BTCUSDT"]
DEFAULT_MAX_POSITION_USD = 44.0
DEFAULT_MAX_LEVERAGE = 3.0
DEFAULT_MARGIN_MODE = "isolated"
DEFAULT_MAX_TRADES_PER_DAY = 1
PROTECTIVE_PREVIEW_ONLY = "PREVIEW_ONLY"
PROTECTIVE_TEST_ONLY = "TEST_ONLY"
LIVE_PROTECTIVE_ENABLED = "LIVE_PROTECTIVE_ENABLED"
PROTECTIVE_ORDER_MODES = {PROTECTIVE_PREVIEW_ONLY, PROTECTIVE_TEST_ONLY, LIVE_PROTECTIVE_ENABLED}
DEFAULT_PROTECTIVE_STOP_TYPE = "STOP_MARKET"
DEFAULT_PROTECTIVE_TAKE_PROFIT_TYPE = "TAKE_PROFIT_MARKET"
DEFAULT_PROTECTIVE_WORKING_TYPE = "MARK_PRICE"


class BinanceOrderAdapter(Protocol):
    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit a sanitized payload through an explicit future adapter."""


class SignedTestOrderAdapter(Protocol):
    def send_test_order(self, signed_request: dict[str, Any]) -> dict[str, Any]:
        """Send a signed Binance USD-M Futures test-order request."""


class SignedLiveOrderAdapter(Protocol):
    def send_live_order(self, signed_request: dict[str, Any]) -> dict[str, Any]:
        """Send a signed Binance USD-M Futures live order request."""


class ProtectiveOrderAdapter(Protocol):
    def send_protective_orders(self, signed_requests: list[dict[str, Any]]) -> dict[str, Any]:
        """Send or validate signed protective stop/take-profit requests."""


class MockSignedTestOrderAdapter:
    def send_test_order(self, signed_request: dict[str, Any]) -> dict[str, Any]:
        return {
            "mock_adapter": True,
            "endpoint": signed_request.get("endpoint"),
            "network_used": False,
            "order_placed": False,
            "validated": True,
        }


class MockSignedLiveOrderAdapter:
    def send_live_order(self, signed_request: dict[str, Any]) -> dict[str, Any]:
        return {
            "mock_adapter": True,
            "endpoint": signed_request.get("endpoint"),
            "network_used": False,
            "order_placed": True,
            "real_order_placed": False,
            "mock_order_placed": True,
            "exchange_order_id": "mock_only",
        }


class MockProtectiveOrderAdapter:
    def send_protective_orders(self, signed_requests: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "mock_adapter": True,
            "endpoints": [request.get("endpoint") for request in signed_requests],
            "network_used": False,
            "protective_orders_sent": False,
            "validated": True,
            "stop_validated": True,
            "take_profit_validated": True,
        }


class BinanceFuturesHttpClient:
    """Minimal explicit test-order client. It only targets /fapi/v1/order/test."""

    def send_test_order(self, signed_request: dict[str, Any]) -> dict[str, Any]:
        endpoint = signed_request.get("endpoint")
        if endpoint != TEST_ORDER_ENDPOINT:
            raise ValueError("R44 only permits Binance test-order endpoint")
        url = f"{signed_request['base_url'].rstrip('/')}{TEST_ORDER_ENDPOINT}"
        query = signed_request["query_string"]
        headers = dict(signed_request["headers"])
        data = query.encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - explicit gated test endpoint
            body = response.read().decode("utf-8")
            payload = json.loads(body) if body else {}
            return {
                "status_code": response.status,
                "body": payload,
                "endpoint": TEST_ORDER_ENDPOINT,
                "network_used": True,
                "order_placed": False,
            }


class BinanceFuturesLiveHttpClient:
    """Explicit live-order client. It only targets /fapi/v1/order."""

    def send_live_order(self, signed_request: dict[str, Any]) -> dict[str, Any]:
        endpoint = signed_request.get("endpoint")
        if endpoint != REAL_ORDER_ENDPOINT:
            raise ValueError("R45 live adapter only permits Binance real order endpoint")
        url = f"{signed_request['base_url'].rstrip('/')}{REAL_ORDER_ENDPOINT}"
        query = signed_request["query_string"]
        headers = dict(signed_request["headers"])
        data = query.encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - explicit gated live endpoint
            body = response.read().decode("utf-8")
            payload = json.loads(body) if body else {}
            return {
                "status_code": response.status,
                "body": payload,
                "endpoint": REAL_ORDER_ENDPOINT,
                "network_used": True,
                "order_placed": True,
                "real_order_placed": True,
                "mock_order_placed": False,
                "exchange_order_id": payload.get("orderId"),
            }


class BinanceFuturesProtectiveHttpClient:
    """Explicit protective-order client. It only targets /fapi/v1/order."""

    def send_protective_orders(self, signed_requests: list[dict[str, Any]]) -> dict[str, Any]:
        responses = []
        for signed_request in signed_requests:
            endpoint = signed_request.get("endpoint")
            if endpoint != PROTECTIVE_ORDER_ENDPOINT:
                raise ValueError("R46 protective adapter only permits Binance real order endpoint")
            url = f"{signed_request['base_url'].rstrip('/')}{PROTECTIVE_ORDER_ENDPOINT}"
            query = signed_request["query_string"]
            headers = dict(signed_request["headers"])
            data = query.encode("utf-8")
            request = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - explicit gated protective endpoint
                body = response.read().decode("utf-8")
                payload = json.loads(body) if body else {}
                responses.append({"status_code": response.status, "body": payload, "endpoint": PROTECTIVE_ORDER_ENDPOINT})
        return {
            "endpoint": PROTECTIVE_ORDER_ENDPOINT,
            "network_used": True,
            "protective_orders_sent": True,
            "order_placed": True,
            "real_order_placed": True,
            "responses": responses,
        }


def build_canonical_query(params: dict[str, Any]) -> str:
    pairs = []
    for key in sorted(params):
        value = params[key]
        if value is None:
            continue
        pairs.append((str(key), str(value)))
    return urllib.parse.urlencode(pairs, doseq=False, quote_via=urllib.parse.quote)


def sign_query(query_string: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()


def sanitize_signed_params(params: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(params)
    sanitized.pop("api_secret", None)
    sanitized.pop("secret", None)
    if "signature" in sanitized:
        sanitized["signature"] = "<hidden>"
    return sanitized


def sanitize_headers(headers: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(headers)
    if "X-MBX-APIKEY" in sanitized:
        sanitized["X-MBX-APIKEY"] = "<present>"
    return sanitized


def build_connector_status(
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    source = os.environ if env is None else env
    config = _config(source)
    return _connector_status_from_config(config, log_dir=get_log_dir(log_dir, use_env=True))


def build_protective_status(
    *,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    config = _config(os.environ if env is None else env)
    return _protective_status_from_config(config, log_dir=resolved_log_dir)


def _connector_status_from_config(config: dict[str, Any], *, log_dir: Path) -> dict[str, Any]:
    blockers = _status_blockers(config)
    readiness = "BLOCKED"
    if not blockers and config["connector_mode"] == TEST_ORDER_ONLY:
        readiness = "READY_FOR_TEST_ORDER"
    if not blockers and config["connector_mode"] == LIVE_ORDER_ENABLED:
        readiness = "READY_FOR_LIVE_ORDER"

    return {
        "connector_name": CONNECTOR_NAME,
        "connector_mode": config["connector_mode"],
        "api_key_present": config["api_key_present"],
        "api_secret_present": config["api_secret_present"],
        "secrets_shown": False,
        "network_used": False,
        "binance_live_enabled": config["binance_live_enabled"],
        "live_execution_enabled": config["live_execution_enabled"],
        "allow_live_orders": config["allow_live_orders"],
        "global_kill_switch": config["global_kill_switch"],
        "allowed_symbols": DEFAULT_ALLOWED_SYMBOLS,
        "configured_allowed_symbols": config["configured_allowed_symbols"],
        "max_position_usd": DEFAULT_MAX_POSITION_USD,
        "configured_max_position_usd": config["max_position_usd"],
        "max_leverage": DEFAULT_MAX_LEVERAGE,
        "configured_max_leverage": config["max_leverage"],
        "margin_mode": DEFAULT_MARGIN_MODE,
        "configured_margin_mode": config["margin_mode"],
        "max_trades_per_day": DEFAULT_MAX_TRADES_PER_DAY,
        "configured_max_trades_per_day": config["max_trades_per_day"],
        "require_exact_approval": config["require_exact_approval"],
        "test_order_network_enabled": config["test_order_network_enabled"],
        "base_url_host": _base_url_host(config["base_url"]),
        "recv_window": config["recv_window"],
        "signing_available": config["api_secret_present"],
        "live_order_adapter_configured": False,
        "protective_orders_supported": config["protective_orders_supported"],
        "protective_order_mode": config["protective_order_mode"],
        "protective_stop_supported": config["protective_stop_supported"],
        "protective_take_profit_supported": config["protective_take_profit_supported"],
        "protective_orders_required": config["protective_orders_required"],
        "protective_orders_ready": False,
        "protective_orders_default_blocked": True,
        "protective_stop_order_type": config["protective_stop_order_type"],
        "protective_take_profit_order_type": config["protective_take_profit_order_type"],
        "protective_order_endpoint": PROTECTIVE_ORDER_ENDPOINT,
        "protective_orders_atomic": False,
        "real_live_endpoint_prepared": True,
        "real_order_endpoint": REAL_ORDER_ENDPOINT,
        "live_order_default_blocked": True,
        "order_placed": False,
        "execution_attempted": False,
        "order_payload_created": False,
        "signed_payload_created": False,
        "readiness": readiness,
        "blockers": blockers,
        "attempts_path": str(connector_attempts_path(log_dir)),
    }


def preview_payload(
    *,
    preflight_pack: dict[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    pack = preflight_pack or build_promoted_strategy_preflight(log_dir=resolved_log_dir)
    config = _config(os.environ if env is None else env)
    payload, blockers = _payload_preview_from_pack(pack, config=config)
    status = "PAYLOAD_PREVIEW_CREATED" if payload is not None and not blockers else "BLOCKED"
    record = _attempt_record(
        action="payload_preview",
        connector_mode=config["connector_mode"],
        signal_id=_signal_id(pack),
        preflight_id=pack.get("preflight_id"),
        status=status,
        blockers=blockers,
        network_used=False,
        order_payload_created=payload is not None and not blockers,
        execution_attempted=False,
        order_placed=False,
        config=config,
        payload_preview=payload,
    )
    if persist:
        append_connector_attempt(record, log_dir=resolved_log_dir)
    return _response(record, connector_status=_connector_status_from_config(config, log_dir=resolved_log_dir))


def protective_preview(
    *,
    preflight_pack: dict[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    config = _config(os.environ if env is None else env)
    pack = preflight_pack or build_promoted_strategy_preflight(log_dir=resolved_log_dir)
    stop_preview, take_profit_preview, blockers = _protective_payload_previews_from_pack(pack, config=config)
    status = "PROTECTIVE_PREVIEW_CREATED" if stop_preview and take_profit_preview and not blockers else "BLOCKED"
    record = _protective_attempt_record(
        action="protective_preview",
        connector_mode=config["connector_mode"],
        protective_order_mode=config["protective_order_mode"],
        signal_id=_signal_id(pack),
        preflight_id=pack.get("preflight_id"),
        strategy_key=pack.get("strategy_key"),
        status=status,
        blockers=blockers,
        network_used=False,
        signed_payload_created=False,
        order_payload_created=status == "PROTECTIVE_PREVIEW_CREATED",
        protective_orders_sent=False,
        stop_order_payload_created=stop_preview is not None and not blockers,
        take_profit_order_payload_created=take_profit_preview is not None and not blockers,
        execution_attempted=False,
        order_placed=False,
        real_order_placed=False,
        config=config,
        stop_preview=stop_preview if not blockers else None,
        take_profit_preview=take_profit_preview if not blockers else None,
    )
    if persist:
        append_protective_attempt(record, log_dir=resolved_log_dir)
    return _protective_response(record, protective_status=_protective_status_from_config(config, log_dir=resolved_log_dir))


def submit_protective_test(
    *,
    preflight_pack: dict[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
    use_mock_adapter: bool = False,
    adapter: ProtectiveOrderAdapter | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    config = _config(source)
    pack = preflight_pack or build_promoted_strategy_preflight(log_dir=resolved_log_dir)
    stop_preview, take_profit_preview, blockers = _protective_payload_previews_from_pack(pack, config=config)
    if config["protective_order_mode"] != PROTECTIVE_TEST_ONLY:
        blockers.append("protective_order_mode must be TEST_ONLY for protective test")
    if not config["protective_orders_enabled"]:
        blockers.append("HAMMER_PROTECTIVE_ORDERS_ENABLED is false")
    if not config["api_key_present"] or not config["api_secret_present"]:
        blockers.append("Binance API key and secret must be present for protective test")
    if not use_mock_adapter and adapter is None:
        blockers.append("protective test real network disabled")
    if _has_protective_attempt(_signal_id(pack), log_dir=resolved_log_dir):
        blockers.append(f"protective orders already recorded for signal_id {_signal_id(pack)}")
    signed_requests = None
    sanitized_response = None
    execution_attempted = False
    network_used = False
    signed_payload_created = False
    status = "BLOCKED"
    if not blockers and stop_preview and take_profit_preview:
        signed_requests = build_signed_protective_order_requests(
            stop_preview,
            take_profit_preview,
            signal_id=_signal_id(pack),
            config=config,
            source=source,
        )
        signed_payload_created = True
        selected_adapter = adapter or MockProtectiveOrderAdapter()
        execution_attempted = True
        response = selected_adapter.send_protective_orders(signed_requests)
        sanitized_response = _sanitize_exchange_response(response)
        network_used = bool(sanitized_response.get("network_used"))
        status = "PROTECTIVE_ORDERS_SENT" if network_used else "PROTECTIVE_TEST_MOCK_VALIDATED"
    record = _protective_attempt_record(
        action="protective_test",
        connector_mode=config["connector_mode"],
        protective_order_mode=config["protective_order_mode"],
        signal_id=_signal_id(pack),
        preflight_id=pack.get("preflight_id"),
        strategy_key=pack.get("strategy_key"),
        status=status,
        blockers=blockers,
        network_used=network_used,
        signed_payload_created=signed_payload_created,
        order_payload_created=bool(stop_preview and take_profit_preview and not blockers),
        protective_orders_sent=status == "PROTECTIVE_ORDERS_SENT",
        stop_order_payload_created=stop_preview is not None and not blockers,
        take_profit_order_payload_created=take_profit_preview is not None and not blockers,
        execution_attempted=execution_attempted,
        order_placed=status == "PROTECTIVE_ORDERS_SENT",
        real_order_placed=status == "PROTECTIVE_ORDERS_SENT",
        config=config,
        stop_preview=stop_preview if not blockers else None,
        take_profit_preview=take_profit_preview if not blockers else None,
        signed_requests=signed_requests,
        exchange_response=sanitized_response,
    )
    if persist:
        append_protective_attempt(record, log_dir=resolved_log_dir)
    return _protective_response(record, protective_status=_protective_status_from_config(config, log_dir=resolved_log_dir))


def submit_test_order(
    *,
    preflight_pack: dict[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
    use_mock_adapter: bool = False,
    require_exact_approval: bool | None = None,
    adapter: SignedTestOrderAdapter | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    config = _config(source)
    pack = preflight_pack or build_promoted_strategy_preflight(log_dir=resolved_log_dir)
    payload, blockers = _payload_preview_from_pack(pack, config=config)
    exact_approval_required = config["require_exact_approval"] if require_exact_approval is None else require_exact_approval
    if config["connector_mode"] != TEST_ORDER_ONLY:
        blockers.append("connector_mode must be TEST_ORDER_ONLY for test-order")
    if not config["api_key_present"] or not config["api_secret_present"]:
        blockers.append("Binance API key and secret must be present for test-order")
    if exact_approval_required and not _has_exact_approval(_signal_id(pack), log_dir=resolved_log_dir):
        blockers.append("exact LIVE APPROVE <signal_id> is missing")
    if not use_mock_adapter and config["test_order_network_enabled"] is not True:
        blockers.append("test-order network disabled")
    signed_request = None
    sanitized_response = None
    network_used = False
    execution_attempted = False
    signed_payload_created = False
    status = "BLOCKED"
    if not blockers and payload is not None:
        signed_request = build_signed_test_order_request(payload, config=config, source=source)
        signed_payload_created = True
        selected_adapter = adapter or (MockSignedTestOrderAdapter() if use_mock_adapter else BinanceFuturesHttpClient())
        execution_attempted = True
        response = selected_adapter.send_test_order(signed_request)
        sanitized_response = _sanitize_exchange_response(response)
        network_used = bool(sanitized_response.get("network_used"))
        status = "TEST_ORDER_SENT" if network_used else "TEST_ORDER_MOCK_VALIDATED"
    record = _attempt_record(
        action="test_order",
        connector_mode=config["connector_mode"],
        signal_id=_signal_id(pack),
        preflight_id=pack.get("preflight_id"),
        status=status,
        blockers=blockers,
        network_used=network_used,
        order_payload_created=payload is not None and not blockers,
        signed_payload_created=signed_payload_created,
        execution_attempted=execution_attempted,
        order_placed=False,
        config=config,
        payload_preview=payload if not blockers else None,
        signed_request=signed_request,
        exchange_response=sanitized_response,
    )
    if persist:
        append_connector_attempt(record, log_dir=resolved_log_dir)
    return _response(record, connector_status=_connector_status_from_config(config, log_dir=resolved_log_dir))


def execute_live_order(
    *,
    preflight_pack: dict[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    log_dir: str | Path | None = None,
    signal_id: str | None = None,
    use_mock_adapter: bool = False,
    require_test_order_first: bool = True,
    require_protective_orders: bool = True,
    adapter: SignedLiveOrderAdapter | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    resolved_log_dir = get_log_dir(log_dir, use_env=True)
    source = os.environ if env is None else env
    config = _config(source)
    pack = preflight_pack or build_promoted_strategy_preflight(log_dir=resolved_log_dir)
    if signal_id is not None and _signal_id(pack) != signal_id:
        pack = dict(pack)
        pack["requested_signal_id"] = signal_id
    payload, blockers = _payload_preview_from_pack(pack, config=config)
    exact_approval_found = _has_exact_approval(_signal_id(pack), log_dir=resolved_log_dir)
    test_order_validated = _has_test_order_validated(_signal_id(pack), log_dir=resolved_log_dir)
    protective_orders_ready = _protective_orders_ready(_signal_id(pack), config=config, log_dir=resolved_log_dir)
    stop_preview, take_profit_preview, _protective_preview_blockers = _protective_payload_previews_from_pack(
        pack,
        config=config,
    )
    blockers.extend(
        _execute_blockers(
            pack,
            config=config,
            log_dir=resolved_log_dir,
            requested_signal_id=signal_id,
            exact_approval_found=exact_approval_found,
            test_order_validated=test_order_validated,
            require_test_order_first=require_test_order_first,
            require_protective_orders=require_protective_orders,
            protective_orders_ready=protective_orders_ready,
        )
    )
    if adapter is None and not use_mock_adapter:
        blockers.append("live Binance order adapter is not configured")

    exchange_response = None
    network_used = False
    order_placed = False
    real_order_placed = False
    mock_order_placed = False
    execution_attempted = False
    signed_request = None
    signed_payload_created = False
    status = "BLOCKED"
    if not blockers and payload is not None:
        signed_request = build_signed_live_order_request(payload, signal_id=_signal_id(pack), config=config, source=source)
        signed_payload_created = True
        selected_adapter = adapter or MockSignedLiveOrderAdapter()
        execution_attempted = True
        try:
            exchange_response = _sanitize_exchange_response(selected_adapter.send_live_order(signed_request))
            network_used = bool(exchange_response.get("network_used"))
            order_placed = bool(exchange_response.get("order_placed"))
            real_order_placed = bool(exchange_response.get("real_order_placed"))
            mock_order_placed = bool(exchange_response.get("mock_order_placed"))
            if real_order_placed:
                status = "LIVE_ORDER_SENT"
            elif mock_order_placed:
                status = "LIVE_ORDER_MOCK_PLACED"
            else:
                status = "ERROR"
        except Exception as exc:  # pragma: no cover - defensive adapter boundary
            status = "ERROR"
            exchange_response = {"error": exc.__class__.__name__, "message": "adapter failed without exposing secrets"}

    record = _attempt_record(
        action="execute",
        connector_mode=config["connector_mode"],
        signal_id=_signal_id(pack),
        preflight_id=pack.get("preflight_id"),
        status=status,
        blockers=blockers,
        network_used=network_used,
        order_payload_created=payload is not None and not blockers,
        signed_payload_created=signed_payload_created,
        execution_attempted=execution_attempted,
        order_placed=order_placed,
        real_order_placed=real_order_placed,
        mock_order_placed=mock_order_placed,
        config=config,
        payload_preview=payload if payload is not None and not blockers else None,
        signed_request=signed_request,
        exchange_response=exchange_response,
        strategy_key=pack.get("strategy_key"),
        exact_approval_found=exact_approval_found,
        test_order_validated=test_order_validated,
        protective_orders_ready=protective_orders_ready,
        protective_orders_required=require_protective_orders,
        protective_orders_sent=False,
        protective_stop_payload_preview=stop_preview if stop_preview is not None and not blockers else None,
        protective_take_profit_payload_preview=take_profit_preview if take_profit_preview is not None and not blockers else None,
        naked_entry_blocked=require_protective_orders and not protective_orders_ready,
    )
    if persist:
        append_connector_attempt(record, log_dir=resolved_log_dir)
    return _response(record, connector_status=_connector_status_from_config(config, log_dir=resolved_log_dir))


def append_connector_attempt(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = connector_attempts_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_connector_attempts(
    *,
    limit: int = 50,
    attempt_id: str | None = None,
    signal_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = connector_attempts_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if attempt_id is not None and record.get("attempt_id") != attempt_id:
                continue
            if signal_id is not None and record.get("signal_id") != signal_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def connector_attempts_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / ATTEMPTS_FILENAME


def append_protective_attempt(record: dict[str, Any], *, log_dir: str | Path) -> None:
    path = protective_attempts_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def load_protective_attempts(
    *,
    limit: int = 50,
    attempt_id: str | None = None,
    signal_id: str | None = None,
    log_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = protective_attempts_path(get_log_dir(log_dir, use_env=True))
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if attempt_id is not None and record.get("attempt_id") != attempt_id:
                continue
            if signal_id is not None and record.get("signal_id") != signal_id:
                continue
            records.append(record)
    records = list(reversed(records))
    if limit > 0:
        return records[:limit]
    return records


def protective_attempts_path(log_dir: str | Path) -> Path:
    return Path(log_dir) / PROTECTIVE_ATTEMPTS_FILENAME


def _payload_preview_from_pack(
    pack: dict[str, Any],
    *,
    config: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    blockers = _preflight_blockers(pack, config=config)
    candidate = pack.get("candidate") or {}
    entry = _float_or_none(candidate.get("entry"))
    if entry is None or entry <= 0.0:
        blockers.append("candidate entry price is required for payload preview")
    quantity = round(float(config["max_position_usd"]) / entry, 6) if entry else None
    if quantity is None or quantity <= 0.0:
        blockers.append("quantity is unavailable")
    if blockers:
        return None, list(dict.fromkeys(blockers))
    side = "BUY"
    payload = {
        "symbol": candidate.get("symbol"),
        "side": side,
        "position_side": "LONG",
        "order_type": "LIMIT",
        "quantity": quantity,
        "price": entry,
        "stop_price": candidate.get("stop"),
        "take_profit_price": candidate.get("take_profit"),
        "leverage": config["max_leverage"],
        "margin_mode": config["margin_mode"],
        "reduce_only": False,
        "preview_only": True,
        "sent": False,
        "signed": False,
        "signature_present": False,
        "order_payload_created": True,
    }
    return payload, []


def _protective_payload_previews_from_pack(
    pack: dict[str, Any],
    *,
    config: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    _, blockers = _payload_preview_from_pack(pack, config=config)
    candidate = pack.get("candidate") or {}
    entry = _float_or_none(candidate.get("entry"))
    stop = _float_or_none(candidate.get("stop"))
    take_profit = _float_or_none(candidate.get("take_profit"))
    if stop is None or stop <= 0.0:
        blockers.append("stop is required")
    if take_profit is None or take_profit <= 0.0:
        blockers.append("take_profit is required")
    if entry is not None and stop is not None and stop >= entry:
        blockers.append("stop must be below entry for long BTCUSDT")
    if entry is not None and take_profit is not None and take_profit <= entry:
        blockers.append("take_profit must be above entry for long BTCUSDT")
    if blockers:
        return None, None, list(dict.fromkeys(blockers))
    quantity = round(float(config["max_position_usd"]) / float(entry), 6)
    common = {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "position_side": "LONG",
        "quantity": quantity,
        "reduce_only": True,
        "working_type": DEFAULT_PROTECTIVE_WORKING_TYPE,
        "preview_only": True,
        "sent": False,
        "signed": False,
        "signature_present": False,
        "endpoint": PROTECTIVE_ORDER_ENDPOINT,
    }
    stop_preview = {
        **common,
        "protective_role": "stop_loss",
        "order_type": config["protective_stop_order_type"],
        "stopPrice": stop,
        "protective_order_payload_created": True,
    }
    take_profit_preview = {
        **common,
        "protective_role": "take_profit",
        "order_type": config["protective_take_profit_order_type"],
        "stopPrice": take_profit,
        "protective_order_payload_created": True,
    }
    return stop_preview, take_profit_preview, []


def build_signed_test_order_request(
    payload_preview: dict[str, Any],
    *,
    config: dict[str, Any],
    source: Mapping[str, str],
    timestamp_ms: int | None = None,
) -> dict[str, Any]:
    timestamp = timestamp_ms if timestamp_ms is not None else int(datetime.now(UTC).timestamp() * 1000)
    params = {
        "symbol": payload_preview["symbol"],
        "side": payload_preview["side"],
        "type": payload_preview.get("order_type", "LIMIT"),
        "timeInForce": "GTC" if payload_preview.get("order_type", "LIMIT") == "LIMIT" else None,
        "quantity": payload_preview["quantity"],
        "price": payload_preview["price"],
        "recvWindow": config["recv_window"],
        "timestamp": timestamp,
    }
    query_without_signature = build_canonical_query(params)
    signature = sign_query(query_without_signature, _env_value(source, ENV_API_SECRET))
    signed_params = dict(params)
    signed_params["signature"] = signature
    query_string = build_canonical_query(signed_params)
    headers = {
        "X-MBX-APIKEY": _env_value(source, ENV_API_KEY),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    return {
        "method": "POST",
        "endpoint": TEST_ORDER_ENDPOINT,
        "base_url": config["base_url"],
        "base_url_host": _base_url_host(config["base_url"]),
        "params": signed_params,
        "query_string": query_string,
        "headers": headers,
        "signed": True,
        "sent": False,
        "order_placed": False,
    }


def build_signed_protective_order_requests(
    stop_preview: dict[str, Any],
    take_profit_preview: dict[str, Any],
    *,
    signal_id: str | None,
    config: dict[str, Any],
    source: Mapping[str, str],
    timestamp_ms: int | None = None,
) -> list[dict[str, Any]]:
    timestamp = timestamp_ms if timestamp_ms is not None else int(datetime.now(UTC).timestamp() * 1000)
    return [
        _build_signed_protective_order_request(
            stop_preview,
            signal_id=signal_id,
            suffix="sl",
            config=config,
            source=source,
            timestamp_ms=timestamp,
        ),
        _build_signed_protective_order_request(
            take_profit_preview,
            signal_id=signal_id,
            suffix="tp",
            config=config,
            source=source,
            timestamp_ms=timestamp + 1,
        ),
    ]


def build_signed_live_order_request(
    payload_preview: dict[str, Any],
    *,
    signal_id: str | None,
    config: dict[str, Any],
    source: Mapping[str, str],
    timestamp_ms: int | None = None,
) -> dict[str, Any]:
    timestamp = timestamp_ms if timestamp_ms is not None else int(datetime.now(UTC).timestamp() * 1000)
    params = {
        "symbol": payload_preview["symbol"],
        "side": payload_preview["side"],
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": payload_preview["quantity"],
        "price": payload_preview["price"],
        "recvWindow": config["recv_window"],
        "timestamp": timestamp,
        "newClientOrderId": _client_order_id(signal_id),
    }
    query_without_signature = build_canonical_query(params)
    signature = sign_query(query_without_signature, _env_value(source, ENV_API_SECRET))
    signed_params = dict(params)
    signed_params["signature"] = signature
    query_string = build_canonical_query(signed_params)
    headers = {
        "X-MBX-APIKEY": _env_value(source, ENV_API_KEY),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    return {
        "method": "POST",
        "endpoint": REAL_ORDER_ENDPOINT,
        "base_url": config["base_url"],
        "base_url_host": _base_url_host(config["base_url"]),
        "params": signed_params,
        "query_string": query_string,
        "headers": headers,
        "signed": True,
        "sent": False,
        "order_placed": False,
    }


def _build_signed_protective_order_request(
    preview: dict[str, Any],
    *,
    signal_id: str | None,
    suffix: str,
    config: dict[str, Any],
    source: Mapping[str, str],
    timestamp_ms: int,
) -> dict[str, Any]:
    params = {
        "symbol": preview["symbol"],
        "side": preview["side"],
        "type": preview["order_type"],
        "quantity": preview["quantity"],
        "stopPrice": preview["stopPrice"],
        "reduceOnly": "true",
        "workingType": preview["working_type"],
        "recvWindow": config["recv_window"],
        "timestamp": timestamp_ms,
        "newClientOrderId": f"{_client_order_id(signal_id)}_{suffix}",
    }
    query_without_signature = build_canonical_query(params)
    signature = sign_query(query_without_signature, _env_value(source, ENV_API_SECRET))
    signed_params = dict(params)
    signed_params["signature"] = signature
    query_string = build_canonical_query(signed_params)
    headers = {
        "X-MBX-APIKEY": _env_value(source, ENV_API_KEY),
        "Content-Type": "application/x-www-form-urlencoded",
    }
    return {
        "method": "POST",
        "endpoint": PROTECTIVE_ORDER_ENDPOINT,
        "base_url": config["base_url"],
        "base_url_host": _base_url_host(config["base_url"]),
        "params": signed_params,
        "query_string": query_string,
        "headers": headers,
        "signed": True,
        "sent": False,
        "order_placed": False,
        "protective_role": preview["protective_role"],
    }


def _preflight_blockers(pack: dict[str, Any], *, config: dict[str, Any]) -> list[str]:
    candidate = pack.get("candidate") or {}
    blockers: list[str] = []
    if pack.get("promoted_strategy_ready") is not True:
        blockers.append("promoted strategy is not ready")
    if pack.get("matching_fresh_signal_found") is not True:
        blockers.append("no fresh promoted signal is available")
    if pack.get("strategy_key") != PROMOTED_STRATEGY_KEY:
        blockers.append(f"strategy_key must be {PROMOTED_STRATEGY_KEY}")
    if candidate.get("symbol") != "BTCUSDT":
        blockers.append("symbol must be BTCUSDT")
    if candidate.get("timeframe") != "13m":
        blockers.append("timeframe must be 13m")
    if candidate.get("direction") != "long":
        blockers.append("direction must be long")
    if pack.get("readiness_status") != "READY":
        blockers.append(f"readiness_status is {pack.get('readiness_status', 'UNKNOWN')}")
    if pack.get("ticket_status") != "PROPOSED":
        blockers.append(f"ticket_status is {pack.get('ticket_status', 'UNKNOWN')}")
    if pack.get("dry_run_status") != "VALID":
        blockers.append(f"dry_run_status is {pack.get('dry_run_status', 'UNKNOWN')}")
    if pack.get("preflight_status") != PREFLIGHT_READY_BUT_EXECUTION_DISABLED:
        blockers.append(f"preflight_status is {pack.get('preflight_status', 'UNKNOWN')}")
    if config["configured_allowed_symbols"] != DEFAULT_ALLOWED_SYMBOLS:
        blockers.append("HAMMER_LIVE_ALLOWED_SYMBOLS must remain BTCUSDT only")
    if float(config["max_position_usd"]) > DEFAULT_MAX_POSITION_USD:
        blockers.append("HAMMER_LIVE_MAX_POSITION_USD exceeds 44")
    if float(config["max_leverage"]) > DEFAULT_MAX_LEVERAGE:
        blockers.append("HAMMER_LIVE_MAX_LEVERAGE exceeds 3")
    if config["margin_mode"] != DEFAULT_MARGIN_MODE:
        blockers.append("HAMMER_LIVE_MARGIN_MODE must be isolated")
    return list(dict.fromkeys(blockers))


def _execute_blockers(
    pack: dict[str, Any],
    *,
    config: dict[str, Any],
    log_dir: Path,
    requested_signal_id: str | None,
    exact_approval_found: bool,
    test_order_validated: bool,
    require_test_order_first: bool,
    require_protective_orders: bool,
    protective_orders_ready: bool,
) -> list[str]:
    signal_id = _signal_id(pack)
    blockers = []
    if requested_signal_id is not None and requested_signal_id != signal_id:
        blockers.append("requested signal_id does not match current preflight signal_id")
    if config["connector_mode"] != LIVE_ORDER_ENABLED:
        blockers.append("connector_mode must be LIVE_ORDER_ENABLED")
    if config["binance_live_enabled"] is not True:
        blockers.append("HAMMER_BINANCE_LIVE_ENABLED is false")
    if config["live_execution_enabled"] is not True:
        blockers.append("live_execution_enabled is false")
    if config["allow_live_orders"] is not True:
        blockers.append("allow_live_orders is false")
    if config["global_kill_switch"] is not False:
        blockers.append("global kill switch is active")
    if not config["api_key_present"] or not config["api_secret_present"]:
        blockers.append("Binance API key and secret must be present")
    if config["require_exact_approval"] is True and not exact_approval_found:
        blockers.append("exact LIVE APPROVE <signal_id> is missing")
    if pack.get("live_safety_status") not in {"PASS", "WOULD_BE_ALLOWED_IF_LIVE_ENABLED"}:
        blockers.append(f"live_safety_status is {pack.get('live_safety_status', 'UNKNOWN')}")
    candidate = pack.get("candidate") or {}
    if candidate.get("stop") is None:
        blockers.append("stop is required")
    if candidate.get("take_profit") is None:
        blockers.append("take_profit is required")
    if require_test_order_first and not test_order_validated:
        blockers.append("successful test-order is required before live execute")
    if require_protective_orders and not protective_orders_ready:
        blockers.append("protective stop/take-profit live order path not ready")
    blockers.extend(_one_trade_lock_blockers(signal_id, config=config, log_dir=log_dir))
    return list(dict.fromkeys(blockers))


def _one_trade_lock_blockers(signal_id: str | None, *, config: dict[str, Any], log_dir: Path) -> list[str]:
    blockers = []
    today = datetime.now(UTC).date()
    live_order_records = [
        record
        for record in load_connector_attempts(limit=0, log_dir=log_dir)
        if record.get("status") == "LIVE_ORDER_SENT" or record.get("order_placed") is True
    ]
    if signal_id and any(record.get("signal_id") == signal_id for record in live_order_records):
        blockers.append(f"live order already recorded for signal_id {signal_id}")
    todays_orders = [record for record in live_order_records if _record_date(record) == today]
    if len(todays_orders) >= int(config["max_trades_per_day"]):
        blockers.append("max live trades per day already reached")
    return blockers


def _has_exact_approval(signal_id: str | None, *, log_dir: Path) -> bool:
    if not signal_id:
        return False
    for record in load_live_approval_requests(limit=0, signal_id=signal_id, log_dir=log_dir):
        if (
            record.get("normalized_action") == "live_approve_exact"
            and record.get("parse_status") == "ACCEPTED"
            and record.get("approval_gate_status") in {"READY_BUT_EXECUTION_DISABLED", "BLOCKED"}
            and record.get("signal_id") == signal_id
        ):
            return True
    return False


def _has_test_order_validated(signal_id: str | None, *, log_dir: Path) -> bool:
    if not signal_id:
        return False
    for record in load_connector_attempts(limit=0, signal_id=signal_id, log_dir=log_dir):
        if record.get("endpoint") == "test_order" and record.get("status") in {
            "TEST_ORDER_SENT",
            "TEST_ORDER_MOCK_VALIDATED",
            "TEST_ORDER_VALIDATED",
        }:
            return True
    return False


def _protective_orders_ready(signal_id: str | None, *, config: dict[str, Any], log_dir: Path) -> bool:
    if not signal_id:
        return False
    if not config["protective_orders_enabled"]:
        return False
    if config["protective_order_mode"] != LIVE_PROTECTIVE_ENABLED:
        return False
    if not config["protective_stop_supported"] or not config["protective_take_profit_supported"]:
        return False
    for record in load_protective_attempts(limit=0, signal_id=signal_id, log_dir=log_dir):
        if record.get("status") in {"PROTECTIVE_TEST_MOCK_VALIDATED", "PROTECTIVE_ORDERS_SENT"}:
            return True
    return False


def _has_protective_attempt(signal_id: str | None, *, log_dir: Path) -> bool:
    if not signal_id:
        return False
    return any(
        record.get("status") in {"PROTECTIVE_TEST_MOCK_VALIDATED", "PROTECTIVE_ORDERS_SENT"}
        for record in load_protective_attempts(limit=0, signal_id=signal_id, log_dir=log_dir)
    )


def _attempt_record(
    *,
    action: str,
    connector_mode: str,
    signal_id: str | None,
    preflight_id: str | None,
    status: str,
    blockers: list[str],
    network_used: bool,
    order_payload_created: bool,
    execution_attempted: bool,
    order_placed: bool,
    real_order_placed: bool = False,
    mock_order_placed: bool = False,
    config: dict[str, Any],
    signed_payload_created: bool = False,
    payload_preview: dict[str, Any] | None = None,
    signed_request: dict[str, Any] | None = None,
    exchange_response: dict[str, Any] | None = None,
    strategy_key: object = None,
    exact_approval_found: bool = False,
    test_order_validated: bool = False,
    protective_orders_ready: bool = False,
    protective_orders_required: bool = False,
    protective_orders_sent: bool = False,
    protective_stop_payload_preview: dict[str, Any] | None = None,
    protective_take_profit_payload_preview: dict[str, Any] | None = None,
    naked_entry_blocked: bool = False,
) -> dict[str, Any]:
    return {
        "attempt_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "endpoint": action,
        "action": action,
        "connector_name": CONNECTOR_NAME,
        "connector_mode": connector_mode,
        "signal_id": signal_id,
        "strategy_key": strategy_key,
        "preflight_id": preflight_id,
        "exact_approval_found": exact_approval_found,
        "test_order_validated": test_order_validated,
        "protective_orders_ready": protective_orders_ready,
        "protective_orders_required": protective_orders_required,
        "protective_orders_sent": protective_orders_sent,
        "protective_stop_payload_preview": _sanitize_payload(protective_stop_payload_preview),
        "protective_take_profit_payload_preview": _sanitize_payload(protective_take_profit_payload_preview),
        "naked_entry_blocked": naked_entry_blocked,
        "status": status,
        "blockers": list(dict.fromkeys(blockers)),
        "network_used": network_used,
        "order_payload_created": order_payload_created,
        "signed_payload_created": signed_payload_created,
        "execution_attempted": execution_attempted,
        "order_placed": order_placed,
        "real_order_placed": real_order_placed,
        "mock_order_placed": mock_order_placed,
        "live_execution_enabled": config["live_execution_enabled"],
        "allow_live_orders": config["allow_live_orders"],
        "global_kill_switch": config["global_kill_switch"],
        "secrets_shown": False,
        "payload_preview": _sanitize_payload(payload_preview),
        "sanitized_signed_request": _sanitize_signed_request(signed_request),
        "exchange_response": _sanitize_exchange_response(exchange_response),
        "sanitized_exchange_response": _sanitize_exchange_response(exchange_response),
    }


def _protective_attempt_record(
    *,
    action: str,
    connector_mode: str,
    protective_order_mode: str,
    signal_id: str | None,
    preflight_id: str | None,
    strategy_key: object,
    status: str,
    blockers: list[str],
    network_used: bool,
    signed_payload_created: bool,
    order_payload_created: bool,
    protective_orders_sent: bool,
    stop_order_payload_created: bool,
    take_profit_order_payload_created: bool,
    execution_attempted: bool,
    order_placed: bool,
    real_order_placed: bool,
    config: dict[str, Any],
    stop_preview: dict[str, Any] | None = None,
    take_profit_preview: dict[str, Any] | None = None,
    signed_requests: list[dict[str, Any]] | None = None,
    exchange_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "attempt_id": uuid4().hex,
        "created_at": datetime.now(UTC).isoformat(),
        "endpoint": action,
        "action": action,
        "connector_name": CONNECTOR_NAME,
        "connector_mode": connector_mode,
        "protective_order_mode": protective_order_mode,
        "signal_id": signal_id,
        "preflight_id": preflight_id,
        "strategy_key": strategy_key,
        "status": status,
        "blockers": list(dict.fromkeys(blockers)),
        "network_used": network_used,
        "signed_payload_created": signed_payload_created,
        "order_payload_created": order_payload_created,
        "protective_orders_sent": protective_orders_sent,
        "stop_order_payload_created": stop_order_payload_created,
        "take_profit_order_payload_created": take_profit_order_payload_created,
        "execution_attempted": execution_attempted,
        "order_placed": order_placed,
        "real_order_placed": real_order_placed,
        "live_execution_enabled": config["live_execution_enabled"],
        "allow_live_orders": config["allow_live_orders"],
        "global_kill_switch": config["global_kill_switch"],
        "secrets_shown": False,
        "sanitized_stop_order_preview": _sanitize_payload(stop_preview),
        "sanitized_take_profit_order_preview": _sanitize_payload(take_profit_preview),
        "sanitized_signed_requests": [_sanitize_signed_request(request) for request in signed_requests or []],
        "sanitized_exchange_response": _sanitize_exchange_response(exchange_response),
    }


def _response(record: dict[str, Any], *, connector_status: dict[str, Any]) -> dict[str, Any]:
    return {
        "connector_name": CONNECTOR_NAME,
        "connector_mode": record["connector_mode"],
        "status": record["status"],
        "attempt": record,
        "blockers": record["blockers"],
        "network_used": record["network_used"],
        "order_payload_created": record["order_payload_created"],
        "signed_payload_created": record.get("signed_payload_created", False),
        "execution_attempted": record["execution_attempted"],
        "order_placed": record["order_placed"],
        "real_order_placed": record.get("real_order_placed", False),
        "mock_order_placed": record.get("mock_order_placed", False),
        "protective_orders_required": record.get("protective_orders_required", False),
        "protective_orders_ready": record.get("protective_orders_ready", False),
        "protective_orders_sent": record.get("protective_orders_sent", False),
        "protective_stop_payload_preview": record.get("protective_stop_payload_preview"),
        "protective_take_profit_payload_preview": record.get("protective_take_profit_payload_preview"),
        "naked_entry_blocked": record.get("naked_entry_blocked", False),
        "live_execution_enabled": record["live_execution_enabled"],
        "allow_live_orders": record["allow_live_orders"],
        "global_kill_switch": record["global_kill_switch"],
        "secrets_shown": False,
        "payload_preview": record.get("payload_preview"),
        "sanitized_signed_request": record.get("sanitized_signed_request"),
        "exchange_response": record.get("exchange_response"),
        "sanitized_exchange_response": record.get("sanitized_exchange_response"),
        "connector_status": connector_status,
    }


def _protective_response(record: dict[str, Any], *, protective_status: dict[str, Any]) -> dict[str, Any]:
    return {
        "connector_name": CONNECTOR_NAME,
        "connector_mode": record["connector_mode"],
        "protective_order_mode": record["protective_order_mode"],
        "status": record["status"],
        "attempt": record,
        "blockers": record["blockers"],
        "network_used": record["network_used"],
        "signed_payload_created": record["signed_payload_created"],
        "order_payload_created": record["order_payload_created"],
        "protective_orders_sent": record["protective_orders_sent"],
        "stop_order_payload_created": record["stop_order_payload_created"],
        "take_profit_order_payload_created": record["take_profit_order_payload_created"],
        "execution_attempted": record["execution_attempted"],
        "order_placed": record["order_placed"],
        "real_order_placed": record["real_order_placed"],
        "live_execution_enabled": record["live_execution_enabled"],
        "allow_live_orders": record["allow_live_orders"],
        "global_kill_switch": record["global_kill_switch"],
        "secrets_shown": False,
        "sanitized_stop_order_preview": record.get("sanitized_stop_order_preview"),
        "sanitized_take_profit_order_preview": record.get("sanitized_take_profit_order_preview"),
        "sanitized_signed_requests": record.get("sanitized_signed_requests"),
        "sanitized_exchange_response": record.get("sanitized_exchange_response"),
        "protective_status": protective_status,
    }


def _config(source: Mapping[str, str]) -> dict[str, Any]:
    mode = _env_value(source, ENV_CONNECTOR_MODE).upper() or DRY_RUN_ONLY
    if mode not in CONNECTOR_MODES:
        mode = DRY_RUN_ONLY
    protective_mode = _env_value(source, ENV_PROTECTIVE_ORDER_MODE).upper() or PROTECTIVE_PREVIEW_ONLY
    if protective_mode not in PROTECTIVE_ORDER_MODES:
        protective_mode = PROTECTIVE_PREVIEW_ONLY
    protective_enabled = _env_bool(source, ENV_PROTECTIVE_ORDERS_ENABLED, default=False)
    return {
        "connector_mode": mode,
        "api_key_present": bool(_env_value(source, ENV_API_KEY)),
        "api_secret_present": bool(_env_value(source, ENV_API_SECRET)),
        "binance_live_enabled": _env_bool(source, ENV_BINANCE_LIVE_ENABLED, default=False),
        "live_execution_enabled": _env_bool(source, ENV_LIVE_EXECUTION_ENABLED, default=False),
        "allow_live_orders": _env_bool(source, ENV_ALLOW_LIVE_ORDERS, default=False),
        "global_kill_switch": _env_bool(source, ENV_GLOBAL_KILL_SWITCH, default=True),
        "configured_allowed_symbols": _allowed_symbols(_env_value(source, ENV_ALLOWED_SYMBOLS)),
        "max_position_usd": _env_float(source, ENV_MAX_POSITION_USD, DEFAULT_MAX_POSITION_USD),
        "max_leverage": _env_float(source, ENV_MAX_LEVERAGE, DEFAULT_MAX_LEVERAGE),
        "margin_mode": (_env_value(source, ENV_MARGIN_MODE).lower() or DEFAULT_MARGIN_MODE),
        "require_exact_approval": _env_bool(source, ENV_REQUIRE_EXACT_APPROVAL, default=True),
        "max_trades_per_day": int(_env_float(source, ENV_MAX_TRADES_PER_DAY, DEFAULT_MAX_TRADES_PER_DAY)),
        "test_order_network_enabled": _env_bool(source, ENV_TEST_ORDER_NETWORK_ENABLED, default=False),
        "base_url": _env_value(source, ENV_BINANCE_BASE_URL) or DEFAULT_BASE_URL,
        "recv_window": int(_env_float(source, ENV_RECV_WINDOW, DEFAULT_RECV_WINDOW)),
        "protective_orders_required": _env_bool(source, ENV_PROTECTIVE_ORDERS_REQUIRED, default=True),
        "protective_orders_enabled": protective_enabled,
        "protective_order_mode": protective_mode,
        "protective_orders_supported": protective_enabled and protective_mode in {PROTECTIVE_TEST_ONLY, LIVE_PROTECTIVE_ENABLED},
        "protective_stop_supported": protective_enabled and protective_mode in {PROTECTIVE_TEST_ONLY, LIVE_PROTECTIVE_ENABLED},
        "protective_take_profit_supported": protective_enabled and protective_mode in {PROTECTIVE_TEST_ONLY, LIVE_PROTECTIVE_ENABLED},
        "protective_stop_order_type": _env_value(source, ENV_PROTECTIVE_STOP_TYPE).upper() or DEFAULT_PROTECTIVE_STOP_TYPE,
        "protective_take_profit_order_type": _env_value(source, ENV_PROTECTIVE_TAKE_PROFIT_TYPE).upper()
        or DEFAULT_PROTECTIVE_TAKE_PROFIT_TYPE,
    }


def _protective_status_from_config(config: dict[str, Any], *, log_dir: Path) -> dict[str, Any]:
    return {
        "connector_name": CONNECTOR_NAME,
        "connector_mode": config["connector_mode"],
        "protective_orders_required": config["protective_orders_required"],
        "protective_orders_enabled": config["protective_orders_enabled"],
        "protective_order_mode": config["protective_order_mode"],
        "protective_orders_supported": config["protective_orders_supported"],
        "protective_stop_supported": config["protective_stop_supported"],
        "protective_take_profit_supported": config["protective_take_profit_supported"],
        "protective_orders_ready": False,
        "protective_orders_default_blocked": True,
        "protective_stop_order_type": config["protective_stop_order_type"],
        "protective_take_profit_order_type": config["protective_take_profit_order_type"],
        "protective_order_endpoint": PROTECTIVE_ORDER_ENDPOINT,
        "protective_orders_atomic": False,
        "live_execution_enabled": config["live_execution_enabled"],
        "allow_live_orders": config["allow_live_orders"],
        "global_kill_switch": config["global_kill_switch"],
        "order_placed": False,
        "real_order_placed": False,
        "protective_orders_sent": False,
        "secrets_shown": False,
        "blockers": _protective_status_blockers(config),
        "protective_attempts_path": str(protective_attempts_path(log_dir)),
    }


def _status_blockers(config: dict[str, Any]) -> list[str]:
    blockers = []
    if config["connector_mode"] == DRY_RUN_ONLY:
        blockers.append("connector_mode is DRY_RUN_ONLY")
    if config["configured_allowed_symbols"] != DEFAULT_ALLOWED_SYMBOLS:
        blockers.append("HAMMER_LIVE_ALLOWED_SYMBOLS must remain BTCUSDT only")
    if config["max_position_usd"] != DEFAULT_MAX_POSITION_USD:
        blockers.append("HAMMER_LIVE_MAX_POSITION_USD must remain 44")
    if config["max_leverage"] != DEFAULT_MAX_LEVERAGE:
        blockers.append("HAMMER_LIVE_MAX_LEVERAGE must remain 3")
    if config["margin_mode"] != DEFAULT_MARGIN_MODE:
        blockers.append("HAMMER_LIVE_MARGIN_MODE must remain isolated")
    if config["connector_mode"] == LIVE_ORDER_ENABLED:
        if config["binance_live_enabled"] is not True:
            blockers.append("HAMMER_BINANCE_LIVE_ENABLED is false")
        if config["live_execution_enabled"] is not True:
            blockers.append("live_execution_enabled is false")
        if config["allow_live_orders"] is not True:
            blockers.append("allow_live_orders is false")
        if config["global_kill_switch"] is not False:
            blockers.append("global kill switch is active")
    if config["connector_mode"] in {TEST_ORDER_ONLY, LIVE_ORDER_ENABLED}:
        if not config["api_key_present"]:
            blockers.append("BINANCE_API_KEY missing")
        if not config["api_secret_present"]:
            blockers.append("BINANCE_API_SECRET missing")
    return list(dict.fromkeys(blockers))


def _protective_status_blockers(config: dict[str, Any]) -> list[str]:
    blockers = []
    if not config["protective_orders_enabled"]:
        blockers.append("HAMMER_PROTECTIVE_ORDERS_ENABLED is false")
    if config["protective_order_mode"] == PROTECTIVE_PREVIEW_ONLY:
        blockers.append("protective_order_mode is PREVIEW_ONLY")
    if config["protective_orders_required"] is not True:
        blockers.append("HAMMER_PROTECTIVE_ORDERS_REQUIRED must remain true for default runtime")
    return list(dict.fromkeys(blockers))


def _client_order_id(signal_id: str | None) -> str:
    digest = hmac.new(b"hammer", str(signal_id or "unknown").encode("utf-8"), hashlib.sha256).hexdigest()[:24]
    return f"hammer_{digest}"


def _sanitize_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    sanitized = dict(payload)
    for key in ("apiKey", "api_key", "secret", "signature"):
        sanitized.pop(key, None)
    sanitized["signed"] = False
    sanitized["signature_present"] = False
    return sanitized


def _sanitize_signed_request(signed_request: dict[str, Any] | None) -> dict[str, Any] | None:
    if signed_request is None:
        return None
    return {
        "method": signed_request.get("method"),
        "endpoint": signed_request.get("endpoint"),
        "base_url_host": signed_request.get("base_url_host"),
        "params": sanitize_signed_params(signed_request.get("params") or {}),
        "headers": sanitize_headers(signed_request.get("headers") or {}),
        "signed": True,
        "sent": False,
        "order_placed": False,
    }


def _sanitize_exchange_response(response: dict[str, Any] | None) -> dict[str, Any] | None:
    if response is None:
        return None
    sanitized = dict(response)
    for key in ("apiKey", "api_key", "secret", "signature"):
        sanitized.pop(key, None)
    return sanitized


def _record_date(record: dict[str, Any]) -> object:
    try:
        return datetime.fromisoformat(str(record.get("created_at"))).date()
    except ValueError:
        return None


def _signal_id(pack: dict[str, Any]) -> str | None:
    value = pack.get("candidate_signal_id") or pack.get("signal_id")
    return str(value) if value else None


def _base_url_host(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    return parsed.netloc or parsed.path


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _env_value(source: Mapping[str, str], key: str) -> str:
    return str(source.get(key) or "").strip()


def _env_bool(source: Mapping[str, str], key: str, *, default: bool) -> bool:
    value = _env_value(source, key).lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _env_float(source: Mapping[str, str], key: str, default: float) -> float:
    value = _env_value(source, key)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _allowed_symbols(value: str) -> list[str]:
    if not value:
        return list(DEFAULT_ALLOWED_SYMBOLS)
    symbols = [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]
    return symbols or list(DEFAULT_ALLOWED_SYMBOLS)
