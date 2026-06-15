from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app.hammer_radar.operator import tiny_live_actual_submit_reconciliation as r264
from src.app.hammer_radar.operator.approval_api import app, _operator_ui_html

OFFICIAL = "BTCUSDT|8m|short|ladder_close_50_618"
NOW = datetime(2026, 6, 12, 14, 0, tzinfo=UTC)
API_KEY = "R264_API_KEY_SHOULD_NOT_APPEAR"
API_SECRET = "R264_API_SECRET_SHOULD_NOT_APPEAR"


def test_cli_preview_returns_json(tmp_path: Path) -> None:
    log_dir, _, _ = _fixture(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(log_dir),
            "tiny-live-actual-submit-reconcile",
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["target_scope"]["official_lane_key"] == OFFICIAL
    assert payload["actual_submit_executed"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    _assert_no_secrets(payload)


def test_dry_preview_record_writes_ledger_but_no_network_order_submit(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = r264.build_tiny_live_actual_submit_reconciliation(
            log_dir=log_dir,
            lane_controls_path=lane_path,
            risk_contract_config_path=risk_path,
            dry_run_actual_submit_reconcile=True,
            record_actual_submit_preview=True,
            confirm_actual_submit_dry_preview=r264.DRY_PREVIEW_CONFIRMATION_PHRASE,
            now=NOW,
        )
    urlopen.assert_not_called()
    assert payload["status"] == r264.TINY_LIVE_ACTUAL_SUBMIT_DRY_PREVIEW_RECORDED
    assert payload["actual_submit_preview_recorded"] is True
    assert payload["actual_submit_executed"] is False
    assert (log_dir / r264.LEDGER_FILENAME).exists()
    _assert_preview_safety(payload)


def test_wrong_live_confirmation_rejects(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    payload = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        execute_actual_live_submit=True,
        allow_binance_order_endpoint=True,
        confirm_actual_live_submit="wrong",
        now=NOW,
    )
    assert payload["status"] == r264.TINY_LIVE_ACTUAL_SUBMIT_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["actual_submit_executed"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False


def test_missing_allow_binance_order_endpoint_rejects(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    payload = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        execute_actual_live_submit=True,
        allow_binance_order_endpoint=False,
        confirm_actual_live_submit=r264.LIVE_SUBMIT_CONFIRMATION_PHRASE,
        now=NOW,
    )
    assert payload["status"] == r264.TINY_LIVE_ACTUAL_SUBMIT_BLOCKED
    assert "allow_binance_order_endpoint_flag_required" in payload["pre_submit_validation"]["blocked_by"]
    assert payload["actual_submit_executed"] is False


def test_stale_signed_triplet_blocks(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    payload = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        now=NOW + timedelta(minutes=5),
    )
    assert payload["pre_submit_validation"]["signed_triplet_fresh"] is False
    assert payload["actual_submit_overall_status"] == r264.TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_STALE_SIGNED_TRIPLET


def test_missing_r263_arming_blocks(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path, armed=False)
    payload = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        now=NOW,
    )
    assert payload["pre_submit_validation"]["controls_armed"] is False
    assert payload["actual_submit_overall_status"] == r264.TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_MISSING_R263_ARMING


def test_duplicate_submit_blocks(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    preview = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        now=NOW,
    )
    r264.append_tiny_live_actual_submit_record(
        {
            "actual_submit_executed": True,
            "idempotency": {
                "actual_submit_idempotency_key": preview["idempotency"]["actual_submit_idempotency_key"]
            },
            "safety": {"secrets_shown": False, "secret_values_in_output": False},
        },
        log_dir=log_dir,
        actual_execution_record=True,
    )
    payload = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        now=NOW,
    )
    assert payload["idempotency"]["prior_live_submit_found"] is True
    assert payload["actual_submit_overall_status"] == r264.TINY_LIVE_ACTUAL_SUBMIT_BLOCKED_BY_DUPLICATE_SUBMIT


def test_wrong_triplet_count_blocks(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path, omit_take_profit=True)
    payload = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        now=NOW,
    )
    assert payload["pre_submit_validation"]["exact_three_orders"] is False
    assert "order_count_not_three" in payload["pre_submit_validation"]["blocked_by"]


def test_main_order_shape_mismatch_blocks(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path, main_side="BUY")
    payload = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        now=NOW,
    )
    assert payload["pre_submit_validation"]["main_order_valid"] is False
    assert "main_order_shape_invalid" in payload["pre_submit_validation"]["blocked_by"]


