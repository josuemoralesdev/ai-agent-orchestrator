from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_runtime_credential_source_drill import OVERRIDE_ENV_NAME
from src.app.hammer_radar.operator.tiny_live_signed_request_runtime_source_write_gate import (
    BINANCE_API_KEY_ENV,
    BINANCE_API_SECRET_ENV,
    CONFIRM_TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_PHRASE,
    build_tiny_live_signed_request_runtime_source_write_gate,
)
from src.app.hammer_radar.operator.tiny_live_submit_readiness_preview import (
    CONFIRM_TINY_LIVE_SUBMIT_READINESS_PREVIEW_PHRASE,
    FUTURE_READONLY_PHASE,
    LEDGER_FILENAME,
    TINY_LIVE_SUBMIT_READINESS_PREVIEW_READY,
    TINY_LIVE_SUBMIT_READINESS_PREVIEW_RECORDED,
    TINY_LIVE_SUBMIT_READINESS_PREVIEW_REJECTED,
    build_tiny_live_submit_readiness_preview,
    load_tiny_live_submit_readiness_preview_records,
)
from tests.hammer_radar.test_tiny_live_signed_request_runtime_source_write_gate import (
    API_KEY,
    API_SECRET,
    _write_external_env,
)
from tests.hammer_radar.test_tiny_live_signed_request_write_gate import _fixture_r251

