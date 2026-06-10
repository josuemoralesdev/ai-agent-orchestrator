from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_order_payload_write_gate import (
    CONFIRM_TINY_LIVE_ORDER_PAYLOAD_WRITE_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_READY,
    TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_REJECTED,
    TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_WRITTEN,
    build_non_executable_order_payload_artifact,
    build_tiny_live_order_payload_write_gate,
    load_tiny_live_order_payload_write_gate_records,
    validate_non_executable_order_payload_artifact,
)
from tests.hammer_radar.test_tiny_live_order_payload_preview import (
    _fixture_logs as _r239_fixture_logs,
    _write_lane_controls,
    _write_risk_contract_config,
)
from tests.hammer_radar.test_tiny_live_order_payload_preview import (
    _append,
)

NOW = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_payload_artifact(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    payload = build_tiny_live_order_payload_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_READY
    assert payload["order_payload_written"] is False
    assert payload["write_order_payload_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["order_payload_write_preview"]["would_write"] is True
    assert payload["order_payload_write_preview"]["order_payload_artifact"] == "ledger_only_non_executable"
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_and_writes_no_artifact(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    payload = build_tiny_live_order_payload_write_gate(
        log_dir=log_dir,
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
        write_order_payload=True,
        confirm_tiny_live_order_payload_write="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["order_payload_written"] is False
    assert payload["order_payload_write_overall_status"] == "TINY_LIVE_ORDER_PAYLOAD_WRITE_REJECTED_BAD_CONFIRMATION"
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_exact_confirmation_writes_only_non_executable_payload_artifact(tmp_path: Path) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir = _fixture_logs(tmp_path)
    risk_path = _write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json")
    lane_path = _write_lane_controls(tmp_path / "lane_controls.json")
    env_path = tmp_path / ".env"
    env_path.write_text("UNCHANGED=1\n", encoding="utf-8")
    before_env = dict(os.environ)
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")
    before_env_file = env_path.read_text(encoding="utf-8")
    protected_logs = {
        "paper_outcomes": log_dir / "paper_outcomes.ndjson",
        "strategy_performance": log_dir / "strategy_performance.ndjson",
        "strategy_promotion_status": log_dir / "strategy_promotion_status.ndjson",
    }
    before_logs = {name: path.read_text(encoding="utf-8") for name, path in protected_logs.items()}

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = build_tiny_live_order_payload_write_gate(
            log_dir=log_dir,
            risk_contract_config_path=risk_path,
            lane_controls_path=lane_path,
            write_order_payload=True,
            confirm_tiny_live_order_payload_write=CONFIRM_TINY_LIVE_ORDER_PAYLOAD_WRITE_PHRASE,
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
    assert {name: path.read_text(encoding="utf-8") for name, path in protected_logs.items()} == before_logs

    records = load_tiny_live_order_payload_write_gate_records(log_dir=log_dir, limit=0)
    assert payload["status"] == TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE_WRITTEN
    assert payload["order_payload_written"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "TINY_LIVE_ORDER_PAYLOAD_WRITE_GATE"
    artifact = records[0]["order_payload"]
    assert validate_non_executable_order_payload_artifact(artifact)["valid"] is True
    assert artifact["order_payload_created"] is True
    assert artifact["executable_payload_created"] is False
    assert artifact["signed"] is False
    assert artifact["signed_order_request_created"] is False
    assert artifact["signed_trading_request_created"] is False
    assert artifact["submit_allowed"] is False
    assert artifact["binance_call_allowed"] is False
    assert artifact["network_allowed"] is False
    assert artifact["quantity"] is None
    assert artifact["quantity_source"] == "requires_precision_and_mark_price_later"
    assert artifact["order_placed"] is False
    assert set(
        [
            "symbol_precision_check",
            "mark_price_or_candidate_price_snapshot",
            "quantity_rounding",
            "min_notional_check",
            "final_operator_executable_payload_confirmation",
            "signature_gate",
            "submit_gate",
        ]
    ).issubset(set(artifact["missing_before_executable_payload"]))
    assert payload["post_write_verification"]["matching_order_payload_found"] is True
    assert payload["post_write_verification"]["matching_order_payload_valid"] is True
    assert payload["post_write_verification"]["order_payload_created"] is True
    assert payload["post_write_verification"]["executable_payload_created"] is False
    assert payload["post_write_verification"]["signed_order_request_created"] is False
    assert payload["post_write_verification"]["signed_trading_request_created"] is False
    assert payload["post_write_verification"]["submit_allowed"] is False
    assert payload["post_write_verification"]["order_placed"] is False
    assert payload["post_write_verification"]["binance_call_allowed"] is False
    assert payload["post_write_verification"]["network_allowed"] is False
    assert payload["order_payload_write_gate_matrix"]["order_payload_created"] is True
    assert payload["order_payload_write_gate_matrix"]["executable_payload_created"] is False
    assert payload["order_payload_write_gate_matrix"]["signed_order_request_created"] is False
    assert payload["order_payload_write_gate_matrix"]["order_ready"] is False
    assert payload["order_payload_write_gate_matrix"]["live_ready_today"] is False
    assert payload["operator_order_payload_write_review_packet"]["operator_should_sign_request"] is False
    assert payload["operator_order_payload_write_review_packet"]["operator_should_place_order"] is False


def test_non_executable_payload_artifact_validates() -> None:
    artifact = build_non_executable_order_payload_artifact(
        latest_r239={"order_payload_preview_record_id": "r239_fixture"},
        latest_r238={"order_preflight": {"order_preflight_id": "r238_order_preflight_BTCUSDT_8m_short_ladder_close_50_618"}},
        latest_r236={"lane_arm": {"lane_arm_id": "r236_lane_arm_BTCUSDT_8m_short_ladder_close_50_618"}},
        risk_config={"matching_risk_contract": {"max_notional_usdt": 44, "max_loss_usdt": 4.44, "leverage": 1}},
        now=NOW,
    )

    validation = validate_non_executable_order_payload_artifact(artifact)

    assert validation["valid"] is True
    assert artifact["artifact_only"] is True
    assert artifact["executable"] is False
    assert artifact["signed"] is False
    assert artifact["submit_allowed"] is False
    assert artifact["binance_call_allowed"] is False
    assert artifact["network_allowed"] is False
    assert artifact["quantity"] is None


def test_safety_flags_preserve_non_actions(tmp_path: Path) -> None:
    payload = build_tiny_live_order_payload_write_gate(
        log_dir=_fixture_logs(tmp_path),
        risk_contract_config_path=_write_risk_contract_config(tmp_path / "tiny_live_risk_contracts.json"),
        lane_controls_path=_write_lane_controls(tmp_path / "lane_controls.json"),
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
    assert payload["safety"]["order_payload_write_gate_only"] is True
    assert payload["safety"]["non_executable_artifact_only"] is True


def test_cli_exists(tmp_path: Path) -> None:
    log_dir = _fixture_logs(tmp_path)
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-order-payload-write-gate",
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
    assert payload["order_payload_written"] is False
    assert "tiny-live-order-payload-write-gate" in help_result.stdout


def _fixture_logs(tmp_path: Path) -> Path:
    log_dir = _r239_fixture_logs(tmp_path)
    _append(log_dir / "tiny_live_order_payload_preview.ndjson", _r239_payload_preview_record())
    return log_dir


def _r239_payload_preview_record() -> dict[str, object]:
    return {
        "event_type": "TINY_LIVE_ORDER_PAYLOAD_PREVIEW",
        "status": "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_RECORDED",
        "order_payload_preview_record_id": "r239_order_payload_preview_record_fixture",
        "generated_at": NOW.isoformat(),
        "order_payload_preview_recorded": True,
        "record_order_payload_preview_requested": True,
        "confirmation_valid": True,
        "target_scope": {
            "official_lane_key": OFFICIAL,
            "symbol": "BTCUSDT",
            "timeframe": "8m",
            "direction": "short",
            "entry_mode": "ladder_close_50_618",
            "order_payload_created": False,
            "executable_payload_created": False,
            "signed_order_request_created": False,
            "order_placed": False,
            "kill_switch_disabled": False,
        },
        "input_summary": {
            "r238_order_preflight_found": True,
            "r238_order_preflight_valid": True,
            "r236_lane_arm_found": True,
            "r236_lane_arm_valid": True,
            "r230_risk_contract_config_found": True,
            "risk_contract_valid": True,
            "r228_evidence_ready": True,
            "fisherman_ready": True,
        },
        "non_executable_order_payload_preview": {
            "order_payload_preview_id": "r239_order_payload_preview_BTCUSDT_8m_short_ladder_close_50_618_fixture",
            "preview_only": True,
            "executable": False,
            "signed": False,
            "submit_allowed": False,
            "binance_call_allowed": False,
            "network_allowed": False,
            "official_lane_key": OFFICIAL,
            "exchange": "binance_futures",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "position_side": "BOTH|SHORT|null",
            "order_type": "MARKET|LIMIT_PREVIEW_ONLY",
            "time_in_force": None,
            "quantity_preview": None,
            "quantity_source": "requires_precision_and_mark_price_later",
            "notional_cap_usdt": 44,
            "max_loss_usdt": 4.44,
            "leverage": 1,
            "reduce_only": False,
            "stop_required": True,
            "take_profit_required": True,
            "stop_payload_preview": {
                "preview_only": True,
                "order_type": "STOP_MARKET|STOP_PREVIEW_ONLY",
                "side": "BUY",
                "reduce_only": True,
                "stop_price": None,
                "requires_future_price_precision": True,
            },
            "take_profit_payload_preview": {
                "preview_only": True,
                "order_type": "TAKE_PROFIT_MARKET|TP_PREVIEW_ONLY",
                "side": "BUY",
                "reduce_only": True,
                "take_profit_price": None,
                "requires_future_price_precision": True,
            },
            "missing_before_payload_write": [
                "symbol_precision_check",
                "mark_price_or_candidate_price_snapshot",
                "quantity_rounding",
                "min_notional_check",
                "final_operator_payload_confirmation",
            ],
        },
        "order_payload_preview_validation": {"valid": True, "errors": [], "warnings": []},
        "order_payload_preview_gate_matrix": {
            "order_preflight_written": True,
            "order_payload_preview_ready": True,
            "order_payload_created": False,
            "executable_payload_created": False,
            "signed_order_request_created": False,
            "order_ready": False,
            "live_ready_today": False,
        },
        "order_payload_preview_overall_status": "TINY_LIVE_ORDER_PAYLOAD_PREVIEW_READY_FOR_FUTURE_GATE",
    }