def test_stop_tp_reduce_only_mismatch_blocks(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path, reduce_only=False)
    payload = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        now=NOW,
    )
    assert payload["pre_submit_validation"]["reduce_only_exits"] is False
    assert "reduce_only_exit_missing" in payload["pre_submit_validation"]["blocked_by"]


def test_44_margin_at_10x_blocks_as_not_proper_tiny_live(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    risk = json.loads(risk_path.read_text(encoding="utf-8"))
    row = risk["risk_contracts"][0]
    row["tiny_live_contract_mode"] = "margin_budget_cap"
    row["margin_budget_usdt"] = 44
    row["tiny_live_margin_usdt"] = 44
    row["max_notional_usdt"] = 440
    row["max_position_notional_usdt"] = 440
    row["leverage"] = 10
    risk_path.write_text(json.dumps(risk), encoding="utf-8")

    payload = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        dry_run_actual_submit_reconcile=True,
        record_actual_submit_preview=True,
        confirm_actual_submit_dry_preview=r264.DRY_PREVIEW_CONFIRMATION_PHRASE,
        now=NOW,
    )

    pre = payload["pre_submit_validation"]
    interpretation = pre["risk_contract_interpretation"]
    assert payload["status"] == r264.TINY_LIVE_ACTUAL_SUBMIT_BLOCKED
    assert pre["risk_contract_valid"] is False
    assert "risk_contract_config_invalid" in pre["blocked_by"]
    assert "risk_contract_notional_cap_exceeds_44" in interpretation["blocked_by"]
    assert interpretation["higher_notional_interpretation_rejected"] is True
    assert payload["safety"]["order_placed"] is False
    assert payload["safety"]["submit_attempted"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False
    assert payload["safety"]["secrets_shown"] is False


def test_r267_explicit_80_notional_10x_contract_is_accepted_in_dry_preview(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(
        tmp_path,
        r267_contract=True,
        reference_price=12000,
        live_execution_enabled=False,
    )

    payload = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        dry_run_actual_submit_reconcile=True,
        record_actual_submit_preview=True,
        confirm_actual_submit_dry_preview=r264.DRY_PREVIEW_CONFIRMATION_PHRASE,
        now=NOW,
    )

    pre = payload["pre_submit_validation"]
    interpretation = pre["risk_contract_interpretation"]
    assert pre["risk_contract_valid"] is True
    assert "risk_contract_config_invalid" not in pre["blocked_by"]
    assert "r262b_contract_fit_invalid" not in pre["blocked_by"]
    assert "main_order_shape_invalid" not in pre["blocked_by"]
    assert "stop_order_shape_invalid" not in pre["blocked_by"]
    assert "take_profit_order_shape_invalid" not in pre["blocked_by"]
    assert interpretation["tiny_live_contract_mode"] == "explicit_notional_cap_with_leverage"
    assert interpretation["max_position_notional_usdt"] == 80.0
    assert interpretation["derived_margin_budget_usdt"] == 8.0
    assert interpretation["live_execution_enabled"] is False
    assert payload["actual_submit_executed"] is False
    assert payload["safety"]["order_placed"] is False
    assert payload["safety"]["submit_attempted"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False


def test_live_submit_request_with_disabled_live_execution_is_separate_safety_blocker(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(
        tmp_path,
        r267_contract=True,
        reference_price=12000,
        live_execution_enabled=False,
    )

    payload = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        execute_actual_live_submit=True,
        allow_binance_order_endpoint=True,
        confirm_actual_live_submit=r264.LIVE_SUBMIT_CONFIRMATION_PHRASE,
        now=NOW,
    )

    pre = payload["pre_submit_validation"]
    assert payload["status"] == r264.TINY_LIVE_ACTUAL_SUBMIT_BLOCKED
    assert pre["risk_contract_valid"] is True
    assert "live_execution_not_enabled" in pre["blocked_by"]
    assert "risk_contract_config_invalid" not in pre["blocked_by"]
    assert payload["actual_submit_executed"] is False
    assert payload["safety"]["order_placed"] is False
    assert payload["safety"]["submit_attempted"] is False
    assert payload["safety"]["binance_order_endpoint_called"] is False


def test_r267_candidate_notional_above_80_rejected_in_dry_preview(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path, r267_contract=True, reference_price=14000)

    payload = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        dry_run_actual_submit_reconcile=True,
        record_actual_submit_preview=True,
        confirm_actual_submit_dry_preview=r264.DRY_PREVIEW_CONFIRMATION_PHRASE,
        now=NOW,
    )

    pre = payload["pre_submit_validation"]
    interpretation = pre["risk_contract_interpretation"]
    assert payload["status"] == r264.TINY_LIVE_ACTUAL_SUBMIT_BLOCKED
    assert pre["risk_contract_valid"] is False
    assert "candidate_notional_exceeds_position_notional_cap" in interpretation["blocked_by"]
    assert payload["actual_submit_executed"] is False
    assert payload["safety"]["order_placed"] is False


def test_fake_client_successful_exact_three_submit_records_all_three(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    client = r264.FakeBinanceFuturesOrderSubmitClient()
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = r264.build_tiny_live_actual_submit_reconciliation(
            log_dir=log_dir,
            lane_controls_path=lane_path,
            risk_contract_config_path=risk_path,
            execute_actual_live_submit=True,
            allow_binance_order_endpoint=True,
            confirm_actual_live_submit=r264.LIVE_SUBMIT_CONFIRMATION_PHRASE,
            submit_client=client,
            now=NOW,
        )
    urlopen.assert_not_called()
    assert payload["status"] == r264.TINY_LIVE_ACTUAL_SUBMIT_EXECUTED_RECONCILED
    assert payload["submit_result"]["all_three_submitted"] is True
    assert payload["reconciliation"]["all_three_reconciled"] is True
    assert len(client.requests) == 3
    _assert_no_secrets(payload)


def test_fake_client_partial_success_records_critical_recovery_packet_no_extra_orders(tmp_path: Path) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    client = r264.FakeBinanceFuturesOrderSubmitClient(
        [
            {"status": "MOCK_ACCEPTED", "orderId": 1},
            {"status": "REJECTED", "error": "stop rejected"},
        ]
    )
    payload = r264.build_tiny_live_actual_submit_reconciliation(
        log_dir=log_dir,
        lane_controls_path=lane_path,
        risk_contract_config_path=risk_path,
        execute_actual_live_submit=True,
        allow_binance_order_endpoint=True,
        confirm_actual_live_submit=r264.LIVE_SUBMIT_CONFIRMATION_PHRASE,
        submit_client=client,
        now=NOW,
    )
    assert payload["status"] == r264.TINY_LIVE_ACTUAL_SUBMIT_PARTIAL_SUCCESS_CRITICAL
    assert payload["reconciliation"]["critical"] is True
    assert payload["partial_success_recovery_packet"]["required"] is True
    assert payload["partial_success_recovery_packet"]["do_not_resubmit_main"] is True
    assert len(client.requests) == 2


def test_no_real_binance_calls_in_preview_and_no_secrets_in_output(tmp_path: Path, monkeypatch) -> None:
    log_dir, lane_path, risk_path = _fixture(tmp_path)
    monkeypatch.setenv("BINANCE_API_KEY", API_KEY)
    monkeypatch.setenv("BINANCE_API_SECRET", API_SECRET)
    with patch.object(urllib.request, "urlopen") as urlopen:
        payload = r264.build_tiny_live_actual_submit_reconciliation(
            log_dir=log_dir,
            lane_controls_path=lane_path,
            risk_contract_config_path=risk_path,
            now=NOW,
        )
    urlopen.assert_not_called()
    _assert_preview_safety(payload)
    _assert_no_secrets(payload)


def test_api_get_checkpoint_returns_json() -> None:
    client = TestClient(app)
    response = client.get("/tiny-live/actual-submit/reconcile")
    assert response.status_code == 200
    assert "target_scope" in response.json()


def test_api_execute_requires_exact_phrase_and_allow_flag() -> None:
    client = TestClient(app)
    response = client.post(
        "/tiny-live/actual-submit/execute",
        json={"confirm_actual_live_submit": "wrong", "allow_binance_order_endpoint": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["confirmation_valid"] is False
    assert body["actual_submit_executed"] is False


def test_ui_contains_warning_and_no_auto_submit_behavior() -> None:
    html = _operator_ui_html()
    section = html.split('<section id="tinyLiveActualSubmit"', 1)[1].split("</section>", 1)[0]
    assert "no auto-submit" in section
    assert "allow Binance order endpoint" in section
    assert "Execute requires the exact R264 phrase" in section


def _fixture(
    tmp_path: Path,
    *,
    armed: bool = True,
    omit_take_profit: bool = False,
    main_side: str = "SELL",
    reduce_only: bool = True,
    r267_contract: bool = False,
    reference_price: float = 7000,
    live_execution_enabled: bool = True,
) -> tuple[Path, Path, Path]:
    log_dir = tmp_path / "logs"
    lane_path = tmp_path / "lane_controls.json"
    risk_path = tmp_path / "tiny_live_risk_contracts.json"
    _write_json(
        lane_path,
        {
            "lanes": [
                {
                    "symbol": "BTCUSDT",
                    "timeframe": "8m",
                    "direction": "short",
                    "entry_mode": "ladder_close_50_618",
                    "mode": "tiny_live" if armed else "paper",
                    "tiny_live_armed_by_phase": "R263" if armed else None,
                    "experimental_lane_acceptance_recorded": armed,
                }
            ]
        },
    )
    _write_json(
        risk_path,
        {
            "risk_contracts": [
                {
                    "official_lane_key": OFFICIAL,
                    "symbol": "BTCUSDT",
                    "timeframe": "8m",
                    "direction": "short",
                    "entry_mode": "ladder_close_50_618",
                    "max_loss_usdt": 4.44,
                    "max_notional_usdt": 80 if r267_contract else 44,
                    "max_position_notional_usdt": 80 if r267_contract else 44,
                    "tiny_live_contract_mode": "explicit_notional_cap_with_leverage"
                    if r267_contract
                    else "position_notional_cap",
                    "margin_budget_usdt": 8 if r267_contract else 44,
                    "tiny_live_margin_usdt": 8 if r267_contract else 44,
                    "leverage": 10 if r267_contract else 1,
                    "live_execution_enabled": live_execution_enabled,
                }
            ]
        },
    )
    _append_ndjson(log_dir / "tiny_live_percentage_risk_contract_fit.ndjson", _r262b_record())
    _append_ndjson(log_dir / "tiny_live_final_console.ndjson", _r263_record(armed=armed))
    artifact = _signed_artifact(omit_take_profit=omit_take_profit, main_side=main_side, reduce_only=reduce_only)
    _append_ndjson(
        log_dir / "tiny_live_signed_request_write_gate.ndjson",
        {
            "target_scope": {"official_lane_key": OFFICIAL},
            "signed_request_written": True,
            "signed_request_artifact": artifact,
        },
    )
    _append_ndjson(
        log_dir / "tiny_live_executable_payload_write_gate.ndjson",
        {
            "target_scope": {"official_lane_key": OFFICIAL},
            "executable_payload_written": True,
            "executable_payload_artifact": _executable_artifact(
                main_side=main_side,
                reduce_only=reduce_only,
                reference_price=reference_price,
            ),
        },
    )
    return log_dir, lane_path, risk_path


def _r262b_record() -> dict:
    return {
        "target_scope": {"official_lane_key": OFFICIAL},
        "output_validation": {"valid": True, "risk_contract_valid_after": True},
        "contract_fit_sizing_plan": {
            "candidate_qty": 0.006,
            "candidate_notional_usdt": 42,
            "candidate_margin_usdt": 42,
            "candidate_estimated_loss_usdt": 4.44,
            "fits_max_notional": True,
            "fits_max_loss": True,
            "fits_binance_step_size": True,
            "fits_binance_min_notional": True,
        },
    }


def _r263_record(*, armed: bool) -> dict:
    return {
        "target_scope": {"official_lane_key": OFFICIAL},
        "final_console_controls_armed": armed,
        "operator_choice_panel": {"experimental_lane_acceptance_recorded": armed},
        "controls_panel": {"controls_armed": armed},
    }


def _signed_artifact(*, omit_take_profit: bool, main_side: str, reduce_only: bool) -> dict:
    timestamp = int(NOW.timestamp() * 1000)
    signed_requests = {
        "main_order": _signed_request(f"symbol=BTCUSDT&side={main_side}&type=MARKET&quantity=0.006&timestamp={timestamp}"),
        "stop_order": _signed_request(
            f"symbol=BTCUSDT&side=BUY&type=STOP_MARKET&quantity=0.006&stopPrice=64415&reduceOnly={str(reduce_only).lower()}&workingType=MARK_PRICE&timestamp={timestamp}"
        ),
    }
    if not omit_take_profit:
        signed_requests["take_profit_order"] = _signed_request(
            f"symbol=BTCUSDT&side=BUY&type=TAKE_PROFIT_MARKET&quantity=0.006&stopPrice=62195&reduceOnly={str(reduce_only).lower()}&workingType=MARK_PRICE&timestamp={timestamp}"
        )
    return {
        "created_by_phase": "R253B_TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE",
        "official_lane_key": OFFICIAL,
        "signed_request_artifact_id": "r264_test_signed_artifact",
        "signed_requests": signed_requests,
    }


def _signed_request(query_without_signature: str) -> dict:
    return {
        "method": "POST",
        "endpoint": "/fapi/v1/order",
        "base_url": "https://fapi.binance.com",
        "query_string_without_signature": query_without_signature,
        "query_string": f"{query_without_signature}&signature={'a' * 64}",
        "signature": "a" * 64,
        "headers": {"X-MBX-APIKEY": API_KEY},
    }


def _executable_artifact(*, main_side: str, reduce_only: bool, reference_price: float = 7000) -> dict:
    return {
        "created_by_phase": "R253B_TINY_LIVE_FRESH_CONTEXT_SIGNED_REQUEST_REGENERATION_GATE",
        "reference_price": reference_price,
        "main_order": {"symbol": "BTCUSDT", "side": main_side, "type": "MARKET", "quantity": 0.006},
        "stop_order": {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "STOP_MARKET",
            "quantity": 0.006,
            "stopPrice": 64415,
            "reduceOnly": reduce_only,
            "workingType": "MARK_PRICE",
        },
        "take_profit_order": {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "TAKE_PROFIT_MARKET",
            "quantity": 0.006,
            "stopPrice": 62195,
            "reduceOnly": reduce_only,
            "workingType": "MARK_PRICE",
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _append_ndjson(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _assert_preview_safety(payload: dict) -> None:
    safety = payload["safety"]
    for key in (
        "env_written",
        "env_mutated",
        "external_env_file_written",
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
        "live_controls_armed_by_phase",
        "secrets_read",
        "secrets_shown",
        "secrets_persisted",
        "secret_values_in_output",
        "global_live_flags_changed",
        "official_tiny_live_lane_changed",
    ):
        assert safety[key] is False
    assert safety["actual_submit_reconcile_gate"] is True
    assert safety["paper_live_separation_intact"] is True


def _assert_no_secrets(payload: dict) -> None:
    raw = json.dumps(payload, sort_keys=True)
    assert API_KEY not in raw
    assert API_SECRET not in raw
    assert "BINANCE_API_KEY" not in raw
    assert "BINANCE_API_SECRET" not in raw
    for value in os.environ.values():
        if value in {API_KEY, API_SECRET}:
            assert value not in raw