NOW = datetime(2026, 6, 12, 11, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_cli_exists_and_returns_json(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r252(tmp_path, monkeypatch)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-submit-readiness-preview",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=_clean_env(),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == TINY_LIVE_SUBMIT_READINESS_PREVIEW_READY
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["submit_readiness_preview_recorded"] is False
    assert payload["final_readonly_refresh_requirement"]["required_before_submit"] is True
    _assert_preview_safety(payload)
    _assert_no_secret_values(payload)


def test_preview_writes_no_ledger(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r252(tmp_path, monkeypatch)

    payload = build_tiny_live_submit_readiness_preview(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_SUBMIT_READINESS_PREVIEW_READY
    assert payload["submit_readiness_preview_recorded"] is False
    assert payload["record_submit_readiness_preview_requested"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()
    _assert_ready_preview(payload, recorded=False)


def test_wrong_confirmation_rejects_and_writes_no_ledger(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r252(tmp_path, monkeypatch)

    payload = build_tiny_live_submit_readiness_preview(
        log_dir=log_dir,
        record_submit_readiness_preview=True,
        confirm_tiny_live_submit_readiness_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_SUBMIT_READINESS_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["submit_readiness_preview_recorded"] is False
    assert payload["submit_readiness_overall_status"] == (
        "TINY_LIVE_SUBMIT_READINESS_REJECTED_BAD_CONFIRMATION"
    )
    assert not (log_dir / LEDGER_FILENAME).exists()
    _assert_preview_safety(payload)


def test_exact_confirmation_records_preview_only(tmp_path: Path, monkeypatch) -> None:
    from src.app.hammer_radar.execution import binance_futures_connector

    log_dir, risk_path, lane_path = _fixture_r252(tmp_path, monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text("UNCHANGED=1\n", encoding="utf-8")
    before_env_file = env_path.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(binance_futures_connector, "execute_live_order") as execute_live_order,
        patch.object(binance_futures_connector, "preview_payload") as preview_payload,
        patch.object(binance_futures_connector, "submit_test_order") as submit_test_order,
        patch.object(binance_futures_connector, "build_signed_live_order_request") as signed_order,
    ):
        payload = build_tiny_live_submit_readiness_preview(
            log_dir=log_dir,
            record_submit_readiness_preview=True,
            confirm_tiny_live_submit_readiness_preview=(
                CONFIRM_TINY_LIVE_SUBMIT_READINESS_PREVIEW_PHRASE
            ),
            now=NOW,
        )

    urlopen.assert_not_called()
    execute_live_order.assert_not_called()
    preview_payload.assert_not_called()
    submit_test_order.assert_not_called()
    signed_order.assert_not_called()
    assert env_path.read_text(encoding="utf-8") == before_env_file
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert payload["status"] == TINY_LIVE_SUBMIT_READINESS_PREVIEW_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["submit_readiness_preview_recorded"] is True
    assert payload["submit_readiness_overall_status"] == (
        "TINY_LIVE_SUBMIT_READINESS_RECORDED_FINAL_READONLY_REFRESH_REQUIRED"
    )
    assert payload["operator_submit_readiness_preview_packet"]["next_required_human_action"] == (
        "RUN_R253_FINAL_READONLY_REFRESH"
    )
    records = load_tiny_live_submit_readiness_preview_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    _assert_ready_preview(payload, recorded=True)


def test_loads_r251e_runtime_source_signed_request(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r252(tmp_path, monkeypatch)

    payload = build_tiny_live_submit_readiness_preview(log_dir=log_dir, now=NOW)

    assert payload["input_summary"]["r251e_runtime_signed_request_found"] is True
    assert payload["input_summary"]["r251e_runtime_signed_request_valid"] is True
    assert payload["signed_request_submit_summary"]["signed_requests_count"] == 3
    assert payload["signed_request_submit_summary"]["main_order_signed"] is True
    assert payload["signed_request_submit_summary"]["stop_order_signed"] is True
    assert payload["signed_request_submit_summary"]["take_profit_order_signed"] is True


def test_blocks_if_r251e_signed_request_missing(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture_r251(tmp_path)

    payload = build_tiny_live_submit_readiness_preview(log_dir=log_dir, now=NOW)

    assert payload["status"] == "TINY_LIVE_SUBMIT_READINESS_PREVIEW_BLOCKED"
    assert payload["input_summary"]["r251e_runtime_signed_request_found"] is False
    assert payload["submit_readiness_overall_status"] == (
        "TINY_LIVE_SUBMIT_READINESS_BLOCKED_BY_MISSING_SIGNED_REQUEST"
    )
    assert "r251e_runtime_signed_request_missing" in payload["submit_blocker_summary"]["blocked_by"]
    assert payload["submit_readiness_preview_recorded"] is False


def test_safety_controls_and_future_refresh_requirement(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r252(tmp_path, monkeypatch)

    payload = build_tiny_live_submit_readiness_preview(log_dir=log_dir, now=NOW)

    assert payload["signed_request_submit_summary"]["submit_allowed"] is False
    assert payload["signed_request_submit_summary"]["network_allowed"] is False
    assert payload["signed_request_submit_summary"]["binance_call_allowed"] is False
    assert payload["signed_request_submit_summary"]["order_placed"] is False
    assert payload["final_readonly_refresh_requirement"]["required_before_submit"] is True
    assert payload["final_readonly_refresh_requirement"]["future_phase"] == FUTURE_READONLY_PHASE
    assert payload["submit_blocker_summary"]["submit_ready_now"] is False
    assert payload["submit_readiness_preview_matrix"]["final_readonly_refresh_required"] is True
    assert payload["submit_readiness_preview_matrix"]["submit_allowed"] is False
    assert payload["submit_readiness_preview_matrix"]["order_ready"] is False
    assert payload["operator_submit_readiness_preview_packet"]["operator_should_submit_now"] is False
    assert payload["operator_submit_readiness_preview_packet"]["operator_should_place_order"] is False
    _assert_preview_safety(payload)
    _assert_no_secret_values(payload)


def _fixture_r252(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _fixture_r251(tmp_path)
    external = _write_external_env(tmp_path, mode=0o600)
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(external))
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)
    r251e = build_tiny_live_signed_request_runtime_source_write_gate(
        log_dir=log_dir,
        write_signed_request_runtime_source=True,
        confirm_tiny_live_signed_request_runtime_source_write=(
            CONFIRM_TINY_LIVE_SIGNED_REQUEST_RUNTIME_SOURCE_WRITE_PHRASE
        ),
        now=NOW,
    )
    assert r251e["signed_request_written"] is True
    return log_dir, risk_path, lane_path


def _assert_ready_preview(payload: Mapping[str, object], *, recorded: bool) -> None:
    input_summary = payload["input_summary"]
    assert input_summary["r251e_runtime_signed_request_found"] is True
    assert input_summary["r251e_runtime_signed_request_valid"] is True
    assert input_summary["r251_signed_request_found"] is True
    assert input_summary["r251_signed_request_valid"] is True
    assert input_summary["r249_executable_payload_found"] is True
    assert input_summary["r249_executable_payload_valid"] is True
    assert input_summary["r248_stop_take_profit_source_found"] is True
    assert input_summary["r248_stop_take_profit_source_valid"] is True
    assert input_summary["r242_readonly_reference_found"] is True
    assert input_summary["r242_readonly_reference_valid"] is True

    signed = payload["signed_request_submit_summary"]
    assert signed["signed_requests_count"] == 3
    assert signed["main_order_endpoint"] == "/fapi/v1/order"
    assert signed["stop_order_endpoint"] == "/fapi/v1/order"
    assert signed["take_profit_order_endpoint"] == "/fapi/v1/order"
    assert signed["submit_allowed"] is False
    assert signed["network_allowed"] is False
    assert signed["binance_call_allowed"] is False
    assert signed["order_placed"] is False

    risk = payload["risk_context_summary"]
    assert risk["symbol"] == "BTCUSDT"
    assert risk["side"] == "SELL"
    assert risk["quantity"] == 0.007
    assert risk["reference_price"] == 62210.3
    assert risk["stop_price"] == 62844.6
    assert risk["take_profit_price"] == 60941.7
    assert round(risk["estimated_loss_at_stop_usdt"], 4) == 4.4401
    assert round(risk["estimated_reward_at_take_profit_usdt"], 4) == 8.8802
    assert risk["risk_reward_ratio"] == 2.0
    assert risk["max_loss_usdt"] == 4.44

    matrix = payload["submit_readiness_preview_matrix"]
    assert matrix["runtime_source_signed_request_ready"] is True
    assert matrix["signed_request_valid"] is True
    assert matrix["submit_controls_safe"] is True
    assert matrix["recorded"] is recorded


def _assert_preview_safety(payload: Mapping[str, object]) -> None:
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
        "binance_exchange_info_endpoint_called",
        "binance_mark_price_endpoint_called",
        "network_allowed",
        "transfer_endpoint_called",
        "withdraw_endpoint_called",
        "kill_switch_disabled",
        "secrets_shown",
        "secrets_persisted",
        "secret_values_in_output",
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert safety[key] is False
    assert safety["submit_readiness_preview_only"] is True
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
