from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_binance_readonly_precision_mark_price_gate import (
    CONFIRM_TINY_LIVE_BINANCE_READONLY_FETCH_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_BINANCE_READONLY_FETCHED_QUANTITY_PREVIEW_READY,
    TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_FETCHED,
    TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_READY,
    TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_REJECTED,
    build_quantity_preview_from_readonly_data,
    build_exchange_minimum_tiny_live_decision_packet,
    build_readonly_request_plan,
    build_tiny_live_binance_readonly_precision_mark_price_gate,
    load_tiny_live_binance_readonly_precision_mark_price_records,
    parse_mark_price_snapshot,
    parse_symbol_precision_from_exchange_info,
    validate_readonly_request_plan,
)
from src.app.hammer_radar.operator.tiny_live_precision_and_mark_price_preview import (
    CONFIRM_TINY_LIVE_PRECISION_MARK_PRICE_PREVIEW_RECORDING_PHRASE,
    build_tiny_live_precision_and_mark_price_preview,
)
from tests.hammer_radar.test_tiny_live_precision_and_mark_price_preview import (
    _fixture_logs as _r241_fixture_logs,
)

NOW = datetime(2026, 6, 10, 18, 0, tzinfo=UTC)
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
    def __init__(self) -> None:
        self.calls: list[urllib.request.Request] = []

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
            return _FakeResponse(_mark_price_payload())
        raise AssertionError(f"unexpected url: {url}")


def test_preview_makes_no_network_call(tmp_path: Path) -> None:
    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = build_tiny_live_binance_readonly_precision_mark_price_gate(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            now=NOW,
        )

    urlopen.assert_not_called()
    assert payload["status"] == TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_READY
    assert payload["readonly_fetch_requested"] is False
    assert payload["readonly_fetch_performed"] is False
    assert payload["readonly_request_plan"]["would_call_network"] is False
    assert payload["readonly_request_plan"]["requires_confirmation"] is True
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_makes_no_network_call_and_writes_no_record(tmp_path: Path) -> None:
    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = build_tiny_live_binance_readonly_precision_mark_price_gate(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            fetch_binance_readonly=True,
            confirm_tiny_live_binance_readonly_fetch="wrong",
            now=NOW,
        )

    urlopen.assert_not_called()
    assert payload["status"] == TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["readonly_fetch_performed"] is False
    assert load_tiny_live_binance_readonly_precision_mark_price_records(log_dir=log_dir, limit=0) == []


