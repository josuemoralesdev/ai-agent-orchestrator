from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_final_readonly_mark_price_refresh_gate import (
    CONFIRM_TINY_LIVE_FINAL_READONLY_REFRESH_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_FETCHED,
    TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_READY,
    TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_REJECTED,
    TINY_LIVE_FINAL_READONLY_REFRESH_FETCHED_READY_FOR_SUBMIT_GATE_PREVIEW,
    TINY_LIVE_FINAL_READONLY_REFRESH_FETCHED_REGENERATE_SIGNED_REQUEST_REQUIRED,
    build_tiny_live_final_readonly_mark_price_refresh_gate,
    load_tiny_live_final_readonly_mark_price_refresh_gate_records,
    validate_final_readonly_endpoint_safety,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_runtime_source_write_gate import (
    BINANCE_API_KEY_ENV,
    BINANCE_API_SECRET_ENV,
)
from tests.hammer_radar.test_tiny_live_signed_request_runtime_source_write_gate import (
    API_KEY,
    API_SECRET,
)
from tests.hammer_radar.test_tiny_live_submit_readiness_preview import (
    CONFIRM_TINY_LIVE_SUBMIT_READINESS_PREVIEW_PHRASE,
    _fixture_r252,
)
from src.app.hammer_radar.operator.tiny_live_submit_readiness_preview import (
    build_tiny_live_submit_readiness_preview,
)

NOW = datetime(2026, 6, 12, 12, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _FakeUrlOpen:
    def __init__(self, mark_price: str = "62210.3") -> None:
        self.calls: list[urllib.request.Request] = []
        self.mark_price = mark_price

    def __call__(self, request: urllib.request.Request, timeout: float) -> _FakeResponse:
        self.calls.append(request)
        url = request.full_url
        assert request.get_method() == "GET"
        assert "signature" not in url
        assert "timestamp" not in url
        assert "/order" not in url
        assert "/account" not in url
        if url.endswith("/fapi/v1/exchangeInfo"):
            return _FakeResponse(_exchange_info_payload())
        if url.endswith("/fapi/v1/premiumIndex?symbol=BTCUSDT"):
            return _FakeResponse({"symbol": "BTCUSDT", "markPrice": self.mark_price, "time": 1781114400000})
        raise AssertionError(f"unexpected url: {url}")


def test_cli_exists_and_returns_json(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r253(tmp_path, monkeypatch)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-final-readonly-mark-price-refresh-gate",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=_clean_env(),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_READY
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["final_readonly_market_fetched"] is False
    assert payload["allowed_public_readonly_request_plan"]["preview_only"] is True
    assert payload["endpoint_safety_validation"]["valid"] is True
    _assert_safety(payload, fetched=False)
    _assert_no_secret_values(payload)


def test_preview_makes_no_network_call_and_writes_no_ledger(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r253(tmp_path, monkeypatch)

    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = build_tiny_live_final_readonly_mark_price_refresh_gate(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    assert payload["status"] == TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_READY
    assert payload["fetch_final_readonly_market_requested"] is False
    assert payload["final_readonly_market_fetched"] is False
    assert payload["signed_request_regeneration_decision"]["must_regenerate_signed_request_before_submit"] is None
    assert not (log_dir / LEDGER_FILENAME).exists()
    _assert_ready_inputs(payload)
    _assert_safety(payload, fetched=False)


def test_wrong_confirmation_rejects_and_makes_no_network_call(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r253(tmp_path, monkeypatch)

    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = build_tiny_live_final_readonly_mark_price_refresh_gate(
            log_dir=log_dir,
            fetch_final_readonly_market=True,
            confirm_tiny_live_final_readonly_refresh="wrong",
            now=NOW,
        )

    urlopen.assert_not_called()
    assert payload["status"] == TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["final_readonly_market_fetched"] is False
    assert payload["final_readonly_refresh_overall_status"] == "TINY_LIVE_FINAL_READONLY_REFRESH_REJECTED_BAD_CONFIRMATION"
    assert load_tiny_live_final_readonly_mark_price_refresh_gate_records(log_dir=log_dir, limit=0) == []
    _assert_safety(payload, fetched=False)


def test_exact_confirmation_calls_only_allowed_public_readonly_endpoints_and_records(
    tmp_path: Path, monkeypatch
) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_r253(tmp_path, monkeypatch)
    fake_urlopen = _FakeUrlOpen(mark_price="62210.3")
    before_env = dict(os.environ)
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    with (
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = build_tiny_live_final_readonly_mark_price_refresh_gate(
            log_dir=log_dir,
            fetch_final_readonly_market=True,
            confirm_tiny_live_final_readonly_refresh=CONFIRM_TINY_LIVE_FINAL_READONLY_REFRESH_PHRASE,
            now=NOW,
            urlopen_func=fake_urlopen,
        )

    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert dict(os.environ) == before_env
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert [call.get_method() for call in fake_urlopen.calls] == ["GET", "GET"]
    assert fake_urlopen.calls[0].full_url.endswith("/fapi/v1/exchangeInfo")
    assert fake_urlopen.calls[1].full_url.endswith("/fapi/v1/premiumIndex?symbol=BTCUSDT")
    assert payload["status"] == TINY_LIVE_FINAL_READONLY_MARK_PRICE_REFRESH_GATE_FETCHED
    assert payload["final_readonly_refresh_overall_status"] == (
        TINY_LIVE_FINAL_READONLY_REFRESH_FETCHED_READY_FOR_SUBMIT_GATE_PREVIEW
    )
    comparison = payload["fresh_vs_signed_context_comparison"]
    assert comparison["quantity_step_valid"] is True
    assert comparison["min_notional_ok"] is True
    assert comparison["short_stop_still_above_fresh_mark"] is True
    assert comparison["short_take_profit_still_below_fresh_mark"] is True
    assert round(comparison["notional_after_rounding_at_fresh_mark"], 4) == 435.4721
    assert round(comparison["estimated_loss_at_stop_from_fresh_mark"], 4) == 4.4401
    assert round(comparison["estimated_reward_at_take_profit_from_fresh_mark"], 4) == 8.8802
    assert payload["signed_request_regeneration_decision"]["must_regenerate_signed_request_before_submit"] is False
    assert payload["operator_final_readonly_refresh_packet"]["operator_should_continue_to_submit_gate_preview"] is True
    records = load_tiny_live_final_readonly_mark_price_refresh_gate_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    _assert_safety(payload, fetched=True)
    _assert_no_secret_values(payload)


def test_regenerate_when_fresh_mark_invalidates_short_stop_direction(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r253(tmp_path, monkeypatch)
    fake_urlopen = _FakeUrlOpen(mark_price="63000")

    payload = build_tiny_live_final_readonly_mark_price_refresh_gate(
        log_dir=log_dir,
        fetch_final_readonly_market=True,
        confirm_tiny_live_final_readonly_refresh=CONFIRM_TINY_LIVE_FINAL_READONLY_REFRESH_PHRASE,
        now=NOW,
        urlopen_func=fake_urlopen,
    )

    assert payload["final_readonly_refresh_overall_status"] == (
        TINY_LIVE_FINAL_READONLY_REFRESH_FETCHED_REGENERATE_SIGNED_REQUEST_REQUIRED
    )
    assert payload["fresh_vs_signed_context_comparison"]["short_stop_still_above_fresh_mark"] is False
    assert payload["signed_request_regeneration_decision"]["must_regenerate_signed_request_before_submit"] is True
    assert "short_stop_still_above_fresh_mark" in payload["signed_request_regeneration_decision"]["blocking_reasons"]
    assert payload["operator_final_readonly_refresh_packet"]["operator_should_regenerate_signed_request"] is True
    _assert_safety(payload, fetched=True)


def test_regenerate_when_min_notional_invalid(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r253(tmp_path, monkeypatch)

    class HighMinNotionalUrlOpen(_FakeUrlOpen):
        def __call__(self, request: urllib.request.Request, timeout: float) -> _FakeResponse:
            if request.full_url.endswith("/fapi/v1/exchangeInfo"):
                self.calls.append(request)
                payload = _exchange_info_payload()
                payload["symbols"][0]["filters"][2]["notional"] = "500"
                return _FakeResponse(payload)
            return super().__call__(request, timeout)

    payload = build_tiny_live_final_readonly_mark_price_refresh_gate(
        log_dir=log_dir,
        fetch_final_readonly_market=True,
        confirm_tiny_live_final_readonly_refresh=CONFIRM_TINY_LIVE_FINAL_READONLY_REFRESH_PHRASE,
        now=NOW,
        urlopen_func=HighMinNotionalUrlOpen(mark_price="62210.3"),
    )

    assert payload["fresh_vs_signed_context_comparison"]["min_notional_ok"] is False
    assert payload["signed_request_regeneration_decision"]["must_regenerate_signed_request_before_submit"] is True
    assert "min_notional_ok" in payload["signed_request_regeneration_decision"]["blocking_reasons"]


def test_endpoint_safety_rejects_order_account_private_and_signed_endpoints() -> None:
    plan = {
        "planned_requests": [
            {"method": "POST", "path": "/fapi/v1/order", "query": {"symbol": "BTCUSDT"}},
            {
                "method": "GET",
                "path": "/fapi/v2/account",
                "query": {"timestamp": "1", "signature": "x"},
            },
        ],
        "method_allowlist": ["GET"],
        "uses_api_key": False,
        "uses_api_secret": False,
        "requires_signature": False,
    }

    validation = validate_final_readonly_endpoint_safety(plan)

    assert validation["valid"] is False
    assert validation["order_endpoint_called"] is True
    assert validation["account_endpoint_called"] is True
    assert validation["signed_endpoint_called"] is True


def test_no_secret_values_in_output_when_env_contains_credentials(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r253(tmp_path, monkeypatch)
    monkeypatch.setenv(BINANCE_API_KEY_ENV, API_KEY)
    monkeypatch.setenv(BINANCE_API_SECRET_ENV, API_SECRET)

    payload = build_tiny_live_final_readonly_mark_price_refresh_gate(log_dir=log_dir, now=NOW)

    assert payload["safety"]["secrets_read"] is False
    assert payload["safety"]["secret_values_in_output"] is False
    _assert_no_secret_values(payload)


def _fixture_r253(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _fixture_r252(tmp_path, monkeypatch)
    r252 = build_tiny_live_submit_readiness_preview(
        log_dir=log_dir,
        record_submit_readiness_preview=True,
        confirm_tiny_live_submit_readiness_preview=CONFIRM_TINY_LIVE_SUBMIT_READINESS_PREVIEW_PHRASE,
        now=NOW,
    )
    assert r252["submit_readiness_preview_recorded"] is True
    return log_dir, risk_path, lane_path


def _exchange_info_payload() -> dict[str, object]:
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "quantityPrecision": 3,
                "pricePrecision": 1,
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                    {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                ],
            }
        ]
    }


def _assert_ready_inputs(payload: Mapping[str, object]) -> None:
    summary = payload["input_summary"]
    assert summary["r252_submit_readiness_found"] is True
    assert summary["r252_submit_readiness_valid"] is True
    assert summary["r251e_runtime_signed_request_found"] is True
    assert summary["r251e_runtime_signed_request_valid"] is True
    assert summary["r251_signed_request_found"] is True
    assert summary["r251_signed_request_valid"] is True
    assert summary["r249_executable_payload_found"] is True
    assert summary["r249_executable_payload_valid"] is True
    assert summary["r248_stop_take_profit_source_found"] is True
    assert summary["r248_stop_take_profit_source_valid"] is True
    signed = payload["signed_artifact_context_summary"]
    assert signed["reference_price"] == 62210.3
    assert signed["quantity"] == 0.007
    assert signed["stop_price"] == 62844.6
    assert signed["take_profit_price"] == 60941.7
    assert signed["side"] == "SELL"
    assert signed["signed_requests_count"] == 3


def _assert_safety(payload: Mapping[str, object], *, fetched: bool) -> None:
    safety = payload["safety"]
    for key in (
        "env_written",
        "env_mutated",
        "external_env_file_written",
        "config_written",
        "risk_contract_config_written",
        "lane_controls_written",
        "live_config_written",
        "hmac_signature_created",
        "signed_request_written",
        "signed_order_request_created",
        "signed_trading_request_created",
        "submit_allowed",
        "submit_attempted",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "binance_account_endpoint_called",
        "private_binance_endpoint_called",
        "signed_binance_endpoint_called",
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "kill_switch_disabled",
        "secrets_read",
        "secrets_shown",
        "secrets_persisted",
        "secret_values_in_output",
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert safety[key] is False
    assert safety["binance_exchange_info_endpoint_called"] is fetched
    assert safety["binance_mark_price_endpoint_called"] is fetched
    assert safety["network_allowed"] is fetched
    assert safety["final_readonly_refresh_gate_only"] is True
    assert safety["paper_live_separation_intact"] is True


def _assert_no_secret_values(payload: Mapping[str, object]) -> None:
    raw = json.dumps(payload, sort_keys=True)
    assert API_KEY not in raw
    assert API_SECRET not in raw


def _clean_env() -> dict[str, str]:
    env = {**os.environ, "PYTHONPATH": "."}
    env.pop(BINANCE_API_KEY_ENV, None)
    env.pop(BINANCE_API_SECRET_ENV, None)
    return env
