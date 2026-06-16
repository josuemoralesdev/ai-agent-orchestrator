from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator.approval_api import app
from src.app.hammer_radar.operator.paths import LOG_DIR_ENV_VAR
from src.app.hammer_radar.operator.tiny_live_binance_autonomous_readiness_binding import (
    BINANCE_READINESS_BLOCKED,
    BINANCE_READINESS_NOT_REQUESTED,
    BINANCE_READINESS_READY,
    CONFIRM_BINANCE_READONLY_ACCOUNT_POSITION_PHRASE,
    EVENT_TYPE,
    build_tiny_live_binance_autonomous_readiness_binding,
)
from src.app.hammer_radar.operator.tiny_live_binance_readonly_precision_mark_price_gate import (
    CONFIRM_TINY_LIVE_BINANCE_READONLY_FETCH_PHRASE,
)
from tests.hammer_radar.test_tiny_live_binance_readonly_precision_mark_price_gate import (
    _FakeResponse,
    _FakeUrlOpen,
    _exchange_info_payload,
    _fixture_logs,
    _mark_price_payload,
)

NOW = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)


def test_default_binding_makes_no_network_call(tmp_path: Path) -> None:
    log_dir, risk_path, _lane_path = _fixture_logs(tmp_path)
    _write_r279_risk_contract(risk_path)
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = build_tiny_live_binance_autonomous_readiness_binding(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            now=NOW,
        )

    urlopen.assert_not_called()
    assert payload["event_type"] == EVENT_TYPE
    assert payload["status"] == BINANCE_READINESS_NOT_REQUESTED
    assert payload["binding_supported"] is True
    assert payload["readonly_requested"] is False
    assert payload["exchange_info_checked"] is False
    assert payload["mark_price_checked"] is False
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True
    assert payload["safety"]["network_allowed"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False


def test_missing_and_wrong_precision_confirmation_blocks_without_network(tmp_path: Path) -> None:
    log_dir, risk_path, _lane_path = _fixture_logs(tmp_path)
    _write_r279_risk_contract(risk_path)
    for confirmation in (None, "wrong"):
        with patch.object(urllib.request, "urlopen") as urlopen:
            payload = build_tiny_live_binance_autonomous_readiness_binding(
                log_dir=log_dir,
                risk_contract_config_path=risk_path,
                fetch_binance_readonly_precision_mark_price=True,
                confirm_tiny_live_binance_readonly_fetch=confirmation,
                now=NOW,
            )

        urlopen.assert_not_called()
        assert payload["status"] == BINANCE_READINESS_BLOCKED
        assert payload["readonly_confirmation_valid"] is False
        assert "readonly_precision_mark_price_confirmation_invalid" in payload["readiness_blockers"]
        assert payload["safety"]["binance_order_endpoint_called"] is False
        assert payload["safety"]["binance_test_order_endpoint_called"] is False


def test_readonly_precision_confirmation_calls_only_public_readonly_path(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, _lane_path = _fixture_logs(tmp_path)
    _write_r279_risk_contract(risk_path)
    fake_urlopen = _FakeUrlOpen()
    with (
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = build_tiny_live_binance_autonomous_readiness_binding(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            fetch_binance_readonly_precision_mark_price=True,
            confirm_tiny_live_binance_readonly_fetch=CONFIRM_TINY_LIVE_BINANCE_READONLY_FETCH_PHRASE,
            now=NOW,
            urlopen_func=fake_urlopen,
        )

    execute_live_order.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert [request.get_method() for request in fake_urlopen.calls] == ["GET", "GET"]
    assert fake_urlopen.calls[0].full_url.endswith("/fapi/v1/exchangeInfo")
    assert fake_urlopen.calls[1].full_url.endswith("/fapi/v1/premiumIndex?symbol=BTCUSDT")
    assert payload["exchange_info_checked"] is True
    assert payload["mark_price_checked"] is True
    assert payload["configured_notional_cap_usdt"] == 80.0
    assert payload["configured_leverage"] == 10.0
    assert payload["configured_margin_budget_usdt"] == 8.0
    assert payload["cap_clears_exchange_minimum"] is True
    assert payload["candidate_quantity_at_cap"] == 0.002
    assert payload["candidate_notional_at_cap"] == 80.0
    assert payload["status"] == BINANCE_READINESS_BLOCKED
    assert "wallet_supports_minimum_tiny_not_verified" in payload["readiness_blockers"]
    assert payload["safety"]["binance_exchange_info_endpoint_called"] is True
    assert payload["safety"]["binance_mark_price_endpoint_called"] is True
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["leverage_change_called"] is False
    assert payload["safety"]["margin_change_called"] is False


def test_readiness_blocks_when_cap_does_not_clear_exchange_minimum(tmp_path: Path) -> None:
    log_dir, risk_path, _lane_path = _fixture_logs(tmp_path)
    _write_r279_risk_contract(risk_path)
    payload = build_tiny_live_binance_autonomous_readiness_binding(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        fetch_binance_readonly_precision_mark_price=True,
        confirm_tiny_live_binance_readonly_fetch=CONFIRM_TINY_LIVE_BINANCE_READONLY_FETCH_PHRASE,
        now=NOW,
        urlopen_func=_HighMinimumUrlOpen(),
    )

    assert payload["status"] == BINANCE_READINESS_BLOCKED
    assert payload["cap_clears_exchange_minimum"] is False
    assert "min_notional_not_met_after_rounding" in payload["readiness_blockers"]
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False


def test_readiness_can_be_ready_with_safe_mocked_wallet_and_no_position_conflict(tmp_path: Path) -> None:
    log_dir, risk_path, _lane_path = _fixture_logs(tmp_path)
    _write_r279_risk_contract(risk_path)
    payload = build_tiny_live_binance_autonomous_readiness_binding(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        fetch_binance_readonly_precision_mark_price=True,
        confirm_tiny_live_binance_readonly_fetch=CONFIRM_TINY_LIVE_BINANCE_READONLY_FETCH_PHRASE,
        account_position_snapshot={
            "available_balance_usdt": 100.0,
            "wallet_supports_minimum_tiny": True,
            "open_position_conflict": False,
            "leverage_matches_expectation": True,
            "margin_mode_matches_expectation": True,
        },
        now=NOW,
        urlopen_func=_FakeUrlOpen(),
    )

    assert payload["status"] == BINANCE_READINESS_READY
    assert payload["readiness_blockers"] == []
    assert payload["wallet_supports_minimum_tiny"] is True
    assert payload["open_position_conflict"] is False
    assert payload["autonomous_one_shot_readiness_matrix"]["binance_readiness_ready"] is True
    assert payload["autonomous_one_shot_readiness_matrix"]["one_shot_live_allowed"] is False
    assert payload["final_command_available"] is False
    assert payload["submit_allowed"] is False
    assert payload["real_order_forbidden"] is True


def test_account_position_fetch_is_explicitly_blocked_even_with_confirmation(tmp_path: Path) -> None:
    payload = build_tiny_live_binance_autonomous_readiness_binding(
        log_dir=tmp_path,
        fetch_binance_readonly_account_position=True,
        confirm_binance_readonly_account_position=CONFIRM_BINANCE_READONLY_ACCOUNT_POSITION_PHRASE,
        now=NOW,
    )

    assert payload["status"] == BINANCE_READINESS_BLOCKED
    assert payload["account_position_readiness_status"] == "NOT_IMPLEMENTED_SAFELY"
    assert "readonly_account_position_check_not_available" in payload["readiness_blockers"]
    assert payload["account_balance_checked"] is False
    assert payload["position_risk_checked"] is False
    assert payload["safety"]["signed_readonly_request_created"] is False
    assert payload["safety"]["binance_account_endpoint_called"] is False


def test_endpoint_default_does_not_fetch_network(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    with patch.object(urllib.request, "urlopen") as urlopen:
        response = TestClient(app).get("/tiny-live/binance-autonomous-readiness")

    urlopen.assert_not_called()
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == BINANCE_READINESS_NOT_REQUESTED
    assert payload["readonly_requested"] is False
    assert payload["safety"]["network_allowed"] is False


def test_endpoint_missing_confirmation_blocks_readonly_fetch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(LOG_DIR_ENV_VAR, str(tmp_path))
    with patch.object(urllib.request, "urlopen") as urlopen:
        response = TestClient(app).get("/tiny-live/binance-autonomous-readiness?fetch_readonly_precision=true")

    urlopen.assert_not_called()
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == BINANCE_READINESS_BLOCKED
    assert "readonly_precision_mark_price_confirmation_invalid" in payload["readiness_blockers"]


def test_cli_default_exists_and_hides_secrets(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path),
            "tiny-live-binance-autonomous-readiness",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={
            **os.environ,
            "PYTHONPATH": ".",
            "BINANCE_API_KEY": "secret-api-key-value",
            "BINANCE_API_SECRET": "secret-api-secret-value",
        },
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    rendered = json.dumps(payload)
    assert payload["event_type"] == EVENT_TYPE
    assert payload["safety"]["secrets_shown"] is False
    assert "secret-api-key-value" not in rendered
    assert "secret-api-secret-value" not in rendered


def test_final_console_includes_binance_autonomous_readiness_panel(tmp_path: Path) -> None:
    from src.app.hammer_radar.operator import tiny_live_final_console as final_console

    payload = final_console.build_tiny_live_final_console(log_dir=tmp_path)

    panel = payload["binance_autonomous_readiness_panel"]
    assert panel["binding_supported"] is True
    assert panel["final_command_available"] is False
    assert panel["submit_allowed"] is False
    assert panel["real_order_forbidden"] is True


class _HighMinimumUrlOpen:
    def __call__(self, request: urllib.request.Request, timeout: float) -> _FakeResponse:
        url = request.full_url
        if url.endswith("/fapi/v1/exchangeInfo"):
            payload = _exchange_info_payload()
            payload["symbols"][0]["filters"][2]["notional"] = "100"
            return _FakeResponse(payload)
        if url.endswith("/fapi/v1/premiumIndex?symbol=BTCUSDT"):
            return _FakeResponse(_mark_price_payload())
        raise AssertionError(f"unexpected url: {url}")


def _write_r279_risk_contract(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["risk_contracts"][0].update(
        {
            "max_position_notional_usdt": 80.0,
            "max_notional_usdt": 80.0,
            "margin_budget_usdt": 8.0,
            "tiny_live_margin_usdt": 8.0,
            "max_margin_usdt": 8.0,
            "leverage": 10.0,
        }
    )
    path.write_text(json.dumps(raw), encoding="utf-8")