def test_exact_confirmation_calls_only_allowed_public_get_endpoints(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    fake_urlopen = _FakeUrlOpen()
    env_path = tmp_path / ".env"
    env_path.write_text("UNCHANGED=1\n", encoding="utf-8")
    before_env = dict(os.environ)
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")
    before_env_file = env_path.read_text(encoding="utf-8")

    with (
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = build_tiny_live_binance_readonly_precision_mark_price_gate(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            fetch_binance_readonly=True,
            confirm_tiny_live_binance_readonly_fetch=CONFIRM_TINY_LIVE_BINANCE_READONLY_FETCH_PHRASE,
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
    assert env_path.read_text(encoding="utf-8") == before_env_file
    assert len(fake_urlopen.calls) == 2
    assert [call.get_method() for call in fake_urlopen.calls] == ["GET", "GET"]
    assert fake_urlopen.calls[0].full_url.endswith("/fapi/v1/exchangeInfo")
    assert fake_urlopen.calls[1].full_url.endswith("/fapi/v1/premiumIndex?symbol=BTCUSDT")
    assert payload["status"] == TINY_LIVE_BINANCE_READONLY_PRECISION_MARK_PRICE_GATE_FETCHED
    assert payload["binance_readonly_overall_status"] == TINY_LIVE_BINANCE_READONLY_FETCHED_QUANTITY_PREVIEW_READY
    assert payload["binance_readonly_result"]["order_endpoint_called"] is False
    assert payload["binance_readonly_result"]["account_endpoint_called"] is False
    assert payload["binance_readonly_result"]["signed_request_created"] is False
    assert payload["quantity_preview"]["quantity_raw"] == 0.0011
    assert payload["quantity_preview"]["quantity_rounded"] == 0.001
    assert payload["quantity_preview"]["notional_after_rounding"] == 40.0
    assert payload["quantity_preview"]["min_notional_ok"] is True
    records = load_tiny_live_binance_readonly_precision_mark_price_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    assert records[0]["safety"]["binance_exchange_info_endpoint_called"] is True
    assert records[0]["safety"]["binance_mark_price_endpoint_called"] is True
    assert records[0]["safety"]["network_allowed"] is True
    assert records[0]["safety"]["order_placed"] is False
    assert records[0]["safety"]["signature_created"] is False


def test_request_plan_rejects_forbidden_endpoint_method_and_signed_private_paths() -> None:
    plan = build_readonly_request_plan(symbol="BTCUSDT")
    plan["planned_requests"] = [
        {"method": "POST", "path": "/fapi/v1/order", "query": {"symbol": "BTCUSDT"}, "symbol": "BTCUSDT"},
        {
            "method": "GET",
            "path": "/fapi/v2/account",
            "query": {"timestamp": "1", "signature": "x"},
            "symbol": "BTCUSDT",
        },
    ]

    validation = validate_readonly_request_plan(plan)

    assert validation["valid"] is False
    assert "non_get_method_forbidden" in validation["errors"]
    assert "forbidden_endpoint_path" in validation["errors"]
    assert "signed_query_param_forbidden" in validation["errors"]


def test_parse_exchange_info_precision() -> None:
    snapshot = parse_symbol_precision_from_exchange_info({"raw": _exchange_info_payload()}, symbol="BTCUSDT")

    assert snapshot == {
        "found": True,
        "symbol": "BTCUSDT",
        "quantity_precision": 3,
        "min_qty": 0.001,
        "step_size": 0.001,
        "price_precision": 1,
        "tick_size": 0.1,
        "min_notional": 5.0,
        "source": "binance_public_exchangeInfo",
    }


def test_parse_mark_price() -> None:
    snapshot = parse_mark_price_snapshot({"raw": _mark_price_payload()}, symbol="BTCUSDT")

    assert snapshot == {
        "found": True,
        "symbol": "BTCUSDT",
        "mark_price": 40000.0,
        "timestamp": 1781114400000,
        "source": "binance_public_premiumIndex",
    }


def test_quantity_preview_min_notional_true_and_false() -> None:
    precision = parse_symbol_precision_from_exchange_info({"raw": _exchange_info_payload()}, symbol="BTCUSDT")
    mark = parse_mark_price_snapshot({"raw": _mark_price_payload()}, symbol="BTCUSDT")
    ok = build_quantity_preview_from_readonly_data(
        notional_cap_usdt=44,
        precision_snapshot=precision,
        mark_price_snapshot=mark,
    )
    precision_high_min = {**precision, "min_notional": 50.0}
    blocked = build_quantity_preview_from_readonly_data(
        notional_cap_usdt=44,
        precision_snapshot=precision_high_min,
        mark_price_snapshot=mark,
    )

    assert ok["can_compute"] is True
    assert ok["min_notional_ok"] is True
    assert ok["min_qty_ok"] is True
    assert blocked["can_compute"] is False
    assert blocked["min_notional_ok"] is False
    assert "min_notional_not_met_after_rounding" in blocked["blocked_by"]


def test_exchange_minimum_decision_packet_blocks_when_44_below_min_qty_notional() -> None:
    precision = parse_symbol_precision_from_exchange_info({"raw": _exchange_info_payload()}, symbol="BTCUSDT")
    mark = parse_mark_price_snapshot({"raw": {"symbol": "BTCUSDT", "markPrice": "70000.0"}}, symbol="BTCUSDT")

    packet = build_exchange_minimum_tiny_live_decision_packet(
        configured_cap_usdt=44,
        precision_snapshot=precision,
        mark_price_snapshot=mark,
        operator_reported_wallet_usdt=126,
    )

    assert packet["configured_cap_possible"] is False
    assert packet["block_reason"] == "proper_tiny_live_below_exchange_minimum"
    assert packet["minimum_valid_quantity_after_rounding"] == 0.001
    assert packet["minimum_valid_notional_after_rounding"] == 70.0
    assert packet["recommended_cap_usdt"] == 70.0
    assert packet["recommended_cap_applied"] is False
    assert packet["wallet_supports_exchange_minimum_tiny"] is True
    assert packet["final_command_available"] is False
    assert packet["order_placed"] is False
    assert packet["binance_order_endpoint_called"] is False
    assert packet["binance_test_order_endpoint_called"] is False
    assert packet["secrets_shown"] is False


def test_safety_flags_preserve_non_actions(tmp_path: Path) -> None:
    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    payload = build_tiny_live_binance_readonly_precision_mark_price_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        now=NOW,
    )

    for key in (
        "env_written",
        "env_mutated",
        "config_written",
        "risk_contract_config_written",
        "lane_controls_written",
        "live_config_written",
        "order_payload_written",
        "order_payload_created",
        "executable_payload_created",
        "signed_order_request_created",
        "signed_trading_request_created",
        "signed_readonly_request_created",
        "submit_allowed",
        "order_placed",
        "real_order_placed",
        "execution_attempted",
        "binance_order_endpoint_called",
        "binance_test_order_endpoint_called",
        "binance_account_endpoint_called",
        "binance_exchange_info_endpoint_called",
        "binance_mark_price_endpoint_called",
        "network_allowed",
        "private_endpoint_called",
        "api_key_used",
        "api_secret_used",
        "signature_created",
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "kill_switch_disabled",
        "secrets_shown",
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert payload["safety"][key] is False
    assert payload["safety"]["paper_live_separation_intact"] is True
    assert payload["safety"]["binance_readonly_gate_only"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-binance-readonly-precision-mark-price-gate",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )
    help_result = subprocess.run(
        [".venv/bin/python", "-m", "src.app.hammer_radar.operator.inspect", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": "."},
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["readonly_fetch_performed"] is False
    assert "tiny-live-binance-readonly-precision-mark-price-gate" in help_result.stdout


def _fixture_logs(tmp_path: Path) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _r241_fixture_logs(tmp_path)
    build_tiny_live_precision_and_mark_price_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        record_precision_mark_price_preview=True,
        confirm_tiny_live_precision_mark_price_preview=CONFIRM_TINY_LIVE_PRECISION_MARK_PRICE_PREVIEW_RECORDING_PHRASE,
        now=NOW,
    )
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
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                ],
            }
        ]
    }


def _mark_price_payload() -> dict[str, object]:
    return {"symbol": "BTCUSDT", "markPrice": "40000.0", "time": 1781114400000}
