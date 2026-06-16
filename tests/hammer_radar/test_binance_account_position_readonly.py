from __future__ import annotations

import json
import urllib.request
from src.app.hammer_radar.operator.binance_account_position_readonly import (
    ACCOUNT_POSITION_CONFIRMATION_REQUIRED,
    ACCOUNT_POSITION_CONFLICTING_POSITION,
    ACCOUNT_POSITION_ENDPOINT_NOT_ALLOWLISTED,
    ACCOUNT_POSITION_READY,
    ACCOUNT_POSITION_WALLET_INSUFFICIENT,
    FUTURES_BALANCE_PATH,
    FUTURES_POSITION_RISK_PATH,
    build_account_position_readiness,
    build_signed_readonly_query,
    validate_private_readonly_endpoint,
)


def test_missing_confirmation_blocks_without_private_endpoint_call() -> None:
    fake = _PrivateFakeUrlOpen(available_balance="20", position_amt="0", notional="0")

    payload = build_account_position_readiness(
        fetch_requested=True,
        confirmation_valid=False,
        env=_safe_env(),
        urlopen_func=fake,
    )

    assert fake.calls == []
    assert payload["account_position_readiness_status"] == ACCOUNT_POSITION_CONFIRMATION_REQUIRED
    assert payload["account_balance_checked"] is False
    assert payload["position_risk_checked"] is False
    assert payload["safety"]["signed_readonly_request_created"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["binance_test_order_endpoint_called"] is False


def test_only_allowlisted_readonly_private_endpoints_can_be_signed() -> None:
    allowed = build_signed_readonly_query(
        endpoint_path=FUTURES_POSITION_RISK_PATH,
        params={"symbol": "BTCUSDT"},
        secret="secret",
        timestamp_ms=1,
    )
    blocked = build_signed_readonly_query(
        endpoint_path="/fapi/v1/order",
        params={"symbol": "BTCUSDT"},
        secret="secret",
        timestamp_ms=1,
    )

    assert validate_private_readonly_endpoint(FUTURES_BALANCE_PATH)["endpoint_allowlisted"] is True
    assert validate_private_readonly_endpoint("/fapi/v1/leverage")["endpoint_allowlisted"] is False
    assert allowed["endpoint_allowlisted"] is True
    assert allowed["signed_readonly_request_created"] is True
    assert allowed["signed_trading_request_created"] is False
    assert allowed["signed_order_request_created"] is False
    assert allowed["hmac_signature_created"] is True
    public_allowed = {k: v for k, v in allowed.items() if not k.startswith("_")}
    assert "signature=" not in json.dumps(public_allowed)
    assert "secret" not in json.dumps(public_allowed)
    assert blocked["endpoint_allowlisted"] is False
    assert blocked["blocked_reason"] == ACCOUNT_POSITION_ENDPOINT_NOT_ALLOWLISTED
    assert blocked["signed_readonly_request_created"] is False


def test_sufficient_balance_and_no_position_is_ready_without_exposing_signature() -> None:
    fake = _PrivateFakeUrlOpen(available_balance="20", wallet_balance="25", position_amt="0", notional="0")

    payload = build_account_position_readiness(
        fetch_requested=True,
        confirmation_valid=True,
        env=_safe_env(),
        urlopen_func=fake,
    )

    assert [call.get_method() for call in fake.calls] == ["GET", "GET"]
    assert fake.calls[0].full_url.startswith("https://fapi.binance.com/fapi/v2/balance?")
    assert fake.calls[1].full_url.startswith("https://fapi.binance.com/fapi/v2/positionRisk?")
    assert payload["account_position_readiness_status"] == ACCOUNT_POSITION_READY
    assert payload["account_balance_checked"] is True
    assert payload["position_risk_checked"] is True
    assert payload["available_balance_usdt"] == 20.0
    assert payload["wallet_balance_usdt"] == 25.0
    assert payload["wallet_supports_minimum_tiny"] is True
    assert payload["wallet_supports_configured_margin_budget"] is True
    assert payload["open_position_conflict"] is False
    assert payload["btcusdt_position_amt"] == 0.0
    assert payload["btcusdt_position_side"] == "BOTH"
    assert payload["btcusdt_position_notional"] == 0.0
    assert payload["leverage_matches_expectation"] is True
    assert payload["margin_mode_matches_expectation"] is True
    rendered = json.dumps(payload)
    assert "account-read-key" not in rendered
    assert "account-read-secret" not in rendered
    assert "signature=" not in rendered
    assert payload["safety"]["hmac_signature_created"] is True
    assert payload["safety"]["signed_readonly_request_created"] is True
    assert payload["safety"]["signed_trading_request_created"] is False
    assert payload["safety"]["signed_order_request_created"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["binance_test_order_endpoint_called"] is False
    assert payload["safety"]["leverage_change_called"] is False
    assert payload["safety"]["margin_change_called"] is False
    assert payload["safety"]["secrets_shown"] is False


def test_insufficient_balance_blocks_wallet_ready() -> None:
    payload = build_account_position_readiness(
        fetch_requested=True,
        confirmation_valid=True,
        env=_safe_env(),
        urlopen_func=_PrivateFakeUrlOpen(available_balance="3", wallet_balance="3", position_amt="0", notional="0"),
    )

    assert payload["account_position_readiness_status"] == ACCOUNT_POSITION_WALLET_INSUFFICIENT
    assert payload["wallet_supports_minimum_tiny"] is False
    assert payload["wallet_supports_configured_margin_budget"] is False
    assert "wallet_supports_configured_margin_budget_false" in payload["readiness_blockers"]


def test_nonzero_btcusdt_position_conflicts_and_blocks() -> None:
    payload = build_account_position_readiness(
        fetch_requested=True,
        confirmation_valid=True,
        env=_safe_env(),
        urlopen_func=_PrivateFakeUrlOpen(
            available_balance="20",
            wallet_balance="20",
            position_amt="-0.002",
            notional="-80",
        ),
    )

    assert payload["account_position_readiness_status"] == ACCOUNT_POSITION_CONFLICTING_POSITION
    assert payload["open_position_conflict"] is True
    assert payload["btcusdt_position_amt"] == -0.002
    assert payload["btcusdt_position_notional"] == -80.0
    assert "btcusdt_open_position_conflict" in payload["readiness_blockers"]


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _PrivateFakeUrlOpen:
    def __init__(
        self,
        *,
        available_balance: str,
        position_amt: str,
        notional: str,
        wallet_balance: str | None = None,
    ) -> None:
        self.available_balance = available_balance
        self.wallet_balance = wallet_balance or available_balance
        self.position_amt = position_amt
        self.notional = notional
        self.calls: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> _FakeResponse:
        self.calls.append(request)
        assert request.get_method() == "GET"
        assert "/fapi/v1/order" not in request.full_url
        assert "/fapi/v1/leverage" not in request.full_url
        assert "/fapi/v1/marginType" not in request.full_url
        assert any(str(key).lower() == "x-mbx-apikey" for key in request.headers)
        if request.full_url.startswith("https://fapi.binance.com/fapi/v2/balance?"):
            return _FakeResponse(
                [
                    {
                        "asset": "USDT",
                        "availableBalance": self.available_balance,
                        "balance": self.wallet_balance,
                    }
                ]
            )
        if request.full_url.startswith("https://fapi.binance.com/fapi/v2/positionRisk?"):
            return _FakeResponse(
                [
                    {
                        "symbol": "BTCUSDT",
                        "positionAmt": self.position_amt,
                        "positionSide": "BOTH",
                        "notional": self.notional,
                        "leverage": "10",
                        "marginType": "isolated",
                    }
                ]
            )
        raise AssertionError(f"unexpected url: {request.full_url}")


def _safe_env() -> dict[str, str]:
    return {
        "HAMMER_ACCOUNT_READ_BINANCE_API_KEY": "account-read-key",
        "HAMMER_ACCOUNT_READ_BINANCE_API_SECRET": "account-read-secret",
        "BINANCE_CONNECTOR_MODE": "read_only",
        "BINANCE_LIVE_TRADING_ENABLED": "false",
        "HAMMER_BINANCE_LIVE_ENABLED": "false",
        "HAMMER_LIVE_EXECUTION_ENABLED": "false",
        "HAMMER_ALLOW_LIVE_ORDERS": "false",
        "HAMMER_GLOBAL_KILL_SWITCH": "true",
    }
