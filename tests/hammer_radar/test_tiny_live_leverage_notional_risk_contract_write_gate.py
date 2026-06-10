from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_leverage_notional_adjustment_preview import (
    CONFIRM_TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDING_PHRASE,
    build_tiny_live_leverage_notional_adjustment_preview,
)
from src.app.hammer_radar.operator.tiny_live_leverage_notional_risk_contract_write_gate import (
    CONFIRM_TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_READY,
    TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_REJECTED,
    TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_WRITTEN,
    build_tiny_live_leverage_notional_risk_contract_write_gate,
    load_tiny_live_leverage_notional_risk_contract_write_gate_records,
    validate_adjusted_risk_contract,
)
from tests.hammer_radar.test_tiny_live_leverage_notional_adjustment_preview import (
    _fixture_logs as _r243_fixture_logs,
)

NOW = datetime(2026, 6, 10, 22, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_config(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r244(tmp_path)
    before = risk_path.read_text(encoding="utf-8")

    payload = build_tiny_live_leverage_notional_risk_contract_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_READY
    assert payload["risk_contract_written"] is False
    assert payload["write_risk_contract_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["adjusted_contract_write_preview"]["would_write"] is True
    assert risk_path.read_text(encoding="utf-8") == before
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_and_writes_no_config(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r244(tmp_path)
    before = risk_path.read_text(encoding="utf-8")

    payload = build_tiny_live_leverage_notional_risk_contract_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        write_risk_contract=True,
        confirm_tiny_live_leverage_notional_risk_contract_write="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["risk_contract_written"] is False
    assert payload["risk_contract_write_overall_status"] == (
        "TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_REJECTED_BAD_CONFIRMATION"
    )
    assert risk_path.read_text(encoding="utf-8") == before
    records = load_tiny_live_leverage_notional_risk_contract_write_gate_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    assert records[0]["risk_contract_written"] is False


def test_exact_confirmation_writes_only_risk_contract_config_and_audit_ledger(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_r244(tmp_path)
    env_path = tmp_path / ".env"
    env_path.write_text("UNCHANGED=1\n", encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")
    before_env_file = env_path.read_text(encoding="utf-8")
    before_env = dict(os.environ)

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = build_tiny_live_leverage_notional_risk_contract_write_gate(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            write_risk_contract=True,
            confirm_tiny_live_leverage_notional_risk_contract_write=(
                CONFIRM_TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_PHRASE
            ),
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert dict(os.environ) == before_env
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert env_path.read_text(encoding="utf-8") == before_env_file
    assert payload["status"] == TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE_WRITTEN
    assert payload["risk_contract_written"] is True
    assert payload["safety"]["config_written"] is True
    assert payload["safety"]["risk_contract_config_written"] is True
    assert payload["safety"]["lane_controls_written"] is False
    assert payload["safety"]["env_mutated"] is False
    assert (log_dir / LEDGER_FILENAME).exists()

    matching = _matching_contract(risk_path)
    assert matching["official_lane_key"] == OFFICIAL
    assert matching["capital_mode"] == "tiny_live_margin_10x"
    assert matching["leverage"] == 10
    assert matching["margin_budget_usdt"] == 44
    assert matching["tiny_live_margin_usdt"] == 44
    assert matching["max_notional_usdt"] == 440
    assert matching["max_position_notional_usdt"] == 440
    assert matching["max_loss_requires_review"] is True
    assert matching["live_authorized"] is False
    assert matching["live_execution_enabled"] is False
    assert matching["enabled_for_preflight"] is False
    assert matching["order_payload_forbidden_until_live_gate"] is True
    assert matching["binance_call_forbidden_until_live_gate"] is True
    assert matching["updated_by_phase"] == "R244_TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITE_GATE"
    assert payload["post_write_verification"]["matching_adjusted_contract_valid"] is True
    assert payload["risk_contract_write_overall_status"] == (
        "TINY_LIVE_LEVERAGE_NOTIONAL_RISK_CONTRACT_WRITTEN_PAYLOAD_REFRESH_REQUIRED"
    )


def test_adjusted_contract_validates(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r244(tmp_path)

    payload = build_tiny_live_leverage_notional_risk_contract_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    contract = payload["adjusted_contract_write_preview"]["proposed_adjusted_contract"]
    validation = validate_adjusted_risk_contract(contract)
    assert validation["valid"] is True
    assert payload["adjusted_contract_validation"]["valid"] is True


def test_no_env_lane_payload_signed_request_order_or_binance_mutation(tmp_path: Path) -> None:
    log_dir, risk_path, _ = _fixture_r244(tmp_path)
    payload = build_tiny_live_leverage_notional_risk_contract_write_gate(
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
    assert payload["safety"]["risk_contract_write_gate_only"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r244(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-leverage-notional-risk-contract-write-gate",
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
    assert "tiny-live-leverage-notional-risk-contract-write-gate" in help_result.stdout


def _fixture_r244(tmp_path: Path) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _r243_fixture_logs(tmp_path)
    payload = build_tiny_live_leverage_notional_adjustment_preview(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        record_adjustment_preview=True,
        confirm_tiny_live_leverage_notional_adjustment_preview=(
            CONFIRM_TINY_LIVE_LEVERAGE_NOTIONAL_ADJUSTMENT_PREVIEW_RECORDING_PHRASE
        ),
        now=NOW,
    )
    assert payload["adjustment_preview_recorded"] is True
    return log_dir, risk_path, lane_path


def _matching_contract(risk_path: Path) -> dict[str, object]:
    config = json.loads(risk_path.read_text(encoding="utf-8"))
    for contract in config["risk_contracts"]:
        if contract.get("official_lane_key") == OFFICIAL:
            return contract
    raise AssertionError("missing official contract")
