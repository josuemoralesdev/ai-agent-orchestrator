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
    build_tiny_live_binance_readonly_precision_mark_price_gate,
)
from src.app.hammer_radar.operator.tiny_live_leverage_notional_adjustment_preview import (
    CONFIRM_TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDING_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED_BY_R242,
    TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_CLEARS_BINANCE_MINIMUMS,
    TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_READY,
    TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDED,
    TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_REJECTED,
    build_tiny_live_leverage_notional_adjustment_preview,
    load_tiny_live_leverage_notional_adjustment_preview_records,
)
from tests.hammer_radar.test_tiny_live_binance_readonly_precision_mark_price_gate import (
    _FakeResponse,
    _fixture_logs as _r242_fixture_logs,
)

NOW = datetime(2026, 6, 10, 19, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


class _R243FakeUrlOpen:
    def __init__(self) -> None:
        self.calls: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> _FakeResponse:
        self.calls.append(request)
        if request.full_url.endswith("/fapi/v1/exchangeInfo"):
            return _FakeResponse(_exchange_info_payload())
        if request.full_url.endswith("/fapi/v1/premiumIndex?symbol=BTCUSDT"):
            return _FakeResponse(_mark_price_payload())
        raise AssertionError(f"unexpected url: {request.full_url}")


def test_preview_writes_no_record(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_logs(tmp_path)

    payload = build_tiny_live_leverage_notional_adjustment_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_READY
    assert payload["adjustment_preview_recorded"] is False
    assert payload["record_adjustment_preview_requested"] is False
    assert payload["confirmation_valid"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_logs(tmp_path)

    payload = build_tiny_live_leverage_notional_adjustment_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        record_adjustment_preview=True,
        confirm_tiny_live_leverage_notional_adjustment_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["adjustment_preview_recorded"] is False
    assert load_tiny_live_leverage_notional_adjustment_preview_records(log_dir=log_dir, limit=0) == []


def test_correct_confirmation_records_preview_only(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_logs(tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text("UNCHANGED=1\n", encoding="utf-8")
    before_env = dict(os.environ)
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")
    before_env_file = env_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = build_tiny_live_leverage_notional_adjustment_preview(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            record_adjustment_preview=True,
            confirm_tiny_live_leverage_notional_adjustment_preview=(
                CONFIRM_TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDING_PHRASE
            ),
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert dict(os.environ) == before_env
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert env_path.read_text(encoding="utf-8") == before_env_file
    assert payload["status"] == TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDED
    assert payload["adjustment_preview_recorded"] is True
    records = load_tiny_live_leverage_notional_adjustment_preview_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    assert records[0]["safety"]["leverage_notional_adjustment_preview_only"] is True
    assert records[0]["safety"]["config_written"] is False
    assert records[0]["safety"]["risk_contract_config_written"] is False
    assert records[0]["safety"]["network_allowed"] is False
    assert records[0]["safety"]["order_placed"] is False


def test_preview_requires_r242_readonly_result(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _r242_fixture_logs(tmp_path)

    payload = build_tiny_live_leverage_notional_adjustment_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["input_summary"]["r242_readonly_found"] is False
    assert payload["adjustment_preview_overall_status"] == TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_BLOCKED_BY_R242


def test_preview_requires_r240_payload_artifact(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_logs(tmp_path)
    (log_dir / "tiny_live_order_payload_write_gate.ndjson").unlink()

    payload = build_tiny_live_leverage_notional_adjustment_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["input_summary"]["r240_payload_found"] is False
    assert payload["adjustment_validation"]["valid"] is False
    assert "r240_payload_artifact_invalid_or_missing" in payload["adjustment_validation"]["errors"]


def test_preview_requires_valid_risk_contract(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_logs(tmp_path)
    config = json.loads(risk_path.read_text(encoding="utf-8"))
    for contract in config["risk_contracts"]:
        if contract.get("official_lane_key") == OFFICIAL:
            contract["max_notional_usdt"] = 45
    risk_path.write_text(json.dumps(config, sort_keys=True), encoding="utf-8")

    payload = build_tiny_live_leverage_notional_adjustment_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["input_summary"]["risk_contract_valid"] is False
    assert "risk_contract_invalid_or_missing" in payload["adjustment_validation"]["errors"]


def test_current_model_reproduces_r242_blocker(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_logs(tmp_path)

    payload = build_tiny_live_leverage_notional_adjustment_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    current = payload["current_risk_model_summary"]
    assert current["leverage"] == 1
    assert current["max_notional_usdt"] == 44
    assert current["max_loss_usdt"] == 4.44
    assert current["quantity_rounded_at_current_notional"] == 0.0
    assert current["min_notional_ok_at_current_notional"] is False
    assert "quantity_rounds_to_zero" in current["blocked_by"]
    assert "min_notional_not_met_after_rounding" in current["blocked_by"]


def test_adjusted_model_and_quantity_clear_binance_minimums(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_logs(tmp_path)

    payload = build_tiny_live_leverage_notional_adjustment_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    adjusted = payload["adjusted_leverage_notional_model_preview"]["adjusted_model"]
    quantity = payload["adjusted_quantity_preview"]
    assert adjusted["margin_budget_usdt"] == 44
    assert adjusted["leverage"] == 10
    assert adjusted["max_notional_usdt"] == 440
    assert adjusted["max_position_notional_usdt"] == 440
    assert adjusted["max_loss_requires_review"] is True
    assert adjusted["risk_contract_write_required_later"] is True
    assert quantity["can_compute"] is True
    assert quantity["quantity_rounded"] == 0.007
    assert quantity["clears_quantity_rounding"] is True
    assert quantity["clears_min_notional"] is True
    assert quantity["min_notional_ok"] is True
    assert payload["adjustment_preview_overall_status"] == (
        TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_CLEARS_BINANCE_MINIMUMS
    )


def test_safety_flags_preserve_non_actions(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_logs(tmp_path)
    payload = build_tiny_live_leverage_notional_adjustment_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
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
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "kill_switch_disabled",
        "secrets_shown",
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert payload["safety"][key] is False
    assert payload["safety"]["paper_live_separation_intact"] is True
    assert payload["safety"]["leverage_notional_adjustment_preview_only"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-leverage-notional-adjustment-preview",
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
    assert payload["adjustment_preview_recorded"] is False
    assert "tiny-live-leverage-notional-adjustment-preview" in help_result.stdout


def _fixture_logs(tmp_path: Path) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _r242_fixture_logs(tmp_path)
    fake_urlopen = _R243FakeUrlOpen()
    build_tiny_live_binance_readonly_precision_mark_price_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        lane_controls_path=lane_path,
        fetch_binance_readonly=True,
        confirm_tiny_live_binance_readonly_fetch=CONFIRM_TINY_LIVE_BINANCE_READONLY_FETCH_PHRASE,
        now=NOW,
        urlopen_func=fake_urlopen,
    )
    assert len(fake_urlopen.calls) == 2
    return log_dir, risk_path, lane_path


def _exchange_info_payload() -> dict[str, object]:
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "quantityPrecision": 3,
                "pricePrecision": 2,
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                    {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "notional": "50"},
                ],
            }
        ]
    }


def _mark_price_payload() -> dict[str, object]:
    return {"symbol": "BTCUSDT", "markPrice": "62210.3", "time": 1781110876000}
