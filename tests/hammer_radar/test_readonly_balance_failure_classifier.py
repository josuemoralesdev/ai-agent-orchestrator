from __future__ import annotations

import io
import json
import os
import subprocess
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

from src.app.hammer_radar.operator.readonly_balance_check import append_readonly_balance_check_record
from src.app.hammer_radar.operator.readonly_balance_failure_classifier import (
    CONFIRM_READONLY_BALANCE_FAILURE_RECHECK_RECORDING_PHRASE,
    ERROR_BODY_NOT_AVAILABLE,
    HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE,
    HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION,
    HTTP_404_OR_ENDPOINT_MISMATCH,
    LEDGER_FILENAME,
    READONLY_BALANCE_FAILURE_RECHECK_RECORDED,
    READONLY_BALANCE_FAILURE_RECHECK_REJECTED,
    UNKNOWN_HTTP_ERROR,
    build_readonly_balance_failure_recheck,
    classify_readonly_balance_failure,
    load_readonly_balance_failure_recheck_records,
    sanitize_readonly_balance_error,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
LANE_8M_SHORT = "BTCUSDT|8m|short|ladder_close_50_618"


def test_preview_writes_no_record(tmp_path: Path) -> None:
    _append_failed_balance_check(tmp_path, http_status=403, binance_code=-2015, binance_message="Invalid API-key, IP, or permissions.")

    payload = build_readonly_balance_failure_recheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    assert payload["record_recheck_requested"] is False
    assert payload["confirmation_valid"] is False
    assert payload["recheck_recorded"] is False
    assert payload["recheck_id"] is None
    assert not (tmp_path / "logs" / LEDGER_FILENAME).exists()


def test_wrong_confirmation_rejects_record(tmp_path: Path) -> None:
    _append_failed_balance_check(tmp_path, http_status=403, binance_code=-2015, binance_message="Invalid API-key, IP, or permissions.")

    payload = build_readonly_balance_failure_recheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        record_recheck=True,
        confirm_readonly_balance_failure_recheck="wrong",
        now=NOW,
    )

    assert payload["status"] == READONLY_BALANCE_FAILURE_RECHECK_REJECTED
    assert payload["confirmation_valid"] is False
    assert payload["recheck_recorded"] is False
    assert load_readonly_balance_failure_recheck_records(log_dir=tmp_path / "logs", limit=0) == []


def test_exact_confirmation_records_recheck_only(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path / "lane_controls.json")
    before = config_path.read_text(encoding="utf-8")
    _append_failed_balance_check(tmp_path, http_status=403, binance_code=-2015, binance_message="Invalid API-key, IP, or permissions.")

    payload = build_readonly_balance_failure_recheck(
        log_dir=tmp_path / "logs",
        config_path=config_path,
        record_recheck=True,
        confirm_readonly_balance_failure_recheck=CONFIRM_READONLY_BALANCE_FAILURE_RECHECK_RECORDING_PHRASE,
        now=NOW,
    )
    records = load_readonly_balance_failure_recheck_records(log_dir=tmp_path / "logs", limit=0)

    assert payload["status"] == READONLY_BALANCE_FAILURE_RECHECK_RECORDED
    assert payload["confirmation_valid"] is True
    assert payload["recheck_recorded"] is True
    assert len(records) == 1
    assert records[0]["event_type"] == "READONLY_BALANCE_FAILURE_RECHECK"
    assert config_path.read_text(encoding="utf-8") == before


def test_http_401_403_classified_permission_or_ip_restriction() -> None:
    assert _classification(401) == HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION
    assert _classification(403) == HTTP_401_OR_403_KEY_PERMISSION_OR_IP_RESTRICTION


def test_http_400_classified_timestamp_recvwindow_or_signature() -> None:
    assert _classification(400) == HTTP_400_TIMESTAMP_RECVWINDOW_OR_SIGNATURE


def test_http_404_classified_endpoint_mismatch() -> None:
    assert _classification(404) == HTTP_404_OR_ENDPOINT_MISMATCH


def test_missing_error_body_classified_error_body_not_available() -> None:
    classification = classify_readonly_balance_failure(
        last_balance_check_summary={
            "error_type": "HTTPError",
            "sanitized_http_status": None,
            "sanitized_binance_code": None,
            "sanitized_binance_message": None,
        }
    )

    assert classification == ERROR_BODY_NOT_AVAILABLE


def test_unknown_httperror_classified_unknown_http_error() -> None:
    classification = classify_readonly_balance_failure(
        last_balance_check_summary={
            "error_type": "HTTPError",
            "sanitized_http_status": 409,
            "sanitized_binance_code": 9999,
            "sanitized_binance_message": "unmapped readonly failure",
        }
    )

    assert classification == UNKNOWN_HTTP_ERROR


