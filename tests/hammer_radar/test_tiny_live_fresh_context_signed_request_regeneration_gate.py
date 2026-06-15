from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.tiny_live_executable_payload_write_gate import (
    LEDGER_FILENAME as R249_LEDGER_FILENAME,
)
from src.app.hammer_radar.operator.tiny_live_final_readonly_mark_price_refresh_gate import (
    CONFIRM_TINY_LIVE_FINAL_READONLY_REFRESH_PHRASE,
    build_tiny_live_final_readonly_mark_price_refresh_gate,
)
from src.app.hammer_radar.operator.tiny_live_fresh_context_signed_request_regeneration_gate import (
    CONFIRM_TINY_LIVE_FRESH_CONTEXT_REGENERATION_PHRASE,
    LEDGER_FILENAME,
    TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_BLOCKED,
    TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_READY,
    TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_REJECTED,
    TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_WRITTEN,
    build_tiny_live_fresh_context_signed_request_regeneration_gate,
    load_tiny_live_fresh_context_signed_request_regeneration_gate_records,
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
    load_tiny_live_signed_request_write_gate_records,
)
from src.app.hammer_radar.operator.tiny_live_stop_take_profit_source_gate import (
    LEDGER_FILENAME as R248_LEDGER_FILENAME,
)
from tests.hammer_radar.test_tiny_live_final_readonly_mark_price_refresh_gate import (
    _FakeUrlOpen,
    _fixture_r253,
)

NOW = datetime(2026, 6, 12, 13, 0, tzinfo=UTC)
OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"
API_KEY = "R253B_TEST_API_KEY_SHOULD_NOT_APPEAR_1234567890"
API_SECRET = "R253B_TEST_API_SECRET_SHOULD_NOT_APPEAR_1234567890"


