from __future__ import annotations

import hmac
import json
import os
import subprocess
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from src.app.hammer_radar.operator.tiny_live_fresh_context_signed_request_regeneration_gate import (
    CONFIRM_TINY_LIVE_FRESH_CONTEXT_REGENERATION_PHRASE,
    build_tiny_live_fresh_context_signed_request_regeneration_gate,
)
from src.app.hammer_radar.operator.tiny_live_runtime_credential_source_drill import (
    OVERRIDE_ENV_NAME,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_runtime_source_write_gate import (
    BINANCE_API_KEY_ENV,
    BINANCE_API_SECRET_ENV,
)
from src.app.hammer_radar.operator.tiny_live_signed_request_write_gate import (
    LEDGER_FILENAME as R251_LEDGER_FILENAME,
)
from src.app.hammer_radar.operator.tiny_live_submit_gate_preview import (
    CONFIRM_TINY_LIVE_SUBMIT_GATE_PREVIEW_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED,
    TINY_LIVE_SUBMIT_GATE_PREVIEW_READY,
    TINY_LIVE_SUBMIT_GATE_PREVIEW_RECORDED,
    TINY_LIVE_SUBMIT_GATE_PREVIEW_REJECTED,
    build_tiny_live_submit_gate_preview,
    load_tiny_live_submit_gate_preview_records,
)
from tests.hammer_radar.test_tiny_live_fresh_context_signed_request_regeneration_gate import (
    API_KEY,
    API_SECRET,
    _clean_env,
    _fixture_ready_r253b,
    _write_external_env,
)

NOW = datetime(2026, 6, 12, 14, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"


def test_cli_exists_and_returns_json(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, external = _fixture_r254(tmp_path, monkeypatch)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-submit-gate-preview",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=_clean_env({OVERRIDE_ENV_NAME: str(external)}),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == TINY_LIVE_SUBMIT_GATE_PREVIEW_READY
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["submit_gate_preview_recorded"] is False
    _assert_ready_preview(payload, recorded=False)
    _assert_preview_safety(payload)
    _assert_no_secret_values(payload)


def test_preview_writes_no_ledger_makes_no_network_call_and_does_not_sign(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir, _, _, _ = _fixture_r254(tmp_path, monkeypatch)

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(hmac, "new") as hmac_new,
    ):
        payload = build_tiny_live_submit_gate_preview(log_dir=log_dir, now=NOW)

    urlopen.assert_not_called()
    hmac_new.assert_not_called()
    assert payload["status"] == TINY_LIVE_SUBMIT_GATE_PREVIEW_READY
    assert payload["submit_gate_preview_recorded"] is False
    assert not (log_dir / LEDGER_FILENAME).exists()
    _assert_ready_preview(payload, recorded=False)


def test_wrong_confirmation_rejects_and_writes_no_ledger(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, _ = _fixture_r254(tmp_path, monkeypatch)

    payload = build_tiny_live_submit_gate_preview(
        log_dir=log_dir,
        record_submit_gate_preview=True,
        confirm_tiny_live_submit_gate_preview="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_SUBMIT_GATE_PREVIEW_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["submit_gate_preview_recorded"] is False
    assert payload["submit_gate_preview_overall_status"] == (
        "TINY_LIVE_SUBMIT_GATE_PREVIEW_REJECTED_BAD_CONFIRMATION"
    )
    assert not (log_dir / LEDGER_FILENAME).exists()
    _assert_preview_safety(payload)


def test_exact_confirmation_records_preview_only(tmp_path: Path, monkeypatch) -> None:
    log_dir, risk_path, lane_path, external = _fixture_r254(tmp_path, monkeypatch)
    before_external = external.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    with (
        patch.object(urllib.request, "urlopen") as urlopen,
        patch.object(hmac, "new") as hmac_new,
    ):
        payload = build_tiny_live_submit_gate_preview(
            log_dir=log_dir,
            record_submit_gate_preview=True,
            confirm_tiny_live_submit_gate_preview=CONFIRM_TINY_LIVE_SUBMIT_GATE_PREVIEW_PHRASE,
            now=NOW,
        )

    urlopen.assert_not_called()
    hmac_new.assert_not_called()
    assert external.read_text(encoding="utf-8") == before_external
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert payload["status"] == TINY_LIVE_SUBMIT_GATE_PREVIEW_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["submit_gate_preview_recorded"] is True
    assert payload["submit_gate_preview_overall_status"] == (
        "TINY_LIVE_SUBMIT_GATE_PREVIEW_RECORDED_R255_SUBMIT_GATE_REQUIRED"
    )
    assert payload["operator_submit_gate_preview_packet"]["next_required_human_action"] == (
        "CONTINUE_TO_R255_ACTUAL_SUBMIT_GATE"
    )
    records = load_tiny_live_submit_gate_preview_records(log_dir=log_dir, limit=0)
    assert len(records) == 1
    _assert_ready_preview(payload, recorded=True)
    _assert_preview_safety(payload)
    _assert_no_secret_values(payload)


def test_loads_latest_r253b_fresh_regeneration(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, _ = _fixture_r254(tmp_path, monkeypatch)

    payload = build_tiny_live_submit_gate_preview(log_dir=log_dir, now=NOW)

    assert payload["input_summary"]["r253b_fresh_regeneration_found"] is True
    assert payload["input_summary"]["r253b_fresh_regeneration_valid"] is True
    assert payload["fresh_signed_request_summary"]["created_by_phase"] == (
        "R253B_TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE"
    )
    assert payload["fresh_signed_request_summary"]["signed_requests_count"] == 3


def test_blocks_if_r253b_fresh_regeneration_missing(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_ready_r253b(tmp_path, monkeypatch, mark_price="63675")

    payload = build_tiny_live_submit_gate_preview(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED
    assert payload["input_summary"]["r253b_fresh_regeneration_found"] is False
    assert payload["submit_gate_preview_overall_status"] == (
        "TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED_BY_MISSING_R253B_REGENERATION"
    )


def test_blocks_if_r253b_signed_request_invalid(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, _ = _fixture_r254(tmp_path, monkeypatch)
    _append_mutated_latest_signed_request(log_dir, signature="bad")

    payload = build_tiny_live_submit_gate_preview(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_SUBMIT_GATE_PREVIEW_BLOCKED
    assert payload["input_summary"]["r253b_signed_request_valid"] is False
    assert payload["fresh_signed_request_summary"]["all_signatures_64_hex"] is False
    assert "main_order_signature_not_64_hex" in payload["submit_gate_preview_matrix"]["blocked_by"]


def test_validates_signed_requests_count_and_all_signatures_64_hex(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir, _, _, _ = _fixture_r254(tmp_path, monkeypatch)

    payload = build_tiny_live_submit_gate_preview(log_dir=log_dir, now=NOW)

    summary = payload["fresh_signed_request_summary"]
    assert summary["signed_requests_count"] == 3
    assert summary["main_order_signature_present"] is True
    assert summary["stop_order_signature_present"] is True
    assert summary["take_profit_order_signature_present"] is True
    assert summary["all_signatures_64_hex"] is True


def test_validates_submit_order_triplet_shape_and_controls(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _, _ = _fixture_r254(tmp_path, monkeypatch)

    payload = build_tiny_live_submit_gate_preview(log_dir=log_dir, now=NOW)

    triplet = payload["submit_order_triplet_preview"]
    assert triplet["valid"] is True
    assert triplet["main_order"] == {
        "method": "POST",
        "endpoint": "/fapi/v1/order",
        "side": "SELL",
        "type": "MARKET",
        "quantity": 0.006,
        "submit_in_this_phase": False,
    }
    assert triplet["stop_order"]["side"] == "BUY"
    assert triplet["stop_order"]["type"] == "STOP_MARKET"
    assert triplet["stop_order"]["quantity"] == 0.006
    assert triplet["stop_order"]["stopPrice"] == 64415.0
    assert triplet["stop_order"]["reduceOnly"] is True
    assert triplet["stop_order"]["workingType"] == "MARK_PRICE"
    assert triplet["take_profit_order"]["side"] == "BUY"
    assert triplet["take_profit_order"]["type"] == "TAKE_PROFIT_MARKET"
    assert triplet["take_profit_order"]["quantity"] == 0.006
    assert triplet["take_profit_order"]["stopPrice"] == 62195.0
    assert triplet["take_profit_order"]["reduceOnly"] is True
    assert triplet["take_profit_order"]["workingType"] == "MARK_PRICE"

    controls = payload["submit_control_summary"]
    assert controls["submit_allowed"] is False
    assert controls["network_allowed"] is False
    assert controls["order_placed"] is False
    assert controls["requires_operator_final_submit_confirmation"] is True
    assert controls["requires_r255_submit_gate"] is True


def test_future_r255_confirmation_phrase_and_requirements_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir, _, _, _ = _fixture_r254(tmp_path, monkeypatch)

    payload = build_tiny_live_submit_gate_preview(log_dir=log_dir, now=NOW)

    phrase = payload["future_submit_confirmation_phrase"]
    assert "PLACE EXACTLY THREE BINANCE FUTURES ORDERS" in phrase
    assert "MAIN SELL MARKET 0.007 BTC" in phrase
    assert "NO OTHER ORDERS" in phrase
    reqs = payload["r255_submit_gate_requirements"]
    assert "signed request age within allowed window" in reqs["must_verify_before_submit"]
    assert "idempotency/dedupe no prior live order for same signal" in reqs["must_verify_before_submit"]
    assert "submit_allowed" in reqs["must_remain_false_until_r255"]


def test_no_env_config_lane_mutation_and_no_secrets_in_output(tmp_path: Path, monkeypatch) -> None:
    log_dir, risk_path, lane_path, external = _fixture_r254(tmp_path, monkeypatch)
    before_external = external.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")

    payload = build_tiny_live_submit_gate_preview(log_dir=log_dir, now=NOW)

    assert external.read_text(encoding="utf-8") == before_external
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert payload["safety"]["hmac_signature_created"] is False
    assert payload["safety"]["signed_request_written"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["network_allowed"] is False
    _assert_no_secret_values(payload)


def _fixture_r254(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path, Path]:
    log_dir, risk_path, lane_path = _fixture_ready_r253b(tmp_path, monkeypatch, mark_price="63675")
    external = _write_external_env(tmp_path, mode=0o600)
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(external))
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)
    r253b = build_tiny_live_fresh_context_signed_request_regeneration_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        regenerate_fresh_context_signed_request=True,
        confirm_tiny_live_fresh_context_regeneration=CONFIRM_TINY_LIVE_FRESH_CONTEXT_REGENERATION_PHRASE,
        now=NOW,
    )
    assert r253b["fresh_context_regeneration_written"] is True
    return log_dir, risk_path, lane_path, external


def _append_mutated_latest_signed_request(log_dir: Path, *, signature: str) -> None:
    path = log_dir / R251_LEDGER_FILENAME
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    latest = rows[-1]
    latest["signed_request_artifact"]["signed_requests"]["main_order"]["signature"] = signature
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(latest, sort_keys=True, separators=(",", ":")) + "\n")


def _assert_ready_preview(payload: Mapping[str, object], *, recorded: bool) -> None:
    input_summary = payload["input_summary"]
    assert input_summary["r253b_fresh_regeneration_found"] is True
    assert input_summary["r253b_fresh_regeneration_valid"] is True
    assert input_summary["r253b_signed_request_found"] is True
    assert input_summary["r253b_signed_request_valid"] is True
    assert input_summary["r253b_payload_found"] is True
    assert input_summary["r253b_payload_valid"] is True
    assert input_summary["r253b_stop_take_profit_found"] is True
    assert input_summary["r253b_stop_take_profit_valid"] is True
    assert input_summary["r253_final_readonly_found"] is True
    assert input_summary["r252_submit_readiness_found"] is True

    matrix = payload["submit_gate_preview_matrix"]
    assert matrix["fresh_regeneration_ready"] is True
    assert matrix["fresh_signed_request_valid"] is True
    assert matrix["submit_order_triplet_valid"] is True
    assert matrix["submit_controls_disabled"] is True
    assert matrix["future_submit_phrase_ready"] is True
    assert matrix["recorded"] is recorded
    assert matrix["submit_allowed"] is False
    assert matrix["order_ready"] is False
    assert matrix["live_ready_today"] is False
    assert matrix["blocked_by"] == []


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
    assert safety["submit_gate_preview_only"] is True
    assert safety["paper_live_separation_intact"] is True


def _assert_no_secret_values(payload: Mapping[str, object]) -> None:
    raw = json.dumps(payload, sort_keys=True)
    assert API_KEY not in raw
    assert API_SECRET not in raw
    assert "BINANCE_API_KEY" not in raw
    assert "BINANCE_API_SECRET" not in raw


def _clean_process_env() -> dict[str, str]:
    env = {**os.environ, "PYTHONPATH": "."}
    env.pop(BINANCE_API_KEY_ENV, None)
    env.pop(BINANCE_API_SECRET_ENV, None)
    return env
