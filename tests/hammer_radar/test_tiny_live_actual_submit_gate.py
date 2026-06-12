from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_actual_submit_gate import (
    DRY_PREVIEW_CONFIRMATION_PHRASE,
    LEDGER_FILENAME,
    REAL_SUBMIT_CONFIRMATION_PHRASE,
    TINY_LIVE_ACTUAL_SUBMIT_GATE_DRY_PREVIEW_RECORDED,
    TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED,
    TINY_LIVE_ACTUAL_SUBMIT_GATE_MOCK_SUBMITTED,
    TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED,
    append_tiny_live_actual_submit_gate_record,
    build_idempotency_key_for_tiny_live_submit,
    build_tiny_live_actual_submit_gate,
    execute_actual_submit_with_injected_client,
    load_latest_tiny_live_signed_request_write_gate,
    load_tiny_live_actual_submit_gate_records,
    validate_exactly_three_order_triplet,
    validate_kill_switch_and_lane_controls_for_tiny_live_submit,
    validate_no_prior_live_submit_for_idempotency_key,
    validate_order_endpoint_allowlist,
    validate_order_sequence_main_stop_take_profit,
    validate_signed_request_timestamp_freshness,
    validate_tiny_live_risk_contract_still_within_bounds,
)
from src.app.hammer_radar.operator.tiny_live_runtime_credential_source_drill import (
    OVERRIDE_ENV_NAME,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_runtime_source_write_gate import (
    BINANCE_API_KEY_ENV,
    BINANCE_API_SECRET_ENV,
)
from src.app.hammer_radar.operator.tiny_live_submit_gate_preview import (
    CONFIRM_TINY_LIVE_SUBMIT_GATE_PREVIEW_PHRASE,
    build_tiny_live_submit_gate_preview,
)
from tests.hammer_radar.test_tiny_live_fresh_context_signed_request_regeneration_gate import (
    API_KEY,
    API_SECRET,
    _clean_env,
    _write_external_env,
)
from tests.hammer_radar.test_tiny_live_submit_gate_preview import (
    NOW,
    _fixture_r254,
)

OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_cli_exists_and_returns_json(tmp_path: Path, monkeypatch) -> None:
    log_dir, external = _fixture_r255(tmp_path, monkeypatch)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-actual-submit-gate",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=_clean_env({OVERRIDE_ENV_NAME: str(external)}),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["actual_submit_executed"] is False
    assert payload["target_scope"]["submit_allowed"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    _assert_no_secret_values(payload)


def test_default_preview_makes_no_network_call_and_does_not_submit(tmp_path: Path, monkeypatch) -> None:
    log_dir, _ = _fixture_r255(tmp_path, monkeypatch)

    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = build_tiny_live_actual_submit_gate(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    assert payload["actual_submit_executed"] is False
    assert payload["target_scope"]["order_placed"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()
    _assert_actual_submit_safety(payload)


def test_dry_preview_exact_confirmation_records_preview_only(tmp_path: Path, monkeypatch) -> None:
    log_dir, _ = _fixture_r255(tmp_path, monkeypatch)

    payload = build_tiny_live_actual_submit_gate(
        log_dir=log_dir,
        dry_run_actual_submit_gate=True,
        record_actual_submit_gate_preview=True,
        confirm_tiny_live_actual_submit_gate_preview=DRY_PREVIEW_CONFIRMATION_PHRASE,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ACTUAL_SUBMIT_GATE_DRY_PREVIEW_RECORDED
    assert payload["preview_confirmation_valid"] is True
    assert payload["actual_submit_executed"] is False
    assert payload["actual_submit_gate_overall_status"] == (
        "TINY_LIVE_ACTUAL_SUBMIT_GATE_DRY_PREVIEW_RECORDED_AWAITING_OPERATOR_REAL_SUBMIT"
    )
    records = load_tiny_live_actual_submit_gate_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    _assert_actual_submit_safety(payload)


def test_wrong_confirmation_rejects(tmp_path: Path, monkeypatch) -> None:
    log_dir, _ = _fixture_r255(tmp_path, monkeypatch)

    payload = build_tiny_live_actual_submit_gate(
        log_dir=log_dir,
        record_actual_submit_gate_preview=True,
        confirm_tiny_live_actual_submit_gate_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED
    assert payload["preview_confirmation_valid"] is False
    assert payload["actual_submit_executed"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_real_submit_path_rejects_without_exact_real_phrase(tmp_path: Path, monkeypatch) -> None:
    log_dir, _ = _fixture_r255(tmp_path, monkeypatch)

    payload = build_tiny_live_actual_submit_gate(
        log_dir=log_dir,
        execute_actual_submit=True,
        confirm_tiny_live_actual_submit="wrong",
        allow_real_binance_order_endpoint=True,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED
    assert payload["real_submit_confirmation_valid"] is False
    assert payload["actual_submit_executed"] is False


def test_real_submit_path_rejects_without_allow_endpoint_flag(tmp_path: Path, monkeypatch) -> None:
    log_dir, _ = _fixture_r255(tmp_path, monkeypatch)

    payload = build_tiny_live_actual_submit_gate(
        log_dir=log_dir,
        execute_actual_submit=True,
        confirm_tiny_live_actual_submit=REAL_SUBMIT_CONFIRMATION_PHRASE,
        allow_real_binance_order_endpoint=False,
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_ACTUAL_SUBMIT_GATE_REJECTED
    assert payload["real_submit_confirmation_valid"] is True
    assert payload["actual_submit_gate_matrix"]["allow_real_endpoint_flag"] is False
    assert payload["actual_submit_executed"] is False


def test_real_submit_path_rejects_stale_signed_timestamp(tmp_path: Path, monkeypatch) -> None:
    log_dir, _ = _fixture_r255(tmp_path, monkeypatch)

    payload = build_tiny_live_actual_submit_gate(
        log_dir=log_dir,
        execute_actual_submit=True,
        confirm_tiny_live_actual_submit=REAL_SUBMIT_CONFIRMATION_PHRASE,
        allow_real_binance_order_endpoint=True,
        now=NOW + timedelta(minutes=5),
    )

    assert payload["signed_request_freshness"]["fresh_enough_for_real_submit"] is False
    assert payload["signed_request_freshness"]["requires_regeneration"] is True
    assert payload["status"] == TINY_LIVE_ACTUAL_SUBMIT_GATE_BLOCKED
    assert payload["actual_submit_executed"] is False


def test_endpoint_allowlist_rejects_non_order_endpoint() -> None:
    triplet = _valid_triplet()
    triplet["stop_order"]["endpoint"] = "/fapi/v1/account"

    summary = validate_order_endpoint_allowlist(triplet)

    assert summary["valid"] is False
    assert summary["forbidden_endpoint_detected"] is True
    assert summary["private_account_endpoint_detected"] is True


def test_blocks_if_order_count_is_not_exactly_three() -> None:
    triplet = _valid_triplet()
    triplet.pop("take_profit_order")

    summary = validate_exactly_three_order_triplet(triplet)

    assert summary["valid"] is False
    assert summary["order_count"] == 2


def test_blocks_if_order_sequence_invalid() -> None:
    triplet = _valid_triplet()
    triplet["stop_order"]["type"] = "TAKE_PROFIT_MARKET"

    summary = validate_order_sequence_main_stop_take_profit(triplet)

    assert summary["valid"] is False


def test_blocks_if_idempotency_prior_submit_exists(tmp_path: Path, monkeypatch) -> None:
    log_dir, _ = _fixture_r255(tmp_path, monkeypatch)
    signed = load_latest_tiny_live_signed_request_write_gate(log_dir=log_dir)
    artifact = signed["signed_request_artifact"]
    key = build_idempotency_key_for_tiny_live_submit(signed_request_artifact=artifact)
    append_tiny_live_actual_submit_gate_record(
        {
            "status": TINY_LIVE_ACTUAL_SUBMIT_GATE_MOCK_SUBMITTED,
            "actual_submit_executed": True,
            "idempotency_summary": {"idempotency_key": key},
            "safety": {"secrets_shown": False, "secrets_persisted": False},
        },
        log_dir=log_dir,
        mock_submit_for_test_only=True,
    )

    summary = validate_no_prior_live_submit_for_idempotency_key(
        idempotency_key=key,
        log_dir=log_dir,
    )

    assert summary["prior_live_submit_found"] is True
    assert summary["dedupe_allows_submit"] is False


def test_blocks_if_kill_switch_disallows(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, lane_path, _ = _fixture_r254(tmp_path, monkeypatch)
    del log_dir

    summary = validate_kill_switch_and_lane_controls_for_tiny_live_submit(
        lane_controls_path=lane_path,
        risk_contract_config_path=tmp_path / "configs" / "hammer_radar" / "tiny_live_risk_contracts.json",
    )

    assert summary["kill_switch_allows_tiny_live"] is False
    assert "official_lane_not_tiny_live" in summary["blocked_by"]


def test_blocks_if_risk_contract_invalid(tmp_path: Path) -> None:
    risk_path = tmp_path / "risk.json"
    risk_path.write_text('{"risk_contracts":[]}', encoding="utf-8")

    summary = validate_tiny_live_risk_contract_still_within_bounds(
        risk_contract_config_path=risk_path,
        order_triplet=_valid_triplet(),
    )

    assert summary["within_tiny_live_contract"] is False


def test_mock_submit_can_inject_fake_client_and_record_without_real_network(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir, _ = _fixture_r255(tmp_path, monkeypatch)
    signed = load_latest_tiny_live_signed_request_write_gate(log_dir=log_dir)
    artifact = signed["signed_request_artifact"]
    key = build_idempotency_key_for_tiny_live_submit(signed_request_artifact=artifact)
    client = _FakeSubmitClient()

    with patch.object(urllib.request, "urlopen") as urlopen:
        result = execute_actual_submit_with_injected_client(
            client=client,
            signed_request_artifact=artifact,
            idempotency_key=key,
            confirm_tiny_live_actual_submit=REAL_SUBMIT_CONFIRMATION_PHRASE,
            allow_real_binance_order_endpoint=True,
            log_dir=log_dir,
            now=NOW,
        )

    urlopen.assert_not_called()
    assert result["status"] == TINY_LIVE_ACTUAL_SUBMIT_GATE_MOCK_SUBMITTED
    assert result["actual_submit_executed"] is True
    assert len(client.requests) == 3
    assert all(request["endpoint"] == "/fapi/v1/order" for request in client.requests)
    raw = (log_dir / LEDGER_FILENAME).read_text(encoding="utf-8")
    assert API_KEY not in raw
    assert API_SECRET not in raw


def test_no_env_config_lane_mutation_and_no_secret_values(tmp_path: Path, monkeypatch) -> None:
    log_dir, risk_path, lane_path, external = _fixture_r254(tmp_path, monkeypatch)
    _record_r254(log_dir)
    before_external = external.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    payload = build_tiny_live_actual_submit_gate(log_dir=log_dir, now=NOW)

    assert external.read_text(encoding="utf-8") == before_external
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    _assert_actual_submit_safety(payload)
    _assert_no_secret_values(payload)


def test_timestamp_freshness_detects_missing_timestamp() -> None:
    summary = validate_signed_request_timestamp_freshness(signed_request_artifact={})

    assert summary["timestamp_present"] is False
    assert summary["requires_regeneration"] is True


def _fixture_r255(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    log_dir, _, _, external = _fixture_r254(tmp_path, monkeypatch)
    _record_r254(log_dir)
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(external))
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)
    return log_dir, external


def _record_r254(log_dir: Path) -> None:
    r254 = build_tiny_live_submit_gate_preview(
        log_dir=log_dir,
        record_submit_gate_preview=True,
        confirm_tiny_live_submit_gate_preview=CONFIRM_TINY_LIVE_SUBMIT_GATE_PREVIEW_PHRASE,
        now=NOW,
    )
    assert r254["submit_gate_preview_recorded"] is True


def _valid_triplet() -> dict[str, object]:
    return {
        "main_order": {
            "method": "POST",
            "endpoint": "/fapi/v1/order",
            "side": "SELL",
            "type": "MARKET",
            "quantity": 0.007,
            "submit_in_this_phase": False,
        },
        "stop_order": {
            "method": "POST",
            "endpoint": "/fapi/v1/order",
            "side": "BUY",
            "type": "STOP_MARKET",
            "quantity": 0.007,
            "stopPrice": 64309.3,
            "reduceOnly": True,
            "workingType": "MARK_PRICE",
            "submit_in_this_phase": False,
        },
        "take_profit_order": {
            "method": "POST",
            "endpoint": "/fapi/v1/order",
            "side": "BUY",
            "type": "TAKE_PROFIT_MARKET",
            "quantity": 0.007,
            "stopPrice": 62406.4,
            "reduceOnly": True,
            "workingType": "MARK_PRICE",
            "submit_in_this_phase": False,
        },
        "valid": True,
    }


class _FakeSubmitClient:
    def __init__(self) -> None:
        self.requests: list[Mapping[str, object]] = []

    def submit_order(self, request: Mapping[str, object]) -> dict[str, object]:
        self.requests.append(dict(request))
        return {"orderId": len(self.requests), "status": "MOCK_ACCEPTED"}


def _assert_actual_submit_safety(payload: Mapping[str, object]) -> None:
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
        "private_binance_endpoint_called",
        "signed_binance_endpoint_called",
        "network_allowed",
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
    assert safety["actual_submit_gate"] is True
    assert safety["dry_preview_only"] is True
    assert safety["paper_live_separation_intact"] is True


def _assert_no_secret_values(payload: Mapping[str, object]) -> None:
    raw = json.dumps(payload, sort_keys=True)
    assert API_KEY not in raw
    assert API_SECRET not in raw
    assert "BINANCE_API_KEY" not in raw
    assert "BINANCE_API_SECRET" not in raw