def test_cli_exists_and_returns_json(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_ready_r253b(tmp_path, monkeypatch, mark_price="63675")
    external = _write_external_env(tmp_path, mode=0o600)

    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-fresh-context-signed-request-regeneration-gate",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=_clean_env({OVERRIDE_ENV_NAME: str(external)}),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_BLOCKED
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["input_summary"]["r253_regeneration_required"] is True
    assert payload["fresh_context_regeneration_written"] is False
    assert "exact_fresh_context_regeneration_confirmation_required" in payload["fresh_regeneration_gate_matrix"]["blocked_by"]
    assert payload["safety"]["network_allowed"] is False
    _assert_no_secret_values(payload)


def test_preview_writes_no_ledger_and_does_not_sign(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_ready_r253b(tmp_path, monkeypatch, mark_price="63675")
    before = _ledger_counts(log_dir)

    payload = build_tiny_live_fresh_context_signed_request_regeneration_gate(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_BLOCKED
    assert payload["regenerate_fresh_context_signed_request_requested"] is False
    assert payload["fresh_context_regeneration_written"] is False
    assert "exact_fresh_context_regeneration_confirmation_required" in payload["fresh_regeneration_gate_matrix"]["blocked_by"]
    assert payload["safety"]["hmac_signature_created"] is False
    assert _ledger_counts(log_dir) == before
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_ready_r253b(tmp_path, monkeypatch, mark_price="63675")
    external = _write_external_env(tmp_path, mode=0o600)
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(external))

    payload = build_tiny_live_fresh_context_signed_request_regeneration_gate(
        log_dir=log_dir,
        regenerate_fresh_context_signed_request=True,
        confirm_tiny_live_fresh_context_regeneration="wrong",
        now=NOW,
    )

    assert payload["status"] == TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["fresh_context_regeneration_written"] is False
    assert payload["fresh_regeneration_overall_status"] == (
        "TINY_LIVE_FRESH_CONTEXT_REGENERATION_REJECTED_BAD_CONFIRMATION"
    )
    assert not (log_dir / LEDGER_FILENAME).exists()


def test_blocks_if_latest_r253_does_not_require_regeneration(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_ready_r253b(tmp_path, monkeypatch, mark_price="62210.3")

    payload = build_tiny_live_fresh_context_signed_request_regeneration_gate(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_BLOCKED
    assert payload["input_summary"]["r253_regeneration_required"] is False
    assert payload["fresh_regeneration_overall_status"] == (
        "TINY_LIVE_FRESH_CONTEXT_REGENERATION_BLOCKED_BY_R253"
    )


def test_blocks_if_r253_fresh_context_missing(tmp_path: Path, monkeypatch) -> None:
    log_dir, _, _ = _fixture_r253(tmp_path, monkeypatch)

    payload = build_tiny_live_fresh_context_signed_request_regeneration_gate(log_dir=log_dir, now=NOW)

    assert payload["status"] == TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_BLOCKED
    assert payload["input_summary"]["r253_final_readonly_found"] is False
    assert "r253_final_readonly_missing" in payload["fresh_regeneration_gate_matrix"]["blocked_by"]


def test_builds_fresh_short_stop_take_profit_and_payload(tmp_path: Path, monkeypatch) -> None:
    log_dir, risk_path, _ = _fixture_ready_r253b(tmp_path, monkeypatch, mark_price="63675")

    payload = build_tiny_live_fresh_context_signed_request_regeneration_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        now=NOW,
    )

    context = payload["fresh_reference_context"]
    stop = payload["fresh_stop_take_profit_source"]
    executable = payload["fresh_executable_payload_summary"]
    assert context["reference_price"] == 63675.0
    assert stop["quantity"] == 0.006
    assert stop["quantity_sizing_plan"]["quantity_reduced_to_fit_contract"] is True
    assert stop["quantity_sizing_plan"]["candidate_notional_usdt"] <= 440
    assert stop["stop_price"] > context["reference_price"]
    assert stop["take_profit_price"] < context["reference_price"]
    assert stop["valid"] is True
    assert round(stop["estimated_loss_at_stop_usdt"], 4) <= 4.4407
    assert round(stop["risk_reward_ratio"], 2) == 2.0
    assert executable["main_order_side"] == "SELL"
    assert executable["main_order_type"] == "MARKET"
    assert executable["stop_order_side"] == "BUY"
    assert executable["stop_order_type"] == "STOP_MARKET"
    assert executable["take_profit_order_side"] == "BUY"
    assert executable["take_profit_order_type"] == "TAKE_PROFIT_MARKET"
    assert executable["reduce_only"] is True
    assert executable["submit_allowed"] is False
    assert executable["network_allowed"] is False
    assert executable["order_placed"] is False


def test_exact_confirmation_writes_fresh_signed_artifact_and_no_secrets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    log_dir, risk_path, lane_path = _fixture_ready_r253b(tmp_path, monkeypatch, mark_price="63675")
    external = _write_external_env(tmp_path, mode=0o600)
    before_external = external.read_text(encoding="utf-8")
    before_risk = risk_path.read_text(encoding="utf-8")
    before_lane = lane_path.read_text(encoding="utf-8")
    monkeypatch.setenv(OVERRIDE_ENV_NAME, str(external))
    monkeypatch.delenv(BINANCE_API_KEY_ENV, raising=False)
    monkeypatch.delenv(BINANCE_API_SECRET_ENV, raising=False)

    payload = build_tiny_live_fresh_context_signed_request_regeneration_gate(
        log_dir=log_dir,
        risk_contract_config_path=risk_path,
        regenerate_fresh_context_signed_request=True,
        confirm_tiny_live_fresh_context_regeneration=CONFIRM_TINY_LIVE_FRESH_CONTEXT_REGENERATION_PHRASE,
        now=NOW,
    )

    assert external.read_text(encoding="utf-8") == before_external
    assert risk_path.read_text(encoding="utf-8") == before_risk
    assert lane_path.read_text(encoding="utf-8") == before_lane
    assert payload["status"] == TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE_WRITTEN
    assert payload["confirmation_valid"] is True
    assert payload["fresh_context_regeneration_written"] is True
    assert payload["fresh_regeneration_overall_status"] == (
        "TINY_LIVE_FRESH_CONTEXT_REGENERATION_WRITTEN_R254_PREVIEW_REQUIRED"
    )
    signed_summary = payload["fresh_signed_request_artifact_summary"]
    assert signed_summary["signed_requests_count"] == 3
    assert signed_summary["main_order_signature_present"] is True
    assert signed_summary["stop_order_signature_present"] is True
    assert signed_summary["take_profit_order_signature_present"] is True
    assert signed_summary["submit_allowed"] is False
    assert signed_summary["order_placed"] is False
    assert signed_summary["binance_order_endpoint_called"] is False
    assert signed_summary["network_allowed"] is False
    assert payload["secret_validation"]["valid"] is True
    assert payload["secret_validation"]["raw_api_key_found_in_artifacts"] is False
    assert payload["secret_validation"]["raw_api_secret_found_in_artifacts"] is False
    assert payload["secret_validation"]["secret_values_in_output"] is False
    assert payload["fresh_regeneration_gate_matrix"]["fresh_signed_request_written"] is True
    assert payload["operator_fresh_regeneration_packet"]["operator_should_submit_now"] is False
    assert payload["operator_fresh_regeneration_packet"]["operator_should_place_order"] is False
    assert payload["operator_fresh_regeneration_packet"]["next_required_human_action"] == (
        "CONTINUE_TO_R254_SUBMIT_GATE_PREVIEW"
    )
    _assert_safety_written(payload)
    _assert_no_secret_values(payload)

    records = load_tiny_live_fresh_context_signed_request_regeneration_gate_records(
        log_dir=log_dir,
        limit=0,
    )
    assert len(records) == 1
    assert (log_dir / R248_LEDGER_FILENAME).exists()
    assert (log_dir / R249_LEDGER_FILENAME).exists()
    assert (log_dir / R251_LEDGER_FILENAME).exists()
    r251_records = load_tiny_live_signed_request_write_gate_records(log_dir=log_dir, limit=0)
    artifact = r251_records[-1]["signed_request_artifact"]
    assert artifact["created_by_phase"] == (
        "R253B_TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE"
    )
    for request in artifact["signed_requests"].values():
        assert re.fullmatch(r"[0-9a-f]{64}", request["signature"])
        assert request["submit_allowed"] is False
        assert request["network_allowed"] is False
    raw = "\n".join(path.read_text(encoding="utf-8") for path in (
        log_dir / R248_LEDGER_FILENAME,
        log_dir / R249_LEDGER_FILENAME,
        log_dir / R251_LEDGER_FILENAME,
        log_dir / LEDGER_FILENAME,
    ))
    assert API_KEY not in raw
    assert API_SECRET not in raw


def _fixture_ready_r253b(tmp_path: Path, monkeypatch, *, mark_price: str) -> tuple[Path, Path, Path]:
    log_dir, risk_path, lane_path = _fixture_r253(tmp_path, monkeypatch)
    r253 = build_tiny_live_final_readonly_mark_price_refresh_gate(
        log_dir=log_dir,
        fetch_final_readonly_market=True,
        confirm_tiny_live_final_readonly_refresh=CONFIRM_TINY_LIVE_FINAL_READONLY_REFRESH_PHRASE,
        now=NOW,
        urlopen_func=_FakeUrlOpen(mark_price=mark_price),
    )
    assert r253["final_readonly_market_fetched"] is True
    return log_dir, risk_path, lane_path


def _write_external_env(tmp_path: Path, *, mode: int) -> Path:
    external = tmp_path / "binance-signing.env"
    external.write_text(
        f"{BINANCE_API_KEY_ENV}={API_KEY}\n{BINANCE_API_SECRET_ENV}={API_SECRET}\n",
        encoding="utf-8",
    )
    os.chmod(external, mode)
    return external


def _clean_env(extra: dict[str, str]) -> dict[str, str]:
    env = {**os.environ, "PYTHONPATH": ".", **extra}
    env.pop(BINANCE_API_KEY_ENV, None)
    env.pop(BINANCE_API_SECRET_ENV, None)
    return env


def _ledger_counts(log_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in (R248_LEDGER_FILENAME, R249_LEDGER_FILENAME, R251_LEDGER_FILENAME, LEDGER_FILENAME):
        path = log_dir / name
        counts[name] = len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0
    return counts


def _assert_no_secret_values(payload: Mapping[str, object]) -> None:
    raw = json.dumps(payload, sort_keys=True)
    assert API_KEY not in raw
    assert API_SECRET not in raw


def _assert_safety_written(payload: Mapping[str, object]) -> None:
    safety = payload["safety"]
    for key in (
        "env_written",
        "env_mutated",
        "external_env_file_written",
        "config_written",
        "risk_contract_config_written",
        "lane_controls_written",
        "live_config_written",
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
        "secrets_shown",
        "secrets_persisted",
        "secret_values_in_output",
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert safety[key] is False
    assert safety["fresh_context_signed_request_regeneration_only"] is True
    assert safety["hmac_signature_created"] is True
    assert safety["signed_request_written"] is True
    assert safety["signed_order_request_created"] is True
    assert safety["signed_trading_request_created"] is True
    assert safety["paper_live_separation_intact"] is True