def test_secrets_and_signature_never_appear_in_sanitized_output() -> None:
    error = urllib.error.HTTPError(
        "https://fapi.binance.com/fapi/v2/account?timestamp=1&signature=raw-signature-secret",
        400,
        "Bad Request",
        {},
        io.BytesIO(b'{"code":-1022,"msg":"Signature for this request is not valid. signature=raw-signature-secret"}'),
    )

    payload = sanitize_readonly_balance_error(error, endpoint_family="futures_account_readonly")
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["http_status"] == 400
    assert payload["binance_code"] == -1022
    assert "raw-signature-secret" not in rendered
    assert "signature=<redacted>" in rendered
    assert "fapi.binance.com" not in rendered


def test_no_order_live_transfer_or_withdraw_commands_emitted(tmp_path: Path) -> None:
    _append_failed_balance_check(tmp_path, http_status=403, binance_code=-2015, binance_message="Invalid API-key, IP, or permissions.")

    payload = build_readonly_balance_failure_recheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )
    safe_commands = "\n".join(payload["safe_recheck_commands"]).lower()

    assert "readonly-balance-failure-recheck" in safe_commands
    assert "readonly-balance-check" in safe_commands
    assert "live-connector-submit" not in safe_commands
    assert " order endpoint" not in safe_commands
    assert "transfer" not in safe_commands
    assert "withdraw" not in safe_commands
    assert "signed order request" in payload["do_not_run_yet"]
    assert "transfer" in payload["do_not_run_yet"]
    assert "withdraw" in payload["do_not_run_yet"]


def test_safety_flags_clean(tmp_path: Path) -> None:
    _append_failed_balance_check(tmp_path, http_status=403, binance_code=-2015, binance_message="Invalid API-key, IP, or permissions.")

    payload = build_readonly_balance_failure_recheck(
        log_dir=tmp_path / "logs",
        config_path=_write_config(tmp_path / "lane_controls.json"),
        now=NOW,
    )

    for key, value in payload["safety"].items():
        if key == "paper_live_separation_intact":
            assert value is True
        else:
            assert value is False, key


def test_cli_exists_and_preview_returns_expected_shape(tmp_path: Path) -> None:
    _append_failed_balance_check(tmp_path, http_status=403, binance_code=-2015, binance_message="Invalid API-key, IP, or permissions.")
    result = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.app.hammer_radar.operator.inspect",
            "--log-dir",
            str(tmp_path / "logs"),
            "readonly-balance-failure-recheck",
            "--latest-balance-checks",
            "50",
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
    assert payload["target_family"]["lane_key"] == LANE_8M_SHORT
    assert "last_balance_check_summary" in payload
    assert "failure_classification" in payload
    assert "readonly-balance-failure-recheck" in help_result.stdout


def _classification(status: int) -> str:
    return classify_readonly_balance_failure(
        last_balance_check_summary={
            "error_type": "HTTPError",
            "sanitized_http_status": status,
            "sanitized_binance_code": None,
            "sanitized_binance_message": "failure",
        }
    )


def _append_failed_balance_check(
    tmp_path: Path,
    *,
    http_status: int | None,
    binance_code: int | None,
    binance_message: str | None,
) -> None:
    append_readonly_balance_check_record(
        {
            "status": "READONLY_BALANCE_CHECK_BLOCKED",
            "generated_at": NOW.isoformat(),
            "record_balance_check_requested": False,
            "confirmation_valid": False,
            "allow_readonly_network_check": True,
            "target_family": {
                "lane_key": LANE_8M_SHORT,
                "symbol": "BTCUSDT",
                "timeframe": "8m",
                "direction": "short",
                "entry_mode": "ladder_close_50_618",
                "current_mode": "paper",
            },
            "readonly_preflight": {},
            "balance_check": {
                "network_check_attempted": True,
                "balance_check_attempted": True,
                "signed_readonly_request_created": True,
                "funding_status": "READONLY_BALANCE_CHECK_FAILED",
                "error": "HTTPError",
                "error_type": "HTTPError",
                "http_status": http_status,
                "binance_code": binance_code,
                "binance_message": binance_message,
                "endpoint_family": "futures_account_readonly",
            },
            "balance_readiness": "READONLY_BALANCE_CHECK_FAILED",
            "safety": {"signed_trading_request_created": False},
        },
        log_dir=tmp_path / "logs",
    )


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lanes = [
        _lane("13m", "long", "tiny_live"),
        _lane("44m", "long", "tiny_live"),
        _lane("8m", "long", "paper"),
        _lane("4m", "long", "paper"),
        _lane("4m", "short", "paper"),
        _lane("8m", "short", "paper"),
        _lane("13m", "short", "paper"),
        _lane("44m", "short", "paper"),
    ]
    path.write_text(json.dumps({"schema_version": "1.0", "default_mode": "disabled", "lanes": lanes}), encoding="utf-8")
    return path


def _lane(timeframe: str, direction: str, mode: str) -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "direction": direction,
        "entry_mode": "ladder_close_50_618",
        "mode": mode,
        "max_daily_trades": 1,
        "max_daily_loss_pct": 0.15,
        "freshness_seconds": 60,
        "cooldown_after_loss_minutes": 120,
        "require_protective_orders": True,
    }
